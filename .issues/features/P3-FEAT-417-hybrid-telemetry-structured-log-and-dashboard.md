---
discovered_date: 2026-02-13
discovered_by: capture_issue
---

# FEAT-417: Hybrid Telemetry — Structured Event Log + Lightweight Dashboard

## Summary

Add a unified telemetry layer that emits structured events from all CLI tools (ll-auto, ll-parallel, ll-sprint, ll-loop) and hooks into an append-only JSONL log. Provide an `ll-telemetry` CLI for querying, summarizing, and exporting this data — with an optional OpenTelemetry (OTel) exporter for sending traces to external backends (Jaeger, Grafana Tempo, LangSmith).

This is the **operational observability** layer for little-loops: it answers "how is the system performing?" while FEAT-324 (History DB) answers "what work has been done?".

## Current Behavior

- `ll-loop` is the only CLI tool that emits a structured event stream (`.loops/.running/{name}.events.jsonl`)
- `ll-auto`, `ll-parallel`, and `ll-sprint` persist timing data in state files but emit no events
- Context monitor writes to `.claude/ll-context-state.json` but data is overwritten each session
- `ll-messages` can extract tool usage from Claude session JSONLs but doesn't persist the results
- There is no unified view of operational metrics across tools
- Performance data is scattered across 5+ file formats with no correlation

## Expected Behavior

A shared `telemetry.py` module provides an `emit()` function that all CLI tools and hooks call. Events are appended to a project-local JSONL log. An `ll-telemetry` CLI queries this log for summaries, trends, and exports.

### Event Flow

```
CLI Tools / Hooks
    │
    ├─ emit("command_start", ...) ──►  .ll/telemetry.jsonl
    ├─ emit("issue_phase", ...)   ──►       │
    ├─ emit("issue_complete", ...)──►       │
    └─ emit("context_snapshot",...)──►      │
                                            │
                                     ll-telemetry CLI
                                       ├─ summary
                                       ├─ trends --weekly
                                       ├─ trace <issue-id>
                                       └─ export --format otel
```

### Event Schema

```jsonl
{"ts":"2026-02-13T10:00:00Z","event":"command_start","tool":"ll-sprint","args":["run","sprint-7"],"project":"little-loops","session_id":"abc123"}
{"ts":"2026-02-13T10:00:05Z","event":"issue_start","tool":"ll-sprint","issue_id":"BUG-042","wave":1}
{"ts":"2026-02-13T10:01:12Z","event":"issue_phase","tool":"ll-sprint","issue_id":"BUG-042","phase":"ready","duration_s":67.2,"result":"pass"}
{"ts":"2026-02-13T10:03:22Z","event":"issue_complete","tool":"ll-sprint","issue_id":"BUG-042","duration_s":197,"result":"success","phases":{"ready":67.2,"implement":98.5,"verify":31.3}}
{"ts":"2026-02-13T10:03:23Z","event":"context_snapshot","estimated_tokens":45000,"tool_calls":23,"breakdown":{"Read":12,"Edit":5,"Bash":6}}
{"ts":"2026-02-13T10:15:00Z","event":"command_end","tool":"ll-sprint","duration_s":900,"issues_completed":3,"issues_failed":1}
```

### ll-telemetry CLI Subcommands

- `ll-telemetry summary` — Velocity, success rates, avg durations, tool usage breakdown
- `ll-telemetry trends --period weekly` — Time-series sparklines in terminal
- `ll-telemetry trace <issue-id>` — Show all events for a specific issue across tools
- `ll-telemetry export --format otel --endpoint http://localhost:4318` — Export as OTel spans
- `ll-telemetry export --format csv` — Export for spreadsheet analysis
- `ll-telemetry prune --older-than 90d` — Rotate old events

## Motivation

The plugin generates rich operational data but it's scattered across tool-specific state files, hook state JSON, and transient console output. Developers can't answer basic questions like:
- "What's my average issue processing time this week vs. last week?"
- "Which phase (ready/implement/verify) is the bottleneck?"
- "How much context am I using per issue on average?"
- "What's the failure rate for ll-parallel vs. ll-sprint?"

A unified telemetry stream enables data-driven workflow optimization and provides the foundation for optional integration with external observability platforms.

## Use Case

A developer finishes a sprint and runs `ll-telemetry summary --since 7d`. They see that their average issue duration increased from 3.2 to 5.1 minutes this week, with the `implement` phase accounting for 80% of the increase. They also see that 2 of 8 issues failed during `verify`, both on ENH-type issues. This tells them their enhancement issue specs may need more detail to reduce rework.

Later, they enable the OTel exporter and send traces to a local Jaeger instance to get waterfall visualizations of their sprint execution across parallel workers.

## Acceptance Criteria

