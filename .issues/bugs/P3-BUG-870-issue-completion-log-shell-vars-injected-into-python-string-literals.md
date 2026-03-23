---
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact interpolation lines**: `issue-completion-log.sh:43` (`dest = Path('$DEST_PATH')`) and `issue-completion-log.sh:44` (`jsonl = Path('$TRANSCRIPT_PATH')`) — both inside a double-quoted shell string spanning lines 39–47
- **Full error suppression**: Line 47 ends with `" 2>/dev/null || true` — both stderr suppression and exit-code swallowing are active; failures are completely invisible
- **`append_session_log_entry` signature** (`scripts/little_loops/session_log.py:85-89`):
  ```python
  def append_session_log_entry(
      issue_path: Path, command: str, session_jsonl: Path | None = None
  ) -> bool:
  ```
  `DEST_PATH` → `issue_path`, `TRANSCRIPT_PATH` → `session_jsonl`; no other shell variables are interpolated in this block

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
- **Confirmed (research)**: `issue-completion-log.sh` is the **only** hook script with shell-variable-into-Python interpolation. All other hook scripts use `jq` throughout or a safe single-quoted heredoc.
- `hooks/scripts/session-start.sh:25-97` — uses `python3 << 'PYTHON'` (single-quoted heredoc suppresses all shell interpolation); reference for the safest alternative approach
- `skills/update-docs/SKILL.md:95-105` — uses `python3 -c "..." "$SINCE_DATE"` with `sys.argv[1]` inside Python; a second safe-passing alternative

### Tests
- `scripts/tests/test_hooks_integration.py` — no existing coverage for `issue-completion-log.sh`; new test class needed
- `scripts/tests/test_session_log.py` — `TestAppendSessionLogEntry` (line 56) tests the Python function directly; shell-layer path-with-quotes is not covered

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Test class to model**: `TestUserPromptCheck` at `test_hooks_integration.py:435-502` — `@pytest.mark.parametrize` with special-character inputs including `"Prompt with \"quotes\" and 'apostrophes'"`, uses `subprocess.run([str(hook_script)], input=json.dumps(input_data), capture_output=True, text=True, timeout=5)` invocation pattern
- **Env-var injection in tests**: `TestContextMonitor` at `test_hooks_integration.py:229-266` — `env = os.environ.copy(); env["VAR"] = "value"; subprocess.run(..., env=env)` pattern; use this to verify the fixed script correctly reads `DEST_PATH`/`TRANSCRIPT_PATH` from environment
- **Suggested new test parametrize values**: `"path/with'quote.md"`, `"it's-fixed.md"`, `"O'Brien/issue.md"` as `$DEST_PATH`; combine with a valid `$TRANSCRIPT_PATH` in a temp dir to confirm no Python `SyntaxError`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Refactor `python3 -c` call in `issue-completion-log.sh` to use env var injection
2. Verify Python code uses `os.environ['DEST_PATH']` and `os.environ['TRANSCRIPT_PATH']`
3. Test with a path containing a single quote to confirm it no longer breaks

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete implementation:**

1. **Edit `hooks/scripts/issue-completion-log.sh:39-47`** — replace the `python3 -c "..."` block with:
   ```bash
   DEST_PATH="$DEST_PATH" TRANSCRIPT_PATH="$TRANSCRIPT_PATH" python3 -c "
   import os
   from pathlib import Path
   from little_loops.session_log import append_session_log_entry
   dest = Path(os.environ['DEST_PATH'])
   jsonl = Path(os.environ['TRANSCRIPT_PATH'])
   if dest.exists():
       append_session_log_entry(dest, 'hook:posttooluse-git-mv', session_jsonl=jsonl)
   " 2>/dev/null || true
   ```
2. **Add `TestIssueCompletionLog` class to `scripts/tests/test_hooks_integration.py`** (after `TestUserPromptCheck` ends at line 502) using:
   - `@pytest.mark.parametrize` with single-quote path values (`"path/with'quote.md"`, etc.)
   - `env = os.environ.copy(); env["DEST_PATH"] = ...; env["TRANSCRIPT_PATH"] = ...; subprocess.run([str(hook_script)], input=json.dumps(input_data), env=env, ...)`
   - Assert `result.returncode == 0` and that the issue file receives a session log entry
3. **Run**: `python -m pytest scripts/tests/test_hooks_integration.py -v -k IssueCompletionLog`

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
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b17f620-f2da-44e2-8f69-81831236e135.jsonl`
- `/ll:refine-issue` - 2026-03-23T23:00:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8abe37ac-d35f-4eda-a4e9-ca0e44b84ecc.jsonl`
- `/ll:format-issue` - 2026-03-23T22:43:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9850963-0ae2-487e-9014-ade593329bce.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P3
