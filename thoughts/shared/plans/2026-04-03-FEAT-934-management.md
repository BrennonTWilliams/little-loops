# Implementation Plan: FEAT-934 — Add prompt-across-issues Built-in Loop

**Date**: 2026-04-03
**Issue**: P3-FEAT-934-add-prompt-across-issues-built-in-loop.md

## Summary

Create a new FSM loop `prompt-across-issues` that accepts an arbitrary prompt string
and runs it sequentially against each open/active issue using a temp-file pending list.

## State Flow

`init → discover → prepare_prompt → execute → advance → (loop: discover | done | error)`

## Phase 0: Write Tests (Red)

- [x] Add `"prompt-across-issues"` to `test_expected_loops_exist` expected set
- [x] Add `TestPromptAcrossIssuesLoop` class to `test_builtin_loops.py`
- [x] Run tests → verify they fail (loop file doesn't exist yet)

## Phase 1: Create Loop YAML

- [ ] Create `scripts/little_loops/loops/prompt-across-issues.yaml`
  - `init`: validate `${context.input}`; build pending list; `on_yes: discover`, `on_error: error`
  - `discover`: head -1 pending file; `capture: current_item`; `on_yes: prepare_prompt`, `on_no: done`
  - `prepare_prompt`: shell sed substitution; `capture: final_prompt`; `next: execute`
  - `execute`: `action: "${captured.final_prompt.output}"`; `action_type: prompt`; `max_retries: 3`; `next: advance`
  - `advance`: remove head from pending file; `next: discover`
  - `done`: `terminal: true`
  - `error`: `terminal: true`

## Phase 2: Update README

- [ ] Add entry to `scripts/little_loops/loops/README.md` under Issue Management section

## Phase 3: Verify

- [ ] `python -m pytest scripts/tests/test_builtin_loops.py -v` — all tests pass
- [ ] `python -m pytest scripts/tests/ -v` — full suite passes
- [ ] `ruff check scripts/` — no lint errors

## Key Design Decisions

- Use temp-file iteration (not live `ll-issues list` each discover call) to avoid infinite loop
- Cross-platform sed: use `tail -n +2 file > file.tmp && mv file.tmp file` instead of `sed -i ''`
- Shell variable escaping: `$${COUNT}` in YAML → `${COUNT}` in shell
- `{issue_id}` substitution done via shell sed in `prepare_prompt` state (FSM only handles `${...}`)
