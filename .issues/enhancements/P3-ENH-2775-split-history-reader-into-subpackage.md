---
id: ENH-2775
status: done
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
relates_to:
- ENH-3359
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 85
score_complexity: 17
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 22
completed_at: '2026-09-03T05:19:16Z'
---

# ENH-2775: Split history_reader.py into a subpackage along concern boundaries

## Summary

Architectural issue found by `/ll:audit-architecture`. `history_reader.py` is
a top-tier large file accreting unrelated concerns.

> **Rescoped 2026-08-29**: this issue originally also covered splitting
> `fsm/executor.py`. That half carried nearly all the outcome risk (33/100
> outcome confidence was dominated by it) and its research showed the
> originally-proposed extractions (retry, handoff, continuity) already exist
> as collaborator modules. The remaining executor work was narrowed and moved
> to ENH-3359 (deferred). This issue is now the `history_reader` split only —
> a mechanical mirror of the completed ENH-2772/ENH-2774 sibling splits.
> Prior confidence/verify scores were removed as they measured the bundled
> scope.

## Location

- **File**: `scripts/little_loops/history_reader.py` — 3,706 lines (was 3,099
  at capture, still growing)
- **Module**: `little_loops.history_reader`

## Current Behavior

`history_reader.py` is one 3,706-line flat module: 27 dataclasses, ~64
independent read-only SQL query functions spanning 13 backing tables/views,
a Summary-DAG retrieval layer, project-digest section providers, and a small
`ll_grep`/`ll_expand`/`ll_describe` formatting layer. Concern boundaries exist
only as region comments and a four-domain unheadered tail. It has no
`__all__`. It is imported by 17 non-test modules, 20 test files, one YAML
heredoc, and four `unittest.mock.patch` string targets — all via the flat
`little_loops.history_reader.<name>` path.

## Expected Behavior

`little_loops.history_reader` is a package: `history_reader/__init__.py`
re-exports the full existing public surface (plus the four private names
external code reaches for) with an explicit `__all__`, and each backing
table/view's query functions live in their own named submodule. Every
existing import line, `patch()` string target, and YAML heredoc import keeps
working unchanged. Tests split one-file-per-submodule under flat
`scripts/tests/`. Doc-sync tests stay green.

## Finding

### Current State

- `history_reader.py`: 88 top-level defs mixing JSONL parsing, session
  discovery, querying, and formatting in one flat module.

### Impact

- **Development velocity**: recurring merge-conflict hotspot.
- **Maintainability**: concern boundaries exist informally (region comments,
  naming prefixes) but not structurally.

## Proposed Solution

Convert `history_reader.py` into a subpackage along its existing seams,
preserving public import paths via re-exports — the exact shape of the
completed EPIC-2789 siblings.

### Suggested Approach

_Rewritten 2026-09-02 to reconcile with the research findings below. The
earlier draft named `parsing.py`/`discovery.py` submodules; research confirmed
no JSONL-parsing or file-discovery code exists in this file, so those are
dropped._

**Grouping rule**: one submodule per backing table/view (or tightly-coupled
table pair). This is the rule future readers use to answer "where does a new
reader go" — write it into the `__init__.py` docstring.

1. Convert `history_reader.py` -> `history_reader/` package with this layout:

   | Submodule | Contents (by current region / backing table) |
   |---|---|
   | `_base.py` | `_connect_readonly`, `_row_to_dataclass`, `_stale_cutoff`, `STALE_DAYS_DEFAULT`, the shared `logger` (see step 3), `CANNOT_JUDGE` re-import, any other cross-domain constants |
   | `models.py` | all 27 dataclasses (`UserCorrection` ... `ReviewEvent`) |
   | `search.py` | `search`, `find_user_corrections`, `recent_file_events` (FTS + corrections + file_events) |
   | `usage.py` | `tool_events` cluster (`agent_usage`, `recent_tool_events`, `mcp_server_usage`, `mcp_failure_rate`) and `usage_events` cluster (`cost_attribution`, `waste_attribution`, `recent_usage_events`, `aggregate_usage`, `_WASTED_RUN_PREDICATE`) |
   | `runs.py` | `orchestration_runs` cluster + `loop_runs` cluster (`recent_orchestration_runs`, `aggregate_orchestration_runs`, `recent_loop_runs`, `find_loop_run`, `aggregate_loop_runs`) |
   | `sessions.py` | session metadata, issue events, issue effort/velocity, lifecycle/handoff, worktree summaries (`lookup_session_metadata`, `sessions_for_issue`, `related_issue_events`, `find_session_for_issue_transition`, `issue_effort`, `recent_issue_velocity`, handoff/worktree readers) |
   | `subagents.py` | `subagent_tree`, `subagent_retries`, `subagent_budget` and the subagent_runs readers |
   | `context.py` | context-pressure curves, commit events, prompt-opt events, learning tests (`find_learning_test`) |
   | `summary_dag.py` | region `Summary DAG retrieval` (FEAT-1712) incl. `condensed_nodes_for_issue` |
   | `digest.py` | region `Project digest — section providers` (ENH-1907) + `project_digest`, `render_project_context` |
   | `hooks.py` | region `Hook execution telemetry` (ENH-2506), `hook_failure_rate` |
   | `harness.py` | region `ll-harness / eval outcome telemetry` (`recent_harness_events`, `harness_eval_pass_rate`, `harness_eval_abstention_rate`, `check_high_confidence_abstention`, `read_prepatch_evidence`) |
   | `events.py` | the unheadered tail: `verdict_events` (ENH-2504), `advisor_consults` (FEAT-3300), `research_triage`, `review_events` (ENH-2512) |
   | `formatting.py` | `ll_grep`, `ll_expand`, `ll_describe` |

   Exact membership of `sessions.py`/`context.py` is the implementer's call
   at inventory time; the rule is "by backing table", and a submodule may
   host two adjacent tables when they share a join (the three cross-domain
   JOINs in the research findings do **not** require merging modules — the
   SQL references a table name, not a Python symbol).

