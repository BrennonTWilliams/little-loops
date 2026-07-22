---
id: ENH-2727
title: autodev refine_current on_error collapses infra kills into the refine_failed
  ledger reason
type: ENH
status: done
priority: P2
captured_at: '2026-07-21T22:10:00Z'
completed_at: '2026-07-22T16:16:48Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- termination-taxonomy
relates_to:
- ENH-1679
- ENH-2522
- ENH-2404
decision_needed: false
confidence_score: 95
outcome_confidence: 82
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2727: autodev `refine_current.on_error` collapses infra kills into the `refine_failed` ledger reason

## Summary

In `scripts/little_loops/loops/autodev.yaml`, `refine_current` routes
`on_no: skip_inflight` and `on_error: skip_inflight` — the same target.
`skip_inflight` appends a hard-coded reason:

```
echo "${captured.input.output}  refine_failed" >> ${context.run_dir}/autodev-skipped.txt
```

An infrastructure failure (host CLI SIGTERM'd, OOM, crash) is therefore ledgered
identically to a genuine refine-quality failure. ENH-1679 fixed the earlier
`on_yes == on_no` laundering; the `on_error == on_no` collapse remains.

## Current Behavior

`refine_current` routes both `on_no: skip_inflight` and `on_error: skip_inflight`
to the same state, which appends a hard-coded `refine_failed` reason. An
infrastructure kill (SIGTERM/OOM/crash) is ledgered identically to a genuine
refine-quality failure in `autodev-skipped.txt`.

## Expected Behavior

An infra-class termination is ledgered with a distinct reason code
(`refine_failed_infra`) and surfaced as a separate, re-runnable bucket in the
`done` summary. Quality failures continue to write `refine_failed`. See
`## Proposed Fix` and the selected **Option A** below.

## Impact

Operators and downstream triage (`ll-issues deferred-triage`,
`skipped_breakdown`) cannot distinguish "refine produced a bad result" (needs
human attention) from "the process was killed mid-flight; just re-run it"
(recoverable). Misattributed infra kills waste triage attention and mask
transient failures.

## Current Pain Point

Infra kills silently masquerade as quality failures, so a re-runnable transient
looks like a real refine defect — the same laundering ENH-1679 fixed for the
`on_yes == on_no` case, now recurring on the `on_error == on_no` collapse.

## Scope Boundaries

- **In scope:** loop-layer changes only — `autodev.yaml` (new `skip_inflight_infra`
  state + `done` summary line) and `refine-to-ready-issue.yaml` (emit a
  termination-class sentinel near `diagnose`), per the selected Option A.
- **Out of scope:** FSM executor / `StateConfig` schema changes (Option B, rejected
  2/12). Reason-agnostic downstream consumers
  (`auto-refine-and-implement.yaml` `finalize`) need no edits.

## Evidence (run `2026-07-21T214941-autodev`)

The refine sub-loop's `refine_issue` action exited **143 (SIGTERM, external kill
after 156s)**, yet `autodev-skipped.txt` records `ENH-2722  refine_failed` — the
operator-facing summary and any downstream triage (`ll-issues deferred-triage`,
`skipped_breakdown`) cannot distinguish "refine produced a bad result" from "the
process was killed mid-flight; just re-run it".

## Proposed Fix

Route `on_error` to a distinct state (e.g. `skip_inflight_infra`) that ledgers a
different reason code (`infra_error` or `refine_killed`), mirroring the
ENH-2005 artifact-channel guidance that infra crashes be attributed separately.
Alternatively keep one state but interpolate a reason derived from the sub-loop
verdict/exit code.

> **Decided (2026-07-22, coordinated with [[BUG-2731]]'s `/ll:refine-issue`
> pass):** new-state shape (Option A above) selected via `/ll:decide-issue`
> on BUG-2731 (10/12 vs 7/12 — see BUG-2731's Decision Rationale). Reason-code
> literal: `refine_failed_infra`, not `infra_error`/`refine_killed` — derived
> from `record_gate_error`'s `GATE_FAILED_INFRA` precedent (stem-suffix on the
> existing failure token), case-matched to `skip_inflight`'s lowercase
> convention. See BUG-2731's Proposed Solution for the full reasoning; both
> issues should land on this same literal string.

## Acceptance Criteria

- [x] `on_error` from `refine_current` produces a ledger entry with a reason code
      distinct from `refine_failed` (routed to `skip_inflight_infra` →
      `refine_failed_infra`)
- [x] The `done` summary surfaces infra-skipped issues separately (re-runnable)
      via a dedicated `Infra-skipped (N): … (transient kill — just re-run)` line
