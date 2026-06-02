---
id: FEAT-1625
type: FEAT
priority: P4
status: done
completed_at: 2026-05-23T04:31:16Z
parent: EPIC-1626
depends_on:
- FEAT-1624
relates_to:
- FEAT-1160
- FEAT-1623
- FEAT-1624
confidence_score: 100
outcome_confidence: 88
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1625: ctx-stats Docs and Wiring — Documentation, Config Schema, and Count Bumps

## Summary

Complete all documentation, configuration schema, template updates, and count-bump wiring for `ll-ctx-stats`. This is a mechanical enumeration pass across 17+ sites once the CLI command exists (FEAT-1624 merged).

## Current Behavior

After FEAT-1624 lands, `ll-ctx-stats` exists as an installed CLI entry point but is invisible to project documentation and tooling: it is absent from `.claude/CLAUDE.md`, README CLI counts, `/ll:help`, `skills/init/SKILL.md`'s Bash allow-list, and `skills/configure/areas.md`. The `analytics` config key is rejected by `config-schema.json` (`additionalProperties: false`), no project template seeds it, and the parallel `test_authorize_all_count_is_25` assertions in `test_feat1504_doc_wiring.py` and `test_ll_logs_wiring.py` lock the published CLI tool count at 25.

## Expected Behavior

All 17+ documentation, config, template, and test count sites consistently reference `ll-ctx-stats` and the `analytics` config block. `config-schema.json` validates the new key; all 9 project templates seed `analytics.enabled = false`; both `test_authorize_all_count_is_*` tests pass at 26; `/ll:help` and `skills/configure/areas.md` advertise the tool; `skills/init/SKILL.md`'s two Bash allow-list blocks authorize `Bash(ll-ctx-stats:*)`.

## Motivation

Without this wiring pass, users cannot discover `ll-ctx-stats` via `/ll:help`, `ll-doctor`, or the `/ll:init` workflow; new projects bootstrapped from any of the 9 templates will not have the `analytics` config block and will fail schema validation if a hook tries to write one; and CI fails on stale `test_authorize_all_count_is_25` assertions the moment FEAT-1624 lands. Mechanical enumeration is low-risk but high-value for tool discoverability and unblocks downstream automation that enumerates ll- CLI tools.

## Use Case

A developer runs `/ll:init` on a fresh TypeScript project. They expect (a) `skills/init/SKILL.md` to authorize all 26 ll- CLI tools — including `ll-ctx-stats` — in both Bash allow-list blocks, (b) the generated `ll-config.json` to include `"analytics": {"enabled": false}` per `templates/typescript.json`, and (c) `/ll:help` to list `ll-ctx-stats` with a one-line description. Without this issue, the new CLI tool ships invisibly: it is installed, but no surface ever mentions it, so users never discover it and `/ll:init`-generated configs cannot opt into analytics.

## Parent Issue
Decomposed from FEAT-1160: Context Window Analytics Command

## Scope
Covers Implementation Steps 8, 9, 10, 11, 12, 13 (docs portion), 14, 16 from FEAT-1160. Requires FEAT-1624 merged so `ll-ctx-stats` entry point exists before updating test count assertions.

### Pre-completed Work (verified via codebase research)
The following Step 9 deliverables already landed (likely via FEAT-1624) and should be **verified-and-skipped**, not re-done:
- `config-schema.json:1203-1214` — the `"analytics"` property block (with `enabled: boolean, default: false`) is already present, sibling to `orchestration`, before the closing `additionalProperties: false` at line 1216.
- `scripts/tests/test_config_schema.py:136-155` — `test_analytics_in_schema` already exists and validates the schema block.
- `scripts/pyproject.toml:73` — `ll-ctx-stats = "little_loops.cli:main_ctx_stats"` entry point already registered.

Remaining work is the 17+ enumeration sites + 9 template seeds + the two count-bump tests.

## Acceptance Criteria
- [ ] `ll-ctx-stats` appears in `.claude/CLAUDE.md` CLI Tools section
- [ ] README CLI count is 29 (both occurrences)
- [ ] `config-schema.json` has `"analytics"` property block with `enabled` sub-property
- [ ] All 9 project templates have `"analytics": {"enabled": false}`
- [ ] `commands/help.md` has `ll-ctx-stats` entry in CLI TOOLS block
- [ ] `skills/configure/areas.md` says "Authorize all 26 ll- CLI tools" and lists `ll-ctx-stats`
- [ ] `test_feat1504_doc_wiring.py::test_authorize_all_count_is_26` passes
- [ ] `test_ll_logs_wiring.py::test_authorize_all_count_is_26` passes
- [ ] `skills/init/SKILL.md` both Bash allow-list blocks include `ll-ctx-stats`
- [ ] All tests pass after count bumps

