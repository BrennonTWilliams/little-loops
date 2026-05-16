---
id: FEAT-1504
type: FEAT
priority: P4
status: done
captured_at: '2026-05-16T15:07:07Z'
completed_at: '2026-05-16T17:27:51Z'
discovered_date: 2026-05-16
discovered_by: issue-size-review
parent: FEAT-1496
blocked_by:
- FEAT-1523
labels:
- host-compat
- preflight
- docs
size: Small
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1504: ll-doctor — documentation and wiring touchpoints

## Summary

Register `ll-doctor` across all count-tracked and cross-reference touchpoints: CLI tool counts, permissions blocks, doc sections, and symbol tables. Mechanical but must be done in one pass to keep string-matching tests green.

## Parent Issue

Decomposed from FEAT-1496: Host-capability preflight check (`ll-doctor`)

## Scope

Covers implementation steps 8, 12, 13 from the parent issue (step 9 — run checks — is also included here).

**Depends on**: FEAT-1523 (tool name and new dataclass names established), FEAT-1503 (entry-point registered; confirms final tool name `ll-doctor`). Can run in parallel with FEAT-1503 once FEAT-1523 lands — the docs changes are mechanical and do not require `doctor.py` to exist.

## Current Behavior

`ll-doctor` is being introduced by sibling issues FEAT-1523/FEAT-1503 but is not yet registered in the documentation and wiring surfaces:
- `README.md` advertises `"23 typed CLI tools"` and `"24 CLI tools"` — counts do not include the new tool.
- `commands/help.md` `CLI TOOLS` block omits `ll-doctor`.
- `skills/configure/areas.md` says `"Authorize all 21"` and does not enumerate `ll-doctor`.
- `skills/init/SKILL.md` permissions block has no `"Bash(ll-doctor:*)"` entry.
- `docs/reference/CLI.md` has no `### ll-doctor` section.
- `docs/reference/API.md` and `docs/ARCHITECTURE.md` symbol tables for `little_loops.host_runner` / `Host CLI Abstraction` do not list `CapabilityReport`, `CapabilityEntry`, `HookEntry`, or `describe_capabilities()`.
- `.claude/CLAUDE.md` CLI Tools section omits `ll-doctor`.
- `docs/reference/HOST_COMPATIBILITY.md` has no cross-link to `ll-doctor`.
- String-matching wiring tests (`test_create_extension_wiring.py`, `test_feat1462_doc_wiring.py`) assert the old counts and missing symbols and will fail once the new tool ships.

## Expected Behavior

After this change, every count-tracked and cross-reference surface acknowledges `ll-doctor`:
- README CLI tool counts incremented by 1 (verified against current strings before editing).
- `commands/help.md` lists `ll-doctor` alongside other CLI tools.
- `skills/configure/areas.md` count incremented and enumerates `ll-doctor`.
- `skills/init/SKILL.md` permissions block includes `"Bash(ll-doctor:*)"`.
- `docs/reference/CLI.md` has a `### ll-doctor` section modeled on `### ll-action`.
- API/architecture symbol tables document `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()`.
- `.claude/CLAUDE.md` CLI Tools section includes `ll-doctor`.
- `docs/reference/HOST_COMPATIBILITY.md` cross-links to `ll-doctor` as the runnable capability check.
- Wiring tests pass with the updated counts/symbol assertions.

## Motivation

Doc and wiring drift causes two concrete problems: (1) string-matching tests in `scripts/tests/test_create_extension_wiring.py` and `test_feat1462_doc_wiring.py` go red the moment `ll-doctor` lands, blocking the merge of FEAT-1523/FEAT-1503; (2) users running `/ll:init`, `/ll:configure`, or reading `docs/reference/CLI.md` would not discover the new tool, defeating the purpose of adding it. Bundling all touchpoints into a single mechanical pass keeps the parent FEAT-1496 work shippable in one merge without partial-wiring regressions.

## Use Case

A developer onboarding to a new project runs `/ll:init`. The bash permissions block presented for approval lists `Bash(ll-doctor:*)` alongside other `ll-*` entries, so they grant it once. Later, they run `ll-doctor` to verify their host CLI supports the features little-loops needs, see a clean `CapabilityReport`, and proceed with confidence — without having to discover the tool by reading source.

