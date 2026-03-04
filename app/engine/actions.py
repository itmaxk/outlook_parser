from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

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


async def execute_action(
    url_template: str,
    method: str,
    body_template: Optional[str],
    variables: dict[str, str],
) -> ActionResult:
    url = render_template(url_template, variables)
    body = render_template(body_template, variables) if body_template else None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, content=body)
            logger.info("Action %s %s -> %d", method, url, response.status_code)
            return ActionResult(url=url, status_code=response.status_code)
    except Exception as e:
        logger.error("Action %s %s failed: %s", method, url, e)
        return ActionResult(url=url, error=str(e))
