---
id: ENH-1140
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1138
related: [ENH-1138, ENH-1134]
size: Very Large
confidence_score: 100
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1140: 429 Resilience — Prose Doc Updates (Loops Guide, Config, Architecture)

## Summary

Update four documentation files with circuit-breaker prose: (1) add circuit-breaker subsection to `docs/guides/LOOPS_GUIDE.md`, (2) add `rate_limits` config block to `docs/reference/CONFIGURATION.md`, (3) add `rate_limit_circuit.py` to `docs/ARCHITECTURE.md` fsm directory tree, (4) add `rate_limit_circuit.py` to `CONTRIBUTING.md` fsm directory tree.

## Parent Issue

Decomposed from ENH-1138: 429 Resilience — Documentation Updates for Circuit Breaker

## Expected Behavior

### 1. `docs/guides/LOOPS_GUIDE.md:1672-1691` — Circuit-breaker subsection

Add a new subsection after the two-tier retry prose covering:

- **Pre-action check behavior**: prompt-mode LLM actions are pre-slept until `estimated_recovery_at` when a circuit is open (note: only `prompt` actions are gated — `slash_command` is NOT; `_maybe_wait_for_circuit` at `executor.py:969-984` skips when `_action_mode(state) != "prompt"`)
- **Cross-worktree coordination**: any `ll-parallel` worker that detects a 429 writes to `.loops/tmp/rate-limit-circuit.json`; all other workers read the shared file and skip redundant API calls
- **Stale detection**: entries older than 1 hour (`STALE_THRESHOLD_SECONDS = 3600.0`) are ignored automatically; no manual reset required
- **Atomicity**: writes use `fcntl.flock` sidecar + `tempfile.mkstemp` + `os.replace`; recovery timestamp advances monotonically (`max(current, proposed)`) so concurrent writers never shrink an in-flight window
- **Configuration**: controlled by `circuit_breaker_enabled` (default: `true`) and `circuit_breaker_path` (default: `".loops/tmp/rate-limit-circuit.json"`) in `rate_limits` config block

### 2. `docs/reference/CONFIGURATION.md:69-80,314-328` — `rate_limits` config block

Add `commands.rate_limits` subsection to both:
- The full config example block (~lines 69-80)
- The `### commands` property table (~lines 314-328)

Document all keys in `RateLimitsConfig` (`scripts/little_loops/config/automation.py:113-146`). The full block has FOUR keys — not just the two circuit-breaker keys — and none are currently documented in `CONFIGURATION.md` (grep confirms zero existing `rate_limits` prose):

- `max_wait_seconds: int = 21600` — total wall-clock budget (6h) before routing to `on_rate_limit_exhausted`
- `long_wait_ladder: list[int] = [300, 900, 1800, 3600]` — long-wait tier backoff ladder
- `circuit_breaker_enabled: bool = True`
- `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`

Block lives under `commands.rate_limits` (confirmed: `AutomationConfig.rate_limits` at `automation.py:158`, serialized at `core.py:411-415`).

### 3. `docs/ARCHITECTURE.md:255-267` — fsm/ directory tree

Add `rate_limit_circuit.py` alongside `signal_detector.py` and `handoff_handler.py` in the `scripts/little_loops/fsm/` tree listing.

### 4. `CONTRIBUTING.md:231-244` — fsm/ directory tree

Same as above — add `rate_limit_circuit.py` to the identical fsm/ listing.

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md` — two-tier retry section (~lines 1672-1691)
- `docs/reference/CONFIGURATION.md` — config example (~lines 69-80) and property table (~lines 314-328)
- `docs/ARCHITECTURE.md` — fsm/ tree (~lines 255-267)
- `CONTRIBUTING.md` — fsm/ tree (~lines 231-244)

### Codebase Research Findings

- **Pre-action check logic**: `scripts/little_loops/fsm/executor.py:969-984` (`_maybe_wait_for_circuit`) — gates only `prompt` actions, not `slash_command` (verified 2026-04-17)
- **Stale threshold**: `scripts/little_loops/fsm/rate_limit_circuit.py:27` — `STALE_THRESHOLD_SECONDS = 3600.0`
- **Default config**: `scripts/little_loops/config/automation.py:133-134` — `circuit_breaker_enabled: bool = True`, `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`
- **Full RateLimitsConfig schema**: `automation.py:113-146` — 4 keys total (`max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`, `circuit_breaker_path`)
- **Config nesting**: `AutomationConfig.rate_limits` field at `automation.py:158`; serialized under `commands.rate_limits` at `config/core.py:411-415`
- **Write side**: `scripts/little_loops/fsm/executor.py:951` (short-burst) and `:962` (long-wait) call `self._circuit.record_rate_limit(_sleep)` after 429
- **Atomicity**: `fcntl.flock` + `tempfile.mkstemp` + `os.replace`; monotonic `max()` advance
- **Existing `rate_limits` prose in CONFIGURATION.md**: NONE — grep for `rate_limit|max_wait_seconds|long_wait_ladder` returns only a color-config row at line 595; the `rate_limits` block is entirely undocumented
- **LOOPS_GUIDE.md insertion point**: new subsection should go AFTER the thundering-herd note at line 1691 and BEFORE `### Stall Detection` at line 1693 (two-tier retry prose spans 1670-1691)
- **ARCHITECTURE.md fsm tree**: lines 255-267, entries end at `handoff_handler.py` line 267 — add `rate_limit_circuit.py` after it
- **CONTRIBUTING.md fsm tree**: lines 231-243 (ends at `handoff_handler.py` line 243), followed by `extension.py` at 244 — add `rate_limit_circuit.py` before line 244

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:100` — `CommandsConfig` attribute description lists `confidence_gate`, `tdd_mode`, `max_refine_count` but omits `rate_limits: RateLimitsConfig`; needs one line added [Agent 2 finding]
- `skills/configure/show-output.md:68-83` — `/ll:configure commands --show` output format lists all `commands` keys except `rate_limits`; four keys will be invisible to users after CONFIGURATION.md adds them [Agent 2 finding]
- `skills/configure/areas.md:308-403` — interactive `commands` configure flow (Round 1 + Round 2) has no `rate_limits` questions; users can't interactively set circuit-breaker config [Agent 2 finding]
- `skills/create-loop/reference.md:939-968` — rate-limit fields section documents `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` but omits `circuit_breaker_enabled` and `circuit_breaker_path` entirely [Agent 2 finding]
- `skills/create-loop/loop-types.md:791-795` — YAML example for rate-limit fields has no circuit-breaker knobs [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1138_doc_wiring.py` — new test file needed; assert `circuit_breaker_enabled`/`circuit_breaker_path` appear in `LOOPS_GUIDE.md` and `CONFIGURATION.md`; follow pattern at `test_create_extension_wiring.py:156-174`; tracked in **ENH-1141** [Agent 3 finding]
- All existing tests (`test_rate_limit_circuit.py`, `test_config.py`, `test_config_schema.py`, `test_fsm_executor.py`, `test_cli_loop_lifecycle.py`, `test_ll_loop_commands.py`) pass today and are unaffected by prose-only changes [Agent 3 finding]

