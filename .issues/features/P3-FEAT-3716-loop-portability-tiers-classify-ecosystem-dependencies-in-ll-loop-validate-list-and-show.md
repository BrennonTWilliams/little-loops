---
id: FEAT-3716
type: FEAT
title: 'Loop portability tiers: classify ecosystem dependencies in ll-loop validate,
  list and show'
priority: P3
status: open
discovered_by: portability-review
discovered_date: '2026-10-03'
captured_at: '2026-10-03T22:42:15Z'
labels:
- loops
- validation
- portability
relates_to:
- FEAT-2248
- EPIC-3581
- FEAT-2354
- FEAT-3717
---

# FEAT-3716: Loop portability tiers: classify ecosystem dependencies in ll-loop validate, list and show

## Summary

Add a portability check to `ll-loop validate` that classifies every loop into a **portability tier**, based on what it needs at runtime beyond the `little-loops` wheel and a host CLI. Show the tier in `ll-loop list` / `ll-loop show`, and run it over the shipped catalog in CI. This turns the existing convention "a general-purpose loop must not couple its core to the Issue system; Issue integration is an optional adapter" (FEAT-2248 § Portability, EPIC-3581 § Out of scope, ENH-2862) into a check a machine can fail. Today the rule exists only in issue prose and project memory. No in-repo doc states it, and nothing checks it.

## Context

Captured 2026-10-03 from a portability review (ll-product hub session) of making FSM loops runnable standalone in a user's repo, with brainstorm as the pilot. Source-verified findings:

- The runtime already supports standalone runs. `ll-loop run <path>` works in a bare `git init` repo with no `ll-init` and no plugin (`fsm/loop_paths.py:46-48` explicit-path resolution; `.loops/` and `.ll/` created on demand at `cli/loop/run.py:390` and `session_store/schema.py:1722`). `import:` fragments fall back to the wheel's built-in library (`fsm/fragments.py:99-110`).
- `LL_PYTHON` is injected unconditionally into every shell-action env as `sys.executable` (`fsm/runners.py:333`, `runner_spec.py:335`). So `$${LL_PYTHON:-python3} -m little_loops.<mod>` always reaches the wheel's interpreter, and a bare `python3 -m little_loops.<mod>` reaches whatever `python3` is on PATH.
- **The coupling is invisible.** Census at `8baa8a471` (`grep -lE '/ll:|ll-issues|\.issues/'`): **39 of 97** top-level built-in loops reference `/ll:*` commands, the `ll-issues` CLI, or `.issues/` paths. Three `lib/` fragments (`cli.yaml`, `policy-router.yaml`, `prompt-fragments.yaml`) and three oracles (`oracle-capture-issue`, `resolve-decision`, `verify-confidence-scores`) do too. Nobody can tell which loops are portable without reading them.
- **Latent bug the check would catch on day one.** Three shipped loops call package modules through a bare interpreter: `fleet-loop-improve.yaml` (10 sites, `little_loops.fleet_improve`), `autodev.yaml:1419,1435` (`autodev_summary`), `oracles/integrate-node.yaml:62,138` (`rn_synth_queue`). Under `uvx`, `pipx`, or any venv where PATH `python3` is not the wheel's interpreter, these fail with `ModuleNotFoundError`.

Strategy tie-in (hub): B1 is "give away the loops, sell the trust", and the catalog sits on the open side of the open-core line (hub ENH-039, decided 2026-09-05). Today that is only partly true, because ~40% of the catalog needs the plugin and issue system. The hub's on-the-stack analysis names `ll-loops` (catalog extraction) as a candidate repo split. A tier stored as loop metadata survives that split; a tier that only exists in `validate` output does not.

## Current Behavior

- `ll-loop validate` checks structure, evaluators, reachability and shell safety (`fsm/validation/`). It does not classify external dependencies. The nearest check is the `/ll:<skill>` regex (`fsm/validation/_base.py:192`), which is used only for `tools:` allowlist consistency (`evaluator_rules.py:259-350`).
- `ll-loop list` entries carry `name, path, builtin, description, category, labels, visibility` (`cli/loop/info.py:395-403`). They have no dependency or portability field.
- Bare `python3 -m little_loops.*` passes validation silently.

## Expected Behavior

