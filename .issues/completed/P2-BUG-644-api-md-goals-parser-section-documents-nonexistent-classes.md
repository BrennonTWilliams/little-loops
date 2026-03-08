---
id: BUG-644
type: BUG
priority: P2
status: completed
title: "API.md goals_parser section documents nonexistent classes PersonaGoals and PriorityGoals"
created: 2026-03-07
---

# BUG-644: API.md goals_parser section documents nonexistent classes PersonaGoals and PriorityGoals

## Summary

The `goals_parser` section in `docs/reference/API.md` (~lines 982–1056) documents a completely fictional class hierarchy. The classes `PersonaGoals` and `PriorityGoals` do not exist anywhere in the codebase. The `ProductGoals` class schema is also wrong. Any code following this documentation will fail with `ImportError`.

## Current Behavior

`docs/reference/API.md` lines 982–1056 document:

```python
class ProductGoals:
    personas: dict[str, PersonaGoals] | None = None
    priorities: dict[str, PriorityGoals] | None = None

class PersonaGoals:
    persona: str; description: str; priorities: list[str]

class PriorityGoals:
    priority: str; description: str; categories: list[str]
```

The usage example (~line 1043) constructs `PersonaGoals(...)` which cannot import because these classes don't exist.

## Expected Behavior

The documentation should accurately reflect the actual classes in `scripts/little_loops/goals_parser.py`:

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

## Steps to Reproduce

1. Open `docs/reference/API.md` and navigate to the `little_loops.goals_parser` section (~line 982)
2. Observe that `ProductGoals` is documented with `personas: dict[str, PersonaGoals]` and `priorities: dict[str, PriorityGoals]`
3. Attempt to import `PersonaGoals` or `PriorityGoals` from `little_loops.goals_parser`
4. Observe: `ImportError: cannot import name 'PersonaGoals' from 'little_loops.goals_parser'`

## Proposed Solution

Rewrite the `goals_parser` section in `docs/reference/API.md` to document the actual classes:

- `ProductGoals` with correct fields (`version`, `persona`, `priorities`, `raw_content`)
- `Persona` (replacing `PersonaGoals`) with fields `id`, `name`, `role`
- `Priority` (replacing `PriorityGoals`) with fields `id`, `name`
- Update all usage examples to use the real class names and field shapes

## Impact

- **Priority**: P2 - Misleading docs cause `ImportError` for anyone following the API reference
- **Effort**: Small - Documentation-only fix, no code changes needed
- **Risk**: Low - No code changes; only updating docs to match existing implementation
- **Breaking Change**: No

## Labels

`documentation`, `goals_parser`, `api-docs`

## Session Log

- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19d57f1f-86a8-4cd8-be15-a811b0ecce9d.jsonl`

## Resolution

- **Status**: Fixed
- **Date**: 2026-03-07
- **Fix**: Rewrote the `little_loops.goals_parser` section in `docs/reference/API.md` (lines 982–1076) to document the actual classes (`Persona`, `Priority`, `ProductGoals`) with correct fields and a working usage example using `ProductGoals.from_file()`.
- **Files changed**: `docs/reference/API.md`

---

**Closed** | Created: 2026-03-07 | Priority: P2