## Proposed Solution

### Step 8: Core documentation updates
- `.claude/CLAUDE.md` — add `ll-ctx-stats` to the **CLI Tools** section list
- `README.md` — increment `28 typed CLI tools` / `28 CLI tools` to `29` (two occurrences: lines 46 and 166)
- `CONTRIBUTING.md` — add `ctx_stats.py` to the package structure tree (~line 188)
- `scripts/little_loops/cli/__init__.py` — add `ll-ctx-stats` bullet to module-level docstring (lines 1–30)

### Step 9: Config schema + templates
- `config-schema.json` — **already done** (FEAT-1624 added the `"analytics"` block at lines 1203-1214). Verify only; no edit needed.
- All 9 project templates — add `"analytics": {"enabled": false}` **immediately before** `"context_monitor"` (which must remain the final top-level key — see Codebase Research Findings):
  - `templates/generic.json`
  - `templates/python-generic.json`
  - `templates/javascript.json`
  - `templates/typescript.json`
  - `templates/go.json`
  - `templates/java-maven.json`
  - `templates/java-gradle.json`
  - `templates/rust.json`
  - `templates/dotnet.json`

### Step 10: help.md CLI TOOLS block
- `commands/help.md` — add `ll-ctx-stats` entry to the CLI TOOLS block (begins line 239); include one-line description

### Step 11 + 14: Count bump in areas.md and parallel test files
- `skills/configure/areas.md` — change `"Authorize all 25 ll- CLI tools"` to `26` and add `ll-ctx-stats` to the inline tool list (line 823)
- `scripts/tests/test_feat1504_doc_wiring.py` — rename `TestConfigureAreasWiring.test_authorize_all_count_is_25` (line 47) to `_count_is_26` and update the assertion string to `"Authorize all 26"`
- `scripts/tests/test_ll_logs_wiring.py` — rename `TestConfigureAreasWiring.test_authorize_all_count_is_25` (line 43) to `_count_is_26` and update the assertion string to `"Authorize all 26"` (parallel occurrence)

### Step 12: skills/init/SKILL.md Bash allow-list
- `skills/init/SKILL.md` — add `"Bash(ll-ctx-stats:*)"` to both Bash allow-list JSON array blocks (~lines 502–522 and 583–619) and add `ll-ctx-stats` to both narrative description lists

### Step 16: Template enumeration verification
Verify all 9 templates updated in Step 9 pass `config-schema.json` validation (no `additionalProperties` violations).

## Integration Map

### Files to Modify
- `.claude/CLAUDE.md` — CLI Tools list
- `README.md` — 2 count occurrences (lines 46, 166)
- `CONTRIBUTING.md` — package structure tree
- `scripts/little_loops/cli/__init__.py` — module docstring
- `config-schema.json` — `"analytics"` property block
- `templates/generic.json` — analytics key
- `templates/python-generic.json` — analytics key
- `templates/javascript.json` — analytics key
- `templates/typescript.json` — analytics key
- `templates/go.json` — analytics key
- `templates/java-maven.json` — analytics key
- `templates/java-gradle.json` — analytics key
- `templates/rust.json` — analytics key
- `templates/dotnet.json` — analytics key
- `commands/help.md` — CLI TOOLS block
- `skills/configure/areas.md` — count bump 25 → 26
- `skills/init/SKILL.md` — two Bash allow-list blocks
- `docs/reference/CLI.md` — add `ll-ctx-stats` entry
- `docs/reference/API.md` — add `main_ctx_stats` reference

### Dependent Files (Callers/Importers)
N/A — this is a wiring pass; no runtime code consumes these doc/config surfaces directly. FEAT-1624 provides the `main_ctx_stats` entry point referenced here.

