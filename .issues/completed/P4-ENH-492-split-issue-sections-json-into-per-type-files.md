---
discovered_date: 2026-02-24
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 64
---

# ENH-492: Split issue-sections.json into per-type files

## Summary

Split the single unified `templates/issue-sections.json` into three per-type template files (`bug-sections.json`, `feat-sections.json`, `enh-sections.json`) while preserving the same internal JSON structure. Each file would contain only the sections relevant to its type (common + type-specific), making the templates easier to read and maintain by hand.

## Current Behavior

All three issue types (BUG, FEAT, ENH) share a single `templates/issue-sections.json` file that embeds type-specific sections under `type_sections.BUG`, `type_sections.FEAT`, and `type_sections.ENH`. The file is 16KB and growing as new sections are added.

## Expected Behavior

Three smaller, focused template files exist:
- `templates/bug-sections.json` — common sections + BUG-specific sections
- `templates/feat-sections.json` — common sections + FEAT-specific sections
- `templates/enh-sections.json` — common sections + ENH-specific sections

Skills (`format-issue`, `capture-issue`, `scan-codebase`, `ready-issue`) and Python code (`issue_template.py`) load the file corresponding to the issue type being processed.

## Motivation

The single-file approach works well for machine processing but makes it hard to read or update type-specific sections in isolation. As the template grows (more sections, more quality guidance, more inference rules), a single large JSON file becomes a maintenance burden. Per-type files reduce cognitive load when editing templates and make diffs easier to review.

This is an architectural quality-of-life improvement — no new functionality, just better organization.

## Proposed Solution

**Consumer Audit Complete** — consumers include 6 skill/command markdown files (Claude reads the JSON directly) and 1 Python module (`issue_template.py`, added by completed ENH-491) that loads `issue-sections.json` via `load_issue_sections()`.

**Load interface:** AI skill consumers use a natural-language instruction: "Read templates/issue-sections.json". Python code uses `load_issue_sections()` which hardcodes the filename at `issue_template.py:32`.

**Key decisions resolved by audit and research:**

1. **Shared data strategy**: Duplicate `_meta`, `common_sections`, `creation_variants`, and `quality_checks` (type-specific + common) into each per-type file. Each file is fully self-contained — agents read exactly one file. No `common-sections.json` or loader shim needed.

2. **Per-type file structure**: Each `{type}-sections.json` contains:
   - `_meta` — with `type` field added (e.g., `"type": "BUG"`)
   - `common_sections` — identical across all 3 files
   - `type_sections` — only the sections for that type (no nesting under type key)
   - `creation_variants` — identical across all 3 files
   - `quality_checks` — `common` checks + only the checks for that type

3. **Python API change**: Update `load_issue_sections()` to accept an `issue_type` parameter and load `{type}-sections.json` directly:
   ```python
   def load_issue_sections(issue_type: str, templates_dir: Path | None = None) -> dict[str, Any]:
       base = templates_dir if templates_dir is not None else _default_templates_dir()
       filename = f"{issue_type.lower()}-sections.json"
       path = base / filename
       ...
   ```
   Callers (`sync.py:658-664`, `assemble_issue_markdown()`) already have the `issue_type` available.

4. **AI skill migration**: Update the instruction text in 6 consumer files:

| Consumer | File | Lines to update |
|---|---|---|
| `capture-issue` | `skills/capture-issue/SKILL.md:231` | Change to `Read templates/{type}-sections.json` |
| `format-issue` (gap check) | `skills/format-issue/SKILL.md:176,201` | Change to `Read templates/{type}-sections.json` |
| `format-issue` (template) | `skills/format-issue/templates.md:7,52,54` | Change to `Read templates/{type}-sections.json` |
| `scan-codebase` | `commands/scan-codebase.md:241,243,278` | Change to `Read templates/{type}-sections.json` |
| `ready-issue` | `commands/ready-issue.md:123` | Change to `Read templates/{type}-sections.json` |
| `init` | `skills/init/SKILL.md:83` | Update exclusion list (no longer one file) |

5. **Python migration** (`issue_template.py` + `sync.py`):
   - `load_issue_sections()` — add `issue_type: str` parameter, construct filename as `f"{issue_type.lower()}-sections.json"`
   - `assemble_issue_markdown()` — simplify extraction since `type_sections` is no longer nested (just `sections_data["type_sections"]` instead of `sections_data["type_sections"][issue_type]`)
   - `sync.py:658-664` — pass `issue_type` to `load_issue_sections()`, remove or adjust caching (different types need different data)
   - `sync.py:269` — change `_sections_data` cache to `dict[str, dict]` keyed by type, or load per-call

## Scope Boundaries

- **In scope**: Splitting `issue-sections.json` into per-type files; updating consumer skills to load by type via a loader shim; documenting the migration
- **Out of scope**: Changing the content or structure of section definitions; adding new sections; modifying consumer skill logic beyond the file-selection step

## Implementation Steps

