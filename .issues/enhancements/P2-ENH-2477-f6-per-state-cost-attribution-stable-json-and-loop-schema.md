---
id: ENH-2477
title: "F6 (finishes) — Per-state cost attribution: stable JSON + per-state ceilings"
type: ENH
priority: P2
status: open
captured_at: "2026-07-04T20:05:34Z"
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to: [FEAT-2476, FEAT-2478]
labels:
  - token-cost
  - cli
  - json-schema
  - fsm
  - tier-1
---

# ENH-2477: F6 (finishes) — Per-state cost attribution

## Summary

Finish the per-state cost table already partially built at
`scripts/little_loops/cli/loop/_helpers.py:1665–1690`: stabilize its JSON
schema, surface `cache_read` / `cache_creation` broken out (already in
the underlying `usage` aggregate), add a stable JSON output path for
downstream consumers, and add `cost_ceiling_per_state` /
`cost_warn_at` per-state keys to the loop YAML schema. This is
EPIC-2456 § Children [TBD-5].

## Motivation

EPIC-2456 Goal #2 names per-state spend as a first-class output, and
ENH-1797 (Cost / token telemetry per FSM state in loop runs) already
shipped the row layout. What's missing is (a) a **stable JSON schema**
that downstream consumers can parse without scraping the CLI table, and
(b) **per-state ceilings** that compose with FEAT-2476's `--max-cost`
ceiling. The loop YAML currently has no cost-shape field; downstream
tests that lock the JSON shape don't exist yet, so a v2 print rewrite
would silently break consumers.

## Current Behavior

- `scripts/little_loops/cli/loop/_helpers.py:1665–1690` prints a per-
  state cost table by reading `UsageEvent` rows from `history.db`.
- `scripts/little_loops/fsm/executor.py:1295–1305` already aggregates
  `cache_read_tokens` / `cache_creation_tokens` per state.
- The CLI prints a textual table; no stable JSON shape exists; no
  `cost_ceiling_per_state` field in the loop YAML schema.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Anchor `_helpers.py:1665–1690` is the middle of the function, not its span.** The actual function is `_print_usage_summary(usage_path: Path) -> None` at `_helpers.py:1652–1714`; the body at `1666–1700` is the per-state `defaultdict` aggregation, and `1705–1714` is the printed table. The caller is `run_foreground()` at `_helpers.py:1608–1614` (try/except-wrapped, non-fatal).
- **Anchor `executor.py:1295–1305` is the `_resolve_next_state()` interceptor — it does NOT aggregate tokens.** The actual per-action token aggregation is at `executor.py:1382–1392` in `FSMExecutor._run_action()`: sums `result.usage_events` (a `list[TokenUsage]` from `subprocess_utils.TokenUsage` at `subprocess_utils.py:44–52`) into `total_input/output/cache_read/cache_creation`, stamps onto the `action_complete` payload, and `_emit()`s. Per-STATE aggregation is reconstructed downstream by `PersistentExecutor._handle_event()` at `persistence.py:637–655`.
- **The data source is `usage.jsonl` (run-local), NOT `.ll/history.db`.** `.ll/history.db` has no `usage_event` table today — the `usage_event` table is proposed in sibling ENH-2461 (P3) as a `_MIGRATIONS` entry appended to `session_store.py:_MIGRATIONS` (currently at v18 / ENH-2459 `test_run_events`). The current concrete data source is `<run_dir>/usage.jsonl` (one row per `action_complete`, keyed by `self._executor.current_state` at write time).
- **Table columns printed today**: `state`, `invoc`, `input`, `output`, `cache` (cache_read + cache_creation merged into one column), `est_cost` (formatted `$X.XXXX`, falls back to `n/a` if any row uses an unknown model). Issue's expected JSON keys (`cache_read_tokens`, `cache_creation_tokens` separately; `wallclock_ms`) go beyond what the existing column block prints.
- **Existing test coverage**: `scripts/tests/test_usage_reporter.py` (`TestPrintUsageSummary`) already exercises 8 scenarios against the data model — preserve those when refactoring the inline builder into `cost_graph.py`.
- **No `cost_attribution()` symbol exists in `scripts/little_loops/cli/ctx_stats.py`.** Closest precedent is `_aggregate_tool_events()` at `ctx_stats.py:118–166` (read-from-SQLite, group-by-toolname pattern). The F6 readout must be **added**, not extended.

