"""Tests for the pii module."""

from __future__ import annotations

import copy
import json
import re
import time
import traceback

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from little_loops.pii import (
    CREDENTIAL_RULES,
    CREDENTIAL_SCANNER_VERSION,
    HISTORY_CREDENTIAL_FIELD_ALIASES,
    HISTORY_ERROR_REASONS,
    HISTORY_PLACEHOLDERS,
    HISTORY_REDACTION_VERSION,
    HISTORY_REGISTERED_HOSTS,
    HISTORY_RULE_IDS,
    CredentialFinding,
    CredentialRule,
    HistorySanitizationError,
    apply_pii_action,
    credential_rules_sha,
    detect_pii,
    redact_history_text,
    redact_pii,
    sanitize_history_payload,
    scan_file,
    scan_text,
)

# Fixtures assembled from fragments so this test file is not itself flagged
# by the gitleaks pre-commit hook (mirrors verify_private_refs.py's _USER_SEG).
_AWS_KEY = "AKIA" + "I" * 16
_GITHUB_TOKEN = "gh" + "p_" + "a" * 36
_ANTHROPIC_KEY = "sk-ant-" + "a" * 24
_SLACK_TOKEN = "xoxb-" + "1234567890"
_PEM_HEADER = "-----BEGIN RSA PRIVATE KEY-----"
_JWT = "eyJ" + "a" * 10 + "." + "eyJ" + "a" * 10 + "." + "a" * 10

_RULE_FIXTURES: dict[str, tuple[str, str]] = {
    "aws_access_key": (_AWS_KEY, "AKIAI" + "I" * 10),  # near-miss: too short
    "github_token": (_GITHUB_TOKEN, "gh" + "x_" + "a" * 36),  # wrong prefix letter
    "anthropic_key": (_ANTHROPIC_KEY, "sk-not-ant-" + "a" * 24),
    "slack_token": (_SLACK_TOKEN, "xox" + "z-" + "1234567890"),  # invalid slack prefix
    "private_key_pem": (_PEM_HEADER, "-----BEGIN CERTIFICATE-----"),
    "jwt": (_JWT, "notajwt.notajwt.notajwt"),
}


class TestCredentialRules:
    """Tests for the CREDENTIAL_RULES table."""

    def test_has_one_rule_per_expected_name(self) -> None:
        names = {rule.name for rule in CREDENTIAL_RULES}
        assert names == set(_RULE_FIXTURES)

    def test_each_pattern_is_compiled_regex(self) -> None:
        for rule in CREDENTIAL_RULES:
            assert isinstance(rule.pattern, re.Pattern)

    def test_each_rule_has_rationale(self) -> None:
        for rule in CREDENTIAL_RULES:
            assert rule.rationale


class TestScanText:
    """Tests for scan_text."""

    @pytest.mark.parametrize("rule_name", sorted(_RULE_FIXTURES))
    def test_detects_positive_fixture(self, rule_name: str) -> None:
        positive, _ = _RULE_FIXTURES[rule_name]
        findings = scan_text(f"leading text {positive} trailing text")
        assert any(f.rule == rule_name for f in findings)

    @pytest.mark.parametrize("rule_name", sorted(_RULE_FIXTURES))
    def test_rejects_near_miss_fixture(self, rule_name: str) -> None:
        _, near_miss = _RULE_FIXTURES[rule_name]
        findings = scan_text(f"leading text {near_miss} trailing text")
        assert not any(f.rule == rule_name for f in findings)

    def test_no_findings_on_clean_text(self) -> None:
        assert scan_text("nothing sensitive here") == []

    def test_line_numbers_are_one_based(self) -> None:
        text = f"line one\n{_AWS_KEY}\nline three"
        findings = scan_text(text)
        assert any(f.line == 2 for f in findings)

    def test_multi_hit_line_yields_one_finding_per_rule(self) -> None:
        text = f"{_AWS_KEY} and {_GITHUB_TOKEN}"
        findings = scan_text(text)
        rules_hit = {f.rule for f in findings if f.line == 1}
        assert {"aws_access_key", "github_token"} <= rules_hit

    def test_findings_sorted_by_line_then_rule(self) -> None:
        text = f"{_GITHUB_TOKEN}\n{_AWS_KEY}"
        findings = scan_text(text)
        keys = [(f.line, f.rule) for f in findings]
        assert keys == sorted(keys)


class TestScanFile:
    """Tests for scan_file."""

    def test_scans_file_contents(self, tmp_path: pytest.TempPathFactory) -> None:
        path = tmp_path / "sample.txt"  # type: ignore[attr-defined]
        path.write_text(f"secret: {_AWS_KEY}\n")
        findings = scan_file(path)
        assert any(f.rule == "aws_access_key" for f in findings)


class TestNoLeak:
    """Findings must never carry the matched secret span."""

    @pytest.mark.parametrize("rule_name", sorted(_RULE_FIXTURES))
    def test_finding_does_not_contain_matched_span(self, rule_name: str) -> None:
        positive, _ = _RULE_FIXTURES[rule_name]
        findings = scan_text(positive)
        assert findings, f"expected a finding for {rule_name}"
        for finding in findings:
            assert positive not in repr(finding)
            for value in (finding.rule, str(finding.line), finding.fingerprint):
                assert positive not in value

    def test_credential_finding_has_no_excerpt_field(self) -> None:
        field_names = {f.name for f in CredentialFinding.__dataclass_fields__.values()}
        assert "excerpt" not in field_names


