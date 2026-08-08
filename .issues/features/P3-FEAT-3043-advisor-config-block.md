---
id: FEAT-3043
title: Advisor configuration - AdvisorConfig block
type: FEAT
parent: FEAT-3037
priority: P3
status: done
testable: true
discovered_date: 2026-08-04
completed_at: '2026-08-08T17:29:19Z'
labels:
- planning-hub
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 96
score_complexity: 24
score_test_coverage: 25
score_ambiguity: 24
score_change_surface: 23
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

## Use Case

A project maintainer wants to enable the advisor for a specific project
without touching any advisor consult code (that ships separately in
FEAT-3044). They add an `advisor:` block to `.ll/ll-config.json` — setting
`host`, `model`, `min_tier`, `timeout_seconds`, and `triggers` — and expect
`ll-config get advisor.*` to read it back without an "unknown section"
warning, and a malformed `host` value to fail schema validation immediately
rather than surfacing as a confusing runtime error once FEAT-3044 lands. A
second maintainer overrides `advisor.timeout_seconds` for their own machine
via `.ll/ll.local.md` and expects the override to take effect on next
session start, using the same deep-merge semantics every other config block
already gets for free.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `BRConfig._parse_config` spans `config/core.py:242-289`; lines `229-240` are the preceding `_load_config` method (reads `.ll/ll-config.json` only — no `.ll/ll.local.md` merge happens there). This section's earlier `229-289` citation combined both methods.
- `to_dict()`'s `"orchestration"` entry is confirmed at `core.py:784-801` (matches this issue's own Program Design → Call Path citation) — this section's separate `786-803` citation has drifted 2 lines from current source.
- BUG-3012 (status `done`, completed 2026-08-03) reconfirmed unchanged as of this pass: it added more hand-rolled `to_dict()` sections plus a schema/`to_dict()` parity guard (`test_config_schema.py:1082` `test_to_dict_emits_every_schema_section`, `:1104` `test_to_dict_emits_no_key_absent_from_schema`) — it did not add a generic dataclass serializer. `AdvisorConfig` still needs a fully hand-rolled `to_dict()` entry, exactly as this issue already assumes.

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

### Deviations

- 2026-08-08: `AdvisorConfig` was implemented as a plain `@dataclass` (mutable,
  with field defaults) rather than the `@dataclass(frozen=True)` shown in the
  API/Interface sketch. This matches `OrchestrationConfig`'s actual shape in
  `config/orchestration.py` (also plain, mutable, with defaults) — the pattern
  this issue's own Proposed Solution says to mirror exactly. None of the
  sibling dataclasses in that module (`ComposerConfig`, `ClusterConfig`, etc.)
  are frozen, so a frozen `AdvisorConfig` would have been inconsistent with
  its neighbors for no behavioral benefit (nothing in this issue's scope
  mutates an `AdvisorConfig` instance after construction either way).

### Types

- `AdvisorConfig: {enabled: bool, host: str | None, model: str, min_tier: str | None, timeout_seconds: int, triggers: list[str]}`

### Signatures

- `AdvisorConfig.from_dict(data: dict[str, Any]) -> AdvisorConfig`

### Call Path

`BRConfig.__init__` (`config/core.py:215`) -> `_load_config` (`config/core.py:229-240`) -> `_parse_config` (`config/core.py:242-289`) -> `AdvisorConfig.from_dict(raw.get("advisor", {}))` -> `self._advisor` -> `property advisor` -> consumer `BRConfig(project_root).advisor` -> `to_dict()` (`config/core.py:650`) -> `"advisor"` entry (mirrors the `"orchestration"` entry at `config/core.py:784-801`)

### Decision Rules