## Expected Behavior

- `ll-loop run` emits a per-state cost summary as both (a) the existing
  human-readable table and (b) a stable JSON object — locked in tests
  so future rewrites don't silently break consumers.
- JSON keys exactly: `state`, `iterations`, `input_tokens`,
  `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`,
  `cost_usd`, `wallclock_ms`. Top-level `states: [...]` plus
  `totals: {...}`.
- Loop YAML schema gains `cost_ceiling_per_state: <float>` and
  `cost_warn_at: <float>` keys per state (composes with FEAT-2476's
  global ceiling).
- `ll-ctx-stats` can read the JSON output and surface per-state spend
  to humans.

## Proposed Solution

1. **`scripts/little_loops/fsm/cost_graph.py`** (new, ~50 LOC):
   - `PerStateCost.from_history(db_path)` — reconstructs per-state
     aggregates from `.ll/history.db` `usage_event` rows
   - `.to_dict()` — returns the stable JSON shape above
   - `.table()` — returns the existing human-readable column layout

2. **`scripts/little_loops/cli/loop/_helpers.py:1665–1690` extension**:
   - Replace the inline table builder with `PerStateCost.from_history`
   - Add `--cost-output-json <path>` flag for machine-readable output
   - JSON shape locked in `scripts/tests/test_cli_cost_table.py`

3. **`scripts/little_loops/fsm/schema.py`**: add
   `cost_ceiling_per_state` and `cost_warn_at` keys under each state
   block in the loop YAML schema. Validation rejects negative or
   non-numeric values.

4. **`scripts/little_loops/cli/ctx_stats.py`**: extend
   `cost_attribution()` query (already on the F5 roadmap) to break out
   per-state spend instead of just per-invocation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Mirror `scripts/little_loops/ab_writer.py` for the new `cost_graph.py` module.** That file already encodes the project's canonical "stable JSON dataclass" pattern: module-level `_AB_SCHEMA` (JSON Schema draft-07 with `additionalProperties: False`), `@dataclass ABResults` at `:131–153`, aggregation function at `:161–202`, pure serialization `ab_results_to_dict()` at `:210–230`, and I/O wrappers `write_ab_json()` / `read_ab_json()`. `PerStateCost` should follow the same shape (dataclass + `.from_usage_jsonl(path)` / `.from_history(db_path)` + `.to_dict()` + `.table()` + `write_cost_json(path)`).
