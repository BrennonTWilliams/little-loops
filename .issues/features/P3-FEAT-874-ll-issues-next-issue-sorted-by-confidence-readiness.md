---
id: FEAT-874
title: "ll-issues next-issue command sorted by confidence and readiness"
type: FEAT
priority: P3
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
---

# FEAT-874: ll-issues next-issue command sorted by confidence and readiness

## Summary

Add a `next-issue` subcommand to `ll-issues` that returns the single issue ranked highest by outcome confidence score, then readiness score (confidence_score), then priority. This surfaces the "most implementation-ready" issue for autonomous tooling and loop orchestration.

## Current Behavior

`ll-issues next-action` finds issues by priority order and checks confidence/readiness as pass/fail thresholds to decide what refinement step is needed — it does not sort by scores.

There is no command that selects the issue most likely to succeed in implementation based on its confidence scores.

## Expected Behavior

`ll-issues next-issue` prints the issue ID (and optionally the full path) of the active issue ranked highest by:

1. **Outcome confidence score** (`outcome_confidence`) — highest first
2. **Readiness score** (`confidence_score`) — highest first
3. **Priority** (`priority_int`) — lowest int first (P0 > P1 > P2…)

Issues with no scores are ranked below all scored issues (treated as score = -1).

```
$ ll-issues next-issue
FEAT-874

$ ll-issues next-issue --json
{"id": "FEAT-874", "path": ".issues/features/P3-FEAT-874-...md", "outcome_confidence": 82, "confidence_score": 78, "priority": "P3"}

$ ll-issues next-issue --path
.issues/features/P3-FEAT-874-...md
```

## Motivation

`ll-loop` and `ll-auto` need a way to pick the next issue to implement that is most likely to succeed — not just the highest priority. Sorting by confidence scores first ensures the automation invests effort in issues that have been verified, scored, and refined to readiness rather than blindly tackling whatever is highest priority. This reduces failed implementation cycles.

## Use Case

A developer runs `ll-loop` with a `manage_issue` loop. The loop calls `ll-issues next-issue` to select the next issue. Because FEAT-874 has `outcome_confidence: 85, confidence_score: 88, P3` and BUG-820 has `outcome_confidence: 45, confidence_score: 50, P2`, `next-issue` returns FEAT-874 — the more implementation-ready issue despite its lower priority.

## Acceptance Criteria

- [ ] `ll-issues next-issue` prints a single issue ID to stdout
- [ ] Sort order: `outcome_confidence` desc → `confidence_score` desc → `priority_int` asc
- [ ] Issues missing both scores rank last (treated as score = -1 for both)
- [ ] `--json` flag outputs a JSON object with `id`, `path`, `outcome_confidence`, `confidence_score`, `priority`
- [ ] `--path` flag outputs only the file path (useful in shell pipelines)
- [ ] Exit 0 when an issue is found, exit 1 when no active issues exist
- [ ] Command is listed in `ll-issues --help` epilog and registered in `__init__.py`
- [ ] Alias `ni2` or `nx` for scripting convenience (optional)

## API/Interface

```python
# scripts/little_loops/cli/issues/next_issue.py

def cmd_next_issue(config: BRConfig, args: argparse.Namespace) -> int:
    """Print the highest-confidence active issue.

    Sort key: (-(outcome_confidence or -1), -(confidence_score or -1), priority_int)

    Returns:
        Exit code (0 = found, 1 = no issues)
    """
```

```
ll-issues next-issue [--json] [--path] [--config PATH]
```

## Proposed Solution

Sort active issues by `(-outcome_confidence, -confidence_score, priority_int)` using `-1` as the fallback for `None` scores. Print the top issue's ID. Reuse the existing `find_issues()` from `issue_parser` — no new parsing logic needed.

The `--json` flag can reuse the same JSON serialization pattern as `cmd_show`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register subparser + dispatch

### New Files
- `scripts/little_loops/cli/issues/next_issue.py` — command implementation

### Dependent Files (Callers/Importers)
- `ll-loop` FSM configs that call `ll-issues next-issue`
- Any shell scripts using `ll-issues next-issue --path`

### Similar Patterns
- `scripts/little_loops/cli/issues/next_id.py` — same minimal structure
- `scripts/little_loops/cli/issues/next_action.py` — same `find_issues` + sort pattern

