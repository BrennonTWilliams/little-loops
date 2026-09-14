---
id: EPIC-3475
title: Harden ll-harness Verdicts
type: EPIC
priority: P3
status: open
captured_at: "2026-09-14T00:00:00Z"
discovered_date: 2026-09-14
discovered_by: link-epics
relates_to: []
---

# EPIC-3475: Harden ll-harness Verdicts

## Summary

Group of 4 related issues: widen the ll-harness evidence surface beyond stdout — stderr, written files, and named side effects; unit-test an eval's grading logic deterministically before it is allowed to grade a live-model run; score harness runs on a named efficiency vector, not only on a pass/fail outcome; benchmark every self-improvement candidate against a frozen external baseline, not only the incumbent.

## Children

- **ENH-3462** — Widen the ll-harness evidence surface beyond stdout — stderr, written files, and named side effects (open)
- **ENH-3463** — Unit-test an eval's grading logic deterministically before it is allowed to grade a live-model run (open)
- **ENH-3464** — Score harness runs on a named efficiency vector, not only on a pass/fail outcome (open)
- **ENH-3465** — Benchmark every self-improvement candidate against a frozen external baseline, not only the incumbent (open)
- **ENH-3476** — Persist ll-harness widened evidence (channels + side effects) to harness_events (open)
