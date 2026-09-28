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
- ENH-3527
decision_needed: false
---

# ENH-3533: Model capability hints for skill and agent frontmatter

## Summary

Extend ENH-3527's `model_hint` vocabulary (`coding`, `reasoning`, `burst`) from loop states to skill and agent frontmatter, so shipped skills/agents stop hard-coding host model IDs. Deferred from ENH-3527 because accepting a frontmatter key does not establish that the host honors it.

## Current Behavior

- Claude Code serves skills and agents natively; there is no little-loops model-resolution step at invocation time.
- Codex agent TOML is generated ahead of execution; `adapters/codex.py` `emit_agent` copies `model` verbatim from frontmatter.
- `ll-verify-skills` checks file sizes, not model selection.

## Expected Behavior

A skill or agent can declare `model_hint` instead of `model`; each supported host receives a host-valid model through a documented, tested mechanism, and unsupported hosts fail or warn explicitly.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-28 — based on codebase analysis:_

**Option A**: Generation-time resolution only, through the existing `ll-adapt` adapter path. Extend `CodexAdapter.emit_agent` (`adapters/codex.py:444`) to call `resolve_model_hint()` alongside the existing literal-`model` passthrough, and add the same resolution (or an explicit `ModelHintError`-based failure) to `KimiEmitter.emit_agent` (`kimi.py:111-126`) and `QwenEmitter.emit_agent` (`qwen.py:128-145`), which today pass any `model_hint:` frontmatter line through unresolved via `_select_frontmatter_fields`. Decide separately how `GeminiEmitter.emit_agent`'s degraded-mode path (`gemini.py:131` → `core._emit_degraded_agent()`, which strips all frontmatter) handles the field. Claude Code itself keeps reading `agents/*.md`/`skills/*/SKILL.md` frontmatter natively — `ClaudeCodeEmitter.emit_skill/emit_command/emit_agent` are declared no-ops (`claude_code.py:30-40`) because "the plugin marketplace serves skills natively," so no little-loops code sits between the source file and Claude Code's own parser. Skills/agents intended for native Claude Code use keep a literal `model:` value; `model_hint:` only resolves for the hosts that already go through adapter-based generation.

> **Selected:** Option A — the only path that reuses an existing seam (`emit_agent`, `resolve_model_hint`, `_select_frontmatter_fields`); Option B has no interception point or source-rewrite precedent anywhere in the codebase.

**Option B**: Resolve `model_hint` for Claude Code's own native invocation too, by having little-loops rewrite the resolved concrete model into `skills/*/SKILL.md`/`agents/*.md` source frontmatter in place before Claude Code reads it. No such mechanism exists in the codebase today: `hooks/hooks.json`'s matcher set has no entry for a `Skill` or `Task` tool, and no code under `scripts/little_loops/` writes back into the repo's own `skills/`/`agents/` directories (every adapter `write_text` call targets a generated mirror under `.codex/`, `.gemini/`, `.kimi-code/`, `.qwen/`, never the source). This option requires building a new interception/rewrite mechanism, plus a way to keep the rewritten concrete value from being treated as the portable source of truth on the next pass (regeneration/staleness handling), before "each supported host receives a host-valid model" can hold for Claude Code itself.

**Recommended**: Option A — it is the only path with an existing mechanism to extend (the codex adapter already does per-field `model` translation at generation time; kimi/qwen already run frontmatter through `_select_frontmatter_fields`). Option B requires inventing frontmatter-rewrite interception that has no precedent anywhere in this codebase, and conflicts with Claude Code's own "plugin marketplace serves skills/agents natively" model that the codebase already routes around rather than through.

### Decision Rationale

**Selected**: Option A — generation-time resolution through the existing `ll-adapt` adapter path; native Claude Code invocation is explicitly out of scope for resolution and keeps literal `model:` values.

**Reasoning**: Option A reuses a single already-established seam — every host's `emit_agent(self, agent_meta: dict) -> str` (`adapters/core.py:30-44`), a resolver already called from two sites (`host_runner.py:153-192`, `fsm/executor.py:3687,3704`), and a frontmatter-pass-through helper already sitting in the two files that need editing (`_select_frontmatter_fields`, `core.py:119-144`, consumed by `kimi.py:125`/`qwen.py:144`). It has real, bounded gaps (no built-in hint→model mapping for codex/kimi-code/qwen/gemini per `host_runner.py:134-138`; `ll-adapt`'s CLI has no config-loading or overrides-threading path per `cli/adapt.py:1-145`; `process_agents()` only catches `AdapterError`, not the `ValueError`-subclass `ModelHintError`, per `core.py:603-611`) but every gap is new wiring inside an existing call chain, not a new mechanism.

