from __future__ import annotations

import logging
import queue
import threading
import time

import pythoncom
import win32com.client

from app.outlook.extractor import extract_email_data, email_data_to_dict
from app.engine.processor import process_email

logger = logging.getLogger(__name__)

_handler_ref = None  # prevent GC
_mail_queue: queue.Queue = queue.Queue()
_stop_event = threading.Event()


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
    logger.info("Connected to Outlook")
    return outlook, namespace


def _drain_and_process(namespace):
    """Process all queued entry IDs."""
    while not _mail_queue.empty():
        try:
            entry_id = _mail_queue.get_nowait()
        except queue.Empty:
            break

        try:
            mail_item = namespace.GetItemFromID(entry_id)
            data = extract_email_data(mail_item)
            email_dict = email_data_to_dict(data)
            logger.info("Processing email: '%s' from %s", data.subject, data.sender)
            process_email(email_dict)
        except Exception:
            logger.exception("Error processing mail entry %s", entry_id)


def _watcher_loop():
    """Main loop for the COM watcher thread."""
    global _handler_ref

    pythoncom.CoInitialize()
    try:
        outlook = None
        namespace = None

        while not _stop_event.is_set():
            # Connect / reconnect
            if outlook is None:
                try:
                    outlook, namespace = _connect_outlook()
                    _handler_ref = outlook
                except Exception:
                    logger.warning("Cannot connect to Outlook, retrying in 30s...")
                    _stop_event.wait(30)
                    continue

            # Pump COM messages and process queue
            try:
                pythoncom.PumpWaitingMessages()
                _drain_and_process(namespace)
            except Exception:
                logger.exception("Error in watcher loop, reconnecting...")
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
