---
id: ENH-2738
type: ENH
title: Flip orchestration.request_path default to sdk once ENH-2719 gate passes; apply
  per-loop batch tranche
priority: P2
status: deferred
captured_at: '2026-07-22T00:00:00Z'
discovered_date: '2026-07-22'
discovered_by: issue-size-review
parent: EPIC-2456
depends_on:
- ENH-2719
- ENH-2737
relates_to:
- ENH-2720
- EPIC-2456
- FEAT-2710
labels:
- token-cost
- caching
- configuration
size: Very Large
decision_needed: false
confidence_score: 80
outcome_confidence: 79
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
deferred_by: automation
deferred_date: '2026-07-22T19:42:20Z'
deferred_reason: low_readiness
---

# ENH-2738: Flip orchestration.request_path default to sdk once ENH-2719 gate passes; apply per-loop batch tranche

## Summary

Once ENH-2719's parity/savings measurement runs demonstrate CLI/SDK parity,
flip `orchestration.request_path`'s default from `"cli"` to `"sdk"` in
`config-schema.json`, and add `request_path: "batch"` overrides to the
latency-insensitive loop YAMLs identified by FEAT-2710. This is the
gate-blocked half of ENH-2720 — it cannot start until ENH-2719 closes, and
requires ENH-2737's fallback to exist first (Option A's downgrade path
protects this flip).

## Parent Issue

Decomposed from ENH-2720: Default-flip tranche — orchestration.request_path
cli → sdk/batch after parity verification.

## Blocking Gate

Do not start until:
1. **ENH-2719** closes with: N ≥ 10 real `ll-loop run` invocations under
   `request_path: "sdk"` across ≥2 distinct loops showing (a) exit-status/
   verdict parity with `"cli"` baselines on the same inputs, (b) no new
   failure modes in `usage_events`/run logs, and (c) measured
   `cache_read_input_tokens` share consistent with the F1 gate (>50% of
   iterations). Quantified realized $/run delta.
2. **ENH-2737** merges — the missing-SDK/missing-API-key fallback must exist
   before the default flip, or a fresh install/non-Anthropic host with the
   new default would hard-fail instead of degrading to `"cli"`.

If ENH-2719's gate fails to demonstrate parity, close this issue as
blocked-on-findings rather than flipping.

## Proposed Solution

1. Change `scripts/little_loops/config-schema.json`'s
   `orchestration.request_path` default from `"cli"` to `"sdk"`
   (lines 1574-1579), and the mirrored dataclass/`from_dict()` literals in
   `scripts/little_loops/config/orchestration.py:86,95`
   (`OrchestrationConfig.request_path` default and `data.get("request_path", "cli")`)
   — both must move together per the existing `BUG-2321` drift precedent.
2. Add a concrete-version CHANGELOG entry (not `[Unreleased]`), following the
   `BUG-2321` format: `- **<Title>** — <one-line what/why>. (ENH-2720)`
   (`CHANGELOG.md:864` is the reference entry).
3. `ll-init` needs **no change** — confirmed via directory-wide grep that
   nothing under `scripts/little_loops/init/` stamps `orchestration.request_path`
   today, so the schema default flip applies uniformly to new and existing
   projects with no init-layer migration.
4. Add `request_path: "batch"` to the loop-state YAMLs FEAT-2710 identified as
   latency-insensitive (e.g. background verify/summarization states), using
   the existing per-state override mechanism —
   `StateConfig.request_path` (`fsm/schema.py:630,707-708,804`) already wins
   over the global config default via `_resolve_request_path()`'s
   state-override-first logic (`executor.py:2006`); no new plumbing is
   required. Each override needs a one-line comment citing the 50% Batches
   discount and the submit+poll latency tradeoff.
