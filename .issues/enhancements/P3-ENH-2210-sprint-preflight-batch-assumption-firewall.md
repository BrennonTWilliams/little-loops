---
id: ENH-2210
title: Sprint pre-flight batch assumption-firewall before ll-sprint execution
type: enhancement
priority: P3
status: done
parent: EPIC-2207
depends_on:
- ENH-2209
- ENH-2208
captured_at: '2026-06-18T15:38:06Z'
completed_at: '2026-06-19T01:31:20Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
confidence_score: 94
outcome_confidence: 79
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 20
decision_needed: false
learning_tests_required: []
labels:
- sprint
- learning-tests
- preflight
- cli
---

# ENH-2210: Sprint pre-flight batch assumption-firewall before ll-sprint execution

## Summary

`ll-sprint` dispatches claude invocations per issue without first validating that the external-API assumptions of those issues are proven. Add a pre-flight phase that aggregates all `learning_tests_required` targets across the sprint, deduplicates them, and gates the sprint on a single `ready-to-implement-gate` run before any implementation begins.

## Current Behavior

`ll-sprint` dispatches claude invocations per issue in priority order without first validating whether the external-API assumptions of those issues are proven. If an issue references an unproven API assumption, the failure is discovered only after a full worktree invocation has been launched.

## Expected Behavior

`ll-sprint` runs a batch pre-flight phase before dispatching any invocations. The pre-flight aggregates all `learning_tests_required` targets across sprint issues, deduplicates them, and runs `ready-to-implement-gate` once. If any target is unproven, the sprint aborts immediately with a message identifying the blocking target(s) and the contributing issue ID(s). A `--skip-learning-gate` flag bypasses pre-flight for emergency runs; when `learning_tests.enabled: false`, the pre-flight is skipped entirely.

## Motivation

Running an issue mid-sprint only to hit an unproven assumption wastes a full worktree invocation. Batching the gate check upfront surfaces the gap in seconds, before any expensive agent work is committed.

## Implementation Steps

1. **Add `add_skip_learning_gate_arg()` to `scripts/little_loops/cli_args.py`** — model exactly after `add_skip_analysis_arg()` (~line 205). This is a one-liner `argparse.add_argument("--skip-learning-gate", action="store_true", ...)` factory.

2. **Wire the flag in `scripts/little_loops/cli/sprint/__init__.py`** — call `add_skip_learning_gate_arg(run_parser)` alongside the existing `add_skip_analysis_arg(run_parser)` (~line 67 in `main_sprint()`).

3. **Insert the pre-flight block in `scripts/little_loops/cli/sprint/run.py`** — after `issue_infos = manager.load_issue_infos(issues_to_process)` (currently line 282), before the dependency analysis block. The block:
   - Reads `config.learning_tests.enabled` via `LearningTestsConfig.from_dict()` (from `scripts/little_loops/config/features.py`); skip entire block if `False`.
   - Short-circuits if `getattr(args, "skip_learning_gate", False)`.
   - For each `IssueInfo` in `issue_infos`: collect `info.learning_tests_required or []`. For any info with `None`, fall back to `extract_learning_targets(path.read_text())` (import from `scripts/little_loops/learning_tests/extractor.py`).
   - Flatten and deduplicate while preserving first-occurrence order across all issues.
   - If the merged list is empty: log a debug message and skip the gate invocation (no-op path).
   - Otherwise: `subprocess.run(["ll-loop", "run", "ready-to-implement-gate", "--context", f"targets={','.join(all_targets)}"], check=False)`. On non-zero exit, print which targets failed and which issues contributed each target, then `sys.exit(1)`.

4. **Update `_execute_learning_state()` in `scripts/little_loops/fsm/executor.py`** (~line 738) — after `check_learning_test(target)` returns a `proven` record, call `is_record_stale(record, config.learning_tests.stale_after_days)` (import from `scripts/little_loops/learning_tests/gate.py`). If stale, treat the record as absent (same retry path). This is a hard ENH-2208 dependency.

5. **Add tests** in `scripts/tests/test_sprint_integration.py` using the `sprint_project` fixture pattern. Cover: dedup (two issues, same `anthropic` target → one gate call), empty-target no-op (gate subprocess not called), abort on unproven (gate exits 1 → sprint exits 1), `--skip-learning-gate` bypass (gate subprocess not called), `learning_tests.enabled: false` skip (gate subprocess not called).

