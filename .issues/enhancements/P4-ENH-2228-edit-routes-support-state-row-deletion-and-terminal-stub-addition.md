---
id: ENH-2228
title: 'edit-routes: support state row deletion and terminal stub addition'
type: ENH
priority: P4
status: open
captured_at: '2026-06-19T17:41:31Z'
discovered_date: '2026-06-19'
discovered_by: capture-issue
relates_to:
- ENH-2227
confidence_score: 98
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 21
score_change_surface: 20
---

# ENH-2228: edit-routes: support state row deletion and terminal stub addition

## Summary

`ll-loop edit-routes` currently treats deleted rows as a silent no-op — removing a state from the edited table leaves that state's YAML block untouched. This is a footgun. Additionally, the editor has no way to add new states because the parser rejects unknown row names and routing info alone can't scaffold a full state definition. This issue adds deletion support and a narrow addition path for terminal stubs.

## Current Behavior

When a state row is removed from the decision table during `ll-loop edit-routes`, the state's YAML block is left unchanged — deletion is a silent no-op with no warning. New state names in the table are rejected by the parser with an error, so users cannot add states through the editor at all.

## Expected Behavior

Removing a row from the edited table deletes the corresponding state block from the loop YAML (guarded by a `--allow-delete` flag or interactive confirm). A warning is emitted for each remaining state that references a deleted state. New rows with all-empty verdict cells are inserted as `terminal: true` stubs. Non-empty rows with unknown names are rejected with a clear error.

## Motivation

After ENH-2227 landed the decision-table editor, two gaps remain:

1. **Silent no-op on row deletion** — users expect that removing a row from the table removes the state from the loop. Instead nothing happens, with no warning. This diverges from the mental model the editor establishes.
2. **No way to add new terminal exits** — a common routing refactor is splitting a monolithic `done` state into `done_success` / `done_failure`. The table editor forces the user to drop to raw YAML for this, even though terminal stubs require no action definition.

Full state addition (states with `action_type`/`action`) is intentionally out of scope — the table format cannot carry the necessary fields.

## Implementation Steps

### 1. Deletion: detect and apply missing rows

In `RouteTableApplier.apply` (`scripts/little_loops/fsm/route_table.py`):

- After parsing `new_matrix`, diff `set(old_matrix.keys()) - set(new_matrix.keys())` to find deleted states.
- For each deleted state, remove its key from `states_data` in the ruamel CommentedMap.
- Scan remaining states in `new_matrix` for any cell value that references a deleted state name; collect as dangling-route warnings.
- Emit warnings to stderr before writing (same channel as gap detection).
- Gate deletion behind a `--allow-delete` flag (or interactive confirm) so a mistaken row omission doesn't silently destroy a state.

### 2. Terminal stub addition: allow new all-empty-route rows

In `RouteTableParser.parse_markdown` / `parse_csv`:

- Relax the `known_states` guard: instead of raising on unknown names, classify them as **new stubs** if all their verdict cells are empty (or `—`).
- Return new stubs in a separate dict alongside the parsed matrix (e.g., `(matrix, new_stubs: list[str])`).

In `RouteTableApplier.apply`:

- For each name in `new_stubs`, insert a minimal state block into `states_data`:
  ```yaml
  <name>:
    terminal: true
  ```
- Preserve ruamel comment round-trip; append new states after the last existing state.

### 3. Parser API change

`parse_markdown` / `parse_csv` currently return `dict[str, dict[str, str]]`. Change to return a dataclass or named tuple:

```python
@dataclass
class ParsedTable:
    matrix: dict[str, dict[str, str]]
    new_stubs: list[str]
    deleted_states: list[str]  # states in known_states but absent from table
```

Update `cmd_edit_routes` in `scripts/little_loops/cli/loop/edit_routes.py` to consume the new return type and pass `deleted_states` + `new_stubs` to the applier.

### 4. Gap detection update

