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

## Use Case

A developer is unfamiliar with the Anthropic SDK's streaming API and wants to understand what events are emitted before writing production code. They run `/ll:explore-api "Anthropic SDK streaming"` and the skill: reads existing registry records and SDK docs; generates 5 falsifiable claims about event structure; runs a minimal proof script; and persists a `LearnTestRecord` to `.ll/learning-tests/anthropic-sdk-streaming.md` showing which claims passed or failed — all without the developer writing a single test script by hand.

## Current Behavior

N/A — This skill does not yet exist. There is no guided workflow for exploring external API behavior and persisting proof records to the Learning Test Registry.

## Expected Behavior

Invoking `/ll:explore-api "<target>"` guides the agent through four phases (Ingest → Hypothesize → Execute → Refine), produces a `.ll/learning-tests/<slug>.md` `LearnTestRecord`, and reports proven/refuted/untested claims back to the conversation.

## Motivation

- Without this skill, agents must manually piece together docs, write ad-hoc proof scripts, and discard results — repeating the same exploration on every related task.
- The Learning Test Registry (FEAT-1285/1286) provides the storage layer but has no guided skill to populate it; this skill closes that gap.
- Enables future agents to skip Phase 1 (Ingest) by querying existing records via `ll-learning-tests check`, compounding knowledge over time.

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

## API/Interface

```
/ll:explore-api "<target>"
/ll:explore-api "<target>" --assume "<claim>"   # can repeat for multiple pre-seeded claims
```

- `target`: Free-text description of the system/API to explore (e.g., `"Anthropic SDK streaming"`)
- `--assume "<claim>"`: Pre-seed a claim as assumed-true without executing a proof script

Output: `.ll/learning-tests/<slug>.md` in `LearnTestRecord` format (FEAT-1285 schema); raw output at `.ll/learning-tests/raw/<slug>.txt`

## Integration Map

### Files to Modify
- `skills/explore-api/SKILL.md` — create (new skill)
- `README.md` — skill count, CLI count, table row, CLI subsection
- `CONTRIBUTING.md` — skill count, skills tree, module tree
- `.claude/CLAUDE.md` — skill count, CLI tools list
- `docs/ARCHITECTURE.md` — add learning test registry section

### Dependent Files (Callers/Importers)
- `ll-learning-tests` CLI (FEAT-1286) — invoked by skill for registry reads/writes
- `scripts/little_loops/learning_tests.py` (FEAT-1285) — underlying registry module

### Similar Patterns
- `skills/manage-issue/SKILL.md` — canonical multi-phase skill template to follow
- `skills/refine-issue/SKILL.md` — another multi-phase research skill using Bash tool

### Tests
- Manual: run `/ll:explore-api "Python pathlib"` and verify `.ll/learning-tests/python-pathlib.md` is created with at least one `pass` or `fail` assertion

### Documentation
- All doc files listed in "Files to Modify" are in scope per issue

### Configuration
- N/A — no config schema changes needed

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

## Impact

- **Priority**: P2 — Completes the Learning Test lifecycle: registry (FEAT-1285) and CLI (FEAT-1286) exist but are unusable without a guided skill entrypoint.
- **Effort**: Medium — New skill file plus doc updates across 4 files; no new Python code needed.
- **Risk**: Low — New isolated skill; no changes to existing behavior or public APIs.
- **Breaking Change**: No

## Labels

`feat`, `skill`, `learning-tests`, `captured`

---

**Open** | Created: 2026-04-25 | Priority: P2


## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `skills/explore-api/` directory ✓
- No `skills/explore-api/SKILL.md` ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:format-issue` - 2026-04-25T20:14:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e97fb3c-4c81-4d9a-b8ce-a2bcf181afa8.jsonl`
