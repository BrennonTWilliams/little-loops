---
id: ENH-1740
type: ENH
priority: P3
status: done
captured_at: '2026-05-27T18:08:06Z'
completed_at: '2026-05-30T22:37:00Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
relates_to:
- FEAT-1696
- FEAT-1695
- EPIC-1694
parent: EPIC-1694
depends_on:
- FEAT-1743
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1740: `assumption-firewall` — record untestable claims via `--assume` flag

## Summary

Extend `assumption-firewall` so that after extracting API assumptions from an issue file, it classifies each assumption as *testable* (can run a local proof script) or *untestable* (requires live credentials, rate-limited endpoints, long-running behavior, or vendor-only environments), and records untestable ones as structured `untested` TODOs via `/ll:explore-api --assume "<claim>"` rather than silently discarding them.

## Current Behavior

`assumption-firewall` (FEAT-1696) extracts up to 7 external-API assumptions from an issue file via LLM, passes all of them to `ready-to-implement-gate`, which in turn calls `/ll:explore-api` to run a proof script. When an assumption can't be proven — because it requires live API credentials, is rate-limited, or depends on long-running behavior — the proof script fails, the record ends up `refuted`, and the gate blocks the implementation.

This is a false block: the assumption may well be correct, just impossible to prove cheaply in this environment. Today there is no way to record "I believe this is true but can't test it" as a structured TODO that persists with the LT record and gets upgraded later.

The `--assume` flag in `/ll:explore-api` exists precisely for this use case — it adds a claim with `result: untested` to the record — but `assumption-firewall` never invokes it.

## Expected Behavior

After assumption extraction, the firewall classifies each assumption before routing:

- **Testable**: passes to `ready-to-implement-gate` as before.
- **Untestable**: routed to a new `record_untestable` state that calls `/ll:explore-api <target> --assume "<claim>"` for each, creating an LT record with `result: untested` assertions.

The gate then only blocks on *testable* assumptions that are refuted. Untestable assumptions are recorded and pass through.

Downstream, `ll-learning-tests check "<target>"` will show the `untested` assertions, and `learning-tests-audit` (FEAT-1739) will surface them in its "Open TODOs" section, prompting a future developer to resolve them when the environment allows.

## Motivation

- **Eliminates false blocks.** Today a single assumption that requires a live API key blocks the entire gate. After this change, untestable claims are recorded as structured TODOs and the gate passes.
- **Closes the `--assume` loop gap.** The `--assume` flag is documented and implemented, but no built-in loop uses it. This is the natural integration point.
- **Structured TODOs that travel with the record.** An `untested` claim in a LT record is more durable than a comment or a TODO in issue prose — it's machine-readable, survives copy-paste, and gets automatically surfaced by `ll-learning-tests check`.

## Proposed Solution

### New state: `classify_assumptions`

After `parse_assumptions` (which produces `extracted.targets`), add a `classify_assumptions` prompt state that asks the LLM to classify each target as `testable` or `untestable`, emitting:

```json
{
  "testable": ["Stripe webhook signature (Stripe-Signature header)"],
  "untestable": ["Stripe rate limit: 100 req/s per webhook endpoint"],
  "rationale": "Rate-limit claims require a live Stripe account and sustained load."
}
```

