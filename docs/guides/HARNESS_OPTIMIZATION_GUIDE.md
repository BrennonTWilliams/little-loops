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
- [The Design Rules (MR-1…MR-5)](#the-design-rules-mr-1mr-5)
- [The Optimizer Error Taxonomy](#the-optimizer-error-taxonomy)
- [The Canonical Shape](#the-canonical-shape)
- [Creating One](#creating-one)
- [Validating and Measuring](#validating-and-measuring)
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

## The Design Rules (MR-1…MR-5)

The normative source for these rules is [`.claude/CLAUDE.md` § Loop Authoring](../../.claude/CLAUDE.md);
`ll-loop validate` enforces them. This section explains *why* each exists. Each rule can be
suppressed with a top-level flag when you have a justified reason.

| Rule | What it requires | Why | Severity | Suppress with |
|------|------------------|-----|----------|---------------|
| **MR-1** | Every `check_semantic` / `llm_structured` state pairs with ≥1 non-LLM evaluator (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `mcp_result`) | Self-grades are unreliable | **ERROR** | `meta_self_eval_ok: true` |
| **MR-3** | Intermediate artifacts write under `${context.run_dir}/`, not bare `.loops/tmp/` | Concurrency safety | WARNING | `shared_state_ok: true` |
| **MR-4** | An LLM-judged state with `on_yes` must also route `on_no`/`on_partial` (or `next:`/full `route:`) — no silent dead-end on a non-yes verdict | Half of verdicts are adverse | WARNING | `partial_route_ok: true` |
| **MR-5** | A harness loop that writes artifacts in a generate→evaluate cycle must snapshot per-iteration (`artifact_versioning: true`), not overwrite a flat path | Errors persist — keep the trajectory | WARNING | `artifact_versioning_ok: true` |

MR-1 is the load-bearing one: an optimizer's self-assessment is no better than a coin
flip, so pair the LLM judge with something it cannot talk its way around — an exit code, a
numeric score, a diff stall, or a convergence gate.

**Canonical MR-1 example — `loop-composer-adaptive`'s `reassess` gate**: The `reassess`
state (`llm_structured`) is preceded in the routing chain by `check_replan_budget`
(`output_numeric`, operator: `lt`). The budget counter is a non-LLM signal the LLM cannot
self-inflate, so it gates access to the reassess prompt. Full routing chain:
`increment_replan_count → check_replan_budget (output_numeric) → read_completed_summaries
→ read_last_verdict → reassess (llm_structured)`. This matches the
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

- **`ll-loop validate <loop>`** — enforces MR-1 (ERROR) and MR-3/MR-4/MR-5 (WARNING)
  before you run.
- **`ll-loop diagnose-evaluators <loop>`** — after MR-1 passes, checks that your gate is
  actually *discriminating*. A gate can satisfy MR-1 yet be toothless if its verdict never
  varies; this flags evaluators with Bernoulli variance `p*(1-p)` below 0.05 across ≥10
  runs.
- **`ll-loop run <loop> --baseline`** — empirically validate the optimizer earns its cost
  by running a blind A/B against an unguided single call. A strong skill is not necessarily
  a strong optimizer — don't assume, measure.
- **`ll-loop promote-baseline <loop>`** — after inspecting a run's output, promote it as
  the new comparator baseline.

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

## See Also

- [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) — the sibling pattern:
  wrapping a *skill* in a quality pipeline (not optimizing the harness itself)
- [LOOPS_GUIDE.md](LOOPS_GUIDE.md) — full FSM reference: evaluators, state fields, CLI
- [`.claude/CLAUDE.md` § Loop Authoring](../../.claude/CLAUDE.md) — the normative MR-1…MR-5 rules
- *Towards Direct Evaluation of Harness Optimizers* — the empirical study behind these guardrails, with the per-step measurements, error taxonomy, and findings the rules above are distilled from
- [`scripts/little_loops/loops/harness-optimize.yaml`](../../scripts/little_loops/loops/harness-optimize.yaml) — the reference harness-optimizer loop
- [`skills/create-loop/templates.md`](../../skills/create-loop/templates.md) — the wizard-generated "Optimize a harness" template