class TestCredentialRulesSha:
    """Tests for credential_rules_sha."""

    def test_stable_across_calls(self) -> None:
        assert credential_rules_sha() == credential_rules_sha()

    def test_changes_when_pattern_changes(self) -> None:
        base_sha = credential_rules_sha()
        altered = (
            CredentialRule(name="aws_access_key", pattern=re.compile(r"CHANGED"), rationale="x"),
        )
        assert credential_rules_sha(altered) != base_sha

    def test_unchanged_when_only_rationale_changes(self) -> None:
        rules = tuple(
            CredentialRule(name=r.name, pattern=r.pattern, rationale="different text")
            for r in CREDENTIAL_RULES
        )
        assert credential_rules_sha(rules) == credential_rules_sha(CREDENTIAL_RULES)

    def test_version_is_pinned_int(self) -> None:
        assert isinstance(CREDENTIAL_SCANNER_VERSION, int)


class TestDetectPii:
    """Tests for detect_pii function."""

    def test_detects_email(self) -> None:
        assert "email" in detect_pii("Contact john@example.com for help")

    def test_detects_phone(self) -> None:
        assert "phone" in detect_pii("Call us at 555-867-5309")

    def test_detects_ssn(self) -> None:
        assert "ssn" in detect_pii("SSN: 123-45-6789")

    def test_detects_multiple_types(self) -> None:
        text = "Email john@example.com or call 555-867-5309"
        found = detect_pii(text)
        assert "email" in found
        assert "phone" in found

    def test_no_pii_returns_empty(self) -> None:
        assert detect_pii("Hello world, nothing sensitive here") == []

    def test_empty_string_returns_empty(self) -> None:
        assert detect_pii("") == []

    def test_email_subdomain(self) -> None:
        assert "email" in detect_pii("user@mail.example.co.uk")

    def test_phone_with_parens(self) -> None:
        assert "phone" in detect_pii("Call (555) 867-5309 now")

    def test_phone_with_country_code(self) -> None:
        assert "phone" in detect_pii("+1-555-867-5309")


