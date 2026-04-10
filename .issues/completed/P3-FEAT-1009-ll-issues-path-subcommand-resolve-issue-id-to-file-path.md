---
id: FEAT-1009
type: FEAT
priority: P3
status: completed
discovered_date: 2026-04-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-1009: ll-issues path sub-command to resolve issue ID to file path

## Summary

Add a `path` sub-command to `ll-issues` that accepts an issue ID in any of the three supported formats (`P3-FEAT-1002`, `FEAT-1002`, or `1002`) and prints the relative path from the project root to that issue file in `.issues/`. This enables scripts and skills to resolve issue IDs to concrete file paths without shelling out to `find` or parsing directory listings.

## Current Behavior

There is no dedicated way to look up an issue file path by ID from the CLI. Scripts that need a file path must either use `ll-issues show --json <ID>` and extract the `path` field, or scan `.issues/` manually. The `show` sub-command already resolves IDs via `_resolve_issue_id` in `show.py`, but it outputs a full formatted card — not a bare path.

## Expected Behavior

```bash
ll-issues path 1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md

ll-issues path FEAT-1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md

ll-issues path P3-FEAT-1009
# .issues/features/P3-FEAT-1009-ll-issues-path-subcommand-resolve-issue-id-to-file-path.md
```

Exits 0 on success, 1 if the issue is not found.

## Acceptance Criteria

- `ll-issues path <ID>` prints the relative path for all three input formats (numeric, TYPE-NNN, P-TYPE-NNN)
- Searches active, completed, and deferred directories (matches `show` behavior)
- Exits 0 on match, 1 on not found with an error message to stderr
- Optional `--json` flag outputs `{"path": "..."}` for programmatic use
- Alias `p` registered (consistent with `show` having alias `s`)

## Motivation

Skills, hooks, and shell scripts frequently need to locate issue files by ID. Currently they must either invoke `ll-issues show --json` and parse JSON, or glob `.issues/**/*.md` and match manually. A dedicated `path` sub-command makes this a one-liner and is consistent with the Unix philosophy of composable tools.

## Use Case

A skill wants to open the file for `FEAT-1009` in an editor or read it with `cat`. With this sub-command:

```bash
ISSUE_PATH=$(ll-issues path FEAT-1009)
cat "$ISSUE_PATH"
```

Without it, the skill must use `ll-issues show --json FEAT-1009 | python3 -c "import sys,json; print(json.load(sys.stdin)['path'])"`.

## Proposed Solution

1. Add `scripts/little_loops/cli/issues/path_cmd.py` with `cmd_path(config, args)` that calls `_resolve_issue_id` (already in `show.py`) and prints the relative path.
2. Import `_resolve_issue_id` directly from `show.py` — no extraction needed. `skip.py:29` already uses `from little_loops.cli.issues.show import _resolve_issue_id`, confirming this is the established pattern.
3. Register the `path` sub-command in `__init__.py` with alias `p`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/__init__.py` — three changes:
  1. Add `from little_loops.cli.issues.path_cmd import cmd_path` to the imports block (`__init__.py:17-29`)
  2. Register `path` sub-parser with alias `p` after the `show` block (`__init__.py:257-261`)
  3. Add dispatch branch `if args.command == "path":` in the `if/elif` chain (`__init__.py:417-432`)
- `scripts/little_loops/cli/issues/show.py` — no changes required; `_resolve_issue_id` (line 17) is imported directly from here

### New Files

- `scripts/little_loops/cli/issues/path_cmd.py` — `cmd_path(config, args) -> int`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/skip.py:29` — already imports `_resolve_issue_id` from `show.py` using `from little_loops.cli.issues.show import _resolve_issue_id`; `path_cmd.py` uses the identical import

### Similar Patterns

- `scripts/little_loops/cli/issues/show.py:17` — `_resolve_issue_id(config, args)` signature; `show.py:186-189` — `path.relative_to(config.project_root)` with `ValueError` fallback
- `scripts/little_loops/cli/issues/next_issue.py:43-57` — `--json` output (`{"id": ..., "path": ...}`) then `--path` plain output pattern; closest analogue for `path_cmd.py`
- `scripts/little_loops/cli/output.py:97-99` — `print_json(data)` utility used for all `--json` output

### Tests

- New file: `scripts/tests/test_issues_path.py` (matches naming convention of `test_next_issue.py`, `test_refine_status.py`)
- Patterns to follow from `scripts/tests/test_next_issue.py`:
  - `--path` output: lines 281-290 (`patch.object(sys, "argv", [...])`, `capsys.readouterr().out.strip()`, `.endswith("filename.md")`)
  - `--json` output: lines 255-262 (`json.loads(out)`, `assert data["path"] ...`)
  - Alias invocation: lines 475-482 (`"p"` instead of `"path"` in argv)
  - Not-found exit code: `assert result == 1`
- Test all three input formats (numeric `1009`, `FEAT-1009`, `P3-FEAT-1009`)
- Test not-found returns exit code 1 with message to stderr
- Test `--json` emits `{"path": "..."}` with relative path

## API/Interface

```python
# scripts/little_loops/cli/issues/path_cmd.py
def cmd_path(config: BRConfig, args: argparse.Namespace) -> int:
    """Print relative path to an issue file.

    Args:
        config: Project configuration
        args: Parsed arguments with .issue_id (str) and optional .json (bool)

    Returns:
        0 if found, 1 if not found
    """
```

