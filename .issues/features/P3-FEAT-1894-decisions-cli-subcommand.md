---
id: FEAT-1894
title: "Decisions Log — CLI Subcommand"
type: FEAT
priority: P3
parent: FEAT-1892
discovered_date: 2026-06-03
depends_on:
- FEAT-1891
decision_needed: false
---

# FEAT-1894: Decisions Log — CLI Subcommand

## Summary

Create the `ll-issues decisions` CLI subcommand with full CRUD sub-sub-commands (`list`, `add`, `generate` stub, `sync`, `outcome`), register it in `cli/issues/__init__.py`, write CLI tests, and update all documentation touchpoints. This is the foundational child of FEAT-1892 and must land before Children 2 and 3 can be worked.

## Parent Issue

Decomposed from FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Integration Map

### Files to Create
- `scripts/little_loops/cli/issues/decisions.py` — `add_decisions_parser(subs)` + `cmd_decisions(config, args)` following `epic_progress.py` dual-function pattern
- `scripts/tests/test_cli_decisions.py` — CLI tests using `patch.object(sys, "argv", ["ll-issues", "decisions", ...])` pattern from `test_issues_cli.py:TestIssuesCLINextId`

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — import `add_decisions_parser`/`cmd_decisions` in lines 21-46 block, call `add_decisions_parser(subs)` after line 674 (`add_epic_progress_parser` call), dispatch `if args.command == "decisions": return cmd_decisions(config, args)` before line 733 fallthrough
- `commands/help.md` — append `decisions` to `ll-issues` subcommand description in CLI TOOLS block
- `docs/reference/CLI.md` — add `#### ll-issues decisions` subsection documenting `list`, `add`, `generate`, `sync`, and `outcome` sub-sub-commands and their flags
- `CONTRIBUTING.md` — add `cli/issues/decisions.py` to the `cli/issues/` directory tree listing
- `.claude/CLAUDE.md` — append `decisions` to `ll-issues` subcommand parenthetical on line 177 (currently ends at `epic-progress`); parallel update to `commands/help.md`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` — two occurrences (lines 406 and 442) of the `ll-issues` subcommand parenthetical are missing both `epic-progress` and `decisions`; both must be updated
- `scripts/little_loops/cli/issues/__init__.py` epilog string (lines 53–121) — human-readable help text shown by `ll-issues --help` enumerates all subcommands; `decisions` must be appended here (separate from the parser/dispatch registration already in the issue)
- `commands/help.md` — also missing `epic-progress` in addition to `decisions`; both must be added to the `ll-issues` CLI TOOLS line

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_decisions.py` — new test file (already in Files to Create); follow `TestIssuesCLIEpicProgress` pattern; import `main_issues` **inside** the `with patch.object` block each time
- `scripts/tests/test_feat1894_doc_wiring.py` — new doc-wiring test file following `test_enh1888_doc_wiring.py` / `test_feat1287_doc_wiring.py` pattern; assert that `commands/help.md`, `docs/reference/CLI.md`, `CONTRIBUTING.md`, and `.claude/CLAUDE.md` all reference the `decisions` subcommand
- `scripts/tests/test_decisions.py` — run for regression check only; no modifications needed (tests data layer, not CLI)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_issues`; no change needed but confirms `decisions` routing via existing entry point
- `scripts/tests/conftest.py` — provides `temp_project_dir` fixture that `decisions_path` chains to; `sample_rule`/`sample_decision`/`sample_exception` fixtures currently live only in `test_decisions.py` and cannot be cross-imported by pytest — must be duplicated in `test_cli_decisions.py` or moved to `conftest.py`

### Similar Patterns (Key Anchors)
- `scripts/little_loops/cli/issues/epic_progress.py:add_epic_progress_parser()` — externalized parser factory model; exact template for `decisions` due to sub-sub-command complexity
- `scripts/little_loops/cli/issues/anchor_sweep.py:cmd_anchor_sweep()` — error-on-missing-path and `sys.stderr` + `return 1` pattern
- `scripts/tests/test_issues_cli.py:TestIssuesCLIEpicProgress` (line 4467) — closest structural match since `epic_progress` uses the same externalized two-function parser pattern

### CRUD Layer (from FEAT-1891)
- `load_decisions(path: Path | None = None) -> list[AnyEntry]` — returns `[]` if file absent
- `add_entry(entry: AnyEntry, path: Path | None = None) -> None` — loads, appends, saves via `atomic_write`
- `list_entries(path: Path | None = None, *, type: str | None = None, category: str | None = None, label: str | None = None) -> list[AnyEntry]` — keyword-only filters; `--no-outcome`, `--before`, `--scope` require additional post-filter in CLI handler (see type-field matrix below)
- `set_outcome(entry_id: str, result: str, measured_at: str, notes: str | None = None, path: Path | None = None, *, force: bool = False) -> None` — raises `KeyError` (not found), `TypeError` (entry is not `DecisionEntry`), `ValueError` (outcome exists without `--force`)
- `resolve_active(entries: list[AnyEntry]) -> list[AnyEntry]` — returns filtered list of entries whose `id` is NOT referenced by any other entry's `supersedes` field; **returns `list[AnyEntry]`, not a set of IDs**
- `AnyEntry = RuleEntry | DecisionEntry | ExceptionEntry` (union alias at `decisions.py:193`)
- Import path: `from little_loops.decisions import load_decisions, add_entry, list_entries, set_outcome, resolve_active`

#### Config Path Resolution
Derive `path` for all CRUD calls from config: `Path(config.project_root) / config.decisions.log_path`
(or pass `None` to let `_resolve_path` default to `Path.cwd() / ".ll/decisions.yaml"`).
`config.decisions.log_path` is `DecisionsConfig.log_path` at `scripts/little_loops/config/features.py:413`, defaults to `".ll/decisions.yaml"`.

#### CLI Post-Filter Matrix for `list`
| Flag | Field | Applies to |
|------|-------|-----------|
| `--no-outcome` | `entry.outcome is None` | `DecisionEntry` only (others never have outcome) |
| `--before <ISO-8601>` | `entry.timestamp < args.before` | All types |
| `--scope <scope>` | `entry.scope == args.scope` | `DecisionEntry` only (`RuleEntry`/`ExceptionEntry` have no `scope` field) |

## Proposed Solution

### Parser Architecture Note

`epic_progress.py` is a **leaf** subcommand — it has no sub-sub-commands and does NOT call `add_subparsers()`. The `decisions` subcommand must use a **two-level** structure. Inside `add_decisions_parser(subs)`:

```python
p = subs.add_parser("decisions", help="Manage rules and decisions log")
p.set_defaults(command="decisions")          # required — drives dispatch in __init__.py
subsubs = p.add_subparsers(dest="subcommand")
list_p = subsubs.add_parser("list", ...)
add_p  = subsubs.add_parser("add", ...)
# etc.
```

Inside `cmd_decisions(config, args)`, handle missing sub-sub-command:
```python
if not getattr(args, "subcommand", None):
    p.print_help()   # p must be captured from add_decisions_parser or looked up
    return 1
