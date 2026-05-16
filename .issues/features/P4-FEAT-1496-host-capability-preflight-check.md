---
id: FEAT-1496
type: FEAT
priority: P4
status: open
captured_at: "2026-05-16T13:04:12Z"
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by: [FEAT-1493]
labels: [captured, codex, host-compat, preflight, ux]
---

# FEAT-1496: Host-capability preflight check (`ll-doctor`)

## Summary

Add a preflight/diagnostic command — tentatively `ll-doctor` — that probes the currently selected host CLI (`LL_HOST_CLI` or `orchestration.host_cli`) and reports which ll capabilities will work, which will degrade silently, and which will outright fail. Today, `CapabilityNotSupported` warnings only fire mid-orchestration when a feature is invoked (`scripts/little_loops/host_runner.py:319,326`), surfacing too late.

## Current Behavior

`CodexRunner.build_streaming` emits `CapabilityNotSupported` to stderr when callers pass `agent=` or `tools=`, but only at the moment the invocation runs. A user kicking off a long `ll-parallel` run discovers degraded behavior 20 minutes in. There is no upfront `ll <something> --check` that says "here's what your host can and cannot do."

## Expected Behavior

Running `ll-doctor` (or `ll <subcommand> --preflight`) prints a table per active host:

```
Host: codex (resolved from LL_HOST_CLI)
Binary: /opt/homebrew/bin/codex  (version 0.5.x)

✓ build_streaming                        full
✓ build_blocking_json                    NDJSON only — `json_schema` unsupported
✓ build_detached                         full
✓ build_version_check                    full
✗ --agent (persona selection)            CapabilityNotSupported — silently dropped
✗ --tools (tool allowlist)               CapabilityNotSupported — sandbox modes only
✓ Hook: session_start                    installed
✓ Hook: pre_compact                      installed
✓ Hook: user_prompt_submit               installed
✓ Hook: post_tool_use                    installed (fire-and-forget, 5s)
○ Hook: pre_tool_use                     handler registered, NOT wired (opt-in)
○ Hook: stop                             deferred (no consumer)
```

Plus exit code 0 if everything required for the configured workflows is present; 1 if a critical capability is missing.

## Motivation

The Codex audit identified that several capability gaps degrade silently. Surfacing them upfront via a single command:

1. Saves users from discovering gaps mid-run (long `ll-parallel` or `ll-sprint` invocations)
2. Provides a single command for issue reports ("what does `ll-doctor` say?")
3. Documents host parity in a runnable form — the table stays in sync with the actual `HostRunner` implementations, unlike `HOST_COMPATIBILITY.md` which can drift

## Proposed Solution

1. Add a `CapabilityReport` dataclass alongside `HostInvocation` in `scripts/little_loops/host_runner.py`
2. Each `HostRunner` (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PiRunner`) implements `describe_capabilities() -> CapabilityReport` enumerating supported features
3. New CLI tool `ll-doctor` (`scripts/little_loops/cli/doctor.py`) prints the report for the resolved host, plus hook-installation status (read from the host adapter's expected install path)
4. Hook discovery: walk the resolved host's adapter dir (`hooks/adapters/<host>/`) and check whether each shim is referenced in the host's installed `hooks.json`

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `CapabilityReport` + `describe_capabilities()` on each runner
- `scripts/pyproject.toml` — register `ll-doctor` entry point

### Files to Create
- `scripts/little_loops/cli/doctor.py` — the CLI tool

### Dependent Files (Callers/Importers)
- `.claude/CLAUDE.md` — document `ll-doctor` in CLI Tools section
- `docs/reference/HOST_COMPATIBILITY.md` — cross-link

### Tests
- `scripts/tests/test_doctor.py` — verify report shape for each host
- Verify report matches the actual `CapabilityNotSupported` warnings emitted by runner methods

## Implementation Steps

1. Define `CapabilityReport` dataclass and the capability namespace (streaming, blocking_json, detached, version_check, agent_select, tool_allowlist, hooks-by-intent)
2. Implement `describe_capabilities()` on each `HostRunner`
3. Author `cli/doctor.py` — resolve host, print report, exit-code reflects critical gaps
4. Register `ll-doctor` entry point
5. Add tests asserting the report shape and key capability values per host
6. Update CLAUDE.md and HOST_COMPATIBILITY.md

## Impact

- **Priority**: P4 — UX improvement, not blocking
- **Effort**: Medium — touches all four host runners and adds a new CLI
- **Risk**: Low — Read-only diagnostic
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Current source of capability info; `ll-doctor` complements it |
| `.claude/CLAUDE.md` | Documents host CLI abstraction and `resolve_host()` |


## Blocks

- ENH-1495

## Labels

`feat`, `captured`, `codex`, `host-compat`, `preflight`, `ux`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
