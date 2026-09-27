---
id: ENH-3626
type: ENH
title: Add opt-in second-model advise readiness consult to refine-to-ready
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:56:15Z'
relates_to:
- ENH-3590
- ENH-3623
blocks:
- ENH-3590
decision_needed: false
---

# ENH-3626: Add opt-in second-model advise readiness consult to refine-to-ready

## Summary

Add an opt-in `ll-advise` (second-model) readiness consult as the last gate on
`refine-to-ready-issue`'s done path, between `check_proof_before_done` and
`write_done_record`. Every caller gets it: `prepare-issue` (and so autodev),
`recursive-refine`, and rn-refine. The consult is veto-only and fails open. Scope also
includes a shared Python helper that calls `consult_for_trigger` in-process (the same
consult `ll-advise` makes), persists the verdict, and maps it to PROCEED/VETO/SKIPPED, so
ENH-3590 reuses it instead of carrying a second copy.

## Current Behavior

`refine-to-ready-issue.yaml` declares an issue ready on deterministic gates only:
`confidence_check` (the `oracles/verify-confidence-scores` sub-loop) →
`route_score_obligation` (`ll-issues next-obligation` against the readiness/outcome
thresholds) → `check_decision_before_done` → `check_proof_before_done` →
`write_done_record` → `done`. The confidence scores come from the default model; no
state consults a stronger or different model before the issue is handed back as ready.

## Expected Behavior

- With the flag `advise_ready` empty (the default), the done path is unchanged and no
  advisor consult is made.
- With the flag set, whether directly (`ll-loop run refine-to-ready-issue --context
  advise_ready=1`) or inherited from a parent loop (autodev → prepare-issue, recursive-refine),
  an issue that has cleared every deterministic gate gets one advisor consult before
  `write_done_record`.
  - **PROCEED** or **SKIPPED** → `write_done_record` → `done`, as today.
  - **VETO** → the issue does not reach `done`. `record_advisor_veto` writes the existing
    `gate_unmet` legacy class and echoes an `[ADVISOR_VETO]` line carrying the advisor's
    `recommendation`; the full payload stays in `<run_dir>/advise-<ID>.json`. "Deferred"
    here is the **run-record outcome** (`outcome_from_legacy_class`: `gate_unmet` →
    `deferred`), not the issue's `status:` — like `record_gate_unmet`, nothing calls
    `ll-issues set-status deferred`; the issue stays `open` and autodev ledgers it as a
    child stop (`ledger_child_stop` / `skip_inflight`).
- Any consult failure (`skipped_reason` of `budget_exhausted`, `not_configured`,
  `floor_violation`, `failed`, or `timeout`; an unreadable issue file; an exception in the
  helper) is SKIPPED: logged, then treated exactly as if the flag were off. The loop never
  waits on a 429 retry for the advisor.
- **One consult per issue per top-level run, and a replayed verdict never bypasses a veto.**
  Within one `refine-to-ready-issue` run the consult cannot happen twice: it is the last step
  on the done path, and every outcome ends the run (PROCEED/SKIPPED → `done`, VETO →
  `failed`); re-entry after `run_spike` or a decide re-score happens upstream of it. A second
  consult is only possible when a later sub-loop invocation for the same ID shares the
  parent's `run_dir` (`fsm/executor.py:1151-1152`, `setdefault`; `context_passthrough`
  inherits it too). For that case the helper persists its verdict to
  `<run_dir>/advise-<ID>.verdict` and, when that file exists, **replays** it without
  consulting again. A prior VETO is replayed as VETO, never as a pass. The file is keyed by
  ID, so it never crosses issues.

## Motivation

ENH-3590 adds a second-model veto only where go-no-go waives the outcome threshold. That
covers issues that *fail* the threshold and get let through anyway; those issues never
reach refine-to-ready's done edge (a sub-threshold outcome routes to
`check_decision_needed`, not `done`). Issues that *pass* the thresholds get no
second-model review at all. This issue covers that complementary, common path. The two
are not redundant.

## Proposed Solution

**Shared helper (land first).** A Python entry point, `ll-issues advise-consult <ID> --run-dir <dir>`, that:

1. **Replays** a prior verdict first: if `<run_dir>/advise-<ID>.verdict` exists, print its
   token and exit 0 without consulting (see Expected Behavior, one consult per issue per
   top-level run).
2. Otherwise calls `little_loops.advisor.consult_for_trigger("refine_ready", question=<q>,
   context=<issue file text>, manual=True)` **in-process**, with `LL_ISSUE_ID=<ID>` set in
   `os.environ` before the call so `resolve_task_key()` bills the per-issue budget bucket.
   `manual=True` matches `ll-advise`: it bypasses `advisor.enabled` and the
   `advisor.triggers` allowlist, so the new signal needs no config entry.
   **No helper-side timeout.** The consult is bounded by `advisor.timeout_seconds`
   (default 180, `run_blocking_json(timeout=...)`) and returns `skipped_reason="timeout"`.
   A shorter outer timeout would kill consults that would have succeeded, and each one would
   still spend budget, because `consult_for_trigger` reserves budget before the host call.
   **Question text (pinned; the mapping depends on it):** _"Is this issue ready to implement
   as written? Begin your recommendation with exactly one word, PROCEED or VETO, then give
   the reason. VETO only for a concrete defect that would make implementation fail or be
   wasted; otherwise PROCEED."_ ("recommendation", not "answer": the advisor returns
   `_VERDICT_SCHEMA` JSON, and the word must lead the `recommendation` field.) ENH-3590
   passes its own signal/question via `--signal` / `--question` overrides.
