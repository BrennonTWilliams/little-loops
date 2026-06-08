---
id: ENH-2017
title: "rn-build — Auto-normalize malformed spec before tech_research"
type: ENH
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-08T01:43:18Z'
discovered_date: 2026-06-08
discovered_by: capture-issue
size: Small
blocked_by:
- ENH-2012
relates_to:
- ENH-2012
- ENH-2014
labels:
- loops
- rn-build
---

# ENH-2017: `rn-build` — Auto-normalize malformed spec before `tech_research`

## Summary

`rn-build` currently passes whatever Markdown the user provides directly into
`tech_research`, with no check that the spec contains the sections needed for
useful output. Users should be able to provide a loosely structured spec and
have the loop normalize it to the standard format before research begins, rather
than needing to pre-format it correctly.

## Current Behavior

`rn-build` accepts a user-provided Markdown spec file and passes it directly to
the `tech_research` state without validating that it contains the required
sections (`## Overview`, `## Core Features`, `## Acceptance Criteria`). Users
who provide a loosely-structured spec — such as a single descriptive paragraph —
encounter downstream states that receive incomplete input, producing
lower-quality research and design artifacts.

## Expected Behavior

When `rn-build` receives a spec missing the three required sections, a
`normalize_spec` pre-gate runs: a non-LLM `check_structure` evaluator detects
the gap, an `llm_normalize` prompt state infers and populates the missing
sections from the content present, and a `verify_structure` evaluator confirms
all three sections exist in the output. The normalized spec is written to
`${context.run_dir}/spec_normalized.md`; the original file is never modified.
Downstream states receive the normalized path. Specs that already contain all
three required sections skip normalization entirely. Specs that cannot be
normalized (e.g., empty file) cause the loop to abort with a clear error
message referencing `specs/SPEC_TEMPLATE.md`.

## Motivation

ENH-2012 establishes `specs/SPEC_TEMPLATE.md` as the ideal input format
(Overview + Core Features + Acceptance Criteria required; Data Model, Non-Goals,
Tech Constraints optional). But requiring users to match that format exactly
raises the barrier to entry. A normalization pre-gate lets the template serve as
the *target* rather than a strict prerequisite — the loop accepts rough input and
self-heals before downstream states run.

## Proposed Solution

Add a `normalize_spec` state to `rn-build.yaml` that runs immediately before
`tech_research`:

### State design

```
normalize_spec
  ├── check_structure (exit_code evaluator)
  │     grep -c "## Overview\|## Core Features\|## Acceptance Criteria" $spec_path
  │     exit 0 if count == 3  →  on_pass: tech_research  (skip normalization)
  │     exit 1 if count < 3   →  on_fail: llm_normalize
  │
  ├── llm_normalize (prompt state)
  │     Infer and populate missing sections from the content present,
  │     targeting specs/SPEC_TEMPLATE.md format. Write normalized
  │     content to ${context.run_dir}/spec_normalized.md.
  │
  └── verify_structure (exit_code evaluator — satisfies MR-1)
        grep -c "## Overview\|## Core Features\|## Acceptance Criteria" \
          ${context.run_dir}/spec_normalized.md
        exit 0 if count == 3  →  on_pass: tech_research (using normalized path)
        exit 1                →  on_fail: abort with clear error message
```

### Key design decisions

- The structural check is a **non-LLM evaluator** (grep exit code), satisfying
  MR-1 (meta-loop rule: `check_semantic` must be paired with a non-LLM evaluator).
- The normalized file is written to `${context.run_dir}/spec_normalized.md`,
  not in-place — the original spec is never mutated (per MR-3 isolation).
- `tech_research` and all downstream states receive the normalized path when
  normalization ran; they receive the original path when it was skipped.
- If normalization produces a spec that still fails the structural check, the
  loop aborts with a message directing the user to `specs/SPEC_TEMPLATE.md`
  rather than silently continuing with a bad spec.

## Implementation Steps

1. Add `normalize_spec` state to `rn-build.yaml` immediately before `tech_research`
2. Implement `check_structure` as an `exit_code` evaluator using grep
3. Implement `llm_normalize` as a `prompt` state targeting `SPEC_TEMPLATE.md` format
4. Implement `verify_structure` as a second `exit_code` evaluator (MR-1 compliance)
5. Thread the `normalized_spec_path` context variable through `tech_research` and
   downstream states so they use the correct path after normalization
6. Add a fallback abort message pointing to `specs/SPEC_TEMPLATE.md`
7. Run `ll-loop validate rn-build` — confirm no MR-1/MR-3/MR-4 violations

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — add `normalize_spec` state and thread normalized path

### Dependent Files (Callers/Importers)
- `tech_research`, `design_artifacts`, `scope_project` states in `rn-build.yaml` — must consume normalized path

### Blocks On
- ENH-2012 must ship first: `specs/SPEC_TEMPLATE.md` must exist before the
  normalizer can reference it as the target format

### Similar Patterns
- `rn-refine.yaml` pre-gate states for input validation

### Tests
- N/A — YAML-only change; validate with `ll-loop validate rn-build` (see Implementation Steps #7) and manual integration tests per Acceptance Criteria

### Documentation
- `specs/SPEC_GUIDE.md` — update if present to note that malformed specs are auto-normalized before research begins
- N/A for other docs

### Configuration
- N/A

## Acceptance Criteria

- Running `ll-loop run rn-build path/to/minimal_spec.md` with a spec that has
  only a one-paragraph description (no section headers) produces a
  `spec_normalized.md` in `run_dir` with all three required sections.
- Running with a fully-formed spec (all three headers present) skips
  normalization entirely (no `spec_normalized.md` written, `llm_normalize`
  state not entered).
- Running with a spec that cannot be normalized (e.g., empty file) aborts with
  a clear error message referencing `specs/SPEC_TEMPLATE.md`.
- `ll-loop validate rn-build` reports no MR-1, MR-3, or MR-4 violations.

## Scope Boundaries

- Normalization only runs on the three required sections; optional sections
  (Data Model, Non-Goals, Tech Constraints) are inferred and added if the LLM
  can derive them, but their absence never causes abort
- No changes to `tech_research`, `design_artifacts`, or `scope_project` logic —
  only the input path they receive may change
- The original spec file is never modified

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low — new pre-gate state; existing FSM paths unchanged if spec is well-formed
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-08

## Session Log
- `/ll:format-issue` - 2026-06-08T03:27:31 - `8ca79972-3964-4396-bf2e-0ac0f3566189.jsonl`
- `/ll:capture-issue` - 2026-06-08T01:43:18Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
