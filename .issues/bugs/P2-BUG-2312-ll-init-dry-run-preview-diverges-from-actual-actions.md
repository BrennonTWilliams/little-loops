---
id: BUG-2312
title: "ll-init --dry-run preview diverges from actual --yes actions"
type: BUG
status: open
priority: P2
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- dry-run
---

# BUG-2312: ll-init --dry-run preview diverges from actual --yes actions

## Summary

`ll-init --dry-run` prints a preview that does not match what `--yes` actually
does: it lists issue subdirectories that are never created, omits one that is, and
skips several real write actions. A dry-run that misrepresents the plan defeats
its purpose.

## Current Behavior

`_print_dry_run` (`scripts/little_loops/init/cli.py:354-381`):

- Line 370 iterates `("bugs", "features", "enhancements", "completed", "deferred")`
  for `[mkdir]` lines — but `make_issue_dirs` actually creates
  `_ISSUE_SUBDIRS = ("bugs", "features", "enhancements", "epics")`
  (`scripts/little_loops/init/writers.py:54`). So the preview shows
  `completed`/`deferred` (never made) and hides `epics` (made).
- The preview omits actions `_run_yes` performs when enabled:
  `make_learning_tests_dir`, `deploy_design_tokens`, `deploy_issue_templates`,
  and the `Skill(ll:explore-api)` permission added to settings when
  learning_tests is enabled.

## Expected Behavior

Dry-run output enumerates exactly the directories and files `--yes` would create,
including learning-tests dir, design-token profiles, issue section templates, and
the explore-api permission (when those features are enabled).

## Root Cause

`_print_dry_run` hardcodes a stale subdir list and a partial action list instead
of deriving them from the same helpers `_run_yes` calls (`make_issue_dirs` uses
`_ISSUE_SUBDIRS`; the deploy/permission steps are gated on config flags).

## Proposed Fix

Drive the preview from `writers._ISSUE_SUBDIRS` rather than a literal, and mirror
the same config-gated branches `_run_yes` uses (learning_tests, design_tokens,
deploy_templates, explore-api permission). Consider routing dry-run through the
real writer functions with `dry_run=True` (they already support it) so preview and
execution share one code path and cannot drift again.

## Impact

Users relying on `--dry-run` to vet changes get a wrong picture: they see dirs
that won't exist and miss writes that will.

## Labels

- init, dry-run

## Session Log
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P2
