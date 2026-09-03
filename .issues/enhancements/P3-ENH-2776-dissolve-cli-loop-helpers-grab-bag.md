---
id: ENH-2776
status: done
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
completed_at: '2026-09-03T06:18:17Z'
focus_area: organization
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
verify_verdict: VALID
relates_to:
- EPIC-2938
- ENH-2773
confidence_score: 97
outcome_confidence: 72
score_complexity: 11
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 21
---

# ENH-2776: Dissolve cli/loop/_helpers.py grab-bag into named modules

## Summary

Architectural issue found by `/ll:audit-architecture`. A 2,156-line module
named `_helpers.py` is a grab-bag hiding several real modules; its contents
are depended on well beyond the CLI layer.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 1-2156 (entire file)
- **Module**: `little_loops.cli.loop._helpers`

## Current Behavior

`cli/loop/_helpers.py` is a 2,255-line underscore-"private" module holding
eight unrelated clusters (signal handling with seven mutable module globals,
queue helpers, pinned-pane/diagram rendering + `StateFeedRenderer`, artifact
header helpers, FSM-context seeding, loop loading, run orchestration, summary
printing) plus an ENH-2773 re-export shim. It is imported by 7 modules at
module level, 7 more via deferred imports — including two from **outside the
CLI layer** (`fsm/executor.py`, `analytics/variance.py`) — and ~20 test files
that reach private names and mock-patch its module namespace (~34
`_helpers.subprocess.Popen` patches, a `_helpers.datetime` monkeypatch, direct
writes to `_helpers._loop_*` globals). It sits in a deferred-import 2-cycle
with `info.py` and another with `layout.py`.

## Expected Behavior

`_helpers.py` no longer exists. Its clusters live in named modules under
`cli/loop/`, and the three self-contained FSM-context seeders plus
`load_loop` move to `fsm/` so no `fsm/` or `analytics/` code imports from
`cli/`. Both deferred-import cycles are gone (module-level imports point
strictly downward). Every production caller and every test import/patch
string is repointed to the new owner module, and a guard test asserts the
old path never reappears.

## Finding

### Current State

- 2,255 lines, 37 top-level defs (35 functions + `_TeeWriter`/`StateFeedRenderer`)
  behind an underscore-private "helpers" name.
- Imported by core code — `fsm/executor.py:1076` (deferred, unconditional:
  `derive_input_hash`, `seed_confidence_thresholds`) and
  `analytics/variance.py:224` (deferred: `load_loop`) — and by
  `cli/loop/info.py` in a 2-cycle (`_helpers.py:1847` ↔ `info.py:21`) held
  apart by deferred imports. _(The original `fsm/validation.py:485,566`
  citation is stale; that import was removed by ENH-2773/ENH-2774 — see
  Codebase Research Findings.)_
- The name gives no signal about ownership, so unrelated functionality keeps
  landing here by default.

### Impact

- **Development velocity**: "where does this go?" defaults to `_helpers.py`,
  compounding the problem.
- **Maintainability**: an underscore-prefixed module with external importers is
  a false-privacy signal.
- **Risk**: low-medium — mostly navigational cost plus the cycle fragility.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **Drifted citation (2026-09-03)**: the Current State claim "Imported by core code (`fsm/validation.py:485,566` — see ENH-2773)" no longer matches the tree — `fsm/validation.py` no longer exists as a single file, ENH-2774 already split it into the `fsm/validation/` package (`__init__.py`, `_base.py`, `evaluator_rules.py`, `meta_rules.py`, `reachability.py`, `shell_safety.py`, `structural_rules.py`). An unfiltered search of every file in that package for `_helpers`/`cli.loop` found zero matches — no file in `fsm/validation/` imports `cli/loop/_helpers.py` today.
- The actual current core-code (non-CLI) dependency is `scripts/little_loops/fsm/executor.py:1076` — a deferred (function-local), unconditional `from little_loops.cli.loop._helpers import derive_input_hash, seed_confidence_thresholds`, inside the child-loop context-resolution path (comments cite BUG-2767/BUG-2832: "a child loop launched here never passes through `cli/loop/run.py`, so it must seed its own confidence-gate thresholds from config"). This is the citation the Current State bullet should point to instead.
- Full grep-confirmed importer set (7 module-level, 7 deferred, 13+ tests) is in Integration Map → Dependent Files (Callers/Importers) below.

## Proposed Solution

Split by actual responsibility into named modules under `cli/loop/`, move
the layer-violating leaves into `fsm/`, repoint every caller and test, and
delete `_helpers.py` outright with a guard test — **no re-export shim** (see
Decisions below for why a shim is unsafe here specifically).

### Suggested Approach

_Rewritten 2026-09-02 to reconcile with the research findings below. The
earlier draft's step 1 (`resolve_loop_path` move) was completed by ENH-2773;
its step 2 importer list was wrong (`layout.py` is imported **by**
`_helpers`, not the reverse; the real set is in Integration Map ->
Dependent Files)._

**Target module map** (from the def inventory at `_helpers.py`, 2026-09-02):

| New home | Moves there | Notes |
|---|---|---|
| `fsm/context_seed.py` (new) | `seed_confidence_thresholds`, `derive_input_hash`, `inject_design_context` | Self-contained leaves (research-confirmed); this removes the `fsm/executor.py:1076` core->CLI import. Same layering fix ENH-2773 made for `resolve_loop_path`. `seed_confidence_thresholds`'s deferred `BRConfig` import is fine — `fsm/executor.py`/`evaluators.py` already import `little_loops.config`. |
| `fsm/loop_paths.py` (existing) | `load_loop`, `load_loop_with_spec` | Both are `resolve_loop_path` + `load_and_validate`; removes the `analytics/variance.py:224` cross-layer import. Keep `load_and_validate` import deferred inside the function as it is today (`fsm.validation` -> `fsm.loop_paths` direction must stay clean). |
| `cli/loop/signals.py` (new) | `_loop_signal_handler`, `register_loop_signal_handlers`, `_sigwinch_handler`, `_install_sigwinch_handler`, `_restore_sigwinch_handler`, **and all seven module globals** (`_loop_shutdown_requested`, `_loop_executor`, `_loop_pid_file`, `_loop_marker_path`, `_using_alt_screen`, `_needs_redraw`, `_original_sigwinch`) | Globals must move with the handlers — tests mutate them by module attribute. `run_foreground` writes `signals._using_alt_screen`; `StateFeedRenderer` reads `signals._needs_redraw`. |
| `cli/loop/queue.py` (existing) | `read_queue_entries`, `_is_earliest_waiter` | Only callers are `queue.py` itself and `run.py`; `queue.py` imports nothing from `run.py`, so no cycle. |
| `cli/loop/feed.py` (new) | `with_diagram_color`, `MIN_ACTION_ROWS`, `_count_display_lines`, `_choose_pinned_layout`, `_classify_fsm_topology`, `_variant_width`, `_build_fallback_ladder`, `_render_single_line_status`, `_build_pinned_pane`, `_render_pinned_pane`, `_render_streaming_diagram`, `StateFeedRenderer`, **plus `_format_history_event` moved out of `info.py:858`** | Moving `_format_history_event` here is the `_helpers`↔`info` cycle break: `info.py` and `runner.py` both import it downward. `layout.py` does not import `_helpers`, so the three deferred `layout` imports become module-level here (second cycle gone). |
| `cli/loop/header.py` (new) | `_relativize_to_cwd`, `_display_loop_path`, `_artifact_lines`, `_resolve_input_value`, `_EFFORT_CODES`, `_effort_code`, `_render_artifact_header_lines` | |
| `cli/loop/runner.py` (new) | `_TeeWriter`, `_make_instance_id`, `run_background`, `run_foreground`, `print_execution_plan`, `EXIT_CODES` | Must `import subprocess` and `from datetime import datetime` at module level — tests patch `<module>.subprocess.Popen` and monkeypatch `<module>.datetime`. |
| `cli/loop/summary.py` (new) | `_print_usage_summary`, `_print_ab_summary`, `_run_cross_host_validation`, `_print_cross_host_table` | |

