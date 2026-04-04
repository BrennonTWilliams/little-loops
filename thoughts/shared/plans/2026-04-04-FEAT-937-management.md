# FEAT-937: Shared Fragment Libraries for Cross-Loop State Reuse

**Date**: 2026-04-04  
**Status**: In Progress

## Approach

Parse-time fragment resolution: `resolve_fragments(raw_dict, loop_dir)` expands all `fragment:` references before `FSMLoop.from_dict` is called. Engine never sees `fragment:` keys.

## Implementation Steps

- [x] Phase 0: Write failing tests (`test_fsm_fragments.py`)
- [ ] Phase 1: Create `scripts/little_loops/fsm/fragments.py`
- [ ] Phase 2: Update `validation.py` (KNOWN_TOP_LEVEL_KEYS + resolve_fragments call)
- [ ] Phase 3: Update `fsm-loop-schema.json` (add import/fragments/fragment properties)
- [ ] Phase 4: Update `info.py` cmd_show (display imports)
- [ ] Phase 5: Create `scripts/little_loops/loops/lib/common.yaml`
- [ ] Phase 6: Migrate 10 built-in loops
- [ ] Phase 7: Run tests (Green)

## Key Files

- New: `scripts/little_loops/fsm/fragments.py`
- New: `scripts/tests/test_fsm_fragments.py`
- New: `scripts/little_loops/loops/lib/common.yaml`
- Modify: `scripts/little_loops/fsm/validation.py` lines 76-96 (KNOWN_TOP_LEVEL_KEYS), 479
- Modify: `scripts/little_loops/fsm/fsm-loop-schema.json`
- Modify: `scripts/little_loops/cli/loop/info.py` line 708-709
- Modify: 10 built-in loop YAML files

## Design Decisions

1. `resolve_fragments` does NOT remove `import:` or `fragments:` keys from the dict — they're left for `KNOWN_TOP_LEVEL_KEYS` to accept and `FSMLoop.from_dict` to ignore.
2. `cmd_show` reads imports from `spec.get("import", [])` (raw dict) — no need to add `imports` field to `FSMLoop`.
3. `StateConfig.from_dict` already ignores unknown keys via `.get()`, so no StateConfig changes needed.
