---
id: ENH-2533
type: ENH
priority: P3
status: done
captured_at: '2026-07-07T21:00:00Z'
completed_at: '2026-07-08T00:46:08Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- ENH-2530
decision_needed: false
labels:
- loops
- observability
confidence_score: 100
outcome_confidence: 83
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2533: rn-implement — per-issue outcomes and learning followups in summary.json

## Summary

Extend the `report` state in `scripts/little_loops/loops/rn-implement.yaml` so
`summary.json` contains structured per-issue outcomes and a
`learning_followups` list, instead of only bucketed counters.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposals 1 and 6). A 4-issue run
parked 3 issues for 3 distinct reasons, but `summary.json` reported only
`blocked: 2` / `learning_gate_blocked_pre_dequeue: 1`. Reconstructing *why*
each issue was parked required manually grepping `events.jsonl`, `failures.txt`,
and per-issue sidecar files.

## Current Behavior

`report` tallies counters from `blocked.txt`, `failures.txt`, `skipped.txt`,
etc. and writes a flat JSON of counts. Per-issue cause data already exists in
the run_dir as sidecars written by other states:

- `subloop_outcome_<ID>.txt` (IMPLEMENTED / MANUAL_REVIEW_NEEDED / MANUAL_REVIEW_RECOMMENDED / LEARNING_GATE_BLOCKED / ...)
- `pre_scores_<ID>.json` / `post_scores_<ID>.json`
- `convergence_<ID>.json`
- `learning_prove_attempted_<ID>.txt` / `learning_unproven_<ID>.txt`

None of this is aggregated; a subsequent run (or human) has no structured view
of why the previous run parked each issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Report state location**: `scripts/little_loops/loops/rn-implement.yaml` lines 1330–1392. Uses shell `printf` to assemble 14 scalar keys (`total_processed`, `implemented`, `decomposed`, `skipped`, `deferred`, `blocked`, `depth_capped`, `failed`, `sub_loop_crashes`, `scores_missing`, `size_review_failed`, `learning_gate_blocked`, `learning_gate_blocked_pre_dequeue`, `rate_limited`) — all integers.
- **Sidecar writers (verified line refs)**:
  - `subloop_outcome_<ID>.txt` — `rn-remediate.yaml` lines 767/778/790/812/814/952/960/967/977 (drifted from refine snapshot 801/803/810/818/825/835 after ENH-2530 added the `manual_review_handoff_<ID>.md` heredoc to `emit_needs_manual_review`); `rn-decompose.yaml` lines 227/244/250; `lib/common.yaml:subloop_rate_limit_diagnostic` line 346. Single token, no trailing newline.
  - `pre_scores_<ID>.json` — `rn-remediate.yaml:verify_scores_persisted` line 158 (then refreshed at line 695).
  - `post_scores_<ID>.json` — `rn-remediate.yaml:verify_re_assess_scores` line 628.
  - `convergence_<ID>.json` — `rn-remediate.yaml:check_convergence` lines 686–689 (single-line JSON: `id`, `pre_confidence`, `post_confidence`, deltas, `total_delta`).
  - `learning_unproven_<ID>.txt` — `rn-implement.yaml:check_learning_ready` line 614; space-separated unproven target names (e.g. `anthropic requests`).
  - `blocked_by_unmet_<ID>.txt` — `rn-implement.yaml:check_blocked_by` line 449.
- **Subloop outcome token enum** (de facto, open free-form): `IMPLEMENTED`, `NEEDS_DECOMPOSE`, `STALLED_NEEDS_DECOMPOSE`, `MANUAL_REVIEW_NEEDED`, `MANUAL_REVIEW_RECOMMENDED`, `IMPLEMENT_FAILED`, `SCORES_MISSING`, `ENV_NOT_READY`, `LEARNING_GATE_BLOCKED`, `RATE_LIMITED` (remediate side); `DECOMPOSED`, `NO_CHILDREN`, `SIZE_REVIEW_FAILED` (decompose side). Substring-superset: `STALLED_NEEDS_DECOMPOSE` ⊃ `NEEDS_DECOMPOSE`; `LEARNING_GATE_BLOCKED_PRE_DEQUEUE[_ATTEMPTED]` ⊃ `LEARNING_GATE_BLOCKED`.
- **Data flow**: `report` is reached only from `fifo_pop:on_yes` (line 180) / `select_next:on_yes` (line 356) when the queue empties, or from `*on_error` fallbacks (lines 182, 358). Never reached from a per-issue recording state — so all sidecars are guaranteed present in `run_dir` by the time `report` runs.
- **Human-readable echo** (lines 1387–1390): three lines starting with `=== rn-implement Complete ===`, then a `Processed/Implemented/Decomposed` summary, then a secondary-metrics line.

## Expected Behavior

`summary.json` additionally contains:

```json
{
  "per_issue": [
    {"id": "ENH-400", "outcome": "MANUAL_REVIEW_RECOMMENDED",
     "reason": "options-missing", "pre_scores": {...}, "post_scores": {...}}
  ],
  "learning_followups": [
    {"id": "BUG-401", "targets": ["anthropic"],
     "remedy": "/ll:explore-api anthropic"}
  ]
}
```

