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

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- `scripts/little_loops/cli/__init__.py:29` — `from little_loops.cli.schemas import main_generate_schemas` has no inline `# internal: dev tooling` comment ✓
- `__all__` at line 42 — `"main_generate_schemas"` listed without annotation ✓
- Feature not yet implemented (comment-only change)

## Status

`backlog`

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eba12ede-7d68-4165-af6c-e13830e98af5.jsonl`