- [x] `ll-loop validate autodev` passes; existing routing tests updated
- [x] **(added by refine)** An infra kill that the sub-loop diagnoses at its
      `failed` terminal (the *evidenced* exit-143 path — see Routing Reality
      below) is ledgered as `refine_failed_infra`, not just the rarer
      `terminated_by == "error"` path. Handled by the `classify_terminal`
      sentinel that `skip_inflight` consumes on the `on_failure` path.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-22):_

### ⚠ Routing Reality — the proposed `on_error` reroute does NOT catch the evidenced case

`refine_current` is a sub-loop delegate. `FSMExecutor._execute_sub_loop`
(`scripts/little_loops/fsm/executor.py:980-996`) maps the child's termination to
the parent's routes as follows:

| Child termination | `terminated_by` | Parent route consulted |
|---|---|---|
| reached `done` terminal | `terminal` | `on_yes` |
| reached a **non-`done` terminal** (e.g. `failed`) | `terminal` | `on_no` → falls back to `on_failure` |
| raised a runtime error/exception | `error` | `on_error` → falls back to `on_no` |
| **signal / timeout / max_iterations** | (else) | `on_no` → falls back to `on_failure` — **`on_error` is never consulted** (executor.py:994-996) |

The evidence run's exit-143 (SIGTERM) does **not** reach the parent as
`terminated_by == "error"`. Trace it through
`scripts/little_loops/loops/refine-to-ready-issue.yaml`:

1. `refine_issue` action exits 143 → its `on_error: diagnose` (line 281).
2. `diagnose` (`action_type: prompt`, lines 391-436) is an **LLM** step that
   writes a one-paragraph *prose* summary and routes `next: failed` (line 436).
   It writes **no** machine-readable infra-vs-quality sentinel to `run_dir`.
3. `failed:` (lines 438-439) is a bare terminal → child ends
   `terminated_by == "terminal"`, `final_state == "failed"`.
4. Parent `refine_current`: non-`done` terminal → `on_no` → (BUG-2611 fallback)
   `on_failure` → `skip_inflight` → writes `refine_failed`.

**Consequence:** rerouting only `on_error: skip_inflight_infra` (the literal
"Proposed Fix" / decided Option A) would leave the exact evidenced exit-143
scenario still ledgered as `refine_failed`. The `on_error` path only fires for a
child *runtime exception*, which is not what a SIGTERM/OOM external kill produces.
To ledger the evidenced infra kill as `refine_failed_infra`, the sub-loop's
termination class must be made visible to autodev's skip path. See options below.

### Implementation approaches (a genuine fork — decide before implementing)

**Option A (sub-loop emits a termination-class sentinel — self-contained in the
loop layer):** Have `refine-to-ready-issue` write a machine-readable class file
(e.g. `${context.run_dir}/refine-terminal-class.txt` = `infra` when the failing
state's `${prev.exit_code}` ∈ {143, 137, 124}, else `quality`) in/adjacent to
`diagnose` before `next: failed`. Then autodev's skip path (a new
`skip_inflight` pre-branch, or a `classify_skip` state) reads it and picks the
reason token — `refine_failed_infra` vs `refine_failed`. This is coupled to
[[BUG-2731]] (exit-143 classification), which owns the exit-code taxonomy;
ENH-2727 becomes "consume BUG-2731's signal." Keeps `on_failure: skip_inflight`
and (per BUG-2611) leaves `on_no` unset.

> **Selected:** Option A (sub-loop emits a termination-class sentinel) — only
> approach that captures the *evidenced* `diagnose → failed` path, self-contained
> in the loop layer (reuses the `refine-broke-down`/`autodev-broke-down` handshake
> and the `GATE_FAILED_INFRA` reason-token precedent), 10/12 vs Option B's 2/12.

**Option B (executor exposes signal/timeout as a distinct route key):** Add an
`on_signal` / `on_infra` route the `else` branch at `executor.py:994-996`
consults, plus a `StateConfig` schema field. Then autodev can route the
signal-termination class directly to `skip_inflight_infra`. Larger blast radius
(schema + executor + every delegate state), but distinguishes infra at the
routing layer instead of via a sentinel file. Note this still would **not** catch
the evidenced case as-is, because that case reaches a `failed` *terminal*
(`terminated_by == "terminal"`), not a signal termination of the sub-loop itself
— the SIGTERM was of an inner action, absorbed by `diagnose`. So Option B alone
also needs the sub-loop to propagate the class. In practice Option A is the
minimal correct fix.

**Recommended:** Option A — it is the only approach that captures the *evidenced*
`diagnose → failed` path, is self-contained in the loop layer, and composes with
the already-decided `skip_inflight_infra` / `refine_failed_infra` shape.