### Tests
- `scripts/tests/test_issues_cli.py` — add `next-issue` test cases covering: scored issues, unscored issues (rank last), tie-breaking by priority, `--json`, `--path`, empty issue list (exit 1)

### Documentation
- `scripts/little_loops/cli/issues/__init__.py` epilog (inline)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`__init__.py` specific locations:**
- Subparser registration block: `__init__.py:68-309` — insert new `next-issue` subparser here, after `next-action` block (~line 309)
- Dispatch chain: `__init__.py:324-344` — add `elif args.command == "next-issue": return cmd_next_issue(config, args)` here
- Epilog (help text): `__init__.py:35-65` — add `next-issue` to the `Sub-commands:` and `Examples:` sections

**Required subparser setup calls (both mandatory):**
- `nx.set_defaults(command="next-issue")` — required for alias `nx` to resolve correctly
- `add_config_arg(nx)` from `little_loops.cli_args:35-42` — must be last call on every subparser

**Sort key reference** (`next_action.py:28`):
```python
issues.sort(key=lambda i: (i.priority_int, -int(i.issue_id.split("-")[1])))
```
For `next-issue`, the sort key is: `(-(oc or -1), -(cs or -1), i.priority_int)` — sorts descending by scores, ascending by priority int.

**`--json` pattern** (`show.py:379-381`):
```python
if getattr(args, "json", False):
    print_json(fields)  # from little_loops.cli.output:97-99
    return 0
```
Use `getattr(args, "json", False)` (defensive), `print_json` from `little_loops.cli.output`.

**`--path` flag convention note**: No existing `--path` flag exists in the issues CLI. The established pattern for path output is including `"path": str(issue.path)` in the `--json` dict. A `--path` plain-text flag is novel here — implement it by checking `getattr(args, "path", False)` and printing `str(issue.path)`, following the same pattern as `--json` short-circuits.

**`IssueInfo` fields** (`issue_parser.py:201-248`):
- `outcome_confidence: int | None` — frontmatter key `outcome_confidence`
- `confidence_score: int | None` — frontmatter key `confidence_score`
- `priority_int: int` — `@property` at line 241; parses `^P(\d+)$` from `self.priority`, returns 99 for unknown
- `issue_id: str`, `path: Path`

**Test patterns:**
- Primary reference: `scripts/tests/test_next_action.py:65-307` — dedicated test file for `next-action`; follow this structure (local `_make_issue` helper, `temp_project_dir`/`sample_config`/`capsys` fixtures, `patch.object(sys, "argv", [..., "--config", str(temp_project_dir)])`)
- Conftest fixtures: `temp_project_dir` (line 56), `sample_config` (line 66), `issues_dir` (line 125) — all available in `scripts/tests/conftest.py`
- Consider creating `scripts/tests/test_next_issue.py` as a dedicated file rather than adding to `test_issues_cli.py`

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/next_issue.py` with `cmd_next_issue(config, args)` using sort key `(-(oc or -1), -(cs or -1), i.priority_int)` on the result of `find_issues(config)`; import `print_json` from `little_loops.cli.output`
2. In `__init__.py:~309`, add subparser `next-issue` (alias `nx`); call `nx.set_defaults(command="next-issue")`, add `--json` / `--path` args, end with `add_config_arg(nx)`; update epilog at lines 35-65
3. In dispatch chain `__init__.py:324-344`, add `elif args.command == "next-issue": return cmd_next_issue(config, args)`
4. Create `scripts/tests/test_next_issue.py` following the structure in `test_next_action.py:65-307`; use `_make_issue` helper pattern; cover: scored issues (sort order), unscored rank last, tie-break by priority, `--json` output shape, `--path` output, empty issue dir (exit 1)
5. Verify with `ll-issues next-issue` on real issue set

## Impact

- **Priority**: P3 — useful for automation, not blocking
- **Effort**: Small — ~80 LOC including tests; reuses existing `find_issues` and CLI patterns exactly
- **Risk**: Low — read-only command, no state mutation
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `cli`, `ll-issues`, `automation`, `captured`

## Session Log
- `/ll:refine-issue` - 2026-03-24T18:16:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/134f1b03-a3a9-4307-be17-0dfb2df69a25.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/123be0f8-c950-4f44-830e-69b04d0e686c.jsonl`

---

**Open** | Created: 2026-03-24 | Priority: P3
