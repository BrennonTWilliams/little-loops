---
id: ENH-1944
title: Add enrich state and quality predicates to sft-corpus.yaml filter
type: ENH
priority: P3
status: done
parent: ENH-1941
relates_to:
- EPIC-1880
- EPIC-1707
- ENH-1710
- ENH-1943
- FEAT-1826
labels:
- enhancement
- sft
- history-db
- corpus-quality
- loops
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-06-04 18:10:42+00:00
---

# ENH-1944: Add enrich state and quality predicates to sft-corpus.yaml filter

## Summary

Add an `enrich` state to `sft-corpus.yaml` that batch-joins `history.db` session-quality metadata onto staged examples, and extend the `filter` state with four optional quality predicates backed by that metadata. Includes wiring (loop registration, documentation, MR-3 compliance, meta-loop classification avoidance) and tests.

## Current Behavior

The `sft-corpus` loop skeleton (planned under FEAT-1826) has a `filter` state for basic content filtering, but lacks an `enrich` state for joining `history.db` session-quality metadata onto staged examples. The filter state has no quality predicates that inspect session metadata (issue outcome, user corrections, tool invocation counts, file modifications). Without these signals, the filter cannot distinguish high-quality training examples from low-quality ones based on session outcomes.

## Expected Behavior

An `enrich` state sits between `stage` and `filter`, batch-joining `history.db` session-quality metadata onto each JSONL example. The `filter` state supports four optional quality predicates (`require_issue_outcome`, `exclude_user_corrections`, `min_tool_invocations`, `require_file_modifications`), each opt-in with a pass-through default, each using `output_numeric` evaluators, and each emitting `rejected_by` annotations for dropped examples. The loop is registered in the built-in catalog with passing tests, MR-3 artifact isolation, and non-meta-loop classification.

## Parent Issue

Decomposed from ENH-1941: Integrate history.db session-quality signals into sft-corpus filtering

## Prerequisites

- **FEAT-1826**: `sft-corpus.yaml` must exist (this file is the primary deliverable of FEAT-1826). If FEAT-1826 is still `open`, either block on it or absorb its skeleton creation into this issue's scope.
- **ENH-1943**: `lookup_session_metadata()` function must be available in `history_reader.py`.

## Implementation Steps

### Enrich State

1. **Add `enrich` state before `filter` in `sft-corpus.yaml`** — batch-joins metadata from `history.db` onto each example in the staged `raw.jsonl`:
   - Extract session ID from each JSONL line's source filename (the JSONL filename IS the session ID — UUID.jsonl)
   - Call `lookup_session_metadata(session_id)` (from ENH-1943)
   - Write enriched examples to `${context.run_dir}/enriched.jsonl` (MR-3 compliance: never to shared `.loops/tmp/`)
   - Model structural pattern after `examples-miner.yaml` `calibrate` state (line 93) and `merge` state (line 244)

### Filter State Extension

2. **Extend the `filter` state** with four new optional predicates. Each uses an `output_numeric` evaluator (pattern from `dataset-curation.yaml` `route_quality` state, line 64):

   | Predicate | Evaluator | Target | Drops when |
   |-----------|-----------|--------|------------|
   | `require_issue_outcome` | `output_numeric` / `eq` | `1` | `metadata.issue_outcome != "done"` |
   | `exclude_user_corrections` | `output_numeric` / `eq` | `0` | `metadata.has_corrections == true` |
   | `min_tool_invocations` | `output_numeric` / `ge` | `${context.min_tool_invocations}` | `metadata.tool_count < context.min_tool_invocations` |
   | `require_file_modifications` | `output_numeric` / `ge` | `1` | `metadata.files_modified == 0` |

3. **Add filter rejection tracking** — extend the filter state to emit a `rejected_by` annotation per dropped example (pattern from `dataset-curation.yaml` `reject_item` state, line 98):
   - Append `{path, score, reason, timestamp}` to `${context.output_dir}/rejections.jsonl`
   - `reason` field = the predicate name that rejected (e.g., `"require_issue_outcome"`)
   - Publish aggregate rejection stats (pattern from `dataset-curation.yaml` `publish` state, line 168)

### Context Block

4. **Update `sft-corpus.yaml` context block** — add four new optional keys with pass-through defaults:
   ```yaml
   require_issue_outcome: false       # default: skip this check
   exclude_user_corrections: false    # default: skip this check
   min_tool_invocations: 0            # default: skip this check
   require_file_modifications: false  # default: skip this check
   ```
   Referenced via `${context.require_issue_outcome}` etc. per `InterpolationContext.resolve()` at `scripts/little_loops/fsm/interpolation.py:71`.