Aggregation happens entirely in the `report` shell state by reading the
existing sidecars — no new writes needed from other states.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema extension is additive**: existing 14 scalar keys stay (so `audit-loop-run` Step 6a/6b at `skills/audit-loop-run/SKILL.md:275-319` keeps working); `per_issue` and `learning_followups` are new top-level keys.
- **Per-issue record minimum fields** (derived from existing sidecar shape):
  - `id` — extracted from filename suffix
  - `outcome` — token from `subloop_outcome_<ID>.txt` (or derived from which flat-file ledger contains the ID — `skipped.txt` → "skipped", `blocked.txt` → "blocked", `deferred.txt` → "deferred", `depth_capped.txt` → "depth_capped", `rate_limits.txt` → "rate_limited")
  - `reason` — for tagged-failure cases, the matching tag from `failures.txt` (e.g. `SUB_LOOP_CRASH`, `SCORES_MISSING`, `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`)
  - `pre_scores` / `post_scores` — optional inclusion of the parsed `pre_scores_<ID>.json` / `post_scores_<ID>.json` body (multi-line JSON, may be omitted when absent to keep summary small)
  - `convergence` — optional `convergence_<ID>.json` record (single-line JSON, always safe to embed)
- **Learning-followup record fields** (derived from `learning_unproven_<ID>.txt` + `/ll:explore-api` contract):
  - `id` — issue ID
  - `targets` — parsed target names (whitespace-split)
  - `remedy` — `/ll:explore-api <targets>` invocation string (consistent with the hint message emitted by `rn-remediate.yaml:emit_learning_gate_blocked` line 836)
- **Distribution channel**: `scripts/little_loops/fsm/persistence.py:archive_run()` (lines 491–534) copies `summary.json` from `run_dir` into `.loops/.history/<run_id>-<loop_name>/summary.json`, so the enriched schema is automatically persisted into history — no separate archival change needed.

## Proposed Solution

- In `report`, glob `subloop_outcome_*.txt`, `pre_scores_*.json`,
  `post_scores_*.json`, `convergence_*.json`, `learning_unproven_*.txt` and
  assemble the two arrays with an inline python3 heredoc (jq is not a
  dependency).
- Include an `on_error:` route or fail-open echo so a malformed sidecar cannot
  crash the terminal report (MR-10: do not swallow parse errors silently —
  print a diagnostic line).
- Update the human-readable "=== rn-implement Complete ===" echo to mention
  followups count.
- Extend `scripts/tests/test_builtin_loops.py` coverage if it asserts the
  summary schema.

### Codebase Research Findings — Implementation Options

_Added by `/ll:refine-issue` — three implementation paths surfaced during research:_

**Option A — Single `python3 << 'PYEOF'` heredoc that builds the entire summary dict** (precedent: `loop-composer-adaptive.yaml:read_completed_summaries` lines 458–487, `goal-cluster.yaml:present_result` lines 687–738).

> **Selected:** Option A — single `python3 << 'PYEOF'` heredoc — directly mirrors the closest codebase precedent for multi-source JSON aggregation (`loop-composer-adaptive.yaml:read_completed_summaries`, lines 458–487) and the array-of-records shape (`goal-cluster.yaml:present_result`, lines 687–738). Keeps the whole aggregation in one Python block where `json.dumps` guarantees well-formed output for both the embedded sidecar bodies (`pre_scores_*.json`, `convergence_*.json`) and the new `per_issue` / `learning_followups` arrays. The MR-10 escape (`on_error: failed`) is the documented mitigation already exemplified by `read_completed_summaries:458`.

- Replace the existing shell `printf` block with one heredoc that reads all sidecars, builds `{**counters, "per_issue": [...], "learning_followups": [...]}`, and `json.dumps` to `summary.json`.
- Requires `on_error: done` (or `on_error: failed`) to satisfy MR-10 (`fsm/validation.py:_validate_parse_swallow` lines 1867–1913): the heredoc necessarily calls `json.loads` + catches `Exception`/`ValueError` + would exit 0 on parse-fail.
- Pros: single source of truth, JSON formatting guaranteed by `json.dumps`, easiest to extend later.
- Cons: replaces the existing shell `printf` block wholesale (touches more lines, larger diff).

**Option B — Hybrid: keep existing shell `printf` for scalars, add a `python3 -c` step that builds only `per_issue` + `learning_followups` JSON, splice into the shell output** (precedent: `auto-refine-and-implement.yaml:finalize` lines 238/263/285 — uses `python3 -c "..."` for `skipped_breakdown` then `printf` for the rest).
- Smaller diff: append one new computed variable + inject into the existing printf block via `"per_issue": ${PER_ISSUE_JSON},`.
- Pros: surgical change, mirrors the ENH-2385/2404 precedent already tested at `scripts/tests/test_builtin_loops.py:2238-2278` (`test_finalize_summary_has_closure_keys`, `test_finalize_summary_has_enh_2404_keys`).
- Cons: split responsibility between shell + Python makes the action harder to read; both halves must agree on key naming.

**Option C — Pure shell with `awk`/`grep`/`jq`-free JSON building** (jq is not a dependency — explicitly stated in the issue body).
- Build arrays of pre-formatted JSON object literals via shell, then concatenate. Highest risk of malformed JSON when a sidecar contains a stray quote.
- Cons: violates the "jq is not a dependency" preference by trying to replace jq with brittle shell. NOT recommended.

**Recommended**: Option A (single heredoc + `on_error: failed`). It is the cleanest mapping to the existing test pattern at `loop-composer-adaptive.yaml:read_completed_summaries` and matches the codebase's preferred pattern for multi-source JSON aggregation.

