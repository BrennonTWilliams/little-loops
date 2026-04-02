# ENH-922: Add Extension API Section to Reference Docs

## Plan

### Phase 1: Module Overview Table
- Add two rows to the table at `docs/reference/API.md:22-54`:
  - `little_loops.events` — Structured events and EventBus dispatcher
  - `little_loops.extension` — Extension protocol, loader, and reference implementation
- Insert after `little_loops.state` row (line 35) since events/extension are core infrastructure

### Phase 2: Add `## little_loops.events` Section (append after line 4911)
- `EventCallback` type alias
- `LLEvent` dataclass (fields, `to_dict()`, `from_dict()`, `from_raw_event()`)
- `EventBus` class (constructor, `register()`, `unregister()`, `add_file_sink()`, `emit()`, `read_events()`)
- Quick-usage example

### Phase 3: Add `## little_loops.extension` Section
- `ENTRY_POINT_GROUP` constant
- `LLExtension` Protocol
- `NoopLoggerExtension` class
- `ExtensionLoader` static methods (`from_config()`, `from_entry_points()`, `load_all()`)
- Configuration subsection (config key format, entry point format)
- Quick-usage example for custom extension

### Patterns to Follow
- Dataclass: `@dataclass` code block + inline comments, optional `#### Methods` with signature blocks
- Protocol: `####` heading, code block with `...` body, one-line description
- Class: `###` heading, usage example, `#### Constructor`, `#### Methods` table or subsections
- Config: four-column table (Key, Type, Default, Description)
- Sections separated by `---` horizontal rules between `##` sections

### Success Criteria
- [ ] Module overview table has events and extension rows
- [ ] `LLEvent`, `EventBus`, `LLExtension`, `ExtensionLoader`, `NoopLoggerExtension` documented
- [ ] Configuration and entry point formats described
- [ ] At least one code example for custom extension
- [ ] Section ordering consistent with existing file
