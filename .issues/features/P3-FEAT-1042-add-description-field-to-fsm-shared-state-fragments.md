---
id: FEAT-1042
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-11
discovered_by: capture-issue
testable: true
confidence_score: 100
outcome_confidence: 85
completed_at: 2026-04-11T00:00:00Z
---

# FEAT-1042: Add description field to FSM shared state fragments

## Summary

Add a structured `description` field to the fragment YAML schema so that each named fragment can document what it does and when it should be used. Currently, fragment intent is encoded only in YAML comments, which tooling cannot surface or validate.

## Current Behavior

Fragment libraries (`lib/common.yaml`, `lib/cli.yaml`) document fragment intent through inline YAML comments:

```yaml
fragments:
  # shell_exit: Shell command evaluated by exit code.
  # State must supply: action, on_yes, on_no (and optionally on_error, timeout)
  shell_exit:
    action_type: shell
    evaluate:
      type: exit_code
```

Comments are invisible to `resolve_fragments` in `scripts/little_loops/fsm/fragments.py` and cannot be surfaced by `ll-loop show`, `ll-loop list`, or any other tooling. Loop authors must read raw YAML to understand what a fragment provides.

## Expected Behavior

Each fragment may include an optional `description` key explaining what the fragment does and what the calling state must supply:

```yaml
fragments:
  shell_exit:
    description: |
      Shell command evaluated by exit code.
      State must supply: action, on_yes, on_no (and optionally on_error, timeout).
    action_type: shell
    evaluate:
      type: exit_code
```

`resolve_fragments` strips `description` before merging the fragment into a state so the FSM engine never sees it. Tooling can read `description` from the resolved all-fragments dict to display in `ll-loop show --fragments` or a new `ll-loop fragments` subcommand.

## Motivation

Loop authors encounter fragments by name (`fragment: shell_exit`) and must trace back to the raw library YAML to understand what fields the state must supply. A structured `description` field enables:
- `ll-loop show` or a `fragments` subcommand to list fragments with descriptions
- Schema validation to flag missing descriptions on new fragments (lint gate)
- Future IDE tooling or autocomplete to surface descriptions inline

## Use Case

A loop author writes a new loop referencing an unfamiliar fragment and runs `ll-loop fragments lib/cli.yaml` to see a table of fragment names, descriptions, and required fields — without opening the raw YAML file.

## Acceptance Criteria

- [x] `description` is a recognized optional key in the fragment schema (schema JSON updated)
- [x] `resolve_fragments` strips `description` from a fragment before merging into the state dict (FSM engine never sees it)
- [x] All existing built-in fragments in `lib/common.yaml` and `lib/cli.yaml` have `description` fields added
- [x] `ll-loop fragments <lib>` subcommand surfaces fragment names and descriptions
- [x] Existing tests still pass; new tests verify `description` is stripped during resolution

## Proposed Solution

1. **`fragments.py` (`resolve_fragments`)**: Before calling `_deep_merge(all_fragments[name], state_dict)`, pop `description` from the fragment copy so it is not merged into the state.

2. **`fsm-loop-schema.json`**: Add `description` to the allowed keys in the fragment object schema.

3. **`lib/common.yaml` + `lib/cli.yaml`**: Convert existing inline comments to `description:` block scalars.

4. **`ll-loop` CLI**: Add `fragments [lib-path]` subcommand (or `--fragments` flag on `show`) that loads a library file and prints a table of `name | description`.

## API/Interface

```python
# fragments.py — modified resolve step
frag_copy = dict(all_fragments[fragment_name])
frag_copy.pop("description", None)   # strip metadata before merge
merged = _deep_merge(frag_copy, state_dict)
```