## Acceptance Criteria

- [ ] `README.md` line 46 `"23 typed CLI tools"` → `"24 typed CLI tools"` and line 164 `"24 CLI tools"` → `"25 CLI tools"` (verify current string first; adjust counts accordingly)
- [ ] `commands/help.md` `CLI TOOLS` block includes `ll-doctor` entry
- [ ] `skills/configure/areas.md` `"Authorize all 21"` → `"Authorize all 22"` with `ll-doctor` in the enumeration
- [ ] `skills/init/SKILL.md` bash permissions block adds `"Bash(ll-doctor:*)"` alongside other `ll-*` entries
- [ ] `docs/reference/CLI.md` has a `### ll-doctor` section following the `### ll-action` model
- [ ] `docs/reference/API.md` `## little_loops.host_runner` symbol table documents `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()`
- [ ] `docs/ARCHITECTURE.md` `## Host CLI Abstraction` symbol table lists the new dataclasses
- [ ] `.claude/CLAUDE.md` CLI Tools section includes `ll-doctor`
- [ ] `docs/reference/HOST_COMPATIBILITY.md` cross-links to `ll-doctor`
- [ ] `scripts/tests/test_create_extension_wiring.py` updated: `"Authorize all 21"` → `"Authorize all 22"` assertion and `"23 typed CLI tools"` count assertion pass
- [ ] `scripts/tests/test_feat1462_doc_wiring.py` `TestApiMdWiring` covers `CapabilityReport` and `describe_capabilities` symbols (add assertions if missing)
- [ ] All tests pass: `python -m pytest scripts/tests/test_create_extension_wiring.py scripts/tests/test_feat1462_doc_wiring.py -v`

## Proposed Solution

Apply the mechanical doc/wiring updates in the order below (see Implementation Steps for full sequence). Key conventions:
- **Verify counts before incrementing** — use `grep -n "CLI tools\|typed CLI" README.md` and `grep -n "Authorize all" skills/configure/areas.md` to confirm the current N before bumping to N+1. Avoid hard-coding line numbers.
- **Model new sections after existing ones** — `### ll-doctor` in `docs/reference/CLI.md` follows the `### ll-action` formatting; CLAUDE.md entry mirrors neighbouring `ll-*` lines.
- **Symbol tables** — add `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()` to both `docs/reference/API.md` (`## little_loops.host_runner` symbol table) and `docs/ARCHITECTURE.md` (`## Host CLI Abstraction` symbol table) so cross-doc consistency holds.
- **Test updates** — bump the count assertion in `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` (and any sibling assertion on `"23 typed CLI tools"`) in lockstep with the README/areas edits; extend `TestApiMdWiring` in `test_feat1462_doc_wiring.py` to assert `CapabilityReport` and `describe_capabilities` are present in both API.md and ARCHITECTURE.md if not already covered.

No new abstractions or refactors; this issue is intentionally a single mechanical pass to keep string-matching tests green.

## Implementation Steps

