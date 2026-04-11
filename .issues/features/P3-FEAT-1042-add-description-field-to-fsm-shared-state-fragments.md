---
id: FEAT-1042
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-11
discovered_by: capture-issue
testable: true
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

- [ ] `description` is a recognized optional key in the fragment schema (schema JSON updated)
- [ ] `resolve_fragments` strips `description` from a fragment before merging into the state dict (FSM engine never sees it)
- [ ] All existing built-in fragments in `lib/common.yaml` and `lib/cli.yaml` have `description` fields added
- [ ] `ll-loop show` (or a new `ll-loop fragments <lib>` subcommand) surfaces fragment names and descriptions
- [ ] Existing tests still pass; new test verifies `description` is stripped during resolution

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
- `scripts/little_loops/fsm/validation.py` — validate fragment schema; may need update
- `scripts/little_loops/cli/loop_cli.py` (or equivalent) — add `fragments` display subcommand

### Tests
- `scripts/tests/test_fragments.py` — add test: `description` stripped during resolution, not present in merged state
- Existing fragment resolution tests should pass unchanged

### Documentation
- `scripts/little_loops/loops/README.md` — document `description` field in fragment authoring guide

### Configuration
- N/A

## Implementation Steps

1. Update `resolve_fragments` to strip `description` before merging a fragment into a state
2. Update `fsm-loop-schema.json` to allow `description` in fragment entries
3. Add `description` block scalars to all fragments in `lib/common.yaml` and `lib/cli.yaml`
4. Add `ll-loop fragments <lib>` subcommand (or extend `ll-loop show`) to print fragment descriptions
5. Add/update tests covering description stripping
6. Update `loops/README.md` fragment authoring docs

## Impact

- **Priority**: P3 — Improves loop author experience; no blocking urgency
- **Effort**: Small — core change is ~5 lines in `fragments.py`; most work is adding descriptions to existing fragments
- **Risk**: Low — `description` removal is additive and isolated to parse time; existing loops unaffected
- **Breaking Change**: No — `description` is optional; existing fragment files with no `description` continue to work

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `fsm-loops`, `fragments`, `dx`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd3ee4fa-61fe-4186-bd96-b1eec470766e.jsonl`

---

## Status

**Open** | Created: 2026-04-11 | Priority: P3
