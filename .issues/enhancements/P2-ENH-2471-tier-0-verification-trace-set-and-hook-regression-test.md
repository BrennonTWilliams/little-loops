---
id: ENH-2471
title: "Tier 0 verification trace set (locked 3–5 traces) + P1 edit-batch hook regression test"
type: ENH
priority: P2
status: open
captured_at: "2026-07-03T00:00:00Z"
discovered_date: 2026-07-03
discovered_by: scope-epic
parent: EPIC-2456
relates_to: [FEAT-2470]
labels:
  - token-cost
  - testing
  - measurement
  - tier-0
---

# ENH-2471: Tier 0 verification trace set + P1 hook regression test

## Summary

Lock a 3–5 trace set for before/after measurement of FEAT-2470's Tier 0
techniques, and land the P1 edit-batch hook regression test. This is EPIC-2456
§ Children [TBD-2] and partially resolves the epic's Open Question #6 (locked
trace sets need owners and members — this issue owns the Tier 0 set).

## Scope

- Select 3–5 representative loop-run traces (e.g. `general-task` runs from `.loops/runs/` or `ll-logs eval-export`) and lock them as fixtures so every Tier 0 "win" is measured against a stable baseline.
- Record the baseline cost per trace via the host CLI `usage` block (Tier 1 telemetry is not yet online).
- Regression test for the P1 edit-batch `PostToolUse` hook (`scripts/tests/test_edit_batch_hook.py`) — fires on Edit/Write/MultiEdit, is a nudge not a block, and does not fire in non-automation contexts.

## Current Behavior

No locked trace set exists for Tier 0; any before/after claim is measured against a moving target. The P1 edit-batch hook (FEAT-2470) has no regression test.

## Expected Behavior

A locked 3–5 trace set with recorded baseline cost figures; FEAT-2470's delta is reported against it; the hook regression test runs in the standard suite.

## Acceptance Criteria

- Trace-set membership documented (fixture paths checked in or reproducibly derivable) with baseline token/cost figures.
- Before/after delta reported for FEAT-2470 on the locked set.
- Hook regression test passes under `python -m pytest scripts/tests/`.

## Scope Boundaries

