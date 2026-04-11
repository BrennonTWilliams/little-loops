---
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# FEAT-1027: Issue Conflict Audit Skill with Auto-Apply

## Summary

Create a new `/ll:` skill/command (`audit-issue-conflicts`) that audits and analyzes open Issues in the user's project for conflicting requirements, objectives, and architecture. The skill synthesizes findings into recommended Issue changes, presents them for user approval in interactive mode, and supports an `--auto` flag to skip approval and auto-apply changes.

## Current Behavior

No tooling exists to detect when open issues have conflicting requirements, contradictory objectives, or architectural incompatibilities. Users must manually review issues for conflicts, which is tedious at scale and easy to miss.

## Expected Behavior

Running `/ll:audit-issue-conflicts` will:
1. Load and analyze all open issues (bugs/, features/, enhancements/)
2. Detect conflicts across: requirements, objectives, architectural decisions, and scope overlap
3. Synthesize findings into a conflict report with recommended changes (merge, close, update, reorder)
4. In interactive mode: present recommendations and ask for user approval before applying
5. With `--auto` flag: skip approval and directly apply all recommended changes

## Use Case

**Who**: A developer managing a large issue backlog, often using `ll-parallel` or `ll-sprint` to execute multiple agents concurrently.

**Context**: The backlog has grown beyond 10-20 open issues. Before kicking off a sprint, the developer suspects some issues may conflict — e.g., two features proposing incompatible data models, or a bug fix that contradicts an enhancement's objective.

**Goal**: Detect and surface conflicting requirements, objectives, or architectural decisions across all open issues in one pass.

**Outcome**: A ranked conflict report with concrete recommendations (merge, deprecate, split, add dependency) — applied interactively or automatically via `--auto`.

## Acceptance Criteria

- [ ] `/ll:audit-issue-conflicts` loads all open issues from bugs/, features/, enhancements/
- [ ] Detects all four conflict types: requirement conflicts, objective conflicts, architecture conflicts, and scope overlap
- [ ] Outputs a conflict report ranked by severity (high/medium/low) with issue IDs and conflict descriptions
- [ ] In interactive mode, presents each recommendation with accept/reject prompt before applying any changes
- [ ] With `--auto` flag, applies all recommendations without prompting
- [ ] With `--dry-run` flag, outputs the conflict report without modifying any issue files
- [ ] When no conflicts are detected, outputs "No conflicts found" and exits with code 0
- [ ] Each recommendation includes: conflict_type, severity, affected issue IDs, description, and proposed_change

## Motivation

As issue backlogs grow, conflicting issues create implementation confusion and wasted effort. A developer implementing FEAT-A may unknowingly conflict with FEAT-B. Automated conflict detection surfaces these issues early, keeps the backlog coherent, and reduces rework. This is especially valuable for projects using `ll-parallel` or `ll-sprint` where multiple agents execute concurrently.

## Proposed Solution

Implement as a `skills/audit-issue-conflicts/SKILL.md` skill following the `commands/tradeoff-review-issues.md` pattern (multi-issue LLM batch scan + per-recommendation approval loop), with the severity-grouped presentation from `skills/audit-claude-config/SKILL.md`.

Likely approach:
- Load all open issue files and extract key metadata (title, summary, objectives, architecture notes, integration maps)
- Use LLM-based pairwise or cluster comparison to identify conflict patterns:
  - **Requirement conflicts**: Issue A requires X, Issue B requires not-X
  - **Objective conflicts**: Two issues solve the same problem differently
  - **Architecture conflicts**: Incompatible technical approaches (e.g., sync vs async, different data models)
  - **Scope overlap**: Issues that partially duplicate each other
- Generate a ranked conflict report grouped by severity
- Recommended changes: merge, deprecate, split, add dependency, update scope
- Interactive approval loop (similar to `ready-issue`) or `--auto` bypass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Primary implementation model**: `commands/tradeoff-review-issues.md` — batches 3-5 issues per Task call for parallel LLM evaluation; aggregates by recommendation type; presents per-recommendation `AskUserQuestion` with `multiSelect: false`; applies changes with `ll-issues append-log`
- **Secondary model**: `skills/audit-claude-config/SKILL.md` — severity-grouped presentation (Critical → Warning → Suggestion) with `--fix` for auto-apply and `--non-interactive` for skip; companion `report-template.md` for final report rendering
- **Flag parsing pattern** (`skills/wire-issue/SKILL.md:55-65`): check `$DANGEROUSLY_SKIP_PERMISSIONS` first, then `--auto`, `--dry-run`, `--check` via substring match on `$FLAGS`; `--check` implies both `--auto` and `--dry-run` for FSM evaluator integration
- **Issue loading** in skill markdown: glob `{{config.issues.base_dir}}/bugs/*.md`, `features/*.md`, `enhancements/*.md`; parse filename for ID/priority/type; read content for Summary, Integration Maps, Implementation Steps sections
- **Reusable Python** (if Python component added): `find_issues(config)` at `scripts/little_loops/issue_parser.py:612`; `IssueInfo.path.read_text()` for full content; existing `parallel/overlap_detector.py` detects file-level conflicts (out of scope for semantic conflicts)
- **Interactive approval loop**: per-recommendation `AskUserQuestion` from `commands/tradeoff-review-issues.md:183-213`; options: accept/reject/update for each conflict pair
- **Session log**: `ll-issues append-log <path> /ll:audit-issue-conflicts` after each modified issue file

