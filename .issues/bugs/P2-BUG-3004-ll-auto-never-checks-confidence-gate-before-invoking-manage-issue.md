---
id: BUG-3004
title: ll-auto never checks the confidence gate, so it spends a full ready-issue pass
  on issues manage-issue will immediately halt
type: BUG
priority: P2
captured_at: '2026-08-02T18:59:27Z'
completed_at: '2026-08-02T21:18:57Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- ll-auto
- confidence-gate
- issue-manager
- autodev-parity
relates_to:
- BUG-3002
status: done
testable: true
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
---

# BUG-3004: ll-auto never checks the confidence gate before invoking manage-issue

## Summary

`ll-auto` selects an issue, spends a full `/ll:ready-issue` LLM pass proving it
implementation-ready, then hands it to `/ll:manage-issue` — which halts
immediately at its own Phase 2.5 confidence gate. Nothing in the `ll-auto`
pipeline reads `confidence_score` or compares it to
`commands.confidence_gate.readiness_threshold`, so `ll-auto` cannot predict,
prevent, or remedy a gate it structurally guarantees it will hit.

Observed on `ll-auto --only BUG-3002` (2026-08-02): 2.3 minutes in Phase 1 to
reach `VERDICT: READY`, then 31.6 seconds in Phase 2 to `HALTED at Phase 2.5
(Confidence Gate)` because `confidence_score: 80` is below the project's
`readiness_threshold: 85`. Zero files changed; Phase 3 correctly refused to mark
the issue done; the run ended with `Issues processed: 0`.

The same gate is handled correctly by `autodev.yaml`, which calls
`ll-issues check-readiness` at three points and routes sub-threshold issues to
`confidence-check` / `refine` remediation states *before* implementing. `ll-auto`
has no equivalent. The deterministic primitive already exists and costs
milliseconds; it is simply never wired in.

## Steps to Reproduce

1. Ensure `.ll/ll-config.json` has `commands.confidence_gate.enabled: true` with
   `readiness_threshold: 85`.
2. Pick an open, unblocked, well-formed issue whose frontmatter carries
   `confidence_score` below 85 (e.g. `confidence_score: 80`,
   `outcome_confidence: 75`).
3. Run `ll-auto --only <ISSUE-ID>`.
4. Observe: Phase 1 runs `/ll:ready-issue` to completion and returns `READY`
   (minutes of LLM time). Phase 2 runs `/ll:manage-issue` and halts in seconds at
   the confidence gate with no files changed. Phase 3 refuses to mark the issue
   complete. The run exits having processed nothing.

## Current Behavior

The confidence gate is enforced at the one layer that cannot see it. All three
places `ll-auto` could catch a sub-threshold score are blind to it:

| Stage | Code | Confidence-aware? |
|-------|------|-------------------|
| Selection | `dependency_graph.py` `get_ready_issues()` | No — filters only on `blocked_by` / `depends_on` |
| Phase 1 | `commands/ready-issue.md` | No — the string "confidence" appears once, in unrelated prose about program design; its validation table has no score row |
| Phase 2 | `issue_manager.py` `process_issue_inplace()` | No — builds `/ll:manage-issue {type} {action} {arg}` with no `--force-implement`; "confidence" appears nowhere in the module except one unrelated comment |

`skills/manage-issue/SKILL.md` (Phase 2.5) makes the gate a hard HALT: when
`config.commands.confidence_gate.enabled` is true and `confidence_score` is
absent or below `readiness_threshold`, and `--force-implement` is not set, it
stops without implementing. `ll-auto` never passes `--force-implement` and never
runs `/ll:confidence-check`, so a sub-threshold issue is an unconditional dead
end that still costs a full Phase 1.

The failure is also silent in the wrong way: Phase 2 exits 0, so the only signal
is Phase 3's tamper guard ("REFUSING to mark ... as completed: no code changes
detected despite returncode 0"), which reads like an execution fault rather than
a gate refusal.

## Expected Behavior

`ll-auto` should evaluate the confidence gate deterministically *before* spending
LLM time, and either skip or remediate:

- Run the millisecond-cost frontmatter check before Phase 1, not after it.
- **The pre-check must replicate `manage-issue` Phase 2.5 exactly, not
  approximate it** — see "Gate Parity" below. Predicting a downstream gate means
  matching its comparison; any divergence re-creates the class of bug this issue
  exists to close, just in the opposite direction (skipping work that
  `manage-issue` would have implemented).
- On a sub-threshold score, either (a) skip the issue with an explicit,
  greppable reason naming the numbers — e.g. `below_readiness_threshold (80 <
  85)` — or (b) run `/ll:confidence-check <ID>` and re-check once, mirroring
  `autodev.yaml`'s remediation route.
- Never invoke `/ll:manage-issue` for an issue whose score cannot clear the gate
  unless `--force-implement` is deliberately threaded through.
- The skip reason must survive into the run summary so the operator sees *why*,
  not a generic filter message.

### Gate Parity: readiness only, not outcome

`skills/manage-issue/SKILL.md:183` gates on **`confidence_score` vs
`readiness_threshold` only**. It never reads `outcome_confidence`. The
pre-Phase-1 check must do the same.

This is a live divergence, not a hypothetical: `check_readiness.py:53` returns
`0 if (confidence >= readiness and outcome_val >= outcome)` — it requires *both*.
Reusing that comparison verbatim would make `ll-auto` **stricter** than the gate
it is predicting, so an issue at `confidence_score: 90` / `outcome_confidence:
60` would be skipped before Phase 1 even though `manage-issue` would have
implemented it without complaint. (BUG-3004 itself sits at 96/66 — one point of
outcome slack.)

Both threshold values still come from the operator's
`commands.confidence_gate` block in `.ll/ll-config.json` (schema:
`config-schema.json:483`). Matching parity means the pre-gate simply does not
consult `outcome_threshold`, exactly as `manage-issue` does not. The
`ll-issues check-readiness` CLI keeps its existing both-thresholds contract
unchanged — see step 1 below; the two callers deliberately ask different
questions of the same helper.

### Gate Parity: `manage-issue` also skips Phase 2.5 on `verify` / `plan` actions

_Added during pre-implementation review (2026-08-02) — second parity hole, same
class as the readiness/outcome one above._

`skills/manage-issue/SKILL.md:181` skips the confidence gate entirely when the
action is `verify` or `plan`, or when `--quick` is set. `ll-auto` picks the
action at `issue_manager.py:1018` via
`action = config.get_category_action(info.issue_type)`, which returns an
**arbitrary operator-configured string** from `issues.categories[*].action`
(`config/core.py:485-496`) — the built-in templates ship `fix` / `implement` /
`improve` / `coordinate`, but nothing constrains a project from configuring
`plan` or `verify` for a category.

An unconditional pre-Phase-1 gate would therefore skip issues that
`manage-issue` would have processed without ever consulting the gate — the
inverse-direction bug this Gate Parity analysis exists to prevent. The pre-gate
must resolve `action` before firing and short-circuit:

```python
action = config.get_category_action(info.issue_type)
if action in ("verify", "plan"):
    # manage-issue Phase 2.5 is skipped for these actions; predicting a gate
    # that will not run would skip work that would otherwise be done.
    ...fall through to Phase 1...
```

