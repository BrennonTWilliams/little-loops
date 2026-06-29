---
id: FEAT-2260
title: Generic host-parameterized skill + command adapter
type: feature
status: done
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
confidence_score: 92
outcome_confidence: 73
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 12
size: Very Large
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
- **OmpEmitter scope**: `OmpEmitter` raises `AdapterError` (not `NotImplementedError`) with a remediation hint ("omp emitter not yet implemented — open a PR adding `adapters/omp.py`") on any `emit_*` call. The spike artifact already implements this correctly — using `AdapterError` rather than `NotImplementedError` gives callers a typed exception they can catch without importing Python builtins. This stub is the complete omp deliverable for this issue; full omp surface support is a separate follow-on under EPIC-2258.
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

**`_process_agents()` signature detail**: `_process_agents(agents_dir, codex_dir, apply, quiet, only) -> tuple[int, int, int]`. The `codex_dir` (output path for `.codex/agents/*.toml`) is a separate positional parameter — distinct from `agents_dir` (source). The `CodexEmitter.emit_agent()` API must receive this split or the shared core must pass both paths to the emitter. Factor this into the `HostEmitter` protocol design: `emit_agent` may need to accept a `dest_dir` kwarg, or the traversal core handles path construction while emitters only return content.

**`test_adapt_agents_for_codex.py` — module-level `_MARKER` copy**: The test file also defines `_MARKER = "# generated by ll-adapt-agents-for-codex"` at module scope (mirrors the source constant). When the source `_MARKER` changes to `"# generated by ll-adapt"`, this test file's copy must also be updated — otherwise `TestMarkerPreservation` and `TestIdempotency` will silently test the wrong string.

**`test_wiring_cli_registry.py` — tuple format for new entry**: `DOC_STRINGS_PRESENT` uses 3-tuples `(doc_rel, needle, issue_id)`. The two existing Codex entries use `"FEAT-1486"` and `"FEAT-1526"` as issue IDs. New `ll-adapt` entries should use `"FEAT-2260"`. The three doc targets are `commands/help.md`, `docs/reference/CLI.md`, and `.claude/CLAUDE.md` — add one 3-tuple per doc target. Exact existing pattern to follow:
```python
("commands/help.md", "ll-adapt-skills-for-codex", "FEAT-1486"),
("docs/reference/CLI.md", "ll-adapt-skills-for-codex", "FEAT-1486"),
(".claude/CLAUDE.md", "ll-adapt-skills-for-codex", "FEAT-1486"),
```
New `ll-adapt` tuples:
```python
("commands/help.md", "ll-adapt", "FEAT-2260"),
("docs/reference/CLI.md", "ll-adapt", "FEAT-2260"),
(".claude/CLAUDE.md", "ll-adapt", "FEAT-2260"),
```

### Codebase Research Findings — Refinement Pass 2

_Added by `/ll:refine-issue` — implementation-detail findings from second research pass:_

**`cli/__init__.py` actual line numbers (correction)**: Prior notes reference lines 39-40 for imports and 83-84 for `__all__`. Actual lines confirmed by reading are **40-41** (the two `from little_loops.cli.adapt_*` imports) and **85-86** (the two `__all__` string entries). Use these corrected line numbers when adding the `main_adapt` import and `__all__` entry.

**`_FM_CLOSE_RE = re.compile(r"\n---\s*\n")`** — module-level constant in `adapt_skills_for_codex.py`. Used by `_insert_fields()` to locate the closing frontmatter delimiter when injecting `name:` and `metadata.short-description:` into SKILL.md content. `CodexEmitter` must carry this regex; it is Codex-specific and does not belong in `adapters/core.py`.

**`_emit_agent_toml()` exact TOML serialization** — the current four-field output follows this exact structure:
```
# generated by ll-adapt-agents-for-codex
name = "<name>"
description = "<desc with \ and " escaped>"
model = "<model with \ and " escaped>"

developer_instructions = """<body with """ replaced by \"\"\">"""
```
Escaping rules: `description` and `model` values have `\` → `\\` then `"` → `\"`. The body has any `"""` occurrence replaced with `\"\"\"`. `CodexEmitter.emit_agent()` must replicate this escaping exactly to preserve byte-for-byte compatibility with existing output.

**Exact fixture helper signatures** for `test_adapters.py` (model after existing tests):

`_make_agent(tmp_path, name, ...)`:
```python
def _make_agent(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    model: str = "sonnet",
    body: str = "Agent instructions.",
) -> Path:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agent_md = agents_dir / f"{name}.md"
    agent_md.write_text(
        f"---\nname: {name}\ndescription: |\n  {description}\nmodel: {model}\n"
        f'tools: ["Read"]\n---\n\n{body}'
    )
    return agent_md
```

