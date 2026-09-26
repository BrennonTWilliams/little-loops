---
id: ENH-3613
type: ENH
title: Autodev summary.json splits cancelled from implemented closures
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T05:02:45Z'
parent: EPIC-3565
decision_needed: false
blocks:
- FEAT-3573
- ENH-3600
---

# ENH-3613: Autodev summary.json splits cancelled from implemented closures

## Summary

autodev's `finalize_done` puts `cancelled` closures in the same `closed` bucket as
implemented ones. The run summary cannot tell "implemented and closed" apart from "closed
without implementation". Split out of FEAT-3573. This split sets the `summary.json` shape
that FEAT-3573 extends and ENH-3600 preserves.

## Current Behavior

`finalize_done` (`scripts/little_loops/loops/autodev.yaml`, state header ~`:3115`) promotes
every staged ID whose status is `done|completed|cancelled` to `autodev-passed.txt` (the
promotion `case` arm, ~`:3133`). After the `case` arm the status is discarded. The human
summary prints one `Passed (N)` line (~`:3237`) and `summary.json` (printf ~`:3317`)
reports one `closed` count. The current keys are `verdict`, `closed`, `not_closed`,
`skipped`, `gate_blocked`, `decision_unresolved`, `not_started`, `inflight_unresolved`,
`abandoned`, `stop_reason`, `pending` and `proof_gate_infra` (12 keys; BUG-3603 added
`proof_gate_infra`).

Cancelled closures reach `finalize_done` when implementation (or `/ll:ready-issue`) closes
an issue as invalid; `verify_impl_closed` (~`:1198`) accepts `cancelled` as closed for the
same reason.

## Expected Behavior

- `closed` stays the total count, for back-compat.
- Two new keys are added: `closed_implemented` (`done`/`completed`) and `closed_cancelled`
  (`cancelled`). The rule `closed_implemented + closed_cancelled == closed` always holds.
- The human-readable summary shows the split and names the cancelled IDs, for example
  `Passed (3): BUG-1,FEAT-1,FEAT-2  (2 implemented, 1 cancelled: FEAT-2)`. The suffix is
  printed only when `closed_cancelled > 0`.
- Verdict behavior: see **Verdict policy** below (open decision).

## Motivation

A run that cancels every issue reports the same `closed` count as a run that implements
them all. Operators, `/ll:audit-loop-run`, and ENH-3600's run-record ledger need the split.

## Proposed Solution

### Design (revised 2026-09-26)

Count cancellations **in memory inside the `finalize_done` promotion loop**. Do not add a
ledger file.

- In the `cancelled` case, append the ID to a shell variable `CANCELLED_IDS` next to the
  existing bare-ID `autodev-passed.txt` append. Split the `case` arm into
  `done|completed)` and `cancelled)`; both still append to `autodev-passed.txt`.
- `CLOSED_CANCELLED` = count of `CANCELLED_IDS` (`grep -c '[^[:space:]]' || true` idiom,
  empty → 0). `CLOSED_IMPLEMENTED` = `PASSED_COUNT - CLOSED_CANCELLED`.
- Append `"closed_implemented":%s,"closed_cancelled":%s` at the end of the `summary.json`
  printf format and argument list, after `proof_gate_infra`.

Why the sum rule holds by construction:
- `autodev-passed.txt` is written only by `finalize_done` (BUG-2908; pinned by
  `test_check_passed_stages_instead_of_passes`), and `finalize_done` runs once per run
  directory (it routes only to the `done`/`failed` terminals).
- `STAGED_IDS` is already deduped by `sort -u`, so each cancelled ID is counted once, and
  every counted ID was also appended to `autodev-passed.txt`, so it is in `PASSED_IDS`.
- `CLOSED_IMPLEMENTED` is derived by subtraction, so the two keys always sum to `closed`
  even if `autodev-passed.txt` held extra IDs.