### Similar Patterns
- Prior CLI-tool-add wiring passes established the enumeration shape and the 25-tool baseline now being bumped to 26. Keep changes consistent with these precedents.

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **FEAT-1504 covered `ll-doctor`** (not `ll-logs`, contrary to the original note). `scripts/tests/test_feat1504_doc_wiring.py:1` docstring confirms this. The parallel `ll-logs` wiring lives in `scripts/tests/test_ll_logs_wiring.py`. FEAT-1625 should mirror both — they are the two canonical examples.
- **`test_authorize_all_count_is_25` is a literal substring match**, not dynamic counting: `assert "Authorize all 25" in content` against `skills/configure/areas.md` text. Bumping requires updating the assertion string to `"Authorize all 26"` in both test files.
- **`test_feat1504_doc_wiring.py` also asserts ll-doctor presence in `docs/reference/HOST_COMPATIBILITY.md`**, but this is `ll-doctor`-specific (capability probing). `ll-ctx-stats` does NOT belong in `HOST_COMPATIBILITY.md` — no analogous assertion needed.
- **The `at-least-N-occurrences` test pattern** (`test_ll_doctor_in_boilerplate_blocks`, `test_feat1504_doc_wiring.py:61-67`) asserts `content.count("ll-doctor") >= 2` against `skills/init/SKILL.md` — confirming the two-allow-list-block requirement. FEAT-1625 should add an analogous test if it gains a `test_feat1625_doc_wiring.py` file (see "Test file question" below).
- **`templates/*.json` shape**: every template ends with `"context_monitor": { "enabled": true }` as the **last** top-level key (no trailing comma). Insert `"analytics": { "enabled": false }` *before* `context_monitor` to preserve "context_monitor stays last" convention. Example from `templates/python-generic.json:69-71`.
- **`skills/init/SKILL.md` allow-list formatting** (lines 516-523 and parallel block ~617): 5-space indent, double-quoted strings, comma after every entry except the last. Add `"Bash(ll-ctx-stats:*)"` adjacent to existing `"Bash(ll-doctor:*)"` entries.
- **`skills/configure/areas.md:823` format**: single-line comma-separated inline prose list (NOT a Markdown bullet list, NOT JSON). Current text reads `"Authorize all 25 ll- CLI tools and handoff write: ll-action, ll-issues, ..., ll-doctor, Write(.ll/ll-continue-prompt.md)"`. Insert `ll-ctx-stats` into the inline list adjacent to `ll-doctor`.
- **`analytics` config consumption point**: `scripts/little_loops/hooks/post_tool_use.py::handle()` calls `feature_enabled(config, "analytics.enabled")` and no-ops when absent/false. Confirms the schema/template wiring is what actually gates the feature at runtime.

### Tests
- `scripts/tests/test_feat1504_doc_wiring.py` — rename + assertion update (25 → 26)
- `scripts/tests/test_ll_logs_wiring.py` — rename + assertion update (parallel 25 → 26)
- `scripts/tests/test_config_schema.py` — verifies `analytics` property accepted; all 9 templates validate against the updated schema

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — **4 assertions will break** when `areas.md` and `README.md` are updated; must be fixed atomically:
  - `TestConfigureAreasWiring.test_count_updated_to_17` (line 57): change `"Authorize all 25"` → `"Authorize all 26"`
  - `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` (line 196): change `"Authorize all 25"` → `"Authorize all 26"`
  - `TestFeat1045DocUpdates.test_readme_tool_count_is_20` (line 79): change `"28 typed CLI tools"` → `"29 typed CLI tools"`
  - `TestFeat1229LlActionWiring.test_readme_tool_count_is_20` (line 192): change `"28 typed CLI tools"` → `"29 typed CLI tools"`
- `scripts/tests/test_feat1625_doc_wiring.py` — new test file to create, modeled on `test_feat1504_doc_wiring.py`; add 7 assertions covering `ll-ctx-stats` presence in: `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md`, `skills/configure/areas.md` (tool name + count `"Authorize all 26"`), and `skills/init/SKILL.md` (Bash allow-list entry + `count("ll-ctx-stats") >= 2` for boilerplate blocks). No `TestHostCompatibilityWiring` class — `ll-ctx-stats` is excluded from `HOST_COMPATIBILITY.md` per codebase research.

