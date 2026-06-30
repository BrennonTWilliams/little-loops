---
id: ENH-2405
title: Learning gate re-extracts targets instead of proving the registered `learning_tests_required`
type: ENH
priority: P3
status: open
relates_to:
- EPIC-2207
- ENH-2209
- ENH-2319
- FEAT-1696
- FEAT-1738
captured_at: '2026-06-30T21:17:26Z'
discovered_date: '2026-06-30'
discovered_by: capture-issue
labels:
- learning-tests
- rn-remediate
- consistency
- efficiency
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2405: Learning gate re-extracts targets instead of proving the registered `learning_tests_required`

## Summary

ENH-2209 made `/ll:refine-issue` and `/ll:wire-issue` auto-populate the issue's
`learning_tests_required` frontmatter — the canonical list of external-API hypotheses to
prove before implementation. But the implement-time learning gate does **not** prove that
list. It uses `learning_tests_required` only as a boolean trigger guard and then
**re-extracts** an independent target list via the `assumption-firewall` LLM step. The
result is a redundant LLM extraction on every gated issue and a silent divergence risk: the
hypotheses an author/refinement registered are not necessarily the ones the gate proves.

## Current Behavior

In `process_issue_inplace` (`scripts/little_loops/issue_manager.py:854-869`):

```python
if config.learning_tests.enabled is True and not dry_run:
    targets = resolve_learning_targets(info)          # reads learning_tests_required frontmatter
    if targets:                                       # ← used only as a trigger guard
        verdict = run_learning_gate_for_issue(info.path, skip=skip_learning_gate, cwd=gate_cwd)
        ...
```

`targets` (the registered list from ENH-2209) gates **whether** the check runs, but is then
discarded — `run_learning_gate_for_issue` (`scripts/little_loops/learning_tests/gate.py:76-114`)
is passed `info.path`, not `targets`. It shells to `ll-loop run proof-first-task`, whose
`gate` state delegates to `assumption-firewall`, which **re-extracts** the external-API
assumption list from the raw issue text via its own `extract_assumptions` LLM step
(max 7) before delegating testable claims to `ready-to-implement-gate` (the `type: learning`
state that actually runs `/ll:explore-api`).

So the proof set is re-derived by a second, independent LLM call rather than read from the
frontmatter that refinement already wrote.

## Expected Behavior

When `learning_tests_required` is populated, the gate proves **exactly that list** and skips
the redundant `assumption-firewall` extraction. The registered hypotheses and the proven
hypotheses are guaranteed identical. LLM extraction at gate time runs only as a fallback when
the frontmatter field is absent (preserving the JIT path for un-refined issues, e.g.
BUG-2320 / ll-parallel).

Concretely: an issue with `learning_tests_required: ["stripe"]` whose body also happens to
mention `requests` in passing must have the gate prove **`stripe`** (the registered target),
not a freshly-extracted `["stripe", "requests"]`.

## Motivation

1. **Single source of truth.** ENH-2209 established `learning_tests_required` as the
   registry of an issue's hypotheses. A gate that re-derives its own list defeats that — the
   field becomes advisory rather than authoritative.
2. **Divergence risk.** Two independent LLM extractions over evolving issue text can disagree
   (different model, different prompt, the 7-target cap, body edited since refine). The gate
   can then prove a different set than what was registered/reviewed.
3. **Redundant cost.** Every gated issue pays for a second assumption-extraction LLM call
   whose answer the system already computed and persisted during refinement.

## Proposed Solution

Thread the registered `learning_tests_required` list through the gate instead of discarding
it, mirroring the pattern that already exists in `_run_learning_gate_preflight`
(`cli/sprint/run.py`), which resolves registered targets and shells
`ll-loop run ready-to-implement-gate --context targets=<csv>` directly, bypassing
`assumption-firewall` entirely:

1. Add an optional `targets: list[str] | None` parameter to `run_learning_gate_for_issue`
   (`gate.py`) and pass the already-resolved `targets` from `process_issue_inplace`
   (`issue_manager.py`) instead of dropping it after the trigger-guard check.