1. **Verify current count strings** before editing — run `grep -n "CLI tools\|typed CLI" README.md` to confirm current numbers, then increment by 1.
2. Update `README.md` CLI tool count strings (lines ~46 and ~164).
3. Update `commands/help.md` — add `ll-doctor` entry in the `CLI TOOLS` block.
4. Update `skills/configure/areas.md` — increment `"Authorize all N"` and add `ll-doctor` to the enumeration.
5. Update `skills/init/SKILL.md` — add `"Bash(ll-doctor:*)"` to the permissions block.
6. Add `### ll-doctor` section to `docs/reference/CLI.md` (follow the `### ll-action` model for formatting).
7. Update `docs/reference/API.md` `## little_loops.host_runner` section — add `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()`, `apply_host_cli_from_config()` to the symbol table; update the stale `__all__` listing (line 5706) and the `HostRunner` Protocol listing (lines 5759–5772) to include `describe_capabilities()`.
8. ~~Update `docs/ARCHITECTURE.md`~~ — **skip**: `CapabilityReport`, `CapabilityEntry`, `HookEntry` are already documented in the `## Host Runner Layer` component table (line 551). No change needed.
9. Update `.claude/CLAUDE.md` CLI Tools section — add `ll-doctor` line.
10. Update `docs/reference/HOST_COMPATIBILITY.md` — add a cross-reference paragraph pointing users to `ll-doctor` for a runnable capability check.
11. Update `scripts/tests/test_create_extension_wiring.py` — fix 4 count assertions: lines 57, 79, 192, 196 (`"Authorize all 21"` → `"Authorize all 22"` and `"23 typed CLI tools"` → `"24 typed CLI tools"`).
11a. Update `scripts/tests/test_ll_logs_wiring.py` — fix `TestConfigureAreasWiring.test_authorize_all_count_is_17` (line 45): `"Authorize all 21"` → `"Authorize all 22"`.
12. Extend `scripts/tests/test_feat1462_doc_wiring.py` `TestApiMdWiring` — add 4 new test methods: `test_capability_report_documented`, `test_capability_entry_documented`, `test_hook_entry_documented`, `test_describe_capabilities_documented` (see Integration Map for exact code).
13. Create `scripts/tests/test_feat1504_doc_wiring.py` — new wiring test file asserting `ll-doctor` appears in `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md`, `skills/configure/areas.md`, `skills/init/SKILL.md`, `docs/reference/HOST_COMPATIBILITY.md`. Follow pattern from `test_ll_logs_wiring.py` (no fixtures, `Path.read_text()` per method).
14. Run: `python -m pytest scripts/tests/test_create_extension_wiring.py scripts/tests/test_feat1462_doc_wiring.py scripts/tests/test_ll_logs_wiring.py scripts/tests/test_feat1504_doc_wiring.py -v && ruff check scripts/`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `docs/reference/API.md` import code block (lines 5695–5703) — add `CapabilityEntry`, `CapabilityReport`, `HookEntry`, `apply_host_cli_from_config` to the `from little_loops.host_runner import (...)` example alongside the `__all__` edit in step 7
2. Create `scripts/tests/test_feat1504_doc_wiring.py` — new wiring test following the established 28-file convention; model after `test_ll_logs_wiring.py`; cover `ll-doctor` string in all 6 updated docs/skill/command files

## Files to Modify

- `README.md` — CLI tool count strings (lines 46, 164)
- `commands/help.md` — `ll-doctor` entry in CLI TOOLS block (lines 239–264)
- `skills/configure/areas.md` — "Authorize all N" count (line 823)
- `skills/init/SKILL.md` — permissions block (lines 502–519) + CLAUDE.md append template (lines 564–583) + CLAUDE.md create template (lines 601–613)
- `docs/reference/CLI.md` — new `### ll-doctor` section (add after line 89, model after `### ll-action` at lines 33–89)
- `docs/reference/API.md` — symbol table + `__all__` + `HostRunner` Protocol listing in `## little_loops.host_runner` (lines 5691–5834)
- ~~`docs/ARCHITECTURE.md`~~ — **already up to date**; `CapabilityReport`, `CapabilityEntry`, `HookEntry` already documented in `## Host Runner Layer` component table (line 551). No edit needed.
- `.claude/CLAUDE.md` — CLI Tools section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link
- `scripts/tests/test_create_extension_wiring.py` — 4 count assertions at lines 57, 79, 192, 196
- `scripts/tests/test_feat1462_doc_wiring.py` — add 4 new test methods to `TestApiMdWiring`
- `scripts/tests/test_ll_logs_wiring.py` — **additional file not in original scope**: `TestConfigureAreasWiring.test_authorize_all_count_is_17` (line 45) also asserts `"Authorize all 21"` and must be updated to `"Authorize all 22"`
- `scripts/tests/test_feat1504_doc_wiring.py` — **new file** (does not exist yet): create wiring test for ll-doctor coverage across updated docs [Agent 3 finding]

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/__init__.py` — already re-exports `CapabilityEntry`, `CapabilityReport`, `HookEntry`, `apply_host_cli_from_config` in `__all__`; no edit needed for FEAT-1504 scope (confirmed complete)
- `scripts/little_loops/host_runner.py` — already has correct `__all__`; no edit needed (confirmed complete)
- `scripts/little_loops/cli/__init__.py` — will need `main_doctor` import and `__all__` addition when `doctor.py` is created; **owned by FEAT-1503/FEAT-1524**, not this issue
- `scripts/pyproject.toml` — will need `ll-doctor = "little_loops.cli:main_doctor"` in `[project.scripts]`; **owned by FEAT-1503/FEAT-1524**, not this issue

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1504_doc_wiring.py` — **new test file needed** following the established 28-file `test_feat<NNNN>_doc_wiring.py` convention; should assert `ll-doctor` appears in `commands/help.md`, `docs/reference/CLI.md`, `.claude/CLAUDE.md`, `skills/configure/areas.md`, `skills/init/SKILL.md`, `docs/reference/HOST_COMPATIBILITY.md`. Pattern to follow: `test_ll_logs_wiring.py` (CLI tool with help.md + init + configure wiring). Add to the test run in step 13.
- `scripts/tests/test_host_runner.py` — existing coverage for `CapabilityReport`, `CapabilityEntry`, `describe_capabilities` in `TestCapabilityReport` and `TestDescribeCapabilities`; no changes needed
- `scripts/tests/test_action.py` — existing coverage for `CapabilityReport` via `cmd_capabilities()`; no changes needed
- Note: `HookEntry` has zero direct unit-test coverage (only `report.hooks == []` in `TestCapabilityReport.test_capability_report_defaults`); FEAT-1504's wiring test only needs the doc assertion, not a new unit test