`--quick` is not reachable from `ll-auto` (it never appends the flag —
`issue_manager.py:1051`), so only the action check is needed. Note this means
`action` is computed slightly earlier than today; the Phase 2 site at `:1018`
should reuse the already-resolved value rather than recompute it.

## Motivation

Every sub-threshold issue in the backlog burns a full `ready-issue` pass —
minutes of paid LLM time — to produce a guaranteed no-op. In an unattended
`ll-auto` run over a backlog, that cost is paid once per affected issue, and each
one ends with a tamper-guard warning that reads like a tooling malfunction.

Worse, it misdirects diagnosis: the operator sees "command returned success but
issue not moved" and "REFUSING to mark as completed", which points at subprocess
invocation, not at a frontmatter score five points shy of a threshold. The real
cause is only visible by reading the streamed Phase 2 transcript.

This is also an `ll-auto` / `autodev.yaml` parity gap. The two paths do the same
job; one gates correctly and one does not, so behavior depends on which runner
the operator happened to pick.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in function process_issue_inplace()`
- **Cause**: The function goes straight from setup into Phase 1
  (`/ll:ready-issue`) and then Phase 2 (`/ll:manage-issue`) with no readiness
  precondition. `little_loops.cli.issues.check_readiness.cmd_check_readiness`
  implements exactly the needed comparison (parse frontmatter, read
  `commands.confidence_gate` from `.ll/ll-config.json`, compare
  `confidence_score`/`outcome_confidence` against thresholds) but is reachable
  only as the `ll-issues check-readiness` CLI subcommand. Its only callers are
  `autodev.yaml` shell actions; no Python caller exists, and `issue_manager.py`
  never invokes the CLI either.

## Proposed Solution

Extract the comparison from the CLI wrapper so Python callers can use it, then
add a pre-Phase-1 gate in `process_issue_inplace()`.

1. **Extract a pure helper** in `check_readiness.py` so the logic is callable
   without an `argparse.Namespace`. The dataclass **reports** state; it does not
   fold policy into a single `passed` verdict, because the two callers ask
   different questions (see Gate Parity above, and the `enabled` hazard below):

   ```python
   @dataclass
   class ReadinessStatus:
       confidence: int
       outcome: int
       readiness_threshold: int
       outcome_threshold: int
       enabled: bool          # reported for callers to honor; NOT folded in below

       @property
       def meets_readiness(self) -> bool:
           """Mirrors manage-issue Phase 2.5 — readiness only."""
           return self.confidence >= self.readiness_threshold

       @property
       def meets_outcome(self) -> bool:
           return self.outcome >= self.outcome_threshold
   ```

   - `cmd_check_readiness()` returns `0 if (status.meets_readiness and
     status.meets_outcome) else 1` — **byte-identical to today, and it must keep
     ignoring `enabled`.**
   - The `ll-auto` pre-gate consults `status.enabled` and `meets_readiness` only.

   > **`enabled` hazard — do not fold it into a combined `passed` property.**
   > `cmd_check_readiness()` never reads `commands.confidence_gate.enabled`
   > today (`check_readiness.py:34-53`); it always compares. A `passed` that
   > short-circuits `True` when the gate is disabled would flip all three
   > `autodev.yaml` `check-readiness` call sites to always-pass on any project
   > that hasn't opted in — and `ConfidenceGateConfig.enabled` defaults to
   > **`False`** (`config/automation.py:147`). autodev would begin implementing
   > unscored issues. Keeping `enabled` a reported field rather than a verdict
   > input makes step 1's "exit codes unchanged" claim actually satisfiable.

2. **Gate before Phase 1** in `process_issue_inplace()`, immediately after the
   `_stamped_result` helper is defined and before the `Phase 1: Verifying issue`
   log line:

   ```python
   action = config.get_category_action(info.issue_type)
   status = readiness_status(config, info.issue_id)
   if (
       status is not None
       and status.enabled
       and not status.meets_readiness
       and not force_implement
       and not dry_run                      # mirrors the decision gate (:949)
       and action not in ("verify", "plan") # manage-issue skips 2.5 for these
   ):
       logger.warning(
           f"{info.issue_id}: below readiness threshold "
           f"(confidence {status.confidence} < {status.readiness_threshold})"
       )
       # Stable, greppable marker for FSM loops that implement via
       # `ll-auto --only` — mirrors LEARNING_GATE_BLOCKED
       # (issue_manager.py:991-997). Without it, a gate refusal is
       # indistinguishable from a genuine implementation failure.
       print(f"CONFIDENCE_GATE_BLOCKED {info.issue_id}", flush=True)
       return _stamped_result(
           success=False,
           duration=time.time() - issue_start_time,
           issue_id=info.issue_id,
           failure_reason=f"below_readiness_threshold ({status.confidence} < {status.readiness_threshold})",
       )
   ```

   Note `status.enabled` is checked here but *not* in the CLI — this is the
   deliberate asymmetry from step 1, and both sides need a test pinning it.

   The `dry_run` guard matches the two existing mid-function gates, which both
   check `not dry_run` (decision gate `issue_manager.py:949`, learning gate
   `:970`). Without it, `ll-auto --dry-run` would emit a fabricated failure
   result and a `CONFIDENCE_GATE_BLOCKED` marker instead of the
   `Would run: /ll:ready-issue ...` preview line, which is the whole point of
   the dry-run mode.

   **Outcome-status reporting is `failed`, deliberately.** `success=False` +
   `failure_reason` routes through `_process_issue`
   (`issue_manager.py:1765-1766, :1777-1788`) to
   `state_manager.mark_failed(id, reason)` and orchestration status `"failed"`.
   That is the intended channel — see "Outcome Channel" below — not an oversight
   to be "corrected" into the `was_blocked` skip path during implementation.

3. **Choose the remedy policy.** Two options, decide during refinement:

**Option A**: Skip-only — report and move on. Cheap, honest, leaves the
operator to run `/ll:confidence-check`.

> **Selected:** Option A — direct reuse of `process_issue_inplace()`'s
> established precondition-gate pattern (learning gate, blocked-issue check);
> Option B's reactive/bounded-retry logic has no precedent in this file and
> adds a full extra LLM pass on every sub-threshold issue.

**Option B**: Remediate (matches `autodev.yaml`) — on a sub-threshold
score, run `/ll:confidence-check <ID>`, re-read frontmatter, and proceed
if it now clears; skip if not. Bounded at one attempt per issue per run to
avoid a refine loop inside `ll-auto`.

Note `autodev.yaml` already demonstrates the remediate shape; reuse its
routing semantics rather than inventing new ones.

### Codebase Research Findings

   _Added by `/ll:refine-issue` — based on codebase analysis:_

   - **`autodev.yaml`'s remediate-then-recheck shape is FSM-only and marker-
     file-based, not a Python precedent.** `run_decide` → `mark_decide_ran` →
     `rerun_confidence_after_decide` → `recheck_after_decide`
     (`autodev.yaml:~599-674`, recurring at `~484-499`/`~1090-1130`) bounds
     the retry with a write-once marker file under `${context.run_dir}`
     (e.g. `autodev-decide-ran`), cleared per-issue at `dequeue_next` — not a
     counter variable. This is an FSM re-entrancy guard; a Python function
     call has no re-entrancy to guard against, so the marker mechanism itself
     doesn't transfer, only the "exactly one retry" bound it enforces.
   - **`process_issue_inplace()` already has a precedent for invoking a
     slash command other than `/ll:ready-issue`/`/ll:manage-issue`
     synchronously mid-function**: the existing decision gate
     (`issue_manager.py:950-970`) calls `/ll:decide-issue <id> --auto` via
     `run_claude_command`/`expand_skill`, the same machinery Phase 1/Phase 2
     use. That precedent does *not* re-check its own result — a non-zero
     return just logs a warning and falls through unconditionally to Phase 2,
     with no re-read of frontmatter and no bounded-retry guard.
   - **No local-boolean "ran once this call" convention exists yet in
     `issue_manager.py`.** The closest bookkeeping precedent is
     `skip_learning_gate: bool` (`issue_manager.py:631`, threaded from
     `AutoManager.__init__` at `:1332,1366,1720`) — a caller-supplied flag,
     not a self-set marker checked mid-function. Option B's "one bounded
     retry" would be the first such pattern in this file, not a repeat of an
     existing one.

4. **Thread `--force-implement`** so an operator can deliberately bypass: add an
   `ll-auto` flag that both skips this pre-gate and appends `--force-implement`
   to the Phase 2 `/ll:manage-issue` invocation, keeping the two gates
   consistent.

Do not solve this by filtering in `get_ready_issues()` — that function models
dependency readiness, and overloading it with confidence semantics would change
behavior for every other consumer of the dependency graph.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

If the *remediate* option (step 3) is chosen, `autodev.yaml`'s existing
one-shot mechanics are worth knowing before designing the Python equivalent:
the FSM never bounds a retry with a counter — it uses **write-once marker
files** instead. `mark_decide_ran` writes a marker so a re-entrant state exits
immediately if the remediation already ran once this cycle
(`autodev.yaml:502-517,628-637`); the marker is documented as cleared at
`dequeue_next` (per-issue, per-iteration scope). The remediation-then-recheck
shape is always the same two-state pair — run `/ll:confidence-check <id>`,
then a freshly-named recheck state that calls `check-readiness` again
(`autodev.yaml:639-674`, recurring at `:1572-1592`, `:1225-1236`). A Python
`process_issue_inplace()` equivalent doesn't need marker files (a local
boolean suffices within one function call), but the "exactly one retry,
enforced structurally rather than by a counter variable" convention is what
`autodev.yaml` actually does, in case the remedy policy is meant to mirror it
precisely rather than just approximate it.

### Decision Rationale

_Added by `/ll:decide-issue` — evidence-based selection:_

**Selected: Option A (Skip-only)**

`process_issue_inplace()` already implements this exact shape twice — the
learning-gate block (`issue_manager.py:975-1017`) and the blocked-issue check
(`issue_manager.py:913-923`) are both precondition-check → early-return via
`_stamped_result` → `failure_reason` string → optional stdout marker for FSM
routing. Option A is a third instance of an established, already-tested
convention; Option B's reactive re-check-and-conditionally-proceed logic, and
its local-boolean one-shot bound, have no precedent anywhere in this file —
the closest analog (`skip_learning_gate`) is caller-supplied, not self-set
mid-function. Option B also costs a full `/ll:confidence-check` LLM pass on
every sub-threshold issue, reintroducing part of the latency cost this bug
exists to eliminate.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| **A: Skip-only** | 3 | 3 | 3 | 2 | **11/12** |
| B: Remediate | 1 | 1 | 1 | 1 | 4/12 |

Key evidence:
- Learning-gate precedent (`issue_manager.py:975-1017`) and blocked-issue
  check (`issue_manager.py:913-923`) both match Option A's shape exactly.
- The existing `/ll:decide-issue` synchronous-invocation precedent
  (`issue_manager.py:950-970`) does **not** re-check its own result — Option
  B would diverge from, not extend, that precedent.
- `autodev.yaml`'s remediate-then-recheck shape is FSM-marker-file-bounded
  (`autodev.yaml:599-674`); no local-boolean equivalent exists in
  `issue_manager.py` today, so Option B would be a first-of-its-kind pattern
  in this file.

### Outcome Channel: report as `failed`, disambiguated by marker

_Decided during pre-implementation review (2026-08-02)._

`IssueProcessingResult` has four distinct outcome channels, and
`AutoManager._process_issue` (`issue_manager.py:1751-1788`) maps them to
different persistence:

| Channel | State effect | Orchestration status | Reason persisted where |
|---------|--------------|----------------------|------------------------|
| `was_closed` | `mark_completed` | `completed` | — |
| `was_blocked` | left pending, log only | `skipped` | DB row only |
| `plan_created` | left pending, log only | `skipped` | DB row only |
| `success=False` + `failure_reason` | `mark_failed(id, reason)` | `failed` | `state.failed_issues[id]` **and** DB row |

**Selected: the `failed` channel.** The operator priority here is *visibility
and easy manual retry*, and `failed` is the only channel that persists the
reason string where an operator would look for it —
`state.failed_issues["BUG-3002"] = "below_readiness_threshold (80 < 85)"`
(`state.py:203-214`). Critically, `mark_failed()` only records; it does **not**
bar the issue from later runs (`is_attempted()` reads a separate
`attempted_issues` set, `state.py:216-225`), so re-running after
`/ll:confidence-check` needs no state surgery.

Rejected alternatives:

- **`was_blocked` (the existing "skip" channel).** Semantically honest — the
  code comment at `:1753-1754` literally reads "Blocked issues are skipped, not
  failed" — but it writes nothing to `state.failed_issues`, so the reason
  survives only in the orchestration DB row and one log line. Strictly less
  visible, which is the opposite of the goal.
- **A new `was_skipped` field** → orchestration `skipped`. Cleanest semantics,
  same visibility loss as `was_blocked`, plus a new field on
  `IssueProcessingResult` and a new branch in the `_process_issue` mapping.
- **Write `status: deferred` + `deferred_reason: low_readiness` to the issue
  frontmatter** (autodev's route; `DEFERRAL_CODES.md:22`). Most durable and most
  visible, but it mutates the operator's issue file and changes how every other
  tool reads that issue, for a score that may be five points shy. Disproportionate.

The one real cost of `failed` — a gate refusal looks identical to a genuine
implementation failure in aggregate counts and in `ll-auto`'s non-zero
per-issue return — is addressed by the `CONFIDENCE_GATE_BLOCKED` stdout marker
(Proposed Solution step 2) plus the FSM routing in wiring step 9, rather than by
a new status field. This mirrors exactly how `LEARNING_GATE_BLOCKED` and
`IMPLEMENT_FAILED` already disambiguate two failures that share the `failed`
channel (`issue_manager.py:991-1015`).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — pre-Phase-1 gate in
  `process_issue_inplace()`; `--force-implement` plumbing through `AutoManager`
- `scripts/little_loops/cli/issues/check_readiness.py` — extract
  `ReadinessStatus` + `readiness_status()`; rewrite `cmd_check_readiness()` as a
  wrapper
- `scripts/little_loops/cli_args.py` — new `add_force_implement_arg()` helper,
  mirroring `add_skip_learning_gate_arg()` (`cli_args.py:214-220`) [Wiring pass:
  resolves the issue's original "wherever `AutoManager` flags are declared"
  placeholder to a concrete file]
- `scripts/little_loops/cli/auto.py` — register the new arg (`~line 55`,
  alongside `add_skip_learning_gate_arg(parser)`) and thread it into the
  `AutoManager(...)` constructor call (`~line 111`, add
  `force_implement=args.force_implement,`) [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — registers the
  `check-readiness` subcommand; must keep working after the refactor
- `scripts/little_loops/loops/autodev.yaml` — three `ll-issues check-readiness`
  call sites; CLI contract and exit codes must not change
- `scripts/little_loops/parallel/` — verify whether `ll-parallel` / `ll-sprint`
  reuse `process_issue_inplace()` and would inherit the new gate (they should,
  but confirm intent)
  - **Resolved by `/ll:refine-issue` (2026-08-02):** confirmed via grep — no
    file under `scripts/little_loops/parallel/` calls
    `process_issue_inplace()` directly. The only callers are
    `scripts/little_loops/issue_manager.py` itself,
    `scripts/little_loops/cli/sprint/run.py` (the two sites the wiring pass
    already flagged), and the FSM callers (`autodev.yaml`,
    `rn-remediate.yaml`, `lib/common.yaml`). `ll-parallel` does not inherit
    the new gate at all; `ll-sprint` inherits it only through
    `cli/sprint/run.py`'s two sites.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — two **direct, previously
  unlisted** call sites of `process_issue_inplace()` (`~line 75`, inside a
  SIGALRM-wrapped timeout helper; `~line 834`, sequential-retry path — its
  comment at `~849` explicitly parallels this issue). Neither is inside
  `scripts/little_loops/parallel/`, so it's outside the file the issue already
  flags for verification. `ll-sprint`'s argparser has **no**
  `--force-implement`-equivalent flag today (confirmed: no `confidence` /
  `force_implement` string in the file), so once the pre-Phase-1 gate lands,
  `ll-sprint` silently inherits skip-before-Phase-1 behavior with no bypass —
  a parity gap to flag during implementation even if fixing it is out of
  scope. Not a test-breakage risk: `scripts/tests/test_cli_sprint.py`
  (`~626-755`) mocks `process_issue_inplace` entirely, so it's insulated from
  the signature change.
- `scripts/little_loops/loops/rn-remediate.yaml` — the `implement` state
  (`~499-518`) runs `ll-auto --only "$ID" ...` and routes its exit via
  `check_learning_gate` (`~603-619`, `fragment: ll_auto_learning_gate_check`)
  → `check_impl_auth` (`~621-631`, `fragment: ll_auto_auth_check`) →
  `emit_implement_failed` (generic bucket). Nothing in this chain greps for a
  confidence-gate marker, so a sub-threshold skip from the new pre-Phase-1
  gate will land in the generic `IMPLEMENT_FAILED` bucket instead of getting
  distinct routing — the exact `LEARNING_GATE_BLOCKED`-style precedent this
  issue's own Codebase Research Findings section says to match is not
  actually wired here.
- `scripts/little_loops/loops/lib/common.yaml` — defines the
  `ll_auto_auth_check` (`~304-325`) and `ll_auto_learning_gate_check`
  (`~327-346`) fragments `rn-remediate.yaml` chains through; the latter's own
  docstring (`~338-341`) instructs pairing gate-check fragments *before* the
  auth check so a gate block isn't misattributed. If the remedy policy needs
  distinct routing (mirroring `autodev.yaml`'s three `check-readiness` call
  sites), a new `ll_auto_confidence_gate_check`-style fragment belongs here,
  grepping for a new marker string analogous to `LEARNING_GATE_BLOCKED`.
- `scripts/little_loops/loops/rn-implement.yaml` — one hop further out:
  `route_rem_learning_gate` (`~971-989`) and the summary tallying
  (`~1480-1535` `failure_tags`, `~1613-1633` `FAILURES` bucket) only see
  whatever `rn-remediate.yaml` emits. If `rn-remediate.yaml` doesn't tag the
  new outcome distinctly, this file's per-run `summary.json` will silently
  absorb sub-threshold skips into the generic `failed` count rather than a
  named bucket.

### Similar Patterns
- `scripts/little_loops/cli/issues/next_action.py` — already reads the same
  config block and emits `NEEDS_REFINE` for sub-threshold issues; a second
  independent copy of the threshold-resolution logic. Consider folding it onto
  the same helper.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`,
  `recursive-refine.yaml` — same gate expressed as inline Python in FSM actions

