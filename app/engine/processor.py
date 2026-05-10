from __future__ import annotations

import asyncio
import json
import logging
import re

from app.db import SessionLocal
from app.models import Rule, ProcessingLog
from app.engine.matcher import match_rule
from app.engine.actions import execute_action

logger = logging.getLogger(__name__)

MR_URL_RE = re.compile(r"https?://\S+/-/merge_requests/\d+\S*", re.IGNORECASE)
MR_IID_RE = re.compile(
    r"(?:\bmr\b|\bmerge\s+request\b|!|ai\s+review)\D*(\d+)",
    re.IGNORECASE,
)


def _load_enabled_rules() -> list[Rule]:
    session = SessionLocal()
    try:
        return session.query(Rule).filter(Rule.enabled.is_(True)).order_by(Rule.priority.desc()).all()
    finally:
        session.close()


def _save_log(log: ProcessingLog):
    session = SessionLocal()
    try:
        session.add(log)
        session.commit()
    finally:
        session.close()


def _infer_mr_input(email_data: dict[str, str]) -> str:
    text = "\n".join(
        email_data.get(field, "")
        for field in ("subject", "body")
        if email_data.get(field)
    )
    url_match = MR_URL_RE.search(text)
    if url_match:
        return url_match.group(0).rstrip(".,;)")

    iid_match = MR_IID_RE.search(text)
    if iid_match:
        return iid_match.group(1)

    return ""


def _build_action_variables(email_data: dict[str, str], extracted: dict[str, str]) -> dict[str, str]:
    variables = {
        key.upper(): value
        for key, value in email_data.items()
        if isinstance(value, str)
    }
    variables.update(extracted)
    if not variables.get("MR_INPUT"):
        mr_input = _infer_mr_input(email_data)
        if mr_input:
            variables["MR_INPUT"] = mr_input
    return variables


async def _process_async(email_data: dict[str, str]):
    rules = _load_enabled_rules()
    entry_id = email_data.get("entry_id")
    subject = email_data.get("subject", "")
    sender = email_data.get("sender", "")

    if not rules:
        logger.debug("No enabled rules, skipping email '%s'", subject)
        _save_log(ProcessingLog(
            entry_id=entry_id, subject=subject, sender=sender,
            matched=False, error_message="No enabled rules",
        ))
        return

    matched_any = False
    for rule in rules:
        conditions = json.loads(rule.conditions_json)
        result = match_rule(email_data, conditions)

        if result.matched:
            matched_any = True
            logger.info("Rule '%s' matched email '%s', vars=%s", rule.name, subject, result.variables)
            action_variables = _build_action_variables(email_data, result.variables)

            action_result = await execute_action(
                rule.action_url, rule.action_method, rule.action_body, action_variables,
            )

            _save_log(ProcessingLog(
                entry_id=entry_id, subject=subject, sender=sender,
                rule_id=rule.id, rule_name=rule.name, matched=True,
                action_url=action_result.url,
                http_status=action_result.status_code,
                error_message=action_result.error,
                raw_vars=json.dumps(action_variables, ensure_ascii=False) if action_variables else None,
            ))

    if not matched_any:
        _save_log(ProcessingLog(
            entry_id=entry_id, subject=subject, sender=sender,
            matched=False,
        ))


def process_email(email_data: dict[str, str]):
    """Entry point called from the COM watcher thread."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_process_async(email_data))
        loop.close()
    except Exception:
        logger.exception("Error processing email '%s'", email_data.get("subject", ""))
