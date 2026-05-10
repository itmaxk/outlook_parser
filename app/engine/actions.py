from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    url: str
    status_code: Optional[int] = None
    error: Optional[str] = None


def render_template(template: str, variables: dict[str, str]) -> str:
    """Replace {VAR} placeholders in template with variable values."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def _parse_json_body(body: str):
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(body.replace('\\"', '"'))
        except json.JSONDecodeError:
            return None

    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except json.JSONDecodeError:
            return None
    return parsed


async def execute_action(
    url_template: str,
    method: str,
    body_template: Optional[str],
    variables: dict[str, str],
) -> ActionResult:
    url = render_template(url_template, variables)
    body = render_template(body_template, variables) if body_template else None

    try:
        async with httpx.AsyncClient(timeout=config.ACTION_TIMEOUT_SECONDS) as client:
            request_kwargs = {}
            if body:
                json_body = _parse_json_body(body)
                if json_body is None:
                    request_kwargs["content"] = body
                else:
                    request_kwargs["json"] = json_body

            response = await client.request(method, url, **request_kwargs)
            logger.info("Action %s %s -> %d", method, url, response.status_code)
            error = response.text[:1000] if response.status_code >= 400 else None
            return ActionResult(url=url, status_code=response.status_code, error=error)
    except Exception as e:
        logger.error("Action %s %s failed: %s", method, url, e)
        return ActionResult(url=url, error=str(e))
