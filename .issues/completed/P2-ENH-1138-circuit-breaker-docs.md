---
id: ENH-1138
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1134
related: [ENH-1134, ENH-1136, ENH-1137]
size: Very Large
confidence_score: 98
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1138: 429 Resilience — Documentation Updates for Circuit Breaker

## Summary

Update `docs/reference/API.md` and `docs/guides/LOOPS_GUIDE.md` to document the `RateLimitCircuit` integration: add `circuit` parameter to the `FSMExecutor.__init__` signature, and add a circuit-breaker subsection to the loops guide.

## Parent Issue

Decomposed from ENH-1134: 429 Resilience — Shared Circuit Breaker Module

## Expected Behavior

### 1. `docs/reference/API.md:4003-4009` — `FSMExecutor.__init__` signature

Add `circuit: RateLimitCircuit | None = None` to the documented signature. While there, also add the already-missing parameters: `signal_detector`, `handoff_handler`, `loops_dir`. Update all four at once.

### 2. `docs/guides/LOOPS_GUIDE.md:1672-1691` — Circuit-breaker subsection

The existing two-tier retry prose describes backoff tiers but has no mention of the circuit-breaker pre-action check or cross-worktree coordination. Add a new subsection covering:

- Pre-action check behavior: LLM actions (`slash_command`, `prompt`) are pre-slept until `estimated_recovery_at` when a circuit is open
- Cross-worktree coordination: any `ll-parallel` worker that detects a 429 writes to `.loops/tmp/rate-limit-circuit.json`; all other workers read the shared file and skip redundant API calls
- Stale detection: entries older than 1h are ignored automatically; no manual reset required
- Configuration: controlled by `circuit_breaker_enabled` and `circuit_breaker_path` in `rate_limits` config block (from ENH-1132)

## Integration Map

### Files to Modify

- `docs/reference/API.md` — `FSMExecutor.__init__` signature section (~lines 4003-4009)
- `docs/guides/LOOPS_GUIDE.md` — two-tier retry section (~lines 1672-1691), add circuit-breaker subsection

### Codebase Research Findings

_Added by `/ll:refine-issue` — source-of-truth anchors for doc accuracy:_

- **Canonical `FSMExecutor.__init__` signature**: `scripts/little_loops/fsm/executor.py:115-124` — parameters in order: `fsm`, `event_callback`, `action_runner`, `signal_detector`, `handoff_handler`, `loops_dir`, `circuit`. All optional except `fsm`. Match this exact ordering in API.md.
- **`RateLimitCircuit` module**: `scripts/little_loops/fsm/rate_limit_circuit.py` (134 lines). Public surface: `record_rate_limit(backoff_seconds)`, `get_estimated_recovery()`, `is_stale()`, `clear()`. Import path: `from little_loops.fsm import RateLimitCircuit` (re-exported via `scripts/little_loops/fsm/__init__.py`).
- **Pre-action check logic**: `scripts/little_loops/fsm/executor.py:969-984` (`_maybe_wait_for_circuit`). Gate conditions: skips when circuit is None, when `_action_mode(state) != "prompt"`, or when `get_estimated_recovery()` returns None. Only `prompt` actions are throttled — `slash_command` is NOT gated despite ENH-1138 text suggesting otherwise; doc prose should say "prompt-mode LLM actions" to match implementation.
- **Stale-detection threshold**: `scripts/little_loops/fsm/rate_limit_circuit.py:27` — `STALE_THRESHOLD_SECONDS = 3600.0` (1 hour since `last_seen`).
- **Default state-file path**: `scripts/little_loops/config/automation.py:133-134` — `circuit_breaker_enabled: bool = True`, `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`. LOOPS_GUIDE.md should cite these exact defaults.
- **Write side (producer)**: `scripts/little_loops/fsm/executor.py:951` (short-burst tier) and `:962` (long-wait tier) call `self._circuit.record_rate_limit(_sleep)` after detecting a 429. Any worker that hits a 429 writes; no designated leader.
- **Atomicity**: writes use `fcntl.flock` sidecar (`<path>.lock`) + `tempfile.mkstemp` + `os.replace`. Recovery timestamp advances monotonically (`max(current, proposed)`) so concurrent writers never shrink an in-flight window — doc prose can note this as a correctness property.
- **Config source was ENH-1132**, already landed in `scripts/little_loops/config/automation.py` (class `RateLimitsConfig`, lines ~120-145). Cross-reference is stable.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

Key implementation files for cross-checking doc accuracy (these consume the API being documented):

- `scripts/little_loops/cli/loop/run.py:32,219` — instantiates `RateLimitCircuit` and passes `circuit=` to `PersistentExecutor`; primary entry point for `ll-loop run`
- `scripts/little_loops/cli/loop/lifecycle.py:253,257` — instantiates `RateLimitCircuit` in `cmd_resume`; `ll-loop resume` path
- `scripts/little_loops/cli/loop/testing.py:9,180` — imports and forwards `circuit: RateLimitCircuit | None = None` in `cmd_simulate`
- `scripts/little_loops/fsm/persistence.py:37,378` — `PersistentExecutor` wraps `FSMExecutor`; passes `circuit=` via `**executor_kwargs`
- `scripts/little_loops/fsm/__init__.py:117,167` — re-exports `RateLimitCircuit` in `__all__`; canonical import path is `from little_loops.fsm import RateLimitCircuit`
- `scripts/little_loops/config/__init__.py:19,61` — re-exports `RateLimitsConfig` in `__all__`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

