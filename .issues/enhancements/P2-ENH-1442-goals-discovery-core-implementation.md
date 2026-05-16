---
id: ENH-1442
priority: P2
type: ENH
parent: ENH-1400
blocked_by:
- ENH-1402
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
status: done
completed_at: 2026-05-11T00:00:00Z
---

# ENH-1442: Goals Discovery — Core Implementation (scan-product, product-analyzer, hooks, tests)

## Summary

Implement the `goals_discovery` fallback path so `scan-product` synthesizes a temporary goals context from existing docs (README, roadmaps, vision files) when `ll-goals.md` is absent, rather than hard-stopping. Remove the independent goals-file read from the skill, update output metadata, downgrade the false-alarm hook warning, and add wiring tests.

## Parent Issue

Decomposed from ENH-1400: Implement `goals_discovery` in product-analyzer

## Files to Modify

- `commands/scan-product.md` — replace hard-exit block at Step 1.2 with discovery logic; inject synthesized `GOALS_CONTENT` into skill invocation
- `skills/product-analyzer/SKILL.md` — remove hard-stop on missing goals file; remove `### 2. Load Product Goals` independent file read; update `analysis_metadata` with `goals_source` and `discovered_from` fields; update `skipped_reason` enum (replace `goals_file_missing` with `goals_content_missing`)
- `hooks/scripts/session-start.sh` — downgrade `"Warning: product.enabled is true but goals file not found"` in `validate_enabled_features()` (lines 134–143) to an informational notice or remove it; missing `ll-goals.md` with `product.enabled: true` is valid after this change
- `scripts/tests/test_hooks_integration.py` — update `test_warns_product_without_goals` (line 1649) assertion to match changed hook message (or remove if warning is dropped)
- `scripts/tests/test_enh1442_doc_wiring.py` (new) — doc-wiring assertions per Integration Map

## Proposed Solution

### `commands/scan-product.md` — discovery path (replaces hard-exit at Step 1.2)

```
1. Read config: goals_discovery.max_files (default 5), goals_discovery.required_files (default ["README.md"])
2. Warn if required_files are missing (but continue)
3. Discover candidate files in priority order:
   - goals_discovery.required_files entries
   - **/ROADMAP*.md, **/roadmap*.md
   - **/vision*.md, **/goals*.md
   - **/requirements*.md, **/product*.md
   - README.md (always included)
   - CONTRIBUTING.md
4. Read up to max_files files
5. Synthesize temporary goals context:
   - Infer primary persona from README "for" / "who uses" language
   - Infer priorities from section headers, feature lists, roadmap items
   - Set goals_source: discovered, discovered_from: [list of files]
6. Inject synthesized context as GOALS_CONTENT into skill invocation
```

Remove the duplicate hard-exit block at Step 1.2.

Access config values via `{{config.product.goals_discovery.max_files}}` and `{{config.product.goals_discovery.required_files}}` — same pattern as `{{config.product.goals_file}}` at line ~67.

### `skills/product-analyzer/SKILL.md`

- Remove `goals_file_missing` from `## Guardrails` and `### 1. Configuration Check` hard-stop blocks
- Remove `### 2. Load Product Goals` section (or make it conditional: only read if `GOALS_CONTENT` is absent from injected prompt)
- Add to `analysis_metadata` output block (lines ~175-184):
  ```yaml
  goals_source: [explicit|discovered]
  discovered_from: ["README.md", ...]  # only when goals_source: discovered
  ```
- `skipped_reason` valid values after this change: `not_enabled`, `goals_content_missing` (new, for caller error)

### `scripts/tests/test_enh1442_doc_wiring.py` (new)

