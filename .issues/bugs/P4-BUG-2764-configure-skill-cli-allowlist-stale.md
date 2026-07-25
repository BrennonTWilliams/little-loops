---
id: BUG-2764
type: bug
priority: P4
status: done
captured_at: '2026-07-24T19:36:28Z'
completed_at: '2026-07-25T05:15:37Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 93
outcome_confidence: 69
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 10
score_change_surface: 22
---

# BUG-2764: configure skill's ll- CLI permission allowlist is stale (31 of 46 tools)

## Summary

`skills/configure/areas.md` offers a permission preset described as authorizing
"all 31 ll- CLI tools," but `scripts/pyproject.toml` now declares 46 console
entry points. Fifteen current tools are missing from the preset, so a user who
accepts it still gets permission prompts for them — and the "all" in the
description is wrong.

## Steps to Reproduce

1. `sed -n '/\[project.scripts\]/,/^\[/p' scripts/pyproject.toml | grep -c "="` → `46`
2. `sed -n '849p' skills/configure/areas.md | grep -oE 'll-[a-z-]+' | sort -u | wc -l` → `31`
3. Diff the two sets and observe 15 entry points absent from the preset.

## Current Behavior

The preset's description claims completeness ("all 31 ll- CLI tools") while
omitting:

`ll-adapt-agents-for-codex`, `ll-adapt-skills-for-codex`, `ll-artifact`,
`ll-code`, `ll-compact-session`, `ll-config`, `ll-generate-schemas`, `ll-init`,
`ll-migrate-labels`, `ll-queue`, `ll-verify-decisions`, `ll-verify-kinds`,
`ll-verify-package-data`, `ll-verify-skill-budget`, `ll-verify-triggers`,
plus the `mcp-call` entry point.

## Expected Behavior

The preset covers every current `[project.scripts]` entry point (or explicitly
scopes itself and drops the word "all"), and does not silently drift as tools
are added.

## Root Cause

- **File**: `skills/configure/areas.md`
- **Anchor**: the permissions preset at ~line 849
- **Cause**: The list is a hand-maintained literal with a hardcoded count in its
  own description. Nothing ties it to `scripts/pyproject.toml`, and no test
  compares the two, so every new entry point since it was written has drifted out.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The `areas.md:849` preset string enumerates 30 `ll-` tool names + 1
  `Edit(.ll/ll-continue-prompt.md)` entry — 30, not 31 — so the "31" count is
  wrong even against its own list, independent of the pyproject.toml drift.
  `mcp-call` is intentionally excluded (not `ll-`-prefixed).
- **A second, independently-stale copy of this same allowlist exists** at
  `scripts/little_loops/init/writers.py:25-51` (`_LL_PERMISSIONS`, a 25-entry
  tuple written by `merge_settings()` into `.claude/settings*.json` during
  `ll-init`). Its tool set differs from `areas.md`'s 30-entry list — e.g.
  `writers.py` includes `ll-verify-package-data` and `ll-create-extension`,
  which `areas.md` also has, but the two lists were clearly edited
  independently and have each drifted from `pyproject.toml` and from each
  other. Any fix must reconcile all three sources, not just `areas.md` vs.
  `pyproject.toml`.
- The exact missing-15 set relative to `pyproject.toml`'s 46 entries:
  `ll-artifact`, `ll-code`, `ll-compact-session`, `ll-config`, `ll-queue`,
  `ll-generate-schemas`, `ll-adapt-skills-for-codex`,
  `ll-adapt-agents-for-codex`, `ll-verify-triggers`,
  `ll-verify-package-data` (present in `writers.py` but not `areas.md`),
  `ll-verify-decisions`, `ll-verify-kinds`, `ll-verify-skill-budget`,
  `ll-init`, plus `ll-migrate-labels`.
- `areas.md:855` says the merge "using the same logic as SKILL.md Step 10",
  but `skills/configure/SKILL.md` currently only defines Steps 1–4 (Area
  Selection, Interactive Configuration, Show Changes, Update Config) — no
  `Step 10` heading exists in that file. This cross-reference is itself
  stale/broken and worth a one-line fix alongside the allowlist regen.
- `scripts/tests/test_wiring_init_and_configure.py:88` hardcodes an
  assertion that `areas.md` contains the literal string `"Authorize all 31"`
  (tagged `FEAT-1049`). This test **must be updated in the same change** or
  it will fail once the stale count is corrected.
- `scripts/tests/test_wiring_cli_registry.py` has `# REMOVED (stale/false-positive)`
  comments at lines 94, 116, 144 referencing earlier "Authorize all 29"
  assertions — evidence this count has drifted and been hand-patched at
  least once before (29 → 31 → now stale again at 46 actual entry points).