3. Writes `<run_dir>/advise-<ID>.json` (the verdict payload, or `{"skipped_reason": ...,
   "error": ...}` on a skip) and `<run_dir>/advise-<ID>.verdict` (the token).
4. Maps the `ConsultOutcome` to PROCEED/VETO/SKIPPED. `verdict is None` → SKIPPED, logging
   `skipped_reason` (a WARNING line for `not_configured` and `floor_violation`). An
   unreadable issue file or any exception inside the helper → SKIPPED. Otherwise the
   **leading word** of `recommendation` decides: `VETO` → VETO, anything else → PROCEED.
   There is no whole-word fallback, so "no reason to VETO" does not veto: a false VETO costs
   more than a false PROCEED. `confidence` and `dissent` are logged but never routed on.
5. Always exits 0 and prints a single routing token (`PROCEED`/`VETO`/`SKIPPED`) that the
   loop routes with `classify` + a `route:` table (the `next-obligation --format token`
   shape). No advisor exit code exists to propagate, so executor-side 429 interception
   (which fires only on non-zero exit) cannot stall the loop.
6. `--write-note`: on VETO, replace any `## Advisor Veto` section in the issue file with
   the recommendation; on PROCEED, remove a stale `## Advisor Veto` section left by an
   earlier run. SKIPPED leaves the file alone. `record_advisor_veto` relies on this (see its
   contract below). The helper owns the note so that one place writes it and clears it.

**Why in-process instead of spawning `ll-advise`:** `ll-advise` exits 2 for every skip
reason and for an unreadable `--context-file`, so a subprocess helper could tell them
apart only by scraping stderr text. It would also stack its own timeout on top of the
advisor's, and it needed a new `.err`/`.rc` persistence convention with no precedent.
The in-process call returns a structured `skipped_reason` and has none of these problems.
Telemetry is unchanged: `consult_for_trigger` writes the `advisor_consults` row itself
(FEAT-3300).

**Why not the existing `advisor_consult` evaluator (FEAT-3039, `fsm/evaluators.py:1743`):**
it already does verdict-map routing and fail-open `neutral`, but it does not fit here:
- It calls `consult_for_trigger` without `manual`, so it needs `advisor.enabled: true` and
  an `advisor.triggers` entry for a non-default signal. The opt-in would then take a config
  change plus the flag.
- It bills whichever task key is ambient, which is the loop-run key under `ll-loop`, not
  the per-issue key.
- It builds its context only from `context_from` interpolation paths, not the issue file.
- It persists no payload, so there is nothing for the veto note or for replay.
- ENH-3590 needs the same consult from a policy step, not from an evaluator.

**Parser reuse:** extract the lead-word step of `_parse_advisor_decision`
(`evaluators.py:1726`) into a shared public function, e.g.
`little_loops.advisor.parse_lead_word(recommendation, choices) -> str | None`. The
evaluator keeps its whole-word fallback on top; the helper uses the lead word only. The two
advisor paths then tokenize a recommendation the same way.

ENH-3590's consult (a policy step once ENH-3623 lands) calls the same helper with its own
`--signal`/`--question`.

**Loop wiring in `refine-to-ready-issue.yaml`:**

```
check_proof_before_done --on_no/on_error--> check_advise_ready_enabled   # was write_done_record
check_advise_ready_enabled --on_no/on_error--> write_done_record          # flag `advise_ready` empty
                           --on_yes--> run_advise_ready
run_advise_ready --PROCEED/SKIPPED--> write_done_record   # helper replays a prior verdict itself
                 --VETO--> record_advisor_veto  # writes gate_unmet, echoes [ADVISOR_VETO], next: failed
```

State names are proposals. The gate checks only the flag. Replay lives in the helper, so no
loop state reads or writes a marker.

**Flag declaration: only top-level loops put it in `context:`.** With
`context_passthrough`, the executor merges `{**parent, **captured, **child_fsm.context}`
(`fsm/executor.py:1160`), so a child's own `context:` literal **overrides** the inherited
value. That is the BUG-2767 trap. If `refine-to-ready-issue.yaml` or `recursive-refine.yaml`
declared `advise_ready: ""` in `context:`, a parent's `advise_ready=1` would be replaced by
`""` and the gate would never fire. The declarations are therefore:
- `autodev.yaml`: `context: advise_ready: ""`. It is top level, the same idiom as
  `skip_learning_gate: ""`, and `--context advise_ready=1` overrides it.
