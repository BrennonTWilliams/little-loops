---
id: FEAT-1460
type: FEAT
priority: P3
status: done
parent: FEAT-1453
discovered_date: 2026-05-12
completed_at: 2026-05-12T05:36:08Z
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1460: Hook-Intent Documentation — Navigation, Wiring Fixes & Tests

## Summary

Wire the new hook-intent documentation into site navigation and fix stale `hooks/core/` references across CLAUDE.md, skills, and tests. Covers mkdocs.yml nav, docs/index.md, CLI.md cross-link, two skill files, and adding `stdout` field test coverage to `test_hook_intents.py`. Run final verification gate.

## Parent Issue

Decomposed from FEAT-1453: Hook-Intent Abstraction Layer — Documentation

## Depends On

- FEAT-1458 (write-a-hook.md guide exists — nav entries target it)
- FEAT-1459 (reference doc updates exist — docs/index.md description update accurate)

## Scope

Covers FEAT-1453 Implementation Steps 10–14 and 16.

### Step 10 — Verification Gate

After all other steps complete:
- Run `ll-check-links` (or `python -m little_loops.cli.check_links`) over `docs/` to catch broken anchors
- Run `ll-verify-docs` to confirm documented counts still match
- Run `python -m pytest scripts/tests/test_feat1457_doc_wiring.py -v` — all assertions must pass (including `TestWriteAHookWiring` from FEAT-1458)

### Step 11 — Fix `hooks/core/` References

Replace `hooks/core/` → `scripts/little_loops/hooks/` in three files (structural reality: no `hooks/core/` directory exists; handlers live in `scripts/little_loops/hooks/`):

1. `.claude/CLAUDE.md` — `## Key Directories` `hooks/` entry: correct `core/` line
2. `skills/workflow-automation-proposer/SKILL.md` — Step 7 "For hooks" block: `"Handlers live in host-agnostic core code under hooks/core/"` → `"scripts/little_loops/hooks/"`
3. `skills/audit-claude-config/SKILL.md` — Plugin Components bullet (line 41): replace `hooks/core/` with `scripts/little_loops/hooks/`

Also update the corresponding test assertion:
- `scripts/tests/test_feat1457_doc_wiring.py::TestAuditClaudeConfigWiring.test_audit_scope_includes_core` — change assertion from `"hooks/core/"` to `"scripts/little_loops/hooks/"` (because Step 11 corrects the skill)

### Step 12 — `mkdocs.yml` Nav Section

The `nav:` block has no `claude-code/` section; the new `write-a-hook.md` (and existing `hooks-reference.md`, `automate-workflows-with-hooks.md`) will be invisible in the published site nav without nav entries. Add a `Claude Code:` nav group containing at minimum:
- `write-a-hook.md`
- `hooks-reference.md`
- `automate-workflows-with-hooks.md`

### Step 13 — `docs/index.md`

- Add entry for `docs/claude-code/write-a-hook.md`
- Broaden the `EVENT-SCHEMA.md` description line from "All LLEvent types…" to also mention hook intent types (`LLHookEvent`, `LLHookResult`) now that FEAT-1459 expanded that doc

### Step 14 — `docs/reference/CLI.md` Cross-Link

In `### ll-create-extension` section (lines 1310-1388): add a cross-link to `docs/claude-code/write-a-hook.md` for the authoring guide. (The guide itself links back to `ll-create-extension` — this completes the bidirectional link.)

### Step 16 — `stdout` Field Test Coverage

In `scripts/tests/test_hook_intents.py::TestLLHookResult`: add `stdout` field tests using the same structure as existing `feedback`/`decision`/`data` tests:
- `test_stdout_field_defaults_to_none`
- `test_to_dict_skips_stdout_when_none`
- `test_to_dict_includes_stdout_when_set`
- `test_roundtrip_with_stdout`

(This adds regression coverage for an already-shipped field that the FEAT-1459 reference docs will describe.)

## Acceptance Criteria