`detect_routing_gaps` should treat newly added terminal stubs as valid targets when checking for dangling routes, so newly wired routes to the stub don't generate false-positive warnings during the same edit session.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update every `argparse.Namespace(...)` in `TestCmdEditRoutes` — add `allow_delete=False` to all 7 existing test constructors before running the test suite; these will fail with `AttributeError` otherwise
6. Add `TestMainLoopEditRoutesFlagForwarding` class in `scripts/tests/test_cli_loop_dispatch.py` — three tests: `--allow-delete` forwarded as `args.allow_delete is True`, `--no-warnings` forwarded as `args.no_warnings is True`, `--format csv` forwarded as `args.format == "csv"`; follow Pattern B from `TestMainLoopRunFlagForwarding.test_dry_run_forwarded` (line 598)
7. If `detect_routing_gaps` signature is changed to accept `new_stubs` (step 4), update its three call sites: `cmd_edit_routes` in `edit_routes.py` and the three `TestDetectRoutingGaps` test methods

## Acceptance Criteria

- Deleting a row from the edited table removes that state block from the YAML (with `--allow-delete` flag or confirm prompt).
- A warning is emitted for every remaining state that routes to a deleted state.
- Adding a new row with all-empty verdict cells creates a `terminal: true` stub in the YAML.
- Rows with unknown names that have non-empty cells are rejected with a clear error (not silently treated as stubs).
- All existing 32 edit-routes tests continue to pass.
- New tests cover: deletion with dangling-route warning, deletion without `--allow-delete` (no-op + warning), terminal stub insertion, mixed edit+delete+add in one pass.

## Scope Boundaries