- `advisor.host` — 7-value registry enum (`claude-code | codex | opencode | pi | gemini | omp | kimi-code`); duplicated inline in `config-schema.json` because the schema has no `$ref`/`$defs` support.
- `timeout_seconds` — mandatory-with-default `180`; no absent path is valid (a sync in-band consult with no timeout can hang a loop indefinitely).
- `triggers` — keyword list (`confidence_gate`, `loop_stall`, `pre_done`); membership is the only validation.
- `min_tier` — capability-floor gate: enforced within a host, warned across hosts.
- `max_consults_per_task` — deliberately absent; deferred to FEAT-3038 (task identity) — shipping an accepted-but-ignored key is a footgun.

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

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_config.py` — mirror `TestOrchestrationConfig`
  (~line 3406) and `TestBRConfigOrchestration` (~line 3476) exactly for
  `AdvisorConfig`'s defaults/override coverage; the
  `deep_merge` arrays-replace/nested-merge/`None`-removes cases are already
  tested generically in `TestDeepMerge` (`:3316-3379`) and don't need
  advisor-specific duplicates — just one `deep_merge()`-direct test
  (raw-dict style, not through `BRConfig`, since `BRConfig._load_config`
  reads only `ll-config.json`) confirming `advisor` participates in the
  existing generic merge.
- `scripts/tests/test_config.py` — additionally mirror
  `test_to_dict_orchestration` (`:1011`) and
  `test_to_dict_orchestration_defaults_when_unset` (`:1035`) — these, not
  `TestBRConfigOrchestration`, are the actual parse → `to_dict()` → reparse
  round-trip pattern AC #1 requires.
- `scripts/tests/test_config_schema.py` — `test_to_dict_emits_every_schema_section`
  (`:1082`) and `test_to_dict_emits_no_key_absent_from_schema` (`:1104`) will
  fail if `advisor` lands in the schema and `to_dict()` out of lockstep;
  land both in the same change.
- `scripts/tests/test_config_cli.py` — `test_every_to_dict_key_is_a_known_root`
  (`:148`) and `test_every_schema_top_level_property_is_a_known_root` (`:164`)
  iterate live schema/`to_dict()` roots and will auto-cover `advisor` once
  it's added to both sides — no source or test-file edits needed here beyond
  keeping schema and `to_dict()` in sync.
- `scripts/tests/test_config_properties.py` — `TestBRConfigProperties.test_to_dict_idempotent`
  (`:59`, Hypothesis-based) round-trips `to_dict()` generically; `advisor`
  is covered automatically, no edit needed.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md` — `AdvisorConfig` under the config reference; exact
  anchor is the `BRConfig` → `#### Properties` table, add an `advisor` row
  immediately after the `orchestration` row (`:151`).
- `docs/reference/CONFIGURATION.md` — not previously listed. Add a new
  `### \`advisor\`` section following the `### \`orchestration\`` section's
  `| Key | Default | Description |` table pattern, inserted after
  `orchestration` ends and before `### \`hooks\`` (`:1202-1274`).

### Configuration

- `.ll/ll-config.json` — new optional `advisor` block (absent = disabled).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- No consumer files — confirmed `AdvisorConfig` has zero callers in this
  issue's scope (consult logic and CLI are FEAT-3044). `host_runner.py:1625-1643`
  (`resolve_host()` reading `config.orchestration.host_cli`) and
  `cli/loop/config_cmds.py:23`, `cli/loop/run.py:592`, `cli/loop/lifecycle.py:586`
  (reading `.orchestration` off `BRConfig`) are `OrchestrationConfig`
  consumers only — informational precedent for FEAT-3044's future
  `config.advisor` consumer, not wiring required by this issue.
- `scripts/little_loops/cli/config.py`'s `_warn_if_unknown_section()`
  (`:83-101`) computes known config roots as the union of
  `cfg.to_dict().keys()` and the schema's top-level `properties` — no code
  change needed there; `ll-config get advisor.*` stops warning automatically
  once `advisor` is in both schema and `to_dict()`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- **Schema/to_dict lockstep**: `test_config_schema.py:1082` (`test_to_dict_emits_every_schema_section`) and `:1104` (`test_to_dict_emits_no_key_absent_from_schema`) force `config-schema.json` and `BRConfig.to_dict()` to stay bidirectionally in sync — declaring `advisor` in the schema without emitting it in `to_dict()` (or vice versa) breaks the suite. `test_config_cli.py:164` additionally requires every schema root be a known `ll-config get` root.
