---
id: EPIC-1663
title: Codify meta-loop harness-design rules (SHOR-driven)
type: epic
status: open
priority: P2
discovered_date: 2026-05-23
discovered_by: manual
labels: [epic, loops, harness, meta-loop, shor, validation, create-loop]
relates_to: [ENH-1664, ENH-1665, ENH-1666, ENH-1667, ENH-1547, ENH-1636, ENH-1795, FEAT-1791]
---

# EPIC-1663: Codify meta-loop harness-design rules (SHOR-driven)

## Summary

Umbrella tracking issue for codifying two design rules across the little-loops
toolchain so that loops which modify other harness artifacts (loop YAMLs,
skills, agents, commands, CLAUDE.md) are designed and validated differently
from loops that operate on data.

The rules are drawn from [Towards Direct Evaluation of Harness Optimizers via
Priority Ranking (SHOR)](../../docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md):

1. **"Good agent harness ≠ good optimizer harness"** (SHOR §6.2, Finding 2).
   The `create-loop` wizard currently generates the same 5-phase pipeline
   regardless of whether the inner skill operates on data (`refine-issue`) or
   on harness artifacts (`review-loop`, `harness-optimize`). These need
   different scaffolding — diagnosis-first for meta-loops.
2. **LLM self-grades on harness changes are unreliable** (SHOR §3 Analysis III,
   Table 1: 33–55% accuracy at self-evaluation; Sonnet 4.6 = 0.334). Any loop
   that modifies a harness artifact MUST pair `check_semantic` evaluation with
   at least one non-LLM evaluator (`exit_code`, `output_numeric`, `convergence`,
   `diff_stall`, or `mcp_result`).

The existing `loop-specialist` agent already lists `self-evaluation bias` and
`feature-stubbing` in its failure-mode taxonomy with the prescription
"Replace the self-judge with an external check" — this epic gives that
prescription teeth at design, validation, and (optionally) runtime.

## Children

- **ENH-1664** — CLAUDE.md "Loop Authoring" section (declarative rule, priority and pairing)
- **ENH-1665** — `ll-loop validate` meta-loop lint rules MR-1 (error) + MR-2 (warning)
- **ENH-1666** — `create-loop` wizard branch: "Optimize a harness (meta-loop)" template (diagnosis-first scaffolding)
- **ENH-1667** — Runtime meta-eval divergence telemetry (follow-up; logs LLM vs non-LLM verdict per iteration)
- **ENH-1636** — `ll-loop validate` lint for zero-retry counter pattern (additional validator rule in the same validate pipeline)
- **ENH-1795** — Action-level loop detection (complement to diff_stall)
- **ENH-1793** — Blind Cross-Iteration Comparator
- **FEAT-1791** — `check_contract` Boundary-Mismatch Evaluator

## Design Decisions (locked)

These were decided during the brainstorming session and apply across all children:

1. **Detector heuristic is structural, not name-based.** A loop is "meta" if any
   `state.action` writes paths matching `loops/[\w-]+\.yaml`,
   `skills/[\w-]+/SKILL\.md`, `agents/[\w-]+\.md`, `commands/[\w-]+\.md`,
   `\.claude/(CLAUDE\.md|settings)`, contains `harness/`, imports
   `lib/benchmark.yaml`, or references `yaml_state_editor` / `replace_action`.
   Sanity-checked against `scripts/little_loops/loops/`: the heuristic
   matches exactly the two known meta-loops (`harness-optimize.yaml`,
   `loop-specialist-eval.yaml`) and nothing else.
2. **Escape hatch is flag-only.** A new YAML top-level field
   `meta_self_eval_ok: true` suppresses MR-1 for the rare justified case.
   No required reason field — comments rot; the flag itself is grep-able.
3. **Wizard branch generates standalone YAML.** The new "Optimize a harness"
   branch does NOT use `from: harness-optimize` inheritance — it generates a
   full, self-contained YAML so user-authored meta-loops are not coupled to
   the canonical template's state graph.
4. **Telemetry is a follow-up.** ENH-1667 is scoped separately and not a
   blocker for the first three children.

## Dependency Chain

```
ENH-1665 (validate MR-1/MR-2)        ← highest-leverage; lands first
   ↓ informs
ENH-1666 (create-loop meta branch)   ← generates YAML that satisfies MR-1
   ↓ informs
ENH-1664 (CLAUDE.md rule)            ← documents the constraint enforced by 1665/1666
   ⇣ separate track
ENH-1667 (runtime telemetry)         ← follow-up; not blocking
```

ENH-1665 lands first because the validator is the only layer with teeth —
humans and Claude can both forget the CLAUDE.md rule, but the validator
won't. Once MR-1 exists, ENH-1666 can be written to generate YAML that
passes the new check by construction.

## Motivation

- The current wizard would happily generate a `harness-optimize`-style loop
  whose only evaluator is `check_semantic`, which the SHOR paper shows is
  ~33–55% reliable at self-judging harness updates.
- The existing `loop-specialist` agent diagnoses self-evaluation bias
  post-hoc; this epic shifts the gate *left* to design and validate time.
- `harness-optimize.yaml` already follows the correct pattern (numeric
  scorer + `convergence` gate, no `check_semantic`) — that's the positive
  template the wizard branch should generate from.

## Out of Scope

- Changes to `review-loop` (already addressed in completed ENH-1547's
  `--strict-semantic` flag and rubric scorecard work).
- Changes to the FSM executor itself (the validator and wizard cover this
  without runtime modifications).
- Multi-agent or multi-model judge designs — defer to ENH-1667 follow-up.

## Related Documentation

| Document | Relevance |
|----------|-----------|
| `docs/research/Towards-Direct-Evaluation-of-Harness-Optimizers.md` | Source paper; Table 1, §6.2 Finding 2, §7.1 diagnosis-first prescription |
| `agents/loop-specialist.md:52–63` | Existing failure-mode taxonomy — `self-evaluation bias` and `feature-stubbing` modes |
| `scripts/little_loops/loops/harness-optimize.yaml` | Positive template — uses external scorer + convergence gate |
| `scripts/little_loops/fsm/validation.py:686` | `validate_fsm` aggregator — insertion point for MR-1/MR-2 |
| `skills/create-loop/SKILL.md:73` | Loop type selection table — insertion point for new meta-loop branch |
| `skills/create-loop/loop-types.md:549` | Harness questions section — model for new meta-loop question flow |

## Labels

- epic
- loops
- harness
- meta-loop
- shor
- validation
- create-loop

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: NEEDS_UPDATE** — Most children are done; epic is nearly complete:
- ENH-1664 (CLAUDE.md Loop Authoring section): **DONE** ✓ — section exists in `.claude/CLAUDE.md` with MR-1, `meta_self_eval_ok`, diagnosis-first scaffolding rules
- ENH-1665 (validate MR-1/MR-2): **DONE** ✓
- ENH-1666 (create-loop meta-loop wizard branch): **DONE** ✓
- ENH-1667 (runtime telemetry): **DONE** ✓
- ENH-1636 (zero-retry counter lint): **DONE** ✓
- ENH-1795 (action-level loop detection): **open**
- ENH-1793 (blind cross-iteration comparator): **open**
- Action: Only ENH-1795 and ENH-1793 block epic completion; update progress notes

## Session Log
- `/ll:verify-issues` - 2026-06-02T22:49:01 - `aeb556c4-3814-4aa1-9bd0-5b4a91c2087e.jsonl`
- `/ll:verify-issues` - 2026-06-01T03:08:51 - `ed2ec455-964e-4a94-92a4-e94218c08ad6.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:19 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
