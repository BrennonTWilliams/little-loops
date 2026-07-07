---
id: ENH-2502
title: "Lock Tier 0 verification trace set (\u22652 traces) for FEAT-2470 measurement"
type: ENH
priority: P2
status: open
size: Small
captured_at: '2026-07-06T00:00:00Z'
discovered_date: 2026-07-06
discovered_by: issue-split
parent: EPIC-2456
relates_to:
- ENH-2471
- FEAT-2470
- ENH-2479
- ENH-2477
decision_needed: false
labels:
- token-cost
- testing
- measurement
- tier-0
confidence_score: 98
outcome_confidence: 88
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 23
---

# ENH-2502: Lock Tier 0 verification trace set (≥2 traces) for FEAT-2470 measurement

## Summary

Lock the Tier 0 trace set (Option A from the 2026-07-05 decision: 2 verified
single-model `general-task` runs) as fixtures, capture baseline cost per trace,
and report FEAT-2470's before/after delta against the locked set. This is the
trace-set half of the now-closed ENH-2471; the P1 edit-batch hook regression
test half already shipped under that issue (via FEAT-2470 + ENH-2499, completed
2026-07-06). Partially resolves EPIC-2456 Open Question #6 (this issue owns the
Tier 0 trace set; ENH-2479 owns the F5 streaming-parity set; F4/F8 sets remain
TBD per the epic's children list).

## Motivation

EPIC-2456's Tier 0 success metrics require a locked trace set so every "win"
claim is measured against a stable baseline. Without it, before/after
comparisons drift with whatever runs happen to be on disk. The
`scripts/little_loops/cli/loop/_helpers.py:1652-1714` `_print_usage_summary`
aggregator is the canonical cost-computation consumer; the locked-set baseline
must use the same per-state aggregation order so diffs are directly comparable.

## Predecessor

**ENH-2471** (split 2026-07-06, `status: done`). The P1 edit-batch hook
regression test half shipped via FEAT-2470 (`status: done`, 2026-07-06) +
ENH-2499 (`status: done`, 2026-07-06T04:22:16Z); `test_edit_batch_hook.py`
holds 11 tests, dispatch parity lives in `test_hook_intents.py`. The 500+ lines
of Integration Map / Wiring Phase content in ENH-2471 were authored against
the since-abandoned `EditBatchNudgeConfig` design (the shipped handler uses no
new config keys — verified by `grep -rn edit_batch_nudge config-schema.json
scripts/little_loops/config/features.py` returning zero hits); that wiring is
explicitly out of scope for this trace-set work and is not inherited here.

## Current Behavior

No locked Tier 0 trace set exists. Any before/after claim against FEAT-2470's
Tier 0 wins is measured against whatever `general-task-*` runs happen to be
on disk under `.loops/runs/` — a moving target. The two confirmed-stable
traces (`general-task-20260608T194041` and `general-task-20260619T225602`) are
present today but have no fixture representation, no documented baseline cost,
and no test gating their use as comparators. EPIC-2456's Tier 0 success
metrics therefore have no enforcement mechanism.

## Locked Trace Set (Option A, 2026-07-05 decision)

| Trace ID | Rows | States | Cache footprint | Single-model? |
|---|---|---|---|---|
| `general-task-20260608T194041` | 56 | 6 (`define_done`, `plan`, `do_work`, `check_done`, `continue_work`, `final_verify`) | ~14.75M cache_read | ✅ `claude-sonnet-4-6` only |
| `general-task-20260619T225602` | 93 | 7 (above + `summarize_partial`) | ~48.07M cache_read | ✅ `claude-sonnet-4-6` only |

Source: `.loops/runs/<trace_id>/usage.jsonl` (both verified on disk today, exact
row counts confirmed). The `summarize_partial` state in trace 2 is a
**superset** of `general-task.yaml`'s canonical 6-state list; downstream F6
`PerStateCost` re-aggregation (ENH-2477) must tolerate the superset, not
assume exact equality.

**Why not 3–5 traces**: the supposed third candidate
(`.loops/runs/general-task-20260530T143631/`) exists but is empty — no
`usage.jsonl`, no artifacts (confirmed via `ls -la`). No other
`general-task-*` run directory exists. The `>= 2` relaxation reuses the
precedent at `scripts/tests/test_policy_builder_corpus.py:51-52` (`>= 12` /
`>= 6` corpus thresholds). Document this deviation with justification inside
the manifest's `_meta` envelope.

