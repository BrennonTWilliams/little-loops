---
id: ENH-2534
type: ENH
priority: P4
status: done
captured_at: '2026-07-07T21:00:00Z'
completed_at: 2026-07-08 01:04:48+00:00
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
decision_needed: false
labels:
- loops
- hardening
confidence_score: 97
outcome_confidence: 91
score_complexity: 24
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
---

# ENH-2534: rn-implement — check_blocked_by should emit UNRESOLVED/PARSE_ERROR tokens

## Summary

The upfront `check_blocked_by` state in
`scripts/little_loops/loops/rn-implement.yaml` still fails open *silently*
(`sys.exit(0)` with no output) when the issue file cannot be resolved or its
frontmatter cannot be parsed. The post-remediation recheck (~line 797) was
already hardened to print `UNRESOLVED` / `PARSE_ERROR`; mirror that in the
upfront gate.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposal 4). No defect was observed
in that run, but the fail-open path means a renamed/unresolvable issue file
silently proceeds past the blocked_by gate as READY. Benign today because the
readiness gate catches most issues, but a distinct defect class if a parked
issue's only constraint is `blocked_by`.

## Current Behavior

In `check_blocked_by` (~line 410):

```python
if not issue_path:
    sys.exit(0)  # unresolved -> fail-open (let downstream handle)
...
except Exception:
    sys.exit(0)  # parse error -> fail-open
```

No token is printed, so events/logs carry no trace that the gate was skipped
rather than passed.

## Expected Behavior

Fail-open behavior is preserved (processing is never blocked on a gate error),
but the skip is observable: print `UNRESOLVED` / `PARSE_ERROR` before exiting,
matching the recheck state, and optionally append a diagnostic line to a
run_dir sidecar (e.g. `blocked_by_gate_skips.txt`) so audits can distinguish
"no unmet deps" from "gate could not evaluate".

## Proposed Solution

