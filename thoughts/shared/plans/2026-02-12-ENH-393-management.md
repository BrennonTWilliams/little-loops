# ENH-393: Add `ll-sprint edit` CLI subcommand - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-393-sprint-review-edit-command.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

The `ll-sprint` CLI (`scripts/little_loops/cli/sprint.py`) has 5 subcommands: `create`, `run`, `list`, `show`, `delete`. They all follow the same pattern: register via `subparsers.add_parser()`, dispatch in `main_sprint()`, delegate to `_cmd_sprint_*()` functions.

### Key Discoveries
- `SprintManager.validate_issues()` at `sprint.py:307-329` validates issue IDs against the 3 active category dirs but does NOT check the completed dir
- `SprintManager.load()` at `sprint.py:268-277` returns `Sprint | None`
- `Sprint.save()` at `sprint.py:169-182` performs a full YAML overwrite
- `parse_issue_ids()` at `cli_args.py:151-168` parses comma-separated IDs to `set[str]`
- `_render_dependency_analysis()` at `cli/sprint.py:491-530` renders dep analysis output
- `_build_issue_contents()` at `cli/sprint.py:486-488` builds content map for dep analysis
- `config.get_completed_dir()` at `config.py:484-486` returns the completed issues path
- The `edit` subcommand needs project root (like `create`, `show`, `run`) to validate issues

## Desired End State

A new `ll-sprint edit` subcommand supporting:
- `--add IDS` — add issue IDs to an existing sprint (validates they exist)
- `--remove IDS` — remove issue IDs from a sprint
- `--prune` — automatically remove invalid (missing file) and completed issue references
- `--revalidate` — re-run dependency analysis and report warnings after edits

### How to Verify
- `ll-sprint edit sprint-1 --add BUG-045` adds BUG-045 to the sprint YAML
- `ll-sprint edit sprint-1 --remove BUG-001` removes BUG-001 from the sprint
- `ll-sprint edit sprint-1 --prune` removes issues whose files are missing or in completed/
- `ll-sprint edit sprint-1 --revalidate` runs dependency analysis on the (possibly edited) sprint
- Flags can be combined: `--add X --remove Y --prune --revalidate`

## What We're NOT Doing

- Not adding AI-guided sprint review (ENH-394)
- Not changing sprint execution logic
- Not adding sprint history/versioning
- Not modifying `SprintManager` class — all logic goes in the CLI handler

## Solution Approach

Add an `edit` subparser to `main_sprint()` and a `_cmd_sprint_edit()` handler. The handler loads the sprint, applies mutations in order (add → remove → prune), saves if changed, and optionally runs revalidation. This is a thin CLI layer over existing `SprintManager` methods.

## Code Reuse & Integration

- **Reuse as-is**: `parse_issue_ids()` for `--add`/`--remove` parsing
- **Reuse as-is**: `SprintManager.validate_issues()` for validating added IDs and detecting invalid refs
- **Reuse as-is**: `SprintManager.load()` and `Sprint.save()` for load/mutate/save cycle
- **Reuse as-is**: `_render_dependency_analysis()`, `_build_issue_contents()`, `SprintManager.load_issue_infos()` for `--revalidate`
- **Reuse as-is**: `config.get_completed_dir()` for `--prune` completed detection
- **New code justification**: Only `_cmd_sprint_edit()` function — the actual mutation logic and CLI glue

## Implementation Phases

### Phase 1: Register `edit` subparser and implement `_cmd_sprint_edit()`

#### Overview
Add the `edit` subcommand to `main_sprint()` and implement the handler function.

#### Changes Required

**File**: `scripts/little_loops/cli/sprint.py`

1. **Add `edit` subparser** between the `show` and `delete` subparsers (after line 118):

```python
# edit subcommand
edit_parser = subparsers.add_parser("edit", help="Edit a sprint's issue list")
edit_parser.add_argument("sprint", help="Sprint name to edit")
edit_parser.add_argument(
    "--add",
    default=None,
    help="Comma-separated issue IDs to add (e.g., BUG-045,ENH-050)",
)
edit_parser.add_argument(
    "--remove",
    default=None,
    help="Comma-separated issue IDs to remove",
)
edit_parser.add_argument(
    "--prune",
    action="store_true",
    help="Remove invalid (missing file) and completed issue references",
)
edit_parser.add_argument(
    "--revalidate",
    action="store_true",
    help="Re-run dependency analysis after edits",
)
add_config_arg(edit_parser)
```

2. **Add dispatch** in the "commands that need project root" block (after the `show` dispatch at line 144):

```python
if args.command == "edit":
    return _cmd_sprint_edit(args, manager)
```

3. **Update epilog** to include `edit` examples.

4. **Implement `_cmd_sprint_edit()`**:

```python
def _cmd_sprint_edit(args: argparse.Namespace, manager: SprintManager) -> int:
    """Edit a sprint's issue list."""
    logger = Logger()
    sprint = manager.load(args.sprint)
    if not sprint:
        logger.error(f"Sprint not found: {args.sprint}")
        return 1

    if not args.add and not args.remove and not args.prune and not args.revalidate:
        logger.error("No edit flags specified. Use --add, --remove, --prune, or --revalidate.")
        return 1

    original_issues = list(sprint.issues)
    changed = False

    # --add: add new issue IDs
    if args.add:
        add_ids = parse_issue_ids(args.add)
        if add_ids:
            # Validate added issues exist
            valid = manager.validate_issues(list(add_ids))
            invalid = add_ids - set(valid.keys())
            if invalid:
                logger.warning(f"Issue IDs not found (skipping): {', '.join(sorted(invalid))}")

            existing = set(sprint.issues)
            added = []
            for issue_id in sorted(valid.keys()):
                if issue_id not in existing:
                    sprint.issues.append(issue_id)
                    added.append(issue_id)
                else:
                    logger.info(f"Already in sprint: {issue_id}")
            if added:
                logger.success(f"Added: {', '.join(added)}")
                changed = True

    # --remove: remove issue IDs
    if args.remove:
        remove_ids = parse_issue_ids(args.remove)
        if remove_ids:
            before = len(sprint.issues)
            sprint.issues = [i for i in sprint.issues if i not in remove_ids]
            removed_count = before - len(sprint.issues)
            not_found = remove_ids - set(original_issues)
            if not_found:
                logger.warning(f"Not in sprint: {', '.join(sorted(not_found))}")
            if removed_count > 0:
                logger.success(f"Removed {removed_count} issue(s)")
                changed = True

    # --prune: remove invalid and completed references
    if args.prune:
        valid = manager.validate_issues(sprint.issues)
        invalid_ids = set(sprint.issues) - set(valid.keys())

        # Also check completed directory
        completed_ids: set[str] = set()
        if manager.config:
            completed_dir = manager.config.get_completed_dir()
            if completed_dir.exists():
                import re
                for path in completed_dir.glob("*.md"):
                    match = re.search(r"(BUG|FEAT|ENH)-(\d+)", path.name)
                    if match:
                        completed_ids.add(f"{match.group(1)}-{match.group(2)}")

        prune_ids = invalid_ids | (completed_ids & set(sprint.issues))
        if prune_ids:
            sprint.issues = [i for i in sprint.issues if i not in prune_ids]
            pruned_invalid = invalid_ids & prune_ids
            pruned_completed = (completed_ids & set(original_issues)) - invalid_ids
            if pruned_invalid:
                logger.success(f"Pruned invalid: {', '.join(sorted(pruned_invalid))}")
            if pruned_completed:
                logger.success(f"Pruned completed: {', '.join(sorted(pruned_completed))}")
            changed = True
        else:
            logger.info("Nothing to prune — all issues are valid and active")

    # Save if changed
    if changed:
        sprint.save(manager.sprints_dir)
        logger.success(f"Saved {args.sprint} ({len(sprint.issues)} issues)")
        if original_issues != sprint.issues:
            logger.info(f"  Was: {', '.join(original_issues)}")
            logger.info(f"  Now: {', '.join(sprint.issues)}")

    # --revalidate: re-run dependency analysis
    if args.revalidate:
        valid = manager.validate_issues(sprint.issues)
        issue_infos = manager.load_issue_infos(list(valid.keys()))
        if issue_infos:
            from little_loops.dependency_mapper import analyze_dependencies

            issue_contents = _build_issue_contents(issue_infos)
            dep_report = analyze_dependencies(issue_infos, issue_contents)
            _render_dependency_analysis(dep_report, logger)
        else:
            logger.info("No valid issues to analyze")

        # Also show invalid count
        invalid = set(sprint.issues) - set(valid.keys())
        if invalid:
            logger.warning(f"{len(invalid)} issue(s) not found: {', '.join(sorted(invalid))}")

    return 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

### Phase 2: Add unit and integration tests

#### Overview
Add tests for the `edit` subcommand covering all flag combinations.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`

Add a new test class `TestSprintEdit` with tests for:
- `test_edit_add_issues` — adds issues to a sprint
- `test_edit_remove_issues` — removes issues from a sprint
- `test_edit_add_validates_existence` — skips non-existent issues with warning
- `test_edit_add_skips_duplicates` — doesn't add already-present issues
- `test_edit_remove_nonexistent_warns` — warns when removing IDs not in sprint
- `test_edit_prune_removes_invalid` — prune removes issues with no backing files
- `test_edit_prune_removes_completed` — prune removes issues in completed/
- `test_edit_prune_nothing_to_prune` — prune with all-valid sprint
- `test_edit_no_flags_returns_error` — returns 1 when no flags given
- `test_edit_sprint_not_found` — returns 1 for nonexistent sprint
- `test_edit_revalidate` — runs dependency analysis on sprint
- `test_edit_combined_flags` — add + remove + prune in one call

Tests will follow the existing pattern: construct `argparse.Namespace`, call `_cmd_sprint_edit()` directly.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] All new tests pass
- [ ] Existing tests still pass

## Testing Strategy

### Unit Tests
- Test each flag independently (`--add`, `--remove`, `--prune`, `--revalidate`)
- Test flag combinations
- Test edge cases: empty sprint, all issues pruned, duplicate adds, nonexistent removes
- Test error paths: sprint not found, no flags specified

### Integration Tests
- Test with real project structure (issue files, config, completed directory)
- Test round-trip: create sprint, edit it, show it — verify consistency

## References

- Original issue: `.issues/enhancements/P4-ENH-393-sprint-review-edit-command.md`
- Subcommand pattern: `scripts/little_loops/cli/sprint.py:52-148`
- SprintManager API: `scripts/little_loops/sprint.py:203-360`
- Existing tests: `scripts/tests/test_sprint.py`
- `parse_issue_ids`: `scripts/little_loops/cli_args.py:151-168`
- `_render_dependency_analysis`: `scripts/little_loops/cli/sprint.py:491-530`