## Integration Map

### Files to Modify
- `skills/audit-issue-conflicts/SKILL.md` — primary deliverable; new skill file to create (does not yet exist)
- `.claude/CLAUDE.md` — add `audit-issue-conflicts`^ to Issue Refinement or Meta-Analysis section

### Dependent Files (Callers/Importers)
- `.claude-plugin/plugin.json` — **no change needed**; `"skills": ["./skills"]` at line 20 auto-discovers all `skills/*/SKILL.md` files
- `commands/audit-issue-conflicts.md` — **not needed**; skills in `skills/*/SKILL.md` are auto-registered as `/ll:audit-issue-conflicts` without a separate command file
- `hooks/hooks.json` — optional hook integration; no changes required for the base implementation

### Similar Patterns
- `skills/audit-claude-config/SKILL.md` — audit pattern with severity-grouped findings (Critical/Warning/Suggestion), `--fix` (auto-apply), `--non-interactive` flags, and companion `skills/audit-claude-config/report-template.md`
- `commands/tradeoff-review-issues.md` — multi-issue LLM batch evaluation with per-recommendation `AskUserQuestion` approval loop; closest match for the interactive approval pattern
- `commands/align-issues.md` — multi-issue loading via `{{config.issues.base_dir}}` glob with `--dry-run` flag
- `commands/ready-issue.md` — `--check` flag (FSM evaluator mode: implies `--auto` + `--dry-run`), structured verdict output with session log

### Tests
- TBD - unit tests for conflict detection logic if implemented in Python
- Integration tests covering: no conflicts, single conflict, multiple conflicts, `--auto` mode

### Documentation
- `docs/ARCHITECTURE.md` - mention new skill
- `CLAUDE.md` - add to command list under Issue Refinement or Meta-Analysis

### Configuration
- N/A (no new config keys required; reads existing `issues.base_dir`)

## Implementation Steps

1. **Define conflict taxonomy** — the four types (requirement, objective, architecture, scope) and three severity levels (high/medium/low) are already specified in the `## API/Interface` section; no additional design needed
2. **Create `skills/audit-issue-conflicts/SKILL.md`** — follow frontmatter pattern from `skills/format-issue/SKILL.md:1-19`; use `commands/tradeoff-review-issues.md` as the primary structural template for the multi-issue scan + approval loop
3. **Implement issue loading** — glob `{{config.issues.base_dir}}/{bugs,features,enhancements}/*.md`; for each file parse ID/type/priority from filename, and extract Summary, Objectives, Integration Map, Architecture, Implementation Steps sections from content
4. **Implement conflict detection engine** — batch issues 3-5 at a time; spawn all batch Task calls in a single message (pattern: `commands/tradeoff-review-issues.md:48-127`); each task returns structured conflict records with `conflict_type`, `severity`, `issues`, `description`, `recommendation`
5. **Implement recommendation synthesis and report** — aggregate all batch findings; group by severity (high → medium → low); output ranked conflict table following the `recommendation` object structure in `## API/Interface`
6. **Implement interactive approval loop** — per-recommendation `AskUserQuestion` with options accept/reject/update (pattern: `commands/tradeoff-review-issues.md:183-213`); skip entirely in `--auto` mode
7. **Implement `--auto` and `--dry-run` flags** — parse from `$FLAGS` using substring match; check `$DANGEROUSLY_SKIP_PERMISSIONS` env var (pattern: `skills/wire-issue/SKILL.md:55-65`); `--dry-run` outputs report without modifying any issue files
8. **Update `.claude/CLAUDE.md`** — add `audit-issue-conflicts`^ to Issue Refinement or Meta-Analysis section; no `plugin.json` changes needed (auto-discovered via `"skills": ["./skills"]`)
9. **Write tests** — integration tests covering: no conflicts, single conflict pair, multiple conflicts across types, `--auto` mode, `--dry-run` mode; follow test patterns in `scripts/tests/`

## API/Interface

```python
# CLI invocation
/ll:audit-issue-conflicts          # interactive mode
/ll:audit-issue-conflicts --auto   # auto-apply all recommendations
/ll:audit-issue-conflicts --dry-run  # report only, no changes

# Recommendation object structure (conceptual)
{
  "conflict_type": "objective",  # requirement | objective | architecture | scope
  "severity": "medium",          # low | medium | high
  "issues": ["FEAT-100", "FEAT-200"],
  "description": "Both issues implement caching but use incompatible backends",
  "recommendation": "merge",     # merge | deprecate | split | add_dependency | update_scope
  "proposed_change": "Close FEAT-200, add its scope to FEAT-100"
}
```

## Impact

- **Priority**: P3 - Medium value; improves backlog hygiene but not blocking
- **Effort**: Medium - New skill with LLM-based analysis; similar to `audit-claude-config`
- **Risk**: Low - Read-heavy with optional write; `--auto` mode is the only risk surface
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `captured`, `issue-management`, `audit`

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-04-11T04:26:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c85b9aa1-79ab-48d3-84d4-705da5aae834.jsonl`
- `/ll:format-issue` - 2026-04-11T04:21:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/747b5bd8-c7d1-4db4-9f6c-74f553aeef25.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f3d0cb5-182d-4d87-9949-f092df0ed97f.jsonl`
