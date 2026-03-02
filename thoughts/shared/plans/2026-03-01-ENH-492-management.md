# ENH-492: Split issue-sections.json into per-type files

## Implementation Plan

### Phase 1: Generate per-type JSON files

Split `templates/issue-sections.json` into three self-contained files:

- `templates/bug-sections.json` — `_meta` (add `"type": "BUG"`), `common_sections` (copy), `type_sections` (BUG only, flattened — no nesting), `creation_variants` (copy), `quality_checks` (`common` + `BUG` only)
- `templates/feat-sections.json` — same structure for FEAT
- `templates/enh-sections.json` — same structure for ENH

Each file is fully self-contained. An agent reads exactly one file.

### Phase 2: Update Python code

**`issue_template.py`**:
- `load_issue_sections(issue_type: str, templates_dir: Path | None = None)` — add `issue_type` as first param, construct filename as `f"{issue_type.lower()}-sections.json"`
- `assemble_issue_markdown()` — change line 69 from `sections_data.get("type_sections", {}).get(issue_type, {})` to `sections_data.get("type_sections", {})` since type_sections is now flat (no nesting under type key)

**`sync.py`**:
- Change `self._sections_data: dict[str, Any] | None = None` to `self._sections_data: dict[str, dict[str, Any]] = {}` (keyed by issue_type)
- Update cache load logic (lines 658-664) to cache per-type: `self._sections_data[issue_type] = load_issue_sections(issue_type, templates_dir)`
- Update usage at line 690 to `self._sections_data[issue_type]`

### Phase 3: Update tests

**`test_issue_template.py`**:
- `sections_data` fixture: `load_issue_sections("ENH")` (or parameterize)
- `test_load_default`: `load_issue_sections("BUG")` etc.
- `test_load_custom_dir`: write `bug-sections.json` to tmp_path
- `test_load_missing_file`: still passes empty tmp_path
- `TestAssembleIssueMarkdown` tests: update `type_sections` extraction expectations

**`test_sync.py`**: No changes needed — tests exercise `_create_local_issue` which internally passes `issue_type` to `load_issue_sections`. The test passes "ENH" and "BUG" which will now load per-type files.

### Phase 4: Update 6 AI skill/command consumers

| File | Change |
|---|---|
| `skills/capture-issue/SKILL.md:231` | `Read templates/{type}-sections.json` where `{type}` is `bug`, `feat`, or `enh` |
| `skills/format-issue/SKILL.md:176,201` | Same |
| `skills/format-issue/templates.md:7,52,54` | Same, also update `type_sections.[TYPE]` → `type_sections` |
| `commands/scan-codebase.md:241,243,278` | Same |
| `commands/ready-issue.md:123` | Same |
| `skills/init/SKILL.md:83` | Update exclusion list: `excluding bug-sections.json, feat-sections.json, enh-sections.json, and ll-goals-template.md` |

### Phase 5: Delete `templates/issue-sections.json`

### Phase 6: Update documentation

- `docs/ARCHITECTURE.md:158`: replace `issue-sections.json` with `bug-sections.json`, `feat-sections.json`, `enh-sections.json`

## Success Criteria

- [ ] Three per-type JSON files exist and are valid JSON
- [ ] `load_issue_sections("BUG")` loads `bug-sections.json`
- [ ] `assemble_issue_markdown()` produces identical output for all three types
- [ ] All existing tests pass with updated signatures
- [ ] `python -m pytest scripts/tests/` passes
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes
- [ ] All 6 skill/command files reference per-type files
- [ ] `templates/issue-sections.json` is deleted
