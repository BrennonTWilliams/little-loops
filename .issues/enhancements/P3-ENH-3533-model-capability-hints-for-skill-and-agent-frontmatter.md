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
---

# ENH-3533: Model capability hints for skill and agent frontmatter

## Summary

Extend ENH-3527's `model_hint` vocabulary (`coding`, `reasoning`, `burst`) from loop states to skill and agent frontmatter. `model_hint` becomes the portable declaration; generated mirrors for non-Claude hosts resolve it at `ll-adapt` time, and a literal `model:` survives only as the Claude Code pin, checked for agreement with the hint. Deferred from ENH-3527 because accepting a frontmatter key does not establish that the host honors it.

## Current Behavior

- Claude Code serves skills and agents natively; there is no little-loops model-resolution step at invocation time.
- `ll-adapt` writes generated mirrors into the **plugin root** (`cli/adapt.py`: `plugin_root / config_dir / "agents"`), and those mirrors are committed and ship with the plugin. They are not generated per consuming project.
- `CodexEmitter.emit_agent` (`adapters/codex.py:444`) copies `model` verbatim; Kimi/Qwen agents and every host's skill mirrors pass `model:` through `_select_frontmatter_fields` unchanged. The resulting Claude-alias leak (`model = "sonnet"` in `.codex/agents/*.toml`) is split out as **BUG-3640**, which this issue builds on.
- `resolve_model_hint` (`host_runner.py:153`) has built-in mappings only for `claude-code`, `anthropic-api` and the test-only fake hosts (`_BUILTIN_HINT_MAPPINGS`, `host_runner.py:134-138`). Codex, Gemini, Kimi-Code and Qwen have none by design (EPIC-3563 scope: "Out: built-in mappings for non-Claude hosts"), so resolution for them raises `ModelHintError` unless `orchestration.model_hints` supplies a value.

## Expected Behavior

- A skill or agent may declare `model_hint: <coding|reasoning|burst>`. Unknown hints are errors.
- A literal `model:` may appear alongside `model_hint` **only** as the Claude Code pin, and it must equal `resolve_model_hint(hint, backend="claude-code")` (e.g. `coding` → `sonnet`). A mismatch is a validation error. `model:` with no `model_hint` keeps today's behavior.
- When generating mirrors, each host gets `resolve_model_hint(hint, backend=<host>, overrides=None)`. Built-in mappings only: generated mirrors are shipped plugin content, so they must not depend on the maintainer's `.ll/ll-config.json` or `.ll/ll.local.md`.
- A host with no built-in mapping (currently codex, gemini, kimi-code, qwen) gets **no model field**, so it uses its own default, and `ll-adapt` prints a per-file warning naming the hint and host. It is not a hard error, so `ll-adapt --apply` still completes.
- Gemini's reduced-mode agent output (`_emit_degraded_agent`) carries no frontmatter, so Gemini agents are "unsupported, omitted" by construction. Gemini *skill* mirrors follow the general rule.
- `model_hint` itself is never emitted into a generated mirror.

**What this delivers today:** a portable declaration plus an enforced Claude-pin consistency check. With no built-in non-Claude mappings, generated hosts currently resolve to "omitted + warning". The payoff for those hosts arrives when a built-in mapping is added to `_BUILTIN_HINT_MAPPINGS`. ENH-3642 (deferred) proposes one for Codex that uses host-default model plus reasoning effort, not a concrete ID; its spike decides whether Codex agent TOML can carry that selection. The mirrors then pick it up on the next `ll-adapt --apply`, and the staleness gate forces that regeneration.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

