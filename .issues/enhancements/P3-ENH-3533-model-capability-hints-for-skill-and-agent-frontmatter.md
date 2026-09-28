---
id: ENH-3533
type: ENH
title: Model capability hints for skill and agent frontmatter
priority: P3
status: open
parent: EPIC-3563
epic: EPIC-3563
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T00:20:40Z'
labels:
- multi-host
blocked_by:
- BUG-3640
decision_needed: false
confidence_score: 90
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3533: Model capability hints for skill and agent frontmatter

## Summary

Extend ENH-3527's `model_hint` vocabulary (`coding`, `reasoning`, `burst`) from loop states to skill and agent frontmatter. `model_hint` becomes the portable declaration; generated mirrors for non-Claude hosts resolve it at `ll-adapt` time, and a literal `model:` survives only as the Claude Code pin, checked for agreement with the hint. Deferred from ENH-3527 because accepting a frontmatter key does not establish that the host honors it.

## Current Behavior

- Claude Code serves skills and agents natively; there is no little-loops model-resolution step at invocation time.
- `ll-adapt` writes generated mirrors into the **plugin root** (`cli/adapt.py`: `plugin_root / config_dir / "agents"`), and those mirrors are committed and ship with the plugin. They are not generated per consuming project.
- The Claude-alias leak (`model = "sonnet"` in `.codex/agents/*.toml`) was fixed by **BUG-3640** (done, `4bd11c089`): `_is_claude_model` (`core.py`) makes `_select_frontmatter_fields` and `CodexEmitter.emit_agent` (`adapters/codex.py:430`) drop a Claude alias / `claude-*` `model:`, and `_format_agent_toml` omits an empty model. Non-Claude literals still pass through verbatim. This issue builds on that seam.
- `resolve_model_hint` (`host_runner.py:153`) has built-in mappings only for `claude-code`, `anthropic-api` and the test-only fake hosts (`_BUILTIN_HINT_MAPPINGS`, `host_runner.py:134-138`). Codex, Gemini, Kimi-Code and Qwen have none by design (EPIC-3563 scope: "Out: built-in mappings for non-Claude hosts"), so resolution for them raises `ModelHintError` unless `orchestration.model_hints` supplies a value.

## Expected Behavior

- A skill or agent may declare `model_hint: <coding|reasoning|burst>`. Unknown hints are errors.
- A literal `model:` may appear alongside `model_hint` **only** as the Claude Code pin, and it must be the exact alias `resolve_model_hint(hint, backend="claude-code")` returns (case-insensitive: `coding` → `sonnet`). A mismatch, a concrete ID (`claude-sonnet-*`) or `inherit` next to a hint is a validation error. `model:` with no `model_hint` keeps today's behavior.
- When generating mirrors, each host gets `resolve_model_hint(hint, backend=<host>, overrides=None)`. Built-in mappings only: generated mirrors are shipped plugin content, so they must not depend on the maintainer's `.ll/ll-config.json` or `.ll/ll.local.md`.
- A resolved `model:` is written only into artifacts whose host reads the field: `"model"` in that host's `frontmatter_fields_read` for skill mirrors, and Codex agent TOML (whose `model` key is written by `_format_agent_toml`). No host's `frontmatter_fields_read` includes `model` today, and this issue does not add it, so every non-Claude **skill** mirror omits `model` silently, with no warning, because the host doesn't read it.
- An artifact that does read `model` but whose host has no built-in mapping (today: Codex agents) gets **no model field**, so the host uses its own default, and `ll-adapt` prints a warning naming the hint and host. Warnings are **aggregated per host per hint** (e.g. "`coding` unmapped for codex; 9 agents omit `model`"), not one line per file. They go to stderr, are suppressed by `quiet=True`, and are not a hard error, so `ll-adapt --apply` still completes.
- Gemini's reduced-mode agent output (`_emit_degraded_agent`) carries no frontmatter, so Gemini agents are "unsupported, omitted" by construction. Gemini *skill* mirrors follow the general rule.
- `model_hint` itself is never emitted into a generated mirror (skills, agents, **or commands**, on every generated host).

