---
id: BUG-3367
type: BUG
title: workflow-generator output not discoverable or runnable
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-31'
captured_at: '2026-08-31T03:21:26Z'
completed_at: '2026-08-31T05:35:50Z'
confidence_score: 100
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 22
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

**Contract: whatever identifier `ll-loop list` displays for a draft, `ll-loop run`
must resolve.** Concretely:

- `ll-loop list` surfaces unpromoted generator drafts under their internal `name:`
  (clearly marked as an unpromoted draft, with the run-dir path shown alongside), and
- `ll-loop run <name>` resolves both a draft's internal `name:` and its instance-folder
  name (`runs/<instance_id>`) to the `run_dir/workflow.yaml` path, and
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

1. **`ll-loop list`** — key catalog entries for drafts by their internal `name:`
   field instead of only `_rel_key`'s relative path, and mark them clearly as
   unpromoted drafts with their run-dir path shown alongside.
   - **Draft scope**: only files matching `runs/*/workflow.yaml` count as drafts.
     Other runnable YAMLs under `runs/` (eval-harness copies, run artifacts) are
     *excluded* from the catalog — today's behavior of surfacing them under an
     unrecognizable path key is part of the bug, not something to preserve.
   - **Duplicate names**: reruns of the generator produce multiple drafts with the
     same internal `name:`. The catalog shows only the *latest* draft per name
     (newest `workflow.yaml` mtime); older same-named drafts are not listed.
   - **Badge/visibility**: introduce a `draft` visibility tier rendered via the
     existing `◆ <word>` badge convention (`_badge_for()`, `cli/loop/info.py:475-483`).
     Drafts are *hidden* under the default `visibilities={"public"}` filter and
     shown via a new `--drafts` flag (mirroring `--internal`/`--examples`), with a
     hidden-count footer hint. This keeps `ll-loop list` from growing unboundedly
     as historical runs accumulate. Note: drafts flow through the shared
     `enumerate_loop_catalog()` into the MCP `loop_list` tool as well
     (`test_feat_3352_mcp_loop_list.py`) — the MCP tool inherits the same
     default-hidden behavior.
2. **`ll-loop run <name>`** — extend `resolve_loop_path` with two fallback
   branches, both *after* the existing literal-path/`<name>.fsm.yaml`/`<name>.yaml`/
   builtin checks so no existing name changes meaning:
   - `loops_dir/runs/<name>/workflow.yaml` (instance-folder name), then
   - a scan of `loops_dir/runs/*/workflow.yaml` for a file whose internal `name:`
     matches — resolving to the *latest* match by mtime when duplicates exist
     (same policy as `list`), with a stderr note when older same-named drafts
     were skipped.
   The terminal `FileNotFoundError` message should enumerate the candidate paths
   tried, matching the `resolve_template()` convention
   (`artifact_templates.py:70-85`).
3. **`ll-loop install <name-or-path>`** — accept an arbitrary filesystem path (not
   just a built-in loop name) and copy it into `loops_dir` under a short name.
   - **Name derivation**: every generator draft is literally named `workflow.yaml`,
     so a path-stem derivation would yield `workflow` for all drafts — derive the
     install name from the YAML's internal `name:` field instead (the same
     convention the generator's own `promote` step uses,
     `workflow-generator.yaml:875`), with an optional `--name` override.
   - **Collision rules**: reuse the promote step's policy — suffix on collision
     (`-2`, `-3`, ...), never shadow a built-in name.
   - **Validation**: run `is_runnable_loop` on the source file before copying and
     refuse (with the validation error) if it fails.
4. **`workflow-generator.yaml`'s `promote` step** — correct its
   `context.loops_dir` default from `.ll/loops` to `.loops`, matching the CLI's
   config default (`config/features.py:998`, read at
   `scripts/little_loops/cli/loop/__init__.py:57`), so promotion (once reachable)
   lands drafts where the CLI actually looks.
   - **Containment-gate widening (deliberate)**: `${context.loops_dir}` feeds the
     FEAT-3335 promote-window scope gate's allowed realpaths (`allow_loops_dir`,
     `workflow-generator.yaml:70-88`, `check_promote_scope` ~line 899). Changing
     the default to `.loops` widens that gate's allowed set from an isolated dir
     to the whole `.loops` tree (project loops, `runs/`, `.history/`). Accepted:
     promote's collision suffixing prevents overwrites, and the gate still
     excludes everything outside `.loops`. Record this in the decision log.
   - **Accepted debt**: hardcoding `.loops` still mismatches projects that
     override `loops.loops_dir` in `.ll/ll-config.json`. The durable fix —
     injecting the configured dir into run context at launch — is out of scope
     here; note it as a follow-up if it bites.

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
- `scripts/tests/test_fsm_loop_paths.py` — one unit test per new
  `resolve_loop_path` branch (instance-folder name; internal-`name:` scan;
  latest-mtime dedup for duplicate names), following the existing
  one-test-per-branch convention