2. Forward `targets` as a `targets_csv` context input on the `ll-loop run proof-first-task`
   subprocess call.
3. In `proof-first-task.yaml`, route a populated `targets_csv` directly to
   `ready-to-implement-gate` (mapping onto its existing `targets` context key) instead of
   through `assumption-firewall`'s `extract_assumptions` step. When `targets_csv` is absent,
   keep today's `assumption-firewall` extraction as the JIT fallback.
4. Mirror the same `targets_csv` threading in the ll-parallel per-worktree gate
   (`worker_pool.py:_run_per_worktree_proof_first_gate`) so the registered list is proven on
   that path too.

See Implementation Steps and Integration Map below for the full file-by-file breakdown.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py` — add optional `targets: list[str] | None` to `run_learning_gate_for_issue`; forward as a `targets_csv` context input into the `proof-first-task` run.
- `scripts/little_loops/issue_manager.py` — in `process_issue_inplace`, pass the already-resolved `targets` (from `resolve_learning_targets`) into `run_learning_gate_for_issue` instead of discarding it after the trigger guard.
- `scripts/little_loops/loops/proof-first-task.yaml` — accept a `targets_csv` context input; when present, route directly to `ready-to-implement-gate` and skip the `assumption-firewall` delegation.
- `scripts/little_loops/loops/assumption-firewall.yaml` — `extract_assumptions` becomes the fallback-only path (runs only when no registered targets are supplied).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/worker_pool.py` — **resolves the "Decision needed" flagged in the Codebase Research Findings section below in favor of inclusion.** `_run_per_worktree_proof_first_gate` (63-129) is an *independent* second gate call site (it does **not** call `run_learning_gate_for_issue`) that shells `ll-loop run proof-first-task --context issue_file=<path>` at 103-114 — forwarding only `issue_file`, never `targets_csv` — and resolves targets inline at 88-96 instead of via `resolve_learning_targets`. Until this is threaded, the ll-parallel path keeps triggering the redundant `assumption-firewall` re-extraction even after the primary fix lands, so the registered list is **not** proven on that path (Acceptance Criterion 1 silently fails under `ll-parallel`). Append `--context targets_csv=<csv>` here (mirroring the `issue_manager.py` change) and optionally collapse the inline extraction (88-96) into `resolve_learning_targets` (the line-87 comment already anticipates this). [Agent 2 finding — confirmed via grep: `run_learning_gate_for_issue` has no second production caller; `worker_pool.py` duplicates the logic, including a private `_read_loop_final_state` at 45-60.]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py` (`process_issue_inplace`) — sole production caller of `run_learning_gate_for_issue`; the behavior change originates here.
- `resolve_learning_targets` (`scripts/little_loops/learning_tests/extractor.py:197`) — already produces the `targets` list now consumed as the proof set rather than a boolean guard. _(refine-issue correction: this function lives in `extractor.py`, not `gate.py`.)_

### Similar Patterns
- `proof-first-task.yaml` already forwards per-target context to the `ready-to-implement-gate` learning state; extend that same mechanism with `targets_csv` rather than introducing a new passing convention.

### Tests
- `scripts/tests/test_issue_manager.py` — covers `process_issue_inplace` gate invocation; add the divergence test (frontmatter `["stripe"]` vs body mentioning `requests`) asserting the gate proves `stripe` only.
- `scripts/tests/test_learning_tests.py`, `scripts/tests/test_learning_state.py` — assert zero `extract_assumptions` calls when registered targets are supplied; retain extraction-path coverage for the absent-field fallback.
- `scripts/tests/test_install_learning_gate.py` — guards the `LEARNING_GATE_BLOCKED` / exit-code contract (Acceptance Criterion 4); confirm byte-for-byte unchanged.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction (AC4 coverage misattributed):** `scripts/tests/test_install_learning_gate.py` does **not** reference `LEARNING_GATE_BLOCKED` (verified: `grep -c` returns 0). Its classes (`TestGateDisabled`, `TestAcceptanceSignals`, `TestInstallVariants`, `TestStaleRecords`, `TestSessionCache`) test the pip/npm install-nudge hook (ENH-2208/2212), not the implement-time marker. The real AC4 contract is guarded by `scripts/tests/test_issue_manager.py::TestAutoManagerLearningGate::test_blocked_gate_prints_greppable_marker` (3656 — `assert "LEARNING_GATE_BLOCKED" in out`) and `scripts/tests/test_builtin_loops.py::TestLearningGateConsistency` (~8662+ — YAML-structure assertions across `rn-remediate.yaml`/`rn-implement.yaml`/`lib/common.yaml`). Re-run/diff **those** for the byte-for-byte check, not `test_install_learning_gate.py`. [Agent 3 finding]
- `scripts/tests/test_worker_pool.py` — `_run_per_worktree_proof_first_gate` is fully covered by 6 tests (3092-3261: `test_gate_skipped_when_lt_disabled`, `test_gate_skipped_when_no_learning_tests_required`, `test_gate_resolves_targets_jit_when_field_none`, `test_gate_logs_no_external_deps_when_jit_empty`, `test_blocked_result_skips_manage_issue`, `test_skip_learning_gate_flag_bypasses_gate`). All assert subprocess `cmd` membership (not exact-signature), so appending `--context targets_csv=<csv>` won't break them. Add a test asserting the cmd contains `targets_csv=<csv>` when `learning_tests_required` is populated — model on `test_gate_resolves_targets_jit_when_field_none` (3143; inspects `mock_sub.call_args[0][0]`). [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — add a structural routing assertion that `proof-first-task.yaml` routes a populated `targets_csv` **past** `assumption-firewall` directly into `ready-to-implement-gate`. Note the existing guard `test_prove_state_has_targets_csv_with_context_ref` (5796) hard-asserts `ready-to-implement-gate.yaml`'s `prove.learning.targets_csv == "${context.targets}"` — the new `proof-first-task` routing must thread its CSV via `with: targets: "${context.targets_csv}"` (mapping onto the sub-loop's existing **`targets`** key), **not** by renaming the sub-loop's context key, or this test breaks. [Agent 2 finding]
- `scripts/tests/test_learning_tests_extractor.py` — covers `resolve_learning_targets` / `extract_learning_targets`; relevant if `worker_pool.py`'s inline extraction (88-96) is collapsed into `resolve_learning_targets`. [Agent 1 finding]

### Documentation
- `docs/guides/LEARNING_TESTS_GUIDE.md` — describes the gate and `learning_tests_required`; update to state the gate proves the registered list and only extracts as a fallback.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~5710-5721) — the `### run_learning_gate_for_issue` section documents the exact signature `(issue_path: Path, *, skip: bool = False, cwd: Path | None = None)`; it goes stale the moment `targets: list[str] | None = None` is added. Update the code-block signature and prose. [Agent 2 finding — verified]
- `docs/guides/LOOPS_REFERENCE.md` (line 163) — `proof-first-task` catalog row reads "extracts external-API assumptions from an issue file, proves each ... then delegates"; this becomes conditional (proves the registered list directly; extracts only as a fallback). [Agent 1 finding — verified]
- `scripts/little_loops/loops/README.md` (line 83) — a second, separately-worded `proof-first-task` description with the same "extracts ... assumptions" claim; same conditional update. [Agent 1 finding — verified]
- `docs/reference/CLI.md` (line 370) — the `ll-parallel` "**Per-worktree proof-first gate (ENH-2219)**" paragraph states the gate "verifies that every resolved API assumption has a proven record." Because `worker_pool.py` is now in scope (above), add the registered-vs-extracted distinction here. [Agent 2 finding — verified]
- `CHANGELOG.md` — add an ENH-2405 entry at release time under a concrete `## [X.Y.Z] - DATE` section (per repo convention, **not** under `[Unreleased]`). No existing entry needs editing. [Agent 2 finding]
- _Not a touchpoint:_ `docs/reference/loops.md` was mis-cited by analysis; verified it contains neither `proof-first-task` nor `assumption-firewall`. The canonical catalog is `docs/guides/LOOPS_REFERENCE.md`.