- **Mirror `ThrottleConfig` for the new YAML fields.** `scripts/little_loops/fsm/schema.py:281–321` is the closest precedent for two new optional per-state numeric fields: `@dataclass` with `field_name: float | None = None`, `to_dict()` skips-None, `from_dict()` uses `data.get(...)`. Round-trip tests already follow this template at `scripts/tests/test_fsm_schema.py:2694–2742` (`TestThrottleConfig`).
- **Mirror the throttle validator** at `validation.py:876–911` for negative-number/type rejection of `cost_ceiling_per_state` / `cost_warn_at`. Wire into the per-state loop in `validate_fsm` at `validation.py:1038–1060`. Test analog: `TestThrottleValidation` at `scripts/tests/test_fsm_validation.py:623–671`.
- **JSON lock-in test pattern**: mirror `test_cli_ctx_stats.py:test_json_mode` (`:234–252`) — `json.loads(...)` + dict-key assertions on the emitted payload. Prefer this over a full JSON-Schema dependency unless downstream consumers need `$ref`s; the codebase's own event schemas (`docs/reference/schemas/`) are generated by `ll-generate-schemas` (`generate_schemas.py:82–180`) and tested by `test_action_complete_schema` at `test_generate_schemas.py:151–169`.
- **`--cost-output-json <path>` flag definition**: register in the `run` subparser at `scripts/little_loops/cli/loop/__init__.py:131–303` (alongside `--max-iterations`, `--host-guard-budget-mb`, `--baseline-skill` — `argparse` `type=Path, default=None, metavar="PATH"`). Read in `cli/loop/run.py:cmd_run` around `:122–200`. **Critical**: also forward through `run_background` re-exec at `_helpers.py:1313–1379` (mirroring `max_iter` at `:1317–1319`), otherwise detached runs silently drop the flag.
- **`estimate_cost_usd()` already handles all four token types** (`pricing.py:58–78`) — reuse unchanged. The unknown-model fallback (`returns None`) is preserved per-state via a `has_unknown_model: bool` flag (already in the inline builder at `_helpers.py:1675, 1698`).
- **`from_history(db_path)` is spec, not current reality.** Use `from_usage_jsonl(path)` as the concrete constructor now; gate `from_history(db_path)` behind an `ENH-2461`-is-merged feature flag (e.g., `try: usage_events = ... except sqlite3.OperationalError: usage_events = []`) so the implementation is shippable before ENH-2461 lands.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/cost_graph.py` (new) — `PerStateCost`
- `scripts/little_loops/fsm/__init__.py:76` — re-export `PerStateCost` /
  `cost_graph` module alongside the existing `ab_writer` precedent
  (parity with `from little_loops.fsm import PerStateCost`)
- `scripts/little_loops/cli/loop/__init__.py:282–303` — register
  `--cost-output-json <path>` flag (mirror `--program-md` cluster:
  `type=Path, default=None, metavar="PATH"`)
- `scripts/little_loops/cli/loop/run.py:497–508` — read `cost_output_json`
  in `cmd_run()` and pass into `run_foreground()`
- `scripts/little_loops/cli/loop/_helpers.py:1313–1379` — forward
  `--cost-output-json` through the `run_background` re-exec block
  (mirroring the `max_iter` block at `:1317–1319`); BUG-1414-style
  silent-drop otherwise
- `scripts/little_loops/cli/loop/_helpers.py:1665–1690` — replace inline
- `scripts/little_loops/fsm/schema.py` — YAML schema additions
- `scripts/little_loops/cli/ctx_stats.py` — per-state readout
- `scripts/little_loops/fsm/executor.py:1295` — wire JSON emission

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/general-task.yaml`,
  `loops/deep-research.yaml` — opt into the new YAML fields
