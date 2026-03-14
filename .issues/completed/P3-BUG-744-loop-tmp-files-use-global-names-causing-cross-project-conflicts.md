---
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 86
---

# BUG-744: Loop `/tmp` scratch files use global names causing cross-project conflicts

## Summary

When `little-loops` is installed at the user level and the same loop is run concurrently in two
different projects, several loops use hard-coded `/tmp` filenames with no project identifier. This
causes the two runs to stomp on each other's scratch files — reading stale data from the wrong
project or having their counters/reports corrupted.

## Current Behavior

Running `ll-loop issue-refinement` in Project A and Project B simultaneously:

- Both `init` states race to `rm -f /tmp/issue-refinement-commit-count` — one run deletes the
  other's counter mid-flight.
- Both `check_commit` states read/write the same `/tmp/issue-refinement-commit-count`, producing
  incorrect commit cadence in both projects.

Affected loops and their shared `/tmp` paths:

| Loop | Shared `/tmp` file |
|------|--------------------|
| `issue-refinement` | `/tmp/issue-refinement-commit-count` |
| `fix-quality-and-tests` | `/tmp/ll-test-results.txt` |
| `dead-code-cleanup` | `/tmp/ll-dead-code-report.txt`, `/tmp/ll-dead-code-excluded.txt`, `/tmp/ll-dead-code-tests.txt` |
| `pr-review-cycle` | `/tmp/ll-pr-test-results.txt` |

## Expected Behavior

Each project's loop run should use isolated scratch files. Running the same loop in two projects
simultaneously should not interfere.

## Motivation

User-level installation is the normal deployment model. Power users routinely work across multiple
projects. Unexpected data corruption or wrong commits are a silent failure — no error, just wrong
behavior.

## Root Cause

- **Files**: `loops/issue-refinement.yaml`, `loops/fix-quality-and-tests.yaml`,
  `loops/dead-code-cleanup.yaml`, `loops/pr-review-cycle.yaml`
- **Anchor**: Shell `action` blocks using hardcoded `/tmp/<name>` paths
- **Cause**: The `/tmp` filenames were designed for single-project use and contain no project
  identifier. The scope-based `LockManager` in `fsm/concurrency.py` prevents concurrent runs
  *within* a project but has no cross-project awareness (each project's `.loops/.running/` is
  independent).

### Codebase Research Findings

_Added by `/ll:refine-issue` — exact line references:_

| Loop file | Line | Kind | `/tmp` path |
|-----------|------|------|-------------|
| `loops/issue-refinement.yaml` | 9 | shell `rm -f` | `/tmp/issue-refinement-commit-count` |
| `loops/issue-refinement.yaml` | 93 | shell `FILE=` | `/tmp/issue-refinement-commit-count` |
| `loops/fix-quality-and-tests.yaml` | 75 | shell `tee` | `/tmp/ll-test-results.txt` |
| `loops/fix-quality-and-tests.yaml` | 85 | **prompt text** | `/tmp/ll-test-results.txt` |
| `loops/dead-code-cleanup.yaml` | 15 | **prompt text** | `/tmp/ll-dead-code-report.txt` |
| `loops/dead-code-cleanup.yaml` | 20, 22 | **prompt text** | `/tmp/ll-dead-code-excluded.txt` |
| `loops/dead-code-cleanup.yaml` | 27 | shell `REPORT=` | `/tmp/ll-dead-code-report.txt` |
| `loops/dead-code-cleanup.yaml` | 72 | shell `tee` | `/tmp/ll-dead-code-tests.txt` |
| `loops/dead-code-cleanup.yaml` | 82, 89 | **prompt text** | `/tmp/ll-dead-code-tests.txt`, `/tmp/ll-dead-code-excluded.txt` |
| `loops/pr-review-cycle.yaml` | 59 | shell `tee` | `/tmp/ll-pr-test-results.txt` |
| `loops/pr-review-cycle.yaml` | 70 | **prompt text** | `/tmp/ll-pr-test-results.txt` |

**Critical complication — prompt action blocks**: Six of the eleven occurrences are inside
`action_type: prompt` blocks (instructions passed to Claude as text). Shell variable substitution
(`_PROJ=$(...)`) does **not** expand in prompt text, so the hash-suffix approach in the Proposed
Solution only works for `action_type: shell` states.

**Recommended alternative — relative `.loops/tmp/` directory**: Replacing `/tmp/<name>` with
`.loops/tmp/<name>` (a path relative to CWD) is project-scoped by nature, requires no hashing or
variable expansion, and works identically in both shell and prompt action text. The `.loops/`
directory is already the loop infrastructure root (`.loops/.running/` exists there). This is
simpler and cross-platform.

**Cross-platform portability note**: The Proposed Solution uses `md5sum` which is Linux-only
(macOS ships `md5 -q`). If a shell-hash approach is chosen, use:
```bash
_PROJ=$(python3 -c "import hashlib,os; print(hashlib.sha256(os.getcwd().encode()).hexdigest()[:8])")
```

