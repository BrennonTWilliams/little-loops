---
discovered_date: 2026-04-05
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
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

## Success Metrics

- `--sprint <name>` flag accepted and parsed by both `confidence-check` and `issue-size-review`
- Sprint-scoped run: 0 issues outside the named sprint appear in output
- Without flag: behavior identical to current full-backlog scan (no regression)
- Sprint summary header (`Sprint: <name> (N issues)`) visible in `issue-size-review` output when flag is used

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Sprint YAML loading**: Use the `Read` tool on `.sprints/${SPRINT_NAME}.yaml` (template: `{{config.sprints.sprints_dir}}/${SPRINT_NAME}.yaml`). Both skills already have `Read` in `allowed-tools` — no frontmatter changes needed. The `issues:` key is a flat list of bare ID strings (e.g., `ENH-175`). After reading, resolve each ID to a file path using the same `find` pattern from each skill's existing Single Issue Mode section.

**`ll-sprint show` flag correction**: The Proposed Solution mentions `ll-sprint show <name> --format json` — the actual flag is `--json`, not `--format json`. The direct YAML read approach is simpler and has no dependency on CLI availability.

**Sprint YAML structure** (from `.sprints/*.yaml`):
```yaml
name: my-sprint
issues:
  - ENH-175
  - FEAT-808
options:
  max_workers: 2
```

**Exact insertion points for argument parsing**:

`confidence-check/SKILL.md` (currently lines 33–65):
- Line 34 — add `SPRINT_NAME=""` in the variable declarations block
- Line 45 (after `--check` detection) — add sprint extraction:
  ```bash
  if [[ "$ARGUMENTS" =~ --sprint[[:space:]]+([^[:space:]]+) ]]; then SPRINT_NAME="${BASH_REMATCH[1]}"; fi
  ```
- Lines 55–60 (after the `--all`+ID conflict check) — add sprint/all conflict check:
  ```bash
  if [[ "$ALL_MODE" == true ]] && [[ -n "$SPRINT_NAME" ]]; then
      echo "Error: --sprint and --all cannot be combined"
      exit 1
  fi
  if [[ -n "$SPRINT_NAME" ]]; then AUTO_MODE=true; fi
  ```

`issue-size-review/SKILL.md` (currently lines 41–60):
- Line 42 — add `SPRINT_NAME=""` in declarations
- Line 51 (after `--check` detection) — add the same sprint extraction one-liner
- After the token loop — add `if [[ -n "$SPRINT_NAME" ]]; then AUTO_MODE=true; fi`

**Issue discovery modification**:

`confidence-check` batch mode (currently lines 101–121): when `SPRINT_NAME` is set, replace the `for dir in ...find...` collection loop with sprint-scoped loading: read the sprint YAML, extract the `issues:` list, resolve each ID to a file path using the Single Issue Mode `find` pattern (lines 84–96), populate `ISSUE_FILES` from results.

`issue-size-review` Phase 1 (currently lines 71–81): add a branch — if `SPRINT_NAME` is set, load from sprint YAML instead of Glob across all three directories.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — add `--sprint` argument parsing and sprint-scoped issue loading
- `skills/issue-size-review/SKILL.md` — add `--sprint` argument parsing and sprint-scoped issue loading

### Dependent Files (Callers/Importers)
- `skills/map-dependencies/SKILL.md` — reference implementation to keep consistent

### Similar Patterns
- `skills/map-dependencies/SKILL.md` — `--sprint` flag pattern and `ll-deps analyze --sprint <name>` usage
- `skills/go-no-go/SKILL.md:92-106` — **closer reference**: direct inline sprint YAML reading (no CLI delegation); resolves sprint issues via `cat`/Read tool then re-runs the `find` pattern per ID. Applicable here because neither target skill has a CLI to delegate sprint filtering to (unlike `map-dependencies` → `ll-deps`)

### Tests
- N/A — skills are prompt-based, no unit tests