- `mkdocs.yml` has a `Claude Code:` nav group with entries for the three `docs/claude-code/` files
- `docs/index.md` has entry for `write-a-hook.md`; EVENT-SCHEMA.md description mentions hook intent types
- `docs/reference/CLI.md` `ll-create-extension` section links to `write-a-hook.md`
- `.claude/CLAUDE.md`, `skills/workflow-automation-proposer/SKILL.md`, `skills/audit-claude-config/SKILL.md` reference `scripts/little_loops/hooks/` not `hooks/core/`
- `TestAuditClaudeConfigWiring.test_audit_scope_includes_core` (`scripts/tests/test_feat1457_doc_wiring.py:118-122`) updated to assert `"scripts/little_loops/hooks/"`
- `TestClaudeMdWiring.test_hooks_entry_lists_core` (`scripts/tests/test_feat1457_doc_wiring.py:138-140`) updated/renamed to assert `"scripts/little_loops/hooks/"` substring in `.claude/CLAUDE.md` (otherwise Step 11.1 breaks this test — see Research Findings)
- `stdout` field has `to_dict`/`from_dict`/roundtrip test coverage in `TestLLHookResult` (recommended approach: extend existing `test_creation_defaults`/`test_to_dict_skips_none`/`test_to_dict_full`/`test_roundtrip`/`test_roundtrip_minimal` to also cover `stdout` — see Research Findings for the naming-convention divergence vs the Step 16 method names)
- `ll-check-links`, `ll-verify-docs`, and `test_feat1457_doc_wiring.py` all pass

## Source References

- `.claude/CLAUDE.md:40` — `## Key Directories` `hooks/` entry, the `core/` line: `  core/         # Host-agnostic Python handlers (session_start, pre_compact, ...) invoked by main_hooks()`
- `skills/workflow-automation-proposer/SKILL.md:117` — text `Handlers live in host-agnostic core code under hooks/core/ (or in a plugin's`
- `skills/audit-claude-config/SKILL.md:41` — `- **Hooks**: \`hooks/hooks.json\` + \`hooks/prompts/*.md\` + \`hooks/core/\` + \`hooks/adapters/\` - Lifecycle hooks (Python handlers in \`core/\`, host adapters in \`adapters/<host>/\`, intent handlers contributed via \`LLHookIntentExtension\`)`
- `scripts/tests/test_feat1457_doc_wiring.py:118-122` — `TestAuditClaudeConfigWiring.test_audit_scope_includes_core` (assertion on `"hooks/core/"` substring in `skills/audit-claude-config/SKILL.md`)
- `scripts/tests/test_feat1457_doc_wiring.py:138-140` — `TestClaudeMdWiring.test_hooks_entry_lists_core` (assertion on `"core/"` substring in `.claude/CLAUDE.md` — **also affected by Step 11**, see Research Findings below)
- `scripts/tests/test_feat1457_doc_wiring.py:109-110` — `TestAuditClaudeConfigWiring` class docstring that still says "must include hooks/adapters/ and hooks/core/" (cosmetic, but worth syncing)
- `scripts/tests/test_hook_intents.py:144-244` — `TestLLHookResult` class — see Research Findings for the actual test-method convention here (does NOT use `test_stdout_field_defaults_to_none`-style naming)
- `scripts/little_loops/hooks/types.py:116` — `stdout: str | None = None` field on `LLHookResult`
- `scripts/little_loops/hooks/types.py:130-132` — `to_dict` branch that emits `stdout` only when not `None`
- `scripts/little_loops/hooks/types.py:143` — `from_dict` line `stdout=data.get("stdout"),`
- `mkdocs.yml:65-91` — `nav:` block; no `Claude Code:` group present today
- `docs/index.md:40` — current EVENT-SCHEMA.md description line: "All LLEvent types, wire format, and machine-readable JSON schemas — primary reference for extension authors and external consumers"
- `docs/index.md:34-41` — `## Developer Documentation` section where the `write-a-hook.md` entry should be added
- `docs/reference/CLI.md:1301-1393` — `### ll-create-extension` section
- `docs/reference/CLI.md:1391` — **EXISTING** `> **See also:** [Write a little-loops hook](../claude-code/write-a-hook.md)` blockquote (Step 14 is largely already done — see Research Findings)
- `docs/reference/CLI.md:1492-1498` — `## See Also` already contains a `write-a-hook.md` entry

## Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current tree on 2026-05-12:_

### Step 14 (`docs/reference/CLI.md` cross-link) is already in place

The bidirectional link the issue calls for **already exists** in two locations:

1. `docs/reference/CLI.md:1391` — at the bottom of the `### ll-create-extension` section body:
   ```
   > **See also:** [Write a little-loops hook](../claude-code/write-a-hook.md) — full authoring walkthrough for the `LLHookIntentExtension` Protocol, including the adapter flow and pure-function + subprocess testing patterns.
   ```
2. `docs/reference/CLI.md:1498` — under the file-level `## See Also` section:
   ```
   - [write-a-hook.md](../claude-code/write-a-hook.md) — hook authoring guide for `LLHookIntentExtension`
   ```