## Success Metrics

- A sprint with two issues both requiring `anthropic` only probes the registry once
- If any target is unproven, sprint aborts with a clear message naming the blocking issue IDs
- `--skip-learning-gate` bypasses the pre-flight for emergency runs
- When `learning_tests.enabled: false`, pre-flight is skipped entirely

## Scope Boundaries

- **In scope**: Pre-flight validation of learning test targets before sprint execution; deduplication of targets across sprint issues; gating sprint execution on `ready-to-implement-gate` results; integration with sprint FSM dispatch logic
- **Out of scope**: Changes to how learning tests are defined or registered in the registry; modification of individual issue execution logic within a sprint; changes to `sprint-refine-and-implement.yaml` or `sprint-build-and-validate.yaml` (the pre-flight is Python-level in `run.py`, not YAML-level)

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/sprint/run.py` — `_cmd_sprint_run()`: insert pre-flight block after `issue_infos = manager.load_issue_infos(issues_to_process)` (~line 282), before dependency analysis. This is the primary change.
- `scripts/little_loops/cli/sprint/__init__.py` — `main_sprint()`: wire `add_skip_learning_gate_arg(run_parser)` alongside `add_skip_analysis_arg(run_parser)` (~line 67).
- `scripts/little_loops/cli_args.py` — add `add_skip_learning_gate_arg(parser)` factory (~line 205, after `add_skip_analysis_arg`).
- `scripts/little_loops/fsm/executor.py` — `_execute_learning_state()` (~line 738): add staleness check via `is_record_stale()` after a `proven` record is returned by `check_learning_test()`. **Hard ENH-2208 dependency.**

### Dependent Files (Callers/Importers)

- `scripts/little_loops/sprint.py` — `SprintManager.load_issue_infos()`: returns `list[IssueInfo]`; each `IssueInfo.learning_tests_required` is already a `list[str] | None` parsed from frontmatter. No changes needed.
- `scripts/little_loops/issue_parser.py` — `IssueInfo.learning_tests_required: list[str] | None`: the parsed field consumed by the pre-flight. No changes needed.
- `scripts/little_loops/learning_tests/__init__.py` — `check_learning_test(target)` and `LearnTestRecord`: imported by executor and indirectly by the gate loop. No changes needed.
- `scripts/little_loops/learning_tests/gate.py` — `is_record_stale(record, stale_after_days)`: called by updated `_execute_learning_state()`. No changes needed (delivered by ENH-2208).
- `scripts/little_loops/learning_tests/extractor.py` — `extract_learning_targets(issue_text, *, llm_call=None)`: fallback extraction for issues with `learning_tests_required: null`. No changes needed (delivered by ENH-2209).
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — receives `targets` via `--context targets=<csv>`; no changes needed.
- `config-schema.json` — `learning_tests.enabled` already exists (boolean, default `false`); **no schema changes needed**.

### Subprocess Invocation Pattern

Model after `scripts/little_loops/cli/loop/_helpers.py` (lines 1563–1576):

```python
cmd = [
    "ll-loop", "run", "ready-to-implement-gate",
    "--context", f"targets={','.join(all_targets)}",
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    # print blocking targets and which issues contributed them
    sys.exit(1)
```

The `--context targets=<csv>` value is CSV-split inside `ready-to-implement-gate.yaml` via `targets_csv: "${context.targets}"`.

### Tests

- `scripts/tests/test_sprint_integration.py` — use `sprint_project` fixture; add `TestSprintPreflightGate` class with:
  - `test_dedup_targets_across_issues`: two issues both list `["anthropic"]`; assert gate subprocess called once with `targets=anthropic`
  - `test_empty_target_noop`: issue infos have no `learning_tests_required`; assert gate subprocess not called
  - `test_abort_on_unproven_target`: gate subprocess exits 1; assert sprint exits 1 and error message names blocking issue
  - `test_skip_learning_gate_bypass`: `args.skip_learning_gate = True`; assert gate subprocess not called
  - `test_disabled_lt_config_skips_preflight`: `config.learning_tests.enabled = False`; assert gate subprocess not called

### Documentation

- `docs/guides/SPRINT_GUIDE.md` — document `--skip-learning-gate` flag and `learning_tests.enabled` config interaction
- `docs/reference/CONFIGURATION.md` — note that `learning_tests.enabled` now gates sprint pre-flight in addition to the discoverability hook

### Configuration

- `learning_tests.enabled` (boolean, default `false`) — **already exists** in `config-schema.json` (~line 939). No schema change needed. ENH-2210 extends what this flag gates (sprint pre-flight) without altering its definition.

## Impact

- **Priority**: P3 — Parent EPIC-2207 is not time-sensitive; improves gate reliability without blocking current workflows
- **Effort**: Small — Pre-flight block in `_cmd_sprint_run()` plus a new `--skip-learning-gate` arg; no YAML loop changes needed
- **Risk**: Low — Additive gating logic; existing sprint behavior unchanged when `learning_tests.enabled: false` or targets list is empty
- **Breaking Change**: No (new opt-in behavior gated on `learning_tests.enabled`)

## Labels

`enhancement`, `sprint`, `learning-tests`, `preflight`, `cli`

---

## Cross-Reference: Shared Utility with ENH-2219

**Note** (added by EPIC-2207 scoping review): The gating logic for sprint pre-flight should be extracted into a shared utility at `scripts/little_loops/learning_tests/gate.py` that both ENH-2210 (sprint-level batch gate) and ENH-2219 (per-worktree gate for `ll-parallel`) call. This avoids two separate implementations needing identical changes when gating behavior evolves.

- **Shared API surface**: `run_proof_gate(issue_file: str) -> tuple[GateResult, list[str]]` where `GateResult` is a `ProofGate` enum (`PASS`, `BLOCKED`) and `list[str]` are the blocking target names
- ENH-2210 calls this once per sprint (batch mode, aggregating all issues)
- ENH-2219 calls this per worktree (single-issue mode)
- `--skip-learning-gate` flag is handled at the caller level, not inside the utility

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`ProofGate` enum and `run_proof_gate()` do NOT exist** in `scripts/little_loops/learning_tests/gate.py`. The file contains only `is_record_stale(record, stale_after_days) -> bool`. The EPIC-2207 cross-reference describing this API is a design aspiration, not current code. The subprocess path (`ll-loop run ready-to-implement-gate`) is the correct implementation approach and requires no new Python API surface on `gate.py`. The `ProofGate`/`run_proof_gate` design is deferred.
- The sprint pre-flight therefore uses direct subprocess invocation as described in Implementation Steps above.

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue depends on ENH-2209 (auto-population of `learning_tests_required`). The sprint pre-flight's effectiveness relies on `learning_tests_required` being reliably populated in issue frontmatter. To handle issues refined before ENH-2209 ships, the pre-flight should include a fallback: for issues without `learning_tests_required`, perform ad-hoc extraction by importing the shared extraction utility from ENH-2209 rather than duplicating the logic inline.

**Lifecycle note**: The fallback is a temporary compatibility shim for issues refined before ENH-2209 ships. Once ENH-2209 is shipped and all active sprint issues have been re-refined, the fallback path should be flagged for removal via a `TODO(stale-after-ENH-2209)` comment.

This issue is declared as `depends_on: ENH-2209` in frontmatter — soft ordering, not a hard block, because the fallback provides resilience. See [[ENH-2209]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2210's sprint pre-flight routes through `ll-loop run ready-to-implement-gate`, which runs via the FSM executor. `executor.py`'s `_execute_learning_state` calls `check_learning_test()` directly — bypassing ENH-2208's stale-age gate. After ENH-2208 ships, a date-old proven record will be passed by the sprint pre-flight even though the same record would block the discoverability hook. The integration map must include `scripts/little_loops/fsm/executor.py` with a note that `_execute_learning_state` must be updated to call `is_record_stale()` (exposed by ENH-2208). This issue is declared `depends_on: ENH-2208` in frontmatter as a hard dependency — the sprint pre-flight gives false confidence without ENH-2208's helper. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): The canonical path for the shared gate utility is `scripts/little_loops/learning_tests/gate.py` (confirmed by ENH-2208). Downstream calls from this issue should import from that path. See [[ENH-2208]].

**Note** (added by `/ll:audit-issue-conflicts`): The Configuration section of this issue labels `learning_tests.enabled` as a "new config key." This is incorrect — the key already exists in `config-schema.json` (added in an earlier feature). ENH-2210 must not add a new schema entry for this key. Only the pre-flight logic wiring is new; the config key itself requires no schema changes. See [[ENH-2212]].

**Note** (added by `/ll:audit-issue-conflicts`): The fallback for issues without `learning_tests_required` ("import the shared extraction utility from ENH-2209") requires ENH-2209 to deliver `scripts/little_loops/learning_tests/extractor.py` with `extract_learning_targets(issue_text: str) -> list[str]`. Without this helper, the fallback cannot be implemented as a Python import. Verify ENH-2209 has committed to this artifact before implementing the fallback. See [[ENH-2209]].

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`extractor.py` exists and ships `extract_learning_targets(issue_text, *, llm_call=None) -> list[str]`** — confirmed at `scripts/little_loops/learning_tests/extractor.py`. The `llm_call` parameter is a mock injection point for unit tests (pattern: `_make_llm(response)` factory in `test_learning_tests_extractor.py`). The fallback can be implemented now.
- **`is_record_stale(record, stale_after_days) -> bool`** — confirmed at `scripts/little_loops/learning_tests/gate.py` (the only export in that file). Clamps threshold to min 1; returns `False` on unparseable dates.
- **`config-schema.json` `learning_tests.enabled`** — confirmed at ~line 939. Boolean, default `false`. Python model: `LearningTestsConfig.enabled` in `scripts/little_loops/config/features.py`.

## API/Interface

- **Config key**: `learning_tests.enabled` (boolean, default `false`) — enables the pre-flight assumption gate
- **CLI flag**: `ll-sprint --skip-learning-gate` — bypasses the pre-flight check for emergency runs when `learning_tests.enabled: true`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-18_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 72/100 → MODERATE

### Concerns
- **run_proof_gate() API inconsistency**: The Cross-Reference section declares `run_proof_gate(issue_file: str) -> tuple[GateResult, list[str]]` as the shared calling pattern (for both ENH-2210 and ENH-2219), but implementation step 5 uses a subprocess call to `ll-loop run ready-to-implement-gate`. These are two different approaches. `gate.py` currently only has `is_record_stale()` — no ProofGate enum, no `run_proof_gate()`. **Resolved by refine-issue research**: subprocess approach is correct; `ProofGate`/`run_proof_gate` do not exist. See Cross-Reference Codebase Research Findings above.
- **Two sprint loop YAMLs may both need pre-flight**: `sprint-refine-and-implement.yaml` and `sprint-build-and-validate.yaml` both exist. **Resolved by refine-issue research**: pre-flight is Python-level in `_cmd_sprint_run()`, so it applies to all sprint modes without YAML changes.

### Outcome Risk Factors
- The aggregation step — collecting `learning_tests_required` across all sprint issues, deduplicating, and building the comma-list for `ll-loop run` — has no implementation spec. **Resolved by refine-issue research**: use `IssueInfo.learning_tests_required` from `manager.load_issue_infos()` (already populated before dependency analysis); Python-level dedup in `_cmd_sprint_run()`.
- Choosing the Python `run_proof_gate()` API (Cross-Reference path) would require adding a ProofGate enum and `run_proof_gate()` to `gate.py` before ENH-2210 is complete; this is not reflected in the Integration Map. **Resolved**: subprocess path requires no changes to `gate.py`.

## Session Log
- `/ll:manage-issue` - 2026-06-19T01:31:20Z - `manage-issue-ENH-2210`
- `/ll:ready-issue` - 2026-06-19T01:08:24 - `2690acfa-1efa-4b91-94a1-191d08fe970d.jsonl`
- `/ll:refine-issue` - 2026-06-19T00:57:36 - `5ef1ec88-2748-42a3-b202-6ca293c1e881.jsonl`
- `/ll:refine-issue` - 2026-06-18T00:00:00Z - `790de704-0be2-4062-b4e4-b1d92251068c.jsonl`
- `/ll:confidence-check` - 2026-06-18T00:00:00Z - `449295f0-1ff8-4bbd-8d15-eb9f0a8be265.jsonl`