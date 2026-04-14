---
discovered_commit: 99fd7bdaaa9bd05b09cba2b878c4d17a27ceaeb7
discovered_branch: main
discovered_date: 2026-04-12T00:00:00Z
discovered_by: audit-docs
doc_file: README.md
confidence_score: 95
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
---

# ENH-1093: Document undocumented CLI entry points (ll-generate-schemas, mcp-call)

## Summary

Documentation issue found by `/ll:audit-docs`.

`pyproject.toml` registers 16 CLI entry points but README.md documents only 14, claiming "14 CLI tools". Two entry points are undocumented: `ll-generate-schemas` and `mcp-call`.

## Location

- **File**: `README.md`
- **Line(s)**: 90
- **Section**: What's Included

## Current Content

```markdown
**14 CLI tools** (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`, etc.) for autonomous and parallel issue processing
```

## Problem

Two entry points installed via `pip install little-loops` are documented in `docs/reference/CLI.md` (lines 1074 and 1096 respectively) but are absent from README.md's "What's Included" summary and the README CLI tools section:

- **`ll-generate-schemas`** — Regenerates JSON Schema files for all `LLEvent` types into `docs/reference/schemas/`. Developer/maintainer build tool used when the event schema changes.
- **`mcp-call`** — CLI wrapper for calling MCP tools: `mcp-call server/tool-name '{"param": "value"}'`. Debugging/testing utility for MCP integrations.

The tools are discoverable via `docs/reference/CLI.md` (linked from README), but the README "14 CLI tools" count and the CLI section do not surface them. The question is whether README should acknowledge them or whether omitting internal/debug tools from README is intentional.

## Expected Content

Decision required (see Options):

**Option A — Document `ll-generate-schemas` in CONTRIBUTING.md** (recommended): It's a maintainer tool, not end-user facing. Move documentation there, leave README count at 14.

**Option B — Document both in README CLI section**: Add brief sections for each, bump count to 16.

**Option C — Leave undocumented**: Both are internal utilities; current 14-count is correct for user-facing tools.

## Impact

- **Severity**: Low (tools still work; just undiscoverable for users who notice them)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

## Session Log
- `/ll:wire-issue` - 2026-04-14T04:13:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bdd82526-543a-44f0-b343-dcd790e5f0b0.jsonl`
- `/ll:refine-issue` - 2026-04-14T04:06:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1d9eec7-9fed-4a0d-b665-ecc469834e45.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb32025b-1ca1-4d96-a7ab-c26226a21aaf.jsonl`

---

## Status

**Open** | Created: 2026-04-12 | Priority: P4

---

## Audit Update — 2026-04-13 (commit 4e5b8a97)

Re-audited by `/ll:audit-docs`. State has changed since this issue was created:

- README.md:92 now claims **"15 CLI tools"** (was "14 CLI tools" when issue was filed)
- `pyproject.toml` still registers **16 entry points** (unchanged)
- The count bump from 14→15 likely reflects `ll-create-extension` being added and counted; it does NOT resolve the two undocumented tools
- **`ll-generate-schemas`** — still undocumented in README CLI section; still uncounted (or silently absorbed into the 15 count)
- **`mcp-call`** — still undocumented in README CLI section; still uncounted

**Current discrepancy**: 16 actual entry points vs 15 claimed in README (1 off, not 2).

Options A/B/C from the original issue remain valid. Option A (document `ll-generate-schemas` in CONTRIBUTING.md and treat `mcp-call` as an internal debug tool, leave README count at 15) is still recommended if neither tool is intended for end users.

---

## Integration Map

### Files to Modify

Scope depends on which Option (A/B/C) is chosen:

**Option A (recommended — document `mcp-call` in CONTRIBUTING.md, keep README count at 15):**
- `CONTRIBUTING.md:553-563` — Add `mcp-call` documentation alongside the existing "Event Schema Maintenance" section (which already covers `ll-generate-schemas` inline)
- `.claude/CLAUDE.md:101-119` — CLI tools list omits both tools; add `ll-generate-schemas` (already counted in 15) to align list with count
- `skills/init/SKILL.md:484-504` and `skills/init/SKILL.md:508-530` — two inline CLAUDE.md boilerplate blocks written to target projects by `/ll:init`; currently list 14 tools, will diverge from `.claude/CLAUDE.md` if `ll-generate-schemas` is added there [wiring pass]
- `commands/help.md:216-231` — flat CLI TOOLS enumeration listing 14 tools; will diverge from `.claude/CLAUDE.md` if `ll-generate-schemas` is added there [wiring pass]
- No README count change; new regression tests needed (see Tests subsection below)

**Option B (document both in README, bump count to 16):**
- `README.md:90` — Bump `"15 CLI tools"` → `"16 CLI tools"`
- `README.md` (after line 466, CLI tools section) — Add `### ll-generate-schemas` and `### mcp-call` sections using the H3 + bash examples pattern from `README.md:256-267`
- `scripts/tests/test_create_extension_wiring.py:77-81` — Update hardcoded `"15 CLI tools"` assertion to `"16 CLI tools"`
- `.claude/CLAUDE.md:101-119` — Add both tools to the CLI list

**Option C (no change):**
- No files to modify

### Dependent Files (Tests / Assertions with Hardcoded Counts)
- `scripts/tests/test_create_extension_wiring.py:77-81` — Asserts `"15 CLI tools"` in `README.md`; **must update if count changes**
- `scripts/tests/test_create_extension_wiring.py:55-58` — Asserts `"Authorize all 14 ll-"` in `skills/configure/areas.md:793`; not affected by `mcp-call` (no `ll-` prefix) or by Option A

