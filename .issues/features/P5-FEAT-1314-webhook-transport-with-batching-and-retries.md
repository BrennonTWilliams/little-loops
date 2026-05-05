---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
---

# FEAT-1314: WebhookTransport with Batching and Retries

## Summary

Add a `WebhookTransport` that POSTs batched FSM events to a configurable HTTP endpoint, so remote dashboards, Slack bots, and CI systems can subscribe to ll loop activity without polling the filesystem.

## Context

Split from the original FEAT-918 on 2026-05-01. FEAT-918 now contains only the `Transport` Protocol foundation, `JsonlTransport`, and the `wire_transports()` registry. This issue plugs in the webhook implementation.

## Current Behavior

No HTTP egress for ll events. Consumers must read `.ll/events.jsonl` (file watcher) or attach as an in-process observer. There is no built-in way to forward events to an external service.

## Expected Behavior

- A `WebhookTransport(url, batch_ms, headers, max_retries)` class that satisfies `Transport`.
- Events are queued non-blocking in `send()` and flushed by a daemon batch thread on a configurable interval (default 1000ms).
- POSTs use `httpx` (optional dep) with exponential backoff on 5xx / connection errors (default: 3 retries, 0.5s → 8s).
- `close()` signals shutdown, drains the queue (one final flush), and joins the daemon thread with a 10s timeout.
- Optional `headers` dict supports auth (`Authorization: Bearer ...`).
- Missing `httpx` raises `RuntimeError("install httpx: pip install little-loops[webhooks]")` only when the transport is **constructed** — package import must not fail without `httpx`.

## Motivation

- Production monitoring and ChatOps integrations need a push channel, not file polling.
- Remote-only consumers (no shared filesystem) have no path today.

## Proposed Solution

1. Add `WebhookTransport` to `scripts/little_loops/transport.py`.
2. Extend `EventsConfig` in `config/features.py` with a nested `WebhookEventsConfig(url, batch_ms, headers)`.
3. Register `"webhook"` in `wire_transports()`'s name → constructor map.
4. Add `httpx>=0.24.0` to `[project.optional-dependencies]` under `webhooks`.
5. Extend `config-schema.json` `events` block with a `webhook` sub-object.

## API/Interface

```python
class WebhookTransport:
    def __init__(
        self,
        url: str,
        batch_ms: int = 1000,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ): ...
    def send(self, event: dict[str, Any]) -> None: ...   # enqueue, non-blocking
    def close(self) -> None: ...                          # drain + join
```

Config:

```json
{
  "events": {
    "transports": ["jsonl", "webhook"],
    "webhook": {
      "url": "https://hooks.example.com/ll-events",
      "batch_ms": 1000,
      "headers": { "Authorization": "Bearer ..." }
    }
  }
}
```

## Integration Map

### Files to Modify

