---
discovered_date: 2026-05-01
discovered_by: split-from-FEAT-918
confidence_score: 80
outcome_confidence: 70
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 22
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

- `scripts/little_loops/transport.py` — add `WebhookTransport`; register `"webhook"` constructor in `wire_transports()`
- `scripts/little_loops/config/features.py` — add `WebhookEventsConfig` dataclass; extend `EventsConfig` with `webhook: WebhookEventsConfig` field
- `config-schema.json` — extend `events` block with `webhook` sub-object: `url: string|null`, `batch_ms: integer (default 1000)`, `headers: object`. Pattern: model after `sync.github` (lines 776–818). Close with `additionalProperties: false`
- `pyproject.toml` — add `webhooks = ["httpx>=0.24.0"]` to `[project.optional-dependencies]` (line 78+)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/transport.py` — `wire_transports()` is the only constructor; it will instantiate `WebhookTransport` when `"webhook"` appears in `transports` list

### Similar Patterns

- `scripts/little_loops/parallel/merge_coordinator.py:57-111` — daemon thread + `Queue` + `threading.Event` shutdown sentinel. Use as the batch-thread template
- `scripts/little_loops/git_lock.py:110-181` — exponential retry with backoff (0.5 → 8.0, capped at `max_retries=3`)
- `scripts/little_loops/issue_history/formatting.py:94-100` — `try/except ImportError` optional-dep guard pattern
- `scripts/little_loops/link_checker.py:163-183` — `urllib.request` stdlib HTTP fallback (only if avoiding `httpx` dep is desired; recommendation: use `httpx`, simpler)

### Tests

- `scripts/tests/test_transport.py` — add:
  - `WebhookTransport` Protocol satisfaction
  - missing-`httpx` `RuntimeError` test via `builtins.__import__` mock (pattern: `test_issue_history_formatting.py:137-154`)
  - batching behavior — enqueue N events, advance time, assert single POST with N events
  - retry behavior — mock 5xx then 200, assert two attempts and exponential delay
  - `close()` drains queue and joins thread within 10s
- `scripts/tests/test_config.py` — `WebhookEventsConfig` defaults and full-tree parse

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

1. Add `WebhookEventsConfig` dataclass to `config/features.py` (`url: str | None`, `batch_ms: int = 1000`, `headers: dict[str, str] = field(default_factory=dict)`); extend `EventsConfig` with `webhook` field.
2. Extend `config-schema.json` `events` block with `webhook` sub-object, modeled after `sync.github`.
3. Add `WebhookTransport` to `scripts/little_loops/transport.py` with optional-`httpx` guard, batch daemon, retry loop, and graceful `close()`.
4. Register `"webhook"` in `wire_transports()`'s constructor map.
5. Add `webhooks` extra to `pyproject.toml`.
6. Write tests in `test_transport.py` (Protocol, missing-dep, batching, retry, close) and `test_config.py` (webhook config parsing).
7. Update docs: `CONFIGURATION.md`, `API.md`, `ARCHITECTURE.md`.

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

## Session Log
- `/ll:format-issue` - 2026-05-03T17:13:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ea146a5-288b-488a-b878-065475896445.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`

- Split from FEAT-918 - 2026-05-01
