---
id: BUG-2313
title: "ll-init apply is lossy vs --yes; apply --force is an unused no-op"
type: BUG
status: open
priority: P3
captured_at: "2026-06-26T21:55:52Z"
discovered_date: "2026-06-26"
discovered_by: capture-issue
labels:
- init
- apply
---

# BUG-2313: ll-init apply is lossy vs --yes; apply --force is an unused no-op

## Summary

The `ll-init --plan` → `ll-init apply` round-trip does not reproduce a full init,
even though the docs present it as the headless apply path. Separately, the `apply`
subcommand's `--force` flag is parsed but never used.

## Current Behavior

`_run_apply` (`scripts/little_loops/init/cli.py:420-464`) writes only:
config + issue dirs + goals + gitignore + settings.

It **skips** steps `_run_yes` performs: `write_claude_md`,
`make_learning_tests_dir`, `deploy_design_tokens`, `deploy_issue_templates`,
host-adapter dispatch (`_dispatch_host_adapters`), and `validate_deps`. So
`ll-init --plan > p.json && ll-init apply -c p.json` yields a materially different
result than `ll-init --yes`.

The `--force` argument is declared on the apply subparser (`cli.py:594-599`) and
threaded into `_run_apply(force=...)` (`cli.py:620-625`), but the body of
`_run_apply` never references `force` — so `apply --force` is a silent no-op.

## Expected Behavior

`apply` produces the same on-disk result as `--yes` for the same config (modulo
install/upgrade checks), or the docs/help clearly scope `apply` as a config-only
operation. `apply --force` either does something meaningful or is removed.

## Root Cause

`_run_apply` was implemented as a reduced subset of `_run_yes`'s write sequence
and the `force` parameter was wired through without a use site.

## Proposed Fix

Either (a) factor the shared write sequence out of `_run_yes` and reuse it in
`_run_apply` (preferred — single source of truth), or (b) explicitly document
`apply` as config+dirs+goals+gitignore+settings only. Remove `--force` from the
apply subparser if it has no semantics, or implement it (e.g. gate codex-adapter
overwrite / existing-file overwrite).

## Impact

Low–moderate: `--plan|apply` users get an incomplete install; the dead `--force`
flag misleads.

## Labels

- init, apply

## Session Log
- `/ll:capture-issue` - 2026-06-26T21:55:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/be6dde92-b804-455f-98d5-436aa89d6e00.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
