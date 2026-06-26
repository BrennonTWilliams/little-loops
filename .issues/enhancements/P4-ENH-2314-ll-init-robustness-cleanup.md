---
id: ENH-2314
title: "ll-init robustness cleanup (unknown --hosts, perm sweep, version compare, bare except)"
type: ENH
status: open
priority: P4
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- robustness
---

# ENH-2314: ll-init robustness cleanup

## Summary

Four low-severity robustness/correctness nits surfaced while auditing `ll-init`.
Each is small and independently shippable; bundled here to avoid issue sprawl.

## Motivation

These don't cause data loss but degrade UX and silently swallow signal. Cheap to
fix; good hygiene for a user-facing init command.

## Findings / Proposed Solution

1. **Unknown `--hosts` silently ignored.** `--hosts` accepts arbitrary strings;
   `_dispatch_host_adapters` (`scripts/little_loops/init/cli.py:67-98`) only acts
   on `codex`/`pi` and ignores anything else with no error. A typo like
   `--hosts codx` does nothing silently. Also `opencode` is a documented host
   (`host_runner`) but is absent from `_detect_hosts` (`cli.py:55-64`) and adapter
   dispatch.
   → Validate host names against a known set; warn/error on unknown.

2. **`merge_settings` over-aggressive sweep.** The idempotency sweep strips *every*
   entry matching `Bash(ll-` (`scripts/little_loops/init/writers.py:185`), so a
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

## Impact

Minor: misleading version warnings, lost custom permissions on re-init, silent
no-op on host typos.

## Labels

- init, robustness

## Session Log
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P4