### Codebase Research Findings — MR-10 Compliance

_Added by `/ll:refine-issue` — MR-10 lint requires explicit `on_error:` when adding `json.loads`:_

- The current `report` state does **not** trigger MR-10 because it uses shell `printf` (no `json.loads`). Any of Options A/B above will introduce `json.loads`, triggering the lint.
- Two escape hatches:
  1. **`on_error: failed`** (preferred) — the diagnostic + state machine preserves the failure signal for `audit-loop-run` and follow-up runs. Precedent: `rn-implement.yaml:check_blocked_by` (line 457), `check_learning_ready` (line 622) already use `on_error:` routes to non-terminal safety states.
  2. **`parse_swallow_ok: true`** at the loop top level — adds to `meta_self_eval_ok: false` and `partial_route_ok: true` already declared at `rn-implement.yaml:48`. **Not recommended**: silently swallows real parse failures, masking data corruption.
- Diagnostic format expected by callers: a stderr line naming the malformed sidecar and parse error, then continue with empty/missing fields rather than aborting the whole report (so a single bad sidecar cannot break the entire run summary).

### Codebase Research Findings — Test Pattern

_Added by `/ll:refine-issue` — model new tests after `_run_finalize`:_

- **Fixture-driven template**: `scripts/tests/test_builtin_loops.py:2025-2088` `_run_finalize()` helper — synthesizes a `run_dir` under `tmp_path`, writes fake sidecars with `Path.write_text()`, `replace()`s `${context.run_dir}` placeholders, runs `subprocess.run(["bash", "-c", script])`, parses the resulting `summary.json` with `json.loads(...)`.
- **No existing test asserts on a `per_issue` array shape** (verified by `scripts/tests/test_builtin_loops.py:8298/9253/2381/2245/2255/2289`) — closest precedent is `test_finalize_skipped_breakdown_aggregates_by_reason` (line 2289) which asserts on a dict, not an array.
- **Existing tests to extend** (not replace):
  - `TestReportAndTerminal` in `scripts/tests/test_rn_implement.py:350-404` — must continue to pass (additive schema).
  - `TestRnImplementDiagnosticOutcomes` in `scripts/tests/test_builtin_loops.py:8230-8280+` — `test_report_tallies_diagnostics_separately_from_failures` (line 8298) is the closest existing assertion.
  - `TestLearningGateConsistency.test_rn_implement_report_tallies_separately` (line 9253) and `test_rn_implement_pre_dequeue_tag_does_not_double_count` (line 9261).
- **New test methods to add**:
  1. `test_report_writes_per_issue_array_with_outcome_per_id` — synthesize `subloop_outcome_ENH-1.txt` + `subloop_outcome_BUG-2.txt`, assert both records appear in `summary["per_issue"]` with the right `outcome`.
  2. `test_report_writes_learning_followups_with_remedy` — synthesize `learning_unproven_BUG-3.txt` containing `anthropic`, assert the followup entry has `targets=["anthropic"]` and `remedy="/ll:explore-api anthropic"`.
  3. `test_report_malformed_sidecar_does_not_crash_run` — write a deliberately-broken `pre_scores_X.json`, assert that the report still completes (`on_error` route engages) and that a diagnostic line is emitted to stderr/stdout.
  4. `test_report_preserves_existing_scalar_keys` — guard against accidental counter-key removal: assert the original 14 keys remain in `summary.json`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option A — Single `python3 << 'PYEOF'` heredoc that builds the entire summary dict (with `on_error: failed` to satisfy MR-10).

**Reasoning**: Option A directly mirrors the closest codebase precedent for multi-source JSON aggregation — `loop-composer-adaptive.yaml:read_completed_summaries` (lines 458–487), which globs `step-*.json`, `json.load`s each with `except Exception: pass`, and `print(json.dumps(...))` — and matches the array-of-records shape via `goal-cluster.yaml:present_result` (lines 687–738). Putting the whole aggregation in one Python block means `json.dumps` guarantees well-formed output for both the embedded sidecar bodies and the new arrays; it eliminates the shell-escape risk flagged in Option B's "split responsibility between shell + Python" caveat and the pure-string fragility flagged for Option C. The MR-10 escape (`on_error: failed`) is the documented mitigation already exemplified by `read_completed_summaries:458`. Option B's precedent at `auto-refine-and-implement.yaml:finalize:238-285` is structurally similar but emits a single DICT (`skipped_breakdown`) from a single file — it does not match ENH-2533's two-array aggregation shape, and a hybrid implementation would be harder to read.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Single heredoc | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| B — Hybrid (printf + `python3 -c`) | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |
| C — Pure shell JSON building | 0/3 | 1/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: 87+ `python3 << 'PYEOF'` heredocs across `loops/` (5 already in `rn-implement.yaml` itself: `select_next:202`, `check_blocked_by:379`, `check_learning_ready:502`, `re_enqueue_unblocked:763`, `prove_learning_gate_targets:961`). Direct precedent for multi-source aggregation + MR-10 escape exists in `loop-composer-adaptive.yaml:read_completed_summaries:458-487`. Tests pass heredocs verbatim through `bash -c` (`test_builtin_loops.py:_run_finalize:2025-2088`).
- **Option B**: Direct precedent at `auto-refine-and-implement.yaml:finalize:238-285` for the hybrid SHAPE — but the precedent emits a DICT (`skipped_breakdown`) from a single file, not an array-of-records from multiple sidecars. All four existing `summary.json` writers in the codebase use shell `printf`, so this would be a closer shape-match overall. MR-10 sidestep via `|| echo '[]'` (`auto-refine-and-implement.yaml:253`) keeps the no-`on_error` shape of the current `report` state. Test pattern at `test_builtin_loops.py:2238-2278` is a direct template for additive key-presence assertions.
- **Option C**: Zero existing array-of-records JSON writers in pure shell anywhere in `loops/`. `lib/common.yaml` exposes 12 fragments and NONE build JSON. Sidecar contents from `failures.txt` (with embedded error messages containing quotes) and embedded `pre_scores_*.json` bodies (multi-line with quotes) are not shell-safe — the agent evidence flags this as the exact risk the issue body warns about. Reuse score 0.

