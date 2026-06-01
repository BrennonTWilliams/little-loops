---
id: ENH-1866
type: ENH
priority: P3
status: open
captured_at: '2026-06-01T00:00:00Z'
discovered_date: '2026-06-01'
discovered_by: issue-size-review
parent: ENH-1858
---

# ENH-1866: `ll-deps tree` CLI command, tests, and docs

## Summary

Wire `ll-deps tree --epic EPIC-NNN` as a new subcommand in `scripts/little_loops/cli/deps.py`, consuming `format_epic_tree()` from ENH-1863. Add a `TestDepsTree` class in a new `scripts/tests/test_deps_cli.py`, update `docs/reference/CLI.md` and `docs/reference/API.md`, and add the `ll-deps tree` row to `skills/map-dependencies/SKILL.md`.

## Parent Issue

Decomposed from ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Prerequisite

**ENH-1863 must ship first.** This issue imports `format_epic_tree()` from `dependency_mapper/formatting.py`; that function is defined in ENH-1863.

## Proposed Solution

### Step 1 — Add `tree` subparser in `main_deps()`

In `scripts/little_loops/cli/deps.py`, add alongside existing `analyze`, `validate`, `fix`, `apply` subparsers:

```python
tree_parser = subparsers.add_parser("tree", help="Render EPIC child hierarchy")
tree_parser.add_argument("--epic", required=True, metavar="EPIC-NNN")
tree_parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
```

Dispatch: `if args.command == "tree": return _cmd_tree(args, config, logger)`.

### Step 2 — Implement `_cmd_tree()` handler

Child resolution (do NOT use `SprintManager.load_or_resolve()` — it filters to active statuses only, but the tree needs all children including done/deferred for the `8/12 done` summary line. Do NOT call the internal `_load_issues()` helper in `deps.py` (lines 15–32) — it wraps `find_issues()` with the same active-only default):

1. Parse EPIC file via `IssueParser(config).parse_file(epic_path)` → `epic_info.relates_to` (forward refs).
2. Call `find_issues` with an explicit `status_filter` — the default excludes `done` and `deferred`, which must appear in the tree for the `8/12 done` count:
   ```python
   all_issues = find_issues(
       config,
       status_filter={"open", "in_progress", "blocked", "deferred", "done"},
   )
   ```
   Filter `issue.parent == epic_id` (backward refs). Union with forward-ref set.
3. Separate into `done_ids` (status in `{"done", "deferred"}`) and the full child set.

Build filtered graph: `graph = DependencyGraph.from_issues(child_issues, completed_ids=done_ids, all_known_ids=all_child_ids)`.

Text path: call `format_epic_tree(root_id, root_info, child_map, graph, use_color=use_color_enabled())` and print.

### Step 3 — JSON path

Build and emit via `print_json()` from `cli/output.py`:

```json
{
  "root": "EPIC-NNN",
  "nodes": [{"id": "...", "title": "...", "status": "...", "parent": "..."}],
  "edges": [{"from": "...", "to": "...", "kind": "..."}]
}
```

### Step 4 — Tests (`test_deps_cli.py`)

New file `scripts/tests/test_deps_cli.py` with `TestDepsTree` class. Use `tmp_path` + `patch.object(sys, "argv", [...])` pattern from `test_dependency_mapper.py:TestMainCLI`. Cover:

1. EPIC with no children → clear message, exit 0
2. EPIC with linear chain → renders chain with `├──` / `└──`
3. EPIC with diamond dependency → renders correctly (shared node annotation)
4. EPIC not found → exit non-zero
5. `--format json` round-trips (nodes + edges structure)

### Step 5 — `docs/reference/CLI.md`

Add `ll-deps tree` subcommand block with usage, `--epic`/`--format` args, and example output matching the "Expected Behavior" block from ENH-1858.

### Step 6 — `docs/reference/API.md`

