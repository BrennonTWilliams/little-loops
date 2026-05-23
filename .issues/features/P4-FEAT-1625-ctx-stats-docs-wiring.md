---
id: FEAT-1625
type: FEAT
priority: P4
status: open
parent: EPIC-1626
depends_on:
- FEAT-1624
relates_to:
- FEAT-1160
- FEAT-1623
- FEAT-1624
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
- `config-schema.json` — add `"analytics"` property block to top-level `"properties"` object (required — schema uses `"additionalProperties": false`); include `enabled` sub-property with boolean type
- All 9 project templates — add `"analytics": {"enabled": false}` beside `context_monitor`:
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
- Prior CLI-tool-add wiring passes (see FEAT-1504 for `ll-logs`) established the enumeration shape and the 25-tool baseline now being bumped to 26. Keep changes consistent with that precedent.

### Tests
- `scripts/tests/test_feat1504_doc_wiring.py` — rename + assertion update (25 → 26)
- `scripts/tests/test_ll_logs_wiring.py` — rename + assertion update (parallel 25 → 26)
- `scripts/tests/test_config_schema.py` — verifies `analytics` property accepted; all 9 templates validate against the updated schema

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

## Verification Strategy
After all edits, run `python -m pytest scripts/tests/test_feat1504_doc_wiring.py scripts/tests/test_ll_logs_wiring.py scripts/tests/test_config_schema.py -v` to confirm all count assertions and schema tests pass.

## Impact
- **Priority**: P4 — mechanical follow-up to FEAT-1624; not user-blocking but blocks downstream discoverability and CI passes once FEAT-1624 lands.
- **Effort**: Medium — 17+ sites, but each edit is mechanical (string add, count bump, JSON key insert).
- **Risk**: Low — no behavior changes; parallel count-bump tests guard against drift and `test_config_schema.py` guards template validity.
- **Breaking Change**: No

## Labels
`feature`, `documentation`, `wiring`, `config-schema`, `ctx-stats`

## Session Log
- `/ll:format-issue` - 2026-05-23T03:58:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9455bcda-9d57-49a9-9450-15ca75ba28f1.jsonl`
- `/ll:issue-size-review` - 2026-05-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

## Status
**Open** | Created: 2026-05-22 | Priority: P4
