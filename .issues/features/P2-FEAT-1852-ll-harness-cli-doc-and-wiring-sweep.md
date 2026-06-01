---
id: FEAT-1852
type: FEAT
title: ll-harness CLI — doc, wiring, and count correction sweep
priority: P2
status: open
parent: FEAT-1689
---

# FEAT-1852: ll-harness CLI — doc, wiring, and count correction sweep

## Summary

Update all documentation surfaces, plugin permissions, orchestration CLI tables, count assertions, and wiring verification tests for `ll-harness`. Requires FEAT-1851 (core implementation) to be merged first. This is a strict doc/config/test sweep — no implementation logic changes.

## Parent Issue

Decomposed from FEAT-1689: add ll-harness CLI for one-shot runner evaluation

## Prerequisite

**FEAT-1851 must be merged before this issue is worked.** Wiring tests (step 9, 13) verify presence of `ll-harness` in config files that step 7 modifies. E2E test (step 10) requires the binary to be installed.

## Implementation Steps

Implements steps 6, 7, 8, 9, 10, 11, 12, and 13 from the parent issue.

### Step 6: Doc-wiring sweep

Per the CONTRIBUTING.md checklist (lines 341-355):
- `docs/reference/CLI.md` — add full `### ll-harness` section
- `commands/help.md` — add one-line `ll-harness` entry in CLI TOOLS block (after line 273)
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list (currently lists 28 tools)
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` directory tree listing (line ~201)
- `CONTRIBUTING.md` — add `harness.py` to project structure tree (line ~186); follow checklist at lines 338-353 ("Documentation wiring for new CLI tools")
- `README.md` — `"30 typed CLI tools"` count (lines 46, 162) is **already current** — no increment needed

### Step 7: Permissions and init wiring

- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions block (after line 551) and both CLAUDE.md boilerplate blocks (lines ~600, ~633)
- `skills/configure/areas.md` — add `ll-harness` to allowed-tools enumeration (line 825) **AND** change `"Authorize all 27"` → `"Authorize all 28"` (see step 12 for count correction)

### Step 8: Orchestration CLI registration

- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` row to Orchestration CLI table (after line 141; table currently has 5 entries: ll-auto, ll-parallel, ll-action, ll-loop, FSM evaluators); update footnote count from "six" to "seven"
- `docs/codex/README.md` — add `ll-harness` to orchestration CLIs list (line 28)
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools parenthetical (line 7)

### Step 9: Wiring test

Add `TestFeat1689LlHarnessWiring` class to `scripts/tests/test_create_extension_wiring.py` verifying `ll-harness` presence in:
- `CLI_REFERENCE` (docs/reference/CLI.md)
- `HELP_MD` (commands/help.md)
- `CLAUDE_MD` (.claude/CLAUDE.md)
- `CONFIGURE_AREAS` (skills/configure/areas.md)
- `INIT_SKILL` (skills/init/SKILL.md)

Include INIT_SKILL assertions per the established pattern (`TestFeat1229LlActionWiring`, `TestFeat1526LlAdaptAgentsWiring`):
- `assert '"Bash(ll-harness:*)"' in INIT_SKILL.read_text()`
- `assert INIT_SKILL.read_text().count("ll-harness") >= 3`

### Step 10: E2E smoke test (optional, `@pytest.mark.integration`)

Add `ll-harness cmd "echo hello" --exit-code 0` to `scripts/tests/test_cli_e2e.py` following the `E2ETestFixture` pattern (base class at line 24).

### Step 11: Changelog

Add FEAT-1689 entry to `CHANGELOG.md` under the next release section.

### Step 12: Count assertion corrections

- `skills/configure/areas.md` line 825: change `"Authorize all 27"` → `"Authorize all 28"` AND append `ll-harness` to the named enumeration (coordinate with step 7)
- `scripts/tests/test_create_extension_wiring.py` lines 57 and 196: update assertion string `"Authorize all 27"` → `"Authorize all 28"`
- `scripts/tests/test_enh1846_doc_wiring.py` line 46: same update `"Authorize all 27"` → `"Authorize all 28"`

Note: `"30 typed CLI tools"` in `README.md` and test assertions (`test_create_extension_wiring.py` lines 79, 192; `test_enh1846_doc_wiring.py` line 66) do **not** need bumping — `ll-harness` was pre-counted when "30" was set.

### Step 13: Complete TestFeat1689LlHarnessWiring (wiring verification test)

The test class in step 9 must also include `test_enh1846_doc_wiring.py` coverage verification and the module docstring bullet (in `cli/__init__.py`, lines 1–33 — add `ll-harness` bullet; this is a distinct edit from the import after line 43 and the `__all__` entry at lines 68–102, both of which are done in FEAT-1851).

## Files to Modify

- `commands/help.md` — add `ll-harness` one-line entry
- `.claude/CLAUDE.md` — add `ll-harness` to CLI Tools list
- `docs/reference/CLI.md` — add `### ll-harness` section
- `docs/reference/HOST_COMPATIBILITY.md` — add `ll-harness` row + update footnote count
- `docs/codex/README.md` — add `ll-harness` to orchestration list
- `docs/codex/usage.md` — add `ll-harness` to orchestration tools
- `docs/ARCHITECTURE.md` — add `harness.py` to `cli/` tree
- `CONTRIBUTING.md` — add `harness.py` to project structure tree
- `CHANGELOG.md` — add FEAT-1689 entry
- `skills/init/SKILL.md` — add `"Bash(ll-harness:*)"` to permissions and boilerplate blocks
- `skills/configure/areas.md` — add `ll-harness` + change count to `"Authorize all 28"`
- `scripts/tests/test_create_extension_wiring.py` — add `TestFeat1689LlHarnessWiring`; update count assertions to `"Authorize all 28"`
- `scripts/tests/test_enh1846_doc_wiring.py` — update count assertion to `"Authorize all 28"`
- `scripts/tests/test_cli_e2e.py` — add `ll-harness cmd "echo hello"` E2E test (optional)
- `scripts/little_loops/cli/__init__.py` — add `ll-harness` bullet to module docstring (lines 1–33); this is the third distinct edit in this file (FEAT-1851 handles the import after line 43 and `__all__` at lines 68–102)

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1ebc34f-6a74-4ed8-b570-856978fc59ce.jsonl`

---

**Open** | Created: 2026-06-01 | Priority: P2