### Configuration
- N/A — no new config; the gate continues to trigger on `learning_tests.enabled`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (line numbers verified against current HEAD):_

**Verified anchors (cited references re-checked):**
- `process_issue_inplace` gate block is `scripts/little_loops/issue_manager.py:854-876` (the issue cites `854-869`; the full block including the early-return runs to 876). `targets = resolve_learning_targets(info)` is at **855**; `targets` is referenced only at **856** (`if targets:`) and **857** (log line) before `run_learning_gate_for_issue(info.path, skip=skip_learning_gate, cwd=gate_cwd)` is called at **859** with `info.path` — confirming the resolved list is discarded after the trigger guard.
- `run_learning_gate_for_issue`: `scripts/little_loops/learning_tests/gate.py:76-114`, signature `(issue_path, *, skip=False, cwd=None)`. It shells `ll-loop run proof-first-task --context issue_file=<path>` at **98-109** (only `issue_file` forwarded), then derives the verdict by reading `.loops/.running/proof-first-task.state.json` via `_read_loop_final_state` (59-73, 111-114) — **not** from the subprocess exit code. The new `targets` param threads in here.
- `proof-first-task.yaml` `context:` block (11-14) declares `task`, `issue_file`, `impl_loop` — no `targets`/`targets_csv` key exists yet. Its `gate` state (24-31) delegates to `assumption-firewall` forwarding only `input: "${context.issue_file}"`.
- The `--context` flag is repeatable (`action="append"`, `cli/loop/__init__.py:235-240`); each `KEY=VALUE` is parsed via `kv.partition("=")` into `fsm.context` (`cli/loop/run.py:155-159`). So threading the registered list = appending a second `--context targets_csv=<csv>` pair (omit it when targets is None/empty).

