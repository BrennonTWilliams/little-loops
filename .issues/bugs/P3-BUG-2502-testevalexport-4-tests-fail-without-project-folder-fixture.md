---
status: done
completed_at: 2026-07-07T04:21:28Z
---
# BUG-2502: 4 Tests in `TestEvalExport` Fail Without Project-Folder Fixture

## Summary

All 4 non-`--help` tests in `scripts/tests/test_ll_logs.py::TestEvalExport`
(`test_no_flags_returns_0`, `test_skill_flag_parses`, `test_all_flags_parse`,
`test_eval_export_json_short_flag`) failed under `python -m pytest scripts/tests/`
with the same error:

```
>       assert result == 0
E       assert 1 == 0
----------------------------- Captured stderr call -----------------------------
No session project folder found for: /Users/brennon/AIProjects/brenentech/little-loops
```

The two passing tests in the class (`test_help_shows_all_flags`,
`test_no_regression_extract`) only exercise `--help` and exit at argparse
before hitting the bug, masking the regression. The 4 broken tests have
failed since the class was added in commit `020d8687` (2026-06-06,
FEAT-1971). The most recent touching commit (`27560827`, added
`test_eval_export_json_short_flag`) followed the same broken pattern.

## Current Behavior

The 4 tests invoke `main_logs()` with `eval-export` flags but no `--project`.
`_cmd_eval_export` (`scripts/little_loops/cli/logs.py:1635`) calls
`get_project_folder(Path.cwd())` at line 1647, and when the lookup fails
returns 1 at line 1650:

```python
cwd_path = Path(args.project) if args.project else Path.cwd()
project_folder = get_project_folder(cwd_path)
if project_folder is None:
    print(f"No session project folder found for: {cwd_path}", file=sys.stderr)
    return 1
```

`get_project_folder` (`scripts/little_loops/user_messages.py:356,395`) encodes
the cwd and probes `Path.home() / ".claude" / "projects" / <encoded>`. None
of the 4 tests mocked `Path.home` or `Path.cwd`, so the probe depended on
host filesystem state pytest cannot guarantee.

## Expected Behavior

The 4 tests should set up a fake `~/.claude/projects/<encoded-cwd>` folder and
patch `pathlib.Path.home` + `little_loops.cli.logs.Path.cwd` — the same
fixture pattern already used by `TestExtract.test_extract_project_creates_output_file`
(`scripts/tests/test_ll_logs.py:1483-1514`).

## Root Cause

The tests were written with implicit dependence on the host filesystem
(`Path.home()` returning a path that contains a project folder matching the
encoded cwd). The `_cmd_eval_export` strict contract — "missing project
folder is an error" — was correct, but the test scaffolding didn't honor it.

## Affected Files

- `scripts/tests/test_ll_logs.py:3274-3341` — `TestEvalExport` class (rewritten
  tests at lines 3293, 3299, 3305, 3327).
- `scripts/little_loops/cli/logs.py:1635-1650` — `_cmd_eval_export` (unchanged;
  contract preserved).
- `scripts/little_loops/user_messages.py:356,395` — `get_project_folder` /
  `_get_claude_project_folder` (unchanged).

## Reproduction Steps

1. `cd /Users/brennon/AIProjects/brenentech/little-loops`
2. `python -m pytest scripts/tests/test_ll_logs.py::TestEvalExport -v`
3. Observe 4 of 6 tests fail with the error above.

## Proposed Fix (chosen)

Rewrite the 4 failing tests to use the established fixture pattern. Added a
`_setup_project_folder()` static helper on `TestEvalExport` that creates
`tmpdir/home/.claude/projects/<encoded-cwd>`, and each test wraps
`patch("sys.argv", ...)`, `patch("pathlib.Path.home", return_value=home)`,
and `patch("little_loops.cli.logs.Path.cwd", return_value=fake_cwd)` around
the `main_logs()` call. `_cmd_eval_export` is unchanged; its strict contract
is preserved (an empty project folder still produces empty output and exits 0).

## Impact

- **Severity**: Low (P3) — test-only failure, no production user impact.
- **Effort**: Trivial (4 tests, ~10 lines each).
- **Risk**: Low — pure test refactor, no production code touched.
- **Breaking Change**: No.

## Labels

`bug`, `tests`, `ll-logs`, `eval-export`

## Session Log
- `hook:posttooluse-status-done` - 2026-07-07T04:21:59 - `adafbe0f-cbce-4ce1-ab52-d6fdff9e201b.jsonl`

---

## Status

**Done** | Created: 2026-07-07 | Priority: P3

## Related Issues

- [FEAT-1970](../features/P3-FEAT-1970-eval-export-reconstructs-harness-fixtures.md) — `eval-export` subcommand scaffold
- [FEAT-1971](../features/P2-FEAT-1971-reconstruct-ll-harness-fixtures-from-session-logs.md) — `eval-export` reconstruction logic

---

## Resolution

- **Action**: fix
- **Completed**: 2026-07-07
- **Status**: Completed

### Changes Made

- `scripts/tests/test_ll_logs.py`: Added `_setup_project_folder()` static helper on `TestEvalExport` (creates `tmpdir/home/.claude/projects/<encoded-cwd>`).
- `scripts/tests/test_ll_logs.py`: Rewrote `test_no_flags_returns_0`, `test_skill_flag_parses`, `test_all_flags_parse`, `test_eval_export_json_short_flag` to patch `pathlib.Path.home` and `little_loops.cli.logs.Path.cwd` around `main_logs()`.

### Solution Approach

Mirrored the working fixture pattern from `TestExtract.test_extract_project_creates_output_file`
(`scripts/tests/test_ll_logs.py:1483-1514`). No change to `_cmd_eval_export` —
its strict contract is preserved (a missing project folder is still an error
in production). The tests now set up a minimal valid project folder, so the
existing code path runs cleanly and returns 0.

### Verification Results

- `python -m pytest scripts/tests/test_ll_logs.py::TestEvalExport -v` → **6 passed**
- `python -m pytest scripts/tests/test_ll_logs.py` → **188 passed**
- Full suite (`python -m pytest scripts/tests/`) has 2 pre-existing
  `test_wiring_*` failures (doc-string assertions in `README.md` /
  `skills/configure/areas.md`) unrelated to this fix — confirmed by stashing
  all unstaged changes and re-running.