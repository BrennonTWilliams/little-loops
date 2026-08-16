---
id: ENH-2977
title: Add a --timeout CLI flag to ll-auto, matching the existing --idle-timeout
type: ENH
priority: P3
status: open
parent: EPIC-3213
epic: EPIC-3213
discovered_date: 2026-08-01
discovered_by: human
relates_to:
- BUG-2976
- FEAT-488
- BUG-3034
labels:
- cli
- ll-auto
- ergonomics
testable: true
verify_verdict: NON_VALID
---

# ENH-2977: Add a --timeout CLI flag to ll-auto, matching the existing --idle-timeout

## Summary

`ll-auto` exposes `--idle-timeout` (which overrides
`config.automation.idle_timeout_seconds`) but has no matching `--timeout` for
`config.automation.timeout_seconds`. The per-issue wall-clock budget is
config-file-only: changing it for a single known-large issue requires editing
`.ll/ll-config.json` — a file that is per-project and, in many consuming
projects, gitignored — and then remembering to change it back.

FEAT-488 added `--idle-timeout` to `ll-auto` and `ll-parallel` for exactly this
reason. The sibling flag was not added, and that asymmetry is the core of this
issue. (An adjacent defect was previously folded in here — `ll-parallel
--timeout 0` not actually disabling the timeout — but that has since been
fixed separately as BUG-3034; see Scope Boundaries and Verification Notes.)

## Motivation

Raising the budget for one unusually large issue is a config edit plus a manual
revert, with no record in the invocation of what was actually run. The natural
gesture — `ll-auto --only FEAT-108 --timeout 7200` — does not exist, so the
recommended workaround in practice is to edit config and hope it is reverted.
Nothing surfaces the setting afterward: the run log shows the timeout only when
it is breached.

## Current Behavior

`scripts/little_loops/cli/auto.py` wires exactly one of the two:

```python
if args.idle_timeout is not None:
    config.automation.idle_timeout_seconds = args.idle_timeout
```

`AutomationConfig` (`scripts/little_loops/config/automation.py`) defines both
`timeout_seconds: int = 7200` and `idle_timeout_seconds: int = 0`, and
`from_dict()` reads both from `.ll/ll-config.json`. Only the idle one has a
CLI override.

## Expected Behavior

`ll-auto --timeout N` sets `config.automation.timeout_seconds` for that
invocation, with the same precedence and shape as `--idle-timeout`:

- Absent (`None`) → the config value, else the `7200` default. Unchanged
  behavior for every existing invocation.
- `--timeout 0` → no wall-clock timeout, consistent with how `0` already
  disables `idle_timeout_seconds` and with `run_claude_command`'s documented
  `timeout: Timeout in seconds (0 for no timeout)`. This is honored at the
  bottom of the stack: `subprocess_utils.py:465` guards with
  `if timeout and (now - start_time) > timeout`, so a falsy `0` never fires.
- `--timeout -N` (any negative) → `parser.error()`. Without a guard, the same
  `if timeout and ... > timeout` check is immediately true and every issue
  instant-fails. The two adjacent overrides in `cli/auto.py`
  (`--handoff-threshold`, `--context-limit`, `auto.py:83-92`) both already
  `parser.error()` on out-of-range input; this follows them.
- `-t` is registered as a short alias, because `add_timeout_arg`
  (`cli_args.py:110,118`) declares `"--timeout", "-t"`. This is a **new short
  flag on `ll-auto`**, which today uses only `-r -n -m -q -c -p -v` — no
  collision, but it is a real addition to the CLI surface and must appear in
  the docs flag table alongside `--timeout`.
- Help text states the unit (seconds) and that the budget is **per issue**, not
  per run. The helper's current text is the bare string `"Timeout in seconds"`,
  so satisfying this means editing `add_timeout_arg` itself — which also
  changes `ll-parallel --help`. That is intended and correct (the value is
  `timeout_per_issue` there too). Target wording, matching the
  `--idle-timeout` register: `"Per-issue timeout in seconds (0 to disable,
  default: from config)"`.

## Scope Boundaries

**In scope:**