- `scripts/tests/test_cli_cost_table.py` (new) — JSON schema lock-in

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/pricing.py:58–78` — `estimate_cost_usd()`
  imported by `_helpers.py:24`; reused unchanged by `PerStateCost`
  (unknown-model fallback preserved per-state via `has_unknown_model`)
- `scripts/little_loops/fsm/types.py:74–83` — `ExecutionResult.usage_events:
  list[TokenUsage]` field type consumed at `executor.py:1382–1392`
- `scripts/little_loops/fsm/runners.py:180` — assigns `usage_events=
  collected_usage`; consumes the data `cost_graph.from_history()` reads
- `scripts/little_loops/ab_writer.py:131–273` — canonical stable-JSON
  dataclass pattern mirrored by `PerStateCost` (`ABResults` + `_AB_SCHEMA`
  + `ab_results_to_dict` + `write_ab_json`/`read_ab_json`)
- `scripts/little_loops/fsm/persistence.py:637–655` —
  `PersistentExecutor._handle_event()` writes per-state rows to
  `<run_dir>/usage.jsonl`; this is the concrete data source the
  `from_usage_jsonl()` constructor reads
- `scripts/little_loops/fsm/__init__.py:76` — re-exports `ab_writer`
  symbols; must add `PerStateCost` / `cost_graph` to keep the public
  import surface consistent
- `scripts/little_loops/cli/loop/_helpers.py:1608–1614` —
  `run_foreground()` caller of `_print_usage_summary()` (try/except,
  non-fatal); the refactor preserves this call site
- `scripts/little_loops/cli/loop/run.py:497–508` — `cmd_run()` calls
  `run_foreground()`; new `args.cost_output_json` is read here and
  threaded through
- `scripts/little_loops/cli/loop/_helpers.py:1313–1379` —
  `run_background()` re-exec cluster; must forward
  `--cost-output-json` like `max_iter` at `:1317–1319` or detached
  runs drop the flag silently (BUG-1414 precedent for `--worktree`)
- `scripts/little_loops/fsm/validation.py:1038–1060` — per-state
  validation loop in `validate_fsm()`; `_validate_state_cost_ceiling`
  wired alongside `_validate_state_routing` (throttle block at
  `:876–911` is the structural mirror)
- `scripts/little_loops/cli/ctx_stats.py:340–395` — `_print_json()`
  target for the new `per_state` payload; reads from a new
  `_aggregate_usage_events()` that mirrors `_aggregate_tool_events()`
  at `:118–166`

### Similar Patterns

- `scripts/little_loops/fsm/validation.py` already returns typed
  outcomes that compose with budget primitives — reuse the pattern
- The JSON layout mirrors the format produced by ENH-2461's
  `input_tokens` / `output_tokens` / `cache_read_input_tokens` /
  `cache_creation_input_tokens` columns — keep consistent

### Tests

- `scripts/tests/test_cli_cost_table.py` (new) — JSON schema lock;
  refactor-safe across `_helpers.py` rewrites
- `scripts/tests/test_fsm_cost_graph.py` (new) — `PerStateCost.from_history`
  on a fixture DB round-trips through `.to_dict()`

_Wiring pass added by `/ll:wire-issue`:_

**Tests likely to break or need extension (UPDATE):**
- `scripts/tests/test_usage_reporter.py:18–200` — `TestPrintUsageSummary`
  (8 scenarios against `_print_usage_summary`); column format at
  `_helpers.py:1706` (`state / invoc / input / output / cache / est_cost`)
  MUST be preserved byte-identical, or column-substring assertions
  at `:125–200` will fail. Refactor must keep `.table()` returning
  the same width/order. (Issue's "Breaking Change: No — existing CLI
  table output unchanged" claim is the only thing keeping these green.)
- `scripts/tests/test_cli_loop_background.py:138–484` — must add
  `test_forwards_cost_output_json` mirroring `test_forwards_baseline_skill`
  at `:913–936` (the Path-flag forwarding precedent). Without this
  test, a future `_helpers.py:1313–1379` edit can silently drop the
  flag from detached runs.

**New tests to write (gaps not yet in the issue):**
- `TestCostCeilingPerStateConfig` class in `scripts/tests/test_fsm_schema.py`
  (mirror `TestThrottleConfig` at `:2694–2771`): 8 methods covering
  from_dict all/partial/empty, to_dict omits-None, round-trip,
  StateConfig.embed, defaults-none, StateConfig round-trip with both
  fields. Imports updated at `:31` to include the new fields.
- `TestCostCeilingPerStateValidation` class in `scripts/tests/test_fsm_validation.py`
  (mirror `TestThrottleValidation` at `:623–671`): positive-value
  acceptance, negative-value rejection (`< 0` ⇒ error), non-numeric
  rejection, partial-set acceptance (one of two fields set is OK),
  validator wiring smoke-test.
- `test_forwards_cost_output_json` in `test_cli_loop_background.py`
  (see above).
- CLI argparse registration test verifying `--cost-output-json
  /tmp/x.json` parses to `args.cost_output_json == Path("/tmp/x.json")`
  in the `run` subparser — follow the existing `test_cli_args.py`
  pattern for the `--program-md` flag.
- `test_cost_attribution_per_state` in `test_cli_ctx_stats.py` (mirror
  `test_json_mode` at `:234–252`) — verifies `cost_attribution()` payload
  contains the new `per_state` block when usage events exist.
- (Optional but load-bearing) `test_action_complete_includes_cache_read_creation_tokens`
  in `test_fsm_executor.py` — currently zero direct unit coverage of
  `FSMExecutor._run_action()` token aggregation at
  `executor.py:1382–1392`. Without this, the upstream source
  `PerStateCost.from_usage_jsonl()` reads is unprotected by a
  unit test.

**Existing tests that should remain unchanged (safe):**
- `scripts/tests/test_usage_journal.py` — end-to-end `<run_dir>/usage.jsonl`
  creation; upstream of `_print_usage_summary` and unaffected.
- `scripts/tests/test_subprocess_utils.py` — `TokenUsage` parsing.
- `scripts/tests/test_pricing.py` — `estimate_cost_usd()` model coverage.
- `scripts/tests/test_generate_schemas.py:151–169` — locks the
  `action_complete` schema (already includes `cache_read_tokens` /
  `cache_creation_tokens` since ENH-1797); unchanged by F6.
- `scripts/tests/test_ab_writer.py` — `ABResults` stable-JSON round-trip
  precedent; mirrors the new `PerStateCost` shape.

### Documentation

- `docs/reference/API.md` — `fsm/cost_graph.py` + JSON schema doc
- `docs/ARCHITECTURE.md` — Token cost layer section (EPIC-2456 passes)
- `.ll/ll-config.json` — note the new YAML fields

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:526–547` — `ll-loop run` flag table; add
  `--cost-output-json <path>` row alongside `--max-iterations` /
  `--host-guard-budget-mb` / `--baseline` / `--baseline-skill` /
  `--cross-host`