**Init-state availability per loop**:
- `issue-refinement.yaml` — has `init` state (line 8, `action_type: shell`); `_PROJ` can be computed there.
- `fix-quality-and-tests.yaml` — initial state `check-quality` is `action_type: prompt`; needs a new `init` shell state added before it.
- `dead-code-cleanup.yaml` — initial state `scan` is `action_type: prompt`; needs a new `init` shell state added before it.
- `pr-review-cycle.yaml` — initial state `check_branch` is `action_type: shell` (lines 9–15); `_PROJ` can be appended there if using the hash approach.

## Steps to Reproduce

1. Install `little-loops` at the user level (`pip install -e scripts/`)
2. Open two terminals, each `cd`-ed into a different project that uses little-loops
3. Run `ll-loop issue-refinement` in both terminals simultaneously
4. Observe: commit counter resets / wrong commit timing in one or both runs

## Proposed Solution

Embed a project-specific token in the `/tmp` filenames. The simplest approach is to hash the CWD:

```bash
_PROJ=$(echo "$PWD" | md5sum | cut -c1-8)
FILE="/tmp/issue-refinement-commit-count-$_PROJ"
```

Alternative: use a project subdirectory under `/tmp`:

```bash
_PROJ=$(echo "$PWD" | md5sum | cut -c1-8)
mkdir -p "/tmp/ll-$_PROJ"
FILE="/tmp/ll-$_PROJ/issue-refinement-commit-count"
```

The second form is cleaner because all per-project scratch files live in one directory, making
cleanup trivial. Each loop needs updating independently.

## Integration Map

### Files to Modify
- `loops/issue-refinement.yaml` — `init` and `check_commit` states
- `loops/fix-quality-and-tests.yaml` — `run_tests` state
- `loops/dead-code-cleanup.yaml` — `scan`, `run_tests`, and `exclude` states
- `loops/pr-review-cycle.yaml` — `run_tests` state

### Dependent Files (Callers/Importers)
- None — loop YAML files are standalone; no Python imports needed

### Similar Patterns
- `fsm/concurrency.py` — already uses per-project locking via `Path.cwd()`-relative `.loops/.running/`
- `scripts/little_loops/fsm/evaluators.py:419–423` — **additional unscoped /tmp paths** not listed above: `/tmp/ll-diff-stall-{cache_key}.txt` and `.count` use a scope-hash but the hash is derived from the *scope argument* (file paths), not the project directory. Two projects scanning the same files would still collide. Consider fixing in the same pass.

### Out-of-Scope /tmp Paths (noted for awareness)
- `hooks/scripts/session-cleanup.sh:17` — `/tmp/ll-scratch` (flat global, cleaned on session stop)
- `commands/manage-release.md:337` — `/tmp/ll-release-notes.md` (single-session command, lower risk)

### Tests
- `scripts/tests/test_builtin_loops.py` — add a test that loads two copies of the same loop with
  different CWDs and verifies their scratch paths don't collide

### Codebase Research Findings

_Added by `/ll:refine-issue` — test structure context:_

`test_builtin_loops.py` uses `monkeypatch.chdir(tmp_path)` to set per-test CWD (lines 72, 91, 109,
128, etc.). A new `TestBuiltinLoopScratchIsolation` class following this pattern could:

```python
def test_scratch_paths_differ_across_projects(self, tmp_path, monkeypatch):
    """Shell action scratch paths must be project-scoped."""
    proj_a = tmp_path / "proj_a"
    proj_b = tmp_path / "proj_b"
    proj_a.mkdir(); proj_b.mkdir()
    # Load YAML and extract shell action text for issue-refinement
    loop_file = BUILTIN_LOOPS_DIR / "issue-refinement.yaml"
    data = yaml.safe_load(loop_file.read_text())
    init_action = data["states"]["init"]["action"]
    check_action = data["states"]["check_commit"]["action"]
    # Verify path includes project discriminator (not bare /tmp/<name>)
    assert "/tmp/issue-refinement-commit-count" not in init_action
    assert "/tmp/issue-refinement-commit-count" not in check_action
```

This static check pattern is the most practical approach since the tests don't execute shell
actions at runtime.

**Alternative test pattern from `test_fsm_evaluators.py:948–961`** (redirect `/tmp` writes at the
Python level):

```python
@pytest.fixture(autouse=True)
def redirect_tmp_paths(self, tmp_path, monkeypatch):
    import little_loops.fsm.evaluators as ev_module
    original_path = Path
    def patched_path(p: str) -> Path:
        if str(p).startswith("/tmp/ll-diff-stall-"):
            return tmp_path / original_path(p).name
        return original_path(p)
    monkeypatch.setattr(ev_module, "Path", patched_path)
```