Evaluate with `output_json .testable | length >= 0` (always passes — classification itself can't fail).

### New state: `record_untestable`

Shell state that iterates `captured.classified.untestable`:

```bash
python3 << 'PYEOF'
import json, subprocess
classified = json.loads("""${captured.classified.output}""")
for claim in classified.get("untestable", []):
    subprocess.run(["ll-action", "invoke", "explore-api",
                    "--args", f"{claim} --assume {claim!r}"], check=False)
PYEOF
```

Routes unconditionally to `flatten_testable` (even if list is empty).

### Modified `flatten_targets`

Change to read from `classified.testable` instead of `extracted.targets`. If `testable` is empty, route directly to `no_external_deps` (all assumptions were untestable — gate passes trivially).

### Modified routing

```
parse_assumptions → classify_assumptions → record_untestable → flatten_testable → run_gate
                                         ↘ (if testable empty) → no_external_deps
```

### State count delta

+2 states (`classify_assumptions`, `record_untestable`), 1 state renamed (`flatten_targets` → `flatten_testable`). Total: ~9 states.

## Scope Boundaries

- **In scope**: Classification of extracted assumptions into testable/untestable; recording untestable claims via `--assume` flag as LT records; routing changes for the empty-testable case (all assumptions untestable → `no_external_deps`).
- **Out of scope**: Automatically resolving or retrying untestable claims later; changing the `--assume` flag behavior itself; modifying the LT record schema; handling assumptions that become testable in future environments.

## Implementation Steps

1. Read `scripts/little_loops/loops/assumption-firewall.yaml` in full.
2. Add `classify_assumptions` prompt state after `parse_assumptions`. Prompt must emit JSON with `testable`, `untestable`, and `rationale` keys. Evaluate `output_json` on `.testable` to confirm structure.
3. Add `record_untestable` shell state: inline Python iterates `classified.untestable`, calls `ll-action invoke explore-api --args "<target> --assume <claim>"` for each.
4. Rename `flatten_targets` to `flatten_testable` and change it to read from `classified.testable`.
5. Add empty-testable branch: if `classified.testable` is empty, route to `no_external_deps`.
6. Update `run_gate` to receive `flatten_testable`'s output.
7. Run `ll-loop validate assumption-firewall` until no ERRORs.
8. Update `scripts/tests/test_builtin_loops.py::TestAssumptionFirewallLoop` — add assertions for the new states.
9. Update `docs/guides/LEARNING_TESTS_GUIDE.md` — note in "Pre-Seeding Assumptions" section that `assumption-firewall` now records untestable claims automatically.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `docs/guides/LOOPS_GUIDE.md` — `assumption-firewall` standalone entry (line 380) describes current behavior only; update to reflect classification into testable/untestable, `--assume` recording, and new routing branches. Also update the usage example comment (line 391).
11. Update `scripts/little_loops/loops/README.md` — `proof-first-task` entry (line 67) references assumption-firewall; minor update for new behavior.
12. Update `scripts/tests/test_builtin_loops.py::test_run_gate_with_contains_targets_and_max_retries` (line 4012) — verify `targets` interpolation source references `flatten_testable` capture, not old `flatten_targets`.
13. Add `--assume` behavioral tests to `scripts/tests/test_learning_tests.py` — round-trip a record with only `untested` assertions through `LearnTestRecord.from_dict()`; verify `check_learning_test` surfaces records with untested assertions.
14. Add CLI output test to `scripts/tests/test_cli_learning_tests.py` — verify `TestMainLearningTestsCheck` handles records containing `result: untested` assertions.
15. Verify `scripts/little_loops/generate_schemas.py` — if `explore-api --assume` emits a new event type, add a `_schema(...)` block; otherwise no change needed.

## Success Metrics

- `ll-loop validate assumption-firewall` reports 0 ERRORs after the change.
- 0 false blocks caused by untestable assumptions (previously: all untestable assumptions caused gate blocks).
- 100% of untestable assumptions produce an LT record with `result: untested`.
- `TestAssumptionFirewallLoop` passes with updated state assertions.
- Existing behavior preserved: testable-only assumptions route identically to FEAT-1696 baseline.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/assumption-firewall.yaml` — Add `classify_assumptions` and `record_untestable` states, rename `flatten_targets` → `flatten_testable`, update routing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — Receives `flatten_testable` output (indirect dependency, no change expected)
- `scripts/little_loops/loops/proof-first-task.yaml` — Wraps `assumption-firewall` as a sub-loop at `gate` state; routes on `check_gate_blocked` distinguishing `no_external_deps` from `blocked`. No change expected (gate passes through unchanged).
- `scripts/little_loops/learning_tests.py` — `ll-action invoke explore-api` calls the LT subsystem; `LearnTestRecord.from_dict()` at line 68 defaults status to `"proven"` when all assertions are `untested` (relevant: records created via `--assume` only will show as `proven` in `ll-learning-tests check`).
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — Structural sibling: also calls `ready-to-implement-gate` with `targets` + `max_retries`; no change expected.
- `scripts/little_loops/loops/integrate-sdk.yaml` — Structural sibling: same pattern; no change expected.

### Similar Patterns
- `loops/oracles/` — Other oracle loops that classify before routing; check for reusable classification patterns
- `scripts/little_loops/loops/loop-router.yaml:61-91` — `classify_goal` prompt state: LLM classifies into categories, outputs tagged line (`BRANCH:<choice>`), routes via `output_contains`. Closest pattern for the new `classify_assumptions` state.
- `scripts/little_loops/loops/ready-to-implement-gate.yaml:32-63` — `check_next` + `branch_on_verdict`: two-state cascade classifies items into `proven`/`refuted`/`needs_explore` using `output_json` on `.verdict` field with `eq` operator. Pattern for multi-way routing from a single JSON output.
- `scripts/little_loops/loops/evaluation-quality.yaml:96-121` — `route_action` → `route_issues` → `route_code`: cascade of `output_contains` evaluations routing to one of N remediation branches. Alternative classification routing pattern.
- `scripts/little_loops/loops/ready-to-implement-gate.yaml:65-82` — `explore` state: bash `for` loop calling `ll-action invoke explore-api --args "$TARGET" || true`, checking results via `ll-learning-tests check`. Direct pattern for `record_untestable` shell state.

### Tests
- `scripts/tests/test_builtin_loops.py::TestAssumptionFirewallLoop` — Add assertions for new states and routing branches

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestAssumptionFirewallLoop::test_run_gate_with_contains_targets_and_max_retries` (line 4012) — Currently checks `run_gate.with["targets"]` key existence but doesn't verify the interpolation source. After `flatten_targets` → `flatten_testable` rename, update this test to confirm `targets` binding references `flatten_testable`'s capture, not the old `flatten_targets`.
- `scripts/tests/test_learning_tests.py` — Zero behavioral tests exist for `result: untested` or `--assume` round-trip. The `sample_record` fixture (line 29) only uses `result: "pass"`. Add tests: (a) round-trip a record with only `untested` assertions through `LearnTestRecord.from_dict()` and verify assertions survive, (b) verify `check_learning_test` surfaces records with untested assertions.
- `scripts/tests/test_cli_learning_tests.py` — `TestMainLearningTestsCheck` mocks `check_learning_test` but never tests records containing `result: untested` assertions. Add a test for CLI output of records with untested assertions.

### Documentation
- `docs/guides/LEARNING_TESTS_GUIDE.md` — Note in "Pre-Seeding Assumptions" that assumption-firewall now auto-records untestable claims

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Standalone entry for `assumption-firewall` (line 380) describes current behavior as "delegates proof of each assumption to ready-to-implement-gate"; must be updated to reflect classification into testable/untestable, `--assume` recording, and the new routing branches. Also update the usage example comment (line 391).
- `scripts/little_loops/loops/README.md` — `proof-first-task` entry (line 67) references assumption-firewall; minor update for new behavior.

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py` — Currently defines 5 learning-related event types (lines 281-347): `learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_blocked`. If `explore-api --assume` emits a new event type (e.g., `learning_target_assumed` or `learning_target_untestable`), add a new `_schema(...)` block to `SCHEMA_DEFINITIONS`. If it reuses an existing event type, no change needed. Verify this during implementation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current state map** (`scripts/little_loops/loops/assumption-firewall.yaml`):
- `read_issue` (lines 14-19): `action_type: shell`, runs `cat "$(ll-issues path '${context.input}')"`, captures `issue_content`, routes `on_error: blocked`, `next: extract_assumptions`.
- `extract_assumptions` (lines 21-51): `action_type: prompt`, LLM extracts up to 7 targets, outputs `ASSUMPTIONS_JSON:{...}` on last line. `llm_structured` evaluator (min_confidence 0.5) sanity-checks structure. Both `on_yes` and `on_no` → `parse_assumptions`.
- `parse_assumptions` (lines 53-83): `action_type: shell`, inline Python parses `ASSUMPTIONS_JSON:` line, emits `{"targets": [...], "rationale": "...", "count": N}`. Evaluator `output_json .count gt 0` → `on_yes: flatten_targets`, `on_no: no_external_deps`.
- `flatten_targets` (lines 85-95): `action_type: shell`, emits comma-separated target list via `print(",".join(data["targets"]))`. Captures as `targets`. `next: run_gate`.
- `run_gate` (lines 97-104): `loop: ready-to-implement-gate`, `with: targets: "${captured.targets.output}", max_retries: "2"`. Routes `on_success: done`, `on_failure: blocked`, `on_error: blocked`.
- Terminals: `done` (line 106), `blocked` (line 109), `no_external_deps` (line 112).

**Classification pattern reference** — `loop-router.yaml:61-91` (`classify_goal` state):
- `action_type: prompt` asks LLM to classify into N categories, output tagged last line (`BRANCH:<choice>`).
- `llm_structured` evaluator with `min_confidence: 0.5` sanity-checks output format (not content).
- Shell states downstream (`route_branch_project`, `route_branch_builtin`) use `exit_code` evaluation: `sys.exit(0 if 'BRANCH:project' in output else 1)`.
- This is the best pattern for `classify_assumptions`: prompt → tagged output → shell parse → route on classification.

**Subprocess invocation pattern** — `ready-to-implement-gate.yaml:65-82` (`explore` state):
- Bash `for` loop: `ll-action invoke explore-api --args "$TARGET" || true`
- Checks result: `ll-learning-tests check "$TARGET"` parses status JSON
- Routes via `echo "RESULT=proven"` / `echo "RESULT=refuted"` + `output_contains` evaluator
- The `|| true` pattern is critical — individual invocation failures must not stop the loop.

**Alternative: Python subprocess pattern** — `ready-to-implement-gate.yaml:32-41` (`check_next` state):
- `python3 - <<'PY'` heredoc with `subprocess.run(["ll-learning-tests","check",target], capture_output=True, text=True)`
- Cleaner for iterating a JSON list and calling external commands per item.
- ENH-1740's proposed `record_untestable` uses this pattern: `subprocess.run(["ll-action", "invoke", "explore-api", "--args", f"{claim} --assume {claim!r}"], check=False)`.

**`--assume` flag behavior** (`skills/explore-api/SKILL.md`):
- Repeatable flag: `--assume "<claim>"` per claim. Each pre-seeds an assertion with `result: untested`.
- Pre-seeded claims are NOT exercised by the proof script — they appear in the record as-is.
- Record status logic (Phase 4): `proven` if ≥1 assertion is `pass`; `refuted` if all exercised assertions are `fail`. When ALL assertions are `untested` (only `--assume` claims), neither condition matches, so `LearnTestRecord.from_dict()` defaults to `"proven"` (`learning_tests.py:68`).
- Implication: `ll-learning-tests check` will report `status: proven` for `--assume`-only records. The `untested` assertions are still visible in the record's `assertions` list with `result: untested`.

**Test class to extend** (`scripts/tests/test_builtin_loops.py:3991-4040`, `TestAssumptionFirewallLoop`):
- 8 existing tests: `test_description_is_nonempty`, `test_run_gate_delegates_to_ready_to_implement_gate`, `test_run_gate_with_contains_targets_and_max_retries`, `test_done_is_terminal`, `test_blocked_is_terminal`, `test_no_external_deps_is_terminal`, plus 2 more.
- Pattern: `@pytest.fixture` returns `data: dict` from `yaml.safe_load(LOOP_FILE.read_text())`. Each test accesses `data["states"].get("<state_name>", {})` and asserts on fields.
- New tests needed: state existence for `classify_assumptions` and `record_untestable`, routing from `parse_assumptions` to `classify_assumptions`, evaluator types on `classify_assumptions`, `flatten_testable` reads from `classified.testable`, `record_untestable` calls `ll-action invoke explore-api` with `--assume`, empty-testable branch routes to `no_external_deps`.
- Also update: `test_run_gate_with_contains_targets_and_max_retries` must check `targets` comes from `flatten_testable` capture, not `flatten_targets`.

**Validation rules that apply** (`.claude/CLAUDE.md` § Loop Authoring):
- MR-1 (ERROR): Meta-loops must pair LLM evaluators with non-LLM evaluators. `classify_assumptions` uses `llm_structured` — ensure a non-LLM evaluator (e.g., `output_json`) is also in the routing chain.
- MR-3 (WARNING): Per-run artifact isolation under `${context.run_dir}/`. The `record_untestable` state calls `ll-action invoke explore-api` which writes LT records to `.ll/learning-tests/` — this is a legitimate cross-instance artifact (exempt from MR-3).

## Acceptance Criteria

- `ll-loop validate assumption-firewall` reports no ERRORs after the change.
- When issue has only untestable assumptions: gate routes `no_external_deps` and each assumption appears as `result: untested` in the corresponding LT record.
- When issue has both testable and untestable assumptions: testable ones go through `ready-to-implement-gate`; untestable ones are recorded as `untested` and do not block.
- When issue has only testable assumptions: behavior is unchanged from FEAT-1696 baseline.
- `TestAssumptionFirewallLoop` passes with updated state assertions.

## Impact

- **Priority**: P3 - Moderate; unblocks assumption-firewall from false-blocking on untestable assumptions, but a manual workaround exists (invoking `--assume` directly).
- **Effort**: Medium - Adds 2 states to an existing loop YAML plus a shell state with inline Python; touches one core file and its tests.
- **Risk**: Low - Changes are additive within an existing loop; no existing behavior paths are removed or altered.
- **Breaking Change**: No

## Labels

`enh`, `loop`, `learning-tests`, `assumption-firewall`, `assume-flag`, `false-block-fix`

---

## Resolution

**Completed**: 2026-05-30T22:37:00Z
**Status**: done

### Changes Made

- Added `classify_assumptions` prompt state to `assumption-firewall.yaml` — classifies extracted API assumptions as testable/untestable via LLM
- Added `record_untestable` shell state — iterates untestable claims, calls `ll-action invoke explore-api --assume` for each
- Renamed `flatten_targets` → `flatten_testable` — reads from `classified.testable` instead of `extracted.targets`
- Added empty-testable branch to `flatten_testable` — routes to `no_external_deps` when all assumptions are untestable
- Updated routing: `parse_assumptions → classify_assumptions → record_untestable → flatten_testable → run_gate`
- Added 18 structural tests for new states, routing, and evaluator configuration
- Added 4 behavioral tests for untested assertion round-trip and CLI output
- Updated `docs/guides/LOOPS_GUIDE.md` — assumption-firewall entry and usage example reflect classification and `--assume` recording
- Updated `scripts/little_loops/loops/README.md` — proof-first-task entry updated for new behavior
- Updated `docs/guides/LEARNING_TESTS_GUIDE.md` — added note about automated untestable claim recording

### Verification

- `ll-loop validate assumption-firewall` reports 0 ERRORs
- All 22 new/modified tests pass (18 structural + 4 behavioral)
- No existing behavior paths removed or altered

### Unresolved

None.

**Done** | Completed: 2026-05-30 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-05-30T22:37:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80a2adba-32fc-466c-a1d6-41449fbc1a3d.jsonl`
- `/ll:wire-issue` - 2026-05-30T22:23:20 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7611c31-d662-413c-b9fa-e6e9e5109f15.jsonl`
- `/ll:refine-issue` - 2026-05-30T22:16:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0801440f-0035-48ed-8387-0c4d15189334.jsonl`
- `/ll:format-issue` - 2026-05-29T19:35:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80e34915-6ade-4d27-95fc-5b7654bf3076.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
- `/ll:confidence-check` - 2026-05-30T22:25:36Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/895b9955-8293-43ae-b3f4-efce3fadd047.jsonl`
- `/ll:ready-issue` - 2026-05-30T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/80a2adba-32fc-466c-a1d6-41449fbc1a3d.jsonl`
