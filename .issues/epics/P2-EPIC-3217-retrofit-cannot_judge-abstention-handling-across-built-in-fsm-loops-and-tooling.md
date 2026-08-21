---
id: EPIC-3217
type: EPIC
title: Retrofit cannot_judge abstention handling across built-in FSM loops and tooling
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:26:39Z'
depends_on:
- EPIC-2789
---

# EPIC-3217: Retrofit cannot_judge abstention handling across built-in FSM loops and tooling

## Summary

ENH-3185 added a 5-value LLM-judge verdict grammar (`yes`/`no`/`blocked`/`partial`/`cannot_judge`) with an SSOT at `scripts/little_loops/fsm/verdicts.py`, bounded abstention routing in `FSMExecutor`, a v41 history schema with `harness_eval_abstention_rate()`, and an `ll-harness` ABSTAIN exit code 3. The mechanism landed; adoption did not.

An audit of the built-in loops found **34 LLM-judged gates across 23 loops in `scripts/little_loops/loops/`, and not one declares `on_cannot_judge`**. Every gate therefore runs on the AC6 undeclared-abstention fallback: hold up to `_ABSTENTION_HOLD_CAP = 2` consecutive re-entries, then escalate to `on_error` (never `on_no`, never `route.default`). That fallback is safe by construction, but the *destination* it escalates to was written for infrastructure errors, not for "the judge could not observe this" — and for a third of the gates it is materially worse than the pre-ENH-3185 behavior.

Audit breakdown:

- **13 gates declare neither `on_cannot_judge` nor `on_error`.** `_abstention_fallback()` (`executor.py:2669`) returns `None`, so the run terminates via "No valid transition" after two holds. This set includes all three `harness-*` templates, which are the documented copy-paste examples in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — so the shape propagates into every user-authored harness.
- **10 "funnel" gates** send `on_yes`/`on_no`/`on_partial` to a single shared target (the LLM produces an artifact rather than judging), leaving abstention as the only diverging verdict. Three diverge into a hard failure: `goal-cluster::dedup_and_batch`, `loop-composer::decompose_goal`, and `loop-router::classify_goal` all fall to `finalize_failed`.
- **1 gate re-creates the fabricated-pass failure mode ENH-3185 exists to remove**: `sprint-build-and-validate::audit_conflicts` has `on_error: commit`, so an abstained conflict audit commits.
- **Both telemetry surfaces are unconsumed**: `harness_eval_abstention_rate()` has zero callers outside its own definition and tests, and `ll-harness` exit 3 collapses to `error` in the FSM `exit_code` evaluator (0→yes, 1→no, 2+→error, `evaluators.py:250-255`), making an abstained harness run indistinguishable from a crash to a parent loop.
- **Neither static-check surface knows the verdict exists**: `fsm/validation/` has no rule for the missing-both-routes condition, and `fsm-loop-schema.json` declares `on_partial` and `on_blocked` on `stateConfig` (`additionalProperties: false`) but not `on_cannot_judge`.

This EPIC coordinates the retrofit. It deliberately separates the mechanical route repairs (which remove latent run-killers and can land immediately) from the per-gate semantic work (which requires deciding what abstention *means* at each gate) and the tooling work (which prevents the gap from recurring).

## Scope

In scope: declaring abstention routes across the built-in loops in `scripts/little_loops/loops/`, a validator rule for `on_cannot_judge`, and wiring the two existing abstention telemetry surfaces into consumers. (No JSON-schema property is needed — see Sequencing step 2.)

Out of scope: changing the abstention grammar, the hold cap, or the routing precedence established by ENH-3185 — with one explicit exception, decision (a) under Sequencing, resolved as the general `_uncertain` suffix fallback and filed as **BUG-3228**; that is a declaration-matching change, not a precedence change, and it lands on its own rather than inside any retrofit child. Also out of scope: admitting `cannot_judge` into the binary consumers (blind comparator, contract evaluator), which `verdicts.py` documents as a deliberate exclusion (AC8).

## Sequencing