Why no ledger file (supersedes the earlier "Option B — `autodev-cancelled.txt`" selection):
the status is only observable inside the promotion loop, and that loop is the only
producer of `autodev-passed.txt`. A persisted ledger would add an `init` truncation line,
an init-truncation test, resumed-run "ledger absent" handling, and an
intersection-with-`autodev-passed.txt` step, none of which buys anything. ENH-3600 moves
`finalize_done` into Python and removes handshake files, so a new ledger would be deleted
soon after it landed.

`autodev-passed.txt` keeps one bare ID per line, because `finalize_done`'s own
`grep -qxF "$INFLIGHT"` check (~`:3210`) and `auto-refine-and-implement.yaml` `finalize`
(`sort -u` → `comm -23`, ~`:1088-:1095`) read it.

### Verdict policy (open decision)

The ladder keys on `PASSED_COUNT` (~`:3295-:3315`), so a cancelled-only run currently
yields `verdict: success`. This contradicts the precedent set by **BUG-3449** for the
parent loop: `auto-refine-and-implement` `finalize` counts only `status: done` as closed,
because counting cancellations "could flip verdict to success on a run that closed nothing"
(pinned by `test_finalize_does_not_count_cancelled_as_closed`, `test_builtin_loops.py`
~`:5364`). After this issue, autodev's `closed_implemented` has the same meaning as the
parent's `closed`.

**Option A**: Keep the verdict ladder unchanged. A cancelled closure still counts toward
`success`/`partial`. The new keys are reporting-only. Document the divergence from BUG-3449
in the `audit-loop-run` Step 6a paragraph: autodev's `closed` means "verified terminal
status, not phantom", and `closed > 0` with `closed_implemented == 0` means closed without
implementation. Smallest change; no existing verdict fixture moves.

**Option B**: Key `success`/`partial` on `CLOSED_IMPLEMENTED > 0`. A run whose only closures
are cancellations falls through the ladder: `phantom` if anything is unverified or
abandoned, otherwise `not_started`/`no-op`. Aligns autodev with BUG-3449. Cost: a verdict
change visible to `ll-loop audit` and parent loops, plus a new all-cancelled verdict test.
Cancellation is not an infra failure, so check that `no-op` is the right landing verdict
rather than adding a dedicated one.

> **Selected:** Option B — matches the BUG-3449 precedent pinned by `test_finalize_does_not_count_cancelled_as_closed`; a run that implemented nothing must not report `success`.

### Decision Rationale

**Selected option:** Option B — key `success`/`partial` on `CLOSED_IMPLEMENTED > 0`.

**Reasoning:** The parent loop already refuses to count cancellations as closed (BUG-3449), so
autodev's `closed_implemented` should carry the same meaning in the verdict. Reporting-only keys
(Option A) would leave `success` on a run that closed nothing, which is the failure BUG-3449 fixed.
Implementation must confirm `not_started`/`no-op` is the right landing verdict for an
all-cancelled run (no dedicated verdict).

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A | 1 | 3 | 3 | 3 | 10/12 |
| B | 3 | 2 | 3 | 2 | 10/12 |

**Key evidence:** Tie on total; broken by Consistency per the scoring rule. Evidence is the
BUG-3449 precedent and its pinning test (`test_builtin_loops.py` ~`:5364`) cited above. Scored from
the issue's own citations; no separate per-option agent sweep was run.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `finalize_done` only: split the promotion
  `case` arm, derive the two counts, add the `Passed` line suffix, append the two keys to
  the `summary.json` printf. Under Option B, also the verdict ladder. `init` is **not**
  touched.
- `skills/audit-loop-run/SKILL.md` — Step 6a: add a bolded per-key paragraph after the
  BUG-3603 `proof_gate_infra` paragraph (~`:275`). It must say how to read the keys, not
  just list them: `closed > 0` with `closed_implemented == 0` is "closed without
  implementation", and autodev's `closed_implemented` corresponds to the parent loop's
  `closed` (BUG-3449). End with "additive; older `summary.json` files will lack them —
  treat absence as no split data, and fall back to `closed`." File is 464 lines against the
  500 cap.
