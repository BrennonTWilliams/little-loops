---
id: ENH-851
type: ENH
priority: P4
status: open
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# ENH-851: Unify Example Loops with Built-in Loops

## Summary

The two harness template loops (`harness-single-shot.yaml`, `harness-multi-item.yaml`) live in `loops/examples/` instead of `loops/`, which excludes them from auto-discovery, `ll-loop list`, `ll-loop install`, and the test suite. Moving them to `loops/` makes them first-class built-ins with no functional change required.

## Current Behavior

Example loops in `loops/examples/` are second-class citizens:
- Not visible in `ll-loop list` output (the `info.py` glob is `loops/*.yaml`, not recursive)
- Cannot be installed via `ll-loop install <name>` (only scans `get_builtin_loops_dir()` which resolves to `loops/`)
- Not validated by `test_builtin_loops.py` (fixture glob `BUILTIN_LOOPS_DIR.glob("*.yaml")` is top-level only)
- Must be referenced by full explicit path (`ll-loop run loops/examples/harness-single-shot.yaml`)
- The `loops/README.md` table omits them entirely

## Expected Behavior

Harness loops are discoverable and installable like any other built-in:
- `ll-loop list` shows `harness-single-shot` and `harness-multi-item` with `[built-in]` tag
- `ll-loop install harness-single-shot` copies to `.loops/` for customization
- Both files pass schema validation in `test_builtin_loops.py`
- `loops/README.md` documents them in the table under a "Harness" category

## Motivation

The conceptual distinction between "built-in" and "example" loops is just a directory location — there's no semantic difference encoded in the schema or code. Keeping them separate creates a discovery gap: users have to know about `loops/examples/` to find harness patterns, and the test suite silently ignores them, creating risk when the schema evolves. Unifying them removes the gap with minimal change.

## Proposed Solution

1. Move `loops/examples/harness-single-shot.yaml` → `loops/harness-single-shot.yaml`
2. Move `loops/examples/harness-multi-item.yaml` → `loops/harness-multi-item.yaml`
3. Delete the now-empty `loops/examples/` directory
4. Add both to the `loops/README.md` table under a "Harness / Templates" category
5. Update any guide references in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` that point to the old `examples/` path

No code changes needed — the existing resolution, listing, install, and test infrastructure already handles any `.yaml` in `loops/`.

## Integration Map

### Files to Modify
- `loops/examples/harness-single-shot.yaml` → move to `loops/`
- `loops/examples/harness-multi-item.yaml` → move to `loops/`
- `loops/README.md` — add harness entries to category table

### Dependent Files (Callers/Importers)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `loops/examples/` paths; update to `loops/`

### Similar Patterns
- N/A (purely a file relocation)

### Tests
- `scripts/tests/test_builtin_loops.py` — no code change needed; moved files auto-included by existing glob

### Documentation
- `loops/README.md` — needs new table rows for both harness loops

### Configuration
- N/A

## Implementation Steps

1. `git mv` both files from `loops/examples/` to `loops/`
2. Remove empty `loops/examples/` directory
3. Update path references in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
4. Add harness loops to `loops/README.md` table
5. Run `test_builtin_loops.py` to confirm both files pass schema validation

## Scope Boundaries

- Do not change the content or structure of the harness YAML files
- Do not change `get_builtin_loops_dir()` or loop resolution logic (no code changes)
- Do not add a new "example" category or tag system to `ll-loop list`

## Impact

- **Priority**: P4 - Low friction issue; usability improvement with no urgency
- **Effort**: Small - File moves + two doc edits; no code changes
- **Risk**: Low - Purely additive; existing built-in infrastructure is already tested
- **Breaking Change**: No (explicit path `loops/examples/harness-*.yaml` would break, but undocumented as a stable interface)

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `dx`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ae8a776-9a67-47c4-9196-89c5316f5812.jsonl`

---

**Open** | Created: 2026-03-20 | Priority: P4
