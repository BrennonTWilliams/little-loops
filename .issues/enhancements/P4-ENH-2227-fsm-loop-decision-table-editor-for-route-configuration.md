---
id: ENH-2227
type: ENH
priority: P4
status: open
discovered_date: 2026-06-19
discovered_by: capture-issue
captured_at: '2026-06-19T15:55:37Z'
decision_needed: false
relates_to:
  - ENH-2226
learning_tests_required:
  - ruamel.yaml
---

# ENH-2227: FSM loop decision-table editor for route configuration

## Summary

Add an authoring-time tool — `ll-loop edit-routes <loop>` — that renders a loop's routing logic as an editable decision table (state × verdict → next-state), lets the user modify it in `$EDITOR` or pipe it as CSV/markdown, then writes changes back to the loop YAML. The YAML remains the single source of truth; the table is a transient editing lens.

## Motivation

FSM loop `route:` blocks are scattered across multiple states in a YAML file. There is no way to see all routing logic at a glance, spot missing verdict arms, or edit routing in a tabular format without manually hunting through YAML. For loops with many states this makes routing audits error-prone and refactoring slow.

A decision-table view collapses the entire routing topology into one readable artifact, making gaps (missing verdict arms), conflicts (duplicate targets), and unreachable states immediately visible.

## Current Behavior

There is no `edit-routes` subcommand in `ll-loop`. Routing logic must be audited manually by reading each state's `route:`, `on_yes`, `on_no`, `on_partial`, `on_error`, `on_blocked`, and `extra_routes` fields across the full YAML file. There is no consolidated view of a loop's routing topology, making it difficult to spot missing verdict arms, unreachable states, or dead-end states without scanning every state entry individually.

## Expected Behavior

```
$ ll-loop edit-routes rn-implement
```

1. Reads the loop YAML and extracts all `route:`, `on_yes`, `on_no`, `on_partial`, `on_error`, `on_blocked`, and `extra_routes` fields across every state.
2. Renders a markdown table (or `--format csv`):

```markdown
| State        | IMPLEMENT | DONE | ERROR | default |
|--------------|-----------|------|-------|---------|
| assess       | implement | done | error | —       |
| implement    | —         | done | error | assess  |
| gate         | implement | done | —     | —       |
```

3. Opens the table in `$EDITOR` (or prints to stdout with `--dry-run`).
4. On save, parses the edited table, diffs against current YAML routes, and applies changes in-place — preserving all non-route fields, comments, and YAML structure.
5. Reports any unrecognized state names introduced in the edited table as errors before writing.

### Gap/conflict detection (always-on)

Before opening the editor, print warnings for:
- Missing verdict arms (a state has `on_yes` but no `on_no` with no `default`)
- Unreachable states (no route from any other state leads there, except `initial`)
- Dead-end states (no outbound routes and not a terminal state)

## Scope Boundaries

- **In scope**: read/write of `route:`, `on_yes`, `on_no`, `on_partial`, `on_error`, `on_blocked`, `extra_routes` fields; markdown and CSV output formats; `$EDITOR` open flow; pre-edit gap/conflict warnings; round-trip fidelity (non-route YAML untouched)
- **Out of scope**: editing `action`, `evaluate`, or other state fields; visual/TUI diagram rendering (see FEAT-670); runtime route injection (see ENH-2226); creating new states from the table

## API/Interface

```
ll-loop edit-routes <loop-name> [options]

Options:
  --format {markdown,csv}   Output format for the table (default: markdown)
  --dry-run                 Print table to stdout without opening editor
  --no-warnings             Skip gap/conflict detection output
```

Exit codes: `0` = success (or no changes), `1` = parse error or unknown state in edited table, `2` = loop not found.

## Implementation Steps