**Option A**: Generation-time resolution only, through the existing `ll-adapt` adapter path. Extend `CodexEmitter.emit_agent` (`adapters/codex.py:444`) to call `resolve_model_hint()` alongside the existing literal-`model` passthrough, and add the same resolution to the Kimi/Qwen emitters and the shared skill path. Claude Code itself keeps reading `agents/*.md`/`skills/*/SKILL.md` frontmatter natively. `ClaudeCodeEmitter.emit_skill/emit_command/emit_agent` are declared no-ops (`claude_code.py:30-40`) because "the plugin marketplace serves skills natively", so no little-loops code sits between the source file and Claude Code's own parser.

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
4. **Skills are in scope.** Resolution applies to `emit_skill` mirrors as well as `emit_agent`. It uses the same frontmatter-rewrite seam BUG-3640 introduces in `_select_frontmatter_fields`.
5. **Gemini agents: unsupported, omitted.** No change to `_emit_degraded_agent` beyond confirming that it emits no model.
6. **Validation lives in the adapter path, not `ll-verify-skills`.** One helper validates in `process_agents`/`process_skills`, and a pytest walks the real `agents/` and `skills/` trees. `ll-verify-skills` is scoped to SKILL.md line counts and doesn't cover `agents/`. Extending it would change its documented scope in ~6 places for no gain.
7. **One exception boundary.** `process_agents`/`process_skills` convert `ModelHintError` to `AdapterError`. They already catch `AdapterError`, so both CLIs (`ll-adapt`, `ll-adapt-agents-for-codex`) and the staleness test get clean per-file errors with no CLI-level try/except.
8. **Staleness needs no new gate.** With built-in-only resolution, a mapping change is a code change to `_BUILTIN_HINT_MAPPINGS`. The existing `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` then fails until the mirrors are regenerated.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — add `_validate_model_decl(fm: dict) -> None` (unknown-hint + pin-agreement check, raises `AdapterError`) and `_resolve_frontmatter_model(fm: dict, backend: str) -> str | None` (hint → host model via `resolve_model_hint(..., overrides=None)`; `None` + warning on missing mapping; falls back to BUG-3640's literal-`model` rule when no hint). Call `_validate_model_decl` in `process_agents` (`:592`) and `process_skills` (`:438`) right after `_read_frontmatter`. Convert `ModelHintError` → `AdapterError` in both.
- `scripts/little_loops/adapters/core.py:119` — `_select_frontmatter_fields` (or the BUG-3640 model-rewrite helper next to it): strip `model_hint:` and write the resolved `model:` (or none) for the target host.
- `scripts/little_loops/adapters/codex.py:444` — `CodexEmitter.emit_agent`: `model = _resolve_frontmatter_model(fm, "codex") or ""`; `_format_agent_toml` omits the line when empty (from BUG-3640).
- `scripts/little_loops/adapters/kimi.py:111-126`, `qwen.py:128-145` — `emit_agent`/`emit_skill` pass the host backend key to the shared rewrite.
- `scripts/little_loops/adapters/gemini.py:81` — `emit_skill` via the shared rewrite. `emit_agent` (`:131-138`, degraded) needs no change.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:153` — `resolve_model_hint`, `ModelHintError`, `hint_backend_keys()`; signature unchanged. Existing callers: `fsm/executor.py:3687,3704`.
- `scripts/little_loops/cli/adapt.py:132`, `cli/adapt_agents_for_codex.py:125-127` — call `process_agents`; covered by the `AdapterError` conversion (refinement 7), no edit.
- `scripts/little_loops/adapters/capabilities.py` — `frontmatter_fields_read` per host. Add `model` for hosts that now receive a managed model field.
- `scripts/little_loops/cli/verify_triggers.py:24,347` — imports `_is_model_invocation_disabled` from `adapters.core`; must be undisturbed by the new helpers.
- `scripts/little_loops/adapters/omp.py` — excluded from `process_agents` degraded emission (`core.py:568-572`). Confirm that omp skill emission goes through the shared rewrite, or document it as unsupported.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — new row/column: which hosts resolve a frontmatter `model_hint` (all generated hosts: omitted until a built-in mapping exists; Gemini agents: unsupported).
- `docs/reference/CLI.md:5827` — `ll-adapt-agents-for-codex` TOML output: `model` is resolved from `model_hint` or omitted.
- `docs/reference/CONFIGURATION.md` (`orchestration.model_hints`, ~line 1370) — state explicitly that frontmatter hints ignore this override (built-in mappings only).
- `docs/reference/API.md` (~11330-11385, `little_loops.adapters`) — `model_hint` handling in the per-emitter table; `ModelHintError` surfaces as `AdapterError`.
- `CONTRIBUTING.md` — authoring note: `model_hint` + optional agreeing `model:` pin.

### Tests
- `scripts/tests/test_adapters.py` — per emitter (Codex agent, Kimi agent/skill, Qwen agent/skill, Gemini skill): hint resolves on a fake-host-mapped backend; omitted + warning on an unmapped backend; `model_hint` never emitted. `TestGeminiEmitterEmitAgent` `_meta()` (`:1046-1056`): assert no model in degraded output.
- `scripts/tests/fixtures/adapt/agent_cases.json` + `test_adapt_golden_corpus.py:156-176` — add a `model_hint` case without perturbing the existing byte-identical cases.
- New validation tests for `_validate_model_decl`: unknown hint → error; `model_hint: coding` + `model: sonnet` → ok; `model_hint: coding` + `model: haiku` → error. Template: `test_model_hints.py::TestStructuralValidation.test_invalid_vocabulary_and_exclusivity` (`:260-266`).
- A pytest walking real `agents/*.md` and `skills/*/SKILL.md` that runs `_validate_model_decl` on each (the in-repo gate for refinement 6).
- `process_agents`/`process_skills`: an unknown hint yields an `errors` count increment, not a traceback.
- Resolution-reaches-artifact matrix: mirror `test_model_hints.py::TestHostArgv` (`:953-1023`) / `TestPortabilityProof` (`:1039-1091`), using the `fake` backend for the positive path, since no real non-Claude host has a built-in mapping.
- `test_wiring_skills_and_commands.py:474-524` (`test_host_artifacts_are_not_stale`) — existing staleness gate; must pass after regeneration.

### Dropped touchpoints (from earlier wiring passes)
Refinements 6 and 7 remove these: `cli/docs.py` `main_verify_skills` + its help text, `doc_counts.py:_parse_skill_frontmatter`, `frontmatter.py:parse_skill_frontmatter`, `cli/doctor.py:943`, `init/writers.py:238`, `CONTRIBUTING.md:691,707` (verify-skills wording), `skills/configure/areas.md:862`, `scripts/little_loops/loops/mechanize-skills.yaml:503`, `scripts/pyproject.toml:92`, `cli/__init__.py:64,156`, `test_cli_docs.py::TestMainVerifySkills`, `test_skill_size_checker.py`, `test_doc_counts.py::TestCheckSkillBudget`, and CLI-level try/except in `cli/adapt.py`/`cli/adapt_agents_for_codex.py`. Refinement 2 removes `config-schema.json:1819-1832` (no new consumer of `orchestration.model_hints`).

## Implementation Steps

1. Land BUG-3640 first. It introduces the Claude-alias predicate, the omit-when-empty Codex TOML rule, and the frontmatter `model:` rewrite seam.
2. Add `_validate_model_decl` and `_resolve_frontmatter_model` to `adapters/core.py`. Wire validation into `process_agents`/`process_skills` with `ModelHintError` → `AdapterError`.
3. Route every generated-host emitter through `_resolve_frontmatter_model` (Codex agent; Kimi/Qwen agent + skill; Gemini skill), stripping `model_hint:` from output.
4. Add `model` to `frontmatter_fields_read` where it is now a managed field.
5. Tests per the Tests list (TDD: write the failing tests first).
6. Docs per the Documentation list.
7. If trivial, migrate one agent (e.g. `agents/codebase-locator.md` → `model_hint: coding` + `model: sonnet`) as a live example, then `ll-adapt --host <codex|gemini|kimi-code|qwen> --apply` so the committed mirrors match.

## Impact

- **Priority**: P3.
- **Effort**: Medium.
- **Risk**: Low-Medium — generated mirrors only; the staleness gate already enforces regeneration.

## Resolved Questions

- **Resolution timing** → generation time only (Option A). Native Claude Code reads the literal `model:` pin, kept consistent by validation.
- **Staleness** → built-in-only resolution makes a mapping change a code change; `test_host_artifacts_are_not_stale` enforces regeneration (refinement 8).
- **Claude-native path** → no `ll-adapt` materialization for Claude Code. The `/ll:spike` on native hint support is not needed under Option A: Claude Code does not have to honor `model_hint`, only tolerate it as an unknown key. Check that tolerance on the first migrated file: it still registers under `/ll:*` / the Agent list and runs on its `model:` pin. If Claude Code rejects the key, ship no migrated files and record that here.

## Acceptance Criteria

- [ ] Every artifact/host combination claimed as supported has an executable test proving the resolved model reaches the host artifact, or that the field is omitted with a warning where no mapping exists.
- [ ] Unknown hints are errors. A `model:` that disagrees with `model_hint`'s `claude-code` resolution is an error. An agreeing `model:` pin is allowed.
- [ ] Generated-mirror resolution never reads `orchestration.model_hints` / `.ll/ll.local.md` (test: an override in config does not change emitted output).
- [ ] `model_hint` never appears in any generated mirror.
- [ ] An unresolvable hint surfaces as a per-file `ll-adapt` error, not a traceback.
- [ ] Generated-file staleness after a mapping change is caught by `test_host_artifacts_are_not_stale`.
- [ ] Migration of shipped skills/agents, if any, is done with mirrors regenerated (`ll-adapt --apply`).

## Scope Boundaries

- **In scope**: `model_hint` in skill and agent frontmatter; generation-time resolution for codex, gemini (skills), kimi-code, qwen; pin-agreement validation; tests per claimed combination.
- **Prerequisites**: ENH-3527 (done — resolver); BUG-3640 (alias stripping + model-rewrite seam).
- **Out of scope**: new hint vocabulary; built-in hint mappings for non-Claude hosts (ENH-3642 for Codex; concrete non-Claude model IDs are out per EPIC-3563); consumer-project config overrides for shipped mirrors; resolution at Claude Code native invocation; migrating every shipped skill/agent.

## Program Design

### Types

- `model_hint: str | None` — optional frontmatter key; value in `host_runner.MODEL_HINTS`.
- `model: str | None` — when present with `model_hint`, must equal `resolve_model_hint(model_hint, backend="claude-code")`.

### Signatures

- `_validate_model_decl(fm: dict) -> None` — new in `adapters/core.py`; raises `AdapterError` on unknown hint or pin mismatch.
- `_resolve_frontmatter_model(fm: dict, backend: str) -> str | None` — new in `adapters/core.py`; returns the host model, or `None` to omit.
- `CodexEmitter.emit_agent(self, agent_meta: dict) -> str` — existing (`codex.py:429`); model comes from `_resolve_frontmatter_model(fm, "codex")`.
- `resolve_model_hint(hint: str, *, backend: str, overrides: dict | None = None) -> str` — existing (`host_runner.py:153`); called with `overrides=None`.
- `process_agents(emitter, agents_dir, output_dir, apply, quiet, only=None) -> tuple[int, int, int]` — existing (`core.py:544`); gains validation + `ModelHintError` → `AdapterError`.

### Call Path

- `process_agents` → `_validate_model_decl` → `CodexEmitter.emit_agent` → `_resolve_frontmatter_model` → `resolve_model_hint` → `.codex/agents/<name>.toml`
- `process_skills` → `_validate_model_decl` → `QwenEmitter.emit_skill` → `_resolve_frontmatter_model` → `resolve_model_hint` → `.qwen/skills/<name>/SKILL.md`

## Verification Notes

Refreshed 2026-09-28 (supersedes the 2026-09-24 check): ENH-3527 is done; `resolve_model_hint`, `ModelHintError`, `MODEL_HINTS`, `_BUILTIN_HINT_MAPPINGS` exist in `host_runner.py` (`:121-192`). The Codex emitter class is `CodexEmitter` (`codex.py:328`), not `CodexAdapter`. `ll-adapt` output lands under the plugin root (`cli/adapt.py`). Committed mirrors confirm the alias leak (`.codex/agents/codebase-analyzer.toml:4` `model = "sonnet"`), now tracked as BUG-3640.

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item). `/ll:verify-issues ENH-3533 --auto`, 2026-09-28: every `file:line` citation in the Codebase Research Findings, Integration Map, Program Design, and Dropped-touchpoints list was checked against the current tree (all `adapters/*.py`, `host_runner.py`, `cli/*.py`, `capabilities.py`, doc/schema files, and the cited test classes/functions) — all confirmed accurate except two stale citations in the Dropped-touchpoints line, now corrected in place: `loops/mechanize-skills.yaml:503` → `scripts/little_loops/loops/mechanize-skills.yaml:503` (the file lives under `scripts/little_loops/loops/`, not a top-level `loops/`); `cli/doctor.py:238,943` → `cli/doctor.py:943` (line 238 is an unrelated `print("  (none found)")`; only line 943, the `check_skill_sizes()`/`ll-verify-skills` adapter docstring, is a real touchpoint). `ll-verify-evidence` found no fabricated quotes. No active required decision rules. Dependency check (§2E) found `blocked_by: BUG-3640` (status: open, correctly unsatisfied) had no reciprocal `## Blocks` entry on BUG-3640 — fixed by adding one there in this pass. B6 proposal-vs-code check: the planned `ModelHintError` → `AdapterError` conversion lands inside `process_agents`/`process_skills`' existing per-file `except AdapterError` blocks (`core.py:456,529,607,649`), so no exception-handler gap.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-28T21:01:34 - `6ee1f8dc-4aaf-4326-9a2c-971c5336e607.jsonl`
- `/ll:wire-issue` - 2026-09-28T20:07:49 - `05090d65-2eac-41cf-a99d-d360b8ff23dc.jsonl`
- `/ll:decide-issue` - 2026-09-28T19:46:46 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:refine-issue` - 2026-09-28T19:41:20 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:wire-issue` - 2026-09-28T19:35:30 - `f552ed04-ad08-4162-b169-daaec37f3df4.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