**Reference corrections:**
- The "Dependent Files" entry originally pointed `resolve_learning_targets` at `gate.py`; it actually lives in `scripts/little_loops/learning_tests/extractor.py:197-218` (field-first: returns `issue.learning_tests_required` when non-`None`, else JIT `extract_learning_targets`). Corrected inline above.
- The "Similar Patterns" claim attributes per-target CSV forwarding to `proof-first-task.yaml`. That forwarding is actually one level deeper, in `assumption-firewall.yaml`'s `run_gate` state (172-179): `with: targets: "${captured.targets.output}"` → `ready-to-implement-gate`. The CSV-`targets` convention to extend is real, but it lives in `assumption-firewall` / `ready-to-implement-gate`, not `proof-first-task`.

**`ready-to-implement-gate` already accepts the registered list (key insight):**
`ready-to-implement-gate.yaml` declares `context.targets: ""` (comma-separated) and its `prove` state (`type: learning`) maps it to `learning.targets_csv: "${context.targets}"`, which `_execute_learning_state` (`scripts/little_loops/fsm/executor.py`, ~745) CSV-splits and proves per target via `/ll:explore-api`. So the cleanest realization of "skip `assumption-firewall` when targets are supplied" is to have `proof-first-task` route a populated `targets_csv` **directly to `ready-to-implement-gate`** (mirroring the sprint precedent below), rather than only short-circuiting inside `assumption-firewall`.

**Second production gate call site — scope gap (recommend resolving before implementation):**
The ll-parallel path does **not** go through `run_learning_gate_for_issue`. `scripts/little_loops/parallel/worker_pool.py:_run_per_worktree_proof_first_gate` (63-128, ENH-2219) is an independent per-worktree gate that resolves the same registered targets (`issue.learning_tests_required` at 88-89, else `extract_learning_targets` at 94) and shells its own `ll-loop run proof-first-task --context issue_file=...` (107-108) — an identical `issue_file`-only invocation with the **same re-extraction bug**. Fixing only `gate.py` + `proof-first-task.yaml` leaves this path threading nothing: once `proof-first-task` honors `targets_csv`, `worker_pool` must also append `--context targets_csv=<csv>` for the ll-parallel path to prove the registered list. **Decision needed:** add `worker_pool.py` to "Files to Modify" (preferred — line 87 already flags its inline extraction as something to collapse into `resolve_learning_targets`), or explicitly scope it out under Scope Boundaries.

