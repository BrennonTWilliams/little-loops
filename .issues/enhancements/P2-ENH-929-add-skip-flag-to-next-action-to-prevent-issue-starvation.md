---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-929: Add `--skip` flag to `ll-issues next-action` to prevent issue starvation

## Summary

`ll-issues next-action` always returns the first issue needing work in priority order, with no mechanism to skip issues that have already failed. When the highest-priority issue's sub-loop fails repeatedly, all lower-priority issues are never processed. Adding a `--skip` flag and corresponding skip-list tracking in the parent `issue-refinement` loop prevents this starvation.

## Current Behavior

`ll-issues next-action` always returns the first issue needing work in priority order. There is no mechanism to exclude specific issues from consideration. When the highest-priority issue fails repeatedly in the `issue-refinement` loop, the loop continues selecting the same issue on every iteration, permanently blocking all lower-priority issues from being processed.

## Expected Behavior

`ll-issues next-action --skip ENH-929,BUG-001` excludes the specified issue IDs and returns the next eligible issue. The `issue-refinement` loop tracks failed issues in an ephemeral skip list and passes it to each `next-action` call, ensuring lower-priority issues are not starved by a single perpetually-failing issue.

## Context

**Conversation mode**: Identified while reviewing a bug report (plan `keen-whistling-spring.md`) about the `issue-refinement` loop being stuck on a single issue. Confirmed as one of two interacting bugs. The fix is straightforward because `find_issues()` already accepts `skip_ids` — the CLI flag just needs to be wired up.

Confirmed via code inspection:
- `scripts/little_loops/cli/issues/next_action.py:27` — `find_issues(config)` called with no skip argument
- `scripts/little_loops/issue_parser.py:615` — `find_issues` already has `skip_ids: set[str] | None = None`
- `scripts/little_loops/loops/issue-refinement.yaml:29-33` — `run_refine_to_ready` routes both `on_yes` and `on_no` to `check_commit` (no failure branch)

## Motivation

The `issue-refinement` loop is designed to process all issues to readiness. Issue starvation defeats its purpose: one perpetually failing issue prevents the remaining 15+ issues from ever being touched. The `find_issues` function already has the `skip_ids` parameter — this enhancement just surfaces it through the CLI and wires the parent loop to use it.

## Success Metrics

- **Starvation prevention**: When `issue-refinement` encounters repeated failures on the same issue, subsequent iterations select a different issue — before: loop permanently stuck on same issue; after: lower-priority issues get processed
- **CLI correctness**: `ll-issues next-action --skip ENH-929` excludes the specified ID and returns the next eligible issue — before: `--skip` flag not supported; after: returns correct next issue
- **Backwards compatibility**: `ll-issues next-action` (no `--skip`) returns identical results to current behavior — before: all issues eligible; after: same behavior preserved

## Proposed Solution

**1. `cli/issues/__init__.py:342`**: Register `--skip` via shared helper (after existing `add_*_arg` calls on the `na` subparser)

```python
add_skip_arg(na)  # adds --skip / -s with default=None
```

**1b. `next_action.py:27`**: Parse skip IDs and pass to `find_issues` (using existing `parse_issue_ids` utility)

```python
skip_ids = parse_issue_ids(args.skip)  # returns set[str] or set()
issues = find_issues(config, skip_ids=skip_ids or None)
```

Note: `add_skip_arg` and `parse_issue_ids` already exist in `scripts/little_loops/cli_args.py:57` and `:197`. Import them the same way other `ll-issues` subcommands do.

**2. `issue-refinement.yaml`**: Add failure branch and skip tracking

