---
discovered_date: 2026-02-13
discovered_by: capture_issue
---

# ENH-408: Add --all and --auto flags to confidence-check skill

## Summary

Update `/ll:confidence-check` to support `--all` and `--auto` flags, matching the batch-processing pattern established by `/ll:ready-issue`. Additionally, ensure the skill updates a `confidence_score` field in the issue's YAML frontmatter after evaluation.

## Current Behavior

`/ll:confidence-check` only accepts a single issue ID argument. It has no batch mode (`--all`) and no non-interactive mode (`--auto`). It does not persist its confidence score to the issue file's frontmatter.

## Expected Behavior

- `--all`: Run confidence check against all active issues (excluding completed), producing a summary table of scores and recommendations.
- `--auto`: Run non-interactively without user prompts (e.g., auto-skip issues that score below threshold, no confirmation dialogs).
- `--all --auto`: Combine both for fully automated batch confidence checking.
- After each evaluation, write/update a `confidence_score` field in the issue's YAML frontmatter (e.g., `confidence_score: 85`).

## Motivation

Several commands (`/ll:format-issue`, `/ll:refine-issue`, `/ll:prioritize-issues`) already support `--all` and `--auto` for batch processing. `/ll:confidence-check` lacks these, creating an inconsistency in the issue refinement pipeline. Batch confidence checking is useful during sprint planning to quickly assess which issues are implementation-ready. Persisting the score to frontmatter enables downstream tools (sprint creation, prioritization) to filter by confidence.

## Proposed Solution

TBD - requires investigation

Reference `commands/format_issue.md` for the `--all`/`--auto` pattern to replicate. Key changes:

1. Parse `$ARGUMENTS` for `--all` and `--auto` flags
2. When `--all`: glob active issue files, iterate and evaluate each
3. When `--auto`: suppress AskUserQuestion calls, use defaults
4. After scoring, use frontmatter parsing to read/update YAML block with `confidence_score: <score>`
5. Output summary table when processing multiple issues

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — add flag parsing, batch logic, frontmatter update step

### Dependent Files (Callers/Importers)
- `commands/manage_issue.md` — references confidence-check as optional step (no changes needed)

### Similar Patterns
- `commands/format_issue.md` — reference implementation for `--all`/`--auto` flags
- `commands/refine_issue.md` — another reference for `--auto` flag pattern

### Tests
- N/A (skill is a prompt-based definition, no Python tests)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Study `commands/format_issue.md` for `--all`/`--auto` flag parsing and batch iteration pattern
2. Add flag parsing and batch iteration logic to `skills/confidence-check/SKILL.md`
3. Add frontmatter update step (write `confidence_score` after evaluation)
4. Add summary table output for batch mode
5. Verify skill invocation works with single issue, `--all`, `--auto`, and combined flags

## Impact

- **Priority**: P3 - Consistency enhancement, not blocking any workflows
- **Effort**: Small - Pattern already established in ready_issue, mostly copying the approach
- **Risk**: Low - Additive changes to an existing skill definition
- **Breaking Change**: No

## Scope Boundaries

- NOT changing the 5-point scoring criteria or score thresholds
- NOT adding `--all`/`--auto` to other skills (separate issues if needed)
- NOT adding frontmatter fields beyond `confidence_score`

## Success Metrics

- `/ll:confidence-check --all` evaluates all active issues and produces summary table
- `/ll:confidence-check --auto ENH-408` runs without user interaction
- Issue frontmatter contains `confidence_score: <number>` after evaluation

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Skill vs Agent preference, issue file format |
| architecture | docs/ARCHITECTURE.md | Skill definition conventions |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-02-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7b1d8ae-1301-4fdc-8b54-232d76034081.jsonl`
- `/ll:manage-issue` - 2026-02-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/adf32343-217d-4a2b-bbda-bd1646f85efe.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `skills/confidence-check/SKILL.md`: Added --all/--auto flag parsing, issue discovery (single + batch), Phase 4 frontmatter update, auto mode behavior docs, batch output format, and usage examples

### Verification Results
- Tests: SKIP (prompt-based skill, no Python code)
- Lint: SKIP
- Types: SKIP
- Run: SKIP
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-13 | Completed: 2026-02-13 | Priority: P3