### Documentation Already Written (No Authoring Needed)
- `docs/reference/CLI.md:1077-1096` — Full docs for `ll-generate-schemas` (flags table, exit codes, examples, maintenance note)
- `docs/reference/CLI.md:1099-1118` — Full docs for `mcp-call` (arguments table, exit codes, examples)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — add new test asserting `"ll-generate-schemas"` appears in `.claude/CLAUDE.md` (no such test currently exists; follow the `.read_text()` pattern in the existing `TestFeat1045DocUpdates` class)
- `scripts/tests/test_create_extension_wiring.py` — add new test asserting `"mcp-call"` appears in `CONTRIBUTING.md` (no test currently asserts on real `CONTRIBUTING.md` content; follow same pattern)

### Related Issues
- `.issues/enhancements/P5-ENH-1025-mark-ll-generate-schemas-as-internal-dev-tooling.md` — Companion issue specifically about classifying `ll-generate-schemas` as internal tooling

---

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Current State Clarification (Critical)

The test at `scripts/tests/test_create_extension_wiring.py:77-81` reveals that the "15 CLI tools" count in `README.md:90` already **includes `ll-generate-schemas`** — the assertion comment reads: *"incremented from 14 after ll-generate-schemas landed"*. This reframes the problem:

- **`ll-generate-schemas`**: Already counted in the README "15" but has no dedicated section in the README CLI tools list — correctly absorbed into the count but intentionally unsurfaced as a user tool. Full docs at `docs/reference/CLI.md:1077-1096`. Already referenced in `CONTRIBUTING.md:553-563` under "Event Schema Maintenance."
- **`mcp-call`**: The truly uncounted tool (16th entry point vs 15 claimed). Zero presence in README or CONTRIBUTING.md. Full docs at `docs/reference/CLI.md:1099-1118`. Only entry point without an `ll-` prefix — convention further signals internal/debug status.

The actual discrepancy is **1 tool** (`mcp-call`), not 2. The core decision is whether to count and document `mcp-call` in README or treat it as a developer-internal utility excluded from the user-facing count.

### Tool Audience Analysis

**`ll-generate-schemas`** (`scripts/little_loops/cli/schemas.py:12`):
- Build-time maintainer tool — regenerates JSON Schema files for all 19 `LLEvent` types into `docs/reference/schemas/`
- Usage: `ll-generate-schemas` or `ll-generate-schemas --output path/to/dir/`
- Audience: contributors only; referenced exclusively in `CONTRIBUTING.md:553-563`

**`mcp-call`** (`scripts/little_loops/mcp_call.py:315`):
- CLI wrapper for calling MCP tools directly via JSON-RPC from a shell, without a full Claude Code session
- Usage: `mcp-call server/tool-name '{"param": "value"}'`
- Reads `.mcp.json` from cwd, spawns the MCP server subprocess, performs JSON-RPC handshake, returns result
- Audience: developers/debuggers; zero CONTRIBUTING.md presence

### areas.md Count (Secondary — Not Affected by mcp-call)

`skills/configure/areas.md:793` hardcodes `"14 ll- CLI tools"` (a permission group covering only `ll-`-prefixed tools). `mcp-call` has no `ll-` prefix so it would not be included regardless of README option chosen. Tested by `test_create_extension_wiring.py:55-58`.

---

## Implementation Steps

**Option A (recommended):**

1. Add `mcp-call` documentation to `CONTRIBUTING.md` — append a brief entry after the "Event Schema Maintenance" section (`CONTRIBUTING.md:563`) introducing `mcp-call` as a debug utility with usage and pointer to `docs/reference/CLI.md`
2. Update `.claude/CLAUDE.md:101-119` — add `ll-generate-schemas` to the CLI tools bullet list (it is counted in the README 15 but absent from CLAUDE.md's list of 14)
3. Verify no regressions: `python -m pytest scripts/tests/test_create_extension_wiring.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `skills/init/SKILL.md:484-504` — add `ll-generate-schemas` to the first inline CLAUDE.md boilerplate CLI list (currently 14 tools; must stay in sync with `.claude/CLAUDE.md`)
5. Update `skills/init/SKILL.md:508-530` — add `ll-generate-schemas` to the second inline CLAUDE.md boilerplate CLI list (duplicate block for the "no file exists" branch)
6. Update `commands/help.md:216-231` — add `ll-generate-schemas` to the CLI TOOLS enumeration (currently 14 tools)
7. Add regression tests to `scripts/tests/test_create_extension_wiring.py` — assert `"ll-generate-schemas"` appears in `.claude/CLAUDE.md` and `"mcp-call"` appears in `CONTRIBUTING.md`; follow the `TestFeat1045DocUpdates` `.read_text()` pattern

**Option B (if both tools should be user-visible):**

1. Update `README.md:90` — change `"15 CLI tools"` to `"16 CLI tools"`
2. Add tool sections to README after line 466 using the H3 pattern from `README.md:256-267`
3. Update `scripts/tests/test_create_extension_wiring.py:77` — change `"15 CLI tools"` assertion to `"16 CLI tools"`
4. Update `.claude/CLAUDE.md:101-119` — add both tools to the CLI list
5. Verify: `python -m pytest scripts/tests/test_create_extension_wiring.py -v`
