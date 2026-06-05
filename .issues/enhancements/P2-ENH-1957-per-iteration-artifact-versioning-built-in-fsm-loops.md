---
id: ENH-1957
status: open
type: enh
priority: P2
captured_at: "2026-06-05T04:04:47Z"
discovered_date: 2026-06-05
discovered_by: capture-issue
---

# ENH-1957: Add Per-Iteration Artifact Versioning to Built-in FSM Loops

## Summary

70+ built-in FSM loops exist, and the majority that iteratively refine artifacts (images, HTML, plans, issues) **overwrite** the same file on every iteration within a run. Only the final result survives — all intermediate versions are lost. The runner already provides run-level isolation (timestamped `run_dir`), but within a single run, every iteration overwrites the previous one.

This enhancement adds per-iteration artifact snapshots so every scored version is preserved in `iter-N/` subdirectories within the run directory, enabling debugging, comparison, and rollback across iterations.

## Current Behavior

Most iterative FSM loops (e.g., `svg-image-generator`, `html-website-generator`, `rn-refine`, `refine-to-ready-issue`) write to a flat artifact path like `${run_dir}/image.svg` or `${run_dir}/plan.md`. Each iteration overwrites the previous output. Only 2 of ~70 loops preserve intermediate versions:

- `adversarial-redesign.yaml` — copies `iter-$ITER.svg` + `iter-$ITER-critique.json` per iteration
- `svg-textgrad.yaml` — tracks `best.svg` / `best-brief.md` when score improves (but not all iterations)

**Key architectural insight**: `oracles/generator-evaluator.yaml` is the **shared sub-loop** used by 7 thin-wrapper harness loops (`html-website-generator`, `html-anything`, `svg-image-generator`, `p5js-sketch-generator`, `pixi-generative-art`, `pixi-data-viz`, `hitl-md`). Adding versioning to this one oracle fixes all 7 wrappers at once.

## Expected Behavior

Every iterative loop that refines an artifact should preserve per-iteration snapshots in `iter-N/` subdirectories within the run directory. The `generator-evaluator.yaml` oracle should provide this as a built-in `snapshot` state between `evaluate` and `score`. A new MR-5 validation rule should warn when harness-category loops write to flat artifact paths in iterative cycles without declaring versioning intent.

## Motivation

- **Debugging**: If iteration 3 produces a great SVG but iteration 4 degrades it, only the degraded version survives — the better version is lost forever
- **Comparison**: Users cannot diff or compare how artifacts evolved across iterations without per-iteration snapshots
- **Rollback**: No way to revert to a previous iteration's output without re-running the entire loop
- **Scale**: 70+ loops affected, but the oracle fix alone addresses 7 at once. Remaining individual loops need targeted updates
- **Prevention**: MR-5 validation prevents future loops from silently regressing on this pattern

## Proposed Solution

Three-phase approach combining **infrastructure support** (schema flag + validation rule + library fragment) with **targeted YAML updates** to the oracle and affected loops.

### Phase 1: Oracle Fix (Highest Leverage — Fixes 7 Loops)

Modify `scripts/little_loops/loops/oracles/generator-evaluator.yaml` to add a `snapshot` state between `evaluate` and `score`:

```
Before: generate → evaluate → score → on_no → generate → ...
After:  generate → evaluate → snapshot → score → on_no → generate → ...
```

**Snapshot state** (shell action):
```bash
RUN_DIR="${context.run_dir}"
COUNTER=$(cat "$RUN_DIR/.iter_counter" 2>/dev/null || echo 0)
COUNTER=$((COUNTER + 1))
echo "$COUNTER" > "$RUN_DIR/.iter_counter"
mkdir -p "$RUN_DIR/iter-$COUNTER"
cp "$RUN_DIR/${context.artifact_path}" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
cp "$RUN_DIR/screenshot.png" "$RUN_DIR/iter-$COUNTER/" 2>/dev/null || true
```

Routing: unconditional `next: score` — snapshot always succeeds. Evaluate's `on_yes`/`on_no` now point to `snapshot` instead of `score`. Add `artifact_versioning: true` top-level declaration.

### Phase 2: Schema and Infrastructure

- Add `artifact_versioning: bool = False` and `artifact_versioning_ok: bool = False` to `FSMLoop` dataclass in `fsm/schema.py` (~line 970), with serialization in `to_dict()` (~line 1038) and deserialization in `from_dict()` (~line 1095)
- Add both to `KNOWN_TOP_LEVEL_KEYS` in `validation.py` (~line 153)
- Add `_validate_artifact_overwrite()` function: **WARNING** when a harness-category loop writes to a flat artifact path in an iterative `generate→evaluate→generate` cycle without `artifact_versioning: true` or `artifact_versioning_ok: true`. Wire into `validate_fsm()` (~line 994)
- Add `snapshot_artifact` library fragment in `loops/lib/common.yaml` for non-oracle loops to compose in

### Phase 3: Update Remaining Individual Loops

| Loop | Change |
|------|--------|
| `svg-textgrad.yaml` | Add per-iteration snapshot lines to `track_best` state + `artifact_versioning: true` |
| `adversarial-redesign.yaml` | Add `artifact_versioning: true` (already writes `iter-$ITER.svg`) |
| `rn-refine.yaml` | Add `snapshot` state after `synthesize` + `artifact_versioning: true` |
| `refine-to-ready-issue.yaml` | Add shell state after `refine_issue` to copy issue into `run_dir/iter-N-issue.md` + `artifact_versioning: true` |
| `recursive-refine.yaml` | Add `artifact_versioning: true` (sub-loops handle snapshots) |
| `general-task.yaml` | Add `artifact_versioning_ok: true` (artifact varies by task — suppress MR-5) |