This autouse fixture pattern (already used in `TestDiffStallEvaluator`) is the right model for
testing Python-layer `/tmp` access (e.g. `evaluators.py`). For YAML-level fixes, the static YAML
parse approach above is more practical.

### Documentation
- None required

## Implementation Steps

**Recommended strategy**: Replace `/tmp/<name>` with `.loops/tmp/<name>` (relative, no hashing needed).

1. **Decide on strategy** — relative `.loops/tmp/` (recommended, works in prompt + shell, no
   cross-platform hash issue) OR per-project `/tmp/ll-<hash>/` with Python-based hash (covers
   shell-only states, needs new `init` states for `fix-quality-and-tests` and `dead-code-cleanup`).

2. **`loops/issue-refinement.yaml`** — two changes:
   - Line 9 (`init` shell state): `rm -f /tmp/issue-refinement-commit-count` → `rm -f .loops/tmp/issue-refinement-commit-count`
   - Line 93 (`check_commit` shell state): `FILE="/tmp/issue-refinement-commit-count"` → `FILE=".loops/tmp/issue-refinement-commit-count"`. Also add `mkdir -p .loops/tmp` before the `FILE=` line.

3. **`loops/fix-quality-and-tests.yaml`** — two changes:
   - Line 75 (shell `tee`): `tee /tmp/ll-test-results.txt` → `tee .loops/tmp/ll-test-results.txt`
   - Line 85 (prompt text): `Read /tmp/ll-test-results.txt` → `Read .loops/tmp/ll-test-results.txt`
   - Add `mkdir -p .loops/tmp` before `tee` on line 75.

4. **`loops/dead-code-cleanup.yaml`** — six changes across lines 15, 20, 22, 27, 72, 82, 89:
   - Replace all `/tmp/ll-dead-code-*.txt` with `.loops/tmp/ll-dead-code-*.txt` in both shell
     and prompt action text. Add `mkdir -p .loops/tmp` before the shell `tee` on line 72.

5. **`loops/pr-review-cycle.yaml`** — two changes:
   - Line 59 (shell `tee`): `tee /tmp/ll-pr-test-results.txt` → `tee .loops/tmp/ll-pr-test-results.txt`
   - Line 70 (prompt text): `Read /tmp/ll-pr-test-results.txt` → `Read .loops/tmp/ll-pr-test-results.txt`
   - Add `mkdir -p .loops/tmp` before `tee` on line 59.

6. **Validate all four loops**: `ll-loop validate issue-refinement`, `ll-loop validate fix-quality-and-tests`, `ll-loop validate dead-code-cleanup`, `ll-loop validate pr-review-cycle`

7. **Add test** to `scripts/tests/test_builtin_loops.py`: new `TestBuiltinLoopScratchIsolation`
   class that parses YAML action text and asserts no bare `/tmp/ll-*` or `/tmp/issue-refinement-*`
   paths appear in the four affected loops (see Tests section above for pattern).

8. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py -v`

## Impact

- **Priority**: P3 — Affects multi-project concurrent use; silent data corruption, no crash
- **Effort**: Small — 4 YAML files, ~2–3 line change each
- **Risk**: Low — only affects the scratch-file variable; FSM logic unchanged
- **Breaking Change**: No

## Labels

`bug`, `loops`, `concurrency`, `captured`

## Status

**Resolved** | Created: 2026-03-14 | Resolved: 2026-03-14 | Priority: P3

## Resolution

Replaced all bare `/tmp/<name>` scratch paths with `.loops/tmp/<name>` across four built-in loop
YAML files. The `.loops/tmp/` directory is relative to CWD, making it project-scoped by nature —
no hashing or init-state changes required. `mkdir -p .loops/tmp` was added before each shell `tee`
write. All six prompt-action references were also updated (variable substitution not needed since
the path is a literal string).

Files changed:
- `loops/issue-refinement.yaml` — `init` and `check_commit` states
- `loops/fix-quality-and-tests.yaml` — `check-tests` shell action and `fix-tests` prompt
- `loops/dead-code-cleanup.yaml` — `scan`, `count_findings`, `verify_tests`, and `revert_and_scan` states
- `loops/pr-review-cycle.yaml` — `run_tests` shell action and `fix_tests` prompt
- `scripts/tests/test_builtin_loops.py` — added `TestBuiltinLoopScratchIsolation` class

---

## Session Log
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0158546f-c101-4ad0-a270-3ce053241b43.jsonl`
- `/ll:format-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/26ed7e7e-3f7a-4274-bdda-1d02ddfc8569.jsonl`
- `/ll:refine-issue` - 2026-03-14T21:20:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01e49223-c5e4-4b64-a87e-955fbdd3f1e3.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/78f65597-4874-4e96-867a-61614a943e9d.jsonl`
- `/ll:ready-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2d8f120-f44d-4581-8c5e-1ed6cc44c121.jsonl`
- `/ll:manage-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