- Add the two `print(...)` calls mirroring the recheck state.
- If routing on the token is desired later, add an `output_contains` route to
  a distinct diagnostic emit; not required for this issue — observability only.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **⚠ Do NOT mirror the recheck's `print()` verbatim to stdout.** The two states
  have opposite stdout data-flow, so a literal copy would flip fail-open →
  fail-closed. In the upfront gate (`check_blocked_by`, `rn-implement.yaml:360`),
  the inner `python3` heredoc's **stdout** is captured by command substitution
  into `$UNMET` (`UNMET=$(python3 << 'PYEOF' ... )`, lines 379/446–447). The bash
  wrapper then treats **non-empty `$UNMET` as BLOCKED** — it writes
  `blocked_by_unmet_<ID>.txt` and echoes `BLOCKED`
  (`if [ -n "$UNMET" ]`, lines 448–451) → `route_blocked_by` matches `BLOCKED`
  → `mark_deferred`. So `print("UNRESOLVED")` to **stdout** would defer the
  issue instead of passing it through. By contrast, the recheck's wrapper
  (line 838) uses `if [ -z "$UNMET" ]` (non-empty = *don't* re-enqueue), so its
  stdout tokens are harmless there.
- **Fix: emit the tokens to stderr**, e.g. `print("UNRESOLVED", file=sys.stderr)`
  and `print("PARSE_ERROR", file=sys.stderr)`. This keeps `$UNMET` empty (→ READY
  → fail-open preserved) while still surfacing the skip. The FSM captures shell
  stderr separately (`fsm/executor.py:1547–1615`) and exposes it to operators via
  `stderr_preview` (`fsm/executor.py:1453–1460`, ENH-2469) — exactly the
  observability the issue asks for, without a routing change.
- **There are four silent fail-open points, not two.** Beyond unresolved
  (`rn-implement.yaml:412`) and parse-error (line 419), the done-set failure has
  two exits (lines 439 and 441) that the recheck labels `DONE_SET_ERROR`
  (lines 827/830). Line 428 is the *normal* no-deps ready path (recheck:
  `NO_BLOCKED_BY`, line 815) — not an error. Emit `DONE_SET_ERROR` too (also to
  stderr) for full parity if scope allows; the issue title only mandates
  `UNRESOLVED`/`PARSE_ERROR`.
- **Optional sidecar** (`blocked_by_gate_skips.txt`): if added, write it under
  `$RUN_DIR` — mirror the existing per-run path `blocked_by_unmet_<ID>.txt`
  (line 449). A bare `.loops/tmp/` path would trip MR-3 (per-run artifact
  isolation) in `ll-loop validate`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `check_blocked_by` state
  (line 360). Replace the bare `sys.exit(0)` at the unresolved (line 412) and
  parse-error (line 419) fail-open points with a preceding
  `print("<TOKEN>", file=sys.stderr)`; optionally the two done-set exits
  (lines 439, 441) with `DONE_SET_ERROR`. Fail-open (`sys.exit(0)`,
  `on_error: check_depth` at line 457) must be preserved unchanged.

### Reference Pattern (mirror, adjusting stream)
- `scripts/little_loops/loops/rn-implement.yaml:796–831` — the post-remediation
  recheck already prints `UNRESOLVED` (797) / `PARSE_ERROR` (805) /
  `NO_BLOCKED_BY` (815) / `DONE_SET_ERROR` (827,830). Copy the token *strings*,
  but route them to `stderr` per the finding above.

### Dependent / Downstream (unchanged, verify no regression)
- `route_blocked_by` (`rn-implement.yaml:459`) evaluates
  `output_contains` on `${captured.blocked_by_status.output}` (the **bash
  wrapper's** stdout: `READY`/`BLOCKED`) — unaffected as long as tokens go to
  stderr and `$UNMET` stays empty on the fail-open paths.
- `mark_deferred` (`rn-implement.yaml:1250`) consumes
  `blocked_by_unmet_<ID>.txt`; must not be written on an unresolved/parse-error
  skip.

### Tests
- `scripts/tests/test_rn_implement.py` — existing gate tests introspect the
  static YAML via `_load_loop()` (e.g.
  `test_check_blocked_by_parses_frontmatter_not_show_json` at line 1039, asserts on
  `action` string contents; `test_check_blocked_by_fails_open_on_error` at line
  1033). Add a sibling test asserting the `check_blocked_by` `action` contains
  `"UNRESOLVED"`, `"PARSE_ERROR"`, and `sys.stderr` (or `>&2`), and that the
  `on_error`/`sys.exit(0)` fail-open shape is retained.
- `scripts/tests/test_fsm_executor.py` — already covers `stderr_preview`
  surfacing (ENH-2469); no change needed, but confirms the stderr route is
  operator-visible.

#### Tests — additional anchors (wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

- **Sibling static pattern**: `scripts/tests/test_rn_implement.py:1402`
  `test_re_enqueue_logs_re_enqueue_marker` is the closest in-file precedent for
  a static stderr-marker assertion (`assert "[RE_ENQUEUE]" in action`); mirror
  this pattern for the new `TestBlockedByGate` sibling test.
- **Runtime stderr pattern**: `scripts/tests/test_loops_recursive_refine.py:480, 517, 531, 547, 563, 578`
  — `TestVisitedSetFilter._bash(...)` + `result.stderr` checks model a runtime
  stderr-emission test (alternative to static-only introspection; pick one,
  not both, for the new sibling test to keep the change scoped).
- **Generic stderr surface** (already covered, no edit): `scripts/tests/test_fsm_executor.py:8668-8716`
  `TestStderrPreview` covers `stderr_preview` (ENH-2469) the new tokens ride on.
- **Adjacent test classes** (do-not-regress, no edits):
  - `scripts/tests/test_builtin_loops.py:8230` `TestRnImplementDiagnosticOutcomes`
  - `scripts/tests/test_builtin_loops.py:9098` `TestRnImplementAuthFastFail`
  - `scripts/tests/test_fsm_validation.py:3028` `test_alternative_capture_branches_no_warning`
    (models the `fifo_pop` + `select_next` dual-`input`-capture shape
    `check_blocked_by` depends on).
- **Hardening guard**: `scripts/tests/test_rn_implement.py:1033`
  `test_check_blocked_by_fails_open_on_error` asserts `on_error == "check_depth"`.
  The planned change must preserve this route exactly — the new stderr tokens
  are observability-only.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/LOOPS_REFERENCE.md:399-435` — describes
  `check_blocked_by` → `route_blocked_by` → `mark_deferred` in the gate
  overview (line 401-402), the fail-open prose (line 404, "if `ll-issues show`
  cannot parse the frontmatter the gate passes"), and the FSM flow diagram
  (line 434). The existing prose remains accurate (fail-open semantics
  preserved); a soft enhancement could note that the gate now emits `UNRESOLVED`
  / `PARSE_ERROR` to stderr (visible via `stderr_preview`, ENH-2469). Strict
  optional — defer to docs-pass if scope allows.

## Implementation Steps

1. In `scripts/little_loops/loops/rn-implement.yaml` `check_blocked_by`
   (line 360), add `print("UNRESOLVED", file=sys.stderr)` before the
   `sys.exit(0)` at line 412 and `print("PARSE_ERROR", file=sys.stderr)` before
   line 419. Optionally add `print("DONE_SET_ERROR", file=sys.stderr)` before
   lines 439 and 441 for full recheck parity.
2. Leave the bash wrapper, `capture: blocked_by_status`, `next: route_blocked_by`,
   and `on_error: check_depth` untouched — fail-open must not change.
3. Add a test in `scripts/tests/test_rn_implement.py` mirroring
   `test_check_blocked_by_parses_frontmatter_not_show_json` that asserts the
   diagnostic tokens and the `sys.stderr` stream appear in the state `action`.
4. Run `python -m pytest scripts/tests/test_rn_implement.py -v` and
   `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` (guards MR-3
   if a sidecar is added).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be verified
during implementation:_

5. **Hardening guard**: Preserve
   `scripts/tests/test_rn_implement.py:1033` `test_check_blocked_by_fails_open_on_error`'s
   assertion (`on_error == "check_depth"`). The new stderr tokens do not
   alter the route — the existing test must continue to pass.
6. **Sibling-pattern anchor** (Step 3 reinforcement): The new sibling test in
   `TestBlockedByGate` should follow the closest in-file precedent at
   `scripts/tests/test_rn_implement.py:1402` `test_re_enqueue_logs_re_enqueue_marker`
   for static substring assertion of the new tokens in `check_blocked_by.action`.
   For a stronger runtime test (verifies tokens actually reach stderr at
   runtime, not just appear in the action string), mirror the `_bash(...)` +
   `result.stderr` pattern from
   `scripts/tests/test_loops_recursive_refine.py:517-547` instead. Pick one,
   not both, to keep the change scoped.
7. **Cross-class do-not-regress**: Run
   `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_validation.py`
   — adjacent test classes `TestRnImplementDiagnosticOutcomes`,
   `TestRnImplementAuthFastFail`,
   `test_alternative_capture_branches_no_warning` must not regress.
8. **Operator-visible surface** (already in place, no edit): `stderr_preview`
   surfaces the new tokens via `scripts/little_loops/fsm/executor.py:1453-1460`
   (`stderr_preview` derivation), and the stderr pipe path that keeps tokens
   out of `$UNMET` lives at `scripts/little_loops/fsm/executor.py:1547-1615`.
9. **Optional docs touch-up**: `docs/guides/LOOPS_REFERENCE.md:399-435` could
   note that `check_blocked_by` emits stderr tokens visible via `stderr_preview`.
   Strictly optional — existing fail-open prose remains accurate.

## Impact

- **Severity**: Low (latent observability gap, no known defect)
- **Effort**: Trivial
- **Risk**: Low


## Status

**Done** | Created: 2026-07-07 | Completed: 2026-07-08 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-07-07T23:15:00 - (session)
- `/ll:wire-issue` - 2026-07-07T23:00:50 - `a2a457a7-62c3-4f9f-8e72-74ba6766d974.jsonl`
- `/ll:refine-issue` - 2026-07-07T22:47:38 - `05eb9217-1e29-4cc7-adf9-f517827261fd.jsonl`
- `/ll:manage-issue` - 2026-07-08T01:04:48Z - (session) — emit UNRESOLVED/PARSE_ERROR/DONE_SET_ERROR to stderr in `check_blocked_by`; 3 sibling tests added; full suite green (14218 passed, 35 skipped).

## Resolution

Added four `print(..., file=sys.stderr)` calls inside the `check_blocked_by`
heredoc (`scripts/little_loops/loops/rn-implement.yaml:413-447`), one before
each silent `sys.exit(0)` fail-open exit:

| Line | Token            | Trigger                                      |
|------|------------------|----------------------------------------------|
| 414  | `UNRESOLVED`     | Issue file not found across category dirs    |
| 422  | `PARSE_ERROR`    | Frontmatter parse exception                   |
| 443  | `DONE_SET_ERROR` | `ll-issues list --status done` non-zero rc    |
| 446  | `DONE_SET_ERROR` | Exception inside the done-set try block      |

The `no deps` ready exit (line 432) is left alone — it is the legitimate
zero-blocker branch, not an error path.

**Why stderr (not stdout).** Routing the tokens to stdout would leak into the
bash wrapper's `UNMET=$(python3 << 'PYEOF' ...)` substitution. The wrapper
treats non-empty `$UNMET` as `BLOCKED` (`if [ -n "$UNMET" ]`, line 454) →
`route_blocked_by` matches `BLOCKED` → `mark_deferred`. So a literal copy of
the post-remediation recheck's stdout prints would flip the upfront gate from
fail-open to fail-closed. POSIX `$(...)` only captures fd 1; `print(..., file=sys.stderr)`
writes to fd 2, keeping `$UNMET` empty (→ `READY` → fail-open preserved) while
still surfacing the skip via the existing `fsm/executor.py:1452-1462`
`stderr_preview` operator-visibility surface (ENH-2469).

**Tests added** (`TestBlockedByGate` in `scripts/tests/test_rn_implement.py`):
1. `test_check_blocked_by_emits_unresolved_token_to_stderr` — asserts `UNRESOLVED` and `sys.stderr` appear in the action.
2. `test_check_blocked_by_emits_parse_error_token_to_stderr` — asserts `PARSE_ERROR` and `sys.stderr` appear.
3. `test_check_blocked_by_emits_done_set_error_token_to_stderr` — asserts `DONE_SET_ERROR` and `sys.stderr` appear.

**Preserved (no regression):**
- `on_error: check_depth` (line 461) — verified by `test_check_blocked_by_fails_open_on_error`.
- `route_blocked_by` `output_contains "BLOCKED"` — verified by `test_route_blocked_by_defers_on_blocked`.
- `capture: blocked_by_status` — verified by `test_check_blocked_by_state_exists`.
- `$RUN_DIR/blocked_by_unmet_<ID>.txt` write path — verified by `test_check_blocked_by_writes_unmet_under_run_dir` and `test_mark_deferred_names_unmet_blocker`.

**Out of scope (follow-up candidates):**
- The sister gate `check_learning_ready` (`rn-implement.yaml:558-566`) has the
  same silent-fail-open pattern (only 2 exits: unresolved + parse-error; no
  done-set equivalent). The issue's scope is `check_blocked_by` exclusively.
  A dedicated follow-up enhancement should mirror this change at ~line 559
  (`UNRESOLVED`) and ~line 566 (`PARSE_ERROR`).
- Docs touch-up at `docs/guides/LOOPS_REFERENCE.md:399-435` — the existing
  fail-open prose remains accurate; only a soft update noting the new stderr
  tokens would be needed.

**Verification:**
- `python -m pytest scripts/tests/` → 14218 passed, 35 skipped (60.5s, exit 0).
- `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` → valid (all MR-* rules pass; MR-3 not tripped because no sidecar added).
- `ruff check scripts/tests/test_rn_implement.py` → clean.
- `python -m mypy scripts/little_loops/` → no new errors (3 pre-existing in unrelated files).
