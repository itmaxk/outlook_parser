import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import actions
from app.engine.processor import _build_action_variables
from app.api import logs
from app.engine.actions import ActionResult
from app.models import ProcessingLog, Rule


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


def test_parse_json_body_accepts_escaped_json_from_curl():
    assert actions._parse_json_body(
        '{\\"mr_input\\":\\"123\\",\\"recipients\\":[\\"author@example.com\\"]}'
    ) == {
        "mr_input": "123",
        "recipients": ["author@example.com"],
    }


def test_parse_json_body_accepts_json_string_with_object_inside():
    assert actions._parse_json_body(
        '"{\\"mr_input\\":\\"123\\",\\"recipients\\":[\\"author@example.com\\"]}"'
    ) == {
        "mr_input": "123",
        "recipients": ["author@example.com"],
    }


def test_replay_log_action_uses_current_rule_not_saved_action_url(monkeypatch):
    captured = {}

    async def fake_execute_action(url, method, body, variables):
        captured["url"] = url
        captured["method"] = method
        captured["body"] = body
        captured["variables"] = variables
        return ActionResult(url="http://review.local/new/123", status_code=202)

    monkeypatch.setattr(logs, "execute_action", fake_execute_action)

    old_log = ProcessingLog(
        entry_id="entry-1",
        subject="AI review 123",
        sender="author@example.com",
        rule_id=7,
        rule_name="Old review rule",
        matched=True,
        action_url="http://review.local/old/123",
        http_status=200,
        raw_vars='{"MR_INPUT":"123","SENDER":"author@example.com"}',
    )
    current_rule = Rule(
        id=7,
        name="Updated review rule",
        conditions_json='[{"field":"subject","operator":"pattern","value":"AI review {MR_INPUT}","case_sensitive":false}]',
        action_url="http://review.local/new/{MR_INPUT}",
        action_method="POST",
        action_body='{"recipients":["{SENDER}"]}',
    )

    replayed = asyncio.run(logs._replay_log_action(old_log, current_rule))

    assert captured == {
        "url": "http://review.local/new/{MR_INPUT}",
        "method": "POST",
        "body": '{"recipients":["{SENDER}"]}',
        "variables": {
            "ENTRY_ID": "entry-1",
            "SUBJECT": "AI review 123",
            "BODY": "",
            "SENDER": "author@example.com",
            "TO": "",
            "CC": "",
            "IMPORTANCE": "",
            "CATEGORIES": "",
            "MR_INPUT": "123",
        },
    }
    assert replayed.rule_id == 7
    assert replayed.rule_name == "Updated review rule"
    assert replayed.action_url == "http://review.local/new/123"
    assert replayed.http_status == 202
