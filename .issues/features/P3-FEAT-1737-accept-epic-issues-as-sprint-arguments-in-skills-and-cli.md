---
id: FEAT-1737
type: FEAT
priority: P3
status: done
captured_at: '2026-05-27T05:02:23Z'
completed_at: '2026-05-28T00:47:52Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-1737: Accept EPIC Issues as Sprint Arguments in Skills and CLI Commands

## Summary

Add `SprintManager.load_or_resolve()` as a single-point resolver that accepts either a sprint name (existing file-based path) or an EPIC ID, transparently propagating to all sprint subcommands and skills. Resolution uses a union of the EPIC's `relates_to:` field (forward) and `parent:` on child issues (backward), filtered to active statuses. An optional `--save` flag on `ll-sprint run` materializes the resolved sprint YAML for inspect/edit-before-run workflows.

## Current Behavior

There is no way to pass an EPIC issue ID directly as a sprint argument. To run all issues under an EPIC, users must first create a sprint YAML file manually listing each child issue, then pass that file to `ll-sprint`. EPICs function as organizational containers but are not first-class execution units — the link between an EPIC and its runnable child set requires a manual intermediate step.

## Motivation

EPICs are already used as organizational containers for related issues via the `parent:` / `relates_to:` relationship. However, to run an EPIC's issues as a batch you currently need to first create a sprint file manually. Accepting EPICs directly as sprint arguments eliminates that friction and makes EPICs a first-class execution unit — the same way sprint files are.

## Expected Behavior

- `ll-sprint run EPIC-1234` resolves EPIC-1234's children and executes them in dependency order, exactly as if a sprint file listing those issues had been passed.
- Resolution is a union of forward lookup (`relates_to:` on the EPIC file) and backward scan (`parent: EPIC-NNN` on child issues), deduplicated and filtered to active statuses (`open`, `in_progress`, `blocked`).
- Skills that call `SprintManager` through the Python path (`/ll:create-sprint`, `/ll:review-sprint`) inherit EPIC resolution automatically — no separate wiring per skill.
- `ll-sprint run EPIC-1234 --save` also writes `.ll/sprints/epic-1234.yaml` before executing.
- If the EPIC has no active children, a clear message is printed and the runner exits cleanly (exit 0).
- Resume (`--resume`) works because `.sprint-state.json` tracks `sprint_name: epic-1234`.

## Acceptance Criteria

- [ ] `SprintManager.load_or_resolve(arg)` is implemented in `sprint.py` and handles both sprint names and `EPIC-NNN` IDs.
- [ ] All sprint subcommands (`run`, `show`, `analyze`, `delete`, `edit`) switch from `manager.load()` to `manager.load_or_resolve()`.
- [ ] Resolution uses the union of forward (`relates_to:`) and backward (`parent:`) lookups, deduplicated.
- [ ] Child issues are filtered to active statuses (`open`, `in_progress`, `blocked`) before execution.
- [ ] Resolved issues are ordered by priority, then dependency graph — matching existing sprint file behavior.
- [ ] When the EPIC has no active children, a clear message is printed and the runner exits cleanly (exit 0).
- [ ] When the EPIC ID does not exist, `load_or_resolve` returns `None` and the caller prints an informative error (exit non-zero).
- [ ] `ll-sprint run EPIC-NNN --save` writes `.ll/sprints/epic-{id}.yaml` before executing.
- [ ] `ll-sprint run EPIC-NNN --resume` works correctly using `sprint_name: epic-{id}` in state.
- [ ] Skills (`/ll:create-sprint`, `/ll:review-sprint`) work with EPIC IDs without additional changes.
- [ ] Existing sprint YAML file paths continue to work unchanged (no regressions).
- [ ] Unit tests cover `load_or_resolve` (file path, EPIC ID, not-found, empty children); integration test covers the `ll-sprint run EPIC-NNN` path.

## Use Case

A developer wants to work through all open issues under EPIC-1405 (EPIC Type Registration). Instead of generating a sprint file first, they run:

```bash
ll-sprint EPIC-1405
```

The runner resolves the child issues, orders them by dependency/priority, and processes them in sequence.

## Implementation Steps

1. **Add `SprintManager.load_or_resolve(arg, config)`** — single detection point in `scripts/little_loops/sprint.py`:
   - If `arg` matches `^EPIC-\d+$`, resolve it to an ephemeral `Sprint` object (name = `epic-{id}`, no YAML written)
   - Otherwise, fall through to the existing `load(arg)` file-based path
   - All subcommands that today call `manager.load(args.sprint)` switch to `manager.load_or_resolve(args.sprint)` — one-line change per subcommand (`run.py`, `show.py`, `manage.py`)

