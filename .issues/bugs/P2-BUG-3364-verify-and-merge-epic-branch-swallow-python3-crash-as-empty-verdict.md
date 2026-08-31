---
id: BUG-3364
type: BUG
priority: P2
status: open
captured_at: '2026-08-30T23:30:00Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- ENH-2601
- ENH-2631
- BUG-2614
decision_needed: false
---

# BUG-3364: `verify` and `merge_epic_branch` swallow a python3 crash as an empty verdict, not `failed`/`not_run`

## Summary

In `scripts/little_loops/loops/auto-refine-and-implement.yaml`, the `verify`
state (line 392) captures its Python heredoc's stdout directly into
`VERIFY_VERDICT` (`VERIFY_VERDICT=$(... python3 << 'PYEOF' ... PYEOF)`, line
527) and the `merge_epic_branch` state redirects its heredoc's stdout
straight into `epic-merge-verdict.txt` (line 570) — neither checks the
python3 subprocess's own exit code. When that subprocess crashes with an
uncaught exception (traceback to stderr, empty stdout), both states still
`echo`/redirect the empty string to their verdict file and complete with
`exit_code: 0`. `finalize`'s fallback (`cat verify-verdict.txt 2>/dev/null ||
echo "not_run"`, lines 966/987) only triggers on file *absence* — the crash
leaves the file present but empty, so the fallback never fires and
`summary.json` ends up with `verify_verdict: ""` / `epic_merge_verdict: ""`,
neither of which matches any documented enum value
(`passed/failed/collection_error/config_error/skipped/not_run`).

## Current Behavior

`verify` (line 392) captures its python3 heredoc's stdout directly into
`VERIFY_VERDICT` via command substitution, and `merge_epic_branch` (line 570)
redirects its heredoc's stdout straight into `epic-merge-verdict.txt` — in
both cases only the heredoc's *stdout* is used as the verdict; neither state
checks the python3 subprocess's own exit code. A crash mid-heredoc (e.g.
`ModuleNotFoundError`) prints a traceback to stderr, leaves stdout empty, and
both states still write the empty string to their verdict file with the
outer shell action reporting `exit_code: 0`. `finalize`'s fallback (lines
966/987: `cat verify-verdict.txt 2>/dev/null || echo "not_run"`) only
substitutes `"not_run"` when the file is *absent* — a present-but-empty file
short-circuits `cat`'s success and the fallback never fires, so
`summary.json` ends up with `verify_verdict: ""` / `epic_merge_verdict: ""`.

## Steps to Reproduce

1. Run `auto-refine-and-implement.yaml` against an `EPIC-*` scope so the
   `verify` and `merge_epic_branch` states take the epic-branch code path
   (the one that imports `little_loops.worktree_utils` / `little_loops.config`
   inside the heredoc).
2. Force the heredoc's python3 subprocess to crash instead of running
   normally — e.g. invoke the loop with a `PYTHONPATH` that shadows/hides the
   `little_loops` package for just that subprocess (matching the machine
   conditions [[ENH-3365]] documents: multiple Python installs on `PATH`,
   only one with `little_loops` importable).
3. Let the run reach `finalize` and inspect `summary.json`.
4. Observe: `verify_verdict` and `epic_merge_verdict` are both `""` (empty
   string) — not `"passed"`, `"failed"`, `"skipped"`, `"collection_error"`,
   `"config_error"`, or `"not_run"` — while the run's own terminal `verdict`
   still reads `"success"`.

## Evidence

Observed via `/ll:audit-loop-run sprint-refine-and-implement
.loops/runs/sprint-refine-and-implement-20260830T172734/`
(archived at `.loops/.history/2026-08-30T222734-sprint-refine-and-implement/`):

```
{"event": "action_complete", ..., "exit_code": 0, "duration_ms": 36,
 "output_preview": "verify: verdict=",
 "stderr_preview": "Traceback (most recent call last):\n  File \"<stdin>\", line 58, in <module>\nModuleNotFoundError: No module named 'little_loops.worktree_utils'",
 "state": "verify"}

{"event": "action_complete", ..., "exit_code": 0, "duration_ms": 41,
 "output_preview": "merge_epic_branch: verdict=",
 "stderr_preview": "Traceback (most recent call last):\n  File \"<stdin>\", line 24, in <module>\nModuleNotFoundError: No module named 'little_loops.config'",
 "state": "merge_epic_branch"}
```

`summary.json` for the run:
```
{"verdict":"success","closed":3,...,"verify_verdict":"","epic_merge_verdict":"",...}
```

The run's actual test/lint gate (`project.test_cmd`) never executed, and the
epic-to-base merge check never ran — yet the run's terminal state and
`ll-loop`'s own success rendering read as green because `finalize` only
diverts to the failure terminal on `phantom`/`incomplete-abandoned`
(`case "$VERDICT" in phantom|incomplete-abandoned) exit 1 ;; esac`), which
this run's `VERDICT=success` (closed=3, no skips/errors/not-closed) never hits.

## Expected Behavior

A python3 subprocess crash inside `verify` or `merge_epic_branch` should
produce a verdict that the existing classification machinery can act on —
either `"error"` (a new class distinct from `failed`/`config_error`) or, at
minimum, `"not_run"` — never a bare empty string that passes silently through
`finalize`'s formatting and lands unexplained in `summary.json`.

## Proposed Solution

1. In both states, capture the python3 subprocess's own exit code alongside
   its stdout (e.g. `VERIFY_VERDICT=$(python3 <<'PYEOF' ... PYEOF); PY_RC=$?`)
   and treat a non-zero `PY_RC` as an explicit `error` verdict rather than
   trusting stdout.
2. In `finalize`, change the fallback from `cat file 2>/dev/null || echo
   not_run` to also treat an empty-but-present file as `not_run`/`error`
   (e.g. `[ -s file ] && cat file || echo not_run`).
3. Add regression coverage: simulate a python3 heredoc crash (e.g. via a
   `PYTHONPATH` that hides `little_loops`) inside `verify`/`merge_epic_branch`
   and assert `summary.json` reports a non-empty, documented verdict token —
   not `""`.

## Program Design

### Signatures

- `emit(verdict, returncode=None, detail='')` (`auto-refine-and-implement.yaml:439`) — must also receive the heredoc's own subprocess exit code from its caller, not just trust stdout being non-empty.
- `classify(returncode, stderr='')` (`auto-refine-and-implement.yaml:428`) — unchanged; the caller must invoke it (or emit `"error"` directly) when the heredoc itself crashed, instead of only calling it on a clean run.

### Call Path

`verify` -> heredoc's `classify()` / `emit()` -> `VERIFY_VERDICT` -> `verify-verdict.txt` -> `finalize` -> `summary.json`'s `verify_verdict` field. Same shape for `merge_epic_branch` -> `epic-merge-verdict.txt` -> `finalize` -> `summary.json`'s `epic_merge_verdict` field.

## Impact

- **Priority**: P2 — mirrors BUG-2614's severity class: a config'd gate
  (test/lint verification, epic-branch merge) silently no-ops for an entire
  run and the run still reports `success`, with the miscue currently visible
  only via a stray empty-string field a human has to notice.

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