**Implementer action**: verify both anchors render correctly via `ll-check-links`; no edit required for Step 14 unless `ll-check-links` reports a broken link.

### Step 11 also breaks a second test — `TestClaudeMdWiring.test_hooks_entry_lists_core`

The issue calls out updating `TestAuditClaudeConfigWiring.test_audit_scope_includes_core` (lines 118-122). But Step 11.1's edit to `.claude/CLAUDE.md` will also break `TestClaudeMdWiring.test_hooks_entry_lists_core` at `scripts/tests/test_feat1457_doc_wiring.py:138-140`, which asserts:

```python
assert "core/" in content, ".claude/CLAUDE.md hooks/ entry must list hooks/core/"
```

After Step 11.1 the line `core/         # Host-agnostic Python handlers ...` becomes something like `scripts/little_loops/hooks/  # Host-agnostic Python handlers ...`, which does NOT contain the substring `core/`. The test fails.

**Implementer action**: update `TestClaudeMdWiring.test_hooks_entry_lists_core` in the same commit as Step 11.1 — either delete the test, rename it to `test_hooks_entry_lists_handlers`, or change the asserted substring to `scripts/little_loops/hooks/`. Recommend renaming + asserting the new path so the wiring contract continues to be enforced.

Additionally, the `TestAuditClaudeConfigWiring` class docstring at `scripts/tests/test_feat1457_doc_wiring.py:109-110` says "audit-claude-config SKILL.md audit scope must include hooks/adapters/ and hooks/core/." This is a docstring (not an assertion) — it won't fail the suite, but it will be inaccurate after Step 11.3. Recommend updating in the same commit for consistency.

### Step 16 — existing test naming convention differs from what the issue requests

The issue requests four new test methods:
- `test_stdout_field_defaults_to_none`
- `test_to_dict_skips_stdout_when_none`
- `test_to_dict_includes_stdout_when_set`
- `test_roundtrip_with_stdout`

The current `TestLLHookResult` class at `scripts/tests/test_hook_intents.py:144-244` does **not** follow per-field naming. It uses combined tests that exercise all nullable fields together:

| Issue-requested name | Behavior tested by (existing method) | Line |
|---|---|---|
| `test_stdout_field_defaults_to_none` | `test_creation_defaults` (asserts `feedback`/`decision` default to `None`, `data` defaults to `{}`) | 147 |
| `test_to_dict_skips_stdout_when_none` | `test_to_dict_skips_none` (asserts `feedback`/`decision`/`data` are absent in dict when defaulted) | 173 |
| `test_to_dict_includes_stdout_when_set` | `test_to_dict_full` (asserts every populated field appears in dict) | 182 |
| `test_roundtrip_with_stdout` | `test_roundtrip` (full) + `test_roundtrip_minimal` (defaults) | 223, 237 |

**Implementer choice (no blocker — both are acceptable; pick one):**
- **Option A — extend existing tests.** Add `assert result.stdout is None` to `test_creation_defaults`, `assert "stdout" not in d` to `test_to_dict_skips_none`, populate `stdout="..."` plus `assert d["stdout"] == "..."` in `test_to_dict_full` and `test_roundtrip`, and `assert restored.stdout is None` in `test_roundtrip_minimal`. Matches existing style; least lines of new code.
- **Option B — add the four new methods verbatim.** Honors the issue text literally and gives `stdout` per-field coverage parallel to no other field. Creates a stylistic divergence inside the class.

Recommend **Option A** for consistency. If picked, update Acceptance Criteria to reference "extended `TestLLHookResult` tests cover `stdout`" rather than the four explicit method names.

### `hooks/core/` references outside the three named files (not in scope for Step 11)

Grep found these additional live-code occurrences of `hooks/core/`:

- `scripts/tests/test_feat1459_doc_wiring.py:160,167,174` — parenthetical strings inside assertion failure messages like `"(context-monitor.sh has not been migrated to hooks/core/)"`. These are explanatory text, not assertions on `hooks/core/`. They will be stale once `hooks/core/` is established as a non-existent path, but FEAT-1460's scope does not include them. **Follow-up issue may be worth filing if maintainers want to scrub all stale references.**

### Existing nav and index patterns confirmed