- `docs/reference/CLI.md:565–593` — `ll-loop run` per-state cost
  table block; update column note if `cache` column is broken out
  into `cache_read` + `cache_creation` separately, and mention the
  new `--cost-output-json` flag
- `docs/reference/CLI.md:774` — `--max-iterations` row in
  `ll-loop simulate` flag table (the new flag is `run`-only, but
  preserve the cross-reference)
- `docs/reference/loops.md:111` — `usage.jsonl` row schema; keep
  field names (`{iteration, state, action_type, input_tokens,
  output_tokens, cache_read_tokens, cache_creation_tokens, model,
  timestamp}`) in lockstep with the new reader; add a section
  describing `cost_ceiling_per_state` / `cost_warn_at` per-state
  YAML fields
- `docs/reference/CONFIGURATION.md:842–852` — per-state config table;
  add a `cost_ceiling` block mirroring the `throttle` entry
- `docs/reference/HOST_COMPATIBILITY.md:132` — claim "no
  `usage.jsonl` file and no per-state cost table in `ll-loop run`
  output" for non-Claude hosts; update to reflect the new
  `--cost-output-json` flag and per-state cost shape
- `docs/reference/API.md:4500–4545` — `StateConfig` dataclass fields;
  extend with `cost_ceiling_per_state: float | None = None` and
  `cost_warn_at: float | None = None` (add to the field table and
  the `to_dict()` / `from_dict()` narrative around `:4506–4545`)
- `docs/reference/API.md:4547–4566` — `ThrottleConfig` reference
  section; serves as the structural template for the new cost-ceiling
  fields. Reference both side-by-side.

### Configuration

- None added at the `ll-config` level; cost fields live in loop YAML
  (matches `model:` field convention)

## Implementation Steps

1. Add `cost_ceiling_per_state` / `cost_warn_at` to `fsm/schema.py`
2. Author `fsm/cost_graph.py` with `PerStateCost`
3. Replace the inline table builder at `_helpers.py:1665–1690` with
   `PerStateCost.from_history(...).table()`
4. Add `--cost-output-json <path>` flag to `ll-loop run`
5. Extend `cli/ctx_stats.py` to read per-state cost
6. Lock JSON schema in `scripts/tests/test_cli_cost_table.py`
7. Update loops (`general-task.yaml`, `deep-research.yaml`) to declare
   per-state ceilings for the most expensive states