Update `### main_deps` sub-commands list: correct stale `validate, suggest, report` → `analyze, validate, fix, apply, tree`.

### Step 7 — `skills/map-dependencies/SKILL.md`

Add `ll-deps tree --epic EPIC-NNN` row to the `## Examples` table and a `### EPIC Tree View` usage section.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/deps.py` — add `tree` subparser + `_cmd_tree()` handler
- `docs/reference/CLI.md` — add `ll-deps tree` subcommand block
- `docs/reference/API.md` — update `main_deps` sub-commands list
- `skills/map-dependencies/SKILL.md` — add `ll-deps tree` row + usage section

### Files to Create

- `scripts/tests/test_deps_cli.py` — new `TestDepsTree` class

### Dependent Files (Callers/Importers)

- `scripts/little_loops/dependency_mapper/formatting.py` — `format_epic_tree()` (defined in ENH-1863)
- `scripts/little_loops/dependency_mapper/__init__.py` — public export of `format_epic_tree` (wired in ENH-1863)
- `scripts/little_loops/issue_parser.py` — `find_issues(config)` + `IssueInfo.parent` for backward child lookup
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()`
- `scripts/little_loops/cli/output.py` — `colorize()`, `print_json()`, `configure_output()`, `use_color_enabled()`
- `scripts/little_loops/cli_args.py` — `--format {text,json}` pattern from `analyze` subcommand

### Similar Patterns

- `scripts/little_loops/cli/deps.py:_cmd_analyze()` — existing handler shape; `--format {text,json}` dispatch pattern
- `scripts/tests/test_dependency_mapper.py:TestMainCLI` — `patch.object(sys, "argv", [...])` test pattern to follow
- `scripts/little_loops/cli/issues/list_cmd.py:cmd_list()` — `parent:` field child-bucketing, including `issue.parent.split("-", 1)[0] == "EPIC"` guard

## Implementation Steps

1. Add `tree` subparser in `main_deps()` in `deps.py`
2. Implement `_cmd_tree()` with child resolution (forward + backward refs, status split)
3. Build `DependencyGraph.from_issues()` restricted to child set
4. Call `format_epic_tree()` (text path) or build JSON dict (JSON path) and emit
5. Add `TestDepsTree` in new `test_deps_cli.py` covering five cases
6. Update `docs/reference/CLI.md` with `ll-deps tree` block
7. Update `docs/reference/API.md` `### main_deps` sub-commands list
8. Update `skills/map-dependencies/SKILL.md` with `ll-deps tree` row

## Covers (from ENH-1858)

Parent steps covered by this child:
- Step 1: Add `tree` subparser to `main_deps()` in `deps.py`
- Step 2: `_cmd_tree` handler + child resolution
- Step 3: `DependencyGraph.from_issues` integration
- Step 5: JSON path via `print_json()`
- Step 6: `TestDepsTree` class in new `test_deps_cli.py` — 5 test cases
- Step 7: `docs/reference/CLI.md` documentation
- Step 9: `docs/reference/API.md` `main_deps` sub-commands list update
- Step 10: `skills/map-dependencies/SKILL.md` add `ll-deps tree --epic EPIC-NNN` row + usage section
- Step 12: Structural note: use `formatting.py` path to avoid `deps.py` → package migration

## Impact

- **Priority**: P3 — follows parent priority
- **Effort**: Small–Medium — CLI wiring, child resolution, tests, and docs
- **Risk**: Low — new read-only subcommand; no mutation of existing behavior
- **Breaking Change**: No

## Success Metrics

- `ll-deps tree --epic EPIC-NNN` works end-to-end and matches the expected output in ENH-1858
- All five `TestDepsTree` test cases pass
- `ll-deps tree` appears in `ll-deps --help`
- `docs/reference/CLI.md`, `docs/reference/API.md`, and `skills/map-dependencies/SKILL.md` are updated

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcaa931c-330d-44e9-b237-2540a93e4fcb.jsonl`