**What this delivers today:** a portable declaration plus an enforced Claude-pin consistency check. With no built-in non-Claude mappings, Codex agents resolve to "omitted + warning" and every other generated artifact omits `model` silently. The payoff for those hosts arrives when a built-in mapping is added to `_BUILTIN_HINT_MAPPINGS`. ENH-3642 (deferred) proposes one for Codex that uses host-default model plus reasoning effort, not a concrete ID; its spike decides whether Codex agent TOML can carry that selection. The mirrors then pick it up on the next `ll-adapt --apply`, and the staleness gate forces that regeneration.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

**Option A**: Generation-time resolution only, through the existing `ll-adapt` adapter path. Extend `CodexEmitter.emit_agent` (`adapters/codex.py:430`) to call `resolve_model_hint()` alongside the existing literal-`model` passthrough, and add the same resolution to the Kimi/Qwen emitters and the shared skill path. Claude Code itself keeps reading `agents/*.md`/`skills/*/SKILL.md` frontmatter natively. `ClaudeCodeEmitter.emit_skill/emit_command/emit_agent` are declared no-ops (`claude_code.py:30-40`) because "the plugin marketplace serves skills natively", so no little-loops code sits between the source file and Claude Code's own parser.

> **Selected:** Option A — the only path that reuses an existing seam (`emit_agent`, `resolve_model_hint`, `_select_frontmatter_fields`); Option B has no interception point or source-rewrite precedent anywhere in the codebase.

**Option B**: Resolve `model_hint` for Claude Code's own native invocation too, by rewriting the resolved concrete model into source frontmatter before Claude Code reads it. No such mechanism exists: `hooks/hooks.json` has no `Skill`/`Task` matcher, and no code under `scripts/little_loops/` writes back into the source `skills/`/`agents/` trees.

### Decision Rationale

**Selected**: Option A — generation-time resolution through the existing `ll-adapt` adapter path. Native Claude Code invocation is out of scope for resolution. Claude Code reads the literal `model:` pin, which validation keeps consistent with the hint.

**Reasoning**: Option A reuses one established seam: each host's `emit_agent`/`emit_skill`, the ENH-3527 resolver, and the `_read_frontmatter` → `process_agents`/`process_skills` pipeline. Option B requires an interception point before Claude Code's own frontmatter read and a write path into the source tree, neither of which exists. It would also work against the "plugin marketplace serves skills natively" boundary (`claude_code.py:30-40`).

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 1/3 |
| Simplicity | 2/3 | 0/3 |
| Testability | 3/3 | 1/3 |
| Risk | 2/3 | 0/3 |
| **Total** | **9/12** | **2/12** |

### Design Refinements (review 2026-09-28)

These refinements close gaps in Option A as first written:

1. **Pin coexistence, not mutual exclusivity.** The original acceptance criterion made `model` + `model_hint` an error. Because Claude Code only reads `model:`, that would have forced every adopting file to lose its Claude Code model selection. The rule is now **agreement**: `model` must equal the hint's `claude-code` resolution.
2. **No config at generation time.** Always call `resolve_model_hint(..., overrides=None)`. Reading `orchestration.model_hints` would bake the maintainer's machine config into shipped mirrors, never apply a consumer's overrides, and make `test_host_artifacts_are_not_stale` machine-dependent.
3. **No mapping → omit + warn.** Catch `ModelHintError` for a *missing mapping* only, then omit the field and warn. An unknown hint, or an unknown backend, is still an error.
4. **Skills are in scope.** Resolution applies to `emit_skill` mirrors as well as `emit_agent`. It uses the same frontmatter-rewrite seam BUG-3640 introduces in `_select_frontmatter_fields`. Writing the resolved value is gated by refinement 15.
5. **Gemini agents: unsupported, omitted.** No change to `_emit_degraded_agent` beyond confirming that it emits no model.
6. **Validation lives in the adapter path, not `ll-verify-skills`.** One helper validates in `process_agents`/`process_skills`, and a pytest walks the real `agents/` and `skills/` trees. `ll-verify-skills` is scoped to SKILL.md line counts and doesn't cover `agents/`. Extending it would change its documented scope in ~6 places for no gain.
7. **One exception boundary.** `process_agents`/`process_skills` convert `ModelHintError` to `AdapterError`. They already catch `AdapterError`, so both CLIs (`ll-adapt`, `ll-adapt-agents-for-codex`) and the staleness test get clean per-file errors with no CLI-level try/except.
8. **Staleness needs no new gate.** With built-in-only resolution, a mapping change is a code change to `_BUILTIN_HINT_MAPPINGS`. The existing `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` then fails until the mirrors are regenerated. This only bites the real tree once at least one shipped file declares `model_hint`, which is why step 7 (migrate one agent + one skill) is mandatory.