- Adding states with `action_type`/`action`/`prompt`/`command` — requires fields the table cannot represent.
- Renaming states — use `/ll:rename-loop` or direct YAML editing.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_GUIDE.md` | edit-routes subcommand docs updated in ENH-2227 |
| `docs/reference/CLI.md` | CLI reference for `ll-loop edit-routes` flags |

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/route_table.py` — `RouteTableParser.parse_markdown` / `parse_csv` (relax `known_states` guard, return `ParsedTable`); `RouteTableApplier.apply` (state-level deletion diff, terminal stub insertion, dangling-route warnings)
- `scripts/little_loops/cli/loop/edit_routes.py` — `cmd_edit_routes()`: consume new `ParsedTable` return type, pass `deleted_states` + `new_stubs` to applier, handle `--allow-delete` flag
- `scripts/little_loops/cli/loop/__init__.py` — `edit_routes_parser` block: add `--allow-delete` flag (currently registers only `--format`, `--dry-run`, `--no-warnings`)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_edit_routes.py` — primary test suite (32 existing tests across `TestRouteTableParser`, `TestRouteTableApplier`, `TestCmdEditRoutes` classes); add new test cases here
- `docs/guides/LOOPS_GUIDE.md` — user-facing edit-routes docs; needs `--allow-delete` flag and terminal stub workflow documented
- `docs/reference/CLI.md` — CLI reference; needs `--allow-delete` added to edit-routes flag table

### Similar Patterns
- `scripts/little_loops/fsm/route_table.py:RouteTableApplier.apply` — existing verdict-level "diff old vs new" pattern: iterates `old_row` keys absent from `new_row` and calls `_clear_route_field`; extend same pattern one level up for state deletion: `set(old_matrix.keys()) - set(new_matrix.keys())`
- `scripts/little_loops/fsm/types.py:ExecutionResult` — `@dataclass` pattern to follow for `ParsedTable`; typed fields, optional `field(default_factory=list)` for list fields
- `scripts/little_loops/cli/migrate_relationships.py` — canonical dry-run gate idiom: `if not dry_run: atomic_write(path, new_content)`; prefix printed lines with `[DRY RUN] `

### Tests
- `scripts/tests/test_ll_loop_edit_routes.py` — add to `TestRouteTableParser` (new stub classification), `TestRouteTableApplier` (deletion + dangling-route warning, no-op without flag), `TestCmdEditRoutes` (mixed edit+delete+add); follow existing helper `_make_project(tmp_path)` and inline YAML fixture pattern
- `scripts/tests/fixtures/fsm/` — existing fixtures (`valid-loop.yaml`, `loop-with-unreachable-state.yaml`) can be referenced; write inline YAML in tests for deletion/stub scenarios

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — currently mocks `cmd_edit_routes` in `_mock_handlers()` (line 31) but has **no flag-forwarding tests** for `edit-routes`; add `TestMainLoopEditRoutesFlagForwarding` class following the Pattern B used for `cmd_validate --json` (line 143): test that `--allow-delete`, `--no-warnings`, and `--format csv` are each parsed and forwarded as the correct `args.*` attribute [Agent 3 finding]
- `scripts/tests/test_ll_loop_edit_routes.py` — all 7 existing `TestCmdEditRoutes` tests construct `argparse.Namespace(format=..., dry_run=..., no_warnings=...)` **without** an `allow_delete` field; once `cmd_edit_routes` accesses `args.allow_delete`, those tests will fail with `AttributeError`; add `allow_delete=False` to every `argparse.Namespace(...)` call in that class before writing new tests [Agent 2 + 3 finding]
- `scripts/tests/test_ll_loop_edit_routes.py` — `TestDetectRoutingGaps` tests (`test_detects_unreachable_state`, `test_valid_loop_no_warnings`, `test_detects_missing_no_arm`) will break if Implementation Step 4 changes the `detect_routing_gaps` signature to accept a `new_stubs` parameter; assess during implementation and update call sites accordingly [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Warning channel**: The issue specifies "emit warnings to stderr" but `edit_routes.py` uses `print(f"⚠  {w}")` to **stdout** (same as `detect_routing_gaps` output). Tests at `test_ll_loop_edit_routes.py` check `captured.out + captured.err` combined for warning assertions, treating channel as an implementation detail. Match existing stdout `⚠  {msg}` pattern for consistency.
- **`--allow-delete` flag not yet registered**: `edit_routes_parser` block in `__init__.py` currently registers three flags only. Add `parser.add_argument("--allow-delete", action="store_true", help="Allow deletion of state blocks from the YAML")` following the existing `--no-warnings` entry.
- **ruamel CommentedMap terminal stub insertion**: Use `states_data[new_state_name] = CommentedMap({"terminal": True})` for append-order insertion. If position relative to an existing state is required, ruamel supports `states_data.insert(pos, key, value)`. Import: `from ruamel.yaml.comments import CommentedMap`.
- **`states_data.get(state_name)` returns `None` guard**: Current `apply()` already has `if state_data is None: continue` — deletion code should call `states_data.pop(state_name, None)` directly on `states_data` (the CommentedMap returned by `data.get("states", {})`) without going through `state_data`.
- **`ParsedTable` dataclass location**: Place in `route_table.py` alongside the existing classes; no separate types file needed for this narrow return type. Follow minimal `@dataclass` pattern (no `to_dict()` needed since it's internal).
- **`FSMState.terminal` field**: Defined in `scripts/little_loops/fsm/schema.py` line 432 as `terminal: bool = False`. New stubs need only `{"terminal": True}` in the YAML block; no other fields required.

## Impact

- **Priority**: P4 — useful ergonomic improvement to `edit-routes`; no blocking issues depend on it
- **Effort**: Small — changes confined to `RouteTableParser`/`RouteTableApplier` in `route_table.py` and `cmd_edit_routes` in `edit_routes.py`; no new infrastructure
- **Risk**: Low — deletion is gated behind `--allow-delete` flag so existing behavior is unchanged without the flag; 32 passing edit-routes tests provide regression coverage
- **Breaking Change**: No — `ParsedTable` return type is internal; CLI flags are additive

## Labels

`enhancement`, `fsm`, `loops`, `edit-routes`, `cli`

## Status

**Open** | Created: 2026-06-19 | Priority: P4

---

## Session Log
- `/ll:ready-issue` - 2026-06-19T18:14:48 - `d86af79c-3e1f-40cd-b9f4-115bb6646250.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `09eb25b3-0a3b-4a28-8e52-2bbf0a723339.jsonl`
- `/ll:wire-issue` - 2026-06-19T18:04:40 - `b1c3d65b-6e13-4490-822a-d67a820c4839.jsonl`
- `/ll:refine-issue` - 2026-06-19T17:52:18 - `3df2b743-e772-4e4b-abbe-61eb8a219027.jsonl`
- `/ll:format-issue` - 2026-06-19T17:45:01 - `a44bb34f-9d7b-48aa-8669-1a25c60dc0d2.jsonl`
- `/ll:capture-issue` - 2026-06-19T17:41:31Z - captured from conversation context