- `README.md:178` carries its own independent hardcoded count ("44 typed CLI
  tools") for the same underlying inventory, also currently stale.
  `CONTRIBUTING.md:418-432` documents the full wiring checklist for adding a
  new CLI tool, including "Add tool name; increment 'Authorize all N' count"
  for `areas.md` and the `README.md` count separately — both are
  hand-maintained per that checklist, not derived.

## Motivation

The preset exists specifically to eliminate permission prompts during automation
runs. A preset that covers two-thirds of the tools delivers prompts anyway at
exactly the moments automation cannot answer them — and the "all" wording means
users won't think to check. This is also a representative instance of the
hand-maintained-inventory drift that FEAT-2763 aims to detect systematically.

## Proposed Solution

Regenerate the list from `scripts/pyproject.toml` and drop the hardcoded count
from the prose (say "all ll- CLI tools", not "all 31"), so the description
cannot go stale independently of the list.

Then prevent recurrence with a pytest gate that parses `[project.scripts]` and
asserts every entry point appears in the preset — cost-free, runs in the
existing `python -m pytest scripts/tests/` suite, and consistent with the
`ll-verify-*` family's convention. Decide during implementation whether
maintainer-only tools (`ll-generate-schemas`, `ll-adapt-*-for-codex`) and the
non-`ll-` `mcp-call` belong in a user-facing preset, and encode that decision as
an explicit exclusion list in the test rather than a silent omission.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reference implementation for the new gate**: `scripts/little_loops/cli/verify_kinds.py`
  (75 lines) is the closest existing `ll-verify-*` analog — a small module
  comparing two hand-maintained inventories with a `_run() -> (exit_code, diff)`
  function, an `argparse` `main_verify_kinds()` wrapper, and a
  `frozenset`-based exclusion list (`_KINDLESS_TABLES`) with inline per-entry
  comments explaining each exclusion. Its pytest wrapper,
  `scripts/tests/test_verify_kinds.py` (53 lines), patches the internal
  data-gathering function to test both the clean-state and drift-detected
  paths — a directly reusable test shape.
- Registration for a new `ll-verify-*` tool is three-place:
  `scripts/pyproject.toml` `[project.scripts]` entry, an import in
  `scripts/little_loops/cli/__init__.py`, and an `__all__` addition in the
  same file (see `verify_kinds` wiring at `cli/__init__.py:93,139`).
- **No existing helper parses `[project.scripts]`** — the three current
  `tomllib` call sites (`host_runner.py:502-505`, `init/introspect.py:134-138`,
  `cli/logs.py:955-960`) each parse a different TOML file/key. The new gate
  will need its own `tomllib.loads(pyproject_path.read_text())["project"]["scripts"]`
  extraction, following the existing `try/except (OSError, tomllib.TOMLDecodeError)`
  guard convention used at those sites.
- Exclusion-list precedent to model the maintainer-only-tools decision on:
  `_ALLOWLIST` in `scripts/little_loops/cli/verify_package_data.py:32-39`
  (frozenset with inline per-entry comments, directly asserted against in
  `test_verify_package_data.py:362-365`) and `EXCLUDED_DIRECTORIES` in
  `scripts/little_loops/work_verification.py:16-25` (tuple + comments) are
  both good shapes for whatever exclusion set this gate ends up needing.
- Because a second stale list exists at `writers.py:_LL_PERMISSIONS` (see Root
  Cause findings above), the "regenerate the list" step applies to **two**
  files, not one, and the new pytest gate should assert both against
  `pyproject.toml` (or assert `areas.md` and `writers.py` are consistent with
  each other, if a shared constant is introduced instead of two literals).

## Integration Map

### Files to Modify
- `skills/configure/areas.md` — the preset list and its description
- `scripts/little_loops/init/writers.py:25-51` (`_LL_PERMISSIONS`) — a second,
  independently-stale 25-entry copy of this allowlist, written into
  `.claude/settings*.json` by `merge_settings()` during `ll-init`; found during
  research, not previously listed in this issue
- `scripts/tests/test_wiring_init_and_configure.py:88` — hardcodes the literal
  `"Authorize all 31"` assertion; must be updated in lockstep or it fails

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/configure/SKILL.md` — surfaces the preset; also contains a broken
  cross-reference (`areas.md:855` says "SKILL.md Step 10" but SKILL.md only
  defines Steps 1–4)
- `.claude/settings.local.json` — where the preset is applied
- `scripts/tests/test_wiring_cli_registry.py:94,116,144` — `# REMOVED
  (stale/false-positive)` comments show this count has drifted and been
  hand-patched before (29 → 31)
- `scripts/little_loops/init/writers.py:58` (`_LEGACY_LL_PERMISSIONS`) and
  `:71-102` (`_CLAUDE_MD_COMMANDS_BLOCK`) — a **third** stale hand-maintained
  tool list living in the same file as `_LL_PERMISSIONS`; not previously
  listed, worth checking whether it needs the same regeneration or is
  intentionally legacy-scoped
- `scripts/little_loops/init/tui.py:903-905` — calls `merge_settings()`
  (interactive `ll-init` path); consumes `_LL_PERMISSIONS` indirectly, verify
  it still behaves correctly if the tuple's shape changes
- `scripts/little_loops/init/cli.py:497,663` (and one further call site) —
  calls `merge_settings()` in the headless `ll-init apply` path; same
  indirect-consumer verification as `tui.py`
- `scripts/little_loops/init/__init__.py:27,54` — re-exports `_LL_PERMISSIONS`
  and `merge_settings` in `__all__`; only needs a change if either symbol is
  renamed, but is the formal public-import surface consumed by
  `test_init_core.py`
- `commands/help.md:267-303` (esp. 281-286) — a fourth independent
  hand-maintained CLI tool enumeration (per-tool one-line descriptions); already
  missing `ll-verify-decisions`, `ll-verify-kinds`, `ll-verify-package-data`,
  `ll-config`, `ll-code`, `ll-compact-session` — same drift, pre-existing and
  not previously listed in this issue

### Similar Patterns
- `.claude/CLAUDE.md` § CLI Tools — another hand-maintained inventory of the same
  entry points; check it for the same drift
- `commands/help.md` — CLI listing
- `README.md:178` — separate hardcoded "44 typed CLI tools" count, also stale
- `CONTRIBUTING.md:418-432` — documents the current hand-maintained wiring
  checklist for adding a new CLI tool (includes the `areas.md` count-increment
  step this issue aims to eliminate)
- `scripts/little_loops/cli/verify_kinds.py` + `scripts/tests/test_verify_kinds.py`
  — closest existing `ll-verify-*` gate to model the new pytest gate after
  (small `_run()` diff function + argparse wrapper + frozenset exclusion list)
- `scripts/little_loops/cli/verify_package_data.py:32-39` (`_ALLOWLIST`) and
  `scripts/little_loops/work_verification.py:16-25` (`EXCLUDED_DIRECTORIES`)
  — exclusion-list-with-inline-comment shapes to model the maintainer-only-tool
  exclusion decision on

### Tests
- New gate in `scripts/tests/` comparing `[project.scripts]` to the preset(s) —
  follow the `verify_kinds.py` / `test_verify_kinds.py` pattern (four-class
  shape: `TestAll<X>` extraction sanity check, `TestRun` clean/dirty via
  `patch()`-injected synthetic mismatch, `TestMain<X>` argv-wrapped clean/dirty
  with `capsys` — confirmed the closest match, `test_verify_package_data.py`'s
  regex-lint shape is a weaker fit)
- `scripts/tests/test_wiring_init_and_configure.py:88` — update the hardcoded
  `"Authorize all 31"` string assertion
- `scripts/tests/test_init_core.py:33` — imports `_LL_PERMISSIONS` from
  `writers.py`; may need updating if that tuple's entries change.
  `TestMergeSettings.test_adds_all_ll_permissions` (~line 896-901) iterates
  `_LL_PERMISSIONS` dynamically rather than pinning a count, so it will **not**
  break from this fix — confirms the tuple-consuming tests are resilient by
  design; only the hardcoded-string wiring tests need updates.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py:90` — pins the literal
  `("README.md", "44 typed CLI tools", "FEAT-1045")` assertion; must be updated
  in lockstep if `README.md:178`'s count is corrected as part of this fix

### Documentation
- `docs/reference/CLI.md` — verify it lists all 46 tools
- `README.md:178` — stale "44 typed CLI tools" count, same root cause

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md:267-303` — fourth independently-drifted CLI tool
  enumeration (see Dependent Files above)

### Configuration
- `scripts/pyproject.toml` — the source of truth to generate from (no existing
  helper parses `[project.scripts]`; will need a fresh `tomllib` extraction —
  see Proposed Solution findings)

## Implementation Steps

1. Decide the inclusion policy for maintainer-only (`ll-generate-schemas`,
   `ll-adapt-*-for-codex`) and non-`ll-` (`mcp-call`) entry points.
2. Regenerate both `skills/configure/areas.md:849` and
   `scripts/little_loops/init/writers.py:25-51` (`_LL_PERMISSIONS`) from
   `[project.scripts]`; remove the hardcoded "31" count from `areas.md`'s
   description text.
3. Add the pytest gate — model it on `scripts/little_loops/cli/verify_kinds.py`
   / `scripts/tests/test_verify_kinds.py` — with an explicit, commented
   exclusion list (see `verify_package_data.py:_ALLOWLIST` or
   `work_verification.py:EXCLUDED_DIRECTORIES` for the shape). Parse
   `pyproject.toml` via `tomllib` following the `try/except (OSError,
   tomllib.TOMLDecodeError)` convention used elsewhere in the codebase.
4. Update `scripts/tests/test_wiring_init_and_configure.py:88`'s hardcoded
   `"Authorize all 31"` assertion to match the new wording.
5. Fix the broken `areas.md:855` cross-reference to "SKILL.md Step 10" (no
   such step currently exists in `skills/configure/SKILL.md`).
6. Sweep `.claude/CLAUDE.md`, `docs/reference/CLI.md`, and `README.md:178`
   (separate "44 typed CLI tools" count) for the same drift.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Decide whether `_LEGACY_LL_PERMISSIONS` / `_CLAUDE_MD_COMMANDS_BLOCK`
   (`writers.py:58,71-102`) — a third stale hand-maintained list in the same
   file — needs regeneration too, or is intentionally legacy-scoped; document
   the decision.
8. Sweep `commands/help.md:267-303` for the same per-tool-listing drift found
   in `areas.md` and `writers.py` (already missing 6 tools).
9. If `README.md:178`'s count is corrected, update
   `scripts/tests/test_wiring_guides_and_meta.py:90`'s hardcoded
   `"44 typed CLI tools"` assertion in lockstep.
10. Sanity-check `scripts/little_loops/init/tui.py:903-905` and
    `scripts/little_loops/init/cli.py:497,663` (the two `merge_settings()`
    call sites) still behave correctly against the regenerated
    `_LL_PERMISSIONS` tuple — no code change expected, verification only.

## Impact

- **Priority**: P4 - Causes avoidable permission prompts, not incorrect behavior.
- **Effort**: Small - Regenerate a list plus a short test.
- **Risk**: Low - Broadening a permission preset the user opts into explicitly;
  the only real consideration is whether maintainer-only tools should be
  auto-authorized for all users.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | Canonical CLI tools list (check for the same drift) |
| `docs/reference/CLI.md` | Per-tool CLI reference |

## Resolution

- Regenerated the "All ll- commands" preset in `skills/configure/areas.md` from
  `scripts/pyproject.toml`'s `[project.scripts]` and dropped the hardcoded "31"
  count from the description text.
- Regenerated `_LL_PERMISSIONS` in `scripts/little_loops/init/writers.py` to the
  same canonical 46-tool set.
- Added `scripts/little_loops/cli/verify_cli_allowlist.py` (`ll-verify-cli-allowlist`)
  which parses `pyproject.toml` and asserts both presets cover every `ll-` entry
  point (excluding `mcp-call`), with `scripts/tests/test_verify_cli_allowlist.py`
  as the pytest gate. Registered in `pyproject.toml` and `cli/__init__.py`.
- Fixed the broken `areas.md:855` "SKILL.md Step 10" cross-reference (no such
  step exists) by describing the merge steps inline instead.
- Updated the hardcoded assertions in `test_wiring_init_and_configure.py` and
  `test_wiring_guides_and_meta.py`, and corrected `README.md`'s stale "44 typed
  CLI tools" count to 46.
- Added `ll-verify-cli-allowlist` to `.claude/CLAUDE.md`'s CLI Tools list.
- Decision: all `ll-`-prefixed entry points (including maintainer-only tools
  like `ll-generate-schemas` and the `ll-adapt-*-for-codex` aliases) are
  included in the preset; only the non-`ll-` `mcp-call` is excluded. This keeps
  the exclusion list minimal and avoids a second hand-maintained category that
  could itself drift.
- Out of scope (not required to close this bug, left for a follow-up): the
  broader `commands/help.md` and `docs/reference/CLI.md` per-tool listing
  drift, and `writers.py`'s `_LEGACY_LL_PERMISSIONS` / `_CLAUDE_MD_COMMANDS_BLOCK`
  constants.

## Session Log
- `/ll:manage-issue` - 2026-07-25T05:15:01Z - `b8e73086-3b71-476e-b3f4-8f41e6a9c328.jsonl`
- `/ll:wire-issue` - 2026-07-25T05:05:17 - `683f9bb0-135f-4893-baea-024d1f4121c1.jsonl`
- `/ll:refine-issue` - 2026-07-25T05:00:54 - `d9ddeefc-e56e-42ef-9912-398c2dd6cee4.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