- `mkdocs.yml` uses 2-space indented group headers `  - Group Name:` with 4-space indented children `    - Display Name: path/to/file.md`. The new `Claude Code:` group should sit between `Reference:` and `Development:` (or after `Architecture:`) and follow this exact pattern.
- `docs/index.md` entries follow `- [Display Name](relative/path.md) - one-line description`. The new `write-a-hook.md` entry should go under `## Developer Documentation` (~line 41), near the EVENT-SCHEMA.md line, since both are extension-author resources.
- The `docs/claude-code/` directory contains **14 files** today (not just the 3 named in Step 12). The issue's "at minimum" phrasing is correct; if maintainers want broader nav coverage they can add more, but the 3 named files are the right baseline for shipping this issue.

## Integration Map

### Files to Modify

(All primary targets already described in Implementation Steps above.)

- `.claude/CLAUDE.md` — fix `core/` line in `## Key Directories` hooks/ entry
- `skills/workflow-automation-proposer/SKILL.md` — fix `hooks/core/` reference in Step 7 body
- `skills/audit-claude-config/SKILL.md` — fix `hooks/core/` reference in Plugin Components bullet
- `mkdocs.yml` — add `Claude Code:` nav group
- `docs/index.md` — add `write-a-hook.md` entry; broaden `EVENT-SCHEMA.md` description
- `docs/reference/CLI.md` — already wired (verify only via `ll-check-links`)
- `scripts/tests/test_feat1457_doc_wiring.py` — update two breaking assertions (lines 120, 140); update class docstring (line 110)
- `scripts/tests/test_hook_intents.py` — add `stdout` field coverage to `TestLLHookResult`

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests to update (will break without fix):**
- `scripts/tests/test_feat1457_doc_wiring.py::TestAuditClaudeConfigWiring.test_audit_scope_includes_core` (lines 118–122) — asserts `"hooks/core/" in content` on the skill; breaks after Step 11.3. Change asserted substring to `"scripts/little_loops/hooks/"`. [Agent 3 finding]
- `scripts/tests/test_feat1457_doc_wiring.py::TestClaudeMdWiring.test_hooks_entry_lists_core` (lines 138–140) — asserts `"core/" in content` on `.claude/CLAUDE.md`; breaks after Step 11.1 (substring `"core/"` does not appear in `scripts/little_loops/hooks/`). Rename to `test_hooks_entry_lists_handlers` and assert `"scripts/little_loops/hooks/"`. [Agent 3 finding]

**Existing tests to update (stale text, not assertions):**
- `scripts/tests/test_feat1457_doc_wiring.py::TestAuditClaudeConfigWiring` class docstring (line 109–110) — says "must include hooks/adapters/ and hooks/core/" — update to mention `scripts/little_loops/hooks/`. [Agent 3 finding]

**New tests to write (Step 12 and Step 13 have no existing coverage):**
- Add a `TestNavWiring` (or `TestMkdocsNavWiring`) class to `scripts/tests/test_feat1457_doc_wiring.py` asserting that `mkdocs.yml` contains a `Claude Code:` nav group and nav entries for `claude-code/write-a-hook.md`, `claude-code/hooks-reference.md`, `claude-code/automate-workflows-with-hooks.md`. The Step 10 verification gate references this test file — without these assertions, Steps 12 and 13 are unprotected. [Agent 3 gap finding]
- Add a `TestIndexMdWiring` class (or methods in `TestNavWiring`) asserting that `docs/index.md` contains a link to `write-a-hook.md` and that the `EVENT-SCHEMA.md` description line mentions hook intent types (`LLHookEvent` or `LLHookResult`). [Agent 3 gap finding]
- Follow the established wiring test pattern: declare `MKDOCS_YML = PROJECT_ROOT / "mkdocs.yml"` and `INDEX_MD = PROJECT_ROOT / "docs" / "index.md"` as module-level `Path` constants; each test method calls `.read_text()` once then asserts a substring. [Agent 3 pattern example]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

