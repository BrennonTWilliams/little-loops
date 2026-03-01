# ENH-519: Enhance `ll-issues show` with additional detail fields

## Plan

### Phase 1: Update `_parse_card_fields()` (show.py:82)

- Add `config: BRConfig` parameter for relative path computation
- Add `collections.Counter` import for session log dedup
- Extract 6 new fields after existing frontmatter extraction:
  1. **summary**: `re.search(r"^## Summary\n+(.+?)(?:\n|$)", content, re.MULTILINE)` → truncate to 80 chars with `...`
  2. **integration_files**: Find `### Files to Modify`, count `^- ` lines until next section header
  3. **risk**: `re.search(r"\*\*Risk\*\*:\s*(Low|Medium|High)", content, re.IGNORECASE)`
  4. **labels**: Find `## Labels` section, extract backtick-delimited labels
  5. **history**: Find `## Session Log`, extract `/ll:*` commands with Counter for dedup
  6. **path**: Convert to relative using `path.relative_to(config.project_root)` with ValueError fallback

### Phase 2: Update `_render_card()` (show.py:138)

- Add new detail section between scores and path sections:
  - Line 1: `Summary: {text}...` (only if present)
  - Line 2: `Integration: N files  │  Labels: ...` (join non-None with `  │  `)
  - Line 3: `History: /ll:cmd1, /ll:cmd2 (3)` (only if present)
- Add `mid_border` before new section
- Include new lines in `content_lines` for width calculation

### Phase 3: Update `cmd_show()` (show.py:207)

- Pass `config` to `_parse_card_fields(path, config)` at line 224

### Phase 4: Add tests in `test_issues_cli.py`

7 new tests:
- `test_show_with_summary`
- `test_show_with_integration_files`
- `test_show_with_risk`
- `test_show_with_labels`
- `test_show_with_session_log`
- `test_show_relative_path`
- `test_show_new_fields_absent_gracefully`

### Phase 5: Update docs and verify

- Update `docs/reference/API.md:2267` to list all new displayed fields
- Run pytest, ruff, mypy

## Success Criteria

- [x] Plan written
- [ ] _parse_card_fields updated with 6 new parsers
- [ ] _render_card updated with new detail section
- [ ] cmd_show passes config through
- [ ] 7 new tests pass
- [ ] Existing 8 tests pass
- [ ] API docs updated
- [ ] ruff/mypy clean
