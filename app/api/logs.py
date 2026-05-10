from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.engine.actions import execute_action
from app.engine.matcher import match_rule
from app.engine.processor import _build_action_variables
from app.models import ProcessingLog, Rule
from app.schemas import LogRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _log_vars(log: ProcessingLog) -> dict[str, str]:
    if not log.raw_vars:
        return {}
    try:
        data = json.loads(log.raw_vars)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Log variables are corrupted") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Log variables are not an object")
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _email_data_from_log(log: ProcessingLog, previous_vars: dict[str, str]) -> dict[str, str]:
    return {
        "entry_id": log.entry_id or previous_vars.get("ENTRY_ID", ""),
        "subject": log.subject or previous_vars.get("SUBJECT", ""),
        "body": previous_vars.get("BODY", ""),
        "sender": log.sender or previous_vars.get("SENDER", ""),
        "to": previous_vars.get("TO", ""),
        "cc": previous_vars.get("CC", ""),
        "importance": previous_vars.get("IMPORTANCE", ""),
        "categories": previous_vars.get("CATEGORIES", ""),
    }


def _conditions(rule: Rule) -> list[dict]:
    try:
        data = json.loads(rule.conditions_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Current rule conditions are corrupted") from exc
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="Current rule conditions are not a list")
    return data


def _replay_vars(log: ProcessingLog, rule: Rule) -> dict[str, str]:
    previous_vars = _log_vars(log)
    email_data = _email_data_from_log(log, previous_vars)
    match = match_rule(email_data, _conditions(rule))
    if not match.matched:
        raise HTTPException(
            status_code=400,
            detail="Log data does not match the current rule conditions",
        )
    return _build_action_variables(email_data, match.variables)


async def _replay_log_action(log: ProcessingLog, rule: Rule) -> ProcessingLog:
    variables = _replay_vars(log, rule)
    action_result = await execute_action(
        rule.action_url,
        rule.action_method,
        rule.action_body,
        variables,
    )

    return ProcessingLog(
        entry_id=log.entry_id,
        subject=log.subject,
        sender=log.sender,
        rule_id=rule.id,
        rule_name=rule.name,
        matched=True,
        action_url=action_result.url,
        http_status=action_result.status_code,
        error_message=action_result.error,
        raw_vars=json.dumps(variables, ensure_ascii=False) if variables else None,
    )


@router.get("", response_model=list[LogRead])
def list_logs(
    matched: Optional[bool] = None,
    rule_id: Optional[int] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    q = session.query(ProcessingLog).order_by(ProcessingLog.id.desc())
    if matched is not None:
        q = q.filter(ProcessingLog.matched == matched)
    if rule_id is not None:
        q = q.filter(ProcessingLog.rule_id == rule_id)
    return q.offset(offset).limit(limit).all()


@router.post("/{log_id}/replay", response_model=LogRead)
async def replay_log(log_id: int, session: Session = Depends(get_session)):
    log = session.get(ProcessingLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    if not log.rule_id:
        raise HTTPException(status_code=400, detail="Log has no rule to replay")

    rule = session.get(Rule, log.rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Current rule not found")

    replay_log_entry = await _replay_log_action(log, rule)
    session.add(replay_log_entry)
    session.commit()
    session.refresh(replay_log_entry)
    return replay_log_entry


@router.delete("", status_code=204)
def clear_logs(session: Session = Depends(get_session)):
    session.query(ProcessingLog).delete()
    session.commit()
