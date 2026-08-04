---
id: FEAT-3043
title: Advisor configuration - AdvisorConfig block
type: FEAT
parent: FEAT-3037
priority: P3
status: open
testable: true
discovered_date: 2026-08-04
labels:
- planning-hub
---

# FEAT-3043: Advisor configuration - AdvisorConfig block

## Summary

Add the `advisor:` configuration block (`AdvisorConfig` dataclass, schema
validation, `BRConfig` round-trip, and `.ll/ll.local.md` merge support) that
the advisor core (FEAT-3044) will read to resolve its host, model, capability
floor, and per-consult timeout. This is pure config plumbing — no consult
logic, no CLI — and is independently testable via config round-trip tests.

## Parent Issue

Decomposed from FEAT-3037: Host-agnostic advisor. FEAT-3037 scored Very Large
(11/11) on `ll-issues size` and covers three architecturally separable
concerns (shared transport, config plumbing, advisor core + CLI). This child
covers the config plumbing concern.

## Current Behavior

- There is no `advisor` configuration block. `OrchestrationConfig`
  (`config/orchestration.py:62-103`) is the closest existing pattern: a
  dataclass with a `from_dict` classmethod that does no enum validation
  itself (enum enforcement lives entirely in `config-schema.json`).
- `BRConfig.to_dict()` has no generic dataclass serializer — every block,
  including `orchestration`, is hand-rolled field-by-field
  (`config/core.py:786-803`, tracked as a known gap under BUG-3012).
- `.ll/ll.local.md` merge (arrays replace, nested deep-merge, `null` removes)
  is one shared, generic `deep_merge()` (`config/core.py:57-84`) applied once
  over the whole raw config in `hooks/session_start.py:145` — this is
  automatic once a block is added to the raw config dict; no per-block merge
  code is needed.

## Expected Behavior

- `advisor` is an optional block in `.ll/ll-config.json`; absent means the
  advisor is disabled by default.
- `AdvisorConfig` round-trips through `BRConfig` (parse → `to_dict()` →
  reparse) with correct defaults.
- `advisor.host` validates against the same enum as `orchestration.host_cli`:
  `claude-code | codex | opencode | pi | gemini | omp | kimi-code`.
- `.ll/ll.local.md` overrides merge correctly (arrays replace, nested
  deep-merge, explicit `null` removes) — this is automatic via the existing
  generic `deep_merge()`, verified by a config-round-trip test, not new merge
  code.

## Proposed Solution

### `advisor:` block shape

```jsonc
"advisor": {
  "enabled": true,
  "host": "claude-code",     // registry key; may differ from orchestration.host_cli
  "model": "opus",
  "min_tier": "opus",        // capability floor; enforced within a host, warned across
  "timeout_seconds": 180,
  "triggers": ["confidence_gate", "loop_stall", "pre_done"]
}
```

- `host` validates against the same enum as `orchestration.host_cli`. Not
  `"claude"` — that is not a registry key. `config-schema.json`'s
  `orchestration.host_cli` enum (`:1558-1562`) is a bare inline literal array
  with no existing `$ref`'able shared definition — `advisor.host`'s enum will
  need to duplicate the same 7-value array rather than reference it.
- `timeout_seconds` is mandatory-with-a-default: a synchronous in-band consult
  with no timeout can hang a loop indefinitely.
- `max_consults_per_task` is **deliberately absent** from this schema.
  Enforcement needs task identity, which arrives in a later slice (FEAT-3038);
  shipping an accepted-but-ignored key is a footgun.
- `AdvisorConfig.from_dict` follows `OrchestrationConfig.from_dict`'s division
  of labor: the dataclass just reads fields; schema validates `host` and
  other enums.
- `AdvisorConfig`'s `to_dict()` entry needs the same manual field listing as
  every other block in `config/core.py` — no shared serializer exists to lean
  on.

## API/Interface

```python
# scripts/little_loops/config/orchestration.py (advisor is host/orchestration
# -shaped; keep it beside OrchestrationConfig)
@dataclass(frozen=True)
class AdvisorConfig:
    enabled: bool
    host: str | None
    model: str
    min_tier: str | None
    timeout_seconds: int
    triggers: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdvisorConfig": ...
```

## Program Design

### Types

- `AdvisorConfig: {enabled: bool, host: str | None, model: str, min_tier: str | None, timeout_seconds: int, triggers: list[str]}`

### Signatures

- `AdvisorConfig.from_dict(data: dict[str, Any]) -> AdvisorConfig`

## Integration Map

### Files to Modify

- `scripts/little_loops/config/orchestration.py` — add `AdvisorConfig`.
- `scripts/little_loops/config/core.py` — parse + expose `advisor` property;
  add to the `to_dict()` round-trip (near line 786, where the `orchestration`
  key starts).
- `scripts/little_loops/config-schema.json` — `advisor` block, `host` enum
  matching `orchestration.host_cli` (line ~1560).
- `scripts/little_loops/config/__init__.py` — add `AdvisorConfig` to the
  `from little_loops.config.orchestration import (...)` block (lines 79-84)
  and to `__all__` (starts line 86); without this, `from little_loops.config
  import AdvisorConfig` fails even though `config/orchestration.py` defines
  it.

### Similar Patterns

- `OrchestrationConfig.from_dict` — dataclass config plumbing convention to
  mirror exactly.

### Tests

- `scripts/tests/test_config.py` — mirror `TestOrchestrationConfig`
  (~line 3404) and `TestBRConfigOrchestration` (~line 3474) exactly for
  `AdvisorConfig`'s defaults/override/`.ll/ll.local.md`-merge coverage; the
  `deep_merge` arrays-replace/nested-merge/`None`-removes cases are already
  tested generically starting ~line 3315 and don't need advisor-specific
  duplicates — just a round-trip test confirming `advisor` participates in
  the existing generic merge.

### Documentation

- `docs/reference/API.md` — `AdvisorConfig` under the config reference.

### Configuration

- `.ll/ll-config.json` — new optional `advisor` block (absent = disabled).

## Acceptance Criteria

1. `advisor` block round-trips through `BRConfig` (parse → `to_dict()` →
   reparse) with correct defaults when absent.
2. `advisor` merges correctly from `.ll/ll.local.md` (arrays replace, nested
   deep-merge, `null` removes) via the existing generic `deep_merge()`.
3. `advisor.host` values outside the registry enum
   (`claude-code | codex | opencode | pi | gemini | omp | kimi-code`) fail
   schema validation.
4. `from little_loops.config import AdvisorConfig` succeeds.
5. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Out of Scope

- `consult()`, `rank_model()`, `check_floor()`, the `ll-advise` CLI, and the
  `ll-doctor` check (FEAT-3044) — this issue ships config parsing only; no
  code reads `AdvisorConfig` yet.
- `max_consults_per_task` — intentionally deferred to FEAT-3038, which has
  the task-identity plumbing to enforce it.

## Impact

- **Priority**: P3 — pure config plumbing, no user-facing behavior on its
  own; unlocks FEAT-3044.
- **Effort**: Small — closely mirrors an existing, well-tested pattern
  (`OrchestrationConfig`).
- **Risk**: Low — additive, isolated to config parsing; no existing call
  sites depend on this block's presence.
- **Breaking Change**: No — `advisor` is absent by default.

## Related Key Documentation

- `docs/reference/API.md`
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli`

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-04T20:47:20 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`
