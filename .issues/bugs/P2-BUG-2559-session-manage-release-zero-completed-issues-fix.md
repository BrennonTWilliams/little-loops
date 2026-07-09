---
id: BUG-2559
title: "Session record: fix /ll:manage-release reporting 0 completed issues (completed_at absent from ll-issues list --json)"
type: BUG
priority: P2
status: done
captured_at: '2026-07-09T03:51:24Z'
completed_at: '2026-07-09T03:51:24Z'
discovered_date: '2026-07-09'
discovered_by: user-report
relates_to:
  - BUG-2558
  - BUG-942
  - ENH-1421
labels:
  - manage-release
  - json-contract
  - regression-guard
  - changelog
  - session-record
confidence_score: 100
outcome_confidence: 95
---

# BUG-2559: Session record — `/ll:manage-release` reported 0 completed issues

## Summary

Work-log for the session that diagnosed and fixed the `/ll:manage-release`
"0 completed issues since last release" defect. The underlying defect and its
resolution are tracked in [[BUG-2558]]; this issue records the full session
scope for traceability.

## Current Behavior

`/ll:manage-release` reported **"0 completed issues since last release"** during
the `v1.140.0` release even though 26 issues (FEAT-2551/2552/2413, ENH-2418,
BUG-2547, …) had been completed since the `v1.139.0` tag. The empty result was
structural — the query returned 0 on **every** release, independent of baseline.

## Expected Behavior

`/ll:manage-release` includes every issue completed since the previous tag in the
generated changelog, and refuses to silently ship an empty release-notes body.

## Steps to Reproduce

1. Complete several issues (status `done`, `completed_at` in frontmatter).
2. Tag a release (`v1.139.0`).
3. Run `/ll:manage-release`.
4. Observe: Agent 2 reports 0 completed issues.

Confirmed directly:

```bash
ll-issues list --status done --json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum('completed_at' in i for i in d))"
# → 0 (before fix); the manage-release filter i.get('completed_at','') >= prev_ts is always False
```

## Root Cause

`commands/manage-release.md` Agent 2 filtered `ll-issues list --status done
--json` by a `completed_at` key that **`ll-issues list --json` never emitted**
(`cli/issues/list_cmd.py`: `IssueInfo` had no `completed_at`; the JSON dict
dropped the already-computed `comp_date`). So the filter was always `'' >=
<timestamp>` → `False` → 0.

Regression lineage: [[BUG-942]] fixed the same symptom (2026-04-03) via `git log
--diff-filter=A ... -- .issues/completed/`; [[ENH-1421]] removed that (correctly
— the directory no longer exists) but swapped in the broken `completed_at`-JSON
filter, silently re-introducing the defect. Contributing gap: `ll-issues
set-status <id> done` never stamped `completed_at`.

## Work Performed This Session

1. **Investigation** — two parallel Explore agents traced the manage-release
   command, the `ll-issues list --json` code path, and the `completed_at` write
   sites; reproduced the always-0 filter (2318 done issues, 0 with a
   `completed_at` key); traced the ENH-1421 regression of BUG-942.
2. **Fix** — `cli/issues/list_cmd.py` now emits `completed_at` in `--json`
   (frontmatter + Resolution parse via `_parse_completion_date(...,
   batch_dates={})`, no per-file git subprocess); `commands/manage-release.md`
   Agent 2 compares on **date** and gained a **loud empty-result guard**;
   `cli/issues/set_status.py` stamps `completed_at` on `done`/cascade-to-done.
3. **Tests** — `test_json_output_contracts.py` (contract requires `completed_at`
   + reproduces the manage-release filter), `test_set_status_cli.py` (done
   stamps `completed_at`; non-terminal does not).
4. **Docs** — `docs/reference/json-output-contracts.md` documents the additive
   field.
5. **Traceability** — filed [[BUG-2558]] as the defect record.

## Status

**Done** — implemented on branch `fix/manage-release-completed-at-json`.

## Resolution

**Fixed**: 2026-07-09

The hardened filter now finds **26** issues completed since `v1.139.0`
(previously 0). All 2319 done issues carry a `completed_at` value in `--json`.
Full gate `python -m pytest scripts/tests/` → **14405 passed, 36 skipped**; ruff
and mypy clean on the changed files.

## Impact

- **Priority**: P2 — changelog automation silently produced empty release notes.
- **Effort**: Small — one CLI field, one command-prompt change, one data-gap close.
- **Risk**: Low — additive JSON field; isolated command-prompt change.
- **Breaking Change**: No.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-09T03:52:15 - `11b4a990-6665-4782-a360-644029312fa4.jsonl`
