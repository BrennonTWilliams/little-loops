---
id: FEAT-1850
title: Add OmpRunner host runner for oh-my-pi (`omp` CLI)
type: feat
status: open
priority: P3
parent: EPIC-1713
captured_at: "2026-06-01T15:06:49Z"
discovered_date: 2026-06-01
discovered_by: capture-issue
labels: [feat, captured, host-compat, pi-adapter, omp]
relates_to: [EPIC-1713, FEAT-1480]
---

# FEAT-1850: Add OmpRunner host runner for oh-my-pi (`omp` CLI)

## Summary

Add `OmpRunner` to `scripts/little_loops/host_runner.py` to support the
[oh-my-pi](https://github.com/can1357/oh-my-pi) `omp` CLI as a first-class
ll host. oh-my-pi is an actively maintained fork of pi-mono with MCP support,
40+ providers, richer hook events, LSP/DAP, and subagent capabilities — making
it a higher-value parallel target alongside `PiRunner` (FEAT-1480).

## Current Behavior

`omp` is not in `_RUNNER_REGISTRY` or `_PROBE_ORDER`. Users with `omp` on PATH
get the fallback error: `"No supported host CLI found on PATH"`. `LL_HOST_CLI=omp`
is also unrecognized.

## Expected Behavior

- `omp` on PATH is auto-detected via `_PROBE_ORDER` and resolves to `OmpRunner`
- `LL_HOST_CLI=omp` (or `orchestration.host_cli: omp` in `.ll/ll-config.json`) works
- `ll-auto`, `ll-sprint`, `ll-loop`, `ll-action` all function against the `omp` binary
- `ll-doctor` reports `OmpRunner` capabilities for the active host

## Motivation

`PiRunner` (FEAT-1480) is a zero-implementation stub targeting vanilla `pi-mono`.
oh-my-pi (`omp`) is a superset fork with:
- **MCP support** — ll's MCP-dependent features work without workarounds
- **Richer hook events** — the EPIC-1713 parity gap (FEAT-1715) may be narrower
  than for vanilla pi-mono, making OmpRunner higher-value at lower integration cost
- **Active maintenance** — 9.3k stars, 754 forks, updated 2026-06-01

Since the Pi adapter is 0% implemented (no sunk cost), `OmpRunner` can be
developed in parallel without coordination overhead.

## Use Case

A user installs oh-my-pi (`bun install -g @oh-my-pi/pi-coding-agent`) and sets
`LL_HOST_CLI=omp`. They expect `ll-auto` and `ll-sprint` to fan out workloads
to `omp` exactly as they do to `claude` or `codex`. Without this issue, `omp`
is silently unrecognized.

## Acceptance Criteria

1. `omp` binary on PATH is auto-detected and `resolve_host()` returns an `OmpRunner` instance
2. `LL_HOST_CLI=omp` env var resolves to `OmpRunner` regardless of PATH state
3. `orchestration.host_cli: omp` in `.ll/ll-config.json` selects `OmpRunner`
4. `ll-auto`, `ll-sprint`, `ll-loop`, and `ll-action` complete at least one task against `omp` without fallback errors
5. `ll-doctor` reports `OmpRunner` capabilities when `omp` is the active host; `LL_HOST_CLI=omp ll-doctor` exits 0 with `omp` on PATH
6. `docs/reference/HOST_COMPATIBILITY.md` contains an `omp` column with correct capability values populated from the headless audit

## Proposed Solution

Follow the `CodexRunner` / `OpenCodeRunner` pattern in `host_runner.py`:

1. Add `OmpRunner` class implementing the `HostRunner` protocol
2. Register `"omp": OmpRunner` in `_RUNNER_REGISTRY`
3. Add `("omp", "omp")` to `_PROBE_ORDER` (after the `pi` entry)
4. Create `hooks/adapters/omp/` TypeScript adapter (parallel to the planned `hooks/adapters/pi/`)
5. Update `docs/reference/HOST_COMPATIBILITY.md` with an `omp` column

**Prerequisite**: Audit `omp --help` and its headless flag surface before
implementing `build_streaming` / `build_blocking_json` / `build_detached`.
`omp` uses a different binary name and may differ from `pi`'s flag conventions.
This audit overlaps with FEAT-1714 scope — coordinate or fold if convenient.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `OmpRunner` class; register in `_RUNNER_REGISTRY` and `_PROBE_ORDER`
- `docs/reference/HOST_COMPATIBILITY.md` — add `omp` column to capability matrix
- `docs/ARCHITECTURE.md` — add `OmpRunner` to the host runner component table

### New Files
- `hooks/adapters/omp/` — TypeScript hook adapter (parallel to planned `hooks/adapters/pi/`)
- `scripts/tests/test_omp_runner.py` — unit tests for `OmpRunner` (pattern: `test_codex_runner.py`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py:resolve_host()` — auto-picks up new entry via `_PROBE_ORDER`
- `ll-doctor` — reads `HostCapabilities` from `OmpRunner` for capability reporting
- Any file that calls `resolve_host()` benefits automatically

### Similar Patterns
- `CodexRunner` in `host_runner.py` — closest analogue (non-Claude headless runner)
- `OpenCodeRunner` stub — shows minimal required shape before full wiring
- `hooks/adapters/codex/` — reference TypeScript adapter to mirror for `omp`

### Tests
- `scripts/tests/test_omp_runner.py` — probe detection, `build_streaming`, `build_blocking_json`, `build_detached`, `HostCapabilities` fields
- Integration: `LL_HOST_CLI=omp ll-doctor` should exit 0 with `omp` binary present

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` — new `omp` column
- `docs/ARCHITECTURE.md` — `OmpRunner` entry in host-runner table

### Configuration
- `LL_HOST_CLI=omp` env var (handled by existing `resolve_host()` logic)
- `orchestration.host_cli: omp` in `.ll/ll-config.json`

## API/Interface

```python
class OmpRunner:
    """HostRunner for the oh-my-pi `omp` CLI (FEAT-1850)."""
    name = "omp"

    @staticmethod
    def is_available() -> bool:
        return shutil.which("omp") is not None

    def build_streaming(self, *, agent: str, prompt: str, ...) -> HostInvocation: ...
    def build_blocking_json(self, *, agent: str, prompt: str, ...) -> HostInvocation: ...
    def build_detached(self, *, prompt: str) -> HostInvocation: ...
```

`HostCapabilities` fields to determine during audit:
- `supports_streaming_json` — does `omp` emit streaming JSON like `claude --output-format stream-json`?
- `supports_permission_skip` — does `omp` have a bypass-approvals flag?
- `supports_agent_select` — does `omp --agent <name>` work?
- `supports_tool_allowlist` — does `omp` accept a tool-filter flag?
- `supports_session_resume` — does `omp --resume <id>` work?

## Implementation Steps

1. **Audit `omp` headless flag surface** — run `omp --help` / `omp run --help`; document the streaming, permission-skip, agent-select, tool-allowlist, and session-resume flags. Record findings in `thoughts/research/omp-headless-flags.md`.
2. **Stub `OmpRunner`** — add the class to `host_runner.py` with `HostNotConfigured` raises (same pattern as current `PiRunner`); register in `_RUNNER_REGISTRY` and `_PROBE_ORDER`.
3. **Wire `build_streaming`** — implement using audited headless flags; validate with `LL_HOST_CLI=omp ll-action`.
4. **Wire `build_blocking_json` and `build_detached`** — implement and test.
5. **Set `HostCapabilities`** — fill in the capability booleans from the audit.
6. **Create `hooks/adapters/omp/`** — TypeScript adapter translating omp hook events to `LLHookEvent`; mirror `hooks/adapters/codex/` structure.
7. **Audit hook event parity** — document which Claude Code hook events omp exposes; update EPIC-1713 / FEAT-1715 with findings.
8. **Tests** — add `scripts/tests/test_omp_runner.py` covering probe, all three `build_*` methods, and capability fields.
9. **Update docs** — `HOST_COMPATIBILITY.md` omp column; `ARCHITECTURE.md` component table.

## Impact

- **Priority**: P3 — valuable but not blocking; Pi adapter and Codex are already covered
- **Effort**: Medium — audit + implementation mirrors existing CodexRunner pattern; hook adapter is the bulk of the work
- **Risk**: Low — additive; no existing runner is modified
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/ARCHITECTURE.md` | Host runner component table; `OmpRunner` entry belongs here |
| `docs/reference/API.md` | `host_runner` module API; `OmpRunner` public interface documented here |
| `docs/reference/HOST_COMPATIBILITY.md` | Capability matrix; `omp` column is an exit criterion for this issue |

## Labels

`feat`, `captured`, `host-compat`, `pi-adapter`, `omp`

## Session Log
- `/ll:format-issue` - 2026-06-01T15:09:51 - `135049e3-c3b6-4e47-a1b7-f422e4bce835.jsonl`

- `/ll:capture-issue` - 2026-06-01T15:06:49Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

## Status

**Open** | Created: 2026-06-01 | Priority: P3
