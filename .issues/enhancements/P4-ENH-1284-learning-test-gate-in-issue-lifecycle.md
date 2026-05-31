---
id: ENH-1284
title: Learning Test Gate in Issue Lifecycle
type: ENH
priority: P4
captured_at: "2026-04-25T18:06:01Z"
discovered_date: "2026-04-25"
discovered_by: capture-issue
parent: EPIC-1694
status: open
---

# ENH-1284: Learning Test Gate in Issue Lifecycle

## Summary

Add a `learning_tests_required` field to issue templates. `ll:ready-issue` and `ll:go-no-go` check whether learning tests have been executed for each declared assumption about external systems, blocking readiness with "unproven assumption: X" when tests are missing or stale.

## Current Behavior

`ll:ready-issue` and `ll:go-no-go` evaluate issue quality based on completeness of written fields (Summary, Integration Map, Implementation Steps, etc.) but have no mechanism to verify that assumptions about external systems have been empirically proven. An issue claiming "this uses the Anthropic streaming API in mode X" is accepted as-is even if that behavior has never been tested against the live system.

## Expected Behavior

Issue frontmatter can declare required learning tests:

```yaml
learning_tests_required:
  - "Anthropic SDK streaming events"
  - "GitHub API pagination"
```

When `ll:ready-issue` runs, it queries the learning test registry (ENH-1282) for each target:
- **Proven and fresh** → passes, noted in readiness report
- **Missing or stale** → blocks with: `❌ Unproven assumption: "Anthropic SDK streaming events" — run /ll:explore-api "Anthropic SDK streaming events"`
- **Refuted** → hard block with explanation of what the actual behavior was

`ll:go-no-go` surfaces unproven assumptions in its confidence score reasoning.

## Motivation

Issue lifecycle gates (ready-issue, go-no-go) currently check structural quality but not epistemic quality — whether the issue's premises are grounded in observed reality. This is the human-workflow complement to the FSM learning state (ENH-1283): even in interactive (non-loop) sessions, the gate prevents an agent from starting implementation on an issue where key external behaviors are assumed rather than proven.

## Proposed Solution

**Issue template addition** — new optional frontmatter field `learning_tests_required: list[str]`

**`ll:ready-issue` change** — after existing quality checks, if `learning_tests_required` is present:
1. Call `learning_tests.read_record(target)` for each target
2. Classify each as: proven-fresh, proven-stale, missing, refuted
3. Fail readiness if any are missing or refuted; warn (but pass) if stale with age noted

**`ll:go-no-go` change** — factor registry status into confidence score:
- All proven-fresh: +5 confidence
- Any stale: neutral
- Any missing: -10 confidence with note
- Any refuted: -20 confidence with hard warning

## Integration Map

### Files to Modify
- `commands/ready-issue.md` — add learning test query phase
- `skills/go-no-go/SKILL.md` — add registry status to confidence scoring
- Issue template frontmatter schema — document `learning_tests_required` field

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests.py` (ENH-1282) — registry query functions

### Similar Patterns
- Existing `ll:ready-issue` quality checks — follow same pattern for adding a new check phase

### Tests
- Integration test: issue with proven target → ready-issue passes
- Integration test: issue with missing target → ready-issue blocks with message

### Documentation
- Issue template docs — document `learning_tests_required` field
- `docs/development/TROUBLESHOOTING.md` — add entry for learning test gate failures

### Configuration
- N/A — uses registry from ENH-1282; no new config needed

## Implementation Steps

1. Add `learning_tests_required` to issue frontmatter schema/docs
2. Implement registry query phase in `ll:ready-issue` after existing checks
3. Add confidence score adjustments to `ll:go-no-go`
4. Write integration tests
5. Update docs

## Success Metrics

- An issue with `learning_tests_required` and missing registry entries is blocked by `ll:ready-issue`
- An issue with all proven targets passes the gate with a note in the report
- `ll:go-no-go` reflects registry status in its confidence reasoning

## Scope Boundaries

- Out of scope: auto-running `ll:explore-api` from within `ll:ready-issue` (user should run it manually)
- Out of scope: requiring `learning_tests_required` for all issues (field is opt-in)
- Out of scope: changing issue file structure beyond adding the frontmatter field

## API/Interface

```yaml
# Issue frontmatter
---
id: ENH-1300
learning_tests_required:
  - "Anthropic SDK streaming events"
---
```

## Impact

- **Priority**: P4 (deferred) — Valuable but lower urgency than ENH-1283; depends on registry adoption and maturity after ENH-1282 ships
- **Effort**: Small-Medium — Additive check in two existing commands; no new infrastructure
- **Risk**: Low — Opt-in field; issues without it are unaffected
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/deterministic-backpressure-learning-tests.md` | Source philosophy; "assumption leakage" concept |
| `docs/ARCHITECTURE.md` | Issue lifecycle and ready-issue architecture |

## Labels

`enhancement`, `deferred`, `issue-lifecycle`, `learning-tests`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`

- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open (Deferred)** | Created: 2026-04-25 | Priority: P4
