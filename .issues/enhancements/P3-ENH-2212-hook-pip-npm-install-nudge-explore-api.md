---
id: ENH-2212
title: Hook on pip/npm install to nudge explore-api for new dependencies
type: enhancement
priority: P3
status: open
parent: EPIC-2207
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
- `/ll:format-issue` - 2026-06-18T19:32:41 - `ef0b05a4-a7e0-47d6-afa2-5f2b99558da6.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`
