---
discovered_date: 2026-02-24
discovered_by: capture-issue
confidence_score: 88
outcome_confidence: 72
---

# ENH-491: Use issue-sections.json in ll-sync pull

## Summary

`ll-sync pull` currently uses a hardcoded inline template (`sync.py:615-670`) when creating local issue files from GitHub Issues. This bypasses the shared `templates/issue-sections.json` (v2.0) that all other issue-creation paths use, resulting in pulled issues that don't conform to the project's template structure.

## Current Behavior

When `_create_local_issue()` runs during `ll-sync pull`, it writes a minimal hardcoded structure:
- YAML frontmatter (`github_issue`, `github_url`, `last_synced`, `discovered_by`)
- Title heading
- Raw GitHub body verbatim
- Labels section

This output lacks the v2.0 section structure (Summary, Current Behavior, Expected Behavior, Impact, Status, etc.) and requires a manual `/ll:format-issue` pass to align with locally-created issues.

## Expected Behavior

`ll-sync pull` should read `templates/issue-sections.json`, select the appropriate `creation_variant`, and assemble pulled issues into the proper section structure. Pulled issues should be structurally consistent with issues created by `/ll:capture-issue` and `/ll:scan-codebase`.

## Motivation

- **Consistency**: All issue-creation paths should produce the same structure so downstream tools (`ready-issue`, `format-issue`, `manage-issue`) work without a reformatting step.
- **Reduced friction**: Users pulling issues from GitHub shouldn't need to manually run `/ll:format-issue` on every imported issue.
- **Single source of truth**: `issue-sections.json` is the canonical template definition — the sync module should use it rather than maintaining a parallel format.

## Proposed Solution

1. Add a Python utility that reads `templates/issue-sections.json` and assembles a section-structured markdown string given a type (BUG/FEAT/ENH), variant (full/minimal/legacy), and content fragments.
2. Refactor `_create_local_issue()` in `sync.py` to call this utility instead of using the inline template.
3. Map GitHub issue body content into the appropriate sections where possible (e.g., body text → Summary, labels → Labels section). Content that doesn't map cleanly goes into a catch-all section (e.g., "Additional Context" or "Summary").
4. Default the creation variant to `"minimal"` for pulled issues (since GitHub bodies are unstructured), but make it configurable via `config.sync.github.pull_template` or similar.

## Scope Boundaries

- **In scope**: Refactoring `_create_local_issue()` to use `issue-sections.json`; adding template assembly utility; adding `pull_template` config option
- **Out of scope**: Changing push behavior; modifying `issue-sections.json` structure; parsing GitHub body into individual sections (unstructured body goes into Summary)

## Integration Map

| File | Role | Change Type |
|------|------|-------------|
| `scripts/little_loops/sync.py:615-670` | `_create_local_issue()` | Modify - replace hardcoded template with shared utility |
| `templates/issue-sections.json` | Section definitions | Read-only reference |
| `scripts/little_loops/issue_template.py` (new) | Template assembly utility | New module |
| `.claude/ll-config.json` | Config | Add `sync.github.pull_template` option |
| `config-schema.json` | Schema | Add `pull_template` property |
| `scripts/tests/test_sync.py` | Tests | Add tests for template-based pull |

## Implementation Steps

1. Create `issue_template.py` with a function that reads `issue-sections.json` and assembles markdown given type, variant, and content dict
2. Add `pull_template` config option (default: `"minimal"`)
3. Refactor `_create_local_issue()` to use the new utility
4. Add/update tests in `test_sync.py` for template-based issue creation
5. Verify round-trip: push a local issue, pull it back, confirm structure is preserved

## Impact

- **Priority**: P3 - Quality of life improvement, not blocking
- **Effort**: Medium - New utility module + sync refactor + tests
- **Risk**: Low - Pull path is isolated; push path unchanged
- **Breaking Change**: No - Pulled issues will have more structure, not less

## Related Key Documentation

| Document | Relevance | Section |
|----------|-----------|---------|
| `docs/ARCHITECTURE.md` | System design context for sync module | Issue Sync |
| `docs/reference/ISSUE_TEMPLATE.md` | Canonical template guide (v2.0) | All sections |
| `CONTRIBUTING.md` | Development guidelines | Issue Template v2.0 |

## Labels

- `enhancement`
- `sync`
- `templates`

## Session Log
- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/111eb543-d1ab-4bb9-b78b-61104209c4eb.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:verify-issues` - 2026-02-24 - Updated `_create_local_issue` line reference from 637-694 to 615-670
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified; no Python code currently loads issue-sections.json (all consumers are AI skill files); confirmed sync.py:615-670 uses hardcoded inline template as stated

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocks

- ENH-492

- ENH-494

- FEAT-441
- ENH-502
- ENH-496
- ENH-484
- FEAT-503
## Blocked By

- ENH-498
