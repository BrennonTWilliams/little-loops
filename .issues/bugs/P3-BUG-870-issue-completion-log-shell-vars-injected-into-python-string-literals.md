---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-870: issue-completion-log.sh shell vars injected into Python string literals

## Summary

`issue-completion-log.sh` embeds `$DEST_PATH` and `$TRANSCRIPT_PATH` directly inside single-quoted Python string literals within a double-quoted shell heredoc. If either path contains a single quote, the generated Python code has a syntax error. All errors are swallowed by `|| true`, so failures are invisible. The fix is to pass values via environment variables instead of shell interpolation.

## Steps to Reproduce

1. Create a completed issue with a path containing a single quote (e.g., `it's-fixed.md` in an unusual directory)
2. Or: construct a transcript path containing a single quote
3. Trigger the hook via a `git mv` Bash command
4. Observe: Python process silently fails; no session log entry appended

## Current Behavior

```bash
python3 -c "
...
dest = Path('$DEST_PATH')
jsonl = Path('$TRANSCRIPT_PATH')
```

Shell substitutes `$DEST_PATH` and `$TRANSCRIPT_PATH` into the Python source string. A path like `/issues/it's-a-dir/file.md` produces `dest = Path('/issues/it's-a-dir/file.md')` — a Python `SyntaxError`. The `|| true` at the end swallows the non-zero exit code silently.

## Expected Behavior

Path values should be passed safely regardless of special characters in the path. The Python script should always execute successfully when the paths are valid filesystem paths.

## Root Cause

- **File**: `hooks/scripts/issue-completion-log.sh`
- **Anchor**: `python3 -c` invocation block
- **Cause**: Direct shell variable interpolation into Python string literals. Single quotes in path values terminate the Python string literal prematurely, breaking syntax. The `|| true` error suppression masks all failures.

## Motivation

Session log entries in completed issues are used for audit trails and session continuity. Silent failures mean log entries are missing without any indication. The fix is also a general hardening for robustness on non-trivial filesystem paths.

## Proposed Solution

Pass values via environment variables instead of interpolation:

```bash
# Before:
python3 -c "
...
dest = Path('$DEST_PATH')
jsonl = Path('$TRANSCRIPT_PATH')
..." || true

# After:
DEST_PATH="$DEST_PATH" TRANSCRIPT_PATH="$TRANSCRIPT_PATH" python3 -c "
import os
from pathlib import Path
from little_loops.session_log import append_session_log_entry
dest = Path(os.environ['DEST_PATH'])
jsonl = Path(os.environ['TRANSCRIPT_PATH'])
..." || true
```

Environment variable values are never interpreted as Python syntax, making this safe for any valid filesystem path.

## Integration Map

### Files to Modify
- `hooks/scripts/issue-completion-log.sh` — replace string interpolation with env var passing

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers this script as the `PostToolUse`/`Bash` matcher handler

### Similar Patterns
- Other `python3 -c` invocations in `hooks/scripts/` — check for same pattern

### Tests
- `scripts/tests/test_hooks_integration.py` — no existing coverage for `issue-completion-log.sh`; new test class needed (cf. `TestUserPromptCheck` pattern for special-character injection tests)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Refactor `python3 -c` call in `issue-completion-log.sh` to use env var injection
2. Verify Python code uses `os.environ['DEST_PATH']` and `os.environ['TRANSCRIPT_PATH']`
3. Test with a path containing a single quote to confirm it no longer breaks

## Impact

- **Priority**: P3 - Affects reliability of session logging; silent failure makes it hard to detect
- **Effort**: Small - Targeted refactor of one python3 invocation
- **Risk**: Low - Additive change; env var injection is strictly safer than string interpolation
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `bug`, `captured`

## Session Log
- `/ll:format-issue` - 2026-03-23T22:43:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