```yaml
run_refine_to_ready:
  loop: refine-to-ready-issue
  context_passthrough: true
  on_yes: check_commit
  on_no: handle_failure      # <-- was: check_commit

handle_failure:
  action: |
    ID="${captured.input.output}"
    FILE=".loops/tmp/issue-refinement-skip-list"
    CURRENT=$(cat "$FILE" 2>/dev/null || echo "")
    if [ -z "$CURRENT" ]; then printf '%s' "$ID" > "$FILE"
    else printf ',%s' "$ID" >> "$FILE"; fi
  action_type: shell
  next: check_commit

evaluate:
  action: ll-issues next-action --skip "$(cat .loops/tmp/issue-refinement-skip-list 2>/dev/null)"
  ...
```

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py:342`, call `add_skip_arg(na)` after the existing `add_config_arg(na)` to register `--skip`/`-s`. In `scripts/little_loops/cli/issues/next_action.py:27`, add `skip_ids = parse_issue_ids(args.skip)` and change the `find_issues` call to `find_issues(config, skip_ids=skip_ids or None)`. Both `add_skip_arg` and `parse_issue_ids` are already in `scripts/little_loops/cli_args.py`; import them the same way other subcommands do.
2. In `scripts/little_loops/loops/issue-refinement.yaml`:
   - Add `handle_failure` state that appends the failed issue ID to `.loops/tmp/issue-refinement-skip-list`
   - Change `run_refine_to_ready.on_no` from `check_commit` to `handle_failure`
   - Update `evaluate` state to pass skip list: `ll-issues next-action --skip "$(cat .loops/tmp/issue-refinement-skip-list 2>/dev/null)"`
3. Update `init` state to also clear the skip list: `rm -f .loops/tmp/issue-refinement-skip-list`
4. Add CLI test for `--skip` flag in the `ll-issues next-action` test suite

## API/Interface

New CLI flag:

```
ll-issues next-action [--skip ISSUE_ID[,ISSUE_ID,...]]
```

- `--skip` accepts a comma-separated list of issue IDs (e.g. `ENH-8987,BUG-001`)
- IDs not present in the list are unaffected
- Empty or absent `--skip` preserves existing behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py:342` — call `add_skip_arg(na)` to register `--skip`/`-s` on the `next-action` subparser (after the existing `add_config_arg(na)` call at the end of the `na` subparser block)
- `scripts/little_loops/cli/issues/next_action.py:27` — add `parse_issue_ids(args.skip)` call and pass `skip_ids` to `find_issues`
- `scripts/little_loops/loops/issue-refinement.yaml` — add `handle_failure` state, update `evaluate` to pass skip list, update `init` to clear skip list
- `docs/reference/CLI.md` — add `--skip` flag to `ll-issues next-action` documentation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:612` — `find_issues()` already accepts `skip_ids: set[str] | None = None`; filter applied at line 665 (`if info.issue_id in skip_ids: continue`); no changes needed
- `scripts/little_loops/cli_args.py:57` — `add_skip_arg()` shared helper (no changes needed; just import and call)
- `scripts/little_loops/cli_args.py:197` — `parse_issue_ids()` shared parser (no changes needed; just import and call)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/issues/__init__.py:312-342` — the `na` subparser block where all `next-action` arguments are registered; the `--skip` arg goes here via `add_skip_arg(na)`, after the existing `add_config_arg(na)` at line 342
- `scripts/little_loops/cli/issues/next_action.py:27-28` — `issues = find_issues(config)` at line 27; local re-sort at line 28 uses `(priority_int, -int(issue_id.split("-")[1]))` (descending ID as tiebreaker), which differs from `find_issues`'s own sort — the skip filter in `find_issues` operates before this re-sort, so behavior is correct
- `scripts/little_loops/loops/issue-refinement.yaml:24` — `parse_id` state uses `capture: "input"`; the issue ID is stored as `captured["input"]["output"]`, making `${captured.input.output}` the correct interpolation in `handle_failure`
- `scripts/little_loops/fsm/executor.py:458-464` — confirms capture dict structure: always `{output, stderr, exit_code, duration_ms}`; `${captured.input.output}` resolves via dot traversal in `interpolation.py:102-123`
- `scripts/little_loops/fsm/executor.py:304-311` — `context_passthrough: true` extracts `.output` strings from `self.captured` into child FSM context; the child `refine-to-ready-issue` loop receives the issue ID as `context.input`