## Impact

- **Severity**: Medium (observability; unblocks audit-loop-run and follow-up runs)
- **Effort**: Small
- **Risk**: Low (additive schema change; report state only)

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/rn-implement.yaml` — replace the `report` state body (lines 1330–1392) with an extended shell action that builds the enriched `summary.json`. Add `on_error: failed` (or another non-terminal fail-route) to satisfy MR-10. Update the human-readable echo lines (1387–1390) to surface `Per-issue records: N` and `Learning followups: N`.

### Dependent Files (Callers / Consumers of summary.json)

- `scripts/little_loops/fsm/persistence.py:archive_run()` lines 491–534 — copies `summary.json` from `run_dir` into `.loops/.history/<run_id>-rn-implement/summary.json`. No change required; new keys flow through automatically.
- `skills/audit-loop-run/SKILL.md:275-319` (Step 6a/6b) — reads summary.json to compute phantom / honest-failure / met / partial / degraded verdicts. New `per_issue` + `learning_followups` keys are additive; no change required for the existing verdict table, but Step 6b can now cite specific parked-issue IDs directly.
- `scripts/tests/test_audit_loop_run_skill.py:125, 144` — `test_skill_step6_reads_summary_json` and `test_skill_step6a_reads_enh_2404_keys`. Add a sibling `test_skill_step6b_reads_enh_2533_keys` asserting Step 6b references `per_issue` and `learning_followups`.
- `scripts/tests/test_fsm_persistence.py:732-748` — `test_archive_run_copies_summary_json_when_exists` asserts the archive contains `"implemented" in content` (line 750). Must continue to pass under the additive schema (the byte-for-byte passthrough preserves the new keys automatically — no test edit needed, but the implementation must not break the assertion).

#### Decoupling Notes — DO NOT confuse adjacent loops with rn-implement's `summary.json`

The following loops each emit or read their OWN `summary.json` with a distinct schema. They are NOT coupled to rn-implement's `per_issue` / `learning_followups` keys. Treat them as out-of-scope for ENH-2533:

- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:read_outcome` (lines 34–44) — `cat`s `summary.json` from inner rn-implement runs (read-only).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:finalize` (lines 151–294) — writes its own `summary.json` with `verdict` / `closed` / `not_closed` / `skipped` / `errored` / `skipped_breakdown` / `gate_blocked` / `parked_rate` (validated at `test_builtin_loops.py:2245` / `2255`). Distinct schema.
- `scripts/little_loops/loops/rn-remediate.yaml:530` — sub-loop writes its own `summary.json` with sub-loop-specific schema. Distinct.
- `scripts/little_loops/loops/general-task.yaml` (ENH-2365) — emits `summary.json` on terminal `done` with `{"verdict":"success","implemented":N,"failed_finals":M}`. Distinct schema.
- `scripts/little_loops/loops/autodev.yaml` — delegates `summary.json` to `auto-refine-and-implement:finalize`.
- `scripts/little_loops/loops/rn-build.yaml:synthesize_result` (lines 662–710) — emits `recommended_next_batch: [string]` array; NOT `learning_followups` (different namespace, different loop).
- `scripts/little_loops/loops/loop-composer-adaptive.yaml:read_completed_summaries` (lines 458–487) — the canonical precedent for Option A's `python3 << 'PYEOF'` heredoc aggregation; uses `on_error: abort_composer`.
- `scripts/little_loops/loops/goal-cluster.yaml:present_result` (lines 687–738) — `per_goal_outcomes` dict-keyed-by-ID precedent; terminal-state pattern, less applicable since `report` is pre-terminal.

### Similar Patterns (precedents to follow)

- `scripts/little_loops/loops/loop-composer-adaptive.yaml:read_completed_summaries` lines 458–487 — canonical example of array-of-records aggregation via `python3 << 'PYEOF'` heredoc with `on_error:` route. Closest match for Option A.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:finalize` lines 151–294 — hybrid `python3 -c "..." "$FILE"` for breakdown dict + shell `printf` for assembled summary. Closest match for Option B.
- `scripts/little_loops/loops/goal-cluster.yaml:present_result` lines 687–738 — `per_goal_outcomes` dict-keyed-by-ID precedent (terminal-state pattern; less directly applicable since `report` is pre-terminal).
- `scripts/little_loops/loops/rn-build.yaml:synthesize_result` lines 662–710 — `recommended_next_batch: [string]` array precedent for `learning_followups`.

