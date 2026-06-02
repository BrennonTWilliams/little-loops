---
id: ENH-1797
type: ENH
title: Cost / token telemetry per FSM state in loop runs
priority: P3
status: done
captured_at: '2026-05-29T20:37:23Z'
completed_at: '2026-06-01T15:38:21Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- captured
- fsm
- harness
- loops
- telemetry
- cost
relates_to:
- FEAT-1689
- ENH-1726
parent: EPIC-1744
confidence_score: 98
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
---

# ENH-1797: Cost / token telemetry per FSM state in loop runs

## Summary

Record token spend (input / output / cache) per FSM state per iteration
and surface aggregates in `ll-loop run` output and the per-run artifacts
directory. Today the runner has no idea what each harness costs, which
makes "is this loop worth running 200 iterations?" an unanswerable
question. DeerFlow's `TokenUsageMiddleware` attributes subagent token
usage back to the dispatching step — we should do the equivalent for
states.

## Motivation

This enhancement would:
- Surface which FSM states dominate token spend, making "is this loop worth running 200 iterations?" an answerable question
- Enable cost-aware loop design: a `check_skill` state that drags 50× more than `check_concrete` shouldn't be invisible
- Business value: honest cost recommendations for long-running harnesses
- Technical debt: removes the need to read CLI billing logs out-of-band to understand harness cost

## Current Behavior

- `ll-loop run` reports iteration counts, transitions, and verdicts.
- There is no breakdown of tokens / cost per state or per iteration.
- A `check_skill` state that costs 50× more than `check_concrete` is
  invisible until you read the host CLI's billing logs out-of-band.
- `ll-ctx-stats` exists for the project level but doesn't slice by FSM
  state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Usage **is already parsed** from the `claude` stream-json `result` event in `run_claude_command()` at `scripts/little_loops/subprocess_utils.py:362-369`. The four available fields per event are `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`.
- The parse path uses an optional `on_usage` callback typed as `UsageCallback = Callable[[int, int], None]` (`subprocess_utils.py:33`). The two-int signature collapses `input_tokens + cache_read_input_tokens` into a single number and **drops `cache_creation_input_tokens` entirely** — ENH-1797 must widen this signature (or add a parallel four-field callback) to preserve all fields.
- The FSM runner **does not pass `on_usage`** when calling `run_claude_command()`. The drop site is `DefaultActionRunner.run()` in `scripts/little_loops/fsm/runners.py` at the `run_claude_command(command=action, timeout=..., stream_callback=..., ...)` call (lines 102-110). Usage data reaches Python and is then discarded.
- `ActionResult` (`fsm/runners.py`) has only `output`, `stderr`, `exit_code`, `duration_ms` — no token fields. The `action_complete` event payload assembled in `FSMExecutor._run_action()` (`fsm/executor.py:1024-1034`) likewise carries no token fields.
- `action_type: mcp_tool` does **not** go through the runner; it dispatches to `FSMExecutor._run_subprocess()` (raw `subprocess.Popen`). Token capture for mcp_tool requires a separate hook — usage data is not surfaced by the MCP transport layer at all today.
- `action_type: shell` invocations have no host-CLI involvement and produce no token data; the per-state summary should skip them (or report `n/a`).
- The `.loops/runs/<instance_id>/` directory (per ENH-1726) is created in `cmd_run()` at `scripts/little_loops/cli/loop/run.py:380` and surfaced to states via `fsm.context["run_dir"]`. The runner itself currently writes **nothing** to this directory — loop YAML action scripts write artifacts (`report.md`, `plan.md`, etc.) there. `usage.jsonl` would be the first runner-authored file in this directory.
- Distinct from `run_dir`: the FSM event log lives at `.loops/.running/<instance_id>.events.jsonl` (written by `StatePersistence.append_event()` in `fsm/persistence.py:373`) and archives to `.loops/.history/<run_id>-<loop_name>/events.jsonl`. ENH-1797 should write `usage.jsonl` under `run_dir`, not the `.running`/`.history` namespace, to keep ENH-1726's per-run grouping coherent.
- There is **no `MODEL_PRICING` table anywhere in the codebase** — `ll-ctx-stats` only tracks bytes, not cost. ENH-1797 must introduce a per-model `$/Mtok` pricing constant for the `est_cost` column.

## Expected Behavior

1. Runner captures input/output/cache tokens from each `action_type:
   prompt` / `slash_command` / `mcp_tool` invocation (whatever the host
   adapter exposes — `claude` already returns usage; `codex` / `opencode`
   may need shim work).
2. Per-iteration usage is journaled to `.loops/runs/<id>/usage.jsonl`
   alongside the existing event log.
3. `ll-loop run` end-of-run summary prints a table:
   `state | invocations | input | output | est_cost`.
