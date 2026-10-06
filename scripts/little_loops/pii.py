"""PII detection and redaction utilities.

Provides regex-based detection and redaction of email, phone, SSN, and
credential-shaped (API key/token/PEM/JWT) patterns. The scanner/SFT surface
(``detect_pii``, ``redact_pii``, ``scan_text``, ``apply_pii_action``) has
stable semantics; its primary consumer is the ``sft-corpus`` FSM loop's
``filter`` state via ``apply_pii_action()``.

A separate, pure *history* policy (``redact_history_text``,
``sanitize_history_payload``; ENH-3750) removes supported credential/PII
matches from decoded session-history JSON while preserving the protocol
fields replay needs. It has its own rule table, placeholders and
``HISTORY_REDACTION_VERSION`` and never changes the scanner semantics above.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

# Compiled PII patterns — module-level to avoid recompilation on each call
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": _EMAIL,
    "phone": _PHONE,
    "ssn": _SSN,
}

_VALID_ACTIONS = frozenset({"flag", "redact", "discard"})


@dataclass(frozen=True)
class CredentialRule:
    """One shape of credential/API-key/token pattern."""

    name: str
    pattern: re.Pattern[str]
    rationale: str


CREDENTIAL_RULES: tuple[CredentialRule, ...] = (
    CredentialRule(
        name="aws_access_key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        rationale="AWS long-term access key ID prefix",
    ),
    CredentialRule(
        name="github_token",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        rationale="GitHub PAT / OAuth / user-server / refresh token prefixes",
    ),
    CredentialRule(
        name="anthropic_key",
        pattern=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        rationale="Anthropic API / OAuth key prefix",
    ),
    CredentialRule(
        name="slack_token",
        pattern=re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        rationale="Slack bot/app/user token prefixes",
    ),
    CredentialRule(
        name="private_key_pem",
        pattern=re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        rationale="PEM private-key block header",
    ),
    CredentialRule(
        name="jwt",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        rationale="Three-segment base64url JWT",
    ),
)

CREDENTIAL_SCANNER_VERSION: int = 1  # bump only when scan semantics change


@dataclass(frozen=True)
class CredentialFinding:
    """One unsuppressed credential-pattern match. Redacted by construction —
    no ``excerpt`` field, so the finding itself never re-leaks the secret."""

    rule: str
    line: int
    fingerprint: str


def scan_text(
    text: str, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES
) -> list[CredentialFinding]:
    """Scan *text* for credential-shaped patterns.

    Args:
        text: Input text to scan.
        rules: Rule table to scan against. Defaults to ``CREDENTIAL_RULES``.

    Returns:
        Findings sorted by ``(line, rule)`` for deterministic output.
        1-based line numbers. A line matching multiple rules yields one
        finding per rule.
    """
    findings: list[CredentialFinding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule in rules:
            for match in rule.pattern.finditer(line):
                fingerprint = hashlib.sha256(match.group().encode()).hexdigest()[:12]
                findings.append(
                    CredentialFinding(rule=rule.name, line=line_no, fingerprint=fingerprint)
                )
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def scan_file(
    path: Path, rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES
) -> list[CredentialFinding]:
    """Thin wrapper: read *path* as text and scan it with ``scan_text``."""
    return scan_text(path.read_text(encoding="utf-8", errors="replace"), rules)


def credential_rules_sha(rules: tuple[CredentialRule, ...] = CREDENTIAL_RULES) -> str:
    """Stable sha256 over the rule table's name/pattern/flags (not rationale)."""
    payload = "\n".join(f"{r.name}\t{r.pattern.pattern}\t{r.pattern.flags}" for r in rules)
    return hashlib.sha256(payload.encode()).hexdigest()


def detect_pii(text: str) -> list[str]:
    """Return list of PII type names found in text.

    Args:
        text: Input text to scan for PII.

    Returns:
        List of PII type names (e.g. ``["email", "phone"]``) present in the
        text, including credential rule names (e.g. ``"aws_access_key"``)
        from ``CREDENTIAL_RULES``. Returns an empty list when no PII is
        detected.
    """
    found = [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]
    found.extend(rule.name for rule in CREDENTIAL_RULES if rule.pattern.search(text))
    return found


