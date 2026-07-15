---
discovered_commit: 6f81ca029f3c40a05520d5f1d8536fdd0a8723cc
discovered_branch: main
discovered_date: 2026-07-15T00:00:00Z
discovered_by: capture-issue
status: open
relates_to: [FEAT-2652, BUG-2651]
labels: [ready-issue, verifier, worktree, epic-branches]
---

# ENH-2653: `ready-issue` must name the branch it checked and not reject on suspected base-branch mismatch

## Summary

The `ready-issue` verifier decides whether an issue's cited symbols exist by
reading files in the current working directory, then reports its verdict against
"the current branch" — without ever naming which branch that is. Inside an EPIC
worktree forked from the wrong base, this yields a confident false `NOT_READY`
("the current branch has no `Tableau`, `center`, … surface") for symbols that
exist exactly where the EPIC intends them. The verifier even noticed the
mismatch in one run — *"the original symbols are present on the alternate
`refactor/tableau-third-revision` branch"* — classified it as a `concern`, and
rejected the issue anyway.

Make the verifier branch-transparent: always print the branch it inspected, and
treat "symbols absent but plausibly on another base" as a **concern**, not a
rejection.

## Current Behavior

- `commands/ready-issue.md` drives an LLM that reads files in `cwd`. It has no
  `target_branch` / `base_branch` parameter (the only branch-adjacent call is
  `ll-history-context {{issue_id}}` at ~line 132, which is branch-agnostic).
- The verifier never runs `git rev-parse --abbrev-ref HEAD`, so its "current
  branch has no X" claim is unfalsifiable from the output — the reader can't tell
  which branch was checked.
- A symbol-absence that is really a base-branch mismatch (the EPIC was sprinted
  off `main` but the symbols live on an unmerged feature branch) is scored as a
  hard `NOT_READY`, producing a silent false negative the user only catches by
  reading the per-issue transcript.

## Expected Behavior

- The verifier **always states which branch it inspected** (`git rev-parse
  --abbrev-ref HEAD`, plus the worktree path when in one) in its output.
- When a cited symbol is absent, the verifier must consider "this may be a
  base-branch mismatch" before rejecting: if the issue is an EPIC child (or the
  EPIC declares a `base_branch` — see FEAT-2652) and the symbol could live on
  that other base, it raises a **concern** ("symbols not on inspected branch
  `<X>`; EPIC target base may differ") instead of a `NOT_READY` verdict.
- If the EPIC declares no target base, flag "EPIC declared no target_branch" as a
  readiness concern rather than silently assuming `cwd` is authoritative.

## Proposed Solution

Two tiers, ship the cheap half first:

1. **Prompt-only (cheap):** Amend `commands/ready-issue.md` so the verifier runs
   and reports `git rev-parse --abbrev-ref HEAD`, names the branch in every
   symbol-existence claim, and downgrades suspected-base-mismatch absences to a
   concern rather than a rejection.
2. **Optional `--target-branch` (larger):** Accept a target branch and run
   symbol-existence checks against `git show <branch>:<file>` (or a sidecar
   worktree) instead of `cwd`. Populated from FEAT-2652's EPIC `base_branch`
   field when available.

## Scope Boundaries

**In scope:**
- Making the `ready-issue` verifier report the branch/worktree it inspected.
- Downgrading suspected base-branch-mismatch symbol absences from `NOT_READY` to
  a concern.
- Optional `--target-branch` to run symbol checks against another ref.

**Out of scope:**
- Choosing or creating the EPIC's base branch (owned by FEAT-2652).
- The FTS5 hyphenated-ID bug in `ll-history-context` (owned by BUG-2651).
- Changing the overall `partial` vs `failed` verdict taxonomy of the loop
  (FEAT-2652's validation gate handles the hard-stop escalation).

## Impact

Medium. The prompt-only tier alone converts a silent false negative into a
visible, actionable concern and is near-zero-cost. Combined with FEAT-2652 it
closes the wrong-base false-`NOT_READY` class end to end. Improves trust in
`sprint-refine-and-implement` verdicts.

## Status

open — captured from consumer-project run findings. Guardrail that complements
root-cause fix FEAT-2652; the prompt-only tier is shippable independently.