```
Since `p` is returned from `add_decisions_parser`, store a module-level reference or use `parser.parse_known_args` to avoid needing it — simplest: add `p.set_defaults(_decisions_parser=p)` so `args._decisions_parser` is accessible in `cmd_decisions`.

### CLI Subcommand

Create `scripts/little_loops/cli/issues/decisions.py` with two functions following `epic_progress.py` pattern:

```python
def add_decisions_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register 'decisions' parser and all sub-sub-command parsers."""
    ...

def cmd_decisions(config: BRConfig, args: argparse.Namespace) -> int:
    """Dispatch on args.subcommand; returns 0/1."""
    ...
```

Supported sub-sub-commands:
- `list [--type=rule|decision|exception] [--category=...] [--label=...] [--no-outcome] [--before=<date>] [--scope=<scope>]`
- `add --type=... --category=... --rule="..." --rationale="..." [--issue=...] [--enforcement=required|advisory] [--rule-ref=...] [--alternatives-rejected="..."] [--supersedes=...]`
- `generate --from=completed` (stub; full implementation in FEAT-1893)
- `sync` (writes `## Active Rules` to `.ll/ll.local.md` — calls `sync_to_local_md` from FEAT-1895)
- `outcome <ID> --result=worked|did_not_work|mixed|reversed [--notes="..."] [--measured-at=<ISO-8601>] [--force]`

**Registration in `cli/issues/__init__.py`** (3-step):
1. Add inside `main_issues()` function body (all imports are deferred inside `with cli_event_context(...)` block, NOT at module level — lines 21–46 are inside `main_issues()`):
   ```python
   from little_loops.cli.issues.decisions import (
       add_decisions_parser,
       cmd_decisions,
   )
   ```
2. Call `add_decisions_parser(subs)` after the existing `add_epic_progress_parser(subs)` call at line 674
3. Add dispatch before the `return 1` fallthrough at line 733:
   ```python
   if args.command == "decisions":
       return cmd_decisions(config, args)
   ```

**Error Handling Convention**: Follow `cmd_anchor_sweep` — fatal errors use `print(..., file=sys.stderr); return 1`. Warnings that don't halt execution use `print(..., file=sys.stderr)` and continue. Note `cmd_epic_progress` uses `print(...)` (stdout) — **use stderr for errors in `cmd_decisions`** for consistency with the newer pattern.

**`add` sub-sub-command field–type matrix** (not all flags apply to all types):
| Flag | `RuleEntry` | `DecisionEntry` | `ExceptionEntry` |
|------|-------------|----------------|-----------------|
| `--rule` | ✓ rule text | ✓ decision text | ✗ |
| `--rule-ref` | ✗ | ✗ | ✓ `rule_ref` |
| `--enforcement` | ✓ | ✗ | ✗ |
| `--alternatives-rejected` | ✗ | ✓ | ✓ |
| `--supersedes` | ✓ | ✗ | ✗ |
| `--scope` | ✗ | ✓ (default `"issue"`) | ✗ |

Validate type-specific required fields in the `add` handler and `print(f"Error: --rule is required for type 'rule'", file=sys.stderr); return 1`.

**`sync` subcommand stub handling**: `sync_to_local_md` comes from FEAT-1895 (not yet merged). Guard with a try-import and stub the behavior:
```python
try:
    from little_loops.decisions_sync import sync_to_local_md
    sync_to_local_md(path=path)
except ImportError:
    print("sync not yet available (requires FEAT-1895)", file=sys.stderr)
    return 1
```

### Docs/Wiring (Step 14, 17, 18, 21)

- `commands/help.md` — append `decisions` to `ll-issues` line
- `docs/reference/CLI.md` — add `#### ll-issues decisions` subsection with all sub-sub-commands and flags
- `CONTRIBUTING.md` — add `cli/issues/decisions.py` to `cli/issues/` directory tree
- `.claude/CLAUDE.md` line 177 — append `decisions` after `epic-progress`

### Tests

`scripts/tests/test_cli_decisions.py` — follow `TestIssuesCLIEpicProgress` structure (`test_issues_cli.py:4467`):
- Reuse fixtures from `test_decisions.py`: `decisions_path`, `sample_rule`, `sample_decision`, `sample_exception`
  - `decisions_path` returns a `Path` only — **file is not created**; call `save_decisions([...], decisions_path)` in each test that needs populated data
  - `decisions_path` depends on `temp_project_dir` (from `conftest.py`) — include in test signature
- Cover: `list`, `add`, `outcome` subcommands via `patch.object(sys, "argv", [...])`; import `main_issues` **inside** the `with` block
- Cover graceful degradation when `decisions.yaml` absent (`list` returns empty, `outcome` errors cleanly)
- Cover `sync` dispatch (assert `return 1` when FEAT-1895 not available)
- Check `result == 0` and `capsys.readouterr().out` for success cases; check `result == 1` and `.err` for error cases
- No `patch()` calls on underlying functions — route through real `main_issues()` only

## Implementation Steps

1. **Create `scripts/little_loops/cli/issues/decisions.py`**: Copy `epic_progress.py` as scaffold; replace body with two-level subparser structure. Implement `add_decisions_parser(subs)` with `p.add_subparsers(dest="subcommand")` and all five sub-sub-parsers. Implement `cmd_decisions(config, args)` dispatching on `args.subcommand`; handle missing subcommand via `args._decisions_parser.print_help(); return 1`.

2. **Implement `list` handler**: Call `list_entries(path=path, type=..., category=..., label=...)` then post-filter for `--no-outcome`, `--before`, `--scope` using the field-type matrix above. Print as text (one entry per line) or JSON (`--format json`). Call `resolve_active(entries)` to mark superseded entries.

3. **Implement `add` handler**: Validate type-specific required fields, construct the appropriate dataclass (`RuleEntry`, `DecisionEntry`, or `ExceptionEntry`) with `id` from `--id` arg (or generate from `--category` + auto-increment via `list_entries` count), call `add_entry(entry, path=path)`. Print confirmation to stdout.

4. **Implement `outcome` handler**: Parse `--result`, `--measured-at` (default to current timestamp if absent), `--notes`, `--force`. Call `set_outcome(args.id, args.result, measured_at, notes=args.notes, path=path, force=args.force)`. Catch `KeyError`/`TypeError`/`ValueError` and print to stderr with `return 1`.

5. **Implement `generate` stub**: Print `"generate: not yet implemented (see FEAT-1893)"` and `return 0`.

6. **Implement `sync` handler**: Use try-import guard for `sync_to_local_md` (see stub pattern above).

7. **Register in `scripts/little_loops/cli/issues/__init__.py`**: Add import block after `add_epic_progress_parser` import (line ~29). Add `add_decisions_parser(subs)` after line 674. Add dispatch block before line 733.

8. **Update `commands/help.md`**: Append `decisions` to the `ll-issues` subcommand list.

9. **Update `docs/reference/CLI.md`**: Add `#### ll-issues decisions` subsection with all sub-sub-commands and their flags.

10. **Update `CONTRIBUTING.md`**: Add `cli/issues/decisions.py` to the `cli/issues/` directory tree.

11. **Update `.claude/CLAUDE.md` line ~177**: Append `, decisions` after `epic-progress` in the `ll-issues` parenthetical.

12. **Write `scripts/tests/test_cli_decisions.py`**: Follow `TestIssuesCLIEpicProgress` class structure (`test_issues_cli.py:4467`). Import `decisions_path`, `sample_rule`, `sample_decision`, `sample_exception` fixtures from `test_decisions.py` (they are `@pytest.fixture` functions — import or move to `conftest.py` if needed). Use `patch.object(sys, "argv", ["ll-issues", "decisions", ...])` pattern only; do not patch underlying functions.

13. **Run tests**: `python -m pytest scripts/tests/test_cli_decisions.py -v` and `python -m pytest scripts/tests/test_decisions.py -v` (ensure no regressions).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

14. **Update `__init__.py` epilog string** — inside `main_issues()`, find the `epilog="""..."""` block (lines 53–121) that lists all subcommands in human-readable help text; append `decisions` so `ll-issues --help` shows the new subcommand.

15. **Resolve pytest fixture strategy** — `decisions_path`, `sample_rule`, `sample_decision`, `sample_exception` fixtures are defined locally in `test_decisions.py` and cannot be cross-imported by pytest; either duplicate them in `test_cli_decisions.py` (simpler, consistent with peer pattern like `test_set_status_cli.py`) or move them to `conftest.py` (preferred if multiple test files need them). Check whether `test_decisions.py` already uses `temp_project_dir` from conftest — if so, moving the four fixtures to conftest avoids duplication.

16. **Write `scripts/tests/test_feat1894_doc_wiring.py`** — follow `test_enh1888_doc_wiring.py` pattern; assert that `commands/help.md`, `docs/reference/CLI.md`, `CONTRIBUTING.md`, and `.claude/CLAUDE.md` all reference `decisions` in the appropriate `ll-issues` context.

17. **Update `skills/init/SKILL.md`** — two occurrences of the `ll-issues` subcommand parenthetical (lines 406 and 442) are missing both `epic-progress` and `decisions`; update both lines to include the full current subcommand list.

## Acceptance Criteria

- [ ] `cmd_decisions(config, args)` created at `scripts/little_loops/cli/issues/decisions.py`
- [ ] `decisions` subparser registered after `add_epic_progress_parser` call in `cli/issues/__init__.py`
- [ ] Dispatch entry added to `main_issues()` chain (before line 733 fallthrough)
- [ ] `list` supports `--type`, `--category`, `--label`, `--no-outcome`, `--before`, `--scope` flags
- [ ] `add` supports all relevant flags for all three entry types
- [ ] `outcome <ID>` subcommand populates outcome; refuses overwrite without `--force`
- [ ] `generate` stub present (full impl deferred to FEAT-1893)
- [ ] `sync` dispatches to `sync_to_local_md` (from FEAT-1895)
- [ ] `commands/help.md` documents `decisions` under `ll-issues`
- [ ] `docs/reference/CLI.md` has `#### ll-issues decisions` subsection
- [ ] `CONTRIBUTING.md` lists `cli/issues/decisions.py`
- [ ] `.claude/CLAUDE.md` updated with `decisions` in `ll-issues` list
- [ ] `test_cli_decisions.py` covers CRUD ops and graceful degradation

## Session Log
- `/ll:wire-issue` - 2026-06-03T05:57:25 - `668e8525-fcbc-4360-adf2-fac62db1d711.jsonl`
- `/ll:refine-issue` - 2026-06-03T05:50:07 - `ad858343-d927-433c-91f1-6ab9312aef3b.jsonl`
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
