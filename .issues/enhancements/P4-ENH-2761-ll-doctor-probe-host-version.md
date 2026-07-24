---
id: ENH-2761
type: enhancement
priority: P4
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
---

# ENH-2761: ll-doctor never probes the host binary version

## Summary

`ll-doctor` always prints `Binary:  claude  (unknown)`. Every
`describe_capabilities()` implementation hardcodes `version=""`, and
`_print_report` falls back to `"(unknown)"`. Meanwhile `build_version_check()`
exists on the `HostRunner` protocol with no production callers — the probe was
built but never wired into the report.

## Current Behavior

- `CapabilityReport.version` is always `""` for every host.
- Human output shows `(unknown)`; `--json` emits `"version": "(unknown)"`.
- `build_version_check()` is dead in production code.

## Expected Behavior

`ll-doctor` invokes the host's version check and reports the real version
string, degrading to `(unknown)` only when the binary is absent, the probe
fails, or it times out — not unconditionally.

## Motivation

Capability support is version-dependent (the `--json-schema` flag behind
ENH-2627 is exactly such a case). Without a version in the report, a capability
table is unverifiable and bug reports arrive with no way to tell which host
build produced them. The probe already exists; only the wiring is missing.

## Scope Boundaries

**In scope**: calling `build_version_check()` from the report path, parsing the
output into `CapabilityReport.version`, and handling absent-binary / failure /
timeout cases.

**Out of scope**: gating individual capability statuses on the detected version
(worth doing, but a separate decision with its own compatibility matrix), and
adding version checks to any caller other than the capability-report path.

## API/Interface

```python
# CapabilityReport.version becomes a real value rather than ""
# describe_capabilities() (or ll-doctor) invokes:
inv = runner.build_version_check()
# run inv.binary + inv.args, capture stdout, timeout-bounded, never raise
```

Note the design decision to settle: probe inside each `describe_capabilities()`
(keeps runners self-describing, but makes the method perform I/O) versus probe
once in `main_doctor` and stamp the field (keeps `describe_capabilities()` pure).
The latter is likely preferable since `ll-action capabilities` also consumes the
report and may not want the subprocess cost.

## Proposed Solution

Probe in the CLI layer, not in `describe_capabilities()`: after
`runner.describe_capabilities()` returns, run the version check with a short
timeout and produce an updated report with the version filled in. `detect()`
already tells you whether the binary exists, so skip the probe entirely when it
does not. Swallow all probe failures into `(unknown)` — a doctor command must
never crash on a diagnostic sub-step.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — `main_doctor` / `_print_report`
- `scripts/little_loops/host_runner.py` — if the probe lands in the runners instead

### Dependent Files (Callers/Importers)
- `ll-action capabilities` — shares `CapabilityReport`; confirm it tolerates a
  populated version and does not newly pay a subprocess cost

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py` — existing timeout-bounded subprocess helpers to reuse

### Tests
- `scripts/tests/test_cli_doctor.py` — assert version rendering for present, absent, and failing binaries
- `scripts/tests/test_host_runner.py` — `build_version_check` argv snapshots

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~line 308) — sample output
- `docs/reference/CLI.md:228` — `ll-doctor` section

### Configuration
- N/A

## Implementation Steps

1. Decide probe location (CLI layer preferred); confirm `CapabilityReport` is
   frozen and whether `replace()` or a mutable field is needed.
2. Wire the probe with a short timeout and total failure containment.
3. Cover present / absent / failing / timing-out binary in tests.
4. Refresh the sample output in the docs.

## Impact

- **Priority**: P4 - Diagnostic quality-of-life; nothing is incorrect today, just
  uninformative.
- **Effort**: Small - The probe builder already exists; this is wiring plus tests.
- **Risk**: Low - Additive; the main hazard is a slow or hanging host binary,
  mitigated by the timeout and by containing all failures to `(unknown)`.
- **Breaking Change**: No — but `--json` consumers pinned to the literal
  `"(unknown)"` would start seeing real values.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Sample `ll-doctor` output |
| `docs/reference/API.md#little_loopshost_runner` | `build_version_check` contract |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