## Integration Map

### Files to Modify
| Priority | File | Change |
|----------|------|--------|
| **P0** | `loops/oracles/generator-evaluator.yaml` | Add `snapshot` state + `artifact_versioning: true` |
| **P0** | `fsm/schema.py` | Add `artifact_versioning`, `artifact_versioning_ok` fields |
| **P0** | `fsm/validation.py` | Add MR-5 validation rule + KNOWN_TOP_LEVEL_KEYS entries |
| P1 | `loops/lib/common.yaml` | Add `snapshot_artifact` fragment |
| P1 | `loops/svg-textgrad.yaml` | Per-iteration snapshot + versioning flag |
| P1 | `loops/rn-refine.yaml` | Snapshot state + versioning flag |
| P1 | `loops/refine-to-ready-issue.yaml` | Issue snapshot + versioning flag |
| P1 | `scripts/tests/test_fsm_validation.py` | MR-5 test cases |
| P2 | `loops/adversarial-redesign.yaml` | Add `artifact_versioning: true` |
| P2 | `loops/recursive-refine.yaml` | Add `artifact_versioning: true` |
| P2 | `loops/general-task.yaml` | Add `artifact_versioning_ok: true` |
| P2 | `skills/create-loop/templates.md` | Default versioning in harness template |
| P2 | `skills/create-loop/reference.md` | Document new config keys |

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — FSM executor reads loop YAML and instantiates `FSMLoop` dataclass
- `scripts/tests/test_fsm_validation.py` — existing MR-1 through MR-4 tests; add MR-5 cases

### Similar Patterns
- `adversarial-redesign.yaml` already implements per-iteration versioning — use as reference pattern for the `iter-N/` convention
- `svg-textgrad.yaml` has best-score tracking — extend to full per-iteration snapshots

### Tests
- `scripts/tests/test_fsm_validation.py` — add MR-5 unit tests:
  - MR-5 fires for harness loop overwriting artifact without versioning
  - MR-5 does NOT fire with `artifact_versioning: true`
  - MR-5 does NOT fire with `artifact_versioning_ok: true`
  - MR-5 does NOT fire for non-iterative loops
- Smoke test: `ll-loop run svg-image-generator --builtin --max-iterations 2 --input '{"description": "a simple blue circle"}' --context pass_threshold=4` — verify `run_dir` contains `iter-1/` and `iter-2/`

### Documentation
- `skills/create-loop/templates.md` — default versioning in harness template
- `skills/create-loop/reference.md` — document new `artifact_versioning` / `artifact_versioning_ok` config keys
- `docs/reference/API.md` — update FSMLoop dataclass field documentation

### Configuration
- N/A — no config changes; new fields are loop-level YAML declarations

## Implementation Steps

1. Add `artifact_versioning` and `artifact_versioning_ok` fields to `FSMLoop` dataclass in `fsm/schema.py` with `to_dict()`/`from_dict()` support
2. Add MR-5 validation rule (`_validate_artifact_overwrite`) in `fsm/validation.py` with iterative-cycle detection heuristic; wire into `validate_fsm()`
3. Add `snapshot_artifact` library fragment in `loops/lib/common.yaml`
4. Modify `generator-evaluator.yaml` oracle to insert `snapshot` state between `evaluate` and `score` (fixes 7 wrapper loops at once)
5. Update `svg-textgrad.yaml` with per-iteration snapshots in `track_best` state
6. Add `snapshot` state to `rn-refine.yaml` after `synthesize`
7. Add issue-copy state to `refine-to-ready-issue.yaml` after `refine_issue`
8. Declare `artifact_versioning: true` on `adversarial-redesign.yaml` and `recursive-refine.yaml`
9. Add `artifact_versioning_ok: true` to `general-task.yaml`
10. Add MR-5 unit tests to `test_fsm_validation.py`
11. Run `ll-loop validate` on all affected loops + full test suite (`python -m pytest scripts/tests/ -v --tb=short` + `ruff check scripts/`)
12. Smoke test with `svg-image-generator` to verify `iter-N/` directories are created

## Impact

- **Priority**: P2 — Important improvement for debugging and observability of FSM loop runs. Not blocking any current workflow but addresses a systematic gap across 70+ loops.
- **Effort**: Medium — ~13 files to modify, but changes are well-scoped and additive. The oracle fix provides highest leverage (7 loops fixed with one change). Schema changes are straightforward field additions.
- **Risk**: Low — New fields are optional (default `False`). MR-5 is WARNING severity, not ERROR. Snapshot state is a non-destructive copy operation. No breaking changes to existing loop behavior or runtime.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop system design and component architecture |
| [docs/reference/API.md](../../docs/reference/API.md) | FSMLoop dataclass and validation API reference |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | Loop authoring rules and meta-loop design constraints |
| [docs/guides/AUTOMATIC_HARNESSING_GUIDE.md](../../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md) | Harness validation and baseline comparison patterns |

## Labels

`enhancement`, `fsm-loops`, `artifact-versioning`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-06-05T04:04:47Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7f9cd92c-4c6c-4bd0-906d-86f3c89b4a18.jsonl`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
