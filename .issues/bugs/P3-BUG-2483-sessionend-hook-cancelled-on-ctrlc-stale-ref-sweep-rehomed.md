---
captured_at: '2026-07-05T16:25:46Z'
completed_at: '2026-07-05T16:25:46Z'
discovered_date: 2026-07-05
discovered_by: capture-issue
status: done
priority: P3
type: BUG
relates_to:
- FEAT-1680
- BUG-2422
- BUG-2420
labels:
- hooks
- session-lifecycle
- ux
confidence_score: 95
outcome_confidence: 92
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 20
---

# BUG-2483: SessionEnd hook cancelled on every exit — stale-ref sweep re-homed to SessionStart

## Summary

Every time the user exited a Claude Code session in this repo (Ctrl+C at the
idle prompt, Ctrl+D, or `/exit`), the terminal printed:

```
SessionEnd hook [bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh] failed: Hook cancelled
```

Investigation traced this to a confirmed, unfixed upstream Claude Code CLI bug
combined with this repo's issue-tracker having grown large enough to trip it.
Fixed by re-homing the FEAT-1680 stale-cross-issue-ref sweep from the
`SessionEnd` event to `SessionStart`, where the race does not exist.

## Current Behavior

`hooks/hooks.json` registered `hooks/adapters/claude-code/session-end.sh`
(pipes to `python -m little_loops.hooks session_end` →
`sweep_stale_refs.handle`, added by FEAT-1680 and re-homed onto `SessionEnd`
by BUG-2422) under the `SessionEnd` event. That handler does a full-tree scan
of `.issues/` — two passes of `find_issues()` plus a per-file regex scan —
which took ~1.6s wall-clock in this repo (2,385 issue files at time of
investigation, versus the ~400-file / <2s target FEAT-1680 was written
against).