### Documentation
- `docs/reference/API.md` — update skill argument tables if present
- `CLAUDE.md` — no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md:204` — `confidence-check` `Flags:` entry currently lists `--auto, --all` only; add `--sprint <name>` [Agent 2 finding]
- `docs/reference/COMMANDS.md:214` — `issue-size-review` `Flags:` entry currently lists `--auto` only; add `--sprint <name>` [Agent 2 finding]
- `docs/reference/COMMANDS.md:15` — Flag Conventions table has no `--sprint` row; consider adding one listing `map-dependencies`, `confidence-check`, `issue-size-review` [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:327-330` — Confidence Scoring usage block shows `--auto` / `--all` examples but no `--sprint` example [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:342-348` — Size Review usage block shows no flag examples; add `--sprint <name>` usage [Agent 2 finding]

### Configuration
- `{{config.sprints.sprints_dir}}` — sprint YAML files are read to resolve issue lists

## Implementation Steps

1. Add `--sprint <name>` argument parsing block to `confidence-check/SKILL.md` Arguments section
2. Add sprint issue filtering logic to confidence-check's evaluation loop
3. Add `--sprint <name>` argument parsing block to `issue-size-review/SKILL.md` Arguments section
4. Add sprint issue filtering logic to issue-size-review's audit loop
5. Update examples tables in both skills to include `--sprint` usage

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/COMMANDS.md:204` — add `--sprint <name>` to `confidence-check` Flags entry
7. Update `docs/reference/COMMANDS.md:214` — add `--sprint <name>` to `issue-size-review` Flags entry
8. Update `docs/reference/COMMANDS.md:15` — add `--sprint <name>` row to Flag Conventions table (alongside `map-dependencies`, `confidence-check`, `issue-size-review`)
9. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:327-330` — add `--sprint` usage example to Confidence Scoring section
10. Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:342-348` — add `--sprint` usage example to Size Review section

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete file:line references for each step:

1. **confidence-check arg parsing** — `skills/confidence-check/SKILL.md:34` (add `SPRINT_NAME=""`), `:45` (add `--sprint` extraction), `:55` (add `--all`/`--sprint` conflict guard and `AUTO_MODE=true` implication)
2. **confidence-check batch loop** — `skills/confidence-check/SKILL.md:101-121` — add `if [[ -n "$SPRINT_NAME" ]]; then` branch before the existing `for dir in` loop; inside the branch, read `.sprints/${SPRINT_NAME}.yaml` and resolve each issue ID via the `find` pattern already at lines 84–96
3. **issue-size-review arg parsing** — `skills/issue-size-review/SKILL.md:42` (add `SPRINT_NAME=""`), `:51` (add `--sprint` extraction), after token loop (add `AUTO_MODE=true` implication)
4. **issue-size-review Phase 1** — `skills/issue-size-review/SKILL.md:71-81` — add a branch: if `SPRINT_NAME` is set, load from `.sprints/${SPRINT_NAME}.yaml` instead of Glob; resolve each ID to a file path the same way go-no-go does at `skills/go-no-go/SKILL.md:92-106`
5. **Examples** — `skills/confidence-check/SKILL.md` examples section and `skills/issue-size-review/SKILL.md` examples section — add `--sprint <name>` usage examples alongside existing `--auto`/`--check` examples

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
- `/ll:confidence-check` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9083c276-ec92-4f47-bfee-c9f15b2ddd69.jsonl`
- `/ll:wire-issue` - 2026-04-05T21:23:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c747cefe-c8d3-48e7-a02e-9920ddcde2c8.jsonl`
- `/ll:confidence-check` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b8b1b50-91f2-4e52-9fe7-aaa56732c3ea.jsonl`
- `/ll:refine-issue` - 2026-04-05T21:12:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3577074d-ed2d-4112-aca6-5c5ee60831de.jsonl`
- `/ll:format-issue` - 2026-04-05T21:07:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e2c33bc-ffe1-4e5a-bd00-0c27ac671382.jsonl`

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5c0edf6-3337-46b9-8b9a-275f18759b63.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P3
