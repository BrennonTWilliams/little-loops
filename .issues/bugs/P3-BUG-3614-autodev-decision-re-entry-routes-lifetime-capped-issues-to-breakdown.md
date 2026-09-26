---
id: BUG-3614
type: BUG
title: Autodev DECISION re-entry routes lifetime-capped issues to breakdown
priority: P3
status: open
discovered_by: capture-issue
discovered_date: '2026-09-26'
captured_at: '2026-09-26T06:53:39Z'
parent: EPIC-3565
relates_to:
- ENH-3610
- ENH-3611
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3614: Autodev DECISION re-entry routes lifetime-capped issues to breakdown

## Summary

Autodev's ENH-3610 `DECISION` re-entry sends an issue that has used up its lifetime refine
budget back into `refine-to-ready-issue`. That child run routes the issue to
`breakdown_issue` before it reaches any decision-resolution state. The issue is then
decomposed instead of being deferred as `decision_unresolved`.

## Current Behavior

- `select_obligation_post_refine` and `select_obligation_pre_implement` (`autodev.yaml`)
  print `DECISION` → `refine_current` whenever `ll-issues check-flag <ID> decision_needed`
  exits 0. `autodev-reentry-DECISION-<ID>` caps this at one re-entry per issue. The only
  guard is that re-entry cap.
- Every child run starts `resolve_issue` → `check_issue_resolved` → `check_epic_id` →
  `check_lifetime_limit`. `check_lifetime_limit` routes `on_no` → `breakdown_issue` once
  `ll-issues refine-status <ID> --json` `refine_count` (the session-log `/ll:refine-issue`
  count) reaches `commands.max_refine_count` (default 5).
- So a capped issue that is re-entered for `DECISION` never reaches
  `check_decision_before_done` / `resolve_decision_pre_breakdown`. `route_refine_success`
  sees `DECOMPOSED` → `detect_children`, not a `decision_unresolved` deferral.
- Every re-entry also runs `/ll:refine-issue` unconditionally (`precheck_format` →
  `refine_issue`), which adds one to `refine_count`. Re-entry itself therefore moves issues
  toward the cap.

## Steps to Reproduce

**Most likely path (count crosses the cap during the first child run):**

1. Take an issue with `decision_needed: true` whose session log records `max_refine_count - 1`
   (default 4) `/ll:refine-issue` runs.
2. Run `ll-loop run autodev`. The first `refine_current` passes `check_lifetime_limit`; the
   child's `refine_issue` takes `refine_count` to the cap, and the child returns with
   `decision_needed` still set.
3. The selector (`select_obligation_post_refine` or `select_obligation_pre_implement`) prints
   `DECISION` → `refine_current`. The re-entered child's `check_lifetime_limit` exits `on_no` →
   `breakdown_issue`.
4. Observe: autodev routes `DECOMPOSED` → `detect_children`. The issue is not ledgered as
   `decision_unresolved`.

**Already-capped path:** an issue whose session log already records `max_refine_count` runs
reaches `select_obligation_pre_implement` via a site that does not run the child first
(`reopen_waived`, `recheck_scores`, …). Steps 3–4 are the same. (An already-capped issue that
goes through the first `refine_current` is broken down there, before any selector runs — that
is existing lifetime-cap behaviour and out of scope.)

## Expected Behavior

- The `DECISION` re-entry guard also requires `refine_count` < `max_refine_count`. Resolve the
  cap the way the child's `check_lifetime_limit` does: `commands.max_refine_count` in
  `.ll/ll-config.json`, default 5. Autodev has no `max_refine_count` context key, so read the
  config and do not add one.
- When the cap is reached, the selector prints `DECISION_EXHAUSTED` → `record_reentry_exhausted`,
  which ledgers `decision_unresolved` and defers the issue. It never reaches `breakdown_issue`
  through a `DECISION` re-entry.