Anchor references from parent issue (Agent 2 findings):
- `README.md:46` — `"23 typed CLI tools"` (verify before editing)
- `README.md:164` — `"24 CLI tools"` (verify before editing)
- `commands/help.md` — `CLI TOOLS` block
- `skills/configure/areas.md` — `"Authorize all 21"` enumeration
- `skills/init/SKILL.md` — bash permissions block
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` asserts count strings
- `scripts/tests/test_feat1462_doc_wiring.py` — `TestApiMdWiring`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified current strings (confirmed exact values):**
- `README.md:46` — exact string: `"23 typed CLI tools"` → target: `"24 typed CLI tools"`
- `README.md:164` — exact string: `"24 CLI tools"` → target: `"25 CLI tools"` (note: the two README counts are already inconsistent with each other — both need incrementing)
- `skills/configure/areas.md:823` — exact string: `"Authorize all 21 ll- CLI tools and handoff write: ll-action, ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, ll-gitignore, ll-migrate, ll-migrate-relationships, ll-create-extension, ll-learning-tests, ll-logs, ll-generate-skill-descriptions, ll-adapt-skills-for-codex, Write(.ll/ll-continue-prompt.md)"` → change count to 22, add `ll-doctor` after `ll-adapt-skills-for-codex`

**`skills/init/SKILL.md` — three locations to update (not just the permissions block):**
- Lines 502–519: `Bash(ll-*:*)` permissions block (17 entries) — add `"Bash(ll-doctor:*)"`
- Lines 564–583: Step 11 "append" variant of the CLAUDE.md template — add `ll-doctor` bullet
- Lines 601–613: Step 11 "create" variant of the CLAUDE.md template — add `ll-doctor` bullet

**`docs/ARCHITECTURE.md` is already up to date — skip it:**
- The `## Host Runner Layer` component table (line 551) already documents `CapabilityReport`, `CapabilityEntry`, `HookEntry`, and explicitly names `ll-doctor` as the consumer. No edits needed.

**Third test file requiring a count bump (not in original issue):**
- `scripts/tests/test_ll_logs_wiring.py:45` — `TestConfigureAreasWiring.test_authorize_all_count_is_17` asserts `"Authorize all 21"` → change to `"Authorize all 22"`

**All exact assertion strings to change in `test_create_extension_wiring.py`:**
- Line 57 (`test_count_updated_to_17`): `assert "Authorize all 21"` → `"Authorize all 22"`
- Line 79 (`test_readme_tool_count_is_20`): `assert "23 typed CLI tools"` → `"24 typed CLI tools"`
- Line 192 (`test_readme_tool_count_is_20`): `assert "23 typed CLI tools"` → `"24 typed CLI tools"`
- Line 196 (`test_configure_areas_count_is_17`): `assert "Authorize all 21"` → `"Authorize all 22"`