1. Register `edit-routes` in `scripts/little_loops/cli/loop/__init__.py` at all **three** required locations: (a) `known_subcommands` set, (b) `subparsers.add_parser("edit-routes", ...)` with `--format {markdown,csv}`, `--dry-run`, `--no-warnings`, (c) `elif args.command == "edit-routes":` dispatch calling `cmd_edit_routes(args.loop, args, loops_dir, logger)`.
2. Create `scripts/little_loops/cli/loop/edit_routes.py` with `cmd_edit_routes()` following the `cmd_validate()` signature in `config_cmds.py:12–69`; use `resolve_loop_path()` + `load_and_validate()` from `_helpers.py` for the read pass and `YAML(typ="rt")` from `yaml_state_editor.py` for the write pass.
3. Implement `RouteTableExtractor` in `scripts/little_loops/fsm/route_table.py` — adapt `_compact_transitions()` in `info.py` to build a `dict[str, dict[str, str]]` matrix of `{state → {verdict → target}}`; enumerate all fields via `StateConfig.get_referenced_states()` pattern; explicitly handle `extra_routes` to avoid dropping custom verdict arms.
4. Implement `RouteTableRenderer.to_markdown()` using `table()` from `scripts/little_loops/cli/output.py` as the rendering backend; implement `to_csv()` with stdlib `csv` module.
5. Implement `RouteTableParser` building on `parse_validation_table()` / `TABLE_ROW_PATTERN` from `scripts/little_loops/output_parsing.py` to parse the edited table back into `{state: {verdict: new_target}}` diff; reject unknown state names (exit 1) using the reachable-state set from `_find_reachable_states()` in `validation.py`.
6. Implement `RouteTableApplier` following `replace_action()` in `yaml_state_editor.py` exactly: `YAML(typ="rt").load(path)` → mutate `CommentedMap` at `data["states"][state]["on_yes"]` etc. → `atomic_write(path, buf.getvalue())`; respect the shorthand-vs-`route:` precedence rule (modify whichever layer the state already uses).
7. Implement gap/conflict detection as `detect_routing_gaps(fsm: FSMLoop)` calling `_find_reachable_states()` for unreachable states; check shorthand presence without `default` for missing-arm warnings.
8. Implement `$EDITOR` open flow: `tempfile.NamedTemporaryFile(suffix='.md', delete=False)` → write table → `subprocess.call([os.environ.get('EDITOR', 'vi'), tmp_path])` → read back → parse; skip when `--dry-run`.
9. Add tests in `scripts/tests/test_ll_loop_edit_routes.py`; reuse `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml` and `custom-on-routing.yaml` for gap detection tests; follow `argparse.Namespace(...)` + `capsys` pattern from `test_ll_loop_commands.py`.
10. Document in `docs/reference/CLI.md` and `docs/guides/LOOPS_GUIDE.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `scripts/tests/test_cli_loop_dispatch.py` — add `("little_loops.cli.loop.edit_routes", ["cmd_edit_routes"])` to `_mock_handlers()` `handler_specs` list; without this, any `TestMainLoopDispatch` test that runs `main_loop()` will invoke the real `cmd_edit_routes` instead of a mock and fail
12. Update `scripts/tests/test_ll_loop_execution.py` — add `test_edit_routes_subcommand_registered()` to `TestCmdSimulate` using the `["ll-loop", "edit-routes", "--help"]` + `SystemExit(0)` pattern used by all other `test_*_subcommand_registered()` tests (lines 1468–1580)
13. Update `.claude/CLAUDE.md` — add `edit-routes` to the `ll-loop` CLI Tools bullet parenthetical alongside `promote-baseline`
14. Note on `atomic_write` import: `atomic_write()` lives in `scripts/little_loops/file_utils.py`, not in `yaml_state_editor.py`; import it from `file_utils` directly in `edit_routes.py` / `route_table.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — register `edit-routes` subcommand
- `docs/reference/CLI.md` — new subcommand entry
- `docs/guides/LOOPS_GUIDE.md` — authoring section

### New Files
- `scripts/little_loops/fsm/route_table.py` — extractor, renderer, parser, applier
- `scripts/little_loops/cli/loop/edit_routes.py` — `cmd_edit_routes()` handler
- `scripts/tests/test_ll_loop_edit_routes.py` — unit + integration tests

