---
id: FEAT-1287
type: FEAT
priority: P2
captured_at: "2026-04-25T00:00:00Z"
discovered_date: "2026-04-25"
discovered_by: issue-size-review
parent_issue: FEAT-1282
size: Medium
---

# FEAT-1287: ll:explore-api Skill

## Summary

Implement `skills/explore-api/SKILL.md` — a new skill that guides agents through the full Feathers Learning Test lifecycle (Ingest → Hypothesize → Execute → Refine) for any external system target, then writes a proof record to the `.ll/learning-tests/` registry via `ll-learning-tests`. Also includes the count/table updates to README, CONTRIBUTING, CLAUDE.md, and ARCHITECTURE.md that completing the full feature requires.

## Parent Issue

Decomposed from FEAT-1282: Learning Test Registry and ll:explore-api Skill

## Proposed Solution

### Skill invocation

```
/ll:explore-api "Anthropic SDK streaming"
/ll:explore-api "Claude API tool use" --assume "tools is a list" --assume "stop_reason is tool_use"
```

### Four-phase lifecycle

**Phase 1 — Ingest**: Read relevant docs, existing code samples, and any prior registry records for the target (via `ll-learning-tests check "<target>"`). Summarize what is already known.

**Phase 2 — Hypothesize**: Generate 3-7 specific, falsifiable claims about the target's behavior. Each claim should be testable with a minimal script. Example: _"streaming events are dicts with a `type` key"_.

**Phase 3 — Execute**: Scaffold a minimal runnable proof script (Python or TypeScript depending on target). Run it via `Bash` capturing stdout/stderr. Save raw output to `.ll/learning-tests/raw/<slug>.txt`.

**Phase 4 — Refine**: Diff expected vs actual. Update claim pass/fail results. Call `ll-learning-tests` (or `Write` directly) to persist a `LearnTestRecord` to `.ll/learning-tests/<slug>.md`. Report proven/refuted/untested claims back to the conversation.

### Skill structure

Follow `skills/manage-issue/SKILL.md` as the canonical multi-phase skill template:
- Frontmatter: `description`, `argument-hint`, `allowed-tools`, `arguments`
- Numbered `## Phase N:` sections
- `{{config.*}}` interpolation where needed
- Use `Bash(ll-learning-tests:*)` permission for registry writes

### Documentation touchpoints (included here as these are the last deliverable)

- `README.md` — increment skill count (27→28) and CLI tool count (16→17); add `explore-api^` skill table row; add `### ll-learning-tests` CLI subsection (CLI count increment shared with FEAT-1286 — coordinate or pick up the diff here)
- `CONTRIBUTING.md` — increment skill count (line 125); add `├── explore-api/` to skills tree and `├── learning_tests.py` to module tree
- `.claude/CLAUDE.md` — increment skill count (line 38); add `ll-learning-tests` to CLI tools list
- `docs/ARCHITECTURE.md` — add learning test registry section describing the lifecycle and registry format

## Files to Create/Modify

- `skills/explore-api/SKILL.md` — **create** (new skill)
- `README.md` — skill count, CLI count, table row, CLI subsection
- `CONTRIBUTING.md` — skill count, trees
- `.claude/CLAUDE.md` — skill count, CLI list
- `docs/ARCHITECTURE.md` — add registry section

## Implementation Steps

1. Write `skills/explore-api/SKILL.md` with all four phases
2. Manually test: run `/ll:explore-api` on a real target (e.g., Python `pathlib.Path`) and verify a `.ll/learning-tests/` record is created
3. Update README, CONTRIBUTING, CLAUDE.md counts and tables
4. Add learning test registry section to `docs/ARCHITECTURE.md`

## Acceptance Criteria

- `/ll:explore-api "Python pathlib"` (or any real target) produces a `.ll/learning-tests/<slug>.md` with at least one `pass` or `fail` assertion
- The skill queries existing registry records before hypothesizing (avoids redundant proofs)
- Counts in README and CONTRIBUTING are accurate after update
- `docs/ARCHITECTURE.md` has a learning test registry section

## Dependencies

- FEAT-1285 (learning_tests module) must be complete
- FEAT-1286 (CLI tool) must be installable — the skill invokes it via `Bash`

---

**Open** | Created: 2026-04-25 | Priority: P2