- **No runtime jsonschema validation**: `jsonschema` is not a dependency; the `host` enum is enforced structurally (test asserts the schema's enum content, cf. `test_config_schema.py:787`) and by `ll-init` when writing configs — there is no runtime validator that rejects a bad `advisor.host`. AC #3 is satisfiable by a schema-structure test, not a runtime check.
- **`to_dict()` does not strip `None`**: `config/core.py:785` emits `"host_cli": null` when unset; `AdvisorConfig`'s `host: str | None` / `min_tier: str | None` fields round-trip as `null` in the `"advisor"` entry, matching existing convention.
- **`ll.local.md` merge is raw-dict level only**: `deep_merge()` (`config/core.py:57-84`) merges `.ll/ll.local.md` into the session-context payload dict at `hooks/session_start.py:146`; `BRConfig._load_config` (`config/core.py:229-240`) reads only the JSON config file. A `BRConfig(...).advisor` property reflects `ll-config.json` only — the advisor ll.local.md-merge test must exercise `deep_merge()` on the raw dict, not through `BRConfig`.
- **Consumer idiom**: existing blocks are read as `BRConfig(project_root).<block>` (`cli/loop/run.py:231`, `cli/loop/lifecycle.py:570`, `cli/loop/config_cmds.py:23`); FEAT-3044's advisor core will consume `advisor` the same way.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- Line-number reconfirmation (2026-08-08 pass): `config-schema.json`'s `orchestration.host_cli` enum block is now at `1568-1576` with the enum literal on line `1574` (property `1572-1576`) — drifted ~14-16 lines from this issue's earlier `~1558-1562`/`~1560` citations. The enum values themselves (`claude-code | codex | opencode | pi | gemini | omp | kimi-code`) and the no-`$ref`/no-`$defs` duplication requirement are unchanged.
- `scripts/tests/test_config.py`'s `TestOrchestrationConfig` and `TestBRConfigOrchestration` are now at lines `3406` and `3476` respectively (2-line drift from this issue's `~3404`/`~3474`) — same classes, same shape, still the correct mirror target.
- `config/__init__.py` import block (`79-84`) and `__all__` start (`86`) confirmed exact, no drift.
- `deep_merge()` (`core.py:57-84`) and its call site in `scripts/little_loops/hooks/session_start.py:145-146` (`if local_overrides:` / `merged_config = deep_merge(base_config, local_overrides)`) confirmed exact, no drift.

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
- `docs/reference/CONFIGURATION.md#orchestration` — added by `/ll:wire-issue`;
  template section for the new `advisor` documentation entry.

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-08T17:29:07 - `29634343-1b19-4d6c-b892-3e3ca13fa784.jsonl`
- `/ll:ready-issue` - 2026-08-08T17:01:19 - `169fb2ff-80d7-4804-865c-40c4291be5b2.jsonl`
- `/ll:confidence-check` - 2026-08-08T16:59:32 - `8487debd-faf6-4d2b-b9d0-bec7dc70a916.jsonl`
- `/ll:verify-issues` - 2026-08-08T16:58:21 - `4b277a3f-dabe-4120-b22e-1248adff0a27.jsonl`
- `/ll:wire-issue` - 2026-08-08T16:56:37 - `251f0f4e-eeaa-4340-a52a-5cd7f33e8a09.jsonl`
- `/ll:refine-issue` - 2026-08-08T16:51:24 - `14b8df4c-540f-4560-8f0d-3e4289c985a3.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:21:35 - `eb104739-3a43-4761-b465-271da6b9bac2.jsonl`
- `/ll:issue-size-review` - 2026-08-04T20:47:20 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`