def redact_pii(text: str) -> str:
    """Replace PII spans with ``[TYPE]`` placeholders.

    Args:
        text: Input text to redact.

    Returns:
        Text with all PII spans replaced by their uppercased type placeholder
        (e.g. ``[EMAIL]``, ``[PHONE]``, ``[SSN]``, ``[AWS_ACCESS_KEY]``).
    """
    for name, pattern in PII_PATTERNS.items():
        text = pattern.sub(f"[{name.upper()}]", text)
    for rule in CREDENTIAL_RULES:
        text = rule.pattern.sub(f"[{rule.name.upper()}]", text)
    return text


def apply_pii_action(example: dict, action: str) -> dict | None:
    """Apply flag/redact/discard to a formatted SFT example dict.

    Scans all top-level string values for PII and applies the requested action.

    Args:
        example: SFT example dict (e.g. Alpaca ``{"instruction": ..., "output": ...}``).
        action: One of ``"flag"``, ``"redact"``, or ``"discard"``.

    Returns:
        - ``"flag"``: original example with ``pii_detected: True`` added if PII
          is present; original example unchanged if no PII found.
        - ``"redact"``: copy of example with PII in string values replaced by
          ``[TYPE]`` placeholders.
        - ``"discard"``: ``None`` when PII is detected; original example when
          no PII is found.

    Raises:
        ValueError: If *action* is not ``"flag"``, ``"redact"``, or ``"discard"``.
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid pii_action {action!r}. Must be one of: {sorted(_VALID_ACTIONS)}")

    combined = " ".join(v for v in example.values() if isinstance(v, str))

    if action == "discard":
        return None if detect_pii(combined) else example

    if action == "flag":
        if detect_pii(combined):
            return {**example, "pii_detected": True}
        return example

    # redact: replace PII in all string values
    return {k: redact_pii(v) if isinstance(v, str) else v for k, v in example.items()}


# ---------------------------------------------------------------------------
# History payload redaction (ENH-3750)
#
# A policy distinct from the scanner/SFT API above: it works on decoded JSON
# (never serialized JSON), removes whole credential spans, and keeps the
# protocol fields replay consumers read. Pure — no database, host runner or I/O.
# ---------------------------------------------------------------------------

HISTORY_REDACTION_VERSION: int = 1  # bump only when history redaction semantics change

#: Finite, content-free failure codes carried by ``HistorySanitizationError``.
HISTORY_ERROR_REASONS: tuple[str, ...] = (
    "invalid_payload",
    "key_collision",
    "unsafe_identity",
    "resource_limit",
)

#: Rule IDs in precedence order (enclosing matches first); also the ``counts`` keys.
HISTORY_RULE_IDS: tuple[str, ...] = (
    "private_key_pem",
    "bearer_credential",
    "uri_userinfo",
    "credential_field",
    "aws_access_key",
    "github_token",
    "anthropic_key",
    "slack_token",
    "jwt",
    "email",
    "phone",
    "ssn",
)

_PLACEHOLDER_PEM = "[PRIVATE_KEY_PEM]"
_PLACEHOLDER_BEARER = "[BEARER_CREDENTIAL]"
_PLACEHOLDER_FIELD = "[CREDENTIAL_FIELD]"

#: Every placeholder the history policy has emitted (current and historical,
#: including ``redact_pii``'s). Exact matches are preserved; extra text is scanned.
HISTORY_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        _PLACEHOLDER_PEM,
        _PLACEHOLDER_BEARER,
        _PLACEHOLDER_FIELD,
        "[AWS_ACCESS_KEY]",
        "[GITHUB_TOKEN]",
        "[ANTHROPIC_KEY]",
        "[SLACK_TOKEN]",
        "[JWT]",
        "[EMAIL]",
        "[PHONE]",
        "[SSN]",
    }
)

#: V1 credential names. Matching is exact after ASCII lowercasing and removal
#: of ``_``/``-`` (so ``apiKey`` and ``API-KEY`` match); never by substring.
HISTORY_CREDENTIAL_FIELD_ALIASES: frozenset[str] = frozenset(
    {
        "api_key",
        "api_token",
        "access_token",
        "refresh_token",
        "auth_token",
        "id_token",
        "authorization",
        "proxy_authorization",
        "password",
        "passwd",
        "private_key",
        "client_secret",
        "secret_access_key",
        "aws_secret_access_key",
        "aws_access_key_id",
    }
)

_ALIASES_NORMALIZED = frozenset(a.replace("_", "") for a in HISTORY_CREDENTIAL_FIELD_ALIASES)
_AUTH_ALIASES_NORMALIZED = frozenset({"authorization", "proxyauthorization"})
_SEPARATOR_STRIP = re.compile(r"[_\-]")

_MAX_PASSES = 8  # fixed-point iterations for one string before ``resource_limit``
_MAX_DEPTH = 200
_MAX_NODES = 10_000_000
_MAX_PATH = 8  # protocol paths are root-anchored and never deeper than this

# PEM: whole-block scan via literal BEGIN/END markers (no backtracking-heavy regex).
_PEM_LABEL = r"(?:(?:RSA|EC|DSA|OPENSSH|PGP|ENCRYPTED) )?PRIVATE KEY(?: BLOCK)?"
_PEM_BEGIN = re.compile(r"-----BEGIN " + _PEM_LABEL + r"-----")
_PEM_END = re.compile(r"-----END " + _PEM_LABEL + r"-----")
_LEGACY_SEP = r"(?:\s|\\[nrt])"
_LEGACY_BODY = re.compile(
    r"(?:" + _LEGACY_SEP + r"+[A-Za-z0-9+/=]{16,})+(?:" + _LEGACY_SEP + r"+[A-Za-z0-9+/=]+)?"
)
_LEGACY_END = re.compile(_LEGACY_SEP + r"*-----END " + _PEM_LABEL + r"-----")

_BEARER = re.compile(r"(?<![A-Za-z0-9])(?i:bearer)[ \t]+(?P<cred>[A-Za-z0-9\-._~+/%=]{8,})")

# Start is anchored to the beginning of a scheme run (lookbehind) so scanning is linear.
_URI_USERINFO = re.compile(
    r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*://(?P<ui>[^\s/?#\"'<>`\\]+@)"
)

_FIELD = re.compile(
    r"(?<![A-Za-z0-9_\-])(?P<name>[A-Za-z][A-Za-z0-9_\-]{0,63})"
    r"\\?[\"']?[ \t]*(?::=|=>|[:=])[ \t]*"
    r"(?:"
    r"\\\"(?P<eq>(?:[^\"\\\r\n]|\\(?!\")[^\r\n])*)(?:\\\"|\\?(?=[\r\n])|\Z)"
    r"|\"(?P<dq>(?:[^\"\\\r\n]|\\[^\r\n])*)(?:\"|\\?(?=[\r\n])|\Z)"
    r"|'(?P<sq>(?:[^'\\\r\n]|\\[^\r\n])*)(?:'|\\?(?=[\r\n])|\Z)"
    r"|(?P<uq>[^\s\"',;&)}\\]+)"
    r")"
)
_AUTH_TAIL = re.compile(r"[ \t]+[^\s\"',;&)}\\]+")
_SCHEME_PLACEHOLDER = re.compile(r"[A-Za-z]+[ \t]+(\[[A-Z_]+\])")

# History-specific variants of the scanner's JWT/email shapes: the same shapes, but the
# start is anchored to the beginning of a character run so a long run of start-like
# fragments cannot trigger quadratic rescans (multi-MB inputs stay linear).
_HISTORY_JWT = re.compile(
    r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_HISTORY_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_FIXED_SHAPE_PREFILTER = {
    "aws_access_key": "AKIA",
    "github_token": "gh",
    "anthropic_key": "sk-ant-",
    "slack_token": "xox",
}
_FIXED_SHAPE_RULES: tuple[CredentialRule, ...] = tuple(
    r for r in CREDENTIAL_RULES if r.name in _FIXED_SHAPE_PREFILTER
)


class HistorySanitizationError(ValueError):
    """Content-free failure of the history policy.

    ``reason`` is one of ``HISTORY_ERROR_REASONS``. ``str()``, ``repr()``, ``args``
    and the traceback carry only the code — never matched text, key spelling or
    payload paths — and the exception chain is suppressed at every raise site.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _fail(reason: str) -> NoReturn:
    raise HistorySanitizationError(reason) from None


