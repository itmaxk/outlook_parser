from __future__ import annotations

import datetime as dt
import json
import logging
import os
import queue
import threading
import time

import pythoncom
import win32com.client

from app.db import SessionLocal
from app.engine.processor import process_email
from app.models import ProcessingLog
from app.outlook.extractor import email_data_to_dict, extract_email_data
from config import DATA_DIR

logger = logging.getLogger(__name__)

_handler_ref = None  # prevent GC
_mail_queue: queue.Queue = queue.Queue()
_stop_event = threading.Event()

INBOX_FOLDER = 6
STATE_FILE = os.path.join(DATA_DIR, "outlook_watcher_state.json")
CONNECTION_CHECK_SECONDS = 10


class OutlookHandler:
    """COM event handler for Outlook.Application events."""

    def OnNewMailEx(self, entry_id_collection):
        """Called by Outlook when new mail arrives."""
        try:
            entry_ids = entry_id_collection.split(",")
            for eid in entry_ids:
                _mail_queue.put(eid.strip())
        except Exception:
            logger.exception("Error in OnNewMailEx")


def _connect_outlook():
    """Try to connect to Outlook and return (outlook, namespace) or raise."""
    outlook = win32com.client.DispatchWithEvents("Outlook.Application", OutlookHandler)
    namespace = outlook.GetNamespace("MAPI")
    namespace.GetDefaultFolder(INBOX_FOLDER)
    logger.info("Connected to Outlook")
    return outlook, namespace


def _normalize_datetime(value: dt.datetime) -> dt.datetime:
    """Return a naive datetime so Python and COM datetimes can be compared."""
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.replace(microsecond=0)


def _load_last_checked_at() -> dt.datetime:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        value = raw.get("last_checked_at")
        if value:
            return _normalize_datetime(dt.datetime.fromisoformat(value))
    except FileNotFoundError:
        pass
    except Exception:
        logger.warning("Could not load Outlook watcher state", exc_info=True)

    last_checked_at = _normalize_datetime(dt.datetime.now())
    _save_last_checked_at(last_checked_at)
    return last_checked_at


def _save_last_checked_at(value: dt.datetime):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_checked_at": _normalize_datetime(value).isoformat()}, f)


def _is_already_processed(entry_id: str) -> bool:
    if not entry_id:
        return False

    session = SessionLocal()
    try:
        return session.query(ProcessingLog.id).filter(ProcessingLog.entry_id == entry_id).first() is not None
    finally:
        session.close()


def _process_mail_item(mail_item, *, skip_processed: bool = False):
    data = extract_email_data(mail_item)
    if skip_processed and _is_already_processed(data.entry_id):
        logger.debug("Skipping already processed email entry %s", data.entry_id)
        return

    email_dict = email_data_to_dict(data)
    logger.info("Processing email: '%s' from %s", data.subject, data.sender)
    process_email(email_dict)


def _drain_and_process(namespace):
    """Process all queued entry IDs."""
    while not _mail_queue.empty():
        try:
            entry_id = _mail_queue.get_nowait()
        except queue.Empty:
            break

        try:
            mail_item = namespace.GetItemFromID(entry_id)
            _process_mail_item(mail_item, skip_processed=True)
        except Exception:
            logger.exception("Error processing mail entry %s", entry_id)


def _scan_inbox_since(namespace, since: dt.datetime) -> dt.datetime:
    """Scan Inbox from the saved checkpoint to recover messages missed while disconnected."""
    scan_started_at = _normalize_datetime(dt.datetime.now())
    since = _normalize_datetime(since)

    logger.info("Scanning Outlook Inbox since %s", since.isoformat(sep=" "))
    inbox = namespace.GetDefaultFolder(INBOX_FOLDER)
    items = inbox.Items
    items.Sort("[ReceivedTime]", True)

    scanned = 0
    processed = 0
    for item in items:
        received_at = getattr(item, "ReceivedTime", None)
        if not received_at:
            continue

        received_at = _normalize_datetime(received_at)
        if received_at < since:
            break

        scanned += 1
        try:
            before_processed = _is_already_processed(getattr(item, "EntryID", ""))
            _process_mail_item(item, skip_processed=True)
            if not before_processed:
                processed += 1
        except Exception:
            logger.exception("Error processing mail received at %s during Inbox scan", received_at)

    _save_last_checked_at(scan_started_at)
    logger.info("Inbox scan complete: scanned=%s, new=%s, checkpoint=%s", scanned, processed, scan_started_at.isoformat(sep=" "))
    return scan_started_at


def _check_connection(namespace):
    """Touch Outlook through COM so a dead/restarted Outlook process is detected."""
    namespace.GetDefaultFolder(INBOX_FOLDER).EntryID


def _watcher_loop():
    """Main loop for the COM watcher thread."""
    global _handler_ref

    pythoncom.CoInitialize()
    try:
        outlook = None
        namespace = None
        last_checked_at = _load_last_checked_at()
        next_connection_check_at = 0.0

        while not _stop_event.is_set():
            # Connect / reconnect
            if outlook is None:
                try:
                    outlook, namespace = _connect_outlook()
                    _handler_ref = outlook
                    last_checked_at = _scan_inbox_since(namespace, last_checked_at)
                    next_connection_check_at = time.monotonic() + CONNECTION_CHECK_SECONDS
                except Exception:
                    logger.warning("Cannot connect to Outlook, retrying in 30s...", exc_info=True)
                    outlook = None
                    namespace = None
                    _handler_ref = None
                    _stop_event.wait(30)
                    continue

            # Pump COM messages and process queue
            try:
                pythoncom.PumpWaitingMessages()
                _drain_and_process(namespace)

                if time.monotonic() >= next_connection_check_at:
                    _check_connection(namespace)
                    last_checked_at = _scan_inbox_since(namespace, last_checked_at)
                    next_connection_check_at = time.monotonic() + CONNECTION_CHECK_SECONDS
            except Exception:
                logger.exception("Outlook connection lost or watcher loop failed, reconnecting...")
                outlook = None
                namespace = None
                _handler_ref = None
                _stop_event.wait(5)
                continue

            _stop_event.wait(0.5)
    finally:
        pythoncom.CoUninitialize()


def start_watcher():
    """Start the Outlook watcher in a daemon thread."""
    _stop_event.clear()
    t = threading.Thread(target=_watcher_loop, name="outlook-watcher", daemon=True)
    t.start()
    logger.info("Outlook watcher thread started")
    return t


def stop_watcher():
    """Signal the watcher to stop."""
    _stop_event.set()
    logger.info("Outlook watcher stop requested")