- `refine-to-ready-issue.yaml` and `recursive-refine.yaml`:
  `parameters: advise_ready: {type: string, required: false, default: ""}`.
  `seed_parameter_defaults` (BUG-3425) uses `setdefault`, so an inherited or `--context`
  value wins and a standalone run still gets `""`. Check that each loop's `parameters:`
  block is compatible with its `context_passthrough` callers.
- `prepare-issue.yaml`: nothing. It has no `context:` block and passes everything through.

The gate reads `${context.advise_ready}` in a `[ -n ... ]` test, escaped per MR-11.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

**Corrections to the premises above (from this pass's research):**
- Only 5 of the 7 skip reasons are reachable through `ll-advise`: `manual=True` makes `disabled` and `trigger_not_allowed` unreachable. Exit 2 also covers an unreadable `--context-file` (not a skip reason) and argparse errors. The helper must treat every non-zero rc as SKIPPED regardless.
- The per-issue budget bucket is billed only if `LL_ISSUE_ID` is exported: no loop YAML sets it (only `issue_manager.py` and `parallel/worker_pool.py` do). Without it, `resolve_task_key()` falls to `LL_LOOP_RUN_ID` (kind `loop_run`), so the helper itself must set `LL_ISSUE_ID` on the child process for the "shared with `confidence_gate`/`pre_done`" budget claim to hold.
- "No stdout parsing (MR-1)" mislabels the rule: MR-1 concerns pairing LLM evaluators with non-LLM ones and permits `classify`. Existing routing helpers use two shapes — exit-code (`check-flag`, `check-verify-verdict`, via `shell_exit`) and stdout token with exit 0 (`next-obligation --format token`, `run-record read --format token`, via `classify` + `route:` table). A three-way PROCEED/VETO/SKIPPED result fits either; the shape is a design decision.
- `.rc`/`.err` persistence has no precedent (existing loops read exit codes via `${captured.<state>.exit_code}`; only `vega-viz.yaml` writes an ad-hoc error file), so the `advise-<ID>.{json,err,rc}` layout is new convention, not a followed one. _(Moot after review: the in-process helper persists only `advise-<ID>.{json,verdict}`.)_

**Review corrections (applied to the directive sections above):**
- **Flag shadowing.** `context_passthrough` puts the child's `context:` last in the merge
  (`fsm/executor.py:1160`), so declaring `advise_ready: ""` in a child loop's `context:`
  would silently disable the gate for every caller. Child loops now use
  `parameters.advise_ready.default` (`fsm/context_seed.py:seed_parameter_defaults`,
  setdefault).
- **Timeout.** `advisor.timeout_seconds` defaults to 180 (`config/orchestration.py:160`),
  and `consult_for_trigger` calls `record_consult()` before the host call
  (`advisor.py:540`). The old 120s subprocess timeout would have killed consults that would
  have succeeded, and still spent the budget. It is removed.
- **Marker.** The "re-entered after `run_spike`/decide re-score" rationale was wrong: the
  consult comes after those gates, and every consult outcome ends the run. Under a shared
  `run_dir`, the old "marker present → `write_done_record`" edge let a second invocation
  pass an issue that the first had vetoed. The marker is replaced by verdict replay in the
  helper.
- **Transport.** `ll-advise` subprocess → in-process `consult_for_trigger(manual=True)`:
  structured `skipped_reason`, no stderr scraping, no `.err`/`.rc` convention.
- **Existing evaluator.** The `advisor_consult` evaluator (FEAT-3039) was considered and
  not used; see "Why not the existing `advisor_consult` evaluator". Its lead-word parser is
  shared instead.

**Option A**: New run-record class `advisor_veto` mapped to a `blocked` outcome, with its own token in `RUN_RECORD_TOKENS`, a recording state in `refine-to-ready-issue.yaml`, a `forward_stop` case in `prepare-issue.yaml`, and an explicit `route_refine_outcome` route in `autodev.yaml`. Distinguishes vetoes in telemetry and lets each caller route them independently; widens a closed vocabulary across five files.

**Option B**: Reuse an existing legacy class (e.g. `gate_unmet` → `deferred`, or `quality` → `blocked`) with the advisor recommendation carried in the session log only. No vocabulary change and callers already handle it; a veto becomes indistinguishable from other gate failures in run records.

> **Selected:** Option B — reuses the existing `gate_unmet`/`quality` legacy classes; no closed-vocabulary change.

**Recommended**: Option B for v1 — the consult is opt-in and veto-only, and the closed-vocabulary change is the highest-cost, highest-blast-radius part of this issue; promote to Option A if veto telemetry proves needed.

### Decision Rationale

**Selected option:** Option B — reuse an existing legacy run-record class.

**Reasoning:** `RUN_RECORD_TOKENS` is a closed 12-member tuple (`run_record.py:143`) and unrecognized tokens collapse to `MISSING`; Option A widens it across `run_record.py`, `refine-to-ready-issue.yaml:classify_terminal`, `prepare-issue.yaml:forward_stop`, `autodev.yaml:route_refine_outcome`, and `test_run_record.py`. Option B reuses `gate_unmet` (→ `deferred`) or `quality` (→ `blocked`), already mapped in `outcome_from_legacy_class` and already handled by every caller. The feature is opt-in and veto-only, so the loss of veto telemetry is acceptable for v1.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — new `advisor_veto` class | 2 | 1 | 2 | 1 | 6/12 |
| B — reuse legacy class | 3 | 3 | 2 | 3 | 11/12 |

**Key evidence:** `run_record.py:46-50,215-217` (existing `gate_unmet`/`quality` mapping); `autodev.yaml:685` (classify table enumerates the full closed vocabulary); the issue's own **Recommended** marker for Option B.

**`record_advisor_veto` contract (mirror `record_gate_unmet`, `refine-to-ready-issue.yaml:1136-1148`):**
1. `printf 'gate_unmet' > ${context.run_dir}/refine-terminal-class` — required: autodev's
   MISSING fallback reads this file, so omitting it loses the class.
2. `ll-issues run-record write <ID> --run-dir ... --writer refine-to-ready-issue --legacy-class gate_unmet || true`.
3. Echo `[ADVISOR_VETO] <ID> - <recommendation>`.
4. **Make the veto actionable:** `run_advise_ready` calls the helper with `--write-note`, so
   by the time `record_advisor_veto` runs, the issue file already has an `## Advisor Veto`
   section carrying the recommendation (replacing any earlier one). A human or the next
   refine pass sees why. The issue already passed every deterministic gate, so
   re-refining without this note changes nothing. A later PROCEED removes the section.
   The edit is **not committed**: the run ends at `failed`, which never reaches a commit
   step, so the note stays in the working tree as a visible change. Say so in the
   `[ADVISOR_VETO]` echo.
5. `next: failed`, `on_error: failed`.

**Follow-through (resolved in review):** the class is `gate_unmet` (→ deferred). `record_gate_unmet` itself is not reused: its message is specific to structure gates. A new `record_advisor_veto` state writes the same `gate_unmet` legacy class with an accurate `[ADVISOR_VETO]` message, then `next: failed`. No vocabulary change.

**Accepted fail-open on re-runs:** a vetoed issue keeps `status: open`, so a later
top-level run refines it again, and each run consults again against the per-issue budget
(`max_consults_per_task=3`). Once that is spent, `consult_for_trigger` returns
`budget_exhausted` → SKIPPED → the issue passes, so repeated runs can wait out a veto.
Accepted for v1: the consult is opt-in and veto-only. Verdict replay is per top-level run
(`run_dir` is per instance), so a prior veto does not force a re-consult beyond what the
budget allows.

**Accepted budget contention with implementation-time consults.** The per-issue budget
file (`.ll/advisor-budget/issue-<ID>.json`) never expires. It is shared with the `pre_done`
hook (`hooks/pre_done.py`) and `issue_manager`'s confidence-gate consult
(`issue_manager.py:849`). Each readiness consult, including re-runs that wait out a veto,
uses one of `max_consults_per_task` (default 3). So enabling `advise_ready` can use up the
budget before implementation's `pre_done` consult runs, and that consult is then skipped.
Accepted for v1 because the feature is opt-in. Document it next to the flag. If it bites,
the follow-up is a separate budget scope for readiness consults, which is a
`resolve_task_key` change.

## Program Design

### Types

- `AdviseVerdict`: `Literal["PROCEED", "VETO", "SKIPPED"]`

### Signatures

- `parse_lead_word(recommendation: str, choices: Iterable[str]) -> str | None` — shared lead-word tokenizer extracted from `_parse_advisor_decision`; returns the lowercased leading word if it is in *choices*, else `None`
- `map_advise_verdict(outcome: ConsultOutcome) -> tuple[AdviseVerdict, str]` — pure mapping of a consult outcome to a verdict plus a log reason (`verdict is None` → SKIPPED; lead word `veto` → VETO; else PROCEED)
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — replays `advise-<ID>.verdict` if present, else sets `LL_ISSUE_ID` and calls `consult_for_trigger(manual=True)`, persists `advise-<ID>.{json,verdict}`, applies `--write-note`, prints the token, always returns 0

### Call Path

`refine-to-ready-issue.yaml:check_proof_before_done` -> `check_advise_ready_enabled` -> `run_advise_ready` -> `cmd_advise_consult` -> `consult_for_trigger` -> `map_advise_verdict` -> `parse_lead_word`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new gate/consult/veto states on the done path (`check_advise_ready_enabled`, `run_advise_ready`, `record_advisor_veto`); bump `max_steps` (currently 100) for the two extra hops and record it in the history comment
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (again) — declare the flag as `parameters.advise_ready.default: ""`, **not** in `context:` (a `context:` literal overrides the parent's value under `context_passthrough`)
- `scripts/little_loops/loops/recursive-refine.yaml` — same `parameters.advise_ready.default: ""` declaration (not `context:`), so a flag from `rn-build`/`sprint-build-and-validate`/`issue-refinement` or `--context` still reaches `refine-to-ready-issue` (pass-through only; it does not read run records)
- `scripts/little_loops/loops/prepare-issue.yaml` — no declaration needed (`context_passthrough: true`, no `context:` block); no veto handling needed, `gate_unmet` → deferred is already handled by `forward_stop`
- `scripts/little_loops/loops/autodev.yaml` — declare the flag in `context:` (`""`; top-level, so the `context:` literal is correct here) and let it pass to `prepare-issue`; no `route_refine_outcome` change
- `scripts/little_loops/cli/issues/advise_consult.py` (new file) — new helper subcommand (`add_advise_consult_parser`/`cmd_advise_consult`/`map_advise_verdict`)
- `scripts/little_loops/advisor.py` — new public `parse_lead_word()`
- `scripts/little_loops/fsm/evaluators.py` — `_parse_advisor_decision` calls `parse_lead_word()` for its lead-word step (behavior unchanged; its whole-word fallback stays)

### Dependent Files (Callers/Importers)
- `ll-advise` CLI (`little_loops.cli.advise.main_advise`) — not called by the helper; it is the model for the `manual=True` in-process call
- `little_loops.advisor.consult_for_trigger` — called directly; reserves budget before the host call; per-issue budget (`max_consults_per_task=3`) shared with the `confidence_gate` (`issue_manager.py:849`) and `pre_done` consults
- `little_loops.fsm.evaluators._parse_advisor_decision` / `evaluate_advisor_consult` — refactored to use `parse_lead_word`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — four registration sites for the new subcommand: lazy import block, epilog listing (next to `next-obligation`/`run-record`), `add_*_parser(subs)` block, `args.command` dispatch [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/next_obligation.py` (`register(subs)`), `check_verify_verdict.py`, `run_record.py` — sibling helper modules; models for the new module's `add_<name>_parser`/`cmd_<name>` shape [Agent 1 finding]
- `scripts/little_loops/run_record.py` (`outcome_from_legacy_class`, `LEGACY_CLASSES`) — Option B reuses `gate_unmet` → deferred; no vocabulary edit, but this is the mapping the veto route depends on. The new `record_advisor_veto` writer state is a new writer of that class, so `test_run_record.py` sets need entries [Agent 1 finding, corrected in review]
- `scripts/little_loops/loops/rn-build.yaml:582`, `sprint-build-and-validate.yaml:82,181`, `issue-refinement.yaml:21` — call `recursive-refine`; inherit the empty default, need edits only if they should forward the flag [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml`, `auto-refine-and-implement.yaml`, `oracles/resolve-decision.yaml` — other `refine-to-ready-issue` callers; confirm they pass no `context:` that would shadow the flag, and that the flag-off path is unchanged for them [Agent 1 finding]
- `scripts/little_loops/hooks/pre_done.py` — existing `consult_for_trigger` consumer; shares the per-issue budget the new consult draws from [Agent 1 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "Score dispatch (ENH-3604)" `NONE` bullet lists `check_decision_before_done` → `write_done_record` → `done`, omitting `check_proof_before_done`; add the proof gate and the opt-in advise hop. Also the `refine-to-ready-issue` table row (~line 84) [Agent 2 finding]
- `docs/reference/CLI.md` — new `#### \`ll-issues <name>\`` section and subcommand-table entry; cross-reference from `### ll-advise` [Agent 2 finding]
- `docs/reference/API.md` — new row in the `little_loops.cli.issues.*` module table (next to the `run-record` row) [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md` — VETO → `gate_unmet` → deferred; add a row if the veto records a new `--reason` code [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` header comment (done-path diagram, ~line 48) — update to include `check_proof_before_done` and the new gate; record any `max_steps` change in the history comment (~lines 120-132) [Agent 2 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- No `config-schema.json` change: the helper passes `manual=True` (as `ll-advise` does), so the `refine_ready` signal needs no `advisor.triggers` entry and `advisor.enabled` need not be set. `docs/reference/CONFIGURATION.md` `### advisor` (`max_consults_per_task`, `timeout_seconds`) is the budget and timeout the consult uses. Document the budget contention with `pre_done` next to the flag [Agent 2 finding, updated in review]

### Tests
- `scripts/tests/test_builtin_loops.py` — chain-shape pins, default-off, flag propagation parent → child (guards against a child `context:` literal shadowing it), stub-`ll-issues advise-consult` execution for routing
- New helper tests — `map_advise_verdict` over fixture `ConsultOutcome`s (each `skipped_reason`, PROCEED/VETO lead words, "no reason to VETO"), replay, `--write-note` write/clear, with `consult_for_trigger` monkeypatched
- `scripts/tests/test_fsm_evaluators.py` and `scripts/tests/test_advisor.py` (existing `advisor_consult` / advisor tests) — must pass unchanged after `parse_lead_word` extraction

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_decision_gate_routes` — asserts `check_proof_before_done` `on_no`/`on_error == "write_done_record"`; will break, retarget to `check_advise_ready_enabled` [Agent 3 finding]
- `scripts/tests/test_autodev_proof_reentry.py` (`STATE = CHILD["check_proof_before_done"]`, lines ~207-208) — same two edge assertions; will break, update [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_only_gate_write_done_record_and_class_writers_reach_done` — inbound-edges-to-`done` check; should survive, re-verify [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (`max_steps == 100` assertion, ~line 1872) — update if the two extra hops force a `max_steps` bump [Agent 3 finding]
- `scripts/tests/test_fsm_topology.py` (state-count asserts at ~lines 291, 322) — unconfirmed whether they cover `refine-to-ready-issue`; read before editing the loop [Agent 3 finding]
- `scripts/tests/test_run_record.py` (`LEGACY_CLASS_STATES`, `TERMINAL_BEARING_STATES`, and the done-path gate sets) — `record_advisor_veto` is a new writer of `gate_unmet`: add it to the class-writer sets, and add the new gate/consult states to whichever done-path sets apply [Agent 3 finding, corrected in review]
- `scripts/tests/test_builtin_loops.py` (`skip_learning_gate` block, ~lines 18023-18264; registry tuples ~lines 20599-20763, e.g. `("loops/autodev.yaml", "context.skip_learning_gate", "ENH-3358")`) — model for the flag's empty-default and pass-through pins; a new `context.<flag>` reference likely needs a matching registry row [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py` (tuple table, ~lines 256-264) — add `("docs/reference/CLI.md", "#### \`ll-issues <name>\`", "ENH-3626")` and the `API.md` row, or the docs gate fails [Agent 3 finding]
- New `scripts/tests/test_ll_issues_<name>.py` — model on `test_ll_issues_next_obligation.py::TestCli` (`_cli()` helper, `--help` registration, exit codes) and `test_run_record.py::TestRecordToken` (parametrized `map_advise_verdict` cases); the helper is in-process, so monkeypatch `consult_for_trigger` rather than stubbing `ll-advise` on `PATH`; loop-level tests stub `ll-issues` with the `chmod(0o755)` pattern from `test_builtin_loops.py` [Agent 3 finding, updated in review]
- `scripts/tests/test_fsm_validation_shell_safety.py` (MR-11) and `test_fsm_validation_evaluator_rules.py` (MR-10) — the new state's shell action must escape `$${...}` and must not swallow a JSON parse failure with exit 0 [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Nothing proposed exists yet: no `check_advise_ready_enabled`/`run_advise_ready`/`record_advisor_veto`/`advisor_veto` outside `.issues/`, no `ll-advise` reference in any loop YAML, no advise-flavored `ll-issues` subcommand.
- Done chain today: `route_score_obligation` (classify on `ll-issues next-obligation --format token`; `NONE` → `check_decision_before_done`) → `check_proof_before_done` (`fragment: shell_exit`; `on_no`/`on_error` → `write_done_record`) → `done`. `check_missing_artifacts.on_yes` also feeds `check_decision_before_done`, so a gate placed after `check_proof_before_done` covers both done edges.
- `refine-to-ready-issue.yaml` `context:` holds only `max_refine_count`; thresholds are seeded at launch and must not be declared (BUG-2767). The empty-string flag needs a declaration site per loop chain: `autodev.yaml` `context:` (as `skip_learning_gate: ""`); `recursive-refine.yaml` `context:`; `refine-to-ready-issue.yaml` `context:` _(superseded in review: a child's `context:` literal overrides the inherited value under `context_passthrough`, so the two child loops use `parameters.advise_ready.default` instead; see Proposed Solution)_. `prepare-issue.yaml` declares no `context:` and receives everything via `context_passthrough: true`, so it needs no declaration. `rn-remediate.yaml` uses `parameters.<k>.default` instead of `context:` (BUG-3425) — a third convention.
- Callers: `autodev.yaml:refine_current` → `prepare-issue` → `run_refine_to_ready` → `refine-to-ready-issue` (all `context_passthrough: true`); `recursive-refine.yaml:run_refine` → `refine-to-ready-issue`. A sub-loop reaching `done` is success; `failed` takes the failure path. `recursive-refine` does not read run records — it routes on the sub-loop terminal then `check_passed`.
- Veto outcome plumbing (if a new run-record class is chosen): `run_record.py` (`LEGACY_CLASSES`, `outcome_from_legacy_class`, `RUN_RECORD_TOKENS` — a closed 12-member tuple, unrecognized → `MISSING`), `refine-to-ready-issue.yaml` `classify_terminal`, `prepare-issue.yaml:forward_stop`, `autodev.yaml:route_refine_outcome` (classify table enumerating the closed vocabulary), `test_run_record.py` (`TestOutcomeMapping.CASES`, `LEGACY_CLASS_STATES`).
- `ll-issues` subcommand wiring is three-site: module in `scripts/little_loops/cli/issues/` with `add_<name>_parser`/`cmd_<name>(config, args) -> int`; lazy import + `add_*_parser(subs)` + `args.command` dispatch + epilog line in `cli/issues/__init__.py`; docs anchors pinned by `scripts/tests/test_wiring_reference_docs.py`.
- 429 handling is executor-side: `fsm/executor.py:_intercept_transient_failure` fires only when `exit_code != 0` AND output classifies as transient rate-limit/quota; a zero exit is never intercepted. It is inert on `loop:` states. The helper's always-routing-code contract must therefore avoid propagating the advisor's non-zero exit and avoid emitting rate-limit text on a state that returns non-zero.
- `ll-advise` (`cli/advise.py:main_advise`/`cmd_invoke`) always passes `manual=True`, which bypasses the `advisor.enabled` switch and the `advisor.triggers` allowlist: `--signal` is a free string, so a new signal name needs no config or code change, and the budget (`max_consults_per_task`) still applies.

## Implementation Steps

1. Extract `parse_lead_word` into `little_loops.advisor` and have `evaluators._parse_advisor_decision` call it (existing evaluator tests must pass unchanged).
2. Build and test the shared helper `ll-issues advise-consult`: in-process `consult_for_trigger(manual=True)`, `LL_ISSUE_ID` set before the call, verdict replay from `advise-<ID>.verdict`, `advise-<ID>.json` persistence, lead-word-only mapping, always-exit-0 token contract, `--write-note` (write on VETO, clear on PROCEED), unreadable issue file → SKIPPED, no outer timeout, pinned question text.
3. (Decided) Veto class = `gate_unmet` via a new `record_advisor_veto` state that writes `refine-terminal-class`, the run-record (`|| true`), and the `[ADVISOR_VETO]` echo (the note is already written by the helper); add the state to `LEGACY_CLASS_STATES`/`TERMINAL_BEARING_STATES` in `test_run_record.py`.
4. Wire `check_advise_ready_enabled` (flag only), `run_advise_ready` (`classify` + `route:`), and `record_advisor_veto` into `refine-to-ready-issue.yaml`; bump `max_steps` and update the header diagram/history. Declare the flag as `advise_ready: ""` in `autodev.yaml` `context:` and as `parameters.advise_ready.default: ""` in `refine-to-ready-issue.yaml` and `recursive-refine.yaml`. **Never** declare it in a child loop's `context:`.
5. Tests: `budget_exhausted`/`not_configured`/`timeout` outcomes → SKIPPED → `write_done_record`; flag set on autodev/recursive-refine reaches the child gate (propagation test that fails if a child `context:` literal shadows it); replay (same ID twice under a shared `run_dir` → one consult; a replayed VETO still vetoes; two IDs → two consults); veto writes `refine-terminal-class`; the note is written on VETO and cleared on PROCEED; lead-word-only mapping ("no reason to VETO" → PROCEED); default-off chain reaches `write_done_record` without consulting; VETO/PROCEED/SKIPPED routing; `LL_ISSUE_ID` is in `os.environ` at consult time; existing callers treat the veto as a deferred stop.
6. `ll-loop validate` for every touched loop.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the new subcommand in `scripts/little_loops/cli/issues/__init__.py` — lazy import, epilog line, `add_*_parser(subs)`, `args.command` dispatch
- Update `scripts/tests/test_autodev_decision_gate.py` and `scripts/tests/test_autodev_proof_reentry.py` — retarget the `check_proof_before_done` `on_no`/`on_error` assertions to the new gate state
- Check `scripts/tests/test_builtin_loops.py` `max_steps == 100` and `scripts/tests/test_fsm_topology.py` state counts; bump if the extra hops require it
- Add `context.<flag>` registry rows and empty-default/pass-through pins in `scripts/tests/test_builtin_loops.py`, modelled on `skip_learning_gate` (note: `skip_learning_gate` is only read in the loop that declares it, so it never had the child-shadowing problem; the `advise_ready` pins must also assert child loops use `parameters.advise_ready.default`, not `context:`)
- Add `scripts/tests/test_wiring_reference_docs.py` rows plus `docs/reference/CLI.md` and `docs/reference/API.md` entries for the new subcommand
- Update `docs/guides/LOOPS_REFERENCE.md` (Score dispatch `NONE` bullet, `refine-to-ready-issue` row) and the `refine-to-ready-issue.yaml` header diagram comment
- Confirm the other `refine-to-ready-issue` / `recursive-refine` callers (`rn-remediate`, `auto-refine-and-implement`, `oracles/resolve-decision`, `rn-build`, `sprint-build-and-validate`, `issue-refinement`) are unaffected by the empty default

## Impact

- **Priority**: P3 - opt-in quality improvement, not blocking
- **Effort**: Medium - one helper (plus a small `parse_lead_word` extraction), three loop states, flag pass-through; no new run-record class
- **Risk**: Low - off by default, fail-open
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the shared helper; the opt-in done-path gate in `refine-to-ready-issue`
  with per-run verdict replay in the helper; a `record_advisor_veto` state reusing the
  `gate_unmet` class; the `## Advisor Veto` note (write on VETO, clear on PROCEED);
  context-flag pass-through; extracting a shared `parse_lead_word`.
- **Out of scope (added in review)**: a new run-record class or `RUN_RECORD_TOKENS` change
  (Option B); caller edits for veto handling; cross-run veto persistence.
- **Out of scope**: the go-no-go waiver veto (ENH-3590); letting a consult grant
  readiness or override a failing gate; routing on `confidence`/`dissent`; enabling the
  consult by default; changing `ll-advise` internals.

## Open Questions

_None outstanding._ Resolved in review:

- **Where does a veto route?** `record_advisor_veto` writes the existing `gate_unmet` class
  (→ deferred) and goes to `failed`; existing callers already handle it (Option B).
- **Does a veto persist across passes?** Within one top-level run, yes: the helper replays
  the persisted verdict. Across runs, no: a later run re-consults until the per-issue budget
  is spent, after which the consult is SKIPPED (accepted fail-open; see Decision Rationale).
- **Subprocess `ll-advise` or in-process?** In-process `consult_for_trigger(manual=True)`
  (review; see "Why in-process instead of spawning `ll-advise`").
- **Reuse the `advisor_consult` evaluator?** No; its lead-word parser is shared instead
  (review; see "Why not the existing `advisor_consult` evaluator").
- **Who writes the veto note?** The helper (`--write-note`), which also clears it on
  PROCEED.

## Acceptance Criteria

- [ ] With the flag empty (default), the done path reaches `write_done_record` without calling `consult_for_trigger`
- [ ] A flag set on a parent (`autodev --context advise_ready=1` → prepare-issue → refine-to-ready-issue; `recursive-refine --context advise_ready=1` → refine-to-ready-issue) reaches the child gate as `1`. No child loop declares `advise_ready` in `context:`; child loops use `parameters.advise_ready.default: ""`
- [ ] With the flag set, a threshold-passing issue gets at most one consult per top-level run, billed to the per-issue budget via `LL_ISSUE_ID` set by the helper before calling `consult_for_trigger`
- [ ] A second helper invocation for the same ID under the same `run_dir` replays the persisted verdict without consulting; a replayed VETO routes to `record_advisor_veto`, never to `write_done_record`
- [ ] The helper sets no outer timeout; a consult slower than `advisor.timeout_seconds` maps to SKIPPED via `skipped_reason="timeout"`
- [ ] The payload (or skip record) and token are persisted to `<run_dir>/advise-<ID>.{json,verdict}` and mapped by the shared helper; the loop routes on the helper's token
- [ ] VETO keeps the issue out of `done`, records `gate_unmet` (run-record outcome `deferred`; issue `status:` unchanged) via `record_advisor_veto`, echoes an `[ADVISOR_VETO]` line with the recommendation, and existing callers handle it with no edits
- [ ] Any consult failure (`budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`, unreadable issue file, helper exception) behaves exactly like the flag being off; the loop never halts or waits on an advisor rate limit
- [ ] `record_advisor_veto` writes `refine-terminal-class` = `gate_unmet`; the helper's `--write-note` has already put an `## Advisor Veto` section carrying the recommendation in the issue file, and a later PROCEED removes it
- [ ] The consult question text ("Begin your recommendation with…") is pinned in the helper, and a fixture test maps the real `_VERDICT_SCHEMA` payload shape to PROCEED/VETO. Only the lead word counts: "no reason to VETO" → PROCEED
- [ ] `parse_lead_word` is shared by the helper and `evaluators._parse_advisor_decision`; the existing `advisor_consult` evaluator tests pass unchanged
- [ ] ENH-3590 can reuse the helper unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-27T04:18:11 - `b81845df-148e-4cb8-8d11-cc360743e07f.jsonl`
- `/ll:decide-issue` - 2026-09-27T04:03:27 - `4b1c5ade-bd97-4871-b4cf-1f3dcd7cc5d1.jsonl`
- `/ll:refine-issue` - 2026-09-27T04:01:53 - `b9726386-58c1-4c65-8485-76e226017a2f.jsonl`
- `/ll:format-issue` - 2026-09-27T03:56:23 - `0b26d35d-ec12-419a-9599-7aa7bcfe4ed1.jsonl`
- `/ll:capture-issue` - 2026-09-27T01:56:21 - `282c1e7b-289d-4b4c-9b06-d9e617a5b759.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Conventions in force: helper verdict mapping is a pure function separate from `cmd_*` and returns a safe token for unrecognized input (`check_verify_verdict.classify_verify_verdict`, `run_record.record_token`); tests parametrize over cases (`test_run_record.py::TestOutcomeMapping.CASES`) and add a subprocess exit-code test (`test_ll_issues_next_obligation.py::TestCli`). Advisor CLI tests patch `sys.argv` and call `main_advise()` (`test_cli_advise.py::TestMainAdvise`).
- Loop tests pin chain shape with static edge assertions on the loaded YAML plus stub-binary execution (`test_builtin_loops.py`: stub `ll-issues`/`ll-advise` on `PATH`, textual `${context.run_dir}` substitution, `"${" not in script`, `$${` restored to `${`). Default-off flags are pinned as `parameters.<k>.default == ""` / `context` value `== ""`. Sub-loop states must not carry `on_no` or `timeout` (`TestSubLoopStateTimeoutAudit`).
- Any new `ll-issues` subcommand needs a `test_wiring_reference_docs.py` entry (`docs/reference/CLI.md` heading and `docs/reference/API.md` row) or the docs gate fails.