@dataclass(frozen=True)
class HistoryRedactionResult:
    """Sanitized payload (fresh, never aliasing the input) plus per-rule counts."""

    payload: dict[str, Any]
    counts: dict[str, int]


_Span = tuple[int, int, str, str]  # (start, end, replacement, rule)


def _is_redacted_value(value: str) -> bool:
    """True when *value* is already a finite placeholder (optionally behind a scheme word)."""
    stripped = value.strip()
    if stripped in HISTORY_PLACEHOLDERS:
        return True
    m = _SCHEME_PLACEHOLDER.fullmatch(stripped)
    return m is not None and m.group(1) in HISTORY_PLACEHOLDERS


def _is_credential_name(name: str) -> bool:
    return _SEPARATOR_STRIP.sub("", name).lower() in _ALIASES_NORMALIZED


def _pem_block_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    pos = 0
    while True:
        begin = _PEM_BEGIN.search(text, pos)
        if begin is None:
            return spans
        end_m = _PEM_END.search(text, begin.end())
        end = end_m.end() if end_m is not None else len(text)  # truncated: BEGIN-to-end
        spans.append((begin.start(), end, _PLACEHOLDER_PEM, "private_key_pem"))
        pos = end


def _legacy_pem_spans(text: str) -> list[_Span]:
    """A ``redact_pii``-era ``[PRIVATE_KEY_PEM]`` followed by key material and/or END."""
    spans: list[_Span] = []
    pos = 0
    while True:
        start = text.find(_PLACEHOLDER_PEM, pos)
        if start < 0:
            return spans
        after = start + len(_PLACEHOLDER_PEM)
        end = after
        body = _LEGACY_BODY.match(text, after)
        if body is not None:
            end = body.end()
        tail = _LEGACY_END.match(text, end)
        if tail is not None:
            end = tail.end()
        if end > after:
            spans.append((start, end, _PLACEHOLDER_PEM, "private_key_pem"))
        pos = end


