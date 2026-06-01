---
id: ENH-1864
type: ENH
priority: P3
status: done
parent: ENH-1858
captured_at: '2026-06-01T00:00:00Z'
completed_at: '2026-06-01T19:06:02Z'
discovered_date: '2026-06-01'
discovered_by: issue-size-review
size: Large
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1864: `ll-deps tree` — core implementation (subparser, resolver, renderer, tests)

## Summary

Implement the core `ll-deps tree --epic EPIC-NNN` command: add the `tree` subparser to `main_deps()`, resolve EPIC children from forward (`relates_to`) and backward (`parent`) refs, build a scoped `DependencyGraph`, render the Unicode tree with inline blocking-edge annotations, and provide JSON output. Add both CLI-level and unit tests.

**Implementation complete as of commit `4ccb0b30`.** All steps except CLI-level integration tests (`TestDepsTree` in `test_deps_cli.py`) landed in that commit. The integration test file (`scripts/tests/test_deps_cli.py`) was the final outstanding item.

## Current Behavior

`ll-deps tree --epic EPIC-NNN` is implemented and functional. The command resolves EPIC children via both forward (`relates_to`) and backward (`parent`) refs, renders a Unicode box-drawing tree with inline blocking-edge annotations, and supports `--format json` output.

## Parent Issue

Decomposed from ENH-1858: `ll-deps tree --epic EPIC-NNN` — render EPIC child hierarchy with dependency edges

## Expected Behavior

```
$ ll-deps tree --epic EPIC-1773
EPIC-1773  Audit & simplify built-in FSM loops [open, 8/12 done]
├── ENH-1641  Extract shared fragments  [open, 24d stalled]
│   └── ⮡ blocks  ENH-1820  Migrate goal-cluster to fragments  [blocked]
├── FEAT-1820  Migrate goal-cluster to fragments  [blocked by ENH-1641]
├── ENH-1774  Wave 1: ll-commit shared fragments  [done]
└── ENH-1775  Wave 2: extract generator-evaluator  [done]
```

JSON output via `--format json`.

## Proposed Solution

### Module placement
Use `formatting.py` for `format_epic_tree()` to keep the change surface flat (avoid promoting `deps.py` to a package). Decided: `formatting.py` was used.

### Implementation Steps

1. ✅ **Add `tree` subparser** in `main_deps()` in `scripts/little_loops/cli/deps.py` — registered at lines 221–238:
   ```python
   tree_parser = subparsers.add_parser("tree", help="Render EPIC child hierarchy with dependency edges")
   tree_parser.add_argument("--epic", required=True, metavar="EPIC-NNN")
   tree_parser.add_argument("-f", "--format", choices=["text", "json"], default="text")
   ```
   Dispatch at line 254: `if args.command == "tree":` — inline handler (no separate function), lines 254–315.

2. ✅ **Resolve children** (inline in `deps.py:259–287`): uses `_find_issues(tree_cfg, status_filter=all_statuses)` where `all_statuses = {"open", "in_progress", "blocked", "deferred", "done", "cancelled"}`. Forward refs from `epic_info.relates_to`; backward refs via `i.parent == epic_id`. Unioned into `all_child_ids`. `done_ids` = statuses in `{"done", "deferred"}`.

3. ✅ **Build filtered `DependencyGraph`** (`deps.py:284–287`): `_DG.from_issues(child_issues, completed_ids=done_ids, all_known_ids=all_child_ids)`.

4. ✅ **Render tree** as `format_epic_tree()` in `scripts/little_loops/dependency_mapper/formatting.py:252–296`. Uses `BOX_BL`/`BOX_ML`/`BOX_V` from `output.py`, `EDGE_COLOR['blocks']` from `clusters.py`. Status badges `[done]`/`[blocked]` inline; `[open]` suppressed. Blocking edges annotated as `⮡ blocks ISSUE-NNN`.

5. ✅ **JSON path** (`deps.py:289–307`): `{"root": ..., "nodes": [...], "edges": [...]}` emitted via `print_json()`.

6. ✅ **Unit tests** for `format_epic_tree()`: `TestFormatEpicTree` at `scripts/tests/test_dependency_mapper.py:1004–1053`. Covers: no-children sentinel, linear chain connectors (`├──`/`└──`), done/blocked badges, blocking-edge annotation (`⮡ blocks`). `make_issue()` helper (lines 35–62) already had `parent` and `status` params — no extension needed.

7. ✅ **Epilog updated** (`deps.py:107–108`): `tree --epic EPIC-1773` and `tree --epic EPIC-1773 -f json` examples added.

8. ✅ **`format_epic_tree` exported** from `scripts/little_loops/dependency_mapper/__init__.py` at lines 50 (import) and 83 (`__all__`).

9. **CLI-level integration tests** in `scripts/tests/test_deps_cli.py` (file does not yet exist): create `TestDepsTree` class using `tmp_path` + `patch.object(sys, "argv", [...])` + `capsys.readouterr()` pattern (see `TestMainCLI.test_analyze_no_issues` at `test_dependency_mapper.py:1407`). Cover:
   - EPIC with no children → `"{epic_id}: (no children)"`, exit 0
   - EPIC with linear chain → output contains `├── ` and `└── `
   - EPIC not found → exit non-zero
   - `--format json` round-trips (nodes + edges structure)