class TestRedactPii:
    """Tests for redact_pii function."""

    def test_redacts_email(self) -> None:
        result = redact_pii("Contact john@example.com for help")
        assert "[EMAIL]" in result
        assert "john@example.com" not in result

    def test_redacts_phone(self) -> None:
        result = redact_pii("Call 555-867-5309 now")
        assert "[PHONE]" in result
        assert "555-867-5309" not in result

    def test_redacts_ssn(self) -> None:
        result = redact_pii("SSN is 123-45-6789")
        assert "[SSN]" in result
        assert "123-45-6789" not in result

    def test_redacts_multiple_types(self) -> None:
        text = "Email john@example.com or call 555-867-5309"
        result = redact_pii(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "john@example.com" not in result
        assert "555-867-5309" not in result

    def test_no_pii_unchanged(self) -> None:
        text = "Hello world, nothing sensitive"
        assert redact_pii(text) == text

    def test_empty_string_unchanged(self) -> None:
        assert redact_pii("") == ""

    def test_preserves_non_pii_content(self) -> None:
        result = redact_pii("Hi john@example.com, your order is ready")
        assert "Hi" in result
        assert "your order is ready" in result


class TestDetectPiiRedactPiiCredentials:
    """detect_pii/redact_pii consult CREDENTIAL_RULES alongside PII_PATTERNS."""

    def test_detect_pii_reports_credential_rule_name(self) -> None:
        assert "aws_access_key" in detect_pii(f"key is {_AWS_KEY}")

    def test_redact_pii_emits_uppercase_placeholder(self) -> None:
        result = redact_pii(f"key is {_AWS_KEY}")
        assert "[AWS_ACCESS_KEY]" in result
        assert _AWS_KEY not in result

    def test_existing_email_phone_ssn_detection_unchanged(self) -> None:
        assert detect_pii("Contact john@example.com for help") == ["email"]

    def test_existing_email_phone_ssn_redaction_unchanged(self) -> None:
        result = redact_pii("Contact john@example.com for help")
        assert result == "Contact [EMAIL] for help"


class TestApplyPiiAction:
    """Tests for apply_pii_action function."""

    _CLEAN_EXAMPLE: dict = {"instruction": "Summarize this", "output": "Done"}
    _PII_EXAMPLE: dict = {
        "instruction": "Email john@example.com",
        "output": "Call 555-867-5309",
    }

    def test_flag_adds_annotation_when_pii_found(self) -> None:
        result = apply_pii_action(self._PII_EXAMPLE, "flag")
        assert result is not None
        assert result["pii_detected"] is True
        # original values not modified
        assert result["instruction"] == self._PII_EXAMPLE["instruction"]

    def test_flag_returns_unchanged_when_no_pii(self) -> None:
        result = apply_pii_action(self._CLEAN_EXAMPLE, "flag")
        assert result == self._CLEAN_EXAMPLE
        assert "pii_detected" not in result

    def test_redact_replaces_pii_in_values(self) -> None:
        result = apply_pii_action(self._PII_EXAMPLE, "redact")
        assert result is not None
        assert "[EMAIL]" in result["instruction"]
        assert "[PHONE]" in result["output"]
        assert "john@example.com" not in result["instruction"]

    def test_redact_preserves_non_pii_values(self) -> None:
        result = apply_pii_action(self._CLEAN_EXAMPLE, "redact")
        assert result == self._CLEAN_EXAMPLE

    def test_discard_returns_none_when_pii_found(self) -> None:
        assert apply_pii_action(self._PII_EXAMPLE, "discard") is None

    def test_discard_returns_example_when_no_pii(self) -> None:
        result = apply_pii_action(self._CLEAN_EXAMPLE, "discard")
        assert result == self._CLEAN_EXAMPLE

    def test_invalid_action_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid pii_action"):
            apply_pii_action(self._CLEAN_EXAMPLE, "unknown")

    def test_redact_preserves_non_string_values(self) -> None:
        example = {"text": "john@example.com", "count": 42, "active": True}
        result = apply_pii_action(example, "redact")
        assert result is not None
        assert result["count"] == 42
        assert result["active"] is True
        assert "[EMAIL]" in result["text"]

    def test_flag_does_not_mutate_original(self) -> None:
        original = {"text": "john@example.com"}
        result = apply_pii_action(original, "flag")
        assert "pii_detected" not in original
        assert result is not original


# ---------------------------------------------------------------------------
# History redaction policy (ENH-3750)
# ---------------------------------------------------------------------------

_PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC" + "A" * 24 + "=="


_BEGIN = "-----" + "BEGIN "  # fragments: keep literal PEM markers out of this file
_END = "-----" + "END "


def _pem(label: str = "RSA PRIVATE KEY", sep: str = "\n") -> str:
    return f"{_BEGIN}{label}-----{sep}{_PEM_BODY}{sep}{_END}{label}-----"


def _sanitize(payload: dict, host: str | None = None, event_type: str | None = None):
    return sanitize_history_payload(payload, host=host, event_type=event_type)


class TestHistoryTextFamilies:
    """Positive and near-miss fixture for every history rule family."""

    @pytest.mark.parametrize(
        "label",
        [
            "PRIVATE KEY",
            "RSA PRIVATE KEY",
            "EC PRIVATE KEY",
            "DSA PRIVATE KEY",
            "OPENSSH PRIVATE KEY",
            "ENCRYPTED PRIVATE KEY",
            "PGP PRIVATE KEY BLOCK",
        ],
    )
    @pytest.mark.parametrize("sep", ["\n", "\\n", "\r\n"])
    def test_complete_pem_block_removed(self, label: str, sep: str) -> None:
        text = f"before {_pem(label, sep)} after"
        out = redact_history_text(text)
        assert out == "before [PRIVATE_KEY_PEM] after"
        assert _PEM_BODY not in out and "END" not in out

    def test_multiple_pem_blocks_each_replaced_and_counted_once(self) -> None:
        text = f"{_pem()}\nmid\n{_pem('EC PRIVATE KEY')}"
        result = _sanitize({"t": text})
        assert result.payload == {"t": "[PRIVATE_KEY_PEM]\nmid\n[PRIVATE_KEY_PEM]"}
        assert result.counts == {"private_key_pem": 2}

    def test_truncated_pem_removed_to_end_of_text(self) -> None:
        text = f"x {_PEM_HEADER}\n{_PEM_BODY}\nmore text"
        assert redact_history_text(text) == "x [PRIVATE_KEY_PEM]"

    def test_public_key_and_certificate_headers_are_not_private_keys(self) -> None:
        for header in ("-----BEGIN PUBLIC KEY-----", "-----BEGIN CERTIFICATE-----"):
            text = f"{header}\n{_PEM_BODY}\n"
            assert redact_history_text(text) == text

    def test_legacy_placeholder_followed_by_key_material_and_end(self) -> None:
        text = f"k: [PRIVATE_KEY_PEM]\n{_PEM_BODY}\n{_END}RSA PRIVATE KEY-----\ndone"
        out = redact_history_text(text)
        assert out == "k: [PRIVATE_KEY_PEM]\ndone"
        assert _PEM_BODY not in out

    def test_legacy_placeholder_with_literal_escaped_newlines(self) -> None:
        text = f"[PRIVATE_KEY_PEM]\\n{_PEM_BODY}\\n{_END}EC PRIVATE KEY-----"
        assert redact_history_text(text) == "[PRIVATE_KEY_PEM]"

    def test_standalone_placeholder_unchanged_with_zero_count(self) -> None:
        result = _sanitize({"t": "key was [PRIVATE_KEY_PEM] here"})
        assert result.payload == {"t": "key was [PRIVATE_KEY_PEM] here"}
        assert result.counts == {}

    def test_bearer_keeps_scheme_and_replaces_whole_credential(self) -> None:
        cred = "abc.DEF-123_456~+/xyz=="
        out = redact_history_text(f"Authorization-ish: bearer {cred}; next")
        assert out == "Authorization-ish: bearer [BEARER_CREDENTIAL]; next"

    def test_bearer_scheme_is_case_insensitive_and_authorization_header(self) -> None:
        out = redact_history_text("Authorization: BEARER sk0123456789abcdef")
        assert out == "Authorization: BEARER [BEARER_CREDENTIAL]"
        assert _sanitize({"t": "Authorization: Bearer sk0123456789abcdef"}).counts == {
            "bearer_credential": 1
        }

    def test_bearer_near_misses(self) -> None:
        for text in ("Bearer short", "Bearer", "notbearer abcdefghijkl", "Bearer\nabcdefghijkl"):
            assert redact_history_text(text) == text

    def test_uri_userinfo_removed_and_uri_remains_parseable(self) -> None:
        from urllib.parse import urlsplit

        cases = {
            "https://user:pa%40ss@example.com:8443/p?q=1#f": "https://example.com:8443/p?q=1#f",
            "postgres://admin@db.internal/x": "postgres://db.internal/x",
            "https://u:p@[2001:db8::1]:443/a": "https://[2001:db8::1]:443/a",
            "ssh://git@host/repo.git": "ssh://host/repo.git",
            "http://a:b@@host/": "http://host/",
        }
        for raw, expected in cases.items():
            out = redact_history_text(raw)
            assert out == expected
            assert urlsplit(out).hostname

    def test_uri_without_userinfo_and_standalone_email_unchanged_family(self) -> None:
        assert redact_history_text("https://example.com/a@b") == "https://example.com/a@b"
        assert redact_history_text("see me@example.com") == "see [EMAIL]"
        counts = _sanitize({"t": "mail me@example.com"}).counts
        assert counts == {"email": 1}

    def test_uri_userinfo_counts_once_and_swallows_nested_token(self) -> None:
        token = "gh" + "p_" + "a" * 36
        result = _sanitize({"t": f"git clone https://{token}@github.com/o/r"})
        assert result.payload == {"t": "git clone https://github.com/o/r"}
        assert result.counts == {"uri_userinfo": 1}

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("password=hunter2", "password=[CREDENTIAL_FIELD]"),
            ("password = hunter2 trailing", "password = [CREDENTIAL_FIELD] trailing"),
            ('{"password": "hun ter2"}', '{"password": "[CREDENTIAL_FIELD]"}'),
            ("{'api_key': 'abc def'}", "{'api_key': '[CREDENTIAL_FIELD]'}"),
            (
                "export AWS_SECRET_ACCESS_KEY=abcd/efgh",
                "export AWS_SECRET_ACCESS_KEY=[CREDENTIAL_FIELD]",
            ),
            ("apiKey: abc123&x=1", "apiKey: [CREDENTIAL_FIELD]&x=1"),
            ('client-secret="a b" next', 'client-secret="[CREDENTIAL_FIELD]" next'),
            ("Authorization: Basic dXNlcjpwYXNz", "Authorization: [CREDENTIAL_FIELD]"),
            ('{\\"password\\":\\"abc d\\"}', '{\\"password\\":\\"[CREDENTIAL_FIELD]\\"}'),
            ('pw: x\npassword="open\nrest', 'pw: x\npassword="[CREDENTIAL_FIELD]\nrest'),
            ("passwd:abc;next", "passwd:[CREDENTIAL_FIELD];next"),
        ],
    )
    def test_credential_field_values(self, text: str, expected: str) -> None:
        assert redact_history_text(text) == expected

    def test_credential_field_aliases_all_covered(self) -> None:
        for alias in HISTORY_CREDENTIAL_FIELD_ALIASES:
            for spelling in (alias, alias.upper(), alias.replace("_", "-")):
                assert redact_history_text(f"{spelling}=v4lue") == f"{spelling}=[CREDENTIAL_FIELD]"

    def test_credential_field_near_misses(self) -> None:
        for text in (
            "input_tokens=5",
            "max_tokens: 4096",
            "token_count=3",
            "my_password_hint=abc",
            "keyboard: qwerty",
            "secret=abc",
            "key=abc",
            "id=abc",
            'password=""',
            "passwords=abc",
        ):
            assert redact_history_text(text) == text

    def test_credential_field_beats_nested_fixed_shape_token(self) -> None:
        aws = "AKIA" + "I" * 16
        result = _sanitize({"t": f"aws_access_key_id={aws}"})
        assert result.payload == {"t": "aws_access_key_id=[CREDENTIAL_FIELD]"}
        assert result.counts == {"credential_field": 1}

    def test_authorization_bearer_value_counts_bearer_only_and_is_stable(self) -> None:
        result = _sanitize({"t": "Authorization: Bearer abcdefgh12345"})
        assert result.payload == {"t": "Authorization: Bearer [BEARER_CREDENTIAL]"}
        assert result.counts == {"bearer_credential": 1}
        assert _sanitize(result.payload).counts == {}

    @pytest.mark.parametrize(
        ("secret", "rule"),
        [
            ("AKIA" + "I" * 16, "aws_access_key"),
            ("gh" + "p_" + "a" * 36, "github_token"),
            ("sk-ant-" + "a" * 24, "anthropic_key"),
            ("xoxb-" + "1234567890", "slack_token"),
            ("eyJ" + "a" * 10 + ".eyJ" + "a" * 10 + "." + "a" * 10, "jwt"),
            ("someone@example.com", "email"),
            ("555-123-4567", "phone"),
            ("123-45-6789", "ssn"),
        ],
    )
    def test_existing_fixed_shape_families_use_existing_placeholders(
        self, secret: str, rule: str
    ) -> None:
        result = _sanitize({"t": f"x {secret} y"})
        assert result.payload == {"t": f"x [{rule.upper()}] y"}
        assert result.counts == {rule: 1}

    def test_decoded_unicode_escape_credential_is_found(self) -> None:
        # json decodes the escape to the real character sequence; the policy sees decoded text.
        token = "sk-ant-" + "a" * 24
        escaped = "".join(f"\\u{ord(c):04x}" for c in token)
        payload = json.loads('{"t": "key ' + escaped + ' end"}')
        assert escaped not in json.dumps(payload)
        assert _sanitize(payload).payload == {"t": "key [ANTHROPIC_KEY] end"}

    def test_placeholder_like_text_with_extra_content_is_still_scanned(self) -> None:
        out = redact_history_text("[CREDENTIAL_FIELD]x password=[CREDENTIAL_FIELD]x")
        assert out == "[CREDENTIAL_FIELD]x password=[CREDENTIAL_FIELD]"

    def test_finite_placeholders_match_no_detector(self) -> None:
        for placeholder in HISTORY_PLACEHOLDERS:
            assert redact_history_text(placeholder) == placeholder
            assert _sanitize({"k": placeholder}).counts == {}
            assert detect_pii(placeholder) == []
            assert scan_text(placeholder) == []

    def test_rule_ids_and_counts_use_the_finite_table(self) -> None:
        text = f"{_pem()} Bearer abcdefgh1234 https://u@h.com password=x me@a.co 123-45-6789"
        counts = _sanitize({"t": text}).counts
        assert set(counts) <= set(HISTORY_RULE_IDS)
        assert counts == {
            "bearer_credential": 1,
            "credential_field": 1,
            "email": 1,
            "private_key_pem": 1,
            "ssn": 1,
            "uri_userinfo": 1,
        }

    def test_version_constant(self) -> None:
        assert HISTORY_REDACTION_VERSION == 1


