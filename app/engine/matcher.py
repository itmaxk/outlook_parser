from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MatchResult:
    matched: bool
    variables: dict[str, str] = field(default_factory=dict)


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Convert a pattern like 'Sonar {ID}' to a compiled regex with named groups."""
    parts = re.split(r"\{(\w+)\}", pattern)
    regex_parts: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            regex_parts.append(re.escape(part))
        else:
            regex_parts.append(f"(?P<{part}>.+?)")
    return re.compile("^" + "".join(regex_parts) + "$")


def _get_field_value(email_data: dict[str, str], field_name: str) -> str:
    return email_data.get(field_name, "")


def _check_condition(value: str, operator: str, pattern: str, case_sensitive: bool) -> MatchResult:
    if not case_sensitive and operator != "regex":
        value = value.lower()
        pattern_cmp = pattern.lower()
    else:
        pattern_cmp = pattern

    if operator == "contains":
        return MatchResult(matched=pattern_cmp in value)
    elif operator == "not_contains":
        return MatchResult(matched=pattern_cmp not in value)
    elif operator == "equals":
        return MatchResult(matched=value == pattern_cmp)
    elif operator == "starts_with":
        return MatchResult(matched=value.startswith(pattern_cmp))
    elif operator == "ends_with":
        return MatchResult(matched=value.endswith(pattern_cmp))
    elif operator == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        m = re.search(pattern, value, flags)
        if m:
            return MatchResult(matched=True, variables=m.groupdict())
        return MatchResult(matched=False)
    elif operator == "pattern":
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = _pattern_to_regex(pattern)
        m = compiled.search(value if case_sensitive else _get_field_value({"_": value}, "_").lower() if False else value)
        # Redo with proper flags
        regex_str = compiled.pattern
        m = re.search(regex_str, value, flags)
        if m:
            return MatchResult(matched=True, variables=m.groupdict())
        return MatchResult(matched=False)

    return MatchResult(matched=False)


def match_rule(email_data: dict[str, str], conditions: list[dict]) -> MatchResult:
    """Check all conditions against email data. All must match (AND logic)."""
    all_vars: dict[str, str] = {}

    for cond in conditions:
        field_name = cond.get("field", "")
        operator = cond.get("operator", "")
        pattern = cond.get("value", "")
        case_sensitive = cond.get("case_sensitive", False)

        field_value = _get_field_value(email_data, field_name)
        result = _check_condition(field_value, operator, pattern, case_sensitive)

        if not result.matched:
            return MatchResult(matched=False)

        all_vars.update(result.variables)

    return MatchResult(matched=True, variables=all_vars)
