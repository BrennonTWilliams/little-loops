---
id: ENH-2314
title: ll-init robustness cleanup (unknown --hosts, perm sweep, version compare, bare
  except)
type: ENH
status: open
priority: P4
captured_at: '2026-06-26T21:55:52Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
labels:
- init
- robustness
learning_tests_required:
- packaging
confidence_score: 92
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 23
score_ambiguity: 18
score_change_surface: 20
---

# ENH-2314: ll-init robustness cleanup

## Summary

Four low-severity robustness/correctness nits surfaced while auditing `ll-init`.
Each is small and independently shippable; bundled here to avoid issue sprawl.

## Motivation

These don't cause data loss but degrade UX and silently swallow signal. Cheap to
fix; good hygiene for a user-facing init command.

## Current Behavior

Four robustness gaps in `ll-init`:

1. `_dispatch_host_adapters` (`cli.py`) silently ignores unrecognized `--hosts`
   values; a typo like `--hosts codx` does nothing. `opencode` is a documented
   host (`host_runner.py`) but absent from `_detect_hosts` and adapter dispatch.
2. `merge_settings` (`writers.py:252`) strips every permission matching the
   `Bash(ll-` prefix, so a user's custom `Bash(ll-mytool:*)` entry is silently
   removed on re-init.
3. `check_version` (`install_check.py:157-169`) compares versions as strings
   (`installed == latest`), so an installed version newer than PyPI is incorrectly
   flagged as `OutOfDate`.
4. `fetch_latest_plugin` (`install_check.py:126`) catches
   `except (HostNotConfigured, Exception)`, making `HostNotConfigured` redundant
   and swallowing unexpected exceptions silently.

## Expected Behavior

1. `--hosts` validates against a known set (`codex`, `pi`, `opencode`); unknown
   values produce a warning or error. `opencode` is handled in both `_detect_hosts`
   and `_dispatch_host_adapters`.
2. `merge_settings` scopes its sweep to the canonical `_LL_PERMISSIONS` list;
   user-added `Bash(ll-mytool:*)` permissions are preserved across re-inits.
3. `check_version` uses `packaging.version.Version` for semver-aware comparison;
   an installed version newer than PyPI latest is reported `UpToDate` (or `Ahead`),
   not `OutOfDate`.
4. `fetch_latest_plugin` catches only the expected exception types (e.g.
   `HostNotConfigured`, `urllib.error.URLError`, `json.JSONDecodeError`);
   unexpected exceptions surface normally.

## Proposed Solution

1. **Unknown `--hosts` silently ignored.** `--hosts` accepts arbitrary strings;
   `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:67-98`) only acts
   on `codex`/`pi` and ignores anything else with no error. A typo like
   `--hosts codx` does nothing silently. Also `opencode` is a documented host
   (`host_runner`) but is absent from `_detect_hosts` (`cli.py:55-64`) and adapter
   dispatch.
   → Validate host names against a known set; warn/error on unknown.

2. **`merge_settings` over-aggressive sweep.** The idempotency sweep strips *every*
   entry matching `Bash(ll-` (`scripts/little_loops/init/writers.py:252`), so a
   user's custom `Bash(ll-mytool:*)` permission is silently removed on re-init.
   → Scope the sweep to the canonical `_LL_PERMISSIONS` set rather than the
   `Bash(ll-` prefix.

3. **`check_version` is string-equality only** (`scripts/little_loops/init/install_check.py:157-169`).
   Any mismatch → `OutOfDate`, so an install *newer* than PyPI latest is reported
   stale. → Use a semver-aware comparison (e.g. `packaging.version`).

4. **Bare `except Exception`** in `fetch_latest_plugin`
   (`scripts/little_loops/init/install_check.py:126`,
   `except (HostNotConfigured, Exception)`). The `Exception` makes
   `HostNotConfigured` redundant and swallows everything.
   → Narrow to the expected exception types.

## Scope Boundaries

- Only the four nits identified above; no other `ll-init` behavior changes.
- No new host detection heuristics beyond adding `opencode` to the known-host set.
- No new `--hosts` validation modes; a simple warn-and-skip or error-and-exit is sufficient.
- `packaging` is likely already a transitive dependency; no new top-level dependency expected.
- Out of scope: reworking `_detect_hosts` auto-detection logic, changing the `OutOfDate` UX flow, or adding new permission groups.

## Implementation Steps

1. Add known-host validation in `_dispatch_host_adapters` (`cli.py`); add `opencode`
   to `_detect_hosts` and its adapter branch.
