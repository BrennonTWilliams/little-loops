---
id: ENH-2212
title: Hook on pip/npm install to nudge explore-api for new dependencies
type: enhancement
priority: P3
status: open
parent: EPIC-2207
relates_to: [ENH-2209]
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2212: Hook on pip/npm install to nudge explore-api for new dependencies

## Summary

When an agent or user runs `pip install <pkg>` or `npm install <pkg>`, nothing currently triggers a learning test check. Add a `PostToolUse` hook on Bash that detects install commands, extracts the package name, queries the registry, and nudges `/ll:explore-api` if no proven record exists. This is the highest-leverage injection point: the exact moment a new external dependency enters the project.

## Current Behavior

Currently, there is no hook or automated process that detects when a new Python or Node.js dependency is installed via `pip install`, `npm install`, or related package manager commands. When an agent or user installs a new package, the learning test registry is never consulted at that moment. This creates a gap where code may be written against unproven API surfaces without prior exploration via `/ll:explore-api`.

## Expected Behavior

When a `Bash` tool call contains a `pip install`, `pip3 install`, `uv add`, `poetry add`, `npm install`, `yarn add`, or `pnpm add` command, a `PostToolUse` hook should:

1. Detect the install command and extract the package name.
2. Normalize the package name (strip version specifiers and extras).
3. Query the learning test registry via `check_learning_test(pkg)`.
4. Emit a nudge message referencing `/ll:explore-api` if no proven record exists.
5. Emit nothing (silent pass) if a proven record already exists.

All behavior is gated behind `learning_tests.enabled` in config.

## Motivation

Install-time is cheap. Proof-later is expensive. A nudge at install time — before any code is written against the new package — costs nothing and prevents the entire pattern of writing code against unknown API surfaces.

## Scope Boundaries

- **In scope**: Detecting `pip install <pkg>`, `pip3 install <pkg>`, `uv add <pkg>`, `poetry add <pkg>`, `npm install <pkg>`, `yarn add <pkg>`, `pnpm add <pkg>`; extracting and normalizing package names; querying learning test registry; emitting nudge messages
- **Out of scope**: Blocking installs (nudge only, not a gate); `pip install -r requirements.txt` (too noisy, no single package name); transitive dependencies (only the explicitly installed package); existing or previously-installed dependencies (only new install invocations); configuration of `learning_tests.enabled` (already exists)

## Implementation Steps

1. Add a `PostToolUse` hook in `hooks/hooks.json` targeting Bash tool calls.
2. Implement `scripts/little_loops/hooks/install_learning_gate.py`.
3. Parse `tool_input.command` with regex patterns:
   - `pip install <pkg>`, `pip3 install <pkg>`, `pip install -r ...` (skip requirements files), `uv add <pkg>`, `poetry add <pkg>`
   - `npm install <pkg>`, `yarn add <pkg>`, `pnpm add <pkg>`
4. Normalize the package name (strip version specifiers: `>=`, `==`, `[extras]`).
5. Run `check_learning_test(pkg)` — if no proven record, emit: `[ll: new dependency] No learning test for "<pkg>". Consider: /ll:explore-api "<pkg>"`
6. If a proven record exists, emit nothing (silent pass).
7. Gate behind `learning_tests.enabled`.

## Integration Map

### Files to Modify
- `hooks/hooks.json` — Register PostToolUse hook for Bash tool calls
- `scripts/little_loops/hooks/install_learning_gate.py` — New hook handler for install detection and registry query

### Dependent Files (Callers/Importers)
- TBD — use grep to find callers of `check_learning_test()` in the learning test registry module

### Tests
- TBD — add tests for install command detection, package name normalization, and registry query

### Documentation
- TBD — document the hook feature and nudge behavior

### Configuration
- `.ll/ll-config.json` — `learning_tests.enabled` gate (existing config key)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2211 (debt marker) was cancelled per EPIC-2207 scoping review. This hook is now the sole PostToolUse detection path for unproven packages — no session-scoped cache coordination with a sibling hook is needed.

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2208 (stale-aware gate). The implementation must use the standalone `is_record_stale(record, stale_after_days)` helper that ENH-2208 exposes in `learning_tests_gate.py` (or `scripts/little_loops/learning_tests/gate.py`), rather than calling `check_learning_test()` directly. `check_learning_test()` returns registry status without date arithmetic — a date-old proven record would return "proven" and the nudge would be silently skipped. The correct call sequence is: (1) call `check_learning_test(pkg)` to get the record; (2) call `is_record_stale(record, lt_config.stale_after_days)` to determine effective staleness; (3) emit the nudge if no record exists or `is_record_stale` returns True. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2209 (refine-issue/wire-issue auto-population) both produce a proven/unproven summary message. Without a shared format, users see inconsistent phrasing depending on whether they encounter an unproven package via an install hook or via refine-issue. The nudge message format must be defined once in the shared gate utility (`scripts/little_loops/learning_tests/gate.py`) and used by both issues. See [[ENH-2209]].

## Acceptance Signals

- `Bash("pip install httpx")` triggers a nudge: "No learning test for 'httpx'..."
- `Bash("pip install requests")` where `requests` has a proven record emits nothing
- `Bash("pip install -r requirements.txt")` is skipped (too noisy, no single package name)
- Version specifiers stripped: `pip install anthropic>=0.20` → checks `anthropic`
- Extras stripped: `pip install "anthropic[bedrock]"` → checks `anthropic`

## Impact

- **Priority**: P3 — High-leverage automation that catches missing learning tests at the earliest possible moment, blocking the costliest pattern before any code is written
- **Effort**: Medium — New hook handler with regex parsing and registry query; existing hook infrastructure can be reused
- **Risk**: Low — Fully gated behind `learning_tests.enabled` config flag; nudge only, no blocking behavior; silent pass for proven records
- **Breaking Change**: No — Adds optional nudge behavior; existing workflows and install commands unaffected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `hooks`, `learning-tests`, `captured`

## Status

**Open** | Created: 2026-06-18 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-18T20:04:54 - `e8724251-0b1a-456e-af9e-59fd2df092b4.jsonl`
- `/ll:format-issue` - 2026-06-18T19:32:41 - `ef0b05a4-a7e0-47d6-afa2-5f2b99558da6.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