def _bearer_spans(text: str) -> list[_Span]:
    return [
        (m.start("cred"), m.end("cred"), _PLACEHOLDER_BEARER, "bearer_credential")
        for m in _BEARER.finditer(text)
    ]


def _userinfo_spans(text: str) -> list[_Span]:
    return [(m.start("ui"), m.end("ui"), "", "uri_userinfo") for m in _URI_USERINFO.finditer(text)]


def _field_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    for m in _FIELD.finditer(text):
        normalized = _SEPARATOR_STRIP.sub("", m.group("name")).lower()
        if normalized not in _ALIASES_NORMALIZED:
            continue
        group = next(g for g in ("eq", "dq", "sq", "uq") if m.group(g) is not None)
        start, end = m.span(group)
        if group == "uq" and normalized in _AUTH_ALIASES_NORMALIZED:
            tail = _AUTH_TAIL.match(text, end)
            if tail is not None and text[start:end].isalpha():
                end = tail.end()
        value = text[start:end]
        if not value or _is_redacted_value(value):
            continue
        spans.append((start, end, _PLACEHOLDER_FIELD, "credential_field"))
    return spans


def _pattern_spans(text: str, pattern: re.Pattern[str], rule: str) -> list[_Span]:
    return [(m.start(), m.end(), f"[{rule.upper()}]", rule) for m in pattern.finditer(text)]


