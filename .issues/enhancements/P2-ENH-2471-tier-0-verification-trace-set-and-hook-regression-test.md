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
relates_to: [FEAT-2470, ENH-2479]
decision_needed: false
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

_Wiring pass added by `/ll:wire-issue` (registration / schema / config out-of-band touchpoints):_
- `scripts/little_loops/hooks/__init__.py:50-54` — extend `_USAGE` block to advertise the new `edit_batch_nudge` intent alongside existing entries [Agent 1 finding]
- `scripts/little_loops/config/features.py:480-499` — add `EditBatchNudgeConfig` dataclass parallel to `LearningTestsConfig` (mirror `from_dict` / `to_dict` pattern) [Agent 2 finding]
- `scripts/little_loops/config/core.py:30,215,281` — wire up `EditBatchNudgeConfig.from_dict(data.get("edit_batch_nudge", {}))` in the central config loader [Agent 2 finding]
- `config-schema.json:949-957` — add `edit_batch_nudge.enabled: boolean default=false` block adjacent to the existing `learning_tests.enabled` precedent [Agent 2 finding]
- `hooks/adapters/opencode/index.ts` — adapter parity for `edit_batch_nudge` once the Python dispatch table registers it (mirror the `_dispatch_table` shape) [Agent 1 finding]
- `scripts/pyproject.toml:51-91` — when the future `ll-verify-trace-set-locked` CLI lands, register near line 86 (`ll-verify-triggers` precedent) [Agent 2 finding]

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