### Wiring (TDD Mode — wiring stays with implementation)

5. **Register `sft-corpus` in the built-in loop catalog** — add `"sft-corpus"` to the hardcoded `expected` set in `scripts/tests/test_builtin_loops.py:test_expected_loops_exist()` (line 73). This is the primary registration gate; without this entry, CI fails.

6. **Document `sft-corpus` in the loop registry** — add rows to:
   - `scripts/little_loops/loops/README.md` — "Data & Testing" table
   - `docs/guides/LOOPS_GUIDE.md` — built-in loops reference table

7. **Verify MR-3 artifact isolation** — ensure the `enrich` state writes intermediate files to `${context.run_dir}/enriched.jsonl` (not shared `.loops/tmp/`). The static validator at `scripts/little_loops/fsm/validation.py:_validate_artifact_isolation()` (line 1256) emits WARNING severity if hardcoded `.loops/tmp/` paths are detected.

8. **Ensure `sft-corpus` is not misclassified as a meta-loop** — keep all action strings in `sft-corpus.yaml` data-focused. The `_is_meta_loop()` function at `scripts/little_loops/fsm/validation.py` (line 1009) checks action strings against harness artifact patterns (`skills/`, `agents/`, `commands/`, `hooks/`, `CLAUDE.md`). Do not reference these patterns in action strings.

### Tests