5. Update `docs/ARCHITECTURE.md` (orchestration.request_path section) and
   `docs/reference/HOST_COMPATIBILITY.md` to note non-Anthropic hosts are
   unaffected (confirmed: `resolve_host()`/`host_cli` is a separate config
   field, never consulted when `request_path` resolves to `"sdk"`/`"batch"`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **ENH-2737 fallback already merged** — the "missing-SDK/missing-API-key
  fallback" blocking-gate precondition is satisfied: commit `6bfa3516`
  ("improve(fsm): fall back sdk/batch request_path to cli on missing package
  or key") is on `main`, implemented inline in
  `FSMExecutor._resolve_request_path()` (`scripts/little_loops/fsm/executor.py:2026-2034`)
  — it probes `import anthropic` and `os.environ.get("ANTHROPIC_API_KEY")`
  after state/config resolution and downgrades to `"cli"` on either failure.
- **A third hardcoded `"cli"` literal exists and is untouched by step 1** —
  `_resolve_request_path()` has an `else: resolved = "cli"` branch
  (`executor.py:2023-2024`) that fires whenever an `FSMExecutor` is
  constructed with `orchestration_config=None`. Two real call sites hit this
  branch and do NOT pass `orchestration_config`, so they will silently stay
  on `"cli"` even after the schema/dataclass default flips to `"sdk"`:
  - `scripts/little_loops/fsm/executor.py:942-950` — the child executor built
    for nested `loop:` state calls (sub-loops never inherit the parent's
    resolved `orchestration_config`).
  - `scripts/little_loops/cli/loop/testing.py:259-264` — `ll-loop simulate`'s
    executor construction.
  This needs an explicit decision before implementation:

  **Option A**: Propagate the parent's `orchestration_config` into the child
  executor (`child_executor = FSMExecutor(..., orchestration_config=self.orchestration_config)`
  at `executor.py:942`) as part of this issue's scope, so nested `loop:`
  states inherit the flipped `"sdk"` default like every other state.

  > **Selected:** Option A — propagating `orchestration_config` to the child
  > executor is a one-line, low-risk change that follows an existing
  > kwarg-passthrough convention at the same call site (`action_runner`,
  > `loops_dir`, `circuit`, `working_dir` already propagate this way), and it
  > closes the exact gap (nested `loop:` states silently staying on `"cli"`)
  > that would otherwise undercut this issue's $/run savings goal for the
  > composite loops most likely to benefit.

  **Option B**: Leave the no-config `else: "cli"` branch as-is and document
  it as a known, intentional gap (nested sub-loops and `ll-loop simulate`
  keep paying full CLI-path cost after the flip).

  **Recommended**: Option A — this issue exists to realize EPIC-2456's $/run
  savings; any loop that fans out via nested `loop:` states would silently
  keep paying full CLI-path cost on the sub-loop legs under Option B,
  undercutting the goal for exactly the composite loops most likely to
  benefit from the flip.
- **FEAT-2710 does not name concrete candidate loop YAML files** — despite
  step 4's phrasing ("loop-state YAMLs FEAT-2710 identified as
  latency-insensitive"), FEAT-2710's Motivation section only lists
  *categories* (`ll-auto` backlog processing, verification/adversarial-verify
  loops, eval harness runs, `ll-queue run` dequeues, FEAT-2598's background
  summarizer), not filenames — FEAT-2710 and its follow-on FEAT-2716 only
  delivered the transport/dispatch infrastructure. A directory-wide grep for
  `request_path:` under `scripts/little_loops/loops/**/*.yaml` returns zero
  matches today — no loop YAML has adopted the override yet, so there is no
  existing example to model placement/comment style after. Candidate files
  matching FEAT-2710's categories (unverified against each loop's actual
  states — confirm latency-insensitivity per-state before adding the
  override): `loops/evaluation-quality.yaml`,
  `loops/oracles/verify-confidence-scores.yaml`, `loops/rn-refine.yaml`,
  `loops/adversarial-redesign.yaml`, `loops/autodev.yaml`,
  `loops/oracles/code-run-gate.yaml`.
- **BUG-2321 precedent is broader than a two-site sync** — its actual scope
  was three disagreeing sources (schema default, an `init/`-layer writer, and
  a runtime `.get(key, default)` consumer), and its Decision Rationale
  explicitly generalizes to "all consumer read-back sites must be
  re-verified in the same pass," not just the schema/dataclass pair — which
  is exactly what surfaced the third `executor.py:2024` literal above.

### Decision Rationale

**Selected: Option A** — propagate `self.orchestration_config` into the
nested child executor at `executor.py:944` (and add the equivalent wiring at
`cli/loop/testing.py`'s `ll-loop simulate` construction), rather than leaving
the no-config `else: "cli"` branch as an undocumented gap.

**Reasoning**: Option A is a mechanically trivial, low-risk change — the
`FSMExecutor.__init__` constructor already accepts `orchestration_config` and
stores it as `self.orchestration_config` before the child-construction call
site runs, so no new plumbing is required, and it follows the identical
kwarg-passthrough convention already used at that call site for
`action_runner`, `loops_dir`, `circuit`, and `working_dir`. No existing test
constructs a nested child executor with a non-`None` `orchestration_config`,
so nothing currently asserts the opposite behavior. Option B's "known,
intentional gap" framing does not hold up under evidence: no comment, doc, or
decision-log entry anywhere characterizes the no-config branch as deliberate
for either call site — it reads as an oversight in the constructor call, not
a considered choice — and for `ll-loop simulate` specifically, the gap is
actively risky rather than neutral: `_dispatch_live()` bypasses the
`SimulationActionRunner` stub entirely, so if the no-config branch ever
naively inherited `"sdk"`/`"batch"` without a real config gate, a dry-run
simulation could make a real, billed API call — undermining the one
documented design property (`no real execution`) `ll-loop simulate` commits
to. Leaving Option B in place would also silently exempt nested `loop:`
states from this issue's default flip, undercutting EPIC-2456's $/run
savings goal for exactly the composite loops most likely to benefit.

**Scoring**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — propagate config | 2 | 3 | 3 | 3 | 11/12 |
| B — leave as-is | 1 | 3 | 2 | 1 | 7/12 |

**Key evidence**:
- `executor.py:165-222` — `FSMExecutor.__init__` already accepts and stores
  `orchestration_config`; the child-construction call site at `executor.py:944`
  needs only `orchestration_config=self.orchestration_config` added to the
  existing kwarg list.
- `executor.py:944-951` already propagates 5 other parent fields
  (`action_runner`, `loops_dir`, `event_callback`, `circuit`, `working_dir`)
  via the identical constructor-kwarg pattern — no precedent exists for
  treating `orchestration_config` differently.
- `cli/loop/testing.py:259-266` (`ll-loop simulate`) has zero
  `orchestration_config` wiring today and no documented rationale tying its
  design intent ("trace through loop logic without executing commands") to
  the request-path choice — the omission is incidental, not deliberate.
- `executor.py:1585` — the `_resolve_request_path(state) in ("sdk", "batch")`
  gate triggers `_dispatch_live()`, which bypasses `SimulationActionRunner`
  entirely; this is why an unguarded flip on the no-config branch would be
  unsafe for `ll-loop simulate`, not merely inconsistent.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json`
- `scripts/little_loops/config/orchestration.py`
- `.ll/ll-config.json` (this repo's own setting, if kept explicit)
- Loop YAMLs selected for `"batch"` per FEAT-2710's candidate list
- `CHANGELOG.md`
- `docs/ARCHITECTURE.md`, `docs/reference/HOST_COMPATIBILITY.md`

### Tests
- `scripts/tests/test_config.py:3208` — `test_from_dict_request_path_defaults_cli` must be updated/renamed to assert `"sdk"`.
- `scripts/tests/test_cache_control.py:294-298,300-304` — `test_orchestration_config_defaults_to_cli` and `test_explicit_sdk_opt_in` (class `TestDefaultBehaviorUnchanged`, docstring "AC: CLI shell path remains default; SDK path is opt-in only") assert `OrchestrationConfig.from_dict({}).request_path == "cli"` — must be updated to `"sdk"` and the docstring/class name reconsidered since "CLI is default" is no longer true.
- `scripts/tests/test_fsm_executor.py:9452` (function starts here; issue's original `:9449` pointed a few lines early) — `test_request_path_cli_default_unaffected` constructs `FSMExecutor(fsm, action_runner=mock_runner)` with **no** `orchestration_config` at all, so it exercises the `else: resolved = "cli"` no-config literal (`executor.py:2023-2024`), not the schema/dataclass default — whether this test's expected behavior changes depends on the open question raised above about whether no-config/child executors should also flip to `"sdk"`.
- `scripts/tests/test_fsm_executor.py:9411-9453` — `test_state_level_request_path_overrides_orchestration_default` (distinct test, not previously distinguished here) constructs `OrchestrationConfig(request_path="cli")` with a state-level `request_path="sdk"` override — asserts state-override-wins and is unaffected by the default flip.
- `scripts/tests/test_config_schema.py:749` — `test_orchestration_request_path_batch_in_schema` (enum membership only) is unaffected by the default flip — no change needed.

## Acceptance Criteria

- `orchestration.request_path` defaults to `"sdk"` with `"cli"` remaining a
  supported explicit opt-out.
- Fresh installs and non-Anthropic hosts (Codex/OpenCode/pi) are unaffected
  (verified via ENH-2737's fallback and `resolve_host()`'s scope check).
- Identified latency-insensitive loop states carry `request_path: "batch"`.
- CHANGELOG entry lands under a concrete version section.
- Full test suite green with the updated default-value assertions.

## Impact

- **Priority**: P2 — the actual $/run-realizing change in EPIC-2456.
- **Effort**: Small once the gate passes — mechanical schema/dataclass/doc edits plus per-loop YAML edits.
- **Risk**: Medium — changes the default network path for every Anthropic-host invocation; mitigated by the parity gate (ENH-2719) and the fallback (ENH-2737).
- **Breaking Change**: No for behavior/outputs (parity-gated); yes for the default transport, which is why the gate exists.

## Labels

`token-cost`, `caching`, `configuration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-22_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION (arithmetic tier only —
actual recommendation is **STOP — BLOCKED**, see Concerns)
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- **Blocking Gate unmet**: ENH-2719 (`EPIC-2456 realized-savings verification
  and closure gate`) is still `status: open`, not closed. This issue's own
  "Blocking Gate" section is explicit: "Do not start until ENH-2719 closes ...
  If ENH-2719's gate fails to demonstrate parity, close this issue as
  blocked-on-findings rather than flipping." Criterion 5 (Dependencies
  Satisfied) is scored 0/20 for this reason — it is the only criterion
  holding readiness back from 100/100. The raw arithmetic lands at
  "PROCEED WITH CAUTION" (80/100) only because every other criterion is
  maxed; this issue-specific hard blocking gate overrides that tier.
- ENH-2737 (the other blocking dependency, missing-SDK/API-key fallback) is
  already satisfied — merged to `main` as commit `6bfa3516`.
- No further refinement is warranted right now: once ENH-2719 closes with a
  passing parity gate, this issue is fully specified and ready to implement
  as written (Option A already decided, files/tests enumerated, third
  hardcoded-literal gap already found).

## Status

**Open** | Created: 2026-07-22 | Priority: P2 | Blocked on: ENH-2719, ENH-2737

## Session Log
- `/ll:confidence-check` - 2026-07-22T00:00:00Z - `cafeda69-1135-4602-b7ba-5314426e3630.jsonl`
- `/ll:decide-issue` - 2026-07-22T19:38:17 - `3403a6c0-5347-46da-bb75-87cafbf4395b.jsonl`
- `/ll:refine-issue` - 2026-07-22T19:34:48 - `07d4f0b8-8d8c-4524-a9cd-fa013c426e58.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `04044445-94db-4521-b724-9e512c0e4211.jsonl`
