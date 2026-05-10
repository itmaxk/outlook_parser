import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import actions
from app.engine.processor import _build_action_variables


def test_build_action_variables_adds_email_fields_and_keeps_extracted_vars():
    variables = _build_action_variables(
        {
            "sender": "author@example.com",
            "subject": "AI review 123",
            "body": "MR 123",
        },
        {"MR_ID": "123"},
    )

    assert variables["SENDER"] == "author@example.com"
    assert variables["SUBJECT"] == "AI review 123"
    assert variables["BODY"] == "MR 123"
    assert variables["MR_ID"] == "123"


def test_execute_action_sends_valid_json_body_as_json(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return Response()

    monkeypatch.setattr(actions.httpx, "AsyncClient", Client)

    result = asyncio.run(actions.execute_action(
        "http://localhost/api/review/{MR_ID}",
        "POST",
        '{"recipients":["{SENDER}"],"mr_input":"{MR_ID}"}',
        {"MR_ID": "123", "SENDER": "author@example.com"},
    ))

    assert result.status_code == 200
    assert captured["method"] == "POST"
    assert captured["url"] == "http://localhost/api/review/123"
    assert captured["kwargs"] == {
        "json": {"recipients": ["author@example.com"], "mr_input": "123"}
    }
