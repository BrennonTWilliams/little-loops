---
id: FEAT-2260
title: Generic host-parameterized skill + command adapter
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
labels:
- host-compat
- portfolio
- skills
- commands
- adapters
learning_tests_required:
- ruamel.yaml
relates_to:
- FEAT-2188
- FEAT-2189
- ENH-2121
confidence_score: 87
outcome_confidence: 73
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 12
---

# FEAT-2260: Generic host-parameterized skill + command adapter

## Summary

Provide **one** host-parameterized adapter that bridges ll skills and commands
into a target host's discovery surface, selected via `--host`
(`codex|gemini|omp`), instead of a bespoke `ll-adapt-*-for-<host>` per host.

Per ARCHITECTURE-049, this consolidates:
- `ll-adapt-skills-for-codex` + `ll-adapt-agents-for-codex` (existing, Codex-only)
- **FEAT-2188** (Gemini skills adaptation)
- **FEAT-2189** (Gemini commands `.md` → `.toml`)
- **ENH-2121** (rich Codex subagent TOML fields — absorbed as the Codex-host
  agent-emitter requirement; see "Codex-host emitter parity" below)
- the omp skill/command adaptation need (folded here, not re-specified under EPIC-2258)

## Use Case

**Who**: A little-loops maintainer adding support for a new host CLI (e.g., Gemini, omp) or keeping Codex adaptation current.

**Context**: When exposing ll skills and commands to a new host's discovery surface requires adapting metadata to a host-specific format.

**Goal**: Run `ll-adapt --host <host>` (or `ll-adapt-skills/ll-adapt-commands --host <host>`) once to produce correct host-specific output without writing a bespoke per-host script.

**Outcome**: Each new host requires only one new output emitter; shared traversal, selection, and `disable-model-invocation` filtering logic is reused automatically.

## Current Behavior

Each host requires a dedicated CLI script:
- `ll-adapt-skills-for-codex` and `ll-adapt-agents-for-codex` exist for Codex.
- Gemini requires separate bespoke scripts (FEAT-2188, FEAT-2189 each specify their own `ll-adapt-*-for-gemini`).
- The traversal, selection, and `disable-model-invocation` filtering logic is duplicated in every per-host script.
- Adding a new host means writing a full new adapt script rather than a single output emitter.

## Expected Behavior

A single unified adapter (`ll-adapt --host <host>`, or `ll-adapt-skills --host <host>` / `ll-adapt-commands --host <host>`) routes to a host-specific output emitter:
- Shared traversal, selection, and filtering logic runs once for all hosts.
- Host-specific differences are encapsulated in per-host output emitters.
- `--host codex`, `--host gemini`, and `--host omp` are all supported.
- Existing Codex scripts (`ll-adapt-skills-for-codex`, `ll-adapt-agents-for-codex`) work as thin `--host codex` aliases or are retired without breaking existing workflows.

## Motivation