def _span_groups(text: str) -> list[list[_Span]]:
    """Candidate spans per rule family, in precedence order; each group is sorted/disjoint."""
    groups: list[list[_Span]] = []
    if "PRIVATE KEY" in text:
        groups.append(_pem_block_spans(text))
    if _PLACEHOLDER_PEM in text:
        groups.append(_legacy_pem_spans(text))
    groups.append(_bearer_spans(text))
    if "://" in text:
        groups.append(_userinfo_spans(text))
    if ":" in text or "=" in text:
        groups.append(_field_spans(text))
    for rule in _FIXED_SHAPE_RULES:
        if _FIXED_SHAPE_PREFILTER[rule.name] in text:
            groups.append(_pattern_spans(text, rule.pattern, rule.name))
    if "eyJ" in text:
        groups.append(_pattern_spans(text, _HISTORY_JWT, "jwt"))
    if "@" in text:
        groups.append(_pattern_spans(text, _HISTORY_EMAIL, "email"))
    groups.append(_pattern_spans(text, PII_PATTERNS["phone"], "phone"))
    groups.append(_pattern_spans(text, PII_PATTERNS["ssn"], "ssn"))
    return groups


def _redact_pass(text: str, counts: dict[str, int]) -> str:
    accepted: list[_Span] = []
    for group in _span_groups(text):
        kept: list[_Span] = []
        j = 0
        n = len(accepted)
        for span in group:
            start, end, replacement, rule = span
            while j < n and accepted[j][1] <= start:
                j += 1
            if j < n and accepted[j][0] < end:
                continue  # inside/overlapping a higher-precedence replacement
            if text[start:end] == replacement:
                continue
            kept.append(span)
            counts[rule] = counts.get(rule, 0) + 1
        if kept:
            accepted = sorted(accepted + kept, key=lambda s: s[0])
    if not accepted:
        return text
    parts: list[str] = []
    pos = 0
    for start, end, replacement, _rule in accepted:
        parts.append(text[pos:start])
        parts.append(replacement)
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def _redact_text(text: str, counts: dict[str, int]) -> str:
    """Redact to a fixed point so a second pass is always a no-op with zero counts."""
    for _ in range(_MAX_PASSES):
        pass_counts: dict[str, int] = {}
        redacted = _redact_pass(text, pass_counts)
        if redacted == text:
            return text
        for rule, n in pass_counts.items():
            counts[rule] = counts.get(rule, 0) + n
        text = redacted
    _fail("resource_limit")


def redact_history_text(text: str) -> str:
    """Remove supported credential/PII matches from an arbitrary string.

    Pure and deterministic; idempotent (a second call returns its input). Applies the
    finite history rule table with enclosing matches (PEM block, bearer credential,
    URI userinfo, explicit credential field) taking precedence over narrower ones.

    Raises:
        HistorySanitizationError: ``invalid_payload`` for a non-``str`` argument, or
            ``resource_limit`` if the text does not converge (never expected).
    """
    if not isinstance(text, str):
        _fail("invalid_payload")
    return _redact_text(text, {})


# -- Protocol context -------------------------------------------------------

_IDX = object()  # list-index path element; a dict key can never equal it


@dataclass(frozen=True)
class _PathRule:
    """A root-anchored path. ``shape is None`` => protected identity (scan, fail if it
    would change); otherwise an opaque value preserved verbatim only if it fullmatches
    ``shape``. ``sibling`` is a ``(key, value)`` discriminator read from the parent map."""

    path: tuple[object, ...]
    sibling: tuple[str, str] | None = None
    shape: re.Pattern[str] | None = None


_STD_B64 = re.compile(r"[A-Za-z0-9+/=\s]*")
_URLSAFE_B64 = re.compile(r"[A-Za-z0-9+/=_\-\s]*")