#### Threshold resolution: consolidate onto `BRConfig`, not a fourth raw-JSON read

_Added during pre-implementation review (2026-08-02)._

There are **three** raw-JSON readers of `commands.confidence_gate`, not two —
`check_readiness.py:34-42`, `next_action.py:37-44`, and `set_flags.py:223-231`
— each opening `.ll/ll-config.json` directly with the same try/except shape.

But a typed canonical accessor already exists and is the correct target:
`ConfidenceGateConfig` (`config/automation.py:144-159`), reached as
`config.commands.confidence_gate`. `seed_confidence_thresholds()`
(`cli/loop/_helpers.py:1366-1392`) already uses exactly this path to resolve the
same two values for FSM context, with a documented precedence chain. So the
earlier finding that "no shared helper exists today" is true only of the
raw-JSON copies — the typed path is what `readiness_status()` should read, and
the raw-JSON copies are what should be retired onto it.

**This is a behavior change, not a pure refactor, and needs its own AC.**
`BRConfig` applies `.ll/ll.local.md` frontmatter overrides; the three raw-JSON
readers bypass that merge entirely. Today an operator who sets
`commands.confidence_gate.readiness_threshold` in `ll.local.md` sees it honored
by FSM loops (via `seed_confidence_thresholds`) but silently ignored by
`ll-issues check-readiness` and `ll-issues next-action`. Consolidating fixes
that inconsistency — desirable, but it will change `check-readiness` exit codes
for any project using a local override, which is precisely the contract
`autodev.yaml` depends on. Land it deliberately with a test, or scope it out of
this issue explicitly rather than letting it ride along unnoticed.