2. **Union resolution strategy** — inside `load_or_resolve`, collect children via two passes:
   - **Forward**: read `relates_to:` from the EPIC's own frontmatter
   - **Backward**: scan all issue files for `parent: EPIC-NNN` in frontmatter (authoritative source of truth)
   - Take the union; deduplicate; filter to active statuses (`open`, `in_progress`, `blocked`)
   - Order by priority field, then dependency graph (reuse existing `DependencyGraph` logic)

3. **Error handling** — `load_or_resolve` returns `None` (same contract as `load`) when:
   - The EPIC ID is not found → callers already handle `None` with a meaningful error message
   - The EPIC has no active children → return a `Sprint` with an empty `issues` list; the run path already handles this with a clean exit

4. **`--save` flag on `ll-sprint run`** — optional flag that materializes the resolved sprint YAML to `.ll/sprints/epic-{id}.yaml` before executing, enabling inspect/edit-before-run workflows without requiring it for normal use

5. **Wire into skills** — `/ll:create-sprint` and `/ll:review-sprint` skills: since they invoke `SprintManager` through the Python path, they inherit the capability automatically; update their argument descriptions to note EPIC ID support

6. **Tests** — write unit tests for `load_or_resolve` leg-by-leg before wiring into subcommands; each leg has a corresponding named test (see Tests section); implement in this order to catch failures early:
   1. `test_load_or_resolve_sprint_name` — pattern detection + fall-through to `load()`
   2. `test_load_or_resolve_epic_id_forward_lookup` — forward `relates_to:` path
   3. `test_load_or_resolve_epic_id_backward_lookup` — backward `parent:` scan
   4. `test_load_or_resolve_epic_id_union_dedup` — union + deduplication
   5. `test_load_or_resolve_filters_inactive_statuses` — status filter
   6. `test_load_or_resolve_epic_not_found` + `test_load_or_resolve_epic_no_active_children` — edge cases
   7. `test_save_flag_materializes_yaml` — `--save` path
   Then wire into subcommands and run the integration test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Resume state normalization** — in `_cmd_sprint_run()` (run.py), when creating `SprintState`, use `sprint.name` (the resolved Sprint object's name, e.g. `"epic-1234"`) rather than raw `args.sprint` (e.g. `"EPIC-1234"`). This ensures the normalized lowercase `epic-{id}` is stored in `.sprint-state.json`, making `--resume` work consistently regardless of user-input casing. The comparison `loaded_state.sprint_name == sprint.name` (not `args.sprint`) must be used in the resume-check block [Agent 2 finding]
8. **Access `args.save` via `getattr(args, 'save', False)`** in `_cmd_sprint_run()` instead of `args.save` directly — `argparse` sets the default when invoked via CLI, but `argparse.Namespace()` constructions in tests do not inherit parser defaults; `getattr` eliminates all ~60 test Namespace() update sites without touching any test file. [Mitigation added post-confidence-check]
9. **Update `_parse_sprint_args()` in `test_cli.py:TestSprintArgumentParsing`** — this helper is a local duplicate of the run parser; add `run.add_argument("--save", action="store_true")` to match the updated `main_sprint()` [Agent 2 finding]
10. **Add `"epics"` category to test fixtures** — `sprint_project` in `test_sprint_integration.py` and both `sprint_project` fixtures in `test_cli.py` need `"epics": {"prefix": "EPIC", "dir": "epics", "action": "coordinate"}` in config and `(issues_dir / "epics").mkdir()` [Agent 2 + 3 finding]
11. **Update `docs/reference/API.md`** — add `load_or_resolve()` to SprintManager methods table [Agent 2 finding]
12. **Update `docs/reference/CLI.md`** — update positional description and add `--save` flag row [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `load_or_resolve()` implementation specifics:**
- Add after `SprintManager.load()` in `scripts/little_loops/sprint.py`
- EPIC file: `self._find_issue_path(epic_id)` — already searches `epics/` via `config.issue_categories` glob; returns `Path | None`
- Forward lookup: `IssueParser(self.config).parse_file(epic_path)` → `epic_info.relates_to` (list of child IDs as strings)
- Backward lookup: `find_issues(self.config, status_filter=_ACTIVE_STATUSES)` → filter where `issue.parent == epic_id`
- Active statuses: import `_ACTIVE_STATUSES` from `scripts/little_loops/cli/issues/clusters.py` or inline `frozenset({"open", "in_progress", "blocked"})`
- `DependencyGraph.from_issues()` only uses `blocked_by`/`blocks`/`depends_on` edges for ordering — `relates_to` is NOT wired into wave ordering; this is correct behavior

**Step 2 — Exact subcommand call sites:**
- `_cmd_sprint_run()` in `scripts/little_loops/cli/sprint/run.py`
- `_cmd_sprint_show()` in `scripts/little_loops/cli/sprint/show.py`
- `_cmd_sprint_analyze()` in `scripts/little_loops/cli/sprint/manage.py`
- `_cmd_sprint_edit()` in `scripts/little_loops/cli/sprint/edit.py`
- `_cmd_sprint_delete()` uses `manager.delete(args.sprint)` (not `manager.load()`) — no change needed there

**Step 4 — `--save` flag wiring:**
- Add inline in `run_parser` block in `scripts/little_loops/cli/sprint/__init__.py`: `run_parser.add_argument("--save", action="store_true", help="...")`
- In `_cmd_sprint_run()`, after `load_or_resolve()` detects an EPIC and builds the ephemeral Sprint, call `sprint.save(manager.sprints_dir)` before executing if `getattr(args, 'save', False)` is set (use `getattr` — not `args.save` — to avoid requiring all test Namespace() calls to carry `save=False`)

**Step 5 — Skills inheritance scope:**
- `create-sprint.md` and `review-sprint.md` route through `SprintManager` via `main_sprint()` — inherit automatically ✓
- `confidence-check/SKILL.md` and `issue-size-review/SKILL.md` read sprint YAML via shell — do NOT inherit EPIC resolution; out of scope for this issue

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — Add `SprintManager.load_or_resolve()` after existing `SprintManager.load()`; uses `_find_issue_path()` for EPIC file lookup (already searches `epics/` via `config.issue_categories` glob)
- `scripts/little_loops/cli/sprint/run.py` — Change `manager.load(args.sprint)` → `manager.load_or_resolve(args.sprint)` in `_cmd_sprint_run()`; add `--save` handling after resolution
- `scripts/little_loops/cli/sprint/show.py` — Change `manager.load(args.sprint)` → `manager.load_or_resolve(args.sprint)` in `_cmd_sprint_show()`
- `scripts/little_loops/cli/sprint/manage.py` — Change `manager.load(args.sprint)` → `manager.load_or_resolve(args.sprint)` in `_cmd_sprint_analyze()`
- `scripts/little_loops/cli/sprint/edit.py` — Change `manager.load(args.sprint)` → `manager.load_or_resolve(args.sprint)` in `_cmd_sprint_edit()`
- `scripts/little_loops/cli/sprint/__init__.py` — Add `--save` flag inline in `run_parser` block (follow `action="store_true"` pattern used by `--prune`, `--revalidate`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/deps.py` — calls `Sprint.load()` directly (bypasses `SprintManager`); EPIC support there is out of scope for this issue
- `skills/confidence-check/SKILL.md` — reads sprint YAML via shell; does NOT inherit Python-path EPIC resolution (out of scope)
- `skills/issue-size-review/SKILL.md` — same; shell-level YAML read, no automatic inheritance (out of scope)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/_helpers.py` — sprint utility functions used by subcommands; imports sprint-related classes alongside the primary files [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — re-exports `main_sprint` in `__all__`; indirect registration point for the sprint entry point [Agent 1 finding]

### Similar Patterns to Follow
- `scripts/little_loops/issue_parser.py:find_issues()` — bulk scan returning `IssueInfo` with `parent` and `relates_to` populated; filter `issue.parent == "EPIC-NNN"` for backward scan
- `scripts/little_loops/cli/issues/clusters.py:_ACTIVE_STATUSES` — canonical `frozenset({"open", "in_progress", "blocked"})` to import for active-status filtering
- `scripts/little_loops/dependency_graph.py:DependencyGraph.from_issues()` + `.get_execution_waves()` — existing ordering logic; takes `list[IssueInfo]`; **does NOT use `relates_to`** (only `blocked_by`/`blocks`/`depends_on` edges contribute to wave order)

### Tests
- `scripts/tests/test_sprint.py:TestSprintManager` — add unit tests for `load_or_resolve()` (file path, EPIC ID, not-found, empty children)
- `scripts/tests/test_sprint_integration.py:sprint_project` — needs `"epics"` category added to config dict and `(issues_dir / "epics").mkdir()` for EPIC integration tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py:TestMainSprintAdditionalCoverage` — end-to-end tests for sprint CLI via `main_sprint()` + `sys.argv`; `_parse_sprint_args()` helper (in `TestSprintArgumentParsing`) is a local duplicate of the run parser and must have `--save` added alongside `run_parser` or new parser tests for `--save` will fail; the `sprint_project` fixture inside `TestMainSprintAdditionalCoverage` needs `"epics"` category + `(issues_dir / "epics").mkdir()` [Agent 1 + Agent 2 finding; `TestSprintCLIEntryPoint` corrected to `TestMainSprintAdditionalCoverage` — only one `sprint_project` fixture exists in this file]
- ~~**HIGH-BREAK RISK**: All `argparse.Namespace(...)` calls that construct args for `_cmd_sprint_run` in `test_sprint.py` (9 tests) and `test_sprint_integration.py` (15+ tests) must add `save=False`~~ — **Mitigated**: use `getattr(args, 'save', False)` in `run.py` instead of `args.save` directly; existing test Namespace() constructions require no changes [Agent 3 finding; mitigation added post-confidence-check]
- New tests to write for `load_or_resolve()` (follow `TestSprintManager.test_load_sprint` / `test_load_nonexistent` pattern): `test_load_or_resolve_sprint_name`, `test_load_or_resolve_epic_id_forward_lookup`, `test_load_or_resolve_epic_id_backward_lookup`, `test_load_or_resolve_epic_id_union_dedup`, `test_load_or_resolve_epic_not_found`, `test_load_or_resolve_epic_no_active_children`, `test_load_or_resolve_filters_inactive_statuses`, `test_save_flag_materializes_yaml` [Agent 3 finding]

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — document EPIC-ID support in the sprint argument description; also add `--save` to the flags table in `## Running a Sprint`; add a note to `## Handling Interruptions (Resume)` about `epic-{id}` state naming

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `load_or_resolve(arg)` → `Sprint | None` row to the `### SprintManager` methods table; note `--save` under the `### main_sprint` sub-commands description [Agent 2 finding]
- `docs/reference/CLI.md` — update `sprint` positional argument description from "Sprint name" to "Sprint name or EPIC ID"; add `--save` row to the flags table for `#### ll-sprint run` [Agent 2 finding]

## API/Interface

```python
# scripts/little_loops/sprint.py — SprintManager

def load_or_resolve(self, arg: str) -> "Sprint | None":
    """Load a sprint by name or resolve an EPIC ID to an ephemeral Sprint.

    Args:
        arg: Sprint name (file-based) or EPIC ID matching ^EPIC-\\d+$

    Returns:
        Sprint instance, or None if not found / EPIC not found
    """
    ...
```

CLI usage (no new flags required for basic use):

```bash
ll-sprint run EPIC-1694             # run all active children of EPIC-1694
ll-sprint run EPIC-1694 --save      # also write .ll/sprints/epic-1694.yaml first
ll-sprint run EPIC-1694 --dry-run   # preview execution plan without running
ll-sprint run my-sprint             # existing sprint YAML — unchanged behavior
```

## Impact

- **Priority**: P3 — Reduces friction for EPIC-driven workflows; not blocking but provides meaningful quality-of-life improvement for users who organize work under EPICs
- **Effort**: Medium — `SprintManager.load_or_resolve()` + union resolver + one-line subcommand updates; existing pipeline handles ordering/filtering; `--save` flag is additive
- **Risk**: Low — New detection branch; existing sprint file behavior is fully unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `sprint-runner`, `epics`, `cli`

## Status

**Open** | Created: 2026-05-27 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27; mitigations applied 2026-05-27_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 75/100 → MODERATE (revised from 67 after mitigations)

### Mitigations Applied

- **Namespace sweep eliminated**: Use `getattr(args, 'save', False)` instead of `args.save` in `_cmd_sprint_run()` — ~60 test Namespace() update sites reduced to zero. Score D: 10 → 18.
- **load_or_resolve() leg-by-leg order**: Explicit test-first sequence added to step 6 — write and pass each unit test leg before wiring into subcommands, localizing failures to individual resolution paths.

### Outcome Risk Factors (residual)
- **Moderate core logic in `load_or_resolve()`**: five resolution legs (pattern detect → forward lookup → backward scan → union dedup → status filter + ordering); mitigated by leg-by-leg test order in step 6.

## Session Log
- `/ll:ready-issue` - 2026-05-28T00:35:38 - `284cd144-0544-4ee8-b806-20b7316ec7e9.jsonl`
- `/ll:confidence-check` - 2026-05-27T06:00:00Z - `a2a9c6cc-4a64-4816-9521-d7ecff878e47.jsonl`
- `/ll:confidence-check` - 2026-05-27T00:00:00Z - `6aa2b389-8690-4aba-a467-a4575b38d46e.jsonl`
- `/ll:wire-issue` - 2026-05-28T00:05:03 - `70d1a28b-6e5d-424c-a7ee-0f4c6c686c6e.jsonl`
- `/ll:refine-issue` - 2026-05-27T23:56:20 - `05bd8488-8487-466c-b194-76003660b362.jsonl`
- `rewrite` - 2026-05-27 - Redesigned to Option C (`SprintManager.load_or_resolve()` + union resolution + `--save` flag) after exploring Epic→Sprint mapping approaches
- `/ll:format-issue` - 2026-05-27T05:04:55 - `2c37f932-1d34-4311-ac57-0faf89f85130.jsonl`
- `/ll:capture-issue` - 2026-05-27T05:02:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c91edf22-5820-4f59-9f8d-4ab2ca66f171.jsonl`