Claude Code enforces a hard ceiling of roughly 1.5s on `SessionEnd` hooks
before forcibly killing them on any exit path (Ctrl+C, Ctrl+D, `/exit`) —
**independent of the hook's configured `timeout` value** (`15` here). This is
a confirmed, currently-unresolved upstream bug:
[anthropics/claude-code#32712](https://github.com/anthropics/claude-code/issues/32712)
("SessionEnd hook cancelled with 'Request interrupted by user' on Ctrl+C",
closed not-planned) and
[#41577](https://github.com/anthropics/claude-code/issues/41577) ("SessionEnd
hooks are killed before completion when running async work", closed as a
duplicate of #24206 with no fix landed). Comments on #32712 confirm the same
symptom fires across `/exit`, Ctrl+D, and headless (`claude -p`) exits, not
just Ctrl+C — it is not an interrupt-specific quirk, it is a blanket deadline
on the event.

Because the sweep's ~1.6s runtime sat right at that ceiling, it was being
killed on very close to every exit, which also means FEAT-1680's stale-ref
detection was likely not completing reliably in practice, not just printing a
noisy error.

## Expected Behavior

Session exit should not print a hook-failure error on ordinary use, and the
stale-cross-issue-ref sweep should reliably run to completion.

## Root Cause

- **Immediate cause**: `hooks/hooks.json` bound `session-end.sh` to
  `SessionEnd`, an event Claude Code kills after ~1.5s regardless of
  configured `timeout`, and the handler's real runtime (~1.6s, scaling with
  `.issues/` file count) exceeds that ceiling.
- **Contributing factor**: the sweep does two whole-tree `find_issues()`
  passes (`sweep_stale_refs.py:159` for done IDs, `:166` for open issues) plus
  a per-file read + regex scan — cost scales with total issue count, which has
  grown ~6x since FEAT-1680's <2s/~400-file target.
- **Not a little-loops logic bug**: the handler itself is correct and
  idempotent (`try/except Exception: return LLHookResult(exit_code=0)`); the
  defect is entirely in *when* it fires relative to an upstream deadline
  little-loops cannot configure around (no documented way to raise the
  ~1.5s `SessionEnd` ceiling, matcher-filter it, or suppress the "Hook
  cancelled" message).

## Root Cause Verification Note

An initial research pass (via a `claude-code-guide` subagent) returned the
correct GitHub issue numbers but paired them with an unfamiliar, seemingly
fabricated source ("MorphLLM documentation"). Verified independently via
`gh issue view` against `anthropics/claude-code` before relying on the
finding — issues #32712 and #41577 and their close reasons/comments checked
out; the other citation was dropped rather than repeated.

## Steps to Reproduce

1. In this repo (or any repo with a large `.issues/` tree), run
   `claude --dangerously-skip-permissions` from the project root.
2. Let the session sit idle at the prompt for any length of time.
3. Press Ctrl+C two or three times to quit (or exit via Ctrl+D / `/exit`).
4. Observe the terminal print
   `SessionEnd hook [bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh] failed: Hook cancelled`
   on very close to every exit.
5. Confirm independently: `time (echo '{}' | bash hooks/adapters/claude-code/session-end.sh)`
   standalone takes ~1.6–1.7s in this repo — over the ~1.5s ceiling Claude Code
   enforces on `SessionEnd` hooks regardless of configured `timeout`.

## Proposed Solution / Resolution

Re-homed the sweep from `SessionEnd` to `SessionStart`. It now runs once at
the start of each session — catching drift left over from the *previous*
session's edits — instead of racing session teardown. `SessionStart` has no
forced-kill deadline, so the ~1.6s scan completes normally. The adapter file
(`session-end.sh`) and dispatch intent name (`session_end`) are unchanged;
only the `hooks.json` event binding moved. `scratch-cleanup.sh` (the other
`SessionEnd` hook, ~0.07s runtime) was left on `SessionEnd` — it is fast
enough not to be implicated and has no reason to move.

**Changes:**
- `hooks/hooks.json` — moved the `session-end.sh` group from the `SessionEnd`
  array to a second group in the `SessionStart` array (alongside
  `session-start.sh`). `SessionEnd` now only binds `scratch-cleanup.sh`.
- `scripts/tests/test_claude_code_adapter.py` — replaced
  `test_hooks_json_registers_sweep_under_session_end` /
  `test_hooks_json_stop_no_longer_references_sweep` (BUG-2422's assertions,
  now stale) with `test_hooks_json_registers_sweep_under_session_start` /
  `test_hooks_json_session_end_no_longer_references_sweep`.
- `scripts/little_loops/hooks/sweep_stale_refs.py` — updated the module
  docstring to describe the `SessionStart` firing point and the rationale
  (previously described the now-superseded `SessionEnd` binding).
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — moved the "Sweep stale cross-issue
  references" write-up from the `## SessionEnd` section into `## SessionStart`
  (with the upstream-bug rationale); updated the lifecycle table and the
  "session from hook's perspective" walkthrough; repurposed the now-sparse
  `## SessionEnd` section to describe `scratch-cleanup.sh` (previously
  undocumented in this guide) with a callout about the ~1.5s ceiling; updated
  the `hooks.stale_ref_fix` config-table event column.
- `docs/reference/HOST_COMPATIBILITY.md` — updated the `session_end` parity
  row to note the `SessionStart`-event binding, with a new footnote citing the
  upstream issues.

No change to `sweep_stale_refs.py`'s actual scan/report logic, the
`session_end` dispatch intent (host-agnostic), or any Codex/OpenCode adapter.
Released `CHANGELOG.md` entries describing the sweep as a `SessionEnd` hook
(FEAT-1680, BUG-2422) were left as-is per repo convention (accurate history
as of their release; not retroactively edited).

**Verification:** Full suite `python -m pytest scripts/tests/` — 13,721
passed, 27 skipped (no failures). Confirmed `hooks/hooks.json` is valid JSON
post-edit and manually timed both hooks standalone
(`session-end.sh` ~1.6–1.7s including Python/import overhead;
`scratch-cleanup.sh` ~0.07s) to confirm the ceiling theory before committing
to the fix. Ran `ll-check-links` against the two edited docs — no new broken
links introduced (all pre-existing failures are unrelated npm/`thoughts/`
files).

## Impact

- **Priority**: P3 — cosmetic/noisy on every exit and likely degraded the
  reliability of an advisory-only feature (FEAT-1680), but never blocked
  session termination or corrupted data (the handler always exits 0).
- **Effort**: Small — one `hooks.json` block moved, two tests swapped, four
  doc/docstring updates; no handler-logic change.
- **Risk**: Low — the handler and its dispatch intent are unchanged; only the
  triggering event moved to one with no exit-teardown race. Full test suite
  green.
- **Breaking Change**: No.

## Out of Scope

- Fixing the upstream Claude Code `SessionEnd`-hard-deadline bug itself (not
  little-loops' code to fix; tracked upstream at
  anthropics/claude-code#32712 / #41577).
- Reducing the sweep's O(issue-count) scan cost (the double `find_issues()`
  pass, flagged separately by BUG-2422) — the fix here addresses *when* it
  runs, not its per-run cost. Worth a follow-up if `.issues/` keeps growing
  and `SessionStart` latency becomes noticeable.
- Codex/OpenCode adapters — Codex has no separate `SessionEnd` event and
  intentionally maps `session_end` onto its `Stop` event (ENH-2105); untouched
  here.

## Related Issues

- **FEAT-1680** — introduced the sweep, originally (incorrectly) bound to
  `Stop`.
- **BUG-2422** — first re-home, from `Stop` to `SessionEnd`, fixing the
  per-turn-firing defect. This issue is the second re-home, from `SessionEnd`
  to `SessionStart`, fixing the exit-teardown-race defect that BUG-2422's fix
  inadvertently exposed (it made the sweep fire once per session instead of
  once per turn, but that one firing now consistently lands inside Claude
  Code's `SessionEnd` kill window).
- **BUG-2420** — established the `SessionEnd` event's initial registration in
  this repo (for `scratch-cleanup.sh`), which remains on `SessionEnd`
  unaffected by this change.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-05T16:27:51 - `5d8d18b9-9ed1-4a2c-8e4b-d180c39f878e.jsonl`

---

## Status

**Current Status**: done
