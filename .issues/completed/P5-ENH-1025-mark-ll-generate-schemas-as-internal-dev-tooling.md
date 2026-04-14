---
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1025: Mark ll-generate-schemas as internal dev tooling

## Summary

`ll-generate-schemas` is an internal developer tool that generates JSON Schema files for all 19 LLEvent types into `docs/reference/schemas/`. It is not intended for end users and is explicitly listed in `CONTRIBUTING.md` as a required dev step when modifying event types. However, the module has no inline comment distinguishing it from the public-facing CLI tools, which could cause future confusion when auditing the tool list.

## Current Behavior

`scripts/little_loops/cli/__init__.py` line 31 imports `main_generate_schemas` without any inline annotation distinguishing it as internal:
```python
from little_loops.cli.schemas import main_generate_schemas
```

And it appears in `__all__` alongside all public tools at line 45.

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

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/__init__.py:31` — Add `# internal: dev tooling` inline comment to `main_generate_schemas` import
- `scripts/little_loops/cli/__init__.py:45` — Add `# internal: dev tooling` inline comment to `__all__` entry
- `scripts/little_loops/cli/__init__.py:18` — Optionally append `(internal: dev tooling)` to the module docstring listing for `ll-generate-schemas`

### Dependent Files (Callers/Importers)
- `scripts/pyproject.toml:63` — `ll-generate-schemas = "little_loops.cli:main_generate_schemas"` — TOML allows standalone `#` comment line above this entry to note it is internal

### Similar Patterns
- `scripts/little_loops/cli/__init__.py:55` — `# Re-exported for backward compatibility (used in tests)` — the only existing inline block comment in this file; the proposed `# internal: dev tooling` follows the same inline comment style

### Tests
- `scripts/tests/test_generate_schemas.py` — existing test coverage for `main_generate_schemas`; no changes needed (comment-only change)

### Documentation
- `CONTRIBUTING.md` — already describes `ll-generate-schemas` as a required dev step when modifying event types; no changes needed

## Implementation Steps

1. Edit `scripts/little_loops/cli/__init__.py:31` — append `# internal: dev tooling` to the `main_generate_schemas` import line
2. Edit `scripts/little_loops/cli/__init__.py:45` — append `# internal: dev tooling` to the `"main_generate_schemas"` entry in `__all__`
3. Optionally: add a `# internal: dev tooling` TOML comment line above `scripts/pyproject.toml:63` to flag the entry point
4. Run `python -m pytest scripts/tests/test_generate_schemas.py -v` to confirm no regressions (comment-only change, should pass trivially)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `cli/__init__.py:31` — current import (no comment): `from little_loops.cli.schemas import main_generate_schemas`
- `cli/__init__.py:40-59` — full `__all__` block; `"main_generate_schemas"` at line 45 is bare like all other public entries
- `cli/__init__.py:55` — only existing inline comment pattern in the file: `# Re-exported for backward compatibility (used in tests)` — confirms inline block comments are an established convention here
- `cli/__init__.py:18` — module docstring lists `ll-generate-schemas` alongside public tools without distinction
- `scripts/pyproject.toml:63` — TOML supports `#` comment on a preceding line, making annotation feasible there too
- `scripts/tests/test_generate_schemas.py` — tests exist; the comment-only change will not affect them

## Labels

`enhancement`, `cli`, `internal-tooling`, `comment-only`

## Scope Boundaries

- Only inline comments added to `scripts/little_loops/cli/__init__.py`
- Optionally, a TOML comment above the entry in `scripts/pyproject.toml`
- No functional changes, no new tests, no documentation updates required
- Out of scope: hiding `ll-generate-schemas` from the public CLI, changing behavior, or adding runtime guards

## Resolution

**Status**: `completed`
**Completed**: 2026-04-13
**Implementation**: Added `# internal: dev tooling` inline comment to the `main_generate_schemas` import (line 31) and `__all__` entry (line 45) in `scripts/little_loops/cli/__init__.py`. Added `(internal: dev tooling)` annotation to the module docstring listing (line 18). Added a TOML comment above the `ll-generate-schemas` entry point in `scripts/pyproject.toml`. All 17 tests passed.

## Session Log
- `/ll:ready-issue` - 2026-04-14T04:34:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d139a92c-4273-4445-936b-ae8d10fb8209.jsonl`
- `/ll:confidence-check` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9e338e6-4afc-4e33-ba90-47e23583f970.jsonl`
- `/ll:refine-issue` - 2026-04-14T04:31:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f2a400e-996d-40e4-b0c9-e7135c284b4f.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eba12ede-7d68-4165-af6c-e13830e98af5.jsonl`
- `/ll:manage-issue` - 2026-04-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
