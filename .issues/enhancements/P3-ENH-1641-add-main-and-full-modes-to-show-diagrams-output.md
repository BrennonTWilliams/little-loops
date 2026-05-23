---
discovered_commit: 31b885420f1cc982bec6297439fddcb8ae1c6d17
discovered_branch: main
discovered_date: 2026-05-23
captured_at: '2026-05-23T19:35:22Z'
completed_at: '2026-05-23T20:35:02Z'
discovered_by: capture-issue
status: done
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1641: Add `main` and `full` Modes to `--show-diagrams` Output

## Summary

`ll-loop run ... --show-diagrams` currently renders every edge and node in the
FSM, including error-handling, retry-exhausted, blocked, and other off-happy-path
transitions. For non-trivial loops this produces a dense graph that's hard for
humans to parse at a glance. Add a `--show-diagrams=main|full` mode where `main`
(the new default) hides error/stall/fail edges and the dead-end terminal nodes
they lead to, leaving only the happy-path skeleton. `full` preserves today's
behavior for users who want the complete picture.

## Current Behavior

`--show-diagrams` is a boolean flag that, when set, renders a box diagram of every
FSM state and edge — including `error`, `retry_exhausted`, `blocked`, `partial`,
`rate_limit_exhausted`, and `throttle_hard` transitions. On non-trivial loops with
many off-happy-path fall-throughs, the resulting graph is dense and hard to read at
a glance. There is no mode selection; all edges are always shown.

## Expected Behavior

`--show-diagrams` accepts an optional value: `main` (new default) or `full`
(current behavior). Bare `--show-diagrams` defaults to `main`, which shows only
happy-path edges (`yes`, `no`, `next`, `route`, `_`) and the states reachable
through them. `--show-diagrams=full` renders all edges and states as today.
If the active state is outside the main-path reachable set, the renderer falls
back to `full` automatically for that iteration and prepends a one-line note:
`(showing full diagram: active state '<name>' is off the main path)`.

## Motivation

- The FSM box diagram is a "delighter" feature for human users watching loop
  execution. Today it's too noisy on real-world loops with many `on_error` /
  `on_retry_exhausted` / `on_blocked` fall-throughs.
- A happy-path view answers the most common question — "what is this loop
  *supposed* to do?" — without making the user mentally filter exception edges.
- Power users debugging an error transition still need the full graph, so
  `full` must remain a single flag away.
- This is a pure presentation enhancement built on FEAT-642's existing
  `--show-diagrams` infrastructure. No FSM model or runtime changes.

## Use Case

A user runs a moderately complex loop and wants the at-a-glance view:

```bash
ll-loop run my-loop.yaml --show-diagrams
# defaults to --show-diagrams=main → only yes/no/next/route edges and reachable states
```

When they later hit an error and want to see what the loop does on failure:

```bash
ll-loop run my-loop.yaml --show-diagrams=full
# all edges (error, partial, blocked, retry_exhausted, rate_limit_exhausted, throttle_hard) and their target states shown
```

The flag also accepts the bare form for back-compat with FEAT-642:

```bash
ll-loop run my-loop.yaml --show-diagrams        # == --show-diagrams=main
```

## Acceptance Criteria

- [ ] `--show-diagrams` accepts an optional value `main` or `full`
- [ ] Bare `--show-diagrams` (no value) defaults to `main` — this is a
      behavior change from FEAT-642's all-edges output; documented in CHANGELOG
- [ ] `main` mode hides edges with labels: `error`, `partial`, `blocked`,
      `retry_exhausted`, `rate_limit_exhausted`, `throttle_hard`
- [ ] `main` mode hides states that become unreachable from `fsm.initial` once
      those edges are removed (i.e., dead-end fail/stall terminals)
- [ ] States still reachable through happy-path edges (`yes`, `no`, `next`,
      `route`, `_` default) remain visible even if they are terminal
- [ ] `full` mode renders identically to today's `--show-diagrams` output
- [ ] Active-state highlighting works in both modes; if the active state is
      hidden in `main`, fall back to rendering `full` for that iteration so the
      user always sees where the loop currently is (with a one-line note:
      `(showing full diagram: active state '<name>' is off the main path)`)
