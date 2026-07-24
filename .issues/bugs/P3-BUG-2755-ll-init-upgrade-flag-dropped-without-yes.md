---
id: BUG-2755
status: done
captured_at: '2026-07-24T17:10:43Z'
completed_at: '2026-07-24T17:43:26Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 75
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 10
score_change_surface: 23
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed exact locations: `--upgrade` arg def (`cli.py:771-778`, plain
  `store_true`, no companion validation unlike `--enable`/`--disable`),
  `--enable`/`--disable` guard (`cli.py:840-852`), terminal dispatch block
  (`cli.py:854-877`), `_run_yes()` upgrade handling (`cli.py:251-260`,
  `312-399`, `501-508`), `_dispatch_host_upgrade()` def (`cli.py:113-163`).
- **`_run_plan()` has the same gap as `run_tui()`**: its signature
  (`cli.py:525-529`) also has no `upgrade` parameter, and it never calls
  `_dispatch_host_upgrade()` or any upgrade-triggering logic. So
  `ll-init --plan --upgrade` *also* silently drops `--upgrade` today — the
  bug isn't limited to the bare-flag/wizard case described above; it's any
  dispatch path except `--yes`/`--dry-run`.
- `_dispatch_host_upgrade()` is invoked from exactly one call site
  (`cli.py:504`, inside `_run_yes()`, guarded by `if upgrade and not
  dry_run:`). Since `--dry-run` short-circuits it via `and not dry_run`, the
  *only* invocation that actually executes `_dispatch_host_upgrade()` today
  is `ll-init --yes --upgrade` (non-dry-run).
- `run_tui()` has its own, unrelated non-interactive guard (`tui.py:138-143`)
  that checks `sys.stdin.isatty()` and prints a `--yes` hint, returning `1`.
  This is a *different* idiom (TTY-based, inside `run_tui`, exit code 1) from
  the `--enable`/`--disable` guard (argument-based, inside `main_init`, exit
  code 2) — two non-interactive-guard conventions already coexist in this
  file; a new `--upgrade` guard should follow the `main_init`/exit-2 idiom
  since it's an argument-combination check, not a TTY check.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

If going the error-out (Alternative) route, the exact guard to mirror is
`cli.py:840-852`:

```python
if feature_choices and not (args.plan or args.yes or args.dry_run):
    print(
        "Error: --enable/--disable require --yes, --dry-run, or --plan "
        "(the interactive wizard uses its own feature checkboxes).",
        file=sys.stderr,
    )
    return 2
```

The `--upgrade` equivalent would be inserted in the same spot (before the
terminal dispatch block at `cli.py:854`):

```python
if args.upgrade and not (args.plan or args.yes or args.dry_run):
    print(
        "Error: --upgrade requires --yes, --dry-run, or --plan "
        "(bare --upgrade would otherwise silently fall through to the "
        "interactive wizard, which has no upgrade parameter).",
        file=sys.stderr,
    )
    return 2
```

Note this file uses `print(..., file=sys.stderr); return 2` uniformly for
these argument-combination guards — not `parser.error()` or `sys.exit()` —
and `main_init()`'s return value becomes the process exit code.

If going the Preferred (imply-`--yes`) route instead, remember `_run_plan()`
also needs the fix (see Current Behavior findings above): `--plan --upgrade`
should either thread `upgrade` into `_run_plan()` or also imply `--yes`
handling for the upgrade-detection side, since `_run_plan()` currently never
calls `_dispatch_host_upgrade()` at all.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Add the new test to `scripts/tests/test_init_core.py`, `TestMainInit`
  class (starts at line 1426), alongside the existing guard/flag tests.
- **Guard-route template** (if choosing the error-out Alternative):
  `test_feature_flags_require_headless_mode()` at
  `test_init_core.py:1696-1704` — patches only `_plugin_root`, asserts
  `code == 2` and an expected substring (`"--yes"`) in
  `capsys.readouterr().err`. A sibling test,
  `test_unknown_feature_flag_exits_2()` (lines 1685-1694), additionally
  asserts *no side effect* occurred via
  `assert not (tmp_project / ".ll" / "ll-config.json").exists()` — the
  closest existing idiom to "the wizard never ran," since no test in this
  file mocks `run_tui` directly with `assert_not_called()`.