## Expected Behavior

- Two per-trace fixture JSONs check into `scripts/tests/fixtures/tier0_traces/`
  with: parsed `usage.jsonl` rows, computed baseline totals
  (`baseline_cost_usd`, `baseline_input_tokens`, `baseline_output_tokens`,
  `baseline_cache_read_tokens`, `baseline_cache_creation_tokens`), per-state
  aggregates keyed by the trace's state set, `has_unknown_model: false`, and a
  reserved `budget_accumulator: {}` sub-record (for FEAT-2476 forward-compat).
- A single `manifest.json` enumerates the locked set with `_meta` envelope
  (`schema_version`, `owner`, `lock_date`, `epic`, `tier`, `baseline_source`,
  deviation note for the `>= 2` relaxation).
- `scripts/tests/test_tier0_traces.py` parametrize-loads the manifest, asserts
  `len(traces) >= 2`, asserts each member file exists with a recorded baseline,
  and asserts each `baseline_cost_usd > 0` (sanity).
- `docs/observability/tier0-traces.md` describes the manifest schema + per-trace
  envelope + `_print_usage_summary` aggregation order so future re-aggregation
  matches.
- FEAT-2470's before/after delta is computed and stamped into the manifest's
  `_meta` envelope as a follow-on commit.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Two semantic clarifications surfaced by codebase-analyzer:

- **`has_unknown_model: false` is bucket-poison semantics, not
  row-poison.** `_print_usage_summary`
  (`scripts/little_loops/cli/loop/_helpers.py:1696-1700`) calls
  `estimate_cost_usd(...)` per row; a single `None` return (unknown model
  not in `MODEL_PRICING`) flips the entire bucket's
  `has_unknown_model` to `True` and renders the printed cost as `"n/a"`
  (line 1710). The fixture-level `has_unknown_model: false` is therefore
  the AND of all bucket-level flags — adding a third trace that touches
  a non-Claude model must either ensure its `model` resolves in
  `MODEL_PRICING` (e.g. a known codex/opencode/pi model) or relax the
  test assertion. The locked traces pass because every row resolves
  `claude-sonnet-4-6` in `pricing.py:24-29`.

- **`manifest.json` `_meta` envelope is load-bearing, not decoration.**
  The `_meta` convention is enforced at
  `scripts/tests/test_issue_template.py:42-49` (asserts
  `_meta.version == "2.0"` and `_meta.type == <type>`) and at
  `scripts/tests/test_init_core.py:2536-2551` (asserts
  `_meta.command_options` is present and non-empty). The
  `scripts/little_loops/init/detect.py:63-169` consumer reads
  `_meta` to drive detection logic. Model the
  `tier0_traces/manifest.json` `_meta` block on
  `scripts/little_loops/templates/python-generic.json` shape: a flat
  dict with `name` / `description` / `tags` plus domain-specific
  fields (`schema_version`, `owner`, `epic`, `tier`, `lock_date`,
  `baseline_source`).

## Scope Boundaries

**In**:
- `scripts/tests/fixtures/tier0_traces/manifest.json` (new)
- `scripts/tests/fixtures/tier0_traces/general-task-20260608T194041.json` (new)
- `scripts/tests/fixtures/tier0_traces/general-task-20260619T225602.json` (new)
- `scripts/tests/test_tier0_traces.py` (new)
- `docs/observability/tier0-traces.md` (new)
- Baseline cost computation using `_print_usage_summary` aggregation order
- FEAT-2470 before/after delta report

