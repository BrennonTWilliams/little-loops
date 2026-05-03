---
captured_at: "2026-05-01T17:33:26Z"
discovered_date: 2026-05-01
discovered_by: capture-issue
---

# FEAT-1310: verify-issue-loop skill (FSM loop generator from issue acceptance criteria)

## Summary

Create a new skill `/ll:verify-issue-loop` that mirrors `/ll:create-eval-from-issues` but emits an FSM loop YAML instead of an eval harness. Given an issue ID, the skill reads its acceptance criteria and synthesizes a custom loop where each criterion becomes a dedicated verify-state.

## Motivation

`/ll:create-eval-from-issues` generates eval harnesses (which exercise a feature as a user would and judge the quality of the experience). There is no parallel command for generating an FSM loop that *verifies* the implementation by stepping through each acceptance criterion. Today, authors of verification loops have to hand-build YAML, copy boilerplate, and manually decompose acceptance criteria into checks — losing the structured, criterion-by-criterion traceability that issue files already encode.

A `verify-issue-loop` skill closes that gap: one issue ID in, one ready-to-run verification loop out, with one verify-state per criterion.

## Current Behavior

There is no skill that generates an FSM verification loop from an issue's acceptance criteria. `/ll:create-eval-from-issues` produces eval harnesses (which exercise a feature as a user would), but verification loops must be hand-built — authors copy YAML boilerplate and manually decompose criteria into checks, losing the structured per-criterion traceability the issue file already encodes.

## Use Case

Author has just finished implementing FEAT-1234 with five acceptance criteria. They run:

```
/ll:verify-issue-loop FEAT-1234
```

The skill resolves the issue, extracts the five acceptance criteria, and writes `.loops/verify-FEAT-1234-<slug>.yaml`. The generated loop contains:

- One `verify-criterion-N` state per criterion, each with a focused prompt scoped to that single criterion and a structured pass/fail evaluator.
- Linear or fan-out transitions between verify-states (linear by default).
- A terminal `done` state when all verify-states pass; a terminal `failed` state when any criterion fails (with a captured reason).

The author then runs `ll-loop run .loops/verify-FEAT-1234-<slug>.yaml` and gets a per-criterion verification report.

## Expected Behavior

- Argument: `<issue-id>` (single ID for v1; multi-issue support deferred).
- Resolves the issue file via `ll-issues show <ID> --json`. Accepts open or completed issues.
- Reads the issue file and parses the Acceptance Criteria section into discrete criterion strings (e.g., bullet/numbered items).
- For each criterion, synthesizes:
  - A verify-state name (`verify-criterion-1`, `verify-criterion-2`, …).
  - A focused natural-language prompt that describes *how to confirm this specific criterion* against the current codebase / runtime.
  - An `llm_structured` evaluator with pass/fail (and a short reason) scoped to just that criterion.
- Wires verify-states sequentially: state N transitions to state N+1 on pass, to a shared `failed` state on fail. Final pass transitions to `done`.
- Writes the loop YAML to `.loops/verify-<ISSUE-ID>-<slug>.yaml`.
- Validates the generated file with `ll-loop validate` and reports the result, mirroring the create-eval-from-issues UX.
- If the issue has no Acceptance Criteria section (or it is empty), fail clearly with guidance to run `/ll:refine-issue` or `/ll:format-issue` first.

## API/Interface

New skill: `skills/verify-issue-loop/SKILL.md`

```
/ll:verify-issue-loop <issue-id>
```

- `argument-hint: "<issue-id>"`
- `allowed-tools`: `Bash(ll-issues:*, ll-loop:*, mkdir:*)`, `Read`, `Write`
- Output file path: `.loops/verify-<ISSUE-ID>-<slug>.yaml`
- Help/registry entry added to `/ll:help` index in CLAUDE.md (Automation & Loops group).

## Implementation Steps