_CLAUDE_CONTENT = ("message", "content", _IDX)
_CLAUDE_RULE_LIST: tuple[_PathRule, ...] = (
    *(
        _PathRule((name,))
        for name in ("sessionId", "uuid", "parentUuid", "type", "timestamp", "version")
    ),
    _PathRule(("message", "id")),
    _PathRule(("message", "model")),
    _PathRule(("message", "role")),
    _PathRule((*_CLAUDE_CONTENT, "type")),
    _PathRule((*_CLAUDE_CONTENT, "id"), sibling=("type", "tool_use")),
    _PathRule((*_CLAUDE_CONTENT, "tool_use_id"), sibling=("type", "tool_result")),
    _PathRule((*_CLAUDE_CONTENT, "signature"), sibling=("type", "thinking"), shape=_STD_B64),
    _PathRule((*_CLAUDE_CONTENT, "data"), sibling=("type", "redacted_thinking"), shape=_STD_B64),
    _PathRule((*_CLAUDE_CONTENT, "source", "data"), sibling=("type", "base64"), shape=_STD_B64),
    _PathRule(
        (*_CLAUDE_CONTENT, "content", _IDX, "source", "data"),
        sibling=("type", "base64"),
        shape=_STD_B64,
    ),
)
_CODEX_NATIVE_RULE_LIST: dict[str, tuple[_PathRule, ...]] = {
    "session_meta": (_PathRule(("id",)), _PathRule(("timestamp",))),
    "turn_context": (_PathRule(("turn_id",)), _PathRule(("model",))),
    "event_msg": (_PathRule(("type",)), _PathRule(("turn_id",))),
    "token_usage_record": (
        _PathRule(("thread_id",)),
        _PathRule(("turn_id",)),
        _PathRule(("response_id",)),
    ),
    "response_item": (
        _PathRule(("type",)),
        _PathRule(("encrypted_content",), sibling=("type", "reasoning"), shape=_URLSAFE_B64),
    ),
}
_KIMI_RULE_LIST: tuple[_PathRule, ...] = (_PathRule(("type",)), _PathRule(("timestamp",)))

_RuleTable = dict[tuple[object, ...], _PathRule]


def _table(rules: tuple[_PathRule, ...]) -> _RuleTable:
    return {r.path: r for r in rules}


_CLAUDE_RULES = _table(_CLAUDE_RULE_LIST)
_KIMI_RULES = _table(_KIMI_RULE_LIST)
_CODEX_NATIVE_RULES = {k: _table(v) for k, v in _CODEX_NATIVE_RULE_LIST.items()}

#: Registered hosts (mirrors ``session_store.sessions._PARSERS``; pinned by a test).
HISTORY_CLAUDE_SHAPED_HOSTS: frozenset[str] = frozenset(
    {"claude-code", "opencode", "pi", "qwen", "gemini", "omp"}
)
HISTORY_REGISTERED_HOSTS: frozenset[str] = HISTORY_CLAUDE_SHAPED_HOSTS | {"codex", "kimi-code"}
_CODEX_NORMALIZED_EXEC_TYPES = frozenset({"assistant", "user"})


def _protocol_rules(host: str | None, event_type: str | None) -> _RuleTable | None:
    """Rule table for caller-supplied context; ``None`` (no exemptions) when unknown."""
    if not isinstance(host, str) or not isinstance(event_type, str):
        return None
    if host in HISTORY_CLAUDE_SHAPED_HOSTS:
        return _CLAUDE_RULES
    if host == "kimi-code":
        return _KIMI_RULES
    if host == "codex":
        if event_type in _CODEX_NORMALIZED_EXEC_TYPES:
            return _CLAUDE_RULES
        return _CODEX_NATIVE_RULES.get(event_type)
    return None


def is_replay_safe_history_context(*, host: str | None, event_type: str | None) -> bool:
    """Whether the protocol-rule registry can protect replay fields for this context.

    True only for string context the registry registers: a Claude-shaped or Kimi host, or a
    registered native/normalized Codex event type. Missing or non-string context, an unknown
    Codex type and an unregistered host are False (the sanitizer would apply no exemptions).
    """
    return _protocol_rules(host, event_type) is not None


def _extend_path(path: tuple[object, ...] | None, key: object) -> tuple[object, ...] | None:
    if path is None or len(path) >= _MAX_PATH:
        return None
    return (*path, key)


def _match_rule(
    rules: _RuleTable | None, path: tuple[object, ...] | None, parent: dict[str, Any]
) -> _PathRule | None:
    if rules is None or path is None:
        return None
    rule = rules.get(path)
    if rule is None:
        return None
    if rule.sibling is not None and parent.get(rule.sibling[0]) != rule.sibling[1]:
        return None
    return rule


# -- Payload traversal ------------------------------------------------------


