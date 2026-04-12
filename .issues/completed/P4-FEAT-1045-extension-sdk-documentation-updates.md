---
discovered_date: 2026-04-11
discovered_by: issue-size-review
confidence_score: 98
outcome_confidence: 70
testable: false
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-12):_

**Blockers resolved**: FEAT-1043 and FEAT-1044 are in `.issues/completed/`. Implementation files confirmed on disk:
- `scripts/little_loops/testing.py` — `LLTestBus` class (`from_jsonl`, `register`, `replay`, `delivered_events`); 104 lines
- `scripts/little_loops/cli/create_extension.py` — `main_create_extension()` with positional `name` and `--dry-run`; **no `--config` flag** (contrary to earlier drafts)
- `templates/extension/` — scaffold templates (`extension.py.tmpl`, `test_extension.py.tmpl`, `pyproject.toml.tmpl`)

**Items 5 and 8 above are already done:**
- `docs/reference/CLI.md:981-1070` — `ll-create-extension` section fully written
- `scripts/little_loops/cli/__init__.py:17` — `ll-create-extension` in docstring, imported at line 22, exported in `__all__` at line 44

**Item 1 is partially done:**
- `docs/reference/API.md:5325-5423` — `LLTestBus` fully documented (constructor, `from_jsonl`, `delivered_events`, `register`, `replay`, event filtering, full example). Only remaining gap: `little_loops.testing` is absent from the Module Overview table (`API.md:24-57`); add one row after line 37.

**Correction to Item 6 (`docs/ARCHITECTURE.md`):**
- Line 213 reads `└── testing.py # LLTestBus offline extension test harness` but that entry is for `cli/loop/testing.py` — the `ll-loop test/simulate` subcommand — **not** LLTestBus. This is a misattribution bug; fix the comment. Then add the real `scripts/little_loops/testing.py` to the package root listing.
- Also missing: `templates/extension/` directory from the templates tree (`ARCHITECTURE.md:160-173`).

**Remaining gaps with exact insertion points:**