**Out** (explicitly retired from ENH-2471's wiring scope):
- All `EditBatchNudgeConfig` dataclass / schema / `ll-init` / adapter-parity /
  `BRConfig` / skill-doc work — the shipped handler uses no new config keys.
- Tier 1 telemetry (F5/F6 children own that — ENH-2479 for streaming-parity,
  ENH-2477 for per-state cost attribution).
- Trace sets for F4 / F8 (EPIC-2456 Open Question #6 assigns those to their
  own children).

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Four behavioral nuances about `_print_usage_summary` that the implementer
must respect when writing the baseline computation in step 2 and the test
in step 4 (these are not "optional polish" — getting them wrong produces
fixtures that drift from the canonical consumer):

1. **`cache_read` and `cache_creation` stay distinct internally, collapse
   in the print column.** `_print_usage_summary` accumulates the two
   channels independently per state
   (`scripts/little_loops/cli/loop/_helpers.py:1691-1694`), then renders
   them as a single combined `"cache"` column (line 1709: `cache = b["cache_read"] + b["cache_creation"]`).
   The per-trace fixture JSON envelope in step 3 MUST keep them separate
   (so F6 `PerStateCost` re-aggregation in ENH-2477 can attribute cost per
   channel); only the print path collapses them.

2. **Per-state `model` is overwritten by the LAST row.** The bucketed
   `model` field is assigned (not aggregated) on every row
   (`_helpers.py:1695`); the last row wins. For locked single-model traces
   (`claude-sonnet-4-6` only) this is a no-op — all rows agree. The
   `has_unknown_model: false` assertion in the test therefore implicitly
   guards "every row resolves to a pricing entry," not "every row's model
   is `claude-sonnet-4-6`."

3. **`has_unknown_model` is bucket-poisoned, not row-poisoned.** A single
   `estimate_cost_usd(...)` returning `None` (unknown model) flips the
   entire bucket's `has_unknown_model` to `True` and the printed cost to
   `"n/a"` (`_helpers.py:1697-1700, 1710`). The fixture-level
   `has_unknown_model: false` is therefore the AND of all bucket-level
   flags; an implementer adding a third trace that touches a non-Claude
   model must either ensure that trace's `model` resolves in
   `MODEL_PRICING` or relax this assertion.

4. **Print output is sorted lexicographically, not in YAML order.**
   `_helpers.py:1708` iterates `sorted(per_state.items())`. The
   per-trace fixture's `states: {...}` map may preserve canonical order
   for human readability, but downstream diff consumers MUST sort before
   comparing — otherwise F6 re-aggregation diffs will be order-sensitive.

5. **RFC3339 timestamp format.** Real `usage.jsonl` rows use
   `+00:00` suffix (e.g. `"2026-06-09T00:41:04.755670+00:00"`), not the
   `Z` suffix used in synthetic test rows. When the per-trace JSON
   embeds `rows` verbatim (step 3), the timestamp strings must be
   preserved exactly as written — do not normalize to `Z`.

6. **`@pytest.mark.parametrize` over a JSON list — idiomatic shape.**
   Mirror `scripts/tests/test_init_core.py:2536-2547`:

   ```python
   @pytest.mark.parametrize("trace", MANIFEST["traces"],
                            ids=[t["id"] for t in MANIFEST["traces"]])
   def test_each_trace_has_recorded_baseline(trace: dict) -> None:
       ...
   ```

   This is the project's canonical parametrize-over-fixture pattern;
   `test_policy_builder_corpus.py:21-29` inlines the iteration instead, so
   the parametrize form is the more explicit / better-failing choice.

### Steps

1. **Author the manifest** at `scripts/tests/fixtures/tier0_traces/manifest.json`:
   ```json
   {
     "_meta": {
       "schema_version": 1,
       "owner": "ENH-2502",
       "epic": "EPIC-2456",
       "tier": "tier-0",
       "lock_date": "2026-07-XX",
       "baseline_source": "host_cli_usage_block",
       "count_relaxation_note": ">=2 (was 3-5); see ENH-2502 § Locked Trace Set"
     },
     "traces": [
       {"id": "general_task_20260608T194041",
        "path": "general-task-20260608T194041.json",
        "loop": "general-task",
        "baseline_cost_usd": null},
       {"id": "general_task_20260619T225602",
        "path": "general-task-20260619T225602.json",
        "loop": "general-task",
        "baseline_cost_usd": null}
     ]
   }
   ```
   (`baseline_cost_usd` filled in step 3 once computed.)

2. **Compute baselines** from the on-disk `usage.jsonl` files using the
   `_print_usage_summary` aggregation order (`scripts/little_loops/cli/loop/
   _helpers.py:1652-1714`):
   ```python
   import json
   from pathlib import Path
   from little_loops.pricing import estimate_cost_usd

   for trace_id in ("general-task-20260608T194041",
                    "general-task-20260619T225602"):
       rows = [json.loads(line) for line in
               Path(f".loops/runs/{trace_id}/usage.jsonl").read_text().splitlines()]
       cost = sum(
           estimate_cost_usd(
               row["model"], row["input_tokens"], row["output_tokens"],
               row["cache_read_tokens"], row["cache_creation_tokens"],
           ) or 0.0
           for row in rows
       )
       # ...also group by state for the per-trace JSON's `states` sub-record
   ```
   The per-trace JSON's `states` keys MUST use the same state names as
   `scripts/little_loops/loops/general-task.yaml:32+` so ENH-2477's F6
   re-aggregation matches without remapping.

3. **Author the per-trace JSONs** at
   `scripts/tests/fixtures/tier0_traces/<trace_id>.json`:
   ```json
   {
     "schema": "usage_jsonl_v1",
     "trace_id": "general_task_20260608T194041",
     "source_path": ".loops/runs/general-task-20260608T194041/usage.jsonl",
     "model": "claude-sonnet-4-6",
     "has_unknown_model": false,
     "rows": [/* verbatim parsed usage.jsonl rows */],
     "totals": {
       "input_tokens": <int>,
       "output_tokens": <int>,
       "cache_read_tokens": <int>,
       "cache_creation_tokens": <int>,
       "baseline_cost_usd": <float>
     },
     "states": {
       "define_done": {...},
       "plan": {...},
       "do_work": {...},
       "check_done": {...},
       "continue_work": {...},
       "final_verify": {...}
     },
     "budget_accumulator": {}
   }
   ```
   Trace 2's envelope adds `summarize_partial` to its `states` map (superset,
   not equality).

