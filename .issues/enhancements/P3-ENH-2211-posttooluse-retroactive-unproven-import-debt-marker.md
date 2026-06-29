---
id: ENH-2211
title: PostToolUse retroactive unproven-import debt marker
type: enhancement
priority: P3
status: cancelled
parent: EPIC-2207
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2211: PostToolUse retroactive unproven-import debt marker

## Summary

When the `PreToolUse` discoverability gate emits a warn-mode nudge and the agent proceeds anyway (writing code that imports packages with no proven record), nothing creates a paper trail of the gap. Add a `PostToolUse` hook that fires after Write/Edit, detects the same unproven imports, and appends the missing targets to `learning_tests_required` in the in-progress issue's frontmatter — creating a concrete debt record even when the agent ignores the pre-write nudge.

## Current Behavior

When the `PreToolUse` discoverability gate is set to `warn` mode and the agent proceeds anyway (writing code that imports packages with no proven learning-test record), no paper trail tracks the gap. The agent writes code based on unverified assumptions, and the unproven status is silently lost after the session ends. This creates a blind spot where technical debt accumulates without visibility.

## Expected Behavior

A `PostToolUse` hook should fire after Write/Edit tool invocations, detect the same class of unproven imports that the pre-tool gate warned about, and append the missing targets to `learning_tests_required` in the in-progress issue's frontmatter. This creates a concrete debt record — even when the agent ignores the pre-write nudge — making the gap visible in `/ll:ready-issue` and downstream planning.

## Motivation

`warn` mode is useful because it doesn't block the agent. But it creates a silent failure mode: the agent writes code based on unverified assumptions and no issue tracks that those assumptions were never proven. The post-write hook closes this loop by making the debt explicit in the issue file.

## Implementation Steps

1. Add a new `PostToolUse` hook entry in `hooks/hooks.json` for Write/Edit tool names.
2. Implement `scripts/little_loops/hooks/learning_tests_debt_marker.py` using the same package extraction logic as `learning_tests_gate.py`.
3. Detect the currently in-progress issue ID (from `LL_ISSUE_ID` env var, context, or session state).
4. For each unproven package in the written file, add it to `learning_tests_required` in the issue frontmatter (append only, no duplicates).
5. Emit a single-line log: "[ll: debt recorded] Added unproven imports to learning_tests_required: <pkg1>, <pkg2>".
6. Only fire when `learning_tests.enabled: true` and `discoverability.mode` is `warn` (not `block`, since block prevents the write from happening).

## Scope Boundaries

- **In scope**: New `PostToolUse` hook for Write/Edit tool names; `scripts/little_loops/hooks/learning_tests_debt_marker.py` handler reusing existing package extraction logic from `learning_tests_gate.py`; append-only `learning_tests_required` frontmatter updates with no duplicate entries; single-line log output for each debt recorded event
- **Out of scope**: Modifying `learning_tests_gate.py` behavior; blocking the write operation (that's `block` mode for pre-tool); retroactive scanning of existing committed files; changing the `discoverability.mode` configuration schema; adding a new learning test from this hook

## Impact

- **Priority**: P3 - Important quality-of-life improvement for warn-mode workflows, but doesn't block existing functionality
- **Effort**: Medium - New hook handler leveraging existing package extraction logic and frontmatter utilities
- **Risk**: Low - Post-hoc debt recording only; no changes to existing write flows or discoverability gate behavior
- **Breaking Change**: No

## Acceptance Signals

- After ignoring a warn nudge and writing code importing `boto3`, the in-progress issue's `learning_tests_required` includes `boto3`
- Running `/ll:ready-issue` afterward surfaces the unproven gap
- Hook is a no-op when `LL_ISSUE_ID` is not set (non-automation context)
- No duplicate entries added on repeat writes to the same file

## Labels

- `enhancement`, `captured`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2212 (pip/npm install hook). Both add `PostToolUse` hooks detecting unproven packages. The debt marker handler must consult a session-scoped cache to skip packages already nudged by ENH-2212, preventing duplicate entries. ENH-2212 should be implemented first; this issue depends on that caching infrastructure.

Additionally, this issue writes to issue frontmatter (`learning_tests_required`) only — it does NOT create `LearningTestRecord` objects in the registry. ENH-2213 operates on registry records only. This separation is intentional: the debt marker records gaps in issue tracking; the verification loop verifies registry assertions. See [[ENH-2213]] for the registry-level verification.

## Cancellation Note

Cancelled per EPIC-2207 scoping review. This only fires in `warn` mode where the agent already saw the PreToolUse nudge and chose to proceed anyway. If debt recording matters, the PreToolUse gate itself should write to `learning_tests_required` when it fires — eliminating the need for a separate PostToolUse hook with its own session-scoped cache coordination with ENH-2212. See EPIC-2207 for rationale.

## Session Log
- `/ll:format-issue` - 2026-06-18T19:32:24 - `848f77db-a0fc-43be-8542-782afcbb1cd7.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P3