### Tests

- `scripts/tests/test_rn_implement.py:350-404` — `TestReportAndTerminal` (extend — must continue to pass with the additive schema).
- `scripts/tests/test_rn_implement.py:946-1027` — learning-gate sidecar coverage (extend — verify `learning_unproven_<ID>.txt` is consumed in the new aggregation).
- `scripts/tests/test_builtin_loops.py:8230-8280+` — `TestRnImplementDiagnosticOutcomes.test_report_tallies_diagnostics_separately_from_failures` (extend — keep passing; substring assertions on `'grep -c "SCORES_MISSING"'` and `'grep -c "SIZE_REVIEW_FAILED"'` at line 8298 must remain in the new heredoc).
- `scripts/tests/test_builtin_loops.py:9198-9300` — `TestLearningGateConsistency.test_rn_implement_report_tallies_separately` (line 9253), `test_rn_implement_pre_dequeue_tag_does_not_double_count` (line 9261).
- `scripts/tests/test_builtin_loops.py:2025-2088` — `_run_finalize` helper (model new tests after this — synthesize `run_dir` under `tmp_path`, write fake sidecars, execute the action via `subprocess.run(["bash", "-c", script])`, parse and assert).
- `scripts/tests/test_fsm_validation.py:3702-3833` — MR-10 test class (no change; the new `on_error:` route will exercise existing `test_mr10_on_error_present_no_warning` since `_validate_parse_swallow` at `fsm/validation.py:1890-1891` skips states with `on_error` set).
- `scripts/tests/test_audit_loop_run_skill.py:125, 144` — add new sibling test for ENH-2533 keys.

#### Test preservation constraints (substring assertions that MUST remain in the report action body)

The following substrings are asserted by existing tests and must be preserved verbatim in the new `python3 << 'PYEOF'` heredoc (Implementation Step 1). Do NOT rename the sidecar filenames or reorganize the grep commands:

- `"summary.json"` — `test_report_state_writes_summary_json` (test_rn_implement.py:362)
- `"dequeue_count.txt"`, `"implemented_count.txt"`, `"decomposed_count.txt"` — `test_report_state_writes_summary_json` (test_rn_implement.py:362)
- `"LEARNING_GATE_BLOCKED_PRE_DEQUEUE"` and `"learning_gate_blocked_pre_dequeue"` — `test_report_tallies_pre_dequeue_separately` (test_rn_implement.py:976-982)
- `'grep -c "SCORES_MISSING"'`, `'grep -c "SIZE_REVIEW_FAILED"'` — `test_report_tallies_diagnostics_separately_from_failures` (test_builtin_loops.py:8298)
- `"LEARNING_GATE_BLOCKED"`, `"learning_gate_blocked"`, `"LEARNING_GATE_BLOCKED_PRE_DEQUEUE"`, `"learning_gate_blocked_pre_dequeue"`, `"LEARNING_GATE_BLOCKED_TOTAL"` — `TestLearningGateConsistency` (test_builtin_loops.py:9253-9274)
- `"skipped.txt"`, `"decomposed_count.txt"` — `test_report_decomposed_and_skipped_use_distinct_sources` (test_rn_implement.py:392)

#### Test fragility notes (NOT expected to break, but flagged for awareness)

- `scripts/tests/test_rn_implement.py:734` — `test_skip_issue_is_sole_skipped_txt_writer` iterates every state's action lines looking for `skipped.txt` writes. The new report state will add reads of `subloop_outcome_*.txt` and `learning_unproven_*.txt` but NOT writes to `skipped.txt`. This test only flags writes (`>>` or `>`), so it should remain safe.
- `scripts/tests/test_fsm_persistence.py:732+` — `test_archive_run_copies_summary_json_when_exists` reads the archived summary.json and asserts `"implemented" in content`. Additive passthrough will preserve this assertion automatically.

#### New test infrastructure (Implementation Step 4 enhancement)

Add a `_run_report` helper to `scripts/tests/test_rn_implement.py::TestReportAndTerminal`, modeled on `scripts/tests/test_builtin_loops.py:_run_finalize:2025-2088`. The helper should:
1. Synthesize a `run_dir` under `tmp_path`.
2. Write fake sidecar files (the 14 counter sidecars + `subloop_outcome_<ID>.txt` + `learning_unproven_<ID>.txt` + JSON sidecars as needed) via `Path.write_text()`.
3. `replace()` `${context.run_dir}` placeholders in the report action.
4. Run `subprocess.run(["bash", "-c", script], cwd=run_dir, capture_output=True, text=True)`.
5. Return parsed `summary.json` via `json.loads((run_dir / "summary.json").read_text())`.

#### New MR-10 direct test recommendation

No existing MR-10 test (`test_fsm_validation.py:3726+`) directly targets the `report` state. Add `test_report_has_on_error_route` to `scripts/tests/test_rn_implement.py::TestReportAndTerminal` (similar in shape to `test_failed_is_bare_terminal` at line 778), asserting `report.on_error == "failed"`. This guards against future regressions where the `on_error:` route is silently removed.

### Documentation