1. The `--timeout` flag on `ll-auto` (via `add_timeout_arg` in
   `add_common_auto_args`), plus its `is not None` assignment and negative-value
   `parser.error()` guard in `cli/auto.py`.
2. The shared help-text update in `add_timeout_arg` (`cli_args.py:100-122`),
   which necessarily also affects `ll-parallel --help`.

> Resolved by research (see Integration Map → Codebase Research Findings):
> `ll-parallel` already declares `--timeout` (`cli/parallel.py:172,259`), so no
> new flag is needed there.

> ~~The `--timeout 0` truthiness fix at `config/core.py:576`~~ — struck
> 2026-08-12. This sub-scope (the "`ll-parallel --timeout 0` defect") has
> already been fixed separately as BUG-3034; `config/core.py` now uses the
> `is not None` form. See Verification Notes.

**Out of scope:**

- Changing the `7200` default.
- Per-phase budgets (splitting implementation from finalization).
- The timeout *handling* defect — that a breach currently aborts the whole run
  and deletes the resume state — which is BUG-2976. This issue only makes the
  existing budget settable from the command line; it does not change what
  happens when the budget is breached. Landing this without BUG-2976 makes it
  easier to avoid the crash, not safer when it happens.

## Backwards Compatibility

Fully backwards compatible. The flag defaults to `None`, leaving the existing
config→default resolution untouched, so no current invocation changes behavior.

## Program Design

### Types

- `timeout: int | None` — the new `argparse.Namespace` attribute; `None` when
  the flag is omitted.
- `timeout_seconds: int` — the existing `AutomationConfig` field it assigns to.

### Signatures

- `add_timeout_arg(parser: argparse.ArgumentParser, default: int | None = None) -> None`
  — already exists (`cli_args.py:100-122`); called from `add_common_auto_args`
  with no `default`, so the `default=None` branch applies. Only its `help=`
  string changes.
- `add_common_auto_args(parser: argparse.ArgumentParser) -> None` — unchanged
  signature; gains one `add_timeout_arg(parser)` call and a docstring line.
- `create_parallel_config(..., timeout_seconds: int | None = None, ...) -> ParallelConfig`
  (`config/core.py:525`) — unchanged signature; the body's `or` fallback at
  line 576 becomes an `is not None` check.
- `from_dict(cls, data: dict[str, Any]) -> AutomationConfig` — unchanged; the
  CLI override is applied after config load, not inside it.

### Call Path

`ll-auto` entry point -> `cli/auto.py` argument parsing ->
`config.automation.timeout_seconds = args.timeout` (guarded by
`if args.timeout is not None:`, immediately alongside the existing
`args.idle_timeout` block at `auto.py:80-81`) -> `AutoManager` ->
`process_issue_inplace()` ->
`run_claude_command(timeout=config.automation.timeout_seconds, ...)` ->
`subprocess_utils.py:465` `if timeout and (now - start_time) > timeout`.

No signature changes below the CLI layer — every consumer already reads the
value off `config.automation`.

**Blast radius is minimal and bounded**: `add_common_auto_args` has exactly one
caller in the entire tree (`cli/auto.py:55`), so adding a flag to it cannot
affect any other entry point. `add_timeout_arg` has one other caller,
`add_common_parallel_args` (`cli_args.py:526`), which is the intended and only
side effect of the help-text change.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli_args.py` — add `add_timeout_arg(parser)` to
  `add_common_auto_args` (alongside the `add_idle_timeout_arg(parser)` call at
  line 512); update that function's docstring flag list (lines 496-499); update
  the `help=` string in `add_timeout_arg` (lines 100-122, both branches).
- `scripts/little_loops/cli/auto.py` — the `if args.timeout is not None:`
  config assignment next to the existing `--idle-timeout` block
  (lines 80-81), plus the negative-value `parser.error()` guard.
- `scripts/little_loops/config/core.py` — line 576, `or` → `is not None`
  (the `--timeout 0` defect).

**No `cli/parallel.py` change**: `--timeout` is already declared
(`parallel.py:172`) and already flows to the config
(`parallel.py:259`). Its `0` bug lives in `core.py`, not here.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py` — reads
  `config.automation.timeout_seconds` at four `run_claude_command()` sites
  (lines 795, 862, 1056, 1158); no change.
