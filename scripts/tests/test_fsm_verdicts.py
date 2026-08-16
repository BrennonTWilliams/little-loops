"""Tests for little_loops.fsm.verdicts (ENH-3185 AC8)."""

from __future__ import annotations

from little_loops.fsm.verdicts import (
    BINARY_VERDICT_ENUM,
    CANNOT_JUDGE,
    CANNOT_JUDGE_DISPLAY,
    DEFAULT_VERDICT_ENUM,
    is_abstention_verdict,
)


def test_cannot_judge_constant() -> None:
    assert CANNOT_JUDGE == "cannot_judge"
    assert CANNOT_JUDGE_DISPLAY == "CANNOT JUDGE"


def test_default_verdict_enum_is_full_grammar() -> None:
    assert set(DEFAULT_VERDICT_ENUM) == {"yes", "no", "blocked", "partial", "cannot_judge"}


def test_binary_verdict_enum_stays_binary() -> None:
    assert BINARY_VERDICT_ENUM == ("yes", "no")


def test_is_abstention_verdict_matches_base_and_suffixed() -> None:
    assert is_abstention_verdict("cannot_judge") is True
    assert is_abstention_verdict("cannot_judge_uncertain") is True


def test_is_abstention_verdict_rejects_others() -> None:
    for verdict in ("yes", "no", "blocked", "partial", "error", "cannot_judgex"):
        assert is_abstention_verdict(verdict) is False
