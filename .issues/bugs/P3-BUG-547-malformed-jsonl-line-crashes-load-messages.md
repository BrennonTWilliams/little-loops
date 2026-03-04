---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# BUG-547: Malformed JSON line in input JSONL crashes `_load_messages` — no partial results

## Summary

`_load_messages` calls `json.loads(line)` with no exception handling. A single malformed line anywhere in the JSONL input file raises `json.JSONDecodeError`, abandons all messages (including those already parsed), and produces no output. The error message does not identify which line was malformed.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 346–354 (at scan commit: a574ea0)
- **Anchor**: `in function _load_messages`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L346-L354)
- **Code**:
```python
def _load_messages(messages_file: Path) -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    messages = []
    with open(messages_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))   # raises json.JSONDecodeError — uncaught
    return messages
```

## Current Behavior

Any non-JSON content in the input file (truncated write, comment line, encoding artifact, accidental newline in content) causes `ll-workflows analyze` to crash. The outer `except Exception` in `main()` prints the error, but no partial results are written and no line number is reported.

## Expected Behavior

Malformed lines are skipped with a warning (including the 1-based line number), and analysis proceeds on all valid messages. Or, optionally, the tool fails with a clear error message that identifies the offending line number.

## Motivation

A single malformed line in the input file causes the entire analysis to abort, discarding all valid messages parsed before the bad line. Real-world JSONL files can have encoding artifacts, manual edits, or truncated writes — any of which produce no output instead of partial-but-useful results. The lack of line-number reporting in the error also makes debugging which line is broken unnecessarily difficult.

## Steps to Reproduce

1. Create a JSONL file where line 50 contains `# session break` (a non-JSON comment).
2. Run `ll-workflows analyze --input <file> --patterns <patterns.yaml>`.
3. Observe crash: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`.
4. No output file is produced even though lines 1–49 were valid.

## Actual Behavior

`json.JSONDecodeError` propagates uncaught from `_load_messages`. The exception message references the malformed JSON fragment, not the file line number.

## Root Cause

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Anchor**: `in function _load_messages`
- **Cause**: `json.loads(line)` is called in a bare loop with no `try/except`. `json.JSONDecodeError` is a subclass of `ValueError` — it could be caught with `except ValueError`.

## Proposed Solution

Wrap the `json.loads` call and report skipped lines:

```python
def _load_messages(messages_file: Path) -> list[dict[str, Any]]:
    """Load messages from JSONL file."""
    messages = []
    skipped = 0
    with open(messages_file, encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                skipped += 1
                print(f"Warning: skipping malformed line {line_num}: {e}", file=sys.stderr)
    if skipped:
        print(f"Warning: skipped {skipped} malformed line(s) in {messages_file}", file=sys.stderr)
    return messages
```

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `_load_messages`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows` calls `_load_messages`

### Similar Patterns
- N/A — no other JSONL loaders in the module

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — add `TestLoadMessages` class with malformed-line test case

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `try/except json.JSONDecodeError` inside `_load_messages` loop
2. Track and report skipped line count and line numbers to stderr
3. Add direct unit test for `_load_messages` with a malformed line in the middle

## Impact

- **Priority**: P3 - Silent data loss on any imperfect JSONL file; `ll-messages` output is generally clean but real-world JSONL files can have encoding issues or be manually edited
- **Effort**: Small - ~10 lines, contained to one function
- **Risk**: Low - Change only adds resilience; no behavior change for valid input
- **Breaking Change**: No

## Labels

`bug`, `workflow-analyzer`, `error-handling`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