- **Imply-`--yes`-route template** (if choosing Preferred): existing
  `--upgrade`-with-`--yes` behavioral tests already establish the mocking
  scaffold to reuse — `test_yes_warns_when_pypi_stale_without_upgrade_flag()`
  (lines 2018-2043) and `test_yes_upgrades_when_pypi_stale_with_upgrade_flag()`
  (lines 2045-2073), which patch `_plugin_root`,
  `install_check.detect_installation`, `install_check.fetch_latest_pypi`,
  and `cli._subprocess.run` to capture the `pip install --upgrade` call.
- **Mocking caveat**: `run_tui` is imported *locally* inside `main_init()`
  (`cli.py:869-871`, `from little_loops.init.tui import run_tui`), not at
  module scope. A test wanting to assert non-invocation must patch
  `little_loops.init.tui.run_tui` (the source), not
  `little_loops.init.cli.run_tui` — patching the latter after the local
  import already executed would be a no-op. The existing tests sidestep
  this entirely by asserting via exit code + stderr/artifact-absence
  instead (see `test_no_args_launches_tui_non_tty()`, lines 1427-1435, for
  the pattern).
- Related test files (present but not yet touched for this bug):
  `scripts/tests/test_init_tui.py` (wizard-side tests),
  `scripts/tests/integration/test_init_e2e.py` (end-to-end init flow).