Assertions to include (follow pattern from `scripts/tests/test_enh1362_doc_wiring.py`):
- `goals_file_missing` absent from `SKILL.md`
- `goals_content_missing` present as a `skipped_reason` in `SKILL.md`
- `### 2. Load Product Goals` section does not contain `Read .ll/ll-goals.md`
- `goals_source` and `discovered_from` appear in `analysis_metadata` block of `SKILL.md`
- `goals_discovery.max_files` and `goals_discovery.required_files` interpolations present in `commands/scan-product.md`
- Hard-exit block ("Goals file not found") absent from `commands/scan-product.md`

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify (with exact line anchors)
- `commands/scan-product.md:73–88` — Step 1.2 hard-exit block ("Check goals file exists" → "If either check fails, stop execution"); replace entirely with discovery logic; `GOALS_CONTENT` is assigned at line 108 and injected into the skill at line 146 (`{{GOALS_CONTENT}}`)
- `skills/product-analyzer/SKILL.md:24–28` — `**STOP and return empty findings if**:` Guardrails block; remove `goals_file_missing` entry
- `skills/product-analyzer/SKILL.md:52–62` — `### 2. Load Product Goals` section; currently reads `.ll/ll-goals.md` **independently** (does not consume the `GOALS_CONTENT` injected by the command); must become conditional: only read the file when `GOALS_CONTENT` is absent from the injected prompt; set `goals_source: explicit` in that branch
- `skills/product-analyzer/SKILL.md:45–48` — `skipped_reason` valid values in the Configuration Check return shape; replace `goals_file_missing` with `goals_content_missing`
- `skills/product-analyzer/SKILL.md:175–184` — `analysis_metadata` output block; `goals_file` is currently hardcoded as string `".ll/ll-goals.md"`; replace with `goals_source: [explicit|discovered]` and `discovered_from: [...]`
- `hooks/scripts/session-start.sh:134–143` — `validate_enabled_features()` product block; the block reads `product.enabled` + `product.goals_file`, then runs `[ ! -f "$goals_file" ]` and echoes `"[little-loops] Warning: product.enabled is true but goals file not found: $goals_file"` to stderr
- `skills/product-analyzer/SKILL.md:17` — `## Context` section preamble; item 1 reads "**Product Goals** (`.ll/ll-goals.md`)" as the sole source; update to mention both explicit and discovered sources alongside the explicit path [Wiring pass]
- `skills/product-analyzer/SKILL.md:267` — `## What NOT to Do` section; contains "Don't proceed without `ll-goals.md`" instruction; must be removed or softened to reflect the discovery fallback path [Wiring pass]
- `skills/product-analyzer/SKILL.md` — `### 3. Goal-Gap Analysis`, `### 4. Persona Journey Analysis`, `### 5. Business Value Opportunities` output templates; each evidence block hardcodes `file: ".ll/ll-goals.md"` as the evidence source; must be generalized to reflect the actual source file (discovered file path or `ll-goals.md`) when `goals_source: discovered` [Wiring pass 2]
- `commands/scan-product.md` — `### 6.5. Confirm Issue Creation` and `### 8. Output Report` both display `**Goals File**: {{config.product.goals_file}}`; this will be misleading when goals were synthesized from discovered docs; must show actual source used (e.g., `**Goals Source**: auto-discovered from N docs` or the explicit path) [Wiring pass 2]

### New Files
- `scripts/tests/test_enh1442_doc_wiring.py` — new doc-wiring test file (follows codebase convention: `test_enh<issue-number>_doc_wiring.py`)

### Dependent Files (Callers/Importers)
- `config-schema.json:767–786` — `goals_discovery` object already defined inside `product` with `max_files` (integer, default 5, range 1–20) and `required_files` (array, default `["README.md"]`); no schema changes needed
- `scripts/tests/test_hooks_integration.py:1649–1669` — `test_warns_product_without_goals`; asserts `"product.enabled is true but goals file not found"` in `result.stderr`; must be updated or removed when the hook warning is dropped
- `commands/create-sprint.md` — `**Grouping Strategy 6: Goal-Aligned**` block gates goal-aligned sprint groupings on `product.goals_file` physical file existence; after ENH-1442, projects without `ll-goals.md` may produce issues with `goal_alignment` frontmatter but will still be skipped by this grouping — semantic gap not in ENH-1442 or ENH-1443 scope; note for a follow-up issue [Wiring pass]

