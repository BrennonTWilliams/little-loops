---
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# ENH-1025: Mark ll-generate-schemas as internal dev tooling

## Summary

`ll-generate-schemas` is an internal developer tool that generates JSON Schema files for all 19 LLEvent types into `docs/reference/schemas/`. It is not intended for end users and is explicitly listed in `CONTRIBUTING.md` as a required dev step when modifying event types. However, the module has no inline comment distinguishing it from the public-facing CLI tools, which could cause future confusion when auditing the tool list.

## Current Behavior

`scripts/little_loops/cli/__init__.py` line 29 imports `main_generate_schemas` without any inline annotation distinguishing it as internal:
```python
from little_loops.cli.schemas import main_generate_schemas
```

And it appears in `__all__` alongside all public tools at line 42.

## Expected Behavior

A `# internal: dev tooling` inline comment on the import (and optionally the `__all__` entry) makes the internal nature explicit for future auditors:
```python
from little_loops.cli.schemas import main_generate_schemas  # internal: dev tooling
```

## Impact

- **Scope**: 1 file, 1–2 line changes (comments only)
- **Behavior change**: None
- **Risk**: None

---

## Status

`backlog`

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eba12ede-7d68-4165-af6c-e13830e98af5.jsonl`