Option B requires inventing a mechanism this codebase has never built: an interception point before Claude Code's own native frontmatter read (Claude Code's documented `PreToolUse` matcher set has no `Skill`/`Task` entry — `docs/claude-code/hooks-reference.md:716`), and a write path into the source `skills/`/`agents/` tree (every existing adapter `write_text` call targets a generated mirror, never the source — confirmed across all of `scripts/little_loops/adapters/*.py`). `ClaudeCodeEmitter.emit_skill/emit_command/emit_agent` are declared no-ops precisely because "the plugin marketplace serves skills natively" (`claude_code.py:30-40`) — Option B would work against that boundary, not within it. The issue's own Open Questions section already gates Option B's core premise behind an unrun `/ll:spike`.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2/3 | 1/3 |
| Simplicity | 2/3 | 0/3 |
| Testability | 3/3 | 1/3 |
| Risk | 2/3 | 0/3 |
| **Total** | **9/12** | **2/12** |

**Key evidence**:
- Option A's seam: `CodexAdapter.emit_agent` already does per-field `model` translation (`adapters/codex.py:444`); `KimiEmitter`/`QwenEmitter.emit_agent` already run frontmatter through `_select_frontmatter_fields` (`kimi.py:125`, `qwen.py:144`).
- Option A's existing test scaffolding: `test_adapters.py:635-638,1500-1504,2155-2162`, `test_model_hints.py` (`TestResolver`, `TestHostArgv`, `TestPortabilityProof`).
- Option B's missing mechanism: no `Skill`/`Task` entry in Claude Code's `PreToolUse` matcher set (`docs/claude-code/hooks-reference.md:716`); no adapter `write_text` call targets the source `skills/`/`agents/` tree; `SessionStart` hooks are contractually advisory-only, never mutating (`hooks/drift_check.py:22-24`).
- Option B's feasibility is explicitly unproven: this issue's own Open Questions gate it behind `/ll:spike` ("can Claude Code honor a frontmatter hint at all... without rewriting the file").

## Integration Map

