---
id: ENH-936
type: ENH
priority: P3
status: open
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 97
outcome_confidence: 71
---

# ENH-936: Add Categories and Labels to FSM Loop Schema

## Summary

Add `category` and `labels` metadata fields to the FSM loop YAML schema, and expose filtering by these fields in `ll-loop list`. Currently 33+ loops are listed without any grouping, making it hard to find the right loop for a task.

## Current Behavior

`ll-loop list` dumps all loops in a flat list with only `name` and `description`. There is no way to group or filter by purpose (e.g., "code quality", "AI optimization", "issue management"). The schema only supports `name`, `description`, `initial`, `max_iterations`, `timeout`, and `states`.

## Expected Behavior

- Loop YAML files can declare a `category` (single string) and optional `labels` (list of strings) at the top level
- `ll-loop list` groups loops by category when no filter is given
- `ll-loop list --category <name>` filters to a specific category
- `ll-loop list --label <label>` filters to loops matching a label
- Built-in loops and user-defined loops both support these fields

## Motivation

With 33+ loops and growing, users cannot quickly discover which loop to run. Issues use a `P[0-5]-[TYPE]` file-naming convention and `Labels:` frontmatter for similar organization. Applying the same concept to loops improves discoverability and aligns with the existing mental model in the project.

## Proposed Solution

1. Add optional `category: str` and `labels: list[str]` fields to the FSM loop loader (likely `scripts/little_loops/fsm/` or wherever loop YAML is parsed and validated)
2. Annotate all existing built-in loops in `scripts/little_loops/loops/*.yaml` with appropriate categories (e.g., `apo`, `code-quality`, `issue-management`, `harness`, `meta`)
3. Extend `cmd_list` in `scripts/little_loops/cli/loop/info.py` to:
   - Accept `--category` and `--label` filter flags
   - Group output by category when listing all loops (similar to how `ll-issues list` groups by type)
