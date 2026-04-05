---
id: FEAT-955
discovered_date: 2026-04-05
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 90
---

# FEAT-955: Add `ll-issues skip` subcommand to deprioritize issues that fail refinement

## Summary

Loop configs that use a `skip_issue` state to handle refinement failures currently have no standard way to lower an issue's priority so `ll-issues next-issue` returns a different issue next time. Without this, any `skip_issue → get_next_issue` cycle will fetch the same issue again forever. Add an `ll-issues skip <ID>` subcommand that permanently deprioritizes an issue (e.g. bumps it to P5) and records the skip in the issue file, giving loop authors a reliable primitive for skip semantics.

## Current Behavior

`ll-issues` has no `skip` subcommand. When FSM loops encounter refinement failures and call `ll-issues next-issue` on the next iteration, the same highest-priority issue is returned again (its priority is unchanged), causing the loop to cycle indefinitely on stuck issues. Loop authors must write ad-hoc inline shell snippets to manually rename issue files — there is no standard primitive, no audit trail, and no consistent interface for skip semantics.

## Expected Behavior

`ll-issues skip <ISSUE_ID>` atomically deprioritizes an issue:
- Renames the issue file to use the new priority prefix (default P5, or `--priority` override)
- Appends a `## Skip Log` entry with ISO timestamp and optional `--reason` text
- Prints the new file path to stdout

After a skip, `ll-issues next-issue` returns a different issue (the next highest-priority non-skipped issue), breaking the infinite-loop cycle.

## Use Case

A user's `auto-issue-processor` loop calls `refine-to-ready-issue` for each issue. When refinement fails, `skip_issue` echoes a message and calls `get_next_issue` — but `ll-issues next-issue` returns the same top-ranked issue again, creating an infinite loop. With `ll-issues skip FEAT-013`, the loop can atomically lower priority and move on:

```yaml
skip_issue:
  action: "ll-issues skip ${captured.input.output}"
  action_type: shell
  next: get_next_issue
```

## Acceptance Criteria

- [ ] `ll-issues skip <ID>` renames the issue file with updated priority prefix (default P5)
- [ ] `ll-issues skip <ID> --priority P4` accepts an optional priority override (P0–P5)
- [ ] `ll-issues skip <ID> --reason "text"` appends the reason to the Skip Log entry
- [ ] A `## Skip Log` section is appended with ISO timestamp and reason
- [ ] New file path is printed to stdout on success
- [ ] Skipped issue no longer ranks first in `ll-issues next-issue` output
- [ ] Non-existent or ambiguous issue ID produces a clear error message with exit code 1
- [ ] Rename is atomic (`Path.rename`)

## Motivation

`skip_issue` patterns in FSM loops are currently implementation-defined ad-hoc shell snippets. Without a standard skip primitive, loops silently cycle on stuck issues and users have no audit trail of which issues were skipped. A first-class `ll-issues skip` command gives loop authors a safe, consistent, auditable way to defer stuck issues.

## Proposed Solution

Add `skip` subcommand to `ll-issues` CLI:

```
ll-issues skip <ISSUE_ID> [--priority P5] [--reason "text"]
```

Behavior:
1. Locate the issue file by ID (all active categories)
2. Rename the file to bump its priority prefix to `--priority` (default P5)
3. Append a `## Skip Log` section with timestamp and optional reason
4. Print the new file path to stdout (so callers can confirm)

The rename preserves the full filename slug and issue number; only the `P[0-5]` prefix changes.

## API/Interface

```
ll-issues skip FEAT-013
# → Deprioritized FEAT-013 to P5: .issues/features/P5-FEAT-013-my-feature.md

ll-issues skip BUG-042 --priority P4 --reason "flaky test env, retry after CI fix"
# → Deprioritized BUG-042 to P4: .issues/bugs/P4-BUG-042-my-bug.md
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — register `skip` subparser and dispatch handler
- `scripts/little_loops/cli/issues/skip.py` — new file implementing `cmd_skip` (follows pattern of `next_id.py`, `append_log.py`)
- `scripts/little_loops/issue_manager.py` — implement rename + append logic

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — could use in `skip_issue`-equivalent states
- Any project-level loop YAML with `skip_issue` states
- `ll-issues next-issue` — benefits from lower priority keeping skipped issues out of rotation

### Similar Patterns
- `scripts/little_loops/cli/issues/next_id.py` — ID lookup pattern
- `scripts/little_loops/cli/issues/append_log.py` — append-to-issue-file pattern

### Tests
- `scripts/tests/test_issues_cli.py` — add `skip` subcommand tests
- Test that `skip` renames file correctly with updated priority prefix
- Test that `skip` appends `## Skip Log` section
- Test that skipped issue no longer ranks first in `next-issue` output

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Corrected / Additional Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — add `skip_issue()` function after `defer_issue()` (lines 715–800); this is where all rename/move logic lives (`_move_issue_to_completed`, `defer_issue`, `undefer_issue`). The issue's reference to `issue_manager.py` as home for rename logic is likely incorrect — verify before implementing.
- `scripts/little_loops/cli_args.py` — `VALID_PRIORITIES = frozenset({"P0","P1","P2","P3","P4","P5"})` at line 268; pass as `choices=list(VALID_PRIORITIES)` to `--priority` argparse argument rather than hardcoding.

