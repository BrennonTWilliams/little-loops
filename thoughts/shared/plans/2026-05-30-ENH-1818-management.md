# Implementation Plan: ENH-1818 — Smoke Test State for html-website-generator

## Summary

Add a `smoke_test` shell state between `score` and `done` in the html-website-generator loop that runs Playwright-powered functional checks (console errors, text content, interactive elements) before accepting the artifact. Also fix a pre-existing test naming discrepancy (`evaluate` → `capture`).

## Changes

### 1. `scripts/little_loops/loops/html-website-generator.yaml`
- **Line 135**: Change `on_yes: done` → `on_yes: smoke_test`
- **After line 137**: Insert `smoke_test` state using Playwright via `@playwright/test` (existing codebase dependency), following the `svg-textgrad.yaml` `verify_score` pattern with compound token `SMOKE_PASS`

### 2. `scripts/tests/test_builtin_loops.py` (TestHtmlWebsiteGeneratorLoop)
- Fix pre-existing naming bug: `"evaluate"` → `"capture"` in 5 tests
- `test_required_states_exist`: add `"smoke_test"` to required set
- `test_score_state_routes_to_done_on_pass`: `"done"` → `"smoke_test"`
- Add `test_smoke_test_state_is_shell`
- Add `test_smoke_test_routes_to_done_on_pass`
- Add `test_smoke_test_routes_to_generate_on_fail`

### 3. `docs/guides/LOOPS_GUIDE.md`
- FSM flow diagram: `ALL_PASS → done` → `ALL_PASS → smoke_test → done`
- Prose: mention smoke test verification step

## Verification
- `python -m pytest scripts/tests/test_builtin_loops.py::TestHtmlWebsiteGeneratorLoop -v`
- `ll-loop validate html-website-generator`
- `ruff check scripts/`