class TestHistoryPayload:
    def test_returns_fresh_payload_without_mutating_or_aliasing_input(self) -> None:
        inner = {"a": ["x me@example.com", {"b": 1}]}
        payload = {"k": inner, "n": [1, 2.5, True, None]}
        before = copy.deepcopy(payload)
        result = _sanitize(payload)
        assert payload == before
        assert result.payload["k"] is not inner
        assert result.payload["k"]["a"] is not inner["a"]
        assert result.payload["n"] is not payload["n"]
        assert result.payload["k"]["a"][0] == "x [EMAIL]"

    def test_numbers_bools_nulls_untouched_including_in_credential_fields(self) -> None:
        payload = {"password": 123456789, "api_key": True, "token": None, "x": 1.5}
        result = _sanitize(payload)
        assert result.payload == payload
        assert result.counts == {}

    def test_credential_field_value_scope_string_list_object(self) -> None:
        payload = {
            "password": "p4ss",
            "api_key": ["a", {"nested": "b", "n": 3}, 7],
            "client_secret": {"k": ["c", None]},
            "empty": {"password": ""},
        }
        result = _sanitize(payload)
        assert result.payload == {
            "password": "[CREDENTIAL_FIELD]",
            "api_key": ["[CREDENTIAL_FIELD]", {"nested": "[CREDENTIAL_FIELD]", "n": 3}, 7],
            "client_secret": {"k": ["[CREDENTIAL_FIELD]", None]},
            "empty": {"password": ""},
        }
        assert result.counts == {"credential_field": 4}

    def test_credential_key_aliases_normalize_case_and_separators(self) -> None:
        for key in ("apiKey", "API-KEY", "Api_Key", "AWS_SECRET_ACCESS_KEY", "proxy-authorization"):
            assert _sanitize({key: "v"}).payload == {key: "[CREDENTIAL_FIELD]"}
        for key in ("token", "key", "id", "secret", "input_tokens", "my_password"):
            assert _sanitize({key: "v"}).payload == {key: "v"}

    def test_mapping_keys_are_scanned_and_nonsecret_keys_keep_order(self) -> None:
        payload = {"z": 1, "who@example.com": 2, "a": 3}
        result = _sanitize(payload)
        assert list(result.payload) == ["z", "[EMAIL]", "a"]
        assert result.counts == {"email": 1}

    @pytest.mark.parametrize(
        "payload",
        [
            {"a@example.com": 1, "[EMAIL]": 2},
            {"[EMAIL]": 2, "a@example.com": 1},
            {"a@example.com": 1, "b@example.com": 2},
        ],
    )
    def test_key_collision_is_rejected(self, payload: dict) -> None:
        with pytest.raises(HistorySanitizationError) as exc:
            _sanitize(payload)
        assert exc.value.reason == "key_collision"

    @pytest.mark.parametrize(
        "payload",
        [
            {1: "a"},
            {"a": (1, 2)},
            {"a": {1, 2}},
            {"a": object()},
            {"a": float("nan")},
            {"a": float("inf")},
            {"a": b"bytes"},
        ],
    )
    def test_invalid_shapes_are_rejected(self, payload: dict) -> None:
        with pytest.raises(HistorySanitizationError) as exc:
            _sanitize(payload)
        assert exc.value.reason == "invalid_payload"

    def test_non_dict_root_and_cycles_are_rejected(self) -> None:
        for bad in ([], "s", None, 3):
            with pytest.raises(HistorySanitizationError) as exc:
                sanitize_history_payload(bad)  # type: ignore[arg-type]
            assert exc.value.reason == "invalid_payload"
        cyc: dict = {}
        cyc["self"] = [cyc]
        with pytest.raises(HistorySanitizationError) as exc:
            _sanitize(cyc)
        assert exc.value.reason == "invalid_payload"

    def test_shared_subobject_is_not_a_cycle(self) -> None:
        shared = ["x me@example.com"]
        result = _sanitize({"a": shared, "b": shared})
        assert result.payload == {"a": ["x [EMAIL]"], "b": ["x [EMAIL]"]}
        assert result.payload["a"] is not result.payload["b"]

    def test_deep_nesting_fails_with_resource_limit_not_recursion_error(self) -> None:
        deep: dict = {}
        node = deep
        for _ in range(5000):
            node["n"] = {}
            node = node["n"]
        with pytest.raises(HistorySanitizationError) as exc:
            _sanitize(deep)
        assert exc.value.reason == "resource_limit"

    def test_result_serializes_and_second_pass_is_a_noop(self) -> None:
        payload = {
            "t": f"{_pem()} me@a.co password=x https://u:p@h.com Bearer abcdefgh1234",
            "k": {"api_key": ["a", "b"], "w@x.com": "v"},
        }
        first = _sanitize(payload)
        json.dumps(first.payload)
        second = _sanitize(first.payload)
        assert second.payload == first.payload
        assert second.counts == {}