#### SCOPED OUT — `readiness_status()` must keep the absence-sensitive raw-JSON read

_Decided during pre-implementation review (2026-08-02). This resolves the
"land it or scope it out" question above: **scoped out.**_

The consolidation is not merely risky, it is **incompatible with step 1's
"exit codes byte-identical" AC**, because the typed accessor cannot express
the distinction the current code depends on:

- `check_readiness.py:37-42` reads `cg.get("readiness_threshold",
  default_readiness)` — **absence-sensitive**. When the key is missing from
  `ll-config.json`, the `--readiness` / `--outcome` CLI args win.
- `ConfidenceGateConfig` is a dataclass with non-`None` defaults of `85` / `65`
  (`config/automation.py:146-148`), so `config.commands.confidence_gate.
  readiness_threshold` is *always* populated. There is no way to distinguish
  "absent from JSON" from "explicitly set to 85", so the CLI args become dead
  code.
- All three `autodev.yaml` call sites pass those CLI args from loop context
  (`autodev.yaml:493-495`, `:667-669`, `:1122-1124`), and the file's own
  comments (`:1537-1540`, `:1796-1798`) document the current config-wins-when-
  set precedence as load-bearing.

Net effect if consolidated: on any project whose `ll-config.json` omits the
`confidence_gate` keys — the common case, since the block is opt-in and
`enabled` defaults to `False` — autodev's context thresholds would silently
stop applying and `check-readiness` exit codes would change. That is precisely
the regression this issue's own Gate Parity discipline forbids.