- **In**: Tier 0 trace-set selection + baseline capture; the P1 edit-batch hook regression test.
- **Out**: Tier 1 telemetry (F5/F6 children own that); trace sets for F4/F8/streaming-parity (epic Open Question #6 assigns those to their own children).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; § Success Metrics (Tier 0), Open Question #6 |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | The work this measures |

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis (locator + analyzer + pattern-finder agents, 2026-07-04):_

### Files to Modify

**P1 hook regression test target:**
- The actual edit-batch handler `scripts/little_loops/hooks/edit_batch_nudge.py` **does not exist yet** — must be created end-to-end as part of FEAT-2470 before this test can land against the real handler. The test should:
  1. Invoke the real handler (once FEAT-2470 lands) — `scripts/tests/test_hook_post_tool_use.py:TestPostToolUseBaseline` is the layout template
  2. Verify dispatch-table registration via subprocess (`scripts/tests/test_hook_intents.py:test_dispatch_pre_tool_use_happy_path` at line 273, or `test_ll_hook_host_env_var_propagates` at line 422)

**Trace-set fixtures:** greenfield directory tree — no precedent for "locked trace set" in this repo. Create:
- `scripts/tests/fixtures/tier0_traces/manifest.json` — single source of truth; lists trace IDs + loop + lock date + baseline totals + `owner: ENH-2471`
- `scripts/tests/fixtures/tier0_traces/<run_id>.json` — one per trace: parsed events.jsonl plus captured `usage` block + baseline `total_cost_usd`
- A future `ll-verify-trace-set-locked` CLI gate (parallel to `ll-verify-docs`, `ll-verify-skill-budget`) — verify-on-demand, not required to land with this issue; the manifest format should support it

### Files to Create

- `scripts/tests/test_edit_batch_hook.py` (new) — Python-direct PostToolUse handler test. `_event()` factory at module top returning `LLHookEvent(host="codex", intent="edit_batch_nudge", payload={...}, cwd=...)`. Two test classes: `TestEditBatchNudgeBaseline` (no config / Edit/Write/MultiEdit fire + non-fire events) and `TestEditBatchNudgeWithAutomationContext` (config-gated test mirroring `TestPostToolUseWithSessionStore` layout). `monkeypatch.chdir(tmp_path)` pre-amble in every test method. `_write_config(tmp_path, *, automation=True)` helper for config-driven gates.
- `scripts/tests/test_tier0_traces.py` (new) — loads `manifest.json` + parametrize-loops each member. Asserts each member file exists with a recorded baseline. Optional: `test_corpus_is_non_trivial` sanity check (mirrors `scripts/tests/test_policy_builder_corpus.py:46-58`).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/post_tool_use.py:137–209` — the existing composite handler that the edit-batch nudge delegates from (line 204–207 is the precedent for Bash → `install_learning_gate`; the new line is `tool_name in {"Edit","Write","MultiEdit"}` → `edit_batch_nudge.gate(event)`, following decision **ARCHITECTURE-036** at `.ll/decisions.yaml:889–901`).
- `scripts/little_loops/hooks/__init__.py:_dispatch_table` (lines 72–95) — must register `edit_batch_nudge` alongside the existing intents.
- `scripts/little_loops/hooks/types.py:20–145` — `LLHookEvent` / `LLHookResult` wire format the new handler conforms to (`exit_code=0` + `feedback` is the nudge-not-block channel per the docstring at line 96).
- `hooks/hooks.json:65–143` — new `PostToolUse` entry with matcher `"Write|Edit|MultiEdit"` (after line 131, adjacent to the existing `*` matcher at line 65).
- `scripts/little_loops/pricing.py:58–78` — `estimate_cost_usd()` is the comparison source for baseline totals (per the issue's "Record the baseline cost per trace via the host CLI `usage` block" requirement).
- `scripts/little_loops/subprocess_utils.py:43–56, 449–470` — `TokenUsage` dataclass + usage-block parser for raw token capture.
- `scripts/little_loops/loops/general-task.yaml` — the harness loop the locked traces come from (only built-in loop with `general-task-*` run directories under `.loops/runs/`).
- `.loops/runs/general-task-20260608T194041/usage.jsonl` — first candidate (56-row trace with full state diversity: `define_done`, `plan`, `do_work`, `check_done`, `continue_work`, `final_verify`).
- `.loops/runs/general-task-20260619T225602/usage.jsonl` — second candidate.
- `.ll/decisions.yaml:889–901` — **ARCHITECTURE-036** delegate-from-`post_tool_use` precedent; the new handler should follow the same single-line dispatch (Decision Option A in BUG-2224/ENH-2212).

### Similar Patterns

- `scripts/tests/test_hook_post_tool_use.py:243–306` (`TestFileEventsWrite.test_per_tool_path_extraction`) — `@pytest.mark.parametrize` shape for table-driven Edit/Write/MultiEdit coverage.
- `scripts/tests/test_install_learning_gate.py:24–72` — nudge-only handler test template (`_bash_event` helper + `_write_config` + `_SESSION_CACHE.clear()` autouse fixture). The edit-batch test mirrors the same per-session-counter clear pattern.
- `scripts/tests/test_hook_intents.py:118–256` — `LLHookEvent` / `LLHookResult` round-trip tests (wire-format primitives).
- `scripts/tests/test_policy_builder_corpus.py:14–58` — `CORPUS = Path(__file__).parent / "fixtures" / "policy_builder" / "conformance_corpus.json"` is the closest precedent for a single-file locked-corpus layout.
- `scripts/tests/conformance/test_host_conformance.py:44–68` — `_GOLDEN_PATHS` constant + `@pytest.mark.parametrize(..., ids=[...])` for stable pytest test IDs.
- `scripts/tests/test_usage_journal.py:75–209` — `TokenUsage` + `PersistentExecutor` + `${run_dir}/usage.jsonl` round-trip; the closest existing fixture shape for trace rows.
- `scripts/tests/test_usage_reporter.py:11–15` (`_make_usage_jsonl` helper) — JSONL row writer for fixture loading.
- `scripts/tests/conftest.py:42–189` — existing `fixtures_dir`, `load_fixture`, `temp_project_dir`, `make_project`, `sample_config` helpers (use directly instead of redefining).

### Tests

- The two new test files above are the deliverables themselves.
- `scripts/tests/test_pricing.py:28–61` — covers `MODEL_PRICING` / `estimate_cost_usd` (touchstone: Tier 1 downstream must not regress this when the budget primitives land).
- `scripts/tests/test_subprocess_utils.py` — covers `TokenUsage` / `DetailedUsageCallback` usage parsing.
- `scripts/tests/test_locked_traces.py` — does NOT exist (this issue creates that file or equivalent).

### Documentation

- `docs/observability/tier0-traces.md` (new) — describes manifest format + per-trace schema; future `ll-verify-trace-set-locked` CLI gate references this. Place alongside `docs/observability/streaming-parity-traces.md` (the ENH-2479 sibling docs land in the same folder).
- `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md:54` — § Tier 0 success gate spells out the 3–5 locked trace set measurement requirement (the issue partially satisfies this).
- `.ll/decisions.yaml` — append an issue-scope decision when the manifest format lands (informational, not gating).

### Configuration

- `.ll/ll-config.json` — no new keys for Tier 0 trace set (gate lives on the fixture itself). Future `edit_batch_nudge.enabled` config flag would gate the handler on/off (default off → explicitly opt in); ENH-2471's test depends on this flag existing (mirroring `install_learning_gate`'s `learning_tests.enabled` pattern).
- `config-schema.json` — if the new flag lands, it must be declared here.

### Key patterns and constraints from research

- **No precedent for locked trace sets** in this repo — this issue creates the convention (`scripts/tests/fixtures/tier0_traces/manifest.json` + per-trace JSON).
- **Handler doesn't exist yet** — `edit_batch_nudge.py` is greenfield; this test issues the assumption that FEAT-2470 lands the handler first (or the test lands concurrent with FEAT-2470's T1 step). If FEAT-2470 not yet merged, write the test against a stub `edit_batch_nudge.handle` that returns `LLHookResult(exit_code=0)` — the test asserts on the contract, not the implementation.
- **Nudge-not-block contract** — exit 0 + non-None `feedback` is the correct nudge channel; exit 2 blocks (per `types.py:96`). Tests must assert `result.exit_code == 0`, not `result.exit_code == 2`.
- **No `rebuild.sh`** precedent — `Glob '**/rebuild.sh'` returns no files in this repo (the codebase convention is "rerun the loop to regenerate"). Plan to either follow that convention or land `rebuild.sh` in this PR.
- **`agent/*` audit-style candidates** (from FEAT-2470 research): the agents the test should NOT touch — `codebase-analyzer`, `codebase-pattern-finder`, `consistency-checker`, `plugin-config-auditor` get haiku-pinned by FEAT-2470; this issue does not need to verify those.

## Implementation Steps

_Added by `/ll:refine-issue` — concrete file references from research:_

1. **Land FEAT-2470 first** — the `edit_batch_nudge.py` handler module must exist before this test can invoke it. If shipping concurrently, write the test in a sibling PR/branch that pins to a stub `handle(event)` returning `LLHookResult(exit_code=0)` and merge after the real handler lands.

2. **Author `scripts/tests/test_edit_batch_hook.py`**:
   - Module docstring citing `ENH-2471` (per existing `test_hook_post_tool_use.py` docstring convention)
   - `_event(payload, *, cwd=None)` factory at module top
   - `_write_config(project_dir, *, automation=True, **kwargs)` helper
   - `class TestEditBatchNudgeBaseline` — covers the three fire-conditions (`Edit` / `Write` / `MultiEdit`) via `@pytest.mark.parametrize` and asserts non-fire events short-circuit to `LLHookResult(exit_code=0)` with no nudge
   - `class TestEditBatchNudgeWithAutomationContext` — when `.ll/ll-config.json` has the gate enabled, assert the nudge fires; when disabled, assert it doesn't
   - `monkeypatch.chdir(tmp_path)` pre-amble in every test method

3. **Trace-set selection**:
   - Pick 3–5 from `.loops/runs/general-task-*/usage.jsonl` that cover the full state set (`define_done`, `plan`, `do_work`, `check_done`, `continue_work`, `final_verify`).
   - Run `ll-logs eval-export --skill general-task --out scripts/tests/fixtures/tier0_traces/raw_eval_export.yaml --json` to get EvalFixture v1 records as cross-check.
   - Promote a subset to the locked set; record baseline `usage` block + `total_cost_usd` per trace (computed via `pricing.estimate_cost_usd()` per row of `usage.jsonl`).

4. **Author `scripts/tests/fixtures/tier0_traces/manifest.json`**:
   ```json
   {
     "owner": "ENH-2471",
     "tier": "tier-0",
     "epic": "EPIC-2456",
     "lock_date": "2026-07-XX",
     "baseline_source": "host_cli_usage_block",
     "traces": [
       {"id": "general_task_<run_id>", "path": "general_task_<run_id>.json", "loop": "general-task", "baseline_cost_usd": <float>}
     ]
   }
   ```

5. **Per-trace JSON** for each locked trace — parses `usage.jsonl` rows + captured baseline totals.

6. **Author `scripts/tests/test_tier0_traces.py`**:
   - `manifest = json.loads((FIXTURES_DIR / "tier0_traces" / "manifest.json").read_text())`
   - `assert manifest["owner"] == "ENH-2471"` (gate check)
   - `@pytest.mark.parametrize("trace_id,trace_meta", [...], ids=lambda t: t["id"])` — for each member, assert file exists + has a `baseline_cost_usd` record
   - Optional `test_manifest_is_non_trivial` (mirrors `test_policy_builder_corpus.py:46–58`)

7. **Verify**:
   - `python -m pytest scripts/tests/test_edit_batch_hook.py -v` passes
   - `python -m pytest scripts/tests/test_tier0_traces.py -v` passes
   - `python -m pytest scripts/tests/` exits 0

8. **Document**: `docs/observability/tier0-traces.md` (new) describes manifest format + per-trace schema; sibling to ENH-2479's `streaming-parity-traces.md`.

## Impact

- **Priority**: P2 — gates the credibility of every Tier 0 "win"; owns the epic's Tier 0 trace set (Open Question #6)
- **Effort**: Small — fixture selection + baseline capture + one regression test
- **Risk**: Low — test/measurement only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-07-04T20:24:50 - `c598e9f8-80b2-4ec0-9e0f-bc292080ce64.jsonl`

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-2] (Tier 0 verification)
