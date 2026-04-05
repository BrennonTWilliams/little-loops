---
discovered_date: 2026-04-05
discovered_by: capture-issue
---

# ENH-956: Add Sprint Scoping to confidence-check and issue-size-review Skills

## Summary

`/ll:confidence-check` and `/ll:issue-size-review` should optionally accept a `--sprint <name>` argument to restrict their analysis to only the issues contained in a named sprint, consistent with how `/ll:map-dependencies` already supports `--sprint`.

## Current Behavior

Both skills operate on the full active issue backlog. There is no way to narrow their scope to a specific sprint when doing pre-sprint readiness or sizing checks.

## Expected Behavior

Users can pass `--sprint <name>` to either skill:

```
/ll:confidence-check --sprint my-sprint
/ll:issue-size-review --sprint my-sprint
```

When the flag is provided, only issues listed in that sprint definition are evaluated. Without the flag, behavior is unchanged (full backlog).

## Motivation

Sprint planning involves two natural pre-flight questions: "Are the issues in this sprint ready to implement?" and "Are the issues in this sprint right-sized?" Today both require manually filtering results from a full-backlog run. Sprint-scoping makes these sprint-planning workflows first-class and reduces noise significantly — a sprint of 10 issues is far easier to evaluate than a backlog of 100+.

`/ll:map-dependencies` already accepts `--sprint <name>` via `ll-deps analyze --sprint <name>`, establishing the precedent and pattern for all issue-set skills.

## Proposed Solution

Both skills should parse `--sprint <name>` from `$ARGUMENTS` and, when present, load the sprint definition to get the issue list before running their analysis.

**Argument parsing pattern** (consistent with map-dependencies):
```bash
SPRINT_NAME=""
if [[ "$ARGUMENTS" =~ --sprint[[:space:]]+([^[:space:]]+) ]]; then
  SPRINT_NAME="${BASH_REMATCH[1]}"
fi
```

**Sprint issue loading**: use `ll-sprint show <name> --format json` (or read the sprint YAML directly from `{{config.sprints.sprints_dir}}/<name>.yaml`) to get the issue ID list, then filter the analysis to only those issues.

**confidence-check**: pass the filtered issue list to the readiness evaluation loop instead of scanning all of `.issues/`.

**issue-size-review**: scope the size audit to the sprint issue set; include a summary line like `Sprint: my-sprint (N issues)` in the output header.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — add `--sprint` argument parsing and sprint-scoped issue loading
- `skills/issue-size-review/SKILL.md` — add `--sprint` argument parsing and sprint-scoped issue loading

### Dependent Files (Callers/Importers)
- `skills/map-dependencies/SKILL.md` — reference implementation to keep consistent

### Similar Patterns
- `skills/map-dependencies/SKILL.md` — `--sprint` flag pattern and `ll-deps analyze --sprint <name>` usage

### Tests
- N/A — skills are prompt-based, no unit tests

### Documentation
- `docs/reference/API.md` — update skill argument tables if present
- `CLAUDE.md` — no changes needed

### Configuration
- `{{config.sprints.sprints_dir}}` — sprint YAML files are read to resolve issue lists

## Implementation Steps

1. Add `--sprint <name>` argument parsing block to `confidence-check/SKILL.md` Arguments section
2. Add sprint issue filtering logic to confidence-check's evaluation loop
3. Add `--sprint <name>` argument parsing block to `issue-size-review/SKILL.md` Arguments section
4. Add sprint issue filtering logic to issue-size-review's audit loop
5. Update examples tables in both skills to include `--sprint` usage

## Scope Boundaries

- Does not add `--sprint` to other skills in this pass (go-no-go, wire-issue, analyze-history are separate candidates)
- Does not change CLI tools (`ll-deps`, `ll-sprint`) — sprint loading is done within the skill prompts
- Does not add `--sprint` to commands (create-sprint, review-sprint already have sprint context)

## API/Interface

```bash
# confidence-check
/ll:confidence-check --sprint <sprint-name>
/ll:confidence-check --sprint <sprint-name> --auto

# issue-size-review
/ll:issue-size-review --sprint <sprint-name>
```

## Impact

- **Priority**: P3 - Useful sprint-planning QoL; not blocking any workflow
- **Effort**: Small - Pattern already exists in map-dependencies; mechanical addition to two SKILL.md files
- **Risk**: Low - Additive only; no behavior change when flag is absent
- **Breaking Change**: No

## Related Key Documentation

| Document | Description | Relevance |
|----------|-------------|-----------|
| `skills/map-dependencies/SKILL.md` | Reference implementation for `--sprint` flag | High |
| `docs/ARCHITECTURE.md` | System design | Medium |

## Labels

`enhancement`, `skills`, `sprint-planning`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5c0edf6-3337-46b9-8b9a-275f18759b63.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P3
