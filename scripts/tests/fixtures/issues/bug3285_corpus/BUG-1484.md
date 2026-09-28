---
id: BUG-1484
type: BUG
priority: P2
status: done
captured_at: '2026-05-15T20:48:07Z'
discovered_date: 2026-05-15
discovered_by: capture-issue
relates_to: FEAT-1479
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-15T00:00:00Z
---

# BUG-1484: `config/__init__.py` Imports `OrchestrationConfig` and `CLConfig` Before They Exist in `core.py`

## Summary

`scripts/little_loops/config/__init__.py` line 32 imports `OrchestrationConfig` and `CLConfig` from `little_loops.config.core`, but neither class is defined there. This causes an `ImportError` on package import, breaking every `ll-*` CLI tool (`ll-issues`, `ll-auto`, `ll-sprint`, etc.).

## Motivation

All `ll-*` CLI tools are completely broken — `ll-issues`, `ll-auto`, `ll-sprint`, `ll-parallel`, `ll-action`, and `ll-loop` all fail at import time. This blocks any `little_loops`-dependent workflow until the import is fixed.

- **Blocks**: All development workflows that use `ll-*` tools
- **Cause**: Partial apply of FEAT-1479 — `__init__.py` was updated to export new classes before they were added to `core.py`
- **Resolution cost**: Low — either add two dataclass stubs or revert one import line

## Root Cause

**File**: `scripts/little_loops/config/__init__.py:32`
**Function/anchor**: module-level import

```python
from little_loops.config.core import BRConfig, CLConfig, OrchestrationConfig, ProjectConfig
```

`BRConfig` and `ProjectConfig` exist in `core.py`. **`CLConfig` also exists** — as a backwards-compatibility alias `CLConfig = BRConfig` at `core.py:661` — so it is **not** missing. Only `OrchestrationConfig` is absent from `core.py`. This appears to be a partial apply of FEAT-1479 (Pi adapter config candidate work) — `__init__.py` was updated to export `OrchestrationConfig` before it was added to `core.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `CLConfig = BRConfig` alias is present at `core.py:661` — it was never missing; the issue title is misleading on this point
- `OrchestrationConfig` is the only class absent from `core.py` that is named in the broken import
- `OrchestrationConfig` was briefly added in commit `a36225e6` with one field `host_cli: str = "auto"` and a `@classmethod from_dict()`, then reverted along with `PI_CONFIG_DIR` and the pi probe branch
- **Current state** (all committed, 314 tests passing): `config/__init__.py:32` reads `from little_loops.config.core import BRConfig, CLConfig, ProjectConfig` — `OrchestrationConfig` is absent from the import; `core.py` has no `OrchestrationConfig` class; the `ImportError` no longer reproduces

**Error observed**:
```
ImportError: cannot import name 'OrchestrationConfig' from 'little_loops.config.core'
```

## Steps to Reproduce

```bash
ll-issues next-id
# or any ll-* CLI tool
```

## Expected Behavior

`ll-issues next-id` (and all other `ll-*` tools) run without import errors.

## Current Behavior

```
Traceback (most recent call last):
  File ".../bin/ll-issues", line 5, in <module>
    from little_loops.cli import main_issues
  File ".../little_loops/__init__.py", line 7, in <module>
    from little_loops.config import BRConfig
  File ".../little_loops/config/__init__.py", line 32, in <module>
    from little_loops.config.core import BRConfig, CLConfig, OrchestrationConfig, ProjectConfig