2. `__init__.py`: one explicit `from .<submodule> import (...)` block per
   submodule (alphabetized, no star imports), a single flat `__all__` with the
   labeled "Private functions ... re-exported for test access" tail listing
   `_connect_readonly`, `_stale_cutoff`, `_row_to_dataclass`. Docstring has
   the "Package layout" and "Public API" headings, matching
   `session_store/__init__.py` and `fsm/validation/__init__.py`, and states
   the grouping rule from above.

3. Logger: define
   `logger = logging.getLogger("little_loops.history_reader")` once in
   `_base.py` and import it into every submodule. Do **not** use
   `getLogger(__name__)` in submodules — keeps the 67 existing
   `"history_reader: <func> query failed"` warnings on the logger name that
   `test_verdict_grammar_regression.py` asserts against.

4. Intra-package imports form a DAG: every submodule may import from
   `_base.py` and `models.py` only; never sibling-to-sibling. (`digest.py`
   is the one expected exception if `project_digest` aggregates other
   domains' readers — if so, it imports downward from those siblings and
   nothing imports `digest.py`.)

5. Split `scripts/tests/test_history_reader.py` one-file-per-submodule
   (`test_history_reader_<submodule>.py`, flat under `scripts/tests/`).
   `TestNewEventReaders` is itself a grab-bag of the four tail domains; move
   it whole into `test_history_reader_events.py` rather than re-splitting the
   class. Redeclare shared fixtures per file (no new conftest), matching
   commit `9a4977a14`.

6. Docs in lockstep (see Integration Map -> Documentation): restructure the
   `docs/reference/API.md` entry under the **unchanged** literal heading
   `## little_loops.history_reader`; update the `docs/ARCHITECTURE.md`
   component-table row and Read Path node; update the `CONTRIBUTING.md`
   module-tree line.

7. Land as a single short-lived branch merged same day. `history_reader.py`
   averaged a commit every 3 days over the last month (last touch
   2026-09-02) and P1 EPIC-3214 / ENH-3381 will keep adding readers; do not
   run this in parallel with EPIC-3214 children.

### Decisions (resolved 2026-09-02)

- **Shared-leaf naming**: `_base.py` (underscore). Two of the three
  precedents (`fsm/validation/_base.py`, `issue_history/_utils.py`) use the
  underscore for a leaf every sibling imports; `session_store/db.py` is the
  outlier and its issue text calls its own naming novel.
- **Test split shape**: one-file-per-submodule, not grouped. The
  `issue_history` 5-modules-per-test-file precedent is the older, larger
  package; the two EPIC-2789 siblings are the pattern this issue is
  explicitly mirroring.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- The two completed EPIC-2789 siblings (ENH-2772 session_store split, ENH-2774
  fsm/validation split) both landed as a **subpackage** — `name/__init__.py`
  plus concern submodules, with matching per-submodule test files — rather
  than sibling flat files kept alongside an unrenamed original (see
  Integration Map -> Conventions in Force for both `__init__.py` examples).
  This issue mirrors that shape directly.
