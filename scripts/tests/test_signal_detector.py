"""Tests for signal_detector module."""

from little_loops.fsm.signal_detector import (
    ERROR_SIGNAL,
    HANDOFF_SIGNAL,
    STOP_SIGNAL,
    SignalDetector,
    SignalPattern,
)


class TestSignalPattern:
    """Tests for SignalPattern class."""

    def test_handoff_pattern_matches(self) -> None:
        """HANDOFF_SIGNAL matches CONTEXT_HANDOFF: with payload."""
        signal = HANDOFF_SIGNAL.search("CONTEXT_HANDOFF: Continue from iteration 5")
        assert signal is not None
        assert signal.signal_type == "handoff"
        assert signal.payload == "Continue from iteration 5"

    def test_handoff_pattern_with_whitespace(self) -> None:
        """HANDOFF_SIGNAL handles extra whitespace after colon."""
        signal = HANDOFF_SIGNAL.search("CONTEXT_HANDOFF:   Ready for fresh session")
        assert signal is not None
        assert signal.payload == "Ready for fresh session"

    def test_error_pattern_matches(self) -> None:
        """ERROR_SIGNAL matches FATAL_ERROR: with payload."""
        signal = ERROR_SIGNAL.search("FATAL_ERROR: Database connection failed")
        assert signal is not None
        assert signal.signal_type == "error"
        assert signal.payload == "Database connection failed"

    def test_stop_pattern_matches(self) -> None:
        """STOP_SIGNAL matches LOOP_STOP: with optional payload."""
        signal = STOP_SIGNAL.search("LOOP_STOP: User requested")
        assert signal is not None
        assert signal.signal_type == "stop"
        assert signal.payload == "User requested"

    def test_stop_pattern_empty_payload(self) -> None:
        """STOP_SIGNAL works with empty payload."""
        signal = STOP_SIGNAL.search("LOOP_STOP:")
        assert signal is not None
        assert signal.signal_type == "stop"
        assert signal.payload == ""

    def test_custom_pattern(self) -> None:
        """Custom pattern works."""
        custom = SignalPattern("custom", r"MY_SIGNAL:\s*(.+)")
        signal = custom.search("MY_SIGNAL: hello world")
        assert signal is not None
        assert signal.signal_type == "custom"
        assert signal.payload == "hello world"

    def test_pattern_no_match(self) -> None:
        """Pattern returns None when not found."""
        signal = HANDOFF_SIGNAL.search("Normal output without signals")
        assert signal is None

    def test_raw_match_captured(self) -> None:
        """DetectedSignal captures the raw matched string."""
        signal = HANDOFF_SIGNAL.search("prefix CONTEXT_HANDOFF: payload suffix")
        assert signal is not None
        assert "CONTEXT_HANDOFF: payload" in signal.raw_match


class TestSignalDetector:
    """Tests for SignalDetector class."""

    def test_detect_first_handoff(self) -> None:
        """Detect handoff signal in output."""
        detector = SignalDetector()
        output = "Running check...\nCONTEXT_HANDOFF: Continue from iteration 5\nDone."
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "handoff"
        assert signal.payload == "Continue from iteration 5"

    def test_detect_first_error(self) -> None:
        """Detect error signal in output."""
        detector = SignalDetector()
        output = "Processing...\nFATAL_ERROR: Database connection failed"
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "error"
        assert signal.payload == "Database connection failed"

    def test_no_signal(self) -> None:
        """Normal output without signals."""
        detector = SignalDetector()
        output = "All checks passed."
        signal = detector.detect_first(output)
        assert signal is None

    def test_detect_multiple(self) -> None:
        """Detect all signals in output."""
        detector = SignalDetector()
        output = "CONTEXT_HANDOFF: foo\nFATAL_ERROR: bar"
        signals = detector.detect(output)
        assert len(signals) == 2
        types = {s.signal_type for s in signals}
        assert types == {"handoff", "error"}

    def test_multiline_output(self) -> None:
        """Finds signal in long multiline output."""
        detector = SignalDetector()
        output = """
        Processing issue BUG-001...
        Work completed successfully.
        CONTEXT_HANDOFF: Ready for fresh session
        Cleaning up resources.
        """
        signal = detector.detect_first(output)
        assert signal is not None
        assert signal.signal_type == "handoff"

    def test_custom_patterns_only(self) -> None:
        """Custom patterns replace defaults."""
        custom = SignalPattern("custom", r"CUSTOM:\s*(.+)")
        detector = SignalDetector(patterns=[custom])

        # Should not detect default patterns
        assert detector.detect_first("CONTEXT_HANDOFF: test") is None

        # Should detect custom pattern
        signal = detector.detect_first("CUSTOM: value")
        assert signal is not None
        assert signal.signal_type == "custom"

    def test_priority_order(self) -> None:
        """First pattern in list has priority."""
        # Custom pattern that would match same text
        custom = SignalPattern("custom_handoff", r"CONTEXT_HANDOFF:\s*(.+)")
        detector = SignalDetector(patterns=[custom, HANDOFF_SIGNAL])

        signal = detector.detect_first("CONTEXT_HANDOFF: test")
        assert signal is not None
        # Custom pattern should win because it's first
        assert signal.signal_type == "custom_handoff"

    def test_empty_output(self) -> None:
        """Empty output returns None."""
        detector = SignalDetector()
        assert detector.detect_first("") is None
        assert detector.detect("") == []

    def test_default_patterns(self) -> None:
        """Default patterns include handoff, error, stop."""
        detector = SignalDetector()
        assert len(detector.patterns) == 3
        pattern_names = {p.name for p in detector.patterns}
        assert pattern_names == {"handoff", "error", "stop"}