- `scripts/little_loops/adapters/codex.py`, `cli/adapt_agents_for_codex.py`, and the Gemini/Kimi/Qwen adapters (`ll-adapt --host <gemini|kimi-code|qwen>`) plus their generated mirrors; `skills/`, `agents/` frontmatter; `ll-verify-skills`.
- Builds on the resolver from ENH-3527 (landed) and `orchestration.model_hints` config.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:3687,3704` — the only two existing callers of `resolve_model_hint()`, both inside `_resolve_model()` (`backend=ANTHROPIC_API_BACKEND` and `backend=backend` resolved via `host_runner.resolve_host().name`). A frontmatter-path caller in an adapter module becomes an independent third call site with its own `backend=` value per host — no shared call-site edit needed, just confirms the resolver signature stays stable.
- `scripts/little_loops/adapters/core.py:89` — `_read_frontmatter(text)`, the shared parser feeding `process_agents()` (`:592`, `fm = _read_frontmatter(content) or {}`) that builds `agent_meta["fm"]` passed to every host's `emit_agent`. Natural insertion point for a `model`/`model_hint` mutual-exclusivity check shared across hosts.
- `scripts/little_loops/adapters/capabilities.py:84,109,129,148,166,184` — `HOST_CAPABILITIES[...].frontmatter_fields_read` per host: codex declares `("description","name","metadata.short-description","tools")` (`:84`); gemini/kimi-code/qwen/omp all declare `("description","name")` (`:109,129,148,166`) or `()` (omp, `:184`). No host declares `model` here — confirmed this allowlist doesn't gate today's incidental verbatim passthrough (kimi/qwen), only the injected fields (`name`, `metadata.short-description`).
- `scripts/little_loops/adapters/kimi.py:111-126` and `scripts/little_loops/adapters/qwen.py:128-145` — `emit_agent()` calls `_select_frontmatter_fields(content, agent_name, _fields_read())` unconditionally (confirmed at kimi.py:125); any `model:`/`model_hint:` line in source frontmatter passes through byte-for-byte as a byproduct, not by declared policy. No guard branch and no existing parameter seam — the caller-suitability gate does not apply; these are genuine touchpoints, not no-edit call sites (see Wiring Phase).
- `scripts/little_loops/adapters/gemini.py:131` → `core._emit_degraded_agent()` (`core.py:225`) — strips all frontmatter, emitting only a fixed preamble + body. Gemini's degraded-mode agent output carries no `model` or `model_hint` today, so "each supported host receives a host-valid model" (AC) currently fails for gemini by construction, not by a missing resolve step.
- `scripts/little_loops/adapters/omp.py` — not confirmed to emit real agent files at all; `HOST_CAPABILITIES["omp"]` excludes it from `process_agents`' degraded-emission path per `core.py:568-572`. Flag as an open question for the spike rather than a confirmed touchpoint.
- `scripts/little_loops/frontmatter.py:371` — `parse_skill_frontmatter(text)`, the canonical SKILL.md parser (separate from `adapters/core.py`'s `_read_frontmatter`), consumed by `tool_catalog.py:101,120,139`, `mcp_server/prompts.py:75,86`, `cli/generate_skill_descriptions.py:37`, `cli/help.py:189`, `cli/action.py:187`, `cli/verify_skill_prose.py:33,168`. None of these six consumers read `model`/`model_hint` today — out of scope unless a validation pass is centralized here instead of in the adapter path.
- `scripts/little_loops/doc_counts.py:479` — `_parse_skill_frontmatter(text)`, a third independent SKILL.md frontmatter parser (own `yaml.safe_load` fallback), used by `check_skill_sizes`/`check_skill_budget` — the function `main_verify_skills` (the issue's own stated validation entry point) actually depends on.
- `scripts/little_loops/loops/mechanize-skills.yaml:503` — gates on `ll-verify-skills`'s exit code with an undifferentiated `REASON="verify-skills"` (line 51 wires only `context.line_cap` into it). If `main_verify_skills` gains a new `model`/`model_hint` validation category, this loop's routing cannot distinguish a size violation from a frontmatter-validation failure.
- `scripts/little_loops/cli/doctor.py:238,943` — `ll-doctor`'s checklist registry entry `("ll-verify-skills", "Check that no SKILL.md exceeds 500 lines")` and its docstring `"""Adapter over check_skill_sizes() (ll-verify-skills)."""` are both scoped to the line-count check and would go stale if `main_verify_skills` takes on frontmatter validation.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5827` — documents `ll-adapt-agents-for-codex`'s TOML output as containing `name`, `description`, `model`, `developer_instructions`; needs a `model_hint` resolution note.
- `docs/reference/CLI.md:888-889,941,947-955,1016` — a *different* `model:` concept lives nearby in the same doc (per-loop-state `--model`/`--effort` CLI overrides from ENH-3527/3547). Not a touchpoint for this issue, but a reader/writer must not conflate the two when adding frontmatter documentation near it.
- `docs/reference/CONFIGURATION.md` (`orchestration` § `model_hints` row, ~line 1370) — description text is scoped to "the loop `model_hint` vocabulary"; needs rewording if `orchestration.model_hints` is reused to back frontmatter resolution.
- `docs/reference/HOST_COMPATIBILITY.md` — confirmed zero `model_hint` mentions; this is the doc carrying the per-host capability table that `capabilities.py`'s `HOST_CAPABILITIES` mirrors (`frontmatter_fields_read`, `subagents`, `agent_output_format`) — needs a new row/column stating which hosts resolve a frontmatter `model_hint` and how.

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json:1819-1832` (`orchestration.model_hints`) — confirmed the JSON shape is already backend-keyed and includes `gemini`, `kimi-code`, `qwen`, `omp`, `codex` in `propertyNames.enum`, so the config surface is structurally reusable for frontmatter resolution with no schema change. The `description` string, however, explicitly cites "ENH-3527" and per-*loop-state* mapping — needs updating (or leaving stale) once a second consumer exists.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapters.py:635-638` (`TestCodexEmitterEmitAgent.test_toml_contains_model`) — existing coverage of the exact line (`codex.py:444`, `model = str(fm.get("model") or "")`) this issue must change; stays valid as a literal-`model`-passthrough regression guard, but is the line that needs an adjacent `model_hint` branch.
- `scripts/tests/test_adapt_agents_for_codex.py:109-111,180-185` — parallel coverage of the same path via the backward-compat wrapper; `scripts/tests/test_adapt_agents_for_codex.py:363-374` (`test_all_real_toml_files_have_required_fields`) is a local-artifact guard over the real `.codex/agents/*.toml` mirrors, skipped when the mirror dir is absent — not CI-portable, but the test that will actually exercise migrated `agents/*.md` files once any switch to `model_hint:`.
- `scripts/tests/test_adapters.py:2155-2162` (`TestQwenEmitterEmitAgent.test_claude_frontmatter_passes_through_verbatim`, asserts `"model: sonnet" in content`) and `scripts/tests/test_adapters.py:1500-1504` (`TestKimiEmitterEmitAgent.test_frontmatter_preserved`) — confirm today's verbatim-passthrough behavior; will need new dedicated `model_hint`-resolution coverage once kimi/qwen stop being pure passthrough, without breaking these as pure-`model:` passthrough regression guards.
- `scripts/tests/test_adapt_golden_corpus.py:156-176` (`test_codex_agent_emission_matches_golden_corpus`) backed by `scripts/tests/fixtures/adapt/agent_cases.json` (4 cases, all literal `model:` values, none `model_hint:`) — a byte-identity snapshot test; needs a new `model_hint` fixture case added without perturbing the existing byte-identical cases.
- `scripts/tests/test_model_hints.py` — the ENH-3527 convention set to mirror for new frontmatter-level tests: `TestResolver` (`:60-127`, hint/backend parametrization sourced from `RUNTIME_HOST_CAPABILITIES | TEST_ONLY_HOSTS | {"anthropic-api"}`), `TestStructuralValidation.test_invalid_vocabulary_and_exclusivity` (`:260-266`, the closest existing "vocabulary + mutual exclusivity" test shape, targeting `_validate_model_hint_decl` in `fsm/validation/structural_rules.py:452-484`), `TestSchemaRoundTrip.test_llm_model_plus_hint_raises` (`:207-209`, targeting `schema.py:1088`), `TestHostArgv` (`:953-1023`, the template for "resolved model reaches the host invocation" per-artifact/host testing this issue's AC requires), `TestPortabilityProof` (`:1039-1091`, cross-backend coverage-matrix template).
- `scripts/tests/test_cli_docs.py::TestMainVerifySkills` (`:634-724`) — the test file/pattern (`patch("little_loops.doc_counts.check_skill_sizes", ...)`) to extend if `main_verify_skills` gains the `model`/`model_hint` mutual-exclusivity check; currently line-count-only, no frontmatter-value assertions beyond `disable-model-invocation` skip logic.

## Impact

- **Priority**: P3.
- **Effort**: Medium.
- **Risk**: Medium — generated artifacts can silently go stale.

## Open Questions (resolve before implementation)

**Not implementation-ready.** Answer these with `/ll:spike` (can Claude Code honor a frontmatter hint at all, and does it tolerate an unknown `model_hint` key in skill/agent frontmatter?) and `/ll:decide-issue` before any implementation. Exclude from the first implementation wave; it must not gate EPIC-3563 closure.

The spike does not need ENH-3527's resolver: it probes Claude Code's frontmatter handling, not the resolver. It can run now, in parallel with the loop-execution work. ENH-3527 has landed, so nothing blocks implementation on it.

- **Resolution timing**: native invocation (Claude Code reads frontmatter — can a hint be honored at all without rewriting the file?) versus generation time (Codex/Gemini/Kimi/Qwen adapters resolve through ENH-3527's resolver when emitting).
- **Staleness**: how generated agent files are detected as stale and regenerated after a mapping or `orchestration.model_hints` change.
- **Claude-native path**: whether hints require an `ll-adapt`-style materialization for Claude Code too, or are limited to generated hosts.

## Acceptance Criteria

- [ ] Every artifact/host combination claimed as supported has an executable test proving the resolved model reaches the host artifact or invocation.
- [ ] Declaring both `model` and `model_hint` in frontmatter is a validation error; unknown hints are errors.
- [ ] Generated-file staleness after a mapping change is detected (gate or regeneration rule).
- [ ] Migration of shipped skills/agents, if any, is done with mirrors regenerated (`ll-adapt --apply`).

## Scope Boundaries

- **In scope**: `model_hint` in skill/agent frontmatter, resolution at native invocation or generation time, staleness detection for generated agent files, tests per claimed artifact/host combination.
- **Prerequisite**: ENH-3527 (resolver and `orchestration` hint mappings).
- **Out of scope**: new hint vocabulary; migrating every shipped skill/agent in the same change unless trivial.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. This issue is gated by the Open Questions above — this phase records the discovered surface for whichever resolution-timing option is chosen, not a sequenced plan:_

- Update `scripts/little_loops/adapters/codex.py:444` — `emit_agent`'s `model = str(fm.get("model") or "")` must add a `model_hint` branch (calling `resolve_model_hint` from `little_loops.host_runner`, not a separate module as the Program Design section's citation implies) alongside the existing literal-`model` passthrough.
- Update `scripts/little_loops/adapters/kimi.py:111-126` and `scripts/little_loops/adapters/qwen.py:128-145` — `emit_agent` currently passes any `model_hint:` frontmatter line through unresolved and meaningless to those hosts' native CLIs; add resolution or an explicit unsupported-host error per the Expected Behavior clause ("unsupported hosts fail or warn explicitly").
- Update `scripts/little_loops/adapters/gemini.py:131` / `core._emit_degraded_agent()` (`core.py:225`) — decide and implement how (or whether) `model_hint` surfaces through gemini's frontmatter-stripping degraded-mode path.
- Update `scripts/little_loops/adapters/capabilities.py` — add `model`/`model_hint` to `frontmatter_fields_read` for any host where it should be an actively managed field rather than incidental verbatim passthrough.
- Add validation — extend `main_verify_skills` (`cli/docs.py:244`) or a new check, mirroring `_validate_model_hint_decl`'s vocabulary + mutual-exclusivity shape (`fsm/validation/structural_rules.py:452-484`), for skill/agent frontmatter. Requires picking which of the three existing frontmatter parsers (`adapters/core.py:_read_frontmatter`, `little_loops/frontmatter.py:parse_skill_frontmatter`, `doc_counts.py:_parse_skill_frontmatter`) the check runs against.
- Update `docs/reference/CLI.md:5827`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/CONFIGURATION.md` (~line 1370), `scripts/little_loops/config-schema.json:1819-1832` — document the new frontmatter consumer of `orchestration.model_hints` alongside the existing loop-state one.
- Add test coverage — extend `scripts/tests/test_adapters.py`, `scripts/tests/fixtures/adapt/agent_cases.json`, and `scripts/tests/test_adapt_golden_corpus.py` with `model_hint` cases; add a new test class mirroring `scripts/tests/test_model_hints.py`'s `TestHostArgv`/`TestPortabilityProof` shape for the "resolved model reaches the host artifact" AC.
- Migration candidates (out of scope per Scope Boundaries unless trivial, recorded for the deciding option): 9 `agents/*.md` files and 20 `skills/*/SKILL.md` files hard-code `model: sonnet` or `model: haiku` today (e.g. `agents/codebase-analyzer.md:13`, `skills/analyze-history/SKILL.md:5`, `skills/wire-issue/SKILL.md:4`); each has mirrors under `.gemini/`, `.kimi-code/`, `.qwen/` needing `ll-adapt --apply` regeneration if migrated.

## Program Design

### Types

- `model_hint: str | None` — optional frontmatter key, mutually exclusive with `model`.

### Signatures

- `CodexAdapter.emit_agent(self, agent_meta: dict) -> str` — existing; resolves `model_hint` through `resolve_model_hint` instead of copying `model` verbatim.
- `resolve_model_hint(hint: str, *, backend: str, overrides: dict | None = None) -> str` — provided by ENH-3527 (no `operation` parameter).

### Call Path

- `emit_agent` → `resolve_model_hint` → generated `.codex/agents/<name>.toml`

## Verification Notes

Verdict at time of check: **VALID** (no corrections needed; this section is a record of what was checked, not an outstanding action item). Evidence-quote check clean (`ll-verify-evidence`); no required decisions rules; graph provider `codegraph` (fresh) available.

Checked 2026-09-24: `CodexAdapter.emit_agent(self, agent_meta: dict) -> str` exists at `adapters/codex.py` L429 with the stated signature; `main_verify_skills` (`cli/docs.py` L244) exists; `resolve_model_hint` does not exist yet and is provided by blocker ENH-3527 (open) as stated.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-28T19:46:46 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:refine-issue` - 2026-09-28T19:41:20 - `c582b1ca-9355-4bc0-b38c-78d8f0f2eb3d.jsonl`
- `/ll:wire-issue` - 2026-09-28T19:35:30 - `f552ed04-ad08-4162-b169-daaec37f3df4.jsonl`
- `/ll:verify-issues` - 2026-09-24T00:46:09 - `047cda0b-279f-4078-b31f-1d7b1fcc2181.jsonl`