`_make_skill(tmp_path, name, ...)`:
```python
def _make_skill(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Skill\n\nDoes stuff.",
) -> Path:
    skill_dir = tmp_path / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return skill_md
```

`_make_command(tmp_path, name, ...)` — not mentioned in prior passes; defined in `test_adapt_skills_for_codex.py`:
```python
def _make_command(
    tmp_path: Path,
    name: str,
    description: str = "Use when user asks for stuff.",
    extra_frontmatter: str = "",
    body: str = "# My Command\n\nDoes stuff.",
) -> Path:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    cmd_md = commands_dir / f"{name}.md"
    cmd_md.write_text(f"---\ndescription: {description}\n{extra_frontmatter}---\n\n{body}")
    return cmd_md
```
The `extra_frontmatter: str = ""` slot enables injecting `"disable-model-invocation: true\n"` for filter tests without separate fixtures.

**`GeminiEmitter.emit_agent()` should also stub** — The Confidence Check Notes flag that Gemini's agent surface is not specified in the research doc. The `gemini-cli-surface.md` research confirms agents exist but as a "preview feature" (`agents/` extension bundle). Implement `GeminiEmitter.emit_agent()` as `raise AdapterError("gemini agent emission not yet stable — Gemini agents are a preview feature; open a PR when they exit preview")` following the OmpEmitter stub pattern. This is consistent with the AC's stub-emitter model and avoids shipping broken output.

### Codebase Research Findings — Refinement Pass 3

_Added by `/ll:refine-issue` — implementation-detail findings from third research pass:_

**`parse_skill_frontmatter()` return type: `dict[str, str]` (flat string-to-string)** — The canonical SKILL.md parser returns strings for all values: booleans are lowercased (`True` → `"true"`), numbers are stringified. This means `disable-model-invocation: true` in a SKILL.md will come back as `"true"` when read via `parse_skill_frontmatter`. Coercion at the shared-core filter becomes a plain string comparison: `fm.get("disable-model-invocation", "") in {"true", "yes", "1"}` (no `.lower()` needed — already lowercased). **Contrast with commands and agents**: `_read_command_frontmatter()` and `_extract_agent_frontmatter()` use raw `yaml.safe_load`, returning Python booleans. Do NOT use `parse_skill_frontmatter()` for command or agent files — it was designed for SKILL.md format. The existing `_process_commands():254–260` `isinstance(v, str)` bool/string dual-check handles the raw-YAML path; replicate it for commands in the shared core.

**`resolve_emitter(host: str) -> HostEmitter`** — confirmed from spike (`adapters/core.py:94–111`). Takes the host identifier string directly — no `env` dict parameter (unlike `resolve_host(env=None)`). Call site in `main_adapt()`: `emitter = resolve_emitter(args.host)`. The factory raises `AdapterError` (not `HostNotConfigured`) when the host key is absent; callers should catch `AdapterError`.

**`_process_agents()` `--only` non-counting skip** — confirmed from `adapt_agents_for_codex.py`. When the `only` filter rejects an agent (`only is not None and agent_name != only`), `continue` executes without touching any counter. The `(adapted, skipped, errors)` tuple reflects only agents that passed the filter. The unified core's `--only` flag must replicate this silently-skipping behavior — filtered agents must NOT be counted as "skipped".

**`cli/__init__.py` `__all__` insertion position** — confirmed: line 84 = `"main_harness"`, line 86 = `"main_adapt_skills_for_codex"`, line 87 = `"main_auto"`. New `"main_adapt"` entry inserts after line 86 and before line 87. Import insertion: after line 41 (`from little_loops.cli.adapt_skills_for_codex import main_adapt_skills_for_codex`).

**Spike `CodexEmitter`/`GeminiEmitter` method bodies** — both currently raise `NotImplementedError` with no message (bare raise). When building out concrete implementations, follow the OmpEmitter pattern for any still-unimplemented `emit_*` method: raise `AdapterError` with a remediation hint, not bare `NotImplementedError`, so callers get a typed catchable exception.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — refactor into `--host codex` alias; extract core to shared module
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — refactor into `--host codex` alias; extract agent emitter
- `scripts/little_loops/cli/__init__.py:40-41,85-86` — add `main_adapt` import and `__all__` entry
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
- `scripts/little_loops/cli/__init__.py:40-41` — re-exports `main_adapt_agents_for_codex` and `main_adapt_skills_for_codex`; add `main_adapt` re-export here
- `scripts/little_loops/cli/__init__.py:85-86` — `__all__` entries for both; extend for new entry point
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

