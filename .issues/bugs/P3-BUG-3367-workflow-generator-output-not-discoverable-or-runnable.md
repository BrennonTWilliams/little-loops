---
id: BUG-3367
type: BUG
title: workflow-generator output not discoverable or runnable
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-31'
captured_at: '2026-08-31T03:21:26Z'
---

# BUG-3367: workflow-generator output not discoverable or runnable

## Summary

The workflow-generator loop's generated FSM workflow is neither discoverable via
`ll-loop list` under its real name, nor runnable via `ll-loop run <run-dir-name>` —
and the CLI-native workaround suggested for this (`ll-loop install <path>`) does not
actually exist for arbitrary paths.

## Current Behavior

A generated workflow-generator draft (`.loops/runs/<instance_id>/workflow.yaml`,
internal `name:` e.g. `sample-brand-kit-synth`) is a dead end for discovery and
execution:

- `ll-loop list` never surfaces it under its internal `name:` — the catalog keys
  entries by relative path (`_rel_key`, `scripts/little_loops/cli/loop/info.py:105-107`),
  so a draft shows up (if at all) as an unrecognizable path like
  `runs/workflow-generator-20260830T220024/workflow`, not `sample-brand-kit-synth`.
- `ll-loop run <name>` cannot resolve a run-dir path or instance folder name to the
  `workflow.yaml` inside it — `resolve_loop_path`
  (`scripts/little_loops/fsm/loop_paths.py:19-40`) only checks a literal file path or
  `loops_dir/<name>{.fsm,}.yaml`/builtin lookups, none of which match a directory.
- `ll-loop install <path>` cannot promote the draft either — `cmd_install`
  (`scripts/little_loops/cli/loop/config_cmds.py:95-124`) only installs *built-in*
  loops by name and rejects an arbitrary filesystem path with "No built-in loop
  named ...".
- Even if a user manually promotes a draft by setting `context.auto_promote=true`,
  the generator's own `promote` step writes to `${context.loops_dir}` which
  defaults to `.ll/loops` — not the CLI's actual default loops dir (`.loops`,
  `scripts/little_loops/cli/loop/__init__.py:57`) — so the promoted loop still
  isn't discoverable via `ll-loop list`/`ll-loop run`.

The only working path today is invoking the literal file
(`ll-loop run .loops/runs/<instance>/workflow.yaml`), which is not surfaced
anywhere in the generator's output or in `ll-loop list`.

## Expected Behavior

At minimum, one of:
- `ll-loop list` surfaces unpromoted generator drafts under their internal `name:`
  (clearly marked as an unpromoted draft, with its run-dir path), and/or
- `ll-loop run <name>` resolves a draft loop's internal name to its `run_dir/workflow.yaml`
  path, and/or
- `ll-loop install <path>` accepts an arbitrary filesystem path (not just built-in loop
  names) so a generated draft can be promoted into `loops_dir` under a short name via a
  documented, working command.

Whichever fix is chosen, the generator's own `promote` step should have its
`context.loops_dir` default corrected to match the CLI's actual default (`.loops`, not
`.ll/loops`) so a fix to promotion doesn't silently land loops in an unused directory.

## Motivation

The workflow-generator loop exists to let a user turn a natural-language automation
request into a runnable FSM loop, but every generated draft is currently stranded:
it can't be found (`ll-loop list`), run (`ll-loop run <name>`), or promoted
(`ll-loop install <path>`) through any documented CLI-native path. Users must
already know the undocumented `.loops/runs/<instance_id>/workflow.yaml` path and
manually `cp` it into `.loops/` to get any value out of a generation run — this
defeats the point of having a generator loop at all and makes the feature look
broken on first use (as observed live — see Reproduction Steps below).

## Proposed Solution

Close all three CLI-side gaps so a generated draft is discoverable end-to-end,
and fix the generator's own config mismatch regardless of which gaps are closed:

1. **`ll-loop list`** — key catalog entries for loops under `runs/` by their
   internal `name:` field (already parsed to validate `is_runnable_loop`) instead
   of only `_rel_key`'s relative path, and mark them clearly as unpromoted drafts
   with their run-dir path shown alongside.