9. **Add tests** in `scripts/tests/test_loops_sft_corpus.py` (created by FEAT-1826; if it doesn't exist yet, create it):
   - Graceful degradation when `history.db` is missing — pipeline completes, no crashes, no empty corpus
   - Each predicate drops only the examples it claims to target (filter precision):
     - `require_issue_outcome` drops sessions where no issue was closed
     - `exclude_user_corrections` drops sessions with user corrections
     - `min_tool_invocations` drops sessions with too few tool calls
     - `require_file_modifications` drops sessions with zero file modifications
   - Predicate=false means pass-through (opt-in behavior)
   - Rejection annotations are correct (each dropped example has a `rejected_by` field with the right predicate name)
   - Follow bash-based loop state testing pattern from `test_loops_recursive_refine.py`:
     - Helper: `def _bash(script: str, cwd: Path) -> subprocess.CompletedProcess[str]: return subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)` (line 14)
     - Use `tmp_path` fixture for isolated filesystem
     - Assertions: `result.returncode == 0`, `result.stdout.strip() == "expected"`, file content via `(tmp_path / "file").read_text()`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Update `README.md` doc count** — correct `72 FSM loops` to `70 FSM loops` at line 163 (current actual count is 69; +1 for sft-corpus = 70; the doc count of 72 was already stale); enforced by `ll-verify-docs` and `scripts/tests/test_doc_counts.py` [Agent 2 finding; count verified 2026-06-04]
11. **Update `CONTRIBUTING.md` file count** — correct `62 YAML files` to `70 YAML files` at line 122 (current actual count is 69; +1 for sft-corpus = 70; the doc count of 62 was already stale); same count enforcement as above [Agent 2 finding; count verified 2026-06-04]
12. **Verify `docs/ARCHITECTURE.md`** — confirm no loop/YAML count line needs incrementing (none found, but verify) [Agent 2 finding]
13. **Verify `scripts/little_loops/pii.py` docstring** — line 4 references `sft-corpus` FSM loop as primary consumer of `apply_pii_action()`; ensure docstring stays consistent with the new loop's filter state [Agent 1 finding]
14. **Verify supplementary tests pass** — `test_doc_counts.py` (count assertions), `test_fsm_validation.py` (MR-3/meta-loop auto-coverage) should pass with no changes needed after doc counts are updated [Agent 2/3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Enrich State: Exact `lookup_session_metadata()` Call Pattern

The shell action for the `enrich` state should use a Python heredoc to batch-process JSONL lines:

```yaml
action_type: shell
action: |
  python3 << 'PYEOF'
import json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
from little_loops.history_reader import lookup_session_metadata

run_dir = Path("${context.run_dir}")
input_file = Path("${captured.stage.output}").resolve()  # raw.jsonl from stage state
output_file = run_dir / "enriched.jsonl"

with open(input_file) as f_in, open(output_file, "w") as f_out:
    for line in f_in:
        line = line.strip()
        if not line:
            continue
        example = json.loads(line)
        # Session ID = the JSONL filename stem (UUID.jsonl → UUID)
        source = example.get("source", "")
        session_id = Path(source).stem if source else ""
        if session_id:
            metadata = lookup_session_metadata(session_id)
        else:
            metadata = {}
        # If metadata is empty (DB missing/error), preserve passthrough behavior
        example["metadata"] = {
            "has_corrections": metadata.get("has_corrections", False),
            "issue_outcome": metadata.get("issue_outcome"),
            "tool_count": metadata.get("tool_count", 0),
            "files_modified": metadata.get("files_modified", 0),
        }
        f_out.write(json.dumps(example) + "\n")
print(str(output_file))
PYEOF
  capture: enriched_file
  next: filter
```

Key design decisions embedded above:
- Writes to `${context.run_dir}/enriched.jsonl` (MR-3 compliant — no `.loops/tmp/` paths)
- Degrades gracefully when `lookup_session_metadata()` returns `{}` (preserves defaults)
- Captures output path for downstream `filter` state consumption

#### Filter Predicate: Exact `output_numeric` Evaluator Pattern

Each predicate follows the `dataset-curation.yaml:route_quality` (line 64) pattern:

```yaml
# Predicate: require_issue_outcome (drops when issue_outcome != "done")
check_issue_outcome:
    action: |
      python3 -c "
import json, sys
ex = json.loads(open('${captured.enrich.output}').readline())
outcome = ex.get('metadata', {}).get('issue_outcome')
print(1 if outcome == 'done' else 0)
"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: eq
      target: 1
    on_yes: check_corrections    # passed → next predicate
    on_no: reject_issue_outcome  # failed → reject with reason
```

For boolean checks (`exclude_user_corrections`), the action prints `1` when metadata is clean (pass) and `0` when it has corrections (fail), using `eq` with `target: 0` to route `on_yes` to pass-through:

```yaml
check_corrections:
    action: |
      python3 -c "
import json
ex = json.loads(open('${captured.enrich.output}').readline())
print(1 if ex.get('metadata', {}).get('has_corrections') else 0)
"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: eq
      target: 0          # 0 = clean (no corrections) → on_yes = pass
    on_yes: check_tools  # no corrections → continue
    on_no: reject_corrections
```

#### Meta-Loop Avoidance Verification

The `_is_meta_loop()` detector at `validation.py:1009` scans action strings for:

```python
_META_LOOP_ACTION_PATTERNS = (
    re.compile(r"loops/[\w-]+\.yaml"),
    re.compile(r"skills/[\w-]+/SKILL\.md"),
    re.compile(r"agents/[\w-]+\.md"),
    re.compile(r"commands/[\w-]+\.md"),
    re.compile(r"\.claude/(CLAUDE\.md|settings)"),
)
_META_LOOP_ACTION_TOKENS = frozenset({"yaml_state_editor", "replace_action"})
_META_LOOP_IMPORT_TRIGGERS = frozenset({"lib/benchmark.yaml"})
```

To avoid misclassification, ensure action strings only reference:
- Data paths: `${context.run_dir}/`, `.issues/`, `.loops/diagnostics/`, `history.db`
- No harness artifact paths: no `skills/`, `agents/`, `commands/`, `hooks/`, `CLAUDE.md`
- No `yaml_state_editor` or `replace_action` tokens

#### MR-3 Artifact Isolation Verification

The `_find_shared_tmp_writes()` function at `validation.py:1215` scans actions for `_SHARED_TMP_PATH_RE = re.compile(r"\.loops/tmp/[\w./-]+")`. The `enrich` state writes to `${context.run_dir}/enriched.jsonl` which resolves to `.loops/runs/sft-corpus-<timestamp>/enriched.jsonl` — this does NOT match the regex and passes validation.

Paths that pass MR-3 (no warning):
- `${context.run_dir}/...` — run_dir interpolation
- `.issues/...`, `.loops/diagnostics/...` — legitimate cross-instance artifacts

#### Registration Gate: Exact `expected` Set Location

The `expected` set at `test_builtin_loops.py:73` must be alphabetically sorted. `"sft-corpus"` fits between `"scan-and-implement"` and `"sprint-build-and-validate"`:

## Scope Boundaries

- **In scope**: `enrich` state; four filter predicates; rejection tracking; context block; wiring (registration, docs, MR-3, meta-loop avoidance); tests
- **Out of scope**: `lookup_session_metadata()` implementation (ENH-1943); changes to `history.db` schema or write paths (EPIC-1707); changes to `extract_conversation_turns()` return type; analytics/reporting on rejection rates (future issue)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sft-corpus.yaml` — add `enrich` state, extend `filter` predicates, add context keys
  > ⚠ **Dependency**: FEAT-1826 must create this file first (or this issue absorbs skeleton creation)
- `scripts/tests/test_loops_sft_corpus.py` — add enrichment + filter predicate + degradation tests
- `scripts/tests/test_builtin_loops.py` — add `"sft-corpus"` to `expected` set (line 73)
- `scripts/little_loops/loops/README.md` — add `sft-corpus` row to "Data & Testing" table
- `docs/guides/LOOPS_GUIDE.md` — add `sft-corpus` to built-in loops reference table

### Similar Patterns
- **Metadata join**: `examples-miner.yaml` `calibrate` (line 93) and `merge` (line 244)
- **Filter evaluator**: `dataset-curation.yaml` `route_quality` (line 64) — `output_numeric` with `operator: ge`
- **Rejection tracking**: `dataset-curation.yaml` `reject_item` (line 98) — append to rejections sidecar
- **Per-run isolation**: `hitl-compare.yaml` `init` (line 26) — `${context.run_dir}/` pattern (runner injects dir, no capture state needed)
- **Graceful degradation**: `history_reader.py` `_connect_readonly()` (line 166) — try/catch/finally; callers check for `None` return

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Verified Anchor References
- `lookup_session_metadata()` at `history_reader.py:435` — returns `dict` with keys: `has_corrections` (bool), `issue_outcome` (str|None), `tool_count` (int), `files_modified` (int), `loop_outcome` (None). Returns `{}` when DB missing, empty, or on `sqlite3.Error`.
- `InterpolationContext.resolve()` at `fsm/interpolation.py:71` — resolves `${context.var}` via `_get_nested()` traversal. Non-string values (bool, int) converted via `str()`. `None` resolves to `""`.
- `_is_meta_loop()` at `fsm/validation.py:1009` — checks action strings against regex patterns: `loops/[\w-]+\.yaml`, `skills/[\w-]+/SKILL\.md`, `agents/[\w-]+\.md`, `commands/[\w-]+\.md`, `\.claude/(CLAUDE\.md|settings)`. Also checks for tokens `yaml_state_editor`/`replace_action` and import of `lib/benchmark.yaml`.
- `_validate_artifact_isolation()` at `fsm/validation.py:1256` — scans action strings with `_SHARED_TMP_PATH_RE = re.compile(r"\.loops/tmp/[\w./-]+")`. MR-3 emits WARNING for matches. Suppressible with `shared_state_ok: true`.
- `test_expected_loops_exist()` at `test_builtin_loops.py:73` — hardcoded `expected` set of 69 loop names. `actual` reads `BUILTIN_LOOPS_DIR.glob("*.yaml")`. Assertion: `assert expected == actual`. Entry must be alphabetically sorted.

#### Dependency Status

- **ENH-1943 (`lookup_session_metadata()`)**: `status: done` — dependency satisfied. The function is available at `history_reader.py:435`.
- **FEAT-1826 (`sft-corpus.yaml` skeleton)**: still `open` — `sft-corpus.yaml` does not exist on disk. ENH-1944 must absorb skeleton creation (stage + filter + context block boilerplate), not just extend an existing file. The `sft-corpus` name is absent from `test_builtin_loops.py:73` `expected` set; no `test_loops_sft_corpus.py` exists.
- **ENH-1710 (session-ID mapping)**: listed as soft dependency in Impact; if incomplete, session-ID extraction from JSONL filename (UUID → stem) is a fallback.

#### Additional Patterns Discovered
- **Inline Python from YAML shell actions**: Two patterns exist — `python3 -c "..."` (one-liner, e.g. `loop-router.yaml:476`) and `python3 << 'PYEOF'` heredoc (multi-line, e.g. test scripts). For calling `lookup_session_metadata()` from a loop state, a heredoc is appropriate given the multi-field return.
- **`output_numeric` with `eq`**: `worktree-health.yaml:16` (`count_worktrees` state) shows `operator: eq` with `target: 0` — the pattern for `require_issue_outcome` and `exclude_user_corrections` predicates.
- **`output_numeric` with `lt` + counter**: `refine-to-ready-issue.yaml:72` and `lib/common.yaml:40` (`retry_counter` fragment) — counter-gated retry pattern using `${context.run_dir}/`.
- **Bash-based loop testing**: `test_loops_recursive_refine.py` — `_bash(script, cwd)` helper using `subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)`. Assertions: `result.returncode == 0`, `result.stdout.strip() == "expected"`, file content checks via `(tmp_path / "file").read_text()`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/pii.py` — docstring at line 4 references `sft-corpus` FSM loop as primary consumer of `apply_pii_action()`; verify docstring consistency after loop creation [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `README.md:163` — doc count `72 FSM loops` needs correcting to `70 FSM loops` when `sft-corpus.yaml` is added (current actual count is 69; +1 = 70; doc count of 72 was already stale) [Agent 2 finding; count verified 2026-06-04]
- `CONTRIBUTING.md:122` — doc count `62 YAML files` needs correcting to `70 YAML files` when `sft-corpus.yaml` is added (current actual count is 69; +1 = 70; doc count of 62 was already stale) [Agent 2 finding; count verified 2026-06-04]
- `docs/ARCHITECTURE.md` — no loop/YAML count line found; verify that no count needs updating [Agent 2 finding]

### Tests (Supplementary)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_doc_counts.py` — `test_count_loops_top_level_glob_non_recursive` at line 46 tests `count_files("loops", "*.yaml")`; verify tests pass after doc count updates [Agent 2 finding]
- `scripts/tests/test_fsm_validation.py` — `TestArtifactIsolation` (line 1036) and `TestMetaLoopValidation` (line 827) automatically cover MR-3 artifact isolation and meta-loop detection checks for the new loop via `test_all_validate_as_valid_fsm()` [Agent 3 finding]

## Impact

- **Priority**: P3 — inherited from parent ENH-1941
- **Effort**: Medium — New YAML state + extended predicates + wiring + tests across 5 files
- **Risk**: Low — All predicates are opt-in (default pass-through); degrades gracefully when DB absent
- **Breaking Change**: No — FEAT-1826 is not yet implemented, so no existing behavior to break
- **Depends on**: ENH-1943 ✅ (`lookup_session_metadata()` — done), FEAT-1826 (`sft-corpus.yaml` skeleton — open; skeleton creation absorbed into this issue), ENH-1710 (session-ID mapping)

## Session Log
- `/ll:ready-issue` - 2026-06-04T18:00:07 - `cafa6827-e3d6-4f53-baec-3e9e9325bbdd.jsonl`
- `/ll:refine-issue` - 2026-06-04T17:40:47 - `995f6a03-33fe-4abc-9c53-edc80e0b7171.jsonl`
- `/ll:issue-size-review` - 2026-06-04T18:45:00Z - `ca366434-0e71-4ffe-883b-0f265ec672e1.jsonl`
- `/ll:wire-issue` - 2026-06-04T19:15:00Z - `e9d37087-fd50-4edb-adf2-54442d79c9be.jsonl`
- `/ll:confidence-check` - 2026-06-04T20:00:00Z - `869bf34f-df9c-42ab-8079-47750c0450ac.jsonl`
- `/ll:manage-issue` - 2026-06-04T18:10:42Z - session TBD

## Resolution

### Completed
- Created `scripts/little_loops/loops/sft-corpus.yaml` with full `stage → enrich → filter → publish → done` pipeline
- `enrich` state batch-joins `history.db` session-quality metadata via `lookup_session_metadata()`, writes to `${context.run_dir}/enriched.jsonl` (MR-3 compliant)
- Four opt-in quality predicates (`require_issue_outcome`, `exclude_user_corrections`, `min_tool_invocations`, `require_file_modifications`), each with `output_numeric` evaluator and pass-through default
- Rejection tracking: each predicate appends `{path, score, reason, timestamp}` to `${context.output_dir}/rejections.jsonl`
- Context block with four default-off flags; no harness artifact paths (avoids meta-loop classification)
- Registered `"sft-corpus"` in `test_builtin_loops.py` expected set (alphabetically between `scan-and-implement` and `sprint-build-and-validate`)
- Created `scripts/tests/test_loops_sft_corpus.py` with 17 tests covering: enrich degradation, predicate precision, opt-in gating, and rejection annotations
- Updated `scripts/little_loops/loops/README.md` Data & Testing table with sft-corpus row
- Updated `docs/guides/LOOPS_GUIDE.md` General-Purpose table with sft-corpus row
- Fixed doc counts: `README.md` (72→70 FSM loops), `CONTRIBUTING.md` (62→70 YAML files)
- `pii.py` docstring already consistent — no changes needed

### Tests
- 17/17 new tests pass (`test_loops_sft_corpus.py`)
- `test_expected_loops_exist` passes with new entry
- 53/53 doc count tests pass
- 133/133 FSM validation tests pass
- `ll-loop validate sft-corpus` reports valid