- [ ] Same flag and semantics added to `ll-loop resume`
- [ ] Help text documents the two modes and the default
- [ ] Existing FEAT-642 tests in `test_ll_loop_display.py` updated to assert
      `full` output where they currently assert all edges present
- [ ] New tests cover: `main` hides error edges; `main` hides unreachable
      fail states; `main` keeps reachable terminals; `full` matches legacy;
      active-state fallback path

## API/Interface

```
ll-loop run <config>    [--verbose] [--show-diagrams[=main|full]] [--clear] [--exit-code] [--context KEY=VALUE]
ll-loop resume <config> [--verbose] [--show-diagrams[=main|full]] [--clear] [--exit-code] [--context KEY=VALUE]
```

- `--show-diagrams` — bare form, equivalent to `--show-diagrams=main`
- `--show-diagrams=main` — happy-path only (new default)
- `--show-diagrams=full` — every edge and reachable state (today's behavior)

Edge labels classified as "non-happy-path" (filtered out in `main`):

| Source field on `FSMState` | Edge label |
| -------------------------- | ---------- |
| `on_error`                 | `error`    |
| `on_partial`               | `partial`  |
| `on_blocked`               | `blocked`  |
| `on_retry_exhausted`       | `retry_exhausted` |
| `on_rate_limit_exhausted`  | `rate_limit_exhausted` |
| `on_throttle_hard`         | `throttle_hard` |

`yes`, `no`, `next`, `route` verdicts, and `_` (route default) are always
treated as main-path.

## Implementation Steps

1. In `scripts/little_loops/cli/loop/__init__.py` (lines ~139 and ~247):
   change the `--show-diagrams` argparse entry from `action="store_true"` to
   `nargs="?"`, `const="main"`, `default=None`, `choices=["main", "full"]`.
   `None` means "off"; `"main"`/`"full"` means "on, with mode".
2. In `scripts/little_loops/cli/loop/_helpers.py:354`, replace the
   `show_diagrams = getattr(args, "show_diagrams", False)` boolean read with
   a tri-state: `None | "main" | "full"`. Update the subprocess re-emission
   at `_helpers.py:294` to forward the value (`cmd.extend(["--show-diagrams", mode])`).
3. In `scripts/little_loops/cli/loop/layout.py`, add a `mode` parameter to
   `_render_fsm_diagram` (default `"full"` to preserve callers like
   `info.py:823` which use it for static diagram dumps). When `mode == "main"`:
   - Filter edges from `_collect_edges` to exclude the six labels listed in
     the table above.
   - Recompute reachability via BFS from `fsm.initial` over the filtered edge
     set; drop states not in that reachable set.
   - Pass the filtered edges + state set into the existing layout pipeline.
4. In `_helpers.py:410` and `_helpers.py:427` (the runtime render call sites),
   pass `mode=show_diagrams_mode` and implement the active-state fallback:
   if `highlight_state` is not in the filtered reachable set, re-render with
   `mode="full"` and prepend the explanatory one-liner.
5. Update `next_loop.py:318` (`show_diagrams=False`) to pass `None` instead.
6. Update help text in both subparsers; keep `--clear`'s help string referring
   to `--show-diagrams` unchanged.
7. Update CHANGELOG with a "Changed" entry noting the new default.
8. Add/update tests in `scripts/tests/test_ll_loop_display.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `show_diagrams=False` → `None` in 5 additional test files that build `argparse.Namespace` with the old boolean default: `test_cli_loop_lifecycle.py` (lines 807, 895), `test_cli_loop_queue.py` (line 25), `test_cli_loop_worktree.py` (line 575), `test_ll_loop_program_md.py` (line 159), `test_ll_loop_commands.py` (line 2641).
10. In `test_ll_loop_display.py`: widen `TestDisplayProgressEvents._make_args` signature from `show_diagrams: bool = False` to `show_diagrams: bool | str | None = None`; update all 13 `show_diagrams=True` call sites to `"main"` or `"full"`; add `mode=<expected>` kwarg to all 5 `mock_render.assert_called_once_with(...)` / `calls[N] == call(...)` assertions; update `TestRunForegroundExitCodes._make_args` `show_diagrams=False` → `None`.
11. Add 4 argparse parse tests (bare flag → `"main"`, `=main` → `"main"`, `=full` → `"full"`, absent → `None`) and 3 subprocess re-emission tests (`"main"` / `"full"` → `cmd.extend(["--show-diagrams", mode])`; `None` → flag absent from cmd) to `test_ll_loop_display.py` or a new `test_cli_loop_argparse.py`.

## Scope Boundaries

- **Out of scope**: FSM model and runtime execution logic — this is purely a presentation change.
- **Out of scope**: `ll-loop info` static diagram mode (adding `--mode` to `ll-loop info` is a potential follow-up; today `info.py:823` will keep defaulting to `full`).
- **Out of scope**: `display.default_diagram_mode` config key in `.ll/ll-config.json` (noted as a future enhancement; hardcoded default `main` is sufficient here).
- **Out of scope**: Sub-loop FSM diagram mode propagation to child diagrams (tracked in ENH-846).

## Impact

- **Priority**: P3 — UX polish on an opt-in flag; no automation depends on it.
- **Effort**: Small-to-medium — single filtering pass added before the existing
  layout pipeline; argparse and call-site plumbing is mechanical.
- **Risk**: Low — purely additive to the renderer; the default change is
  user-facing only via `--show-diagrams` (an opt-in flag), so no silent
  behavior change in default runs.
- **Breaking Change**: Soft — bare `--show-diagrams` previously rendered the
  full graph; now it renders the main-path subset. Users who scripted around
  the exact output need `--show-diagrams=full`. Call out in CHANGELOG.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — change `--show-diagrams`
  argparse entry on both `run` (~line 139) and `resume` (~line 247) subparsers
  from boolean flag to `nargs="?"` with `const="main"` and
  `choices=["main", "full"]`.
- `scripts/little_loops/cli/loop/_helpers.py` — treat `show_diagrams` as
  `None | "main" | "full"`; forward the value through `run_background` (line
  294) and `run_foreground` (line 354); pass `mode=` into both
  `_render_fsm_diagram` call sites (lines 410, 427); implement active-state
  fallback to `full` when highlight is off the main path.
- `scripts/little_loops/cli/loop/layout.py` — add `mode: Literal["main", "full"] = "full"`
  parameter to `_render_fsm_diagram` (line 1503); when `"main"`, filter
  `_collect_edges` output and recompute the reachable state set before handing
  off to the existing layout pipeline.
- `scripts/little_loops/cli/loop/next_loop.py` — line 318 already passes
  `show_diagrams=False`; change to `show_diagrams=None` to match the new
  tri-state.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py:823` — calls `_render_fsm_diagram`
  for static `ll-loop info` output. Default `mode="full"` preserves today's
  behavior here. Optionally accept a `--mode` flag on `ll-loop info` in a
  follow-up.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/run.py` — top-level entry point for `ll-loop run`; calls `run_background()` (line 201) and `run_foreground()` (line 352) with the parsed `args` namespace; no direct code changes needed, but the argparse change in `__init__.py` propagates through here
- `scripts/little_loops/cli/loop/lifecycle.py` — top-level entry point for `ll-loop resume`; calls `run_background()` (line 318) with the parsed `args` namespace; no direct code changes needed

### Similar Patterns
- FEAT-642's flag propagation (`run` → `_helpers.run_foreground` →
  `_render_fsm_diagram`) is the exact template to extend.
- Edge label classification already exists implicitly in `layout.py:42`
  (`_colorize_diagram_labels` recognizes `error`/`fail` for coloring) — reuse
  the same label set for filtering.

### Tests
- `scripts/tests/test_ll_loop_display.py` — update existing
  `--show-diagrams` tests to pass `=full` where they assert error edges
  appear; add new tests:
  - `test_show_diagrams_main_hides_error_edges`
  - `test_show_diagrams_main_hides_unreachable_fail_terminals`
  - `test_show_diagrams_main_keeps_reachable_terminals`
  - `test_show_diagrams_full_matches_legacy_output`
  - `test_show_diagrams_main_falls_back_to_full_when_highlight_off_path`

_Wiring pass added by `/ll:wire-issue`:_

**Within `test_ll_loop_display.py` — structural updates required (not just new tests):**
- `TestDisplayProgressEvents._make_args` at line 1645: widen signature from `show_diagrams: bool = False` to `show_diagrams: bool | str | None = None` so tests can pass `"main"` or `"full"` explicitly
- 13 call sites `self._make_args(show_diagrams=True)` inside `TestDisplayProgressEvents` — update `True` → `"main"` (or `"full"` where the test asserts off-path edges are present); affected tests: `test_show_diagrams_state_enter_prints_diagram`, `test_verbose_and_show_diagrams_prints_diagram`, `test_clear_flag_emits_ansi_clear_when_tty`, `test_clear_flag_suppressed_when_not_tty`, `test_show_diagrams_and_clear_enters_alt_screen`, `test_show_diagrams_only_no_alt_screen`, `test_alt_screen_exited_on_normal_completion`, `test_alt_screen_exited_on_executor_exception`, `test_sub_loop_diagram_keeps_parent_state_highlighted`, `test_sub_loop_child_diagram_rendered_during_sub_loop_execution`, `test_grandchild_sub_loop_diagram_rendered_at_depth_2`, `test_shallow_reentry_clears_deeper_sub_loop_diagrams`, `test_top_level_loop_header_shown_when_show_diagrams`
- 5 `mock_render.assert_called_once_with(...)` / `calls[N] == call(...)` assertions at lines 1952–1957, 2012–2018, 2249–2268, 2340–2352 — add `mode=<expected>` kwarg to each expected call once `_helpers.py` starts forwarding it
- `TestRunForegroundExitCodes._make_args` at line 2454: update `show_diagrams=False` → `None`
- New: 4 argparse parse tests (bare flag → `"main"`, `=main` → `"main"`, `=full` → `"full"`, absent → `None`)
- New: 3 subprocess re-emission tests (mode `"main"`, `"full"`, `None` each produce or suppress `--show-diagrams` in `cmd`)

**Additional test files with `show_diagrams=False` → `None` that will contain stale values after the change:**
- `scripts/tests/test_cli_loop_lifecycle.py` — `_make_args` helpers at lines 807 and 895 have `show_diagrams=False`; update to `None` [Agent 2 finding]
- `scripts/tests/test_cli_loop_queue.py` — module-level `DEFAULT_ARGS` dict at line 25 has `"show_diagrams": False`; update to `None` [Agent 2 finding]
- `scripts/tests/test_cli_loop_worktree.py` — `_make_args` at line 575 has `"show_diagrams": False`; update to `None` [Agent 2 finding]
- `scripts/tests/test_ll_loop_program_md.py` — `_make_args` at line 159 has `"show_diagrams": False`; update to `None` [Agent 2 finding]
- `scripts/tests/test_ll_loop_commands.py` — inline `argparse.Namespace` at line 2641 has `show_diagrams=False`; update to `None` [Agent 2 finding]

### Documentation
- `CHANGELOG.md` — Changed entry under the next release noting bare
  `--show-diagrams` now defaults to `main`; users wanting the old behavior
  pass `--show-diagrams=full`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:671` — passive mention of `--show-diagrams` in the `cli.colors.fsm_active_state` key description; low-priority; verify the description still reads correctly after the flag gains a value parameter [Agent 2 finding]

### Configuration
- N/A — no `.ll/ll-config.json` schema change. (A future enhancement could
  add a `display.default_diagram_mode` key; out of scope here.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Line-number / anchor corrections to the above:**

- `layout.py:42` is `_colorize_label` (single compound-label colorizer), **not** `_colorize_diagram_labels`. The latter is at `layout.py:86`. The actual label-set source of truth is the `_EDGE_LABEL_COLORS` dict at `layout.py:27`, which already enumerates the exact six non-happy-path labels this enhancement filters (`error`, `partial`, `blocked`, `retry_exhausted`, `rate_limit_exhausted`, `throttle_hard`) plus the happy-path labels (`yes`, `no`, `next`, `_`). Reuse the dict keys (or `_edge_line_color`'s inline tuple at `layout.py:68`) instead of defining a new constant.
- The Similar Patterns bullet should say "recognizes `error`/`blocked`/`retry_exhausted`/…" rather than "`error`/`fail`" — there is no `fail` label produced anywhere; `_collect_edges` (`layout.py:196`) is the sole edge-label producer.

**Reusable helpers already in `layout.py` (no need to write from scratch):**

- `_collect_edges(fsm)` at `layout.py:196` — emits `(source, target, label)` tuples directly from `FSMState.on_yes`/`on_no`/`on_error`/`on_partial`/`on_blocked`/`on_retry_exhausted`/`on_rate_limit_exhausted`/`on_throttle_hard`/`next`/`route`. Filter its return value by label before passing downstream.
- `_bfs_order(initial, edges)` at `layout.py:228` — already does BFS from `fsm.initial` over a given edge list, returning `(order, depth_map)`. This is exactly the reachability primitive Step 3 needs; pass it the filtered edge list and use `depth_map.keys()` as the reachable-state set.
- `_render_fsm_diagram` (`layout.py:1503`) currently pipes `_collect_edges` → `_bfs_order` → `_trace_main_path` → `_classify_edges`. Insert the `mode == "main"` filter immediately after `_collect_edges` and before `_bfs_order` so the rest of the pipeline operates on the already-reduced graph.

**Argparse pattern is novel — no existing template in this codebase:**

- A search of `scripts/` finds **zero** existing flags using `nargs="?" + const=`. ENH-1641 will be the first instance. The only `nargs="?"` usages are on positionals (e.g. `cli/deps.py:175`). Implementer should rely on stdlib docs, not codebase mimicry, for this argparse construction.

**Subprocess re-emission template (Step 2):**

- `_helpers.py:283` (`run_background`) currently has both patterns side-by-side: boolean re-emission (`if getattr(args, "show_diagrams", False): cmd.append("--show-diagrams")`) and optional-value re-emission a few lines below (`delay = getattr(args, "delay", None); if delay is not None: cmd.extend(["--delay", str(delay)])`). Replace the boolean form with the `delay`-style pattern: `mode = getattr(args, "show_diagrams", None); if mode is not None: cmd.extend(["--show-diagrams", mode])`.

**Test helper that needs widening (in addition to the new tests):**

- `test_ll_loop_display.py` has a `_make_args` helper in `TestDisplayProgressEvents` (~line 1645) whose signature is `show_diagrams: bool = False`. Widen to `show_diagrams: bool | str | None = None` (or accept either form and normalize) so existing tests can call `show_diagrams=True` (back-compat → `"main"`) or `show_diagrams="full"` / `"main"` explicitly.
- Existing assertion style in `TestRenderFsmDiagram` (~line 640) is direct-call: `result = _render_fsm_diagram(fsm); assert "state_name" in result; assert "┌" in result`. New `main` tests should follow this pattern — construct an `FSMLoop` with known `on_error`/`on_blocked` edges, call with `mode="main"`, then assert those label strings are **absent** from the rendered output while `"yes"`/`"next"` remain present.
- Spy-on-render pattern at `test_ll_loop_display.py:1936` (`patch.object(layout_mod, "_render_fsm_diagram", wraps=...)`) is the right template for the active-state fallback test — assert `_render_fsm_diagram` is called twice (once with `mode="main"`, once re-entered with `mode="full"`) when `highlight_state` is off-path.

**Additional documentation surfaces beyond CHANGELOG:**

- `docs/reference/CLI.md` documents the `--show-diagrams` flag; update to describe `main` (default) vs `full`.
- `docs/guides/LOOPS_GUIDE.md` references `--show-diagrams` in the user-facing loop walkthrough; sync the example output if it shows a diagram that would change under `main`.

## Labels

`enhancement`, `cli`, `loop`, `ux`, `diagram`

## Related Key Documentation

- FEAT-642 (done) — added `--show-diagrams` flag this enhancement extends
- BUG-989 (`ll-loop --show-diagrams` ghost fragments) — same render path
- ENH-846 (show sub-loop FSM diagram alongside parent) — mode flag should
  propagate to child diagrams the same way

## Resolution

Implemented `--show-diagrams[=main|full]` on both `ll-loop run` and `ll-loop resume`:

- **argparse** (`cli/loop/__init__.py`): both `run_parser` (line 138) and `resume_parser` (line 254) changed from `action="store_true"` to `nargs="?"`, `const="main"`, `default=None`, `choices=["main", "full"]`, with help text describing the two modes.
- **Layout filter** (`cli/loop/layout.py`): added `_MAIN_PATH_EDGE_LABELS` constant + `_filter_main_path_graph()` helper. `_render_fsm_diagram` gained a `mode: str = "full"` parameter; when `"main"`, edges are filtered and reachability is recomputed via the existing `_bfs_order` before the rest of the layout pipeline runs. Default `"full"` preserves callers like `info.py` static diagram dumps.
- **Subprocess + foreground plumbing** (`cli/loop/_helpers.py`): `run_background` re-emits as `--show-diagrams <mode>` when mode is not `None`. `run_foreground` normalizes the tri-state (legacy `True` → `"main"`), forwards `mode=` into both parent and child render call sites, and implements the active-state fallback: when the highlighted state is not in the main-path reachable set, re-render with `mode="full"` and prepend `(showing full diagram: active state '<name>' is off the main path)`.
- **Defaults**: `next_loop.py:318` switched from `show_diagrams=False` to `show_diagrams=None` to match the new tri-state.
- **Tests**: `test_ll_loop_display.py` widened `_make_args(show_diagrams=...)` to `bool | str | None` with a back-compat shim (`True → "main"`, `False → None`), so all 13 existing call sites work unchanged; added `mode="main"` kwarg to 5 `mock_render` assertions. New coverage: `TestShowDiagramsMode` (5 tests for main/full filtering + active-state fallback), `TestShowDiagramsArgparse` (4 parse tests: bare, `=main`, `=full`, absent), `TestShowDiagramsSubprocessReemit` (3 re-emission tests). Five dependent test files updated from `show_diagrams=False` to `None`.
- **Docs**: `CHANGELOG.md`, `docs/reference/CLI.md` (both `ll-loop run` and `ll-loop resume` tables), and `docs/guides/LOOPS_GUIDE.md` flag tables updated to describe `main` (default) vs `full`.

**Verification**: `python -m pytest scripts/tests/` → 7398 passed, 5 skipped, 0 failed. `ruff check scripts/` clean. `ruff format scripts/` clean after one reformat. `python -m mypy scripts/little_loops/` clean (only pre-existing `wcwidth` stub note).

## Session Log
- `/ll:manage-issue` - 2026-05-23T20:35:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7379b14f-1161-411a-88a9-5a21bedf0144.jsonl`
- `/ll:ready-issue` - 2026-05-23T20:16:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd363937-9ef0-4fed-900a-5e261d42fe40.jsonl`
- `/ll:confidence-check` - 2026-05-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9148d08-0197-4089-be39-89d58f0c2962.jsonl`
- `/ll:wire-issue` - 2026-05-23T20:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75642ced-0d2e-4093-9060-f4dda47af138.jsonl`
- `/ll:refine-issue` - 2026-05-23T20:05:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02c12a40-e1b4-41aa-9b68-8f8897d8870c.jsonl`
- `/ll:format-issue` - 2026-05-23T19:38:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fea0e6db-4667-413a-a780-b1a7b539504a.jsonl`

- `/ll:capture-issue` - 2026-05-23T19:35:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d78e31da-79c0-488b-9c76-e0ed6a110193.jsonl`

---

**Status**: done | Created: 2026-05-23 | Completed: 2026-05-23 | Priority: P3
