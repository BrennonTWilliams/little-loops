---
id: ENH-2475
title: "F5.1 \u2014 Existing-event audit (DES adoption prerequisite)"
type: ENH
priority: P2
status: done
captured_at: '2026-07-04T20:05:34Z'
completed_at: 2026-07-07 04:27:22+00:00
discovered_date: 2026-07-04
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- FEAT-2470
- FEAT-2476
- FEAT-2478
blocks:
- FEAT-2478
decision_needed: false
labels:
- token-cost
- observability
- des
- history-db
- tier-1
confidence_score: 100
outcome_confidence: 88
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 25
---

# ENH-2475: F5.1 — Existing-event audit (DES adoption prerequisite)

## Summary

Enumerate every event currently written to `.ll/history.db`, classify each
into a DES (discriminated-union) variant, and port non-conforming shapes
into new variants so that F5 (`gen_ai.usage.*` emission under a canonical
schema) can land without coercing unmodeled shapes.

This is EPIC-2456 § Children [TBD-3] — the gate that precedes F5's DES
adoption. Per EPIC-2456 § Success Metrics, F5's gate is "DES schema accepts
100% of currently-emitted events"; that gate cannot be measured without
this audit finishing first.

## Motivation

EPIC-2456 already lists a canonical DES schema for `gen_ai.usage.*` emission
(F5), but F5's emit path is non-trivial: it requires every existing
event-emission site to map cleanly to a known variant. Until we audit
what's currently emitted, F5 risks either silently dropping events or
growing an ad-hoc shape registry that defeats the point of a canonical
schema.

This issue pays down that prerequisite debt in one short pass so F5
(`observability/tracing.py`) can ship with a static-known surface instead
of a runtime shape-coercion layer.

## Current Behavior

Today, every site that writes to `.ll/history.db` chooses its own event
shape. There is no central registry of event variants. F5's emit path will
either (a) refuse to emit when an event doesn't match a known variant, or
(b) grow a runtime adapter that handles each non-conforming shape — both
are bad outcomes for cost attribution.

## Expected Behavior

A new `scripts/little_loops/observability/schema.py` (~30 LOC) holding the
DES variant definitions, plus a one-shot audit script that walks every
current event-emission site, classifies the shape it emits against the DES
registry, and lists the ones whose shape doesn't match a known variant
(MUST be empty before F5 ships).

After this lands, every event emit path uses one of the registered
variants — or registers a new one before adopting F5.

## Proposed Solution

1. **Inventory**: grep `scripts/little_loops/**` for `history.db` writers
   (`SQLiteTransport`, `subprocess_utils.UsageEvent`, etc.) and any direct
   `INSERT`/`REPLACE` into the event tables.
2. **DES registry**: `observability/schema.py` defines each variant as a
   `TypedDict` keyed by `type` (discriminator) — the canonical shape is
   the OTel `gen_ai.usage.*` attribute set used in F5, plus the existing
   `tool_events` / `loop_runs` / `fsm_state` / `session_*` event shapes.
3. **Audit script**: a testable CLI (`observability/audit.py`) that walks
   every emit site via static analysis (call-graph or import-graph), runs
   each branch against the schema, and exits non-zero if any shape is
   unmatched.
4. **Port report**: a `docs/observability/des-audit.md` listing every
   registered variant and the emit sites that satisfy it (auto-generated
   output, not hand-written).

## Integration Map

### Files to Modify

- `scripts/little_loops/observability/schema.py` (new) — DES variant registry
- `scripts/little_loops/observability/audit.py` (new) — one-shot audit script
- `docs/observability/des-audit.md` (new) — auto-generated port report

