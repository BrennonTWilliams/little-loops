---
id: ENH-1015
type: ENH
priority: P2
status: active
title: "Document `agent:` and `tools:` fields in docs/reference/API.md"
discovered_date: 2026-04-09
discovered_by: issue-size-review
parent_issue: ENH-1014
confidence_score: 95
outcome_confidence: 85
testable: false
---

# ENH-1015: Document `agent:` and `tools:` fields in docs/reference/API.md

## Summary

Add `agent:` and `tools:` state-level field documentation to `docs/reference/API.md` at three locations: the `StateConfig` dataclass block, the `ActionRunner` Protocol `run()` signature, and the `run_claude_command` function signature. Decomposed from ENH-1014.

## Parent Issue

Decomposed from ENH-1014: "Document `agent:` and `tools:` in API.md and create-loop wizard reference"

## Current Behavior

The `agent:` and `tools:` state-level fields (added by FEAT-1011 to `StateConfig`) are not documented in `docs/reference/API.md`. Programmatic users reading the API reference have no documentation for these fields.

## Expected Behavior

`docs/reference/API.md` documents `agent:` and `tools:` in three locations:
1. `StateConfig` dataclass block — two field entries
2. `ActionRunner` Protocol `run()` signature — two additional parameters
3. `run_claude_command` function signature — two parameters + two bullet entries in Parameters list

## Motivation

This documentation enhancement would:
- **Close a discoverability gap**: `agent:` and `tools:` fields added by FEAT-1011 are invisible to programmatic users relying on `docs/reference/API.md` — discovery requires reading source code
- **Enable correct API usage**: Users building loops via the Python API need documented `StateConfig`, `ActionRunner.run()`, and `run_claude_command()` signatures to use these fields with correct types (`str | None`, `list[str] | None`)
- **Complete the FEAT-1011 rollout**: Implementation landed without corresponding API reference updates; this closes the documentation debt before the next release

## Implementation Steps

### Location 1: `StateConfig` dataclass block (lines 3766–3786)

Insert these two lines **before the closing ` ``` ` on line 3786**:
```python
    agent: str | None = None           # Claude agent model override for this state (prompt action_type only)
    tools: list[str] | None = None     # Restrict available tools for this state (prompt action_type only)
```

Current last field for reference: `context_passthrough: bool = False  # Pass parent context vars to child; merge child captures back`

### Location 2: `ActionRunner` Protocol `run()` signature (lines 4044–4057)

Insert these two lines **before `    ) -> ActionResult: ...`** (approximately line 4054):
```python
        agent: str | None = None,
        tools: list[str] | None = None,
```

Current last parameter for reference ends with `on_output_line: Callable[[str], None] | None = None,`

### Location 3: `run_claude_command` function signature (lines 1923–1942)

Add `agent` and `tools` to the documented signature **before the closing `)` on approximately line 1931**:
```python
    agent: str | None = None,
    tools: list[str] | None = None,
```

Add two bullets to the `**Parameters:**` list:
```
- `agent` - Claude agent model override; appended as `--agent <value>` to CLI invocation
- `tools` - Restrict available tools; appended as `--tools <value>` to CLI invocation
```

> **Pre-existing divergence note:** The current API.md `run_claude_command` block documents a signature that does NOT match the actual implementation at `scripts/little_loops/subprocess_utils.py:62–71`. ENH-1015 should add `agent` and `tools` to the documented signature, but reconciling the full signature divergence is out of scope.

## Scope Boundaries

- **In scope**: `docs/reference/API.md` only (3 locations)
- **Out of scope**: `skills/create-loop/reference.md` (covered by ENH-1016), LOOPS_GUIDE.md, generalized-fsm-loop.md, CLI.md (covered by ENH-1013)

## Integration Map

### Files to Modify
- `docs/reference/API.md`:
  - Lines 3766–3786: `StateConfig` dataclass block (add two field lines)
  - Lines 4044–4057: `ActionRunner` Protocol `run()` signature (add two parameters)
  - Lines 1923–1942: `run_claude_command` signature block (add `agent`/`tools` params + bullets)

### Dependent Files (Callers/Importers)
- N/A — `docs/reference/API.md` is a reference document, not imported by code