1. **Generate per-type JSON files** — Script or manually split `templates/issue-sections.json` (349 lines) into `bug-sections.json`, `feat-sections.json`, `enh-sections.json`. Each file gets: `_meta` (add `"type"` field), `common_sections` (copy), `type_sections` (flatten — only that type's sections, no nesting), `creation_variants` (copy), `quality_checks` (common + that type only).
2. **Update Python loader** — Modify `load_issue_sections()` in `issue_template.py:19-34` to accept `issue_type: str` param and load `f"{issue_type.lower()}-sections.json"`. Update `assemble_issue_markdown()` to handle flattened `type_sections`. Update `sync.py:658-664` to pass `issue_type`.
3. **Update tests** — Fix `test_issue_template.py` (loader tests need `issue_type` param, fixture needs per-type loading, `test_load_custom_dir` needs per-type fixture file). Fix `test_sync.py` if it mocks `load_issue_sections`.
4. **Update 6 AI skill/command consumers** — Change "Read templates/issue-sections.json" to "Read templates/{type}-sections.json" in: `capture-issue/SKILL.md`, `format-issue/SKILL.md`, `format-issue/templates.md`, `scan-codebase.md`, `ready-issue.md`, `init/SKILL.md`.
5. **Delete `templates/issue-sections.json`** — Remove the unified file after all consumers are migrated.
6. **Update documentation** — `docs/reference/ISSUE_TEMPLATE.md` (describe per-type structure), `docs/ARCHITECTURE.md:158` (update directory listing).

## Integration Map

### Files to Modify
- `templates/issue-sections.json` — delete after generating per-type files
- `scripts/little_loops/issue_template.py` — update `load_issue_sections()` signature and `assemble_issue_markdown()` extraction logic
- `scripts/little_loops/sync.py:658-664` — pass `issue_type` to `load_issue_sections()`, adjust caching
- `skills/capture-issue/SKILL.md:231` — update read instruction to per-type file
- `skills/format-issue/SKILL.md:176,201` — update read instructions to per-type file
- `skills/format-issue/templates.md:7,52,54` — update read instructions to per-type file
- `commands/scan-codebase.md:241,243,278` — update read instructions to per-type file
- `commands/ready-issue.md:123` — update read instruction to per-type file
- `skills/init/SKILL.md:83` — update exclusion list (currently excludes `issue-sections.json` by name)

### New Files
- `templates/bug-sections.json` — common + BUG-specific sections
- `templates/feat-sections.json` — common + FEAT-specific sections
- `templates/enh-sections.json` — common + ENH-specific sections

### Similar Patterns
- `skills/init/SKILL.md:83-103` — loads per-type project template JSON files from `templates/` (e.g., `python-generic.json`, `typescript.json`). Established pattern for type-based file selection in the templates directory.

### Tests
- `scripts/tests/test_issue_template.py` — `TestLoadIssueSections` tests need `issue_type` param added; `sections_data` fixture needs update; `test_load_custom_dir` fixture file needs per-type name. `TestAssembleIssueMarkdown` tests need flattened `type_sections` handling.
- `scripts/tests/test_sync.py` — tests that exercise `_create_local_issue()` need updated mocks/fixtures for the new `load_issue_sections(issue_type)` signature.

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — update to describe per-type file structure
- `docs/ARCHITECTURE.md:158` — update directory tree listing (currently shows `issue-sections.json`)

### Configuration
- N/A

## Impact

- **Priority**: P4 — Architectural quality-of-life; not blocking
- **Effort**: Medium — Per-type file generation + Python loader/assembler changes + 6 skill/command updates + test updates + docs
- **Risk**: Low — purely structural refactor, no behavioral changes if loader shim is correct
- **Breaking Change**: No

## Labels

`enhancement`, `templates`, `refactor`

## Session Log

- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/568ba5fc-d209-4c80-bff7-a8c1237be3b5.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Consumer audit complete: 5 skill/command files reference issue-sections.json; no Python code loads it yet; proposed solution TBD replaced with concrete migration plan
- `/ll:refine-issue` - 2026-03-01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8df6efac-cbed-4ac5-b021-cdbb2749f5d4.jsonl` - Post-ENH-491 research: corrected Integration Map (removed manage-issue, added init/SKILL.md + ARCHITECTURE.md), added Python loader/test changes, resolved shared-data and API decisions
- `/ll:manage-issue` - 2026-03-01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/061f76fb-6ebe-4bb8-909b-9b7d60324b8a.jsonl` - Full implementation: split issue-sections.json into 3 per-type files, updated Python loader/sync/tests/6 consumers/docs

## Resolution

**Completed** on 2026-03-01.

Split `templates/issue-sections.json` into three per-type files (`bug-sections.json`, `feat-sections.json`, `enh-sections.json`). Updated Python loader (`load_issue_sections()`) to accept `issue_type` parameter and load the corresponding file. Updated all 6 skill/command consumers to reference per-type files. Updated sync.py caching to be per-type. All 3045 tests pass.

### Files Changed
- `templates/bug-sections.json` — NEW: BUG-specific template
- `templates/feat-sections.json` — NEW: FEAT-specific template
- `templates/enh-sections.json` — NEW: ENH-specific template
- `templates/issue-sections.json` — DELETED
- `scripts/little_loops/issue_template.py` — Added `issue_type` param to `load_issue_sections()`, flattened `type_sections` access
- `scripts/little_loops/sync.py` — Per-type caching, pass `issue_type` to loader
- `scripts/tests/test_issue_template.py` — Per-type fixtures, updated all test calls
- `scripts/tests/test_sync.py` — Updated docstring
- `skills/capture-issue/SKILL.md` — Per-type file reference
- `skills/format-issue/SKILL.md` — Per-type file reference
- `skills/format-issue/templates.md` — Per-type file reference, flattened type_sections
- `commands/scan-codebase.md` — Per-type file reference
- `commands/ready-issue.md` — Per-type file reference
- `skills/init/SKILL.md` — Updated exclusion list
- `docs/ARCHITECTURE.md` — Updated directory tree

---

## Status

**Completed** | Created: 2026-02-24 | Completed: 2026-03-01 | Priority: P4

## Blocked By

- ~~ENH-491~~ (completed)

- ~~FEAT-441~~ (completed)