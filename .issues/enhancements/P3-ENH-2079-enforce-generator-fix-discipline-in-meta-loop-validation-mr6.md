---
id: ENH-2079
title: Enforce generator-fix discipline in meta-loop validation (MR-6)
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2079: Enforce generator-fix discipline in meta-loop validation (MR-6)

## Motivation

Meta-loops that generate YAML, issue files, or FSM states frequently hand-patch the emitted artifact rather than fixing the generation logic. Hand-patching creates fragile output that diverges from the generator on the next run, undermining iterative refinement. The stable approach is to fix the generator — the loop's action/transition rules — so every subsequent run produces correct output automatically.

## Proposed Solution

Add rule MR-6 to `ll-loop validate`: detect states where an `apply` action writes to a file that was also directly modified by a prior `shell` action in the same run (a proxy for hand-patching). Emit a WARNING with a suggestion to move the fix into the generating action. Document the rule in `CLAUDE.md` under Loop Authoring alongside MR-1 through MR-5. Add `generator_fix_ok: true` as a suppression flag for cases where direct post-processing is intentional.

## Implementation Steps

1. Add MR-6 rule definition to the `ll-loop validate` rule registry
2. Implement heuristic: detect `shell` actions modifying the same file target as an `apply` action in the same loop run
3. Emit WARNING severity with remediation suggestion
4. Add `generator_fix_ok: true` suppression flag support at loop top-level
5. Document MR-6 in `CLAUDE.md` under Loop Authoring (alongside MR-1 through MR-5)
6. Add test cases for MR-6 detection and suppression

## Acceptance Criteria

- [ ] `ll-loop validate` emits MR-6 WARNING when hand-patch pattern is detected
- [ ] WARNING message suggests moving the fix into the generator action
- [ ] `generator_fix_ok: true` suppresses the warning
- [ ] `CLAUDE.md` Loop Authoring section documents MR-6 with rationale
- [ ] Tests cover both detection and `generator_fix_ok` suppression

## Status

open