- `docs/guides/LOOPS_REFERENCE.md` — no page lists autodev's `summary.json` keys. The only
  key-level mention is the BUG-3603 sentence at the end of the "Diagram omissions"
  paragraph (~`:1081`: "…surfaces as a dedicated `Proof-gate-infra` summary bucket and
  `proof_gate_infra` `summary.json` key."). Add one sentence after it naming
  `closed_implemented`/`closed_cancelled`, the sum rule, and the `Passed` line suffix.

### Dependent Files
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `finalize` (~`:1088`,
  `:1254-:1260`) — reads `autodev-passed.txt` and computes its own `closed`; unaffected
  because cancelled IDs stay in `autodev-passed.txt` and the bare-ID format is unchanged.
- `scripts/little_loops/loops/autodev.yaml` `finalize_rate_limited` — routes into
  `finalize_done`, so early exits also emit the new keys; no separate edit.
- `scripts/little_loops/fsm/persistence.py`, `scripts/little_loops/cli/loop/audit.py`,
  `scripts/little_loops/cli/loop/evidence.py`, `scripts/little_loops/hooks/pre_compact_handoff.py`
  — shape-agnostic `summary.json` consumers. Adding keys is safe. No consumer reads
  autodev's `closed` via `jq` or parses the human `Passed (N):` line.

_Wiring pass added by `/ll:wire-issue` (Option B verdict change):_
- `scripts/little_loops/loops/autodev.yaml` `finalize_done` exit routing (`case "$VERDICT"`,
  ~`:3323`) — only `phantom` exits 1; `success`/`partial`/`no-op`/`not_started` exit 0. An
  all-cancelled run moves `success` → `no-op` (or `not_started`) with the **same exit code
  (0)**, so the FSM terminal (`done`) and the `shell_exit` fragment routing are unchanged.
  A mixed cancelled + unverified run moves `partial` → `phantom` (exit 1 → `failed`); this is
  the only exit-code change Option B introduces.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `finalize` — confirmed it reads
  `autodev-passed.txt`/`autodev-skipped.txt` and the child exit code, not autodev's
  `summary.json` `verdict`, so the verdict change does not reach it.
- `docs/guides/LOOPS_REFERENCE.md` autodev section — no sentence documents autodev's verdict
  ladder (`success`/`partial`/`phantom`/`no-op`); the only verdict vocabulary listed (~`:1009`)
  is the parent loop's. Include the Option B rule (`success`/`partial` require
  `closed_implemented > 0`) in the sentence already planned for `closed_implemented`/`closed_cancelled`.

### Tests
- `scripts/tests/test_builtin_loops.py` `TestAutodevLoop` (`_run_finalize_done` ~`:7481`):
  - New tests with a **per-ID** `ll-issues` stub (existing stubs ignore `$2` and return one
    fixed status). Sketch: `case "$2" in FEAT-1) echo '{"status":"Completed"}';;
    FEAT-2) echo '{"status":"Cancelled"}';; esac`. These are the real display values
    (`show.py` `_STATUS_DISPLAY` ~`:108`: `done` → `"Completed"`, `cancelled` →
    `"Cancelled"`).
  - Fixtures: all implemented, all cancelled, mixed. Assert both keys, the sum rule, the
    `Passed` line suffix naming the cancelled ID (absent when none are cancelled), and that
    `autodev-passed.txt` still holds bare IDs matchable by `grep -qxF`.
  - Dedupe: a cancelled ID appended twice to `autodev-staged.txt` counts once.
  - Nothing staged (extend `test_finalize_done_no_op_when_nothing_staged` ~`:7550`): both
    keys are 0.
  - Extend `test_finalize_done_promotes_verified_closure_to_passed` (~`:7524`) and
    `test_finalize_done_mixed_run_still_resolves_success` (~`:7828`) to assert
    `closed_implemented == 1`, `closed_cancelled == 0`.
  - Verdict: the all-cancelled fixture pins `success` (Option A) or the chosen
    fall-through verdict (Option B).