**New test methods to add to `TestApiMdWiring` in `test_feat1462_doc_wiring.py`:**
```python
def test_capability_report_documented(self) -> None:
    assert "CapabilityReport" in content

def test_capability_entry_documented(self) -> None:
    assert "CapabilityEntry" in content

def test_hook_entry_documented(self) -> None:
    assert "HookEntry" in content

def test_describe_capabilities_documented(self) -> None:
    assert "describe_capabilities" in content
```

**`docs/reference/API.md` import code block (lines 5695–5703) — not explicitly called out in original scope:**
- The `from little_loops.host_runner import (...)` code example lists only: `CapabilityNotSupported`, `HostCapabilities`, `HostInvocation`, `HostNotConfigured`, `HostRunner`, `resolve_host`. It is missing `CapabilityEntry`, `CapabilityReport`, `HookEntry`, `apply_host_cli_from_config`. Update this block alongside the `__all__` line (step 7) to keep the usage example consistent with the symbol table additions. [Agent 2 finding]

**`docs/reference/CLI.md` — model section location:**
- `### ll-action` spans lines 33–89 under `## Skill Invocation`; has subcommands `#### invoke`, `#### capabilities`, `#### list`
- Add `### ll-doctor` in a new `## Diagnostics` section (or append after `## Skill Invocation`) — does not belong under `## Issue Processing` (that's for `ll-auto`, `ll-parallel`, etc.)

**`docs/reference/API.md` — two locations to update in `## little_loops.host_runner` (lines 5691–5834):**
- `__all__` listing at line 5706 is stale — missing `CapabilityEntry`, `CapabilityReport`, `HookEntry`, `apply_host_cli_from_config`
- `HostRunner` Protocol listing at lines 5759–5772 omits `describe_capabilities()` — add it
- Add symbol table entries for `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()`, `apply_host_cli_from_config()`

**Data model signatures (from `host_runner.py` lines 106–144, all already implemented):**
- `CapabilityEntry(name: str, status: Literal["full","partial","unsupported"], note: str = "")` — frozen dataclass (line 106)
- `HookEntry(name: str, status: Literal["installed","registered","deferred","absent"], note: str = "")` — frozen dataclass (line 119)
- `CapabilityReport(host: str, binary: str, version: str, capabilities: list[CapabilityEntry], hooks: list[HookEntry])` — frozen dataclass (line 130)
- `describe_capabilities() -> CapabilityReport` — Protocol method (line 202), implemented in all four runners

## Impact

- **Priority**: P4 — Cosmetic/discoverability and test-greenness, not user-blocking. Becomes effectively P2 the moment FEAT-1523/FEAT-1503 land because the wiring tests will fail without it; that lockstep is what motivates bundling.
- **Effort**: Small — All edits are string substitutions or single-line additions across ~11 known files; no new code paths or design decisions.
- **Risk**: Low — No runtime code changes; failure mode is a red wiring test, which surfaces immediately on `pytest`.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/CLI.md` — target location for the new `### ll-doctor` section (model after `### ll-action`).
- `docs/reference/API.md` § `little_loops.host_runner` — symbol table to extend.
- `docs/ARCHITECTURE.md` § `Host CLI Abstraction` — symbol table to extend.
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link target.
- `.claude/CLAUDE.md` § `CLI Tools` — list to extend.
- Parent: FEAT-1496 (host-capability preflight); siblings: FEAT-1523, FEAT-1503.

## Session Log
- `/ll:ready-issue` - 2026-05-16T17:23:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a9680c6-2120-4081-a81e-5791f4995480.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2518977a-4e9e-4286-8dc8-8e511a668f16.jsonl`
- `/ll:wire-issue` - 2026-05-16T17:19:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fba1b70-3600-48bf-8074-93d926bd2132.jsonl`
- `/ll:refine-issue` - 2026-05-16T17:13:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f2a8206-a627-4684-bd7e-f021a0e6de2e.jsonl`
- `/ll:format-issue` - 2026-05-16T15:15:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9fd0d0fa-5b4e-41d5-9893-56163f3cc33e.jsonl`
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P4