- [ ] `scripts/little_loops/telemetry.py` module with `emit()`, `query()`, and `TelemetryEvent` dataclass
- [ ] Events emitted from `ll-auto` (issue_manager.py) at command start/end and per-issue phase boundaries
- [ ] Events emitted from `ll-parallel` (orchestrator.py, worker_pool.py) at command start/end and per-worker results
- [ ] Events emitted from `ll-sprint` (sprint.py) at command start/end, per-wave, and per-issue
- [ ] Events emitted from `ll-loop` (executor.py) — adapt existing `.events.jsonl` to also write to unified log
- [ ] Context monitor hook emits `context_snapshot` events to telemetry log
- [ ] `ll-telemetry` CLI with `summary`, `trends`, `trace`, `export`, and `prune` subcommands
- [ ] JSONL log stored at `.ll/telemetry.jsonl` (gitignored, project-local)
- [ ] Log rotation via `prune` subcommand
- [ ] Optional OTel OTLP exporter (behind `--otel-endpoint` flag or config setting)

## API/Interface

```python
# scripts/little_loops/telemetry.py

@dataclass
class TelemetryEvent:
    ts: str                          # ISO 8601 timestamp
    event: str                       # Event type (command_start, issue_complete, etc.)
    tool: str                        # CLI tool name (ll-auto, ll-sprint, etc.)
    project: str | None = None       # Project name from config
    session_id: str | None = None    # Claude session ID if available
    issue_id: str | None = None      # Issue being processed
    phase: str | None = None         # Phase name (ready, implement, verify)
    duration_s: float | None = None  # Duration in seconds
    result: str | None = None        # Outcome (success, failure, skipped)
    metadata: dict | None = None     # Tool-specific extra data

class Telemetry:
    def __init__(self, log_path: Path | None = None): ...
    def emit(self, event: TelemetryEvent) -> None: ...
    def query(self, since: str | None, until: str | None, event_type: str | None,
              tool: str | None, issue_id: str | None) -> list[TelemetryEvent]: ...
    def summary(self, since: str | None = None) -> TelemetrySummary: ...
    def prune(self, older_than_days: int) -> int: ...

# CLI: scripts/little_loops/cli/telemetry.py
# Entry point: ll-telemetry
```

```python
# OTel exporter (optional module)
# scripts/little_loops/telemetry_otel.py

class OTelExporter:
    def __init__(self, endpoint: str): ...
    def export_events(self, events: list[TelemetryEvent]) -> int: ...
    def export_as_traces(self, events: list[TelemetryEvent]) -> int: ...
```

## Proposed Solution

### Phase 1: Core Event Log (no new dependencies)

1. Create `telemetry.py` with `TelemetryEvent` dataclass and `Telemetry` class
2. `emit()` appends JSON lines to `.ll/telemetry.jsonl` (atomic writes with file locking)
3. Instrument `ll-auto`, `ll-parallel`, `ll-sprint` at phase boundaries — follow `ll-loop`'s existing pattern in `fsm/persistence.py:append_event()`
4. Bridge `ll-loop`: have executor emit to both `.events.jsonl` (loop-specific) and unified telemetry log
5. Add `context_snapshot` emission to context-monitor hook
6. Create `ll-telemetry` CLI with `summary` and `trends` subcommands

### Phase 2: Query and Export

7. Add `trace` subcommand (filter events by issue_id, show timeline)
8. Add `prune` subcommand with configurable retention
9. Add `export --format csv` for spreadsheet analysis
10. Add `export --format json` for programmatic consumption

### Phase 3: OTel Integration (adds `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` dependencies)

11. Create `telemetry_otel.py` module with OTLP span exporter
12. Map event hierarchy to OTel traces: command → wave → issue → phase
13. Add `--otel-endpoint` flag to `ll-telemetry export`
14. Add optional `telemetry.otel_endpoint` config setting for always-on export
15. Document Jaeger/Grafana Tempo Docker setup for local visualization

### Existing Pattern to Follow

`ll-loop` already implements event emission in `scripts/little_loops/fsm/persistence.py`:
- `append_event()` at line 168 — atomic JSONL append
- Event types: `loop_start`, `state_enter`, `action_execute`, `evaluate`, `route`, `loop_complete`
- `get_loop_history()` — reads event stream back

The telemetry module generalizes this pattern across all CLI tools.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — Emit events from ll-auto processing phases
- `scripts/little_loops/parallel/orchestrator.py` — Emit events from ll-parallel orchestration
- `scripts/little_loops/parallel/worker_pool.py` — Emit events from worker results
- `scripts/little_loops/sprint.py` — Emit events from ll-sprint wave execution
- `scripts/little_loops/fsm/executor.py` — Bridge ll-loop events to unified telemetry
- `hooks/scripts/context-monitor.sh` — Emit context_snapshot events (or call Python helper)
- `scripts/setup.cfg` or `pyproject.toml` — Add `ll-telemetry` console_scripts entry point
- `.gitignore` — Ensure `.ll/` is gitignored (shared with FEAT-324)