Resulting import DAG (all module-level, no deferred imports needed):
`runner -> {signals, feed, header, summary, fsm.loop_paths, fsm.context_seed}`;
`feed -> {signals, layout, fsm.loop_paths}`; `info -> {feed, fsm.loop_paths}`;
`lifecycle -> {feed, signals, runner}`; `run -> {runner, feed, queue, header}`.

**Steps** (three independently-green commits):

1. **fsm-layer moves.** Create `fsm/context_seed.py`; append `load_loop`/
   `load_loop_with_spec` to `fsm/loop_paths.py`. Repoint the deferred imports
   in `fsm/executor.py:1076`, `analytics/variance.py:224`, and
   `cli/loop/{run,testing,lifecycle,info,audit}.py`. Repoint the `mock.patch`
   string targets for `derive_input_hash` in `test_advisor.py:232` and for
   `load_loop` in `test_ll_loop_display.py` and `test_cli_loop_background.py`,
   plus the import in `test_cli_loop_testing.py:271`. Repoint the ENH-2773 shim consumers
   (`info.py`, `lifecycle.py`, `config_cmds.py`, `edit_routes.py`,
   `cli/queue.py:147`, `cli/doctor.py:533`, `test_rn_plan.py:308`,
   `test_deep_research*.py`, `test_cli_doctor_install_checks.py` patch
   strings) to `fsm.loop_paths` directly. Update
   `test_fsm_loop_paths.py:67-71` (the `_helpers` re-export identity test) to
   assert the new import sites instead, or delete it.
2. **signals + feed + header + queue.** Create the four modules, move
   `_format_history_event` out of `info.py`, convert the deferred `layout`
   imports to module-level. Repoint `test_cli_loop_background.py::TestLoopSignalHandler`
   and `test_cli_loop_lifecycle.py:905-919,3081-3145` (globals + `StateFeedRenderer`
   patches), `test_state_feed_renderer.py`, `test_cli_loop_layout.py`,
   `test_loop_layout_alignment.py`, `test_ll_loop_display.py` (`terminal_width`
   patch strings -> `feed.terminal_width`), `test_cli_loop_queue.py`.
3. **runner + summary + delete.** Create the two modules, repoint the ~34
   `patch("little_loops.cli.loop._helpers.subprocess.Popen")` sites in
   `test_cli_loop_background.py` and the one in `test_ll_loop_execution.py:488`,
   the `_helpers.datetime` monkeypatch at `test_cli_loop_background.py:1408`,
   `mcp_server/tools.py:684`, `mcp_server/tasks.py:104`,
   `test_cross_host_baseline.py` (10 sites), `test_feat_3151_mcp_start_path.py`,
   `test_feat_3168_stdio_policy_enforcement.py`, `test_usage_reporter.py`.
   Repoint `test_enh3184_spawn_site_guard.py:38`'s path pin to
   `little_loops/cli/loop/runner.py` with the same `(2, 0)` count. Delete
   `_helpers.py`. Add `scripts/tests/test_enh2776_no_loop_helpers_module.py`
   asserting (a) the file does not exist and (b) no `.py` under
   `scripts/little_loops/` or `scripts/tests/` contains the string
   `cli.loop._helpers` — mirror of `test_enh3097_no_mixed_automation_kwargs.py`.
