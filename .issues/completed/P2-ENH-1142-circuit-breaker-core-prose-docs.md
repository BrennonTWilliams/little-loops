---
id: ENH-1142
type: ENH
priority: P2
status: completed
completed_date: 2026-04-17
discovered_date: 2026-04-17
parent: ENH-1140
related: [ENH-1138, ENH-1134, ENH-1141]
size: Medium
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
testable: false
---

# ENH-1142: 429 Resilience — Circuit Breaker Core Prose Doc Updates

## Summary

Update four documentation files with circuit-breaker prose: (1) add circuit-breaker subsection to `docs/guides/LOOPS_GUIDE.md`, (2) add `rate_limits` config block to `docs/reference/CONFIGURATION.md`, (3) add `rate_limit_circuit.py` to `docs/ARCHITECTURE.md` fsm directory tree, (4) add `rate_limit_circuit.py` to `CONTRIBUTING.md` fsm directory tree.

## Parent Issue

Decomposed from ENH-1140: 429 Resilience — Prose Doc Updates (Loops Guide, Config, Architecture)

## Current Behavior

The `RateLimitCircuit` module (`scripts/little_loops/fsm/rate_limit_circuit.py`) landed under ENH-1134 with full test coverage and CLI wiring, but four prose docs still omit it:

1. `docs/guides/LOOPS_GUIDE.md` — two-tier retry section ends at the thundering-herd note; has no circuit-breaker subsection
2. `docs/reference/CONFIGURATION.md` — `commands.rate_limits` block is absent from both the full config example and the `### commands` property table
3. `docs/ARCHITECTURE.md` — fsm/ directory tree lists `handoff_handler.py` last, with no `rate_limit_circuit.py` entry
4. `CONTRIBUTING.md` — same fsm/ tree gap as ARCHITECTURE.md

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

Document all keys in `RateLimitsConfig` (`scripts/little_loops/config/automation.py:113-146`). The full block has FOUR keys:

- `max_wait_seconds: int = 21600` — total wall-clock budget (6h) before routing to `on_rate_limit_exhausted`
- `long_wait_ladder: list[int] = [300, 900, 1800, 3600]` — long-wait tier backoff ladder
- `circuit_breaker_enabled: bool = True`
- `circuit_breaker_path: str = ".loops/tmp/rate-limit-circuit.json"`

Block lives under `commands.rate_limits` (confirmed: `CommandsConfig.rate_limits` at `automation.py:158`, serialized at `core.py:411-416`).

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
- **Config nesting**: `CommandsConfig.rate_limits` field at `automation.py:158` (not `AutomationConfig`); serialized under `commands.rate_limits` at `config/core.py:411-416`
- **LOOPS_GUIDE.md insertion point**: new subsection should go AFTER the thundering-herd note at line 1691 and BEFORE `### Stall Detection` at line 1693
- **ARCHITECTURE.md fsm tree**: lines 255-267, entries end at `handoff_handler.py` line 267 — add `rate_limit_circuit.py` after it
- **CONTRIBUTING.md fsm tree**: lines 231-243 (ends at `handoff_handler.py` line 243), followed by `extension.py` at 244 — add `rate_limit_circuit.py` before line 244

### Tests

- All existing tests (`test_rate_limit_circuit.py`, `test_config.py`, `test_config_schema.py`, `test_fsm_executor.py`, `test_cli_loop_lifecycle.py`, `test_ll_loop_commands.py`) pass today and are unaffected by prose-only changes
- Doc-wiring test (`test_enh1138_doc_wiring.py`) is tracked in **ENH-1141**

_Wiring pass added by `/ll:wire-issue`:_
- **Coverage gap (steps 4–5)**: ENH-1141's planned `test_enh1138_doc_wiring.py` assertions cover `LOOPS_GUIDE.md` (`circuit_breaker_enabled`, `circuit_breaker_path`) and `CONFIGURATION.md` (`circuit_breaker_enabled`), but do NOT include assertions for:
  - `docs/ARCHITECTURE.md` containing `rate_limit_circuit.py` (step 4)
  - `CONTRIBUTING.md` containing `rate_limit_circuit.py` (step 5)
  ENH-1141 should be updated to add these two assertions before it is implemented, or a standalone test should be added to `test_create_extension_wiring.py` following the pattern at `scripts/tests/test_create_extension_wiring.py:156`.

## Implementation Steps