### Similar Patterns
- `skills/init/SKILL.md:88–108` — template-file glob + `_meta.detect` array checking for project-type discovery (most analogous to the goals file candidate discovery loop)
- `skills/audit-docs/SKILL.md:43–56` — `find . -name "*.md" -not -path "./.git/*"` glob-based collection with exclusions
- `skills/init/SKILL.md:339–392` — warn-but-continue block; each check emits `Warning: '<name>' not found — <consequence>` then the block ends with `"**Always proceed to Step N regardless of results.**"` to make non-halting behavior unambiguous
- `scripts/tests/test_enh1362_doc_wiring.py` — canonical doc-wiring test: `PROJECT_ROOT = Path(__file__).parent.parent.parent`, one class per surface area, `content.index("## Section")` to scope assertions, assertion messages are full English sentences
- `scripts/tests/test_enh1433_doc_wiring.py` — second doc-wiring test example following same structure

### Tests
- `scripts/tests/test_hooks_integration.py:1649` — existing test to update (asserts old warning string)
- `scripts/tests/test_enh1442_doc_wiring.py` — new test file to create
- `scripts/tests/test_goals_parser.py` — existing goals-parser tests (no changes needed)
- `scripts/tests/test_hooks_integration.py:1671` — `test_no_warnings_when_properly_configured`; passes `goals_file` in config and creates the file; stays green post-change but stops verifying meaningful behavior if the warning block is dropped — review whether a new assertion for the `Note:` message (if kept) is needed [Wiring pass]
- `scripts/tests/test_enh1402_doc_wiring.py` — `TestGoalsFilePathFromConfig.test_section2_references_product_goals_file_config` (line ~122); calls `content.index("### 2. Load Product Goals")` and asserts `"product.goals_file"` is in that section; will raise `ValueError` if the heading is removed during ENH-1442 rewrite of Section 2 — **preserve the `### 2. Load Product Goals` heading** and ensure `product.goals_file` reference remains in the conditional branch [Wiring pass 2]
- `scripts/tests/test_enh1403_doc_wiring.py` — `TestSkillSection2ConditionalGoalsRead.test_section2_references_product_goals_file_config` (line ~59); same `### 2. Load Product Goals` heading dependency; must also survive the Section 2 rewrite [Wiring pass 2]

### Documentation
- `docs/reference/CONFIGURATION.md` — documents `product.goals_discovery` schema (handled in ENH-1443, not this issue)

## Implementation Steps

1. **Update `commands/scan-product.md`** — Replace the lines 73–88 hard-exit block ("Check goals file exists") with discovery logic:
   - Read `{{config.product.goals_discovery.max_files}}` (default 5) and `{{config.product.goals_discovery.required_files}}` (default `["README.md"]`) using the same `{{config.*}}` interpolation pattern already used for `{{config.product.goals_file}}` at line 24
   - Warn (but continue) if any `required_files` entry is absent (follow `skills/init/SKILL.md:339–392` warn-but-continue pattern)
   - Discover candidate files in the priority order specified in Proposed Solution
   - Read up to `max_files` files, synthesize `GOALS_CONTENT` with inferred persona and priorities
   - Assign `GOALS_SOURCE=discovered` and `GOALS_DISCOVERED_FROM=[list]` for later injection alongside `GOALS_CONTENT`
   - When `ll-goals.md` exists, keep the existing `cat {{config.product.goals_file}}` path and set `GOALS_SOURCE=explicit`