### Documentation
- `.claude/CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `commands/help.md`, `docs/reference/CLI.md`, `docs/reference/API.md` — as listed above

### Configuration
- `config-schema.json` + 9 `templates/*.json` files — as listed above

## Implementation Steps
1. Core docs (CLAUDE.md CLI Tools list, README counts, CONTRIBUTING tree, package docstring)
2. Config schema `analytics` property + 9 template seeds
3. `commands/help.md` CLI TOOLS entry
4. Count bump 25 → 26 in `skills/configure/areas.md` + parallel test renames/assertions
5. `skills/init/SKILL.md` two Bash allow-list blocks + narrative lists
6. Reference docs (`docs/reference/CLI.md`, `docs/reference/API.md`)
7. Verify: run `test_feat1504_doc_wiring.py`, `test_ll_logs_wiring.py`, `test_config_schema.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_create_extension_wiring.py` — fix 4 stale count assertions atomically with Step 1 and Step 4 edits (2× `"Authorize all 25"` → `"Authorize all 26"` in `TestConfigureAreasWiring` and `TestFeat1229LlActionWiring`; 2× `"28 typed CLI tools"` → `"29 typed CLI tools"` in `TestFeat1045DocUpdates` and `TestFeat1229LlActionWiring`)
9. Create `scripts/tests/test_feat1625_doc_wiring.py` — new wiring test file modeled on `test_feat1504_doc_wiring.py`; 7 assertions for `ll-ctx-stats` presence/count across help.md, CLI.md, CLAUDE.md, areas.md, and init SKILL.md

## Verification Strategy
After all edits, run `python -m pytest scripts/tests/test_feat1504_doc_wiring.py scripts/tests/test_ll_logs_wiring.py scripts/tests/test_config_schema.py scripts/tests/test_create_extension_wiring.py scripts/tests/test_feat1625_doc_wiring.py -v` to confirm all count assertions and schema tests pass. Note: `test_create_extension_wiring.py` must be included — it contains 4 assertions on `areas.md` and `README.md` counts that will fail if not updated atomically.

## Impact
- **Priority**: P4 — mechanical follow-up to FEAT-1624; not user-blocking but blocks downstream discoverability and CI passes once FEAT-1624 lands.
- **Effort**: Medium — 17+ sites, but each edit is mechanical (string add, count bump, JSON key insert).
- **Risk**: Low — no behavior changes; parallel count-bump tests guard against drift and `test_config_schema.py` guards template validity.
- **Breaking Change**: No

## Labels
`feature`, `documentation`, `wiring`, `config-schema`, `ctx-stats`

## Session Log
- `/ll:manage-issue` - 2026-05-23T04:31:16Z - `001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
- `/ll:ready-issue` - 2026-05-23T04:23:30 - `aa901c73-8efc-47cf-b03e-fd087f3ebfcc.jsonl`
- `/ll:confidence-check` - 2026-05-22T00:00:00 - `fdda758a-3d91-4a1a-addc-2b1e3900fe07.jsonl`
- `/ll:wire-issue` - 2026-05-23T04:20:28 - `56db5cd8-df7b-4e18-8560-530a021ab1b9.jsonl`
- `/ll:refine-issue` - 2026-05-23T04:14:16 - `a08c39dd-7ac9-4941-ae83-00e2a448c148.jsonl`
- `/ll:format-issue` - 2026-05-23T03:58:36 - `9455bcda-9d57-49a9-9450-15ca75ba28f1.jsonl`
- `/ll:issue-size-review` - 2026-05-22T00:00:00 - `fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status
**Done** | Created: 2026-05-22 | Completed: 2026-05-23 | Priority: P4

## Resolution

All 17+ documentation, config, template, and test wiring sites updated to reference `ll-ctx-stats` and the `analytics` config block.

**Files modified (19 + 1 new test file):**
- Core docs: `.claude/CLAUDE.md`, `README.md` (2 count bumps 28→29), `CONTRIBUTING.md` (cli tree), `scripts/little_loops/cli/__init__.py` (docstring)
- Schema/templates: `config-schema.json` (verified pre-existing), all 9 `templates/*.json` seeded with `"analytics": {"enabled": false}` inserted before `context_monitor`
- Discovery surfaces: `commands/help.md` (CLI TOOLS block), `skills/configure/areas.md` (count 25→26 + tool name)
- `skills/init/SKILL.md`: added `Bash(ll-ctx-stats:*)` allow-list entry + entry in both CLAUDE.md narrative boilerplate blocks
- Reference docs: `docs/reference/CLI.md` (new `### ll-ctx-stats` section), `docs/reference/API.md` (new `### main_ctx_stats` entry)
- Test count bumps: `test_feat1504_doc_wiring.py`, `test_ll_logs_wiring.py` (rename `_25` → `_26` + assertion string)
- Test wiring drift: `test_create_extension_wiring.py` (4 stale count assertions: 2× "Authorize all 25"→26, 2× "28 typed CLI tools"→29)
- New: `scripts/tests/test_feat1625_doc_wiring.py` (7 assertions covering ctx-stats wiring across help/CLI/CLAUDE/areas/init)

**Verification:** All 85 targeted wiring tests pass (`test_feat1504_doc_wiring.py`, `test_ll_logs_wiring.py`, `test_config_schema.py`, `test_create_extension_wiring.py`, `test_feat1625_doc_wiring.py`). Full suite: 7362 passed, 1 pre-existing failure unrelated to this issue (`test_feat1287_doc_wiring.py::TestClaudeMdWiring::test_skill_count_updated` expects `(30 skills)` in CLAUDE.md, which is absent before this change too — verified by `git stash` baseline).
