# Harness Optimization Guide

A **harness-optimizer loop** (a "meta-loop") iteratively rewrites a harness *artifact* —
a skill file, a command, an agent definition, a loop YAML, or `.claude/CLAUDE.md` itself —
proposing one edit at a time, scoring the result against a benchmark, and keeping the
change only when the score improves.

> **Not to be confused with harnessing a *skill*.** This guide is about optimizing the
> *harness itself*. If you want to wrap a skill in a quality pipeline (run it, gate the
> output, advance to the next item), that is a different pattern — see
> [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md). The quick test: if the
> thing being *changed* each iteration is your prompt/skill/config, you are optimizing a
> harness (this guide). If the thing being changed is your *project's code or issues* and
> the harness stays fixed, you are harnessing a skill (the other guide).

This pattern is powerful and dangerous in equal measure: a careless optimizer makes
output *worse* roughly half the time and cannot tell that it did. The design rules below
exist to make harness optimization safe — see [Why It Needs Guardrails](#why-it-needs-guardrails).

---

## Table of Contents

- [What Is Harness Optimization?](#what-is-harness-optimization)
- [Why It Needs Guardrails](#why-it-needs-guardrails)
- [The Design Rules (MR-1…MR-10)](#the-design-rules-mr-1mr-10)
- [The Optimizer Error Taxonomy](#the-optimizer-error-taxonomy)
- [The Canonical Shape](#the-canonical-shape)
- [Creating One](#creating-one)
- [Validating and Measuring](#validating-and-measuring)
- [Planning Loop Guards](#planning-loop-guards)
- [See Also](#see-also)

---

## What Is Harness Optimization?

In the harness-optimization literature, a harness is the software layer around the LLM
"brain" that manages its workflow, context, and external interactions. It decomposes into
four mutable components:

| Component | In little-loops terms |
|-----------|-----------------------|
| `prompt` | The instruction text in a skill, command, or `CLAUDE.md` |
| `tool` | The tools/commands a skill or agent is allowed to call |
| `memory` | Accumulated context, examples, scratch notes |
| `workflow` | The state machine / ordering of steps (e.g. a loop YAML) |

A harness-optimizer loop is an **outer loop** that updates one of these components on a
**target** (the inner harness) based on how the target performs. Each iteration: look at
what is failing, change one component, re-measure, keep or discard.

**Reach for it when** you want to systematically improve a skill, command, agent, loop
YAML, or `CLAUDE.md` against a measurable benchmark — not for one-off edits, and not for
running a skill over a batch of work items (that is the [skill-harness](AUTOMATIC_HARNESSING_GUIDE.md)
pattern).

---

## Why It Needs Guardrails

The rules in this guide are not stylistic preferences. They follow from a few hard facts
about how optimizers actually behave step-to-step, not just at the end:

- **Nearly half of an optimizer's edits make output worse.** → *You must measure each
  change and be able to revert it.*
- **Intermediate mistakes are mostly *not* self-correcting** — a bad edit tends to persist
  to the final harness rather than wash out. → *External measurement, not the optimizer's
  own say-so, must decide what survives.*
- **An optimizer cannot reliably tell whether its own edit helped or hurt** — its
  self-assessment is close to a coin flip. → *An LLM self-grade on a harness edit is worth
  little; pair it with a non-LLM signal.* This is exactly MR-1.
- **The bottleneck is *diagnosis* — knowing which component to act on — not the edit
  itself.** Telling the optimizer where the flaw is sharply lifts its fix-rate. →
  *Diagnose first; spend the first step identifying the highest-priority component.*
- **A good agent harness is not necessarily a good optimizer harness.** → *Don't assume
  your strongest skill will also be your strongest optimizer; validate it.*

The throughline: harness optimization is driven far more by trial-and-error than by
informed judgment, and end-result-only evaluation hides this. The guardrails turn
trial-and-error into *safe* trial-and-error.

---

## The Design Rules (MR-1…MR-10)

`ll-loop validate` enforces these rules. [`.claude/CLAUDE.md` § Loop Authoring](../../.claude/CLAUDE.md)
carries the compact lookup table for quick in-session reference; **this section is the rationale
it points to** — the "why" behind each row, kept here so `CLAUDE.md` stays lean. Each rule can be
suppressed with a top-level flag when you have a justified reason.

| Rule | What it requires | Why | Severity | Suppress with |
|------|------------------|-----|----------|---------------|
| **MR-1** | Every `check_semantic` / `llm_structured` state pairs with ≥1 non-LLM evaluator (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `score_stall`, `mcp_result`) | Self-grades are unreliable (ENH-1665) | **ERROR** | `meta_self_eval_ok: true` |
| **MR-2** | A meta-loop's captured baseline value must be referenced by a later evaluator (measure→propose→apply→re-measure spine) | Without a baseline comparison, the gate cannot tell whether an edit helped or hurt | WARNING | `meta_self_eval_ok: true` |
| **MR-3** | Intermediate artifacts write under `${context.run_dir}/`, not bare `.loops/tmp/` | Concurrency safety — shared `.loops/tmp/` corrupts state across concurrent runs (`.issues/`, `.loops/diagnostics/`, `thoughts/` are exempt) | WARNING | `shared_state_ok: true` |
| **MR-4** | An LLM-judged state with `on_yes` must also route `on_no`/`on_partial` (or `next:`/full `route:`) — no silent dead-end on a non-yes verdict | Half of verdicts are adverse (ENH-1917) | WARNING | `partial_route_ok: true` |
| **MR-5** | A harness loop that writes artifacts in a generate→evaluate cycle must snapshot per-iteration (`artifact_versioning: true`), not overwrite a flat path | Errors persist — keep the trajectory (ENH-1957) | WARNING | `artifact_versioning_ok: true` |
| **MR-6** | A meta-loop must not have a `shell` state that writes to the same path as an LLM-generator state (`prompt`/`slash_command` with `yaml_state_editor` or `replace_action` markers) | Hand-patching creates output that diverges from the generator on the next run; fix the generator instead (ENH-2079) | WARNING | `generator_fix_ok: true` |
| **MR-7** | No FSM action string may contain an unescaped `${namespace.path:-default}` (bash `:-` default syntax) — the interpolation engine crashes on this form at runtime | Use `${ns.path:default=value}` (engine-native) or `$${VAR:-value}` (shell-escaped) instead (ENH-2348) | **ERROR** | `bash_default_ok: true` |
| **MR-8** | A `check_semantic`/`llm_structured` state whose `evaluate.prompt` omits evidence-contract keywords (`verbatim`, `quote`, `evidence`) may return verdicts without citing output text, defaulting to optimism (SHOR Table 1: 33–55% accuracy) | Require the LLM to quote specific output text; absent evidence is coerced to `"no"` at the parsing layer (ENH-2342). States with no `evaluate.prompt` (using `DEFAULT_LLM_PROMPT`) are exempt — the contract is injected automatically | WARNING | `evidence_contract_ok: true` |
| **MR-9** | A shell action string contains `$$(` or `$$VAR` — over-escaped bash. The FSM interpolator only rewrites `$${...}` → `${...}`; bare `$(...)` / `$VAR` doubled with `$$` expand to the runner's PID at runtime, silently corrupting every downstream `${captured.*}` reference | Use single `$` for command substitution and variables; reserve `$$` exclusively for the `$${VAR}` brace form that collides with `${ns.path}` interpolation | **ERROR** | `shell_pid_ok: true` |
| **MR-10** | A `shell` state whose inline Python calls `json.load`/`json.loads`, catches `JSONDecodeError`/`ValueError`/bare `Exception`, and `exit(0)`s without an `on_error:` route | Swallowed parse failures reach the FSM as exit 0 → treated as successful, producing zero results with no log, stderr, or non-zero exit (BUG-2383, observed across three loops). Add an `on_error:` route so parse failures route explicitly | WARNING | `parse_swallow_ok: true` |
| **policy-table** | For any loop with `context.policy_rules`, every predicate dimension must be *scored* — listed in `context.rubric_dimensions` (normalized: lowercase + spaces→hyphens) or written by a shell state as `rubric-dim-<name>.txt` | An unscored dimension is silently inert: `_eval_predicate` returns `True` only for `!=`, so `==`/`>=`/`<=`/`<`/`>` predicates never match and routing always falls to the catch-all (ENH-2309) | WARNING | `policy_dims_scored_ok: true` |
| **static `loop:` ref** | A state's static (non-`${...}`) `loop:` name must resolve to a `.yaml` file at definition time — use the full relative path incl. any subdir prefix (`loop: oracles/verify-confidence-scores`, not `loop: verify-confidence-scores`) | An unresolvable static ref fails identically every run (`FileNotFoundError`); the validator blocks load so `ll-loop validate` exits 1 and `ll-loop run` refuses to start (BUG-2400). Dynamic `${...}` names are not checked | **ERROR** | — |

MR-1 is the load-bearing one: an optimizer's self-assessment is no better than a coin
flip, so pair the LLM judge with something it cannot talk its way around — an exit code, a
numeric score, a diff stall, or a convergence gate.

**Canonical MR-1 example — `loop-composer-adaptive`'s `reassess` gate**: When a
sub-loop fails, `reassess` (`llm_structured`) is reached unconditionally via
`write_step_failed → read_completed_summaries → read_last_verdict → reassess`.
If `reassess` decides to replan, `check_replan_budget` (`output_numeric`, operator: `lt`)
gates *re-entry*: `reassess → parse_reassess_decision → route_reassess_replan (on_yes)
→ check_replan_budget → increment_replan_count → apply_replan → (sub-loop re-runs)
→ … → reassess`. The budget counter is a non-LLM signal the LLM cannot self-inflate,
so it enforces a hard ceiling on how many times the LLM judge can decide to replan —
satisfying MR-1's requirement that every `llm_structured` state be paired with a
non-LLM evaluator in its routing chain. This matches the
`harness-single-shot.yaml:check_semantic → check_invariants` pattern — a measurable
external signal gates entry to the LLM judge. See
[`loops/loop-composer-adaptive.yaml`](../../scripts/little_loops/loops/loop-composer-adaptive.yaml).

---

## The Optimizer Error Taxonomy

These are the recurring ways optimizers damage a harness. Treat the list as a
**review checklist for your `propose`/`apply` steps** — the failure modes your
diagnosis prompt should watch for and your scorer should catch:

| Error type | What it looks like | Mitigation |
|------------|--------------------|------------|
| **Redundant Duplication** | Adds a tool/memory that already exists | Diagnose existing capabilities before proposing additions |
| **Hardcoding** | Embeds task-specific values seen during optimization | Score against a held-out task set, not the tuning set |
| **Task-specific Addition** | Adds instructions valid only for a narrow subset | Reject edits that don't generalize across the benchmark |
| **Hallucination** | References tools/memory/info that don't exist | `check_concrete` / run the target after every edit |
| **Overengineering** | Wraps simple logic in needless tools; appends without pruning | Watch `check_invariants` / diff size; favor deletions |
| **Direct Performance-degrading Update** | Removes a format/behavior critical to the agent | Score-gate + revert (the whole point of the gate) |
| **Overgeneralized Heuristic** | Collapses diverse cases into one rule | Use a diverse task set so the over-broad rule regresses |
| **Safety Violation** | Strips step/cost limits or deletes scaffold | Treat removed guardrails as a red flag in `diagnose` |

The first six map cleanly onto the `diagnose → score → gate → revert` shape below: catch
what you can at diagnosis, and let the score gate catch the rest by reverting any edit
that doesn't measurably help.

### Runtime Failure Modes

These failure modes occur during loop **execution** (detected post-hoc by `/ll:audit-loop-run`
rather than during optimization). They are distinct from the optimizer error taxonomy above,
which covers mistakes a harness-optimizer loop makes when editing another loop.

| Failure mode | What it looks like | Detection signal | Remediation |
|---|---|---|---|
| **feature-stubbing** | Loop claims it implemented X but only added a placeholder, comment, or TODO; no real code change. | External verification state (run tests, lint, or smoke command) absent before `success`. | Add a non-LLM exit-code evaluator that runs the target and confirms real output before allowing `success`. |
| **shallow-iteration** | Burns high tool-call budget (>30 `action_complete` events) without creating or modifying helper files outside the primary artifact path. Loop iterates without accumulating reusable structure. | `ll:audit-loop-run` Step 5.5 flags when `action_complete` count exceeds threshold with no auxiliary file mutations. Corroborated by a co-present `diff_stall` evaluator verdict. When the primary path is gitignored (e.g. the default `.loops/runs/` run-directory root), `git diff HEAD` can't see it — Step 5.5 checks `git check-ignore` first and falls back to a `find -newermt <run_start>` filesystem scan, reporting `unknown` (not a false `0`) when neither signal is available (BUG-2482). | Add intermediate artifact-write states that produce named helper files each iteration; break monolithic iteration into smaller sub-tasks. |

**Relationship between the two modes**: `feature-stubbing` is about the *content* of the output (placeholder vs. real work); `shallow-iteration` is about the *shape* of execution (high budget with no structural accumulation). A run can exhibit both simultaneously — shallow iteration that never produces real output — in which case both warnings are emitted and the `diff_stall` corroboration signal is particularly diagnostic.

---

## The Canonical Shape

Harness-optimizer loops follow a `diagnose → propose → apply → measure-externally` shape,
**not** the generic 5-phase skill-harness pipeline. The reference implementation is
[`scripts/little_loops/loops/harness-optimize.yaml`](../../scripts/little_loops/loops/harness-optimize.yaml),
and the wizard-generated template lives in
[`skills/create-loop/templates.md`](../../skills/create-loop/templates.md):

```
diagnose → baseline → propose → apply → score → gate ─┬─► commit ─► (loop back to diagnose)
                                                       └─► revert ─► done
```

| State | Role |
|-------|------|
| `diagnose` | **Initial state.** Identify the highest-priority component to fix before any edit — this is the biggest lever on fix-rate. |
| `baseline` | Run the scorer once; capture the pre-edit score. |
| `propose` | LLM proposes **one** targeted edit to the diagnosed component. |
| `apply` | Apply the proposed change to the target file(s). |
| `score` | Run the scorer again; capture the post-edit score. |
| `gate` | A **non-LLM `convergence` evaluator** compares scores: accept on improvement/target, reject on stall/regression. |
| `commit` | Persist the accepted edit; re-enter `diagnose` to re-prioritize against the new baseline. |
| `revert` | `git restore` the rejected edit; terminate. |

Two properties make this shape safe by construction:

- **`diagnose` is initial**, so every iteration re-prioritizes *which* component to touch
  rather than blindly editing.
- **The success signal is the non-LLM `convergence` gate**, never an LLM self-grade. This
  satisfies MR-1 by construction (there is no `check_semantic` to pair). The accept/revert
  branch is the operational answer to "half of edits are detrimental."

Artifacts isolate per run under `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`,
recording every iteration's score and accept/reject verdict — so the trajectory survives
even when individual edits are reverted (MR-3 / MR-5).

> **One-line hardening for `diagnose`:** make the priority ranking an explicit gate, not a
> suggestion — `diagnose` should emit a single committed highest-priority component and
> refuse to advance to `propose` without one, so every iteration spends its first step on
> the highest-leverage component rather than drifting into an unscoped edit.

### Minimal Example

A 20-line harness optimizer for a single skill file, with one comment per key state:

```yaml
name: optimize-capture-issue
category: harness
initial: diagnose
max_steps: 10

states:
  diagnose:                          # identify WHICH component is weakest before editing
    action: "Review skills/capture-issue/SKILL.md against the test results and name the single highest-priority component to fix (prompt/tool/workflow). Output: COMPONENT=<name>"
    action_type: prompt
    next: baseline

  baseline:                          # measure BEFORE the edit so the gate has a reference
    action: "pytest scripts/tests/test_capture_issue.py -q --tb=no && echo SCORE=$(pytest --co -q | wc -l)"
    on_yes: propose
    on_error: propose

  propose:                           # LLM generates ONE targeted edit
    action: "Propose exactly one change to the ${captured.diagnose.output} component of skills/capture-issue/SKILL.md that would fix the pattern you diagnosed. Output the diff."
    action_type: prompt
    next: apply

  apply:                             # apply the edit
    action: "Apply the proposed diff to skills/capture-issue/SKILL.md"
    action_type: prompt
    next: score

  score:                             # measure AFTER the edit
    action: "pytest scripts/tests/test_capture_issue.py -q --tb=no"
    next: gate

  gate:                              # NON-LLM convergence gate: keep on improvement, revert on regression
    evaluate:
      type: convergence
      source: "${captured.score.exit_code}"
      target: "0"
    on_yes: commit
    on_no: revert

  commit:                            # accept and loop back to diagnose
    action: "git add skills/capture-issue/SKILL.md && git commit -m 'harness: optimizer improvement'"
    action_type: shell
    next: diagnose

  revert:                            # discard the failed edit
    action: "git restore skills/capture-issue/SKILL.md"
    action_type: shell
    terminal: true
```

### Feed the trajectory forward: cumulative summaries

The per-iteration `trajectory.jsonl` is also the substrate for the optimizer's `memory`
component. On each re-entry to `diagnose`, summarize the prior iterations — *what was
proposed, what the score did, and what was reverted* — and put that summary in the
diagnosis context. This directly counters **Redundant Duplication**: without a memory of
reverted edits, an optimizer happily re-proposes the change it just discarded, since these
mistakes don't self-correct. The summary is a cumulative ledger ("tried X → +0, reverted;
tried Y → +3, kept"), not a verbatim replay — keep it short enough to ride in the
diagnosis prompt.

---

## Creating One

Run `/ll:create-loop` and choose **"Optimize a harness"**. The wizard asks for:

- **Targets** — space-separated artifact paths to optimize (e.g. `skills/foo/SKILL.md`,
  `.loops/docs-sync.yaml`).
- **Scorer** — a shell command that exits 0 and prints a numeric score
  (e.g. `pytest scripts/tests/test_docs_sync.py -q --tb=no`).
- **Tasks directory** — the benchmark/task set the scorer runs against.
- **Diagnose action** — shell or prompt that surfaces what is currently wrong (this seeds
  the priority-identification step).

The generated loop is the [canonical shape](#the-canonical-shape) above and passes MR-1 by
construction (no `check_semantic`; the `convergence` gate is the sole success signal). Do
**not** adapt the standard "harness a skill" template for this — meta-loops have stricter
rules.

---

## Validating and Measuring

Run these three commands in sequence before declaring a harness optimizer production-ready:

```bash
# Step 1: Check the YAML for rule violations
ll-loop validate my-optimizer
# → Enforces MR-1, MR-7, MR-9 (ERROR) and MR-2/MR-3/MR-4/MR-5/MR-6/MR-8/MR-10 (WARNING). Fix all ERRORs before continuing.

# Step 2: Verify the gate actually discriminates
ll-loop diagnose-evaluators my-optimizer
# → Reports Bernoulli variance p*(1-p) per evaluator. A score below 0.05 means the gate
#   always returns the same verdict — it's not measuring anything useful. Fix before raising max_steps.

# Step 3: Confirm the harness beats a single unguided call
ll-loop run my-optimizer --baseline
# → Runs two arms: harness vs. single-shot. Reports quality delta and token cost.
#   If the harness doesn't beat baseline by a meaningful margin, the loop isn't worth the overhead.
```

- **`ll-loop validate <loop>`** — enforces MR-1, MR-7, MR-9 (ERROR) and MR-2/MR-3/MR-4/MR-5/MR-6/MR-8/MR-10 (WARNING)
  before you run.
- **`ll-loop diagnose-evaluators <loop>`** — after MR-1 passes, checks that your gate is
  actually *discriminating*. A gate can satisfy MR-1 yet be toothless if its verdict never
  varies; this flags evaluators with Bernoulli variance `p*(1-p)` below 0.05 across ≥10
  runs.
- **`ll-loop calibrate-budget <loop>`** — decide whether increasing `max_steps` will
  earn its token cost. Reports `p*(1-p)` per evaluator state with a WARN when variance
  falls below 0.05: iterations spent against a toothless evaluator change nothing, so fix
  the evaluator before raising the budget. Complements `diagnose-evaluators` with a
  retry-budget framing.
- **`ll-loop run <loop> --baseline`** — empirically validate the optimizer earns its cost
  by running a blind A/B against an unguided single call. A strong skill is not necessarily
  a strong optimizer — don't assume, measure.
- **`ll-loop promote-baseline <loop>`** — after inspecting a run's output, promote it as
  the new comparator baseline.

### Cross-host validation (`--cross-host`)

A harness improvement measured on one host CLI may not transfer to another —
judge prompts, slash-command dispatch, and output formatting all vary by host.
Add `--cross-host` to a baseline run to check whether the improvement is
host-general or host-specific:

```bash
ll-loop run my-optimizer --baseline --cross-host
```

What it does:

1. Runs the normal baseline A/B on your primary host (whatever `resolve_host()`
   selects — `LL_HOST_CLI` / `orchestration.host_cli` / probe order).
2. Picks the next available host from the probe order (`claude`, `codex`,
   `opencode`, `pi`) whose binary is on `PATH`, and re-runs the identical
   baseline trial with `LL_HOST_CLI` overridden to it. `--baseline-skill` and
   `--items` are forwarded unchanged.
3. Prints a **Cross-host Comparison** table: per-host harness pass rate with
   Wilson 95% confidence intervals and trial counts.

```
Cross-host Comparison
  Host                   Pass rate              95% CI      n
  --------------------  ----------  ------------------  -----
  claude                       80%  [0.49, 0.94]           10
  codex                        60%  [0.31, 0.83]           10
```

If the harness-vs-baseline **ordering reverses** between hosts (harness wins on
one, baseline wins on the other), the run prints an explicit
`⚠ Ordering reversal` warning — treat the improvement as host-specific and
don't bake it into a shared loop without a host guard.

If only one host binary is installed, the step is skipped with a notice
(`Cross-host: only one host available`) — the primary baseline results are
unaffected.

### Debugging a Stuck Optimizer

**Symptom: the optimizer keeps proposing the same change it already tried (or very similar ones)**

Cause: `diagnose` doesn't have memory of prior rejected edits. Without a trajectory summary, the optimizer treats each iteration as a fresh start and rediscovers the same dead end.

Fix: implement cumulative trajectory summarization (see [Feed the trajectory forward](#feed-the-trajectory-forward-cumulative-summaries) above). The `diagnose` prompt should receive a summary of what was tried and rejected, not just the current state of the file.

**Symptom: the gate always passes (or always fails) regardless of what was changed**

Cause: the convergence evaluator is miscalibrated — it measures something that doesn't vary with edit quality, or the scorer is brittle. Diagnose with `ll-loop diagnose-evaluators` to check Bernoulli variance; a score below 0.05 means the gate is toothless.

Fix: broaden the scorer (add more test cases, diversify the benchmark), or tighten the convergence threshold so meaningful improvement is required to pass.

**Symptom: the optimizer makes many edits but the benchmark score doesn't improve over 10 iterations**

Cause: the diagnosis step isn't identifying the right component. The highest-leverage fix may be in a different part of the harness than `diagnose` is pointing at.

Fix: lower `max_steps` temporarily to 3 and inspect the `trajectory.jsonl` to see what's actually being proposed. Often the fix is to make `diagnose` output more specific component identification.

### Tracking which strategies actually work

Once `trajectory.jsonl` tags each edit by component and strategy (which component was
touched, what kind of change it was), you can analyze **which fix strategies correlate with
score improvement** versus which tend to regress — and bias future `propose` steps toward
the ones that earn their keep. This is a genuine learning layer, but it is only meaningful
**at sample size**. With nearly half of update steps detrimental and single-task
scores noisy, a correlation drawn from a handful of iterations is indistinguishable from
chance — the same trap the `diagnose-evaluators` Bernoulli-variance check guards against
(`p*(1-p)` below 0.05 across ≥10 runs is too flat to trust). Treat strategy-outcome
correlation as an aggregate signal across many runs, not a per-run verdict, and never let it
override the non-LLM `convergence` gate on any individual edit.

---

## Planning Loop Guards

Planning loops (`specialist-pipeline` type generated by `/ll:create-loop`) reason about
*logical* correctness — whether the proposed plan is sound — but not about *execution
feasibility*: whether each action in the plan can actually run in the target environment.
A plan that is valid in a standard shell may silently fail in Claude Code, Codex, or a
restricted CI environment where specific MCP tools, shell commands, or write paths are
unavailable.

The `check_substrate` state is an optional LLM-judged feasibility gate for planning loops
that target non-standard execution environments. It sits between the `plan` state and the
`research` state, validating each proposed action against known environment constraints
before the loop commits to research and implementation.

### When to Use It

Add `check_substrate` when your planning loop targets:
- **Claude Code / Codex**: not all shell commands or MCP tools are available in every session
- **Restricted shells**: Docker containers, sandboxed CI environments, or environments where
  `git`, network tools, or write paths may be absent
- **Token-budget-constrained runs**: plans that propose expensive multi-file operations when
  the token budget won't cover them
- **Remote or offline environments**: plans that require external network access (web search,
  API calls) but the target environment is air-gapped

### State Shape

```yaml
check_substrate:
  action: "echo 'Checking substrate constraints'"
  action_type: shell
  evaluate:
    type: llm_structured
    source: "${captured.plan.output}"
    prompt: >
      Enumerate the target execution environment's known constraints:
      shell command availability, MCP tool access, file write permissions, token budget.
      Validate each proposed action in the plan against these constraints.
      Answer YES if every action is feasible in the target environment.
      Otherwise NO, listing each infeasible action and the constraint it violates.
  on_yes: research      # all actions feasible → proceed to research
  on_no: plan           # one or more actions infeasible → re-plan with diagnosis context
```

The `on_no: plan` routing matches the canonical back-link pattern established by
`review_plan` in the same planning template. The infeasibility diagnosis in the evaluator
response is surfaced in the `plan` state's next iteration as captured context, so the
planner can revise the approach.

### Activation

The `/ll:create-loop` wizard (specialist-pipeline type, Step S3.5) offers an explicit
prompt: *"Does this loop target a non-standard execution environment?"* Answer **Yes** to
have the wizard emit `check_substrate` as an active (uncommented) state. The state is
always present as a commented-out block in generated YAMLs so it can be activated later
by uncommenting.

The canonical example with a commented `check_substrate` block is at
[`scripts/little_loops/loops/harness-plan-research-implement-report.yaml`](../../scripts/little_loops/loops/harness-plan-research-implement-report.yaml).

### Note on MR-1

`check_substrate` uses `evaluate: type: llm_structured`. In a standard specialist-pipeline
loop (not a meta-loop), MR-1 does not apply — planning loops are not category `harness`
or `meta`. If you embed this state in a meta-loop, pair it with a non-LLM evaluator
(e.g., `exit_code` or `output_numeric`) to satisfy MR-1.

---

## See Also

- [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) — the sibling pattern:
  wrapping a *skill* in a quality pipeline (not optimizing the harness itself)
- [LOOPS_GUIDE.md](LOOPS_GUIDE.md) — full FSM reference: evaluators, state fields, CLI
- [`.claude/CLAUDE.md` § Loop Authoring](../../.claude/CLAUDE.md) — the normative MR-1…MR-10 rules
- *Towards Direct Evaluation of Harness Optimizers* — the empirical study behind these guardrails, with the per-step measurements, error taxonomy, and findings the rules above are distilled from
- [`scripts/little_loops/loops/harness-optimize.yaml`](../../scripts/little_loops/loops/harness-optimize.yaml) — the reference harness-optimizer loop
- [`skills/create-loop/templates.md`](../../skills/create-loop/templates.md) — the wizard-generated "Optimize a harness" template
- [`skills/create-loop/loop-types.md`](../../skills/create-loop/loop-types.md) § Specialist Pipeline — `check_substrate` template and wizard question S3.5
