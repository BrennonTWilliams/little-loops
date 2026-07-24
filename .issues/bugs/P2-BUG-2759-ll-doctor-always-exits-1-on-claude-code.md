---
id: BUG-2759
type: bug
priority: P2
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
---

# BUG-2759: ll-doctor always exits 1 on claude-code (contradictory json_schema entry)

## Summary

`ll-doctor` exits `1` on the primary host (`claude-code`) even when the host is
fully healthy. `ClaudeCodeRunner.describe_capabilities()` emits two capability
entries describing the *same* `--json-schema` flag with opposite verdicts:
`json_schema` is hardcoded `"unsupported"` while `structured_output` is
`"full"`. ENH-2627 added the second entry (and flipped
`HostCapabilities.structured_output=True`) but left the older, now-false
`json_schema` entry in place. Since `main_doctor` exits non-zero if *any*
capability is `"unsupported"`, the stale entry permanently poisons the exit
code.

## Steps to Reproduce

1. On a machine with the `claude` CLI installed, run `ll-doctor` from the repo root.
2. Observe the capability table shows both:
   - `✗  json_schema  claude CLI does not accept an inline schema flag; parameter is silently dropped`
   - `✓  structured_output  claude CLI honors an inline --json-schema flag; ...`
3. Run `ll-doctor >/dev/null 2>&1; echo $?` — prints `1`.

## Current Behavior

- Two mutually contradictory entries for one flag.
- Exit code `1` on a fully-supported host, so the documented health contract is
  broken. `docs/codex/usage.md:96` and `docs/reference/HOST_COMPATIBILITY.md:312`
  both treat "exits non-zero if any capability is unsupported" as the CI signal,
  which makes `ll-doctor` unusable as a preflight gate for claude-code.

## Expected Behavior

- One entry per real capability, agreeing with `HostCapabilities`.
- `ll-doctor` exits `0` on a healthy `claude-code` host.

## Root Cause

- **File**: `scripts/little_loops/host_runner.py`
- **Anchor**: `in ClaudeCodeRunner.describe_capabilities()`
- **Cause**: The `CapabilityEntry("json_schema", "unsupported", ...)` predates
  ENH-2627's `CapabilityEntry("structured_output", "full", ...)`. Both describe
  the inline `--json-schema` flag; only the newer one is accurate. Exit-code
  logic in `scripts/little_loops/cli/doctor.py` (`main_doctor`, final return)
  treats any `"unsupported"` as failure.

## Motivation

`ll-doctor` is the documented preflight/CI gate for host capability support and
is referenced from `docs/guides/LOOPS_GUIDE.md` as the check to run before
relying on `suppress_catalog` / `suppress_claude_md`. A gate that always fails
on the default host trains users and automation to ignore it, which defeats the
purpose of the whole capability-reporting layer.

## Proposed Solution

Preferred: delete the stale `json_schema` entry so `structured_output` is the
single source of truth for the flag.

Alternative if the `json_schema` name is load-bearing for a consumer (check
`ll-action capabilities` and `docs/reference/HOST_COMPATIBILITY.md` before
choosing): keep the name but correct its status to `"full"` and merge the notes,
retiring the redundant `structured_output` entry instead.

Either way, decide deliberately whether the two names are one capability or two —
the current state asserts both.

## Integration Map

### Files to Modify
- `scripts/little_loops/host_runner.py` — `ClaudeCodeRunner.describe_capabilities()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/doctor.py` — renders entries and derives the exit code
- `ll-action capabilities` path (see FEAT-1525 / FEAT-1503) — consumes the same report

### Similar Patterns
- `CodexRunner`, `OpenCodeRunner`, `PiRunner`, `GeminiRunner`, `OmpRunner`
  `describe_capabilities()` — check whether any carries the same stale
  `json_schema` entry alongside a newer `structured_output`.

### Tests
- `scripts/tests/test_cli_doctor.py`
- `scripts/tests/test_host_runner.py`

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (capability matrix, ~line 126 and 312)
- `docs/codex/usage.md:96` (exit-code note)

### Configuration
- N/A

## Implementation Steps

1. Confirm no consumer keys off the literal name `json_schema`; pick merge vs. delete.
2. Remove or correct the entry in `ClaudeCodeRunner.describe_capabilities()`;
   audit the other runners for the same duplication.
3. Update the capability matrix in `HOST_COMPATIBILITY.md`.
4. Add a regression test asserting `ll-doctor` exits `0` for a `claude-code`
   report with no genuinely-unsupported capabilities, and that no two entries
   describe the same flag with conflicting statuses.

## Impact

- **Priority**: P2 - The documented preflight/CI gate is permanently red on the
  default host; low fix cost, high signal-restoration value.
- **Effort**: Small - Delete/correct one entry plus test and doc updates.
- **Risk**: Low - Narrows a false-negative; the only behavior change is the exit
  code and one table row. Verify no CI/automation currently depends on the
  always-1 exit.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Capability matrix and exit-code contract |
| `docs/reference/API.md#capabilityreport` | `CapabilityReport` data model |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
