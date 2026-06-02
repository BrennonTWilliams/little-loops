---
id: ENH-1866
type: ENH
priority: P3
status: done
captured_at: '2026-06-01T00:00:00Z'
completed_at: '2026-06-01T19:32:27Z'
discovered_date: '2026-06-01'
discovered_by: issue-size-review
parent: ENH-1858
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1866: `ll-deps tree` CLI command, tests, and docs

## Summary

Document the already-shipped `ll-deps tree` subcommand: add the `ll-deps tree` block to `docs/reference/CLI.md`, correct the stale `main_deps` sub-commands list in `docs/reference/API.md` (`validate, suggest, report` → `analyze, validate, fix, apply, tree`), and add the `ll-deps tree --epic EPIC-NNN` row to `skills/map-dependencies/SKILL.md`.

The CLI implementation and tests shipped in commit `91ae2f9c` — `scripts/little_loops/cli/deps.py` has the `tree` subparser (lines 222–238) and handler (lines 254–315), `scripts/little_loops/dependency_mapper/formatting.py` has `format_epic_tree()` (line 252), and `scripts/tests/test_deps_cli.py:TestDepsTree` has 6 passing tests. Only documentation remains.

## Current Behavior

`ll-deps tree --epic EPIC-NNN` works end-to-end — the subcommand shipped in commit `91ae2f9c`. However:
- `docs/reference/CLI.md` has no `ll-deps tree` section (only `analyze`, `validate`, `fix`, `apply` are documented)
- `docs/reference/API.md:3427` lists stale sub-commands: `validate, suggest, report`
- `skills/map-dependencies/SKILL.md` has no `tree` row in its Examples table

## Expected Behavior

After this issue: `docs/reference/CLI.md` documents `ll-deps tree` with `--epic`/`--format` flags and example output. `docs/reference/API.md` lists `analyze, validate, fix, apply, tree` for `main_deps`. `skills/map-dependencies/SKILL.md` includes an `ll-deps tree --epic EPIC-NNN` row.

## Parent Issue

Decomposed from ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Prerequisite

~~**ENH-1863 must ship first.**~~ `format_epic_tree()` shipped in `formatting.py:252` as part of commit `91ae2f9c`. Prerequisite satisfied.

## Proposed Solution

_Steps 1–5 shipped in commit `91ae2f9c`. Only documentation remains._

### ~~Step 1 — Add `tree` subparser in `main_deps()`~~ ✓ Done

`deps.py:222–238`. Subparser declares `--epic` (required) and `-f/--format {text,json}` (default `text`).

### ~~Step 2 — Implement `_cmd_tree()` handler~~ ✓ Done

`deps.py:254–315`. Loads all issues with `status_filter=all_statuses` (all 6 values), resolves forward refs from `epic_info.relates_to` and backward refs where `i.parent == epic_id`, builds `DependencyGraph.from_issues()`, dispatches on `args.format`.

### ~~Step 3 — JSON path~~ ✓ Done

`deps.py:289–307`. Emits `{"root": ..., "nodes": [...], "edges": [...]}` via `print_json()`.

### ~~Step 4 — Tests~~ ✓ Done

`scripts/tests/test_deps_cli.py:TestDepsTree` — 6 test cases:
- `test_tree_epic_not_found` — EPIC not found → exit 1
- `test_tree_no_children` — empty EPIC → `"{EPIC}: (no children)"`, exit 0
- `test_tree_linear_chain` — renders `├──`/`└──` connectors
- `test_tree_backward_refs` — `parent:` frontmatter child resolution
- `test_tree_done_children_included` — done children appear in tree and count
- `test_tree_json_output` — JSON round-trip with `root`, `nodes`, `edges`

### Step 5 — `docs/reference/CLI.md` (REMAINING)

Insert `#### ll-deps tree` block immediately before the `**Examples:**` block at line 1237 of `docs/reference/CLI.md`. Add usage, `--epic`/`--format` args table, and a brief example:

```markdown
#### `ll-deps tree`

Render an EPIC's child issue hierarchy as a Unicode box-drawing tree with dependency edges.

| Flag | Short | Description |
|------|-------|-------------|
| `--epic` | | EPIC issue ID to render (required, e.g. `EPIC-1773`) |
| `--format` | `-f` | Output format: `text` (default), `json` |

JSON output (`--format json`) emits `{"root": "EPIC-NNN", "nodes": [...], "edges": [...]}`.
Exits 0 on success; exits non-zero if the EPIC is not found.
```

Also add `ll-deps tree --epic EPIC-NNN` to the `**Examples:**` bash block.

### Step 6 — `docs/reference/API.md` (REMAINING)

At `API.md:3427`, replace:

```
**Sub-commands:** `validate`, `suggest`, `report`
```

with:

```
**Sub-commands:** `analyze`, `validate`, `fix`, `apply`, `tree`
```

### Step 7 — `skills/map-dependencies/SKILL.md` (REMAINING)

Add two rows to the `## Examples` table at `SKILL.md:118–131`:

```markdown
| "Show EPIC child hierarchy" | `ll-deps tree --epic EPIC-NNN` |
| "EPIC tree as JSON" | `ll-deps tree --epic EPIC-NNN --format json` |
```

Add a `### EPIC Tree View` usage section under the existing `### Validation Only` section:

```markdown
### EPIC Tree View

```bash
ll-deps tree --epic EPIC-1773          # Text tree with ├──/└── connectors
ll-deps tree --epic EPIC-1773 -f json  # Structured JSON (root, nodes, edges)
```
```

## Integration Map

### Files Already Modified (shipped `91ae2f9c`)