1. Funnel-gate repairs (BUG-3220 — mechanical, one line per gate, removes three run-killers).
2. Validator rule (ENH-3222 — prevents regression before the semantic work lands). No JSON-schema change is needed: `fsm-loop-schema.json`'s `stateConfig.patternProperties` `^on_` catch-all (lines 686-692) already admits `on_cannot_judge` under `additionalProperties: false`, verified by `ll-loop validate` exiting 0 on a loop carrying the key. BUG-3221 was cancelled NO-GO on that basis.
3. Per-gate semantics for the 13 no-route gates, including the harness templates (BUG-3219,
   decomposed into BUG-3226 for the 11 route-addition gates and BUG-3227 for the two
   `check_substrate` gates needing a deterministic probe). BUG-3226 and BUG-3227 both edit
   `skills/create-loop/loop-types.md` and `reference.md`, so run them serially rather than
   as parallel epic branches.
4. Telemetry consumers (ENH-3223, ENH-3224).

The `audit_conflicts` fix (BUG-3218) is independent of the sequence and should land first on severity.

BUG-3228 (the `_uncertain` suffix fallback, from decision (a) below) is likewise independent — it touches `_route`/`_abstention_declared` only, no loop YAML, and none of the children depend on it landing first.

### Two decisions this EPIC owned — both RESOLVED 2026-08-16

**(a) RESOLVED: general `_uncertain` suffix fallback in `_route`, filed separately, not blocking the retrofit.**

The framing that opened this decision was too narrow. `evaluators.py:1295-1296` appends `_uncertain` to *whatever* verdict the judge returned, and `_route` has no suffix handling for **any** of them — verified empirically against a state declaring `on_yes`/`on_no`/`on_error`:

```
yes                    -> _route=None        ← run dies: "No valid transition"
no_uncertain           -> _route=None
partial_uncertain      -> _route=None
cannot_judge_uncertain -> _route=None   (even with on_cannot_judge declared)
```

So `uncertain_suffix: true` kills a run on the first below-threshold **yes**, long before abstention is reachable. That is why no loop in the corpus sets it, and why the "declare both keys at every site" option was rejected: it would add ~22 lines of routing ritual (plus an ENH-3222 rule to enforce them) to harden one branch of an already-fatal configuration. An abstention-only prefix-match was rejected for fixing 1 of 5 suffixed verdicts and encoding an asymmetry that would be hard to explain later.

Resolution: `X_uncertain` falls back to `on_X` when no explicit `on_X_uncertain` is declared, applied **after** the exact-verdict lookup and **before** `route.default` — see BUG-3228, which also records that the family is six verdicts, not five (`error_uncertain` is reachable: `evaluators.py:1270` exempts `"error"` from the grammar check), and that `route:`-table states carrying a `_` default silently misroute suffixed verdicts today rather than dying. This fixes the whole family, makes `uncertain_suffix` usable for the first time, and subsumes the abstention case. It preserves AC12's "these are distinct signals" stance, which is about *meaning* — an author wanting different handling still declares `on_X_uncertain` explicitly and it wins. Because it changes shipped ENH-3185 routing semantics, it lands as its own issue with its own tests, **not** inside the retrofit children.

Consequence for the children: BUG-3218/3219/3220 declare `on_cannot_judge` only, exactly as written, and need no revision when the fallback lands. ENH-3222's rule likewise checks `on_cannot_judge` only.

**(b) RESOLVED: FSM terminals stay binary; ENH-3224 lands at the evaluator boundary instead.**

Exit-code inventory taken during this decision:

| | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| `ll-loop run` | success | infra/limit (max_steps, timeout, stall) | failure terminal (`fsm/types.py:25`) | — |
| `ll-harness` | pass | fail | infra error | **abstain** (`cli/harness.py:698-700`) |
| FSM `exit_code` evaluator | `yes` | `no` | `error` | `error` (`evaluators.py:249-254`) |

The two CLIs already disagree on what `2` means, so a loop-level `3` would not be the clean parallel it appears to be.

The decisive point: **ENH-3224 never needed a new terminal shape.** Its real complaint is that a parent FSM cannot distinguish an abstained `ll-harness` run from a crash — decided entirely by `evaluate_exit_code` collapsing `2+` to `error`. Mapping `3 → cannot_judge` there is a few lines, needs no schema change, and feeds directly into the abstention routing this EPIC is already retrofitting. A new terminal kind would only serve the opposite direction (a child *loop* reporting "inconclusive" to its caller), which has zero consumers today and would cost a `StateConfig` flag, an `ExecutionResult` field, `_finish`, persistence, `EXIT_CODES`, the `worker_pool`/`queue` consumers of `FAILURE_TERMINAL_EXIT_CODE`, the validation walker, docs, and a policy call on what `ll-parallel` does with an abstaining gate.