```yaml
# Fragment schema shape (lib/*.yaml)
fragments:
  <name>:
    description: <optional str — human-readable intent + required fields>
    <...state template fields...>
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/fragments.py` — strip `description` in `resolve_fragments`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — allow `description` in fragment definitions
- `scripts/little_loops/loops/lib/common.yaml` — add `description` to each fragment
- `scripts/little_loops/loops/lib/cli.yaml` — add `description` to each fragment

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` — **no changes needed**: validates the post-resolution `FSMLoop`; fragments are consumed by `resolve_fragments` at `validation.py:494` before `FSMLoop.from_dict` at `validation.py:497`, so the engine never sees `description`
- `scripts/little_loops/cli/loop/__init__.py` — add `"fragments"` to `known_subcommands` set (lines 38–61), register `subparsers.add_parser("fragments", ...)` block (modeled after `show_parser` at lines 337–345), add dispatch branch at lines 352–375
- `scripts/little_loops/cli/loop/__init__.py:22` — import line `from little_loops.cli.loop.info import cmd_history, cmd_list, cmd_show` must also include `cmd_fragments`; missing from the four-file change in step 4 below
- `scripts/little_loops/cli/loop/info.py` — implement `cmd_fragments` handler here (alongside `cmd_show`, `cmd_list`, `cmd_history`); access fragment definitions via `load_loop_with_spec` from `_helpers.py:131–152` which returns the raw YAML spec

_Wiring pass added by `/ll:wire-issue`:_

### Tests
- `scripts/tests/test_fsm_fragments.py` — add test: `description` stripped during resolution, not present in merged state; model after the `assert "fragment" not in state` pattern at lines 132 and 185
- Existing fragment resolution tests should pass unchanged

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_commands.py` — new `TestCmdFragments` class for `cmd_fragments` handler; follow `TestCmdShowJson` pattern at lines 2390–2477 (`capsys` + `argparse.Namespace` + assert `result == 0`)
- `scripts/tests/test_ll_loop_parsing.py` — new test asserting `ll-loop fragments <lib>` routes to `cmd_fragments`; follow `TestLoopJsonShortForm` patch pattern at lines 461–478
- `scripts/tests/test_ll_loop_execution.py` — assert `"fragments"` is present in `known_subcommands`; follow `test_test_subcommand_registered` / `test_simulate_subcommand_registered` pattern
- **Ordering risk**: `test_builtin_loops.py:36` (`test_all_validate_as_valid_fsm`) and `test_fsm_fragments.py:822` (`TestBuiltinLoopMigration`) will fail if `lib/common.yaml` or `lib/cli.yaml` get `description` fields before `fragments.py` strips them — implement step 1 (`fragments.py` change) before step 3 (lib YAML edits)

### Documentation
- `scripts/little_loops/loops/README.md` — document `description` field in fragment authoring guide

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1657–1783` — "Reusable State Fragments" section shows fragment YAML format and built-in library tables without `description`; update format example and both tables to include the new optional field
- `skills/create-loop/reference.md:646–678` — `fragments (Optional)` field reference shows fragment YAML without `description`; add `description:` to the example object so loop authors discover it
- `docs/reference/CLI.md` — `ll-loop` subcommand reference (lines 230–370) has no entry for `fragments`; add heading, synopsis, and usage example matching the other subcommand entries

### Configuration
- N/A

## Implementation Steps

1. **`fragments.py:136–137`** — Before `_deep_merge`, copy the fragment dict and pop `description` from the copy so it never merges into the state:
   ```python
   frag_copy = dict(all_fragments[fragment_name])
   frag_copy.pop("description", None)   # strip metadata before merge
   merged = _deep_merge(frag_copy, state_dict)
   del merged["fragment"]
   ```
2. **`fsm-loop-schema.json:158–162`** — Replace `"additionalProperties": true` on the `fragments` object with a typed `additionalProperties` schema that declares `description` as an optional string property (all other fragment keys remain allowed via inner `additionalProperties: true`)
3. **`lib/common.yaml`** (4 fragments) and **`lib/cli.yaml`** (11 fragments) — Convert inline `# ...` comments to `description: |` block scalars on each fragment definition
4. **CLI subcommand** — Four-file change:
   - `cli/loop/__init__.py:38–61` — add `"fragments"` to `known_subcommands`
   - `cli/loop/__init__.py:337–346` — add `subparsers.add_parser("fragments", ...)` block after `show_parser`, same pattern
   - `cli/loop/info.py` — implement `cmd_fragments(name_or_path, args, loops_dir, logger)` that calls `load_loop_with_spec` (from `_helpers.py:131–152`), reads `spec["fragments"]`, and prints a table of `name | description`; use the `_load_loop_meta` / `cmd_list` display pattern (info.py:28–41, 166–172)
   - `cli/loop/__init__.py:352–375` — add `elif args.command == "fragments": return cmd_fragments(...)` dispatch branch
