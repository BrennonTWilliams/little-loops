---
id: EPIC-3041
title: Host-agnostic advisor
type: EPIC
priority: P3
status: open
verify_verdict: VALID
discovered_date: 2026-08-04
labels:
- planning-hub
relates_to:
- FEAT-3300
- FEAT-3301
---

# EPIC-3041: Host-agnostic advisor

## Summary

Four-slice rollout of a host-agnostic advisor consult path: a one-shot
escalation to a second, stronger — possibly different-provider — model that
returns a structured verdict (`{recommendation, risks[], confidence,
dissent}`) before the primary model commits to an approach.

## Children

- **FEAT-3037** — Host-agnostic advisor: invocation mechanism, config,
  capability floor, and `ll-doctor` check (slice 1). **Decomposed**
  (scored Very Large) into three grandchildren:
  - **FEAT-3042** — Advisor transport: shared `run_blocking_json` helper
  - **FEAT-3043** — Advisor configuration: `AdvisorConfig` block
  - **FEAT-3044** — Advisor core: `ll-advise` CLI, capability floor, and
    `ll-doctor` check (depends on FEAT-3042, FEAT-3043). **Decomposed**
    (2026-08-10) into four great-grandchildren:
    - **FEAT-3108** — Capability floor: `MODEL_RANKS`, `rank_model`,
      `check_floor` — **done**
    - **FEAT-3120** — Advisor `consult()` core and `ll-advise` CLI
    - **FEAT-3121** — `/ll:advise` skill wrapping the `ll-advise` CLI
    - **FEAT-3122** — `ll-doctor` advisor-reachability check
- **FEAT-3038** — Advisor signal-gated auto-consults and per-task budget:
  wires `confidence_gate`/`pre_done` triggers and `max_consults_per_task`
  (slice 2) — **done** (**Decomposed** into FEAT-3116 (budget/task-identity),
  FEAT-3117 (`confidence_gate` wiring), and FEAT-3118 (`pre_done` wiring),
  all still open)
- **FEAT-3039** — Advisor FSM stall escalation and routable verdicts: lets
  FSM loops escalate on stall and route on the verdict (slice 3)
- **FEAT-3040** — Advisor consult telemetry in `history.db`: persists
  consults for `ll-ctx-stats` and downstream analytics (slice 4)

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-04:_

Verdict: **OUTDATED** (corrected). FEAT-3037 ("slice 1") shows `status: done`
but its Resolution is a decomposition, not an implementation — it was split
into FEAT-3042/FEAT-3043/FEAT-3044 (all still `open`), which the `## Children`
section previously did not mention. Updated the section above to reflect the
decomposition. `epic-progress` rollup walks `parent:` transitively, so the
grandchildren already count toward this epic's progress mechanically; this
was a documentation gap, not a rollup bug.

Also found and fixed a stale dependency: FEAT-3038 and FEAT-3039 both
declared `depends_on: [3037]`. Since FEAT-3037 is `status: done`, dependency
resolvers treat that edge as satisfied even though the actual slice-1
deliverables don't exist yet (they're still open under FEAT-3042/3043/3044).
Repointed both to `depends_on: [FEAT-3044]` (FEAT-3044 already correctly
depends on FEAT-3042 and FEAT-3043).

No active required decisions-log rules to check (log has no entries).
Parent backlinks on all four direct children (FEAT-3037/3038/3039/3040)
correctly resolve to `EPIC-3041`.

## Verification Notes (2026-08-12)

Verdict: **NON_VALID (OUTDATED)**. FEAT-3038 is now `status: done`, but the
`## Children` section above still described it as active "slice 2" work
without a completion marker. Updated the FEAT-3038 bullet to flag it as
**done**.

## Verification Notes (2026-08-14)

Verdict: **VALID**. Cross-checked every entry in `## Children` against current
issue state: FEAT-3037 `done` (decomposed shell, per convention), FEAT-3042/
FEAT-3043 `open`, FEAT-3044 `done` (decomposed shell) depending correctly on
FEAT-3042/FEAT-3043, FEAT-3108 `done`, FEAT-3120/FEAT-3121/FEAT-3122 `open`,
FEAT-3038 `done` decomposed into FEAT-3116/FEAT-3117/FEAT-3118 (all `open`,
matching the text), FEAT-3039/FEAT-3040 `open`. `depends_on` repoints noted in
the 2026-08-04 entry hold: FEAT-3038 and FEAT-3039 both depend on FEAT-3044
(not the stale FEAT-3037 edge). Parent backlinks on FEAT-3037/3038/3039/3040
all resolve to `EPIC-3041`. No `## Blocked By`/`## Blocks` sections on the
epic itself. No active required decisions-log rules (`ll-issues decisions
list --type rule --enforcement required --active-only` returned none). The
frontmatter `verify_verdict: NON_VALID` predating this pass appears to be a
leftover from a prior `--check`-mode run (which persists the verdict field
without writing Verification Notes) — corrected to `VALID` here.

## Session Log
- `/ll:verify-issues` - 2026-08-14T16:47:56 - `c9c216e7-2d10-4e53-9fc0-c38b57955ad8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-13T22:00:52 - `e21c16b3-391d-4ef2-80c4-decd2dced91f.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:07:49 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:53 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:verify-issues` - 2026-08-04T21:29:47 - `e72897bf-a708-4dcd-aeaa-907564ef9e34.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This epic's FEAT-3039 (advisor FSM stall escalation with routable verdicts) and FEAT-3038 (per-task budget, `max_consults_per_task`) add a budget/stall-triggered FSM routing primitive. EPIC-3022's ENH-3020 independently adds a per-state/iteration token/wall-clock budget config and routing hook to the same `fsm/executor.py` / `fsm-loop-schema.json` surface. Before implementing FEAT-3039, confirm whether its stall-escalation route reuses ENH-3020's budget-hook mechanism/route naming convention or is a genuinely separate FSM extension point.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): FEAT-3044 (advisor core) was
decomposed on 2026-08-10 into FEAT-3108 (**done**), FEAT-3120, FEAT-3121, and
FEAT-3122 (related issue: FEAT-3122 carries `parent: FEAT-3044`), and
FEAT-3038 was decomposed into FEAT-3116, FEAT-3117, and FEAT-3118. The
Children section above now tracks that generation; any future rollup or
scoping of this epic should reference the open grandchildren rather than the
decomposed FEAT-3038/FEAT-3044 shells.
