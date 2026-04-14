---
parent: BUG-1105
priority: P2
type: BUG
size: Medium
---

# BUG-1109: Tests and Documentation for Rate Limit Handling

## Summary

Decomposed from BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures.

This child covers all test work (fixing 2 breaking tests + writing 7 new test classes/functions) and all documentation updates (8 files) for the rate-limit handling feature introduced in BUG-1107 and BUG-1108.

## Scope

### Breaking Tests to Fix Before First Test Run

These tests will fail as soon as BUG-1107/BUG-1108 changes land:

1. **`test_signal_detector.py:149-154`** — `test_default_patterns` asserts `len(detector.patterns) == 3` and `pattern_names == {"handoff", "error", "stop"}`; adding `RATE_LIMIT_STORM` breaks both assertions → update to `4` and add `"rate_limit_storm"` to set
2. **`test_generate_schemas.py:18-19,23-43,50-53,165-168`** — 4 test bodies assert count `19` and/or exact set of 19 event type strings → update count to `20`, add `"rate_limit_exhausted"` to set literals

### New Tests to Write

Follow the existing patterns listed:

1. **`test_fsm_executor.py`** — new `TestRateLimitHandling` class; mirror `TestPerStateRetryLimits` (lines 3206–3376):
   - 429 detection in `before_route` (output + stderr patterns)
   - Backoff sleep calls: mock both `time.sleep` and `random.uniform`; verify total sleep for attempt `n` equals `base * 2^n + mocked_jitter` (not a hardcoded schedule); use `random.uniform` mock returning `base` to produce a deterministic upper-bound for assertion
   - Jitter desynchronization: verify two executor instances with the same retry count produce different sleep totals when `random.uniform` is not mocked (probabilistic assertion — run 10 times, assert at least 1 pair differs)
   - `_rate_limit_retries` dict tracking
   - `rate_limit_exhausted` event emission
   - Configurable base: set `rate_limit_backoff_base_seconds=10` on `StateConfig`, verify sleep uses `10 * 2^n + jitter` not `30 * 2^n + jitter`
   - Use `MockActionRunner(use_indexed_order=True)` from `test_fsm_executor.py:3238-3253`
   - Assert emitted events with `event_callback` pattern from `test_fsm_executor.py:3336-3357`
   - Mock 429: `ActionResult(output="rate limit exceeded (429)", stderr="", exit_code=1, duration_ms=100)`

2. **`test_fsm_schema.py`** — tests for `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` fields: construction, `from_dict`, `to_dict`, `get_referenced_states`, roundtrip; verify `rate_limit_backoff_base_seconds` defaults to `30` when absent; mirror `on_blocked` pattern (lines 342–398)

3. **`test_fsm_validation.py`** — paired field validation: `max_rate_limit_retries` without `on_rate_limit_exhausted` → error, and vice versa; `rate_limit_backoff_base_seconds=0` → error; `rate_limit_backoff_base_seconds` alone (without pair) → valid; mirror `validation.py:280–301` logic

4. **`test_signal_detector.py`** — `RATE_LIMIT_STORM` pattern test: match, no-match, payload; mirror `test_custom_pattern` (lines 49–55)

5. **`test_fsm_fragments.py`** — `with_rate_limit_handling` defined in `common.yaml`, correct fields, resolves from real `common.yaml`; mirror `test_llm_gate_*` pattern (lines 534–584); **fragment must include non-empty `description` field** or `test_all_common_yaml_fragments_have_description` (line 945) fails

6. **`test_ll_loop_display.py`** — add parallel test for `on_rate_limit_exhausted` edge appearing in `_collect_edges()` output; mirror existing `on_retry_exhausted` test at lines 2378-2387

7. **`test_config.py:1324`** — add assertion for `rate_limit_exhausted` default color value on `CliColorsEdgeLabelsConfig`

### Documentation to Update

- `docs/reference/schemas/rate_limit_exhausted.json` — new event schema, modeled after `docs/reference/schemas/retry_exhausted.json`
- `docs/reference/EVENT-SCHEMA.md` — register new `rate_limit_exhausted` event type
- `docs/reference/CONFIGURATION.md:594` — `cli.colors.fsm_edge_labels` table; add `rate_limit_exhausted` row
- `docs/reference/OUTPUT_STYLING.md:59,203,214` — edge label color table (line 59), `_collect_edges()` prose (line 203), edge label color table (line 214)
- `docs/reference/API.md:3780-3802` — `StateConfig` class API block; add `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` fields (note default=30 and jitter formula for base)
- `docs/guides/LOOPS_GUIDE.md:993-1003,1620-1627` — add parallel section for new fields alongside `max_retries`/`on_retry_exhausted` pattern docs; include a note on thundering herd and jitter behavior for parallel worktree users
- `docs/reference/COMMANDS.md:512` — add `rate_limit_exhausted` rule alongside `retry_exhausted` mention
- `skills/analyze-loop/SKILL.md:107,143-147` — event type table + signal classification rules; add `rate_limit_exhausted` event
- `skills/create-loop/reference.md:891-937` — add parallel `max_rate_limit_retries`/`on_rate_limit_exhausted`/`rate_limit_backoff_base_seconds` reference section; document jitter and why it matters for `ll-parallel`
- `skills/create-loop/loop-types.md:789-790,849` — add parallel rate-limit note to per-item retry safeguard mentions

## Acceptance Criteria

- [ ] `test_signal_detector.py` `test_default_patterns` passes with count `4` and `"rate_limit_storm"` in set
- [ ] `test_generate_schemas.py` passes with count `20` and `"rate_limit_exhausted"` in all set literals
- [ ] `TestRateLimitHandling` in `test_fsm_executor.py` covers detection, backoff with jitter, configurable base seconds, dict tracking, event emission
- [ ] Schema field tests in `test_fsm_schema.py` cover all 5 pattern steps for all three new fields; `rate_limit_backoff_base_seconds` defaults to `30`
- [ ] Paired validation tests in `test_fsm_validation.py` cover both missing-field directions; `rate_limit_backoff_base_seconds=0` rejected; standalone `rate_limit_backoff_base_seconds` accepted
- [ ] `RATE_LIMIT_STORM` signal test covers match, no-match, payload
- [ ] Fragment test in `test_fsm_fragments.py` validates `with_rate_limit_handling` fields
- [ ] `test_ll_loop_display.py` covers `on_rate_limit_exhausted` edge
- [ ] `test_config.py` asserts `rate_limit_exhausted` default color
- [ ] All 10 documentation files updated
- [ ] `python -m pytest scripts/tests/ -x` passes

## Dependencies

- Requires BUG-1107 (executor) and BUG-1108 (schema/config) to be implemented first

## Session Log
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`

---

## Status

**Open** | Created: 2026-04-14 | Priority: P2