### New Files
- `scripts/little_loops/telemetry.py` — Core telemetry module
- `scripts/little_loops/cli/telemetry.py` — CLI entry point
- `scripts/little_loops/telemetry_otel.py` — Optional OTel exporter (Phase 3)
- `scripts/tests/test_telemetry.py` — Unit tests for emit/query/summary
- `scripts/tests/test_telemetry_cli.py` — CLI integration tests

### Dependent Files (Callers/Importers)
- FEAT-324 (History DB) shares `.ll/` directory and `issue_id` correlation key
- All CLI tools become telemetry producers

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py` — `append_event()` is the direct model for `emit()`
- `scripts/little_loops/logger.py` — Console output counterpart (telemetry is its structured sibling)
- `scripts/little_loops/user_messages.py` — Similar JSONL parsing patterns for `query()`

### Tests
- `scripts/tests/test_telemetry.py` — Event emission, query filtering, summary calculation, prune
- `scripts/tests/test_telemetry_cli.py` — CLI subcommand integration tests
- `scripts/tests/test_telemetry_otel.py` — OTel export tests (Phase 3, mock OTLP endpoint)

### Documentation
- `docs/ARCHITECTURE.md` — Document telemetry layer and event schema
- `docs/API.md` — Document telemetry module public interface

### Configuration
- `.claude/ll-config.json` — Add `telemetry` section:
  ```json
  {
    "telemetry": {
      "enabled": true,
      "log_path": ".ll/telemetry.jsonl",
      "retention_days": 90,
      "otel_endpoint": null
    }
  }
  ```

## Implementation Steps

1. Create `telemetry.py` module with `TelemetryEvent`, `Telemetry.emit()`, and file-locking JSONL append
2. Instrument `ll-auto` issue_manager.py at phase boundaries (ready/implement/verify)
3. Instrument `ll-parallel` orchestrator.py and worker_pool.py at worker start/complete
4. Instrument `ll-sprint` sprint.py at wave and issue boundaries
5. Bridge `ll-loop` executor.py to emit to unified log alongside `.events.jsonl`
6. Create `ll-telemetry` CLI with `summary`, `trends`, `trace`, `prune`, and `export` subcommands
7. Add OTel exporter module with OTLP span export (Phase 3)
8. Add config schema support for `telemetry` section

## Impact

- **Priority**: P3 — High value for workflow optimization but not blocking other features
- **Effort**: Large — Touches all CLI tools, new module + CLI, optional OTel integration
- **Risk**: Low — Append-only JSONL is safe; telemetry failures should never block CLI operations (emit should be fire-and-forget with error swallowing)
- **Breaking Change**: No

## Related Issues

- **FEAT-324** (SQLite History DB) — Complementary. FEAT-324 stores domain data (issue metadata for duplicate detection); this stores operational data (event timings for dashboards). Both share `.ll/` directory and `issue_id` as correlation key. FEAT-324's `session_summaries` table is deferred in favor of querying telemetry events by issue_id.
- **ENH-390** (Split issue_history module) — Refactoring that may affect where summary metrics live

## Scope Boundaries

**In scope:**
- Unified JSONL event log from all CLI tools and hooks
- `ll-telemetry` CLI for query, summary, trends, trace, export, prune
- Optional OTel OTLP exporter (Phase 3)
- CSV/JSON export formats

**Out of scope:**
- Web dashboard UI (use external tools like Grafana with OTel export)
- LangSmith-specific integration (use OTel exporter with LangSmith's OTLP ingestion)
- Real-time streaming (telemetry is post-hoc analysis; real-time comes from OTel backends)
- Modifying `ll-history` or `ll-messages` output (those remain separate tools)
- Replacing `ll-loop`'s `.events.jsonl` (unified log is additive, not a replacement)

## Success Metrics

- All 4 CLI tools (ll-auto, ll-parallel, ll-sprint, ll-loop) emit events to unified log
- `ll-telemetry summary` produces output within 1s for 10,000+ events
- `ll-telemetry trace <issue-id>` correlates events across tools for a single issue
- OTel export successfully sends spans to a local Jaeger instance
- No measurable performance impact on CLI tool execution from telemetry emission

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design, module structure, CLI tool architecture |
| architecture | docs/API.md | Python module conventions, CLI entry points |
| guidelines | CONTRIBUTING.md | Development setup, testing patterns |

## Labels

`feature`, `observability`, `captured`

## Session Log

- `/ll:capture_issue` - 2026-02-13T20:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0592a7db-5806-42c2-ab13-a65ef3818ff6.jsonl`

---

## Status

**Open** | Created: 2026-02-13 | Priority: P3
