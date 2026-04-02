---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Summary

Extend the observe-only extension protocol (FEAT-911) to support bidirectional communication: extensions can intercept operations via `before_`/`after_` hooks, contribute new FSM action types, and register custom evaluators. This transforms extensions from passive observers into active participants in the loop lifecycle.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." FEAT-911 scopes extensions as event consumers only. This issue captures the write-path capabilities needed for extensions that modify loop behavior — not just observe it.

## Current Behavior

FEAT-911 (once implemented) will provide observe-only extensions: they receive events but cannot influence execution. All action types and evaluators must live in the core plugin.

## Expected Behavior

Extensions can:
- Register `before_` and `after_` hooks on key operations (e.g., `before_route`, `before_issue_close`) that can modify or block the operation
- Contribute new FSM action types (e.g., a "slack-notify" extension adds `action: slack` usable in loop YAML)
- Contribute custom evaluators (e.g., a "metrics-eval" extension checks Prometheus thresholds as gate conditions)
- Declare execution priority so ordering conflicts are detected at load time

## Motivation

Observe-only extensions cover dashboards and logging but not the richer ecosystem use cases: approval gates, custom CI integrations, notification actions, or domain-specific evaluators. Bidirectional hooks make the extension API a true integration surface.

## Proposed Solution

1. Extend `LLExtension` Protocol with optional hook methods: `before_route()`, `after_route()`, `before_issue_close()`, etc.
2. Define `ActionProvider` Protocol — extensions that contribute new action types register a name + callable
3. Define `EvaluatorProvider` Protocol — extensions that contribute evaluator types
4. Add priority/ordering to extension registration; detect conflicts at load time
5. Hook dispatch in FSM executor checks for registered interceptors before key operations

## API/Interface

```python
class LLExtension(Protocol):
    def on_event(self, event: LLEvent) -> None: ...

class InterceptorExtension(LLExtension, Protocol):
    def before_route(self, context: RouteContext) -> RouteDecision | None: ...
    def after_route(self, context: RouteContext) -> None: ...

class ActionProviderExtension(LLExtension, Protocol):
    def provided_actions(self) -> dict[str, ActionRunner]: ...

class EvaluatorProviderExtension(LLExtension, Protocol):
    def provided_evaluators(self) -> dict[str, Evaluator]: ...
```

## Use Case

A compliance extension intercepts `before_issue_close` and blocks closure unless an external approval system has signed off. A Slack extension contributes an `action: slack-notify` type that loops use to send messages at specific states.

## Acceptance Criteria

- [ ] `InterceptorExtension` Protocol defined with at least `before_route` and `after_route`
- [ ] `ActionProviderExtension` Protocol defined; contributed actions usable in loop YAML
- [ ] Extension priority/ordering enforced at registration time
- [ ] Existing observe-only extensions continue to work unchanged
- [ ] At least one reference interceptor extension demonstrates the API

## Impact

- **Priority**: P4 - Strategic; depends on FEAT-911 being implemented first
- **Effort**: Large - Extends core execution path with hook dispatch
- **Risk**: High - Interceptors in the execution path add complexity and potential for misbehaving extensions to break loops
- **Breaking Change**: No (additive to FEAT-911's extension Protocol)
- **Depends On**: FEAT-911

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM executor architecture and action runner protocol |
| architecture | docs/reference/API.md | Extension type exports and public API surface |

## Labels

`feat`, `extension-api`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