### Similar Patterns
- `scripts/little_loops/loops/dead-code-cleanup.yaml:20-22,90` — identical exclusion-list pattern: appends failed items to `.loops/tmp/ll-dead-code-excluded.txt` one per line, reads file in subsequent states via `cat` to filter next scan
- `scripts/little_loops/cli_args.py:57-72` — `add_skip_arg()` shared helper (already exists): adds `--skip`/`-s` string arg with `default=None`; use this instead of inline `add_argument` in `__init__.py`
- `scripts/little_loops/cli_args.py:197` — `parse_issue_ids()` function: parses comma-separated IDs into a `set[str]`; used by `ll-auto`, `ll-parallel`, `ll-sprint` for skip/only filtering

### Tests
- `scripts/tests/test_next_action.py` — existing `next-action` tests; add `--skip` integration tests here following the pattern: patch `sys.argv` with `["ll-issues", "next-action", "--skip", "ENH-929", "--config", str(temp_project_dir)]`, call `main_issues()`, assert on exit code and output
- `scripts/tests/test_cli_args.py:435-472` — `TestAddSkipArg` class already tests the `add_skip_arg()` helper; no new tests needed there
- `scripts/tests/test_builtin_loops.py` — has `TestIssueRefinementSubLoop` class; add assertions for the new `handle_failure` state and updated `evaluate` action

### Documentation
- `docs/reference/CLI.md` — documents `ll-issues next-action`; update to add `--skip` flag description

### Configuration
- N/A — skip list file (`.loops/tmp/issue-refinement-skip-list`) is ephemeral, not a config file

## Scope Boundaries

- **In scope**: Adding `--skip` CLI flag to `ll-issues next-action`; updating `issue-refinement.yaml` to maintain a per-run skip list and use it in the `evaluate` state; clearing the skip list in the `init` state
- **Out of scope**: Persistent skip lists across separate loop runs; applying skip logic to other `ll-issues` subcommands; automatic retry policies or backoff; skip list UI in `ll-issues list`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop design and `ll-issues` CLI conventions |
| guidelines | .claude/CLAUDE.md | `ll-issues` CLI tools reference |

## Labels

`enhancement`, `loops`, `issue-refinement`, `cli`, `captured`

## Impact

- **Priority**: P2 — Directly causes issue starvation in `issue-refinement` loop; blocks multiple issues from ever being processed when one repeatedly fails
- **Effort**: Small — `find_issues()` already accepts `skip_ids`; only CLI wiring and YAML loop update needed
- **Risk**: Low — Additive change; absent `--skip` preserves existing behavior exactly
- **Breaking Change**: No

---

## Status

**Completed** | Created: 2026-04-02 | Resolved: 2026-04-03 | Priority: P2

## Resolution

Implemented as described. All success metrics met:

- `cli/issues/__init__.py`: Added `add_skip_arg(na)` before `add_config_arg(na)` on the `next-action` subparser
- `cli/issues/next_action.py`: Added `parse_issue_ids(args.skip)` and pass `skip_ids` to `find_issues`
- `issue-refinement.yaml`: Added `handle_failure` state (appends to skip list), changed `on_no` from `check_commit` to `handle_failure`, updated `evaluate` to pass skip list, updated `init` to clear skip list
- `docs/reference/CLI.md`: Added `--skip` flag documentation and example
- Tests: 8 new tests (3 CLI + 5 YAML structure); 4150 total pass

## Verification Notes

**Verdict**: VALID — Verified 2026-04-02

- `scripts/little_loops/cli/issues/next_action.py:27`: `find_issues(config)` called with no skip argument ✓
- `scripts/little_loops/issue_parser.py:615`: `find_issues` has `skip_ids: set[str] | None = None` parameter — not wired to CLI ✓
- `scripts/little_loops/loops/issue-refinement.yaml:32-33`: `on_yes: check_commit`, `on_no: check_commit` — no failure/skip branch ✓
- Enhancement is accurately described; the fix is additive only

## Session Log
- `/ll:manage-issue` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae5f2d8c-a912-40b2-b762-74de7662f6ff.jsonl`
- `/ll:ready-issue` - 2026-04-03T20:34:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ae5f2d8c-a912-40b2-b762-74de7662f6ff.jsonl`
- `/ll:verify-issues` - 2026-04-03T06:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T06:18:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T06:14:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/677939b4-0616-4d61-b3ac-9611ab44a683.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d10376d2-598f-4355-a0dc-b5100fe5afca.jsonl`