- The guard mirrors the one ENH-3611 adds for `PROOF` re-entry (ENH-3611 "Shared re-entry
  guard"). No shared helper exists, so drift is prevented by: (a) a structural test asserting
  the two selectors' `DECISION` blocks stay byte-identical, and (b) ENH-3611 copying this
  issue's cap snippet verbatim (BUG-3614 lands first).
- When the cap term fires, the selector writes a diagnostic to **stderr**
  (`[DECISION_CAPPED] <ID> refine_count=N cap=M`) — `classify` reads stdout only, and
  `record_reentry_exhausted`'s own message ("after child re-entry") is inaccurate for this case.

## Motivation

Heavily refined issues are the most exposed: several passes that did not converge are what
leave `decision_needed` set. At the pre-implement site the issue already passes readiness and
outcome, so the current behaviour decomposes a high-scoring issue that only needed a decision.
A spurious breakdown creates child issues and hides the real reason, an unresolved decision.

## Proposed Solution

Add a lifetime-cap term to the `DECISION` branch of both obligation selectors. When the cap is
reached, reuse the existing `DECISION_EXHAUSTED` → `record_reentry_exhausted` route. No new
state and no new token are needed.

### Alternatives Considered

- **Fix in the child** (`check_lifetime_limit` routes decision-flagged leaves to decision
  resolution instead of `breakdown_issue`): rejected — it spends LLM budget past the lifetime
  cap and changes `refine-to-ready-issue`'s standalone semantics for every caller.
- **Read the cap with `ll-config get commands.max_refine_count`**: not viable —
  `max_refine_count` is not modelled in `BRConfig`, so `resolve_variable()` (via `to_dict()`)
  returns nothing even when the key is set (verified with a temp config of `7`). A raw JSON
  read of `.ll/ll-config.json` is the only option; like `check_lifetime_limit`, it does not
  honour `.ll/ll.local.md` overrides (consistent with the child, so acceptable).
- **Follow-up (not this issue)**: expose `max_refine_count` / `at_lifetime_cap` in
  `ll-issues refine-status --json` so all four cap sites (`check_lifetime_limit`,
  `check_attempt_budget`, both selectors, ENH-3611's PROOF guard) share one helper.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`: `select_obligation_post_refine` and
  `select_obligation_pre_implement` `DECISION` branch; update both comments (the re-entry cap
  now has two terms).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: `check_lifetime_limit` (read-only
  reference; the cap resolution must match it)
- `little_loops.cli.issues.refine_status`: source of `refine_count`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status` emits `refine_count` (single object when an ID filter is given; excludes gap-analysis passes per BUG-3356; deferred issues return their real count per BUG-3357) [Agent 2 finding]
- `scripts/little_loops/loops/recursive-refine.yaml` — `check_attempt_budget` (~169-188) is a second copy of the cap idiom (`max_refine_count` from config, `LL_ARG_MAX_REFINE_COUNT` fallback); keep the selector's resolution rule aligned [Agent 1 finding]
- `scripts/little_loops/loops/autodev.yaml` — `record_reentry_exhausted` (`DECISION_EXHAUSTED` target; must keep its `set-status deferred --by automation --reason decision_unresolved` shape) and `dequeue_next` (clears `autodev-reentry-*-<ID>` markers) [Agent 1/2 finding]
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — comment above `check_unresolved` (~246-253) describes the one-shot re-entry; update wording if it should mention the lifetime-cap exit [Agent 1/2 finding]
- `scripts/little_loops/config-schema.json` — `commands.max_refine_count` (read-only; source of the cap) [Agent 1 finding]
- Selector entry edges (read-only, must stay intact): `check_passed`, `recheck_scores`, and the reopen/regate states routing to `select_obligation_pre_implement` in `autodev.yaml` [Agent 1 finding]

### Similar Patterns
- ENH-3611's `PROOF` re-entry guard (same cap term; specified as prose only, no shared code)
- `check_lifetime_limit`'s config read (`commands.max_refine_count`, env-var fallback from
  `context.max_refine_count` — a key autodev lacks, so the fallback is hardcoded 5 here)

### Tests
- `scripts/tests/test_autodev_decision_gate.py`: `TestObligationSelectorStructural` and
  `TestObligationSelectorBehavior`; extend `_StubIssues` to answer `refine-status --json`
  (see `## Tests` below)
- `scripts/tests/test_autodev_scores_freshness.py::test_dequeue_clears_markers_for_reentry`:
  must keep passing (regression check)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py::TestObligationSelectorStructural` — exact `route` dict equality (~lines 192-206, includes `"DECISION_EXHAUSTED": "record_reentry_exhausted"`) breaks only if a new route key is added; the plan reuses the existing token, so it should pass unchanged [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py::TestDecisionReentryFlow` (~453) and the `_drive(states, stub, run_dir, start, child)` FSMExecutor harness — model for the new "capped issue never visits `breakdown_issue`" tests; extend `_StubIssues` (~46) to answer `refine-status --json` [Agent 3 finding]
- New subprocess-level selector tests following `test_builtin_loops.py::test_check_readiness_honors_context_over_config` (~2050: tmp `.ll/ll-config.json`, fake `ll-issues` on `PATH`, `bash -c`) — cover the cap boundary (`refine_count == cap-1` re-enters, `== cap` exhausts) and `commands.max_refine_count` override; compare `test_loops_recursive_refine.py::TestCheckAttemptBudget::test_exactly_max_refine_count_attempts_then_budget_skip` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestAutodevRnImplementDeferralParity` (`AUTODEV_NOT_READY_STATES`, ~9671-9676) — requires `record_reentry_exhausted` to keep the rn-implement `mark_deferred` shape; do not alter that state [Agent 2 finding]
- `scripts/tests/test_builtin_loops.py` `TestInterpSweepBaseline` / `MR11_MARKER_ALLOWLIST` (~21006-21021) and `scripts/tests/data/loop_interpolation_baseline.json` — a new embedded Python body interpolating `${context.*}` in a selector is an unbaselined site; pass values via env var in a quoted heredoc [Agent 1/3 finding]
- `scripts/tests/test_fsm_interpolation.py` (`test_nested_variable_syntax_raises_interpolation_error`, `test_bash_default_operator_raises_interpolation_error`, BUG-954) — constrains cap syntax: no `${X:-${context.*}}` nesting; write bash defaults as `$${VAR:-x}` [Agent 3 finding]
- `scripts/tests/test_fsm_topology.py` (`len(topo["states"]) == 105`, ~271) — unaffected while no state is added; breaks if a new terminal state is introduced [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_gate.py::test_implement_edges_route_through_guard` (~302) — pins `selector["route"]["_"]`/`["_error"]` on `select_obligation_pre_implement`; leave those keys unchanged [Agent 3 finding]
- `scripts/tests/test_refine_status.py` — existing pins on the `refine_count` JSON field (~950, ~991, ~1627, ~2140-2169); read-only reference [Agent 2 finding]

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` (autodev section): mention the lifetime-cap term on
  re-entry, if the selector re-entry cap is documented there

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "Decision handling" paragraph (~1081) says the child is re-entered at most once and that exhaustion goes via `record_reentry_exhausted`; add that a lifetime-capped issue also exhausts there. Read long lines ~152 and ~1087 ("Outcome failure triage") before editing [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — `max_refine_count` context-variable row (~1140) says the cap is enforced by `check_attempt_budget`; autodev selectors are now a further consumer [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-issues check-flag` "Which gate states consume which flag (ENH-3250)" (~2269-2275): selectors now also read `refine-status` after `check-flag` [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md` — `decision_unresolved` row (~21): `record_reentry_exhausted` emitter description still holds; optionally note the lifetime-cap trigger [Agent 2 finding]
- `docs/reference/CONFIGURATION.md`, `skills/configure/areas.md`, `skills/configure/show-output.md` — `commands.max_refine_count` text says it is enforced by refine-to-ready-issue and `check_attempt_budget`; add autodev DECISION re-entry. Editing `skills/` trips mirror gates: run `ll-adapt --host <gemini|kimi-code|qwen> --apply` afterwards [Agent 2 finding]

### Configuration
- N/A (reads the existing `commands.max_refine_count`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` — `commands.max_refine_count` description (~540) may need "autodev DECISION re-entry" added; no new key [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Cap-resolution convention**: the cap is `commands.max_refine_count` from `.ll/ll-config.json`, read in a quoted `python3 << 'PYEOF'` heredoc that receives its fallback through an env var (`LL_ARG_MAX_REFINE_COUNT=${context.max_refine_count:shell}`), so no context value is interpolated into Python source. `refine_count` comes from `ll-issues refine-status "<ID>" --json | python3 -c "...int(d.get('refine_count', 0))..."` with `except: print(0)` / `|| echo 0`, compared with `-ge`. Evidence: `refine-to-ready-issue.yaml:check_lifetime_limit` (lines ~226-258). The `:shell` suffix is the convention for interpolated IDs/values.
- **Default-5 source**: the default lives in a loop `context:` key (`refine-to-ready-issue.yaml:137`, `recursive-refine.yaml:40`). `autodev.yaml` has no such key (only a comment near line 2625), so a selector that needs a fallback either hardcodes 5 or reads an undefined context key — the two-layer default cannot be copied as-is. No shared cap-check helper exists in `loops/lib/`; both `check_lifetime_limit` copies and the two selector DECISION blocks are inline duplicates.
- **Selector DECISION block is duplicated byte-for-byte** in `select_obligation_post_refine` (~733-780) and `select_obligation_pre_implement` (~782-827): `check-flag <ID> decision_needed`; on exit 0, un-stage the ID (`grep -vxF` on `autodev-staged.txt`); read marker `${context.run_dir}/autodev-reentry-DECISION-<ID>`; `N>=1` prints `DECISION_EXHAUSTED`, else write `N+1` and print `DECISION`; then `exit 0` so `next-obligation` never runs while the flag is set. Route tables for `DECISION` (→ `refine_current`) and `DECISION_EXHAUSTED` (→ `record_reentry_exhausted`) are identical in both. Ordering constraint: a cap term evaluated after the marker write would consume the one-shot re-entry marker for an issue that is never re-entered.
- **`record_reentry_exhausted`** (~829-852) hardcodes the `decision_unresolved` ledger reason and defers via `set-status deferred --by automation --reason decision_unresolved` (skipped if already done/completed/cancelled), then `dequeue_next`; `dequeue_next` clears `autodev-reentry-*-<ID>` markers (line ~127).
- **Interpolation-baseline ratchet**: `TestInterpSweepBaseline.test_completeness_guard` (`test_builtin_loops.py`) diffs `scan_corpus` against `scripts/tests/data/loop_interpolation_baseline.json` in both directions, and scans only embedded Python bodies (heredocs, `python3 -c`). Neither selector has an embedded Python body today and neither is baselined, so a new Python snippet interpolating `${context.*}` in a selector is a new unbaselined site. Passing values by env var with a quoted heredoc (as `check_lifetime_limit` does) avoids it.
- **Brace escape**: selectors currently use bare `$ID`/`$N`/`$F`; any new bash `${VAR:-x}` in an FSM action must be written `$${VAR:-x}` (only the summary state uses it today).
- **ENH-3611 guard is prose-only**: it is specified (ENH-3611 "Shared re-entry guard") as a per-selector shell block with no shared code artifact, and PROOF has no `_EXHAUSTED` token (an exhausted PROOF defers as `blocked_by_gate`). The "one idiom or helper" expectation therefore has nothing implemented to reuse; the two caps can only be kept aligned by matching the `check_lifetime_limit` resolution rule.

## Program Design

### Types

- No new types

### Signatures

- `cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int` — existing; the selectors read `refine_count` from its `--json` output
- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing; the `DECISION` probe that the new cap term extends

### Call Path

Both selectors share the same path; each can reach either target:

`autodev.yaml:select_obligation_pre_implement` -> `cmd_check_flag` -> `cmd_refine_status` -> `autodev.yaml:record_reentry_exhausted` (capped or marker set) | `autodev.yaml:refine_current` (under cap, first re-entry)

`autodev.yaml:select_obligation_post_refine` -> `cmd_check_flag` -> `cmd_refine_status` -> `autodev.yaml:record_reentry_exhausted` (capped or marker set) | `autodev.yaml:refine_current` (under cap, first re-entry)

## Implementation Steps

1. In both selectors' `DECISION` branch (duplicated byte-for-byte), read `refine_count` via
   `ll-issues refine-status <ID> --json` and the cap from `commands.max_refine_count` in
   `.ll/ll-config.json` (hardcoded fallback 5, since autodev has no `max_refine_count` context
   key). If `refine_count >= cap`, print `DECISION_EXHAUSTED`. Keep the un-staging before the
   route, and evaluate the cap term **before** the `autodev-reentry-DECISION-<ID>` marker write so
   an issue that is never re-entered does not consume the one-shot marker.
2. Keep ENH-3610's exit-code contract: a `refine-status` failure must not break the
   `check-flag` → `next-obligation` fall-through. Treat an unreadable count as "under the cap"
   (current behaviour).
3. Match `check_lifetime_limit`'s **resolution rule**, not its heredoc form:
   - **Do not use an indented `python3 << 'PYEOF'` heredoc.** The `DECISION` branch is nested in
     an `if`, and an indented terminator never closes the heredoc (verified: bash fails with
     "unexpected EOF"). Use a single-quoted `python3 -c '…'` that reads `.ll/ll-config.json`
     (`commands.max_refine_count`) with no FSM interpolation in its body. (If a heredoc is
     preferred, follow `autodev.yaml` ~409-426: body and terminator at the block's base indent.)
   - Never interpolate `${context.*}` (incl. `run_dir`) into Python source
     (interpolation-baseline ratchet).
   - **Do not write the fallback as `$${CAP:-5}`.** The test harness's `_interp()` regex
     (`\$\{([^}]+)\}`) matches the inner `${CAP:-5}` and raises `KeyError`. Use the
     `check_lifetime_limit` form: `[ -z "$CAP" ] && CAP=5`.
   - Do not use `ll-config get` (see Alternatives Considered).
4. ENH-3611's guard is prose-only (no shared code artifact), so implement the cap term inline in
   each selector (byte-identical blocks). ENH-3611 copies this snippet for `PROOF`.
5. Emit `[DECISION_CAPPED] <ID> refine_count=N cap=M` to stderr when the cap term fires.
6. Update the comment above each selector's `DECISION` branch (the re-entry cap now has two
   terms) and add tests in `scripts/tests/test_autodev_decision_gate.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_autodev_decision_gate.py` — extend `_StubIssues` to answer `refine-status --json` (count from a file, so it can change between calls) and give `_StubIssues.run()` a `cwd` parameter (tmp dir) so the selector's `.ll/ll-config.json` read never picks up the repo's own config; add `_drive`-based tests (capped → `record_reentry_exhausted`, `breakdown_issue` never visited, for both selectors) and under-cap unchanged
- Cover the cap boundary and `commands.max_refine_count` override in the same file via the `cwd`-isolated stub (tmp `.ll/ll-config.json`) — no separate `test_builtin_loops.py` subprocess tests needed
- Add a structural test asserting the two selectors' `DECISION` blocks are byte-identical (drift guard)
- Keep `record_reentry_exhausted`, the selector `_`/`_error` routes, and the entry edges unchanged (`test_builtin_loops.py` deferral-parity, `test_ll_issues_check_gate.py`, `test_fsm_topology.py` count of 105)
- Update `docs/guides/LOOPS_REFERENCE.md` ("Decision handling" ~1081, `max_refine_count` row ~1140)
- Update the `commands.max_refine_count` description in `scripts/little_loops/config-schema.json` to name autodev `DECISION` re-entry
- Update the comment above `check_unresolved` in `scripts/little_loops/loops/oracles/resolve-decision.yaml` (~246-253) to mention the lifetime-cap exit
- **Descoped** (Effort: Small): `docs/reference/CLI.md` check-flag consumer note, `docs/reference/CONFIGURATION.md`, `skills/configure/areas.md`, `skills/configure/show-output.md` (the `skills/` edits would also trip the `ll-adapt` mirror gates)
- Run `python -m pytest scripts/tests/test_builtin_loops.py -k "InterpSweep or Autodev"` to confirm no new unbaselined interpolation site

## Impact

- **Priority**: P3 - wrong outcome (spurious decomposition) but only for issues at the
  lifetime refine cap; no data loss
- **Effort**: Small - one guard term in two selectors plus tests
- **Risk**: Low - only narrows when a re-entry fires; the fallback route already exists
- **Breaking Change**: No (loop-internal)

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `select_obligation_post_refine`, `select_obligation_pre_implement` (ENH-3610)
- **Cause**: the re-entry guard checks only the per-run re-entry marker. It ignores the child's
  own lifetime entry gate (`check_lifetime_limit` in `refine-to-ready-issue.yaml`), which runs
  before any decision state.

## Tests

- Real-FSM test: a `decision_needed` issue with `refine_count == max_refine_count` reaches
  `select_obligation_pre_implement` and is deferred `decision_unresolved` via
  `record_reentry_exhausted`. `breakdown_issue` never runs.
- Same for `select_obligation_post_refine`.
- **Cross-the-cap test** (the realistic path): `refine_count == cap - 1` on entry; the stubbed
  child bumps it to `cap` and returns with `decision_needed` set; the selector exhausts →
  `record_reentry_exhausted`, and the `autodev-reentry-DECISION-<ID>` marker is not written.
- Boundary: `refine_count == cap - 1` at the selector re-enters; `== cap` exhausts.
  `commands.max_refine_count` override in a tmp `.ll/ll-config.json` is honoured.
- Unreadable count (stub prints nothing) → treated as under the cap.
- `[DECISION_CAPPED]` appears on stderr, not stdout.
- Structural: both selectors' `DECISION` blocks are byte-identical.
- Under the cap, behaviour is unchanged: one `DECISION` re-entry → `refine_current`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Selector tests live in `scripts/tests/test_autodev_decision_gate.py`, not `test_builtin_loops.py` (which only has structural checks such as `test_required_states_exist`). Two layers: `TestObligationSelectorStructural` (exact `route` dict equality, substring presence in the action, `load_and_validate`) and `TestObligationSelectorBehavior` (runs the real action under `bash -c` against `_StubIssues`).
- `_StubIssues` handles only `check-flag`, `next-obligation`, `show`; every other subcommand (including `refine-status`) hits `*) exit 0` and prints nothing, and the test cwd has no `.ll/ll-config.json`. Under-cap and capped behavioral cases therefore need the stub to answer `refine-status --json`; the "unreadable count = under cap" contract is exactly what the current stub exercises by default.
- `_interp()` substitutes `${...}` through a fixed dict (`context.run_dir`, `captured.input.output[:shell]`, thresholds); a new `${context.X}` reference in a selector raises `KeyError` unless added there.
- `test_autodev_scores_freshness.py::test_dequeue_clears_markers_for_reentry` covers marker clearing and must keep passing.

## Acceptance Criteria

- [ ] Neither selector re-enters the child for `DECISION` once `refine_count` >= `max_refine_count`
- [ ] A capped decision-flagged issue defers as `decision_unresolved`, never decomposes
- [ ] Under-cap behaviour and ENH-3610's exit-code contract are unchanged
- [ ] The cap term is evaluated before the re-entry marker write (a capped issue never consumes the marker)
- [ ] Both selectors' `DECISION` blocks are byte-identical, pinned by a structural test

## Related

Found during the ENH-3611 review (2026-09-26); ENH-3611 lists this as out of scope.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-26T07:14:04 - `1eb03218-20ce-453a-bf86-789e28cb50a6.jsonl`
- `/ll:wire-issue` - 2026-09-26T07:04:31 - `c8822019-43a9-4d0f-b257-475aeb4ab3ec.jsonl`
- `/ll:reconcile-issue` - 2026-09-26T07:01:39 - `7d8d5da2-5970-46c4-a7de-295402f96f22.jsonl`
- `/ll:refine-issue` - 2026-09-26T06:59:52 - `83a53e9a-c833-443d-91cf-22a5699e1980.jsonl`
- `/ll:capture-issue` - 2026-09-26T06:53:45 - `06522881-acec-4007-9c05-e417309eaff8.jsonl`
