"""Unit tests for scripts/tests/helpers.py's general-purpose test utilities."""

from __future__ import annotations

from tests.helpers import sgr_codes


class TestSgrCodes:
    def test_extracts_bare_basic_16_code(self) -> None:
        assert sgr_codes("\033[32mgreen\033[0m") == {"32", "0"}

    def test_extracts_compound_basic_16_code(self) -> None:
        assert sgr_codes("\033[32;1mbold green\033[0m") == {"32;1", "0"}

    def test_extracts_multi_segment_indexed_256_code(self) -> None:
        assert sgr_codes("\033[38;5;240mgray\033[0m") == {"38;5;240", "0"}

    def test_extracts_multi_segment_indexed_256_bold_code(self) -> None:
        assert sgr_codes("\033[38;5;240;1mbold gray\033[0m") == {"38;5;240;1", "0"}

    def test_deduplicates_repeated_codes(self) -> None:
        assert sgr_codes("\033[1ma\033[1mb\033[1mc") == {"1"}

    def test_empty_text_yields_empty_set(self) -> None:
        assert sgr_codes("") == set()

    def test_text_without_sgr_yields_empty_set(self) -> None:
        assert sgr_codes("plain text, no escapes") == set()

    def test_non_sgr_csi_sequence_is_ignored(self) -> None:
        # Cursor-position and other CSI sequences ending in a letter other
        # than "m" are not SGR codes and must not be picked up.
        assert sgr_codes("\033[2J\033[H\033[32mgreen\033[0m") == {"32", "0"}