- `scripts/little_loops/cli/sprint/run.py` — also consumes
  `automation.timeout_seconds` and absorbs its `TimeoutExpired` (see the
  BUG-2976 comment at lines 101-108); no change, and `ll-sprint` gaining its
  own `--timeout` is not in scope.
- `scripts/little_loops/loops/autodev.yaml` and any other caller shelling out
  to `ll-auto` — unaffected; the flag is additive and optional.

### Similar Patterns

- The `--idle-timeout` block in `cli/auto.py` (lines 80-81) is the template for
  the config assignment; the `--handoff-threshold` / `--context-limit` blocks
  immediately below it (lines 83-92) are the template for the negative-value
  `parser.error()` guard.
- `config/core.py:577-579` — the `idle_timeout_per_issue` argument in the very
  same `ParallelConfig(...)` call already uses the correct
  `if ... is not None else` form. It is the in-place model for the line-576
  fix.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The shared-helper question above is already answered: `add_timeout_arg(parser,
  default=None)` exists at `scripts/little_loops/cli_args.py:100-122`, styled
  to mirror `add_idle_timeout_arg` (`cli_args.py:125-136`) exactly — same
  `default=None` / `type=int` shape, same "N seconds" help-text register. It
  is exported in `__all__` (`cli_args.py:550`) but currently has exactly one
  caller in the whole tree: `add_common_parallel_args`
  (`cli_args.py:517-534`, calls it at line 526). No code path adds it to
  `add_common_auto_args` (`cli_args.py:496-514`). This changes the shape of
  the fix: the implementer does not need to write a new `argparse.add_argument`
  block in `cli/auto.py` — the flag declaration already exists and needs only
  to be called from `add_common_auto_args`, alongside the existing
  `add_idle_timeout_arg(parser)` call at `cli_args.py:512`.
