---
discovered_date: 2026-03-24
discovered_by: /ll:capture-issue
confidence_score: 100
outcome_confidence: 100
---

# ENH-884: Add `next-issues` subcommand to `ll-issues`

## Summary

`ll-issues next-issue` (alias `nx`) returns only the single highest-ranked active issue. A list variant — `next-issues` (alias `nxs`) — is needed to return the full ranked queue, using the same three-tier sort: `-(outcome_confidence or -1)`, `-(confidence_score or -1)`, `priority_int`. Supports `--json`, `--path`, and an optional positional count argument.

## Current Behavior

Only `next-issue` / `nx` exists, returning a single issue. There is no way to get the full ranked list of active issues from the CLI without piping through additional tooling.

## Expected Behavior

`ll-issues next-issues` prints all active issues in ranked order, one ID per line. Flags:
- `--json`: output JSON array with `id`, `path`, `outcome_confidence`, `confidence_score`, `priority` per item
- `--path`: output one file path per line
- `N` (optional positional int): cap results at N items

Exit codes: `0` = at least one issue found, `1` = no active issues.

```
ll-issues next-issues
ll-issues next-issues 5
ll-issues next-issues --json
ll-issues nxs --path
```

## Motivation

Automation loops and scripts that need to process multiple issues in priority order currently have no clean CLI entry point. They must call `next-issue` repeatedly (bumping state between calls) or re-implement the sort externally. A `next-issues` command closes this gap and makes the ranked queue a first-class CLI primitive.

## Scope Boundaries

- Only adds `next-issues` / `nxs`; does not modify `next-issue` / `nx`
- Does not change the ranking algorithm; reuses the existing sort key from `next_issue.py`
- Does not add persistent state, caching, or filtering beyond `count`, `--json`, and `--path`
- No changes to `find_issues`, output helpers, or shared utilities

## Proposed Solution

Mirror `next_issue.py` in a new `next_issues.py` module. Sort all active issues by the same three-tier key, slice with `count`, then output via the requested format flag.

```python
def cmd_next_issues(config: BRConfig, args: argparse.Namespace) -> int:
    issues = find_issues(config)
    if not issues:
        return 1

    issues.sort(key=lambda i: (
        -(i.outcome_confidence if i.outcome_confidence is not None else -1),
        -(i.confidence_score if i.confidence_score is not None else -1),
        i.priority_int,
    ))

    count = getattr(args, "count", None)
    ranked = issues[:count] if count else issues

    if getattr(args, "json", False):
        print_json([{"id": i.issue_id, "path": str(i.path),
                     "outcome_confidence": i.outcome_confidence,
                     "confidence_score": i.confidence_score,
                     "priority": i.priority} for i in ranked])
        return 0

    if getattr(args, "path", False):
        for i in ranked:
            print(str(i.path))
        return 0

    for i in ranked:
        print(i.issue_id)
    return 0
```

