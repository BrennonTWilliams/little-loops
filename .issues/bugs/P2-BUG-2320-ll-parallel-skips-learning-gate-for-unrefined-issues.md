---
id: BUG-2320
title: ll-parallel silently skips the learning gate for unrefined issues
type: BUG
status: open
priority: P2
captured_at: '2026-06-26T22:27:56Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- ENH-2319
- ENH-2219
- FEAT-1282
labels:
- learning-tests
- ll-parallel
- automation
confidence_score: 94
outcome_confidence: 88
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 25
---

# BUG-2320: ll-parallel silently skips the learning gate for unrefined issues

## Summary

`ll-parallel`'s per-worktree learning gate
(`_run_per_worktree_proof_first_gate`) early-returns `True` whenever an issue's
`learning_tests_required` frontmatter is absent, so it only ever fires the
assumption firewall for issues that were already refined. An issue that reaches
`ll-parallel` without refinement (e.g. `capture-issue → ll-parallel`) has an
empty field and silently bypasses the gate — implementation proceeds against
unproven external-API assumptions with no `/ll:explore-api` ever invoked.

## Current Behavior

`scripts/little_loops/parallel/worker_pool.py:63`
(`_run_per_worktree_proof_first_gate`, called from
`WorkerPool._process_issue` between VALIDATING and IMPLEMENTING) opens with:

```python
if issue.learning_tests_required is None:
    return True
```

`None` is treated as "no external dependencies, proceed" — but it actually means
"nobody has computed the dependencies yet." Unlike `ll-sprint`'s preflight
(`scripts/little_loops/cli/sprint/run.py:164`), which falls back to
`extract_learning_targets()` when the field is `None`, the parallel gate has no
just-in-time extraction. The result is a silent skip, not a logged decision.

## Expected Behavior

When `learning_tests_required` is empty, the gate resolves targets just-in-time
from the issue text before deciding to proceed. If extraction yields targets,
the firewall runs as usual; if it yields none, the gate proceeds and logs that
no external dependencies were detected (an auditable outcome, not a silent
bypass). Behavior for issues with a populated field is unchanged.

## Motivation

The learning gate is an assumption firewall: it forces `/ll:explore-api` to
prove external-API assumptions before code is written against them. The gate is
most valuable exactly on the path it currently skips — `capture-issue →
ll-parallel`, where an issue never passes through a refine step and `ll-parallel`
runs many issues concurrently with the least review attention. A silent bypass
here lets unverified API assumptions reach implementation unproven, which is the
specific failure the gate exists to prevent.

## Steps to Reproduce

1. Capture an issue that depends on an external API (e.g. a new SDK call) and do
   **not** run `/ll:refine-issue`, `/ll:wire-issue`, or `/ll:scope-epic`, so
   `learning_tests_required` stays absent.
2. Run it through `ll-parallel`.
3. Observe: `_run_per_worktree_proof_first_gate` returns `True` immediately;
   `proof-first-task` never runs; implementation proceeds with no proof record
   in `.ll/learning-tests/`.

## Root Cause

`scripts/little_loops/parallel/worker_pool.py:75` (`if
issue.learning_tests_required is None: return True`) conflates "field unset" with
"no dependencies." The eager-population assumption (ENH-2209) does not hold for
issues that never pass through a refine step.

## Proposed Solution

Replace the `is None → return True` short-circuit with the shared
`resolve_learning_targets(issue)` helper introduced in ENH-2319:

- Resolve targets (field if populated, else extract from issue text).
- If targets is empty after resolution, log "no external dependencies detected"
  and return `True`.
- Otherwise run the `proof-first-task` gate as today.

Land this on the same shared gate-runner ENH-2319 factors out, so `ll-auto`,
`ll-parallel`, and `ll-sprint` share one code path. Honor the existing
`--skip-learning-gate` and `learning_tests.enabled` short-circuits (which
correctly precede the target resolution).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Ordering correction (important).** The statement that
  `--skip-learning-gate` and `learning_tests.enabled` "correctly precede the
  target resolution" does **not** match the current code. Today the order in
  `_run_per_worktree_proof_first_gate` is `is None` → `learning_tests.enabled`
  → `skip_learning_gate`, with the `is None` check **first**. A naive swap of
  just the `is None` line would run the LLM extraction even when the gate is
  disabled or `--skip-learning-gate` is set. The fix must **reorder** so
  `learning_tests.enabled` and `skip_learning_gate` are checked **before**
  `resolve_learning_targets()` — which is the order `ll-sprint`'s
  `_run_learning_gate_preflight()` already uses
  (`scripts/little_loops/cli/sprint/run.py:164`).
- **"One shared code path" is not a drop-in.** `ll-parallel` and `ll-sprint`
  invoke **different loops** with **different shapes**: parallel runs
  `proof-first-task` per-issue (`--context issue_file=<path>`, `cwd=worktree`)
  and reads the state file to tell `blocked` from `done`; sprint runs
  `ready-to-implement-gate` once as a batch (`--context targets=<comma-joined>`)
  and keys off exit code. A genuine shared gate-runner (ENH-2319) must
  reconcile per-issue vs. batch and the two loop names. Keep BUG-2320 minimal by
  adding JIT resolution only to the existing per-issue `proof-first-task` path,
  and leave the unification to ENH-2319.