Added in the 2026-09-28 second review:

9. **Distinguish "unmapped" from other `ModelHintError`s.** `resolve_model_hint` raises the same class for a missing mapping, unknown backend, unsupported backend (opencode/pi) and a config-disabled hint. Add `class ModelHintUnmappedError(ModelHintError)` in `host_runner.py`, raised only at the `builtin is None` branch (signature unchanged). `_resolve_frontmatter_model` catches that subclass only: omit + record for the aggregated warning. Never match on message text.
10. **Backend and warning plumbing.** `_select_frontmatter_fields(content, name, fields_read)` has no `fm`, backend or `quiet`, and the skill path reaches it through `(content, name)` lambdas (`kimi.py:68`, `qwen.py:72`, `omp.py:73`). Emitters resolve the model themselves via `_resolve_frontmatter_model` and pass the result in as a new optional parameter. `_select_frontmatter_fields` only applies it: it strips any Claude-alias `model:`, then writes the resolved `model:` if not `None`. The `model_hint:` strip is **unconditional** (refinement 16), not tied to this parameter. Warning accumulation lives with the emitter/`process_*` layer, not the string helper (refinement 18).
11. **Pin must be the exact alias (revised in the third review).** Compare `pin.strip().lower()` against `resolve_model_hint(hint, backend="claude-code")`. Do **not** normalize through `resolve_model_alias`. The earlier normalizing rule was wrong in its own example: `MODEL_ALIASES["sonnet"]` is `claude-sonnet-5`, so a `claude-sonnet-5-5` pin would have *disagreed*. It would also tie validation to `MODEL_ALIASES`, so every concrete-ID pin next to a hint would start failing when the table moves. A concrete ID or `inherit` next to a hint is an error. Case differences (`Sonnet`) are allowed. All 19 shipped pins are already bare aliases, so this rule costs nothing.
12. **Pin presence.** Claude Code reads only `model:`, so a hint with no pin has no effect on the primary host. `_validate_model_decl` stays lenient (hint-only is valid for consumer files). The real-tree pytest over `agents/` + `skills/` additionally requires a pin wherever a shipped file declares a hint.
13. **Validation order.** In `process_skills`, call `_validate_model_decl` before the `disable-model-invocation` skip so a skipped skill with a bad hint still errors.
14. **omp is a generated host.** `omp` is in `GATED_HOSTS` and passes skills/agents through `_select_frontmatter_fields` (`omp.py:73,122`). It goes through the same shared rewrite (hint stripped, no model emitted) and is covered by the "never emitted" test. It is not a "confirm or document" item. **This repo has no tracked `.omp/` mirror** (`test_host_artifacts_are_not_stale` returns early for omp when `.omp/` is absent), so omp coverage is unit tests only. Step 7 must **not** run `ll-adapt --host omp --apply`, which would create a whole new mirror tree.

Added in the 2026-09-28 third review:

15. **Emit `model` only where the host reads it.** No host's `frontmatter_fields_read` (`capabilities.py`) includes `model`, and nothing here verifies that Kimi, Qwen, Gemini, omp or Codex skills honor a `model:` key. Widening `fields_read` would claim support nobody has checked, which is the reason ENH-3527 deferred this issue. So `_resolve_frontmatter_model` is consulted for skill mirrors only when `"model" in fields_read` for that host. Codex agent TOML is the one artifact that already carries a `model` key (`_format_agent_toml`). `frontmatter_fields_read` is **not** changed by this issue. The unmapped-hint warning fires only for artifacts that read `model` (today: Codex agents). Otherwise every `ll-adapt` run would warn for 4 hosts until mappings exist. A future issue that verifies a host reads `model` adds it to that host's `fields_read`, and resolution starts reaching those mirrors with no further code change.
16. **Strip `model_hint:` unconditionally in `_select_frontmatter_fields`.** Every generated skill and command mirror passes through that helper, including Codex skills (`codex.py:105`, which the earlier Integration Map omitted) and commands (`kimi.py:93`). An unconditional strip makes "never emitted" hold everywhere, commands included, even though command validation is out of scope. Codex agent TOML never copies frontmatter keys, so it needs no strip.
17. **The staleness gate must also assert no errors.** `test_host_artifacts_are_not_stale` asserts `adapted == 0` but discards `_errors`, so a shipped file with an invalid hint passes it. Add `assert errors == 0` alongside the existing assertion. This backs up the real-tree walker.
18. **Warning plumbing is concrete.** `process_*` returns `tuple[int, int, int]`, and `cli/adapt.py` depends on that shape, so the return type stays unchanged. The emitter instance collects a `Counter[tuple[str, str]]` of `(host, hint)` omissions via `_resolve_frontmatter_model`. `process_agents`/`process_skills` print one summary line per key to **stderr** after the walk, and none when `quiet=True`. That keeps the staleness test and `--dry-run` quiet.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — add `_validate_model_decl(fm: dict) -> None` (unknown-hint + exact-alias pin check per refinement 11, raises `AdapterError`) and `_resolve_frontmatter_model(fm: dict, backend: str) -> str | None` (hint → host model via `resolve_model_hint(..., overrides=None)`; `None` + recorded omission on `ModelHintUnmappedError`; falls back to BUG-3640's literal-`model` rule when no hint). Callers consult it only for artifacts that read `model` (refinement 15). `process_agents`/`process_skills` print the aggregated warning summary to stderr after the walk unless `quiet` (refinement 18). Call `_validate_model_decl` in `process_agents` (`:565`) and `process_skills` (`:435`) right after `_read_frontmatter`. Convert `ModelHintError` → `AdapterError` in both.
- `scripts/little_loops/host_runner.py:~180` — add `ModelHintUnmappedError(ModelHintError)`, raised where `_BUILTIN_HINT_MAPPINGS.get(backend)` is `None` (refinement 9).
- `scripts/little_loops/adapters/core.py:120` — `_select_frontmatter_fields` (with the BUG-3640 `_is_claude_model` alias-strip already inside it): gains an optional resolved-model parameter (refinement 10); strips `model_hint:` **unconditionally** (refinement 16) and writes the resolved `model:` only when one is passed in.
- `scripts/little_loops/adapters/omp.py:62-73,109-122` — route skill and agent emission through the same rewrite (refinement 14).
- `scripts/little_loops/adapters/codex.py:430` — `CodexEmitter.emit_agent`: `model = _resolve_frontmatter_model(fm, "codex") or ""`; `_format_agent_toml` omits the line when empty (from BUG-3640). This is the only artifact that receives a resolved model today (refinement 15).
- `scripts/little_loops/adapters/codex.py:105` — Codex skill mirrors go through `_select_frontmatter_fields`, so the unconditional strip covers them. No model is written because `model` is not in Codex's `fields_read` (refinement 16).
- `scripts/little_loops/adapters/kimi.py:111-126`, `qwen.py:128-145` — `emit_agent`/`emit_skill` pass the host backend key to the shared rewrite. The resolved model is written only when `"model" in fields_read` (not today).
- `scripts/little_loops/adapters/gemini.py:81` — `emit_skill` via the shared rewrite. `emit_agent` (`:131-138`, degraded) needs no change.
- `scripts/tests/test_wiring_skills_and_commands.py:474-524` — `test_host_artifacts_are_not_stale`: add `assert errors == 0` (refinement 17).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:153` — `resolve_model_hint`, `ModelHintError`, `hint_backend_keys()`; signature unchanged. Existing callers: `fsm/executor.py:3687,3704`.
- `scripts/little_loops/cli/adapt.py:132`, `cli/adapt_agents_for_codex.py:125-127` — call `process_agents`; covered by the `AdapterError` conversion (refinement 7), no edit.
- `scripts/little_loops/adapters/capabilities.py` — `frontmatter_fields_read` per host. **No change**: it becomes the gate for writing a resolved model (refinement 15), and no host is verified to read `model` today.
- `scripts/little_loops/cli/verify_triggers.py:24,347` — imports `_is_model_invocation_disabled` from `adapters.core`; must be undisturbed by the new helpers.
- `scripts/little_loops/adapters/omp.py` — excluded from `process_agents` degraded emission (`core.py:589-593` comment; degraded-emission gate in `process_agents`), so it emits agents verbatim via `emit_agent`. Both skill and agent emission must go through the shared rewrite (refinement 14).

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — new row/column: which hosts resolve a frontmatter `model_hint` (Codex agents: resolved, omitted + warning until a built-in mapping exists; skill mirrors: omitted until the host is verified to read `model`; Gemini agents: unsupported).
- `docs/reference/CLI.md:5827` — `ll-adapt-agents-for-codex` TOML output: `model` is resolved from `model_hint` or omitted.
- `docs/reference/CONFIGURATION.md` (`orchestration.model_hints`, ~line 1370) — state explicitly that frontmatter hints ignore this override (built-in mappings only).
- `docs/reference/API.md` (~11330-11385, `little_loops.adapters`) — `model_hint` handling in the per-emitter table; `ModelHintError` surfaces as `AdapterError`.
- `CONTRIBUTING.md` — authoring note: `model_hint` + optional agreeing `model:` pin.

### Tests
- `scripts/tests/test_adapters.py` — per emitter (Codex agent + skill, Kimi agent/skill/command, Qwen agent/skill, Gemini skill, omp skill/agent): `model_hint` never emitted. Codex agent: hint resolves on a monkeypatched mapping; omitted + aggregated warning when unmapped. Skill mirrors: no `model` written with the real `fields_read`, and no warning. With `model` monkeypatched into a host's `fields_read` plus a mapping, the resolved `model:` is written (proves the refinement 15 gate opens). `TestGeminiEmitterEmitAgent` `_meta()` (`:1046-1056`): assert no model in degraded output.
- `scripts/tests/fixtures/adapt/agent_cases.json` + `test_adapt_golden_corpus.py:156-176` — add a `model_hint` case without perturbing the existing byte-identical cases.
- New validation tests for `_validate_model_decl`: unknown hint → error; `model_hint: coding` + `model: sonnet` → ok; `model_hint: coding` + `model: haiku` → error. Template: `test_model_hints.py::TestStructuralValidation.test_invalid_vocabulary_and_exclusivity` (`:260-266`).
- A pytest walking real `agents/*.md` and `skills/*/SKILL.md` that runs `_validate_model_decl` on each (the in-repo gate for refinement 6).
- `process_agents`/`process_skills`: an unknown hint yields an `errors` count increment, not a traceback.
- Resolution-reaches-artifact matrix: mirror `test_model_hints.py::TestHostArgv` (`:953-1023`) / `TestPortabilityProof` (`:1039-1091`). Emitters hard-code their backend, so the `fake` backend never reaches them. For the positive path use `monkeypatch.setitem(_BUILTIN_HINT_MAPPINGS, "<host>", {h: f"x-{h}" for h in MODEL_HINTS})` per host (codex, gemini skills, kimi-code, qwen, omp). Skill-mirror hosts also need `model` monkeypatched into their `frontmatter_fields_read` (refinement 15). Negative path: leave the host unmapped and assert omission; the aggregated warning appears only for artifacts that read `model`.
- Pin cases for `_validate_model_decl` (refinement 11): `Sonnet` (ok, case-insensitive), `claude-sonnet-5` and `claude-sonnet-5-5` next to `model_hint: coding` (**error**: concrete IDs are rejected), `inherit` (error), and a hint with no pin (valid).
- Warning plumbing (refinement 18): two Codex agents with the same unmapped hint → exactly one stderr summary line with count 2; `quiet=True` → no output; `process_*` return shape unchanged.
- `test_host_artifacts_are_not_stale`: a fixture tree with an invalid hint makes the gate fail through the new `errors == 0` assertion (refinement 17).
- Real-tree walker additionally asserts a pin is present wherever a shipped file declares `model_hint` (refinement 12).
- Ordering test: a `disable-model-invocation: true` skill with an unknown hint still yields an error (refinement 13).
- `ModelHintUnmappedError` is raised for a missing mapping only; unknown/unsupported backend and config-disabled hints raise plain `ModelHintError` and surface as `AdapterError`.
- `test_wiring_skills_and_commands.py:474-524` (`test_host_artifacts_are_not_stale`) — existing staleness gate, now also asserting `errors == 0`; must pass after regeneration.

### Dropped touchpoints (from earlier wiring passes)
Refinements 6 and 7 remove these: `cli/docs.py` `main_verify_skills` + its help text, `doc_counts.py:_parse_skill_frontmatter`, `frontmatter.py:parse_skill_frontmatter`, `cli/doctor.py:943`, `init/writers.py:238`, `CONTRIBUTING.md:691,707` (verify-skills wording), `skills/configure/areas.md:862`, `scripts/little_loops/loops/mechanize-skills.yaml:503`, `scripts/pyproject.toml:92`, `cli/__init__.py:64,156`, `test_cli_docs.py::TestMainVerifySkills`, `test_skill_size_checker.py`, `test_doc_counts.py::TestCheckSkillBudget`, and CLI-level try/except in `cli/adapt.py`/`cli/adapt_agents_for_codex.py`. Refinement 2 removes `config-schema.json:1819-1832` (no new consumer of `orchestration.model_hints`).

## Implementation Steps

0. **Pre-implementation checks (before writing code).**
   - Settle the uncommitted working-tree change that removes `model: sonnet` from 10 `skills/*/SKILL.md` files (audit-issue-conflicts, confidence-check, spike, and others). Land or revert it first, since it decides which skills carry a pin. Either way, `skills/map-dependencies/SKILL.md` (`model: sonnet`) keeps its pin and is a safe Step 7 target.
   - Confirm Claude Code tolerates an unknown `model_hint:` key: put it on a scratch agent and a scratch skill, run `claude plugin validate`, and check that both register and run on their `model:` pin. If Claude Code rejects the key, stop and re-scope; do not ship migrated files.
1. BUG-3640 is done (`4bd11c089`); build on its `_is_claude_model` predicate, omit-when-empty Codex TOML rule, and the `model:` strip in `_select_frontmatter_fields`.
2. Add `ModelHintUnmappedError` to `host_runner.py`. Add `_validate_model_decl` and `_resolve_frontmatter_model` to `adapters/core.py`. Wire validation into `process_agents`/`process_skills` (in `process_skills`, before the `disable-model-invocation` skip) with `ModelHintError` → `AdapterError`.
3. Make the `model_hint:` strip in `_select_frontmatter_fields` unconditional (covers Codex skills and all commands). Route every generated-host emitter through `_resolve_frontmatter_model` (Codex agent; Kimi/Qwen/omp agent + skill; Gemini skill). Pass the result into `_select_frontmatter_fields` only when the artifact reads `model` (refinement 15). Collect unmapped omissions on the emitter and print one stderr summary per host per hint unless `quiet` (refinement 18).
4. Leave `frontmatter_fields_read` unchanged (refinement 15). Add `assert errors == 0` to `test_host_artifacts_are_not_stale` (refinement 17).
5. Tests per the Tests list (TDD: write the failing tests first).
6. Docs per the Documentation list.
7. **Mandatory:** migrate one agent (e.g. `agents/codebase-locator.md` → `model_hint: coding` + `model: sonnet`) and one skill that keeps a pin (e.g. `skills/map-dependencies/SKILL.md` → `model_hint: coding` + `model: sonnet`), then `ll-adapt --host <codex|gemini|kimi-code|qwen> --apply` so the committed mirrors match. **Not omp**: this repo tracks no `.omp/` mirror (refinement 14). This is the only real-tree proof of tolerance, pin agreement and staleness.

## Impact

- **Priority**: P3.
- **Effort**: Medium.
- **Risk**: Low-Medium — generated mirrors only; the staleness gate already enforces regeneration.

## Resolved Questions

- **Resolution timing** → generation time only (Option A). Native Claude Code reads the literal `model:` pin, kept consistent by validation.
- **Staleness** → built-in-only resolution makes a mapping change a code change; `test_host_artifacts_are_not_stale` enforces regeneration (refinement 8).
- **Claude-native path** → no `ll-adapt` materialization for Claude Code. The `/ll:spike` on native hint support is not needed under Option A: Claude Code does not have to honor `model_hint`, only tolerate it as an unknown key. Verify that tolerance **before implementing** (Implementation Step 0), not on the first migrated file: it still registers under `/ll:*` / the Agent list and runs on its `model:` pin. If Claude Code rejects the key, stop, ship no migrated files, and record that here.

## Acceptance Criteria

- [ ] Every artifact/host combination claimed as supported has an executable test proving the resolved model reaches the host artifact, or that the field is omitted with a warning where no mapping exists.
- [ ] Unknown hints are errors. A `model:` next to `model_hint` must be the exact `claude-code` alias (case-insensitive); a different alias, a concrete `claude-*` ID or `inherit` is an error.
- [ ] Generated-mirror resolution never reads `orchestration.model_hints` / `.ll/ll.local.md` (test: an override in config does not change emitted output).
- [ ] `model_hint` never appears in any generated mirror, commands and Codex skills included.
- [ ] A resolved `model:` is written only into artifacts whose host reads `model` (`frontmatter_fields_read`, or Codex agent TOML); `frontmatter_fields_read` is unchanged.
- [ ] An unresolvable hint surfaces as a per-file `ll-adapt` error, not a traceback.
- [ ] Generated-file staleness after a mapping change is caught by `test_host_artifacts_are_not_stale`, which also asserts `errors == 0`.
- [ ] Migration of at least one shipped agent and one shipped skill is done with mirrors regenerated (`ll-adapt --apply`), and the real-tree walker passes (pin present and agreeing).
- [ ] omp skill and agent mirrors strip `model_hint` and emit no model (covered by the "never emitted" test).
- [ ] Unmapped-host warnings are aggregated per host per hint, go to stderr, are silent under `quiet=True`, and fire only for artifacts that read `model`. Only a missing mapping (`ModelHintUnmappedError`) is downgraded to omit + warn.
- [ ] Claude Code tolerance of an unknown `model_hint:` key is confirmed before implementation and recorded under Resolved Questions.

## Scope Boundaries

- **In scope**: `model_hint` in skill and agent frontmatter; generation-time resolution for codex, gemini (skills), kimi-code, qwen, omp, written only where the host reads `model`; pin-agreement validation; tests per claimed combination.
- **Prerequisites**: ENH-3527 (done — resolver); BUG-3640 (alias stripping + model-rewrite seam).
- **Out of scope**: new hint vocabulary; built-in hint mappings for non-Claude hosts (ENH-3642 for Codex; concrete non-Claude model IDs are out per EPIC-3563); consumer-project config overrides for shipped mirrors; resolution at Claude Code native invocation; migrating every shipped skill/agent.

## Program Design

### Types

- `model_hint: str | None` — optional frontmatter key; value in `host_runner.MODEL_HINTS`.
- `model: str | None` — when present with `model_hint`, `model.strip().lower()` must equal `resolve_model_hint(model_hint, backend="claude-code")` (exact alias, no `resolve_model_alias` normalization).

### Signatures

- `_validate_model_decl(fm: dict) -> None` — new in `adapters/core.py`; raises `AdapterError` on unknown hint or pin mismatch.
- `_resolve_frontmatter_model(fm: dict, backend: str) -> str | None` — new in `adapters/core.py`; returns the host model, or `None` to omit.
- `CodexEmitter.emit_agent(self, agent_meta: dict) -> str` — existing (`codex.py:430`); model comes from `_resolve_frontmatter_model(fm, "codex")`.
- `resolve_model_hint(hint: str, *, backend: str, overrides: dict | None = None) -> str` — existing (`host_runner.py:153`); called with `overrides=None`.
- `process_agents(emitter, agents_dir, output_dir, apply, quiet, only=None) -> tuple[int, int, int]` — existing (`core.py:565`); gains validation + `ModelHintError` → `AdapterError`.

### Call Path

- `process_agents` → `_validate_model_decl` → `CodexEmitter.emit_agent` → `_resolve_frontmatter_model` → `resolve_model_hint` → `.codex/agents/<name>.toml`
- `process_skills` → `_validate_model_decl` → `QwenEmitter.emit_skill` → `_resolve_frontmatter_model` → `resolve_model_hint` → `.qwen/skills/<name>/SKILL.md`

## Verification Notes

Refreshed 2026-09-28 (supersedes the 2026-09-24 check): ENH-3527 is done; `resolve_model_hint`, `ModelHintError`, `MODEL_HINTS`, `_BUILTIN_HINT_MAPPINGS` exist in `host_runner.py` (`:121-192`). The Codex emitter class is `CodexEmitter` (`codex.py:329`), not `CodexAdapter`. `ll-adapt` output lands under the plugin root (`cli/adapt.py`). Committed mirrors confirm the alias leak (`.codex/agents/codebase-analyzer.toml:4` `model = "sonnet"`), now tracked as BUG-3640.

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item). `/ll:verify-issues ENH-3533 --auto`, 2026-09-28: every `file:line` citation in the Codebase Research Findings, Integration Map, Program Design, and Dropped-touchpoints list was checked against the current tree (all `adapters/*.py`, `host_runner.py`, `cli/*.py`, `capabilities.py`, doc/schema files, and the cited test classes/functions) — all confirmed accurate except two stale citations in the Dropped-touchpoints line, now corrected in place: `loops/mechanize-skills.yaml:503` → `scripts/little_loops/loops/mechanize-skills.yaml:503` (the file lives under `scripts/little_loops/loops/`, not a top-level `loops/`); `cli/doctor.py:238,943` → `cli/doctor.py:943` (line 238 is an unrelated `print("  (none found)")`; only line 943, the `check_skill_sizes()`/`ll-verify-skills` adapter docstring, is a real touchpoint). `ll-verify-evidence` found no fabricated quotes. No active required decision rules. Dependency check (§2E) found `blocked_by: BUG-3640` (status was open at that time, so unsatisfied) had no reciprocal `## Blocks` entry on BUG-3640 — fixed by adding one there in this pass. BUG-3640 has since completed (`4bd11c089`), so that edge is now satisfied (see the 2026-09-28 re-check below). B6 proposal-vs-code check: the planned `ModelHintError` → `AdapterError` conversion lands inside `process_agents`/`process_skills`' existing per-file `except AdapterError` blocks (`core.py:477,550,628,670`), so no exception-handler gap.

Re-check 2026-09-28 (after BUG-3640 landed), `/ll:verify-issues ENH-3533 --auto`: verdict at time of check **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item). Re-checked every `file:line` citation against the current tree: `codex.py:430` (`CodexEmitter.emit_agent`), `host_runner.py:134-138`/`:153`/`:186` (`_BUILTIN_HINT_MAPPINGS`, `resolve_model_hint`, the `builtin is None` branch the new `ModelHintUnmappedError` attaches to), `core.py:120,435,565` and the four `except AdapterError` sites (`:477,550,628,670`), `kimi.py:111-126`, `qwen.py:128-145`, `omp.py:62-73,109-122`, `gemini.py:81,131-138`, `fsm/executor.py:3687,3704` — all accurate. Two stale items corrected in place: the `CodexEmitter` class line (`codex.py:328` → `:329`), and the prior note's "BUG-3640 status: open" claim (BUG-3640 is now `done`). The frontmatter `blocked_by: BUG-3640` edge is a satisfied edge (`done`), so it is informational and needs no backlink. The Step 0 working-tree premise still holds (10 `skills/*/SKILL.md` modified, uncommitted). `ll-verify-evidence` clean; no active required decision rules; no new B6 findings.
Graph: `ll-code` provider=`codegraph` freshness=`fresh` (used only to cross-check anchors; all confirmed by direct Grep).

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-28 (re-scored after BUG-3640 landed)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- ~~Unresolved `blocked_by` dependency: BUG-3640~~ — resolved: BUG-3640 is done (`4bd11c089`), verified by `/ll:ready-issue` 2026-09-28.

## Session Log
- `/ll:confidence-check` - 2026-09-28T21:57:32 - `8c4886b8-e5fe-4392-8c81-999e92290df1.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:55:16 - `5f779b40-d61a-4af9-929a-1df2e6a1dc35.jsonl`
- `/ll:ready-issue` - 2026-09-28T21:47:46 - `fbc10432-1400-4e81-b8f4-4b69027756de.jsonl`
- `/ll:confidence-check` - 2026-09-28T21:08:24 - `7f294095-d1d9-4ee9-9b43-311d4ce2c57c.jsonl`
- `/ll:verify-issues` - 2026-09-28T21:01:34 - `6ee1f8dc-4aaf-4326-9a2c-971c5336e607.jsonl`
- `/ll:wire-issue` - 2026-09-28T20:07:49 - `05090d65-2eac-41cf-a99d-d360b8ff23dc.jsonl`
- `/ll:decide-issue` - 2026-09-28T19:46:46 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:refine-issue` - 2026-09-28T19:41:20 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:wire-issue` - 2026-09-28T19:35:30 - `f552ed04-ad08-4162-b169-daaec37f3df4.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
