from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Rule
from app.schemas import RuleCreate, RuleRead, RuleUpdate, MatchCondition

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _rule_to_read(rule: Rule) -> RuleRead:
    conditions = [MatchCondition(**c) for c in json.loads(rule.conditions_json)]
    return RuleRead(
        id=rule.id,
        name=rule.name,
        enabled=rule.enabled,
        priority=rule.priority,
        conditions=conditions,
        action_url=rule.action_url,
        action_method=rule.action_method,
        action_body=rule.action_body,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("", response_model=list[RuleRead])
def list_rules(
    enabled: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    q = session.query(Rule).order_by(Rule.priority.desc())
    if enabled is not None:
        q = q.filter(Rule.enabled == enabled)
    return [_rule_to_read(r) for r in q.all()]


@router.post("", response_model=RuleRead, status_code=201)
def create_rule(data: RuleCreate, session: Session = Depends(get_session)):
    rule = Rule(
        name=data.name,
        enabled=data.enabled,
        priority=data.priority,
        conditions_json=json.dumps([c.model_dump() for c in data.conditions], ensure_ascii=False),
        action_url=data.action_url,
        action_method=data.action_method,
        action_body=data.action_body,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return _rule_to_read(rule)


@router.get("/{rule_id}", response_model=RuleRead)
def get_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _rule_to_read(rule)


@router.put("/{rule_id}", response_model=RuleRead)
def update_rule_full(rule_id: int, data: RuleCreate, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.name = data.name
    rule.enabled = data.enabled
    rule.priority = data.priority
    rule.conditions_json = json.dumps([c.model_dump() for c in data.conditions], ensure_ascii=False)
    rule.action_url = data.action_url
    rule.action_method = data.action_method
    rule.action_body = data.action_body
    session.commit()
    session.refresh(rule)
    return _rule_to_read(rule)


@router.patch("/{rule_id}", response_model=RuleRead)
def update_rule_partial(rule_id: int, data: RuleUpdate, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if data.name is not None:
        rule.name = data.name
    if data.enabled is not None:
        rule.enabled = data.enabled
    if data.priority is not None:
        rule.priority = data.priority
    if data.conditions is not None:
        rule.conditions_json = json.dumps([c.model_dump() for c in data.conditions], ensure_ascii=False)
    if data.action_url is not None:
        rule.action_url = data.action_url
    if data.action_method is not None:
        rule.action_method = data.action_method
    if data.action_body is not None:
        rule.action_body = data.action_body

    session.commit()
    session.refresh(rule)
    return _rule_to_read(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    session.delete(rule)
    session.commit()
