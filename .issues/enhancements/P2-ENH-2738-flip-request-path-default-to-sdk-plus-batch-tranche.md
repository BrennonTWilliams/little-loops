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
learning_tests_required:
- anthropic
confidence_score: 80
outcome_confidence: 79
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
deferred_by: human
deferred_date: '2026-07-23T02:14:55Z'
deferred_reason: 'Blocking Gate (ENH-2719 criterion 1) still requires a real N>=10
  opt-in request_path:"sdk" ll-loop run set across >=2 loops, which this sandbox
  cannot execute without ANTHROPIC_API_KEY. A Claude subscription OAuth path exists
  (anthropic SDK credential chain) but whether using it for automated/programmatic
  SDK calls outside Claude Code is permitted under Anthropic''s Consumer Terms of
  Service/Usage Policy is unverified. Deferred pending that ToS clarification or a
  console API key.'
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

### Codebase Research Findings (Blocking Gate re-check)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Both formal dependencies are now closed** — `ll-issues show ENH-2719
  --json` and `ll-issues show ENH-2737 --json` both return `status:
  "Completed"` (ENH-2719 closed 2026-07-23T01:42:46Z via commit
  `f9d0444c`; ENH-2737 closed earlier via commit `6bfa3516`, already noted
  above). Dependency-graph-wise, this issue is unblocked.
- **But the closure report shows criterion 1's quantitative bar was not
  actually met** — `docs/observability/realized-savings-verification.md`
  (ENH-2719's own closure artifact) states, per gate:
  - **F1** (`cache_read_input_tokens` populated on >50% of FSM iterations):
    verdict **"PASS on paper, sample negligible"** — the 6 populated rows
    came from `confidence_check`/`refine_issue`/`wire_issue` states
    captured incidentally during the ENH-2719 session itself, not from a
    real opt-in `request_path: "sdk"` `ll-loop run` set (report lines
    76-95).
  - **F10** (warmed cache-hit rate >80%): verdict **"BLOCKED (structurally
    dormant)"** — zero `sdk`/`batch` traffic exists to measure; the report
    states explicitly "No opt-in `sdk`/`batch` run set exists to measure
    against" (report lines 97-106).
  - The report's own Follow-ups section defers this exact gap to this
    issue: *"F1/F10 remain dormant under the `cli` default; ENH-2738
    already tracks the default flip and is blocked on this issue closing —
    no separate follow-up needed beyond noting F1's tiny sample size in
    ENH-2738's own gate"* (report lines 127-129).
  - This issue's Blocking Gate criterion 1 explicitly requires "N ≥ 10 real
    `ll-loop run` invocations under `request_path: "sdk"` across ≥2
    distinct loops" with parity, no new failure modes, and a quantified
    $/run delta — none of that run set was executed. ENH-2719 closed on
    the strength of its own Expected Behavior clause ("closure is
    conditioned on this report existing — not on every gate passing"),
    which is a lower bar than this issue's own criterion 1.

  **Option A**: Treat ENH-2719's closure as satisfying the Blocking Gate and
  proceed with the flip as scoped. ENH-2737's fallback (already merged,
  `executor.py:2026-2034`) downgrades any `sdk`/`batch` resolution to
  `"cli"` on a missing package or key, which bounds the downside risk even
  without a large pre-flip sample.

  **Option B**: Treat the Blocking Gate as still substantively unmet.
  Before flipping the production default, first execute the N≥10 opt-in
  `request_path: "sdk"` run set across ≥2 distinct loops that ENH-2719's
  own Proposed Solution step 4 scoped but never ran, then re-evaluate this
  issue's readiness against the quantified evidence.

  > **Selected:** Option B — the quantitative bar in this issue's own
  > Blocking Gate criterion 1 was deliberately written stricter than "epic
  > closure," and it remains unmet.

  **Recommended**: Option B — this issue's Blocking Gate criterion 1 is a
  specific, quantified bar (N≥10, ≥2 distinct loops, cache_read >50%
  share, quantified $/run delta) that was deliberately written stricter
  than "epic closure," precisely because this issue changes the default
  network path for every Anthropic-host invocation. ENH-2719's own report
  acknowledges rather than satisfies this gap. Proceeding under Option A
  means flipping the production default on a 6-row incidental sample and
  zero measured `sdk`/`batch` production traffic — the parity evidence
  this issue's Blocking Gate was written to require doesn't yet exist.

#### Blocking Gate Decision Rationale

**Selected: Option B** — the Blocking Gate stays open; do not flip the
default yet.

**Reasoning**: Re-verified at decision time (2026-07-22), not just carried
over from the refine-issue pass: `docs/observability/realized-savings-verification.md`
still shows F1 as "PASS on paper, sample negligible" (6 incidental rows) and
F10 as "BLOCKED (structurally dormant)" (line 21-22 of the report) — no
change since the report was written. A directory-wide grep for
`request_path:` across `scripts/little_loops/loops/**/*.yaml` returns zero
matches, confirming no loop has opted into `sdk`/`batch` and no real
production traffic exists to measure parity against. Both formal
dependencies (ENH-2719, ENH-2737) are closed, so this issue is
dependency-graph-unblocked, but graph-closure and evidentiary sufficiency
are different bars — this issue's own criterion 1 text anticipates and
rejects exactly the "epic already closed" argument Option A makes. Flipping
a default that governs the network transport for every Anthropic-host
invocation on a 6-row incidental sample carries asymmetric downside (silent
degradation across all loops) versus the upside of skipping a small,
already-scoped verification run (ENH-2719 Proposed Solution step 4).

**Scoring**:

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-----------:|:----------:|:------------:|:----:|:-----:|
| A — flip now | 1 | 3 | 1 | 0 | 5/12 |
| B — verify first | 3 | 2 | 3 | 3 | 11/12 |

**Key evidence**:
- `docs/observability/realized-savings-verification.md:21-22` — F1/F10
  verdicts unchanged, re-checked at decision time.
- Zero `request_path:` matches under `scripts/little_loops/loops/**/*.yaml`
  — no opt-in traffic exists yet to satisfy criterion 1's N≥10 bar.
- This issue's own Blocking Gate text (line 68-69): "If ENH-2719's gate
  fails to demonstrate parity, close this issue as blocked-on-findings
  rather than flipping" — Option B is the literal instruction already
  written into the issue, not a new position.

#### Deferral: Auth path for the opt-in run set is blocked on a ToS question (2026-07-23)

**Attempted next step**: execute ENH-2719 Proposed Solution step 4's opt-in
`request_path: "sdk"` run set (N≥10 `ll-loop run` invocations across ≥2
loops) to produce this issue's criterion-1 evidence directly, since ENH-2719
closed without running it.

**Blocker found**: this sandbox has no `ANTHROPIC_API_KEY`, so `_resolve_request_path()`'s
ENH-2737 fallback (`executor.py:2026-2034`) would silently downgrade every
attempted `"sdk"` run back to `"cli"` — producing more `"cli"` traffic, not
the SDK evidence the gate needs.

A Claude subscription auth path does exist and was previously documented as
viable (`FEAT-2673`'s 2026-07-19 correction, lines 144-159): the installed
`anthropic` 0.104.1 SDK's credential chain resolves `ANTHROPIC_API_KEY` →
`ANTHROPIC_AUTH_TOKEN` → an on-disk OAuth profile written by `ant auth login`
→ Workload Identity Federation → a fallback on-disk profile
(confirmed against `anthropic/lib/credentials/_chain.py`). No console API
key is strictly required in principle.

However, on this specific machine that on-disk profile is unpopulated
(`_has_active_profile_config()` returns `False`, `ant` is not installed) —
Claude Code's own OAuth session instead lives in the macOS Keychain
(`security find-generic-password -s "Claude Code-credentials"` confirms it
exists there), a separate store the SDK's credential chain never reads. So
using the subscription for this would require either installing `ant` and
running `ant auth login`, or extracting the Keychain token into
`ANTHROPIC_AUTH_TOKEN` directly.

**Deferred rather than proceeding**: whether using a Claude Pro/Max
subscription's OAuth credential to drive automated, programmatic SDK calls
outside Claude Code itself is permitted under Anthropic's Consumer Terms of
Service / Usage Policy is unverified — that credential is provisioned for
first-party interactive use (claude.ai, Claude Code), and this would be a
different usage pattern (extracted-token, repeated programmatic API calls).
Pulling a stored credential out of Keychain to drive this is not easily
reversible if it turns out to conflict with a usage policy, so this issue is
deferred pending either (a) confirmation from Anthropic that this usage is
permitted, or (b) provisioning a normal console `ANTHROPIC_API_KEY`
(unambiguously billed/metered API access with no ToS question), whichever
the user decides.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Propagate `orchestration_config=self.orchestration_config` into the nested child-executor construction at `scripts/little_loops/fsm/executor.py:944` (Decision Rationale already selected this as Option A, but it was missing from the Integration Map's "Files to Modify" list).
7. Propagate `orchestration_config` into `ll-loop simulate`'s `FSMExecutor` construction at `scripts/little_loops/cli/loop/testing.py:259-266` (same Option A decision, same gap).
8. Add `test_sub_loop_inherits_parent_orchestration_config` to `scripts/tests/test_fsm_executor.py`, modeled on `test_sub_loop_inherits_parent_circuit` (`test_fsm_executor.py:7306-7325`), asserting the child executor's `orchestration_config` is inherited by identity.
9. Add a guard test to `scripts/tests/test_cli_loop_testing.py` patching `dispatch_anthropic_request`/`dispatch_batch_request` and asserting they are never invoked during `cmd_simulate`, to catch `ll-loop simulate` accidentally routing through `_dispatch_live()` after step 7.
10. Update `docs/reference/CONFIGURATION.md`'s `orchestration.request_path` table row and `docs/reference/API.md`'s "Default (`"cli"`) behavior is unaffected" sentence.

## Integration Map

### Files to Modify
- `scripts/little_loops/config-schema.json`
- `scripts/little_loops/config/orchestration.py`
- `.ll/ll-config.json` (this repo's own setting, if kept explicit)
- Loop YAMLs selected for `"batch"` per FEAT-2710's candidate list
- `CHANGELOG.md`
- `docs/ARCHITECTURE.md`, `docs/reference/HOST_COMPATIBILITY.md`
- `scripts/little_loops/fsm/executor.py:942-951` — propagate `orchestration_config=self.orchestration_config` into the nested child-executor construction (Decision Rationale Option A already selected this; it was missing from this file list).
- `scripts/little_loops/cli/loop/testing.py:259-266` — propagate `orchestration_config` into `ll-loop simulate`'s `FSMExecutor` construction (same Option A decision; also missing from this list).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — the `orchestration.request_path` table row states the default as `"cli" (default, unchanged — CLI shell subprocess via resolve_host())"`; goes stale after the flip and is not in this issue's known docs list [Agent 2 finding].
- `docs/reference/API.md` — states "Default (`"cli"`) behavior is unaffected" near `build_anthropic_request`/`dispatch_anthropic_request` docs; goes stale after the flip [Agent 2 finding].

