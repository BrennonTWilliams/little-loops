---
id: ENH-1916
title: history.*/analytics.* config discoverability + EPIC-1707 back-links
type: ENH
priority: P3
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T21:38:03Z'
completed_at: '2026-06-04T02:03:13Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1913
- ENH-1905
- ENH-1907
- ENH-1909
- ENH-1911
- ENH-1914
- ENH-1915
depends_on:
- ENH-1913
- ENH-1911
- ENH-1909
labels:
- history-db
- configurability
- docs
confidence_score: 96
outcome_confidence: 77
score_complexity: 18
score_test_coverage: 15
score_ambiguity: 22
score_change_surface: 22
---

# ENH-1916: Config discoverability + EPIC-1707 back-links

## Summary

Because there is intentionally no `ll-config get` CLI, the new `history.*` /
`analytics.*` keys are only discoverable if they are documented and surfaced by
`/ll:configure`. This issue closes the discoverability gap and fixes
bidirectional EPIC wiring so dependency/progress tooling counts the new work.

## Motivation

A consistency effort that ships tunable keys nobody can find is consistent in
principle only. Two concrete gaps from the EPIC-1707 audit:

1. **Discoverability**: no consolidated reference of every `history.*` /
   `analytics.*` key, its default, and meaning.
2. **Broken EPIC wiring**: EPIC-1707's `relates_to` does **not** include
   ENH-1909, ENH-1911, or the new children — so `ll-deps` / `epic-progress`
   under-count the work. Child→parent links (added in those issues) must be
   matched by parent→child links.

## Implementation Steps

1. **Patch EPIC-1707 `relates_to`** — Edit `.issues/epics/P2-EPIC-1707-history-db-as-agent-context-layer.md`
   frontmatter line 13: append ENH-1909 and ENH-1911 to the existing inline list (ENH-1913,
   1914, 1915, 1916 are already present). Run `ll-deps validate` to confirm no new cycles and
   that all referenced IDs resolve.

2. **Author `### \`history\`` section in CONFIGURATION.md** — Insert after the `### \`analytics\``
   section at `docs/reference/CONFIGURATION.md:437`, following the exact same structure:
   - One-paragraph description with `(ENH-1913)` parenthetical
   - 4-column `| Key | Type | Default | Description |` table for the 4 flat keys
     (`velocity_window`, `effort_fields`, `max_age_days`, `planning_skills`) pulled
     from `config-schema.json:1406–1450`
   - Sub-object tables for `session_digest`, `evolution`, `go_no_go`, `capture_issue`
     pulled from `config-schema.json:1451–1503`
   - A minimal JSON example block
   - Remove the orphan `### \`history.session_digest\`` entry from `## Manual Configuration`
     (currently `docs/reference/CONFIGURATION.md:1088–1115`) or fold it into the new section.

3. **Add `history` area to `skills/configure/SKILL.md`** — The skill is **fully hardcoded**;
   it does NOT read `config-schema.json` dynamically. Four edits are required:
   - Add a row to the `## Area Mapping` table: `| history | history | History.db consumer tuning |`
   - Append `|history` to the `argument-hint` frontmatter pipe-separated string
   - Add `history` entry to the `## Mode: --list` example output block
   - Add `history` to the `## Arguments` list and to one of the five interactive picker pages

4. **Add `## Area: history` interactive flow to `skills/configure/areas.md`** — Model after
   `## Area: analytics` (line 1216). Include a "Current Values" display block and Round 1
   questions for the most commonly tuned keys: `history.velocity_window`,
   `history.max_age_days`, `history.planning_skills`, `history.session_digest.enabled`.
   Defaults come from `config-schema.json:1406–1503` and `HistoryConfig` dataclass
   (`scripts/little_loops/config/features.py:716`).

5. **Add `## history --show` template to `skills/configure/show-output.md`** — Model after
   `## analytics --show` (line 218). Render all `history.*` flat keys and sub-object keys
   with their defaults from `config-schema.json:1406–1503`.

6. **Validate**: `ll-deps validate` (EPIC-1707 edges + no cycles); `/ll:configure --list`
   (confirms `history` appears in output); `/ll:configure history --show` (confirms all keys
   display correctly).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/COMMANDS.md` — in the `### \`/ll:configure\`` section's `area` argument
   value list, append `history` after `decisions` (follow the same pattern as every prior
   configure area addition to keep COMMANDS.md and SKILL.md in sync)
8. Update `docs/reference/API.md` — in `### BRConfig` → `#### Properties` table, add row for
   `history: HistoryConfig` (and `analytics_capture: AnalyticsCaptureConfig` which is also absent);
   cross-link to `CONFIGURATION.md#history` following the `decisions` / `design_tokens` subsection pattern
9. Write `scripts/tests/test_enh1916_doc_wiring.py` — new doc-wiring regression test file (see
   `### Tests` section above); run `python -m pytest scripts/tests/test_enh1916_doc_wiring.py -v`
   after completing Steps 1–8 to confirm all assertions pass

## Acceptance Criteria

- `ll-deps` validates the new dependency edges; EPIC-1707 `relates_to` contains
  every new child (1913, 1914, 1915, 1916) plus 1909 and 1911; no cycles.
- A single reference enumerates all `history.*` / `analytics.*` keys.
- `/ll:configure` lists or validates the new `history.*` keys.

## Success Metrics

