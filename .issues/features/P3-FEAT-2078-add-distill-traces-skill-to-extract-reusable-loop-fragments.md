---
id: FEAT-2078
title: Add distill-traces skill to extract reusable loop fragments from history
type: FEAT
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
relates_to: [EPIC-2087]
---

# FEAT-2078: Add distill-traces skill to extract reusable loop fragments from history

## Motivation

Successful loop execution traces already exist in `.ll/history.db` and ll-logs, but no skill mines them into reusable loop YAML fragments or Python helpers. Distilling behavioral traces into a small reference library — rather than documenting strategy in prose — gives future loop runs a concrete scaffold to build on.

## Use Case

A developer wants to reuse patterns from past successful runs of `rn-plan`. They invoke `/ll:distill-traces rn-plan --min-success 3` and receive YAML state templates and transition patterns in `loops/lib/rn-plan/`, along with a `primitives.md` summary they can reference when authoring or modifying the loop.

## Proposed Solution

Create a `ll:distill-traces` skill that:
1. Queries `ll-session` for successful runs of a named loop
2. Extracts the action sequences and shell primitives used across those runs
3. Writes reusable YAML fragments (state templates, common transition patterns) to `loops/lib/<loop-name>/`
4. Accepts a loop name and a minimum success count threshold
5. Produces a `primitives.md` summary alongside the YAML fragments
6. Optionally updates loop-suggester's context with the extracted patterns

## Implementation Steps

1. Create `skills/distill-traces/SKILL.md` with invocation spec and argument docs
2. Implement query logic against `ll-session search` / `ll-session recent` for successful loop runs
3. Parse action sequences from run transcripts to extract reusable state patterns
4. Write YAML fragment files to `loops/lib/<loop-name>/` with a `primitives.md` index
5. Add optional `--update-suggester` flag to push extracted patterns into loop-suggester context

## Acceptance Criteria

- [ ] `ll:distill-traces <loop-name>` queries history and outputs YAML fragments
- [ ] `loops/lib/<loop-name>/primitives.md` is created/updated with extracted patterns
- [ ] `--min-success N` threshold parameter filters runs
- [ ] Skill gracefully handles loops with no successful history

## Status

open