class TestHistoryProtocolContext:
    _SID = "11111111-2222-3333-4444-555555555555"

    def _claude(self, **overrides: object) -> dict:
        record = {
            "type": "assistant",
            "sessionId": self._SID,
            "uuid": "aaaaaaaa-0000-4000-8000-000000000001",
            "parentUuid": None,
            "timestamp": "2026-10-05T01:02:03.456Z",
            "version": "2.1.284",
            "message": {
                "id": "msg_01ABC",
                "model": "claude-opus-5-5",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01X",
                        "name": "Bash",
                        "input": {"id": "me@a.co"},
                    },
                    {"type": "tool_result", "tool_use_id": "toolu_01X", "content": "ok"},
                ],
                "usage": {"input_tokens": 5, "output_tokens": 7},
            },
        }
        record.update(overrides)
        return record

    def test_registered_hosts_match_session_parsers(self) -> None:
        from little_loops.session_store.sessions import _PARSERS

        assert set(_PARSERS) == set(HISTORY_REGISTERED_HOSTS)

    @pytest.mark.parametrize("host", ["claude-code", "opencode", "pi", "qwen", "gemini", "omp"])
    def test_claude_shaped_identity_survives_and_tool_lookalike_is_scanned(self, host: str) -> None:
        result = _sanitize(self._claude(), host, "assistant")
        out = result.payload
        assert out["message"]["content"][0]["id"] == "toolu_01X"
        assert out["message"]["content"][1]["tool_use_id"] == "toolu_01X"
        assert out["message"]["content"][0]["input"]["id"] == "[EMAIL]"
        assert out["message"]["usage"] == {"input_tokens": 5, "output_tokens": 7}
        assert result.counts == {"email": 1}

    def test_normalized_codex_exec_uses_claude_shape_but_native_codex_does_not(self) -> None:
        exec_record = {
            "type": "user",
            "sessionId": self._SID,
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1"}]},
        }
        assert _sanitize(exec_record, "codex", "user").payload == exec_record
        native = {"type": "token_count", "turn_id": "t1", "thread_id": "me@a.co"}
        # event_msg root has no thread_id exemption: it is scanned like any field
        assert _sanitize(native, "codex", "event_msg").payload["thread_id"] == "[EMAIL]"

    @pytest.mark.parametrize(
        ("event_type", "record"),
        [
            ("session_meta", {"id": "thread-1", "timestamp": "2026-10-05T00:00:00Z"}),
            ("turn_context", {"turn_id": "turn-1", "model": "gpt-5.1-codex"}),
            ("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            (
                "token_usage_record",
                {
                    "thread_id": "thread-1",
                    "turn_id": "t",
                    "response_id": "resp_1",
                    "usage": {"n": 1},
                },
            ),
        ],
    )
    def test_codex_native_protected_fields_survive(self, event_type: str, record: dict) -> None:
        assert _sanitize(record, "codex", event_type).payload == record

    def test_kimi_protects_only_what_consumers_read(self) -> None:
        record = {"type": "x", "timestamp": "t", "request_id": "me@a.co"}
        out = _sanitize(record, "kimi-code", "x").payload
        assert out == {"type": "x", "timestamp": "t", "request_id": "[EMAIL]"}

    def test_spoofed_tool_use_discriminator_gets_no_exemption(self) -> None:
        record = self._claude()
        record["message"]["content"][0] = {"type": "text", "id": "me@a.co"}
        out = _sanitize(record, "claude-code", "assistant").payload
        assert out["message"]["content"][0]["id"] == "[EMAIL]"

    def test_protected_path_with_secret_raises_unsafe_identity(self) -> None:
        for record in (
            self._claude(sessionId="user@example.com"),
            self._claude(uuid="AKIA" + "I" * 16),
        ):
            with pytest.raises(HistorySanitizationError) as exc:
                _sanitize(record, "claude-code", "assistant")
            assert exc.value.reason == "unsafe_identity"
        with pytest.raises(HistorySanitizationError) as exc:
            _sanitize({"turn_id": "me@a.co"}, "codex", "turn_context")
        assert exc.value.reason == "unsafe_identity"

    def test_unknown_or_missing_context_has_no_exemptions(self) -> None:
        record = {"sessionId": "me@a.co", "message": {"id": "x@y.com"}}
        for host, event in ((None, None), ("claude-code", None), (None, "assistant"), ("zzz", "a")):
            out = _sanitize(record, host, event).payload
            assert out == {"sessionId": "[EMAIL]", "message": {"id": "[EMAIL]"}}
        assert _sanitize({"id": "me@a.co"}, "codex", "unknown_type").payload == {"id": "[EMAIL]"}

    def test_opaque_fields_preserved_only_with_shape_and_discriminator(self) -> None:
        blob = "AAAA" + "b" * 60 + "=="
        content = [
            {"type": "thinking", "thinking": "mail me@a.co", "signature": blob},
            {"type": "redacted_thinking", "data": blob},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": blob},
            },
            {
                "type": "tool_result",
                "tool_use_id": "t",
                "content": [{"type": "image", "source": {"type": "base64", "data": blob}}],
            },
        ]
        record = {"type": "assistant", "message": {"id": "m", "content": content}}
        out = _sanitize(record, "claude-code", "assistant").payload["message"]["content"]
        assert out[0] == {"type": "thinking", "thinking": "mail [EMAIL]", "signature": blob}
        assert out[1]["data"] == blob
        assert out[2]["source"]["data"] == blob
        assert out[3]["content"][0]["source"]["data"] == blob

    def test_opaque_lookalikes_are_scanned(self) -> None:
        secret = "ghp_" + "a" * 36
        record = {
            "type": "assistant",
            "signature": secret,
            "data": secret,
            "input": {"type": "thinking", "signature": secret},
            "message": {
                "id": "m",
                "content": [
                    {"type": "thinking", "signature": secret},  # wrong shape: '_' not base64
                    {"type": "text", "signature": secret, "data": secret},
                    {
                        "type": "tool_use",
                        "id": "t",
                        "input": {"type": "redacted_thinking", "data": secret},
                    },
                ],
            },
        }
        raw = json.dumps(_sanitize(record, "claude-code", "assistant").payload)
        assert secret not in raw

    def test_codex_encrypted_reasoning_preserved_but_not_for_other_types(self) -> None:
        blob = "gAAAAAB" + "x_-" * 30
        keep = {"type": "reasoning", "encrypted_content": blob, "summary": ["me@a.co"]}
        out = _sanitize(keep, "codex", "response_item").payload
        assert out["encrypted_content"] == blob and out["summary"] == ["[EMAIL]"]
        spoof = {"type": "function_call", "encrypted_content": "AKIA" + "I" * 16}
        assert (
            _sanitize(spoof, "codex", "response_item").payload["encrypted_content"]
            == "[AWS_ACCESS_KEY]"
        )

    def test_ordinary_ids_hashes_and_base64ish_text_survive(self) -> None:
        text = (
            "550e8400-e29b-41d4-a716-446655440000 "
            "da39a3ee5e6b4b0d3255bfef95601890afd80709 "
            "SGVsbG8gd29ybGQsIHRoaXMgaXMgYmFzZTY0 toolu_01ABCdef call_9x8y7z"
        )
        assert redact_history_text(text) == text

    def test_hosts_with_null_basis_do_not_matter(self) -> None:
        # host_basis is an attribution qualifier, not a payload format; the API has no such arg.
        out = _sanitize(self._claude(), "claude-code", "assistant").payload
        assert out["sessionId"] == self._SID