### Dependent Files (Callers/Importers)
- N/A — new subcommand; no existing code imports `route_table.py` at authoring time (entry point is `ll-loop edit-routes` CLI only)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — `ll-loop` bullet in `## CLI Tools` section mentions only `promote-baseline` in the parenthetical; add `edit-routes` alongside it [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — `_mock_handlers()` enumerates every handler module in `handler_specs`; when `cmd_edit_routes` is imported inside `main_loop()` and a test calls `main_loop()`, the unmocked handler will attempt real execution. **WILL BREAK** — add `("little_loops.cli.loop.edit_routes", ["cmd_edit_routes"])` to `handler_specs` [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — `TestCmdSimulate` has `test_*_subcommand_registered()` tests (lines 1468–1580) for every existing subcommand; `edit-routes` has no such test yet — add `test_edit_routes_subcommand_registered()` following the `["ll-loop", "edit-routes", "--help"]` + `SystemExit(0)` pattern [Agent 3 finding]

### Similar Patterns
- `scripts/little_loops/cli/loop/config_cmds.py:cmd_validate()` (lines 12–69) — model for a read-only loop inspection subcommand; signature `(loop_name, args, loops_dir, logger) -> int`; catches `FileNotFoundError`/`ValueError` from `load_and_validate()`, returns `0`/`1`
- `scripts/little_loops/fsm/schema.py:RouteConfig` — source of truth for all routing field names
- `scripts/little_loops/fsm/validation.py:_find_reachable_states` — BFS from `fsm.initial`; returns `set[str]` of all reachable state names; reuse for unreachable-state detection
- `scripts/little_loops/cli/loop/info.py:_compact_transitions()` — canonical function that already extracts all routing fields (`on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, `extra_routes`, `route.routes`, `route.default`) from a `StateConfig` into `(verdict, target)` pairs; `RouteTableExtractor` can adapt this directly instead of re-implementing route field enumeration
- `scripts/little_loops/output_parsing.py:parse_validation_table()` — existing markdown table row parser (`TABLE_ROW_PATTERN` regex); `RouteTableParser` can build on this rather than writing a new table parser from scratch
- `scripts/little_loops/cli/output.py:table()` — box-drawn (┌─┬─┐) table helper that accepts `headers: list[str]` and `rows: list[list[str]]`; returns a string; usable as the rendering backend for `RouteTableRenderer.to_markdown()`
- `scripts/little_loops/loops/yaml_state_editor.py:replace_action()` — canonical `ruamel.yaml` round-trip write-back pattern: `YAML(typ="rt").load(path)` → mutate `CommentedMap` → `yaml.dump(data, buf)` → `atomic_write(path, buf.getvalue())`; `RouteTableApplier` should follow this exactly

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Three-part subcommand registration in `__init__.py`** — adding `edit-routes` requires touching three places:
1. `known_subcommands` set (lines 52–82) — controls whether a positional arg is treated as a loop name or subcommand; add `"edit-routes"` here
2. `subparsers.add_parser("edit-routes", ...)` call with `set_defaults(command="edit-routes")` and option definitions (`--format`, `--dry-run`, `--no-warnings`)
3. `elif args.command == "edit-routes":` dispatch branch calling `cmd_edit_routes(args.loop, args, loops_dir, logger)`

**`$EDITOR` invocation — no existing precedent in codebase** — `run_background()` in `_helpers.py` is the closest subprocess pattern but is not an editor-open flow. Implementation needs: `tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False)` → write rendered table → `subprocess.call([os.environ.get('EDITOR', 'vi'), tmp_path])` → read back edited file → parse → apply.

**Shorthand vs `route:` conflict** — `_validate_state_routing()` in `validation.py` emits a `WARNING` when both shorthand fields (`on_yes`, etc.) and a `route:` block are present on the same state; the runtime resolves by giving `route:` precedence. The `RouteTableApplier` must choose one layer to write to and be consistent; recommending `route:` layer for states that already use it, shorthand layer for states that don't.

**Write-back loading path** — `load_and_validate()` uses PyYAML (`yaml.safe_load`); cannot preserve comments. For the write-back flow, use `load_loop_with_spec()` from `_helpers.py` (lines 887–908) to get both `FSMLoop` (for validation) and the raw `dict` spec, then open separately with `YAML(typ="rt")` for mutation. Never use `yaml.safe_load` for a file you intend to write back.

**`StateConfig._known_on_keys`** — the complete set of recognized `on_*` keys (including aliases `on_success` → `on_yes`, `on_failure` → `on_no`). Any key with an `on_` prefix not in this set lands in `extra_routes`. The `RouteTableExtractor` must handle `extra_routes` to avoid silently dropping custom verdict arms.

**`StateConfig.get_referenced_states()`** (lines 621–657) — already unifies all routing fields (`on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, `next`, `on_maintain`, `on_retry_exhausted`, `on_rate_limit_exhausted`, `on_throttle_hard`, `route.routes`, `route.default`, `route.error`, `extra_routes`) into one `set[str]`; use this to enumerate valid next-state candidates for the validation step after table editing.

**Test fixtures available** — `scripts/tests/fixtures/fsm/loop-with-unreachable-state.yaml` and `custom-on-routing.yaml` exist in `scripts/tests/fixtures/fsm/`; reuse these for gap detection and `extra_routes` test cases rather than writing new fixtures from scratch.

### Tests
- Round-trip: extract → render → parse → apply produces identical YAML (modulo whitespace) when no edits made
- Gap detection: loop with missing `on_no` arm triggers warning; loop with unreachable state triggers warning
- Edit application: changing a target state in the table updates the correct YAML field; non-route fields untouched
- Unknown-state error: introducing a nonexistent state name in the edited table exits 1 with clear message
- `--dry-run`: prints table to stdout, does not open editor, does not write YAML

### Configuration
- N/A — no new config keys or schema changes required

## Impact

- **Priority**: P4 - Quality-of-life authoring improvement; not blocking core functionality
- **Effort**: Medium - New subcommand + round-trip table parser/applier; `ruamel.yaml` round-trip is the trickiest piece
- **Risk**: Low - Read-only path (dry-run/warnings) is zero-risk; write path is additive and gated on user save
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `routing`, `authoring`, `cli`

## Status

**Open** | Created: 2026-06-19 | Priority: P4

---

## Session Log
- `/ll:wire-issue` - 2026-06-19T16:17:26 - `75a1d8f3-0162-4b62-ade2-3ec63db853a4.jsonl`
- `/ll:refine-issue` - 2026-06-19T16:08:16 - `3f849637-ef14-45df-ac0b-e882ddd94825.jsonl`
- `/ll:format-issue` - 2026-06-19T16:00:14 - `f74d9864-172e-4f8c-9fa2-9e903b4e36a4.jsonl`
- `/ll:capture-issue` - 2026-06-19T15:55:37Z - `0e874f66-f078-4a5f-b47b-3256b06fe84f.jsonl`