8. Verify `python -m pytest scripts/tests/` exits 0

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation alongside steps 1–8 above:_

9. **Re-export `PerStateCost` from `scripts/little_loops/fsm/__init__.py:76`**
   alongside the existing `ab_writer` re-export — both
   `from little_loops.fsm import PerStateCost` and a `__all__` entry
   are expected (parity with `ABResults`).
10. **Register `--cost-output-json <path>` in `cli/loop/__init__.py:282–303`**
    using the existing `--program-md` precedent (`type=Path,
    default=None, metavar="PATH"`); insert between `--cross-host`
    at `:299–303` and the `# Validate subcommand` comment at `:305`.
11. **Read `args.cost_output_json` in `cli/loop/run.py:cmd_run()` around
    `:497–508`** and thread it into the `run_foreground()` call site.
12. **Forward `--cost-output-json` through `run_background` re-exec at
    `cli/loop/_helpers.py:1313–1379`** (mirroring `max_iter` at
    `:1317–1319`). Without this, detached runs silently drop the
    flag (BUG-1414 precedent).
13. **Add `test_forwards_cost_output_json` to
    `scripts/tests/test_cli_loop_background.py`** mirroring
    `test_forwards_baseline_skill:913–936` to lock the forwarding
    contract.
14. **Add `TestCostCeilingPerStateConfig` class to
    `scripts/tests/test_fsm_schema.py`** mirroring `TestThrottleConfig`
    at `:2694–2771` (8 methods: from_dict all/partial/empty,
    to_dict omits-None, round-trip, StateConfig.embed,
    defaults-none, StateConfig round-trip with both fields). Update
    imports at `:31` to include the new fields.
15. **Add `TestCostCeilingPerStateValidation` class to
    `scripts/tests/test_fsm_validation.py`** mirroring
    `TestThrottleValidation` at `:623–671` (negative-value rejection,
    non-numeric rejection, partial-set acceptance, validator wiring
    smoke-test).
16. **Add CLI argparse registration test** verifying
    `--cost-output-json /tmp/x.json` parses to
    `args.cost_output_json == Path("/tmp/x.json")` in the `run`
    subparser.
17. **Add `test_cost_attribution_per_state` to `test_cli_ctx_stats.py`**
    mirroring `test_json_mode` at `:234–252` to verify the
    `_aggregate_usage_events()` payload appears in JSON output.
18. **Update `docs/reference/CLI.md:526–547`** with the new flag row
    and `docs/reference/CLI.md:565–593` for the per-state cost table
    column note.
19. **Update `docs/reference/CONFIGURATION.md:842–852`** with a
    `cost_ceiling` per-state config block mirroring the `throttle`
    entry.
20. **Update `docs/reference/loops.md:111`** — keep `usage.jsonl`
    field names in lockstep and add a section for the new YAML
    fields.
21. **Update `docs/reference/HOST_COMPATIBILITY.md:132`** — the
    non-Claude-host claim about missing `usage.jsonl` / per-state
    cost table needs updating for the new flag.
22. **Update `docs/reference/API.md:4500–4566`** — extend `StateConfig`
    field table and reference `ThrottleConfig` section as the
    structural template.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 precision**: `StateConfig` lives at `scripts/little_loops/fsm/schema.py:380–639` (declaration at `:380`, `to_dict()` at `:480–557`, `from_dict()` at `:559–639`). Add `cost_ceiling_per_state: float | None = None` and `cost_warn_at: float | None = None` after the existing `max_retries: int | None = None` field at `:457` (closest analog). Validate non-negative floats in a new `_validate_state_cost_ceiling(...)` block wired into `validate_fsm` at `validation.py:1038–1060` (alongside `_validate_state_routing`).