**Therefore:** `readiness_status()` keeps the existing raw-JSON,
absence-sensitive resolution verbatim (moved, not rewritten). It takes
`config` only for `config.project_root` and issue resolution. Retiring
`next_action.py` / `set_flags.py` onto the shared helper, and the separate
question of honoring `ll.local.md` overrides, are **out of scope for
BUG-3004** and should be captured as a follow-up ENH if wanted — they are a
deliberate behavior change to a contract `autodev.yaml` depends on and deserve
their own issue, not a ride-along.

Consequence for the Tests section: the "Local-override consolidation" AC below
is **not applicable to this issue** and should not be written.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Config-read duplication is confirmed byte-for-byte, not just similar.**
  `check_readiness.py:34-42` and `next_action.py:37-44` both open
  `.ll/ll-config.json`, read `commands.confidence_gate.{readiness_threshold,
  outcome_threshold}`, and fall back to CLI/default args on any exception with
  the identical try/except shape. No shared helper exists today — each CLI
  subcommand inlines its own copy. This strengthens the "fold onto the same
  helper" note above from a suggestion into a confirmed duplication.
- **This codebase's convention for CLI-thin extraction has no existing
  precedent to match against.** `check_readiness.py`, `check_flag.py`,
  `check_decidable.py`, `check_open_questions.py` are already uniformly thin
  (`cmd_check_*`: parse → call one library function → print/exit), but none of
  them delegates to a separately-named non-CLI-prefixed helper module. The
  `readiness_status()` extraction this issue proposes would be a new pattern
  within `cli/issues/`, not a repeat of one — worth knowing so the extraction
  isn't assumed to have a template to copy.
- **The closest existing bypass-flag precedent is `--skip-learning-gate`, not
  a force-implement flag, but it demonstrates the full threading shape a
  `--force-implement` flag would need to replicate:** parser helper
  `add_skip_learning_gate_arg()` (`cli_args.py:214-220`, `action="store_true"`)
  → registered and read in `cmd_auto` (`cli/auto.py:55`, `:111`) → threaded as
  a plain kwarg through `process_issue_inplace(..., skip_learning_gate: bool =
  False, ...)` (`issue_manager.py:631`) and `AutoManager.__init__`
  (`issue_manager.py:1332,1366,1720`) → for FSM/loop parity, re-exposed as an
  empty-string-default context var and conditionally appended to a
  shell-built command string (`autodev.yaml:822-826`,
  `rn-implement.yaml:549`, `rn-remediate.yaml:507-508`) — the same four-place
  pattern recurs identically across all four loop YAMLs.
- **`IssueProcessingResult` has no distinct "skipped" status field**
  (`issue_manager.py:564-579`: only `success, was_closed, was_blocked,
  failure_reason, corrections, ...`). Two different existing precedents exist
  for reporting a precondition failure, and they disagree:
  - The learning-gate block (`issue_manager.py:975-1017`) reports a gate
    failure as an early-return result: `success=False` +
    `failure_reason="Learning gate blocked: ..."` plus a stdout marker token
    (`LEARNING_GATE_BLOCKED <id>`) printed for FSM loops to grep on. This
    matches the shape this issue's Proposed Solution step 2 already proposes
    for the confidence gate.
  - A true bypass (`skip=True`) does the opposite: it just logs and falls
    through to Phase 2 without constructing an early-return result at all
    (`issue_manager.py:983-984`).
  These two precedents disagree on whether a bypass is a distinct code path
  or a no-op flag check — the implementer should pick knowingly rather than
  averaging them.

### Codebase Research Findings (2026-08-02 re-refine)

_Added by `/ll:refine-issue` — the previous pass's Integration Map was flagged
stale because `autodev.yaml` changed after that pass; re-verified below:_

- **All three `ll-issues check-readiness` call sites in `autodev.yaml` are
  still current** at `check_passed` (~484-500), `recheck_after_decide`
  (~658-674), and `recheck_scores` (~1090-1130) — state names, line ranges,
  and `on_yes`/`on_no`/`on_error` routing are unchanged from the prior pass.
  One content change since then: `recheck_scores`'s check (~1122-1125) is now
  hard-`&&`-gated with a Program Design check (from BUG-3002/BUG-3003 work),
  not a bare `check-readiness` call. If the remedy policy (step 3) mirrors
  `recheck_scores`'s routing shape specifically, mirror the compound-gate
  form, not the simpler `check_passed`/`recheck_after_decide` form.
- **The "no existing CLI-thin-extraction precedent" conclusion is now
  confirmed against the full `cli/issues/check_*` family**, not just
  `check_readiness.py`/`next_action.py`: `check_flag.py`, `check_decidable.py`,
  and `check_open_questions.py` were surveyed and each keeps its pass/fail
  comparison inline in the `cmd_check_*` function, delegating only generic
  parsing/counting helpers (`parse_frontmatter`,
  `locate_enumerable_options`, `count_open_questions_in_sections`) — never the
  decision itself. `readiness_status()` would be the first `cmd_check_*` in
  this codebase to delegate its comparison to a separately-named helper.
- **`process_issue_inplace()` has exactly four callers codebase-wide** (grep-
  confirmed): `issue_manager.py` itself, `cli/sprint/run.py` (2 sites, already
  flagged), and the FSM layer (`autodev.yaml`, `rn-remediate.yaml`,
  `lib/common.yaml` reference it via loop state action text, not a Python
  import). No other Python module calls it.

### Tests
- `scripts/tests/` — new test: sub-threshold issue causes `ll-auto` to skip
  before Phase 1 (assert `/ll:ready-issue` is never invoked)
- New test: `--force-implement` bypasses the pre-gate *and* reaches Phase 2 with
  the flag appended
- New test: `cmd_check_readiness` exit codes unchanged after the refactor
  (protects the three `autodev.yaml` call sites)

_Added during pre-implementation review (2026-08-02) — these pin the four
decisions above, each of which is silently reversible without coverage:_

- **Gate disabled → no skip.** With `commands.confidence_gate.enabled: false`
  (the `ConfidenceGateConfig` default, `config/automation.py:147`) and a
  `confidence_score` of 0 or absent, `process_issue_inplace()` must still run
  Phase 1. This is the test that protects every pre-existing
  `test_issue_manager.py` fixture from the new gate — the breakage analysis in
  the wiring notes above turns entirely on this behavior.
