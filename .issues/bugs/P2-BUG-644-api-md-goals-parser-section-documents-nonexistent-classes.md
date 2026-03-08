---
id: BUG-644
type: BUG
priority: P2
status: active
title: "API.md goals_parser section documents nonexistent classes PersonaGoals and PriorityGoals"
created: 2026-03-07
---

# BUG-644: API.md goals_parser section documents nonexistent classes PersonaGoals and PriorityGoals

## Problem

The `goals_parser` section in `docs/reference/API.md` (~lines 982–1056) documents a completely fictional class hierarchy. The classes `PersonaGoals` and `PriorityGoals` do not exist anywhere in the codebase. The `ProductGoals` class schema is also wrong. Any code following this documentation will fail with `ImportError`.

## Findings

### Documented (wrong)

```python
class ProductGoals:
    personas: dict[str, PersonaGoals] | None = None
    priorities: dict[str, PriorityGoals] | None = None

class PersonaGoals:
    persona: str; description: str; priorities: list[str]

class PriorityGoals:
    priority: str; description: str; categories: list[str]
```

### Actual code

```python
class ProductGoals:
    version: str
    persona: Persona | None          # singular typed Persona, not dict[str, PersonaGoals]
    priorities: list[Priority]       # list of Priority objects, not dict[str, PriorityGoals]
    raw_content: str = ""

class Persona:                       # not PersonaGoals
    id: str; name: str; role: str

class Priority:                      # not PriorityGoals
    id: str; name: str
```

The usage example (~line 1043) constructs `PersonaGoals(...)` which cannot import.

## Files

- `docs/reference/API.md` — lines ~982–1056
- `scripts/little_loops/goals_parser.py` — actual source

## Fix

Rewrite the `goals_parser` section to document the actual classes:
- `ProductGoals` with correct fields (`version`, `persona`, `priorities`, `raw_content`)
- `Persona` (replacing `PersonaGoals`) with fields `id`, `name`, `role`
- `Priority` (replacing `PriorityGoals`) with fields `id`, `name`
- Update all usage examples to use the real class names and field shapes