class _Frame:
    __slots__ = ("items", "dst", "is_dict", "path", "cred", "src")

    def __init__(
        self,
        src: dict[str, Any] | list[Any],
        dst: Any,
        path: tuple[object, ...] | None,
        cred: bool,
    ) -> None:
        self.src = src
        self.dst = dst
        self.is_dict = isinstance(src, dict)
        self.items = iter(src.items()) if isinstance(src, dict) else iter(src)
        self.path = path
        self.cred = cred


def _leaf(value: str, rule: _PathRule | None, cred: bool, counts: dict[str, int]) -> str:
    if rule is not None:
        if rule.shape is None:
            if _redact_text(value, {}) != value:
                _fail("unsafe_identity")
            return value
        if rule.shape.fullmatch(value) is not None:
            return value
        # opaque rule but wrong shape: no exemption, scan normally
    if cred and value and not _is_redacted_value(value):
        counts["credential_field"] = counts.get("credential_field", 0) + 1
        return _PLACEHOLDER_FIELD
    return _redact_text(value, counts)


def sanitize_history_payload(
    payload: dict[str, Any],
    *,
    host: str | None = None,
    event_type: str | None = None,
) -> HistoryRedactionResult:
    """Return a fresh, redacted copy of a decoded history payload plus rule counts.

    Strings and mapping keys are redacted with :func:`redact_history_text`'s policy
    plus credential-name context (a value — or every string leaf under a container
    value — of a ``HISTORY_CREDENTIAL_FIELD_ALIASES`` key becomes
    ``[CREDENTIAL_FIELD]``). Numbers, booleans and nulls are never changed. Input
    containers are never mutated or aliased; regex substitution never runs over
    serialized JSON.

    ``host`` and ``event_type`` are out-of-band caller context (the parser's host and
    event type). With a registered pair, a finite root-anchored path registry protects
    replay identity fields (scanned; a would-be change raises ``unsafe_identity``) and
    narrowly preserves verified opaque base64 fields. Unknown or missing context gets
    no exemptions at all.

    Raises:
        HistorySanitizationError: ``invalid_payload`` (non-dict root, non-JSON value,
            non-string key, cycle, non-finite float), ``key_collision`` (a rewritten
            key equals another key), ``unsafe_identity`` or ``resource_limit``. The
            error carries only the fixed code.
    """
    if type(payload) is not dict:
        _fail("invalid_payload")
    rules = _protocol_rules(host, event_type)
    counts: dict[str, int] = {}
    root: dict[str, Any] = {}
    ancestors = {id(payload)}
    stack = [_Frame(payload, root, () if rules is not None else None, False)]
    nodes = 0
    try:
        while stack:
            frame = stack[-1]
            try:
                item = next(frame.items)
            except StopIteration:
                ancestors.discard(id(frame.src))
                stack.pop()
                continue
            nodes += 1
            if nodes > _MAX_NODES:
                _fail("resource_limit")
            if frame.is_dict:
                key, value = item
                if type(key) is not str:
                    _fail("invalid_payload")
                new_key = _redact_text(key, counts)
                if new_key in frame.dst:
                    _fail("key_collision")
                child_path = _extend_path(frame.path, key)
                rule = _match_rule(rules, child_path, frame.src)  # type: ignore[arg-type]
                cred = frame.cred or _is_credential_name(key)
            else:
                key = new_key = ""
                value = item
                rule = None
                child_path = _extend_path(frame.path, _IDX)
                cred = frame.cred
            out: Any
            kind = type(value)
            if kind is str:
                out = _leaf(value, rule, cred, counts)
            elif kind is dict or kind is list:
                if id(value) in ancestors:
                    _fail("invalid_payload")
                if len(stack) >= _MAX_DEPTH:
                    _fail("resource_limit")
                out = {} if kind is dict else []
                ancestors.add(id(value))
                stack.append(_Frame(value, out, child_path, cred))
            elif kind is bool or kind is int or value is None:
                out = value
            elif kind is float and math.isfinite(value):
                out = value
            else:
                _fail("invalid_payload")
            if frame.is_dict:
                frame.dst[new_key] = out
            else:
                frame.dst.append(out)
    except RecursionError:
        _fail("resource_limit")
    return HistoryRedactionResult(payload=root, counts=dict(sorted(counts.items())))
