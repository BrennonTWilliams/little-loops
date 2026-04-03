---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-929: Add `--skip` flag to `ll-issues next-action` to prevent issue starvation

## Summary

`ll-issues next-action` always returns the first issue needing work in priority order, with no mechanism to skip issues that have already failed. When the highest-priority issue's sub-loop fails repeatedly, all lower-priority issues are never processed. Adding a `--skip` flag and corresponding skip-list tracking in the parent `issue-refinement` loop prevents this starvation.

## Context

**Conversation mode**: Identified while reviewing a bug report (plan `keen-whistling-spring.md`) about the `issue-refinement` loop being stuck on a single issue. Confirmed as one of two interacting bugs. The fix is straightforward because `find_issues()` already accepts `skip_ids` — the CLI flag just needs to be wired up.

Confirmed via code inspection:
- `scripts/little_loops/cli/issues/next_action.py:27` — `find_issues(config)` called with no skip argument
- `scripts/little_loops/issue_parser.py:615` — `find_issues` already has `skip_ids: set[str] | None = None`
- `scripts/little_loops/loops/issue-refinement.yaml:29-33` — `run_refine_to_ready` routes both `on_yes` and `on_no` to `check_commit` (no failure branch)

## Motivation

The `issue-refinement` loop is designed to process all issues to readiness. Issue starvation defeats its purpose: one perpetually failing issue prevents the remaining 15+ issues from ever being touched. The `find_issues` function already has the `skip_ids` parameter — this enhancement just surfaces it through the CLI and wires the parent loop to use it.

## Proposed Solution

**1. `next_action.py`**: Add `--skip` argument

```python
parser.add_argument(
    "--skip",
    default="",
    help="Comma-separated issue IDs to exclude from consideration",
)
skip_ids = {s.strip() for s in args.skip.split(",") if s.strip()}
issues = find_issues(config, skip_ids=skip_ids or None)
```

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

1. Add `--skip` argument to `cmd_next_action` in `scripts/little_loops/cli/issues/next_action.py`, parse as comma-separated set, pass to `find_issues(config, skip_ids=...)`
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

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop design and `ll-issues` CLI conventions |
| guidelines | .claude/CLAUDE.md | `ll-issues` CLI tools reference |

## Labels

`enhancement`, `loops`, `issue-refinement`, `cli`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d10376d2-598f-4355-a0dc-b5100fe5afca.jsonl`
