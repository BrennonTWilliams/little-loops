---
status: done
discovered_date: 2026-05-30
discovered_by: capture-issue
captured_at: '2026-05-30T22:43:51Z'
completed_at: '2026-05-31T00:52:16Z'
labels:
- validation
- loop-authoring
- harness
- captured
confidence_score: 100
outcome_confidence: 93
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# P3-ENH-1819: Add validation warning for multimodal evaluator blind spot in harness loops

## Summary

Harness loops like `html-website-generator` use `action_type: prompt` states that read screenshots/images and output a text verdict gated by `output_contains`. The evaluator can verify the LLM wrote the pass string but cannot verify the LLM actually processed the image vs. silently falling back to text-only analysis. Add a `validate_fsm` WARNING when a harness-category loop has this pattern with routing directly to a terminal state.

## Current Behavior

`validate_fsm()` has MR-1 (ERROR) and MR-2 (WARNING) rules for meta-loops, ensuring LLM self-evaluation is paired with non-LLM verification. No equivalent rule exists for harness-category loops that use LLM multimodal evaluation (screenshot reading + text verdict) as the sole gate to a terminal state. The pattern is structurally valid and passes all current validators.

## Expected Behavior

A new validation function `_validate_harness_multimodal_evaluator_blind_spot` fires a WARNING when:

1. Loop has `category: harness` (or is classified as a harness loop)
2. A state uses `action_type: prompt`
3. The action text references reading a screenshot or image (matches patterns like `screenshot.png`, `Read the screenshot`, `view the generated website`)
4. The evaluate type is `output_contains` (text-based, cannot verify multimodal processing)
5. The state's `on_yes` routes to a terminal state (or all paths from `on_yes` lead to terminal without passing through a shell-action state)

The warning message suggests adding a non-LLM verification state (shell action with functional tests) between the scoring state and the terminal.

Suppressed by `meta_self_eval_ok: true` at the loop top-level (reusing the existing escape hatch, since the underlying concern — LLM self-evaluation bias — is the same).

## Motivation

The `/ll:debug-loop-run html-website-generator` analysis found that an artifact with functional defects passed the screenshot evaluator because the LLM fell back to source-only scoring when it couldn't read the screenshot. The `output_contains` evaluator faithfully reported "ALL_PASS" — it just couldn't detect that the verdict was based on incomplete information. This is the same class of failure as MR-1 (LLM self-grades on harness updates are ~33-55% accurate per SHOR Table 1) but applied to artifact evaluation rather than harness modification. Catching this at validation time prevents future harness loops from shipping with the same blind spot.

## Proposed Solution

Add `_validate_harness_multimodal_evaluator_blind_spot` to `scripts/little_loops/fsm/validation.py`:

```python
# Regex patterns for detecting multimodal evaluation in prompt actions
_MULTIMODAL_EVAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'Read the screenshot', re.IGNORECASE),
    re.compile(r'view the (generated )?(website|page|image)', re.IGNORECASE),
    re.compile(r'screenshot\.(png|jpg|jpeg|webp)'),
    re.compile(r'\.(png|jpg|jpeg|webp)\b.*\b(read|view|evaluate|score|judge)', re.IGNORECASE),
)

def _validate_harness_multimodal_evaluator_blind_spot(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when harness loops use LLM multimodal eval as sole gate to terminal."""
    errors = []
    if fsm.meta_self_eval_ok or fsm.category != "harness":
        return errors

    terminal_states = fsm.get_terminal_states()

    for state_name, state in fsm.states.items():
        if state.action_type != "prompt" or not state.action:
            continue
        if state.evaluate is None or state.evaluate.type != "output_contains":
            continue
        if not any(p.search(state.action) for p in _MULTIMODAL_EVAL_PATTERNS):
            continue
        # Check if on_yes routes directly to a terminal
        if state.on_yes in terminal_states:
            errors.append(ValidationError(
                message=(
                    f"State '{state_name}' evaluates a screenshot/image via LLM prompt "
                    "and routes directly to a terminal on success. The output_contains "
                    "evaluator can verify the LLM wrote the pass string but not that the "
                    "LLM actually processed the image. Consider adding a shell-action "
                    "verification state (e.g., functional smoke test) between scoring "
                    "and the terminal."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            ))

    return errors
```

