---
id: BUG-3634
type: BUG
title: diff_stall evaluator fingerprints main tree instead of worktree child_working_dir
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T05:28:45Z'
---

# BUG-3634: diff_stall evaluator fingerprints main tree instead of worktree child_working_dir

## Summary

[Description extracted from input]

## Current Behavior

`evaluate_diff_stall` (`little_loops.fsm.evaluators`) runs its git commands
(`git ls-files`, `git hash-object`, `git rev-parse --show-toplevel`) with no
`cwd=` argument, so it always fingerprints the process's current working
directory — the main tree. A `diff_stall` state that lives inside a
`worktree:` child FSM (`executor.py` `child_working_dir`, ~:1232) fingerprints
the wrong tree: the main checkout, not the worktree where the child loop's
actual edits land.

## Expected Behavior

The evaluator fingerprints the worktree's own working directory when it runs
inside a `worktree:` child. `evaluate()` (`fsm/evaluators.py`) needs the
executor's resolved working directory threaded through to
`evaluate_diff_stall`/`_diff_stall_fingerprint`, and every `subprocess.run`
call inside the fingerprint helper needs a `cwd=` argument.

## Motivation

Discovered during BUG-3627 (diff_stall content-fingerprint rewrite). Explicitly
scoped out of that issue: "today the git commands run with no `cwd=`, so a
diff_stall state inside a `worktree:` child (`executor.py` ~:1232,
`child_working_dir`) fingerprints the main tree instead of the worktree...
the evaluator needs the executor's working dir threaded through to
`evaluate()`."

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related

- BUG-3627 — diff_stall content fingerprint (this gap is out of scope there).

## Status

**Open** | Created: 2026-09-27 | Priority: P4