Resolution: `failure: true` remains the FSM's only non-success terminal shape — fail-closed, which is the right default for gates. Abstention is distinguished in *telemetry* (ENH-3223's `harness_eval_abstention_rate()`), not in control flow. Revisit only if a loop genuinely needs to report inconclusive to its caller.

Consequences: BUG-3219's harness templates route abstention to `failed` as the permanent answer, not an interim, and never need revisiting. ENH-3224 is rescoped to the `evaluate_exit_code` mapping. Independent of this decision, `harness-plan-research-implement-report.yaml` and `loop-specialist-eval.yaml` still need a failure terminal added — neither has one.

---

_Original statement of the two decisions, retained for context:_

**(a) Does `on_cannot_judge` claim `cannot_judge_uncertain`?** Today it does not. `_abstention_declared` (`executor.py:2655-2664`) and `_route` (`:2699-2752`, via `extra_routes[verdict]`) both match the **literal** verdict string, while `is_abstention_verdict` (`fsm/verdicts.py:25-27`) accepts the `_uncertain` suffix. So a gate that declares `on_cannot_judge` still holds twice and escalates to `on_error` on `cannot_judge_uncertain` — or dies on "No valid transition" where no `on_error` exists. Unreachable across the built-in corpus today: `uncertain_suffix` defaults to `false` (`fsm/schema.py:103`) and no loop under `scripts/little_loops/loops/` sets it, so nothing produces the suffixed verdict (`evaluators.py:1295-1296` is its only writer).

It still needs deciding before the retrofit lands, for three reasons: BUG-3218's gate is fail-open to `commit` the moment anyone sets `uncertain_suffix: true` there; the harness templates BUG-3219 fixes are copied and modified by users, who may well enable it; and ENH-3222's rule as specified checks for `on_cannot_judge` only, so it would certify the narrow form as complete.

The fork:
- **Prefix-match in the executor** — one-line change in `_abstention_declared` (and the corresponding `_route` lookup) so a declared `on_cannot_judge` covers every `cannot_judge*` verdict. Arguably what ENH-3185 AC12 intended for loop authors; makes all three children's route additions complete as written; a behavior change to shipped ENH-3185 semantics, so it needs its own issue and test.
- **Declare both keys at every site** — no executor change, but doubles the route lines across ~22 gates, and every future gate has to remember both.

Until this resolves, the children are written to be safe under either outcome (BUG-3218 by removing `commit` from its error route; BUG-3219/3220 by noting the gap explicitly).

**(b) Is there an abstain-shaped FSM terminal?** `ll-harness` already models abstention as a third outcome — `cli/harness.py:621-633`, "an abstention is neither a pass nor a failure", exit code 3 — but the FSM side has no vocabulary for it: loops carry `done` (success) and `failure: true` terminals, nothing between. So BUG-3219 routing an unobservable `check_semantic` to `failed` makes the FSM say "failed" where the CLI says "inconclusive" for the identical condition, and ENH-3224 (which wants exit 3 to survive into a parent FSM) has nowhere for that signal to land.

Decide whether a third terminal shape exists before ENH-3224 designs its exit-code mapping. BUG-3219's harness templates are the first consumers either way; `failed` is the correct interim there, since it is fail-closed under both outcomes. Note this also interacts with the `harness-plan-research-implement-report.yaml` and `loop-specialist-eval.yaml` gap found during BUG-3219 review — neither has *any* failure terminal today, so both need a terminal added regardless, and it is cheaper to add the right shape once.


## Motivation