5. **`test_fsm_fragments.py`** — Add test asserting `"description" not in state` after `resolve_fragments`; also add integration test loading a real fragment with `description` from `lib/common.yaml` via the `loops_dir` path pattern (lines 560–584)
6. **`loops/README.md`** — Document `description` field in fragment authoring guide

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **`cli/loop/__init__.py:22`** — Add `cmd_fragments` to the import: `from little_loops.cli.loop.info import cmd_history, cmd_list, cmd_show, cmd_fragments`
8. **`test_ll_loop_commands.py`** — Add `TestCmdFragments` class testing `cmd_fragments` handler (follow `TestCmdShowJson` at lines 2390–2477); assert `result == 0` and verify table output contains fragment names/descriptions
9. **`test_ll_loop_parsing.py`** — Add test verifying `ll-loop fragments <lib>` routes to `cmd_fragments` (follow patch pattern at lines 461–478)
10. **`test_ll_loop_execution.py`** — Add assertion that `"fragments"` is in `known_subcommands` (follow `test_test_subcommand_registered` pattern)
11. **`docs/guides/LOOPS_GUIDE.md:1657–1783`** — Update fragment YAML format example and both built-in library tables to show the optional `description:` field
12. **`skills/create-loop/reference.md:646–678`** — Update `fragments (Optional)` YAML example to include `description:` field
13. **`docs/reference/CLI.md`** — Add `ll-loop fragments` subcommand entry (heading, synopsis, usage example)

## Impact

- **Priority**: P3 — Improves loop author experience; no blocking urgency
- **Effort**: Small — core change is ~5 lines in `fragments.py`; most work is adding descriptions to existing fragments
- **Risk**: Low — `description` removal is additive and isolated to parse time; existing loops unaffected
- **Breaking Change**: No — `description` is optional; existing fragment files with no `description` continue to work

## Related Key Documentation

- `scripts/little_loops/loops/README.md` — Fragment authoring guide (needs `description` field added)
- `scripts/little_loops/fsm/fsm-loop-schema.json` — Fragment schema definition at lines 158–162
- `scripts/little_loops/loops/lib/common.yaml` — 4 fragments to convert (shell_exit, retry_counter, llm_gate, numeric_gate)
- `scripts/little_loops/loops/lib/cli.yaml` — 11 CLI fragments to convert

## Labels

`feature`, `fsm-loops`, `fragments`, `dx`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-04-11T20:58:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e8c752a5-44fe-4905-8364-2b3caae715c6.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11b55a8-6268-4da2-acf5-b185d14859ce.jsonl`
- `/ll:wire-issue` - 2026-04-11T20:39:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/35573571-1f84-410f-9008-7381f53f7b56.jsonl`
- `/ll:refine-issue` - 2026-04-11T20:26:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c6b466e-e8fd-4bc0-86d9-6515099fe37d.jsonl`

- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd3ee4fa-61fe-4186-bd96-b1eec470766e.jsonl`

---

## Resolution

Implemented 2026-04-11.

- `fragments.py`: pops `description` from fragment copy before `_deep_merge` so the FSM engine never sees it
- `fsm-loop-schema.json`: `fragments.additionalProperties` is now a typed object schema with an optional `description: string` property
- `lib/common.yaml`, `lib/cli.yaml`: all 16 fragments have `description:` block scalars replacing inline comments
- `ll-loop fragments <lib>`: new subcommand in `info.py` + `__init__.py` that prints a table of fragment names and first-line descriptions
- Tests: 5 new tests in `test_fsm_fragments.py`, 4 in `test_ll_loop_commands.py`, 1 in `test_ll_loop_parsing.py`, 1 in `test_ll_loop_execution.py` (365 → total suite 4596 pass)
- Docs: `loops/README.md`, `LOOPS_GUIDE.md`, `CLI.md`, `skills/create-loop/reference.md` updated

## Status

**Completed** | Created: 2026-04-11 | Priority: P3
