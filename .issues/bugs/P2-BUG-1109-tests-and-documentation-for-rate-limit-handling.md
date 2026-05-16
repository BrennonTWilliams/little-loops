---
parent: BUG-1105
priority: P2
type: BUG
size: Medium
---

# BUG-1109: Tests and Documentation for Rate Limit Handling

## Summary

Decomposed from BUG-1105: FSM Loops Silently Skip All Work on 429 Rate Limit Failures.

This child covers the remaining test and documentation work for the rate-limit handling feature introduced in BUG-1107 and BUG-1108.

**Note:** BUG-1107/1108 landed as commits `8dba4536` and `95b4fed2`. The original scope of this issue assumed they had not shipped; significant portions are already complete. See the Codebase Research Findings section below for the full already-done list. This Scope and Acceptance Criteria section is the reconciled, remaining work.

## Scope

### Tests to Add

1. **`test_fsm_schema.py`** — new field tests for `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds`. Mirror the `on_blocked` pattern at lines 342–398. Cover all 5 steps: construction, `from_dict`, `to_dict`, `get_referenced_states`, roundtrip. Verify `rate_limit_backoff_base_seconds` defaults to `30` when absent.

2. **`test_fsm_validation.py`** — extend existing `TestRateLimitFieldValidation` class (line 69) with one case: standalone `rate_limit_backoff_base_seconds` (without the paired fields) → valid. The paired-field directions and `rate_limit_backoff_base_seconds=0` rejection (line 130 `test_backoff_base_less_than_one_fails`) are already covered.

3. **`test_fsm_fragments.py`** — new test for `with_rate_limit_handling` fragment (defined in `scripts/little_loops/loops/lib/common.yaml:49`). Mirror `test_llm_gate_*` at lines 534–584. Verify fields resolve from real `common.yaml`. Fragment must have non-empty `description` field or `test_all_common_yaml_fragments_have_description` (line 945) fails.

4. **`test_ll_loop_display.py`** — new test for `on_rate_limit_exhausted` edge appearing in `_collect_edges()` output. Mirror the `on_retry_exhausted` test at lines 2378–2387.

5. **`test_config.py:1324`** — add assertion for `rate_limit_exhausted` default color on `CliColorsEdgeLabelsConfig`.

### Documentation to Update

- `docs/reference/API.md:3780-3802` — `StateConfig` class API block; add `max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds` fields (note default=30 and the `base * 2^n + jitter` formula)
- `docs/guides/LOOPS_GUIDE.md:1620-1627` — add parallel prose section alongside the `max_retries`/`on_retry_exhausted` pattern docs; include a thundering-herd / jitter note for `ll-parallel` users (the field-table entries at 995–997 are already present)
- `docs/reference/COMMANDS.md:512` — add `rate_limit_exhausted` rule alongside the existing `retry_exhausted` mention
- `skills/analyze-loop/SKILL.md:107,143-147` — add `rate_limit_exhausted` to event type table + signal classification rules
- `skills/create-loop/reference.md:891-937` — add parallel reference section for `max_rate_limit_retries`/`on_rate_limit_exhausted`/`rate_limit_backoff_base_seconds`; document jitter rationale for `ll-parallel`
- `skills/create-loop/loop-types.md:789-790,849` — add parallel rate-limit note to per-item retry safeguard mentions

### Out of Scope (Completed by BUG-1107/1108)

These items from the original issue are already done and are **not** part of this issue's remaining work. See Codebase Research Findings for line references:

- `test_generate_schemas.py` count + set-literal updates
- `test_fsm_executor.py` `TestRateLimitRetries` and `TestRateLimitStorm` classes
- `test_fsm_validation.py` paired-field validation cases
- Schema field definitions in `fsm/schema.py`
- `with_rate_limit_handling` fragment in `common.yaml`
- `rate_limit_exhausted.json`, `EVENT-SCHEMA.md`, `CONFIGURATION.md`, `OUTPUT_STYLING.md` doc updates
- `LOOPS_GUIDE.md:995–997` field table

### Explicitly Dropped

- **`test_signal_detector.py` `test_default_patterns` fix** and **new `RATE_LIMIT_STORM` pattern test** — storm detection was implemented in the executor (covered by `TestRateLimitStorm` at `test_fsm_executor.py:4518`), not as a `signal_detector.py` default pattern. The existing test correctly asserts 3 patterns. If a future issue decides to also expose storm detection via `signal_detector.py`, those test items can be revived there.

## Acceptance Criteria