- `docs/guides/LOOPS_REFERENCE.md:405-427` — Output-artifacts table lists the current 14 summary.json keys. Add the new `per_issue` and `learning_followups` rows with their schemas.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md:42, 128-240, 297-305` — references `summary.json` semantics. Add a paragraph on the new per-issue/followup fields.
- `skills/audit-loop-run/SKILL.md:340-355` — Step 8 already references the `subloop_outcome_` artifact channel; add Step 6b enhancement noting the structured `per_issue` channel.
- `docs/reference/API.md:5314` — `archive_run()` docstring should mention the enriched schema is preserved verbatim.

### Configuration

- No `.ll/ll-config.json` keys required (per the issue body).
- The loop YAML's top-level flags (`rn-implement.yaml:48`) already declare `meta_self_eval_ok: false` and `partial_route_ok: true`. **Do NOT add `parse_swallow_ok: true`** — use `on_error: failed` instead (preferred per Codebase Research Findings above).

#### Compliance Anchors — `.ll/decisions.yaml` policy rules that constrain the implementation

These pre-existing decisions govern `summary.json` shape and MUST be honored by the implementation. They favor the additive approach and require no new entries:

- `.ll/decisions.yaml` line 1325–1330 (ENH-2250) — "When adding a new failure category, add a corresponding key to summary.json and a matching human-readable echo line in r…" → `per_issue` is a richer aggregation, not a new failure counter category, so no new counter or echo line is mandated. The Implementation Step 3 echo update should still surface the new arrays.
- `.ll/decisions.yaml` line 1733–1736 (BUG-2267 precedent) — "FSM shell states that write structured output files (JSON, YAML) must verify…" → the file-write itself was already verified by existing tests; the aggregation block must produce parseable JSON (guaranteed by `json.dumps`).
- `.ll/decisions.yaml` line 3033–3036 (ENH-2005) — "Preserve established output contracts (summary files, outcome tokens) when…" → additive change preserves all established keys; compliant.
- `.ll/decisions.yaml` line 3397 (ENH-2402) — "Blocked or gated outcomes must be tallied separately from failures in summary.json and subtracted from the generic failures…" → not triggered by `per_issue`/`learning_followups`.

#### Release-prep note

- `CHANGELOG.md` line 24 has a current `[Unreleased]` section. Per the project rule `feedback_changelog_no_unreleased.md` ("Don't put new CHANGELOG entries under `[Unreleased]`; promote to a concrete `## [X.Y.Z] - DATE` section during release prep"), the ENH-2533 entry should NOT be added to `[Unreleased]` here — it should land directly under the next concrete release version when cut.

## Implementation Steps

1. **Replace `report` action body** (`rn-implement.yaml:1330-1392`) with a `python3 << 'PYEOF' ... PYEOF` heredoc (Option A) that:
   - Reads scalar counters from `dequeue_count.txt`, `implemented_count.txt`, `decomposed_count.txt`, `skipped.txt`, `deferred.txt`, `blocked.txt`, `depth_capped.txt`, `failures.txt` (with grep -c tags), `rate_limits.txt` — preserving the existing 14-key schema.
   - Globs `subloop_outcome_*.txt`, extracts the ID from the filename suffix and the token from the file body; builds a `per_issue` array of `{id, outcome}` records.
   - Optionally enriches each record with `reason` (parsed from `failures.txt` lines containing the ID) and embedded `pre_scores` / `post_scores` / `convergence` from the JSON sidecars when present.
   - Globs `learning_unproven_*.txt`, splits each file's body on whitespace to get target names, builds a `learning_followups` array of `{id, targets, remedy}` records with `remedy = "/ll:explore-api " + " ".join(targets)`.
   - Assembles the full dict `{**scalars, "per_issue": [...], "learning_followups": [...]}` and `json.dump`s to `$RUN_DIR/summary.json` with `indent=2` for readability.
   - Wraps each sidecar read in `try/except (OSError, ValueError, json.JSONDecodeError)` — on parse error, append a diagnostic to a `summary_warnings.txt` sidecar and skip the record (do not abort the whole report).
   - Prints the same three human-readable `echo` lines (with updated followups count line) plus a `Wrote summary.json: N per-issue records, M learning followups` line.

2. **Add `on_error: failed`** to the `report` state (satisfies MR-10). Wire `failed:` to also write `summary_warnings.txt` if it isn't already present, so the diagnostic state is recoverable on the next run.

3. **Update the human-readable echo** (was lines 1387–1390) to include `Per-issue records: $PER_ISSUE_COUNT | Learning followups: $FOLLOWUP_COUNT` on the secondary-metrics line.

4. **Add new tests** in `scripts/tests/test_rn_implement.py` (or extend `TestReportAndTerminal`):
   - `test_report_writes_per_issue_array` — synthesize 3 `subloop_outcome_<ID>.txt` sidecars, assert all 3 records appear in `summary["per_issue"]`.
   - `test_report_writes_learning_followups_with_remedy` — synthesize 1 `learning_unproven_<ID>.txt` containing `anthropic requests`, assert the followup record has `targets=["anthropic", "requests"]` and `remedy="/ll:explore-api anthropic requests"`.
   - `test_report_malformed_sidecar_does_not_crash` — write a broken JSON sidecar; assert `summary.json` still parses, contains the broken sidecar's record with `outcome=None` or omits it, and a diagnostic was written.
   - `test_report_preserves_existing_scalar_keys` — assert all 14 existing keys are still present.

5. **Extend `TestLearningGateConsistency`** in `scripts/tests/test_builtin_loops.py:9198-9300` with a method that asserts the new aggregation consumes `learning_unproven_<ID>.txt` (substring assertion: `learning_unproven_*.txt` appears in the action body).