2. Replace the `Bash(ll-` prefix sweep in `merge_settings` (`writers.py`) with a
   set-membership check against `_LL_PERMISSIONS`.
3. Replace string equality in `check_version` (`install_check.py`) with
   `packaging.version.Version` comparison; handle `installed > latest` case.
4. Narrow the broad `except Exception` in `fetch_latest_plugin` to specific expected
   exception types.
5. Add/update tests in `test_init_core.py` covering each of the four fixes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_init_core.py` — invert `test_removes_stale_ll_entries` assertion and add the five new test cases (unknown host, opencode detection, custom-ll-permission preserved)
7. Update `scripts/tests/test_init_install.py` — invert `test_installed_ahead_returns_out_of_date` assertion and add semver lexicographic edge case + Fix 4 unexpected-exception propagation case
8. (Conditional) Add `packaging>=21.0` to `[project.dependencies]` in `scripts/pyproject.toml` if Fix 3 uses `packaging.version.Version`; skip if stdlib tuple comparison is used instead
9. Update `docs/reference/CLI.md` — add `opencode` to the `--hosts` valid-values list
10. Update `docs/reference/API.md` — update `check_version` semantics to describe three-way comparison behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` — `_detect_hosts`, `_dispatch_host_adapters`
- `scripts/little_loops/init/writers.py` — `merge_settings`
- `scripts/little_loops/init/install_check.py` — `check_version`, `fetch_latest_plugin`
- `scripts/little_loops/init/tui.py` — also calls `_dispatch_host_adapters()` (line 871); verify host-name validation UX is consistent with the headless path

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/pyproject.toml` — add `packaging>=21.0` to `[project.dependencies]` (only required if Fix 3 uses `packaging.version.Version`; stdlib tuple comparison avoids this change)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/cli.py` calls `check_version` and `fetch_latest_plugin` from `install_check`
- `scripts/little_loops/host_runner.py` — source of truth for recognized host names; keep in sync

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/__init__.py` — re-exports `check_version`, `detect_installation`, `fetch_latest_plugin`, `fetch_latest_pypi`, `merge_settings`, and other writers functions; no signature changes so no edits required, but verify `__all__` if a new `InstallStatus.Ahead` enum value is introduced for Fix 3

### Similar Patterns
- Host name validation in `host_runner.py` (`resolve_host`) — follow same known-set pattern
- Other `except Exception` sweeps in `install_check.py` — review for similar narrowing

### Tests
- `scripts/tests/test_init_core.py` — add tests for unknown host validation, permission preservation across re-init
- `scripts/tests/test_init_install.py` — already covers `check_version()` and `fetch_latest_plugin()` directly; add the newer-than-PyPI semver case and the narrowed-except case here (more natural home than `test_init_core.py`)

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break and must be updated:**
- `scripts/tests/test_init_core.py::TestMergeSettings::test_removes_stale_ll_entries` (line 721) — asserts `count == 0` for `Bash(ll-old-tool:*)` after re-init; Fix 2 preserves that entry (it is not in `_LL_PERMISSIONS`), so the assertion inverts. Replace with a test that seeds a genuinely stale canonical entry and a companion case asserting `Bash(ll-mytool:*)` is preserved.
- `scripts/tests/test_init_install.py::TestCheckVersion::test_installed_ahead_returns_out_of_date` (line 31) — asserts `check_version("2.0.0", "1.0.0") == InstallStatus.OutOfDate`; Fix 3 makes installed > latest return `UpToDate` (or `Ahead`). Assert must be inverted.

**New test cases needed (coverage gaps per fix):**
- `test_init_core.py::TestHostDispatch` — add case: unknown host name (e.g. `--hosts codx`) produces a warning/error, not silent no-op (Fix 1a)
- `test_init_core.py::TestDetectHosts` — add case: `opencode` binary detected via `shutil.which`; follow pattern of `test_pi_binary_detected` (Fix 1b)
- `test_init_core.py::TestMergeSettings` — add case: `Bash(ll-mytool:*)` (not in `_LL_PERMISSIONS`) survives re-init; follow pattern of `test_preserves_unrelated_existing_entries` (Fix 2)
- `test_init_install.py::TestCheckVersion` — add case: `check_version("1.10.0", "1.9.0")` returns `UpToDate` (catches string-vs-semver lexicographic failure) (Fix 3)
- `test_init_install.py::TestFetchLatestPlugin` — add case: unexpected exception from `resolve_host()` (not `HostNotConfigured`) propagates rather than being swallowed (Fix 4)

**Additional test files to verify (integration paths):**
- `scripts/tests/test_init_tui.py` — exercises `_dispatch_host_adapters`, `merge_settings`, `check_version` as integration paths through TUI flows; verify no tests pass invalid host names that would now error under Fix 1
- `scripts/tests/test_wiring_init_and_configure.py` — end-to-end init/configure wiring; check for host-dispatch paths

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `--hosts` table row in `### ll-init` lists `(claude-code, codex, pi)` but omits `opencode`; add `opencode` to the valid-values list once Fix 1 lands
- `docs/reference/API.md` — `### check_version` section states "Returns `InstallStatus.OutOfDate` otherwise"; after Fix 3, `installed > latest` returns `UpToDate` (or a new `Ahead` value), so the description must be updated to reflect the three-way comparison logic

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Fix 1 — host validation**: `_dispatch_host_adapters()` is at `cli.py:67–98`; `_detect_hosts()` is at `cli.py:55–64`. The canonical known-host set lives in `host_runner._HOST_RUNNER_REGISTRY` (keys: `claude-code`, `codex`, `opencode`, `pi`). The `--hosts` argument enters `main_init()` at `cli.py:609–617` with comma-splitting but no validation before reaching `_dispatch_host_adapters`. `opencode` only needs a dispatch branch added to `_dispatch_host_adapters` — it is intentionally absent from `_PROBE_ORDER` and auto-detection should stay that way. Validation pattern to follow: `resolve_host()` raises `HostNotConfigured(f"Host {explicit!r} is not registered. Available: {sorted(_HOST_RUNNER_REGISTRY)}.")` for unknown names.
- **Fix 2 — permission sweep**: `_LL_PERMISSIONS` is defined at `writers.py:24–52` (27 entries: 26 `Bash(ll-…:*)` + 1 trailing `Write(.ll/ll-continue-prompt.md)`). The idempotency sweep at `writers.py:252` uses `e.startswith("Bash(ll-")`. Replace with `e in _LL_PERMISSIONS` (or `e in set(_LL_PERMISSIONS)` for O(1) — the tuple is small so either is fine).
- **Fix 3 — version comparison ⚠ dependency gap**: `check_version()` is at `install_check.py:157–169`; current body is `if installed == latest: return UpToDate; return OutOfDate`. `packaging` is **not declared** in `scripts/pyproject.toml` `[project.dependencies]` (lines 37–43) — it must be added there, or a stdlib alternative used (e.g., `tuple(int(x) for x in v.split("."))` works for strict `MAJOR.MINOR.PATCH` strings). The scope boundary says "no new top-level dependency expected" but research shows `packaging` is not a current transitive — either add it or use the stdlib tuple approach.
- **Fix 4 — bare except**: `fetch_latest_plugin()` Zone 1 catch is at `install_check.py:122–127`: `except (HostNotConfigured, Exception)`. `HostNotConfigured` is a `RuntimeError` subclass and is already subsumed by `Exception`, making the tuple redundant. The correct narrowing is `except HostNotConfigured` — this is the only expected error from `resolve_host()` / `build_version_check()` when no host is configured. Zones 2 and 3 in the same function already use properly narrowed catches (`subprocess.TimeoutExpired, FileNotFoundError, OSError` / `…, json.JSONDecodeError`) and need no changes.

## Impact

- **Priority**: P4 — Minor robustness nits; no data loss risk; each fix is independently shippable
- **Effort**: Small — Targeted 2–10 line changes in well-understood code; existing test suite covers integration points
- **Risk**: Low — Changes narrow or validate existing behavior; no new APIs introduced
- **Breaking Change**: No

## Labels

- init, robustness

## Verification Notes

- **2026-06-26** (/ll:verify-issues): Updated Fix-2's permission-sweep edit site from `writers.py:185` to `writers.py:252` (the `e.startswith("Bash(ll-")` line drifted); Current Behavior, Proposed Solution, Implementation, and Codebase Research now point at the correct line. The four other nits and the `install_check.py` refs (126, 157-169) verified accurate and left unchanged.

## Session Log
- `/ll:confidence-check` - 2026-06-26T22:31:07 - `6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:27:48 - `6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:13:46 - `6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`
- `/ll:format-issue` - 2026-06-26T22:06:39 - `c619bbe2-2f0b-4c0f-8966-375ca40f0190.jsonl`
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P4