- **This resolves the Scope Boundaries question below about `ll-parallel`.**
  `scripts/little_loops/cli/parallel.py` already has `--timeout` fully wired
  — `add_timeout_arg(parser)` is called at `parallel.py:172`, and the parsed
  value flows to `timeout_seconds=args.timeout` in the parallel config at
  `parallel.py:259` (alongside `idle_timeout_per_issue=args.idle_timeout` at
  line 260). `ll-parallel --timeout` is not a *declaration* gap; the flag ships
  today. **Corrected on review:** its `0` value is nonetheless swallowed by an
  `or` fallback one layer down at `config/core.py:576`, so `--timeout 0` there
  silently resolves to the config default rather than disabling the timeout.
  That one-line fix is now in scope; see Scope Boundaries → "The `ll-parallel
  --timeout 0` defect". The flag-declaration asymmetry remains `ll-auto`-only,
  because `cli/auto.py` calls `add_common_auto_args`
  (`auto.py:58`, wired via `cli_args.py:496-514`) rather than
  `add_common_parallel_args`, and that helper never picked up
  `add_timeout_arg`. No `parallel.py` change is needed for this issue.
- Once `add_timeout_arg(parser)` is added to `add_common_auto_args`, the
  `config.automation.timeout_seconds = args.timeout` assignment belongs in
  `cli/auto.py` right next to the existing `if args.idle_timeout is not None:`
  block (`auto.py:78-79`), following the identical `is not None` guard shape
  already used there.

### Tests

- `scripts/tests/test_cli_args.py` is the actual coverage location (not a
  `test_cli_auto.py`, which does not exist in this tree) — specifically
  `TestAddCommonAutoArgs.test_adds_all_expected_arguments`
  (`test_cli_args.py:748-786`), which currently parses `--idle-timeout` and
  `--handoff-threshold` but has no `--timeout` case. `TestAddCommonParallelArgs`
  (`test_cli_args.py:789-827`) already exercises the identical assertion
  (`assert args.timeout == 1800`, line 820) for the parallel side — the
  pattern to mirror for the auto-side test. That test's own docstring
  (line 749) enumerates the flags it covers and needs `timeout` added.
- `--timeout N` reaches `config.automation.timeout_seconds`; omitting it
  leaves the config/default value intact; `--timeout 0` is preserved as `0`
  rather than being coerced to the default by a falsy check.
- `--timeout -1` (and any negative) exits with the `argparse` usage error
  (status 2), the same shape as the existing `--handoff-threshold` /
  `--context-limit` range tests.
- `-t 900` parses identically to `--timeout 900` on `ll-auto` (pins the new
  short alias).
- **`create_parallel_config(timeout_seconds=0)` yields
  `timeout_per_issue == 0`, not the config default** — the regression test for
  the `core.py:576` fix. Its sibling assertion (a `None` argument still falls
  back to `parallel.base.timeout_seconds`) must be kept or added so the fix
  can't regress in the other direction.

### Documentation

- **`docs/reference/CLI.md:344`** — the canonical CLI reference per
  `.claude/CLAUDE.md`. Add a `--timeout` row with the `-t` short flag to the
  `ll-auto` flag table, directly adjacent to the existing `--idle-timeout` row.
  Check the `ll-parallel` table's `--timeout` row (line 402) still matches the
  new shared help text.
- `docs/reference/CONFIGURATION.md` — note the CLI override next to
  `automation.timeout_seconds`.
- `CHANGELOG.md` — new entry. Per project convention, do not file it under
  `[Unreleased]`; put it in a concrete version section.

### Configuration

- No schema change; the config key already exists.

## Impact

- **Priority**: P3 — mostly ergonomics with an existing workaround, though the
  folded-in `core.py:576` item is a genuine (if narrow) defect in shipped
  `ll-parallel` behavior. BUG-2976 is still where the real risk sits.
- **Effort**: Small — one helper call, one assignment, one guard, one
  one-line bug fix, and their tests, all mirroring code that already exists a
  few lines away.
- **Risk**: Low — additive and opt-in on the `ll-auto` side. The trap is a
  `if args.timeout:` truthiness check silently discarding `--timeout 0`; the
  `is not None` idiom avoids it and the tests pin it. Note this trap is not
  hypothetical — it is the exact shape of the live `core.py:576` bug now in
  scope.
- **Breaking Change**: No. The `core.py:576` fix changes behavior only for
  `ll-parallel --timeout 0`, which today silently does the opposite of what it
  says; no invocation relying on documented behavior is affected.

## Status

**Open** | Created: 2026-08-01 | Priority: P3

Filed alongside BUG-2976 after reviewing a recovery plan for a timed-out
`ll-auto --only FEAT-108` run in a downstream project. The plan's remedy for
the timeout was a `.ll/ll-config.json` edit precisely because no CLI override
exists.


## Related Key Documentation

- `docs/reference/CLI.md` — the full `ll-*` CLI reference and the flag table
  this change must land in (`ll-auto` at line 344). `.claude/CLAUDE.md` names
  it authoritative, with `<cmd> --help` winning over any prose.
- `docs/reference/API.md` — documents the `cli/*` entry points (including
  `ll-auto`) whose argument wiring (`cli_args.py`, `cli/auto.py`) this issue
  modifies.

> Correction: an earlier revision of this section pointed at a "CLI Tools
> catalog" bullet for `ll-auto` in `.claude/CLAUDE.md`. No such catalog
> exists — `ll-auto` appears there exactly once, in the Automation/Scratch Pad
> section, with no flag list. `.claude/CLAUDE.md` needs no edit for this issue.

## Verification Notes

**2026-08-12** (`/ll:verify-issues`): The folded-in `ll-parallel --timeout 0`
truthiness sub-scope (`config/core.py:576`) was already fixed by a separate
commit that closed BUG-3034 — `config/core.py` now uses the `is not None`
form — so that item is struck from Scope Boundaries. The cited
`AutomationConfig.timeout_seconds` default was also stale (`3600` →
now `7200`, per commit `1405c21b`) and has been corrected. The core ask —
adding a `--timeout` CLI flag to `ll-auto` — remains valid and open.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:18:53 - `52bc5a67-0032-4383-ae03-a6de98447a01.jsonl`