4. **Author `scripts/tests/test_tier0_traces.py`** following
   `scripts/tests/test_policy_builder_corpus.py:51-52` (`>= 12` / `>= 6`):
   ```python
   from pathlib import Path
   import json
   import pytest

   FIXTURES_DIR = Path(__file__).parent / "fixtures" / "tier0_traces"
   MANIFEST = json.loads((FIXTURES_DIR / "manifest.json").read_text())


   def test_manifest_owner() -> None:
       assert MANIFEST["_meta"]["owner"] == "ENH-2502"
       assert MANIFEST["_meta"]["tier"] == "tier-0"


   def test_manifest_count_at_or_above_minimum() -> None:
       # >= 2 relaxation of original 3-5 AC; see issue § Locked Trace Set
       assert len(MANIFEST["traces"]) >= 2


   @pytest.mark.parametrize("trace", MANIFEST["traces"],
                            ids=[t["id"] for t in MANIFEST["traces"]])
   def test_each_trace_has_recorded_baseline(trace: dict) -> None:
       path = FIXTURES_DIR / trace["path"]
       assert path.exists(), f"missing fixture: {path}"
       envelope = json.loads(path.read_text())
       assert envelope["totals"]["baseline_cost_usd"] > 0
       assert envelope["has_unknown_model"] is False
       assert envelope["budget_accumulator"] == {}
   ```

5. **Verify**:
   ```bash
   python -m pytest scripts/tests/test_tier0_traces.py -v
   python -m pytest scripts/tests/                       # full suite, exit 0
   ```

6. **Author `docs/observability/tier0-traces.md`** describing:
   - Manifest format (`_meta` envelope + `traces` array)
   - Per-trace JSON envelope (`schema`, `rows`, `totals`, `states`,
     `budget_accumulator`)
   - The exact `_print_usage_summary` aggregation order
     (`scripts/little_loops/cli/loop/_helpers.py:1652-1714`) — required for
     downstream F6 / OTel consumers
   - Forward-compat notes for `budget_accumulator` (FEAT-2476) and the
     `has_unknown_model` flag (cross-host when non-Claude traces arrive per
     `docs/reference/HOST_COMPATIBILITY.md:132` `[^tok]` footnote)

   _Style template_: mirror `docs/guides/HISTORY_SESSION_GUIDE.md`
   (H1 title → "When to Use This Guide" intro → TOC → sections with
   file-path anchors). `docs/observability/` already exists (created
   by ENH-2475 on 2026-07-06 with `des-audit.md`); `tier0-traces.md` and
   ENH-2479's `streaming-parity-traces.md` will be the SECOND and THIRD
   docs there. Both must still land in the same PR (step 7) to keep
   the EPIC-2456 children's documentation coordinated.

