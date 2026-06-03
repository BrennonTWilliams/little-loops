"""Tests for the pii module."""

from __future__ import annotations

import pytest

from little_loops.pii import apply_pii_action, detect_pii, redact_pii


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
