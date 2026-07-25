---
id: FEAT-2793
type: feature
priority: P3
status: done
parent: EPIC-2765
relates_to:
- FEAT-2763
confidence_score: 96
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
completed_at: '2026-07-25T14:09:50Z'
---

# FEAT-2793: Introduce ll-doctor check-registry protocol and settle exit-code semantics

## Summary

`ll-doctor` currently hardcodes its two sections (host capabilities,
capture/issues echoes) with no extension point. Before any new install-surface
checks can be added (FEAT-2794, FEAT-2795), `doctor.py` needs a lightweight
check-registry protocol that the existing host-capability report can be ported
onto without changing its output, plus a documented, resolved policy for how
new check failures affect the process exit code.

## Current Behavior

`ll-doctor` (`scripts/little_loops/cli/doctor.py`) hardcodes its two sections
— the host-capability report and the analytics-capture/issues echoes — with
no extension point. There is no `CheckResult`-style protocol a new check can
register against; adding a new install-surface check today means editing
`_print_report()` and `main_doctor()` directly.

## Expected Behavior

`doctor.py` exposes a lightweight check-registry protocol (a `CheckResult`
dataclass plus a `_CHECKS: list[Callable[[], CheckResult]]` registration
list) that the existing host-capability report is ported onto without
changing its current text or `--json` output. `main_doctor()`'s exit-code
logic folds registered checks' results using a documented severity split
(error-tier vs. informational), so FEAT-2794 and FEAT-2795 can register new
checks against this registry without further core changes.

## Use Case

As a maintainer adding a new install-surface check (FEAT-2794, FEAT-2795), I
want a registry to register a `CheckResult`-producing function against,
instead of hand-editing `_print_report()`/`main_doctor()` for every new
check.

## Impact

Foundational — FEAT-2794 and FEAT-2795 are both `blocked_by: FEAT-2793` and
cannot register their checks until this registry protocol and the resolved
exit-code semantics land.

## Parent Issue

Decomposed from FEAT-2763: Expand ll-doctor to validate little-loops' own
install surface. This child covers Implementation Steps 1, 2, and 5 of the
parent (verifier shell-out-vs-import decision — already resolved in favor of
import per the parent's refine-issue research — registry protocol design, and
exit-code semantics).

## Proposed Solution

Introduce a lightweight check-registry protocol (name, category, run → status
+ note) mirroring the existing `_STATUS_SYMBOLS` vocabulary and the
`CapabilityEntry`/`CapabilityReport` frozen-dataclass shape (`host_runner.py:131,144`).
Register the host-capability report as one category on the new registry so
current `ll-doctor` output is preserved exactly, not special-cased. Decide and
document the still-open exit-code question (whether install-surface failures
affect the default exit status or only under `--full`) directly in this
issue's implementation — this is a blocking design decision for FEAT-2794 and
FEAT-2795, both of which register checks against this registry.

Prefer the plain-registry approach over an entry-points/decorator abstraction:
per the parent's codebase research, checks are internal to little-loops, not
third-party-pluggable (unlike `extension.py`'s `ExtensionLoader`), so a
module-level `_CHECKS` list of `Callable[[], CheckResult]` is the right shape.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Confirmed dataclass shape to mirror**: `CapabilityEntry`
  (`scripts/little_loops/host_runner.py:131-140`) is `@dataclass(frozen=True)`
  with `name: str`, `status: Literal["full", "partial", "unsupported"]`,
  `note: str = ""`; `CapabilityReport` (`:144-155`) wraps
  `host/binary/version` plus `capabilities: list[CapabilityEntry]`. `CheckResult`
  should follow the same frozen-dataclass + closed-`Literal`-status + optional
  `note` shape for consistency.
- **No existing "run-and-aggregate" registry to port from** — this is a new
  pattern, not a refactor of an existing one. The two closest codebase
  analogues are `extension.py`'s `ExtensionLoader` (a *discovery/loading*
  pattern, already correctly rejected in this section) and
  `hooks/__init__.py`'s `_HOOK_INTENT_REGISTRY: dict[str, Callable[...]]`
  (`:114`, a *name-keyed dispatch table* invoking one handler by intent name —
  not an aggregate-all-and-collect-results list either). Neither is a template
  to reuse; `_CHECKS: list[Callable[[], CheckResult]]` as proposed is correct
  and novel to this codebase.
- **Closest sibling for the exit-code decision**: `fsm/validation.py`'s
  `ValidationSeverity` enum (`ERROR`/`WARNING`) paired with
  `ValidationError.severity`, consumed by `cli/loop/config_cmds.py:cmd_validate()`
  as `has_errors = any(v.severity == ValidationSeverity.ERROR for v in violations)`
  → `return 1 if has_errors else 0`. This is the codebase's only existing
  precedent for "some check failures affect exit code, others don't" and maps
  directly onto this issue's open question: give `CheckResult` a severity
  field (or reuse a two-tier status split within the existing `full` /
  `partial` / `unsupported` vocabulary) so exit-code aggregation in
  `main_doctor()` can fold `_CHECKS` results the same way `cmd_validate()`
  folds `violations` — only `unsupported`/error-tier results affecting the
  default exit code, `partial`/informational ones (e.g. an absent optional
  subsystem, per FEAT-2794) never do. No existing `--full`-style flag
  precedent exists anywhere in `scripts/little_loops/cli/` (grep returned no
  matches), so FEAT-2795's `--full` gating will be new plumbing, not reuse.