**Strong precedent to model (the approach already exists at sprint level):**
`scripts/little_loops/cli/sprint/run.py:_run_learning_gate_preflight` (164-216) already does what ENH-2405 wants — it calls `resolve_learning_targets(info)` (196), aggregates the registered targets, and shells `ll-loop run ready-to-implement-gate --context targets=<csv>` (214-216), bypassing `assumption-firewall` entirely. This is the canonical "prove the registered list directly" pattern in-tree; model the new gate path on it.

**Concrete test models (for the new divergence + routing tests in the Tests subsection above):**
- `scripts/tests/test_issue_manager.py::TestAutoManagerLearningGate` (3563-3736) — `_make_issue(..., learning_tests_required=[...])` helper plus the `mock_gate.call_args` kwargs idiom; model the divergence test as `assert kwargs.get("targets") == ["stripe"]`. _(refine-issue correction: class is `TestAutoManagerLearningGate`, not `TestLearningGateInvocation`.)_
- `scripts/tests/test_sprint_integration.py::TestLearningGatePreflight.test_dedup_targets_across_issues` (1938-1959) — mocks `subprocess.run`, reads `cmd_args = mock_sub.call_args[0][0]`, asserts `"targets=anthropic" in cmd_args`; closest existing model for asserting the CSV reaches `--context`.
- `scripts/tests/test_builtin_loops.py::TestProofFirstTaskLoop` / `TestAssumptionFirewallLoop` (`test_run_gate_targets_refers_to_flatten_testable` ~5975) — structural YAML-routing assertions; add one asserting a populated `targets_csv` routes past `assumption-firewall`.
- `scripts/tests/test_learning_state.py::TestLearningStateCsvTargets` (415-510) — `targets_csv` CSV round-trip / whitespace-strip coverage.

## Implementation Steps

1. **Thread the registered targets into the gate.** Pass the resolved `targets` from
   `issue_manager.py:855` into `run_learning_gate_for_issue` (new optional `targets:
   list[str] | None` parameter on `gate.py:76`).
2. **Prefer registered targets in the gate chain.** When targets are supplied, route them to
   `ready-to-implement-gate` directly (the `type: learning` prover) — bypassing
   `assumption-firewall`'s `extract_assumptions` step. `proof-first-task` already accepts
   per-target context; add a `targets_csv` context input it forwards to the learning gate.
3. **Keep extraction as fallback.** When `targets` is `None`/absent (un-refined issue),
   retain today's `assumption-firewall` re-extraction so the JIT path (ENH-2319) is
   unchanged.
4. **Unit test divergence.** Add a test where frontmatter and body disagree, asserting the
   gate proves the frontmatter list and makes zero `extract_assumptions` calls.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. **Thread the registered list through the ll-parallel gate too.** In
   `scripts/little_loops/parallel/worker_pool.py:_run_per_worktree_proof_first_gate`, append
   `--context targets_csv=<csv>` to the `ll-loop run proof-first-task` subprocess call
   (103-114) when targets are present — mirroring the `issue_manager.py` change. Without this,
   Acceptance Criterion 1 silently fails under `ll-parallel` (the path keeps re-extracting).
   Optionally collapse the inline target resolution (88-96) into `resolve_learning_targets`
   (the line-87 comment already anticipates this).
6. **Honor the sub-loop's existing context-key name.** When `proof-first-task.yaml` routes a
   populated `targets_csv` directly to `ready-to-implement-gate`, pass it via
   `with: targets: "${context.targets_csv}"` — mapping onto `ready-to-implement-gate.yaml`'s
   existing **`targets`** context key (line 11). Do **not** rename the sub-loop's key, or
   `test_builtin_loops.py::test_prove_state_has_targets_csv_with_context_ref` (5796) breaks.
   `ready-to-implement-gate.yaml` therefore stays out of "Files to Modify."