Wire into `validate_fsm()` alongside the existing MR-1/MR-2/zero-retry-counter calls.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact wiring location**: `validate_fsm()` at `validation.py:878-886` — insert `errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))` alongside existing calls to `_validate_meta_loop_evaluation`, `_validate_artifact_isolation`, and `_validate_zero_retry_counter`
- **`meta_self_eval_ok` already registered** in `KNOWN_TOP_LEVEL_KEYS` at `validation.py:131` — no additional config change needed to avoid "Unknown top-level key" warnings when loops use the suppression flag
- **3 harness loops currently trigger this blind spot**: `svg-image-generator.yaml` (score state `on_yes: done`), `hitl-compare.yaml` (score state `on_yes: done`), `html-anything.yaml` (score state `on_yes: done`) — all have `action_type: prompt` states that read screenshots, evaluate via `output_contains`, and route `on_yes` directly to a terminal
- **3 harness loops correctly avoid the pattern** via a non-LLM state between scoring and terminal: `html-website-generator.yaml` (smoke_test shell state), `svg-textgrad.yaml` (verify_score shell state), `hitl-md.yaml` (finalize shell copy state) — these serve as reference implementations for the fix pattern this warning recommends
- **`FSMLoop.get_terminal_states()`** at `schema.py:1026` returns `set[str]` of state names where `terminal=True` — use this instead of reimplementing terminal detection
- **Test import pattern**: import the private `_validate_harness_multimodal_evaluator_blind_spot` directly alongside `validate_fsm` (following `test_fsm_validation.py` convention of importing `_validate_meta_loop_evaluation`, `_validate_artifact_isolation`, etc.)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_MULTIMODAL_EVAL_PATTERNS` (module-level regex tuple), `_validate_harness_multimodal_evaluator_blind_spot` (following pattern of `_validate_meta_loop_evaluation()` at line 916), wire into `validate_fsm()` at approximately line 878-886 (alongside existing MR-1/MR-2/zero-retry-counter calls)

### Dependent Files (Callers/Importers)
- `ll-loop validate` CLI (`scripts/little_loops/cli/loop/config_cmds.py:cmd_validate()`) — consumes `validate_fsm()` output (no changes needed)
- `scripts/little_loops/fsm/__init__.py` — exports `validate_fsm`, `load_and_validate`, `ValidationError`, `ValidationSeverity` (no new exports needed; `_validate_harness_multimodal_evaluator_blind_spot` is private)

### Similar Patterns
- `_validate_meta_loop_evaluation()` at `validation.py:916` — same signature, same `meta_self_eval_ok` suppression gate, same early-return pattern; is the structural template for this new rule
- `_validate_artifact_isolation()` at `validation.py:1067` — another WARNING-severity rule with category-specific gating and regex-based state scanning
- `_validate_zero_retry_counter()` at `validation.py:982` — pattern for iterating states, skipping non-matching, appending ValidationError per occurrence

### Tests
- `scripts/tests/test_fsm_validation.py` — add test class `TestHarnessMultimodalEvaluatorBlindSpot` (modeled after `TestMetaLoopValidation` at line 709) with cases for: fires on matching pattern, does not fire on non-harness loops, does not fire when on_yes goes to non-terminal, does not fire when shell-action state intervenes, suppressed by `meta_self_eval_ok`, integration test confirming wiring into `validate_fsm()`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — documents MR-1/MR-2 under `ll-loop validate` section (lines ~455-462); references `meta_self_eval_ok` suppression — should note the new harness multimodal blind-spot rule reuses the same escape hatch [Agent 2 finding]
- `docs/reference/API.md` — documents `validate_fsm()` return value and MR-1/MR-2 enumeration (lines ~4572-4590); new rule adds WARNING entries to the return list [Agent 2 finding]
- `.claude/CLAUDE.md` — Loop Authoring section documents meta-loop validation rules (MR-1/MR-2/MR-3) and `meta_self_eval_ok` suppression flag (lines ~93-126); the new harness-category rule extends the same `meta_self_eval_ok` escape hatch [Agent 2 finding]
- `skills/review-loop/reference.md` — hardcodes the first-pass check list from `ll-loop validate` (lines ~17-41); table may need updating if the new rule receives a formal check ID [Agent 2 finding]

_Note: No documentation changes are strictly required for implementation — this is a WARNING-only rule with no public API changes. The above files are coupling points to update during the release documentation pass._

### Configuration
- `meta_self_eval_ok` is already registered in `KNOWN_TOP_LEVEL_KEYS` at `validation.py:131` — no config change needed to avoid unknown-key warnings

## API/Interface

N/A - no public API changes; new `_validate_harness_multimodal_evaluator_blind_spot()` is internal (called from existing `validate_fsm()`).

## Implementation Steps

1. Add `_MULTIMODAL_EVAL_PATTERNS` regex tuple to `validation.py` (module level, following pattern of `_META_LOOP_ACTION_PATTERNS` at line 83)
2. Implement `_validate_harness_multimodal_evaluator_blind_spot(fsm: FSMLoop) -> list[ValidationError]` following the structural template of `_validate_meta_loop_evaluation()` at `validation.py:916` — early return on `meta_self_eval_ok` or non-harness category, iterate states, append `ValidationError(severity=ValidationSeverity.WARNING, path=f"states.{state_name}")` per match
3. Wire into `validate_fsm()` at approximately `validation.py:878-886` (alongside existing MR-1/MR-2/zero-retry-counter calls): `errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))`
4. Add test class `TestHarnessMultimodalEvaluatorBlindSpot` in `scripts/tests/test_fsm_validation.py`, modeled after `TestMetaLoopValidation` (line 709). Import both `validate_fsm` and the private `_validate_harness_multimodal_evaluator_blind_spot`. Include: positive control (fires on harness loop with multimodal prompt → terminal routing), negative controls (non-harness loop, non-terminal on_yes, shell-action state intervenes, meta_self_eval_ok suppression), and an integration test confirming wiring into `validate_fsm()`
5. Run `python -m pytest scripts/tests/test_fsm_validation.py -v` to confirm all pass
6. Run `ll-loop validate svg-image-generator` — should emit the new WARNING (this loop has `score` → `done` with no non-LLM state intervening). `html-website-generator` should NOT trigger (its `smoke_test` shell state intervenes between `score` and `done`)

## Success Metrics

- `ll-loop validate html-website-generator` emits the new WARNING (before ENH-1818 fix)
- Non-harness loops are not flagged
- `meta_self_eval_ok: true` suppresses the warning
- No existing tests break

## Scope Boundaries

- Only checks `category: harness` loops — does not apply to all loops
- Only checks `output_contains` evaluators — does not cover `llm_structured` or other evaluator types
- Only checks direct `on_yes` → terminal routing — does not trace multi-hop paths to terminal
- Does not auto-fix loops — informational warning only

## Impact

- **Priority**: P3 — preventive guardrail; the immediate blind spot is fixed by ENH-1818
- **Effort**: Small — ~40 lines of validation code + ~60 lines of tests
- **Risk**: Low — WARNING only, does not block loop execution; regex patterns may have false negatives but false positives are unlikely given the `category: harness` gate
- **Breaking Change**: No

## Related Key Documentation

- [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md) — Loop Authoring section (MR-1/MR-2/MR-3 rules, `meta_self_eval_ok` suppression flag)
- [docs/reference/API.md](../../docs/reference/API.md) — `validate_fsm()` at line 4572, `load_and_validate()` at line 4610, `ValidationError`, `ValidationSeverity`
- [docs/guides/LOOPS_GUIDE.md](../../docs/guides/LOOPS_GUIDE.md) — `ll-loop validate` usage

## Labels

`validation`, `loop-authoring`, `harness`, `captured`

## Session Log
- `/ll:wire-issue` - 2026-05-31T00:43:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a4c5ef3-be36-467b-b9a4-1a846642f59b.jsonl`
- `/ll:format-issue` - 2026-05-30T22:47:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/161b9a00-98fc-4a06-9eec-25494c352734.jsonl`
- `/ll:capture-issue` - 2026-05-30T22:43:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a21d14e7-ea27-437a-b7be-dfdc28dd7d84.jsonl`
- `/ll:refine-issue` - 2026-05-30T19:35:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df621d71-875d-43c5-95c3-21b12295b16b.jsonl`
- `/ll:manage-issue` - 2026-05-31T00:52:16Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b230c9dd-59f7-4047-ad66-3eb247b8ffa4.jsonl`

## Resolution

Implemented `_validate_harness_multimodal_evaluator_blind_spot` in `scripts/little_loops/fsm/validation.py`:

1. Added `_MULTIMODAL_EVAL_PATTERNS` module-level regex tuple for detecting screenshot/image-reading prompt actions
2. Implemented `_validate_harness_multimodal_evaluator_blind_spot(fsm)` following the structural template of `_validate_meta_loop_evaluation()` — early return on `meta_self_eval_ok` or non-harness category, iterates states matching `prompt` + `output_contains` + multimodal patterns + direct-to-terminal routing
3. Wired into `validate_fsm()` alongside existing MR-1/MR-2/artifact-isolation calls
4. Added `TestHarnessMultimodalEvaluatorBlindSpot` test class (7 tests) covering: positive control, non-harness skip, non-terminal on_yes skip, shell-action intervenes, non-output_contains evaluator skip, meta_self_eval_ok suppression, integration wiring

Verified: `svg-image-generator` correctly emits WARNING; `html-website-generator` correctly silent.

---

**Open** | Created: 2026-05-30 | Priority: P3
