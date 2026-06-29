---
id: ENH-2399
title: Issue assembler still emits `## Labels` body section for new issues post-ENH-1392
type: enhancement
status: open
priority: P4
discovered_date: 2026-06-29
discovered_by: BUG-2395 reconciliation
relates_to:
- BUG-2395
- ENH-1392
labels:
- issue-template
- assembler
- cleanup
decision_needed: false
---

# ENH-2399: Issue assembler still emits `## Labels` body section for new issues post-ENH-1392

## Summary

ENH-1392 moved labels from a `## Labels` body section into the `labels:`
frontmatter field, and BUG-2395 demoted `Labels.required` to `false` in the
section templates. But the issue assembler still lists `Labels` in
`creation_variants.full.include_common`, so newly created issues still get a
`## Labels` body heading — duplicating the canonical frontmatter location.

## Current Behavior

`scripts/little_loops/issue_template.py` (`assemble_issue_markdown()`) includes
`Labels` via `creation_variants.full.include_common`. New issues are emitted with
both `labels:` frontmatter and a `## Labels` body section. The body section is
now redundant (frontmatter is canonical) and is exactly the deprecated location
`ll-migrate-labels` strips from existing issues.

## Expected Behavior

The assembler does not emit a `## Labels` body section for new issues; labels
live only in `labels:` frontmatter. Remove `Labels` from the relevant
`include_common` list(s) in the section templates / assembler.

## Scope Boundaries

- In scope: assembler `include_common` for `Labels`; corresponding assembly test
  fixtures in `test_issue_template.py`.
- Out of scope: the `required` flag (handled by BUG-2395); migrating existing
  issues (handled by `ll-migrate-labels`).

## Impact

Cosmetic divergence: new issues carry a redundant, deprecated body section.
No functional break — `is_formatted()` and the gate no longer require it after
BUG-2395 — but it perpetuates the inconsistency BUG-2395 was about.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/enh-sections.json` — remove `"Labels"` from `creation_variants.full.include_common` (index 9) and `creation_variants.legacy.include_common`
- `scripts/little_loops/templates/bug-sections.json` — same (index 9 in `full`, present in `legacy`)
- `scripts/little_loops/templates/feat-sections.json` — same (index 9 in `full`, present in `legacy`)
- `scripts/little_loops/templates/epic-sections.json` — same (`full` variant, present in `legacy`)
- `scripts/little_loops/issue_template.py` — fallback guard at lines 152–159 (`assemble_issue_markdown()`) currently fires when `labels` arg is passed but `"Labels" not in include_common`; after removing `Labels` from `full.include_common` this guard will activate for `full` variant too — must be deleted to prevent the body section from re-appearing via the fallback path
- `scripts/little_loops/sync.py` — lines 734–748 (`_create_from_github()`): `section_content["Labels"]` write (line 736) becomes dead code once `Labels` is removed from `include_common`; `labels=gh_labels` kwarg (line 747) triggers the fallback guard — both must be cleaned up

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sync.py` — the only Python caller that passes `labels=gh_labels` to `assemble_issue_markdown()`; also explicitly populates `section_content["Labels"]` (line 736) which feeds the body section

### Tests to Update / Add
- `scripts/tests/test_issue_template.py` — `test_labels_in_content_used_by_full_variant()` (line 205) currently asserts `## Labels` IS in `full` output — must be inverted to assert absence; `test_labels_appended_in_minimal()` (line 159) tests the fallback guard for `minimal`, may be deleted if guard is removed
- `scripts/tests/test_ll_issues_sections.py` — `TestLabelsNotRequired` class (follows `TEMPLATES_DIR` pattern): add a companion test asserting `"Labels" not in data["creation_variants"]["full"]["include_common"]` for all four types
- `scripts/tests/test_sync.py` — `test_create_local_issue_labels_in_section()` (line 756, class `TestCreateLocalIssue`) asserts `"## Labels" in content`, `"`enhancement`" in content`, `"`testing`" in content` — **will break**; must be rewritten to assert `"## Labels" not in content` and that labels appear in the frontmatter `labels:` field [Agent 3 finding]
- `scripts/tests/test_dependency_mapper.py` — `TestApplyProposals` at line 1741 has `assert "## Labels" in content` — **will break**; must be updated to reflect that new issues no longer carry a `## Labels` body section [Agent 3 finding]