- **`--json` shape to preserve exactly**: the current flat dict built in
  `_print_report()` (`doctor.py:117-126`) — keys `host`, `binary`, `version`,
  `capabilities` (list of `{name, status, note}`), `analytics_capture`,
  `issues`. `test_json_output_flag` (`test_cli_doctor.py:260-288`) explicitly
  asserts `"hooks" not in data` (a stray key removed per BUG-2760) — the
  registry-driven JSON assembly must not reintroduce dead keys.
- **Test-coupling constraint**: `TestVersionProbe` patches
  `little_loops.cli.doctor.subprocess.run` directly — `_probe_version()`'s
  `subprocess.run` call must stay resolvable from the `doctor` module's own
  namespace after the refactor, not move into a separate registry module, or
  those mocks silently stop intercepting.
- **Downstream requirements from FEAT-2794/FEAT-2795** (both `blocked_by:
  FEAT-2793`): the registry must (a) support per-check gating so FEAT-2795 can
  register verifiers that only run under `--full`, (b) let a check report an
  "informational" (non-failing) status for an absent-but-optional subsystem
  (FEAT-2794's history-DB check), and (c) remain compatible with directly
  importing pure `_run() -> tuple[int, ...]` functions from the `ll-verify-*`
  family (e.g. `verify_kinds.py:38-47`, `verify_cli_allowlist.py:69`) without
  requiring subprocess shell-out.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports `main_doctor` (line 64) and
  re-exports it in `__all__` (line 114); `main_doctor(argv)`'s external
  signature must stay unchanged since this is the module the
  `ll-doctor = "little_loops.cli:main_doctor"` entry point
  (`scripts/pyproject.toml:77`) resolves through. [Agent 1 finding]
- `scripts/little_loops/cli/action.py` (`cmd_capabilities`) — sibling surface
  that also calls `describe_capabilities()` and documents a similar
  `--json` shape; not modified by this issue but its output shape is the
  precedent `CheckResult`/`_print_report()` must stay consistent with.
  [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md:312` — states "Exits non-zero if any
  capability is unsupported"; this line becomes stale/incomplete once the
  resolved exit-code policy lets install-surface checks affect (or not
  affect) the exit code independently of capability status — update to
  reflect the new policy. [Agent 2 finding]
- `docs/reference/API.md` (~lines 769, 875, 8702, 8737, 8765-8767) —
  documents `ll-doctor --json`'s payload as "a superset of `CapabilityReport`"
  describing the pre-registry assembly; review phrasing once
  `_print_report()`'s JSON is registry-assembled (even though the emitted
  keys are unchanged). [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_guides_and_meta.py`,
  `scripts/tests/test_wiring_init_and_configure.py`,
  `scripts/tests/test_wiring_cli_registry.py` — presence-only wiring checks
  asserting the literal string `"ll-doctor"` stays in `commands/help.md`,
  `docs/reference/CLI.md`, `.claude/CLAUDE.md`,
  `docs/reference/HOST_COMPATIBILITY.md`, `CONTRIBUTING.md`, and
  `skills/configure/areas.md`. No exact-text lock on exit-code wording, but
  re-run these after editing `docs/reference/HOST_COMPATIBILITY.md` /
  `CLI.md` to confirm the substring survives. [Agent 1 + 2 finding]
- `scripts/tests/test_host_runner.py` (`TestCapabilityReport`, ~line 984+) —
  construction-only coverage of `CapabilityEntry`/`CapabilityReport`; worth a
  spot-check for shape drift since `CheckResult` mirrors this dataclass but
  is not the same class. [Agent 1 finding]
- New registry unit tests should follow the `TestMainDoctor`/`TestVersionProbe`
  class-per-concern convention already in `test_cli_doctor.py`, and model the
  mixed-severity exit-code test after `cmd_validate()`'s pattern
  (`scripts/tests/test_ll_loop_commands.py::test_validate_json_output_invalid_loop`,
  `::test_validate_json_loop_reference_error`) — no existing test exercises a
  mixed error+informational `CheckResult` set in one call to confirm only the
  error-tier result flips the exit code; this is a genuinely new test shape,
  analogous in intent to `TestMainDoctor::test_partial_capability_does_not_trigger_exit_one`
  applied to the new registry severity split. [Agent 3 finding]
- Preserve `TestVersionProbe`'s patch target — `_probe_version()`'s
  `subprocess.run` call must stay resolvable as
  `little_loops.cli.doctor.subprocess.run`; if the registry protocol moves
  version-probing into a separate module, all 5 `TestVersionProbe` tests
  silently stop intercepting the mock. [Agent 3 finding]

## Acceptance Criteria

- [x] `doctor.py` exposes a check-registry protocol (`CheckResult` dataclass +
      `_CHECKS: list[Callable[[], CheckResult]]` or equivalent) that the
      host-capability report is ported onto without changing existing
      `ll-doctor` text or `--json` output.
- [x] `main_doctor()`'s exit-code logic is updated per the resolved semantics:
      documented distinction between "unsupported host capability" and
      "broken install," with the decision written into
      `docs/reference/CLI.md`'s exit-code line.
- [x] Existing `scripts/tests/test_cli_doctor.py` passes unchanged — this
      issue is a pure refactor of `doctor.py`'s internals plus the exit-code
      policy, not a new user-visible section.
- [x] New unit tests cover the registry mechanism itself (registering a check,
      merging its `CheckResult` into `--json` output) and the exit-code policy
      decision.

## Files

- `scripts/little_loops/cli/doctor.py` — add the registry protocol, port
  `_capture_section_data`/`_issues_section_data`/host-capability report onto
  it, update `main_doctor()` exit-code logic
- `docs/reference/CLI.md:235` — exit-code line, rewritten per the resolved
  policy
- `scripts/tests/test_cli_doctor.py` — regression coverage plus new registry
  unit tests

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints must be included in the implementation:_

- `docs/reference/HOST_COMPATIBILITY.md:312` — update the "exits non-zero if
  any capability is unsupported" line to reflect the resolved policy for
  install-surface check failures
- `docs/reference/API.md` — spot-check `CapabilityReport` superset phrasing
  once `ll-doctor --json` is registry-assembled
- Re-run `test_wiring_guides_and_meta.py`, `test_wiring_init_and_configure.py`,
  `test_wiring_cli_registry.py` after doc edits to confirm the `"ll-doctor"`
  presence checks still pass
- Verify `scripts/tests/test_host_runner.py::TestCapabilityReport` for shape
  drift against the new `CheckResult` dataclass
- Add a mixed-severity exit-code test (error-tier + informational
  `CheckResult` in one registry run) modeled on
  `test_ll_loop_commands.py::test_validate_json_output_invalid_loop`
- Keep `_probe_version()`'s `subprocess.run` call patchable as
  `little_loops.cli.doctor.subprocess.run` — do not move it into a separate
  registry module

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/host_runner.py:131-155` — `CapabilityEntry`/
  `CapabilityReport` frozen dataclasses the new `CheckResult` shape should
  mirror (read-only reference, not modified by this issue).
- `scripts/little_loops/fsm/validation.py` — `ValidationSeverity` enum +
  `ValidationError` dataclass; reference precedent for the exit-code severity
  split (read-only reference).
- `scripts/little_loops/cli/loop/config_cmds.py:12-41` (`cmd_validate()`) —
  reference precedent for folding mixed-severity results into a single exit
  code (read-only reference).
- `scripts/tests/test_host_runner.py` (`TestCapabilityReport`, line ~984+) —
  existing coverage of `CapabilityEntry`/`CapabilityReport` construction;
  unaffected by this issue but worth checking for shape drift.

## Execution Pattern

Foundational — FEAT-2794 and FEAT-2795 both register checks against the
registry this issue introduces and must start after this issue is done.

## Resolution

Added `CheckResult` (frozen dataclass mirroring `CapabilityEntry`, with a
`severity: "error" | "informational"` field independent of `status`),
`_CHECKS: list[Callable[[], list[CheckResult]]]` plus `register_check()`,
`_capability_check_results()` (folds the existing `CapabilityReport` into
`CheckResult`s without changing text/`--json` output), `_run_registered_checks()`,
and `_exit_code_for()` in `scripts/little_loops/cli/doctor.py`. `main_doctor()`
now computes its exit code by folding capability + registered-check results
through the error/informational severity split instead of checking
`capabilities` directly. Updated the exit-code line in
`docs/reference/CLI.md` and `docs/reference/HOST_COMPATIBILITY.md`. Added
`TestCheckRegistry` (5 new tests) to `scripts/tests/test_cli_doctor.py`;
all pre-existing doctor tests pass unchanged.

## Session Log
- `/ll:manage-issue` - 2026-07-25T14:09:14 - `4639fae3-ee9d-4cea-878b-28748cf5edf6.jsonl`
- `/ll:ready-issue` - 2026-07-25T14:04:05 - `5e2d2095-dffb-485e-a389-d391b666d7cf.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00 - `97f01cf0-0a54-45d4-b480-f10355610ab6.jsonl`
- `/ll:wire-issue` - 2026-07-25T14:00:59 - `6dd85b41-7678-486e-965b-10c81681652c.jsonl`
- `/ll:refine-issue` - 2026-07-25T13:55:52 - `fa35f24d-9ea6-4605-a6ba-a488e443ff3b.jsonl`
- `/ll:issue-size-review` - 2026-07-25T00:00:00 - `decomposed-from-FEAT-2763`

---

## Status

**Open** | Created: 2026-07-25 | Priority: P3