- `scripts/little_loops/transport.py` — add `WebhookTransport`; add `"webhook": "webhook"` to `_TRANSPORT_REGISTRY`; add `elif name == "webhook":` branch in `wire_transports()` (same pattern as the existing `"socket"` branch)
- `scripts/little_loops/config/features.py` — add `WebhookEventsConfig` dataclass; extend `EventsConfig` with `webhook: WebhookEventsConfig` field
- `scripts/little_loops/__init__.py` — add `WebhookTransport` to public exports alongside `Transport`, `JsonlTransport`, `UnixSocketTransport`, `wire_transports`
- `config-schema.json` — extend `events` block with `webhook` sub-object: `url: string|null`, `batch_ms: integer (default 1000)`, `headers: object`. Pattern: model after `sync.github` (lines 907–967). Close with `additionalProperties: false`
- `scripts/pyproject.toml` — add `webhooks = ["httpx>=0.24.0"]` to `[project.optional-dependencies]`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — add `WebhookEventsConfig` to the import from `features.py` (after `SocketEventsConfig`) and to `__all__`; without this, callers that do `from little_loops.config import WebhookEventsConfig` will fail at runtime [Agent 1 + 2 finding]
- `scripts/little_loops/config/core.py` — extend `BRConfig.to_dict()`: add `"webhook"` sub-dict to the `events` block (parallel to the existing `"socket"` sub-dict); without this, template variable substitution for `${config.events.webhook.url}` silently returns `None` [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_TRANSPORT_REGISTRY` implementation detail** (critical): The registry is `dict[str, str] = {"jsonl": "jsonl", "socket": "socket"}` — a name-to-name string dict used as a **membership check**, not a constructor map. `wire_transports()` has explicit `if name == "jsonl":` / `elif name == "socket":` branches after the registry check. Adding `"webhook"` requires **two changes**: (1) add `"webhook": "webhook"` to `_TRANSPORT_REGISTRY`, and (2) add an `elif name == "webhook":` branch that instantiates `WebhookTransport`.

**Module-level constants pattern**: `transport.py` lines 36–42 define all tunable values as named module-level constants (e.g., `_CLIENT_QUEUE_MAXSIZE = 1024`, `_CLOSE_TOTAL_TIMEOUT = 10.0`). Follow this pattern — do not use magic literals inside the class. Suggested: `_WEBHOOK_BATCH_MS_DEFAULT = 1000`, `_WEBHOOK_CLOSE_TIMEOUT = 10.0`, `_WEBHOOK_RETRY_BASE_S = 0.5`, `_WEBHOOK_RETRY_MAX_S = 8.0`.

**`config-schema.json` sync.github model**: The referenced pattern is at lines 907–967 (not 776–818 as originally noted).

### State Update (2026-05-05) — FEAT-1312 landed

_Added by `/ll:refine-issue` — FEAT-1312 (OTelTransport) has landed since the prior pass; the items below supersede stale references in the sections above:_

**`_TRANSPORT_REGISTRY` (prior "critical" note is stale)**: Registry is now `{"jsonl": "jsonl", "otel": "otel", "socket": "socket"}` at `transport.py:444`. `wire_transports()` (line 447) already has a `elif name == "otel":` branch (lines 475–480); adding `"webhook"` means a third `elif` alongside both `"otel"` and `"socket"`.

**Updated line numbers** (shifted by FEAT-1312 additions):
- Module-level constants block: now lines 40–46 (was 36–42)
- `_SocketClient`: now line 88 (was 84)
- `_accept_loop`: now line 154 (was 150)
- `_client_loop`: now line 185 (was 181)
- `config-schema.json` events block: now lines 1048–1094; `events.socket` at 1058–1073, `events.otel` at 1075–1091 — use `events.otel` as the closer template for `events.webhook` (both have a nullable URL-style field plus simple key-value fields)
- `TestSocketEventsConfig` in `test_config.py`: now line 1286 (was 1266)
- `TestEventsConfig` in `test_config.py`: now line 1235 (was 1234)
- `test_events_socket_round_trips_through_to_dict`: now line 1360 (was 1320); `test_events_otel_round_trips_through_to_dict` at line 1378 — model `test_events_webhook_round_trips_through_to_dict` after both

**`config/features.py`**: `OTelEventsConfig` is now at line 391 alongside `SocketEventsConfig` (line 375). `EventsConfig.from_dict()` (line 420) already parses `otel`; add `webhook` at the same level.

**`config/core.py` `BRConfig.to_dict()`**: Events block (lines 459–466) now serializes both `"socket"` and `"otel"` sub-dicts; add `"webhook"` as a third parallel entry.

**`config/__init__.py`**: `OTelEventsConfig` is now exported alongside `SocketEventsConfig`; add `WebhookEventsConfig` after `OTelEventsConfig` in the import and `__all__`.

**`__init__.py` exports**: `OTelTransport` is now exported; add `WebhookTransport` alongside it.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/transport.py` — `wire_transports()` is the only constructor; it will instantiate `WebhookTransport` when `"webhook"` appears in `transports` list

### Similar Patterns

- `scripts/little_loops/transport.py:84` — `_SocketClient` + `_accept_loop` (line 150) + `_client_loop` (line 181): Queue-based daemon thread pattern **already in transport.py** — the closest structural template for `WebhookTransport`'s batch thread (same file, same module conventions)
- `scripts/little_loops/parallel/merge_coordinator.py:81` — `start()` / `_merge_loop` (line 679): alternative daemon thread + `Queue` + `threading.Event` shutdown pattern
- `scripts/little_loops/parallel/git_lock.py:110` — `GitLock._run_with_retry()`: exponential retry with `initial_backoff=0.5`, `max_backoff=8.0`, `backoff = min(backoff * 2, self.max_backoff)` formula
- `scripts/little_loops/issue_history/formatting.py:85` — `format_analysis_yaml()`: `try: import yaml / except ImportError: fallback` optional-dep guard pattern (inline import, not module-level)
- `scripts/little_loops/link_checker.py:163-183` — `urllib.request` stdlib HTTP fallback (only if avoiding `httpx` dep is desired; recommendation: use `httpx`, simpler)

### Tests

- `scripts/tests/test_transport.py` — add class `TestWebhookTransport` (model after `TestUnixSocketTransport`):
  - Protocol satisfaction: `assert isinstance(t, Transport)`
  - missing-`httpx` `RuntimeError` test via `builtins.__import__` mock — exact pattern at `test_issue_history_formatting.py:TestFormatAnalysisYaml.test_yaml_fallback_to_json` (line 137)
  - batching behavior — enqueue N events, advance time, assert single POST with N events
  - retry behavior — mock 5xx then 200, assert two attempts and exponential delay
  - `close()` drains queue and joins thread within 10s
- `scripts/tests/test_config.py` — add `TestWebhookEventsConfig` (defaults and full-tree) after `TestSocketEventsConfig` (line 1266); add `TestEventsConfig` (line 1234) webhook field assertions

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — `TestConfigSchema.test_events_in_schema`: extend to assert `"webhook" in events_props` and verify the webhook sub-object carries `additionalProperties: false`; without this, the schema guard for `events.webhook` is untested [Agent 2 + 3 finding — existing test to update]
- `scripts/tests/test_config.py` — `TestBRConfigEventsIntegration`: add `test_events_webhook_round_trips_through_to_dict` parallel to `test_events_socket_round_trips_through_to_dict` (line 1320), asserting `result["events"]["webhook"]["url"]` and other fields [Agent 3 finding — new test to write]

### Documentation

- `docs/reference/CONFIGURATION.md` — document `events.webhook` block and `pip install little-loops[webhooks]` install
- `docs/reference/API.md` — `WebhookTransport` constructor params
- `docs/ARCHITECTURE.md` — webhook transport in the multi-transport list

### Configuration

- `config-schema.json` — already listed in Files to Modify (new `events.webhook` sub-object)
- `pyproject.toml` — already listed in Files to Modify (`webhooks` optional dependency group)

## Use Case

A team runs `ll-parallel` against 10 issues. Their internal Slack bot exposes a `/ll-events` webhook. Each loop event POSTs to the bot, which posts loop completions and failures to `#engineering`. No local log scraping, no shared FS.

## Acceptance Criteria

- [ ] `WebhookTransport` implemented and satisfies `isinstance(t, Transport)`
- [ ] `httpx` is **optional** — package import succeeds without it; `WebhookTransport.__init__` raises clear `RuntimeError` when constructed without it
- [ ] Daemon thread batches events on `batch_ms` interval
- [ ] Exponential backoff retry with `max_retries=3`, base 0.5s, cap 8s; gives up after retries and logs a warning (does not raise to caller)
- [ ] `close()` puts shutdown sentinel, drains queue with one final flush, joins thread with 10s timeout
- [ ] Config schema validates `events.webhook.url`, `batch_ms`, `headers`
- [ ] `wire_transports()` recognizes `"webhook"` and constructs `WebhookTransport(config.events.webhook.url, ...)`; logs warning + skips if `url` is `None`
- [ ] All transport tests pass; missing-`httpx` test passes without `httpx` installed

## Implementation Steps

1. Add `WebhookEventsConfig` dataclass to `scripts/little_loops/config/features.py` (`url: str | None`, `batch_ms: int = 1000`, `headers: dict[str, str] = field(default_factory=dict)`); extend `EventsConfig.from_dict()` to parse `data.get("webhook", {})` and construct `WebhookEventsConfig` (follow `SocketEventsConfig` pattern at line 375).
2. Extend `config-schema.json` `events` block with `webhook` sub-object modeled after `sync.github` (lines 907–967): `url: ["string", "null"]`, `batch_ms: integer (default 1000)`, `headers: object`. Close with `additionalProperties: false`.
3. Add module-level tunable constants to `scripts/little_loops/transport.py` (after the existing block at lines 36–42): `_WEBHOOK_BATCH_MS_DEFAULT`, `_WEBHOOK_CLOSE_TIMEOUT`, `_WEBHOOK_RETRY_BASE_S`, `_WEBHOOK_RETRY_MAX_S`.
4. Add `WebhookTransport` class to `transport.py`: optional-`httpx` guard (inline `try: import httpx / except ImportError: raise RuntimeError(...)` in `__init__`), `Queue`-based batch daemon thread (template: `_SocketClient`/`_client_loop` pattern already in the same file), exponential backoff retry (`backoff = min(backoff * 2, _WEBHOOK_RETRY_MAX_S)` formula from `GitLock._run_with_retry()`), and `close()` that sets shutdown event, does one final flush, and joins with 10s timeout.
5. Register `"webhook"` in `_TRANSPORT_REGISTRY` dict and add `elif name == "webhook":` branch in `wire_transports()` (check `config.events.webhook.url is None` → log warning + skip; otherwise instantiate `WebhookTransport(url, batch_ms, headers, max_retries=3)`).
6. Add `WebhookTransport` to `scripts/little_loops/__init__.py` exports alongside `Transport`, `JsonlTransport`, `UnixSocketTransport`.
7. Add `webhooks = ["httpx>=0.24.0"]` to `[project.optional-dependencies]` in `scripts/pyproject.toml`.
8. Write tests in `test_transport.py` (Protocol satisfaction, missing-httpx via `builtins.__import__` mock, batching, retry, close) and `test_config.py` (`TestWebhookEventsConfig` after line 1266, webhook assertions in `TestEventsConfig` after line 1234).
9. Update docs: `docs/reference/CONFIGURATION.md` (`events.webhook` block + `pip install little-loops[webhooks]`), `docs/reference/API.md` (`WebhookTransport` constructor + update the "Currently shipped" enumeration in `### wire_transports` to include `"webhook"`), `docs/ARCHITECTURE.md` (webhook in multi-transport list).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/config/__init__.py` — add `WebhookEventsConfig` to the `from .features import` line (after `SocketEventsConfig`) and to `__all__`; matches the existing `SocketEventsConfig` export pattern
11. Extend `BRConfig.to_dict()` in `scripts/little_loops/config/core.py` — add `"webhook": dataclasses.asdict(self.events.webhook)` (or equivalent) to the `events` sub-dict at the same level as the existing `"socket"` sub-dict; prevents `${config.events.webhook.url}` template substitution from silently returning `None`
12. Update `scripts/tests/test_config_schema.py` — extend `TestConfigSchema.test_events_in_schema` to assert `"webhook" in events_props` and verify `events_props["webhook"].get("additionalProperties") is False`

## Impact

- **Priority**: P5 — depends on FEAT-918 foundation
- **Effort**: Medium — daemon thread + retry + optional dep
- **Risk**: Low-Medium — daemon-thread shutdown timing is the main hazard
- **Breaking Change**: No (additive, optional)
- **Depends On**: FEAT-918

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Multi-transport event fan-out |
| reference | docs/reference/CONFIGURATION.md | `events.webhook` config block |
| reference | docs/reference/API.md | `WebhookTransport` constructor |

## Labels

`feat`, `observability`, `extension-api`

## Status

**Open** | Created: 2026-05-01 (split from FEAT-918) | Priority: P5

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-04_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- **FEAT-1312 conflict zone**: FEAT-1312 (OTelTransport, still active) and FEAT-1314 both modify `_TRANSPORT_REGISTRY`, `EventsConfig`, `wire_transports()`, and `config/features.py`. Sequencing should be resolved before implementing to avoid a messy merge.
- **Daemon-thread shutdown timing**: The `close()` drains + joins with a 10s timeout — race conditions under test (time mocking, thread join ordering) are the most likely source of flaky tests; plan extra time for the test harness.
- **httpx optional-dep test**: Mocking `builtins.__import__` is fragile if test order matters; isolate the import-mock test in its own method (as the referenced pattern does at `test_issue_history_formatting.py:137`).

## Session Log
- `/ll:confidence-check` - 2026-05-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/61328427-9db0-4165-a515-89b899d0858b.jsonl`
- `/ll:refine-issue` - 2026-05-05T17:46:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76919b1c-78ef-4e2f-b9d8-636083810f70.jsonl`
- `/ll:wire-issue` - 2026-05-05T04:28:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d01428b3-36bf-4273-8acb-4dec51c409f8.jsonl`
- `/ll:refine-issue` - 2026-05-05T04:23:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a202e3b-c7a9-41fd-a93d-16f49a478d61.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:format-issue` - 2026-05-03T17:13:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ea146a5-288b-488a-b878-065475896445.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`

- Split from FEAT-918 - 2026-05-01

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): FEAT-1312 (OTelTransport) and this issue both modify `wire_transports()` and `EventsConfig` in `scripts/little_loops/transport.py`. Implement this issue after FEAT-1312 lands, or combine both transports in a single PR. At minimum, coordinate PR ordering so the second merge applies cleanly over the first's changes to `_TRANSPORT_REGISTRY` and `EventsConfig`.