```
usage: ll-issues path [-h] [--json] issue_id

positional arguments:
  issue_id    Issue ID (e.g., 1009, FEAT-1009, P3-FEAT-1009)

options:
  --json, -j  Output as JSON object {"path": "..."}
```

## Implementation Steps

1. **Create `path_cmd.py`** — implement `cmd_path` using `from little_loops.cli.issues.show import _resolve_issue_id` (pattern established at `skip.py:29`). Relativize using `path.relative_to(config.project_root)` with `ValueError` fallback (`show.py:186-189`). For `--json`, emit `{"path": rel_path}` via `print_json` from `little_loops.cli.output`. For not-found, print to `sys.stderr` and return `1`.
2. **Register in `__init__.py:17-29`** — add `from little_loops.cli.issues.path_cmd import cmd_path` to the lazy-imports block inside `main_issues()`.
3. **Add sub-parser in `__init__.py`** — after the `show` block (`__init__.py:257-261`), add:
   ```python
   path_p = subs.add_parser("path", aliases=["p"], help="Print file path for an issue ID")
   path_p.set_defaults(command="path")
   path_p.add_argument("issue_id", help="Issue ID (e.g., 1009, FEAT-1009, P3-FEAT-1009)")
   path_p.add_argument("--json", "-j", action="store_true", help="Output as JSON object")
   add_config_arg(path_p)
   ```
4. **Add dispatch branch in `__init__.py:417-432`** — insert `if args.command == "path": return cmd_path(config, args)` before the final `return 1`.
5. **Write tests in `scripts/tests/test_issues_path.py`** — follow `test_next_issue.py` fixture setup (`_write_config`, `_make_issue`, `_setup_dirs`). Cover: all three ID formats resolve correctly, not-found returns exit code 1, `--json` emits `{"path": "..."}`, alias `p` works.
6. **Verify** — run `ll-issues path 1009` against a real issue; check exit codes with `echo $?`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/CLI.md` — add `#### ll-issues path` sub-section (with `p` alias) and example to the consolidated examples block (near line 382–606)
8. Update `README.md` — add `ll-issues path <ID>` example line in the `ll-issues` usage block (near line 391–419)
9. Update `.claude/CLAUDE.md:115` — append `path` to the parenthetical sub-command list
10. Update `commands/help.md:219` — append `path` to the parenthetical sub-command list
11. Update `skills/init/SKILL.md` — append `path` at both template text locations (lines 521 and 545)

## Impact

- **Priority**: P3 - Medium (frequently useful in scripting contexts)
- **Effort**: XS — ~50 lines of new code; ID resolution already implemented
- **Risk**: Low — additive; no changes to existing sub-commands
- **Breaking Change**: No

## Related Key Documentation

| Category | File | Relevance |
|----------|------|-----------|
| Architecture | `docs/reference/API.md` | CLI module conventions |
| Guidelines | `CONTRIBUTING.md` | Code style and test patterns |

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:382–606` — primary CLI reference; contains `### ll-issues` with `**Subcommands:**` header and individual `####` sections per sub-command plus consolidated examples block; add `path`/`p` entry in both the sub-commands list and examples block
- `README.md:391–419` — `ll-issues` usage block listing sub-commands with inline comments; add `ll-issues path <ID>` example line
- `.claude/CLAUDE.md:115` — parenthetical `(next-id, list, show, sequence, impact-effort, refine-status)` enumeration; add `path` to the list
- `commands/help.md:219` — identical parenthetical enumeration; add `path` to the list
- `skills/init/SKILL.md:521,545` — two locations in template text that the init skill writes into target projects; both contain the same `(next-id, list, show, sequence, impact-effort, refine-status)` string; add `path` at both locations

## Labels

`feat`, `cli`, `ll-issues`, `scripting`, `captured`

## Status

**Open** | Created: 2026-04-09 | Priority: P3

## Resolution

Implemented `ll-issues path` sub-command with alias `p` that resolves issue IDs (numeric, `TYPE-NNN`, `P-TYPE-NNN`) to relative file paths. Searches active, completed, and deferred directories. Supports `--json` flag for programmatic use. Exits 0 on match, 1 if not found.

**Changes:**
- New: `scripts/little_loops/cli/issues/path_cmd.py` — `cmd_path()` implementation
- Modified: `scripts/little_loops/cli/issues/__init__.py` — import, sub-parser, dispatch
- New: `scripts/tests/test_issues_path.py` — 11 tests covering all formats, not-found, --json, alias, completed/deferred search
- Updated: `docs/reference/CLI.md`, `README.md`, `commands/help.md`, `skills/init/SKILL.md`

## Session Log
- `/ll:ready-issue` - 2026-04-10T21:58:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f73f697-01a3-4f97-9a2f-75a37b51d4b5.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0229f88b-b9ac-496f-9859-b598848e3e06.jsonl`
- `/ll:wire-issue` - 2026-04-10T20:52:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3dd38e6d-dc64-4ee8-9c1d-97ee8b581541.jsonl`
- `/ll:refine-issue` - 2026-04-10T20:37:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd0b0fa9-7a50-4db0-881c-16e641733287.jsonl`
- `/ll:capture-issue` - 2026-04-09T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:manage-issue` - 2026-04-10T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