## Integration Map

### Files Modified

- `scripts/little_loops/cli/deps.py` — `tree` subparser at lines 221–238; inline handler at lines 254–315; epilog `tree` examples at lines 107–108; imports `format_epic_tree` at line 80
- `scripts/little_loops/dependency_mapper/formatting.py` — `format_epic_tree()` at lines 252–296 (alongside `format_report()` at line 21 and `format_text_graph()` at line 145)
- `scripts/little_loops/dependency_mapper/__init__.py` — `format_epic_tree` imported at line 50, listed in `__all__` at line 83

### Remaining File to Create

- `scripts/tests/test_deps_cli.py` — CLI-level integration tests (`TestDepsTree`)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_parser.py` — `find_issues(config, status_filter=...)` at line 831; `IssueParser.parse_file()` at line 383; `IssueInfo` has `parent: str | None`, `relates_to: list[str]`, `status: str`, `issue_id: str`, `title: str`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues(issues, completed_ids, all_known_ids)` at line 55
- `scripts/little_loops/cli/output.py` — `colorize()` (line 139), `print_json()` (line 146), `BOX_ML = "├"` (line 60), `BOX_BL = "└"` (line 58), `BOX_V = "│"` (line 55), `TYPE_COLOR` (line 80), `PRIORITY_COLOR` (line 72), `configure_output()` (line 88), `use_color_enabled()` (line 134)
- `scripts/little_loops/cli/issues/clusters.py` — `EDGE_COLOR` (line 16): `"blocks": "31"` (red), `"blocked_by": "33"` (yellow), `"depends_on": "35"` (magenta), `"relates_to": "37"` (white), `"parent": "34"` (blue), `"sibling": "36"` (cyan)
- `scripts/little_loops/cli/deps.py` internal `_load_issues()` (lines 15–63) — NOT used by tree handler; applies active-only `status_filter` by default

### Similar Patterns

- `scripts/doc_scraper.py:DocScraper._print_sitemap()` (line 824) — canonical recursive indent pattern used as reference
- `scripts/little_loops/cli/issues/clusters.py:_render_cluster_diagram()` (line 215) — EDGE_COLOR-based coloring reference
- `scripts/little_loops/dependency_mapper/formatting.py:format_text_graph()` (line 145) — ASCII chain renderer; `format_epic_tree()` uses Unicode box chars instead

### Tests

- `scripts/tests/test_dependency_mapper.py` — `make_issue()` at lines 35–62 (already has `parent` + `status` params); `TestFormatEpicTree` at lines 1004–1053 (4 tests: linear chain, no-children, done/blocked badges, blocking-edge annotation); `TestMainCLI` at lines 1330+ for setup convention reference
- `scripts/tests/conftest.py` — shared fixtures (`temp_project_dir`, `sample_config`, `issues_dir`)
- `scripts/tests/test_deps_cli.py` — new file (does not yet exist); `TestDepsTree` CLI integration tests

### Documentation

- `docs/reference/CLI.md` — `### ll-deps` section needs `tree --epic EPIC-NNN` entry — **tracked by ENH-1865**
- `docs/reference/API.md` — `### main_deps` section has stale subcommands list — **tracked by ENH-1865**
- `skills/map-dependencies/SKILL.md` — `## How to Use` and `## Examples` table missing `tree` — **tracked by ENH-1865**

## Impact

- **Priority**: P3 - Low-urgency enhancement; dependency visualization is useful for EPIC oversight but not blocking other work
- **Effort**: Large - New subparser, child-resolution logic, Unicode tree renderer, JSON output path, CLI-level tests, and unit tests across multiple files
- **Risk**: Low - Purely additive; no existing subcommands or data structures are modified
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `deps`, `ll-deps`

## Scope Boundaries

- No mutation of issue files.
- No automatic edge inference from prose — only `blocked_by` / `depends_on` / `blocks` frontmatter.
- `SprintManager.load_or_resolve()` intentionally NOT used here.

## Session Log
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f7d04b57-0a32-4582-abef-34489b0e43ac.jsonl`
- `hook:posttooluse-status-done` - 2026-06-01T19:07:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a952b9dc-117a-44ac-8bd2-f5791b458cb1.jsonl`
- `/ll:refine-issue` - 2026-06-01T19:21:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a38dfe29-9c06-43e8-ade3-e040edecae62.jsonl`
- `/ll:ready-issue` - 2026-06-01T18:56:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a38dfe29-9c06-43e8-ade3-e040edecae62.jsonl`
- `/ll:refine-issue` - 2026-06-01T18:43:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca893-3738-4d07-9997-b5b15ecc0bae.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b821a849-b0a9-44d9-97a9-a7d0507e8dea.jsonl`
- `/ll:wire-issue` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8eeca893-3738-4d07-9997-b5b15ecc0bae.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c41ca909-db8c-449b-9875-0d6bc9aa84fa.jsonl`

---

## Status

**Done** | Created: 2026-06-01 | Completed: 2026-06-01 | Priority: P3