### Similar Patterns
- ENH-1016 follows the same doc-addition pattern for `skills/create-loop/reference.md`

### Tests
- N/A — no automated tests for doc content; validate with `ll-verify-docs` and `ll-check-links`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py:43–52` — `MockActionRunner.run()` test mock will need updating when FEAT-1011 adds `agent`/`tools` params to `ActionRunner.run()` Protocol; its signature already omits `on_output_line` (pre-existing gap); should be updated alongside FEAT-1011
- `scripts/tests/test_fsm_schema.py:1626–1712` — `TestSubLoopStateConfig` is the established 6-test pattern (constructor, default, `to_dict` include/omit, `from_dict` with/without) for new `StateConfig` field tests; follow when writing tests for `agent`/`tools` fields in FEAT-1011

### Documentation
- N/A — this issue IS the documentation update

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md:538` — documents `MockActionRunner.run()` with an already-incomplete signature (missing `on_output_line`); will further diverge from the Protocol once ENH-1015 adds `agent`/`tools` to the `ActionRunner` `run()` documentation — consider updating this example alongside FEAT-1011 (out of scope for ENH-1015 alone)

### Configuration
- N/A

### Dependency
- Should be implemented after FEAT-1011 lands, or in the same PR

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-04-09):_

**FEAT-1011 implementation status (as of this writing):**
- `StateConfig` in `scripts/little_loops/fsm/schema.py:179-231` ends with `context_passthrough: bool = False` — `agent` and `tools` fields are NOT yet present. This issue is a pre-implementation documentation task to be applied when FEAT-1011 lands.
- `ActionRunner.run()` in `scripts/little_loops/fsm/runners.py:31-37` has signature `(self, action, timeout, is_slash_command, on_output_line)` — no `agent`/`tools` yet.

**Line number accuracy (verified):**
- Location 1 (`StateConfig` block): `API.md:3766-3786` — confirmed ends with `context_passthrough` on line 3785, closing ` ``` ` on line 3786
- Location 2 (`ActionRunner Protocol`): `API.md:4044-4057` — confirmed `-> ActionResult: ...` closes on line 4054
- Location 3 (`run_claude_command`): `API.md:1923-1942` — confirmed signature starts line 1926, `**Parameters:**` list on lines 1936-1940

**`run_claude_command` divergence (confirmed):**
- API.md documents `(command, logger, timeout, stream_output)` but actual implementation at `scripts/little_loops/subprocess_utils.py:62` is `(command, timeout, working_dir, stream_callback, on_process_start, on_process_end, idle_timeout, on_model_detected)` — the pre-existing divergence note in the issue is accurate; out of scope for ENH-1015.

## Acceptance Criteria

- [ ] `docs/reference/API.md` `StateConfig` block includes `agent: str | None` and `tools: list[str] | None` fields
- [ ] `docs/reference/API.md` `ActionRunner` Protocol `run()` signature includes `agent` and `tools` parameters
- [ ] `docs/reference/API.md` `run_claude_command` block includes `agent`/`tools` params and two new `**Parameters:**` bullets

## Impact

- **Priority**: P2 — FEAT-1011 is implemented; documentation is needed to make the fields discoverable
- **Effort**: Small — 3 additive text insertions in a single file
- **Risk**: None — documentation-only; no runtime behavior affected
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `fsm`, `ll-loop`, `api`

## Related

- Sibling: ENH-1016 (create-loop reference.md)
- Parent: ENH-1014 (decomposed)
- Grandparent: ENH-1012
- Implementation: FEAT-1011

---

## Status

Active

## Session Log
- `/ll:confidence-check` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96c8bcc5-9d78-4121-b927-8e51c61d459e.jsonl`
- `/ll:wire-issue` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4edfc0f0-2b56-4ae6-bba0-6d90d78541f2.jsonl`
- `/ll:refine-issue` - 2026-04-09T15:54:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4edfc0f0-2b56-4ae6-bba0-6d90d78541f2.jsonl`
- `/ll:format-issue` - 2026-04-09T15:52:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48bbf93f-f03a-4c80-b15a-00732f7212f5.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a3e695e-d9fa-4fce-939c-e7bfcc83f05b.jsonl`