1. Scaffold `skills/verify-issue-loop/SKILL.md` by copying `skills/create-eval-from-issues/SKILL.md` as a starting point.
2. Replace harness-generation logic with FSM loop generation:
   - Reuse the issue resolution + parsing block (`ll-issues show ... --json`, then read file).
   - Extract Acceptance Criteria into a list (handle `- `, `* `, and `1.` styles).
   - Synthesize verify-state nodes: name, prompt, `llm_structured` evaluator.
   - Wire transitions (linear pass-chain, shared `failed` terminal, `done` terminal).
3. Use existing FSM loop schema (see other YAMLs under `.loops/` and `loops/` for shape — states, transitions, evaluators).
4. Write the YAML, then run `ll-loop validate <path>` and surface validation output.
5. Add registration: append the skill to `.claude/CLAUDE.md` "Automation & Loops" line and ensure `/ll:help` discovers it (skills are auto-discovered via `skills/*/SKILL.md` glob — verify no extra wiring needed).
6. Tests: add a unit/integration test in `scripts/tests/` that runs the skill against a fixture issue with N acceptance criteria and asserts the generated YAML has N verify-states + `done` + `failed`, and passes `ll-loop validate`.

## Acceptance Criteria

- [ ] `skills/verify-issue-loop/SKILL.md` exists with frontmatter, description, trigger keywords, and argument-hint mirroring `create-eval-from-issues`.
- [ ] Running `/ll:verify-issue-loop <ID>` against an issue with N acceptance criteria writes a YAML with exactly N verify-states.
- [ ] Each verify-state has a prompt scoped to one criterion and an `llm_structured` pass/fail evaluator.
- [ ] Verify-states transition linearly on pass; any failure transitions to a shared `failed` terminal state with reason captured.
- [ ] Final verify-state transitions to `done` on pass.
- [ ] Generated YAML passes `ll-loop validate` without errors.
- [ ] Issue with no Acceptance Criteria section produces a clear error referencing `/ll:refine-issue` / `/ll:format-issue`, and writes no file.
- [ ] Skill is listed in `/ll:help` output and CLAUDE.md "Automation & Loops" group.
- [ ] Test in `scripts/tests/` covers a multi-criterion fixture and asserts state count, transitions, and `ll-loop validate` success.

## Impact

- **Priority**: P3 - Reduces friction for verification authoring; nice-to-have, not blocking.
- **Effort**: Medium - New skill scaffold mirroring `create-eval-from-issues` + criterion parser + FSM emitter + `ll-loop validate` integration + fixture-based test.
- **Risk**: Low - Generates a new YAML file; does not modify existing skills or runtime behavior.
- **Breaking Change**: No - Purely additive.

## Labels

feature, skill, verification, fsm, loops, captured

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/create-eval-from-issues/SKILL.md` | Sibling skill to mirror — argument parsing, issue resolution, YAML emission, `ll-loop validate` UX |
| `docs/ARCHITECTURE.md` | FSM loop architecture and state/transition model |
| `.claude/CLAUDE.md` | Skill registration / Automation & Loops grouping |

## Session Log
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:format-issue` - 2026-05-01T17:38:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1483ec77-4cf9-4aca-8312-065f15a52a5f.jsonl`
- `/ll:capture-issue` - 2026-05-01T17:33:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a6d2d86-ddb4-4191-bb20-7505a1373a52.jsonl`

---

## Status
- **Status**: Open
- **Discovered**: 2026-05-01
- **Discovered by**: capture-issue

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Once FEAT-1308 (loop YAML `from:` template inheritance) lands, the YAML emitted by this skill SHOULD use `from: verify-issue-base` (or similar shared base loop) and override only the per-criterion verify states, instead of emitting fully-expanded ~100-line YAML each time. If FEAT-1310 ships before FEAT-1308, the initial implementation may emit standalone YAML, but a follow-up should refactor the emitter to use inheritance. Do not block FEAT-1310 on FEAT-1308.
