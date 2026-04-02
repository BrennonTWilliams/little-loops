# ENH-923: Enhance `ll-sprint show` Detail and Output Quality

## Implementation Plan

### Phase 0: Write Tests (Red)

Add tests to `scripts/tests/test_sprint.py` in `TestSprintDependencyAnalysis`:

1. **test_show_omits_empty_description** — Sprint with `description=""` should NOT print `Description:` line
2. **test_show_human_friendly_timestamp** — Output contains formatted date like `2026-04-02 19:49 UTC` instead of raw ISO
3. **test_show_composition_line** — Output contains `Composition:` with type/priority breakdown
4. **test_show_lighter_separators** — Output contains `──` separator, NOT `===` banners
5. **test_show_wider_title** — Title longer than 45 chars is NOT truncated at 42
6. **test_show_issue_file_paths** — Output contains issue file path below each issue
7. **test_show_readiness_scores** — Output contains confidence/outcome scores
8. **test_show_json_output** — `--json` flag produces valid JSON with sprint metadata
9. **test_show_sprint_run_state** — When `.sprint-state.json` exists, shows last run info

### Phase 1: Move shared utility

Move `_format_relative_time()` from `cli/loop/lifecycle.py` to `cli/output.py`. Update import in `lifecycle.py`.

### Phase 2: Separator styling

Replace `"=" * width` banners in:
- `_helpers.py:57-61` — Execution plan header
- `show.py:48-51` — Dependency graph header

New pattern: `f"── {title} {'─' * (width - len(title) - 4)}"`

### Phase 3: Dynamic title truncation

In `_helpers.py` lines 82-84 and 127-129, replace hardcoded `45` with `max(45, terminal_width() - 30)`.

### Phase 4: Omit empty description

In `show.py:190`, only print description when `sprint.description` is truthy.

### Phase 5: Human-friendly timestamps

In `show.py:191`, parse ISO string and format as `"2026-04-02 19:49 UTC (Xh ago)"` using the shared `format_relative_time()`.

### Phase 6: Composition breakdown

After health summary in `show.py:226`, compute type/priority distribution from `issue_infos` and print.

### Phase 7: Sprint run state

Load `.sprint-state.json` if it exists and display last run summary.

### Phase 8: Readiness/confidence scores per issue

In `_helpers.py`, display `[ready: N, conf: N]` inline after each issue.

### Phase 9: Issue file paths

In `_helpers.py`, add `│   <issue.path>` line after each issue entry.

### Phase 10: --json flag

Add `--json` argument to `show_parser` in `__init__.py`. Add early-exit JSON branch in `show.py`.

## Success Criteria

- [ ] All 9 improvements visible in output
- [ ] `--json` produces valid JSON
- [ ] Existing tests pass without regression
- [ ] New tests cover each feature
