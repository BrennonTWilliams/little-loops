---
id: ENH-851
type: ENH
priority: P4
status: completed
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
- `scripts/tests/test_builtin_loops.py:22-27` — fixture glob auto-includes moved files
- `scripts/tests/test_builtin_loops.py:46-72` — `test_expected_loops_exist` uses exact set equality; **must add `"harness-single-shot"` and `"harness-multi-item"` to the `expected` set**
- `scripts/tests/test_review_loop.py:187-198` — parameterized `test_builtin_loops_are_valid`; picks up moved files automatically via `LOOPS_DIR.glob("*.yaml")`

### Documentation
- `loops/README.md` — needs new table rows for both harness loops

### Configuration
- N/A

## Implementation Steps

1. `git mv` both files from `loops/examples/` to `loops/`
2. Remove empty `loops/examples/` directory
3. Update the `# Usage:` comments in each moved YAML file (lines 11-12 of `harness-single-shot.yaml`, lines 12-13 of `harness-multi-item.yaml`) from `loops/examples/harness-*.yaml` → `loops/harness-*.yaml`
4. Update path references in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (8+ occurrences at lines ~426, 496, 547–552, 559, 560, 574, 575, 583–585, 607, 715–717)
5. Add harness loops to `loops/README.md` table under a new "Harness / Templates" category
6. Update `scripts/tests/test_builtin_loops.py:46-72` — add `"harness-single-shot"` and `"harness-multi-item"` to the `expected` set in `test_expected_loops_exist`
7. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_review_loop.py -v` to confirm schema validation passes for both files

### Critical Test Requirement (Step 6)

`test_expected_loops_exist` (`test_builtin_loops.py:46-72`) asserts `expected == actual` using exact set equality. The current `expected` set lists exactly 21 names (no harness entries). Moving the files to `loops/` makes them discoverable by the glob (`actual` grows to 23), but **the test will fail until `expected` is updated**. This is the only code change required.

## Scope Boundaries

- Do not change `get_builtin_loops_dir()` or loop resolution logic — no production code changes needed
- Do not add a new "example" category or tag system to `ll-loop list`
- The harness YAML structure/schema should not change — only the `# Usage:` path comments and directory location

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
- `/ll:ready-issue` - 2026-03-21T02:59:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b414242a-7c10-49f7-aa41-bdbd5cdf4644.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a45f8274-0823-4329-a446-ba23ffbf5ad8.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:52:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b97e6f95-4e3d-4b42-9409-9b35dfe09ebe.jsonl`

- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ae8a776-9a67-47c4-9196-89c5316f5812.jsonl`

## Resolution

- Moved `loops/examples/harness-single-shot.yaml` → `loops/harness-single-shot.yaml`
- Moved `loops/examples/harness-multi-item.yaml` → `loops/harness-multi-item.yaml`
- Deleted empty `loops/examples/` directory
- Updated `# Usage:` comments in both YAML files to use built-in name (`ll-loop run harness-*`)
- Updated all 8 `loops/examples/` path references in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`
- Added "Harness / Templates" section to `loops/README.md`
- Added `"harness-single-shot"` and `"harness-multi-item"` to `test_expected_loops_exist` expected set
- All 36 `test_builtin_loops.py` tests pass

---

**Completed** | Created: 2026-03-20 | Priority: P4