2. **Update `skills/product-analyzer/SKILL.md`**:
   - Remove `goals_file_missing` entry from the Guardrails stop-list (lines 24–28)
   - Make `### 2. Load Product Goals` (lines 52–62) conditional: read `.ll/ll-goals.md` only when `GOALS_CONTENT` is **not** already present in the injected context; set `goals_source: explicit` in that branch, `goals_source: discovered` otherwise
   - Update `skipped_reason` at lines 45–48: replace `goals_file_missing` with `goals_content_missing` (triggered only when the caller omits `GOALS_CONTENT` entirely — a caller error, not a missing file)
   - Update `analysis_metadata` at lines 175–184: replace `goals_file: ".ll/ll-goals.md"` with `goals_source: [explicit|discovered]` and `discovered_from: [...]` (populated only when `goals_source: discovered`)

3. **Update `hooks/scripts/session-start.sh`** — In `validate_enabled_features()` lines 134–143: change the `Warning:` emit to an informational `[little-loops] Note:` (or remove the block entirely), since a missing `ll-goals.md` with `product.enabled: true` is now valid

4. **Update `scripts/tests/test_hooks_integration.py:1649`** — Update `test_warns_product_without_goals` to assert the new informational message if kept, or remove the test if the warning block is dropped

5. **Create `scripts/tests/test_enh1442_doc_wiring.py`** — Follow `scripts/tests/test_enh1362_doc_wiring.py` class-per-surface structure. Assertions per issue Proposed Solution:
   - `goals_file_missing` absent from `skills/product-analyzer/SKILL.md`
   - `goals_content_missing` present as a `skipped_reason` in `SKILL.md`
   - `### 2. Load Product Goals` does not unconditionally contain `Read .ll/ll-goals.md`
   - `goals_source` and `discovered_from` appear in the `analysis_metadata` block of `SKILL.md`
   - `{{config.product.goals_discovery.max_files}}` and `{{config.product.goals_discovery.required_files}}` present in `commands/scan-product.md`
   - `"Goals file not found"` hard-exit block absent from `commands/scan-product.md`

6. **Run tests** — `python -m pytest scripts/tests/test_hooks_integration.py -v -k "product" && python -m pytest scripts/tests/test_enh1402_doc_wiring.py scripts/tests/test_enh1403_doc_wiring.py scripts/tests/test_enh1442_doc_wiring.py -v`
   _(Note: `test_enh1400_product_analyzer_wiring.py` does not exist — the pre-existing wiring tests live in `test_enh1402` and `test_enh1403`)_

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Update `skills/product-analyzer/SKILL.md` `## Context` section (line ~17)** — item 1 currently reads "**Product Goals** (`.ll/ll-goals.md`)"; update to reflect that goals may come from either explicit `ll-goals.md` or synthesized from discovered files
8. **Update `skills/product-analyzer/SKILL.md` `## What NOT to Do` section (line ~267)** — remove or soften "Don't proceed without `ll-goals.md`" to reflect the discovery fallback path (missing `ll-goals.md` is now valid when discovery succeeds)
9. **Verify `scripts/tests/test_hooks_integration.py:1671` (`test_no_warnings_when_properly_configured`)** — stays green but tests diminished behavior if the warning block is dropped; decide whether to add a new assertion for the `Note:` message (if kept) or leave as a smoke test
10. **Generalize evidence `file:` fields in `skills/product-analyzer/SKILL.md` Sections 3–5** — each of `### 3. Goal-Gap Analysis`, `### 4. Persona Journey Analysis`, `### 5. Business Value Opportunities` contains an evidence block with `file: ".ll/ll-goals.md"`; update to reference the actual goals source file (use `{{goals_source_file}}` or equivalent placeholder to reflect discovered vs explicit path) [Wiring pass 2]
11. **Update output display in `commands/scan-product.md` Steps 6.5 and 8** — both steps currently show `**Goals File**: {{config.product.goals_file}}`; change to display actual source: `**Goals Source**: {{config.product.goals_file}}` when explicit, or `**Goals Source**: auto-discovered from N files ({{GOALS_DISCOVERED_FROM}})` when in discovery mode [Wiring pass 2]
12. **Verify `scripts/tests/test_enh1402_doc_wiring.py` and `test_enh1403_doc_wiring.py` survive Section 2 rewrite** — both files use `content.index("### 2. Load Product Goals")` to scope assertions; the heading must be preserved exactly; `product.goals_file` reference must remain in the conditional branch so their `test_section2_references_product_goals_file_config` assertions pass [Wiring pass 2]