- The single flat "Query API" region (L456-2386, ~1,930 lines, ~35 functions)
  covers at least 9 distinguishable query domains — finer-grained than a
  single `queries.py` would comfortably hold; expect several query submodules
  (see Program Design -> Signatures).

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Both completed sibling splits document their `__init__.py` with the same two-heading docstring shape — "Package layout" (submodule -> one-line concern) and "Public API" (re-exported names) — each citing the originating issue number in the parenthetical, evidence: `scripts/little_loops/session_store/__init__.py:16-24` and `scripts/little_loops/fsm/validation/__init__.py:9-39`.
- Both re-export via one explicit `from .<submodule> import (...)` block per submodule (alphabetized, no star imports), followed by a single flat `__all__` list with a labeled "Private functions ... re-exported for test access" tail — every re-exported name appears in `__all__`, evidence: `session_store/__init__.py:64-167,169-271` and `fsm/validation/__init__.py:44-162,164-275`.
- Intra-package dependencies form a DAG with exactly one leaf/shared module every other submodule may import from — never sibling-to-sibling — evidence: `session_store`'s `db.py`/`schema.py` are the leaves under `queries.py`/`writers.py`/`lifecycle.py`; `fsm/validation`'s `_base.py` is the single leaf every other submodule imports, with `structural_rules.py` at the top of the DAG hosting the entry points.
- The two sibling splits **disagree** on whether the shared-internals leaf gets an underscore-prefixed name: `fsm/validation` names it `_base.py` and its docstring states explicitly it holds "cross-rule helpers used by 2+ rule families"; `session_store` has no underscore-prefixed shared module at all — its cross-cutting DB-path/connection logic lives in the non-underscore `db.py` instead, and that issue's own text states "no split has used exactly `schema.py`/`queries.py`/`lifecycle.py`/`db.py` before — this issue's naming is novel, not an established convention." `history_reader.py`'s own shared helpers (`_connect_readonly`, called at 64 sites, `_row_to_dataclass`, `logger`, `STALE_DAYS_DEFAULT`) are used by 2+ query-domain groups the same way `_base.py`'s contents are — a plausible `_base.py`-shaped candidate — but which naming convention to follow is a decision the implementer needs to make knowingly; the codebase does not settle it.
- Neither split added a new shared `conftest.py` fixture file; each new test file redeclares its own copy of any shared test-local fixtures/helpers rather than centralizing them, evidence: `_module_tmp_parent` independently redefined across `test_session_store_{db,lifecycle,queries,schema,writers}.py`, and `make_state` independently redefined across `test_fsm_validation_{meta_rules,shell_safety,structural,reachability,evaluator_rules}.py`.
- Test-file naming does not always exactly echo the production submodule name: `fsm/validation`'s `structural_rules.py` submodule is tested by `test_fsm_validation_structural.py`, not `..._structural_rules.py` — the per-submodule test-split convention allows a shortened suffix.
- Neither split created a mirror test subdirectory (e.g. `scripts/tests/session_store/`); both kept flat, module-name-prefixed files directly under `scripts/tests/`.

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- `history_reader.py` contains **zero** filesystem/JSONL-parsing code — no `open()`, `.glob()`/`.rglob()`, `os.walk`, `.jsonl` reads anywhere in the file (unfiltered whole-file search, zero hits). `conversation_turns()` (`history_reader.py:2278`) is the closest related function, but its own docstring explicitly defers actual JSONL parsing to `_extract_turn_pairs()` in `user_messages.py`, outside this file. The Suggested Approach's proposed `parsing.py` ("JSONL/event decoding") and `discovery.py` ("session file location") submodules therefore do not correspond to code that exists inside `history_reader.py` today — this file's actual concerns are dataclasses, DB-connection/row-mapping helpers, ~64 independent SQL query functions, and a small formatting layer (`ll_grep`/`ll_expand`/`ll_describe`, `render_project_context`).
- Larger-than-EPIC-2789-sibling subpackage precedent exists in this repo: `scripts/little_loops/issue_history/` (16 submodules, the largest in the repo), `scripts/little_loops/parallel/` (9), `scripts/little_loops/init/` (9), `scripts/little_loops/adapters/` (8) — all exceed session_store/fsm.validation's 5-6. They use two coexisting grouping shapes: strict one-file-per-domain (e.g. `issue_history/hotspots.py`, `coupling.py`, `regressions.py`) and several related domains grouped into one file (e.g. `issue_history/debt.py` docstring: "cross-cutting concerns, agent effectiveness, complexity" — three domains, one file).
- None of these four larger subpackages use the "Package layout" + "Public API" two-heading `__init__.py` docstring convention this issue's Conventions in Force section attributes to the codebase generally — a repo-wide grep for the literal strings `"Package layout"` and `"split from the former flat"` across every `__init__.py` matches only `session_store/__init__.py` and `fsm/validation/__init__.py`. `issue_history/__init__.py:12-73` instead groups its *exports* (not files) under five prose headings (`# Models`, `# Parsing`, `# Analysis`, `# Formatting`, `# Documentation synthesis`).
- `issue_history/` is the closest existing precedent for a query-heavy split (independent read-only `analyze_*`/`detect_*` functions grouped by domain, the same shape as `history_reader.py`'s query functions) rather than fsm/validation's rule-based or session_store's CRUD-based organization. At its 16-submodule scale, its test-file mapping is not strict 1:1: `scripts/tests/test_issue_history_advanced_analytics.py` alone covers 5 different source submodules (`hotspots.py`, `coupling.py`, `regressions.py`, `quality.py`, `debt.py`) via 8 `Test*` classes — a data point against assuming the two EPIC-2789 siblings' flat one-for-one test-split convention holds at `history_reader.py`'s larger domain count (9-13 domains).
- A third data point on the underscore-vs-non-underscore shared-leaf naming disagreement (beyond the `fsm/validation`/`session_store` split already on record): `issue_history/_utils.py` (underscore-prefixed) is imported by 8 of 16 submodules (~50% fan-in) and its own docstring states it was extracted "so `rework.py` and `agent_quality.py` share one convention instead of forking it" — a fan-in lower than `history_reader.py`'s own `_connect_readonly` (64 call sites, effectively 100% of query functions) yet still named with a leading underscore, unlike `session_store/db.py`'s ~80%-fan-in non-underscore precedent. No subpackage in the repo promotes such a shared helper into `__init__.py` itself, regardless of fan-in.

## Impact

- **Severity**: Medium
- **Effort**: Medium — mechanical moves, but ~13 submodules, a 3,304-line
  test file to split, and six doc files to touch.
- **Risk**: Low — no behavior change; every importer path is preserved by
  re-export; the two doc-sync tests and the logger-name test catch the
  known failure modes.
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: package conversion, `__all__`, test-file split, doc updates
  listed in Integration Map -> Documentation, the `CONTRIBUTING.md` line.
- **Out of scope**: changing any query's SQL or signature; deduplicating the
  "rate" wrappers that reimplement their sibling's SQL (`mcp_failure_rate`,
  `hook_failure_rate`, etc.) — file a follow-up if wanted; adding a
  `conftest.py`; the `fsm/executor.py` split (ENH-3359, deferred); the four
  `docs/reference/CLI.md` function-name citations that no test guards (they
  cite function names, not the module path, so they do not go stale on this
  split — leave them).

## Acceptance Criteria

- [x] `scripts/little_loops/history_reader.py` no longer exists;
      `scripts/little_loops/history_reader/__init__.py` plus the submodules
      in Suggested Approach step 1 do.
- [x] Every name in the pre-split module docstring's "Public API" list, plus
      `_connect_readonly`, `_stale_cutoff`, `_row_to_dataclass`, is listed in
      `history_reader/__init__.py.__all__` and importable via
      `from little_loops.history_reader import <name>`.
- [x] Zero edits to any of the 17 non-test importers or 20 test importers
      listed in Integration Map -> Dependent Files (verify with
      `git diff --stat` against the branch base).
- [x] `unittest.mock.patch("little_loops.history_reader.lookup_session_metadata")`
      and `...sessions_for_issue` in `test_ll_logs.py`/`test_cli_history.py`
      still apply (those tests pass unmodified).
- [x] `loops/sft-corpus.yaml`'s heredoc
      `from little_loops.history_reader import lookup_session_metadata`
      resolves (`python -c` smoke check).
- [x] `test_verdict_grammar_regression.py::test_high_confidence_abstention_warns`
      passes unmodified.
- [x] `test_wiring_reference_docs.py` and `test_wiring_guides_and_meta.py`
      pass; `docs/reference/API.md` still contains the literal heading
      `## little_loops.history_reader`.
- [x] No submodule imports a sibling other than `_base.py`/`models.py`
      (`digest.py` exception per step 4); no submodule calls
      `logging.getLogger(__name__)`.
- [x] `scripts/tests/test_history_reader.py` is replaced by
      `test_history_reader_<submodule>.py` files with the same `Test*`
      classes; collected test count is unchanged.
