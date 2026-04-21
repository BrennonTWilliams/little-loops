---
captured_at: "2026-04-21T20:38:05Z"
discovered_date: "2026-04-21"
discovered_by: capture-issue
decision_needed: false
---

# FEAT-1236: Add /ll:decide-issue skill to resolve multiple implementation options

## Summary

A new `/ll:decide-issue` skill that, when an issue has a `decision_needed: true` frontmatter flag, compares listed implementation options using codebase evidence, evaluates their tradeoffs, selects the best-fit option, updates the issue with the decision and reasoning, and clears the flag. Enables the refinement pipeline to fully resolve issues before implementation without requiring human intervention for every option-bearing issue.

## Current Behavior

When `/ll:refine-issue --auto` finds multiple valid implementation approaches from codebase research, it deposits all options without choosing one. There is no mechanism to automatically evaluate and select among them. The choice is left to the implementer at implementation time — when switching is most expensive and context is most stale.

## Expected Behavior

A `/ll:decide-issue` skill can be run after `/ll:refine-issue` to evaluate listed options using codebase evidence (similar patterns, call sites, consistency, complexity), select one, annotate the reasoning inline, and update the issue with a final decision. A `decision_needed: true` frontmatter flag (set by `refine-issue --auto` per ENH-1237) signals to automation that this step should run before the issue proceeds to `/ll:wire-issue`.

## Motivation

Unresolved implementation options left in issues create ambiguity for automated pipelines — `ll-auto` cannot choose among them, and implementers must make the decision at implementation time when switching cost is highest. Resolving options early, with codebase evidence, produces cleaner, more actionable issues and makes automated pipelines fully unattended through the refinement phase.

## Use Case

A developer runs `ll-auto` on a backlog of issues. `/ll:refine-issue --auto` enriches an ENH issue and finds 3 viable implementation approaches from pattern research. It sets `decision_needed: true` in frontmatter. `ll-auto` detects the flag and invokes `/ll:decide-issue`, which evaluates the 3 options, finds that Option 2 matches an established pattern in the codebase, selects it, and annotates the reasoning. The issue proceeds to `/ll:wire-issue` with a clear, decided approach — no human decision required.

## Acceptance Criteria

- Given an issue with `decision_needed: true` and 2+ options in Proposed Solution, `/ll:decide-issue` selects one and updates the issue with the choice highlighted and reasoning annotated
- `decision_needed` is cleared (false or removed) from frontmatter after a decision is made
- If only one option is present, the skill exits cleanly without modifying the issue
- Can be run manually on any issue even without the `decision_needed` flag
- `--dry-run` flag previews the decision without modifying the issue
- Output report includes the chosen option, scoring summary, and options considered
- `/ll:manage-issue` halts at Phase 2 with a clear message when `decision_needed: true` is present, directing the user to run `/ll:decide-issue` first; `--force-implement` bypasses the halt with a warning

## Proposed Solution

New skill at `skills/decide-issue/SKILL.md`:

1. Read the issue and extract all implementation options from `Proposed Solution` (numbered list items, option headers, or "Option A / Option B" patterns)
2. For each option, spawn a `codebase-pattern-finder` subagent to gather evidence: does this pattern exist elsewhere? how many call sites? any existing utilities that support it?
3. Score each option against: consistency with existing patterns, implementation simplicity, testability, and risk
4. Select the top-scoring option; annotate it inline in `Proposed Solution` with a `> **Selected:** ...` callout and a `### Decision Rationale` subsection explaining the scoring
5. Clear `decision_needed: true` from frontmatter (set to `false` or remove key)

Triggered by `decision_needed: true` in frontmatter when invoked by `ll-auto`/`ll-parallel`. Can also be invoked manually on any issue with multiple options.

## API/Interface

```
/ll:decide-issue [ISSUE_ID] [--auto] [--dry-run]
```

Frontmatter field:
```yaml
decision_needed: true   # set by refine-issue --auto; cleared by decide-issue
```

## Integration Map

### Files to Modify
- `skills/decide-issue/SKILL.md` — new skill (create)
- `commands/` — register skill if needed
- `scripts/little_loops/auto.py` — add conditional `decide-issue` invocation when `decision_needed: true`
- `scripts/little_loops/parallel_runner.py` — same conditional invocation
- `skills/manage-issue/SKILL.md` — add `decision_needed` gate at Phase 2 (after reading issue, before plan creation): halt with message if `true`, respect `--force-implement` to bypass with warning

### Dependent Files (Callers/Importers)
- TBD - use grep to find references to `decision_needed` after ENH-1237 lands

### Similar Patterns
- `skills/refine-issue/` — existing skill with similar subagent spawning pattern
- `skills/wire-issue/` — similar post-refine enrichment skill structure

### Tests
- TBD - identify test files to update

### Documentation
- `docs/ARCHITECTURE.md` — pipeline diagram may need updating
- `commands/refine-issue.md` — pipeline position section should reference decide-issue

### Configuration
- N/A

## Implementation Steps

1. Design and document `decision_needed` frontmatter field in issue schema
2. Create `skills/decide-issue/SKILL.md` with option extraction, evidence gathering, scoring, and update logic
3. Implement option extraction (parse numbered/bulleted alternatives from Proposed Solution)
4. Implement codebase evidence gathering via `codebase-pattern-finder` subagent
5. Implement scoring and selection logic with tie-breaking rules
6. Implement issue update (annotate chosen option, add rationale subsection, clear flag)
7. Add conditional `decide-issue` invocation to `ll-auto` and `ll-parallel` when `decision_needed: true`
8. Add `decision_needed` gate to `skills/manage-issue/SKILL.md` Phase 2: halt if `true`, bypass with `--force-implement`
9. Add to pipeline documentation in `commands/refine-issue.md`

## Impact

- **Priority**: P3 - improves automated pipeline quality; not blocking but meaningfully increases unattended throughput
- **Effort**: Medium - new skill with multi-step logic; option parsing and scoring are novel
- **Risk**: Low - reads and writes to issue files only; no system-wide state changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `pipeline`, `automation`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-21T20:38:05Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c8873df-f234-41f4-a242-d1cae3dc0002.jsonl`

---

**Open** | Created: 2026-04-21 | Priority: P3