2. **`ll-loop run <name>`** — extend `resolve_loop_path` to also try
   `loops_dir/runs/<name>/workflow.yaml` (and the bare instance-folder name shown
   in the generator's own output) before falling through to "Loop not found".
3. **`ll-loop install <path>`** — accept an arbitrary filesystem path (not just a
   built-in loop name) and copy it into `loops_dir` under a derived or
   user-supplied short name, so a draft can be promoted without a manual `cp`.
4. **`workflow-generator.yaml`'s `promote` step** — correct its
   `context.loops_dir` default from `.ll/loops` to `.loops`, matching
   `scripts/little_loops/cli/loop/__init__.py:57`, so promotion (once reachable)
   lands drafts where the CLI actually looks.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `enumerate_loop_catalog`/`_rel_key`
  (lines 105-107, 151-222): key drafts under `runs/` by internal `name:`
- `scripts/little_loops/fsm/loop_paths.py` — `resolve_loop_path` (lines 19-40):
  add a run-dir/instance-name resolution branch
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_install` (lines 95-124):
  accept an arbitrary filesystem path, not just built-in loop names
- `scripts/little_loops/loops/workflow-generator.yaml` — `context.loops_dir`
  default (~line 48): change `.ll/loops` → `.loops`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:117` — calls `resolve_loop_path`; no
  change needed beyond the resolver itself, but its "Loop not found" error
  message should mention the new resolution path once added
- `scripts/little_loops/fsm/validation/structural_rules.py:1670-1695` —
  `is_runnable_loop`, used as the catalog filter; unaffected but worth
  confirming it still passes for `runs/` entries once they're surfaced

### Similar Patterns
- `get_builtin_loops_dir()` lookup in `cmd_install` — the existing built-in
  name resolution is the pattern to extend (not replace) when adding
  arbitrary-path support

### Tests
- `scripts/tests/test_builtin_loops.py` or a dedicated `test_loop_cli.py` —
  add cases for: `ll-loop list` surfacing a `runs/` draft under its `name:`,
  `ll-loop run` resolving a run-dir/instance name, `ll-loop install` accepting
  a filesystem path
- Regression test asserting `workflow-generator.yaml`'s `promote` step default
  matches the CLI's actual `.loops` default

### Documentation
- `docs/reference/CLI.md` — `ll-loop list`/`ll-loop run`/`ll-loop install`
  entries, once behavior changes

### Configuration
- N/A — the only config touched is the generator loop's own
  `context.loops_dir` default, already covered above

## Implementation Steps

1. Fix the `workflow-generator.yaml` `loops_dir` default mismatch
   (`.ll/loops` → `.loops`) — smallest, unconditional fix.
2. Extend `resolve_loop_path` to resolve a run-dir/instance name to its
   `workflow.yaml`.
3. Key `ll-loop list`'s catalog entries for `runs/` loops by internal `name:`,
   marked as unpromoted drafts.
4. Extend `cmd_install` to accept an arbitrary filesystem path and promote it
   into `loops_dir` under a short name.
5. Add regression tests for each of the above and verify against the
   reproduction steps.

## Impact

- **Priority**: P3 — usability/discoverability gap in a generator feature, not
  a correctness or data-loss bug; the workaround (manual file path/`cp`) exists
  but is undocumented.
- **Effort**: Medium — four small, independent fixes across three CLI modules
  plus one YAML default, each well-localized with no shared state between them.
- **Risk**: Low — additive path-resolution logic in `resolve_loop_path`/
  `cmd_install`/`enumerate_loop_catalog`; existing built-in/`.loops/<name>.yaml`
  resolution order is preserved, new checks only add fallback branches.
- **Breaking Change**: No — purely additive; no existing CLI behavior is
  removed or changed for already-discoverable loops.

## Root Cause

Two compounding gaps in the loop CLI, plus a config default mismatch in the generator loop itself:

1. **`ll-loop list` keys the catalog by relative path, not the loop's internal `name:`.**
   `enumerate_loop_catalog` (`scripts/little_loops/cli/loop/info.py:151-222`) does an
   unfiltered `loops_dir.rglob("*.yaml")` (line 175) with no exclusion for `runs/`,
   `.history/`, or `.running/`, filtered only by `is_runnable_loop`
   (`scripts/little_loops/fsm/validation/structural_rules.py:1670-1695`). The catalog key
   comes from `_rel_key` (`info.py:105-107`), e.g.
   `runs/workflow-generator-20260830T220024/workflow` — not the loop's own
   `name:` field (e.g. `sample-brand-kit-synth`) that a user would recognize.

2. **`ll-loop run <name>` never looks inside a directory for a `workflow.yaml`.**
   `resolve_loop_path` (`scripts/little_loops/fsm/loop_paths.py:19-40`, called from
   `cli/loop/run.py:117`) only checks, in order: literal path exists ->
   `loops_dir/<name>.fsm.yaml` -> `loops_dir/<name>.yaml` -> builtin `<name>.yaml`.
   Running `ll-loop run runs/workflow-generator-20260830T220024` (the natural thing to
   try after seeing the run directory) fails with "Loop not found" because none of
   those checks match a directory. The generated loop is only runnable by pointing at
   the literal file path (`ll-loop run .loops/runs/<instance>/workflow.yaml`), which is
   not surfaced anywhere in the generator's own output or in `ll-loop list`.

3. **`ll-loop install <path>` does not accept arbitrary filesystem paths.**
   `cmd_install` (`scripts/little_loops/cli/loop/config_cmds.py:95-124`) only installs
   *built-in* loops by name, looked up in `get_builtin_loops_dir()`, and errors
   "No built-in loop named ..." when given a run-dir path. There is currently no
   CLI-native way to promote/register a generator-produced draft under a short,
   runnable name — the only workaround is a manual `cp` into `.loops/<name>.yaml`.

4. **Separately, the generator's own `promote` step has a loops_dir default mismatch.**
   `scripts/little_loops/loops/workflow-generator.yaml` gates promotion behind
   `context.auto_promote` (default `"false"`, ~line 45), so by default a run stops at
   `await_confirmation` (~lines 943-947) and the draft never leaves `run_dir`. If
   `auto_promote` is ever set `true`, the `promote` step (~lines 859-897) copies into
   `${context.loops_dir}`, which defaults to `.ll/loops` (~line 48) — this does not
   match the CLI's actual default loops dir `.loops` (set at
   `scripts/little_loops/cli/loop/__init__.py:57`). A promoted loop would land in the
   wrong directory and still not be discoverable via `ll-loop list`/`ll-loop run`.