4. **Docs** (all in step 3's commit): the eleven locations in Integration
   Map -> Documentation, plus `skills/review-loop/reference.md:848`,
   `test_review_loop.py:1078` comment, `test_verify_package_data.py` example
   string, `fsm/cost_graph.py:90,129` and `fsm/types.py:21` docstring cites.

### Decisions (resolved 2026-09-02)

- **No re-export shim; delete `_helpers.py` in this issue.** The research
  correctly notes codebase practice skews "keep shims indefinitely", but a
  shim is actively hazardous for this specific module, not merely untidy:
  (a) `patch("little_loops.cli.loop._helpers.subprocess.Popen")` would keep
  *succeeding* through a shim but stop affecting `run_background`'s real
  module, so ~34 tests would silently spawn real `ll-loop` subprocesses;
  (b) tests that assign `_h._loop_shutdown_requested = True` through a shim
  write to the shim's namespace, not the module the handler reads — a
  silent no-op; (c) `test_enh3184_spawn_site_guard.py` pins the literal
  path. A shim that satisfies imports but not patches is the worst outcome.
  The ENH-3097 "remove + permanent guard test" precedent is the right one.
- **Cycle break = move `_format_history_event` down into `feed.py`**, not
  keep the deferred import. It is a pure formatter over an event dict with
  no `info.py`-internal dependencies.
- **`load_loop` goes to `fsm/`, not a new loader module under `cli/loop/`.**
  It is two lines over `resolve_loop_path`, already in `fsm/loop_paths.py`,
  and has a non-CLI caller.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Named modules under `cli/loop/` are conventionally titled after the subcommand verbs they own, one module per subcommand group — evidence: `lifecycle.py` ("status, stop, resume"), `info.py` ("list, history, show"), `config_cmds.py` ("validate, install"), `testing.py` ("test, simulate"), `queue.py` ("list, remove"). `layout.py` is the one precedent for the other shape this split needs — a shared rendering *engine* extracted from a larger file ("Extracted from info.py and extended with adaptive layout capabilities"), not a subcommand grouping — directly applicable to `_helpers.py`'s diagram/pinned-pane rendering cluster.
- Shared-but-internal plumbing consumed by multiple named siblings gets its own underscore-prefixed module rather than living inside any one subcommand module — evidence: `_scaffold_core.py` ("Only the genuinely-shared bits live here... the `ScaffoldResult` report shape, and clean-YAML serialization"), consumed by `scaffold_eval.py`/`scaffold_verify.py`.
- Deferred (function-local) imports are this codebase's standing convention for breaking a load-time cycle, applied independently in at least five module pairs, not a one-off invented for `_helpers`/`info`: `_helpers.py` itself already breaks a second, separate cycle with `layout.py` the same way, at three call sites (`_helpers.py:363-369`, `:388-390`, `:500-506`, one with an explicit comment "Local import avoids the layout↔_helpers module-load cycle"); `parallel/worker_pool.py:652-658` (cycle with `test_tamper_guard`); `ready_issue.py:32-37` (cycle with `config.core`, which also documents a `__getattr__`-based lazy re-export as a second variant of the same technique); `hooks/__init__.py:137-140`. Every site's comment names the concrete import chain being broken.
- ENH-2773's prior move of `resolve_loop_path`/`get_builtin_loops_dir` out of `_helpers.py` left a permanent re-export shim behind (`_helpers.py:27`: `from little_loops.fsm.loop_paths import get_builtin_loops_dir, resolve_loop_path`) rather than updating the sibling importers to the new location — `info.py`, `lifecycle.py`, `config_cmds.py`, `edit_routes.py`, and the top-level `cli/queue.py` (deferred) all still import these two names from `_helpers`, not from `fsm.loop_paths`, today. This is direct precedent that "moved but re-exported from the old location" is this codebase's actual behavior for a partial extraction, not merely a stated intent.
- No codebase precedent was found for actually **deleting** a whole-module re-export shim once its importers migrate. The two comparable whole-module shims found (`cli/adapt_skills_for_codex.py`, `cli/loop/queue.py`/`queue_store.py`) state in their own docstrings that they are kept **indefinitely** as compatibility surfaces, not pending removal. The one "removed once migrated" precedent found (ENH-3097/ENH-3261) operated at the function-kwarg level, not the whole-module level, and was paired with a permanent regression test (`test_enh3097_no_mixed_automation_kwargs.py`) asserting the legacy shape never reappears. This is a live tension with this issue's own plan to "delete the shim once no importers remain" (item 3 above) — the codebase's revealed practice for shims skews toward "kept indefinitely," not "deleted."

## Impact

- **Severity**: Medium
- **Effort**: Large (re-rated 2026-09-02 from Medium) — 7 new/extended
  modules, 14 production importers, ~20 test files with ~50 individual
  patch-string/import repoints, ~15 doc citations.
- **Risk**: Medium (re-rated 2026-09-02 from Low) — signal handlers,
  mutable module globals, and subprocess spawning are the clusters most
  likely to pass a vacuous test if a patch target is mis-repointed; the
  three-commit sequencing and the no-shim decision exist to keep each
  failure loud.
- **Breaking Change**: No (no public CLI or config surface changes;
  `little_loops.cli.loop._helpers` was underscore-private).

## Scope Boundaries

- **In scope**: everything in Suggested Approach steps 1-4; the
  `_format_history_event` move out of `info.py`; the ENH-2773 shim
  consumers' repoint to `fsm.loop_paths`.
- **Out of scope**: `cli/sprint/_helpers.py` (same name, different module —
  see Documentation note); any behavior change inside the moved functions;
  splitting `run_foreground` (~280 lines) itself; ENH-2943's and ENH-3233's
  own `_helpers.py` line citations (refresh those issues after this lands,
  not as part of it); the `fsm/cost_graph.py` docstring's stale line numbers
  beyond repointing the module name.

## Acceptance Criteria

- [x] `scripts/little_loops/cli/loop/_helpers.py` does not exist.
- [x] `grep -rn "cli.loop._helpers" scripts/ docs/ skills/` returns zero
      hits (the new guard test enforces the `scripts/` half permanently).
      **Note**: intentional "Relocated from `cli/loop/_helpers.py`"
      historical-pointer docstrings remain in the new modules themselves
      (and in a handful of out-of-scope fixture/research docs) — the
      literal shell command still matches those as prose; the guard test's
      actual enforcement (`.py`-scoped, self-excluding, checked in CI) is
      the real mechanism and passes.
- [x] No file under `scripts/little_loops/fsm/` or
      `scripts/little_loops/analytics/` imports from `little_loops.cli`
      (`grep -rn "from little_loops.cli" scripts/little_loops/fsm scripts/little_loops/analytics` is empty).
      **Note**: `fsm/persistence.py`'s pre-existing deferred `cli.artifact`
      import (unrelated to `_helpers.py`, predates this issue) is out of
      scope and was left untouched.
- [x] No deferred (function-local) import exists between any two of
      `cli/loop/{signals,feed,header,runner,summary,info,layout}.py` — all
      imports among them are module-level and acyclic.
- [x] `grep -c "cli.loop.runner.subprocess.Popen" scripts/tests/test_cli_loop_background.py`
      reports at least 33 (the current `_helpers.subprocess.Popen` count),
      `grep -rn "_helpers.subprocess" scripts/tests/` is empty, and
      `test_cli_loop_background.py` passes — i.e. every Popen patch was
      repointed, none dropped.
- [x] `test_cli_loop_background.py::TestLoopSignalHandler` and
      `test_cli_loop_lifecycle.py` signal tests pass while mutating globals
      on `cli.loop.signals`, not a shim.
- [x] `test_fsm_signal_integration.py` (black-box real-signal test) passes.
- [x] `test_enh3184_spawn_site_guard.py` passes with its path pin repointed.
      **Deviation**: the single `_helpers.py: (2, 0)` entry became two
      entries, `runner.py: (1, 0)` and `summary.py: (1, 0)` — the file's 2
      spawns (`run_background`'s `subprocess.Popen`,
      `_run_cross_host_validation`'s `subprocess.run`) split across the two
      destination modules along with the functions that make them.
- [x] `test_fsm_loop_paths.py` no longer asserts a `_helpers` re-export.
- [x] All doc citations in Integration Map -> Documentation reference the
      new module names; `docs/ARCHITECTURE.md`'s two `cli/loop/` tree
      diagrams list the new modules.
- [x] `python -m pytest scripts/tests/`, `ruff check scripts/`,
      `python -m mypy scripts/little_loops/` all exit 0 after **each** of
      the three commits, not only the last.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` (2,255 lines, 37 top-level defs:
  35 functions + `_TeeWriter`/`StateFeedRenderer` classes) — the grab-bag
  itself. Clusters by responsibility (see Program Design → Signatures):
  signal handling, queue helpers, diagram/pinned-pane rendering, artifact/path
  header helpers, FSM-context seeding, loop loading, run orchestration,
  summary printing.

### Dependent Files (Callers/Importers)
- Module-level importers (7): `cli/loop/config_cmds.py:10`,
  `cli/loop/queue.py:19`, `cli/loop/run.py:17`, `cli/loop/testing.py:8`,
  `cli/loop/lifecycle.py:15`, `cli/loop/info.py:21`,
  `cli/loop/edit_routes.py:8`.
- Deferred (function-local) importers (7, invisible to `ll-code
  importers-of`): `cli/loop/audit.py:104`, `cli/doctor.py:533`,
  `cli/queue.py:147` (the top-level `cli/queue.py`, distinct from
  `cli/loop/queue.py`), `mcp_server/tools.py:684`, `mcp_server/tasks.py:104`,
  `fsm/executor.py:1076`, `analytics/variance.py:224`.
- Test importers (13+): `test_ll_loop_display.py:14`,
  `test_usage_reporter.py:8`, `test_state_feed_renderer.py:8`,
  `test_cli_loop_background.py:19`, `test_cli_loop_layout.py`,
  `test_loop_layout_alignment.py`, `test_cli_loop_queue.py`,
  `test_rn_plan.py`, `test_builtin_loops.py`,
  `test_cli_doctor_install_checks.py`, `test_advisor.py`,
  `test_feat_3151_mcp_start_path.py`, `test_feat_3168_stdio_policy_enforcement.py`.
  Most reach private (`_`-prefixed) names directly for white-box testing, not
  just the public surface.
- `cli/logs.py:20` and three test files (`test_cli_loop_lifecycle.py`,
  `test_cli_loop_next.py`, `test_loop_show_overview.py`) reach `_helpers.py`
  only transitively, through `info.py`/`config_cmds.py`/`lifecycle.py` — not
  direct importers, no update required on their part.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- **Correction**: `test_cli_loop_lifecycle.py` above is misclassified as
  transitive-only. It is a direct white-box importer: `:905` does
  `from little_loops.cli.loop._helpers import _loop_signal_handler`, `:909`
  does `import little_loops.cli.loop._helpers as _h` and mutates module
  globals (`_h._loop_shutdown_requested`, `_h._loop_executor`,
  `_h._loop_pid_file`, `_h._using_alt_screen`) before invoking the handler,
  and `:3081,3117,3145` patch `little_loops.cli.loop._helpers.StateFeedRenderer`
  directly inside `cmd_monitor` tests.
- Additional deferred (function-local) import call sites in already-listed
  importer files, beyond their known module-level import line: `cli/loop/audit.py:265`
  (`load_loop_with_spec`), `cli/loop/info.py:1709` (`seed_confidence_thresholds`),
  `cli/loop/testing.py:218` (`derive_input_hash`), `cli/loop/run.py:204`
  (`derive_input_hash`), `cli/loop/lifecycle.py:674` (`derive_input_hash`),
  `cli/loop/lifecycle.py:747` (`run_foreground`), `cli/loop/lifecycle.py:834`
  (`StateFeedRenderer`, `_install_sigwinch_handler`, `_restore_sigwinch_handler`
  — comment notes this is deliberately late-imported so test patches take
  effect at call time).
- New test-file importers not in the known list: `scripts/tests/test_deep_research_arxiv.py:221`
  and `scripts/tests/test_deep_research.py:194` (re-export shim only:
  `get_builtin_loops_dir`, `resolve_loop_path`); `scripts/tests/test_ll_loop_execution.py:488`
  (`patch("little_loops.cli.loop._helpers.subprocess.Popen")`);
  `scripts/tests/test_cli_loop_testing.py:271` (`load_loop`);
  `scripts/tests/test_fsm_loop_paths.py:67-71` —
  `test_cli_helpers_reexports_resolve_loop_path_and_builtin_dir` does
  `from little_loops.cli.loop import _helpers` and asserts
  `_helpers.resolve_loop_path is resolve_loop_path` /
  `_helpers.get_builtin_loops_dir is get_builtin_loops_dir` — a re-export
  identity test that must keep passing however the split lands;
  `scripts/tests/test_cross_host_baseline.py:225,288,373-588` (`run_background`,
  `_run_cross_host_validation`, 10 sites total).
- `skills/review-loop/reference.md:848` — prose reference to
  `` `scripts/little_loops/cli/loop/_helpers.py:EXIT_CODES` `` (skill
  companion doc, not `SKILL.md` itself).

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_
- **Correction**: `mcp_server/tasks.py`'s deferred import is at line 104, not
  line 224 as previously recorded, and imports `_make_instance_id` — a symbol
  not previously in the traced key-symbol list:
  `from little_loops.cli.loop._helpers import _make_instance_id`.
- `scripts/little_loops/cli/doctor.py:533,540` — imports and calls
  `get_builtin_loops_dir()` directly (`loop_dirs = {get_builtin_loops_dir()}`);
  `scripts/tests/test_cli_doctor_install_checks.py:443,465,484`
  (`TestLoopValidity`) monkeypatches
  `"little_loops.cli.loop._helpers.get_builtin_loops_dir"` to drive this — a
  cross-package dependency (outside `cli/loop/`) not previously called out.
- `scripts/tests/test_rn_plan.py:308` —
  `from little_loops.cli.loop._helpers import get_builtin_loops_dir,
  resolve_loop_path`, called directly to assert `rn-plan` resolves as a
  built-in loop.
- New `mock.patch` string targets on `little_loops.cli.loop._helpers.*` beyond
  those already documented: `test_ll_loop_display.py:1724,1741,1758,1773,1822,1854`
  (`terminal_width`, imported into `_helpers` from `cli.output` and patched at
  the `_helpers` site), `test_ll_loop_display.py:2539,2632,2706,3860` and
  `test_cli_loop_background.py:844,901` (`load_loop`), `test_advisor.py:232`
  (`derive_input_hash`).
- `scripts/tests/test_cli_loop_background.py:1408-1422` —
  `monkeypatch.setattr(_helpers, "datetime", _FrozenDatetime)`, freezing the
  `datetime` name imported into `_helpers`'s module namespace (used by
  `_make_instance_id`). Whichever new module ends up owning `_make_instance_id`
  must keep `datetime` patchable as a module-level name from the test's
  perspective.
- `scripts/tests/test_enh3184_spawn_site_guard.py:38` —
  `_TASK_PATH_MODULES` pins the literal relative path
  `"little_loops/cli/loop/_helpers.py"` to an exact AST-derived
  subprocess-spawn count `(2, 0)`. This breaks the moment `_helpers.py` is
  dissolved (the path stops existing) and needs repointing to wherever the 2
  spawns relocate.
- `scripts/tests/test_verify_package_data.py:112,161,165` — reuses the
  `cli/loop/_helpers.py` path shape as a synthetic naming-pattern fixture
  example (not a live import of the real file); weaker dependency, but the
  example string should be updated for accuracy once the file no longer
  exists.
- `scripts/tests/test_fsm_signal_integration.py` — a black-box,
  subprocess-based integration test (e.g. `test_second_signal_force_exit_archives`)
  that spawns a real `ll-loop run` child and delivers real `SIGINT`/`SIGTERM`,
  exercising `_loop_signal_handler`'s force-exit branch end-to-end. Cited only
  in a comment (`:285-288`, `_helpers.py:172-173`), invisible to import-based
  greps — a genuinely different coverage mode from the white-box tests
  already listed for the signal-handling cluster.

### Conventions in Force
- Named modules under `cli/loop/` are titled after the subcommand verbs they
  own, one module per subcommand group — evidence: `lifecycle.py` ("status,
  stop, resume"), `info.py` ("list, history, show"), `config_cmds.py`
  ("validate, install"), `testing.py` ("test, simulate"), `queue.py` ("list,
  remove"). `layout.py` is this codebase's precedent for the other shape —
  a shared rendering engine extracted from a larger file, not a subcommand
  grouping.
- Shared-but-internal plumbing consumed by multiple named siblings gets its
  own underscore-prefixed module rather than living inside any one subcommand
  module — evidence: `_scaffold_core.py`, consumed by `scaffold_eval.py`/
  `scaffold_verify.py`.
- Deferred (function-local) imports are this codebase's standing convention
  for breaking a load-time cycle — confirmed independently in at least five
  module pairs, including `_helpers.py`'s own second cycle with `layout.py`
  (three call sites). See Proposed Solution → Codebase Research Findings for
  full evidence.
- ENH-2773's prior partial extraction (`resolve_loop_path`/
  `get_builtin_loops_dir`) left a permanent re-export shim in `_helpers.py`
  rather than updating sibling importers to the new location — direct
  precedent that this codebase's actual practice for a partial extraction is
  "move but re-export," not "move and repoint every caller."

### Tests
- No test file exists specifically for `_helpers.py` as a unit — it is
  exercised almost entirely through white-box imports of individual private
  functions from the 13+ test files listed above, not one dedicated test
  module. A split needs every one of those import paths preserved or updated
  individually; there is no single test file to redirect.
- `scripts/tests/test_helpers.py` is a false positive by name only — it tests
  `tests/helpers.py`'s `sgr_codes` utility, unrelated to
  `cli/loop/_helpers.py`.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- **Mutable module-global coupling** (new risk, not just import-path
  coupling): `test_cli_loop_background.py::TestLoopSignalHandler` does
  `import little_loops.cli.loop._helpers as helpers_module` and directly
  pokes/reads module-level globals (`_loop_shutdown_requested`,
  `_loop_executor`, `_loop_pid_file`, `_loop_marker_path`,
  `_using_alt_screen`, `_needs_redraw`, `_original_sigwinch`);
  `test_cli_loop_lifecycle.py:905-919` does the same via `_h.<global>`. These
  globals must move together with `_loop_signal_handler`/
  `register_loop_signal_handlers` to the same destination module, or the
  split needs an explicit shared-state object.
- `test_cli_loop_background.py` has ~40 call sites of
  `patch("little_loops.cli.loop._helpers.subprocess.Popen")` — coupling to
  `subprocess` being imported into `_helpers`'s own module namespace, not
  wherever `run_background` ends up. All ~40 need repointing if `run_background`
  moves to a different module.
- **Cluster → test-file map** (which of the 13+ known test files exercises
  which of the 8 responsibility clusters, so imports can be repointed
  correctly): signal handling → `test_cli_loop_background.py`,
  `test_cli_loop_lifecycle.py`; queue helpers → `test_cli_loop_queue.py`;
  diagram/pinned-pane rendering → `test_cli_loop_layout.py`,
  `test_loop_layout_alignment.py`, `test_ll_loop_display.py`,
  `test_state_feed_renderer.py`, `test_cli_loop_lifecycle.py`
  (`StateFeedRenderer` patches); artifact/path header helpers →
  `test_state_feed_renderer.py` only; FSM-context seeding →
  `test_builtin_loops.py`, `test_advisor.py`; loop loading →
  `test_ll_loop_display.py`, `test_cli_loop_background.py`,
  `test_cli_loop_testing.py`; run orchestration →
  `test_cli_loop_background.py`, `test_ll_loop_display.py`,
  `test_feat_3151_mcp_start_path.py`, `test_feat_3168_stdio_policy_enforcement.py`,
  `test_cross_host_baseline.py`; summary printing → `test_usage_reporter.py`,
  `test_ll_loop_display.py`.
- **Untested functions** (no direct white-box test import found anywhere,
  black-box coverage only or none): `print_execution_plan` (its own
  `TestPrintExecutionPlan` class docstring is stale — claims the function is
  "nested in `main_loop()`", but it's top-level at `_helpers.py:1492`),
  `load_loop_with_spec`, `_print_cross_host_table`, `inject_design_context`,
  `_relativize_to_cwd`, `_display_loop_path`, `_effort_code`. Flag these as
  higher-risk relocations since no test will catch a signature/behavior
  change directly.
- **Precedent for this exact shape** (grab-bag reached mostly via scattered
  white-box `patch()` strings, not one dedicated test file): `ENH-469`
  (`cli/sprint.py` → `cli/sprint/` package, done 2026-02-24, already cited in
  Conventions in Force) is the closer analogue than `session_store`/
  `fsm_validation` — its resolution required literally repointing 9
  `monkeypatch`/`patch` string targets like
  `"little_loops.cli.sprint.ParallelOrchestrator"` to
  `"little_loops.cli.sprint.run.ParallelOrchestrator"`, while a package-level
  `__init__.py` re-export meant callers importing through the package needed
  no change. The same two-tier strategy applies here: `_helpers`'s
  module-qualified `patch()` strings need literal repointing; anything
  importing through a future `_helpers.py` shim's re-export does not.

### Documentation
- `docs/reference/API.md:4401,4406` — cites literal
  `scripts/little_loops/cli/loop/_helpers.py:157-173` and `:103-107` line
  ranges documenting the SIGINT/signal-handling contract; goes stale the
  moment signal handling moves to a named module.
- `docs/ARCHITECTURE.md:161,183` — two `cli/loop/` directory-tree diagrams
  list `_helpers.py      # Shared utilities`; needs updating to whichever
  named modules replace it.
- `docs/development/TESTING.md` — a `monkeypatch.setattr` example references
  `little_loops.cli.loop._helpers` directly (alongside the sibling
  `cli.sprint._helpers` example, an out-of-scope module sharing the same
  naming pattern).

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — cites `_helpers.py:121-172`
  and `:126-148` for the SIGINT/SIGTERM handler and second-Ctrl-C force-exit
  branch, independently of the `docs/reference/API.md:4401,4406` citations.
- `docs/reference/OUTPUT_STYLING.md` — references `StateFeedRenderer.handle_event()`
  and `print_execution_plan()` by name, tying `cli.colors.fsm_edge_labels`
  behavior to those two functions.
- `docs/ARCHITECTURE.md` — a location distinct from the known L161/183 tree
  diagrams: the extension-wiring table's `ll-loop monitor` row names
  `StateFeedRenderer` as the event-forwarding target.
- `docs/reference/CLI.md` — the `ll-loop monitor` subcommand description
  names `StateFeedRenderer` as shared with `ll-loop run`.
- `docs/reference/API.md` — a location distinct from the known L4401/4406
  citations: the advisor-consult API doc states it "structurally never
  touches `derive_input_hash`" as a negative-coupling proof point.
- `docs/guides/MCP_SERVER_GUIDE.md` — cites `mcp_server/tools.py:699-705`
  wrapping `run_background()` in `redirect_stdout`/`redirect_stderr` as the
  canonical "wrap a still-printing function" extraction example.
- Note: `docs/guides/SPRINT_GUIDE.md` mentions a same-named but *different*
  module, `cli/sprint/_helpers.py` — not this issue's target; flagged only to
  avoid cross-contamination during a grep-driven migration.

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_
- `docs/reference/CLI.md:872` — a separate location from the already-known
  `ll-loop monitor`/`StateFeedRenderer` citation: the `ll-loop queue list`
  section's "Pruning side effect" paragraph names `read_queue_entries()`
  (`_helpers.py:181-209`) as the mechanism behind dead-PID entry cleanup.
- `docs/observability/tier0-traces.md:138-142,230`,
  `docs/observability/streaming-parity-traces.md:58-59`,
  `docs/observability/otel-mapping.md:60` — all three cite
  `_print_usage_summary` by name (two with explicit line-number anchors,
  `_helpers.py:1742-1767`/`:1699-1702`, both already stale against the
  current file — `_print_usage_summary` is now at line 2003 — independent of
  this split but compounded by it).
- `scripts/tests/test_review_loop.py:1078-1084` — hardcodes a literal
  duplicate of a subset of `EXIT_CODES`'s semantics in a comment-cited
  assertion (`# From _helpers.py EXIT_CODES: exit code 1 covers max_steps,
  timeout, cycle_detected`) rather than importing the dict; the file-citation
  comment goes stale on relocation even though the assertion itself won't
  break.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02 (post-rewrite sweep
against the new target module map):_
- `scripts/tests/test_ll_loop_display.py:14` —
  `from little_loops.cli.loop._helpers import EXIT_CODES, run_foreground`;
  `EXIT_CODES` (`_helpers.py:70`) is asserted key-by-key at `:2854-2868`.
  `EXIT_CODES` was not in any prior key-symbol list; the module map assigns
  it to `runner.py`, so this import repoints there in step 3.
- `scripts/tests/test_cli_loop_layout.py` imports `with_diagram_color` and
  `MIN_ACTION_ROWS` directly — both go to `feed.py` in step 2.
- `_format_history_event` (the cycle-break move out of `info.py:858`) has
  **zero** test import or `patch()` sites; the only test mentions are
  docstring prose at `test_ll_loop_display.py:4186,4204,4216`. The move is
  unobserved by any white-box test, so it cannot silently break a patch —
  low-risk.
- `_TeeWriter` has zero references outside `_helpers.py` — moves to
  `runner.py` with no repoints.
- `terminal_width`/`terminal_size` patched at the `_helpers` site: 7 sites
  total across `scripts/tests/` (the earlier list of six line numbers in
  `test_ll_loop_display.py` is one short). All repoint to `feed.py`, which
  must import both names from `cli.output` at module level.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:1156` — a YAML
  comment cites `cli/loop/_helpers.py` `` `_is_success` ``. No function of
  that name exists anywhere in `scripts/little_loops/` (unfiltered grep);
  the comment is already stale independent of this split. Fix or drop it
  while touching docs in step 4.
- Non-Python sweep (`skills/`, `commands/`, `agents/`, `hooks/`,
  `scripts/little_loops/loops/`) found no other live references beyond the
  already-recorded `skills/review-loop/reference.md:848` and the YAML
  comment above — the non-`.py` surface is now fully enumerated.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `cli/loop/_helpers.py` | Signal handling (`register_loop_signal_handlers`, SIGWINCH handlers) | PRESERVED | Relocates to a named module; module-level and deferred callers continue via re-export until the shim is deleted |
| `cli/loop/_helpers.py` | Diagram/pinned-pane rendering (`StateFeedRenderer` + 9 helper functions) | PRESERVED | Relocates; no external production importer today, only `test_state_feed_renderer.py` |
| `cli/loop/_helpers.py` | Loop loading (`load_loop`, `load_loop_with_spec`) | PRESERVED | Relocates; both call the re-exported `resolve_loop_path` |
| `cli/loop/_helpers.py` | Run orchestration (`run_background`, `run_foreground`, `print_execution_plan`) | PRESERVED | Relocates; `run_foreground`'s deferred `info._format_history_event` import must move with it |
| `cli/loop/_helpers.py` | `resolve_loop_path`/`get_builtin_loops_dir` re-export (ENH-2773 shim) | REMOVED (consumers repointed) | Step 1 repoints `info.py`, `lifecycle.py`, `config_cmds.py`, `edit_routes.py`, `cli/queue.py`, `cli/doctor.py` and the test patch strings to `fsm.loop_paths`; the shim goes with the file. Decision rationale in Proposed Solution -> Decisions. |
| `cli/loop/_helpers.py` | FSM-context seeding (`seed_confidence_thresholds`, `derive_input_hash`, `inject_design_context`) | PRESERVED, relocated to `fsm/context_seed.py` | Removes the last core->CLI import (`fsm/executor.py:1076`) |
| `cli/loop/info.py` | `_format_history_event` | PRESERVED, relocated to `cli/loop/feed.py` | The `_helpers`↔`info` cycle break; `info.py` imports it back downward |

## Program Design

### Types
- No new data shape is introduced. `StateFeedRenderer` and `_TeeWriter`
  (the file's only two classes) relocate unchanged.

### Signatures
- `run_background(loop_name: str, args: argparse.Namespace, loops_dir: Path, subcommand: str = "run", instance_id: str | None = None) -> int` (`scripts/little_loops/cli/loop/_helpers.py:1552`)
- `run_foreground(...)` (`scripts/little_loops/cli/loop/_helpers.py:1724`) — the largest function (~280 lines); wires `StateFeedRenderer`, tees stdout/stderr via `_TeeWriter`, and (only when `--follow` is set) deferred-imports `info._format_history_event` at `_helpers.py:1845-1847` — the `info.py` half of the cycle this issue names.
- `print_execution_plan(fsm: FSMLoop, edge_label_colors: dict[str, str] | None = None) -> None` (`scripts/little_loops/cli/loop/_helpers.py:1492`)
- `load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop` (`scripts/little_loops/cli/loop/_helpers.py:1454`)
- `register_loop_signal_handlers(executor: Any, pid_file: Path | None = None, marker_path: Path | None = None) -> None` (`scripts/little_loops/cli/loop/_helpers.py:226`)
- `derive_input_hash(context: dict[str, Any]) -> None` (`scripts/little_loops/cli/loop/_helpers.py:1437`) and `seed_confidence_thresholds(context: dict[str, Any], config: Any = None) -> None` (`scripts/little_loops/cli/loop/_helpers.py:1372`) — the pair `fsm/executor.py:1076` imports (see Finding → Codebase Research Findings for the corrected core-code dependency).

### Call Path
- `cli/loop/run.py:274` (`cmd_run`) -> `_helpers.print_execution_plan()` (`scripts/little_loops/cli/loop/_helpers.py:1492`)
- `cli/loop/run.py:346` (`cmd_run`) -> `_helpers.run_background()` (`scripts/little_loops/cli/loop/_helpers.py:1552`)
- `cli/loop/info.py:21` (module-level) -> `_helpers.get_builtin_loops_dir`/`load_loop_with_spec`/`resolve_loop_path`/`with_diagram_color`; `_helpers.py:1845-1847` (inside `run_foreground`, deferred, `--follow`-gated) -> `info._format_history_event` — the confirmed current shape of the `_helpers`↔`info` cycle (line numbers corrected from the issue's original `_helpers.py:1847` ↔ `info.py:21,1709` citation; `info.py:1709`'s own deferred `_helpers` import is not part of the cycle — `info.py` already imports `_helpers` at module level, so that second deferred import adds no new circularity).
- `fsm/executor.py:1076` (deferred, unconditional) -> `_helpers.derive_input_hash()`/`_helpers.seed_confidence_thresholds()` — the corrected core-code dependency (see Finding → Codebase Research Findings; supersedes the issue's original `fsm/validation.py:485,566` citation, which is stale).
- `run_foreground()` (`_helpers.py:1724`) -> `StateFeedRenderer()` construction (`_helpers.py:1784`) -> `executor.event_bus.register(renderer.handle_event)` (`_helpers.py:1811`/`:1813`) — an undocumented edge from run orchestration into the diagram/pinned-pane cluster, currently same-file so no import is required; becomes a real inter-module import once the two clusters split.
- `StateFeedRenderer.handle_event()` (`_helpers.py:920`) -> `load_loop()` (`_helpers.py:956`, loop-loading cluster) — one hop downstream of the edge above, for `state_enter` events on a child loop.
- `cli/loop/lifecycle.py:834` (`cmd_monitor`, deferred import) -> `StateFeedRenderer`/`_install_sigwinch_handler`/`_restore_sigwinch_handler` — a second, independent path into the diagram cluster that does not go through `run_foreground` at all.

### Decision Rules
N/A — no new decision logic; this issue is a structural module split
introducing no new gate, threshold, or classification rule.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- `run_foreground()` (`_helpers.py:1724`, ~280 lines, the "run orchestration" cluster's largest function) makes direct in-module calls into three other named clusters, not just its own: signal handling (`_install_sigwinch_handler:269`, `_restore_sigwinch_handler:284`, both alt-screen-branch-gated), artifact/path-header helpers (`_artifact_lines:1262`, `_effort_code:1309`, `_relativize_to_cwd:1224`), and summary printing (`_print_usage_summary:2003`, `_print_ab_summary:2031`, `_run_cross_host_validation:2121` which itself calls `_print_cross_host_table:2212`). It also directly constructs `StateFeedRenderer` (`:1784`, diagram/pinned-pane cluster) and registers `renderer.handle_event` on the event bus (`:1811`/`:1813`) — a same-file construction requiring no import today, but becoming a fourth inter-cluster edge once split. `run_foreground` therefore touches 4 of the 8 named clusters directly.
- Module-global `_using_alt_screen` is a cross-cluster shared-mutable-state coupling independent of any function call: `run_foreground` sets it (`:1873`, `:1898`) while `_loop_signal_handler` (signal-handling cluster, `:139`) reads it — whichever module each ends up in, this global must stay shared or be replaced with an explicit shared-state object.
- The SIGWINCH pair (`_install_sigwinch_handler:269-281`, `_restore_sigwinch_handler:284-299`) is a narrower sub-scope of "signal handling", distinct from the SIGINT/SIGTERM shutdown handling (`register_loop_signal_handlers`/`_loop_signal_handler`, `:226-250`/`:127-178`): different signal (`SIGWINCH`), different module globals (`_original_sigwinch`/`_needs_redraw`, vs. `_loop_shutdown_requested`/`_loop_executor`/`_loop_pid_file`/`_loop_marker_path`), and its only consumer of `_needs_redraw` is `StateFeedRenderer.handle_event()` (diagram cluster, `:925`), not the executor shutdown path.
- A second, independent path into the diagram cluster exists beyond `run_foreground`: `cmd_monitor` (`cli/loop/lifecycle.py:834`, per the issue's own wiring-pass citation) reaches `StateFeedRenderer`/`_install_sigwinch_handler`/`_restore_sigwinch_handler` via its own deferred import, not through `run_foreground` at all.
- `derive_input_hash` (`:1437-1451`) and `seed_confidence_thresholds` (`:1372-1398`) are confirmed fully self-contained leaves: neither calls the other or any other `_helpers.py` function; `derive_input_hash` calls only stdlib `hashlib`, and `seed_confidence_thresholds`'s only dependency is a deferred import of external `little_loops.config.BRConfig` (`:1390`) when `config` isn't passed in. Both can relocate independently with no internal `_helpers.py` coupling to carry along.

## Related Key Documentation

- `docs/reference/API.md` — catalogs `cli/*` entry points module-by-module; splitting `_helpers.py` into named modules changes what that catalog should list.
- `docs/ARCHITECTURE.md` — covers module placement/decomposition questions directly; this issue is exactly that kind of "where should this code live" call.

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: `_helpers.py` still
exists at ~2,183 lines (grown from 2,156). `resolve_loop_path` has already
moved to fsm/loop_paths.py per ENH-2773 (status: done) — that specific
sub-step is complete; remaining decomposition work is still open.

**2026-09-02** (`/ll:verify-issues`): Core finding still real; `_helpers.py`
now 2,255 lines (36 top-level defs), the `info.py` deferred-import cycle
still exists, `resolve_loop_path` confirmed still re-exported from
`fsm/loop_paths.py`. Corrected drifted cycle line citations. Also changed
`depends_on: EPIC-2938` to `relates_to: EPIC-2938` in frontmatter — the
direction was backwards: `EPIC-2789`'s and `EPIC-2938`'s own
`/ll:audit-issue-conflicts` notes both say ENH-2776 should sequence *before*
EPIC-2938's new `cli/loop/*` additions, not that this issue is blocked on
EPIC-2938 first. `depends_on` as written would stall this refactor on an
unrelated epic. Verdict: NON_VALID (dependency-reference fix; content
otherwise accurate).

**2026-09-02** (pre-implementation review): re-verified the def inventory
(37 defs at the cited lines), the cross-layer importers (`fsm/executor.py:1076`,
`analytics/variance.py:224` — the latter was mis-cited as `:265`),
`mcp_server/tasks.py:104`, that `layout.py` does not import `_helpers` (so
that cycle is one-directional and disappears once rendering moves), that
`_format_history_event` (`info.py:858`) is a self-contained formatter, and
that the stale `epic/epic-2938` branch has no unmerged `cli/loop/` changes.
Reconciled the Suggested Approach with the research (removed the completed
ENH-2773 step, fixed the wrong importer list, added a concrete module map and
three-commit plan), decided against a re-export shim with rationale, re-rated
Effort to Large and Risk to Medium, added Current/Expected Behavior, Scope
Boundaries, and Acceptance Criteria. The earlier NON_VALID verdict was for
the dependency-direction fix, which has been applied. Verdict: VALID.

## Resolution

Implemented as three independently-green commits, exactly matching the
Suggested Approach's plan:

1. **fsm-layer moves** (`7c4ed55ab`) — `fsm/context_seed.py` (new:
   `seed_confidence_thresholds`, `derive_input_hash`, `inject_design_context`)
   and `load_loop`/`load_loop_with_spec` appended to `fsm/loop_paths.py`;
   repointed `fsm/executor.py`, `analytics/variance.py`, every `cli/loop/*`
   consumer, the ENH-2773 shim consumers, and their test patch strings.
   Deleted the now-vacuous `_helpers` re-export identity test.
2. **signals + feed + header + queue** (`43c762c64`) — new
   `cli/loop/signals.py`, `cli/loop/feed.py`, `cli/loop/header.py`;
   `read_queue_entries`/`_is_earliest_waiter` moved into the existing
   `cli/loop/queue.py`. `_format_history_event` moved down from `info.py`
   into `feed.py` (the `_helpers`<->`info` cycle break); the `layout.py`
   imports that dodged the second cycle became module-level. Discovered and
   fixed a gap the issue's own research didn't catch: several tests patched
   `layout.<fn>` expecting the deferred-import call site to pick up the
   patch — once the call site moved to module-level imports in `feed.py`,
   those patches had to repoint to `feed.<fn>` (mock.patch affects the
   lookup site, not the definition site).
3. **runner + summary + delete** (`fc4f65436`) — new `cli/loop/runner.py`
   (`run_background`, `run_foreground`, `print_execution_plan`, `_TeeWriter`,
   `_make_instance_id`, `EXIT_CODES`) and `cli/loop/summary.py`
   (`_print_usage_summary`, `_print_ab_summary`, `_run_cross_host_validation`,
   `_print_cross_host_table`). Deleted `_helpers.py`; repointed the ~34
   `subprocess.Popen` test patches, the `datetime` monkeypatch, the
   ENH-3184 spawn-site guard's per-file table (split into two entries), and
   two production imports (`run.py`, `lifecycle.py`) the earlier steps had
   deliberately left pointing at `_helpers` until this step. Added
   `test_enh2776_no_loop_helpers_module.py` (ENH-3097 "remove + permanent
   guard test" precedent). Swept the remaining doc/test citations
   (`docs/ARCHITECTURE.md`'s two tree diagrams, `API.md`,
   `AUTOMATIC_HARNESSING_GUIDE.md`, `TESTING.md`, the two `tier0`/
   `streaming-parity` observability docs, `fsm/cost_graph.py`, `fsm/types.py`,
   `host_runner.py`, `worktree_utils.py`, `decisions.py`,
   `skills/review-loop/reference.md`, `test_review_loop.py`,
   `test_verify_package_data.py`'s synthetic fixture paths, and the stale
   YAML comment in `auto-refine-and-implement.yaml`).

Both former deferred-import cycles (`_helpers`<->`info`, `_helpers`<->
`layout`) are gone; every inter-module import among the split modules is
module-level and acyclic, matching the target DAG in Suggested Approach.
`python -m pytest scripts/tests/`, `ruff check scripts/`, and
`python -m mypy scripts/little_loops/` are clean after each commit (the one
consistently-failing test, `test_issue_parser.py::
TestBug3293DecisionRulesCorpusDifferential::test_only_pinned_files_gain_program_design_options`,
is caused by an unrelated pre-existing uncommitted change to a different
issue file and is not a regression from this work).

## Session Log
- `/ll:manage-issue` - 2026-09-03T06:17:59 - `5cb15e44-c94b-4293-b663-953a704c456e.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:56:30 - `7842a080-b0fe-422b-a8bd-a0e7be14b133.jsonl`
- `/ll:confidence-check` - 2026-09-03T03:55:11 - `01821a2b-4cf7-4cc7-bdc4-16881b6cbd8f.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:32:07 - `b08d9181-74d3-46eb-8d3a-a167537e57ed.jsonl`
- `/ll:refine-issue` - 2026-09-03T03:19:31 - `983e671b-5b21-4f7b-86e9-1898ea8c1563.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:06:46 - `e42909d5-e77d-478c-b142-52f1ba049345.jsonl`
- `/ll:refine-issue` - 2026-09-03T02:56:56 - `00f0e408-f05f-43a3-bdc7-1e52bd1f47ab.jsonl`
- `/ll:verify-issues` - 2026-09-03T02:27:51 - `ec373f26-c22d-4cdb-bcd2-9da717f53d54.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:57 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`

---

## Status

**Done** | Created: 2026-07-24 | Priority: P3

## Relationships

relates_to: ENH-2773