4. `ll-loop runs show <id>` (or whatever the per-run reporter is, post
   ENH-1726) surfaces the same breakdown.
5. Sets a foundation for budget-aware control: a future `max_cost:`
   field at the loop level can abort cleanly when crossed (parallel to
   today's `max_iterations`).

## Proposed Solution

Pipe host-adapter token usage through the runner's action execution layer into a per-run
`usage.jsonl` journal and a terminal summary table.

1. **Capture**: Extend the runner's action-invocation path to record `input_tokens`,
   `output_tokens`, `cache_tokens` (and optionally `cache_write_tokens`) from each
   host-adapter response. `claude` already returns usage; `codex`/`opencode` may need
   shim work deferred to adapter tickets.
2. **Journal**: Write per-iteration usage lines to `.loops/runs/<id>/usage.jsonl`
   alongside the existing event log, keyed by `{iteration, state, action_type, ...}`.
3. **Summarize**: In the end-of-run reporter, aggregate usage by state and emit a table:
   `state | invocations | input_tokens | output_tokens | cache_tokens | est_cost`.
4. **Per-run reporter** (post ENH-1726): `ll-loop runs show <id>` surfaces the same
   breakdown from `usage.jsonl`.
5. **Future**: Add `max_cost:` loop-level field (out of scope here) that gates iteration
   when cumulative cost exceeds the threshold.

## API/Interface

### New file format: `.loops/runs/<id>/usage.jsonl`

```jsonl
{"iteration": 0, "state": "check_skill", "action_type": "slash_command", "input_tokens": 1234, "output_tokens": 567, "cache_read_tokens": 890, "cache_creation_tokens": 200, "model": "claude-opus-4-7", "timestamp": "..."}
```

Field choices grounded by codebase research: the raw `claude` event already exposes four token fields (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`); journal all four so a future re-pricing pass against historical runs is possible. The `model` field is the host-reported model ID, needed for cost estimation against the per-model `$/Mtok` table.

### Callback signature widening

The existing `UsageCallback = Callable[[int, int], None]` at `scripts/little_loops/subprocess_utils.py:33` collapses cache-read into input and drops cache-creation. ENH-1797 must widen this to a four-int callback (or introduce a parallel `Callable[[TokenUsage], None]` where `TokenUsage` is a small dataclass with the four fields plus `model`). The existing two-int callsite (`context-monitor.sh` hook via the shell path is the only current consumer) needs back-compat, so a parallel callback is the cleaner shape.

### End-of-run summary table (stdout from `ll-loop run`)

```
state           invocations  input    output   cache   est_cost
check_skill     1            1234     567      890     $0.016
check_concrete  1            234      56       100     $0.003
```

### `ll-loop runs show <id>` integration

The per-run reporter reads `usage.jsonl` and surfaces the same aggregated breakdown
as a sub-table under the iteration log.

## Implementation Steps

1. Extend the runner action-execution path to capture token usage from host responses
2. Add `usage.jsonl` journaling alongside the existing event log
3. Add per-state aggregation in the end-of-run reporter (`ll-loop run` summary)
4. Wire the per-run reporter (`ll-loop runs show <id>`) to surface usage breakdown
5. Add tests: verify `usage.jsonl` is written, aggregation is correct, table output renders

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation surface:_

1. **Widen the callback in `subprocess_utils.py`** (around line 33 / lines 362-369). Either:
   - Extend `UsageCallback` to `Callable[[int, int, int, int, str], None]` (input/output/cache_read/cache_creation/model), or
   - Add a parallel `on_usage_detailed: Callable[[TokenUsage], None]` taking a small dataclass. The dataclass shape is cleaner because future fields (e.g. `service_tier`) won't break callers.
   At the `etype == "result"` branch, also pull `event.get("usage", {})` plus `event.get("model")` and fire the new callback unconditionally (drop the `if on_usage and usage:` short-circuit for the new path so empty-usage events still record a zero row).
2. **Wire the callback at `DefaultActionRunner.run()`** in `scripts/little_loops/fsm/runners.py` (the `run_claude_command(...)` call at ~lines 102-110). Allocate a `_usage_accumulator` list inside `run()`, pass its `.append` as the callback, then attach the collected list onto a new `ActionResult.usage_events: list[TokenUsage]` field (extend the dataclass).
3. **Enrich the `action_complete` payload** in `FSMExecutor._run_action()` at `scripts/little_loops/fsm/executor.py:1024-1034` so journalled events carry token totals: add `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, and `model` fields aggregated from `result.usage_events`.
4. **Write `usage.jsonl`** by extending `PersistentExecutor._handle_event()` in `scripts/little_loops/fsm/persistence.py` to also write to `Path(fsm.context["run_dir"]) / "usage.jsonl"` when handling `action_complete` events with usage fields. Use the existing JSONL idiom (`with open(..., "a", encoding="utf-8") as f: f.write(json.dumps(entry) + "\n")`) seen in `StatePersistence.append_event()` (line 373) and `_write_meta_eval_entry()` (line 678).
5. **Aggregate by state** using the `ctx_stats.py` pattern at `_aggregate_tool_events()` (lines 129-144): `per_state: dict[str, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "invocations": 0, "est_cost_cents": 0})` and `+=` accumulate.
6. **Print the summary table** in `run_foreground()` at `scripts/little_loops/cli/loop/_helpers.py:1196-1217`, immediately before the existing `print(f"{completion_prefix}: ...")` line. Follow the `_render()` style from `cli/ctx_stats.py:196-201`: plain f-string column padding with `{state:<20} {input:>8} {output:>8} {cache_read:>8} {est_cost:>10}` — no `rich` library is used anywhere in the project.
7. **Introduce a pricing constant** in a new module (e.g. `scripts/little_loops/pricing.py`) or as a top-level constant in `cli/loop/_helpers.py`. Suggested shape: `MODEL_PRICING: dict[str, dict[str, float]] = {"claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_creation": 18.75}, ...}` in $/Mtok. Fall back to `"unknown"` model bucket emitting `est_cost: None` (display as `n/a`).
8. **Tests** (new files `scripts/tests/test_usage_journal.py` and `scripts/tests/test_usage_reporter.py`):
   - Journal test: follow `test_fsm_persistence.py:test_append_events()` (line 274) and `test_events_file_is_append_only()` (line 331) — write via the new hook, then `path.read_text().splitlines()` + `json.loads()` per line, assert dict fields.
   - Reporter test: follow `test_cli_ctx_stats.py:_capture_print()` (line 23) — pass a print stub, assert `any("check_skill" in line for line in lines)` and `any("$0.0" in line for line in lines)`.
   - Skip-paths test: confirm `action_type: shell` and `action_type: mcp_tool` invocations either record `n/a`-marked rows or are skipped from `usage.jsonl` (decide explicitly).
9. **Run the test suite**: `python -m pytest scripts/tests/test_usage_journal.py scripts/tests/test_usage_reporter.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_persistence.py -v`.

### Codebase Research Findings — Stale Anchor Correction

_Added by `/ll:refine-issue` — line numbers verified against current codebase (June 2026):_

> ⚠ Step 6 cites "lines 1196-1217" as the insertion point in `run_foreground()`. Those lines are inside the executor invocation `try/finally` block — not the completion print. The actual `print(f"{completion_prefix}: ...")` is at **`_helpers.py:1245`**. Insert the usage table around **line 1225** (after the `finally:` restores the alt-screen, before the `if not renderer.quiet:` block). Step 6's instruction ("immediately before the existing `print(f'{completion_prefix}: ...')` line") is correct; only the line number is stale. Note also that FEAT-1822 added an A/B summary block at lines 1249-1253 after the completion print; the usage table should precede the completion print (line 1225), not follow the A/B block.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Add `usage_events` field to `ActionResult` in `scripts/little_loops/fsm/types.py` (line 58 area)** — NOT `runners.py`. Use `usage_events: list[TokenUsage] = field(default_factory=list)`. This is the canonical dataclass definition; all kwargs-based constructors in tests and runtime remain back-compat.
11. **Update `scripts/little_loops/fsm/__init__.py`** — re-exports `ActionResult` via `__all__`; if the package docstring lists field names, update it.
12. **Verify back-compat for two-int `UsageCallback` consumers** — `issue_manager.py` (lines 105, 172, 460) and `parallel/worker_pool.py` (line 647). Preferred: keep `on_usage: Callable[[int, int], None]` unchanged and add parallel `on_usage_detailed: Callable[[TokenUsage], None]` in `subprocess_utils.py`. This avoids cascading changes to both files. Alternative: widen in place and update all callers + their tests.
13. **Update `docs/reference/schemas/action_complete.json`** — add new optional fields under `properties`: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`. Leave them out of `required` since shell/mcp_tool invocations won't have them. Then run `ll-generate-schemas` to verify.
14. **Update `docs/reference/EVENT-SCHEMA.md`** — `### action_complete` field table + both JSON examples (shell and prompt). Add token fields to the prompt example only (shell has no usage).
15. **Update `docs/reference/loops.md` and `docs/guides/LOOPS_GUIDE.md`** — document `usage.jsonl` as a runner-written artifact under `run_dir`.
16. **Decide and document archive policy** — `StatePersistence.archive_run()` does NOT currently copy `usage.jsonl` to `.history/`. Recommended: leave at `.loops/runs/<id>/` permanently. Add a `test_usage_journal_not_archived` test to pin the decision.
17. **Decide and document skip-paths** — `action_type: shell` and `action_type: mcp_tool` produce no token data. Recommended: skip them from `usage.jsonl` entirely (no `n/a` row). Add a `test_shell_action_skipped_from_journal` and `test_mcp_tool_action_skipped_from_journal` test in `test_usage_journal.py`.
18. **Update `scripts/tests/test_subprocess_utils.py`** — depending on callback-signature decision in step 12: if parallel callback added, add a new `test_on_usage_detailed_callback_called_with_result_event` test; if in-place widened, update existing `test_on_usage_callback_called_with_result_event` (line 1505) to assert the new 4-int/dataclass shape.
19. **Update `scripts/tests/test_generate_schemas.py`** — extend `test_action_complete_schema` (line 150) to assert the new token field properties exist after schema regen.
20. **Extend `scripts/tests/test_ll_loop_display.py`** — add `test_run_foreground_prints_usage_summary_table` and `test_run_foreground_omits_table_when_no_usage` to `TestRunForegroundResumeMode` (or a new class). Use `capsys` like existing tests.
21. **Update skills/cleanup-loops/SKILL.md** — if Step 6 bash needs to know about `usage.jsonl` (depends on step 16 decision), update the snippet; otherwise add a one-line note that `usage.jsonl` lives under `.loops/runs/<id>/`.
22. **Document host-adapter gap** — add a note in `docs/reference/HOST_COMPATIBILITY.md` (or create `HostCapabilities.usage_reporting` flag) that codex/opencode adapters do not yet expose usage events.
23. **Update `scripts/little_loops/generate_schemas.py`** — `SCHEMA_DEFINITIONS["action_complete"]` entry (around line 129) is the source-of-truth `ll-generate-schemas` reads; the new optional token fields (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`) must be authored here before the `ll-generate-schemas` call in step 13 will produce the correct output. The `test_generate_schemas.py:test_action_complete_schema` test should be extended to assert these new properties. [Wiring pass 2]

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — extend `UsageCallback` and result-event parse block (lines 33, 362-369)
- `scripts/little_loops/fsm/types.py` — add `usage_events: list[TokenUsage]` field to `ActionResult` dataclass (line 58)
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()`: wire callback, collect usage events (~lines 102-110)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()`: add token fields to `action_complete` payload (~lines 1024-1034)
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor._handle_event()`: write `usage.jsonl` to `run_dir` (line 373 idiom)
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()`: print per-state aggregation table before completion line (~line 1246)
- _Possibly new:_ `scripts/little_loops/pricing.py` — `MODEL_PRICING` constant (no existing table in codebase)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_usage_journal.py` — new tests for usage journaling (new file)
- `scripts/tests/test_usage_reporter.py` — new tests for summary output (new file)

### Similar Patterns
- `ll-ctx-stats` — project-level token analytics; follow same aggregation style

### Tests
- `scripts/tests/test_usage_journal.py` — verify `usage.jsonl` format and content
- `scripts/tests/test_usage_reporter.py` — verify end-of-run table output

### Documentation
- `docs/reference/API.md` — document new `usage.jsonl` format
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add cost-awareness section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — update the `### action_complete` section: field table and both JSON examples (shell and prompt) must add the new token fields (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`). [Agent 2 finding]
- `docs/reference/schemas/action_complete.json` — JSON Schema for the `action_complete` event. Currently lists only 5 properties; add the new optional token fields (or regenerate via `ll-generate-schemas`). [Agent 2 finding]
- `docs/reference/loops.md` — add a "Runner-Written Files" section documenting `usage.jsonl` as the first runner-authored file under `run_dir` (today the doc only lists user-written artifacts like `report.md`, `plan.md`). [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — per-loop "Output artifacts" tables document user-written files only; add a parallel "Runner-written files" entry for `usage.jsonl`. [Agent 2 finding]
- `docs/reference/CLI.md` — currently has no `ll-loop run` stdout examples, so no doc breaks; consider adding an example showing the new per-state summary table. [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — document the codex/opencode adapter gap (no usage exposed today) so the deferred adapter work is discoverable. [Agent 2 finding]
- `skills/cleanup-loops/SKILL.md` — Steps 3 and 6 show manual archive bash that moves only `state.json` and `events.jsonl`; if `usage.jsonl` archive behavior changes (see Configuration below), update the skill's bash; otherwise note that `usage.jsonl` lives at `.loops/runs/<id>/` permanently. [Agent 2 finding]

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — "Structured Events" section (around line 1606) shows inline `action_complete` JSONL examples with only `exit_code` and `duration_ms`; add the new token fields to those examples so they remain canonical. [Agent 2 finding]
- `docs/ARCHITECTURE.md` — "OTel mapping" paragraph (around line 534) brackets `action_start`/`action_complete` as an OTel grandchild span; update if token fields are exposed as span attributes. [Agent 2 finding]

### Configuration
- N/A — no new config keys in this issue (`max_cost` is deferred to a follow-up)

_Wiring pass added by `/ll:wire-issue`:_
- **Archive policy decision** — `StatePersistence.archive_run()` in `fsm/persistence.py` currently copies `state.json`, `events.jsonl`, `meta-eval.jsonl` to `.loops/.history/<run_id>-<loop_name>/`. Decide and document: does `usage.jsonl` get archived too? Recommended: leave at `.loops/runs/<id>/usage.jsonl` permanently (consistent with ENH-1726's per-run grouping). Pin via test in `test_fsm_persistence.py`. [Wiring decision]
- **Callback signature decision** — `UsageCallback` in-place widen vs. parallel `on_usage_detailed`. Per refine notes, parallel is cleaner (preserves back-compat for `issue_manager.py` and `parallel/worker_pool.py` two-int callers). Pin via test in `test_subprocess_utils.py`. [Wiring decision]
- **Schema regen** — after editing `docs/reference/schemas/action_complete.json`, run `ll-generate-schemas` to ensure consistency with `LLEvent` Python types. [Agent 2 finding]
- `pyproject.toml` — no change required; new `little_loops/pricing.py` module is auto-discovered. Documenting for completeness only. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — the planning-time paths above are partly fictional; corrected list:_

**Files to actually modify (verified to exist):**
- `scripts/little_loops/subprocess_utils.py` — extend `UsageCallback` (line 33) and the `result`-event parse block (lines 362-369) so all four token fields plus model ID flow through. **(Replaces the imagined `host_runner.py` work — `HostInvocation` is a pure argv descriptor with no usage field; parsing happens in `subprocess_utils.py`.)**
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` (lines 56-170): wire the new callback at the `run_claude_command(...)` call (~lines 102-110) and collect events into the new `ActionResult.usage_events` field.
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()` (~lines 1024-1034): add token fields to the `action_complete` event payload so journal consumers receive them. **(Replaces the imagined `loop_runner.py` — the runner lives under `fsm/`, not at module top-level.)**
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor._handle_event()` (uses `StatePersistence.append_event()` pattern at line 373): on `action_complete` events with usage, also append to `Path(fsm.context["run_dir"]) / "usage.jsonl"`.
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (lines 1196-1217): print the per-state aggregation table before the existing completion line. **(Replaces the imagined `loop_reporter.py` — there is no dedicated reporter module; post-run printing lives inline here.)**
- _Possibly new:_ `scripts/little_loops/pricing.py` — `MODEL_PRICING` constant (no such table exists anywhere in the codebase today).

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/little_loops/fsm/types.py`** — `ActionResult` dataclass actually lives here at line 58, NOT in `runners.py`. The new `usage_events: list[TokenUsage] = field(default_factory=list)` field must be added on the dataclass definition. `TokenUsage` is the proposed parallel-callback dataclass shape (input/output/cache_read/cache_creation tokens + model + service_tier). All existing call sites construct `ActionResult(...)` with kwargs, so a defaulted new field is back-compat. [Agent 2 finding]
- **`scripts/little_loops/fsm/__init__.py`** — re-exports `ActionResult` via `__all__`; the package docstring lists `ActionResult` fields. Update both if the docstring is normative. [Agent 1 finding]
- **`scripts/little_loops/cli/loop/testing.py`** — `cmd_test()` constructs `ActionResult(output=f"[simulated output...]", ...)` for slash-command simulation. Verify back-compat after adding `usage_events`. [Agent 2 finding]
- **`scripts/little_loops/issue_manager.py`** — uses `Callable[[int, int], None]` for `on_usage` at lines 105, 172, 460 (`run_claude_command`, `run_with_continuation`, `process_issue`) with `_on_usage_writer(input_tokens, output_tokens)` closure. **Decision required**: if `UsageCallback` widens in-place, this needs the wider signature; if a parallel `on_usage_detailed` is added (preferred per refine notes), this file is unchanged. [Agent 2 finding]
- **`scripts/little_loops/parallel/worker_pool.py`** — uses `Callable[[int, int], None]` for `on_usage` at line 647 (`_run_claude_command`) and `_run_with_continuation`, with `_usage_tracker` closure. Same back-compat decision applies. [Agent 2 finding]
- **`hooks/scripts/context-monitor.sh`** — shell consumer of token usage at lines 114-122, 288-290. Not a Python `UsageCallback` consumer (reads Claude Code's native hook JSON directly), so unaffected by callback widening, but documents the existing two-int contract. No change needed. [Agent 1 finding]
- **`docs/reference/schemas/action_complete.json`** — JSON Schema file for the `action_complete` event. Currently declares `required: ["event", "ts", "exit_code", "duration_ms", "is_prompt"]` and lists five `properties` — the new `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model` fields are not present. `additionalProperties: true` so validators won't reject, but the schema is factually incomplete after the change. Regenerate via `ll-generate-schemas` or update manually. [Agent 2 finding]
- **`docs/reference/EVENT-SCHEMA.md`** — `### action_complete` section has a field table and two JSON examples (shell and prompt). Both must add the new token fields. [Agent 2 finding]
- **`scripts/little_loops/host_runner.py`** — `HostCapabilities` dataclass has no `usage_reporting` flag. Codex/opencode adapter gaps are deferred per issue scope, but documenting the missing capability flag (or noting in `docs/reference/HOST_COMPATIBILITY.md`) prevents the gap from being silently re-discovered. [Agent 2 finding]
- **`scripts/little_loops/fsm/persistence.py`** — `StatePersistence.archive_run()` copies only `state.json`, `events.jsonl`, `meta-eval.jsonl` to `.loops/.history/<run_id>-<loop_name>/`. **Decision required**: archive `usage.jsonl` from `run_dir` to `.history/` too, or leave it permanently at `.loops/runs/<instance_id>/usage.jsonl`? Issue scope implies the latter (consistent with ENH-1726 layout), but the decision must be explicit. [Agent 2 finding]

**Dependent files (callers/importers verified):**
- `scripts/little_loops/fsm/executor.py` imports `ActionResult` from `fsm/types.py` (re-exported via `fsm/__init__.py`) — extending the dataclass touches one call site at most.
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` (line 453) re-injects `run_dir` on resume; verify that journal writes survive a resume.
- No external (out-of-repo) consumers of `ActionResult` — it's an internal dataclass.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py` — imports `ActionRunner` protocol (line 28); not directly affected by `usage_events` addition but documents the extension surface. [Agent 1 finding]
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` creates `run_dir` at line 380 and sets `fsm.context["run_dir"]`; no change required but confirms the directory exists before `_handle_event` tries to write `usage.jsonl`. [Agent 1 finding]
- `scripts/little_loops/cli/loop/info.py` — displays `action_complete` event details; will naturally surface new token fields once payload widens (no code change required, but visual side-effect to be aware of). [Agent 1 finding]
- `scripts/little_loops/transport.py` — transports `action_complete` events; payload is opaque dict so additional keys flow through automatically. [Agent 1 finding]
- `scripts/little_loops/extension.py` — `EventBus`/`LLExtension` observers receive `action_complete` events; external extensions pattern-matching on payload keys will see additional keys (tolerated since payload is plain dict, no schema validation). [Agent 2 finding]
- `scripts/little_loops/cli/loop/_helpers.py:StateFeedRenderer` — processes `action_complete` events for display; will receive new fields and may want to surface them in the per-state feed. [Agent 1 finding]

**Tests to add (mirror existing patterns):**
- `scripts/tests/test_usage_journal.py` — model after `test_fsm_persistence.py:test_append_events()` (line 274) and `test_events_file_is_append_only()` (line 331).
- `scripts/tests/test_usage_reporter.py` — model after `test_cli_ctx_stats.py:_capture_print()` (line 23) for stdout-table assertions. (Alternative: use pytest `capsys` fixture like `test_ll_loop_display.py:TestRunForegroundResumeMode` — same coverage, simpler pattern, already used for `run_foreground()` assertions.)

**Tests to extend:**
- `scripts/tests/test_fsm_executor.py:TestDefaultActionRunnerProcessTracking` (line 3376) — assert `DefaultActionRunner.run()` now collects usage events. **Correction**: `scripts/tests/test_fsm_runners.py` does NOT exist in the repo. The canonical `DefaultActionRunner` test class lives inside `test_fsm_executor.py`. Use the existing patch target `patch("little_loops.fsm.runners.run_claude_command", side_effect=fake_run_claude_command)` (pattern at line 3419) and fire `kwargs["on_usage"](...)` (or new-name callback) inside the fake.
- `scripts/tests/test_fsm_executor.py` — assert `action_complete` events carry the new token fields. Existing pattern at line 1975-1997 uses targeted key access (`action_complete["exit_code"]`), so additions are non-breaking; extend with positive assertions for new keys.

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/tests/test_subprocess_utils.py`** — **likely-break risk**. `TestRunClaudeCommandModelDetection.test_on_usage_callback_called_with_result_event` (line 1505) asserts `usage_calls == [(1500, 200)]`, the exact two-int tuple. If `UsageCallback` widens in place, the assertion shape must change. If a parallel `on_usage_detailed` callback is added and the two-int contract is preserved (preferred per refine notes), the test passes unchanged. Adjacent test `test_on_usage_not_called_when_result_has_no_usage` (line 1530) is should-extend only. [Agent 3 finding]
- **`scripts/tests/test_generate_schemas.py`** — `test_action_complete_schema` (line 150) uses `in` checks (not exhaustive), so adding new fields won't break it. Extend to positively assert the new `input_tokens`/`output_tokens`/`cache_read_tokens`/`cache_creation_tokens`/`model` properties exist after `ll-generate-schemas` regenerates the JSON Schema. [Agent 3 finding]
- **`scripts/tests/test_ll_loop_display.py`** — `TestDisplayProgressEvents` (line 1645) and `TestRunForegroundResumeMode` (line 2846) use `capsys`-based substring checks. The new summary table is additive (printed before completion line) and existing assertions use `in`/`not in` — low break risk, but extend with new tests that assert the table renders correctly when usage data is present, and is absent (or shows `n/a`) when usage data is empty. [Agent 3 finding]
- **`scripts/tests/test_fsm_persistence.py`** — extend `TestPersistentExecutor` (around line 651) with a `_handle_event` test that injects an `action_complete` event with token fields and a `tmp_path`-based `run_dir`, then asserts `(run_dir / "usage.jsonl").read_text().splitlines()` decodes to expected JSON. Existing `test_run_archives_to_history_on_completion` (line 991) does NOT check `run_dir`, so won't break — but add a partner test that pins whether `usage.jsonl` is archived to `.history/` (currently it is NOT — `StatePersistence.archive_run()` copies only state.json/events.jsonl/meta-eval.jsonl). [Agent 3 finding]
- **`scripts/tests/test_ll_loop_execution.py`** — constructs `ActionResult(output=..., stderr=..., exit_code=..., duration_ms=...)` at multiple sites (lines ~954, ~993, ~1040) when building `RouteContext` for routing tests. All use kwargs, so the defaulted `usage_events` field is back-compat. No break, but verify after change. [Agent 2 finding]
- **`scripts/tests/test_learning_state.py`** — imports `ActionResult` (line 22), uses kwargs-style construction. Back-compat with new field default. [Agent 1 finding]
- **`scripts/tests/test_cli_loop_worktree.py`** — patches `run_foreground` entirely at lines 612/648 (`patch("little_loops.cli.loop.run.run_foreground", return_value=0)`). Summary-table changes are invisible here — no risk. [Agent 3 finding]
- **Skip-paths test gap (decision-pinning test)** — no current test pins whether `action_type: shell` and `action_type: mcp_tool` invocations produce a `usage.jsonl` row marked `n/a` or are skipped entirely. The issue's step 8 bullet 3 says "decide explicitly." Add the decision-pinning test in `test_usage_journal.py`. [Agent 3 finding]
- **Archive-decision test gap** — pin via a new test in `test_fsm_persistence.py` whether `StatePersistence.archive_run()` copies `usage.jsonl` to `.history/` or leaves it permanently at `.loops/runs/<id>/`. [Wiring decision]

_Wiring pass 2 added by `/ll:wire-issue`:_
- **`scripts/tests/test_ll_loop_integration.py`** — `TestMainLoopIntegration` (line ~75) exercises `main_loop()` end-to-end and asserts on stdout strings like `"Loop completed: done"` (lines ~148-153). The usage table is printed before that line (additive, won't break existing assertions), but extend with: `test_run_prints_usage_table_when_llm_actions_ran` and `test_run_omits_usage_table_when_no_llm_actions`. [Agent 3 finding]
- **`scripts/tests/test_issue_manager.py`** — has `on_usage(185_000, 10_000)` two-arg lambda calls (lines ~1374, ~1451, ~1509). **BREAK if `UsageCallback` widens in-place**; safe if parallel `on_usage_detailed` callback is used (preferred per issue). Flag as explicit verification point after callback-signature decision. [Agent 3 finding]
- **`scripts/tests/test_worker_pool.py`** — has `on_usage(185_000, 10_000)` two-arg lambda call (line ~2382). Same break condition as `test_issue_manager.py`. [Agent 3 finding]
- **`scripts/tests/test_pricing.py`** (new, if `pricing.py` is a separate module) — test `MODEL_PRICING` lookup, `est_cost` calculation, unknown-model `None`/`n/a` fallback, and ±15% accuracy against reference token counts. If pricing constants are inlined into `_helpers.py`, add these tests to `test_usage_reporter.py` instead. [Agent 3 finding]

**Similar patterns (verified):**
- `scripts/little_loops/cli/ctx_stats.py:_aggregate_tool_events()` (lines 129-144) — `defaultdict(lambda: {...})` accumulation idiom.
- `scripts/little_loops/cli/ctx_stats.py:_render()` (lines 196-201) — column-padded `print()` style for the summary table (no `rich` library in use anywhere).
- `scripts/little_loops/fsm/persistence.py:append_event()` (line 373) — JSONL append idiom (`with open(..., "a") as f: f.write(json.dumps(entry) + "\n")`).

**EPIC siblings (EPIC-1744 — FSM Loop Hardening):**
- ENH-1677, ENH-1678, ENH-1735, ENH-1684, ENH-1701, FEAT-1689 — ENH-1797 lives among these; coordinate with any of them touching the same runner/persistence files.

## Impact

- **Priority**: P3 — observability now, gating later. Without it we
  can't honestly recommend long-running harnesses.
- **Effort**: Medium — host-adapter pass-through, runner journaling,
  reporter format. Cost is dominated by host adapters that don't yet
  expose usage cleanly.
- **Risk**: Low — pure instrumentation.
- **Breaking Change**: No.

## Success Metrics

- `ll-loop run` end-of-run summary includes a per-state token/cost table
- `usage.jsonl` is written for every loop run and contains one line per action invocation
- The most expensive state in a loop can be identified from the summary alone (no out-of-band billing logs required)
- Cost estimate in summary is within ±15% of the host CLI's billing totals

## Acceptance Criteria

- `usage.jsonl` exists at `<run_dir>/usage.jsonl` after any `ll-loop run` that executes at least one LLM action state
- Each line in `usage.jsonl` is valid JSON containing: `iteration` (int), `state` (str), `action_type` (str), `input_tokens` (int), `output_tokens` (int), `cache_read_tokens` (int), `cache_creation_tokens` (int), `model` (str), `timestamp` (ISO-8601 str)
- `action_type: shell` invocations produce **no row** in `usage.jsonl` (skip-path decision pinned by `test_shell_action_skipped_from_journal`)
- End-of-run stdout from `ll-loop run` contains a per-state table with columns `state | invocations | input | output | cache | est_cost` when at least one LLM action ran
- When no LLM action ran, the summary table is absent from stdout (no crash, no empty-header table)
- `est_cost` values are within ±15% of the host CLI's billing totals for a known fixture
- Resume (`ll-loop run --resume <id>`) appends to (does not overwrite) `usage.jsonl` because `run_dir` is restored by `lifecycle.py:cmd_resume()` at line 453
- `StatePersistence.archive_run()` does **not** copy `usage.jsonl` to `.loops/.history/` (permanent at `run_dir`, pinned by `test_usage_journal_not_archived`)

## Scope Boundaries

- **In scope**:
  - Per-state token capture for `action_type: prompt`, `slash_command`, and `mcp_tool`
  - `usage.jsonl` journaling per iteration
  - End-of-run summary table in `ll-loop run` output
  - Integration with per-run reporter (`ll-loop runs show <id>`, post ENH-1726)
- **Out of scope**:
  - Budget-aware gating (`max_cost` loop-level field) — deferred to follow-up
  - Host-adapter engineering for `codex`/`opencode` token reporting — blocked on adapter work
  - Per-project cost dashboards or historical cost trending (future `ll-ctx-stats` extension)

## Related Key Documentation

| Document | Why Relevant |
|---|---|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § Tips | "Set `timeout` for long runs" — the cost dimension belongs alongside |
| `FEAT-1689` | `ll-harness` CLI for one-shot evaluation — natural consumer |
| `ENH-1726` | Per-run artifacts directory — the storage target |

## Labels

`captured`, `cost`, `fsm`, `harness`, `loops`, `telemetry`

## Status

**Open** | Created: 2026-05-29 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Wide change surface — 16+ distinct sites across core logic (6 Python files), tests (7 test files), and docs/schemas (8 documentation files). Per-site depth is Local (callback wiring, field additions, JSONL append), so risk is coordination overhead from breadth rather than per-site complexity.
- tests are co-deliverables — implement decision-pinning tests (`test_shell_action_skipped_from_journal`, `test_usage_journal_not_archived`) alongside core logic to lock in the callback-signature and archive-policy decisions early; deferring them risks scope creep as each decision branches into callers.

## Session Log
- `/ll:ready-issue` - 2026-06-01T15:22:13 - `c67bd210-6925-420e-ba34-e0e71e9d6693.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00 - `bb12131c-6afa-4a03-ab11-646596f9a0b3.jsonl`
- `/ll:wire-issue` - 2026-06-01T15:09:49 - `c9d6444b-ae99-4db8-9651-f85fa0072ba3.jsonl`
- `/ll:refine-issue` - 2026-06-01T14:59:03 - `fa8f3c24-5078-4643-8c92-8e40de4d18b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:16 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:wire-issue` - 2026-05-30T21:49:10 - `cef1c26e-c8c0-44a3-ad97-7b7a90baf186.jsonl`
- `/ll:refine-issue` - 2026-05-30T21:37:13 - `d87dc942-b337-46e9-a574-9cadac23728c.jsonl`
- `/ll:format-issue` - 2026-05-29T21:14:28 - `cf11edc6-7c38-44c6-bc14-9d68aba363ce.jsonl`
- `/ll:capture-issue` - 2026-05-29T20:37:23Z - `f2a0c61b-6b34-41d4-98fb-c566ba046de6.jsonl`