## Implementation Steps

1. **Update `docs/guides/LOOPS_GUIDE.md`** — insert new circuit-breaker subsection between line 1691 (end of thundering-herd note) and line 1693 (`### Stall Detection`). Cover: pre-action check (prompt-mode only; `slash_command` is NOT gated), cross-worktree coordination via `.loops/tmp/rate-limit-circuit.json`, 1-hour stale auto-ignore, atomicity (`fcntl.flock` + `os.replace` + monotonic `max()` advance), config knobs (`circuit_breaker_enabled`, `circuit_breaker_path`)
2. **Update `docs/reference/CONFIGURATION.md:69-80`** — add `rate_limits` sub-block inside the `commands` block of the full config example, showing all 4 keys with defaults (`max_wait_seconds: 21600`, `long_wait_ladder: [300, 900, 1800, 3600]`, `circuit_breaker_enabled: true`, `circuit_breaker_path: ".loops/tmp/rate-limit-circuit.json"`)
3. **Update `docs/reference/CONFIGURATION.md:314-327`** — add 4 rows to the `### commands` property table for `rate_limits.max_wait_seconds`, `rate_limits.long_wait_ladder`, `rate_limits.circuit_breaker_enabled`, `rate_limits.circuit_breaker_path`
4. **Update `docs/ARCHITECTURE.md:255-267`** — insert `│   ├── rate_limit_circuit.py   # Shared 429 circuit breaker` before line 267 (`handoff_handler.py`) or after it, matching the existing indentation and comment style
5. **Update `CONTRIBUTING.md:231-243`** — insert `│   ├── rate_limit_circuit.py` matching the existing no-comment style in that tree (CONTRIBUTING's fsm tree is sparser than ARCHITECTURE's)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/API.md:100` — add `rate_limits: RateLimitsConfig` to the `CommandsConfig` attribute description alongside `confidence_gate`, `tdd_mode`, `max_refine_count`
7. Update `skills/configure/show-output.md:68-83` — add `rate_limits` display block (all 4 keys with defaults) to the `commands --show` output template
8. Update `skills/configure/areas.md:308-403` — add a `rate_limits` question round to the interactive `commands` configure flow exposing `circuit_breaker_enabled` and `circuit_breaker_path`
9. _(Optional / separate)_ Update `skills/create-loop/reference.md:939-968` and `loop-types.md:791-795` — add `circuit_breaker_enabled` / `circuit_breaker_path` to the rate-limit fields prose and YAML examples (may be deferred to a follow-up)
10. Note: doc-wiring test (`test_enh1138_doc_wiring.py`) is tracked in **ENH-1141** and is a dependency for completeness

## Acceptance Criteria

- LOOPS_GUIDE.md has a circuit-breaker subsection mentioning `circuit_breaker_enabled` and `circuit_breaker_path`
- CONFIGURATION.md documents the `rate_limits` block with `circuit_breaker_enabled` and `circuit_breaker_path`
- Both ARCHITECTURE.md and CONTRIBUTING.md list `rate_limit_circuit.py` in the fsm/ tree

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T06:20:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e20512e-4152-4cfc-9884-2846f71c2341.jsonl`
- `/ll:wire-issue` - 2026-04-17T06:16:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c3528ae-7717-4fa3-abee-f6ad07546776.jsonl`
- `/ll:refine-issue` - 2026-04-17T06:12:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eda26ff9-e951-44b6-86e0-56070ccba333.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6682d5-cb79-4c33-9ce6-ede83cb84a43.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5fa063e0-a03b-43ad-bd68-a49943f3ad8f.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e20512e-4152-4cfc-9884-2846f71c2341.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score 11/11 — Very Large after wiring pass expanded scope)

### Decomposed Into
- ENH-1142: 429 Resilience — Circuit Breaker Core Prose Doc Updates
- ENH-1143: 429 Resilience — Circuit Breaker Skills & API.md Wiring Updates

---

## Status
- [x] Decomposed
