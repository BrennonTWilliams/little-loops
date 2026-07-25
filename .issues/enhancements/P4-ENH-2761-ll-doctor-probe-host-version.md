---
id: ENH-2761
type: enhancement
priority: P4
status: done
captured_at: '2026-07-24T19:36:28Z'
completed_at: '2026-07-25T06:21:43Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 100
outcome_confidence: 96
score_complexity: 24
score_test_coverage: 24
score_ambiguity: 25
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The exact pattern to copy already exists and answers the "settle" question
  in this section.** `cmd_capabilities()` in `scripts/little_loops/cli/action.py:335-366`
  (the `ll-action capabilities` handler) already does precisely this: it calls
  `runner.describe_capabilities()` for `host`/`binary`/`capabilities`, checks
  `available = runner.detect()`, and only if available calls
  `invocation = runner.build_version_check()` then
  `subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)`,
  catching `(subprocess.TimeoutExpired, FileNotFoundError, OSError)` and
  falling back `available = False` / empty version on any failure. It never
  mutates `CapabilityReport` — it emits its own JSON blob combining
  `report.host`/`report.binary` with the freshly-probed version string. This
  confirms probing in the CLI layer (not inside the frozen, I/O-free
  `describe_capabilities()`) is not just preferable but already the
  established, working pattern for `ll-action`'s output — `ll-doctor` should
  match it rather than diverge with a different design.
- `CapabilityReport` (`host_runner.py:143`, `@dataclass(frozen=True)`) has no
  `dataclasses.replace()` usage anywhere in the codebase, and `ll-action`'s
  precedent avoids the question entirely by building its own output dict
  instead of mutating the report. `ll-doctor`'s `_print_report()` should follow
  suit: compute `version_display` from a locally probed string rather than
  trying to reconstruct/replace the frozen `CapabilityReport`.
- `main_doctor()` (`doctor.py:87`) currently never calls `runner.detect()` or
  `runner.build_version_check()` at all — only `runner.describe_capabilities()`
  at line 128. `_print_report()` (`doctor.py:55`) already has the
  `report.version or "(unknown)"` fallback wired at both the JSON branch
  (line 65) and text branch (line 73/75) — the display-fallback logic is
  correct and needs no change; only the probe step feeding `report.version`
  is missing.
- Stub runners `OpenCodeRunner.build_version_check` (`host_runner.py:738`) and
  `PiRunner.build_version_check` (`host_runner.py:811`) raise
  `HostNotConfigured` instead of returning a `HostInvocation` — the probe call
  must catch `HostNotConfigured` alongside the subprocess-failure tuple, same
  as `install_check.py`'s `fetch_latest_plugin()` (`scripts/little_loops/init/install_check.py:132-173`)
  does when resolving the runner.
- No dedicated timeout-bounded subprocess helper exists in
  `subprocess_utils.py` (its only top-level function is the heavier streaming
  `run_claude_command()` at line 299) — both existing precedents
  (`action.py:346` and `install_check.py`) call stdlib `subprocess.run(...,
  capture_output=True, text=True, timeout=N)` inline rather than through a
  shared wrapper. Follow that inline-call convention; do not introduce a new
  shared helper for this.
