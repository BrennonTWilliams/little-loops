"""Tests for the pii module."""

from __future__ import annotations

import re

import pytest

from little_loops.pii import (
    CREDENTIAL_RULES,
    CREDENTIAL_SCANNER_VERSION,
    CredentialFinding,
    CredentialRule,
    apply_pii_action,
    credential_rules_sha,
    detect_pii,
    redact_pii,
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