- **Per-issue LLM cost.** Unlike sprint's single batch extraction, JIT
  resolution here runs once **per issue inside each worktree** — under
  concurrency that is N concurrent `claude-haiku` calls. Acceptable, but it
  reinforces why resolution must happen *after* the `enabled`/`skip`
  short-circuits, so disabled runs incur no LLM cost.
- `ll-auto` has **no** learning gate at all (`scripts/little_loops/cli/auto.py`
  → `process_issue_inplace`), confirming the broader gap ENH-2319 targets;
  BUG-2320 fixes only the `ll-parallel` path.

## Integration Map

- **Files to modify**:
  - `scripts/little_loops/parallel/worker_pool.py:63`
    (`_run_per_worktree_proof_first_gate`).
- **Depends on**: ENH-2319 (`resolve_learning_targets` helper / shared
  gate-runner). Can be implemented independently by inlining the resolver, but
  prefer landing after or with ENH-2319 to avoid duplicating logic.
- **Tests**: `scripts/tests/` (parallel worker pool gate tests) — add a case
  where `learning_tests_required is None` but the issue text contains an external
  API: assert the gate resolves targets and runs `proof-first-task` rather than
  early-returning.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md:369` — the "Per-worktree proof-first gate (ENH-2219)"
  paragraph states "The gate reads `learning_tests_required` from the issue
  file"; this becomes inaccurate after the fix. Update it to note that the gate
  resolves targets JIT from the issue text when the field is absent. **Do not**
  touch the sprint paragraph at `CLI.md:434` — `ll-sprint` already documents its
  own fallback and is unchanged by this fix. [Agent 2 finding]
- `docs/guides/LEARNING_TESTS_GUIDE.md:308` — "Issues without
  `learning_tests_required` are unaffected — the gate is opt-in" is no longer
  true for `ll-parallel` after this fix. Qualify the statement per-runner: still
  true for `ll-auto` (no gate at all); `ll-sprint` already had JIT fallback;
  `ll-parallel` now runs JIT extraction when the field is absent. [Agent 2 finding]

### Wiring Gotchas

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/parallel/worker_pool.py:85` — the existing pre-gate log
  line `f"... (targets: {', '.join(issue.learning_tests_required)})"` will raise
  `TypeError` on the new JIT path, because `issue.learning_tests_required` is
  `None` exactly when extraction runs. The log must join the **resolved targets
  variable** returned by `extract_learning_targets(...)`, not the raw field.
  This is the same value already passed to `proof-first-task` via `--context`.
  [Agent 2 finding — blocking for implementation]
- `scripts/little_loops/cli_args.py` — `add_skip_learning_gate_arg()` help text
  describes a "pre-flight gate" (accurate for sprint's batch gate, imprecise for
  the per-worktree parallel gate). Pre-existing wording, not introduced here;
  optional clarification now that the parallel gate is more active. [Agent 2
  finding — advisory]
- Test patch target: patch `extract_learning_targets` at its definition module
  (`little_loops.learning_tests.extractor.extract_learning_targets`), matching
  `TestSprintPreflightGate::test_empty_target_noop` in `test_sprint_integration.py`,
  so the JIT path never hits the real `claude-haiku` LLM call. No end-to-end test
  exercises the parallel learning gate today — coverage stays at the unit level in
  `TestPerWorktreeProofFirstGate`. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the codebase:_

**Verified anchors**

- `scripts/little_loops/parallel/worker_pool.py:63` — `_run_per_worktree_proof_first_gate()`.
  The `if issue.learning_tests_required is None: return True` short-circuit is the
  **first** check (≈ lines 75–76), ahead of the `learning_tests.enabled` and
  `skip_learning_gate` checks. This ordering is wrong for the fix — see the
  Proposed Solution findings below.
- `scripts/little_loops/parallel/worker_pool.py:45` — `_read_loop_final_state()`;
  reads `.loops/.running/proof-first-task.state.json` to distinguish `blocked`
  from `done` (both exit 0). The gate returns `False` on non-zero exit **or**
  `final_state == "blocked"`.
- Call site: `WorkerPool._process_issue()` (≈ `worker_pool.py:454`), after the
  ready-issue CLOSE/BLOCKED/NOT_READY checks and
  `set_worker_stage(..., WorkerStage.PROVING)`. On `False` it returns
  `WorkerResult(success=False, error="proof-first-task gate blocked")` and
  `IMPLEMENTING` is never reached.

**Resolver / extractor**

- `resolve_learning_targets()` **does not exist yet** anywhere in
  `scripts/little_loops/` — it is proposed by ENH-2319. To land BUG-2320
  independently, inline `extract_learning_targets()`.
- `scripts/little_loops/learning_tests/extractor.py:69` —
  `extract_learning_targets(issue_text: str, *, llm_call: Callable[[str], str] | None = None) -> list[str]`.
  Takes full issue text (frontmatter + body), calls an LLM
  (`claude-haiku-4-5-20251001` by default), returns a deduplicated target list
  (`[]` when none). Inject `llm_call=` for unit tests.