- `scripts/tests/test_audit_loop_run_skill.py` — add
  `test_skill_step6a_reads_closed_implemented_cancelled_keys` modeled on
  `test_skill_step6a_reads_enh_2404_keys` (~`:144`) /
  `test_skill_step6a_reads_closed_via_recovery_key` (~`:157`): slice `## Step 6:` to
  `## Step 7:`, assert both keys and "additive".
- _Wiring pass added by `/ll:wire-issue`:_ Option B verdict fixtures to add in
  `TestAutodevLoop` next to `test_finalize_done_not_started_verdict_and_no_double_count`
  (~`:7702`) and `test_finalize_done_reports_phantom_when_staged_but_not_closed` (~`:7429`):
  (a) all-cancelled → `no-op`, exit 0, `closed == closed_cancelled`; (b) all-cancelled plus a
  not-started ID → `not_started`; (c) cancelled + staged-but-unverified → `phantom`, exit 1;
  (d) cancelled + implemented → `success`. No existing `finalize_done` fixture in
  `~:7400-:7860` uses a `Cancelled` stub (the stub at ~`:7440` returns `Open`), so no
  existing verdict assertion breaks. The `skip_cancelled` tests (~`:7983-:8000`) exercise a
  different state (`autodev-skipped.txt`) and are unaffected.
- Will not break: `test_fsm_topology.py` autodev state count (no state is added);
  `TestInterpSweepBaseline` (no baseline entry for `finalize_done`; keep new logic in plain
  shell with `$${...}` escaping, no heredoc or `python3 -c` block containing
  `${context.run_dir}`). No test pins autodev's full `summary.json` key set or the
  `Passed (N)` text.
- Run after the SKILL.md and LOOPS_REFERENCE.md edits: `test_enh494_skill_companions.py`,
  `test_docs_audience_gate.py`, `test_adapt_skills_for_codex.py`, `test_adapters.py`.
  No host mirror of `audit-loop-run` exists under `.gemini/`, `.kimi-code/` or `.qwen/`.

### Conventions in Force
- **Counts use `grep -c '[^[:space:]]' || true` followed by `[ -z "$COUNT" ] && COUNT=0`**
  (BUG-2827) — evidence: `finalize_done` counting block.
- **New `summary.json` keys are appended at the end of both the printf format string and
  the argument list; keys are flat scalars** — evidence: `proof_gate_infra` (BUG-3603).
- **FSM escaping**: bash `${...}` in the action must be `$${...}`; interpolation covers the
  whole action including comments — evidence: `$${PASSED_LIST:-none}` on the `Passed` line.
- **Docs convention for a new additive key**: a bolded per-key paragraph in
  `audit-loop-run` Step 6a ending with the "additive … treat absence as …" sentence, plus an
  inline mention in `LOOPS_REFERENCE.md`.

## Implementation Steps

1. Wait for ENH-3610 to land. Its uncommitted changes to `autodev.yaml` and the
   `check_decision_at_dequeue` states named in `LOOPS_REFERENCE.md:1081` overlap this edit.
2. Verdict policy resolved: Option B (see Decision Rationale).
3. `finalize_done`: split the promotion `case` arm into `done|completed)` and
   `cancelled)` (both append to `autodev-passed.txt`; `cancelled)` also accumulates
   `CANCELLED_IDS`). Derive `CLOSED_CANCELLED` and `CLOSED_IMPLEMENTED`. Add the `Passed`
   line suffix. Append both keys to the printf. Under Option B, change the ladder's success
   and partial conditions to `CLOSED_IMPLEMENTED`.
4. Add the `TestAutodevLoop` tests and the `test_audit_loop_run_skill.py` test.
5. Add the `audit-loop-run` Step 6a paragraph and the `LOOPS_REFERENCE.md` sentence.
6. Run the full suite plus the gates listed under Tests.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update the comment block above the verdict ladder in `finalize_done` (BUG-2908 comment,
  ~`:3292`) and the exit-routing comment (~`:3324`) — both say a verdict of `success`/`partial`
  means "verifiably closed"; reword to "verifiably implemented" under Option B.