- [x] `python -m pytest scripts/tests/`, `ruff check scripts/`,
      `python -m mypy scripts/little_loops/` all exit 0.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Additional documentation surface beyond the two already-cited files, found via broader research (2026-09-03): `docs/guides/HISTORY_SESSION_GUIDE.md` (cites `recent_orchestration_runs`/`aggregate_orchestration_runs`/`recent_loop_runs`/`find_loop_run`/`aggregate_loop_runs`/`lookup_session_metadata`), `docs/guides/EVALUATION_GUIDE.md` (cites `recent_harness_events`/`harness_eval_pass_rate`), `docs/guides/BUILTIN_HOOKS_GUIDE.md` (cites `subagent_tree`/`subagent_retries`/`subagent_budget`), `docs/observability/otel-mapping.md` (cites `cost_attribution`), `docs/reference/loops.md` (cites `lookup_session_metadata`), `CONTRIBUTING.md` (module-tree listing line citing "8 query functions, 7 dataclasses" — will go stale the same way `docs/ARCHITECTURE.md`'s component-table row does).
- Two doc-sync test guards enforce these doc citations stay resolvable and must be checked after the split: `scripts/tests/test_wiring_reference_docs.py:87-91` (asserts `docs/reference/API.md`'s `## little_loops.history_reader` heading and named anchors resolve) and `scripts/tests/test_wiring_guides_and_meta.py:132-136` (asserts `docs/ARCHITECTURE.md`'s history_reader-related content resolves; already carries one `# REMOVED (stale/false-positive)` row for this module from a prior pass).
- `docs/reference/API.md:8138-8189` — the `## little_loops.history_reader` entry re-exports the module's ~35-name public surface in one `from little_loops.history_reader import (...)` block; this needs restructuring to match whichever package layout the split lands on (mirrors how `docs/reference/API.md` documents `session_store`/`fsm.validation` post-split, per the Conventions in Force sibling examples).

### Files to Modify
- `scripts/little_loops/history_reader.py` (3,706 lines currently — grown
  further since capture, was 3,585) — flat module; existing region comments
  already mark `Dataclasses` (L104), `Helpers` (L412), `Query API` (L456,
  spans ~1,930 lines through L2386 and covers at least 9 distinguishable query
  domains — not one homogeneous group), `Summary DAG retrieval` (L2389,
  FEAT-1712), `Project digest — section providers` (L2624, ENH-1907), `Hook
  execution telemetry` (L2833, ENH-2506), `ll-harness / eval outcome
  telemetry` (L2966).

### Dependent Files (Callers/Importers)
- `history_reader` direct importers (8, via `ll-code importers-of`):
  `cli/history_context.py`, `cli/session.py`, `issue_history/collisions.py`,
  `issue_history/evolution.py`, `issue_history/rework.py`,
  `tests/test_assistant_messages.py`, `tests/test_enh_2505_subagent_runs.py`,
  `tests/test_history_reader.py`.

  **Stale as of 2026-09-02** — a grep for `history_reader` imports now finds
  18+ non-test importers (adds at least `cli/ctx_stats.py`, `cli/harness.py`,
  `cli/history.py`, `cli/logs.py`, `cli/loop/evidence.py`, `fsm/executor.py`,
  `hooks/session_start.py`, `issue_history/agent_quality.py`,
  `mcp_server/tools.py`, `prepatch_check.py`, `user_messages.py`,
  `work_verification.py`) plus ~20 test files. Needs a re-run of the
  `ll-code importers-of`/`impact-of` research this section was built from —
  the count below is very likely stale too.
- Transitive impact set (`ll-code impact-of`) is 16 files (reaches
  `cli/__init__.py`, `issue_history/analysis.py`) — **unverified as of
  2026-09-02**, see stale-importer note above. The split must keep
  `from little_loops.history_reader import ...` importable unchanged across
  all of these — the re-export requirement the Proposed Solution already
  states.
- **Corrected 2026-09-03 (`/ll:refine-issue`)**: grep-confirmed 17 non-test
  importers (module-level or deferred `from little_loops.history_reader
  import ...`): `cli/ctx_stats.py:178,192`, `cli/harness.py:576,602`,
  `cli/history_context.py:31,366`, `cli/history.py:546`, `cli/logs.py:1885`,
  `cli/loop/evidence.py:466`, `cli/session.py:40,50,601,793`,
  `fsm/executor.py:1845`, `hooks/session_start.py:214`,
  `issue_history/agent_quality.py:43`, `issue_history/collisions.py:28`,
  `issue_history/evolution.py:17`, `issue_history/rework.py:20`,
  `mcp_server/tools.py:159`, `user_messages.py:941`,
  `work_verification.py:275` — plus 20 test files (`test_advisor.py`,
  `test_assistant_messages.py`, `test_enh_2497_agent_type.py`,
  `test_enh_2505_subagent_runs.py`, `test_enh_2511_mcp_telemetry.py`,
  `test_fsm_executor.py`, `test_history_reader.py`, `test_hook_intents.py`,
  `test_hook_session_start.py`, `test_hooks_integration.py`,
  `test_issue_manager.py`, `test_loops_sft_corpus.py`,
  `test_pre_compact_handoff.py`, `test_pre_compact.py`,
  `test_record_hook_event_shim.py`, `test_session_store_writers.py`,
  `test_sweep_stale_refs.py`, `test_verdict_grammar_regression.py`,
  `test_worker_pool.py`, `test_worktree_utils.py`). Total 37 files. The
  earlier `ll-code importers-of` count (8) missed 9 of these because they
  use deferred (function-local) imports, which that query does not index.
  `prepatch_check.py` was previously miscounted above as an importer — it
  only mentions `history_reader` in a docstring, it does not import it.
- Three files import the **private** `_connect_readonly` helper directly at
  top level (`issue_history/collisions.py:28`, `issue_history/rework.py:20`,
  `issue_history/agent_quality.py:43`), and one imports the private
  `_stale_cutoff` (`issue_history/evolution.py:17`). The package split must
  keep both underscore-prefixed names re-exported — matching how
  `session_store/__init__.py` and `fsm/validation/__init__.py` explicitly
  re-export private names "for test access" (see Conventions in Force).

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- `scripts/little_loops/loops/sft-corpus.yaml:75` — the `enrich` state's
  embedded Python heredoc contains a live runtime import,
  `from little_loops.history_reader import lookup_session_metadata`. This is
  a non-`.py` production dependency the grep-based importer sweeps miss; the
  split must keep `lookup_session_metadata` resolvable at
  `little_loops.history_reader.lookup_session_metadata`.
- `scripts/little_loops/mcp_server/tools.py` — beyond the module-level import
  already listed above, the `_TOOL_HANDLERS["history_search"]` registry entry
  maps MCP tool name `history_search` to `_tool_history_search()`, whose
  docstring states it "Wraps `history_reader.search()` directly" and which
  lazy-imports `search` at call time. `search` must stay resolvable at
  `little_loops.history_reader.search` for this MCP tool registration to keep
  working.

### Conventions in Force
- This codebase's established convention for splitting a god-module is a
  **subpackage**, not sibling flat files left alongside an unrenamed original:
  convert `name.py` -> `name/__init__.py` + concern submodules, with the
  `__init__.py` docstring documenting a "Package layout" (submodule ->
  concerns) section and a "Public API" (re-exported names) section — evidence:
  `scripts/little_loops/session_store/__init__.py:1-40` (ENH-2772, split into
  `db.py`/`lifecycle.py`/`queries.py`/`schema.py`/`writers.py`) and
  `scripts/little_loops/fsm/validation/__init__.py:1-30` (ENH-2774, split into
  `_base.py`/`structural_rules.py`/`evaluator_rules.py`/`meta_rules.py`/
  `reachability.py`/`shell_safety.py`) — both are completed sibling issues of
  this one under the same parent EPIC-2789.
- The same convention extends to tests: the flat test file is split one-for-one
  into per-submodule test files (`test_<pkg>_<submodule>.py`), not kept as one
  shared file — evidence: commit `9a4977a14` split `test_fsm_validation.py`
  (5,358 lines) into
  `test_fsm_validation_{evaluator_rules,meta_rules,reachability,shell_safety,structural}.py`.

### Tests
- `scripts/tests/test_history_reader.py` — 3,221 lines, already organized into
  25 domain-scoped `Test*` classes (e.g. `TestCostAttribution`,
  `TestWasteAttribution`, `TestHandoffFrequency`, `TestWorktreeSummary`,
  `TestSummaryDagRetrieval`) that map directly onto candidate submodule
  boundaries — the test-file split is a mechanical class-per-domain move.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- `scripts/tests/test_ll_logs.py:4730,4800` and `scripts/tests/test_cli_history.py:289,305`
  — `unittest.mock.patch("little_loops.history_reader.<name>", ...)` targets
  (`lookup_session_metadata`, `sessions_for_issue`) not in the prior importer
  count. These are string-based patch targets, invisible to import-statement
  greps; the new `__init__.py` must keep both names resolvable at the flat
  `little_loops.history_reader.<name>` path for the patches to still apply.
- `scripts/tests/test_verdict_grammar_regression.py::test_high_confidence_abstention_warns`
  (~line 173) — asserts on `caplog.at_level("WARNING", logger="little_loops.history_reader")`
  around `check_high_confidence_abstention()`, plus the exact message text
  `"high-confidence abstention: ..."`. Whichever submodule ends up hosting
  this function must log via `logging.getLogger("little_loops.history_reader")`
  explicitly (not a bare `__name__`-derived child logger) or this test breaks.
- Confirmed test-file layout for the two completed sibling splits is flat,
  not subdirectory-nested (`scripts/tests/session_store/` and
  `scripts/tests/fsm_validation/` do not exist) — the history_reader split's
  `test_history_reader_<submodule>.py` files should likewise live flat under
  `scripts/tests/`, matching the Suggested Approach's own naming, not nested.
- No test file outside `test_history_reader.py` imports a private
  (underscore-prefixed) `history_reader` name — all 20 known test importers
  key off public functions only, so none need special handling for
  private-name relocation.

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_
- `scripts/tests/test_wiring_reference_docs.py:87` — a `DOC_STRINGS_PRESENT`
  row (ENH-1753) asserts the literal heading `"## little_loops.history_reader"`
  exists in `docs/reference/API.md`. The split must either preserve that exact
  heading text in `docs/reference/API.md`, or this test row needs updating in
  lockstep. (Rows 88-91 in the same list check symbol names only — unaffected
  by the module→package rename itself.)

### Documentation
- `docs/reference/API.md` — the `little_loops.history_reader` entry (line 54)
  cites the current flat-module layout and needs updating to the new package
  structure.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — carries structural, not just conceptual, file-path
  references that go stale on a split. Specific spots: the Read Path mermaid
  diagram's `HR[history_reader.py]` node (L730); the Components table row
  `history_reader.py | history_reader.py | Public read API: 10 query
  functions, 7 dataclasses, ...` (L758), which states counts that presuppose a
  single flat file.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02:_
- `docs/guides/LOOPS_GUIDE.md` — cites `history_reader.read_prepatch_evidence(issue_id)`
  by dotted name in the pre-patch-check section.
- `CHANGELOG.md` — three historical entries name the module/functions verbatim
  (`history_reader.cost_attribution()`, `` `history_reader` module ``,
  `` `history_reader` `` in the ENH-3211 entry) — these are historical and
  don't need editing, but a doc-sync check should confirm they aren't
  mistaken for live references during the split.

_Wiring pass added by `/ll:wire-issue` — 2026-09-03:_
- `docs/reference/CLI.md` — four citations of history_reader functions by
  name, missed by prior passes because this file never contains the literal
  string `history_reader` (it documents CLI behavior, not the module): the
  `ll-harness` JSON output field table (L256-262) and prose (L264) documenting
  `prepatch_evidence`/`history_pass_rate`/`history_pass_rate_runs`/
  `history_abstention_rate`/`history_judged_runs`/`history_since` (populated
  from `read_prepatch_evidence`, `harness_eval_pass_rate`,
  `harness_eval_abstention_rate`, `recent_harness_events`); the
  `ll-issues set-status` "Side effect" paragraph (L2597) naming
  `issue_effort()`; the `ll-history` `subagents --budget` flag row (L3755)
  naming `subagent_budget`; and the `ll-history-context` "Effort Context
  block" paragraph (L4022) naming `recent_issue_velocity()`. None of these
  four are covered by either of the two doc-sync guard tests already on
  record (`test_wiring_reference_docs.py` checks unrelated anchors in this
  file; `test_wiring_guides_and_meta.py`'s only `CLI.md` reference is
  unrelated) — they can go stale post-split with nothing to catch it.

_Wiring pass added by `/ll:wire-issue` — 2026-09-02 (post-rewrite sweep
against the new submodule map):_
- `scripts/little_loops/prepatch_check.py:7-8` — module docstring cites
  `little_loops.history_reader.read_base_sha` and `.read_base_dirty` by
  dotted path. Both exist (`history_reader.py:1829,1885`, inside the
  orchestration-runs region, so they land in `runs.py`) and the dotted path
  stays valid via `__init__.py` re-export — no action, but add both names to
  the `__all__` checklist; they were not in any prior key-symbol list.
- Full string-target sweep for `little_loops.history_reader.<name>` across
  `scripts/tests/` and `scripts/little_loops/` (excluding
  `test_history_reader.py`) finds exactly four distinct names:
  `lookup_session_metadata` (`test_ll_logs.py:4730`), `sessions_for_issue`
  (`test_cli_history.py:290`), `read_base_sha`, `read_base_dirty`
  (`prepatch_check.py:7-8`, docstring only). The two `mock.patch` targets
  already on record are the complete set.
- Non-Python sweep (`skills/`, `commands/`, `agents/`, `hooks/`,
  `scripts/little_loops/loops/`) found no live references beyond the
  already-recorded `loops/sft-corpus.yaml:75` heredoc import — the non-`.py`
  surface is fully enumerated.
- `ll-code importers-of little_loops.history_reader` (re-run 2026-09-02)
  returns 5 module-level hits, confirming the earlier note that it does not
  index deferred imports; the grep-derived 17+20 importer set above remains
  authoritative.
- No config surface names the module: `scripts/pyproject.toml` has no
  per-module mypy/ruff override for `history_reader`, and the hatch
  `packages = ["little_loops"]` entry already ships `session_store/` and
  `fsm/validation/` as subpackages, so no packaging change is needed.

### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `history_reader.py` | Public functions/dataclasses (`find_user_corrections`, `search`, `cost_attribution`, `UserCorrection`, etc.) | PRESERVED | Split is purely structural; `history_reader/__init__.py` re-exports the full existing public surface per the Proposed Solution's own stated goal ("preserving public import paths via re-exports") |

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- `search()` (`scripts/little_loops/history_reader.py:530`, first param `query: str`, returns `list[SearchResult]`) — FTS5 full-text query entry point, representative of the Query API surface the split relocates unchanged.
- `find_user_corrections()` (`scripts/little_loops/history_reader.py:462`, first param `topic: str`, returns `list[UserCorrection]`) — corrections query, same relocation-only disposition.
- `cost_attribution()` (`scripts/little_loops/history_reader.py:925`, first param `group_by: str`, returns `list[dict]`) — cost/waste-attribution domain exemplar.

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- The file has no `__all__` (confirmed by an unfiltered `^__all__` search) — only an informal "Public API" list in the module docstring. Both completed sibling splits (`session_store`, `fsm/validation`) add an explicit `__all__` as part of the split, including a labeled "Private functions ... re-exported for test access" tail — this is new structure the split introduces, not merely a relocation.
- The region-comment boundaries this issue's own text uses for the 9 named query domains are coarser than the code's actual table/constant boundaries in two places: "usage aggregation" is really two separate table-backed clusters back-to-back with no separating comment — `tool_events` (`agent_usage`/`recent_tool_events`/`mcp_server_usage`/`mcp_failure_rate`, `history_reader.py:726-925`) vs. `usage_events` (`cost_attribution`/`waste_attribution`/`recent_usage_events`/`aggregate_usage`, `history_reader.py:925-1180`); and "orchestration/loop-run aggregation" is likewise two clusters (`orchestration_runs`: `history_reader.py:1735-1984`, then `loop_runs`: `history_reader.py:1984-2087`).
- Four query domains exist in the unheadered tail (`history_reader.py:3137-3706`) that this issue's 9-domain list does not name at all: `verdict_events` (ENH-2504), `advisor_consults` (FEAT-3300), `research_triage`, and `review_events` (ENH-2512).
- No circular import exists today in either direction between `history_reader.py` and its two module-level upstream dependencies: `session_store` does not import `history_reader` (only 3 code-comment mentions found, no import statement), and `fsm.verdicts` (source of the one cross-package import, `CANNOT_JUDGE`) has zero `little_loops.*` imports of its own — it is a leaf dependency, not part of a cycle. A split does not need to solve a cycle problem here, unlike ENH-2776's `_helpers.py`/`info.py` case.
- The test file's own structure only partially maps onto the 9 named domains: of 25 `Test*` classes in `test_history_reader.py`, one — `TestNewEventReaders` (`test_history_reader.py:1753-2405`) — is itself a grab-bag class bundling the four unheadered tail domains (verdict events, advisor consults, research triage, review events) into a single class with no per-domain subclassing, so the "mechanical class-per-domain move" the Proposed Solution describes needs that one class split further, not just relocated.

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Four distinct cross-package imports exist, not just `search()`'s `fts_phrase` — two module-level, two function-local: `session_store` (`history_reader.py:92-97`, module-level) supplies `DEFAULT_DB_PATH` (default `db=` param on nearly every function), `ensure_db` (called inside `_connect_readonly`, so every query function transitively depends on it), `fts_phrase` (`search()` only), and `normalize_issue_id` (4 functions: `related_issue_events`, `find_session_for_issue_transition`, `sessions_for_issue`, `issue_effort`); `little_loops.fsm.verdicts.CANNOT_JUDGE` (`history_reader.py:91`, module-level, used only in `harness_eval_abstention_rate`); `little_loops.observability.tracing.*` token constants (`history_reader.py:946`, function-local import inside `cost_attribution` only); `little_loops.issue_parser.slugify` (`history_reader.py:1451`, function-local import inside `find_learning_test` only).
- At the Python function-call level, cross-domain coupling is almost nonexistent: grepping all ~64 query function names as call targets across the whole file finds exactly one inter-function call — `recent_issue_velocity()` (`:2196`) calling `issue_effort()` — and both belong to the same domain (issue effort/velocity), so no true cross-domain Python call exists anywhere in the file. Several functions that look like "rate" wrappers over a "recent" sibling (`mcp_failure_rate`, `hook_failure_rate`, `harness_eval_pass_rate`, `verdict_pass_rate`, `review_velocity`, `aggregate_orchestration_runs`, `aggregate_loop_runs`, `aggregate_usage`) do NOT call their sibling — each independently reimplements its own SQL against the same table.
- Cross-domain coupling instead shows up at the SQL/table level in exactly three places: `waste_attribution()` (cost/waste-attribution domain, `:1021-1075`) joins `usage_events` to `loop_runs` (`:1048`) and its `_WASTED_RUN_PREDICATE` constant (`:1012-1018`) references `lr.terminated_by`/`lr.failure_terminal`/`lr.final_state` — columns backing the separate orchestration/loop-run domain; `lookup_session_metadata()` (session-metadata domain, `:2202-2275`) joins the `issue_sessions` view to `issue_events` (`:2234-2241`) — the table backing the separate `related_issue_events`/`find_session_for_issue_transition` domain; `condensed_nodes_for_issue()` (Summary DAG domain, `:2568-2621`) joins `summary_nodes` to `issue_sessions` (`:2594`) — the view backing the separate issue-effort/velocity domain. No other `JOIN` in the file crosses a domain boundary.
- A third de facto shared-internals element beyond `_connect_readonly`/`_row_to_dataclass`: `logger.warning`/`.error` (module-level `logger = logging.getLogger(__name__)` at `:99`) appears 67 times, essentially one per query function's `except sqlite3.Error:` block, with a uniform `"history_reader: <func> query failed"` message format — stdlib `logging`, not in-module code to relocate, but a convention every submodule must preserve. `_stale_cutoff` (`:418`) is a narrower shared helper used at only 3 sites (`find_user_corrections`, `recent_file_events`, `project_digest`) rather than file-wide.

### Types
- No new data shape is introduced. The 27 dataclasses in `history_reader.py`
  (`UserCorrection`, `FileEvent`, `SearchResult`, ... `ReviewEvent`) are
  relocated by the split, not changed.

### Signatures
- `history_reader.py` has no classes besides its dataclasses; its 75
  module-level functions are grouped by naming/region rather than by class.
  The "Query API" region alone (L456-2386) spans roughly 35 of those 75
  functions across at least 9 distinguishable domains — cost/waste
  attribution, usage aggregation, context-pressure curves, commit events,
  prompt-opt events, learning tests, lifecycle/handoff, worktree summaries,
  subagent tree/retries/budget, orchestration/loop-run aggregation, issue
  effort/velocity, session metadata, and grep/search formatting
  (`ll_grep`/`ll_expand`/`ll_describe`) — finer-grained than a single
  `queries.py` module would comfortably hold.
- Representative signatures the split relocates unchanged (no shape change):
  - `find_user_corrections(topic: str, *, limit: int = 10, include_stale: bool = False, db: Path | str = DEFAULT_DB_PATH) -> list[UserCorrection]` (`scripts/little_loops/history_reader.py:462`)
  - `search(query: str, *, kind: str | None = None, limit: int = 10, db: Path | str = DEFAULT_DB_PATH) -> list[SearchResult]` (`scripts/little_loops/history_reader.py:530`)
  - `cost_attribution(group_by: str = "gen_ai.invocation.id", *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]` (`scripts/little_loops/history_reader.py:925`)
- Shared internals every query function depends on: `_connect_readonly(db_path: Path) -> sqlite3.Connection | None` (`scripts/little_loops/history_reader.py:423`, called at 64 sites) and `_row_to_dataclass(row: sqlite3.Row, dc: type) -> Any` (`scripts/little_loops/history_reader.py:450`) — candidates for a shared internals module, see Proposed Solution → Codebase Research Findings for the naming disagreement between the two sibling splits on this point.

### Call Path
- `cli/session.py:44` -> `history_reader.search()` (`scripts/little_loops/history_reader.py:529`) — representative importer path; after the split this resolves through `history_reader/__init__.py` re-exports with the import line unchanged.
- `cli/history_context.py:31` -> `history_reader.condensed_nodes_for_issue()` and other query functions — same re-export-preserved path; all 8 direct importers follow this shape.

### Decision Rules
N/A — no new decision logic; this issue is a structural module split
introducing no new gate, threshold, or classification rule.

## Related Key Documentation

- `docs/reference/API.md` — documents `history_reader` module-by-module;
  splitting it requires updating those entries to match the new package
  layout.
- `docs/ARCHITECTURE.md` — describes the internals `history_reader.py`
  implements; a structural split is exactly the kind of architecture change
  this doc covers.

## Verification Notes

- 2026-08-16: Core issue still real; file has grown further since capture
  rather than shrunk — `history_reader.py` is now 3,351 lines (was 3,099).
  Verdict: OUTDATED (line counts updated above).
- 2026-08-29: Rescoped to `history_reader` only; `fsm/executor.py` half moved
  to ENH-3359 (deferred). Prior verify verdict and confidence scores removed —
  they measured the bundled two-file scope.
- 2026-09-02: Core issue still real; file has grown further —
  `history_reader.py` is now 3,706 lines (was 3,585). Corrected drifted line
  citations for `search()`, `find_user_corrections()`, `cost_attribution()`,
  and the two `docs/ARCHITECTURE.md` cites. Flagged the Integration Map's
  "8 direct importers" / "16 transitive impact" counts as stale — a grep now
  finds 18+ non-test importers alone; needs a re-run of the `ll-code
  importers-of`/`impact-of` research, not attempted here (`impact-of` is out
  of scope for `/ll:verify-issues`). Verdict: OUTDATED.
- 2026-09-02 (pre-implementation review): re-verified line count (3,706),
  importer set, the `test_enh3184`-style path-pin sweep (none pin
  `history_reader.py`), hatch `packages = ["little_loops"]` includes
  subpackages (session_store already ships this way), and that the stale
  `epic/epic-2938` branch has no unmerged changes here. Reconciled the
  Suggested Approach with the research (dropped `parsing.py`/`discovery.py`,
  added a concrete submodule map), resolved the two open naming/test-shape
  decisions, added Current/Expected Behavior, Scope Boundaries, and
  Acceptance Criteria. Verdict: VALID.

## Resolution

Converted `scripts/little_loops/history_reader.py` (3,706 lines) into
`scripts/little_loops/history_reader/` — a 14-file subpackage mirroring the
ENH-2772/ENH-2774 sibling splits:

- `_base.py` — shared `_connect_readonly`/`_row_to_dataclass`/`_stale_cutoff`/
  `STALE_DAYS_DEFAULT` plus the fixed `logger = logging.getLogger(
  "little_loops.history_reader")` and re-imported cross-package names
  (`session_store`'s `DEFAULT_DB_PATH`/`ensure_db`/`fts_phrase`/
  `normalize_issue_id`, `fsm.verdicts.CANNOT_JUDGE`).
- `models.py` — the 20 dataclasses from the file's original `# Dataclasses`
  region. The 9 additional dataclasses defined inline within a single
  domain's region (`HookEvent`, `HarnessEvent`, `HighConfidenceAbstention`,
  `VerdictEvent`, `AdvisorConsultRow`, `ConsultStats`, `AxisRates`,
  `ResearchTriageStats`, `ReviewEvent`) were co-located with that domain's
  submodule instead, per the issue's own suggested judgment call for
  `HookEvent` applied consistently.