#### Additional Files to Modify (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/observability/__init__.py` (new) — package init for the new `observability` subpackage (parallel to `scripts/little_loops/events.py`); re-exports `DES_VARIANTS`, `AuditResult`, `audit_tree` so `little_loops.observability.schema` / `.audit` are importable via the package surface.
- `scripts/little_loops/cli/verify_des_audit.py` (new) — CLI wrapper exposing `main_verify_des_audit() -> int`; modeled on `cli/verify_design_tokens.py:197–267`.
- `scripts/little_loops/cli/__init__.py:81–83` — add `from little_loops.cli.verify_des_audit import main_verify_des_audit` between the existing `verify_design_tokens` / `verify_package_data` imports.
- `scripts/little_loops/cli/__init__.py:118–123` — **also add `"main_verify_des_audit"` to the `__all__` block** (the issue body cited lines 81–83 only; the existing `__all__` enumerates every `main_verify_*` symbol and the new entry must be appended there too).
- `scripts/pyproject.toml:51–91` — register `ll-verify-des-audit = "little_loops.cli:main_verify_des_audit"` under `[project.scripts]`.
- `commands/help.md:280–284` — add one-line `ll-verify-des-audit` entry to the CLI TOOLS block (per `CONTRIBUTING.md` § "Documentation wiring for new CLI tools" lines 354–368).
- `scripts/tests/test_wiring_cli_registry.py` lines 20–104 — add a new `DOC_STRINGS_PRESENT` triple-entry for `ll-verify-des-audit` (precedent: the existing `ll-verify-design-tokens` triple at lines 70–72 requires the name to appear in `commands/help.md`, `docs/reference/CLI.md`, **and** `.claude/CLAUDE.md`; the new tool will fail this guard unless the entry is added).
- `skills/configure/areas.md:832` — add `ll-verify-des-audit` to the comma-separated name list under "All ll- commands (Recommended)"; bump the count `30 → 31` in the description text.
- `README.md:46` — bump `**37 typed CLI tools**` count to `**38**`.
- `README.md:78` — bump `**37 CLI tools**` count to `**38**`. (Per `CONTRIBUTING.md:366`, do **NOT** add a `### ll-verify-des-audit` section to `README.md`; the structural guard in `scripts/tests/test_readme_structure.py` will fail CI.)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/sqlite_transport.py` — write path that this audit walks
- `scripts/little_loops/subprocess_utils.py:50–51, 462–465` — `UsageEvent` write site
- `scripts/little_loops/fsm/executor.py:1295–1305` — per-state cache-aggregator write
- Future F5 emit path (`observability/tracing.py`, not yet filed) consumes the registry

#### Codebase Research Findings (verified anchors + stale-ref corrections)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

**Stale-reference corrections** (verified by `ll:codebase-locator`):
- `scripts/little_loops/sqlite_transport.py` **does not exist** — `class SQLiteTransport` lives at `scripts/little_loops/session_store.py:1311` (constructor + `send()` at line 1341).
- `subprocess_utils.py:50–51, 462–465` — `TokenUsage` dataclass is at `scripts/little_loops/subprocess_utils.py:44–52`; the stream-json parse site is at `subprocess_utils.py:449–485` (`etype == "result"` branch with `on_usage_detailed` callback).
- `fsm/executor.py:1295–1305` — those line numbers currently sit in the FSM interceptor hook. The per-state cache-aggregator (the F5 partial that folds `result.usage_events[*]` into the `action_complete` payload) lives at `scripts/little_loops/fsm/executor.py:1381–1393` (function `FSMExecutor._run_action`).

**All `.ll/history.db` write sites the audit must walk** (Channel A — direct typed writers):

| Helper | Anchor | Table |
| --- | --- | --- |
| `write_file_event` | `scripts/little_loops/session_store.py:721–752` | `file_events` |
| `record_correction` | `scripts/little_loops/session_store.py:755–785` | `user_corrections` |
| `record_skill_event` | `scripts/little_loops/session_store.py:788–813` | `skill_events` |
| `record_issue_snapshot` | `scripts/little_loops/session_store.py:816–866` | `issue_snapshots` |
| `cli_event_context` | `scripts/little_loops/session_store.py:869–908` | `cli_events` |
| `skill_event_context` | `scripts/little_loops/session_store.py:925–1000` | `skill_events` (completion cols) |
| `record_commit_event` | `scripts/little_loops/session_store.py:1041–1091` | `commit_events` |
| `record_test_run_event` | `scripts/little_loops/session_store.py:1171–1233` | `test_run_events` |
| `record_retirement` | `scripts/little_loops/session_store.py:2735–2756` | `correction_retirements` |

**Channel B — EventBus emit sites** feeding `SQLiteTransport.send()` (`session_store.py:1341–1422`; classifier `frozenset _LOOP_EVENT_TYPES` at `session_store.py:133–145`; `event_type.startswith("issue.")` branch at `session_store.py:1377`):

- FSM executor primary emitter `fsm/executor.py:_emit()` — 26 distinct event types spread across `fsm/executor.py:336, 519–526, 539–546, 632–638, 644–653, 884–887, 910–943, 1019–1047, 1179–1188, 1329, 1332, 1393, 1404–1411, 1430–1433, 1710–1718, 1789–1797, 1820, 2038–2048, 2081–2121, 2187–2236, 2248, 2259–2267, 2292–2299`.
- `fsm/persistence.py:703, 867` — `event_bus.emit(event)` for re-emit + `loop_resume`.
- `issue_lifecycle.py:576–586, 674–684, 748–757, 841–850, 934–944, 993–1003` — six `issue.*` lifecycle emits (`failure_captured`, `closed`, `completed`, `deferred`, `skipped`, `started`).
- `state.py:104–107` (`StateManager._emit`) — `state.*` events at lines 201, 212–214.
- `parallel/orchestrator.py:1078–1087` — `parallel.worker_completed`.

**Direct INSERT outside `session_store.py`** (audit must walk these too):
- `hooks/post_tool_use.py:159–180` — `INSERT INTO tool_events` (cache_hit/bytes_in/bytes_out).
- `hooks/user_prompt_submit.py:84–86` — calls `record_correction`.
- `hooks/post_commit.py:97` — `record_head_commit` → `record_commit_event`.
- `cli/issues/set_status.py:60–66` — direct `record_issue_snapshot` (bypasses EventBus).
- `pytest_history_plugin.py:126` — pytest11 entry → `record_test_run_event`.

**Channel C — F5 token side-channel**:
- `scripts/little_loops/fsm/types.py:74–83` — `usage_events: list[TokenUsage]` on `ActionResult`.
- `scripts/little_loops/fsm/executor.py:1382–1393` — aggregation into `action_complete`.
- `scripts/little_loops/fsm/persistence.py:639–655` — `usage.jsonl` journal entry.

#### Additional Dependent Files (Callers/Importers) added by `/ll:wire-issue`

_Wiring pass added by `/ll:wire-issue`:_

**Channel A — additional direct DB / read-side paths** (the audit walker must enumerate these because they share the same `connect()`/`resolve_history_db()` surface):

- `scripts/little_loops/history_reader.py` — typed read-only query API for `.ll/history.db` (entire module); 19 functions take `db: Path | str = DEFAULT_DB_PATH`. The audit's read-side companion; flagged as a "future enhancement" but the walker still has to know about the table set it queries.
- `scripts/little_loops/issue_history/parsing.py:363,368` — `from little_loops.session_store import connect` + `conn = connect(db_path)` (writes through the same helper layer).
- `scripts/little_loops/issue_history/analysis.py:41,142` — imports `DEFAULT_DB_PATH` and resolves `_resolved_db = db_path if db_path is not None else Path(DEFAULT_DB_PATH)`.
- `scripts/little_loops/user_messages.py:817,835–868` — `from little_loops.session_store import resolve_history_db` + `db_path = resolve_history_db(project_folder / ".ll" / "history.db")` (read-only path resolution).
- `scripts/little_loops/decisions.py:398` — `db_path = project_root / ".ll" / "history.db"` (decisions log reads history.db via `scan_completed_issues_from_db`).
- `scripts/little_loops/issue_history/evolution.py:30–45` — direct `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` (read-only; not a writer, but reads the same tables the audit classifies).

**Channel B — additional EventBus wiring** (the same `SQLiteTransport` instance receives every FSM emit during an `ll-auto` run; the audit's emit-type enumeration must cover them):

- `scripts/little_loops/issue_manager.py:44,1160–1161` — `AutoManager.__init__` wires `self.event_bus = EventBus()` then `self.event_bus.add_transport(SQLiteTransport(db_path or DEFAULT_DB_PATH))`. Hard-wired counterpart of the configurable wiring.
- `scripts/little_loops/transport.py:652–655` — `wire_transports(...)` adds `bus.add_transport(SQLiteTransport(base / "history.db"))` when `events.transports: ["sqlite"]` is configured. Configurable counterpart of issue_manager's hard-wired wiring.
- `scripts/little_loops/__init__.py:44,96–97` — re-exports `SQLiteTransport` + `record_issue_snapshot` at top-level package surface (relevant for any module that imports `from little_loops import SQLiteTransport`).

**Channel C — additional `cli_event_context` callers** (each opens/writes to history.db on every CLI invocation; each `cli/*.py` invocation must be classified by the audit):

- `scripts/little_loops/cli/auto.py:22,33`
- `scripts/little_loops/cli/parallel.py:32,44`
- `scripts/little_loops/init/cli.py:14,580`
- `scripts/little_loops/cli/issues/__init__.py:9,20`
- `scripts/little_loops/cli/sprint/__init__.py:26,56`
- `scripts/little_loops/cli/loop/__init__.py:11,24`
- `scripts/little_loops/cli/verify_triggers.py:20,583`
- `scripts/little_loops/cli/verify_design_tokens.py:32,206`
- `scripts/little_loops/cli/verify_package_data.py:26,241`

(All 25+ remaining `cli/*.py` files use the same `with cli_event_context(DEFAULT_DB_PATH, "<binary>", sys.argv[1:])` wrapper; see the canonical call sites.)

**Same-name cousins (audit must EXCLUDE)** — these share names with history.db writers but target a different store (the audit walker must skip them):

- `scripts/little_loops/state.py:227` — `StateManager.record_corrections()` writes to the on-disk state JSON file (`.ll/ll-state.json`), **NOT** to `history.db`. Reference note for the audit walker to skip.
- `scripts/little_loops/issue_manager.py:1442` — `self.state_manager.record_corrections(info.issue_id, result.corrections)` (consumes the state-file variant).

**Doc-comment references** (the audit's doc-comments pass should pick these up):

- `scripts/little_loops/hooks/adapters/codex/post-tool-use.sh:9` — header comment cites `.ll/history.db`.
- `scripts/little_loops/loops/sft-corpus.yaml:1,10,58` — header + Stage/Enrich sections cite history.db session-quality enrichment.
- `scripts/little_loops/loops/README.md:132` — `sft-corpus` description cites history.db.

### Similar Patterns

- `scripts/little_loops/fsm/schema.py` — already uses discriminator-style typing for loop YAML; reuse the pattern
- `scripts/little_loops/history_reader.py` — read-side can validate every row against the registry at load time (companion enhancement)

#### Codebase Research Findings (concrete precedents)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

**Discriminator-style typing pattern** (verbatim reuse target — `Literal[...]` field on a dataclass):

- `scripts/little_loops/fsm/schema.py:63–78` — `class EvaluateConfig.type: Literal[...]` enumerating 14 evaluator variants (`exit_code`, `output_numeric`, ..., `classify`). Closest 1:1 precedent for the new registry.
- `scripts/little_loops/fsm/schema.py:1004` — `FSMLoop.on_handoff: Literal["pause","spawn","terminate"]`.
- `scripts/little_loops/host_runner.py:113–135` — *frozen* dataclasses `CapabilityEntry` / `HookEntry` with `Literal["full","partial","unsupported"]` + `Literal["installed","registered","deferred","absent"]` discriminators. Per the file comment at `host_runner.py:101–104`, frozen dataclasses are the established value-object convention — adopt for the new registry.
- `scripts/little_loops/learning_tests/__init__.py:26–50` — `Assertion.result: Literal["pass","fail","untested"]` + `LearnTestRecord.status: Literal["proven","refuted","stale"]`.

**Convention summary from `ll:codebase-pattern-finder`**:
- `@dataclass` + `Literal[...]` discriminator is the *universal* project convention.
- **`TypedDict` is not used anywhere in `scripts/little_loops/`** (grep returned zero matches). The new registry should follow the dataclass+Literal convention rather than introduce `TypedDict` (which would be a first-time stylistic outlier).
- **Pydantic `BaseModel` is not used anywhere** (zero matches) — do not introduce as a dependency.
- **jsonschema runtime validation is intentionally avoided** (per `scripts/tests/test_config_schema.py:39–54`) — validation belongs in Python-side shape assertions, not as a runtime dep.

**Audit / lint CLI precedent** (the new `observability/audit.py` should model after this):
- `scripts/little_loops/cli/verify_design_tokens.py:197–267` — `main_verify_design_tokens()` with `cli_event_context` + `argparse` + dataclass result types (`ProfileResult`/`ThemeViolation`) + dual `--json` / text output + `return 1 if results else 0`. **Reuse this exact scaffolding**.
- `scripts/little_loops/cli/verify_package_data.py:99–143` — `pkg_root.rglob("*.py")` + regex scanner (the "syntactic lint" pattern). Reuse for `observability/audit.py`'s emit-site walker.

**Static-walk precedent** (`ll:codebase-analyzer` finding):
- **No AST walker exists in this codebase** — `import ast` has zero matches across `scripts/little_loops/`. The audit should follow the `learning_tests/import_scan.py:8–31` precedent (regex against `rglob`) and extend with `ast.literal_eval` *only* where regex fails to capture dict literals cleanly.
- Spread-construction call sites (`state.py:104–107` and `fsm/persistence.py:700–703` use `{"event": etype, "ts": ..., **payload}`) require AST extraction — not regex handleable.

**JSON Schema precedent for the auto-generated docs**:
- `scripts/little_loops/generate_schemas.py:548–572` (`generate_schemas()` + `if __name__ == "__main__"`) writes per-event JSON Schema files into `docs/reference/schemas/` (39 files today). Reuse this exact write-to-docs-dir shape — but for `.md` not `.json` (this will be the first auto-generated Markdown doc; no precedent exists, so establish the convention here with an HTML-comment sentinel header: `<!-- DO NOT EDIT — generated by ll-verify-des-audit -->`).

### Tests

- `scripts/tests/test_des_schema.py` (new) — every registered variant parses cleanly from a representative event payload
- `scripts/tests/test_des_audit.py` (new) — audit script exits non-zero on an unmodeled shape, zero on a clean tree
- Wired into `python -m pytest scripts/tests/` per project CI policy

#### Codebase Research Findings (test patterns to model after)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

**Catalog / registry completeness tests** (direct precedent for `test_des_schema.py::class TestSchemaDefinitions`):
- `scripts/tests/test_generate_schemas.py:14–63` — `class TestSchemaDefinitions`: `test_all_38_event_types_defined` (`assert len(SCHEMA_DEFINITIONS) == 38`) + `test_expected_event_types_present` (`assert set(SCHEMA_DEFINITIONS.keys()) == expected`). Clone this exact shape for the new variant catalog.
- `scripts/tests/test_generate_schemas.py:14` anchor — `class TestSchemaDefinitions`. Use `class Test*` naming to match `[tool.pytest.ini_options] python_classes = ["Test*"]` (`scripts/pyproject.toml:145`).

**Audit-CLI exit-code tests** (direct precedent for `test_des_audit.py::class TestMain`):
- `scripts/tests/test_verify_design_tokens.py:178–238` — `class TestMain` testing `main_verify_design_tokens()` exit codes via `patch("sys.argv", [...])` + `patch("builtins.print")`: `test_clean_profiles_dir_returns_zero`, `test_half_flipped_returns_one`, `test_json_output_is_parseable`. **Direct template**.

**Dataclass round-trip + spot-checks** (use for variant conformance assertions):
- `scripts/tests/test_events.py:19–89` — `class TestLLEvent` (creation, `to_dict`, `from_dict`, round-trip). Use for `test_des_schema.py::class TestVariantRoundtrip`.
- `scripts/tests/test_generate_schemas.py:66–180` — `class TestGenerateSchemas` (`test_all_schemas_have_required_json_schema_fields`, `test_all_schemas_require_event_and_ts` for wire-format fields, per-shape `test_<variant>_schema` method).

**Parametrize for table-driven coverage**:
- `@pytest.mark.parametrize` precedent for "every variant maps cleanly": `scripts/tests/test_fsm_evaluators.py:56–66` and `scripts/tests/test_cli_loop_dispatch.py:805`.

**Conftest hygiene for history.db tests** (must honor the existing isolation contract):
- `scripts/tests/conftest.py:447–498` — sets `LL_HISTORY_DB` env var and bails fast on tests touching the real `.ll/history.db`. The new tests must use `tmp_path` + the `LL_HISTORY_DB` redirection.
- Cross-references: `.issues/bugs/P2-BUG-1995-pytest-opens-real-history-db.md` documents the contract being defended.

**Event-shape test fixtures available for reuse** (without writing fixtures from scratch):
- `scripts/tests/test_history_reader.py:99–1489` — hand-written `INSERT` payloads for every table. Reuse as fixture data.
- `scripts/tests/test_session_store.py:1454–1503` (`TestRecordCorrection`, `TestWriteFileEvent`) and `:3550–3602` (`TestRecordTestRunEvent`) — round-trip tests for every direct writer.
- `scripts/tests/test_usage_journal.py:88–196` — `TokenUsage` round-trip; relevant for the F5 token-emission variant.

### Documentation

- `docs/observability/des-audit.md` — registered variants + emit-site map (auto-generated)
- `docs/reference/API.md` — document `observability/schema.py` registry API

#### Codebase Research Findings (existing docs precedents + API.md sections to update)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

**Where the new registry entry belongs in `docs/reference/API.md`** (existing sections to extend with cross-references):
- § `little_loops.history_reader` at `docs/reference/API.md:6436` — read-side (companion enhancement flagged in § Similar Patterns).
- § `little_loops.session_store` at `docs/reference/API.md:6881` — write-side; the new DES registry lists every `record_*` helper here.
- § `little_loops.events` at `docs/reference/API.md:~6420` — `EventBus` + `LLEvent`; cross-link to the new DES registry.
- § `little_loops.fsm.schema` at `docs/reference/API.md:4368` — the discriminator-style precedent the new module follows.

**Auto-generated docs precedent** (for `docs/observability/des-audit.md`):
- `scripts/little_loops/generate_schemas.py:548–572` — `generate_schemas()` writes 39 JSON Schema files into `docs/reference/schemas/`. Reuse the function-and-CLI-wrapper shape exactly.
- **No precedent for auto-generated Markdown** exists in the repo (grep for `DO NOT EDIT|AUTO-GENERATED|generated by` only found `docs/reference/CLI.md:2876`'s `# generated by ll-adapt` sentinel). Establish a new convention here — recommend `<!-- DO NOT EDIT — generated by ll-verify-des-audit -->` as the leading HTML comment in `docs/observability/des-audit.md`.

**Companion reference docs** (cross-link, don't duplicate):
- `docs/reference/EVENT-SCHEMA.md` — the 38-event reference; the new registry should supersede / consolidate this catalog. Add a top-line "DES registry lives at `scripts/little_loops/observability/schema.py`" pointer.
- `docs/guides/HISTORY_SESSION_GUIDE.md:41` — producer/consumer overview; cross-link to the audit's port report.
- `docs/ARCHITECTURE.md:661–686` — producer/consumer sequence diagram; add a "DES audit gate" callout to the producer/consumer arrow.
- `docs/development/TESTING.md` + `docs/development/TROUBLESHOOTING.md` — confirm the `python -m pytest scripts/tests/` gate (per `.claude/CLAUDE.md` "Testing & CI Policy") picks up the new audit exit code.

#### Additional Documentation wiring (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2448–2603` — **`### ll-verify-des-audit` subsection MUST be added** to the existing `ll-verify-*` section (the file enumerates each tool individually: `ll-verify-docs` lines 2448–2469, `ll-verify-skill-budget` 2473–2494, `ll-verify-skills` 2498–2519, `ll-verify-triggers` 2523–2544, `ll-verify-package-data` 2548–2575, `ll-verify-design-tokens` 2579–2603). The new entry should match the established format (description, flags table, exit codes, examples) and model after the `ll-verify-design-tokens` subsection (the closest precedent — newest, same static-lint shape).
- `docs/reference/API.md:3737–3745` — add a `### main_verify_des_audit` docstring block matching the existing `### main_verify_docs` pattern (the issue body only cites adding the registry API section; this CLI entrypoint block is in addition).
- `.claude/CLAUDE.md` (CLI Tools block in the project instructions) — add a one-line entry for `ll-verify-des-audit` so the `scripts/tests/test_wiring_cli_registry.py` triple-entry guard passes (see Files to Modify above).
- `CHANGELOG.md` `## [Unreleased]` / `### Planned` (lines 18–21) — optional `ENH-2475` Planned entry (matches existing entries for `ENH-2472` / `ENH-2473`; convention but not strictly required).
- `.ll/decisions.yaml` — optional ARCH-rule entry documenting the "new event variants must be registered in `observability/schema.py` before emission" invariant the audit enforces (the issue does not require this but the team may want it logged).

### Configuration

- N/A — no config schema changes; the schema is source-of-truth in code

#### Codebase Research Findings (configuration note)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

- `analytics.capture.*` config keys (`scripts/little_loops/config/features.py:765–771` for `EventsConfig`/`SqliteEventsConfig`; `analytics.capture.corrections` consulted at `session_store.py:768–773`) **suppress writes but do NOT change emit-site shapes** — the audit's static walk must source `scripts/little_loops/` regardless of `capture.*` value. The audit invariant is "every known shape has a registered variant," not "every shape is currently writable."
- `LL_HISTORY_DB` env var (`session_store.py:91–99`, `resolve_history_db()`) — orthogonal to this issue; the audit needs no DB connection at all (it walks source, not data).
- `RETENTIONConfig` (`config/features.py:903`, ENH-1906) — orthogonal; retention operates on rows already written, not on emit sites.

## Implementation Steps

1. Inventory emit sites with a grep walk; produce a draft variant list
2. Author `observability/schema.py` with the DES variant registry
3. Author `observability/audit.py` that walks emit sites statically and classifies each
4. Add `scripts/tests/test_des_schema.py` + `scripts/tests/test_des_audit.py`
5. Wire CI: `python -m pytest scripts/tests/ test_des_audit.py` must exit 0
6. Document in `docs/reference/API.md`
7. Hand off to F5 (`observability/tracing.py`) — gate ships when audit returns 100% match

### Codebase Research Findings (concrete file references + mechanism)

_Added by `/ll:refine-issue ENH-2475 --auto`:_

**Step 1 — Inventory** (which files to grep, in order of precedence):
1. Channel A direct writers — `scripts/little_loops/session_store.py` rows 721, 755, 788, 816, 869, 925, 1041, 1171, 2735.
2. Hook-handler direct writes — `scripts/little_loops/hooks/post_tool_use.py:158–180` (tool_events), `hooks/user_prompt_submit.py:84,92`, `hooks/post_commit.py:73`, `cli/issues/set_status.py:60–66`.
3. Channel B FSM emit — `scripts/little_loops/fsm/executor.py` (use `rg "_emit\(" fsm/executor.py` to find all ~43 call sites).
4. Issue lifecycle emit — `scripts/little_loops/issue_lifecycle.py:576–944` (six sites).
5. State manager — `scripts/little_loops/state.py:104–214`.
6. Parallel orchestrator — `scripts/little_loops/parallel/orchestrator.py:1078–1087`.
7. Pytest plugin — `scripts/little_loops/pytest_history_plugin.py:125–129`.

**Step 2 — DES registry** (pattern to copy):
- Use `@dataclass(frozen=True)` for value-typed variants (per `host_runner.py:101–104` convention).
- Discriminator field: `type: Literal["loop_start", ...]` exactly like `scripts/little_loops/fsm/schema.py:63–78`.
- Collect the union as a `Final[Tuple[Type, ...]]` (e.g., `DES_VARIANTS: Final[Tuple[type, ...]] = (LoopStartVariant, StateEnterVariant, ActionCompleteVariant, ...)`) so the audit walker can iterate without importing each variant individually.
- File: `scripts/little_loops/observability/schema.py` (greenfield; directory does not exist yet — create it).

**Step 3 — Audit script** (mechanism):
- Walk `scripts/little_loops/` via `pkg_root.rglob("*.py")` (precedent `cli/verify_package_data.py:139`).
- Phase 1 — regex detector for emit-call patterns: `\bself\._emit\(`, `\bevent_bus\.emit\(`, `\bbus\.emit\(`, capture the 1st-arg string literal (event-type). Builds the "classified-emit-sites" set.
- Phase 2 — for each captured event-type, look up matching `DES_VARIANTS` entry by the `type: Literal[...]` value. Assert set-equality: every captured event-type must have a registered variant.
- Phase 3 — AST fallback (`ast.parse` per file + `ast.walk` for `ast.Call`) for spread-construction sites (`state.py:104–107`, `fsm/persistence.py:700–703`) that regex can't capture cleanly. Wrap in try/except so a single bad file doesn't kill the audit.
- Return a typed `AuditResult` dataclass (`uncovered_event_types: list[str]`, `unmodeled_payload_keys: dict[str, set[str]]`) and exit `1 if uncovered_event_types else 0` (precedent `cli/verify_design_tokens.py:197–267`).
- File: `scripts/little_loops/observability/audit.py` (greenfield).
- CLI wrapper: `scripts/little_loops/cli/verify_des_audit.py` exposing `main_verify_des_audit() -> int` using the `cli_event_context(DEFAULT_DB_PATH, "ll-verify-des-audit", sys.argv[1:])` wrapper + `argparse` + `--json` mode (exact precedent `cli/verify_design_tokens.py:197–266`).
- Re-export at `scripts/little_loops/cli/__init__.py:81–83` and add to `__all__`.
- Register in `scripts/pyproject.toml:51–91` `[project.scripts]` as `ll-verify-des-audit = "little_loops.cli:main_verify_des_audit"`.

**Step 4 — Tests** (file + structure):
- `scripts/tests/test_des_schema.py` — `class TestSchemaDefinitions` (catalog completeness) + `class TestVariantRoundtrip` (sample payload → dataclass → `to_dict` matches source) + `class TestGenerateSchemaDocs` (the `--json` markdown writer).
- `scripts/tests/test_des_audit.py` — `class TestMain` (clean-tree returns 0; with a synthetic bad emit returns 1) modeled on `scripts/tests/test_verify_design_tokens.py:178–238`. `class TestAuditWalker` exercises the regex + AST phases against fixtures in `tmp_path`.
- Honor `scripts/tests/conftest.py:447–498` isolation contract (`LL_HISTORY_DB` env var) so the new tests never open the real `.ll/history.db`.

**Step 5 — CI gate**:
- The existing `python -m pytest scripts/tests/` invocation is the project's only enforced gate (per `.claude/CLAUDE.md` "Testing & CI Policy" — no GitHub Actions). The new tests must run under that one command and exit 0.
- Audit runs on demand via `python -m ll_loop.cli verify-des-audit` (or `ll-verify-des-audit` once registered); it is a developer-tool, not a CI blocker, but it must pass before F5 ships.

**Step 6 — Documentation** (concrete cross-links):
- New auto-generated `docs/observability/des-audit.md` (table-of-variants × emit-site-pass/fail) emitted by the audit script's `--write-docs` flag (or auto-emitted on every clean run).
- Add a § `little_loops.observability.schema` entry in `docs/reference/API.md` immediately after § `little_loops.fsm.schema` (~line 4368) documenting the registry API.
- Bump `docs/reference/EVENT-SCHEMA.md` top-of-file cross-link: "Canonical DES registry at `scripts/little_loops/observability/schema.py`; this Markdown catalog is the human-readable digest."
- Add a one-line cross-link in `docs/ARCHITECTURE.md` near the producer/consumer sequence diagram (~line 661–686).

**Step 7 — Hand-off to F5**:
- After the audit exits 0 with a registered variant for every currently-emitted event, F5 (`scripts/little_loops/observability/tracing.py`, greenfield per EPIC-2456) can land its `gen_ai.usage.*` emit path against the static-known surface rather than against a runtime shape-coercion layer.
- The audit also serves as a regression gate: any new emit site that introduces an unregistered variant will fail the audit, forcing registration before shipping.

**Stale-reference note (auto-flagged by `ll:codebase-locator`)**:
- The issue body cites `scripts/little_loops/sqlite_transport.py` (line 50–51, 462–465, 1295–1305), which **does not exist**. Trust the canonical anchors above; do not chase these paths.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Create the new `observability` package** — `scripts/little_loops/observability/__init__.py` re-exports `DES_VARIANTS` (from `schema.py`), `AuditResult`, and `audit_tree` (from `audit.py`) so the module is importable as `little_loops.observability.schema` / `.audit`. (No `MANIFEST.in` or hatch-build change needed — `packages = ["little_loops"]` at `pyproject.toml:124–126` already covers the new subpackage.)
9. **Extend `cli/__init__.py` to the `__all__` block** — add `"main_verify_des_audit"` to lines 118–123 alongside `main_verify_design_tokens` / `main_verify_package_data` / etc. (the issue body only mentions the import at lines 81–83).
10. **Register the new CLI** in `commands/help.md:280–284` CLI TOOLS block, in `skills/configure/areas.md:832` (count bump `30 → 31` + add name to comma list), in `README.md:46,78` (count bumps `37 → 38` only — no new section per `CONTRIBUTING.md:366`), and in `.claude/CLAUDE.md` CLI Tools block.
11. **Add the `DOC_STRINGS_PRESENT` triple-entry** to `scripts/tests/test_wiring_cli_registry.py` (lines 20–104) — without this, the structural guard will fail because `commands/help.md` / `docs/reference/CLI.md` / `.claude/CLAUDE.md` will all cite the new tool name but the registry test won't know to look.
12. **Add the `### ll-verify-des-audit` subsection** to `docs/reference/CLI.md:2448–2603` (model after `ll-verify-design-tokens` at 2579–2603).
13. **Add the `### main_verify_des_audit` docstring block** to `docs/reference/API.md:3737–3745` (model after `main_verify_docs`).
14. **Extend the audit walker's source tree** to include the additional Channel A / B / C sites discovered by `/ll:wire-issue`:
    - Channel A read-side: `history_reader.py`, `issue_history/parsing.py`, `issue_history/analysis.py`, `user_messages.py`, `decisions.py`, `issue_history/evolution.py` (read-only — exclude from coverage test but include in the table map).
    - Channel B transport wiring: `issue_manager.py:44,1160–1161` + `transport.py:652–655` (the audit must confirm every emit routed through these `SQLiteTransport` instances has a registered variant).
    - Channel C `cli_event_context` callers: `cli/auto.py`, `cli/parallel.py`, `init/cli.py`, `cli/issues/__init__.py`, `cli/sprint/__init__.py`, `cli/loop/__init__.py`, `cli/verify_triggers.py`, `cli/verify_design_tokens.py`, `cli/verify_package_data.py` (and the remaining 25+ `cli/*.py` files; verify the walker covers all of them).
    - Audit-exclude list: `state.py:227` and `issue_manager.py:1442` `record_corrections` (these are state-JSON writers, NOT history.db — the walker must skip them).
15. **Add `tests/test_wiring_cli_registry.py` coverage** for the new triple-entry (per step 11 above).
16. **Optional**: add `CHANGELOG.md` `Planned` entry for `ENH-2475` (convention, not required).
17. **Optional**: add ARCH-rule entry in `.ll/decisions.yaml` documenting the "register-before-emit" invariant.

## Acceptance Criteria

- DES variant registry in `observability/schema.py` covers every event table in `.ll/history.db`
- Audit script exits 0 against the current tree (i.e. every emit site maps to a known variant), OR exists with an explicit list of remaining port sites that F5 will pick up
- `python -m pytest scripts/tests/` exits 0 with the new tests added
- `docs/reference/API.md` documents the registry API
- EPIC-2456 § Success Metric "DES schema accepts 100% of currently-emitted events" gate is unblocked

## Scope Boundaries

- **In**: Audit + DES registry + port list
- **Out**: OTel `gen_ai.usage.*` attribute emission (F5 child); `gen_ai.invocation.id` UUID stamping (F5 child); cost attribution UI (out of scope for this EPIC)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; § Tier 1 [TBD-3], § Success Metrics F5 |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | Sibling Tier 0 work; emits the events this audit will classify |

## Impact

- **Priority**: P2 — gates EPIC-2456 § Tier 1 F5 from being able to land its DES schema cleanly
- **Effort**: Small — ~30 LOC schema + audit script + tests
- **Risk**: Low — read-only audit + static registry; no runtime behavior change
- **Breaking Change**: No — registry is additive; existing events keep flowing

## Status

**Done** | Created: 2026-07-04 | Priority: P2 | Completed: 2026-07-07

## Session Log
- `/ll:ready-issue` - 2026-07-07T03:38:09 - `dae638b1-ff71-4075-91db-d423028513e4.jsonl`
- `/ll:ready-issue` - 2026-07-07T03:37:50 - `dae638b1-ff71-4075-91db-d423028513e4.jsonl`
- `/ll:wire-issue` - 2026-07-05T04:25:40 - `96cde535-2534-4eef-a0ab-403a9dd9c557.jsonl`
- `/ll:refine-issue` - 2026-07-05T01:12:27 - `33f03ea0-c7a0-42a0-9db7-35a7941f27c4.jsonl`
- `/ll:manage-issue` - 2026-07-07T04:27:22Z - implementation complete: 65 variants registered, `ll-verify-des-audit` passes against the real tree, full test suite green

- `/ll:capture-issue` - 2026-07-04T20:05:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a4ee548-94b7-4694-b8c1-49e3f31cc127.jsonl`