These files use `LLHookResult`/`LLHookEvent`/`stdout` and do NOT require changes for this issue, but are listed for implementer awareness:
- `scripts/little_loops/hooks/__init__.py` — dispatcher reads `result.stdout` and writes to `sys.stdout` (lines 110–111); unaffected by this issue [Agent 1 finding]
- `scripts/little_loops/hooks/session_start.py` — constructs `LLHookResult(stdout=stdout_payload)`; unaffected by this issue [Agent 2 finding]
- `scripts/little_loops/__init__.py` — re-exports `LLHookEvent`, `LLHookResult`, `LLHookIntentExtension`; unaffected by this issue [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

These doc files already document `stdout` and the hook-intent types correctly — **no changes needed** for this issue:
- `docs/reference/EVENT-SCHEMA.md` — `LLHookResult` fields table at lines 54–62 already includes `stdout` row; no change needed [Agent 2 finding]
- `docs/reference/API.md` — documents `LLHookResult.stdout` at lines 5647 and 5658; no change needed [Agent 2 finding]
- `docs/claude-code/write-a-hook.md` — documents `stdout` field at line 45; no change needed [Agent 2 finding]
- `docs/claude-code/hooks-reference.md` — references `stdout` in `LLHookResult` description; no change needed [Agent 2 finding]

### Out-of-Scope Stale References

_Wiring pass added by `/ll:wire-issue`:_

`hooks/core/` appears in `scripts/tests/test_feat1459_doc_wiring.py` at lines 160, 167, 174 — inside assertion *failure message* strings only (not in the predicate), so these do **not** break after FEAT-1460 changes the skill files. They are explanatory text and are out of scope per the issue description. [Agent 2 + 3 finding]

## Resolution

Implemented FEAT-1453 Steps 10–14 and 16 in a single commit:

- **Step 11 (hooks/core/ references)** — Replaced `hooks/core/` with `scripts/little_loops/hooks/` in `.claude/CLAUDE.md` (`## Key Directories` block), `skills/workflow-automation-proposer/SKILL.md` (Step 7 "For hooks" sketch), and `skills/audit-claude-config/SKILL.md` (Plugin Components bullet).
- **Step 12 (mkdocs nav)** — Added a `Claude Code:` nav group to `mkdocs.yml` between `Reference:` and `Development:`, with entries for `write-a-hook.md`, `hooks-reference.md`, and `automate-workflows-with-hooks.md`.
- **Step 13 (docs/index.md)** — Added `Write a Hook` entry under `## Developer Documentation` and broadened the `EVENT-SCHEMA.md` description to mention `LLHookEvent` and `LLHookResult`.
- **Step 14 (CLI.md cross-link)** — Verified the bidirectional link at `docs/reference/CLI.md:1391` and the `## See Also` entry already exist; no edit needed.
- **Step 16 (stdout coverage)** — Used **Option A** (per Codebase Research Findings recommendation): extended `TestLLHookResult.test_creation_defaults`, `test_creation_full`, `test_to_dict_skips_none`, `test_to_dict_full`, `test_from_dict`, `test_from_dict_missing_fields`, `test_roundtrip`, and `test_roundtrip_minimal` to cover the `stdout` field. This matches the existing per-class test style instead of adding four parallel per-field methods (Option B).
- **Test wiring follow-ups** — Updated `TestAuditClaudeConfigWiring.test_audit_scope_includes_core` to assert `scripts/little_loops/hooks/`; renamed `TestClaudeMdWiring.test_hooks_entry_lists_core` → `test_hooks_entry_lists_handlers` with an assertion on `scripts/little_loops/hooks/`; updated the `TestAuditClaudeConfigWiring` class docstring; added new `TestMkdocsNavWiring` (4 methods) and `TestIndexMdWiring` (2 methods) classes to lock in Steps 12 and 13.

Verification:
- `python -m pytest scripts/tests/test_feat1457_doc_wiring.py scripts/tests/test_hook_intents.py` — 61 passed, 0 failed.
- `python -m pytest scripts/tests/` — 6492 passed, 7 pre-existing failures (`test_generate_schemas.py`, `test_update_skill.py`) unrelated to this issue's change set.
- `ll-check-links` — 6 broken external HTTP links, all in `.claude/skills/excalidraw-diagram/` and `.issues/completed/`; none in `docs/` and none introduced by this issue.
- `ll-verify-docs` — 1 pre-existing mismatch in `CONTRIBUTING.md:522` (skills count), unrelated to this issue.
- `ruff check` on touched test files — clean.

## Session Log
- `/ll:manage-issue` - 2026-05-12T05:36:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ee24c53-4a50-40f5-87d0-cfa286e6878c.jsonl`
- `/ll:ready-issue` - 2026-05-12T05:30:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/833b1dee-1923-413b-8bf1-9689f2423052.jsonl`
- `/ll:wire-issue` - 2026-05-12T05:25:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79fead5a-8bf9-428e-a7b5-806678c17cb3.jsonl`
- `/ll:refine-issue` - 2026-05-12T05:21:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80d5db40-25d8-4ef3-a5be-eeffe799ff83.jsonl`
- `/ll:issue-size-review` - 2026-05-12T04:28:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`
- `/ll:confidence-check` - 2026-05-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