6. **Add `test_skill_step6b_reads_enh_2533_keys`** in `scripts/tests/test_audit_loop_run_skill.py` mirroring the existing `test_skill_step6a_reads_enh_2404_keys` pattern (line 144).

7. **Update docs**:
   - `docs/guides/LOOPS_REFERENCE.md:405-427` — append `per_issue` and `learning_followups` rows to the Output-artifacts table.
   - `docs/guides/RECURSIVE_LOOPS_GUIDE.md:128-240` — add a paragraph on the enriched summary schema.

8. **Verify**:
   - `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_builtin_loops.py::TestLearningGateConsistency scripts/tests/test_builtin_loops.py::TestRnImplementDiagnosticOutcomes scripts/tests/test_audit_loop_run_skill.py scripts/tests/test_fsm_validation.py -v` — full suite must pass.
   - `python -m mypy scripts/little_loops/` — no new type errors (Python heredoc is not type-checked; only relevant if any helpers are extracted into a module).
   - `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` — must not raise MR-10 or any new warnings.
   - `ruff check scripts/little_loops/loops/rn-implement.yaml` — no style issues (the YAML linter may flag indentation of the embedded Python block).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation (in addition to the Implementation Steps above):_

9. **Preserve all substring assertions in the new heredoc** (per `Test preservation constraints` under Integration Map → Tests). The existing tests at `test_rn_implement.py:362, 392, 976-982` and `test_builtin_loops.py:8298, 9253-9274` grep the action body for specific substrings — `dequeue_count.txt`, `implemented_count.txt`, `decomposed_count.txt`, `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`, `grep -c "SCORES_MISSING"`, etc. — that MUST remain in the new `python3 << 'PYEOF'` block (or the equivalent shell+Python hybrid if Option B is selected).

10. **Add `test_report_has_on_error_route`** to `scripts/tests/test_rn_implement.py::TestReportAndTerminal` (per `New MR-10 direct test recommendation`). Assert `report.on_error == "failed"` — guards against future regressions where the MR-10 escape route is silently removed.

11. **Add `_run_report` helper** to `scripts/tests/test_rn_implement.py::TestReportAndTerminal` (per `New test infrastructure`). Modeled on `test_builtin_loops.py:_run_finalize:2025-2088`, this helper synthesizes `run_dir` + sidecars and runs the report action in a subprocess so the four new test methods can drive end-to-end aggregation assertions.

12. **Confirm `scripts/tests/test_fsm_persistence.py:732+` `test_archive_run_copies_summary_json_when_exists`** continues to pass under the additive schema (the byte-for-byte passthrough in `archive_run()` automatically preserves the new keys — no test edit needed, but the implementation must not break the `"implemented" in content` assertion at line 750).

13. **Confirm `test_skip_issue_is_sole_skipped_txt_writer` (test_rn_implement.py:734)** is not impacted — the new report state reads `subloop_outcome_*.txt` and `learning_unproven_*.txt` but does NOT write to `skipped.txt`, so this test's writer-only check should remain safe (per `Test fragility notes`).

14. **Compliance Anchors**: The implementation must respect the four `.ll/decisions.yaml` rules (ENH-2250, BUG-2267, ENH-2005, ENH-2402) per `Compliance Anchors` under Integration Map → Configuration. None requires new entries — the additive approach already satisfies all four.

15. **Release-prep**: Do NOT add ENH-2533 to `CHANGELOG.md` `[Unreleased]` section (line 24). Per the project rule `feedback_changelog_no_unreleased.md`, the entry should land directly under the next concrete release version when cut.