- `scripts/tests/test_builtin_loops.py` (`TestBuiltinLoopInstall`) and
  `test_cli_loop_next.py` (`TestCmdInstall`) — `ll-loop install <path>`:
  installs under the YAML's internal `name:` (NOT the `workflow` path stem),
  `--name` override, collision suffixing, built-in shadowing refused,
  `is_runnable_loop` rejection
- `scripts/tests/test_feat_3352_mcp_loop_list.py` (or adjacent) — catalog
  cases: draft surfaced under its `name:` with `draft` visibility, hidden
  under the default filter, shown with drafts enabled; only
  `runs/*/workflow.yaml` counts; latest-per-name dedup; contract test that
  `resolve_loop_path` resolves the exact name `enumerate_loop_catalog` emits
  for a draft
- Regression test asserting `workflow-generator.yaml`'s `promote` step default
  matches the CLI's actual `.loops` default

### Documentation
- `docs/reference/CLI.md` — `ll-loop list`/`ll-loop run`/`ll-loop install`
  entries, once behavior changes

### Configuration
- N/A — the only config touched is the generator loop's own
  `context.loops_dir` default, already covered above

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- **Ordered-fallback resolution convention**: `resolve_loop_path()` (`scripts/little_loops/fsm/loop_paths.py:19-40`) is a comment-labeled `if <path>.exists(): return <path>` early-return chain, ordered most-specific to most-general, terminating in `raise FileNotFoundError(name_or_path)`. The same shape recurs in `resolve_template()` (`scripts/little_loops/artifact_templates.py:70-85`, though its error names every candidate tried, not just the input) and `resolve_run()` (`scripts/little_loops/cli/loop/audit.py:85-115`).
- **`name_or_path` dual-mode argument convention**: every `ll-loop` subcommand except `install` declares its positional as `"Loop name or path"` (`cli/loop/__init__.py:137,377,481,648,678,902`) and routes through the shared `resolve_loop_path()`, whose own `path.exists()` first branch is what makes name-or-path work as one argument. `install_parser`'s argument is instead labeled `"Built-in loop name to install"` (`cli/loop/__init__.py:667-671`), and `cmd_install()` (`cli/loop/config_cmds.py:95-124`) does its own direct `get_builtin_loops_dir()`-only lookup rather than calling `resolve_loop_path()` — it is the one `ll-loop` subcommand that does not follow the dual-mode convention the others share. A second, differently-worded name-or-path precedent exists outside `ll-loop`: `ll-artifact status`'s `template` argument (`cli/artifact/status.py:174-180`), resolved via `resolve_template()`.
- **Catalog status-marker conventions disagree, and neither defines a draft/unpromoted value**: loop-catalog listings use a `◆ <word>`-prefixed colored badge keyed off `visibility`/`builtin` dataclass fields (`_badge_for()`, `cli/loop/info.py:475-483`, values `internal`/`example`/`project`); issue listings instead use a plain `[status]` bracket suffix keyed off frontmatter `status` (`cli/issues/list_cmd.py:278,293,329`). A repo-wide search for `draft|unpromoted|pending_promotion|promoted` found no existing status value for "generated but not yet promoted" in either convention.
- **Test conventions**: `resolve_loop_path()` has one direct `tmp_path`-based unit test per resolution branch in `scripts/tests/test_fsm_loop_paths.py`; `cmd_install()` is tested both via direct function call with a monkeypatched `get_builtin_loops_dir` (`test_cli_loop_next.py:354+`, class `TestCmdInstall`) and via full CLI dispatch (`test_builtin_loops.py:804-868`, class `TestBuiltinLoopInstall`). `enumerate_loop_catalog()` has no direct unit test of its own — it's exercised only indirectly through the `loop_list` MCP tool test (`scripts/tests/test_feat_3352_mcp_loop_list.py`), which uses a `_write_loop(loops_dir, rel_name, **fields)` fixture helper supporting nested `rel_name` paths.
- **No existing "derive a short name from a path" utility**: a repo-wide search (`slugify`, `derive_name`, `.stem` call sites) found no shared helper for turning an arbitrary filesystem path into a catalog-safe short name. The two adjacent "derive a name" examples — `workflow-generator.yaml`'s `promote` step (`~lines 859-897`, derives from the artifact's own `name:` field, collision-disambiguated by incrementing a `-<suffix>`) and `persistence.py:770-801`'s `promote_run_artifact()` (derives from `run_id`, not a path stem) — both derive from content or an ID, not from a source path.

