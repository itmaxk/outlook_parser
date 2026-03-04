from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    entry_id: str
    subject: str
    body: str
    sender: str
    to: str
    cc: str
    importance: str
    categories: str


def _resolve_sender(mail_item) -> str:
    """Resolve Exchange DN to SMTP address if possible."""
    try:
        sender_type = getattr(mail_item, "SenderEmailType", "")
        if sender_type == "EX":
            exchange_user = mail_item.Sender.GetExchangeUser()
            if exchange_user:
                return exchange_user.PrimarySmtpAddress
        return mail_item.SenderEmailAddress or ""
    except Exception:
        logger.debug("Could not resolve sender SMTP, using SenderEmailAddress")
        return getattr(mail_item, "SenderEmailAddress", "") or ""


def _get_recipients(mail_item, recipient_type: int) -> str:
    """Get recipients of a specific type (1=To, 2=CC, 3=BCC) as semicolon-separated string."""
    try:
        recipients = mail_item.Recipients
        addrs = []
        for i in range(1, recipients.Count + 1):
            r = recipients.Item(i)
            if r.Type == recipient_type:
                try:
                    exchange_user = r.AddressEntry.GetExchangeUser()
                    if exchange_user and exchange_user.PrimarySmtpAddress:
                        addrs.append(exchange_user.PrimarySmtpAddress)
                        continue
                except Exception:
                    pass
                addrs.append(r.Address)
        return "; ".join(addrs)
    except Exception:
        return ""


IMPORTANCE_MAP = {0: "low", 1: "normal", 2: "high"}


def extract_email_data(mail_item) -> EmailData:
    """Extract relevant data from a COM MailItem object."""
    importance_val = getattr(mail_item, "Importance", 1)
    return EmailData(
        entry_id=getattr(mail_item, "EntryID", ""),
        subject=getattr(mail_item, "Subject", "") or "",
        body=getattr(mail_item, "Body", "") or "",
        sender=_resolve_sender(mail_item),
        to=_get_recipients(mail_item, 1),
        cc=_get_recipients(mail_item, 2),
        importance=IMPORTANCE_MAP.get(importance_val, "normal"),
        categories=getattr(mail_item, "Categories", "") or "",
    )


def email_data_to_dict(data: EmailData) -> dict[str, str]:
    return {
        "entry_id": data.entry_id,
        "subject": data.subject,
        "body": data.body,
        "sender": data.sender,
        "to": data.to,
        "cc": data.cc,
        "importance": data.importance,
        "categories": data.categories,
    }