Register in `scripts/little_loops/cli/issues/__init__.py` with alias `nxs`, `--json`, `--path` flags, optional positional `count` (`nargs="?", type=int`), and epilog examples.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/next_issues.py` — **create** (command implementation)
- `scripts/little_loops/cli/issues/__init__.py` — add import, subparser `next-issues` / `nxs`, dispatch, epilog entry

### Dependent Files (Callers/Importers)
- Any automation loop or script that currently calls `next-issue` in a loop to iterate all issues

### Similar Patterns
- `scripts/little_loops/cli/issues/next_issue.py` — mirror this; reuse `find_issues`, sort logic, output helpers

### Tests
- `scripts/tests/test_next_issues.py` — **create** (reuse `_make_issue` / `_setup_dirs` / `_write_config` helpers from `test_next_issue.py`)

### Documentation
- Epilog in `__init__.py` for inline help; no separate doc update needed

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/output.py:97` — `print_json(data: Any)` calls `json.dumps(data, indent=2)`; accepts both `dict` and `list`, so `print_json([...])` works without modification
- `scripts/little_loops/cli/issues/__init__.py:324-332` — exact registration pattern for `next-issue` / `nx` alias: `subs.add_parser("next-issue", aliases=["nx"])`, then `nx.set_defaults(command="next-issue")`, then dispatch via `if args.command == "next-issue":`; follow the same pattern for `"next-issues"` / `"nxs"`
- `scripts/little_loops/cli/issues/__init__.py:367-368` — dispatch block location: add `if args.command == "next-issues": return cmd_next_issues(config, args)` immediately after the `next-issue` dispatch block
- `scripts/little_loops/cli/issues/__init__.py:130-134` — `nargs="?"` positional precedent: `search` uses `query: nargs="?", default=None` without `type`; for `count`, `type=int` **must** be specified or argparse passes a string
- `scripts/tests/test_next_issue.py:231-263` — `test_json_flag_output_shape` asserts `json.loads(out)` is a dict; for `next-issues`, assert `isinstance(data, list)` and check `data[0]["id"]`, `data[0]["path"]`, `data[0]["outcome_confidence"]`, `data[0]["confidence_score"]`, `data[0]["priority"]`

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/next_issues.py` with `cmd_next_issues`
2. Register in `__init__.py`: import, subparser (`next-issues` + alias `nxs`), flags (`--json`, `--path`), positional `count` (`nargs="?"`), dispatch, epilog
3. Create `scripts/tests/test_next_issues.py` with 7 test cases:
   - `test_returns_all_issues_in_ranked_order`
   - `test_count_caps_results`
   - `test_default_output_is_ids_one_per_line`
   - `test_json_flag_returns_array`
   - `test_path_flag_returns_paths`
   - `test_empty_exits_1`
   - `test_nxs_alias_works`
4. Run `python -m pytest scripts/tests/test_next_issues.py -v` and smoke-test the CLI

## Impact

- **Priority**: P3 - Useful automation primitive; not blocking anything currently
- **Effort**: Small - mirrors existing `next_issue.py` with minor list-handling additions
- **Risk**: Low - additive only, no changes to existing commands
- **Breaking Change**: No

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| `docs/reference/API.md` | Python module reference | `find_issues`, output helpers |
| `.claude/CLAUDE.md` | CLI tools overview | `ll-issues` command context |

## Labels

`enhancement`, `cli`, `ll-issues`, `captured`

## Resolution

**Completed** | 2026-03-24

### Changes Made
- Created `scripts/little_loops/cli/issues/next_issues.py` with `cmd_next_issues` — mirrors `next_issue.py`, sorts all active issues by the three-tier key, slices by optional count, outputs via `--json` (array), `--path`, or default ID-per-line
- Updated `scripts/little_loops/cli/issues/__init__.py` — added import, subparser registration (`next-issues` + alias `nxs`), `count` positional (`nargs="?"`, `type=int`), `--json` and `--path` flags, epilog entries, and dispatch block
- Created `scripts/tests/test_next_issues.py` — 7 tests covering ranked order, count cap, default/JSON/path output, empty exit code, and `nxs` alias

### Verification
- All 7 tests pass (`python -m pytest scripts/tests/test_next_issues.py -v`)
- Lint and type check clean (`ruff check`, `mypy`)

## Status

**Completed** | Created: 2026-03-24 | Priority: P3

---

## Session Log
- `hook:posttooluse-git-mv` - 2026-03-25T04:03:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/805fc52b-7d2c-47cc-a3b7-8544d617c513.jsonl`
- `/ll:manage-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:ready-issue` - 2026-03-25T03:59:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9eae0db-b8f9-4875-b665-76cf8683dd1b.jsonl`
- `/ll:refine-issue` - 2026-03-25T02:34:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf417607-090b-45cf-9a30-9183f02b6bda.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/260efed5-c346-4a55-ab79-a03e97451fe4.jsonl`
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6397182f-baef-4093-8056-e07b0b54b84b.jsonl`