## Acceptance Criteria

- `/ll:scan-product` on a project with only `README.md` and no `ll-goals.md` produces meaningful findings
- Output metadata clearly indicates `goals_source: discovered`
- If `required_files` are missing, a warning is shown but analysis still proceeds
- `max_files` limit is respected
- With an explicit `ll-goals.md`, behavior is unchanged (`goals_source: explicit`)
- Hook no longer emits a false-alarm warning when `ll-goals.md` is absent and `product.enabled: true`
- All wiring test assertions pass

## Scope Boundaries

- **In scope**: `commands/scan-product.md`, `skills/product-analyzer/SKILL.md`, `hooks/scripts/session-start.sh`, both test files
- **Out of scope**: Documentation softening (covered in ENH-1443)
- **Out of scope**: Creating or modifying `ll-goals.md` files; changes to `ll:init`; modifying `goals_discovery` config schema

## Codebase Reference

- Config schema: `config-schema.json:767-786` — `goals_discovery` already defined
- File discovery pattern: `skills/init/SKILL.md` lines ~88-108
- Glob-based collection: `skills/audit-docs/SKILL.md` lines ~43-56
- Warn-but-continue pattern: `skills/init/SKILL.md` lines ~375-378
- Test pattern: `scripts/tests/test_enh1362_doc_wiring.py`

## Labels

`enhancement`, `product-analyzer`, `core-implementation`

## Status

**Open** | Created: 2026-05-11 | Priority: P2

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-11
- **Reason**: Issue too large for single session (score: 11/11 — Very Large)

### Decomposed Into
- ENH-1444: Goals Discovery — Implementation (scan-product, SKILL.md, wiring tests)
- ENH-1445: Goals Discovery — Hook Warning Fix + Test Update

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Moderate change breadth** — 6-15 distinct change sites across 5 files; manageable but requires systematic execution through all 12 implementation steps
- **Compatibility constraints on two existing tests** — `test_enh1402_doc_wiring.py` and `test_enh1403_doc_wiring.py` both use `content.index("### 2. Load Product Goals")` and assert `product.goals_file` is in that section; the heading must be preserved exactly and the `product.goals_file` reference retained in the conditional branch during the Section 2 rewrite
- **Discovery algorithm is markdown-only** — the new file-discovery and synthesis logic in `commands/scan-product.md` has no execution-level unit test; correctness depends on doc-wiring assertions plus manual walkthrough

## Session Log
- `/ll:issue-size-review` - 2026-05-11T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0abadba2-fa26-422a-8f2e-9ed2d2744c98.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/510b8632-aa30-48aa-84bd-7fbb58b199e9.jsonl`
- `/ll:wire-issue` - 2026-05-11T19:19:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/58ce4a17-05ac-4da2-a843-1fdb8f6a75a6.jsonl`
- `/ll:refine-issue` - 2026-05-11T19:13:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3036d514-e8b7-4f4f-bb91-7ecd12913690.jsonl`
- `/ll:refine-issue` - 2026-05-11T19:13:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3036d514-e8b7-4f4f-bb91-7ecd12913690.jsonl`
- `/ll:wire-issue` - 2026-05-11T08:20:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d5472e8-2046-416d-aef1-36891c83fc07.jsonl`
- `/ll:refine-issue` - 2026-05-11T08:13:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a51073a8-32f8-4cb4-b8d7-89559d2abda8.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a400556-76fe-4ad7-9557-40b6a1c32a72.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91964bec-3326-48c8-ac3d-4b50f98761b4.jsonl`