#### Additional Dependent Files
- `scripts/little_loops/loops/issue-refinement.yaml` — uses `ll-issues next-action --skip` pattern; most relevant loop for `ll-issues skip` integration
- `scripts/little_loops/loops/lib/cli.yaml` — `ll_issues_next_issue` FSM fragment definition

#### Additional Similar Patterns (with concrete references)
- `scripts/little_loops/cli/issues/show.py:17–83` — `_resolve_issue_id()`: canonical single-issue lookup supporting "955", "FEAT-955", and "P4-FEAT-955" input formats via regex cascade + `glob(f"*-{numeric_id}-*.md")` across all active + completed + deferred dirs. Reuse or replicate instead of writing new ID-lookup logic.
- `scripts/little_loops/issue_lifecycle.py:715–724` — `_build_deferred_section(reason)`: section builder for `## Deferred` block; model the `## Skip Log` section builder after this pattern using `datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")`.
- `scripts/little_loops/issue_lifecycle.py:251` — `_is_git_tracked(path)`: determines git-tracked status before choosing `git mv` vs `Path.rename`; call this to decide rename strategy (matches pattern used in `_move_issue_to_completed`).
- `scripts/little_loops/issue_parser.py:29` — `_NORMALIZED_RE = r"^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$"`: use for post-rename filename validation.
- Filename rename one-liner: `new_name = re.sub(r"^P\d-", f"{new_priority}-", path.name)` — derived from `show.py:103–104` `re.match(r"^(P\d)-", filename)` pattern; no dedicated rename utility exists.

#### Additional Tests
- `scripts/tests/test_issues_cli.py:1793–1881` — `TestIssuesAppendLog`: the closest existing test class in structure; follow its two-test pattern (happy path + error case) and `sys.argv` patching approach.
- `scripts/tests/test_issue_lifecycle.py` — has `mock_run` helper for simulating `git mv`; reuse for testing skip in a git-tracked repo.
- `scripts/tests/conftest.py:56–157` — `issues_dir` fixture creates 5 issues (P0-BUG-001, P1-BUG-002, P2-BUG-003, P1-FEAT-001, P2-FEAT-002); a P0 issue already exists for testing that skip makes it no longer rank first.

## Implementation Steps

1. Add `skip` subparser to `ll-issues` CLI with `issue_id`, `--priority`, `--reason` args
2. Implement file search by ID across all active category dirs
3. Rename file with new priority prefix (atomic `Path.rename`)
4. Append `## Skip Log` section with ISO timestamp and reason
5. Print new path to stdout
6. Update docs / `ll:help` output to include `skip`

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references:_

1. **Register subparser** in `scripts/little_loops/cli/issues/__init__.py` (after the last `subs.add_parser` block, ~line 372): `skip = subs.add_parser("skip", help="Deprioritize an issue by renaming its priority prefix")` with `skip.add_argument("issue_id")`, `skip.add_argument("--priority", choices=list(VALID_PRIORITIES), default="P5")`, `skip.add_argument("--reason", default=None)`; import `VALID_PRIORITIES` from `cli_args`; add dispatch case at the bottom of the `if args.command ==` chain (~line 411): `if args.command == "skip": return cmd_skip(config, args)`.

2. **Create `scripts/little_loops/cli/issues/skip.py`**: implement `cmd_skip(config, args) -> int`; call `_resolve_issue_id(config, args.issue_id)` from `show.py:17` for lookup (supports "955", "FEAT-955", "P4-FEAT-955"); build new filename via `re.sub(r"^P\d-", f"{args.priority}-", path.name)`; call `skip_issue(path, new_path, args.reason)` from step 3; print new path; return 0 or 1.

3. **Add `skip_issue(original_path, new_path, reason)` to `scripts/little_loops/issue_lifecycle.py`** (after `defer_issue()` at line ~800): use `_is_git_tracked(original_path)` from line 251 to decide `git mv` vs `Path.rename`; append `## Skip Log` section following `_build_deferred_section()` template at lines 715–724 using `datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")`.

4. **Add tests** in `scripts/tests/test_issues_cli.py`: follow `TestIssuesAppendLog` pattern at lines 1793–1881; use `conftest.py:56–157` `issues_dir` fixture (P0-BUG-001 exists for ranking test); reuse `mock_run` from `test_issue_lifecycle.py` for git-mv simulation. Cover: rename succeeds, Skip Log appended, stdout shows new path, `next-issue` no longer returns skipped issue, not-found returns exit code 1.

5. **Verify** with `python -m pytest scripts/tests/test_issues_cli.py -v -k skip` and `python -m pytest scripts/tests/test_issue_lifecycle.py -v -k skip`.

## Impact

- **Priority**: P4 — nice-to-have quality-of-life; loops work around it with inline shell
- **Effort**: Small — single CLI subcommand, no external dependencies
- **Risk**: Low — purely additive; renames are reversible
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `ll-issues`, `cli`, `fsm`, `loops`, `captured`

## Status

**Open** | Created: 2026-04-05 | Priority: P4

---

## Session Log
- `/ll:confidence-check` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de47cb54-45bc-466b-8d8c-fb753e0644be.jsonl`
- `/ll:refine-issue` - 2026-04-05T22:01:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16b88510-7860-47a9-a9cb-a98b5afdb7ff.jsonl`
- `/ll:format-issue` - 2026-04-05T21:57:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f0d2451-be7b-4fa5-a4bd-e5b8aaaf1187.jsonl`

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3203fd4-ea84-4c13-b186-96678a2c9062.jsonl`