> The pre-existing "Decided (2026-07-22)" note above selected the new-state shape
> and the `refine_failed_infra` literal — both still correct and preserved. What
> the research adds is that the *trigger* cannot be `on_error` alone; the reason
> token must be selected from a sub-loop termination-class signal.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option A (sub-loop emits a termination-class sentinel — self-contained in the loop layer)

**Reasoning**: Option A is the only approach that catches the *evidenced* exit-143
scenario, which reaches autodev as a `failed` **terminal** (`terminated_by ==
"terminal"`) after `diagnose` absorbs the SIGTERM — not as the signal termination
Option B's new route key would consult. Option A reuses two already-tested plumbing
patterns in this exact loop pair: the `refine-broke-down` → `autodev-broke-down`
sub-loop-to-parent file handshake enabled by `context_passthrough: true` (shared
`run_dir`, executor.py:848-855), and the `GATE_FAILED_INFRA` stem-suffix reason-token
convention (rn-remediate.yaml:572-593). Option B, even fully implemented, would not
fix the bug on its own and touches 6+ files (schema, executor, route_table,
validation, CLI) versus Option A's two loop YAMLs plus one new autodev state.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A (sub-loop sentinel) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| B (executor route key) | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- Option A: Direct precedent exists twice in this loop pair (`write_broke_down` →
  `copy_broke_down`); test templates (`test_finalize_skipped_breakdown_aggregates_by_reason`,
  `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`) apply directly.
  The one new piece is exit-code-set (`∈ {143,137,124}`) classification in a shell state
  spliced before the LLM `diagnose` (reached from 8+ fan-in paths) — reuse score 2.
- Option B: `terminated_by` already carries the `system_signal` granularity and
  `extra_routes` offers a schema-light hook, but the evidenced case never reaches the
  `_execute_sub_loop` `else` branch it modifies (executor.py:994-996), so it is
  insufficient alone — reuse score 1.

### Integration Map

#### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add `skip_inflight_infra` sibling
  of `skip_inflight` (lines 151-165) writing `refine_failed_infra`; select it
  from the sub-loop termination class (per Option A). Keep `on_failure:
  skip_inflight` and do **not** add an explicit `on_no:` (BUG-2611 constraint,
  lines 136-142).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — emit the
  termination-class sentinel at/near `diagnose` (lines 391-436) before `next:
  failed` (Option A).
- `scripts/little_loops/loops/autodev.yaml` `done` state (lines 1219-1261) — add
  a dedicated `Infra-skipped (N): … (re-run)` summary line (mirrors the existing
  `Gate-blocked` / `Decision-unresolved` lines at 1250-1255) to satisfy AC #2.
  The generic `Skipped` list currently lumps all reasons together.

#### Reason-agnostic downstream — NO change needed
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `finalize`
  `SKIPPED_BREAKDOWN` (lines 841-861) splits each `ID  REASON` line on first
  whitespace and buckets by token — a new `refine_failed_infra` token surfaces
  automatically in `summary.json`'s `skipped_breakdown`. No edit required.
- `skills/audit-loop-run/SKILL.md` (~line 290) documents `skipped_breakdown`
  semantics; optionally note `refine_failed_infra` is a re-runnable (non-quality)
  bucket.

#### Reason-code convention (existing writers to `autodev-skipped.txt`)
Two-space-delimited `ID  REASON`, lowercase snake_case (ENH-2404). Existing
tokens: `refine_failed` (autodev.yaml:160), `decomposed` (627, 917),
`resolved_by_subloop` (732, 1125, 1204), `oversized_atomic` (1129),
`low_readiness` (1209). Ledger truncated at loop start (lines 57-59). Precedent
for the `_infra` stem-suffix: `record_gate_error` in
`scripts/little_loops/loops/rn-remediate.yaml:572-593` writes `GATE_FAILED_INFRA`
(sibling of `GATE_FAILED`).

### Tests to add / update
- `scripts/tests/test_builtin_loops.py` — existing routing block for
  `refine_current` / `skip_inflight` lives at ~lines 3824-3917. Add parallel
  assertions for `skip_inflight_infra` (exists, `action_type: shell`, writes
  `autodev-skipped.txt`, clears `autodev-inflight`, `next`/`on_error:
  dequeue_next`). **Keep** `test_refine_current_compiled_on_no_resolves_to_skip_inflight`
  green — compiled `on_no` must still resolve to `skip_inflight` (not the infra
  state), i.e. do not divert `on_failure`.
- Shell-execution test modeled on
  `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight`
  (test_builtin_loops.py:5086-5112) asserting `"ID  refine_failed_infra"` is
  written for the infra path.
