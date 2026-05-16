# ENH-069: Add Corrupted State File Edge Case Tests for ll-loop

## Summary

The persistence layer handles basic invalid JSON but lacks tests for edge cases like truncated files, zero-byte files, and encoding issues. These edge cases can occur in real-world scenarios (disk full, crash during write, encoding mismatch).

## Current State

- **Test File**: `scripts/tests/test_fsm_persistence.py` (~920 lines)
- **Corruption Tests**: Basic invalid JSON tested
- **Edge Cases**: Not tested

### What's Covered

```python
# Existing tests
def test_load_state_returns_none_for_invalid_json  # Malformed JSON
def test_read_events_skips_malformed_lines         # Bad JSONL line
```

### What's Missing

Tests for:
1. Zero-byte state file
2. Truncated JSON (e.g., `{"status": "runn`)
3. State file with wrong encoding (UTF-16 vs UTF-8)
4. Binary garbage in file
5. Very large state file
6. Missing expected fields in otherwise valid JSON

## Proposed Tests

### File Corruption Edge Cases

```python
class TestCorruptedStateFiles:
    """Tests for corrupted state file handling."""

    def test_zero_byte_state_file(self, tmp_loops_dir: Path):
        """Zero-byte state file should be handled gracefully."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text("")  # Empty file

        result = persistence.load_state()
        assert result is None

    def test_truncated_json_state_file(self, tmp_loops_dir: Path):
        """Truncated JSON should not crash."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"status": "running", "current_sta')  # Cut off

        result = persistence.load_state()
        assert result is None

    def test_binary_garbage_state_file(self, tmp_loops_dir: Path):
        """Binary content in state file handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_bytes(b'\x00\xff\xfe\x80\x90')  # Random bytes

        result = persistence.load_state()
        assert result is None

    def test_wrong_encoding_state_file(self, tmp_loops_dir: Path):
        """Non-UTF-8 encoding handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        content = '{"status": "running"}'.encode('utf-16')
        persistence.state_file.write_bytes(content)

        result = persistence.load_state()
        assert result is None  # Should not crash
```

### Field Validation Edge Cases

```python
    def test_missing_required_field_in_state(self, tmp_loops_dir: Path):
        """State JSON missing required field handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"loop_name": "test"}')  # Missing current_state

        result = persistence.load_state()
        assert result is None  # Should return None due to KeyError

    def test_wrong_type_for_field_in_state(self, tmp_loops_dir: Path):
        """Wrong type for field handled gracefully."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"loop_name": 123, "current_state": "test"}')

        result = persistence.load_state()
        # Should validate type or handle gracefully

    def test_null_values_in_state(self, tmp_loops_dir: Path):
        """Null values for required fields handled."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.state_file.write_text('{"loop_name": null, "current_state": null}')

        result = persistence.load_state()
        # Should handle null appropriately
```

### Events File Corruption

```python
    def test_truncated_events_file(self, tmp_loops_dir: Path):
        """Truncated events JSONL recovers gracefully."""
        persistence = StatePersistence("test-loop", tmp_loops_dir)
        persistence.initialize()
        persistence.events_file.write_text('{"event": "start"}\n{"event": "tran')  # Cut off mid-line

        events = persistence.read_events()
        assert len(events) == 1  # Only valid line loaded
```

## Implementation Approach

Add tests to `test_fsm_persistence.py`:

1. Create various corrupted state files
2. Test `load_state()` and `load_events()` behavior
3. Verify no crashes (returns None or raises expected exception)
4. Document expected behavior for each case

## Impact

- **Priority**: P4 (Low)
- **Effort**: Low
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Test for zero-byte state file
- [x] Test for truncated JSON
- [x] Test for binary garbage
- [x] Test for wrong encoding
- [x] Test for missing required fields
- [x] Test for wrong field types
- [x] Test for truncated events file
- [x] All tests verify graceful handling (no crashes)
- [x] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `persistence`, `edge-cases`

---

## Status

**Open** | Created: 2026-01-15 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_fsm_persistence.py`: Added `TestCorruptedStateFiles` class with 8 new tests:
  - `test_zero_byte_state_file` - Tests empty state file handling
  - `test_truncated_json_state_file` - Tests incomplete JSON handling
  - `test_binary_garbage_state_file` - Tests binary content handling
  - `test_wrong_encoding_state_file` - Tests UTF-16 encoded content handling
  - `test_missing_required_field_in_state` - Tests missing field handling
  - `test_wrong_type_for_field_in_state` - Documents type handling behavior
  - `test_null_values_in_state` - Documents null value handling behavior
  - `test_truncated_events_file` - Tests truncated JSONL recovery

### Verification Results
- Tests: PASS (51 tests, all passing)
- Lint: PASS
- Types: PASS
