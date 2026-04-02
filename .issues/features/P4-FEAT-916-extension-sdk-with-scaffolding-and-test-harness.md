---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# FEAT-916: Extension SDK with Scaffolding Command and Test Harness

## Summary

Provide developer experience tooling for extension authors: an `ll create-extension` command that scaffolds a new extension repo with correct `pyproject.toml` entry points, a skeleton `on_event` handler, and a test harness (`LLTestBus`) that replays recorded `.events.jsonl` files through extensions for offline testing. Auto-generate JSON Schema documentation from typed event dataclasses.

## Context

Identified from conversation reviewing FEAT-911's "unconstrained vision." Without scaffolding and test tooling, every extension author must reverse-engineer the setup from docs alone. A proper SDK lowers the barrier to building extensions.

## Current Behavior

No extension system exists yet (FEAT-911 pending). Once FEAT-911 ships, extension authors would need to manually configure `pyproject.toml` entry points, implement the Protocol from scratch, and run real loops to test their extensions.

## Expected Behavior

- `ll create-extension <name>` scaffolds a new directory/repo with:
  - `pyproject.toml` with correct `[project.entry-points."little_loops.extensions"]`
  - Skeleton `on_event` handler implementing `LLExtension` Protocol
  - Example test using `LLTestBus`
- `LLTestBus` class loads a recorded `.events.jsonl`, replays events through an extension, and exposes `recorded_events` for assertions — no real loop execution needed
- JSON Schema auto-generated from `LLEvent` typed dataclasses and published as part of the extension SDK

## Motivation

Extension ecosystems live or die on developer experience. Scaffolding eliminates boilerplate; the test harness eliminates the need to run full loops during development; published schemas let non-Python tools validate events.

## Proposed Solution

1. Create `ll create-extension` CLI command (new entry point in `scripts/pyproject.toml`)
2. Add scaffolding templates under `templates/extension/` with Jinja2 or string substitution
3. Implement `LLTestBus` in `scripts/little_loops/testing.py` — reads JSONL, replays through extension's `on_event`, collects results
4. Add JSON Schema generation script that introspects `LLEvent` dataclass hierarchy and outputs `.json` schema files
5. Include the test harness and schema as part of `pip install little-loops[dev]`

## API/Interface

```python
# Test harness
from little_loops.testing import LLTestBus

bus = LLTestBus.from_jsonl("path/to/recorded.events.jsonl")
bus.register(MyExtension())
bus.replay()
assert len(bus.delivered_events) == 15
assert bus.delivered_events[0].type == "loop_start"
```

```bash
# Scaffolding
ll create-extension my-dashboard-ext
# Creates: my-dashboard-ext/
#   pyproject.toml (with entry point)
#   my_dashboard_ext/__init__.py
#   my_dashboard_ext/extension.py (skeleton)
#   tests/test_extension.py (with LLTestBus example)
```

## Use Case

A developer wants to build a Grafana dashboard extension. They run `ll create-extension grafana-dashboard`, get a working skeleton, write their event handler, test it against recorded events from a real loop run, and publish to PyPI.

## Acceptance Criteria

- [ ] `ll create-extension <name>` produces a working, installable extension skeleton
- [ ] Skeleton extension passes its own generated test suite out of the box
- [ ] `LLTestBus` can replay `.events.jsonl` files and expose delivered events for assertions
- [ ] JSON Schema generated from `LLEvent` hierarchy is valid and published
- [ ] Documentation covers the full create → develop → test → publish workflow

## Impact

- **Priority**: P4 - Developer experience; valuable once extension ecosystem has traction
- **Effort**: Medium - Scaffolding is straightforward; test harness needs careful API design
- **Risk**: Medium - Schema generation from dataclasses requires maintenance as events evolve
- **Breaking Change**: No (new tooling only)
- **Depends On**: FEAT-911

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Extension Protocol and event type definitions |
| guidelines | CONTRIBUTING.md | Development setup patterns to model scaffolding after |

## Labels

`feat`, `extension-api`, `developer-experience`, `captured`

---

## Status

**Open** | Created: 2026-04-02 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/233246d6-aba3-4c73-842f-437f09922574.jsonl`