- **Priority**: P4 — Low urgency; consolidation improvement for maintainers adding new host support. Not blocking any active workflows; existing per-host scripts continue to work throughout the transition period.
- **Effort**: Medium.
- **Risk**: Low-Medium — must preserve existing Codex output byte-for-byte to
  avoid regressing the landed Codex adapter.
- **Breaking Change**: No (existing Codex scripts kept as aliases during transition).

## Status

**Open** | Created: 2026-06-24 | Priority: P4


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-28 (updated 2026-06-29 post-refinement passes 1 + 2 + 3)_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 73/100 → Moderate Risk

### Outcome Risk Factors
- **Broad change surface across 21+ files spanning 5+ subsystems.** The docs/wiring pass (Codex guides, `CONTRIBUTING.md`, `skills/configure/areas.md`, `commands/help.md`) carries the highest coordination risk; implementation steps 10-15 (wiring phase) should be treated as required deliverables, not optional cleanup.
- **ENH-2121 rich-field mapping requires implementer judgment.** The `sandbox_mode`, `mcp_servers`, and `skills.config` derivation from `tools:` frontmatter is bounded by "when derivable" — read ENH-2121's body for the derivation schema before coding `CodexEmitter.emit_agent()`.
- **Alias retirement timing is informal.** Nine `.codex/agents/*.toml` files will carry the old marker until `ll-adapt --host codex --apply` is re-run post-landing; `TestRealAgentsIntegrationGuard` is the trigger for that regeneration step.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-29
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-2391: Core adapter infrastructure + CodexEmitter
- FEAT-2392: GeminiEmitter implementation (FEAT-2188 + FEAT-2189)
- FEAT-2393: Documentation migration and alias retirement for ll-adapt

**Execution pattern**: Partially ordered — FEAT-2391 and FEAT-2392 can run in parallel; FEAT-2393 depends on FEAT-2391 (requires `ll-adapt --host codex --apply` to be runnable before TOML regeneration).

## Session Log
- `/ll:issue-size-review` - 2026-06-29T00:00:00 - `1113a873-5cfd-4186-9b3c-13c3306e634d.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00 - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
- `/ll:refine-issue` - 2026-06-29T05:10:09 - `2576a5df-97a3-44ac-a9a6-9eb88573f68e.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00 - `4713836d-161b-4ca7-8e3e-362e565183e5.jsonl`
- `/ll:refine-issue` - 2026-06-29T04:58:13 - `1a8693c2-db4c-4db1-a47c-75c51833ec18.jsonl`
- `/ll:confidence-check` - 2026-06-28T00:00:00 - `e74ec2e6-7eaf-4ca4-80e7-1aab21043b09.jsonl`
- `/ll:refine-issue` - 2026-06-29T04:46:42 - `8f7e45db-7238-404d-941a-067487c3d31b.jsonl`
- `/ll:confidence-check` - 2026-06-28T00:00:00 - `67259380-07b9-4521-b497-032d8941261a.jsonl`
- `/ll:format-issue` - 2026-06-29T04:36:41 - `3f28c22f-d225-491b-a351-47f1d91b540d.jsonl`
- `/ll:refine-issue` - 2026-06-28T19:58:17 - `fc58955b-8ad7-4f9c-9f01-9db7cc12324e.jsonl`
- Protocol spike (`adapters/__init__.py` + `adapters/core.py`) - 2026-06-28 - mypy clean; `score_complexity` 11→17, `outcome_confidence` 67→73
- `/ll:confidence-check` - 2026-06-28T00:00:00 - `21cf19fc-222d-4e73-a05e-bea40e65db5a.jsonl`
- `/ll:confidence-check` (re-run, gate cleared) - 2026-06-28 - `dcb52e94-0280-4152-a74c-c9ae184c654c.jsonl`
- `/ll:refine-issue` - 2026-06-28T17:25:55 - `75663ab2-c73a-4ef7-8c3f-ef349639e486.jsonl`
- `/ll:wire-issue` - 2026-06-25T18:42:58 - `b48daf6e-e26f-40d4-9aab-ea94d716a199.jsonl`
- `/ll:refine-issue` - 2026-06-25T18:30:36 - `2896fb18-50ad-4c0c-a3c3-dfbdab05512f.jsonl`
- `/ll:format-issue` - 2026-06-25T18:20:17 - `9285574b-00e2-4b27-85e4-574f9b9140d0.jsonl`