7. **Add the ll-parallel threading test.** In `scripts/tests/test_worker_pool.py`, assert the
   subprocess cmd contains `targets_csv=<csv>` when `learning_tests_required` is populated
   (model: `test_gate_resolves_targets_jit_when_field_none`, 3143).
8. **Update docs.** `docs/reference/API.md` signature for `run_learning_gate_for_issue`;
   `proof-first-task` descriptions in `docs/guides/LOOPS_REFERENCE.md` (163) and
   `scripts/little_loops/loops/README.md` (83); the `ll-parallel` per-worktree gate paragraph
   in `docs/reference/CLI.md` (370).

## Scope Boundaries

- **In scope**: making the implement-time gate consume `learning_tests_required` as its proof
  set; suppressing the redundant extraction when the field is populated.
- **In scope** _(wire-issue: resolves the "Decision needed" in Codebase Research Findings)_: the ll-parallel
  per-worktree gate (`worker_pool.py:_run_per_worktree_proof_first_gate`) — without threading
  `targets_csv` there too, the registered list is not proven on the `ll-parallel` path and
  Acceptance Criterion 1 silently fails for concurrent runs.
- **Out of scope**: changing how refinement populates the field (ENH-2209); changing
  `/ll:explore-api` record creation; removing the gate from the `ll-auto` choke point
  (ENH-2319 — the gate stays there, it just sources targets differently); the
  post-implement `check_learning_gate` marker classifier in rn-remediate/autodev (reporting
  shim, unaffected).

## Acceptance Criteria

1. An issue with `learning_tests_required: ["stripe"]` and a body mentioning `requests` is
   gated on `stripe` only; `requests` is not proven.
2. With the field populated, no `assumption-firewall` `extract_assumptions` LLM call is made
   (verified via mock/log).
3. An issue with no `learning_tests_required` field still runs the existing extraction-based
   gate (JIT path unchanged).
4. `ll-auto --only` exit-code / `LEARNING_GATE_BLOCKED` contract is byte-for-byte unchanged.

## Impact

- **Priority**: P3 — correctness/consistency seam in a working feature; not blocking.
- **Effort**: Small–Medium — one new parameter threaded through `gate.py` + `proof-first-task`
  context; reuses the existing `ready-to-implement-gate` prover.
- **Risk**: Low — additive; fallback preserves current behavior for un-refined issues.
- **Breaking Change**: No.

## Related Key Documentation

- [LEARNING_TESTS_GUIDE.md](../../docs/guides/LEARNING_TESTS_GUIDE.md) — learning test registry, the implement-time gate, and `learning_tests_required` semantics.

## Labels

`enhancement`, `learning-tests`, `consistency`, `efficiency`

## Session Log
- `/ll:ready-issue` - 2026-06-30T22:50:23 - `1785790f-eac6-470a-b7f9-1c5edff6ff08.jsonl`
- `/ll:confidence-check` - 2026-06-30T22:44:46Z - `edd3a86a-a9fc-4550-94a9-f80b858e42c0.jsonl`
- `/ll:confidence-check` - 2026-06-30T21:50:12Z - `a69cdcc2-dcb8-4c8c-8d25-8101c9563e35.jsonl`
- `/ll:wire-issue` - 2026-06-30T21:44:54 - `7475cb34-e529-45a6-ae0d-48e2395d6a0c.jsonl`
- `/ll:refine-issue` - 2026-06-30T21:32:27 - `d936c18f-af8b-463c-a9ae-9bb32d4ac27a.jsonl`
- `/ll:format-issue` - 2026-06-30T21:23:15 - `8bc99825-3dc5-4925-a87b-bed78c17905a.jsonl`
- `/ll:capture-issue` - 2026-06-30T21:17:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/517f4fde-43d5-44f7-afc7-41dd7c15be45.jsonl`

## Status

**Open** | Created: 2026-06-30 | Priority: P3