## Implementation Steps

1. Fix the `workflow-generator.yaml` `loops_dir` default mismatch
   (`.ll/loops` → `.loops`) — smallest, unconditional fix. Log the
   containment-gate widening (see Proposed Solution item 4) in the decision log.
2. Extend `resolve_loop_path` with the two fallback branches (instance-folder
   name, then internal-`name:` scan with latest-mtime dedup) and the
   candidates-tried error message.
3. Key `ll-loop list`'s catalog draft entries (`runs/*/workflow.yaml` only,
   latest per name) by internal `name:`, add the `draft` visibility tier +
   badge and `--drafts` flag, exclude other `runs/` YAMLs from the catalog.
4. Extend `cmd_install` to accept a filesystem path: internal-`name:` dest
   derivation with `--name` override, promote-style collision suffixing,
   `is_runnable_loop` pre-validation.
5. Add regression tests for each of the above (including: `run` resolves the
   exact identifier `list` displays; duplicate-named drafts resolve to the
   latest; `install` on a draft named `workflow.yaml` does NOT install as
   `workflow`; MCP `loop_list` hides drafts by default) and verify against the
   reproduction steps.

## Impact

- **Priority**: P3 — usability/discoverability gap in a generator feature, not
  a correctness or data-loss bug; the workaround (manual file path/`cp`) exists
  but is undocumented.
- **Effort**: Medium — four well-localized fixes across three CLI modules plus
  one YAML default. Fixes 1 and 2 share a contract (the identifier `list`
  displays must be what `run` resolves, latest-mtime dedup policy) and should
  land together; fixes 3 and 4 are independent.
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

- `enumerate_loop_catalog(*, loops_dir: Path, category: str | None, label: list[str] | None, visibilities: set[str] | None, builtin_only: bool) -> LoopCatalog`
  (`scripts/little_loops/cli/loop/info.py:151`) — key `runs/*/workflow.yaml`
  draft entries by their parsed `name:` field (latest per name by mtime),
  exclude other `runs/` YAMLs, and assign drafts the new `draft` visibility
  tier so the existing visibility filter hides them by default.
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path`
  (`scripts/little_loops/fsm/loop_paths.py:19`; raises `FileNotFoundError`,
  never returns `None`) — append two fallback branches after the existing
  literal-path/`<name>.fsm.yaml`/`<name>.yaml`/builtin checks:
  `loops_dir/runs/<name>/workflow.yaml`, then an internal-`name:` scan of
  `loops_dir/runs/*/workflow.yaml` (latest mtime wins). Shared by the FSM core
  (`fsm/validation/structural_rules.py`, `fsm/fragments.py`, `fsm/executor.py`) — both branches
  are additive fallbacks after all existing checks, so core resolution is
  unaffected for existing names.
- `cmd_install(loop_name: str, loops_dir: Path, logger: Logger) -> int`
  (`scripts/little_loops/cli/loop/config_cmds.py:95`) — fall back to treating
  the argument as a filesystem path when it isn't a known built-in loop name;
  derive the dest name from the source YAML's `name:` field (or a new
  `--name` flag), apply promote-style collision suffixing, validate with
  `is_runnable_loop` before copying. Relabel the parser argument from
  `"Built-in loop name to install"` to `"Built-in loop name or path to a loop
  YAML"` (`cli/loop/__init__.py:667-671`).

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
- `/ll:manage-issue` - 2026-08-31T05:35:03 - `57895937-283e-4bda-9ec3-825fc4752302.jsonl`
- `/ll:ready-issue` - 2026-08-31T05:17:46 - `28163470-98d0-43dd-92ef-a9663f48cfd0.jsonl`
- `/ll:confidence-check` - 2026-08-31T04:04:11 - `e6624bad-8105-48eb-a1a4-bb4f8a49ae52.jsonl`
- `/ll:refine-issue` - 2026-08-31T03:37:52 - `d3fa0ee5-3d96-476c-a86f-50795f749f97.jsonl`
- `/ll:format-issue` - 2026-08-31T03:25:45 - `58ca304a-54ac-44f8-bc17-9bdf9d83c13c.jsonl`
- `/ll:capture-issue` - 2026-08-31T03:21:32 - `41ef66dd-c959-46d5-a910-2bd5157e43bf.jsonl`
