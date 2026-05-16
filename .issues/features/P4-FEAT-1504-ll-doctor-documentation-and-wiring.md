---
id: FEAT-1504
type: FEAT
priority: P4
status: open
captured_at: '2026-05-16T15:07:07Z'
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
7. Update `docs/reference/API.md` `## little_loops.host_runner` section — add `CapabilityReport`, `CapabilityEntry`, `HookEntry`, `describe_capabilities()` to the symbol table.
8. Update `docs/ARCHITECTURE.md` `## Host CLI Abstraction` symbol table — add new dataclasses.
9. Update `.claude/CLAUDE.md` CLI Tools section — add `ll-doctor` line.
10. Update `docs/reference/HOST_COMPATIBILITY.md` — add a cross-reference paragraph pointing users to `ll-doctor` for a runnable capability check.
11. Update `scripts/tests/test_create_extension_wiring.py` — fix count assertions.
12. Verify or extend `scripts/tests/test_feat1462_doc_wiring.py` — ensure `TestApiMdWiring` asserts the presence of `CapabilityReport` and `describe_capabilities` in `API.md` and `ARCHITECTURE.md`.
13. Run: `python -m pytest scripts/tests/test_create_extension_wiring.py scripts/tests/test_feat1462_doc_wiring.py -v && ruff check scripts/`

## Files to Modify

- `README.md` — CLI tool count strings
- `commands/help.md` — `ll-doctor` entry
- `skills/configure/areas.md` — "Authorize all N" count
- `skills/init/SKILL.md` — permissions block
- `docs/reference/CLI.md` — new `### ll-doctor` section
- `docs/reference/API.md` — symbol table additions
- `docs/ARCHITECTURE.md` — symbol table additions
- `.claude/CLAUDE.md` — CLI Tools section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link
- `scripts/tests/test_create_extension_wiring.py` — count assertions
- `scripts/tests/test_feat1462_doc_wiring.py` — symbol coverage

## Integration Map

Anchor references from parent issue (Agent 2 findings):
- `README.md:46` — `"23 typed CLI tools"` (verify before editing)
- `README.md:164` — `"24 CLI tools"` (verify before editing)
- `commands/help.md` — `CLI TOOLS` block
- `skills/configure/areas.md` — `"Authorize all 21"` enumeration
- `skills/init/SKILL.md` — bash permissions block
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1229LlActionWiring.test_configure_areas_count_is_17` asserts count strings
- `scripts/tests/test_feat1462_doc_wiring.py` — `TestApiMdWiring`

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
- `/ll:format-issue` - 2026-05-16T15:15:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9fd0d0fa-5b4e-41d5-9893-56163f3cc33e.jsonl`
- `/ll:issue-size-review` - 2026-05-16T15:07:07Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b57cdb22-126d-4dc6-b12f-a5213e07e705.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P4
