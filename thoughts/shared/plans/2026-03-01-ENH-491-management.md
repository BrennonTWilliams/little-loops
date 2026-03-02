# ENH-491: Use issue-sections.json in ll-sync pull

## Plan Summary

Replace the hardcoded inline template in `sync.py:_create_local_issue()` with a shared Python utility that reads `templates/issue-sections.json` and assembles structured markdown. This ensures pulled GitHub issues match the v2.0 section structure used by all other issue-creation paths.

## Research Findings

### Current State
- `_create_local_issue()` at `sync.py:615-670` uses a Python f-string to produce a minimal structure: frontmatter + title + raw body + labels
- No Python code currently reads `issue-sections.json` — all consumers are AI skill markdown files
- `IssuesConfig` already has a `templates_dir` field (default: `None`) but it's unused by any Python code
- `GitHubSyncConfig` has no `pull_template` field

### Template Structure (issue-sections.json)
- `common_sections`: 13 sections with `required`, `creation_template`, `ai_usage` fields
- `type_sections`: BUG (6), FEAT (6), ENH (4) type-specific sections
- `creation_variants`: `full` (11 common + type), `minimal` (5 common, no type), `legacy` (9 common + type)
- The `minimal` variant includes: Summary, Current Behavior, Expected Behavior, Impact, Status

### Design Decisions (Autonomous)
1. **Template location**: Use `Path(__file__).parent.parent.parent / "templates"` to locate the bundled `issue-sections.json` relative to the package. This works for both development and installed-package scenarios. Allow override via `IssuesConfig.templates_dir`.
2. **GitHub body mapping**: Entire unstructured GitHub body goes into "Summary" section. Other sections get `creation_template` placeholders.
3. **Variant default**: `minimal` — matches issue proposal. Keeps pulled issues lightweight since GitHub bodies are unstructured.
4. **Labels section**: Always include Labels section (even though not in `minimal` variant's `include_common`) since we have the data from GitHub.
5. **Module pattern**: Follow `from_file`/`from_content` split pattern (like `goals_parser.py`) for testability.

## Implementation Phases

### Phase 1: Create `issue_template.py` utility module

**File**: `scripts/little_loops/issue_template.py` (new)

```python
# Core API:
def load_issue_sections(templates_dir: Path | None = None) -> dict[str, Any]
    """Load issue-sections.json from templates dir or default bundled location."""

def assemble_issue_markdown(
    sections_data: dict[str, Any],
    issue_type: str,           # BUG, FEAT, ENH
    variant: str,              # full, minimal, legacy
    issue_id: str,             # e.g. "ENH-517"
    title: str,
    frontmatter: dict[str, Any],
    content: dict[str, str],   # section_name -> content (e.g. {"Summary": "body text"})
    labels: list[str] | None = None,
) -> str
    """Assemble structured markdown from template sections and content."""
```

**Logic for `assemble_issue_markdown`**:
1. Look up `creation_variants[variant]` to get `include_common` list and `include_type_sections` flag
2. Build YAML frontmatter from `frontmatter` dict
3. Add title heading: `# {issue_id}: {title}`
4. For each section in `include_common`:
   - If section name exists in `content` dict, use that value
   - Otherwise use `common_sections[name].creation_template`
   - Skip deprecated sections if variant has `exclude_deprecated: true`
5. If `include_type_sections` is true, add type-specific sections from `type_sections[issue_type]`
   - Apply same deprecated filter
   - Use content dict or creation_template
6. If `labels` provided and "Labels" not already in include_common, append Labels section
7. Return assembled markdown string

### Phase 2: Add `pull_template` config option

**Files**: `config.py`, `config-schema.json`

- Add `pull_template: str = "minimal"` to `GitHubSyncConfig` dataclass (line ~358)
- Add to `from_dict()`: `pull_template=data.get("pull_template", "minimal")`
- Add to `to_dict()` in the `github` block (line ~823)
- Add to `config-schema.json` in `sync.github.properties` (after line ~711):
  ```json
  "pull_template": {
    "type": "string",
    "enum": ["full", "minimal", "legacy"],
    "description": "Creation variant for issues pulled from GitHub",
    "default": "minimal"
  }
  ```

### Phase 3: Refactor `_create_local_issue()`

**File**: `scripts/little_loops/sync.py:615-672`

Replace the hardcoded f-string content block (lines 652-669) with:
1. Import `load_issue_sections` and `assemble_issue_markdown` from `issue_template`
2. Load sections data (cache at class level or module level to avoid re-reading per issue)
3. Build frontmatter dict: `github_issue`, `github_url`, `last_synced`, `discovered_by`, `discovered_date`
4. Build content dict: `{"Summary": gh_body}` (unstructured body goes into Summary)
5. Call `assemble_issue_markdown()` with the variant from `self.sync_config.github.pull_template`
6. Keep everything else unchanged (priority determination, slug generation, file write, result mutation)

**Preserve**: Priority logic, slug generation, issue numbering, category resolution, file write, result tracking — only the content assembly changes.

### Phase 4: Tests

**New file**: `scripts/tests/test_issue_template.py`
- `test_load_issue_sections_default` — loads from bundled templates/
- `test_load_issue_sections_custom_dir` — loads from a custom path
- `test_assemble_minimal_variant` — produces correct structure for minimal variant
- `test_assemble_full_variant` — produces correct structure for full variant
- `test_assemble_with_content_overrides` — provided content replaces templates
- `test_assemble_includes_labels_in_minimal` — Labels appended even when not in variant
- `test_deprecated_sections_excluded` — deprecated sections skipped in minimal variant

**Existing file**: `scripts/tests/test_sync.py`
- Update `test_create_local_issue_avoids_completed_collision` — still works (numbering unchanged)
- Add `test_create_local_issue_uses_template_structure` — verify created file has v2.0 sections
- Add `test_create_local_issue_with_full_variant` — test config override to `full`
- Add `test_create_local_issue_body_in_summary` — verify GitHub body ends up in Summary section

### Phase 5: Verification

- [ ] `python -m pytest scripts/tests/` — all tests pass
- [ ] `ruff check scripts/` — no lint errors
- [ ] `python -m mypy scripts/little_loops/` — no type errors
- [ ] Existing `test_create_local_issue_avoids_completed_collision` still passes
- [ ] New template tests pass

## Success Criteria

- [ ] Pulled issues have v2.0 section structure (Summary, Current Behavior, Expected Behavior, Impact, Status for minimal)
- [ ] GitHub body content appears in Summary section
- [ ] Labels from GitHub populate Labels section
- [ ] Frontmatter includes github_issue, github_url, last_synced, discovered_by, discovered_date
- [ ] `pull_template` config option works (defaults to "minimal")
- [ ] No regression in push behavior or existing sync tests
- [ ] `issue_template.py` is independently testable and reusable
