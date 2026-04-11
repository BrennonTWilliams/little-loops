---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 90
---

# FEAT-1045: Extension SDK Documentation Updates

## Summary

Update all documentation after FEAT-1043 (LLTestBus) and FEAT-1044 (ll-create-extension) are implemented: API reference, CLI reference, architecture docs, configuration guide, CONTRIBUTING.md, CLAUDE.md, and README.md.

## Parent Issue

Decomposed from FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Context

Once LLTestBus and ll-create-extension are implemented, 7 documentation files need updating to reflect the new tooling. Grouping all doc updates in a single focused issue avoids scattered doc touches across the two implementation issues.

## Current Behavior

- No `LLTestBus` docs in `docs/reference/API.md`
- No `ll-create-extension` section in `docs/reference/CLI.md`
- No `create_extension.py` / `testing.py` in `docs/ARCHITECTURE.md`
- No `ll-create-extension` or `LLTestBus` cross-reference in `docs/reference/CONFIGURATION.md` "Authoring an extension" block
- CONTRIBUTING.md missing extension development workflow
- `.claude/CLAUDE.md` CLI Tools list missing `ll-create-extension`
- README.md tool count and CLI Tools section outdated

## Expected Behavior

All 7 files updated to accurately document the new extension SDK tooling.

## Proposed Solution

Make all doc changes in a single pass after FEAT-1043 and FEAT-1044 land.

## Integration Map

### Files to Modify

1. **`docs/reference/API.md`** (lines 5037-5209, existing extension section from ENH-922):
   - Add `LLTestBus` API docs: class, `from_jsonl()`, `register()`, `replay()`, `delivered_events`
   - Add create → develop → test → publish workflow section
   - Note: there is a `<!-- TODO: update-docs stub — FEAT-927 -->` marker at lines 5142-5144 (separate scope)

2. **`CONTRIBUTING.md`**:
   - Add extension development workflow section

3. **`.claude/CLAUDE.md`** (CLI Tools list, lines 104-116):
   - Add `- \`ll-create-extension\`` entry in alphabetical order

4. **`README.md`**:
   - Increment "13 CLI tools" to "14 CLI tools" (confirm count after FEAT-1044 lands)
   - Add `### ll-create-extension` section to `## CLI Tools`

5. **`docs/reference/CLI.md`**:
   - Add `### ll-create-extension` section with usage/flags (`<name>`, `--dry-run`, `--config`) before `### mcp-call`

6. **`docs/ARCHITECTURE.md`**:
   - Add `create_extension.py` to `scripts/little_loops/cli/` tree (lines 177-213)
   - Add `testing.py` to module list
   - Add `templates/extension/` to templates tree (lines 160-173)

7. **`docs/reference/CONFIGURATION.md`** ("Authoring an extension" block, lines 631-659):
   - Add cross-reference pointing to `ll-create-extension` for scaffolding and `LLTestBus` for offline testing

8. **`scripts/little_loops/cli/__init__.py`** module docstring (lines 3-18):
   - Add `- ll-create-extension: Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example`

## Implementation Steps

Verify line numbers against current file state before editing each file — line numbers above reflect state as of FEAT-916 refinement passes and may shift as FEAT-1043/1044 land.

1. Update `docs/reference/API.md` — extend existing extension section with `LLTestBus` API docs
2. Update `CONTRIBUTING.md` — add extension workflow section
3. Update `.claude/CLAUDE.md` — add `ll-create-extension` to CLI Tools list
4. Update `README.md` — increment count, add CLI section
5. Update `docs/reference/CLI.md` — add `ll-create-extension` command reference
6. Update `docs/ARCHITECTURE.md` — add new files to directory trees
7. Update `docs/reference/CONFIGURATION.md` — add cross-reference in extension block
8. Update `scripts/little_loops/cli/__init__.py` module docstring

## Acceptance Criteria

- [ ] `docs/reference/API.md` documents `LLTestBus` class and full extension SDK workflow
- [ ] `CONTRIBUTING.md` covers extension development (create → develop → test → publish)
- [ ] `.claude/CLAUDE.md` lists `ll-create-extension` in CLI Tools
- [ ] README.md tool count and CLI section are accurate
- [ ] `docs/reference/CLI.md` has `ll-create-extension` command reference
- [ ] `docs/ARCHITECTURE.md` directory trees include new files
- [ ] `docs/reference/CONFIGURATION.md` references both new tools in the extension authoring block

## Impact

- **Priority**: P4 - Developer experience documentation
- **Effort**: Small - Focused doc edits, no code changes
- **Risk**: None - Docs only
- **Breaking Change**: No
- **Depends On**: FEAT-1043 (LLTestBus implementation), FEAT-1044 (ll-create-extension implementation)

## Labels

`feat`, `extension-api`, `developer-experience`, `documentation`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- Both blockers unimplemented: `testing.py` (FEAT-1043) and `create_extension.py` (FEAT-1044) do not exist ✓
- No `LLTestBus` API docs added to `docs/reference/API.md` yet ✓
- Feature not yet implemented (awaiting FEAT-1043, FEAT-1044)

## Status

**Open** | Created: 2026-04-11 | Priority: P4

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
