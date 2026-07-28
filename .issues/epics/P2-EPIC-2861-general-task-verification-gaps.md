---
id: EPIC-2861
status: done
priority: P2
captured_at: '2026-07-27T16:17:56Z'
discovered_date: 2026-07-27
discovered_by: capture-issue
labels:
- loops
- general-task
- verification
- fsm
relates_to:
- ENH-2857
- ENH-2858
- ENH-2859
- ENH-2860
completed_at: '2026-07-28T20:13:10Z'
---

# EPIC-2861: Close general-task verification gaps (postmortem remediation)

## Summary

Umbrella for the remediations from `POSTMORTEM-general-task-verification-gaps.md`: the
`little-loops-hermes` plugin was built across three `general-task` runs, shipped five
blocking defects, and every one passed the loop's verification gate (the July run
reported `{"verdict":"success","implemented":15,"failed_finals":0}` over a plan with
8 abandoned steps in the June runs). Root causes: (1) the abandon path launders a
failed hard blocker into a completed `[x]` step and a hardcoded success verdict;
(2) `define_done` derives criteria only from the plan, so unnamed properties are
checked by nobody and defective criteria are enforced faithfully; (3) delta static-
analysis gates grandfather rot and teach the worker to spread it; (4) same-agent
post-hoc tests repair the harness instead of the code; (5) no closing consistency
sweep catches invalidated docs/counts.

## Goal

A `general-task` run cannot report success while hard-blocker steps were abandoned,
and its DoD always contains mechanical, task-independent criteria covering the defect
classes that actually shipped. The abandonment-verdict convention becomes a validator
gate so other loops can't reinvent the bug.

## Children

- **ENH-2857** — Make step abandonment visible (`[!]`), counted (`abandoned` in summary.json), and blocking (`incomplete-abandoned` verdict; dependency halt). *Highest leverage; prevents defect 5.*
- **ENH-2858** — Plan-independent Standing Criteria block in `define_done` + absolute static-analysis gate framing. *Prevents defects 1, 2, 4 and suppression rot.*
- **ENH-2859** — Harness-workaround flag in `check_done` + closing consistency/doc-reconciliation sweep in `final_verify`. *Would have surfaced defect 1; prevents the "six tools" class.*
- **ENH-2860** — `fsm/validation.py` lint: abandonment must reach summary.json and downgrade the verdict; flag hardcoded success verdicts. *Blocked by ENH-2857.*

## Sequencing

ENH-2857 first (pure shell/awk, in-repo precedent in `auto-refine-and-implement.yaml`
ENH-2657), then ENH-2858 (prompt edit); ENH-2859 anytime (prompt-only); ENH-2860 last
(lint must not fail the builtin loops it audits).

## Non-Goals

- Changing the `plan` prompt — the postmortem showed the plans were reasonable.
- A general "disagree with the spec" mechanism in `check_done`.
- Changing `run_final_tests`' ENH-2244 test-suite baseline compare.

## Session Log
- `/ll:capture-issue` - 2026-07-27T16:17:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3601f984-5d3e-4c48-a9b5-5cb709fc86b3.jsonl`
