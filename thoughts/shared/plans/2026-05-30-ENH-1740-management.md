# ENH-1740 Implementation Plan

## Summary
Add `classify_assumptions` and `record_untestable` states to `assumption-firewall.yaml`, rename `flatten_targets` → `flatten_testable`, and add empty-testable routing branch.

## Phase 0: Write Tests (Red) — TDD Mode

### Existing tests to update
- `test_run_gate_with_contains_targets_and_max_retries` (line 4012): verify `targets` interpolation references `flatten_testable` capture

### New tests to add
1. `test_classify_assumptions_has_prompt_action` — validates new state exists with `action_type: prompt`
2. `test_classify_assumptions_evaluates_output_json` — validates `output_json` evaluator on `.testable`
3. `test_record_untestable_is_shell_state` — validates new state exists with `action_type: shell`
4. `test_record_untestable_calls_ll_action_explore_api_assume` — validates `ll-action invoke explore-api` in action
5. `test_flatten_testable_reads_from_classified` — validates reads `classified.testable`
6. `test_flatten_testable_empty_routes_to_no_external_deps` — validates empty-testable branch
7. `test_parse_assumptions_next_is_classify_assumptions` — validates routing chain
8. `test_classify_assumptions_on_yes_is_record_untestable` — validates routing

### New tests for --assume / untested in learning_tests.py
9. `test_round_trip_untested_assertions` — round-trip a record with only `untested` assertions through `from_dict()/to_dict()`
10. `test_check_learning_test_surfaces_untested` — verify `check_learning_test` surfaces records with untested assertions

### New tests for CLI output in test_cli_learning_tests.py
11. `test_check_shows_untested_status` — verify `ll-learning-tests check` handles records with `result: untested` assertions

## Phase 1: Modify assumption-firewall.yaml

### 1.1 Add `classify_assumptions` state after `parse_assumptions`
- `action_type: prompt`
- LLM prompt to classify targets as testable/untestable
- Evaluate with `output_json` on `.testable` (non-LLM evaluator — satisfies MR-1)
- `on_yes: record_untestable`

### 1.2 Update `parse_assumptions` routing
- Change `on_yes: flatten_targets` → `on_yes: classify_assumptions`

### 1.3 Add `record_untestable` state
- `action_type: shell`
- Python heredoc iterates `classified.untestable`, calls `ll-action invoke explore-api --args "<target> --assume <claim>"`
- `on_error: flatten_testable` (even if empty list)
- `next: flatten_testable`

### 1.4 Rename `flatten_targets` → `flatten_testable`
- Read from `classified.testable` instead of `extracted.targets`
- Add empty-testable branch: `evaluate: output_json .testable length eq 0` → `on_yes: no_external_deps`

### 1.5 Update description at top of file

## Phase 2: Update Documentation

### 2.1 docs/guides/LOOPS_GUIDE.md (line 380)
- Update assumption-firewall entry to describe classification/testable/untestable routing

### 2.2 scripts/little_loops/loops/README.md (line 67)
- Update proof-first-task entry reference

### 2.3 docs/guides/LEARNING_TESTS_GUIDE.md
- Note auto-recording of untestable claims

## Phase 3: Run Tests (Green) — TDD Mode

- Run `python -m pytest scripts/tests/` — confirm all tests pass
- Run `ll-loop validate assumption-firewall` — confirm 0 ERRORs