## Steps to Reproduce

1. Run the workflow-generator loop (e.g. `ll-loop run workflow-generator`) to
   completion with default settings (`auto_promote=false`).
2. Note it writes a draft to `.loops/runs/<instance_id>/workflow.yaml` with an
   internal `name:` (e.g. `sample-brand-kit-synth`).
3. Run `ll-loop list` — the draft does not appear under `sample-brand-kit-synth` (or
   any name a user would recognize as "the loop I just generated").
4. Run `ll-loop run runs/<instance_id>` (or the instance folder name shown in step 2's
   output) — fails with "Loop not found".
5. Try `ll-loop install .loops/runs/<instance_id>/workflow.yaml` as a workaround —
   fails with "No built-in loop named ...", since `install` only accepts built-in loop
   names.

Observed live on 2026-08-30 in a local-editable install of little-loops:
`workflow-generator` generated a loop named `sample-brand-kit-synth` under
`.loops/runs/workflow-generator-20260830T220024/`, which was not listed by
`ll-loop list` and not runnable by `ll-loop run runs/workflow-generator-20260830T220024`.
Confirmed via source investigation against this repo's current `main` — not stale/dated
behavior.

## Program Design

### Types

- No new types — fixes are behavioral changes to existing path-resolution
  functions.

### Signatures

- `enumerate_loop_catalog(loops_dir: Path) -> dict[str, LoopCatalogEntry]`
  (`scripts/little_loops/cli/loop/info.py:151`) — key `runs/`-nested entries
  by their parsed `name:` field instead of only `_rel_key(path)`.
- `resolve_loop_path(name: str, loops_dir: Path) -> Path | None`
  (`scripts/little_loops/fsm/loop_paths.py:19`) — add a check for
  `loops_dir/runs/<name>/workflow.yaml` alongside the existing
  `<name>.fsm.yaml`/`<name>.yaml`/builtin checks.
- `cmd_install(name_or_path: str, loops_dir: Path) -> int`
  (`scripts/little_loops/cli/loop/config_cmds.py:95`) — fall back to treating
  `name_or_path` as an arbitrary filesystem path when it isn't a known
  built-in loop name.

### Call Path

`ll-loop run <name>` -> `cli/loop/run.py:117` -> `resolve_loop_path()` ->
`runs/<name>/workflow.yaml`. Separately: `ll-loop list` -> `enumerate_loop_catalog()`
-> `_rel_key()`/`name:` lookup -> catalog entries shown to the user. Separately:
`ll-loop install <path>` -> `cmd_install()` -> `get_builtin_loops_dir()` lookup
(existing) -> new arbitrary-path fallback -> copy into `loops_dir`.

## Related Issues

- `P3-FEAT-2354` — designed the workflow-generator loop and its HITL-gated promotion
  (`context.auto_promote`), but did not address discoverability of unpromoted drafts or
  provide a working path-based install/promote path.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-31 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-08-31T03:25:45 - `58ca304a-54ac-44f8-bc17-9bdf9d83c13c.jsonl`
- `/ll:capture-issue` - 2026-08-31T03:21:32 - `41ef66dd-c959-46d5-a910-2bd5157e43bf.jsonl`