- `scripts/little_loops/issue_parser.py:271` —
  `IssueInfo.learning_tests_required: list[str] | None`; the parser (lines
  490–498) sets `None` for an absent key, a `None` YAML value, **or** an empty
  list — so any unrefined issue lands in the buggy branch.
- `scripts/little_loops/cli_args.py:214` — `add_skip_learning_gate_arg()`
  registers `--skip-learning-gate`.

**Tests to extend**

- `scripts/tests/test_worker_pool.py:2992` — `TestPerWorktreeProofFirstGate`.
  Reuse its `_make_issue()` helper and `lt_enabled_br_config` fixture. The
  existing `test_gate_skipped_when_no_learning_tests_required` (asserts
  `subprocess.run` is **not** called when the field is `None`) is the test whose
  expectation **changes** under this fix. Add: (a) a sibling test where the issue
  text names an API and `extract_learning_targets` is patched to return targets,
  asserting `subprocess.run` **is** called with `proof-first-task`; (b) a no-API
  case asserting the new "no external dependencies detected" log and an early
  `True` with no subprocess.
- Reference pattern to copy:
  `scripts/tests/test_sprint_integration.py` →
  `TestSprintPreflightGate::test_empty_target_noop` shows the `None` +
  patched-`extract_learning_targets` setup.

## Implementation Steps

1. Replace the `learning_tests_required is None → return True` short-circuit in
   `_run_per_worktree_proof_first_gate` with `resolve_learning_targets(issue)`
   (the ENH-2319 shared resolver), preserving the existing
   `--skip-learning-gate` / `learning_tests.enabled` short-circuits ahead of it.
2. Branch on the resolved targets: empty → log "no external dependencies
   detected" and return `True`; non-empty → run the `proof-first-task` gate.
3. Add a parallel worker-pool test where `learning_tests_required is None` but
   the issue text names an external API, asserting the gate resolves targets and
   runs the firewall instead of early-returning.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation:_

4. Update the pre-gate log line in `_run_per_worktree_proof_first_gate`
   (`worker_pool.py:85`) to join the **resolved** targets variable, not
   `issue.learning_tests_required` (which is `None` on the JIT path and would
   `TypeError`).
5. In the breaking/updated test
   (`test_gate_skipped_when_no_learning_tests_required`) and the two new tests,
   patch `little_loops.learning_tests.extractor.extract_learning_targets` so the
   JIT path never reaches the real LLM (mirror
   `TestSprintPreflightGate::test_empty_target_noop`).
6. Update `docs/reference/CLI.md:369` (per-worktree gate paragraph) and
   `docs/guides/LEARNING_TESTS_GUIDE.md:308` (opt-in claim) to reflect JIT
   extraction for `ll-parallel`. Leave the sprint paragraph (`CLI.md:434`)
   untouched.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Step 1 currently reads "preserving the existing short-circuits **ahead of
  it**" — but they are not ahead today (the `is None` check is first). Concretely:
  **move** the `learning_tests.enabled` and `skip_learning_gate` checks to the
  top of `_run_per_worktree_proof_first_gate`, then call the resolver, then
  branch (mirroring `_run_learning_gate_preflight` in `cli/sprint/run.py:164`).
- Until ENH-2319 lands `resolve_learning_targets`, step 1 should inline
  `extract_learning_targets(issue.path.read_text())` (with an `OSError` guard, as
  sprint does) rather than import a helper that does not yet exist.
- Add the test alongside `TestPerWorktreeProofFirstGate` in
  `scripts/tests/test_worker_pool.py:2992` (reuse `_make_issue` /
  `lt_enabled_br_config`); patch `little_loops...extract_learning_targets` for the
  resolved-targets case, matching the sprint test in `test_sprint_integration.py`.

## Impact

- **Priority**: P2 — a safety gate silently does nothing on a real code path,
  letting unverified API assumptions reach implementation under concurrent
  automation (where review attention is lowest).
- **Effort**: Small — one function changes; test coverage is the bulk of the
  work.
- **Risk**: Low — behavior is unchanged for issues with a populated
  `learning_tests_required` field; the new path only affects the previously
  silent `None` case. Reuses the ENH-2319 resolver rather than introducing new
  extraction logic.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/explore-api/SKILL.md` | Proof lifecycle the gate is meant to trigger |
| `.claude/CLAUDE.md` (CLI Tools) | `ll-parallel` / learning-test gate overview |

## Labels

- learning-tests
- ll-parallel
- bug

## Session Log
- `/ll:ready-issue` - 2026-06-26T23:33:53 - `efe99123-da40-4a82-b80e-010de22783dd.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:54:12 - `6450c656-750b-4d27-8678-b5873c0b541e.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:44:59 - `aed09bae-4126-4c13-b831-260707aa5886.jsonl`
- `/ll:format-issue` - 2026-06-26T22:34:22 - `d992b141-a5e8-43b7-be56-6f508203a1ac.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:27:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`

---

## Status

open