- [ ] Schema field tests in `test_fsm_schema.py` cover all 5 pattern steps for all three new fields; `rate_limit_backoff_base_seconds` defaults to `30`
- [ ] `TestRateLimitFieldValidation` in `test_fsm_validation.py` extended: standalone `rate_limit_backoff_base_seconds` accepted (the `=0` rejection case already exists at line 130)
- [ ] Fragment test in `test_fsm_fragments.py` validates `with_rate_limit_handling` fields and description
- [ ] `test_ll_loop_display.py` covers `on_rate_limit_exhausted` edge in `_collect_edges()`
- [ ] `test_config.py` asserts `rate_limit_exhausted` default color
- [ ] All 6 remaining documentation files updated (API.md, LOOPS_GUIDE.md prose, COMMANDS.md, analyze-loop SKILL.md, create-loop reference.md, create-loop loop-types.md)
- [ ] `python -m pytest scripts/tests/ -x` passes

## Dependencies

- Requires BUG-1107 (executor) and BUG-1108 (schema/config) to be implemented first

## Codebase Research Findings

_Added by `/ll:refine-issue` 2026-04-14 — BUG-1107/1108 commits (8dba4536, 95b4fed2) have landed. Current state verified against the repo:_

### Already Done (remove from remaining scope)

- **`test_generate_schemas.py`** — count now `21` (not 20); `"rate_limit_exhausted"` and `"rate_limit_storm"` already in set literals at lines 18, 23–46, 52–56. No change needed.
- **`test_fsm_executor.py`** — `TestRateLimitRetries` class at **line 4303** already covers 429 detection, backoff sleep, event emission, routing to `on_rate_limit_exhausted`, configurable base seconds. `TestRateLimitStorm` at **line 4518** covers consecutive-exhaustion storm detection.
- **`test_fsm_validation.py`** — `TestRateLimitFieldValidation` at **line 69** covers both paired-field directions. Still missing: `rate_limit_backoff_base_seconds=0` rejection and standalone-accepted cases — add to this existing class.
- **Schema fields** `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds` exist in `scripts/little_loops/fsm/schema.py`.
- **Fragment** `with_rate_limit_handling` exists in `scripts/little_loops/loops/lib/common.yaml:49`.
- **Docs already updated**: `docs/reference/schemas/rate_limit_exhausted.json`, `docs/reference/EVENT-SCHEMA.md` (224–252), `docs/reference/CONFIGURATION.md:595`, `docs/reference/OUTPUT_STYLING.md:59,203,214`. `docs/guides/LOOPS_GUIDE.md:995–997` has field table entries.

### Remaining Work (the real BUG-1109 scope)

**Breaking test fix:**
1. **`test_signal_detector.py:149-154`** — still asserts `len(detector.patterns) == 3`. **Note:** `RATE_LIMIT_STORM` is NOT currently a `signal_detector.py` pattern (storm detection is implemented in the executor directly, per `TestRateLimitStorm`). Decision needed: either (a) add `RATE_LIMIT_STORM` to `signal_detector.py` defaults and update this test to `4`, or (b) keep storm detection in the executor and leave `test_default_patterns` at `3`. Option (b) matches current implementation — recommend dropping the "breaking test" and the "new RATE_LIMIT_STORM pattern test" items unless the user wants the signal-detector path added.

**New tests still needed:**
2. **`test_fsm_schema.py`** — no rate-limit field tests found. Add 5-pattern tests (construction, `from_dict`, `to_dict`, `get_referenced_states`, roundtrip) for all three new fields; verify `rate_limit_backoff_base_seconds` defaults to `30`. Mirror `on_blocked` pattern at lines 342–398.
3. **`test_fsm_validation.py`** — extend existing `TestRateLimitFieldValidation` (line 69) with: standalone `rate_limit_backoff_base_seconds` → valid. (The `=0` rejection case already exists as `test_backoff_base_less_than_one_fails` at line 130.)
4. **`test_fsm_fragments.py`** — no `with_rate_limit_handling` fragment test. Mirror `test_llm_gate_*` at lines 534–584. Fragment must have non-empty `description` or line 945 check fails.
5. **`test_ll_loop_display.py`** — no `on_rate_limit_exhausted` edge test in `_collect_edges()`. Mirror `on_retry_exhausted` test at lines 2378–2387.
6. **`test_config.py:1324`** — no `rate_limit_exhausted` default color assertion on `CliColorsEdgeLabelsConfig`.