### Tests
- `scripts/tests/test_config.py:3208` — `test_from_dict_request_path_defaults_cli` must be updated/renamed to assert `"sdk"`.
- `scripts/tests/test_cache_control.py:294-298,300-304` — `test_orchestration_config_defaults_to_cli` and `test_explicit_sdk_opt_in` (class `TestDefaultBehaviorUnchanged`, docstring "AC: CLI shell path remains default; SDK path is opt-in only") assert `OrchestrationConfig.from_dict({}).request_path == "cli"` — must be updated to `"sdk"` and the docstring/class name reconsidered since "CLI is default" is no longer true.
- `scripts/tests/test_fsm_executor.py:9452` (function starts here; issue's original `:9449` pointed a few lines early) — `test_request_path_cli_default_unaffected` constructs `FSMExecutor(fsm, action_runner=mock_runner)` with **no** `orchestration_config` at all, so it exercises the `else: resolved = "cli"` no-config literal (`executor.py:2023-2024`), not the schema/dataclass default — whether this test's expected behavior changes depends on the open question raised above about whether no-config/child executors should also flip to `"sdk"`.
- `scripts/tests/test_fsm_executor.py:9411-9453` — `test_state_level_request_path_overrides_orchestration_default` (distinct test, not previously distinguished here) constructs `OrchestrationConfig(request_path="cli")` with a state-level `request_path="sdk"` override — asserts state-override-wins and is unaffected by the default flip.
- `scripts/tests/test_config_schema.py:749` — `test_orchestration_request_path_batch_in_schema` (enum membership only) is unaffected by the default flip — no change needed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — **new test needed**: no test today asserts the nested child executor (built at `executor.py:944-951`) inherits `orchestration_config` from its parent. Model directly on the existing sibling `test_sub_loop_inherits_parent_circuit` (`test_fsm_executor.py:7306-7325`), which asserts `child._circuit is parent._circuit` via the identical constructor-kwarg mirroring pattern — add `test_sub_loop_inherits_parent_orchestration_config` asserting `child.orchestration_config is parent.orchestration_config` [Agent 3 finding].
- `scripts/tests/test_cli_loop_testing.py` — **new test needed, safety-critical**: no existing test in this file (or any `SimulationActionRunner` test elsewhere) patches `dispatch_anthropic_request`/`dispatch_batch_request` and asserts they are never called during `cmd_simulate`. Once `orchestration_config` is propagated into `testing.py:259-266`'s executor construction under the new `"sdk"` default, `ll-loop simulate` risks hitting `_dispatch_live()` and making a real, billed API call — the exact regression the Decision Rationale already flags as a risk of Option A. Add a guard test patching `little_loops.host_runner.dispatch_anthropic_request` (same target used in `test_request_path_sdk_calls_dispatch_not_cli`, `test_fsm_executor.py:9376`) and asserting `mock_dispatch.called is False` for a simulate run [Agent 3 finding].

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — update the `orchestration.request_path` table row; its default-value text currently reads `"cli"` [Agent 2 finding].
- `docs/reference/API.md` — update the "Default (`"cli"`) behavior is unaffected" sentence near the `build_anthropic_request`/`dispatch_anthropic_request` docs [Agent 2 finding].

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

**Deferred** | Created: 2026-07-22 | Priority: P2 | Blocked on: ENH-2719 criterion-1
evidence (unmet) | Deferred 2026-07-23: opt-in `sdk` run set needs either Anthropic
ToS clarification on subscription-OAuth automated use, or a console
`ANTHROPIC_API_KEY`

## Session Log
- `manual-deferral-tos-question` - 2026-07-23T02:15:47 - `f8a392b7-41ef-4f88-a08a-18a38d7d47eb.jsonl`
- `/ll:wire-issue` - 2026-07-23T02:05:44 - `3dffeb66-a7e1-4a84-82b4-d52e6b6612ab.jsonl`
- `/ll:decide-issue` - 2026-07-23T01:55:41 - `b7857b0b-ff46-4283-9763-cff28557a105.jsonl`
- `/ll:refine-issue` - 2026-07-23T01:51:24 - `44ea30ac-dd48-4d76-bfaa-a31dc41815ac.jsonl`
- `/ll:confidence-check` - 2026-07-22T00:00:00Z - `cafeda69-1135-4602-b7ba-5314426e3630.jsonl`
- `/ll:decide-issue` - 2026-07-22T19:38:17 - `3403a6c0-5347-46da-bb75-87cafbf4395b.jsonl`
- `/ll:refine-issue` - 2026-07-22T19:34:48 - `07d4f0b8-8d8c-4524-a9cd-fa013c426e58.jsonl`
- `/ll:issue-size-review` - 2026-07-22T00:00:00Z - `04044445-94db-4521-b724-9e512c0e4211.jsonl`