Each loop resolves to one tier. The tier is computed over the loop **after** fragment and `from:` resolution, so imported fragments and inherited states count, and it includes the tiers of its sub-loops (`loop:` references), taking the highest:

| Tier | Meaning | Detected by |
|---|---|---|
| `portable` | Needs only the wheel + a host CLI | none of the below |
| `requires-plugin` | Invokes plugin surface | `/ll:<name>` in prompt/action text |
| `requires-issues` | Needs an initialized issue system | `ll-issues` / other issue-system `ll-*` CLIs, `.issues/` paths, `scope:` containing `.issues/` |

- **Declared and verified.** An optional top-level `portability:` field (schema enum: the three tiers). When the field is present, `validate` errors if the detected tier is higher than the declared one, because a loop declared portable must stay portable. When it is absent, `validate` reports the detected tier at info level only, so existing loops do not break.
- **Optional-adapter states.** States reachable only from a declared adapter route (for example, brainstorm's `sink_issue` / `sink_decision` behind `route_sink` with default `sink: none`) do not raise the core tier. The loop reports `portable (adapters: requires-plugin)`. Declare these with a state-level `adapter: true` marker rather than guessing from reachability.
- **Interpreter rule.** A shell action that invokes `python`/`python3 -m little_loops.` without `LL_PYTHON` is a validation **warning** for every loop, whatever its tier, with a fix hint pointing at `$${LL_PYTHON:-python3}`.
- `ll-loop list` shows the tier (a column, plus `--json` field, plus a `--portability <tier>` filter). `ll-loop show` prints the tier and the evidence lines that set it.
- A CI corpus check over `scripts/little_loops/loops/` prints the tier distribution and fails if any loop declared `portable` regresses.

## Motivation

- Makes the decoupling rule enforceable. Today it depends on reviewers remembering a memory entry.
- Gives users a visible answer to "which loops can I run in my repo without adopting the issue system?"
- It is a prerequisite for `ll-loop export` (FEAT-3717), which has to know what it can bundle cleanly.
- It catches a real interpreter bug in three shipped loops.

## Proposed Solution

New rule module `fsm/validation/portability_rules.py` with `classify_portability(fsm, loops_dir) -> PortabilityReport(tier, adapter_tier, evidence: list[(state, field, match)])`. It reuses `_SKILL_INVOKE_RE` and walks resolved state text (`action`, `prompt`, evaluator prompts, `scope`). Sub-loop tiers are resolved through `resolve_loop_path` with a visited set to guard against cycles. Wire it into `load_and_validate`'s rule list, `cmd_validate` output, and the `info.py` catalog entry. Add `portability` (top-level enum) and `adapter` (state-level bool) to `fsm-loop-schema.json`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation/portability_rules.py` (new): `classify_portability()`, `PortabilityReport`
- `scripts/little_loops/fsm/validation/structural_rules.py`: register the rule in `load_and_validate` (runs after `resolve_fragments`)
- `scripts/little_loops/fsm/fsm-loop-schema.json`: top-level `portability` enum, state-level `adapter` bool, `portability_ignore`
- `scripts/little_loops/cli/loop/config_cmds.py`: `cmd_validate` output and `--json`
- `scripts/little_loops/cli/loop/info.py`: catalog entry field (~:395-403), `list` column and `--portability` filter, `show` evidence
- `scripts/little_loops/cli/loop/__init__.py`: `--portability` flag on `list`
- `scripts/little_loops/loops/fleet-loop-improve.yaml`, `autodev.yaml`, `oracles/integrate-node.yaml`: bare `python3 -m little_loops.*` → `$${LL_PYTHON:-python3}`
- `scripts/little_loops/loops/brainstorm.yaml`: `adapter: true` on `sink_issue` / `sink_decision` (coordinate with FEAT-3582)

### Dependent Files (Callers/Importers)
- `fsm/validation/_base.py:192` `_SKILL_INVOKE_RE` (reuse, don't fork)
- `fsm/fragments.py` `resolve_fragments` / `resolve_inheritance`; `fsm/loop_paths.py` `resolve_loop_path` (sub-loop tier walk)

### Similar Patterns
- `fsm/validation/evaluator_rules.py:259-350`: the existing `/ll:<skill>` vs `tools:` allowlist check
- `fsm/validation/reachability.py:70`: sub-loop `loop:` reference validation (walk pattern)

### Tests
- `scripts/tests/test_fsm_validation*.py` / new `test_portability_rules.py`: tier fixtures (direct, via fragment, via `from:`, via sub-loop, adapter-only, dynamic sub-loop, comment false-positive)
- `scripts/tests/test_builtin_loops.py`: corpus check (declared tiers validate; distribution recorded)

### Documentation
- `docs/guides/LOOPS_GUIDE.md`: decoupling rule and tiers (first in-repo statement of the rule)
- `docs/guides/LOOPS_REFERENCE.md`: `portability`, `adapter`, `portability_ignore` fields

### Configuration
- N/A

## Implementation Steps

1. Classifier + schema fields + fixtures (no CLI wiring); confirm census reproduces (39/97 top-level).
2. Interpreter warning; convert the three bare-interpreter loops in the same commit.
3. Wire into `validate` / `list` / `show`; mark brainstorm adapter states.
4. Corpus CI check; docs.

## Impact

- **Priority**: P3. Small, protects an existing invariant, and fixes a latent bug. Sequence it after the EPIC-3581 core chain (FEAT-3667 → FEAT-3582) so the brainstorm adapter marker lands with the rewrite rather than against the old loop.
- **Effort**: Small–medium. Most of it reuses fragment resolution and the existing regex.
- **Risk**: Low. Info-level for undeclared loops, so nothing existing breaks.
- **Breaking Change**: No.

## Use Case

A developer browsing `ll-loop list` wants a loop they can run in a client repo that has never run `ll-init`. Today they have to open each YAML and grep for `/ll:` and `ll-issues`. With tiers, `ll-loop list --portability portable` answers immediately. A loop author who declares `portability: portable` learns at `validate` time, not from a user's bug report, that a new state they added pulls in `/ll:capture-issue`.

## Acceptance Criteria

- [ ] `ll-loop validate <loop>` prints `Portability: <tier>` (plus adapter tier when present); `--json` includes `portability` with evidence.
- [ ] Declared `portability: portable` on a loop that references `/ll:capture-issue` in a non-adapter state → validation error naming the state and match.
- [ ] Tier accounts for imported fragments, `from:` inheritance and sub-loops (fixture: a portable-looking loop whose imported fragment calls `ll-issues` → `requires-issues`).
- [ ] Bare `python3 -m little_loops.X` in a shell action → warning with fix hint. `fleet-loop-improve.yaml`, `autodev.yaml` and `oracles/integrate-node.yaml` are converted to `$${LL_PYTHON:-python3}` in the same change.
- [ ] Brainstorm's `sink_issue` / `sink_decision` marked `adapter: true`. `ll-loop validate brainstorm` reports `portable (adapters: requires-plugin)`. Coordinate the marker with FEAT-3582 so the rewritten loop keeps it.
- [ ] `ll-loop list` shows the tier column and supports `--portability`. `ll-loop show` lists evidence lines.
- [ ] CI corpus test asserts that every loop with a declared tier validates, and records the tier distribution.
- [ ] Loop authoring docs (`docs/guides/LOOPS_GUIDE.md`) state the decoupling rule and the tiers. This is the rule's first in-repo home.

## Edge Cases

- `/ll:` text inside a comment, a `description:`, or an example in a prompt that says "do not run /ll:..." gives false positives. Match only action/prompt bodies, and allow a per-state `portability_ignore:` escape hatch with a required reason.
- Interpolated sub-loop names (`loop: ${context.child}`) cannot be resolved statically, so report the tier as `unknown (dynamic sub-loop)` rather than guessing.
- `ll-*` CLIs that are wheel console scripts (e.g. `ll-loop`, `ll-history`) are portable. Only issue-system and plugin-dependent commands raise the tier, so keep an explicit allowlist rather than flagging every `ll-` prefix.

## Related Key Documentation

- FEAT-2248 § Portability (origin of the decoupling rule)
- EPIC-3581 § Out of scope ("Core must stay decoupled from the Issue system")
- FEAT-2354 § Portability & Lock-in Analysis
- FEAT-3717: `ll-loop export` (consumes this classification)
- Hub: `ll-product/docs/architecture/little-loops-on-the-stack/` §2 (EPIC-397 "advertised surface not mechanically checked"), §6 `ll-loops` extraction

## Labels

`loops`, `validation`, `portability`

## Status

**Open** | Created: 2026-10-03 | Priority: P3
