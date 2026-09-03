---
id: ENH-2776
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: organization
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
verify_verdict: NON_VALID
relates_to:
- EPIC-2938
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

## Finding

### Current State

- 2,255 lines, 36 top-level defs behind an underscore-private "helpers" name.
- Imported by core code (`fsm/validation.py:485,566` — see ENH-2773) and by
  `cli/loop/info.py` in a 2-cycle (`_helpers.py:1847` ↔ `info.py:21,1709`)
  held apart by deferred imports.
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

Split by actual responsibility into named modules (e.g. loop-path resolution —
moving to `fsm/` per ENH-2773 — run inspection, output formatting), leaving
`_helpers.py` as a temporary re-export shim before deleting it.

### Suggested Approach

1. Inventory the 37 defs and cluster by concern; land `resolve_loop_path`'s
   move with ENH-2773 first.
2. Create named modules under `cli/loop/` for the remaining clusters; update
   importers (`__init__.py`, `info.py`, `lifecycle.py`, `layout.py`).
3. Break the `_helpers ↔ info` 2-cycle as part of the split; delete the shim
   once no importers remain.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Named modules under `cli/loop/` are conventionally titled after the subcommand verbs they own, one module per subcommand group — evidence: `lifecycle.py` ("status, stop, resume"), `info.py` ("list, history, show"), `config_cmds.py` ("validate, install"), `testing.py` ("test, simulate"), `queue.py` ("list, remove"). `layout.py` is the one precedent for the other shape this split needs — a shared rendering *engine* extracted from a larger file ("Extracted from info.py and extended with adaptive layout capabilities"), not a subcommand grouping — directly applicable to `_helpers.py`'s diagram/pinned-pane rendering cluster.
- Shared-but-internal plumbing consumed by multiple named siblings gets its own underscore-prefixed module rather than living inside any one subcommand module — evidence: `_scaffold_core.py` ("Only the genuinely-shared bits live here... the `ScaffoldResult` report shape, and clean-YAML serialization"), consumed by `scaffold_eval.py`/`scaffold_verify.py`.
- Deferred (function-local) imports are this codebase's standing convention for breaking a load-time cycle, applied independently in at least five module pairs, not a one-off invented for `_helpers`/`info`: `_helpers.py` itself already breaks a second, separate cycle with `layout.py` the same way, at three call sites (`_helpers.py:363-369`, `:388-390`, `:500-506`, one with an explicit comment "Local import avoids the layout↔_helpers module-load cycle"); `parallel/worker_pool.py:652-658` (cycle with `test_tamper_guard`); `ready_issue.py:32-37` (cycle with `config.core`, which also documents a `__getattr__`-based lazy re-export as a second variant of the same technique); `hooks/__init__.py:137-140`. Every site's comment names the concrete import chain being broken.
- ENH-2773's prior move of `resolve_loop_path`/`get_builtin_loops_dir` out of `_helpers.py` left a permanent re-export shim behind (`_helpers.py:27`: `from little_loops.fsm.loop_paths import get_builtin_loops_dir, resolve_loop_path`) rather than updating the sibling importers to the new location — `info.py`, `lifecycle.py`, `config_cmds.py`, `edit_routes.py`, and the top-level `cli/queue.py` (deferred) all still import these two names from `_helpers`, not from `fsm.loop_paths`, today. This is direct precedent that "moved but re-exported from the old location" is this codebase's actual behavior for a partial extraction, not merely a stated intent.
- No codebase precedent was found for actually **deleting** a whole-module re-export shim once its importers migrate. The two comparable whole-module shims found (`cli/adapt_skills_for_codex.py`, `cli/loop/queue.py`/`queue_store.py`) state in their own docstrings that they are kept **indefinitely** as compatibility surfaces, not pending removal. The one "removed once migrated" precedent found (ENH-3097/ENH-3261) operated at the function-kwarg level, not the whole-module level, and was paired with a permanent regression test (`test_enh3097_no_mixed_automation_kwargs.py`) asserting the legacy shape never reappears. This is a live tension with this issue's own plan to "delete the shim once no importers remain" (item 3 above) — the codebase's revealed practice for shims skews toward "kept indefinitely," not "deleted."

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low
- **Breaking Change**: No

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
  `cli/loop/queue.py`), `mcp_server/tools.py:684`, `mcp_server/tasks.py:224`,
  `fsm/executor.py:1076`, `analytics/variance.py:265`.
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

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `cli/loop/_helpers.py` | Signal handling (`register_loop_signal_handlers`, SIGWINCH handlers) | PRESERVED | Relocates to a named module; module-level and deferred callers continue via re-export until the shim is deleted |
| `cli/loop/_helpers.py` | Diagram/pinned-pane rendering (`StateFeedRenderer` + 9 helper functions) | PRESERVED | Relocates; no external production importer today, only `test_state_feed_renderer.py` |
| `cli/loop/_helpers.py` | Loop loading (`load_loop`, `load_loop_with_spec`) | PRESERVED | Relocates; both call the re-exported `resolve_loop_path` |
| `cli/loop/_helpers.py` | Run orchestration (`run_background`, `run_foreground`, `print_execution_plan`) | PRESERVED | Relocates; `run_foreground`'s deferred `info._format_history_event` import must move with it |
| `cli/loop/_helpers.py` | `resolve_loop_path`/`get_builtin_loops_dir` re-export (ENH-2773 shim) | PRESERVED, shim not yet dropped | Stays a pass-through from `fsm/loop_paths.py` until `info.py`, `lifecycle.py`, `config_cmds.py`, `edit_routes.py`, and `cli/queue.py` are repointed — no codebase precedent shows a whole-module shim like this actually being deleted (see Conventions in Force / Proposed Solution) |

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

### Decision Rules
N/A — no new decision logic; this issue is a structural module split
introducing no new gate, threshold, or classification rule.

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

## Session Log
- `/ll:wire-issue` - 2026-09-03T03:06:46 - `e42909d5-e77d-478c-b142-52f1ba049345.jsonl`
- `/ll:refine-issue` - 2026-09-03T02:56:56 - `00f0e408-f05f-43a3-bdc7-1e52bd1f47ab.jsonl`
- `/ll:verify-issues` - 2026-09-03T02:27:51 - `ec373f26-c22d-4cdb-bcd2-9da717f53d54.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:57 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3

## Relationships

relates_to: ENH-2773
