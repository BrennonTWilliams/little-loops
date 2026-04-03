# FEAT-927: Wire ExtensionLoader to Live EventBus in CLI Entry Points

## Overview
Connect loaded extensions to live EventBus instances in all four CLI entry points, completing the extension architecture's consumer path.

## Phase 0: Write Tests (Red)

Add `TestWireExtensions` to `test_extension.py`:
1. `test_wire_extensions_registers_on_bus` — load NoopLoggerExtension via config, wire to EventBus, emit raw dict, verify extension received LLEvent
2. `test_wire_extensions_no_extensions` — no config, no entry points, returns empty list, bus still works
3. `test_wire_extensions_failed_load_doesnt_crash` — invalid config path, returns empty list, no exception
4. `test_wire_extensions_from_raw_event_no_mutation` — verify original dict is not mutated after emit

## Phase 1: Add `wire_extensions()` Helper

File: `scripts/little_loops/extension.py` (after `ExtensionLoader` class, ~line 130)

```python
def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
) -> list[LLExtension]:
    extensions = ExtensionLoader.load_all(config_paths)
    for ext in extensions:
        bus.register(lambda event, e=ext: e.on_event(LLEvent.from_raw_event(event)))
    if extensions:
        logger.info("Wired %d extension(s) to EventBus", len(extensions))
    return extensions
```

Key decisions:
- Use `LLEvent.from_raw_event()` (not `from_dict()`) to avoid mutating shared event dict
- Default `e=ext` capture in lambda to avoid late-binding closure bug
- Import `EventBus` from `events.py` (already imports `LLEvent`)

## Phase 2: Add `extensions` Property to BRConfig

File: `scripts/little_loops/config/core.py`

Add property after existing properties (~line 175):
```python
@property
def extensions(self) -> list[str]:
    return self._raw_config.get("extensions", [])
```

## Phase 3: Wire CLI Entry Points

### 3a: `cli/loop/run.py` (~line 161)
After `config = BRConfig(Path.cwd())` at line 157, before `return run_foreground(...)`:
```python
from little_loops.extension import wire_extensions
wire_extensions(executor.event_bus, config.extensions)
```

### 3b: `cli/loop/lifecycle.py` (~line 254)
After signal handlers at line 254, before `executor.resume()`:
```python
from little_loops.config import BRConfig
from little_loops.extension import wire_extensions
config = BRConfig(Path.cwd())
wire_extensions(executor.event_bus, config.extensions)
```

### 3c: `cli/parallel.py` (~line 225)
After `event_bus = EventBus()` at line 225, before `ParallelOrchestrator(...)`:
```python
from little_loops.extension import wire_extensions
wire_extensions(event_bus, config.extensions)
```

### 3d: `cli/sprint/run.py` (~line 389)
After `event_bus = EventBus()` at line 389, before `ParallelOrchestrator(...)`:
```python
from little_loops.extension import wire_extensions
wire_extensions(event_bus, config.extensions)
```

## Phase 4: Verify
- [ ] All existing tests pass
- [ ] New wire_extensions tests pass
- [ ] Lint clean
- [ ] Type check clean

## Success Criteria
- [ ] `ExtensionLoader.load_all()` called in all 4 CLI entry points
- [ ] Extension `on_event` callbacks receive `LLEvent` instances
- [ ] Extensions loaded from both config paths and entry points
- [ ] Failed extension loads log warnings but don't crash
- [ ] Existing behavior unchanged when no extensions configured