| File | Anchor | What to add/fix |
|------|--------|-----------------|
| `docs/reference/API.md:37` | After `little_loops.extension` row | `` \| `little_loops.testing` \| Offline test harness (LLTestBus) for extension development \| `` |
| `docs/ARCHITECTURE.md:173` | Before `└── generic.json` | `├── extension/           # Extension scaffold templates (.tmpl)` |
| `docs/ARCHITECTURE.md:179` | After `├── auto.py` | `├── create_extension.py     # ll-create-extension scaffold CLI` |
| `docs/ARCHITECTURE.md:213` | Fix existing comment | `LLTestBus offline extension test harness` → `ll-loop test/simulate subcommand utilities` |
| `docs/ARCHITECTURE.md` | After `extension.py` in pkg root (~line 214) | `├── testing.py           # Offline LLTestBus test harness for extension development` |
| `.claude/CLAUDE.md:116` | After `ll-check-links` entry | `- \`ll-create-extension\` - Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example` |
| `README.md:90` | Inline | `13 CLI tools` → `14 CLI tools` |
| `README.md` | After `### ll-gitignore` section (~line 444) | New `### ll-create-extension` section |
| `CONTRIBUTING.md:185` | After `├── auto.py` in cli/ tree | `├── create_extension.py  # ll-create-extension scaffold CLI` |
| `CONTRIBUTING.md` | Package root listing, before `├── extensions/` | Add `extension.py` and `testing.py` entries |
| `CONTRIBUTING.md` | After `## Adding Skills` (~line 437) | New `## Authoring Extensions` workflow section |
| `docs/reference/CONFIGURATION.md:659` | After existing cross-reference sentence | Tip pointing to `ll-create-extension` (CLI.md) and `LLTestBus` (API.md) |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — Add release note bullet documenting the FEAT-1045 doc updates in the current release block when this issue lands [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — No assertions currently guard the FEAT-1045 target doc files; extend this file with live-content checks following its established pattern:
  - Assert `ll-create-extension` appears in `README.md` CLI Tools section
  - Assert `LLTestBus` / `little_loops.testing` row appears in `docs/reference/API.md` Module Overview table
  - Assert `ll-create-extension` appears in `.claude/CLAUDE.md` CLI Tools list
  - Assert `ll-create-extension` section exists in `docs/reference/CLI.md` (already present, but unguarded)
- `scripts/tests/test_testing.py` and `scripts/tests/test_create_extension.py` — existing test suites covering the implementation files; no update needed for this doc-only issue [Agent 3 finding]

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected, concrete steps (items 3 and 5 from original list are already done):_

Effective remaining work in recommended order:

1. **`docs/ARCHITECTURE.md`** (4 sub-edits):
   - Templates tree (`ARCHITECTURE.md:173`): Add `├── extension/           # Extension scaffold templates (.tmpl)` before `└── generic.json`
   - cli/ tree (`ARCHITECTURE.md:179`): Add `├── create_extension.py     # ll-create-extension scaffold CLI` after `├── auto.py`
   - Bug fix (`ARCHITECTURE.md:213`): Change comment `LLTestBus offline extension test harness` → `ll-loop test/simulate subcommand utilities`
   - Package root (~`ARCHITECTURE.md:214`): Add `├── testing.py           # Offline LLTestBus test harness for extension development` after the `extension.py` entry

2. **`docs/reference/API.md:37`** — Insert `| \`little_loops.testing\` | Offline test harness (LLTestBus) for extension development |` after the `little_loops.extension` row in the Module Overview table

3. **`.claude/CLAUDE.md:116`** — Add `- \`ll-create-extension\` - Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example` after the `ll-check-links` entry (alphabetical order)

4. **`README.md`** — Change `13 CLI tools` → `14 CLI tools` at line 90; add `### ll-create-extension` section after `### ll-gitignore` (~line 444) before `### ll-verify-docs / ll-check-links`

5. **`CONTRIBUTING.md`** (3 sub-edits):
   - cli/ tree (after `├── auto.py` at line 185): Add `├── create_extension.py  # ll-create-extension scaffold CLI`
   - Package root listing (before `├── extensions/` sub-package): Add `├── extension.py  # Extension protocol, loader, and reference implementation` and `├── testing.py   # Offline LLTestBus test harness for extension development`
   - After `## Adding Skills` (~line 437): Add `## Authoring Extensions` section covering create → develop → test → publish workflow

6. **`docs/reference/CONFIGURATION.md:659`** — After the existing `Extensions can also be auto-discovered...` sentence, add a tip cross-referencing `ll-create-extension` ([CLI.md#ll-create-extension](CLI.md#ll-create-extension)) and `LLTestBus` ([API.md#lltestbus](API.md#lltestbus))

Pre-edit verification: `python -m pytest scripts/tests/test_create_extension.py scripts/tests/test_testing.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `CHANGELOG.md` — add release note entry documenting the FEAT-1045 documentation updates in the current release block
8. Optionally extend `scripts/tests/test_create_extension_wiring.py` — add live-content guards for the updated doc files (`README.md`, `docs/reference/API.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`) following the existing pattern in that test file

## Acceptance Criteria

- [x] `docs/reference/API.md` documents `LLTestBus` class and full extension SDK workflow
- [x] `CONTRIBUTING.md` covers extension development (create → develop → test → publish)
- [x] `.claude/CLAUDE.md` lists `ll-create-extension` in CLI Tools
- [x] README.md tool count and CLI section are accurate
- [x] `docs/reference/CLI.md` has `ll-create-extension` command reference
- [x] `docs/ARCHITECTURE.md` directory trees include new files
- [x] `docs/reference/CONFIGURATION.md` references both new tools in the extension authoring block

## Impact

- **Priority**: P4 - Developer experience documentation
- **Effort**: Small - Focused doc edits, no code changes
- **Risk**: None - Docs only
- **Breaking Change**: No
- **Depends On**: FEAT-1043 (LLTestBus implementation) ✅ completed, FEAT-1044 (ll-create-extension implementation) ✅ completed — this issue is now unblocked

## Labels

`feat`, `extension-api`, `developer-experience`, `documentation`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- Both blockers unimplemented: `testing.py` (FEAT-1043) and `create_extension.py` (FEAT-1044) do not exist ✓
- No `LLTestBus` API docs added to `docs/reference/API.md` yet ✓
- Feature not yet implemented (awaiting FEAT-1043, FEAT-1044)

## Resolution

**Completed** — 2026-04-12

All 7 documentation files updated in a single pass:
- `docs/reference/API.md` — added `little_loops.testing` row to Module Overview table
- `docs/ARCHITECTURE.md` — added `extension/` to templates tree, `create_extension.py` to cli/ tree, fixed `cli/loop/testing.py` comment misattribution, added `extension.py` and `testing.py` to package root listing
- `.claude/CLAUDE.md` — added `ll-create-extension` entry to CLI Tools list
- `README.md` — incremented count to 14, added `### ll-create-extension` section
- `CONTRIBUTING.md` — added `create_extension.py` to cli/ tree, added `extension.py`/`testing.py` to package root, added `## Authoring Extensions` workflow section
- `docs/reference/CONFIGURATION.md` — added tip cross-referencing `ll-create-extension` and `LLTestBus`
- `CHANGELOG.md` — added FEAT-1045 release note to v1.80.0 block
- `scripts/tests/test_create_extension_wiring.py` — extended with 5 live-content guards for FEAT-1045 targets (all pass)

## Status

**Completed** | Created: 2026-04-11 | Closed: 2026-04-12 | Priority: P4

## Session Log
- `/ll:manage-issue` - 2026-04-12T16:18:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d082d17-d895-4266-a5dd-6916d61eeda0.jsonl`
- `/ll:ready-issue` - 2026-04-12T16:11:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/388c35ae-4c5c-4460-87fb-eccb1507565e.jsonl`
- `/ll:confidence-check` - 2026-04-12T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc0ab9f5-bd9c-4c21-a2d2-8a159bb1ea23.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:06:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5e1862d-1ce2-4fd0-b6cf-ed246f5c9bff.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:01:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c65d2b05-89e3-4873-bc5a-57a30f09d366.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:issue-size-review` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8463ec2-3356-49c3-888b-ccb8aab90cb6.jsonl`