class TestHistoryErrorSafety:
    _CANARY = "CANARY" + "SECRET" * 4

    def _assert_clean(self, exc: BaseException) -> None:
        rendered = "".join(traceback.format_exception(exc))
        assert self._CANARY not in rendered
        assert self._CANARY not in str(exc) + repr(exc) + repr(exc.args)
        assert exc.__cause__ is None and exc.__suppress_context__ is True

    def test_error_carries_only_fixed_reason(self) -> None:
        canary = self._CANARY
        cases = [
            ({f"{canary}@example.com": 1, "[EMAIL]": 2}, None, None, "key_collision"),
            ({"sessionId": f"{canary}@example.com"}, "claude-code", "user", "unsafe_identity"),
            ({canary: (1,)}, None, None, "invalid_payload"),
            ({canary: {1: canary}}, None, None, "invalid_payload"),
        ]
        for payload, host, event, reason in cases:
            with pytest.raises(HistorySanitizationError) as exc:
                sanitize_history_payload(payload, host=host, event_type=event)
            assert exc.value.reason == reason
            assert exc.value.reason in HISTORY_ERROR_REASONS
            assert str(exc.value) == reason
            self._assert_clean(exc.value)

    def test_text_api_rejects_non_str_safely(self) -> None:
        with pytest.raises(HistorySanitizationError) as exc:
            redact_history_text(b"x")  # type: ignore[arg-type]
        assert exc.value.reason == "invalid_payload"

    def test_error_is_a_value_error_for_backfill_workers(self) -> None:
        assert issubclass(HistorySanitizationError, ValueError)


