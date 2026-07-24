---
id: BUG-2755
status: open
captured_at: "2026-07-24T17:10:43Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
---

# BUG-2755: `ll-init --upgrade` silently drops into the wizard without `--yes`

## Summary

`ll-init --upgrade` (no `--yes`) does not perform an upgrade at all. `--upgrade`
is only wired into the headless `_run_yes`/`_run_plan` paths — the interactive
`run_tui()` path doesn't accept an `upgrade` parameter, so the flag is silently
dropped and the user gets the normal interactive wizard instead of an upgrade.

## Current Behavior

In `scripts/little_loops/init/cli.py:857-877`, dispatch is:

```python
if args.plan:
    return _run_plan(...)
if args.yes or args.dry_run:
    return _run_yes(..., upgrade=args.upgrade)
from little_loops.init.tui import run_tui
return run_tui(project_root=..., templates_dir=..., plugin_root=..., force=args.force, hosts=hosts)
```

`args.upgrade` is only ever passed into `_run_yes` (line 866). Running
`ll-init --upgrade` alone (without `--yes`) falls through to the `else` branch
and calls `run_tui()`, which has no `upgrade` parameter at all — the flag is
silently ignored and the user is dropped into the interactive setup wizard.

By contrast, `--enable`/`--disable` already guard against this exact class of
mistake (`cli.py:846-852`): they error out with "require --yes, --dry-run, or
--plan" instead of being silently swallowed by the wizard path.

## Expected Behavior

`ll-init --upgrade` without `--yes` should either:
- imply `--yes` (act non-interactively, since the whole point of `--upgrade` is
  to act automatically on version drift), or
- error out explicitly like the `--enable`/`--disable` guard does, telling the
  user `--upgrade` requires `--yes` (or `--plan`/`--dry-run`).

Silently entering the wizard, with the flag having no effect, is the wrong
behavior in both cases.

## Motivation

`--upgrade` exists specifically so users/scripts can non-interactively act on
version drift (auto-install/upgrade the package, force-regenerate host
adapters via `_dispatch_host_upgrade`). A user who runs `ll-init --upgrade`
expecting that behavior instead gets dumped into the wizard with no
indication their flag was ignored — a confusing, silent no-op.

## Proposed Solution

- **File**: `scripts/little_loops/init/cli.py`
- **Anchor**: dispatch block in `main_init()`, around lines 857-877
- Preferred: when `args.upgrade` is set and neither `args.yes` nor
  `args.dry_run`/`args.plan` is set, treat it as implying `--yes` (call
  `_run_yes(..., upgrade=True)` directly) — this matches the flag's stated
  intent ("Act on version drift automatically").
- Alternative: add the same guard pattern used for `--enable`/`--disable`
  (`cli.py:846-852`) that errors with a clear message when `--upgrade` is
  passed without `--yes`/`--dry-run`/`--plan`.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/cli.py` (dispatch logic in `main_init()`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/tui.py` — currently tells users to run
  `ll-init --upgrade` (line 235) as a refresh hint; that hint is misleading
  under current behavior and should keep working once fixed.

### Similar Patterns
- `--enable`/`--disable` guard at `cli.py:846-852` — reuse this pattern if
  going the error-out route.

### Tests
- `scripts/tests/` — add a test asserting `ll-init --upgrade` (no `--yes`)
  either performs the non-interactive upgrade path or errors, and never
  invokes `run_tui()`.

### Documentation
- N/A

## Implementation Steps

1. Decide imply-`--yes` vs explicit-error behavior for bare `--upgrade`.
2. Update the dispatch block in `main_init()` accordingly.
3. Add/update a regression test covering `ll-init --upgrade` without `--yes`.
4. Verify the `tui.py:235` "Refresh: `ll-init --upgrade`" hint still behaves as documented.

## Impact

- **Priority**: P3 - Confusing but not data-destructive; discovered via user question during a live session, not a user-reported failure.
- **Effort**: Small - Localized to the dispatch block in `main_init()`; ~5-10 line change plus a test.
- **Risk**: Low - Behavior-only change to an underused flag combination; no schema/config changes.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-24T17:10:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/671f7bf7-7469-47e9-9b97-b5b730223574.jsonl`

---
## Status
**Open** | Created: 2026-07-24 | Priority: P3