1. **Update `docs/guides/LOOPS_GUIDE.md`** — insert new circuit-breaker subsection between line 1691 (end of thundering-herd note) and line 1693 (`### Stall Detection`). Cover: pre-action check (prompt-mode only; `slash_command` is NOT gated), cross-worktree coordination via `.loops/tmp/rate-limit-circuit.json`, 1-hour stale auto-ignore, atomicity (`fcntl.flock` + `os.replace` + monotonic `max()` advance), config knobs (`circuit_breaker_enabled`, `circuit_breaker_path`)
2. **Update `docs/reference/CONFIGURATION.md:69-80`** — add `rate_limits` sub-block inside the `commands` block of the full config example, showing all 4 keys with defaults
3. **Update `docs/reference/CONFIGURATION.md:314-327`** — add 4 rows to the `### commands` property table (table ends at line 327) for all `rate_limits.*` keys
4. **Update `docs/ARCHITECTURE.md:255-267`** — insert `│   ├── rate_limit_circuit.py   # Shared 429 circuit breaker` after `handoff_handler.py`
5. **Update `CONTRIBUTING.md:231-243`** — insert `│   ├── rate_limit_circuit.py` matching the existing no-comment style in that tree

## Acceptance Criteria

- `docs/guides/LOOPS_GUIDE.md` has a circuit-breaker subsection mentioning `circuit_breaker_enabled` and `circuit_breaker_path`
- `docs/reference/CONFIGURATION.md` documents the `rate_limits` block with all 4 keys including `circuit_breaker_enabled` and `circuit_breaker_path`
- Both `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` list `rate_limit_circuit.py` in the fsm/ tree

## Proposed Solution

Prose-only edits, no code changes. See Implementation Steps for the per-file insertion points. Use anchors (`### Stall Detection` header, `handoff_handler.py` tree entry, `commands` config block boundaries) to locate inserts rather than line numbers, which drift.

## Scope Boundaries

- Out of scope: any test additions (tracked in ENH-1141)
- Out of scope: expanding API.md (already landed under ENH-1138)
- Out of scope: editing CHANGELOG.md or README.md
- Out of scope: refactoring the existing two-tier retry prose — only append the new subsection

## Impact

- **Priority**: P2 — docs-only gap for a shipped feature; does not block users but leaves the config surface undiscoverable
- **Effort**: Small — ~4 targeted insertions across 4 files, all locations pre-scouted
- **Risk**: Low — prose-only; no code paths touched, no tests to break
- **Breaking Change**: No

## Labels

`enhancement`, `docs`, `rate-limit-circuit`

## Resolution

Completed 2026-04-17. Prose-only doc updates landed across four files:

- `docs/guides/LOOPS_GUIDE.md` — added "Cross-worktree circuit breaker" subsection after the thundering-herd note, before `### Stall Detection`. Covers prompt-mode gating (`slash_command` is NOT gated), `.loops/tmp/rate-limit-circuit.json` sidecar coordination, 1h stale auto-ignore, atomicity (`fcntl.flock` + `os.replace` + monotonic `max()`), and the `circuit_breaker_enabled` / `circuit_breaker_path` config knobs.
- `docs/reference/CONFIGURATION.md` — added `commands.rate_limits` sub-block to the full config example with all 4 keys (`max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`, `circuit_breaker_path`), plus 4 matching rows in the `### commands` property table.
- `docs/ARCHITECTURE.md` — added `rate_limit_circuit.py` entry to `scripts/little_loops/fsm/` tree after `handoff_handler.py` (with inline comment).
- `CONTRIBUTING.md` — added `rate_limit_circuit.py` entry to the identical fsm/ tree (no comment, matching sibling entries).

Verification: grep confirms both `circuit_breaker_enabled` and `circuit_breaker_path` appear in LOOPS_GUIDE.md; `rate_limits` + both circuit-breaker keys appear in CONFIGURATION.md; `rate_limit_circuit.py` appears in both ARCHITECTURE.md and CONTRIBUTING.md. `ruff check scripts/` passes (no code changes). No tests run — `testable: false` per frontmatter; doc-wiring test assertions are the scope of ENH-1141.

## Session Log
- `/ll:manage-issue` - 2026-04-17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/506ab92a-05c5-4bf9-bf1d-50aa96302fe8.jsonl`
- `/ll:ready-issue` - 2026-04-17T06:29:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0825439-7dab-4986-9025-fa22fb0ff302.jsonl`
- `/ll:wire-issue` - 2026-04-17T06:26:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04ae6c1d-2ee0-4a43-b8c5-f8600c76df7b.jsonl`
- `/ll:refine-issue` - 2026-04-17T06:22:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c2b0411e-88e8-453f-bf55-0ff9ea0f9e56.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e20512e-4152-4cfc-9884-2846f71c2341.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4faedd2a-5d12-4c73-9ecb-a0e8ae7b27b0.jsonl`

---

## Status
- [x] Completed
