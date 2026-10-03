---
id: EPIC-3694
title: Autodev Gate & Citation False-Failure Hardening
type: EPIC
priority: P3
status: open
captured_at: "2026-10-02T17:34:29Z"
discovered_date: 2026-10-02
discovered_by: link-epics
relates_to: []
---

# EPIC-3694: Autodev Gate & Citation False-Failure Hardening

## Summary

Group of related issues about autodev/refine gates failing on non-defects: env leakage into the quality gate's test run, transient corpus-ratchet test failures, verify-issues citation checking instability, and missing repair routes for citation-only / coverage-gap verify findings.

## Children

Recommended order (re-reviewed 2026-10-03 with an Opus second opinion): **replay BUG-3689 trigger + AC#1 → BUG-3702 → BUG-3695 → ENH-3697 (ENH-3690 cancelled: the replay passed)** (done: BUG-3689, BUG-3691, BUG-3708) (updated 2026-10-03: BUG-3691 split into a detector half and BUG-3708 for the B8 prose; ENH-3690 and BUG-3695 both declare BUG-3708 as a dependency; serialize their shared `commands/verify-issues.md` edits).

1. **BUG-3689** — Autodev quality gate false-fails on env leakage (11 env-driven tests; shared `HERMETIC_ENV_VARS` constant + gate `unset` + `pin_terminal_size`) (**done**, P2)
2. **ENH-3697** — Make corpus-ratchet gate tests read the committed `.issues` tree, not the working tree (open, P3) — supersedes ENH-3692; **re-scoped 2026-10-03:** narrow to the prose-dependency sweep via in-memory `git cat-file` HEAD reads behind a gate-only env flag; decide against a clean-checkout gate first
3. **BUG-3691** — verify-issues citation checking is unstable across passes (**done**, P3) — **detector half**: extend `ll-issues format-check` (defined-in vs imported-in rule, line-past-EOF, bare-filename resolution) and emit an `examined_refs` payload; all new findings **advisory** until ENH-3690 promotes them; no new CLI
4. **BUG-3708** — verify-issues check B8: defer to format-check `examined_refs` for citation findings (**done**, P3) — prose half of the BUG-3691 split (`45481a2ba`)
5. ~~**ENH-3690**~~ (**cancelled**, 2026-10-03; superseded by BUG-3708) — refine-to-ready-issue: NON_VALID citation-only findings get a repair route (open, P3) — **re-scoped 2026-10-03:** BUG-3691/BUG-3708 landed and make both BUG-3689 triggers verdict-neutral under B8; implement only if a live replay still ends `NON_VALID`, with mechanical `correction_target` eligibility
6. **BUG-3695** — refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria (open, P3) — unblocked (BUG-3708 done; rescore); live-evaluation AC split to a follow-up; sibling of ENH-3690 (same "verdict has no working remedy" class); reviewed 2026-10-03 with an evidence-gated AC/Step repair and unchanged budget
- ~~**ENH-3692**~~ — baseline-aware code-run-gate (**cancelled**, won't-do): the two motivating "pre-existing" failures pass on a clean `main` and only went red from uncommitted `.issues/` working-tree state, so the mechanism could not have rescued them and carried High masking risk; superseded by ENH-3697.
- **BUG-3702** — refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state (open, P4) — largely fixed by BUG-3705's 24h age guard; re-scoped to one parametrize case + two-tier docstring (~10 min), then close
- **ENH-3718** — Live-evaluate reconcile-issue --from-verify-evidence DIRECTIVE_DRIFT repair (open)



## Acceptance Criteria

_Owner for AC#1/AC#2 verification: the 2026-10-03 BUG-3689 replay (deterministic half done via `ll-issues format-check`: bare `runner_spec.py:335` → `path_resolves ok`, `feed.py:terminal_size()` → advisory mislocated; live `verify-issues --check` half also run 2026-10-03: neither citation yields a non-VALID finding under B8 — see ENH-3690; the full BUG-3688-scenario autodev rerun for AC#1 is still pending)._

- A rerun of the BUG-3688 scenario reaches the quality gate green: none of the 11 env-sensitive tests fail with `LL_PYTHON` and a wide `COLUMNS` set, and the two corpus-ratchet tests do not fail from uncommitted `.issues/` edits.
- Repeated format-check calls over an unchanged issue and code snapshot give identical mechanical citation findings; B8 consumes only examined occurrence/property results, with semantic content/premise judgments remaining model-decidable. Citation repair/promotion follows ENH-3690's measured policy.
- A run whose only verify findings are deterministic citation-shaped findings is repaired in-loop rather than ending `GATE_UNMET`; premise-changing findings still persist as `NON_VALID`.