- **`enabled` asymmetry.** With the gate disabled and a sub-threshold score,
  `cmd_check_readiness` must still exit **1** while the `ll-auto` pre-gate does
  **not** fire. A single combined `passed` property makes this test impossible
  to satisfy, so it fails loudly if someone re-folds `enabled` into the verdict.
- **Readiness/outcome parity.** An issue at `confidence_score: 90`,
  `outcome_confidence: 60`, thresholds 85/65, gate enabled → pre-gate must
  **not** fire (matching `manage-issue`), while `cmd_check_readiness` on the
  same issue must still exit 1. This is the Gate Parity decision in executable
  form; without it, a later "consistency" cleanup silently re-introduces the
  strictness bug.
- **Marker emitted on the gate path.** Assert stdout contains
  `CONFIDENCE_GATE_BLOCKED <id>` when the pre-gate fires, and that it does
  *not* contain `LEARNING_GATE_BLOCKED` or `IMPLEMENT_FAILED` — the FSM routing
  in wiring step 9 depends on the distinction.
- **Failed-channel semantics.** After a pre-gate skip, assert
  `state.failed_issues[id]` contains the `below_readiness_threshold (N < M)`
  string and that `is_attempted(id)` is `False`, pinning the "visible and
  retryable" property the Outcome Channel decision selected for.
- ~~**Local-override consolidation**~~ — **not applicable**: the `BRConfig`
  consolidation is scoped out (see "SCOPED OUT" under Similar Patterns). Do not
  write this test; write the CLI-arg-fallback test below instead.

_Added during pre-implementation review (2026-08-02), second pass:_

- **CLI-arg fallback preserved.** With `commands.confidence_gate` **absent**
  from `ll-config.json`, `ll-issues check-readiness <ID> --readiness 50
  --outcome 50` must honor the CLI values (exit 0 for an issue at 60/60), and
  with `readiness_threshold` **present** the config value must win over the CLI
  arg. This is the executable form of the SCOPED OUT decision and the direct
  guard on `autodev.yaml:493-495, 667-669, 1122-1124`. It fails loudly if
  someone re-sources thresholds from `ConfidenceGateConfig`.
- **Action parity — `verify` / `plan` do not gate.** With the gate enabled, a
  sub-threshold score, and a category whose configured `action` is `plan` (or
  `verify`), `process_issue_inplace()` must still run Phase 1 and reach Phase 2.
  Pins the second Gate Parity decision; without it a "simplification" drops the
  action check and silently skips work `manage-issue` would have done.
- **`--dry-run` does not gate.** With the gate enabled and a sub-threshold
  score, `process_issue_inplace(..., dry_run=True)` must emit the
  `Would run: /ll:ready-issue` path and must **not** print
  `CONFIDENCE_GATE_BLOCKED` or return `success=False`.

_Wiring pass added by `/ll:wire-issue`:_
- **No existing test file covers `check_readiness.py` / `cmd_check_readiness`
  at all** — confirmed via grep, no `scripts/tests/test_check_readiness.py`
  and no unit test asserting its exit codes directly. The "exit codes
  unchanged after refactor" AC has zero regression coverage today; the new
  test must establish the baseline, not just protect one.
- **Breakage risk, not just a gap**: `scripts/tests/test_issue_manager.py`
  has dozens of direct, unmocked `process_issue_inplace(sample_issue, ...)`
  calls across `TestReadyIssueErrorHandling`, `TestCorrectionsAndConcerns`,
  `TestClassifyFailureIntegration`, `TestCloseVerdictHandling`,
  `TestFailureClassification`, `TestFallbackVerification`,
  `TestEarlyCompletionGuard`, `TestDecisionNeededGate`,
  `TestDequeueTimeBaseStateStamp`, and `TestAutoManagerLearningGate` (class at
  `~4338`, including `test_skip_learning_gate_bypasses_gate_and_runs_implement`
  at `~4515`). Their `sample_issue`/`_make_issue()` fixtures write frontmatter
  with **no `confidence_score`** field. Since `check_readiness.py` treats a
  missing score as `0` (`int(fm.get("confidence_score") or 0)`), the new
  pre-Phase-1 gate would evaluate `0 < 85` and short-circuit every one of
  these tests before they reach the code paths they're meant to exercise —
  *unless* their `mock_config` fixtures leave `commands.confidence_gate`
  disabled (several do, via `config-schema.json`'s `enabled: false` default,
  which makes `ReadinessStatus.passed` short-circuit `True`) or the fixtures
  are updated to include a passing `confidence_score`/`outcome_confidence`.
  Verify per-class which `mock_config` fixtures actually enable the gate
  before assuming breakage; where it's enabled, follow `test_next_action.py`'s
  `_make_issue()` (`~19-53`), which already supports optional
  `confidence_score`/`outcome_confidence` kwargs — the established pattern to
  reuse rather than a new fixture shape.
- `test_skip_learning_gate_bypasses_gate_and_runs_implement`
  (`test_issue_manager.py:4515`) is the closest existing template for the new
  `--force-implement` bypass test: it calls `process_issue_inplace(issue,
  config, logger, skip_learning_gate=True)` directly and asserts the gated
  phase runs; the new test should mirror this shape with
  `force_implement=True`.
- `scripts/tests/test_next_action.py` (`test_reads_readiness_threshold_from_config`
  and neighbors, `~407-535`) duplicate the same `commands.confidence_gate`
  config-read logic this issue's Proposed Solution step 1 wants folded onto
  `readiness_status()`. If `next_action.py` is repointed at the shared
  helper, these tests need to keep passing unchanged (same config shape) —
  no rewrite expected, but worth a explicit pass/fail check post-refactor.
- No dedicated test exists asserting `cli/auto.py`'s `main()` maps
  `args.force_implement` → `AutoManager(force_implement=...)` end-to-end
  (the `--skip-learning-gate` precedent has the same gap) — new coverage
  should close this rather than only testing `process_issue_inplace()` in
  isolation.