_Wiring pass added by `/ll:wire-issue` (additional CLI entry points + adapter parity that touch the locked traces or `edit_batch_nudge`):_
- `scripts/little_loops/cli/loop/run.py:102,381,480` — `ll-loop run` is the producer of `usage.jsonl` rows that feed the manifest baseline computation (read-only consumer reference) [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py:400,542` — `cmd_resume`; relevant if `.loops/.running/general-task-20260530T143631` is promoted to a locked trace after completion [Agent 1 finding]
- `scripts/little_loops/cli/logs.py` — `ll-logs` subcommands (`eval-export` already cited in Step 3); reads `usage.jsonl` indirectly via `_print_usage_summary` [Agent 1 finding]
- `hooks/adapters/opencode/README.md`, `hooks/adapters/codex/README.md` — adapter docs may need parity update when `edit_batch_nudge` is registered [Agent 1 finding]
- `scripts/little_loops/host_runner.py:1112` — comment cross-reference to `_dispatch_table`; verify comment stays consistent once `edit_batch_nudge` is registered [Agent 1 finding]

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

_Wiring pass added by `/ll:wire-issue` (guards, cross-checks, and pattern precedents):_
- `scripts/tests/test_general_task_loop.py:53-74` — tests the `general-task.yaml` state set; must continue passing once the manifest references these states [Agent 3 finding]
- `scripts/tests/test_ll_logs.py:3274-3594+` — `TestEvalExport` / `TestEvalExportMapping` cover the `ll-logs eval-export --skill general-task` cross-check called out in Implementation Step 3 [Agent 3 finding]
- `scripts/tests/test_benchmark_fragment.py:299-335` — `TestHarborFixtures` is the multi-dir fixture layout precedent that ENH-2479's `streaming-parity-traces` references [Agent 3 finding]
- `scripts/tests/test_usage_reporter.py:18-201` — full `_print_usage_summary` aggregation tests; per-trace `baseline_cost_usd` MUST match this aggregator's per-state order for diff parity [Agent 3 finding]
- `scripts/tests/test_fsm_persistence.py:1079-1191` — `test_meta_eval_written_on_llm_structured_in_meta_loop` shows the pattern for a future gap-fill test asserting on `action_complete` + `input_tokens` JSONL writes via `_handle_event` directly (defensible follow-on, not required by ENH-2471) [Agent 3 finding]

### Documentation

- `docs/observability/tier0-traces.md` (new) — describes manifest format + per-trace schema; future `ll-verify-trace-set-locked` CLI gate references this. Place alongside `docs/observability/streaming-parity-traces.md` (the ENH-2479 sibling docs land in the same folder).
- `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md:54` — § Tier 0 success gate spells out the 3–5 locked trace set measurement requirement (the issue partially satisfies this).
- `.ll/decisions.yaml` — append an issue-scope decision when the manifest format lands (informational, not gating).

_Wiring pass added by `/ll:wire-issue` (additional doc touchpoints the edit-batch handler and locked trace set will need):_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:215,225-277` — add `edit_batch_nudge` as a sibling nudge-style handler in the PostToolUse section (the `pre-tool-use.sh → little_loops.hooks.install_learning_gate.gate` precedent at line 215 is the layout template) [Agent 2 finding]
- `docs/reference/CLI.md:273,319,374,376,441,2328` — mirror the `learning_tests.enabled` + `--skip-learning-gate` precedent for the future `--skip-edit-batch-nudge` flag once `edit_batch_nudge.enabled` lands [Agent 2 finding]
- `docs/reference/loops.md:111` — cross-reference `usage.jsonl` schema block from new `docs/observability/tier0-traces.md` (sibling to `apply-research` per-state output block at line 196) [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md:132` — extend the `[^tok]` footnote for non-Claude hosts (manifest format currently implies Claude-only; add a `host:` field per trace when a non-Claude trace lands) [Agent 2 finding]
- `docs/ARCHITECTURE.md:1392-1402` — add an "EditBatchNudge Consumers" row to the LearningTestsConfig Consumers table [Agent 2 finding]
- `docs/reference/API.md:123` — add `edit_batch_nudge | EditBatchNudgeConfig` row in the config API table [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — mirror the schema entry for `edit_batch_nudge.enabled` (per the precedent at `learning_tests.enabled` lines 97-99 of `.ll/ll-config.json`) [Agent 1 finding]
- `CHANGELOG.md` — Tier 0 trace set + edit-batch hook regression test entry under the next `[X.Y.Z] - DATE` block (per `feedback_changelog_no_unreleased.md` rule; never under `[Unreleased]`) [Agent 2 finding]
- `docs/observability/` directory itself does not exist — coordinate with ENH-2479 to land `tier0-traces.md` and `streaming-parity-traces.md` in the same PR so the folder is created consistently [Agent 2 finding]

### Configuration

- `.ll/ll-config.json` — no new keys for Tier 0 trace set (gate lives on the fixture itself). Future `edit_batch_nudge.enabled` config flag would gate the handler on/off (default off → explicitly opt in); ENH-2471's test depends on this flag existing (mirroring `install_learning_gate`'s `learning_tests.enabled` pattern).
- `config-schema.json` — if the new flag lands, it must be declared here.

_Wiring pass added by `/ll:wire-issue` (specific line anchors for the new `edit_batch_nudge` config):_
- `config-schema.json:949-957` — mirror `learning_tests.enabled: boolean default=false` block shape for new `edit_batch_nudge` block (specific anchor documented in Files to Modify above)
- `scripts/little_loops/config/features.py:480-499` — `LearningTestsConfig` is the structural twin for `EditBatchNudgeConfig`; mirror its `from_dict` / `to_dict` shape
- `scripts/little_loops/config/core.py:30,215,281` — the central config loader already calls `LearningTestsConfig.from_dict(data.get("learning_tests", {}))`; add the parallel call for `edit_batch_nudge` once the dataclass lands
- `.ll/ll-config.json:97-99` — when `edit_batch_nudge.enabled` flag lands, add at the same level as `learning_tests`; Tier 0 trace set itself adds NO config keys (gate lives on the fixture per the issue's Configuration section)

### Key patterns and constraints from research

- **No precedent for locked trace sets** in this repo — this issue creates the convention (`scripts/tests/fixtures/tier0_traces/manifest.json` + per-trace JSON).
- **Handler doesn't exist yet** — `edit_batch_nudge.py` is greenfield; this test issues the assumption that FEAT-2470 lands the handler first (or the test lands concurrent with FEAT-2470's T1 step). If FEAT-2470 not yet merged, write the test against a stub `edit_batch_nudge.handle` that returns `LLHookResult(exit_code=0)` — the test asserts on the contract, not the implementation.
- **Nudge-not-block contract** — exit 0 + non-None `feedback` is the correct nudge channel; exit 2 blocks (per `types.py:96`). Tests must assert `result.exit_code == 0`, not `result.exit_code == 2`.
- **No `rebuild.sh`** precedent — `Glob '**/rebuild.sh'` returns no files in this repo (the codebase convention is "rerun the loop to regenerate"). Plan to either follow that convention or land `rebuild.sh` in this PR.
- **`agent/*` audit-style candidates** (from FEAT-2470 research): the agents the test should NOT touch — `codebase-analyzer`, `codebase-pattern-finder`, `consistency-checker`, `plugin-config-auditor` get haiku-pinned by FEAT-2470; this issue does not need to verify those.

### Second-pass re-verification (2026-07-05)

_Added by `/ll:refine-issue` — second pass after live re-research; reinforces the existing Integration Map with concrete code anchors:_

- **Single-model candidate traces** (verified): both candidate `usage.jsonl` files (`general-task-20260608T194041` 56 rows, `general-task-20260619T225602` 93 rows) contain **only `claude-sonnet-4-6`** — no `unknown`-model rows. Baseline cost computation does **not** need to handle `estimate_cost_usd()` returning `None`.
- **Second trace has heavy cache footprint** — `.loops/runs/general-task-20260619T225602/usage.jsonl:5` has `cache_read_tokens: 1517891`. This is a useful contrastive baseline for cache-aware Tier 0 wins.
- **`MODEL_PRICING` values for `claude-sonnet-4-6`** (from `scripts/little_loops/pricing.py:10–55`, verbatim): input $3.00/M, output $15.00/M, cache_read $0.30/M, cache_creation $3.75/M. Lock the per-trace baseline computation to these values when stamping `baseline_cost_usd`.
- **`usage.jsonl` writer** lives at `scripts/little_loops/fsm/persistence.py:637–655` (`PersistentExecutor._handle_event()`); only emits rows when `event_type == "action_complete"` and `input_tokens in event`. Shell states produce no rows.
- **`ActionResult.usage_events: list[TokenUsage]`** carrier type defined at `scripts/little_loops/fsm/types.py:83` — the in-memory bridge between runner output and the JSONL writer.
- **`_print_usage_summary()` consumer** lives at `scripts/little_loops/cli/loop/_helpers.py:1652–1714` — the canonical aggregator that calls `estimate_cost_usd` per row and groups by state. The locked-trace per-trace JSON must use the **same aggregation order** so future before/after diffs are directly comparable.
- **Sibling decisions worth knowing** (`.ll/decisions.yaml:844–873`): **SECU-028** restricts Edit via `allowed-tools` glob; **ARCH-029** pairs tool-level path restrictions with scope-boundary instructions. The new `edit_batch_nudge` should respect both when it surfaces a feedback message (the nudge can name the config flag the user has set to scope Edit).
- **`TestEditTool` precedent for MultiEdit-aware parametrize** at `scripts/tests/test_learning_tests_discoverability.py:247–274` — useful pattern for the Edit/Write/MultiEdit coverage shape.
- **Use `make_project(config, extra_dirs)` conftest factory** (`scripts/tests/conftest.py:139–186`) rather than redefining `_write_config` from scratch — it's the established helper for `.ll/ll-config.json`-plus-subdirs test setups and already returns `(project_root, issues_base)`.
- **Use module-level `FIXTURES_DIR` constant** for the new `scripts/tests/fixtures/tier0_traces/` (per `scripts/tests/test_audit_loop_run_skill.py:15` convention) — conftest's `fixtures_dir` is reserved for shared fixtures (e.g. `issues/bug-with-frontmatter.md`).
- **No third `general-task-*` candidate** exists under `.loops/runs/`; only two stable runs available. The locked set must be **3–5** per the acceptance criteria — recommend either (a) lowering the lock-date to include the `.loops/.running/general-task-20260530T143631` once it completes, or (b) lifting the trace set from a sibling loop if FEAT-2470's wins need broader coverage. Flag this for the implementer to confirm before locking the manifest.

### Wiring Pass — forward-compat invariants (added by `/ll:wire-issue`)

These cross-cutting concerns don't fit any single existing subsection; they MUST be in the manifest format from day one so downstream EPIC-2456 siblings can build on ENH-2471 without a re-lock.

**Manifest format invariants:**
- Top-level `schema_version: 1` and reserved `_meta` envelope on `scripts/tests/fixtures/tier0_traces/manifest.json` — supports future DES (ENH-2475) and OTel (FEAT-2478) annotations without breaking fixtures [Agent 2 finding]
- Per-trace JSON envelope: `{schema: "usage_jsonl_v1", rows: [...], totals: {...}, states: {...}}` — keep `totals` and `states` as separate top-level keys so F6 (`PerStateCost.from_history().to_dict()` per ENH-2477 line 69–71) can re-aggregate without re-parsing [Agent 2 finding]
- `has_unknown_model: bool` per-trace flag — mirrors `_helpers.py:1675,1698` semantics; required for cross-host forward-compat (non-Claude traces will start appearing per the `[^tok]` footnote at `docs/reference/HOST_COMPATIBILITY.md:132`) [Agent 2 + Agent 3 finding]
- Reserved `budget_accumulator:` sub-record per trace — for FEAT-2476 (`--max-cost` ceiling active during recorded run) so replay-via-`ll-loop run` is reproducible [Agent 2 finding]
- Document the exact `_print_usage_summary` aggregation order (`scripts/little_loops/cli/loop/_helpers.py:1652-1714`) in `docs/observability/tier0-traces.md` so future F6 re-aggregation matches [Agent 2 finding]

**Cross-issue coordination:**
- `docs/observability/` directory creation is a first-mover coupling — ENH-2471 (tier0-traces.md) and ENH-2479 (streaming-parity-traces.md) must land in the same PR [Agent 2 finding]
- ENH-2479's fixture layout (one dir per trace with `recorded.jsonl` + `expected.json`) differs from ENH-2471's flat `manifest.json` + per-trace JSON — reconcile in a follow-on central doc pass [Agent 2 finding]
- FEAT-2478 OTel envelope — when `observability/tracing.py` lands, per-trace rows gain `gen_ai.usage.*` fields; the envelope schema must bump gracefully via the reserved `_meta` slot [Agent 2 finding]
- ENH-2477 F6 PerStateCost compat — per-trace JSON's `states: {...}` top-level key MUST use the same per-state keys as `general-task.yaml:32+` (`define_done`, `plan`, `do_work`, `check_done`, `continue_work`, `final_verify`) [Agent 2 finding]

**Future `ll-verify-trace-set-locked` CLI** (out-of-scope for ENH-2471 but the manifest format MUST support it; layout template follows `verify_triggers.py:577-661`):
- `scripts/little_loops/cli/verify_trace_set_locked.py` (new) — single `main_verify_trace_set_locked() -> int` entry-point with `argparse` + `cli_event_context(DEFAULT_DB_PATH, "ll-verify-trace-set-locked", sys.argv[1:])` decorator [Agent 2 finding]
- `scripts/little_loops/cli/__init__.py:81-83` — import + `__all__` entry alongside `verify_triggers` [Agent 2 finding]
- `scripts/pyproject.toml:51-91` — `ll-verify-trace-set-locked = "little_loops.cli:main_verify_trace_set_locked"` near line 86 [Agent 2 finding]
- `docs/reference/CLI.md` — doc stub in the existing `ll-verify-*` cluster [Agent 2 finding]
- `scripts/tests/test_verify_trace_set_locked.py` (new) — mirror `test_verify_triggers.py` (`TestRunValidation`, `TestSkillTriggerResult` classes) [Agent 2 finding]

**hooks/hooks.json ordering invariant:**
- The new `PostToolUse` matcher `"Write|Edit|MultiEdit"` must NOT shadow the existing `*` matcher at `hooks/hooks.json:65` or the per-tool `Write`/`Edit` issue-auto-commit matchers at lines 89–130. The Claude-Code adapter at `hooks/adapters/claude-code/post-tool-use.sh:11` invokes `python -m little_loops.hooks post_tool_use` (singular intent), so the matcher change is purely host-side config [Agent 2 finding]

**Sibling-decision alignment:**
- The new `edit_batch_nudge` feedback message MUST respect **SECU-028** (Edit via `allowed-tools` glob, `.ll/decisions.yaml:844-873`) and **ARCH-029** (pair tool-level path restrictions with scope-boundary instructions) when naming the config flag the user has set to scope Edit [Agent 2 finding]

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

### Second-pass implementation notes (2026-07-05)

_Added by `/ll:refine-issue` — second-pass refinements after live re-research:_

- **Trace-set lock decision** — confirm with the user whether to:
  - (a) lock **just the 2 confirmed stable traces** (`.loops/runs/general-task-20260608T194041/` + `.loops/runs/general-task-20260619T225602/`) and **lower the manifest count assertion** to `>= 2`, OR
  - (b) lock **3+ traces** by either waiting for `.loops/.running/general-task-20260530T143631/` to complete (then promote) or pulling from a sibling loop if available.

  The acceptance criterion ("3–5 trace set") may need a follow-on note in the manifest justifying any deviation; document the decision in the per-trace JSON header.

- **Baseline-cost computation** — use `_print_usage_summary()`'s exact aggregation order (`scripts/little_loops/cli/loop/_helpers.py:1652–1714`) so diffs are directly comparable:
  ```python
  cost = sum(
      estimate_cost_usd(
          row["model"], row["input_tokens"], row["output_tokens"],
          row["cache_read_tokens"], row["cache_creation_tokens"],
      ) or 0.0
      for row in rows
  )
  ```

- **`edit_batch_nudge.py` stub for concurrent landing** — if shipping concurrent with FEAT-2470, the test stub should return `LLHookResult(exit_code=0)` with `feedback=None` (silent no-op), exercising the dispatch path but deferring the nudge-message contract to the real handler. The test class should be split: `TestEditBatchNudgeBaseline` (asserts dispatch + no-op contract) and `TestEditBatchNudgeWithAutomationContext` (asserts nudge fires when config flag is set, once FEAT-2470 lands).

- **Sibling docs to author** — `docs/observability/tier0-traces.md` (this issue) and `docs/observability/streaming-parity-traces.md` (ENH-2479 sibling) share the same folder convention. Land them together in a single docs PR to keep the folder self-consistent.

### Wiring Phase (added by `/ll:wire-issue` — 2026-07-04)

_These touchpoints were identified by wiring analysis and must be included in the implementation. Numbered to follow the existing 1–8 sequence above:_

9. **Register `edit_batch_nudge` in the Python dispatch table** — extend `scripts/little_loops/hooks/__init__.py:_dispatch_table` (lines 72-95) to include `"edit_batch_nudge": edit_batch_nudge.handle`, and extend the `_USAGE` block (lines 50-54) to advertise the new intent. Shape per `LLHookEvent → LLHookResult` contract at `scripts/little_loops/hooks/types.py:20-145`. (Step 2 lands concurrent with this.)

10. **Add `EditBatchNudgeConfig` to the config layer**:
    - `config-schema.json:949-957`-adjacent — add `edit_batch_nudge.enabled: boolean default=false` block mirroring `learning_tests.enabled` precedent
    - `scripts/little_loops/config/features.py:480-499` — add `EditBatchNudgeConfig` dataclass parallel to `LearningTestsConfig` (mirror `from_dict` / `to_dict` shape)
    - `scripts/little_loops/config/core.py:30,215,281` — wire `EditBatchNudgeConfig.from_dict(data.get("edit_batch_nudge", {}))` into the central config loader
    - `.ll/ll-config.json:97-99` — add the new flag at the same level as `learning_tests` once it lands

11. **Adapter parity for the opencode hook** — `hooks/adapters/opencode/index.ts` (mirror the Python `_dispatch_table` shape once `edit_batch_nudge` is registered). Read-only verify of `hooks/adapters/opencode/README.md`, `hooks/adapters/codex/README.md` for stale references.

12. **Stamp manifest forward-compat invariants** — in Step 4 (`manifest.json`) include:
    - top-level `schema_version: 1` field + reserved `_meta` envelope
    - per-trace entries include `has_unknown_model: bool` flag
    - per-trace entries reserve `budget_accumulator:` sub-record for FEAT-2476
    - per-trace JSON file envelope (Step 5) uses `{schema: "usage_jsonl_v1", rows: [...], totals: {...}, states: {...}}` with separate top-level `totals` and `states` keys
    - `_print_usage_summary` aggregation order (`scripts/little_loops/cli/loop/_helpers.py:1652-1714`) documented in `docs/observability/tier0-traces.md` so F6 re-aggregation matches

13. **Documentation coupling — author alongside the test fixtures**:
    - `docs/guides/BUILTIN_HOOKS_GUIDE.md:225-277` — add `edit_batch_nudge` PostToolUse section (mirror `install_learning_gate` precedent at line 215)
    - `docs/ARCHITECTURE.md:1392-1402` — add EditBatchNudge Consumers row to LearningTestsConfig Consumers table
    - `docs/reference/API.md:123` — add `edit_batch_nudge | EditBatchNudgeConfig` API row
    - `docs/reference/CONFIGURATION.md` — mirror the schema entry for `edit_batch_nudge.enabled`
    - `docs/reference/CLI.md:441` — mirror `--skip-edit-batch-nudge` flag (precedent at lines 273, 319, 374, 376)
    - `docs/reference/loops.md:111` — cross-reference `usage.jsonl` schema block from new `docs/observability/tier0-traces.md`
    - `docs/reference/HOST_COMPATIBILITY.md:132` — extend `[^tok]` footnote for non-Claude hosts (manifest format currently implies Claude-only)
    - `CHANGELOG.md` — Tier 0 trace set + edit-batch hook regression test entry under the next `[X.Y.Z] - DATE` block (NOT under `[Unreleased]` per `feedback_changelog_no_unreleased.md` rule)
    - Coordinate with ENH-2479 to create `docs/observability/` directory in a single PR (both `tier0-traces.md` and `streaming-parity-traces.md` land together)

14. **Test guards (added to Step 7)**:
    - Verify `scripts/tests/test_general_task_loop.py:53-74` continues passing (state set guard)
    - Run `scripts/tests/test_ll_logs.py:3274-3594+` `TestEvalExport` cross-check (Step 3's `ll-logs eval-export --skill general-task` invocation)
    - Reference `scripts/tests/test_usage_reporter.py:18-201` as the aggregator parity check (per-trace `baseline_cost_usd` must match `_print_usage_summary`'s per-state order)

15. **hooks/hooks.json ordering invariant** — the new `PostToolUse` matcher `"Write|Edit|MultiEdit"` must NOT shadow the existing `*` matcher at `hooks/hooks.json:65` or the per-tool `Write`/`Edit` issue-auto-commit matchers at lines 89-130. Order the new entry after line 131 per the issue's existing anchor.

16. **Sibling-decision alignment** — the new `edit_batch_nudge` feedback message MUST respect **SECU-028** (`allowed-tools` glob, `.ll/decisions.yaml:844-873`) and **ARCH-029** (pair tool-level path restrictions with scope-boundary instructions) when naming the config flag the user has set to scope Edit.

## Impact

- **Priority**: P2 — gates the credibility of every Tier 0 "win"; owns the epic's Tier 0 trace set (Open Question #6)
- **Effort**: Small — fixture selection + baseline capture + one regression test
- **Risk**: Low — test/measurement only
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log
- `/ll:wire-issue` - 2026-07-05T04:20:53 - `a1f1af17-5b49-4369-a64a-0b4d12f597a0.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:09:21 - `d881e8f0-16f1-4e98-869b-bd6e7a95fbc5.jsonl`
- `/ll:refine-issue` - 2026-07-04T20:24:50 - `c598e9f8-80b2-4ec0-9e0f-bc292080ce64.jsonl`

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-2] (Tier 0 verification)
