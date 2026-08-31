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

## Impact

- **Priority**: P2 — mirrors BUG-2614's severity class: a config'd gate
  (test/lint verification, epic-branch merge) silently no-ops for an entire
  run and the run still reports `success`, with the miscue currently visible
  only via a stray empty-string field a human has to notice.
