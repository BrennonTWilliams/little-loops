---
id: ENH-612
type: ENH
priority: P4
status: active
title: "Add subcommand aliases to ll-issues, ll-loop, and ll-sprint"
discovered_date: 2026-03-05
discovered_by: capture-issue
confidence_score: 91
outcome_confidence: 88
---

# ENH-612: Add subcommand aliases to ll-issues, ll-loop, and ll-sprint

## Summary

Add short aliases for frequently used subcommands across `ll-issues`, `ll-loop`, and `ll-sprint` to reduce typing in interactive workflows. Argparse supports aliases natively; the primary non-trivial change is that `ll-loop` also maintains a `known_subcommands` set used for its positional-shorthand dispatch, which must include the new aliases.

## Current Behavior

All three CLIs register subcommands without aliases. Users must type full subcommand names (`list`, `impact-effort`, `refine-status`, etc.) on every invocation. `ll-loop` additionally maintains a hardcoded `known_subcommands` set in `main_loop()` for its positional-shorthand dispatch (`ll-loop fix-types` → `ll-loop run fix-types`); aliases not in that set would be misinterpreted as loop names.

## Expected Behavior

Short aliases work identically to their full subcommand names:

| Command | Subcommand | Alias |
|---------|-----------|-------|
| ll-issues | list | l |
| ll-issues | show | s |
| ll-issues | sequence | seq |
| ll-issues | impact-effort | ie |
| ll-issues | refine-status | rs |
| ll-issues | next-id | ni |
| ll-loop | run | r |
| ll-loop | list | l |
| ll-loop | status | st |
| ll-loop | show | s |
| ll-loop | history | h |
| ll-loop | test | t |
| ll-loop | simulate | sim |
| ll-loop | compile | c |
| ll-loop | validate | val |
| ll-loop | resume | res |
| ll-sprint | list | l |
| ll-sprint | show | s |
| ll-sprint | run | r |
| ll-sprint | edit | e |
| ll-sprint | analyze | a |
| ll-sprint | delete | del |

`ll-sprint create` is already short — no alias needed.

## Impact

- **Priority**: P4 — Developer ergonomics; no functional change
- **Effort**: Small — Argparse `aliases=[...]` parameter plus `known_subcommands` set update; no logic changes
- **Risk**: Low — Additive only; existing full subcommand names remain unchanged
- **Breaking Change**: No

## Scope Boundaries

**In scope:**
- Add `aliases=[...]` to each `subparsers.add_parser(...)` call in the three CLI entry points
- Add alias strings to `ll-loop`'s `known_subcommands` set so they are not misrouted as loop names
- Dispatch blocks that use `if args.command == "list":` work without change because argparse normalizes `args.command` to the canonical name, not the alias

**Out of scope:**
- Custom user-defined alias configuration
- Shell completion changes (separate concern)
- Any behavioral changes to subcommand logic

## API/Interface

```
# Before
ll-issues list
ll-issues impact-effort
ll-loop run my-loop
ll-sprint list

# After (both forms work identically)
ll-issues l
ll-issues list
ll-issues ie
ll-issues impact-effort
ll-loop r my-loop
ll-loop run my-loop
ll-sprint l
ll-sprint list
```

Argparse native support:
```python
subparsers.add_parser("list", aliases=["l"], help="List issues")
```

`args.command` after `parse_args()` returns the canonical name (`"list"`, not `"l"`), so all existing `if args.command == "list":` dispatch blocks require no modification.

## Success Metrics

