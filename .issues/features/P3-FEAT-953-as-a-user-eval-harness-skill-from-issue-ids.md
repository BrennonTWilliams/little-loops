---
id: FEAT-953
type: FEAT
title: "as-a-user eval harness skill from issue IDs"
priority: P3
status: open
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# FEAT-953: as-a-user eval harness skill from issue IDs

## Summary

Create a new `/ll:create-eval-harness` skill (or similar name) that accepts one or more Issue IDs (open or completed), reads each issue's context and acceptance criteria, derives as-a-user evaluation criteria from that context, and generates a ready-to-run FSM harness YAML containing a `check_skill` evaluation gate that simulates a real user verifying the feature works as described.

## Current Behavior

There is no automated way to go from an issue file to a `check_skill`-based eval harness. Users must hand-author the harness YAML and write evaluation criteria manually, referencing the issue content by memory.

## Expected Behavior

Running `/ll:create-eval-harness FEAT-919 ENH-950` (or equivalent) should:
1. Read each named issue file and extract relevant context (title, use case, acceptance criteria, proposed solution)
2. Synthesize concise "did this work as a user would expect?" evaluation criteria from that context
3. Generate a harness YAML containing a `check_skill` state with those criteria embedded in an `llm_structured` evaluation prompt
4. Write the harness to `.loops/<slug>.yaml` and print validation output

For a single issue: produce a Variant A (single-shot) harness targeting the issue's skill.
For multiple issues: produce a Variant B (multi-item) harness that iterates over each issue's associated skill.

## Motivation

The `check_skill` evaluation gate is the highest-fidelity phase in the harness pipeline — it's the only phase that evaluates from a real user's perspective. But it's currently the hardest to author because it requires translating issue language into a precise, testable evaluation prompt. This skill closes that gap: an issue already contains the user story, use case, and acceptance criteria; those are exactly the inputs needed to define a meaningful as-a-user eval.

This also enables a "issue-to-harness-to-loop" workflow: refine an issue → generate a harness → run the loop unattended.

## Proposed Solution

### Skill: `/ll:create-eval-harness`

**Arguments**: one or more issue IDs (e.g., `FEAT-919`, `ENH-950`)
**Output**: `.loops/eval-harness-<slug>.yaml`

**Steps:**

1. **Resolve issue files** — use `ll-issues` to resolve each ID to a file path; support both open and completed issues.
2. **Extract evaluation context** — from each issue, extract:
   - `title` — the feature being evaluated
   - Use Case / User Story section — what does success look like to the user?
   - Proposed Solution / Implementation Steps — scope of what was built
   - Acceptance criteria (if present in any section)
3. **Synthesize as-a-user criteria** — compose an `llm_structured` evaluation prompt that asks "did the user experience work as the issue described?" Include:
   - The specific use case / workflow to exercise
   - The observable signal that indicates success
   - The failure signal (error, missing element, wrong behavior)
4. **Select harness variant**:
   - 1 issue → Variant A (single-shot) with `initial: execute`
   - 2+ issues → Variant B (multi-item) with `discover` state iterating over issue IDs
5. **Generate YAML** following the structure in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, with:
   - `execute` state: invokes the issue's associated skill (inferred from issue content or prompted)
   - `check_skill` state: runs as-a-user simulation with synthesized criteria
   - `check_invariants` state: diff size guard
6. **Validate** via `ll-loop validate` before writing and report result.

### Example output (single issue)

```yaml
name: "eval-harness-feat-919"
initial: execute
max_iterations: 5
states:
  execute:
    action: "/ll:manage-issue FEAT IMPLEMENT 919"
    action_type: prompt
    next: check_skill

  check_skill:
    action: >
      Use the JSON schema generation feature as described in FEAT-919.
      Navigate to the schema builder, provide a sample input, and confirm
      that a valid JSON schema is generated without errors.
    action_type: prompt
    timeout: 180
    evaluate:
      type: llm_structured
      prompt: >
        Did the skill successfully exercise the JSON schema generation flow
        from FEAT-919? Confirm: (1) the schema builder accepted input,
        (2) a valid JSON schema was returned, (3) no errors occurred.
        Answer YES only if all three conditions are met. Otherwise NO with
        which condition failed.
    on_yes: check_invariants
    on_no: execute

  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: done
    on_no: execute

  done:
    terminal: true
```

## Integration Map

### Files to Modify
- `skills/create-eval-harness/SKILL.md` — new skill definition
- `skills/create-eval-harness/skill.md` (or `prompt.md`) — implementation prompt
- `commands/create-eval-harness.md` — slash command entry point

### Dependent Files (Callers/Importers)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add reference to this skill in "Creating a Harness" section
- `skills/create-loop/loop-types.md` — optionally reference as an alternative entry point for check_skill harnesses
- `.claude-plugin/plugin.json` — register new skill

### Similar Patterns
- `skills/create-loop/` — existing harness creation wizard; this skill is a focused alternative for the `check_skill` path
- `skills/refine-issue/` — reads issue files and extracts structured content
- `scripts/little_loops/loops/harness-single-shot.yaml` — template for generated output
- `scripts/little_loops/loops/harness-multi-item.yaml` — template for multi-issue output

### Tests
- `scripts/tests/` — add unit tests for criteria synthesis logic and YAML generation

## Implementation Steps

1. Read `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (already loaded) and `docs/guides/LOOPS_GUIDE.md` to understand required YAML structure for `check_skill` harnesses
2. Create `skills/create-eval-harness/SKILL.md` with skill metadata
3. Implement the prompt/instruction file that drives:
   - Issue file resolution (via `ll-issues show <ID>`)
   - Context extraction (title, use case, proposed solution, acceptance criteria)
   - Criteria synthesis into `llm_structured` evaluation prompt
   - Variant A vs Variant B selection based on issue count
   - YAML generation and `ll-loop validate` call
4. Register in `commands/create-eval-harness.md` and `plugin.json`
5. Add a reference from `AUTOMATIC_HARNESSING_GUIDE.md` → "See also: `/ll:create-eval-harness`"
6. Write tests for the YAML generation logic

## Impact

- **Priority**: P3 — Useful workflow accelerator; not blocking anything current
- **Effort**: Medium — Requires issue parsing logic, criteria synthesis prompt, and YAML templating; no new infrastructure
- **Risk**: Low — Read-only issue parsing + file write; no destructive operations
- **Breaking Change**: No

## API/Interface

```bash
# Single issue → single-shot harness
/ll:create-eval-harness FEAT-919

# Multiple issues → multi-item harness
/ll:create-eval-harness FEAT-919 ENH-950

# Completed issue (harness to verify regression doesn't recur)
/ll:create-eval-harness BUG-347
```

Output file written to: `.loops/eval-harness-<slug>.yaml`

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Harness YAML structure, `check_skill` phase spec, evaluation pipeline |
| `docs/guides/LOOPS_GUIDE.md` | FSM field reference, evaluator catalog |
| `scripts/little_loops/loops/harness-single-shot.yaml` | Template for Variant A output |
| `scripts/little_loops/loops/harness-multi-item.yaml` | Template for Variant B output |

## Labels

`feature`, `loops`, `harness`, `eval`, `captured`

## Status

**Open** | Created: 2026-04-04 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdd75d9a-15c4-4632-b6fd-adac60caf156.jsonl`