class TestHistoryScaling:
    """Adversarial multi-MB inputs stay linear; a quadratic regex would take hours."""

    @pytest.mark.parametrize(
        "unit",
        [
            "a.",  # email local-part run
            "-eyJaaaaaaaa",  # JWT start-like fragments in one run
            "sk-ant-",
            "http://a",
            "password=",
            'password="',
            "Bearer ",
            _PEM_HEADER,
            "[PRIVATE_KEY_PEM]\n",
            "a@",
            "x:",
            "AKIA",
            "\\n",
        ],
    )
    def test_multi_megabyte_adversarial_text_is_bounded(self, unit: str) -> None:
        text = unit * (2_000_000 // len(unit))
        start = time.perf_counter()
        out = redact_history_text(text)
        assert time.perf_counter() - start < 30
        assert isinstance(out, str)

    def test_large_clean_text_and_many_matches(self) -> None:
        clean = "plain log line without secrets\n" * 100_000
        assert redact_history_text(clean) == clean
        many = "me@example.com 555-123-4567 AKIA" + "I" * 16 + " " * 1
        start = time.perf_counter()
        out = redact_history_text(many * 50_000)
        assert time.perf_counter() - start < 30
        assert "@" not in out

    def test_wide_payload_is_bounded(self) -> None:
        payload = {"items": [{"k": f"v{i}", "s": "me@a.co"} for i in range(50_000)]}
        start = time.perf_counter()
        result = _sanitize(payload)
        assert time.perf_counter() - start < 30
        assert result.counts == {"email": 50_000}


_ALPHABET = st.sampled_from(
    list("abcxyz019 \n\t.:=,;&@/_-'\"[]{}()\\")
    + ["Bearer ", "password", "=", "api_key", "https://", "u:p@", "AKIA", "I" * 16, "[EMAIL]"]
    + [_PEM_HEADER, _END + "RSA PRIVATE KEY-----", "[PRIVATE_KEY_PEM]"]
    + ["me@example.com", "123-45-6789", "555-123-4567", "ghp_" + "a" * 36, "[CREDENTIAL_FIELD]"]
    + ["Authorization: ", "\\n", "eyJaaaaaaaa", "sk-ant-" + "b" * 22]
)
_TEXT = st.lists(_ALPHABET, max_size=14).map("".join)
_LEAF = st.one_of(
    _TEXT,
    st.integers(-5, 5),
    st.booleans(),
    st.none(),
    st.floats(allow_nan=False, allow_infinity=False),
)
_KEY = st.one_of(
    st.sampled_from(["password", "api_key", "token", "id", "[EMAIL]", "me@example.com", "k"]),
    _TEXT,
)
_JSON = st.recursive(
    _LEAF,
    lambda children: st.one_of(
        st.lists(children, max_size=4), st.dictionaries(_KEY, children, max_size=4)
    ),
    max_leaves=18,
)
_PROP = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


class TestHistoryProperties:
    @_PROP
    @given(_TEXT)
    def test_text_is_idempotent_with_no_detectable_remainder(self, text: str) -> None:
        once = redact_history_text(text)
        assert redact_history_text(once) == once
        counts: dict[str, int] = {}
        assert _sanitize({"t": once}).counts == counts

    @_PROP
    @given(_TEXT)
    def test_text_is_deterministic_and_has_no_supported_secret_left(self, text: str) -> None:
        out = redact_history_text(text)
        assert out == redact_history_text(text)
        for rule in CREDENTIAL_RULES:
            if rule.name == "private_key_pem":
                continue
            assert rule.pattern.search(out) is None

    @_PROP
    @given(st.dictionaries(_KEY, _JSON, max_size=5))
    def test_payload_properties(self, payload: dict) -> None:
        before = copy.deepcopy(payload)
        try:
            first = _sanitize(payload)
        except HistorySanitizationError as exc:
            assert exc.reason == "key_collision"
            return
        assert payload == before
        json.dumps(first.payload)
        second = _sanitize(first.payload)
        assert second.payload == first.payload
        assert second.counts == {}
        assert set(first.counts) <= set(HISTORY_RULE_IDS)
        assert all(n > 0 for n in first.counts.values())
        assert _sanitize(payload).counts == first.counts  # deterministic

    @_PROP
    @given(_JSON)
    def test_nonsecret_structure_is_preserved(self, value: object) -> None:
        def skeleton(v: object) -> object:
            if isinstance(v, dict):
                return ("dict", [skeleton(x) for x in v.values()])
            if isinstance(v, list):
                return ("list", [skeleton(x) for x in v])
            if isinstance(v, str):
                return "str"
            return (type(v).__name__, v)  # numbers/bools/null are never altered

        try:
            out = _sanitize({"root": value}).payload["root"]
        except HistorySanitizationError as exc:
            assert exc.reason == "key_collision"
            return
        assert skeleton(out) == skeleton(value)


class TestHistoryExistingApiUnchanged:
    def test_scanner_semantics_untouched(self) -> None:
        assert CREDENTIAL_SCANNER_VERSION == 1
        assert [r.name for r in CREDENTIAL_RULES] == [
            "aws_access_key",
            "github_token",
            "anthropic_key",
            "slack_token",
            "private_key_pem",
            "jwt",
        ]
        assert redact_pii(_PEM_HEADER) == "[PRIVATE_KEY_PEM]"
        assert redact_pii(f"{_PEM_HEADER}\nbody") == "[PRIVATE_KEY_PEM]\nbody"

    def test_top_level_package_does_not_export_history_api(self) -> None:
        import little_loops

        for name in ("redact_history_text", "sanitize_history_payload", "HistorySanitizationError"):
            assert not hasattr(little_loops, name)
