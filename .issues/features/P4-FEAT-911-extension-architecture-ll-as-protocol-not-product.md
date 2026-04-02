---
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# FEAT-911: Extension Architecture — little-loops as a Protocol, not a Product

## Summary

Design and implement an explicit extension point into the plugin: a published schema/event bus that external packages can hook into. The OSS plugin emits structured data (loop state, issue history, FSM transitions); external tools consume it. Each experiment lives in its own repo but is a "first-class ll extension."

## Current Behavior

little-loops has no formal extension API. All integrations must live inside the plugin repo, making the OSS/commercial boundary a directory boundary rather than an API surface.

## Expected Behavior

External packages can hook into little-loops via a stable, published schema/event bus. The plugin emits structured events (loop state changes, issue history updates, FSM transitions); consumers subscribe without forking or patching the core. New experiments ship as independent repos that are recognized as first-class ll extensions.

## Motivation

Forces clean architectural thinking — the OSS/commercial boundary becomes the API surface, not a directory. This is the correct long-term shape for a plugin that wants to stay lean at its core while supporting a growing ecosystem of specialized tooling.

## Proposed Solution

TBD - requires investigation

Define and publish an event/schema contract:
- Identify emission points: FSM transitions, loop lifecycle hooks, issue state changes
- Design a structured payload format (JSON Schema or dataclass protocol)
- Decide transport: file-based (append-only log), in-process callbacks, or IPC
- Define extension discovery mechanism (e.g., entry points, config key, directory convention)

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- TBD - new config keys if needed

## Implementation Steps

1. Audit current emission points (FSM executor, ll-loop, ll-auto, ll-parallel, issue lifecycle)
2. Design event schema and transport layer (start minimal: file-based event log)
3. Define extension discovery convention
4. Implement emitter in core with a no-op default consumer
5. Build one reference extension to validate the API surface
6. Publish schema as part of plugin manifest

## Use Case

A commercial tool wants to consume loop state transitions to update a dashboard. It runs alongside ll without touching plugin source — it simply subscribes to the event stream ll emits.

## API/Interface

```python
# Conceptual extension hook
class LLExtension(Protocol):
    def on_event(self, event: LLEvent) -> None: ...

# Emitted event shape
@dataclass
class LLEvent:
    type: str           # "fsm.transition" | "issue.created" | "loop.complete"
    timestamp: str
    payload: dict       # type-specific data
```

## Acceptance Criteria

- [ ] Extension contract documented as a published schema
- [ ] At least one emission point wired to the event bus
- [ ] Reference extension (even a no-op logger) demonstrates the API works
- [ ] No breaking changes to existing ll behavior when no extensions are registered

## Impact

- **Priority**: P4 - Strategic architecture; no current blocker; significant upfront design cost
- **Effort**: Large - New cross-cutting abstraction affecting multiple subsystems
- **Risk**: High - Easy to over-engineer before knowing what extensions actually need; premature abstraction risk is real
- **Breaking Change**: No (additive)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `architecture`, `extension-api`, `captured`

---

## Status

**Open** | Created: 2026-04-01 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-04-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1dc851d2-a56a-4f1d-8be1-ae404b7f7f2e.jsonl`