16. **Decoupling guard**: When modifying the heredoc, do NOT touch `sprint-refine-and-implement.yaml:read_outcome`, `auto-refine-and-implement.yaml:finalize`, `rn-remediate.yaml:530`, `general-task.yaml`, `autodev.yaml`, or `rn-build.yaml:synthesize_result` — these adjacent loops emit/read their OWN distinct `summary.json` schemas and are out of scope for ENH-2533 (per `Decoupling Notes` under Integration Map → Dependent Files).

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/rn-implement.yaml:report` (lines 1330–1392) writes `summary.json` with all 14 existing scalar keys (`total_processed`, `implemented`, `decomposed`, `skipped`, `deferred`, `blocked`, `depth_capped`, `failed`, `sub_loop_crashes`, `scores_missing`, `size_review_failed`, `learning_gate_blocked`, `learning_gate_blocked_pre_dequeue`, `rate_limited`) at their original values.
- [ ] `summary.json` additionally contains `per_issue: [{id, outcome, ...}]` and `learning_followups: [{id, targets, remedy}]` top-level keys.
- [ ] Each `per_issue` record's `id` matches the issue ID encoded in a `subloop_outcome_<ID>.txt` filename, and `outcome` matches the token inside that file.
- [ ] Each `learning_followups` record's `targets` is a non-empty list of target names parsed from the matching `learning_unproven_<ID>.txt` body, and `remedy` equals `"/ll:explore-api " + " ".join(targets)`.
- [ ] `report` has an explicit `on_error:` route (per MR-10 lint); `parse_swallow_ok: true` is NOT added to the loop top-level.
- [ ] A malformed JSON sidecar (e.g. truncated `pre_scores_<ID>.json`) does NOT crash the report; the report completes, the affected record is omitted or marked with a sentinel, and a diagnostic is written to `summary_warnings.txt` (or echoed to stderr).
- [ ] `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` reports zero new warnings (MR-1 through MR-10 remain clean or improve).
- [ ] `scripts/tests/test_rn_implement.py` extends `TestReportAndTerminal` with the four new test methods listed in Implementation Step 4; all four pass under `python -m pytest scripts/tests/test_rn_implement.py -v`.
- [ ] `scripts/tests/test_builtin_loops.py:TestLearningGateConsistency` extends with a method asserting the new aggregation consumes `learning_unproven_*.txt`.
- [ ] `scripts/tests/test_audit_loop_run_skill.py` adds `test_skill_step6b_reads_enh_2533_keys` mirroring the ENH-2404 pattern at line 144.
- [ ] `docs/guides/LOOPS_REFERENCE.md:405-427` lists `per_issue` and `learning_followups` in the Output-artifacts table with their schemas.
- [ ] `skills/audit-loop-run/SKILL.md:275-319` (Step 6b) cites the new `per_issue` array as the source for per-issue verdicts.

## Resolution

Implemented Option A: replaced the `report` state body in `scripts/little_loops/loops/rn-implement.yaml` with a `python3 << 'PYEOF'` heredoc that builds an enriched `summary.json` containing the original 14 scalar counters plus two additive top-level keys:

- `per_issue: [{id, outcome, reason?, pre_scores?, post_scores?, convergence?}]` — one record per `subloop_outcome_<ID>.txt` sidecar, with the diagnostic reason cross-referenced from `failures.txt` and optional JSON sidecar embeddings.
- `learning_followups: [{id, targets, remedy}]` — one record per `learning_unproven_<ID>.txt` sidecar, with `remedy` formatted as `/ll:explore-api <targets>` (consistent with the hint emitted by `rn-remediate.yaml:emit_learning_gate_blocked`).

Malformed per-issue sidecars are written to a new `summary_warnings.txt` sidecar rather than aborting the report (MR-10 spirit — surface failure, do not silently swallow). The state declares an explicit `on_error: failed` route to satisfy MR-10 (the validator skips states with `on_error` set).

Tests added (8 new) and updated (2 existing):
- `test_rn_implement.py::TestReportAndTerminal` — `_run_report` helper modeled on `test_builtin_loops.py:_run_finalize`; plus `test_report_writes_per_issue_array_with_outcome_per_id`, `test_report_writes_learning_followups_with_remedy`, `test_report_malformed_sidecar_does_not_crash_run`, `test_report_preserves_existing_scalar_keys`, `test_report_has_on_error_route`.
- `test_builtin_loops.py::TestLearningGateConsistency` — `test_rn_implement_report_consumes_learning_unproven_sidecars`, `test_rn_implement_report_consumes_subloop_outcome_sidecars`. Updated `test_report_tallies_diagnostics_separately_from_failures` and `test_rn_implement_pre_dequeue_tag_does_not_double_count` to match the Python implementation (semantic intent — separate counters, no double-counting — preserved).
- `test_audit_loop_run_skill.py` — `test_skill_step6b_reads_enh_2533_keys` mirroring the existing ENH-2404 pattern.

Docs updated:
- `docs/guides/LOOPS_REFERENCE.md` — Output-artifacts table expanded with `summary.json` schema note.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — paragraph added on the enriched schema + downstream `archive_run()` propagation.
- `skills/audit-loop-run/SKILL.md` — Step 6a enhanced with the ENH-2533 visibility note (citing specific parked IDs from `per_issue` in verdict rationale).

Verification:
- `python -m pytest scripts/tests/` — 14215 passed, 35 skipped.
- `ruff check scripts/tests/test_rn_implement.py scripts/tests/test_builtin_loops.py scripts/tests/test_audit_loop_run_skill.py` — clean.
- `python -m mypy` on touched test files — clean.
- `ll-loop validate scripts/little_loops/loops/rn-implement.yaml` — clean (MR-10 stays silent via the `on_error: failed` route).

Decoupling guards honored: `sprint-refine-and-implement.yaml:read_outcome`, `auto-refine-and-implement.yaml:finalize`, `rn-remediate.yaml`, `general-task.yaml`, `autodev.yaml`, and `rn-build.yaml:synthesize_result` are untouched — these emit/read their own distinct `summary.json` schemas outside `rn-implement`'s scope.

## Session Log
- `/ll:manage-issue` - 2026-07-08T00:46:08 - `f65f2135-758e-4fda-a4ce-7d08a8258f23.jsonl`
- `/ll:ready-issue` - 2026-07-08T00:31:11 - `780acdc0-26bf-4aa1-844c-6adf3db1922b.jsonl`
- `/ll:confidence-check` - 2026-07-07T23:14:00 - `c8a52db6-2114-42b4-9644-1d2ebe91b605.jsonl`
- `/ll:wire-issue` - 2026-07-07T23:08:33 - `f9ec0e8a-cdaa-400f-a9d4-d5bdf7386ee3.jsonl`
- `/ll:decide-issue` - 2026-07-07T22:58:53 - `24cdeaea-b8cc-400a-800e-ee06ba0ab109.jsonl`
- `/ll:refine-issue` - 2026-07-07T22:52:38 - `5804340f-e2f5-4db5-9485-37433e0c9da8.jsonl`