- **EPIC dependency completeness**: `ll-deps` reports 0 validation errors; EPIC-1707 `relates_to` contains all 6 child IDs (1909, 1911, 1913, 1914, 1915, 1916).
- **Config key coverage**: reference table lists ≥ all keys added by ENH-1913 with default and description for each.
- **Configure discoverability**: running `/ll:configure` interactively surfaces the `history` section without requiring knowledge of key names.

## Scope Boundaries

- **In scope**: updating EPIC-1707 bidirectional links; authoring a consolidated `history.*` / `analytics.*` config reference; verifying `/ll:configure` coverage of the `history` namespace.
- **Out of scope**: defining new config keys (ENH-1913); changing `config-schema.json` structure; altering how `ll-config get` works (intentionally absent per design).

## API/Interface

N/A — No public API changes. This issue modifies issue metadata (frontmatter links) and documentation only.

## Integration Map

### Files to Modify
- `.issues/epics/P2-EPIC-1707-history-db-as-agent-context-layer.md:13` — append ENH-1909, ENH-1911
  to `relates_to` inline list (ENH-1913/1914/1915/1916 already present; only 1909 and 1911 are missing)
- `docs/reference/CONFIGURATION.md:437` — insert `### \`history\`` section after `### \`analytics\``;
  remove orphan `### \`history.session_digest\`` from `## Manual Configuration` (line 1088)
- `skills/configure/SKILL.md` — add `history` to `## Area Mapping` table, `argument-hint`
  frontmatter, `## Mode: --list` output block, `## Arguments` list, and one picker page
- `skills/configure/areas.md` — add `## Area: history` section after `## Area: analytics` (line 1216)
- `skills/configure/show-output.md` — add `## history --show` section after `## analytics --show` (line 218)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — add `history` to the `/ll:configure` `area` argument value list
  (currently ends at `analytics`; mirrors every SKILL.md area addition per Agent 2 side-effect analysis)
- `docs/reference/API.md` — add `history: HistoryConfig` row to `### BRConfig` → `#### Properties`
  table (follows the `design_tokens: DesignTokensConfig` / `decisions: DecisionsConfig` pattern found
  by Agent 2; `analytics_capture: AnalyticsCaptureConfig` is also absent and should be added at the
  same time)

### Read-Only References
- `config-schema.json:1406–1503` — complete `history.*` key names, types, defaults, descriptions
  (authoritative source for all table content; do not invent defaults)
- `config-schema.json:1365–1404` — `analytics.*` section (reference implementation pattern to follow)
- `scripts/little_loops/config/features.py` at `HistoryConfig` (line 716) — dataclass field names
  and sub-config types (`SessionDigestConfig`, `EvolutionConfig`, `GoNoGoConfig`, `CaptureIssueConfig`)
- `docs/reference/CONFIGURATION.md:437–470` — `analytics` section template (4-column table + JSON block)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/deps.py` at `_load_issues` (line 15) — reads `relates_to` from frontmatter
  via `find_issues()` → `IssueInfo`; used to validate EPIC-1707 edge additions
- `scripts/little_loops/issue_parser.py` at `IssueInfo.relates_to` (line 253) — frontmatter field;
  accepts inline YAML flow sequences `[ID1, ID2, ...]`
- `scripts/little_loops/dependency_mapper/analysis.py` at `validate_dependencies` (line 473) —
  broken-ref detection logic run by `ll-deps validate`

### Tests
- `ll-deps validate` — run after Step 1; confirms EPIC-1707 edges resolve and no cycles introduced
- `/ll:configure --list` — run after Steps 3–5; confirms `history` appears in area list
- `/ll:configure history --show` — run after Step 5; confirms all keys render with correct defaults

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1916_doc_wiring.py` — **new test file** following canonical configure-area
  addition pattern (model after `scripts/tests/test_enh1884_analytics_wiring.py`); must include:
  - `TestConfigureSkillMd` — asserts `history` in area mapping table and arguments list
  - `TestConfigureAreasMd` — asserts `## Area: history` and all `history.*` key names present
  - `TestConfigureShowOutputMd` — asserts `## history --show` and key fields present
  - `TestConfigurationMd` — asserts `### \`history\`` header and `velocity_window`, `max_age_days`,
    `session_digest`, `evolution`, `go_no_go`, `capture_issue` fields in CONFIGURATION.md
  - `TestEpic1707Frontmatter` — asserts ENH-1909 and ENH-1911 appear in EPIC-1707 `relates_to`

### Documentation
- `docs/reference/CONFIGURATION.md` — primary target; `### \`history\`` section (new)
  must enumerate all 8 key groups with type, default, and description per `config-schema.json:1406–1503`

## Dependencies

- **Depends on**: ENH-1913 (the `history` schema must exist for `/ll:configure`
  to surface it).

## Session Log
- `/ll:ready-issue` - 2026-06-04T01:57:20 - `80ac657b-a2fe-4dc9-ab64-61fdf8ddc11b.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `6bf7ef3b-ffba-4ead-8279-50cfad96b6d9.jsonl`
- `/ll:wire-issue` - 2026-06-04T01:51:05 - `99250592-55d9-4851-8853-7de1536ecc42.jsonl`
- `/ll:refine-issue` - 2026-06-04T01:45:37 - `72f74a0c-52e6-45fa-b827-ed29f633c353.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T21:44:12 - `39a37568-d7a7-42c9-8508-05b4e238e1ce.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

open
