from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MatchResult:
    matched: bool
    variables: dict[str, str] = field(default_factory=dict)


VARIABLE_TYPE_MAP: dict[str, str] = {
    "digits": r"\d+",
    "d": r"\d+",
    "alpha": r"[a-zA-Zа-яА-ЯЁё]+",
    "a": r"[a-zA-Zа-яА-ЯЁё]+",
    "word": r"\w+",
    "w": r"\w+",
    "any": r".+?",
}


def _resolve_var_regex(type_spec: str | None) -> str:
    if not type_spec or type_spec.lower() == "any":
        return r".+?"
    key = type_spec.lower()
    if key in VARIABLE_TYPE_MAP:
        return VARIABLE_TYPE_MAP[key]
    return type_spec


def _pattern_to_regex(pattern: str) -> re.Pattern:
    """Convert a pattern like 'AI review {mr_id:digits}' to a compiled regex with named groups.

    Supported variable types:
      {name}        — any characters (default, same as {name:any})
      {name:digits} — only digits  (\\d+)
      {name:d}      — alias for digits
      {name:word}   — word characters (\\w+)
      {name:w}      — alias for word
      {name:alpha}  — letters only (Latin + Cyrillic)
      {name:a}      — alias for alpha
      {name:any}    — any characters (.+?)
      {name:<regex>} — custom regex pattern
    """
    result: list[str] = []
    last_end = 0
    for m in re.finditer(r"\{(\w+)(?::([^}]+))?\}", pattern):
        result.append(re.escape(pattern[last_end:m.start()]))
        var_name = m.group(1)
        type_spec = m.group(2)
        var_regex = _resolve_var_regex(type_spec)
        result.append(f"(?P<{var_name}>{var_regex})")
        last_end = m.end()
    result.append(re.escape(pattern[last_end:]))
    return re.compile("^" + "".join(result) + "$")


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
        m = re.search(compiled.pattern, value, flags)
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