### Documentation
- `docs/reference/CLI.md` — `ll-auto` flag table
- `docs/reference/DEFERRAL_CODES.md` — if the remedy policy (step 3) skips a
  sub-threshold issue by setting the issue's own status to `deferred` (mirroring
  `autodev.yaml`'s `mark_gate_blocked`/`recheck_after_size_review` states),
  reuse the existing `low_readiness` code (`DEFERRAL_CODES.md:22`) rather than
  minting a new one — it already means exactly this
  ("Readiness score below threshold with no applicable pre-deferral remedy").
  `gate_blocked` (`:20`) is explicitly documented as a *different* condition
  ("distinct from a readiness-score deferral") and should not be reused here.
  This only applies if the remedy writes issue-level `deferred_reason`
  frontmatter; `IssueProcessingResult.failure_reason` (the run-level signal
  this issue's Proposed Solution step 2 already specifies) is a separate,
  unrelated string and needs no doc entry.
- `.claude/CLAUDE.md` — no change expected

### Configuration
- `.ll/ll-config.json` / `scripts/little_loops/config-schema.json` — no new keys;
  reuses `commands.confidence_gate`

## Program Design

### Types

- `ReadinessStatus.confidence: int`
- `ReadinessStatus.outcome: int`
- `ReadinessStatus.readiness_threshold: int`
- `ReadinessStatus.outcome_threshold: int`
- `ReadinessStatus.enabled: bool` (reported only — never folded into a verdict;
  see the `enabled` hazard in Proposed Solution step 1)
- `ReadinessStatus.meets_readiness: bool` (property — mirrors `manage-issue`
  Phase 2.5: `confidence >= readiness_threshold`)
- `ReadinessStatus.meets_outcome: bool` (property — `outcome >= outcome_threshold`;
  used by the CLI only, never by the `ll-auto` pre-gate)

There is deliberately **no** combined `passed` property. The two callers ask
different questions and a single verdict would force one of them to be wrong.

### Constants

- `CONFIDENCE_GATE_BLOCKED` — stdout marker token, emitted as
  `f"CONFIDENCE_GATE_BLOCKED {issue_id}"`. Must match the string the
  `lib/common.yaml` fragment greps for (wiring step 9). Sibling of the existing
  `LEARNING_GATE_BLOCKED` / `IMPLEMENT_FAILED` tokens
  (`issue_manager.py:991, :1006`).

### Signatures

- `readiness_status(config: BRConfig, issue_id: str, *, default_readiness: int = 85, default_outcome: int = 65) -> ReadinessStatus | None`
  (`None` when the issue cannot be resolved — the pre-gate treats `None` as
  "do not gate" and falls through to Phase 1, since an unresolvable ID is a
  different failure that Phase 1 already reports).
  `config` supplies `project_root` and issue resolution only. Threshold
  resolution stays the **absence-sensitive raw-JSON read** moved verbatim from
  `check_readiness.py:37-42` — `default_readiness`/`default_outcome` must still
  win when the `commands.confidence_gate` keys are absent. Do **not** re-source
  these from `config.commands.confidence_gate`; see "SCOPED OUT" above.
  `status.enabled` is the one field read from the typed accessor (or from the
  same raw dict), since the CLI never consults it and the pre-gate always does.
- `cmd_check_readiness(config: BRConfig, args: argparse.Namespace) -> int`
  (unchanged signature; reimplemented over `readiness_status`; still requires
  **both** thresholds and still ignores `enabled`)
- `process_issue_inplace(..., force_implement: bool = False) -> IssueProcessingResult`

### Call Path

`AutoManager._process_issue` -> `process_issue_inplace` -> `readiness_status` ->
`parse_frontmatter` / `_resolve_issue_id`, then either `_stamped_result` (skip)
or the existing Phase 1 `run_ready_issue_with_retry`.

CLI path preserved: `ll-issues check-readiness` -> `cmd_check_readiness` ->
`readiness_status`.

## Implementation Steps

1. Extract `ReadinessStatus` + `readiness_status()` in `check_readiness.py` with
   **separate `meets_readiness` / `meets_outcome` properties and no combined
   `passed`**; reimplement `cmd_check_readiness()` over it, keeping both-threshold
   semantics and continuing to ignore `enabled`. **Move the existing
   absence-sensitive raw-JSON threshold read verbatim — do not re-source it from
   `config.commands.confidence_gate`** (see "SCOPED OUT"); the
   `--readiness`/`--outcome` CLI fallback must survive. Confirm exit codes are
   byte-identical for the `autodev.yaml` call sites.
2. Add the pre-Phase-1 gate to `process_issue_inplace()` — gated on
   `status.enabled and not status.meets_readiness` (readiness only, per Gate
   Parity), **and additionally suppressed when `dry_run` is set or the resolved
   category `action` is `verify`/`plan`** (per the second Gate Parity section) —
   with an explicit `below_readiness_threshold (N < M)` failure reason
   and a `CONFIDENCE_GATE_BLOCKED <id>` stdout marker. Hoist the
   `config.get_category_action(...)` call from `:1018` so both sites share it.
3. ~~Decide the remedy policy~~ — **resolved**: Option A (skip-only), reported
   through the `failed` channel per the Outcome Channel decision. No
   `/ll:confidence-check` invocation from `ll-auto`.
4. Thread a `--force-implement` bypass through `ll-auto` into both the pre-gate
   and the Phase 2 `/ll:manage-issue` command string.
5. Add tests covering skip-before-Phase-1, force bypass, and CLI exit-code
   stability; run `python -m pytest scripts/tests/`.
6. Update `docs/reference/CLI.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

7. Audit `test_issue_manager.py`'s `sample_issue`/`_make_issue()` fixtures
   (used across `TestReadyIssueErrorHandling`, `TestCloseVerdictHandling`,
   `TestFallbackVerification`, `TestAutoManagerLearningGate`, and others) for
   whether their `mock_config` enables `commands.confidence_gate`; add
   passing `confidence_score`/`outcome_confidence` frontmatter wherever the
   gate is enabled, so the new pre-Phase-1 check doesn't silently short-
   circuit tests that predate it.
8. Decide whether `scripts/little_loops/cli/sprint/run.py`'s two direct
   `process_issue_inplace()` call sites (`~75`, `~834`) should also gain a
   `--force-implement`-equivalent bypass for parity with `ll-auto`, or
   explicitly document that `ll-sprint` inherits the gate with no bypass for
   now.
9. If the remedy policy (step 3) requires distinct failure routing (matching
   the `LEARNING_GATE_BLOCKED` precedent), add an
   `ll_auto_confidence_gate_check`-style fragment to
   `scripts/little_loops/loops/lib/common.yaml`, paired before
   `ll_auto_auth_check`, and wire it into `rn-remediate.yaml`'s `implement`
   state chain so a sub-threshold skip isn't misclassified as generic
   `IMPLEMENT_FAILED`.

## Impact

- **Priority**: P2 - Wastes a full LLM pass per affected issue on every
  unattended run and produces a misleading failure signature that misdirects
  diagnosis. Not P1: no data loss or corruption, and the tamper guard correctly
  prevents a false completion.
- **Effort**: Small/Medium - The comparison logic already exists and is tested
  via the CLI; the work is one extraction, one call site, one flag, and tests.
  The remedy-policy decision (step 3) is the only open design question.
- **Risk**: Low/Medium - Low for the extraction (CLI contract preserved by
  test). Medium for the gate itself: it changes which issues `ll-auto` attempts,
  so a backlog with many unscored or sub-threshold issues will suddenly skip work
  it previously attempted-and-failed. That is the intended behavior, but it will
  look like a regression in run counts and should be called out in the changelog.
  Mitigating factor: `commands.confidence_gate.enabled` defaults to **`False`**
  (`config/automation.py:147`), so the new gate is inert for any project that
  hasn't opted in — the blast radius is opted-in projects only.
- **Accepted behavior loss: sub-threshold issues can no longer be auto-closed.**
  Today a sub-threshold issue that is stale, invalid, or already implemented
  still reaches `/ll:ready-issue`, which can return a CLOSE verdict and route
  through `was_closed=True` → `mark_completed` (`issue_manager.py:895-911`).
  After this change it never gets that far: it fails with
  `below_readiness_threshold` on every subsequent run, and no automated path
  ever resolves it — the operator must run `/ll:confidence-check` (or
  `--force-implement`) to unstick it. This is an accepted consequence of Option
  A, not an oversight, but it is a genuine regression in one dimension and the
  changelog entry must say so alongside the run-count change.
- **Breaking Change**: No — but the behavioral change is **not** limited to
  `ll-auto`. `scripts/little_loops/cli/sprint/run.py` calls
  `process_issue_inplace()` at two sites (`~75`, `~834`), so `ll-sprint`
  inherits the pre-Phase-1 gate with no bypass flag of its own (see wiring
  step 8). The changelog entry must name both runners.

## Related Key Documentation

| Document | Relevance | Why |
|----------|-----------|-----|
| `docs/reference/API.md` | High | Documents `little_loops.issue_manager` and the `cli.issues` modules being changed; the new `readiness_status()` helper needs an entry |
| `docs/reference/CLI.md` | High | `ll-auto` flag table (new bypass flag) and the `ll-issues check-readiness` contract that must stay stable |
| `.claude/CLAUDE.md` | Medium | Testing & CI policy — the new gate must be covered by `python -m pytest scripts/tests/`, not a hosted runner |

## Labels

`bug`, `captured`, `ll-auto`, `confidence-gate`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02 (re-run after `/ll:decide-issue`)_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 66/100 → PASSES (config outcome_threshold: 65)

`/ll:decide-issue` resolved the remedy-policy ambiguity that drove the prior
run's below-threshold outcome score (Option A selected, `decision_needed:
false`, rationale table recorded above). Remaining minor residual risk —
`check_readiness.py` has no existing test coverage today, and `ll-sprint`'s
bypass parity (wiring step 8) is an explicit, documented, non-blocking
decision left to implementation — is reflected in the Test Coverage and
Complexity sub-scores but does not clear the outcome-risk-factor reporting
threshold.

## Pre-Implementation Review Notes

_Added 2026-08-02 (manual review before implementation). Four design defects in
the Proposed Solution were found and resolved; each is now recorded above with
its rationale and a pinning test._

1. **Gate parity** — the pre-gate would have been stricter than the gate it
   predicts (`check_readiness` requires both thresholds; `manage-issue` Phase 2.5
   requires readiness only). Resolved: match `manage-issue` exactly. See "Gate
   Parity".
2. **`enabled` short-circuit** — folding `enabled` into a combined `passed`
   property would have flipped all three `autodev.yaml` `check-readiness` call
   sites to always-pass on projects that haven't opted in (`enabled` defaults to
   `False`). Resolved: `enabled` is reported, never a verdict input. See the
   hazard note in Proposed Solution step 1.
3. **Outcome channel** — `success=False` + `failure_reason` marks the issue
   *failed*, not *skipped*, which the Expected Behavior text didn't reflect.
   Resolved deliberately in favor of `failed` (best visibility, and
   `mark_failed` doesn't block retry). See "Outcome Channel".
4. **Missing marker** — step 2 returned without printing a token, while wiring
   step 9 wires an FSM fragment that greps for one. Resolved: literal
   `CONFIDENCE_GATE_BLOCKED` named in Program Design → Constants.

Also corrected: a third raw-JSON threshold reader (`set_flags.py`) and the
existing typed accessor (`config.commands.confidence_gate`) were missing from
the consolidation analysis; the Impact section wrongly scoped the behavioral
change to `ll-auto` alone when `ll-sprint` inherits it too.

### Second review pass (2026-08-02)

Five further defects found and resolved above:

5. **`BRConfig` consolidation would have broken the exit-code AC it sits next
   to.** `ConfidenceGateConfig`'s non-`None` defaults make the current
   absence-sensitive read inexpressible, killing the `--readiness`/`--outcome`
   CLI fallback all three `autodev.yaml` call sites rely on. Resolved: the
   consolidation is **scoped out** of BUG-3004; `readiness_status()` moves the
   raw-JSON read verbatim. New AC: "CLI-arg fallback preserved."
6. **Second gate-parity hole — `verify`/`plan` actions.** `manage-issue` Phase
   2.5 is skipped for those actions (`SKILL.md:181`), and `action` is an
   arbitrary operator-configured string (`config/core.py:485-496`), so an
   unconditional pre-gate would skip work the gate would never have blocked.
   Resolved: pre-gate short-circuits on `action in ("verify", "plan")`. New AC.
7. **`dry_run` unhandled.** The step-2 snippet lacked the `not dry_run` guard
   both sibling gates carry (`:949`, `:970`), so `--dry-run` would have emitted
   a fabricated failure and a spurious marker. Resolved: guard added. New AC.
8. **Accepted behavior loss made explicit** — skipping before Phase 1 forfeits
   `/ll:ready-issue`'s CLOSE path for sub-threshold issues, which now have no
   automated resolution route. Recorded in Impact; must appear in the changelog.
9. **Frontmatter scores contradicted the body** (`100`/`71` in frontmatter vs
   the documented `96`/`66` from the 20:22 `/ll:confidence-check` run, matching
   no logged run). Resolved: frontmatter reset to the documented `96`/`66`.

**Scores not re-run.** `confidence_score: 96` / `outcome_confidence: 66` predate
both review passes. The design has now changed materially twice (nine resolved
defects, one new constant, one scoped-out refactor, nine test ACs) — re-run
`/ll:confidence-check BUG-3004` before implementing if the gate is being
enforced on this issue itself.

## Session Log
- `/ll:manage-issue` - 2026-08-02T21:18:11 - `d5820802-7cf9-4ad0-bdea-8c14e2282441.jsonl`
- `/ll:ready-issue` - 2026-08-02T20:44:41 - `a8bb94f2-a430-4d7b-a6ed-68db16f58c14.jsonl`
- `/ll:confidence-check` - 2026-08-02T20:40:27 - `3a335d2c-6a4c-4144-a579-513545967cf2.jsonl`
- `/ll:confidence-check` - 2026-08-02T20:22:09 - `2a315922-1352-4ff5-a67d-ada57eca27ce.jsonl`
- `/ll:confidence-check` - 2026-08-02T20:06:29 - `4124e8ee-9f3a-4499-b26f-15aa9a2bb6f8.jsonl`
- `/ll:decide-issue` - 2026-08-02T19:55:29 - `0fd6f4d2-2c1d-46cc-8247-507c80435ade.jsonl`
- `/ll:refine-issue` - 2026-08-02T19:52:54 - `0fd6f4d2-2c1d-46cc-8247-507c80435ade.jsonl`
- `/ll:confidence-check` - 2026-08-02T19:48:49 - `0d449d14-ca2c-4891-b6a0-800c9d7c16e9.jsonl`
- `/ll:refine-issue` - 2026-08-02T19:43:32 - `1911b6e3-deb9-402f-a2b8-ed88f18f9129.jsonl`
- `/ll:wire-issue` - 2026-08-02T19:14:56 - `c2ddc2b8-a949-46f6-8466-7e925f3a2db0.jsonl`
- `/ll:refine-issue` - 2026-08-02T19:06:55 - `c2ddc2b8-a949-46f6-8466-7e925f3a2db0.jsonl`
- `/ll:capture-issue` - 2026-08-02T19:02:30 - `97be14aa-df1e-4353-ae1f-24a9a6e1da2f.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P2