ENH-3185's stated purpose was to stop LLM-judged gates from coercing unobservable checks into a fabricated binary pass/fail. The grammar, the routing, the persistence, and the exit code all landed. What did not land is any *use* of them: no built-in loop declares an abstention route, and neither telemetry surface has a consumer. Until the retrofit happens, the enhancement's benefit is theoretical, and its safe-by-construction fallback is in some places worse than the behavior it replaced — a run that dies on "No valid transition", or an audit that commits.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/*.yaml` — 23 loops, 34 judged gates (see per-issue tables for the exact list)
- `scripts/little_loops/fsm/validation/` — new structural rule (ENH-3222)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — **no change needed**; the `^on_` `patternProperties` catch-all already admits `on_cannot_judge` (BUG-3221 cancelled NO-GO, see Sequencing step 2)
- `scripts/little_loops/fsm/evaluators.py` — `exit_code` mapping, if ENH-3224 takes that route
- `scripts/little_loops/history_reader.py` / a CLI reporting surface — ENH-3223 consumer

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_abstention_declared` / `_abstention_fallback` / `_route_abstention_hold` define the semantics every loop change is written against; not expected to change
- `scripts/little_loops/fsm/verdicts.py` — SSOT for the grammar; not expected to change
- Consuming projects' own loop YAMLs — unaffected by the built-in loop edits, but affected by a validator rule that warns on their gates

### Tests
- `scripts/tests/test_fsm_schema.py` — existing schema/dataclass lockstep conventions (ENH-2896, ENH-2934, ENH-2997) are the pattern for BUG-3221
- FSM validation tests for the new rule
- `ll-loop validate` over all built-in loops must stay clean after the retrofit

### Documentation
- `docs/generalized-fsm-loop.md` — already documents `on_cannot_judge`; may need the funnel/expensive-gate guidance
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — the harness templates' inline comments are the de facto pattern documentation
- `docs/reference/API.md` — if `harness_eval_abstention_rate()` gains a CLI surface

## Impact

- **Priority**: P2 — one child is P1 (a fail-open path to `commit`); the rest are latent run-terminations and unrealized value in a just-shipped feature.
- **Effort**: Medium — the funnel repairs and the schema property are near-mechanical; the per-gate semantics for 13 gates and the telemetry consumers carry the real work.
- **Risk**: Low-Medium — loop YAML route additions are individually small and reversible, but they change control flow in loops that this repo's own automation runs, and every local-editable project on this machine picks up working-tree changes immediately.
- **Breaking Change**: No — all changes are additive routes, a new schema property, a warning-severity rule, and new reporting.

## Related Key Documentation

- `docs/reference/API.md` `little_loops.fsm.executor` / `little_loops.fsm.validation`
  sections — abstention-fallback mechanics and the MR rule set this EPIC's
  children extend
- `.claude/CLAUDE.md` `## Loop Authoring` — meta-loop rules enforced by
  `ll-loop validate`, and the harness-template guide affected by 3 of the 13
  no-route gates

## Status

**Open** | Created: 2026-08-16 | Priority: P2

## Goal

Every LLM-judged gate in the built-in loops routes abstention deliberately, static checks prevent the shape from recurring, and the abstention data already being recorded reaches a consumer.

## Children
- **BUG-3218** — sprint-build-and-validate commits when the conflict audit abstains (open)
- **BUG-3219** — Judged gates with neither on_cannot_judge nor on_error terminate the run on abstention (cancelled — decomposed into BUG-3226/BUG-3227, nothing implemented under this ID)
- **BUG-3226** — Add on_cannot_judge routes to 11 judged gates across 9 loop files (open; supersedes BUG-3219)
- **BUG-3227** — check_substrate abstention needs a deterministic probe state in rn-build/rn-plan (open; supersedes BUG-3219)
- **BUG-3220** — Funnel judged gates route abstention into finalize_failed in composer and router loops (open)
- **BUG-3221** — fsm-loop-schema.json stateConfig omits on_cannot_judge under additionalProperties false (cancelled — NO-GO, the `^on_` patternProperties catch-all already admits the key; see Sequencing step 2)
- **ENH-3222** — Validator rule for judged gates with no abstention route and no error route (open)
- **ENH-3223** — harness_eval_abstention_rate has no consumers - surface abstention as a criterion-quality signal (open)
- **ENH-3224** — ll-harness ABSTAIN exit code 3 is indistinguishable from an error to a parent FSM (open)
- **BUG-3228** — uncertain_suffix verdicts are unroutable: X_uncertain matches no route and terminates the run (open)




## Success Metrics

- Zero judged gates in `scripts/little_loops/loops/` declare neither `on_cannot_judge` nor `on_error` (currently 13).
- No judged gate routes abstention to a state its other verdicts do not reach, unless that divergence is stated deliberately (currently 4 diverge accidentally, 6 more coincide only by accident of `on_error`).
- No path exists from an abstained gate to `commit` (currently 1).
- `ll-loop validate` flags the missing-both-routes condition (currently no rule).
- `harness_eval_abstention_rate()` has at least one non-test consumer (currently zero).

## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-21T19:06:54 - `8c9f6596-f570-42d1-a2a2-c4e750b706f8.jsonl`
- `/ll:capture-issue` - 2026-08-16T23:29:36 - `501abea1-df2c-4fca-aa0c-5bb8bbb6d4ba.jsonl`