### Similar Patterns
- `scripts/tests/test_issue_template.py:test_minimal_variant()` — negative assertion pattern: `assert "## Context" not in result` (used for other deprecated sections)
- `scripts/tests/test_ll_issues_sections.py:TestLabelsNotRequired` — iterates all four type JSON files and asserts structural properties; the new template guard test extends this class

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — "Full Template (v2.0)" section at line 818 lists `Labels` in the section enumeration; lines 659–661 and 802–804 include `## Labels` in illustrative example markdown snippets — remove `Labels` from the enumeration and update the examples [Agent 2 finding]

### Advisory: Behavioral Gap (out of scope for ENH-2399)
- `scripts/little_loops/cli/issues/search.py:_parse_labels_from_content()` (line 90) uses a regex on the `## Labels` body section to feed the `--label LABEL` filter in `cmd_list()`. After this change, newly assembled issues carry labels only in `labels:` frontmatter, so `ll-issues list --label <tag>` will silently miss them. This is a follow-on defect — not in ENH-2399 scope but should be tracked separately [Agent 2 finding]

## Implementation Steps

1. **Remove `"Labels"` from `creation_variants.full.include_common`** in all four template JSON files (`enh-sections.json`, `bug-sections.json`, `feat-sections.json`, `epic-sections.json`). The `minimal` variant already omits it. Decide whether to also remove from `legacy` (backward-compat variant) or leave it there.
2. **Delete the fallback Labels guard** in `assemble_issue_markdown()` (`issue_template.py` lines 152–159). Without this deletion, passing `labels=` to the assembler (as `sync.py` does) re-emits `## Labels` via the fallback path, defeating the template fix.
3. **Clean up `sync.py`** (`_create_from_github()` lines 734–748): remove `section_content["Labels"] = labels_str` (line 736) and the `labels=gh_labels` kwarg (line 747). Labels are already written to `frontmatter["labels"]` (line 722) — that path is canonical and sufficient.
4. **Update tests**: invert `test_labels_in_content_used_by_full_variant()` to assert `"## Labels" not in result`; add a `TestLabelsNotInFullVariant` (or extend `TestLabelsNotRequired`) in `test_ll_issues_sections.py` asserting `"Labels" not in data["creation_variants"]["full"]["include_common"]` for all four types.
5. **Update `test_sync.py`**: rewrite `test_create_local_issue_labels_in_section()` to assert `"## Labels" not in content` and that labels are present in the frontmatter `labels:` field.
6. **Update `test_dependency_mapper.py`**: fix `TestApplyProposals` at line 1741 — the `assert "## Labels" in content` breaks after the assembler stops emitting the body section for new issues.
7. **Update `docs/reference/ISSUE_TEMPLATE.md`**: remove `Labels` from the "Full Template (v2.0)" section enumeration (line 818) and update the illustrative markdown snippets at lines 659–661 and 802–804 that show `## Labels` body content.
8. **Verify**: run `python -m pytest scripts/tests/test_issue_template.py scripts/tests/test_ll_issues_sections.py scripts/tests/test_sync.py scripts/tests/test_dependency_mapper.py -v`.

## Status

open


## Session Log
- `/ll:wire-issue` - 2026-06-29T21:58:37 - `b7bf5167-27d7-41c6-a78e-542f6cd6cbd5.jsonl`
- `/ll:refine-issue` - 2026-06-29T21:49:56 - `e64a7c26-25a2-445e-903b-32e93688b461.jsonl`