- [ ] `ll-issues l`, `ll-issues s`, `ll-issues seq`, `ll-issues ie`, `ll-issues rs`, `ll-issues ni` all execute without error and produce identical output to their full-name equivalents
- [ ] `ll-loop r`, `ll-loop l`, `ll-loop st`, `ll-loop s`, `ll-loop h`, `ll-loop t`, `ll-loop sim`, `ll-loop c`, `ll-loop val`, `ll-loop res` all dispatch correctly; none are misrouted as loop names
- [ ] `ll-sprint l`, `ll-sprint s`, `ll-sprint r`, `ll-sprint e`, `ll-sprint a`, `ll-sprint del` all execute correctly
- [ ] `ll-loop --help` and `ll-issues --help` and `ll-sprint --help` show aliases alongside full names
- [ ] All existing tests in `scripts/tests/test_ll_loop_parsing.py`, `scripts/tests/test_issues_cli.py`, `scripts/tests/test_sprint.py` continue to pass unchanged

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/__init__.py` — Add `aliases=[...]` to each `subs.add_parser(...)` call (6 subcommands: `next-id`, `list`, `show`, `sequence`, `impact-effort`, `refine-status`)
- `scripts/little_loops/cli/loop/__init__.py` — Add `aliases=[...]` to each `subparsers.add_parser(...)` call (10 subcommands); also add alias strings to `known_subcommands` set (lines 36–49)
- `scripts/little_loops/cli/sprint/__init__.py` — Add `aliases=[...]` to each `subparsers.add_parser(...)` call (6 subcommands: `run`, `list`, `show`, `edit`, `delete`, `analyze`)

### Dependent Files (Callers/Importers)

- All dispatch blocks (`if args.command == "..."`) require no modification — argparse normalizes to canonical name
- `scripts/tests/test_ll_loop_execution.py` — Tests `test_test_subcommand_registered` and `test_simulate_subcommand_registered` check `known_subcommands` indirectly via `--help` invocation; will continue to pass

### Similar Patterns

- `scripts/little_loops/cli_args.py` already uses short flags (`-n`, `-q`, `-v`, `-b`, `-w`, `-t`, `-m`, `-r`) on argument parsers — same ergonomics goal at the flag level

### Tests

- `scripts/tests/test_ll_loop_parsing.py` — Local `_create_subparser_only()` helper creates its own parser without aliases; unaffected
- `scripts/tests/test_issues_cli.py` — Covers subcommand dispatch by string; `args.command` normalization means no changes needed
- `scripts/tests/test_sprint.py`, `scripts/tests/test_sprint_integration.py` — Sprint subcommand tests; unaffected

### Documentation

- No doc changes required; `--help` output self-documents aliases automatically via argparse

### Configuration

- None

## Implementation Steps

1. In `scripts/little_loops/cli/issues/__init__.py`: add `aliases=[...]` to all 6 `subs.add_parser(...)` calls
2. In `scripts/little_loops/cli/loop/__init__.py`: add `aliases=[...]` to all 10 `subparsers.add_parser(...)` calls; add all alias strings to the `known_subcommands` set
3. In `scripts/little_loops/cli/sprint/__init__.py`: add `aliases=[...]` to all 6 `subparsers.add_parser(...)` calls
4. Run `python -m pytest scripts/tests/` to confirm no regressions
5. Manually verify `ll-issues l`, `ll-loop r <loop>`, `ll-sprint l` execute correctly

## Labels

`enhancement`, `ll-issues`, `ll-loop`, `ll-sprint`, `cli`, `ergonomics`

## Session Log

- `/ll:capture-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc7a2692-cd06-48ba-917f-fc490461e29c.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: no `aliases=` in subcommand parsers for ll-issues, ll-loop, or ll-sprint
- `/ll:format-issue` - 2026-03-06T00:00:00Z - Reformatted to v2.0 ENH template; removed v1.0 "Scope" heading, added Current Behavior, Expected Behavior, Impact, API/Interface, Success Metrics, Integration Map, Labels; identified known_subcommands as key non-trivial change; verified exact file paths and line numbers against codebase
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - Readiness: 91/100 PROCEED; Outcome: 88/100 HIGH CONFIDENCE
- `/ll:ready-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a17ccb9d-9868-40e3-a073-09a98d00ef8e.jsonl` — CORRECTED: fixed API/Interface example (ll-sprint impact-effort → ll-issues impact-effort)
- `/ll:manage-issue` - 2026-03-06T00:00:00Z - IMPLEMENTED: added `aliases=[...]` to all 6 ll-issues subcommands, 10 ll-loop subcommands + updated `known_subcommands` set with 10 alias strings, 6 ll-sprint subcommands; 116 tests pass; smoke-tested aliases via `--help` invocations

## Resolution

- Added `aliases=["l"]` / `["ni"]` / `["seq"]` / `["s"]` / `["ie"]` / `["rs"]` to all 6 `subs.add_parser(...)` calls in `scripts/little_loops/cli/issues/__init__.py`
- Added `aliases=["r"]` / `["c"]` / `["val"]` / `["l"]` / `["st"]` / `["res"]` / `["h"]` / `["t"]` / `["sim"]` / `["s"]` to 10 `subparsers.add_parser(...)` calls in `scripts/little_loops/cli/loop/__init__.py`; also added all 10 alias strings to `known_subcommands` set
- Added `aliases=["r"]` / `["l"]` / `["s"]` / `["e"]` / `["del"]` / `["a"]` to all 6 `subparsers.add_parser(...)` calls in `scripts/little_loops/cli/sprint/__init__.py`
- All 116 existing tests pass unchanged; aliases verified via `--help` smoke tests

## Status

**Completed** | Created: 2026-03-05 | Completed: 2026-03-06 | Priority: P4