- **Step 2 precision**: New file `scripts/little_loops/fsm/cost_graph.py` (~50–80 LOC). Reads JSONL at construction time (parallels `_print_usage_summary` at `helpers.py:1666–1700`), aggregates per-state, exposes `.to_dict()` returning the exact shape `{"states": [...], "totals": {...}}`, and `.table() -> str` for the existing human-readable columns. Mirror `ab_writer.py` structure (dataclass + pure serializer + I/O wrappers).
- **Step 3 precision**: Replace at `_helpers.py:1652–1714` (the full `_print_usage_summary` function). Preserve `print()` block as `.table()`; call site stays at `_helpers.py:1608–1614`. Add the optional JSON write inside the same try/except so a write failure stays non-fatal.
- **Step 4 precision**: Register at `cli/loop/__init__.py` in the `--baseline`/`--items`/`--max-iterations` cluster (lines `131–303`). **Also forward in `run_background` re-exec** at `_helpers.py:1313–1379` (mirroring `max_iter = getattr(args, "max_iterations", None); if max_iter: cmd.extend([...])`), otherwise the flag is silently dropped for detached-process runs.
- **Step 5 precision**: Add `_aggregate_usage_events(db_path) -> dict | None` to `cli/ctx_stats.py` (mirror `_aggregate_tool_events` at `:118–166` for the SQL/group-by shape), then call it from the JSON payload assembly at `ctx_stats.py:340–395` (around `_print_json`). Until ENH-2461 (P3) lands the `usage_events` SQLite table, this can fall back to reading the latest `<run_dir>/usage.jsonl` — design `PerStateCost.from_history` to accept either source via a feature flag.
- **Step 6 precision**: New test file `scripts/tests/test_cli_cost_table.py`. Mirror `TestJsonMode` at `test_cli_ctx_stats.py:234–252` for the JSON emission test; mirror `TestThrottleConfig` at `test_fsm_schema.py:2694–2742` for the dataclass round-trip; mirror `TestThrottleValidation` at `test_fsm_validation.py:623–671` for the new validator (negative-value rejection).
- **Step 7 precision**: Both `loops/general-task.yaml` and `loops/deep-research.yaml` are valid candidates; check which states actually invoke LLMs (prompt / slash_command / mcp action kinds) before setting ceilings — silent default-on would generate spurious warnings for shell-only states.
- **Step 8 precision**: Also run `python -m mypy scripts/little_loops/` per `commands.check_code` defaults.

## Acceptance Criteria

- `ll-loop run --cost-output-json /tmp/per-state.json` emits JSON whose
  schema is locked by `scripts/tests/test_cli_cost_table.py`
- JSON breaks out `cache_read_tokens` / `cache_creation_tokens` and
  matches `usage_event` totals at run finish
- Loop YAML accepts `cost_ceiling_per_state` / `cost_warn_at` per state;
  validation rejects negative values
- Schema-version bump (if shape changes) is reflected in tests
- `python -m pytest scripts/tests/` exits 0

## Scope Boundaries

- **In**: Stable JSON shape; per-state YAML schema; CLI output flag;
  context-stats readout
- **Out**: OTel `gen_ai.usage.*` emission (F5 child owns that); cost
  ceiling guard (FEAT-2476 owns that); routing cascade (F7-lite)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent; § Tier 1 [TBD-5], Goal #2 |
| `scripts/little_loops/cli/loop/_helpers.py:1665–1690` | Where the new builder plugs in |
| `FEAT-2476` | Sibling: composes per-state ceilings with the global `--max-cost` flag |
| `ENH-2461` | Persistence layer for the underlying `input_tokens` etc. |

## Impact

- **Priority**: P2 — finishes in-flight work; no new primitives, just
  stabilization
- **Effort**: Small — ~40–80 LOC across cost_graph + CLI flag + tests
- **Risk**: Low — additive JSON output; human-readable table preserved
- **Breaking Change**: No — existing CLI table output unchanged; new
  JSON is opt-in via flag

## Status

**Open** | Created: 2026-07-04 | Priority: P2

## Session Log
- `/ll:wire-issue` - 2026-07-05T04:06:04 - `24e80095-e5ab-460d-a045-d84cf2220c68.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:11:30 - `6412d46f-caf7-49a3-86b3-b6f00ea65f1f.jsonl`

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