4. Update `ll-loop list` argparser in `scripts/little_loops/cli/loop/__init__.py` with the new flags

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--category` and `--label` args to the `list` subparser (line 164, after existing `--builtin` arg at line 171)
- `scripts/little_loops/cli/loop/info.py` — update `cmd_list` (line 41) to support filtering and grouped display; extend `_load_loop_meta()` (line 28) to also return `category` and `labels`
- `scripts/little_loops/fsm/schema.py` — `FSMLoop` dataclass (line 455): add `category: str = ""` and `labels: list[str] = field(default_factory=list)`; update `from_dict()` (line 531) and `to_dict()` (line 490)
- All `scripts/little_loops/loops/*.yaml` (34 files) — add `category:` and optional `labels:` to each

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:334` — calls `cmd_list(args, loops_dir)`, passes `args` namespace; `cmd_list` must use `getattr(args, "category", None)` / `getattr(args, "label", None)` to stay backward-compatible with existing tests
- `scripts/tests/test_ll_loop_commands.py` — has `test_list_*` tests at lines 123–316 that construct `argparse.Namespace(running=False, status=None)`; these will need `category=None, label=None` added to the namespace or `cmd_list` must use `getattr` with defaults

### Similar Patterns
- `scripts/little_loops/cli/issues/__init__.py:88` — `--type` filter (`choices=["BUG", "FEAT", "ENH"]`) — simple `choices` pattern
- `scripts/little_loops/cli/issues/__init__.py:177` — `--label` with `action="append"`, `dest="label"` (repeatable flag) — exact pattern to follow for `--label` in loop list
- `scripts/little_loops/cli/auto.py:52` — `--category` flag on `ll-auto` — convention to follow for flag name
- `scripts/little_loops/cli/issues/search.py:254-271` — exact filter consumption pattern to follow in `cmd_list`: `type_filters = getattr(args, "type", None) or []` / `label_filters = getattr(args, "label", None) or []`, then `if not any(lf.lower() in labels for lf in label_filters): continue`
- `scripts/little_loops/cli/issues/list_cmd.py:119-138` — grouped display bucket pattern; for loops use a dynamic dict (categories are user-defined strings, not a fixed set like BUG/FEAT/ENH)

### Tests
- `scripts/tests/test_ll_loop_commands.py` — existing `TestLoopListCommand` class (line 123); add `TestLoopListCategoryFilter` tests following same pattern (create temp YAMLs with `category:` field, call `cmd_list`, assert grouping/filtering output)
- `scripts/tests/test_builtin_loops.py` — may need updates if it validates loop schema fields

### Documentation
- `docs/` — no specific loop list docs found that need updating

### Configuration
- No config schema changes needed (`category`/`labels` are pure YAML fields read at load time)

### Note: oracles subdirectory
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` exists in a subdirectory; `cmd_list`'s current `builtin_dir.glob("*.yaml")` does NOT pick it up. Whether to include oracles in the categorized listing is an open question for the implementer.

### Additional Files to Modify (from deeper research)
- `scripts/little_loops/fsm/validation.py:76-94` — `KNOWN_TOP_LEVEL_KEYS` frozenset: `category` and `labels` are NOT in this set; adding them to YAML files without updating this set will trigger `ValidationSeverity.WARNING` on every loop load. This set **must** be updated.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for loop YAML validation; new `category` (string) and `labels` (array of strings) properties must be declared here.

### Note: dataset-curation.yaml
- `scripts/little_loops/loops/dataset-curation.yaml` already has `category`/`labels` fields in its YAML — it is the one existing loop using these fields. Inspect it as a concrete example of the intended format.

### Note: _load_loop_meta bypasses load_and_validate
- `info.py:28` — `_load_loop_meta()` calls `yaml.safe_load` directly; it bypasses `fsm/validation.py`. The `cmd_list` filter logic can read `category`/`labels` from this lightweight function without touching the full FSM load pipeline.

## Implementation Steps

1. **`validation.py:76-94` — `KNOWN_TOP_LEVEL_KEYS`**: add `"category"` and `"labels"` to this frozenset — this must come first or existing YAMLs with those fields will emit warnings immediately
2. **`fsm/fsm-loop-schema.json`**: add `category` (type: string) and `labels` (type: array of strings) to the JSON Schema properties
3. **`schema.py:455` — `FSMLoop` dataclass**: add `category: str = ""` and `labels: list[str] = field(default_factory=list)` after the `input_key` field (line 487); update `from_dict()` (line 546 `cls(...)` call) with `category=data.get("category", "")` and `labels=data.get("labels", [])`; update `to_dict()` to emit them when non-empty
4. **`info.py:28` — `_load_loop_meta()`**: extend to return a dict `{"description": ..., "category": ..., "labels": ...}` instead of a plain string, then update all call sites in `cmd_list` (lines 113–138) accordingly; note the issues grouping pattern at `cli/issues/list_cmd.py:119` uses hardcoded buckets — loop grouping needs a dynamic `dict[str, list[Path]]` since categories are user-defined
5. **`info.py:41` — `cmd_list`**: add category/label filtering using `getattr(args, "category", None)` and `getattr(args, "label", None)`; change default view to group loops by category; loops without a `category` fall into an `"uncategorized"` bucket; update JSON output (line 105–107) to include `category` and `labels`
6. **`__init__.py:164` — list subparser**: add `--category` and `--label` args following the `action="append"` pattern from `cli/issues/__init__.py:177`
7. **All 34 `loops/*.yaml` files**: add `category:` to each. Check `dataset-curation.yaml` first — it already has these fields and shows the format. Suggested groupings: `issue-management` (issue-refinement, refine-to-ready-issue, issue-staleness-review, issue-size-split, issue-discovery-triage, backlog-flow-optimizer, prompt-across-issues), `code-quality` (fix-quality-and-tests, dead-code-cleanup, test-coverage-improvement, incremental-refactor), `apo` (apo-feedback-refinement, apo-contrastive, apo-beam, apo-opro, apo-textgrad), `rl` (rl-rlhf, rl-bandit, rl-policy, rl-coding-agent), `evaluation` (evaluation-quality, eval-driven-development, agent-eval-improve, prompt-regression-test), `harness` (harness-single-shot, harness-multi-item, general-task, greenfield-builder), `meta` (worktree-health, context-health-monitor, docs-sync, sprint-build-and-validate), `data` (examples-miner, dataset-curation)
8. **`test_ll_loop_commands.py`**: update existing `test_list_*` namespace mocks to include `category=None, label=None`; add new tests for grouped display and `--category`/`--label` filtering; also check `test_fsm_schema.py` and `test_builtin_loops.py` for schema field coverage
9. **Smoke test**: run `ll-loop list` and verify category-grouped output; run `ll-loop list --category apo` to verify filter

## Impact

- **Priority**: P3 - Usability improvement, not blocking
- **Effort**: Medium - Schema change is small; the bulk is annotating 33+ YAML files and updating display logic
- **Risk**: Low - additive change; existing loops without `category`/`labels` fall back to "uncategorized" group

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `cli`, `usability`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ad79933-6e71-429b-bca6-5b79f40d8a4a.jsonl`
- `/ll:refine-issue` - 2026-04-03T21:55:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b97f38eb-10b6-49e1-9b95-16bde969e44b.jsonl`

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d21e2100-9421-4796-91d0-fde897d2aa2b.jsonl`

---

## Status

**Open** | Created: 2026-04-03 | Priority: P3
