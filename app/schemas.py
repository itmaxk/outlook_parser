from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel


class MatchCondition(BaseModel):
    field: str  # subject, body, sender, to, cc, importance, categories
    operator: str  # contains, not_contains, equals, starts_with, ends_with, regex, pattern
    value: str
    case_sensitive: bool = False


class RuleCreate(BaseModel):
    name: str
    enabled: bool = True
    priority: int = 0
    conditions: list[MatchCondition] = []
    action_url: str
    action_method: str = "GET"
    action_body: Optional[str] = None


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[list[MatchCondition]] = None
    action_url: Optional[str] = None
    action_method: Optional[str] = None
    action_body: Optional[str] = None


class RuleRead(BaseModel):
    id: int
    name: str
    enabled: bool
    priority: int
    conditions: list[MatchCondition]
    action_url: str
    action_method: str
    action_body: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class LogRead(BaseModel):
    id: int
    received_at: datetime.datetime
    entry_id: Optional[str]
    subject: Optional[str]
    sender: Optional[str]
    rule_id: Optional[int]
    rule_name: Optional[str]
    matched: bool
    action_url: Optional[str]
    http_status: Optional[int]
    error_message: Optional[str]
    raw_vars: Optional[str]

    model_config = {"from_attributes": True}