Skill/command adaptation differs per host only in **output format** (Codex
Skills API frontmatter, Gemini `.toml`, omp's surface). The traversal,
selection, and `disable-model-invocation` filtering logic is identical. One
adapter with per-host output emitters removes N near-duplicate scripts.

## Acceptance Criteria

- A single entry point (`ll-adapt-skills --host <host>` / `ll-adapt-commands
  --host <host>`, or a unified `ll-adapt --host`) emits the correct
  host-specific format.
- Codex output matches today's `ll-adapt-skills/agents-for-codex` behavior
  (those become thin `--host codex` aliases or are retired).
- Gemini `.toml` command output covers FEAT-2189; Gemini skill frontmatter
  covers FEAT-2188 (both closed as superseded once this lands).
- Respects `disable-model-invocation: true` (skips those skills) for every host.
- Adding a host = adding one output emitter, not a new script.
- **OmpEmitter scope**: `OmpEmitter` raises `NotImplementedError` with a remediation hint ("omp emitter not yet implemented; open a PR adding `adapters/omp.py`") on any `emit_*` call. This stub is the complete omp deliverable for this issue; full omp surface support is a separate follow-on under EPIC-2258.
- **Alias retirement**: `ll-adapt-skills-for-codex` and `ll-adapt-agents-for-codex` are removed in the next minor release after this issue lands, not in this PR. The aliases remain functional throughout the transition period.

### Codex-host emitter parity (absorbs ENH-2121)

The `--host codex` agent emitter must not regress to today's lossy four-field
output. Since this issue generalizes `ll-adapt-agents-for-codex`, it owns
ENH-2121's scope: the Codex agent emitter maps available source-agent metadata
onto the richer Codex subagent schema rather than dropping it.

- Codex agent TOML emits `sandbox_mode` (vocabulary aligned with ENH-1529:
  `off` / `read-only` / `write-to-cwd` / `network`), `model_reasoning_effort`,
  `mcp_servers`, and `skills.config` **when derivable from the source agent's
  `tools:` frontmatter / model identifier**; fields with no source mapping are
  omitted (Codex inherits from the parent session — omission stays safe).
- `nickname_candidates` remains **out of scope** (no clean source mapping), and
  no new `agents/*.md` frontmatter fields are invented — derive from existing
  `tools:` / model only. (Both boundaries carried over verbatim from ENH-2121.)
- Test parity: the Codex emitter's tests assert each rich field emits for a
  fixture agent that declares it and is omitted otherwise (was
  `test_adapt_agents_for_codex.py`; folds into this adapter's test suite).

## API/Interface

```bash
# Unified CLI (preferred)
ll-adapt --host <host>           # adapt both skills and commands

# Or per-artifact subcommands
ll-adapt-skills --host <host>    # adapt skills only
ll-adapt-commands --host <host>  # adapt commands only

# Hosts: codex | gemini | omp
```

```python
# HostEmitter protocol (scripts/little_loops/adapters/core.py)
class HostEmitter(Protocol):
    def emit_skill(self, skill_meta: dict) -> str: ...
    def emit_command(self, cmd_meta: dict) -> str: ...
    def emit_agent(self, agent_meta: dict) -> str: ...
```

## Proposed Solution

Implement a shared adapter core with pluggable per-host output emitters:

1. **New entry point**: `ll-adapt` (or `ll-adapt-skills` / `ll-adapt-commands`) with a required `--host` parameter.
2. **Shared core**: Extract traversal and `disable-model-invocation` filtering from `ll-adapt-skills-for-codex.py` into a common `scripts/little_loops/adapters/core.py`.
3. **Emitter interface**: Define a `HostEmitter` protocol (`emit_skill`, `emit_command`, `emit_agent`).
4. **Host emitters**: Implement `CodexEmitter` (migrated from existing scripts + ENH-2121 rich fields), `GeminiEmitter` (FEAT-2188/2189 formats), `OmpEmitter` (TBD format).
5. **Aliases**: Retain `ll-adapt-skills-for-codex` and `ll-adapt-agents-for-codex` as thin `--host codex` wrappers during transition.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Duplicated logic to consolidate into `adapters/core.py`** — both existing scripts independently contain:
- `_find_plugin_root()` — delegates to `little_loops.skill_expander._find_plugin_root`; checks `CLAUDE_PLUGIN_ROOT` env var first
- `_extract_short_desc()` — parses YAML frontmatter, returns first non-empty description line ≤80 chars (`_MAX_SHORT_DESC = 80`)
- `_extract_*_frontmatter()` — identical `text.find("---", 3)` sentinel pattern + `yaml.safe_load(text[3:end])` with `YAMLError` catch
- `--apply / --quiet / --dry-run` CLI argument pattern
- `(adapted, skipped, errors)` return tuple from `_process_*()` functions

**`disable-model-invocation` behavioral gap**: In `adapt_skills_for_codex.py`, this filter applies only to **commands** (`_process_commands()`), not to skills (`_process_skills()`). The shared core should normalize this to filter both skills and commands consistently.

**Codex agent "lossy four-field" output** (`adapt_agents_for_codex.py:_emit_agent_toml`): currently emits only `name`, `description`, `model`, `developer_instructions`. Fields silently dropped: `sandbox_mode`, `model_reasoning_effort`, `mcp_servers`, `skills.config` (from `tools:` frontmatter). ENH-2121 absorption means `CodexEmitter` must map these from source agent frontmatter `tools:` / model identifier when derivable.

**User-authored file protection** in `adapt_agents_for_codex.py`: checks `_MARKER = "# generated by ll-adapt-agents-for-codex"` as first line of existing `.toml`; skips if absent. The marker string will need updating to `"# generated by ll-adapt"` in the unified adapter.

**`--only <stem>` filter** in `adapt_agents_for_codex.py:_process_agents()`: single-agent targeting. Carry this into `CodexEmitter` / unified core.

**Entry-point wiring path**: `pyproject.toml` → `little_loops.cli:main_adapt` → `cli/__init__.py` re-export → `cli/adapt.py:main_adapt()`. Follow the established one-module-per-CLI-tool pattern.

**Frontmatter parsing**: prefer `scripts/little_loops/frontmatter.py:parse_skill_frontmatter()` (canonical, with line-scan fallback) over duplicating the inline `yaml.safe_load(text[3:end])` pattern in `adapters/core.py`.

**`_extract_body(text)` as shared logic**: `adapt_agents_for_codex.py` has `_extract_body(text)` that strips the frontmatter fence and returns everything after the closing `---\n`. This feeds `_emit_agent_toml()` to populate `developer_instructions`. The equivalent for skills is inlined in `_process_skills()`. Both should move to `adapters/core.py` so emitters receive a pre-stripped body without re-implementing the fence scan.

**`cli_event_context` wrapping**: Both `main_adapt_skills_for_codex()` and `main_adapt_agents_for_codex()` wrap their logic in `cli_event_context(DEFAULT_DB_PATH, "<tool-name>", sys.argv[1:])`. The unified `main_adapt()` must do the same with `"ll-adapt"` as the tool name so CLI events land correctly in the session database.

**Stub emitter pattern for `OmpEmitter`**: Follow the `OpenCodeRunner` stub pattern from `host_runner.py:626` — register `OmpEmitter` in `_EMITTER_REGISTRY` so unknown-host errors are descriptive, but exclude it from any auto-detect probe order. All `emit_*` methods should raise a `HostNotConfigured`-equivalent with a remediation hint ("omp emitter not yet implemented; open a PR adding `adapters/omp.py`"). This produces a clear message on `--host omp` instead of a `KeyError`.

**Gemini output format specifics from `thoughts/research/gemini-cli-surface.md`**: Skills land at `.gemini/skills/<name>/SKILL.md` (same SKILL.md format as ll's `skills/*/SKILL.md`; no `agents/openai.yaml` equivalent — Gemini does not use it). Commands land at `.gemini/commands/*.toml`. The `name:` and `description:` fields are required; `metadata.short-description:` has no Gemini equivalent and should be omitted from `GeminiEmitter` output.

**`parse_skill_frontmatter()` fallback caveat**: The line-scan fallback path does NOT resolve YAML block scalars — only the `yaml.safe_load()` primary path does. Agent and skill `description:` values using block scalar syntax (`description: |`) return `None` in the fallback. Test fixtures exercising block-scalar descriptions must use valid YAML so the primary path fires.

**Protocol spike findings** (validated 2026-06-28, `adapters/__init__.py` + `adapters/core.py` created as spike artifacts):
- `...` is valid in Protocol method bodies (same as `HostRunner`) but mypy raises `empty-body` in **concrete** classes — use `raise NotImplementedError` for unimplemented `CodexEmitter`/`GeminiEmitter` methods during the transition period.
- All three concrete emitters (`CodexEmitter`, `GeminiEmitter`, `OmpEmitter`) satisfy `isinstance(obj, HostEmitter)` at runtime — `@runtime_checkable` structural matching works as expected.
- `dict` type annotation for `skill_meta`/`cmd_meta`/`agent_meta` is accepted by mypy without complaint; `TypedDict` refinement can be deferred to a follow-on without blocking implementation.
- Registry + factory design passes mypy clean: `_EMITTER_REGISTRY: dict[str, type[HostEmitter]]` with `resolve_emitter()` matches the `HostRunner` pattern exactly. Protocol design is structurally validated — no interface surprises expected during implementation.

**Additional reference research docs**: `thoughts/research/codex-command-discovery.md` and `thoughts/research/codex-agent-selection.md` document Codex command discovery and agent selection behavior; useful context for `CodexEmitter` implementation details.

**`GeminiEmitter.emit_skill()` — `name:` injection requirement** (`thoughts/research/gemini-cli-surface.md`): Gemini requires `name:` in `SKILL.md` frontmatter (used as slug identifier; Claude Code's format omits it, using directory name instead). Most ll skills already have `name:`; `GeminiEmitter.emit_skill()` must inject `name: <dir-stem>` when absent. Output path: `.gemini/skills/<name>/SKILL.md` — note the `.agents/skills/<name>/SKILL.md` path is also accepted by Gemini as a cross-tool compatibility alias, but `.gemini/skills/` is the canonical target. `metadata.short-description:` (Codex-only) must be omitted from Gemini output.

**`GeminiEmitter.emit_command()` — TOML field names** (`thoughts/research/gemini-cli-surface.md`): Gemini command TOML has exactly two fields: `description = "..."` (optional) and `prompt = "..."` (required). The `prompt` field maps to the ll command body (the full markdown content minus frontmatter); the `description` field maps to the frontmatter `description:` value. Output path: `.gemini/commands/<stem>.toml`. No Gemini equivalent of `developer_instructions` — the body becomes `prompt`. Subdirectory namespacing is supported (`git/commit.toml` → `/git:commit`).

**`test_adapt_skills_for_codex.py` — full test class inventory**: 10 classes fold into the unified adapter test suite: `TestExtractShortDesc`, `TestInsertFields`, `TestMakeOpenaiYaml` (Codex `agents/openai.yaml` side-file), `TestTitleCase` (slug → display name helper), `TestProcessSkills`, `TestMainAdaptSkillsForCodex`, `TestRealSkillsIntegrationGuard` (runs against real `skills/` dir; verifies idempotency), `TestSynthesizedSkillMd` (validates synthesized SKILL.md field injection), `TestProcessCommands`, `TestRealCommandsIntegrationGuard`. The `TestMakeOpenaiYaml` + `TestSynthesizedSkillMd` classes are Codex-specific and have no `GeminiEmitter` equivalent.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — refactor into `--host codex` alias; extract core to shared module
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — refactor into `--host codex` alias; extract agent emitter
- `scripts/little_loops/cli/__init__.py:39-40,83-84` — add `main_adapt` import and `__all__` entry
- `scripts/pyproject.toml:82,86` — add `ll-adapt = "little_loops.cli:main_adapt"` alongside existing entries; keep old names as aliases

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py:48-49,93-94` — `_LL_PERMISSIONS` lists `Bash(ll-adapt-skills-for-codex:*)` and `Bash(ll-adapt-agents-for-codex:*)`; `_CLAUDE_MD_COMMANDS_BLOCK` names both commands; replace with `Bash(ll-adapt:*)` and unified `ll-adapt` entry
- `scripts/little_loops/host_runner.py:443` — user-visible `CapabilityNotSupported` warning embeds `"ll-adapt-agents-for-codex --apply"`; update to `ll-adapt --host codex`
- `.claude/CLAUDE.md:250-251` — CLI Tools section has two separate bullets for old command names; replace with unified `ll-adapt --host <host>` entry
- `.codex/agents/*.toml` (9 files: `codebase-analyzer.toml`, `codebase-locator.toml`, `codebase-pattern-finder.toml`, `consistency-checker.toml`, `loop-specialist.toml`, `plugin-config-auditor.toml`, `prompt-optimizer.toml`, `web-search-researcher.toml`, `workflow-pattern-analyzer.toml`) — first-line marker `# generated by ll-adapt-agents-for-codex`; all 9 require regeneration when marker becomes `"# generated by ll-adapt"`

### Files to Create
- `scripts/little_loops/adapters/__init__.py`
- `scripts/little_loops/adapters/core.py` — shared traversal + `disable-model-invocation` filter + `HostEmitter` protocol
- `scripts/little_loops/adapters/codex.py` — Codex emitter (skills, agents; ENH-2121 rich TOML fields)
- `scripts/little_loops/adapters/gemini.py` — Gemini emitter (FEAT-2188 skills + FEAT-2189 commands `.toml`)
- `scripts/little_loops/adapters/omp.py` — omp emitter (TBD format)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:39-40` — re-exports `main_adapt_agents_for_codex` and `main_adapt_skills_for_codex`; add `main_adapt` re-export here
- `scripts/little_loops/cli/__init__.py:83-84` — `__all__` entries for both; extend for new entry point
- `scripts/tests/test_wiring_cli_registry.py` — validates all CLI entry points are registered; must be updated when `ll-adapt` is added
- `scripts/tests/test_wiring_guides_and_meta.py` — validates documentation consistency; will need update if CLI.md changes
- `docs/reference/HOST_COMPATIBILITY.md:85,100-102,135-137` — references current Codex adapter behavior and documents ENH-2121 gap; needs update with unified interface
- `docs/reference/CLI.md:2679-2730` — documents both existing commands; deprecation/update needed
- `README.md:92` — references `ll-adapt-skills-for-codex` in Codex getting-started section; update when unified interface ships

### Similar Patterns
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — reference implementation for core extraction (traversal, `disable-model-invocation` filter, `(adapted, skipped, errors)` return tuple)
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — reference implementation for agent emitter (four-field TOML output: `name`, `description`, `model`, `developer_instructions`; user-authored file protection via `_MARKER`)
- `scripts/little_loops/host_runner.py:HostRunner` — exact Protocol pattern to follow for `HostEmitter`: `@runtime_checkable`, `...` method bodies, name-keyed `_HOST_RUNNER_REGISTRY: dict[str, type[HostRunner]]`, `resolve_host()` factory
- `scripts/little_loops/extension.py:ExtensionLoader` — registry + plugin discovery pattern for reference
- `scripts/little_loops/frontmatter.py:parse_skill_frontmatter` — canonical frontmatter parser for SKILL.md; prefer over duplicating the inline `yaml.safe_load(text[3:end])` pattern in `adapters/core.py`
- `thoughts/research/gemini-cli-surface.md` — Gemini output paths: `.gemini/skills/<name>/SKILL.md` and `.gemini/commands/*.toml`

### Tests
- `scripts/tests/test_adapt_agents_for_codex.py` — folds into adapter test suite; extend with multi-host fixtures; 7 test classes: `TestExtractAgentFrontmatter`, `TestEmitAgentToml`, `TestProcessAgents`, `TestMainAdaptAgentsForCodex`, `TestRealAgentsIntegrationGuard`, `TestIdempotency`, `TestMarkerPreservation`
- `scripts/tests/test_adapt_skills_for_codex.py` — also folds into adapter test suite; covers `_extract_short_desc`, `_insert_fields`, command synthesis
- `scripts/tests/test_wiring_cli_registry.py` — must be updated to register `ll-adapt` entry point
- New: `scripts/tests/test_adapters.py` — unified tests per emitter and shared core; use `_make_agent(tmp_path, name, ...)` and `_make_skill(tmp_path, name, ...)` fixture helpers following existing class-per-function grouping pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_init_and_configure.py` — `DOC_STRINGS_PRESENT` asserts old names present in `skills/configure/areas.md`; add `ll-adapt` tuples when old names are retired [Agent 2]
- `scripts/tests/test_init_core.py:test_all_canonical_permissions_present` — validates `_LL_PERMISSIONS` in `init/writers.py`; will break if old `Bash(ll-adapt-*:*)` entries are removed without updating [Agent 2]

### Documentation
- `docs/reference/CLI.md:2679-2730` — add `ll-adapt`; update/deprecate `ll-adapt-skills-for-codex` and `ll-adapt-agents-for-codex`
- `docs/reference/API.md` — document `HostEmitter` protocol and `adapters` module
- `docs/reference/HOST_COMPATIBILITY.md:85,100-102,135-137,160` — update Codex adapter section to reflect unified interface; remove ENH-2121 gap note once rich fields are emitted
- `README.md:92` — update Codex getting-started to reference `ll-adapt --host codex`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/codex/README.md` — multiple references to both adapters in setup and troubleshooting table; update to `ll-adapt --host codex` [Agent 2]
- `docs/codex/getting-started.md:88-101` — step-by-step `--apply` invocations for both old commands; update to unified entry point (troubleshooting at line 133 also references `ll-adapt-skills-for-codex`) [Agent 2]
- `docs/codex/usage.md:41,50,85,87` — 4 occurrences across skills and agent fallback sections [Agent 2]
- `CONTRIBUTING.md:500-514,599` — three instructional sections ("Adding a new command" ~line 502, "Adding a new agent" ~line 514, "New Skill Checklist" ~line 599) each reference old adapt CLI names [Agent 2]
- `docs/claude-code/skills.md:186` — `metadata.short-description` table row references `ll-adapt-skills-for-codex` [Agent 2]
- `commands/help.md:288-289` — adapter tool listing entries for both old CLI names [Agent 2]
- `skills/configure/areas.md:832` — Codex adapter listing in configure area documentation [Agent 2]

### Configuration
- N/A

## Implementation Steps

1. ~~Spike `adapters/__init__.py` + `adapters/core.py` with Protocol + registry only; gate on `mypy` clean~~ **Done** — spike artifacts landed; Protocol design validated (see spike findings in Codebase Research Findings).
2. Build out `scripts/little_loops/adapters/core.py` with traversal + `disable-model-invocation` filter — spike stubs are the starting point; replace `raise NotImplementedError` with real logic
3. Migrate `ll-adapt-skills-for-codex` and `ll-adapt-agents-for-codex` logic into `CodexEmitter` (with ENH-2121 rich TOML fields)
4. Implement `GeminiEmitter` covering FEAT-2188 (skills frontmatter) and FEAT-2189 (commands `.toml`) output
5. `OmpEmitter` is already a correctly-raising stub (spike artifact) — no additional work needed for omp scope in this issue
6. Wire `ll-adapt --host <host>` CLI entry point (wrap in `cli_event_context(DEFAULT_DB_PATH, "ll-adapt", sys.argv[1:])` following `main_adapt_skills_for_codex` pattern); keep old scripts as thin `--host codex` aliases
7. Port/extend tests from `test_adapt_agents_for_codex.py` into unified adapter test suite; assert rich Codex field parity
8. Update CLI reference docs; verify FEAT-2188, FEAT-2189, ENH-2121 can be closed as superseded

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/init/writers.py:48-49,93-94` — replace `Bash(ll-adapt-skills-for-codex:*)` and `Bash(ll-adapt-agents-for-codex:*)` in `_LL_PERMISSIONS` with `Bash(ll-adapt:*)`; update `_CLAUDE_MD_COMMANDS_BLOCK` to reference unified command
9. Update `scripts/little_loops/host_runner.py:443` — fix `CapabilityNotSupported` warning to reference `ll-adapt --host codex` instead of `ll-adapt-agents-for-codex --apply`
10. Update Codex guide docs — `docs/codex/README.md`, `docs/codex/getting-started.md:88-101`, `docs/codex/usage.md:41,50,85,87`: replace old command invocations with `ll-adapt --host codex`
11. Update contributor docs — `CONTRIBUTING.md:500-514,599`, `docs/claude-code/skills.md:186`, `skills/configure/areas.md:832`: update instructions to reference unified command
12. Update `.claude/CLAUDE.md:250-251` — replace two separate CLI Tools bullets with single `ll-adapt --host <host>` entry
13. Update `commands/help.md:288-289` — replace old adapter tool listing entries
14. Regenerate `.codex/agents/*.toml` (9 files) — after marker string changes to `"# generated by ll-adapt"`, run `ll-adapt --host codex --apply` to update all generated files; `TestRealAgentsIntegrationGuard` must pass after regeneration
15. Update wiring tests — add `ll-adapt` tuples to `test_wiring_cli_registry.py`, `test_wiring_guides_and_meta.py`, `test_wiring_init_and_configure.py`; update `test_init_core.py` for new permission entry; update `test_wiring_guides_and_meta.py:88` count needle when `README.md` CLI tool count changes

## Reference

- `ll-adapt-skills-for-codex`, `ll-adapt-agents-for-codex` — existing Codex emitters.
- FEAT-2188 / FEAT-2189 — the bespoke Gemini specs this generalizes.
- ENH-2121 — rich Codex subagent TOML fields, absorbed here as the Codex-host
  emitter parity requirement (closed as superseded; full source-mapping detail
  and the `developers.openai.com/codex/subagents` schema link live in its body).

## Impact

- **Effort**: Medium.
- **Risk**: Low-Medium — must preserve existing Codex output byte-for-byte to
  avoid regressing the landed Codex adapter.
- **Breaking Change**: No (existing Codex scripts kept as aliases during transition).

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-28_

**Readiness Score**: 87/100 → PROCEED (learning test gate resolved; re-run pending)
**Outcome Confidence**: 61/100 → Moderate Risk

### Gaps Resolved (2026-06-28)
- **`toml` learning test** — REMOVED from `learning_tests_required`. TOML output is hand-built f-strings with manual escaping (same as `_emit_agent_toml` in the existing `adapt_agents_for_codex.py`). No TOML library is needed.
- **`yaml` learning test** — RENAMED `yaml` → `ruamel.yaml`. The new `adapters/core.py` calls `parse_skill_frontmatter()` (canonical parser, already uses ruamel.yaml internally); raw `yaml.safe_load` is not used in the shared core. `ruamel.yaml` is already proven in the registry.

### Outcome Risk Factors
- Broad enumeration across 21+ distinct change sites: code, tests, config, commands, and docs span 5 subsystems; coordination risk is highest in the docs pass (Codex guides, CONTRIBUTING.md, skills docs).
- OmpEmitter format not yet defined: scoped as a raising stub, but any consumer expecting `--host omp` hits a hard error rather than a graceful no-op. Backward-compat alias retirement timeline also unspecified.
- Moderate change surface with 6–10 external callers of existing adapt entry points; backward-compat aliases during transition reduce regression risk.

## Session Log
- `/ll:refine-issue` - 2026-06-28T19:58:17 - `fc58955b-8ad7-4f9c-9f01-9db7cc12324e.jsonl`
- Protocol spike (`adapters/__init__.py` + `adapters/core.py`) - 2026-06-28 - mypy clean; `score_complexity` 11→17, `outcome_confidence` 67→73
- `/ll:confidence-check` - 2026-06-28T00:00:00 - `21cf19fc-222d-4e73-a05e-bea40e65db5a.jsonl`
- `/ll:confidence-check` (re-run, gate cleared) - 2026-06-28 - `dcb52e94-0280-4152-a74c-c9ae184c654c.jsonl`
- `/ll:refine-issue` - 2026-06-28T17:25:55 - `75663ab2-c73a-4ef7-8c3f-ef349639e486.jsonl`
- `/ll:wire-issue` - 2026-06-25T18:42:58 - `b48daf6e-e26f-40d4-9aab-ea94d716a199.jsonl`
- `/ll:refine-issue` - 2026-06-25T18:30:36 - `2896fb18-50ad-4c0c-a3c3-dfbdab05512f.jsonl`
- `/ll:format-issue` - 2026-06-25T18:20:17 - `9285574b-00e2-4b27-85e4-574f9b9140d0.jsonl`