7. **Land `docs/observability/tier0-traces.md` in the same PR as ENH-2479's
   `docs/observability/streaming-parity-traces.md`** — both extend
   `docs/observability/` (already populated by ENH-2475's `des-audit.md`)
   with EPIC-2456's measurement-layer docs. Coordinate via a shared PR.

8. **Stamp FEAT-2470 before/after delta** into the manifest's `_meta`
   envelope as a follow-on commit once the differential measurement is
   captured.

## Acceptance Criteria

- `scripts/tests/fixtures/tier0_traces/manifest.json` checked in with
  `_meta.owner == "ENH-2502"`, two members, and `>= 2` count assertion
  documented.
- Both per-trace JSONs checked in with non-zero `baseline_cost_usd` and
  `has_unknown_model: false`.
- `python -m pytest scripts/tests/test_tier0_traces.py -v` passes.
- `python -m pytest scripts/tests/` exits 0.
- `docs/observability/tier0-traces.md` describes the schema and aggregation
  order; lands in the same PR as ENH-2479's sibling doc.
- FEAT-2470 before/after delta is computed and recorded in the manifest's
  `_meta` envelope.

## Files Touched

**New**:
- `scripts/tests/fixtures/tier0_traces/manifest.json`
- `scripts/tests/fixtures/tier0_traces/general-task-20260608T194041.json`
- `scripts/tests/fixtures/tier0_traces/general-task-20260619T225602.json`
- `scripts/tests/test_tier0_traces.py`
- `docs/observability/tier0-traces.md`

**Modified**: none (gate lives on the fixture itself; no new config keys).

## Dependencies

- `scripts/little_loops/pricing.py:10-55` — `MODEL_PRICING` constants for
  `claude-sonnet-4-6` (input $3.00/M, output $15.00/M, cache_read $0.30/M,
  cache_creation $3.75/M). Required for baseline computation.
- `scripts/little_loops/cli/loop/_helpers.py:1652-1714` —
  `_print_usage_summary` aggregation order. Required for diff parity with
  `scripts/tests/test_usage_reporter.py:18-201`.
- `scripts/tests/conftest.py:42-189` — `fixtures_dir`, `load_fixture`,
  `temp_project_dir` helpers (use directly, do not redefine).
- `scripts/tests/test_policy_builder_corpus.py:51-52` — `>=`-threshold
  relaxation precedent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Additional load-bearing anchors surfaced by codebase-locator and
codebase-analyzer:

- `scripts/little_loops/subprocess_utils.py:44-52` — `TokenUsage` dataclass
  defines the canonical row schema (5 fields: `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`).
  The 6th field `state` is added by the executor at write time.
- `scripts/little_loops/subprocess_utils.py:449-470` — `run_claude_command()`
  populates `TokenUsage` from the host CLI's 4-field usage block.
- `scripts/little_loops/fsm/persistence.py:679-708` — actual `usage.jsonl`
  writer inside `PersistentExecutor._handle_event()`. Writes 9 fields per
  row: `state`, `iteration`, `action_type`, `model`, the 5 `TokenUsage`
  fields, and `timestamp` (RFC3339 with `+00:00` suffix).

_Wiring pass added by `/ll:wire-issue`:_
- The issue originally cited `scripts/little_loops/fsm/executor.py:1382-1392`
  as the write site. The actual writer is
  `scripts/little_loops/fsm/persistence.py:679-708`; the executor only
  populates `usage_events` which persistence then flushes. Implementer
  should anchor the per-trace JSON's `rows` field preservation on
  `persistence.py:679-708`, not the executor.
- `scripts/tests/test_usage_journal.py:1-209` — documents the row schema
  in test form (contract: rows are written only for `action_type: prompt`
  states).
- `scripts/tests/test_pricing.py:30-54` — direct cost-math assertion
  (`test_accuracy_within_15_percent`); models the per-row baseline math
  used in step 2.
- `scripts/tests/test_init_core.py:2536-2547` — canonical
  `@pytest.mark.parametrize("filename", LIST)` over fixture JSONs pattern;
  the implementer should mirror this for `test_each_trace_has_recorded_baseline`.
- `scripts/little_loops/init/detect.py:63-169` — consumer of `_meta`
  envelopes in `scripts/little_loops/templates/*.json`; proves `_meta`
  is a load-bearing convention (not decoration) and that
  `scripts/tests/test_issue_template.py:42-49` and `test_init_core.py:2536-2551`
  enforce its shape.
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` —
  top-level indexed case-list precedent (closest analog to the planned
  `tier0_traces/manifest.json` + per-case files layout).
- `scripts/tests/fixtures/harbor/` — per-task subdirectory + paired file
  precedent (`task_01/`, `task_02/`, `task_03/` each with `task.md` +
  `expected.json`).
- `scripts/little_loops/templates/python-generic.json` — `_meta` envelope
  convention (name, description, tags, command_options) — model the
  `_meta` block in `manifest.json` on this shape.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — observability-flavored doc
  style template (H1 title, "When to Use This Guide" intro, TOC, sections
  with file-path anchors). `docs/observability/` does not exist yet, so
  this is the closest existing style precedent.

The `temp_project_dir` conftest helper is NOT needed for this test —
`tier0_traces` fixtures live in the repo at import time, so module-level
`Path(__file__).parent / "fixtures" / "tier0_traces"` is the canonical
idiom (matches `test_policy_builder_corpus.py:14` and
`test_usage_reporter.py:11-15`).

_Wiring pass added by `/ll:wire-issue`:_

Conftest helpers exist at `scripts/tests/conftest.py:104-133`:
- `fixtures_dir` — function-scoped pytest fixture returning
  `Path(__file__).parent / "fixtures"`
- `load_fixture(fixtures_dir, *parts)` — returns `str` (not parsed JSON);
  used twice in the suite (`test_issue_parser.py:22-25`,
  `test_review_loop.py:711`)

These are **NOT used** by the planned `test_tier0_traces.py`. Two reasons:
(1) the manifest is loaded once at module-level (`MANIFEST = json.loads(...)`)
  which requires a literal path, not a pytest fixture; (2) the dominant
idiom across fixture-set tests (5+ examples — `test_policy_builder_corpus.py:14`,
`test_audit_loop_run_skill.py:15`, `test_debug_loop_run_synthesis.py:13`,
`test_review_loop.py:26`, `test_feat1544_loop_specialist_eval.py:20`) is
module-level `FIXTURES_DIR = Path(__file__).parent / "fixtures" / ...`.
Implementer should NOT add `fixtures_dir` as a test parameter — that would
break the module-level `MANIFEST` constant.

- `.ll/decisions.yaml::ARCHITECTURE-105` — already records the `>= 2`
  relaxation decision with `issue: ENH-2471` (the predecessor). This
  citation is **intentional and correct**: `ARCHITECTURE-105` captured the
  decision while ENH-2471 was still open. The new manifest's
  `_meta.owner: "ENH-2502"` is the per-artifact citation for the
  fixture itself. Implementer should NOT edit
  `.ll/decisions.yaml::ARCHITECTURE-105` to point at ENH-2502 — the
  decision and the artifact have different ownership semantics. If a
  follow-on decision is needed to record the ENH-2471 → ENH-2502 split,
  add a new entry (`ARCHITECTURE-106`-class or similar) rather than
  rewriting the existing one.

## Sibling Coordination

- **ENH-2479** (F5 streaming-parity trace set): must land
  `docs/observability/tier0-traces.md` and
  `docs/observability/streaming-parity-traces.md` in the same PR so the folder
  is created consistently.
- **ENH-2477** (F6 per-state cost attribution): per-trace JSON's `states: {...}`
  top-level key MUST use the same per-state keys as `general-task.yaml:32+`
  (`define_done`, `plan`, `do_work`, `check_done`, `continue_work`,
  `final_verify`); trace 2 additionally has `summarize_partial` — F6 must
  tolerate the superset.
- **FEAT-2476** (cost ceiling): reserved `budget_accumulator: {}` sub-record
  per trace for future `--max-cost` ceiling data.
- **FEAT-2478** (OTel): when `observability/tracing.py` lands, per-trace rows
  gain `gen_ai.usage.*` fields; the envelope schema bumps gracefully via the
  reserved `_meta.schema_version` slot.

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; § Tier 0 success metrics, Open Question #6 (trace-set owners) |
| `.issues/enhancements/P2-ENH-2471-tier-0-verification-trace-set-and-hook-regression-test.md` | Predecessor (closed); P1 hook test half shipped there; rationale for the `>= 2` relaxation |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | The work this issue measures; before/after delta target |
| `.issues/enhancements/P2-ENH-2479-f5-streaming-vs-blocking-cache-accounting-parity-trace-set.md` | Sibling F5 trace set; same-PR docs coordination |
| `.issues/enhancements/P2-ENH-2477-f6-per-state-cost-attribution.md` | Downstream F6 consumer of the `states` aggregate |
| `.loops/runs/general-task-20260608T194041/usage.jsonl` | First locked trace (56 rows) |
| `.loops/runs/general-task-20260619T225602/usage.jsonl` | Second locked trace (93 rows) |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md:54` | § Tier 0 success gate spells out the original 3-5 trace set requirement |
| `scripts/little_loops/cli/loop/_helpers.py:1652-1714` | `_print_usage_summary` aggregation order (canonical consumer) |
| `scripts/tests/test_policy_builder_corpus.py:51-52` | `>=`-threshold relaxation precedent |
| `scripts/tests/test_usage_reporter.py:18-201` | Aggregator parity check |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Additional anchors surfaced by codebase-locator and codebase-pattern-finder:

- `scripts/little_loops/subprocess_utils.py:44-52` — `TokenUsage` dataclass
  defines the canonical row schema (5 fields); the 6th `state` field is
  added by the executor at write time.
- `scripts/little_loops/subprocess_utils.py:449-470` —
  `run_claude_command()` populates `TokenUsage` from the host CLI's
  4-field usage block.
- `scripts/little_loops/fsm/persistence.py:679-708` — actual `usage.jsonl`
  writer inside `PersistentExecutor._handle_event()`. Writes 9 fields per
  row (4 writer-added + 5 TokenUsage); `fsm/executor.py:1382-1392` only
  populates `usage_events` which persistence then flushes — not the
  primary anchor.
- `scripts/tests/test_usage_journal.py:1-209` — documents the row
  schema in test form (contract: rows are written only for
  `action_type: prompt` states).
- `scripts/tests/test_pricing.py:30-54` — direct cost-math assertion
  (`test_accuracy_within_15_percent`); models the per-row baseline math
  used in step 2.
- `scripts/tests/test_init_core.py:2536-2547` — canonical
  `@pytest.mark.parametrize("filename", LIST)` over fixture JSONs
  pattern.
- `scripts/little_loops/init/detect.py:63-169` — consumer of `_meta`
  envelopes in `scripts/little_loops/templates/*.json`; proves the
  `_meta` convention is load-bearing (the `manifest.json` `_meta`
  block is more than decoration).
- `scripts/tests/fixtures/policy_builder/conformance_corpus.json` —
  top-level indexed case-list precedent (closest analog to the planned
  `tier0_traces/manifest.json` + per-case files layout).
- `scripts/tests/fixtures/harbor/` — per-task subdirectory + paired file
  precedent (`task_01/`, `task_02/`, `task_03/` each with `task.md` +
  `expected.json`); cited by `test_benchmark_fragment.py:299-336`.
- `scripts/little_loops/templates/python-generic.json` — `_meta`
  envelope convention (name, description, tags, command_options);
  enforce-via-test pattern at `test_issue_template.py:42-49` and
  `test_init_core.py:2536-2551`.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — observability-flavored doc
  style template (H1 title, "When to Use This Guide" intro, TOC,
  sections with file-path anchors); closest existing style precedent
  for `docs/observability/tier0-traces.md`. `docs/observability/`
  already exists as of 2026-07-06 (ENH-2475 created it with
  `des-audit.md`); this is the SECOND doc landing there, not the first.

## Impact

- **Priority**: P2 — gates the credibility of every Tier 0 "win" claim;
  partially resolves EPIC-2456 Open Question #6.
- **Effort**: Small — fixture selection + baseline capture + one regression
  test + one doc.
- **Risk**: Low — test/measurement scaffolding only; no production code paths
  touched.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-06 | Priority: P2 | Split from ENH-2471

## Session Log
- `/ll:ready-issue` - 2026-07-07T04:34:42 - `71556a01-644a-4aca-a3b7-5235418df0f0.jsonl`
- `/ll:wire-issue` - 2026-07-07T02:55:24 - `df9eb152-e5b0-421f-82b4-251e88e53f04.jsonl`
- `/ll:refine-issue` - 2026-07-07T02:43:55 - `6fad77bc-f16c-48a5-b236-3cc5a1594b2e.jsonl`
- issue-split - 2026-07-06 - Extracted trace-set half from closed ENH-2471. Predecessor ENH-2471 done via FEAT-2470 + ENH-2499 (P1 hook test shipped 2026-07-06). Stale EditBatchNudgeConfig wiring explicitly retired.