- Add the four Option B verdict fixtures listed under Tests (all-cancelled, all-cancelled +
  not-started, cancelled + unverified, cancelled + implemented).
- In the `audit-loop-run` Step 6a paragraph, state the Option B verdict rule and that an
  all-cancelled run reports `no-op` with `closed > 0`, so readers do not treat `closed > 0`
  as evidence of `success`.
- In the `LOOPS_REFERENCE.md` sentence, include the Option B rule alongside the key names.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low (Option A) / Low-Medium (Option B changes a verdict)

## Program Design

### Types

- `summary.json` (autodev `finalize_done`) gains two integer keys, `closed_implemented` and
  `closed_cancelled`, appended after `proof_gate_infra` (14 keys total). The rule
  `closed_implemented + closed_cancelled == closed` always holds.
- No new ledger file. `autodev-passed.txt` stays bare IDs, one per line.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/show.py:786`; `ll-issues show --json` supplies the display-cased `status` that `finalize_done` lowercases before bucketing. Unchanged.

### Call Path

`autodev.yaml:finalize_done` → per staged ID `ll-issues show --json` (`cmd_show`, `show.py:786`) → lowercased status → `done|completed` appends to `autodev-passed.txt`; `cancelled` appends to `autodev-passed.txt` and to in-memory `CANCELLED_IDS` → `PASSED_COUNT`, `CLOSED_CANCELLED`, `CLOSED_IMPLEMENTED = PASSED_COUNT - CLOSED_CANCELLED` → `Passed` summary line + `summary.json` printf.

### Decision Rules

- `done` and `completed` count as implemented. `cancelled` counts as cancelled.
- A cancelled closure still counts in `closed` and still lands in `autodev-passed.txt`.
- A cancelled closure does not count toward `success`/`partial`; those key on `CLOSED_IMPLEMENTED > 0` (Verdict policy: Option B).
- The `autodev-passed.txt` format does not change (bare IDs).

## Acceptance Criteria

- [ ] `summary.json` has `closed_implemented` and `closed_cancelled`, and their sum equals `closed` for all-implemented, all-cancelled, mixed, and nothing-staged runs
- [ ] The `Passed` summary line names the cancelled IDs when any exist, and is unchanged when none do
- [ ] `autodev-passed.txt` format is unchanged (bare IDs, `grep -qxF`-matchable)
- [ ] No new ledger file and no `init` change
- [ ] Verdict behavior matches the chosen **Verdict policy** option. Under Option A, the verdict is unchanged for all existing `TestAutodevLoop` fixtures.
- [ ] `audit-loop-run` Step 6a explains how to read the keys (including closed-without-implementation and the BUG-3449 relationship); `LOOPS_REFERENCE.md` names them

## Scope Boundaries

- FEAT-3573 adds the quality-gate buckets (`quality_failed`, `quality_gate_infra`) on top
  of this shape. This issue does not add them.
- The parent `auto-refine-and-implement` summary is out of scope. It already excludes
  cancellations from `closed` (BUG-3449).
- Moving `finalize_done` into Python is ENH-3600.

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-26T06:20:29 - `3f6bcacf-9a24-433d-b1ef-920a7913f4ff.jsonl`
- `/ll:decide-issue` - 2026-09-26T06:18:44 - `8ade3bc4-e17f-4d10-aa22-4a48a2f01bb0.jsonl`
- `/ll:wire-issue` - 2026-09-26T06:05:49 - `7d4fe7ad-aaa1-48a1-b0d0-90c193fc70c2.jsonl`
- `/ll:decide-issue` - 2026-09-26T06:01:33 - `95a3ad40-ecc6-4e5c-befd-9be7a282a332.jsonl`
- `/ll:refine-issue` - 2026-09-26T05:58:48 - `e3c050f9-1131-496e-87dd-53db8a85423f.jsonl`
