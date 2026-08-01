---
id: ENH-2977
title: Add a --timeout CLI flag to ll-auto, matching the existing --idle-timeout
type: ENH
priority: P3
status: open
discovered_date: 2026-08-01
discovered_by: human
relates_to:
- BUG-2976
- FEAT-488
labels:
- cli
- ll-auto
- ergonomics
testable: true
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
reason. The sibling flag was not added, and the asymmetry is the whole of this
issue.

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
`timeout_seconds: int = 3600` and `idle_timeout_seconds: int = 0`, and
`from_dict()` reads both from `.ll/ll-config.json`. Only the idle one has a
CLI override.

## Expected Behavior

`ll-auto --timeout N` sets `config.automation.timeout_seconds` for that
invocation, with the same precedence and shape as `--idle-timeout`:

- Absent (`None`) → the config value, else the `3600` default. Unchanged
  behavior for every existing invocation.
- `--timeout 0` → no wall-clock timeout, consistent with how `0` already
  disables `idle_timeout_seconds` and with `run_claude_command`'s documented
  `timeout: Timeout in seconds (0 for no timeout)`.
- Help text states the unit (seconds) and that the budget is **per issue**, not
  per run.

## Scope Boundaries

**In scope:** the `--timeout` flag on `ll-auto`, and the same flag on
`ll-parallel` if and only if `--idle-timeout` is already wired there (FEAT-488
covered both; verify rather than assume) — the point of this issue is
symmetry, so a half-symmetric result would be worse than none.

> Resolved by research (see Integration Map → Codebase Research Findings):
> `ll-parallel` already has `--timeout` (`cli/parallel.py:172,259`). Scope is
> `ll-auto` only — no `parallel.py` change is in scope for this issue.

**Out of scope:**

- Changing the `3600` default.
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

- `add_argument("--timeout", type=int, default=None, metavar=SECONDS) -> Action`
  — the `argparse` declaration added in `scripts/little_loops/cli/auto.py`,
  mirroring the existing `--idle-timeout` line verbatim in style and help-text
  shape.
- `from_dict(cls, data: dict[str, Any]) -> AutomationConfig` — unchanged; the
  CLI override is applied after config load, not inside it.

### Call Path

`ll-auto` entry point -> `cli/auto.py` argument parsing ->
`config.automation.timeout_seconds = args.timeout` (guarded by
`if args.timeout is not None:`, immediately alongside the existing
`args.idle_timeout` block) -> `AutoManager` -> `process_issue_inplace()` ->
`run_claude_command(timeout=config.automation.timeout_seconds, ...)`.

No signature changes below the CLI layer — every consumer already reads the
value off `config.automation`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/auto.py` — flag declaration and the one-line
  config assignment.
- `scripts/little_loops/cli/parallel.py` — same, conditional on
  `--idle-timeout` already being present there.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py` — reads
  `config.automation.timeout_seconds` at four `run_claude_command()` sites;
  no change.
- `scripts/little_loops/loops/autodev.yaml` and any other caller shelling out
  to `ll-auto` — unaffected; the flag is additive and optional.

### Similar Patterns

- The `--idle-timeout` block in `cli/auto.py` is the template to copy.
- `scripts/little_loops/cli_args.py` — check whether the shared-argument
  helpers are the right home for a paired timeout-flag helper before
  duplicating the declaration across `auto.py` and `parallel.py`.

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
  line 260). `ll-parallel --timeout` is not a gap; it ships today. The only
  asymmetry is `ll-auto`, because `cli/auto.py` calls `add_common_auto_args`
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
  pattern to mirror for the auto-side test.
- `--timeout N` reaches `config.automation.timeout_seconds`; omitting it
  leaves the config/default value intact; `--timeout 0` is preserved as `0`
  rather than being coerced to the default by a falsy check.

### Documentation

- `docs/reference/CONFIGURATION.md` — note the CLI override next to
  `automation.timeout_seconds`.
- `ll-auto --help` output, wherever it is mirrored in docs.
- `CHANGELOG.md` — new entry.

### Configuration

- No schema change; the config key already exists.

## Impact

- **Priority**: P3 — pure ergonomics with an existing workaround. It is a
  papercut, not a defect; BUG-2976 is where the real risk sits.
- **Effort**: Small — one flag, one assignment, one test, mirroring code that
  already exists a few lines away.
- **Risk**: Low — additive and opt-in. The only real trap is a `if
  args.timeout:` truthiness check silently discarding `--timeout 0`; the
  existing `is not None` idiom avoids it and the test pins it.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-01 | Priority: P3

Filed alongside BUG-2976 after reviewing a recovery plan for a timed-out
`ll-auto --only FEAT-108` run in a downstream project. The plan's remedy for
the timeout was a `.ll/ll-config.json` edit precisely because no CLI override
exists.


## Session Log
- `/ll:refine-issue` - 2026-08-01T20:18:53 - `52bc5a67-0032-4383-ae03-a6de98447a01.jsonl`
