---
id: BUG-2224
title: refine-issue implements code instead of documenting gaps
type: BUG
priority: P3
status: done
captured_at: '2026-06-18T23:58:00Z'
completed_at: '2026-06-18T23:58:00Z'
discovered_date: '2026-06-18'
discovered_by: post-mortem
labels:
- refine-issue
- allowed-tools
- llm-behavior
---

# BUG-2224: refine-issue implements code instead of documenting gaps

## Summary

`/ll:refine-issue` modified source code files (`scripts/little_loops/cli/learning_tests.py`,
`scripts/tests/test_cli_learning_tests.py`) instead of restricting its edits to the issue
file under `.issues/`. The command's `allowed-tools` listed bare `Edit` (no path restriction),
so when research agents surfaced a small, well-specified implementation gap, the LLM pivoted
from "document this" to "implement this."

## Root Cause

The `allowed-tools` frontmatter in `commands/refine-issue.md` and
`skills/ll-refine-issue/SKILL.md` specified `Edit` without a path glob:

```yaml
allowed-tools:
  - Edit          # unrestricted — any file editable
```

The command body directed Claude to use `Edit` on the issue file, but contained no explicit
prohibition against editing code files. When research surfaced an exact, implementable gap
(missing `--stale-aware` flag in `cmd_check`), the LLM reasoned that completing the
implementation was the helpful action — the tool was available, the files were already read,
and the gap was trivial to close.

## Trigger Conditions

The failure mode requires all three:

1. **Issue is `status: done` with a documented incomplete implementation** — the rn-implement
   loop committed ENH-2208 partially (steps 1–5 only) and marked it `done`. The issue file
   contained an explicit note: "What did NOT ship: step 6 — the `--stale-aware` flag."
2. **Gap is tiny and fully specified** — exact file, function, and argument syntax were
   present in the issue's Implementation Steps.
3. **`Edit` tool unrestricted** — no path glob prevented editing files outside `.issues/`.

Without condition 1, research findings are treated as documentation targets. Without
condition 3, the Edit call would fail at the tool layer regardless of LLM reasoning.

## Why It Started Happening Now

This is the first time the rn-implement loop closed an issue (`done`) before all
implementation steps were verified complete. Prior refine-issue runs operated on `open`
issues where "filling gaps" unambiguously meant enriching documentation. On a `done` issue
with a known missing step, the LLM interprets "fill the gap" as "complete the implementation."

## Fix Applied

Two changes in commit `a1ced67f` (2026-06-18):

**1. Path-restricted `Edit` in both command and skill frontmatter:**

```yaml
# commands/refine-issue.md and skills/ll-refine-issue/SKILL.md
allowed-tools:
  - Edit(.issues/**)    # restricted to issue files only
```

**2. Explicit scope boundary instruction added to Step 5a of `commands/refine-issue.md`:**

> **Scope boundary**: Only use `Edit` to modify files under `.issues/`. If research reveals
> a missing implementation (code, tests, config), document it in the issue — write it as a
> gap finding under `## Codebase Research Findings`. Do NOT implement code, even when the
> gap is small and the implementation is obvious.

The tool-level restriction is the hard gate; the instruction reinforces it so Claude does
not attempt a doomed Edit call on code files.

## Files Changed

- `commands/refine-issue.md` — `Edit` → `Edit(.issues/**)` in frontmatter; scope boundary added to Step 5a
- `skills/ll-refine-issue/SKILL.md` — `Edit` → `Edit(.issues/**)` in frontmatter

## Session Log
- `hook:posttooluse-status-done` - 2026-06-19T00:05:36 - `3b4902af-3b9d-4ebf-9d5c-aa30643400cb.jsonl`

- `post-mortem` - 2026-06-18T23:58:00Z - (current session)
