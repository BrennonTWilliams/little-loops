---
id: FEAT-2680
title: "F1-prereq (c.1) \u2014 Catalog-assembly function deriving Anthropic tool definitions\
  \ from skill/command/agent frontmatter"
type: FEAT
priority: P2
status: done
parent: EPIC-2456
relates_to:
- FEAT-2671
- FEAT-2672
- FEAT-2673
- FEAT-2681
- FEAT-2679
blocks:
- FEAT-2672
- FEAT-2673
spike_needed: true
decision_needed: false
learning_tests_required:
- anthropic
completed_at: '2026-07-18T20:27:14Z'
confidence_score: 90
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-2680: F1-prereq (c.1) — Catalog-assembly function deriving Anthropic tool definitions from skill/command/agent frontmatter

## Summary

Build the catalog-assembly function that produces a full Anthropic Messages
API `tools` array (`{"name", "description", "input_schema"}` per tool,
optional `cache_control`) for little-loops' own tool set, sourced from
`skills/*/SKILL.md`, `commands/*.md`, and `agents/*.md` frontmatter (Option
C, selected in the parent issue's `/ll:decide-issue` pass).

## Parent Issue

Decomposed from FEAT-2679: F1-prereq (c) — Tool-definition JSON schema
catalog for the Anthropic Messages API. Covers Implementation Steps 1
(source-surface spike), 2 (build the catalog function), and 4 (expose a
stable interface FEAT-2672/FEAT-2673 can consume) from the parent.

## Use Case

FEAT-2672 (deferred-loading stub/resolve mechanism) and FEAT-2673
(`build_anthropic_request()`) both need a single, stable Python call that
returns little-loops' own tool set as a full Anthropic Messages API `tools`
array — instead of each reimplementing skill/command/agent frontmatter
enumeration. A developer implementing either downstream issue imports the
catalog-assembly function from this issue, calls it once, and gets back a
ready-to-serialize `tools` array with no further architectural investigation
into where `input_schema` bodies come from.

## Current Behavior

- `fsm/runners.py`'s `ActionRunner.run()` Protocol accepts `tools:
  list[str] | None` — bare tool names, no schema bodies.
- `host_runner.py`'s `ClaudeCodeRunner.build_streaming()` (lines ~263-264)
  joins that list into a `--tools` CSV flag passed to the `claude` CLI
  subprocess. No code anywhere serializes full tool-definition JSON.
- `scripts/little_loops/cli/action.py:_load_skills()` (lines 45-64) and
  `scripts/little_loops/cli/artifact.py:_load_skill_catalog()` (line 24+)
  already enumerate `skills/*/SKILL.md` into `{name, description}` shape via
  `frontmatter.py:parse_skill_frontmatter()` (lines 175-217), but neither
  produces `input_schema` and neither walks `agents/*.md`.

## Expected Behavior

A catalog-assembly function exists that, given little-loops' skill/command/
agent set, produces the full Anthropic Messages API `tools` array — each
entry carrying `name`, `description`, `input_schema`, and (when applicable)
`cache_control`. This is the data structure FEAT-2673's
`build_anthropic_request()` serializes and FEAT-2672's deferred-loading
stub/resolve mechanism attaches to.

## Proposed Solution

Extend the existing `_load_skills()` (`cli/action.py:45-64`) /
`_load_skill_catalog()` (`cli/artifact.py:24+`) precedents rather than
inventing a new enumeration path:

1. Add `agents/*.md` walking alongside the existing `skills/*/SKILL.md` /
   `commands/*.md` coverage (no existing function walks `agents/*.md` today).
2. Resolve the open spike question: whether the free-text `args`/
   `argument-hint` frontmatter field is sufficient to derive a structured
   `input_schema`, or whether schemas need hand-authoring per tool following
   the `_str()`/`_int()`/`_schema()` typed-field-builder pattern in
   `generate_schemas.py` (lines 33-74).
3. Assemble entries into the Anthropic `tools` array shape, following the
   `CapabilityEntry`/`HookEntry`/`CapabilityReport` frozen-dataclass trio
   (`host_runner.py:118-156`) as the structural precedent for a
   `ToolDefinition` dataclass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Spike question (Implementation Step 1) is resolved — schemas need
hand-authoring, not mechanical derivation.** Grepping `args`/`argument-hint`
values across `commands/*.md` shows only bracketed display placeholders
(`"[issue-id]"`, `"[flags]"`, `"[sprint-name]"`, `"[base-branch]"`,
`"[mode]"`, `"[setting]"`, `"[issue-ids]"`) — human-facing usage-line hints
with no type, required/optional marker, or enum information. There is no
mechanical path from this free text to a valid Anthropic `input_schema`.
The catalog function must hand-author `input_schema` bodies per tool,
following the `generate_schemas.py:_str()/_int()/_schema()` typed-field
pattern (exact signatures: `_str(description: str) -> dict[str, Any]`
returns `{"type": "string", "description": description}`;
`_schema(event_type, title, description, extra_props, extra_required=None)`
assembles the full dict). The closest existing example of an
Anthropic-style `input_schema` body already in the repo is
`DEFAULT_LLM_SCHEMA` in `scripts/little_loops/fsm/evaluators.py:74-106`
(flat `{"type": "object", "properties": {...}, "required": [...]}` dict),
not `BLIND_COMPARATOR_SCHEMA` — both are `input_schema`-shaped, but
`DEFAULT_LLM_SCHEMA` is structurally nearer to what a tool-definition
`input_schema` needs.

**No code today parses `agents/*.md` frontmatter via `parse_skill_frontmatter()`.**
The only existing `agents/*.md` walker is
`scripts/little_loops/adapters/core.py:process_agents()` (lines 242-304),
which uses its own separate, near-duplicate frontmatter parser,
`_read_frontmatter()` (lines 77-87) — this returns `dict | None` straight
from `yaml.safe_load` (nested structures preserved), whereas
`parse_skill_frontmatter()` (`frontmatter.py:175-217`, used by both
`_load_skills()` and `_load_skill_catalog()`) returns a flattened
`dict[str, str]` (non-string scalars stringified, nested lists/dicts
silently dropped) with a line-scan fallback if YAML parsing fails. The new
catalog function needs to decide which parser's contract to standardize on
for agents — reusing `parse_skill_frontmatter()` for consistency would lose
any nested `tools:`/`model:` structure that `_read_frontmatter()` preserves.
Real example (`agents/codebase-analyzer.md:1-5`) shows agent frontmatter
today carries only `name` + `description` — no `args`-equivalent field, so
Step 2's "extend enumeration to also walk `agents/*.md`" has no analogous
free-text hint to reuse; agent `input_schema` bodies will need to be
hand-authored from the agent's description/tool-list rather than any
existing frontmatter field.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/action.py` (`_load_skills()`, lines 45-64) and/or
  `scripts/little_loops/cli/artifact.py` (`_load_skill_catalog()`, line 24+)
  — extension points for the new catalog function; both already enumerate
  `skills/*/SKILL.md` into `{name, description}` shape.
- `scripts/little_loops/generate_schemas.py` — potential home for a shared
  typed-field JSON-Schema-builder pattern (`_str()`/`_int()`/`_schema()`,
  lines 33-74) if `input_schema` bodies are hand-authored rather than
  derived from frontmatter.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.build_streaming()`
  (lines ~263-264) is the current `--tools` CSV assembly site; would need to
  consume the new catalog once it exists (actual wiring is FEAT-2672/2673's
  scope, not this issue's).
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
  (~282-328), the `resolve_host()` call site.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py:cmd_list()` (lines 189-194) — live CLI
  contract: `ll-action list` prints `_load_skills()`'s JSON output verbatim
  (`skills = _load_skills(); print_json(skills)`). If the catalog function
  changes `_load_skills()`'s return shape (e.g. adding `input_schema`), this
  is the CLI surface whose output contract changes.
- `scripts/little_loops/cli/artifact.py:cmd_policy_builder()` (lines 77-105)
  — live CLI contract: `ll-artifact policy-builder` consumes
  `_load_skill_catalog()` directly, stamping it into generated HTML as a
  `catalog_json` JS island (lines 99-100).

### Similar Patterns
- `scripts/little_loops/cli/action.py:_load_skills()` (lines 45-64) and
  `scripts/little_loops/cli/artifact.py:_load_skill_catalog()` (line 24+)
  — existing catalog-builder precedents to extend.
- `scripts/little_loops/generate_schemas.py` — `_schema()` (lines 57-74) and
  typed-field helpers show the repo's convention for hand-authored
  JSON-Schema property dicts; also see `BLIND_COMPARATOR_SCHEMA` in
  `scripts/little_loops/fsm/evaluators.py` (lines 176-201) for an
  `input_schema`-shaped module-level dict constant.
- `scripts/little_loops/host_runner.py` — `CapabilityEntry`/`HookEntry`/
  `CapabilityReport` frozen-dataclass trio (lines 118-156).
- `scripts/little_loops/adapters/codex.py:_format_agent_toml()` (lines
  207-247) and `CodexEmitter.emit_skill()`/`emit_command()` (lines 255-340+)
  — parallel "read SKILL.md frontmatter → derive rich fields → emit a
  different host's definition format" conversion.

### Tests
- No dedicated test exists yet for `cli/action.py:_load_skills()` or
  `cli/artifact.py:_load_skill_catalog()` — write new tests alongside the
  extension (tdd_mode is enabled for this project).
- `scripts/tests/test_generate_schemas.py` — precedent for testing
  schema-dict output shape if the catalog reuses `generate_schemas.py`'s
  builder pattern.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction**: `_load_skill_catalog()` is not entirely untested —
  `scripts/tests/test_policy_builder_emit.py` exercises it indirectly via
  `cmd_policy_builder()` (`rc = cmd_policy_builder(args, logger)`, lines
  25/58). No test asserts its exact return shape directly, but a shape
  change isn't invisible to the suite the way the issue's Tests section
  implies.
- `scripts/tests/test_action.py::TestLoadSkills::test_skill_dict_has_name_and_description`
  and `::test_skill_dict_includes_args_when_present` — **will break**, not
  just need updating: both assert exact dict equality
  (`assert skills == [{"name": ..., "description": ..., "args": None}]`).
  Adding an `input_schema` key to `_load_skills()`'s per-entry shape breaks
  these assertions.
- `scripts/tests/test_adapt_agents_for_codex.py` and
  `scripts/tests/test_adapters.py::TestProcessAgentsTraversal` (with its
  `_make_agent()` fixture factory, lines 60-76) — the closest existing
  pattern for the new `agents/*.md`-walking piece specifically (more
  directly transferable than `test_adapt_skills_for_codex.py`, which only
  covers skills). `_make_agent()`'s `name`/`description`/`model`/`tools`
  frontmatter shape mirrors real `agents/*.md` files.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — no `## little_loops.cli.action` or
  `## little_loops.cli.artifact` module section exists today; a new
  catalog function/`ToolDefinition` dataclass would be the first API.md
  entry for either module, not an edit to an existing one. Follow the
  `CapabilityEntry`/`HookEntry`/`CapabilityReport` doc pattern already at
  lines 8066-8135 (frozen dataclass definition + field table) as the
  precedent to replicate. `parse_skill_frontmatter` is already documented
  at lines 6084-6107 with the exact "nested structures are dropped" caveat
  this issue's parser-reconciliation question (§ Codebase Research
  Findings) must resolve before agents/*.md enumeration can rely on it.
- `docs/reference/CLI.md` — documents the `ll-artifact policy-builder`
  command (~line 3101) that consumes `_load_skill_catalog()`; update if the
  catalog's shape or the command's output changes.
- `docs/ARCHITECTURE.md:980` — names `cli/action.py:_load_skills()`
  explicitly as the canonical example of "little-loops generators stamp
  resolved project context into their output at generation time" (citing
  `ll-artifact policy-builder` as the consumer). Stale if this issue
  changes `_load_skills()`'s role or return shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/adapters/core.py:process_agents()` (lines 242-304)
  and its local `_read_frontmatter()` (lines 77-87) — the only existing
  `agents/*.md` walker; a second, non-`parse_skill_frontmatter` parsing
  path the new catalog function should reconcile with rather than
  duplicate.
- `scripts/tests/test_adapt_skills_for_codex.py:200-284` — closest
  transferable test template: `tmp_path`-based fixture SKILL.md files via
  helper factories (`_make_skill()`, `_make_skill_block_scalar()`), plus an
  error-path test mocking `Path.read_text` for unreadable files. More
  directly applicable than `test_generate_schemas.py` since it tests a
  directory-walk/frontmatter-enumeration function, not schema-dict shape.
- `scripts/tests/test_action.py`, `scripts/tests/test_frontmatter.py`,
  `scripts/tests/test_adapters.py`, `scripts/tests/test_host_runner.py` —
  existing test files covering the modules this issue extends; new tests
  should live alongside these rather than a new top-level test file.
- `scripts/little_loops/fsm/evaluators.py:74-106` (`DEFAULT_LLM_SCHEMA`) —
  flat `{"type": "object", "properties": {...}, "required": [...]}` dict,
  the closest existing example of an Anthropic-style `input_schema` body
  already in the repo (used for `--json-schema` structured output, not tool
  definitions).
- `_load_skills()` (`cli/action.py:45-64`) walks **skills only** — it does
  not walk `commands/*.md`. `_load_skill_catalog()` (`cli/artifact.py:24-56`)
  walks both `skills/*/SKILL.md` and `commands/*.md` but its returned dict
  drops the `args`/`argument-hint` field that `_load_skills()` keeps —
  neither is a drop-in base; the new catalog function needs `args` from one
  and command coverage from the other.

## Implementation Steps

1. Spike: confirm whether `args`/`argument-hint` free text is sufficient to
   derive `input_schema`, or whether schemas need hand-authoring per tool.
2. Extend the skill/command enumeration to also walk `agents/*.md`.
3. Build the catalog-assembly function producing Anthropic Messages API
   `tools` array entries (`name`, `description`, `input_schema`, optional
   `cache_control`), with tests.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

4. Update `scripts/tests/test_action.py`'s `TestLoadSkills::test_skill_dict_has_name_and_description`
   and `::test_skill_dict_includes_args_when_present` — their exact
   dict-equality assertions will break once `_load_skills()` (or its
   replacement) gains an `input_schema` key.
5. Add `docs/reference/API.md` module sections for whichever module houses
   the new catalog function/`ToolDefinition` dataclass, following the
   `CapabilityEntry`/`HookEntry`/`CapabilityReport` doc pattern (lines
   8066-8135) as precedent.
6. Update `docs/ARCHITECTURE.md:980` and `docs/reference/CLI.md`
   (~line 3101, `ll-artifact policy-builder`) if `_load_skills()`'s role or
   `_load_skill_catalog()`'s output shape changes.

## Acceptance Criteria

- [ ] A function exists that produces a full Anthropic Messages API `tools`
      array for little-loops' own tool set (not just names).
- [ ] Each catalog entry includes `name`, `description`, and `input_schema`
      at minimum.
- [ ] `agents/*.md` frontmatter is enumerated alongside `skills/*/SKILL.md`
      and `commands/*.md`.
- [ ] FEAT-2672 and FEAT-2673 can each name this catalog as their input data
      structure without further architectural investigation.

## Impact

- **Priority**: P2 - Prerequisite for FEAT-2672/FEAT-2673, both of which are
  blocked on this catalog-assembly function existing.
- **Effort**: Medium - Extends existing enumeration precedents
  (`_load_skills()`, `_load_skill_catalog()`) rather than building from
  scratch, but requires reconciling two divergent frontmatter parsers and
  hand-authoring `input_schema` bodies per tool.
- **Risk**: Low - Additive; existing `_load_skills()`/`_load_skill_catalog()`
  callers are unaffected unless their return shape changes, which is
  called out explicitly in the Wiring Phase.
- **Breaking Change**: No (unless `_load_skills()`'s return shape changes in
  place rather than via a new function — see Wiring Phase step 4 for the
  two tests that would break in that case).

## Resolution

Added `scripts/little_loops/tool_catalog.py` — a new, additive module (not an
in-place edit of `_load_skills()`/`_load_skill_catalog()`, so their existing
tests and CLI/HTML-stamping contracts are untouched):

- `ToolDefinition` — frozen dataclass (`name`, `description`, `input_schema`,
  `cache_control: dict[str, str] | None = None`), following the
  `CapabilityEntry`/`HookEntry`/`CapabilityReport` precedent.
- `assemble_tool_catalog(project_root)` — walks `skills/*/SKILL.md`,
  `commands/*.md`, `agents/*.md` (each `sorted(glob(...))`), all three
  standardized on `frontmatter.parse_skill_frontmatter()`. Missing
  directories yield no entries, never raise.
- `to_anthropic_tools(entries)` — serializes to the literal Anthropic
  `tools` array shape, omitting `cache_control` entirely when unset (the
  API rejects a literal `null`).
- `input_schema` is hand-authored per entry *kind*, per the issue's spike
  finding that free-text `args`/`argument-hint` carries no type
  information: skills/commands get a single opaque `args` string property
  when a hint exists (else empty-properties object); agents get a fixed
  `description`/`prompt` schema mirroring the real Agent-tool contract.
  `cache_control` population is left to FEAT-2681/downstream, out of scope
  here.

16 new tests in `scripts/tests/test_tool_catalog.py` (TDD: confirmed Red via
`ModuleNotFoundError` before the module existed, Green after). Added a
`## little_loops.tool_catalog` section to `docs/reference/API.md` following
the `CapabilityEntry` doc pattern. No other Wiring Phase doc/test updates
were needed — those were conditioned on `_load_skills()`/
`_load_skill_catalog()` changing shape in place, which this issue
deliberately avoids.

## Status

**Done** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-07-18T20:14:08 - `e7b62e0a-83fc-4e49-9d66-e222ca33f335.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `d62b6170-d4a7-4105-95e8-33164a8f5ae5.jsonl`
- `/ll:wire-issue` - 2026-07-18T20:09:40 - `39b90054-36a2-4b0e-b28f-e834ba100fd3.jsonl`
- `/ll:refine-issue` - 2026-07-18T20:02:44 - `55566d11-1008-42c9-bf4c-345dceb0b69c.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `478e94ef-30f6-4532-a6ed-1ba334c74117.jsonl`
- `/ll:manage-issue` - 2026-07-18T20:26:47Z - `c712b5ae-28ef-4004-aa04-ce77b9b50734.jsonl`