- **Confirmed by `/ll:wire-issue` test-gap pass**: no existing test currently
  asserts that bare `--upgrade` (no `--yes`) falls through to `run_tui()` —
  the only fallthrough test, `test_no_args_launches_tui_non_tty`
  (`test_init_core.py:1427`), calls `main_init([])` with zero flags, not
  `--upgrade`. Neither fix approach breaks an existing assertion.
  `test_init_tui.py::TestNonTTY.test_non_tty_returns_1` (line 139) calls
  `run_tui()` directly and is `--upgrade`-unaware; `test_init_e2e.py` has no
  `--upgrade` coverage at all. `TestDispatchHostUpgrade` (`test_init_core.py`
  ~line 2442) tests `_dispatch_host_upgrade()` directly, bypassing
  `main_init()`'s dispatch — unaffected by this fix either way.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:52` — `--upgrade` row describes behavior but never
  states the `--yes`/`--dry-run`/`--plan` precondition (contrast the
  `--enable`/`--disable` row at line 50, which already says "Requires
  `--yes`/`--dry-run`/`--plan`"). Needs the same caveat once the fix lands.
- `docs/guides/GETTING_STARTED.md:99,126,130,131` — the `--upgrade` flag
  table row and all three "Existing Installation Detection" table rows say
  "pass `--upgrade` to …" with no mention that `--upgrade` alone (no `--yes`)
  currently/previously no-ops into the wizard. Needs the same precondition
  note.
- `docs/codex/getting-started.md:125` — instructs users to run bare
  `ll-init --upgrade` (no `--yes`) as the remedy for a stale
  `.codex/hooks.json` — this is the exact silently-broken invocation this bug
  describes. Must be updated to match whichever fix is chosen (either the
  instruction becomes correct for free under the imply-`--yes` route, or it
  needs `--yes` added if the explicit-error route is chosen).
- `skills/init/SKILL.md:140` — `## Related` section hardcodes the anchor
  `scripts/little_loops/init/cli.py:525-573` (`_run_plan`) and `:595-677`
  (`_run_apply`). If the fix shifts line numbers in `cli.py` (new guard block
  or widened `_run_plan()` signature), this anchor goes stale and needs
  updating.

## Implementation Steps

1. Decide imply-`--yes` vs explicit-error behavior for bare `--upgrade`.
2. Update the dispatch block in `main_init()` accordingly.
3. Also handle `--plan --upgrade` (`_run_plan()` at `cli.py:525-529` never
   consumes `upgrade` either — same class of silent drop, per Current
   Behavior research findings above).
4. Add/update a regression test covering `ll-init --upgrade` without `--yes`
   in `scripts/tests/test_init_core.py::TestMainInit` (see Integration Map →
   Tests → Codebase Research Findings for the exact template to follow), plus
   a companion test confirming bare `main_init([])` (no flags at all) still
   falls through to `run_tui()` unchanged — pins the fix as scoped to
   `--upgrade` only.
5. Verify the `tui.py:235` "Refresh: `ll-init --upgrade`" hint still behaves as documented.
6. Update the four documentation touchpoints above (`CLI.md`,
   `GETTING_STARTED.md`, `codex/getting-started.md`,
   `skills/init/SKILL.md`'s anchor) to reflect the fixed behavior and any
   shifted line numbers.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Confirm `_run_plan()`'s only call site (`cli.py:855`, inside `main_init()`)
   is updated consistently if its signature grows an `upgrade` param — no
   other module or test calls `_run_plan()` directly, so this is a
   zero-fallout signature change (confirmed via caller trace).
8. No config-schema or `.ll/ll-config.json` changes needed — `--upgrade` is
   confirmed CLI-argument-only, no corresponding config key exists
   (cross-referenced against ENH-2256, the flag's origin issue).
9. No changes needed to `scripts/little_loops/cli/__init__.py` (re-exports
   `main_init` unchanged) or `.claude-plugin/plugin.json` /
   `scripts/pyproject.toml` (entry-point registration unaffected) — confirmed
   via caller trace, listed here to record that they were checked and ruled
   out, not omitted by oversight.

## Impact

- **Priority**: P3 - Confusing but not data-destructive; discovered via user question during a live session, not a user-reported failure.
- **Effort**: Small - Localized to the dispatch block in `main_init()`; ~5-10 line change plus a test.
- **Risk**: Low - Behavior-only change to an underused flag combination; no schema/config changes.
- **Breaking Change**: No

## Resolution

Implemented the Preferred (imply-`--yes`) fix from the plan:

- `scripts/little_loops/init/cli.py:857` — dispatch condition changed from
  `if args.yes or args.dry_run:` to `if args.yes or args.dry_run or
  args.upgrade:`. Bare `ll-init --upgrade` now runs headlessly through
  `_run_yes(..., upgrade=True)` instead of silently falling through to
  `run_tui()`.
- `_run_plan()` gained an `upgrade: bool = False` parameter and now echoes it
  as `requested_upgrade` in the emitted plan JSON (`--plan --upgrade` no
  longer silently drops the flag with no visible trace — plan mode still
  performs no writes/actions by design, but the flag is no longer invisible).
- Docs updated: `docs/reference/CLI.md` (`--plan` and `--upgrade` rows),
  `docs/guides/GETTING_STARTED.md` (`--upgrade` row), `skills/init/SKILL.md`
  (shifted `_run_plan`/`_run_apply` line-number anchors). No change needed to
  `docs/codex/getting-started.md:125` — its bare `ll-init --upgrade`
  instruction is now correct behavior for free.
- Tests added to `scripts/tests/test_init_core.py::TestMainInit`:
  `test_bare_upgrade_implies_yes_never_launches_wizard` and
  `test_plan_upgrade_surfaces_requested_upgrade`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:manage-issue` - 2026-07-24T17:42:55 - `b07d9f2a-ea28-415d-aef1-9ae548aa9883.jsonl`
- `/ll:ready-issue` - 2026-07-24T17:36:06 - `37102d19-ddc2-4245-8e2d-6c669c5937f3.jsonl`
- `/ll:confidence-check` - 2026-07-24T17:40:00 - `35fb47a9-9572-41e7-a183-3fb1b159bfc8.jsonl`
- `/ll:wire-issue` - 2026-07-24T17:33:19 - `374e3022-6315-4905-8370-61f32a5d0436.jsonl`
- `/ll:refine-issue` - 2026-07-24T17:28:29 - `13fb66b9-b02b-43c7-becf-456fc20ec8a1.jsonl`
- `/ll:capture-issue` - 2026-07-24T17:10:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/671f7bf7-7469-47e9-9b97-b5b730223574.jsonl`

---
## Status
**Open** | Created: 2026-07-24 | Priority: P3
