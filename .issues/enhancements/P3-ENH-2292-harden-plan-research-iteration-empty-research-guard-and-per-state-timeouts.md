---
id: ENH-2292
type: ENH
priority: P3
status: done
size: Small
captured_at: '2026-06-25T15:00:41Z'
discovered_date: 2026-06-25
discovered_by: audit-loop-run
relates_to:
- BUG-2289
decision_needed: false
completed_at: '2026-06-25T15:00:41Z'
---

# ENH-2292: Harden plan-research-iteration — empty-research guard + per-state timeouts

## Summary

Two robustness fixes to `scripts/little_loops/loops/oracles/plan-research-iteration.yaml`,
the research sub-loop shared by `rn-plan` and `rn-refine`. Surfaced by an audit of
an interrupted `rn-refine` run (`audit-rn-refine-2026-06-25T142426.md`) whose
`research_web` action was killed (exit -9) before any refinement iteration completed.

1. **Empty-research guard before `synthesize`** — a new `check_research` shell gate
   ensures `synthesize` never runs against an empty `research.md` (which would produce
   a phantom no-op plan rewrite that burns tokens).
2. **Per-state timeouts on the research actions** — `research_web` and `research_files`
   now carry `timeout: 600` + `on_error: check_research`, bounding a runaway research
   prompt and degrading gracefully through the guard.

## Motivation

`synthesize` reads `${run_dir}/research.md` unconditionally (loop lines 169-186). When
that file is empty — e.g. a research action wrote nothing, or was killed/timed out
mid-write — synthesis does a no-op rewrite of the plan with zero new information, wasting
an entire iteration's token budget while reporting progress.

Separately, the research actions (`research_web` especially, via parallel WebSearch /
WebFetch) are unbounded long-running prompts with no per-state ceiling. The loop-level
`timeout: 3600` is too coarse to protect a single action from hanging.

## Root-Cause Analysis

The triggering audit attributed the run failure to a SIGKILL/OOM in `research_web` and
proposed four fixes. Tracing each against the actual FSM engine:

- **Audit proposal #2 (engine: "trap the sub-loop signal, run `diagnose` first") —
  REJECTED.** Parent and child are separate `FSMExecutor` instances, so the child's
  shutdown flag does not bleed into the parent, and the engine *already* routes a
  signal-terminated child through `on_no` (`executor.py:739-741`); the audited loop set
  `on_no: diagnose`. If instead the whole process group took the SIGKILL (consistent with
  "parent terminated_by: signal"), SIGKILL is uncatchable by definition — no handler can
  run. The proposal is impossible/redundant.
- **Audit proposal #1 (split `research_web` into search→fetch to dodge OOM) — DEFERRED.**
  The OOM root cause is unverified; the audit's Token Usage table even cites a nonexistent
  model id, indicating parts of the assessment are templated/hallucinated rather than
  observed. Not worth a structural rewrite on this evidence.
- **Audit proposal #3 (empty-research guard) — ADOPTED** (fix 1 below). A genuine latent
  defect independent of the SIGKILL.
- **Audit proposal #4 (per-state timeout) — ADOPTED with correction** (fix 2 below). A
  per-state `timeout:` is a real `StateConfig` field (`schema.py:435`), but the audit's
  `on_timeout:` key is **not** a schema field. A timed-out prompt returns exit 124
  (`runners.py:138-143`), which routes via `on_error`. Used `on_error: check_research`,
  not the invented `on_timeout:`.

A separately-noted non-bug: `research_web` has no explicit `next:` in `state_defs`, but
the `flow:` shorthand supplies `next: synthesize` (now `next: check_research`) via flow
expansion (`fragments.py:310-318`). It was never a dead-end.

## What Changed

`scripts/little_loops/loops/oracles/plan-research-iteration.yaml`:

- Added `check_research` to the flow as a **ternary** entry
  (`"check_research?synthesize:done"`). The ternary form is required: a flat flow entry
  would inject an implicit `next:`, and the executor honors `next` *before* `evaluate`
  (`executor.py:1001`), which would defeat the guard.
- `check_research` runs `test -s ${context.run_dir}/research.md && echo HAS_RESEARCH ||
  echo NO_RESEARCH`, evaluates on `HAS_RESEARCH`, and routes populated → `synthesize`,
  empty/missing → `done` (an honest no-op iteration).
- Re-routed every inbound edge to `synthesize` through the guard: `research_files.next`,
  `research_web.next` (via flow), `route_files.on_error`, `route_web.on_error`, and
  `classify_fallback.on_no`/`on_error` now target `check_research`. `synthesize` has no
  unguarded inbound edge.
- Added `timeout: 600` + `on_error: check_research` to both `research_web` and
  `research_files`.

## Scope Boundaries

- Did **not** make any FSM engine change (audit #2 rejected as impossible/redundant).
- Did **not** restructure `research_web` into separate search/fetch states (audit #1
  deferred — unverified root cause).
- Left a pre-existing wart alone (out of scope): `classify_fallback` has both a flow
  `next:` and `on_yes/on_no`, so its `evaluate` is dead code and it always falls through
  to `research_files`. Harmless here — that path still reaches the guard.

## Verification

- `ll-loop validate oracles/plan-research-iteration` → valid.
- Programmatic flow-expansion check confirmed: both research states →
  `next/on_error: check_research` with `timeout: 600`; `check_research` →
  `on_yes: synthesize`, `on_no: done`, no `next`; `synthesize` reachable only via the guard.
- Updated 1 test (`test_research_files_overrides_next_to_synthesize` →
  `..._to_check_research`) and added 3 new tests in
  `TestPlanResearchIterationOracle` (`test_builtin_loops.py`): per-state timeout + error
  route, guard shape, and a structural assertion that only `check_research` routes to
  `synthesize`.
- `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_rn_decompose.py
  scripts/tests/test_rn_implement.py` → 1089 passed.

## Related

- Triggered by audit artifact `audit-rn-refine-2026-06-25T142426.md`.
- relates_to BUG-2289 (rn-decompose, same loop family).

## Resolution

Both fixes applied to `plan-research-iteration.yaml`; tests updated and green; loop
validates. `synthesize` is now fully guarded against empty research, and the research
actions are bounded by a 600s per-state timeout that degrades through the same guard.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-25T15:01:20 - `c7206b3e-c9c6-4a60-913b-83ac8c124da1.jsonl`

- 2026-06-25 — Reviewed `audit-rn-refine-2026-06-25T142426.md`; traced all four audit
  proposals against `fsm/executor.py`, `fragments.py`, `schema.py`, `runners.py`.
  Rejected proposals #1 and #2, adopted #3 and #4 (the latter corrected: `on_error`
  not the nonexistent `on_timeout`). Implemented the guard + timeouts, updated/added
  tests, validated, and documented in this issue.