- `search.py`, `sessions.py`, `usage.py`, `subagents.py`, `context.py`,
  `runs.py`, `summary_dag.py`, `digest.py`, `hooks.py`, `harness.py`,
  `events.py`, `formatting.py` — one submodule per backing table/view (or
  tightly-coupled cluster), matching the Suggested Approach's submodule map
  (re-derived from a fresh AST-level inventory of the file rather than the
  issue's line citations, which had drifted).
- `digest.py` needed no DAG exception: its `project_digest`/
  `render_project_context` section-provider queries hit `file_events`/
  `issue_events`/`user_corrections` directly by table name rather than
  calling another submodule's function, so it imports only from
  `_base.py`/`models.py` like every other sibling.
- `__init__.py` re-exports the full public surface (98 names in `__all__`,
  including every name from the pre-split docstring's "Public API" list, the
  three private test-access names, `STALE_DAYS_DEFAULT` (`cli/history_context.py`
  imports it directly — found via a from-scratch importer sweep, not listed
  in the issue's importer inventory), and `read_base_sha`/`read_base_dirty`).

Test file `scripts/tests/test_history_reader.py` (3,304 lines, 25 `Test*`
classes) split one-for-one into 11 `test_history_reader_<submodule>.py`
files (no dedicated file for `subagents.py`/`models.py` — the original file
had no test classes for those). `TestNewEventReaders` was moved whole into
`test_history_reader_events.py` per the Suggested Approach, even though a
fresh inspection shows it actually spans more domains (skill/commit/
prompt-opt/learning-test/orchestration/loop-run tests, not just the four
`events.py` tail domains) than the issue's research described — the file
had grown since that research was captured. Collected test count is
unchanged: 181 before and after.

Verified: full suite (`python -m pytest scripts/tests/`) — 22,620 passed, 42
skipped, 1 pre-existing unrelated failure (`test_issue_parser.py::
TestBug3293DecisionRulesCorpusDifferential::test_only_pinned_files_gain_program_design_options`,
caused by an already-staged, unrelated FEAT-3323 issue-file edit predating
this session — confirmed via `git diff --cached` showing no history_reader
content). `ruff check scripts/` and `python -m mypy scripts/little_loops/`
both exit 0. The `git diff --stat` sweep confirms none of the 17 non-test /
20 test importer files changed. Docs updated in the same commit:
`docs/reference/API.md` (restructured `## little_loops.history_reader`
entry, heading text unchanged), `docs/ARCHITECTURE.md` (Read Path mermaid
node + Components table row), `CONTRIBUTING.md` (module-tree listing).

## Session Log
- `/ll:manage-issue` - 2026-09-03T05:18:58 - `ca5d5b5d-2640-4a8f-b9c1-7d66de090028.jsonl`
- `/ll:manage-issue` - 2026-09-03T05:18:33 - `ca5d5b5d-2640-4a8f-b9c1-7d66de090028.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:56:29 - `7842a080-b0fe-422b-a8bd-a0e7be14b133.jsonl`
- `/ll:confidence-check` - 2026-09-03T03:55:11 - `01821a2b-4cf7-4cc7-bdc4-16881b6cbd8f.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:32:07 - `b08d9181-74d3-46eb-8d3a-a167537e57ed.jsonl`
- `/ll:refine-issue` - 2026-09-03T03:19:30 - `983e671b-5b21-4f7b-86e9-1898ea8c1563.jsonl`
- `/ll:wire-issue` - 2026-09-03T03:06:46 - `e42909d5-e77d-478c-b142-52f1ba049345.jsonl`
- `/ll:refine-issue` - 2026-09-03T02:51:56 - `00f0e408-f05f-43a3-bdc7-1e52bd1f47ab.jsonl`
- `/ll:verify-issues` - 2026-09-03T02:27:50 - `ec373f26-c22d-4cdb-bcd2-9da717f53d54.jsonl`
- `/ll:confidence-check` - 2026-08-29T23:32:17 - `8d7bb2d0-d27b-4d28-89fe-e2d8b28cb272.jsonl`
- `/ll:verify-issues` - 2026-08-29T23:27:10 - `8d7bb2d0-d27b-4d28-89fe-e2d8b28cb272.jsonl`
- `/ll:wire-issue` - 2026-08-29T23:19:32 - `3877ebdc-d9d3-4449-9bcf-1a7f4ef3ce26.jsonl`
- `/ll:refine-issue` - 2026-08-29T23:06:34 - `ed9b2f61-6325-4a0c-aa2f-badcd208e1b6.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:49 - `6160b806-1147-4cb9-be05-f6b3edf1653b.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`

---

## Status

**Completed** | Created: 2026-07-24 | Completed: 2026-09-03 | Priority: P3