ImportError: cannot import name 'OrchestrationConfig' from 'little_loops.config.core'
```

## Proposed Solution

**Option A** (preferred if FEAT-1479 is in-flight): Add `OrchestrationConfig` dataclass to `scripts/little_loops/config/core.py` per the FEAT-1479 spec. (`CLConfig` already exists as `CLConfig = BRConfig` at `core.py:661` — no action needed for it.)

**Option B** (quick unblock): Remove `OrchestrationConfig` from the `__init__.py` import line and from `__all__` until FEAT-1479 is complete.

> **Selected:** Option B — Bug already fixed by revert `fb5d2721`; no live code needs `OrchestrationConfig`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A implementation spec** (from commit `a36225e6` which briefly had a working version):
- Add before `ProjectConfig` at `core.py:117`:
  ```python
  @dataclass
  class OrchestrationConfig:
      """Orchestration-layer configuration for host CLI selection."""
      host_cli: str = "auto"

      @classmethod
      def from_dict(cls, data: dict[str, Any]) -> OrchestrationConfig:
          return cls(host_cli=data.get("host_cli", "auto"))
  ```
- Wire into `BRConfig._parse_config()` (following the pattern at `core.py:207`): `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))`
- Add `@property orchestration(self) -> OrchestrationConfig` accessor to `BRConfig`
- Add `OrchestrationConfig` to `config/__init__.py:32` import and to `__all__`
- Add `test_orchestration_in_schema()` to `test_config_schema.py` following `test_hooks_in_schema()` pattern
- Add `orchestration` section to `config-schema.json` with `host_cli` string property

**Option B was already applied**: The current committed state has no `OrchestrationConfig` in `config/__init__.py:32` or in `core.py`. If the goal is only to fix the `ImportError`, this bug is already resolved. The issue may only need closing.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-15.

**Selected**: Option B — Accept current state, close bug as fixed

**Reasoning**: The `ImportError` cannot reproduce in the current committed state — revert `fb5d2721` already removed `OrchestrationConfig` from `config/__init__.py` and from `core.py` (all 314 tests pass). No live code reads `orchestration.host_cli` from config today (`host_runner.py` reads only env vars), so `OrchestrationConfig` has zero consumers. Implementing Option A would add FEAT-1479 plumbing to a BUG ticket without bridging the `host_runner.py` integration gap — creating a config key that silently does nothing until FEAT-1467 (P3) is complete. Future `OrchestrationConfig` work belongs in FEAT-1467 and FEAT-1479, not here.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 1/3 | 2/3 | 1/3 | 7/12 |
| Option B | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: Fits the dataclass pattern perfectly (reuse score 3/3) but adds feature plumbing (FEAT-1479) to a BUG ticket; `resolve_host()` would still not read `orchestration.host_cli` from config without a separate FEAT-1467 change
- **Option B**: `OrchestrationConfig` absent from all Python source; `host_runner.py` uses env vars only; revert `fb5d2721` already committed; 314 tests pass; zero consumers exist anywhere in the codebase

## Implementation Steps

1. Verify current state: run `python3 -c "from little_loops.config import BRConfig; print('OK')"` — if it prints `OK`, the `ImportError` is already resolved (Option B was applied); consider closing as fixed
2. **If re-adding `OrchestrationConfig` (Option A)**:
   a. Add `OrchestrationConfig` dataclass to `scripts/little_loops/config/core.py` before `ProjectConfig` (line 117) with field `host_cli: str = "auto"` and `from_dict()` classmethod following the `ProjectConfig` pattern at `core.py:117–143`
   b. Wire into `BRConfig._parse_config()` following the pattern at `core.py:207`: `self._orchestration = OrchestrationConfig.from_dict(self._raw_config.get("orchestration", {}))`
   c. Add `@property orchestration(self) -> OrchestrationConfig` to `BRConfig` following the accessor pattern at `core.py:278`
   d. Add `OrchestrationConfig` to `config/__init__.py:32` import and add to `__all__`
   e. Add `orchestration` block to `config-schema.json` with `host_cli` string property (enum: `["auto","claude-code","codex","opencode","pi"]`)
   f. Add `TestOrchestrationConfig` class to `scripts/tests/test_config.py` following `TestProjectConfig` pattern; add `test_orchestration_in_schema()` to `scripts/tests/test_config_schema.py` following `test_hooks_in_schema()`
3. Verify all `ll-*` CLI tools import without errors: `python3 -c "from little_loops.config import BRConfig, OrchestrationConfig; print('OK')"`
4. Run test suite: `python -m pytest scripts/tests/ -x -q`

## Integration Map

### Files to Modify
- `scripts/little_loops/config/__init__.py` — fix the broken import (line 32)
- `scripts/little_loops/config/core.py` — add `CLConfig` and `OrchestrationConfig` (Option A)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/__init__.py` — imports `BRConfig` from `little_loops.config`
- All `ll-*` CLI entry points transitively import from `little_loops`

### Similar Patterns
- `core.py:661` — `CLConfig = BRConfig` alias: the established pattern for backwards-compat re-exports is a bare name assignment at the bottom of the module, not a separate dataclass
- `scripts/little_loops/config/automation.py:AutomationConfig.from_dict()` — canonical `@dataclass` + `@classmethod from_dict(cls, data)` pattern to follow for any new config class
- `scripts/little_loops/config/features.py:EventsConfig.from_dict()` — sub-config composition pattern using `data.get("key", {})`

### Tests
- `scripts/tests/test_config.py` — `TestBRConfigAliases.test_clconfig_alias` (existing) verifies `CLConfig is BRConfig`; `TestProjectConfig` is the template pattern for any new config class tests
- `scripts/tests/test_config_schema.py` — `TestConfigSchema.test_hooks_in_schema()` is the template for a `test_orchestration_in_schema()` regression guard if `OrchestrationConfig` is re-introduced
- `scripts/tests/test_orchestrator.py` — previously held `TestBRConfigWithoutOrchestration.test_br_config_loads_without_orchestration_key` (asserted `config.orchestration.host_cli == "auto"`); this test was removed when `OrchestrationConfig` was reverted (all 314 tests currently pass)

### Documentation
- N/A

### Configuration
- `config-schema.json` — may need additions for `CLConfig`/`OrchestrationConfig` per FEAT-1479 spec

## Impact

- **Priority**: P2 — All `ll-*` CLI tools broken; unblocks all `little_loops`-dependent workflows
- **Effort**: Small — Add two dataclasses (Option A) or revert one import line (Option B)
- **Risk**: Low — Targeted import fix; no behavior change
- **Breaking Change**: No — Restores existing behavior
- **Blast Radius**: All `ll-*` CLI tools (`ll-issues`, `ll-auto`, `ll-sprint`, `ll-parallel`, `ll-action`, `ll-loop`) and any tool that imports from `little_loops`; automation runs fail immediately on import

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/config/__init__.py:32` | The broken import line |
| `scripts/little_loops/config/core.py` | Missing `CLConfig` and `OrchestrationConfig` definitions |
| `.issues/features/P5-FEAT-1479-pi-adapter-config-candidate-schema-and-config-tests.md` | In-progress work that likely introduced this partial apply |

## Labels

config, import-error, broken, pi-adapter

## Status

**Open** | Created: 2026-05-15 | Priority: P2

---

## Session Log
- `/ll:confidence-check` - 2026-05-15T00:00:00Z - `625d3686-d0e2-4e0f-84ef-fb76e68715c7.jsonl`
- `/ll:decide-issue` - 2026-05-15T21:09:41 - `078745a5-ea9c-4f51-a51e-f76ca76e5b84.jsonl`
- `/ll:refine-issue` - 2026-05-15T21:03:19 - `1169a12a-6e8b-4461-bd90-cb7a7c13e359.jsonl`
- `/ll:capture-issue` - 2026-05-15T20:48:07Z - `5ac48eaf-913e-40cd-8b15-98d99f2901cc.jsonl`
- `/ll:format-issue` - 2026-05-15T00:00:00Z