- Test mocking precedent for present/absent/timeout/failing-binary cases is in
  `scripts/tests/test_init_install.py` (patches `subprocess.run` with
  `MagicMock(returncode=0, stdout=...)`, `side_effect=subprocess.TimeoutExpired(...)`,
  `side_effect=OSError(...)`, and `side_effect=HostNotConfigured(...)` on
  `resolve_host`) and `scripts/tests/test_cli_doctor.py`'s `_make_runner()`
  helper (line 27) which mocks `runner.describe_capabilities()` — extend that
  fixture with `runner.detect.return_value` / `runner.build_version_check.return_value`
  to cover the new probe step.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — `main_doctor()` (line 87, where
  `report = runner.describe_capabilities()` is called at line 128) add the
  `runner.detect()` + `runner.build_version_check()` + `subprocess.run(...)`
  probe here, matching `action.py:335-366`'s shape; `_print_report()` (line 55)
  already has the correct `report.version or "(unknown)"` fallback and needs no
  change beyond receiving a populated version string.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/action.py` — `cmd_capabilities()` (line 335) is the
  **only existing production caller** of `build_version_check()`; it does not
  consume `ll-doctor`'s output so is unaffected by this change, but its inline
  probe logic (lines 341-354) is the pattern to copy verbatim.
- `scripts/little_loops/init/install_check.py` — `fetch_latest_plugin()`
  (lines 132-173) and `detect_installation()` (lines 72-105) are a second,
  independent precedent for the same "resolve_host → build_version_check →
  subprocess.run → swallow to None/unknown" shape, including catching
  `HostNotConfigured` at the resolve step.

### Similar Patterns
- `scripts/little_loops/cli/action.py:335-366` (`cmd_capabilities`) — the
  canonical version-probe implementation: `detect()` gate, `build_version_check()`
  → `subprocess.run(..., capture_output=True, text=True, timeout=10)`, catch
  `(subprocess.TimeoutExpired, FileNotFoundError, OSError)`.
- `scripts/little_loops/init/install_check.py` — same shape plus
  `HostNotConfigured` handling at the `resolve_host()` step.
- No shared subprocess wrapper exists in `subprocess_utils.py` (only
  `run_claude_command()` at line 299, a heavier streaming invoker) — both
  precedents call stdlib `subprocess.run` inline; do the same here rather than
  adding a new helper.
- `dataclasses.replace()` is unused anywhere in the codebase — `CapabilityReport`
  is frozen (`host_runner.py:143`); follow `action.py`'s approach of building a
  separate output value rather than mutating/replacing the report.

### Tests
- `scripts/tests/test_cli_doctor.py` — `_make_runner()` helper (line 27) mocks
  only `describe_capabilities()`; extend it (or add `runner.detect`/
  `runner.build_version_check` mocks per-test) to assert version rendering for
  present, absent, timing-out, and failing binaries.
- `scripts/tests/test_host_runner.py` — existing per-runner `build_version_check`
  shape tests (e.g. line 173 for `ClaudeCodeRunner`, lines 595/653 for the
  `HostNotConfigured`-raising stub runners) already cover the invocation
  builder; no change needed there, only in doctor's consumption of it.
- `scripts/tests/test_init_install.py` — reference for subprocess-mocking style
  (`MagicMock(returncode=0, stdout=...)`, `side_effect=subprocess.TimeoutExpired(...)`,
  `side_effect=OSError(...)`, `side_effect=HostNotConfigured(...)`) to model new
  `test_cli_doctor.py` cases after.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_action.py:25-49` — `FakeRunner`, a full `HostRunner`
  protocol test double (`detect()`, `build_version_check()`,
  `describe_capabilities()` all implemented together, modeled on `FakeCodex` in
  `test_host_runner.py`) already backs `cmd_capabilities()`'s own probe tests
  (`test_emits_full_capability_report` at line 586, `detect_returns=False` case
  at line 615). This is a cleaner alternative to the `MagicMock`-based mocking
  in `test_init_install.py` for `test_cli_doctor.py`'s new probe cases — a
  `FakeRunner(detect_returns=...)` double avoids re-mocking each method
  individually per test.

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md` (~line 308) — sample output
- `docs/reference/CLI.md:228` — `ll-doctor` section

### Configuration
- N/A

## Implementation Steps

1. In `main_doctor()` (`scripts/little_loops/cli/doctor.py:87`), after
   `report = runner.describe_capabilities()` (line 128), add a probe step
   copying `cmd_capabilities()`'s shape (`scripts/little_loops/cli/action.py:335-366`):
   check `runner.detect()`, then `runner.build_version_check()` →
   `subprocess.run([invocation.binary, *invocation.args], capture_output=True, text=True, timeout=10)`,
   catching `(subprocess.TimeoutExpired, FileNotFoundError, OSError, HostNotConfigured)`.
   Do not mutate the frozen `CapabilityReport` (line 143) — pass the probed
   version string separately into `_print_report()`.
2. Update `_print_report()` (`doctor.py:55`) to accept the probed version
   string (its `report.version or "(unknown)"` fallback logic at lines 65/73
   is already correct and stays unchanged in shape).
3. Extend `_make_runner()` in `scripts/tests/test_cli_doctor.py:27` with
   `detect`/`build_version_check` mocks; add present/absent/timeout/failing/
   `HostNotConfigured` cases modeled on `scripts/tests/test_init_install.py`'s
   subprocess-mocking patterns.
4. Refresh the sample output in `docs/reference/HOST_COMPATIBILITY.md` (~line 308)
   and `docs/reference/CLI.md:228`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Consider using `test_action.py`'s `FakeRunner` (line 25) as the test double
   for the new `test_cli_doctor.py` probe cases instead of hand-rolling
   `MagicMock` setups — it already implements `detect()`/`build_version_check()`/
   `describe_capabilities()` together and is exercised by
   `test_emits_full_capability_report` (line 586) for the identical scenario.

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
- `/ll:manage-issue` - 2026-07-25T06:21:12Z - `42e911d0-636a-4d59-ae96-d8a57523cb0f.jsonl`
- `/ll:ready-issue` - 2026-07-25T06:14:41 - `128eb7e2-c670-49a4-8b22-8e7e3d79fd1f.jsonl`
- `/ll:wire-issue` - 2026-07-25T06:13:03 - `8ec9a84c-9f75-462d-9a76-60094aaef3f5.jsonl`
- `/ll:refine-issue` - 2026-07-25T06:06:06 - `e5b1258c-27cd-4aab-8066-f9d2b8e4adf4.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
