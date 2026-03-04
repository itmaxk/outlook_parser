from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ProcessingLog
from app.schemas import LogRead

router = APIRouter(prefix="/api/logs", tags=["logs"])


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


@router.delete("", status_code=204)
def clear_logs(session: Session = Depends(get_session)):
    session.query(ProcessingLog).delete()
    session.commit()