- Round-trip test modeled on
  `test_finalize_skipped_breakdown_aggregates_by_reason`
  (test_builtin_loops.py:3081-3110) proving `refine_failed_infra` buckets
  distinctly in `skipped_breakdown`.
- If Option A adds an exit-code branch, add a `refine-to-ready-issue` termination
  fixture exercising exit 143 → `infra` class (no such test exists today).

### Related / precedent
- Sub-loop routing semantics: `FSMExecutor._execute_sub_loop`
  (`scripts/little_loops/fsm/executor.py:775-996`).
- Prior partial split (`on_yes == on_no` laundering): [[ENH-1679]]. BUG-2611
  `on_no`-shadow constraint: autodev.yaml:136-142. Coordinated exit-code
  classification: [[BUG-2731]] (deferred P1) — ENH-2727's correct fix depends on
  its signal.

## Resolution

Implemented **Option A** (sub-loop emits a termination-class sentinel), loop-layer
only. Two YAMLs plus one new autodev state, exactly as the Integration Map scoped:

- **`refine-to-ready-issue.yaml`** — new `classify_terminal` shell state inserted
  between `diagnose` and `failed`. It reads the failing state's own captured exit
  code (`${captured.refine_issue.exit_code?}` etc. — BUG-2726 already captures those;
  `${prev.exit_code}` is diagnose's own 0 by then) and writes
  `${context.run_dir}/refine-terminal-class` = `infra` when any is `143/137/124` (or a
  negative signal code), else `quality`. `diagnose.next` now points at it.
- **`autodev.yaml`** —
  - `skip_inflight` converted to a `shell_exit` classifier: no sentinel or
    `class=quality` → writes `refine_failed`, clears inflight, exit 0 → `on_yes:
    dequeue_next`; `class=infra` → exit 1 → `on_no: skip_inflight_infra` (defers the
    ledger write). `refine_current.on_failure` stays `skip_inflight`, so the compiled
    `on_no` fallback is preserved (BUG-2611).
  - new `skip_inflight_infra` sibling writes `refine_failed_infra` and clears inflight.
  - `refine_current.on_error` → `skip_inflight_infra` directly (a child runtime
    exception is a crash with no refine verdict — infra-class, satisfies AC #1
    literally, complementary to the sentinel path that catches the evidenced
    exit-143 `failed`-terminal case).
  - `done` summary excludes `refine_failed_infra` lines from the generic `Skipped`
    bucket and adds a dedicated `Infra-skipped (N): … (transient kill — just re-run)`
    line.

Downstream `auto-refine-and-implement.yaml` `finalize`/`skipped_breakdown` needed no
change — it splits `ID  REASON` on first whitespace, so `refine_failed_infra` buckets
automatically (verified by a new round-trip test). Added a re-runnable-bucket note to
`skills/audit-loop-run/SKILL.md`.

**Tests:** updated `test_refine_current_error_routes_to_skip_inflight` →
`…_infra`, `test_diagnose_routes_to_failed` → `…_classify_terminal`, and
`test_skip_inflight_routes_to_dequeue_next` (now `shell_exit` on_yes/on_no). Added
`classify_terminal` exit-code classification (parametrized 143/137/124/2/1/empty),
`skip_inflight` quality/infra branch execution, `skip_inflight_infra` structure +
shell-exec, and a `skipped_breakdown` distinct-bucket round-trip test.
`test_refine_current_compiled_on_no_resolves_to_skip_inflight` kept green.
Full suite: 15796 passed; `ll-loop validate` clean on both loops.

## Session Log
- `/ll:manage-issue` - 2026-07-22T16:16:06 - `00041c0b-3526-41ec-b743-a686380c429a.jsonl`
- `/ll:ready-issue` - 2026-07-22T15:56:04 - `cf3d91ea-f495-480a-9c45-cef8b124a720.jsonl`
- `/ll:confidence-check` - 2026-07-22T16:30:00 - `ccc564e1-c19b-4a35-a17a-d851ade14644.jsonl`
- `/ll:decide-issue` - 2026-07-22T15:51:20 - `6bff9a3b-8322-4102-889b-f3e1fc825b60.jsonl`
- `/ll:refine-issue` - 2026-07-22T15:45:51 - `35904d38-d154-40ea-a13a-2cca0585584a.jsonl`
- `/ll:refine-issue` - 2026-07-22T02:53:11 - `7f3d9a33-9486-4122-8fd1-85fd59741abd.jsonl`
- `/ll:verify-issues` - 2026-07-21T23:08:30 - `9fc8185c-278a-4573-8071-af3d44765f41.jsonl`