- `scripts/little_loops/cli/deps.py` — `tree` subparser at lines 222–238, handler at lines 254–315
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_epic_tree()` at line 252
- `scripts/tests/test_deps_cli.py` — `TestDepsTree` with 6 test cases (created by this work)

### Files to Modify (remaining doc work)

- `docs/reference/CLI.md` — add `#### ll-deps tree` block before the `**Examples:**` block (after line 1235)
- `docs/reference/API.md` — fix `main_deps` sub-commands at line 3427 (`validate, suggest, report` → `analyze, validate, fix, apply, tree`)
- `skills/map-dependencies/SKILL.md` — add two `tree` rows to Examples table (after line 131) and a `### EPIC Tree View` usage section

### Dependent Files (read-only, no changes needed)

- `scripts/little_loops/dependency_mapper/formatting.py:252` — `format_epic_tree(root_id, root_info, child_map, graph, use_color=True) -> str`
- `scripts/little_loops/dependency_graph.py:55` — `DependencyGraph.from_issues(issues, completed_ids, all_known_ids) -> DependencyGraph`
- `scripts/little_loops/issue_parser.py:831` — `find_issues(config, status_filter=...) -> list[IssueInfo]`; `IssueInfo.parent` at line 251
- `scripts/little_loops/cli/output.py` — `colorize()` (line 139), `print_json()` (line 146), `configure_output()` (line 88), `use_color_enabled()` (line 134)

### Similar Patterns

- `scripts/little_loops/cli/deps.py:222` — existing `tree` subparser (reference for docs)
- `scripts/tests/test_deps_cli.py:TestDepsTree` — 6 test cases (already exist)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1866_doc_wiring.py` — new test file needed; follow pattern in `scripts/tests/test_enh1846_doc_wiring.py`. Assert: (1) `"ll-deps tree"` in `CLI.md`, (2) `"--epic"` in `CLI.md`, (3) `"tree"` in `API.md` after the `main_deps` anchor, (4) stale `"suggest"` and `"report"` absent from `API.md` `main_deps` block, (5) `"ll-deps tree --epic"` in `skills/map-dependencies/SKILL.md` [Agent 3 finding]

## Implementation Steps

~~1. Add `tree` subparser in `main_deps()` in `deps.py`~~ ✓ `deps.py:222`
~~2. Implement `_cmd_tree()` with child resolution~~ ✓ `deps.py:254`
~~3. Build `DependencyGraph.from_issues()` restricted to child set~~ ✓ `deps.py:284`
~~4. Call `format_epic_tree()` (text) or `print_json()` (JSON)~~ ✓ `deps.py:289–313`
~~5. Add `TestDepsTree` in `test_deps_cli.py`~~ ✓ 6 tests passing

6. Add `#### ll-deps tree` block to `docs/reference/CLI.md` (before `**Examples:**` block, after line 1235)
7. Fix stale `main_deps` sub-commands in `docs/reference/API.md:3427`
8. Add `tree` rows and `### EPIC Tree View` section to `skills/map-dependencies/SKILL.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Write `scripts/tests/test_enh1866_doc_wiring.py` — doc wiring test file asserting all three doc targets contain the expected `ll-deps tree` content and the stale `suggest`/`report` text is absent from `API.md`; follow pattern in `scripts/tests/test_enh1846_doc_wiring.py`

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

- ~~`ll-deps tree --epic EPIC-NNN` works end-to-end~~ ✓ shipped
- ~~All `TestDepsTree` test cases pass~~ ✓ 6/6 passing
- ~~`ll-deps tree` appears in `ll-deps --help`~~ ✓ confirmed
- `docs/reference/CLI.md` has `#### ll-deps tree` section with `--epic`/`--format` args table
- `docs/reference/API.md:3427` lists `analyze, validate, fix, apply, tree` (not the stale `validate, suggest, report`)
- `skills/map-dependencies/SKILL.md` Examples table includes `ll-deps tree --epic EPIC-NNN` row

## Scope Boundaries

- Only adds the `tree` subcommand; does not modify `analyze`, `validate`, `fix`, or `apply` behavior
- Read-only command — no mutation of issue files or dependency data
- Does not change `DependencyGraph`, `format_epic_tree()`, or other core dependency logic (ENH-1863's scope)
- Does not support depth limits, status filtering flags, or non-EPIC roots in this iteration

## Labels

`cli`, `enhancement`, `deps`

## Status

**Done** | Created: 2026-06-01 | Completed: 2026-06-01 | Priority: P3

## Resolution

Completed 2026-06-01T19:32:27Z.

- Added `#### ll-deps tree` section to `docs/reference/CLI.md` with `--epic`/`--format` flags table and examples
- Fixed stale `main_deps` sub-commands in `docs/reference/API.md` (`validate, suggest, report` → `analyze, validate, fix, apply, tree`)
- Added two `tree` rows to `skills/map-dependencies/SKILL.md` Examples table and a `### EPIC Tree View` usage section
- Created `scripts/tests/test_enh1866_doc_wiring.py` with 6 passing wiring tests

## Session Log
- `/ll:ready-issue` - 2026-06-01T19:26:00 - `393dcf8d-0e5a-4ff6-ba4d-fb43986db4b5.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `393dcf8d-0e5a-4ff6-ba4d-fb43986db4b5.jsonl`
- `/ll:wire-issue` - 2026-06-01T19:20:58 - `36158ddf-75a7-400d-9f98-59ebf44c44b6.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:15:40 - `1d1e555b-f2c7-4df6-b812-792f05bcbe18.jsonl`
- `/ll:format-issue` - 2026-06-01T18:50:49 - `c41ca909-db8c-449b-9875-0d6bc9aa84fa.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `bcaa931c-330d-44e9-b237-2540a93e4fcb.jsonl`
