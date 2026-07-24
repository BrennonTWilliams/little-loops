---
id: BUG-2760
type: bug
priority: P3
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
---

# BUG-2760: CapabilityReport.hooks never populated — ll-doctor Hooks section is dead

## Summary

`ll-doctor` renders a "Hooks" section from `CapabilityReport.hooks`, but no
`HostRunner` implementation ever populates that list — `HookEntry(...)` is
constructed only inside `scripts/tests/test_cli_doctor.py`. The section
therefore never prints for any real host, while
`docs/reference/HOST_COMPATIBILITY.md:312` explicitly promises a report with one
entry "per registered hook event."

## Steps to Reproduce

1. Run `ll-doctor` (or `ll-doctor --json`) on any host.
2. Observe no `Hooks` section appears in the output; the JSON `hooks` array is empty.
3. `grep -rn "HookEntry(" scripts/` returns matches only in
   `scripts/tests/test_cli_doctor.py`.

## Current Behavior

- `HookEntry` dataclass and the `hooks` field exist and are exported.
- `_print_report` in `scripts/little_loops/cli/doctor.py` has a fully-implemented
  rendering branch for hooks that is unreachable in practice.
- The `"installed" | "registered" | "deferred" | "absent"` statuses in
  `_STATUS_SYMBOLS` exist solely to serve that dead branch.
- Docs advertise per-hook status output that users never see.

## Expected Behavior

Either:
- **(a)** Each runner populates `hooks` with the real installation status of the
  hook intents it supports, so `ll-doctor` reports hook wiring; or
- **(b)** The `hooks` field, its rendering branch, its status symbols, and the
  documentation claim are removed together.

(a) is the more useful outcome given the hook surface has grown substantially
since the field was introduced — `hooks/hooks.json`, the per-host adapters under
`hooks/adapters/{claude-code,opencode,codex}/`, and the host-agnostic Python
handlers under `scripts/little_loops/hooks/` dispatched by `main_hooks()`.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: every `describe_capabilities()` implementation
- **Cause**: `CapabilityReport.hooks` defaults to an empty list
  (`field(default_factory=list)`) and no runner overrides it. The consumer side
  was built (FEAT-1496/1503/1524 chain) but the producer side never landed, and
  no test asserts a non-empty `hooks` list for a real runner — the only coverage
  constructs `HookEntry` by hand.

## Motivation

Hook misconfiguration is a common, hard-to-diagnose failure mode (a hook that
silently never fires looks identical to a feature that does not exist).
`ll-doctor` is the natural place to surface it, and the data model for doing so
already ships — it is just never filled in. Meanwhile the documentation makes a
promise the tool does not keep, which erodes trust in the rest of the report.

## Proposed Solution

If pursuing (a): derive hook status per host by reading the host's registered
hook configuration and cross-checking against ll's own hook inventory —
`hooks/hooks.json` plus the adapter directory for the active host — mapping each
declared intent to `installed` / `registered` / `deferred` / `absent`. The
existing `_USAGE` intent list in `scripts/little_loops/hooks/__init__.py` is the
canonical intent enumeration to check against. Hosts with no hook mechanism
should report `absent` (or return an empty list and have `_print_report` skip
the section for them) rather than silently omitting the section everywhere.

If pursuing (b): delete `HookEntry`, the `hooks` field, the `_print_report`
branch, the four hook-only `_STATUS_SYMBOLS` entries, the test that constructs
them, and the `HOST_COMPATIBILITY.md` sentence.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `HookEntry`, `CapabilityReport`, each `describe_capabilities()`
- `scripts/little_loops/cli/doctor.py` — `_print_report`, `_STATUS_SYMBOLS`

### Dependent Files (Callers/Importers)
- `ll-action capabilities` — consumes the same `CapabilityReport`
- `scripts/little_loops/hooks/__init__.py` — `_USAGE` intent list (see the
  dispatch-table note: it is a static list requiring manual update)

### Similar Patterns
- `hooks/hooks.json` and `hooks/adapters/*/` — the actual hook inventory to check against

### Tests
- `scripts/tests/test_cli_doctor.py` (currently the only `HookEntry` construction site)
- `scripts/tests/test_host_runner.py`

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:312` — the unfulfilled per-hook claim
- `docs/reference/API.md` — `CapabilityReport` / `HookEntry` entries (~line 8732)

### Configuration
- `hooks/hooks.json`

## Implementation Steps

1. Decide (a) populate vs. (b) remove; if (a), settle what each of the four
   statuses means for a hook intent.
2. Implement the producer side (or the removal) across all six runners.
3. Add a test asserting the real runner report matches the on-disk hook
   inventory — not a hand-built `HookEntry` fixture.
4. Reconcile `HOST_COMPATIBILITY.md` and `API.md` with actual behavior.

## Impact

- **Priority**: P3 - No incorrect output today, but a documented feature is
  entirely absent and dead code is accumulating around it.
- **Effort**: Medium if populating (needs a per-host hook-inventory probe);
  Small if removing.
- **Risk**: Low - Additive to the report, or a pure deletion of unreachable code.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Makes the per-hook reporting claim |
| `docs/reference/API.md#capabilityreport` | `HookEntry` / `CapabilityReport` model |
| `docs/ARCHITECTURE.md` | `CapabilityReport` row (~line 875) |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3