Additional files that need updating alongside the primary targets:

- `docs/reference/CONFIGURATION.md:69-80,314-328` — `commands.rate_limits` block entirely absent from both the full config example and the `### commands` property table; LOOPS_GUIDE.md will cite `circuit_breaker_enabled` and `circuit_breaker_path` defaults without a canonical config-doc home; add a `rate_limits` subsection covering all keys in `RateLimitsConfig` (including `circuit_breaker_enabled` default `true` and `circuit_breaker_path` default `".loops/tmp/rate-limit-circuit.json"`)
- `docs/ARCHITECTURE.md:255-267` — `rate_limit_circuit.py` absent from the `scripts/little_loops/fsm/` directory tree listing; add it alongside `signal_detector.py` and `handoff_handler.py`
- `CONTRIBUTING.md:231-244` — identical fsm/ directory tree omission; add `rate_limit_circuit.py`
- `docs/reference/API.md:3672,3677-3695` — two internal gaps outside the primary signature section: (1) module table at line 3672 lists `little_loops.fsm.rate_limit_circuit` but there is no corresponding `### little_loops.fsm.rate_limit_circuit` class-level section in the file; (2) the Quick Import block at lines 3677-3695 omits `RateLimitCircuit` despite it being exported in `fsm/__all__`; add both

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_enh1138_doc_wiring.py` — **new test file** following the pattern from `scripts/tests/test_create_extension_wiring.py`; assert that `docs/reference/API.md` contains `signal_detector`, `handoff_handler`, `loops_dir`, `circuit: RateLimitCircuit | None = None`, and `RateLimitCircuit` in the Quick Import block; assert that `docs/guides/LOOPS_GUIDE.md` contains `circuit_breaker_enabled` and `circuit_breaker_path`; assert that `docs/reference/CONFIGURATION.md` contains `circuit_breaker_enabled`

## Implementation Steps

1. **Update `docs/reference/API.md:4003-4009`** — replace the 3-parameter `FSMExecutor.__init__` signature with the full 7-parameter version from `executor.py:115-124`; add type annotations matching the implementation (`SignalDetector | None`, `HandoffHandler | None`, `Path | None`, `RateLimitCircuit | None`)
2. **Update `docs/reference/API.md:3672`** — add `### little_loops.fsm.rate_limit_circuit` class section documenting `RateLimitCircuit` public surface: `__init__(path)`, `record_rate_limit(backoff_seconds)`, `get_estimated_recovery()`, `is_stale()`, `clear()`
3. **Update `docs/reference/API.md:3677-3695`** — add `RateLimitCircuit` to the Quick Import block under `# Execution` or a new `# Rate Limiting` comment group
4. **Update `docs/guides/LOOPS_GUIDE.md:1672-1691`** — add circuit-breaker subsection after the two-tier retry prose covering: pre-action check (prompt-mode only, via `_maybe_wait_for_circuit`), cross-worktree coordination (shared JSON file), stale detection (1h threshold), atomicity (monotonic `max()` advance), config knobs (`circuit_breaker_enabled: true`, `circuit_breaker_path: ".loops/tmp/rate-limit-circuit.json"`)
5. **Update `docs/reference/CONFIGURATION.md:69-80,314-328`** — add `commands.rate_limits` subsection to both the full config example block and the `### commands` property table; document all keys in `RateLimitsConfig` including `circuit_breaker_enabled` and `circuit_breaker_path`
6. **Update `docs/ARCHITECTURE.md:255-267`** — add `rate_limit_circuit.py` to the `scripts/little_loops/fsm/` directory tree
7. **Update `CONTRIBUTING.md:231-244`** — add `rate_limit_circuit.py` to the `fsm/` directory tree
8. **Write `scripts/tests/test_enh1138_doc_wiring.py`** — follow `test_create_extension_wiring.py` pattern; assert the four new parameters appear in `docs/reference/API.md`; assert `circuit_breaker_enabled` appears in both `LOOPS_GUIDE.md` and `CONFIGURATION.md`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Verify no broken cross-references: run `ll-check-links` after all doc edits complete
10. Run `ll-verify-docs` — no count changes expected but confirms no regressions

## Acceptance Criteria

- `FSMExecutor.__init__` docs include `circuit: RateLimitCircuit | None = None`, `signal_detector`, `handoff_handler`, `loops_dir`
- LOOPS_GUIDE.md has a circuit-breaker subsection explaining pre-action check, cross-worktree coordination, stale detection, and config knobs
- No broken cross-references introduced

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T05:56:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6682d5-cb79-4c33-9ce6-ede83cb84a43.jsonl`
- `/ll:refine-issue` - 2026-04-17T05:45:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/914b84e4-f844-4eb4-8c1a-96b685a19ae2.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81193e52-67e2-461f-8b12-656dced49eb5.jsonl`
- `/ll:wire-issue` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/914b84e4-f844-4eb4-8c1a-96b685a19ae2.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ce3f849e-32b4-4df2-a22a-842c7c640c75.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2e6682d5-cb79-4c33-9ce6-ede83cb84a43.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score: 11/11 — Very Large)

### Decomposed Into
- ENH-1139: 429 Resilience — API.md Reference Updates for Circuit Breaker
- ENH-1140: 429 Resilience — Prose Doc Updates (Loops Guide, Config, Architecture)
- ENH-1141: 429 Resilience — Doc Wiring Test and Link Verification

## Status
- [ ] Open