**Docs still needing updates:**
- `docs/reference/API.md:3780-3802` — `StateConfig` API block missing all three new fields.
- `docs/guides/LOOPS_GUIDE.md:1620-1627` — parallel-section prose + thundering-herd/jitter note missing (the field table at 995–997 landed, but the prose section did not).
- `docs/reference/COMMANDS.md:512` — `rate_limit_exhausted` rule mention missing alongside `retry_exhausted`.
- `skills/analyze-loop/SKILL.md:107,143-147` — event type table + signal classification rules missing `rate_limit_exhausted`.
- `skills/create-loop/reference.md:891-937` — parallel reference section for the three new fields missing (include jitter rationale for `ll-parallel`).
- `skills/create-loop/loop-types.md:789-790,849` — parallel rate-limit note on per-item retry safeguard mentions missing.

## Session Log
- `/ll:ready-issue` - 2026-04-14T19:53:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5812cb7b-7e70-4b6a-abe8-7d2fff73423e.jsonl`
- `/ll:refine-issue` - 2026-04-14T19:49:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9fca1b06-b8a8-46b6-8419-fea8aba1ead4.jsonl`
- `/ll:issue-size-review` - 2026-04-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4abdbd46-1b62-4801-9d00-a2569583afde.jsonl`
- `/ll:manage-issue` - 2026-04-14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c90f42b3-22d4-474b-9b3a-362990c033a4.jsonl`

## Resolution

All remaining test and documentation work landed:

**Tests added:**
- `test_fsm_schema.py` — 7 new tests on `TestStateConfig` covering construction, defaults, `from_dict`, `to_dict` (set + omitted), `get_referenced_states`, and roundtrip for `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds`. Note: `StateConfig` dataclass defaults are `None`; the `30`-second fallback lives in the executor, so the schema test asserts `None` defaults and the fragment test asserts the fragment ships `30`.
- `test_fsm_validation.py` — new `test_standalone_backoff_base_seconds_passes` on the existing `TestRateLimitFieldValidation` class confirming `rate_limit_backoff_base_seconds` has no paired-field requirement.
- `test_fsm_fragments.py` — 4 new tests on `TestCommonYamlNewFragments`: fragment presence, non-empty description (satisfies the `test_all_common_yaml_fragments_have_description` check), default field values, and full `resolve_fragments` integration against real `common.yaml`.
- `test_ll_loop_display.py` — `test_collect_edges_includes_on_rate_limit_exhausted` mirroring the `on_retry_exhausted` edge test.
- `test_config.py` — `TestCliColorsEdgeLabelsConfig.test_defaults` now asserts `rate_limit_exhausted == "38;5;214"`.

**Docs updated:**
- `docs/reference/API.md` — `StateConfig` API block now lists the three new fields with a rate-limit-handling callout (backoff formula + jitter/`ll-parallel` note).
- `docs/guides/LOOPS_GUIDE.md` — parallel prose section alongside `max_retries`/`on_retry_exhausted`, including the thundering-herd / jitter warning for `ll-parallel` users.
- `docs/reference/COMMANDS.md` — `rate_limit_exhausted` rule added next to the existing `retry_exhausted` rule in the analyze-loop signal detection list.
- `skills/analyze-loop/SKILL.md` — event table row for `rate_limit_exhausted` plus a new "BUG — Rate-limit exhaustion" signal classification rule that calls out the distinction from retry floods.
- `skills/create-loop/reference.md` — new section "`max_rate_limit_retries`, `on_rate_limit_exhausted`, and `rate_limit_backoff_base_seconds`" parallel to the retry-limit section, including jitter rationale and a worked example.
- `skills/create-loop/loop-types.md` — harness template yaml includes the three new fields; added a `max_rate_limit_retries` callout alongside the existing `max_retries` callout.

**Explicitly dropped (confirmed):** `test_signal_detector.py` changes — storm detection is implemented in the executor (`TestRateLimitStorm` at `test_fsm_executor.py:4518`), not as a `signal_detector.py` default pattern. Current assertion of 3 patterns is correct.

**Verification:**
- Targeted tests (`test_fsm_schema.py`, `test_fsm_validation.py`, `test_fsm_fragments.py`, `test_ll_loop_display.py`, `test_config.py`): 498 passed.
- Full suite: 4828 passed, 5 skipped, 2 pre-existing failures unrelated to BUG-1109 — both in `test_update_skill.py::TestMarketplaceVersionSync` caused by `marketplace.json` version `1.81.1` lagging `plugin.json` version `1.82.0` (stale since the v1.82.0 release in commit `2fb7a8e9`; a release-sync issue, not caused by this work).

---

## Status

**Completed** | Created: 2026-04-14 | Completed: 2026-04-14 | Priority: P2
