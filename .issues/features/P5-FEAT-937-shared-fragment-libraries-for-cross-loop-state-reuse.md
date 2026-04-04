---
id: FEAT-937
type: FEAT
priority: P5
status: open
discovered_date: 2026-04-03
discovered_by: capture-issue
testable: true
confidence_score: 100
outcome_confidence: 64
---

# FEAT-937: Shared Fragment Libraries for Cross-Loop State Reuse

## Summary

Introduce shared state fragment libraries — YAML files in `.loops/lib/` that define named, reusable partial state definitions — which any loop can import via a top-level `import:` key. This closes the reusability gap that currently exists between whole sub-loops (full YAML file + execution overhead) and copy-pasting state definitions across loops.

## Current Behavior

Reuse in the FSM loop system operates at two extremes only:
- **Whole sub-loops** (`loop:` field): reuse an entire loop as a child FSM. Requires a separate YAML file, adds handoff/context overhead, and is overkill for sharing a state shape (e.g., "shell command + exit code evaluator").
- **Copy-paste**: state definitions like the retry counter in `refine-to-ready-issue.yaml`, the `shell_exit` pattern, and the LLM structured evaluator shape are duplicated across dozens of built-in loops with minor variations. These copies diverge over time.

There is no mechanism to define a partial state (a "fragment") once and reference it from multiple loop files.

## Expected Behavior

Users can define named state fragments in `.loops/lib/*.yaml` files and import them into any loop:

```yaml
# .loops/lib/common.yaml
fragments:
  shell_exit:
    action_type: shell
    evaluate:
      type: exit_code

  retry_counter:
    action: |
      FILE=".loops/tmp/${context.counter_key}"
      N=$(cat "$FILE" 2>/dev/null || echo 0)
      N=$((N + 1)); printf '%s' "$N" > "$FILE"; echo "$N"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: "${context.max_retries}"
```

```yaml
# .loops/my-loop.yaml
name: my-loop
import:
  - "lib/common.yaml"

states:
  lint:
    fragment: shell_exit    # inherits action_type + evaluate
    action: "ruff check ."
    on_yes: done
    on_no: fix              # routing always caller-defined

  check_retries:
    fragment: retry_counter
    on_yes: refine_issue
    on_no: failed
```

Fragment merging is **deep-first-wins**: state-level fields override fragment fields at every level, including nested objects like `evaluate`. This allows a fragment to set `evaluate.type` and `evaluate.operator` while the state provides only `evaluate.target`.

Parameterization uses the existing `${context.*}` interpolation system — no new namespace needed. Fragment resolution happens at parse time in `FSMLoop.from_dict`, so the engine never sees `fragment:` keys.

## Motivation

- **DRY across built-in loops**: At least 8 built-in loops duplicate the retry counter pattern. `shell_exit` appears in every quality-check loop. Shared fragments let the canonical version live once.
- **Reduces authoring errors**: Users copy-pasting states introduce subtle bugs (wrong operator, missing `on_error`, wrong evaluator type). Referencing a tested fragment eliminates a class of mistakes.
- **Natural extension path**: In-file fragments (Option B, `fragments:` block in the same YAML) can ship first as a lower-risk feature. Cross-file `import:` is the follow-on that unlocks project-wide reuse.
- **Composable with sub-loops**: Fragments handle state-level reuse; sub-loops handle loop-level reuse. They solve different granularities and are complementary.

## Proposed Solution

### High-Level Design

1. **Fragment libraries**: YAML files in `.loops/lib/` (or any user-specified path) with a top-level `fragments:` dict mapping names to partial `StateConfig` dicts.
2. **`import:` key**: Top-level list of library paths, resolved relative to the importing loop file's directory (i.e. `Path(loop_file).parent / import_path`). Loaded before `states` are parsed.
3. **Merge semantics**: `fragment: <name>` in a state triggers a deep merge of the named fragment's dict into the state dict, with state-level keys taking precedence.
4. **Local override**: In-loop `fragments:` block (in-file fragments, Option B) takes precedence over imported fragments with the same name.
5. **Validation**: The validator checks that all `fragment:` references resolve to a known fragment (local or imported). Unknown fragment references are a fatal validation error.
6. **`ll-loop show`**: Display which fragments are imported and where they're used.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `imports: list[str]` and `fragments: dict[str, dict]` fields to `FSMLoop` (`FSMLoop.__init__` at line 455); add `fragment: str | None` field to `StateConfig` (line 180); update `to_dict`/`from_dict` to skip these (fragment fields are consumed at resolve time, not serialized)
- `scripts/little_loops/fsm/validation.py:76` — add `"import"` and `"fragments"` to `KNOWN_TOP_LEVEL_KEYS` frozenset to suppress spurious warnings
- `scripts/little_loops/fsm/validation.py:479` — call `resolve_fragments(data, loop_file.parent)` between `yaml.safe_load` and `FSMLoop.from_dict(data)` in `load_and_validate()`; also add fragment-reference validation to `validate_fsm()` for post-parse checks
- **`scripts/little_loops/fsm/fragments.py`** — **new file**; implement `resolve_fragments(raw_loop_dict, project_root)` and `_deep_merge(base, override)` helper
- `scripts/little_loops/cli/loop/info.py:675` — update `cmd_show` to display `import:` paths from `spec` dict in the config summary line
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `"import"` (type: array, items: string) and `"fragments"` (type: object) as recognized top-level properties; also add `"fragment"` (type: string) to the state object schema; prevents schema-based validators from rejecting loops that use the feature
- `scripts/little_loops/loops/*.yaml` (10 built-in loops) — migrate `exit_code` evaluator states to reference `shell_exit` fragment from new `scripts/little_loops/loops/lib/common.yaml`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py:479` — **only production call site** of `FSMLoop.from_dict(data)` inside `load_and_validate()`; this is where `resolve_fragments(data, loop_file.parent)` must be called (between `yaml.safe_load` at line 452 and `FSMLoop.from_dict` at line 479)
- `scripts/little_loops/fsm/validation.py:76` — `KNOWN_TOP_LEVEL_KEYS` frozenset must have `"import"` and `"fragments"` added, otherwise `load_and_validate` emits spurious unknown-key warnings for every loop that uses the feature
- `scripts/tests/test_review_loop.py:149,195` — test-only direct callers; no changes needed
- `scripts/tests/test_fsm_schema_fuzz.py:394,397,423,460` — fuzz test callers; no changes needed

### Similar Patterns
- `context_passthrough: true` — existing mechanism for cross-loop variable sharing (runtime, not parse-time); defined in `StateConfig` at `schema.py:231`
- `LoopConfigOverrides.from_dict` at `schema.py:429` — existing parse-time config merging pattern with nested-key traversal; model the resolver's dict-merge style after this
- `StateConfig.from_dict` at `schema.py:279` — current implementation silently ignores unknown keys (e.g., `fragment:`), so no change is needed there; the resolver consumes `fragment:` before `from_dict` is ever called
- **`interpolate_dict` at `scripts/little_loops/fsm/interpolation.py:209`** — closest structural analog to `resolve_fragments`: recursively walks a `dict[str, Any]`, returns a new dict (non-mutating), handles nested dicts and lists, passes non-string scalars through unchanged. Model `resolve_fragments` after this pattern.
- YAML anchors (`&anchor` / `<<: *anchor`) — existing zero-cost same-file alternative; document as complementary pattern

### JSON Schema
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema used to validate loop YAML files; must add `"import"` (array of strings) and `"fragments"` (object) as recognized top-level properties alongside existing `"name"`, `"initial"`, `"states"` etc. Currently defines `"required": ["name", "initial", "states"]` and `"additionalProperties": false` (or equivalent), so without this update the schema validator would reject loops that use the feature

### Tests
- `scripts/tests/test_builtin_loops.py` — validates all built-in loop YAML files via `load_and_validate`; after migrating 10 built-in loops to use `import: ["lib/common.yaml"]`, this test suite must still pass — requires that `lib/common.yaml` exists at `scripts/little_loops/loops/lib/common.yaml` before the migration, or the tests will fail with `FileNotFoundError` on fragment resolution
- `scripts/tests/test_fsm_fragments.py` — new file; use these existing test helpers:
  - `make_state()` / `make_fsm()` factory functions at `test_fsm_schema.py:39-77` — build minimal valid FSMs without boilerplate
  - `tmp_path` + inline YAML write pattern from `test_fsm_executor.py:3394` — write library YAML to a temp dir, call `resolve_fragments` against it; this is the exact pattern for isolating fragment resolution tests
  - `test_fsm_schema.py:1797` (`test_fsm_loop_from_dict_with_config_block`) — config-block parse pattern to model post-resolve `FSMLoop.from_dict` assertions after
- Test cases: fragment not found → `ValueError`, import file not found → `FileNotFoundError`, local `fragments:` block overrides imported same-name fragment, deep merge correctness (state keys win at every level), `fragment:` absent = no-op, `KNOWN_TOP_LEVEL_KEYS` no longer warns for `import`/`fragments`

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add "Reusable State Fragments" section after "Composable Sub-Loops"
- `docs/generalized-fsm-loop.md` — add `import:` and `fragments:` to the schema reference
- `skills/create-loop/reference.md` — update to mention fragment libraries as an authoring option

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The sole production call path through `FSMLoop.from_dict`:**
1. `scripts/little_loops/cli/loop/_helpers.py:148` — `load_loop_with_spec()` calls `load_and_validate(path)`
2. `scripts/little_loops/fsm/validation.py:452,479` — `load_and_validate()` does `yaml.safe_load(f)` then `FSMLoop.from_dict(data)`
3. The resolver call `resolve_fragments(data, loop_file.parent)` belongs between these two lines (line 479 becomes the insertion point)

**Built-in loop migration targets (10 loops with `exit_code` evaluator — canonical `shell_exit` fragment candidates):**
`dead-code-cleanup.yaml`, `docs-sync.yaml`, `fix-quality-and-tests.yaml`, `harness-multi-item.yaml`, `harness-single-shot.yaml`, `issue-refinement.yaml`, `prompt-across-issues.yaml`, `refine-to-ready-issue.yaml`, `sprint-build-and-validate.yaml`, `test-coverage-improvement.yaml` — all in `scripts/little_loops/loops/`

**No existing deep-merge utility** — `_deep_merge(base, override)` must be written as a private helper inside the new resolver module (`scripts/little_loops/fsm/fragments.py`); model its recursive dict-walk after `interpolate_dict` at `interpolation.py:209` (same non-mutating, recurse-into-nested-dicts pattern)

**`ll-loop show` integration point:** `scripts/little_loops/cli/loop/info.py:675` — `config_parts` list is built then printed; add an `imports` entry from `spec.get("import", [])` here; the raw `spec` dict is already available via `load_loop_with_spec()`

### Configuration
- N/A — no new config keys; library paths are specified in the loop YAML `import:` list

## Implementation Steps

1. **Schema** (`scripts/little_loops/fsm/schema.py`): Add `imports: list[str] = field(default_factory=list)` and `fragments: dict[str, dict] = field(default_factory=dict)` to `FSMLoop` (after `labels` at line 490); add `fragment: str | None = None` to `StateConfig` (after `context_passthrough` at line 231); update `to_dict` to skip these fields (consumed at resolve time)
2. **Resolver** (new `scripts/little_loops/fsm/fragments.py`): Implement `_deep_merge(base, override)` and `resolve_fragments(raw_loop_dict, project_root)` — loads library files (YAML with top-level `fragments:` dict), merges namespaces (local `fragments:` block overrides imported), expands `fragment:` in each state dict via deep merge (state keys win)
3. **Validation hook** (`scripts/little_loops/fsm/validation.py`): (a) Add `"import"` and `"fragments"` to `KNOWN_TOP_LEVEL_KEYS` at line 76; (b) call `resolve_fragments(data, loop_file.parent)` at line 479 before `FSMLoop.from_dict(data)` — `loop_file` is the `Path` already in scope from `load_and_validate(path)`; (c) extend `validate_fsm()` to emit ERROR for unresolved `fragment:` references and WARNING for declared-but-unused fragments
3a. **JSON Schema** (`scripts/little_loops/fsm/fsm-loop-schema.json`): Add `"import"` (array of strings), `"fragments"` (object), and `"fragment"` (string) to the schema so schema-based validators don't reject loops using the feature; do this in the same pass as the `KNOWN_TOP_LEVEL_KEYS` update
4. **CLI display** (`scripts/little_loops/cli/loop/info.py:675`): In `cmd_show`, append `f"imports: {', '.join(spec.get('import', []))}"` to `config_parts` when the list is non-empty
5. **Built-in library** (`scripts/little_loops/loops/lib/common.yaml`): Create with `shell_exit`, `retry_counter`, `llm_quality_gate` fragments; migrate 10 built-in loops (see migration targets above) to use `import: ["lib/common.yaml"]` + `fragment: shell_exit` (path is relative to the loop file's directory, so `lib/common.yaml` resolves to `scripts/little_loops/loops/lib/common.yaml` for built-in loops)
6. **Tests** (`scripts/tests/test_fsm_fragments.py`): Cover `resolve_fragments` unit cases: missing fragment → `ValueError`, import file not found → `FileNotFoundError`, local overrides imported, deep merge at every nesting level, `fragment:` absent = no-op; use `make_state`/`make_fsm` helpers from `test_fsm_schema.py:39` and `tmp_path` + inline YAML write from `test_fsm_executor.py:3394` (`TestSubLoopExecution.test_sub_loop_success_routes_to_on_success` — first test in the sub-loop class, uses `tmp_path` + `.write_text()` to create child loop YAML inline)

## Impact

- **Priority**: P5 - Reduces authoring friction and copy-paste maintenance burden; not blocking current workflows
- **Effort**: Medium - Schema + resolver + validator + CLI display + built-in library migration
- **Risk**: Low - Pure parse-time transformation; engine never sees `fragment:` keys; existing loops unaffected
- **Breaking Change**: No — additive schema fields; all existing loop YAML remains valid

## API/Interface

```python
# schema.py additions (sketch)
@dataclass
class FSMLoop:
    imports: list[str] = field(default_factory=list)   # library paths
    fragments: dict[str, dict] = field(default_factory=dict)  # in-file fragments

@dataclass
class StateConfig:
    fragment: str | None = None   # name of fragment to inherit from

# resolver (new function)
def resolve_fragments(raw_loop_dict: dict, loop_dir: Path) -> dict:
    """Load imports, merge fragment namespaces, expand fragment: references.
    Import paths are resolved relative to loop_dir (the importing loop file's directory),
    so built-in loops find their lib/ naturally and user loops find .loops/lib/ naturally.
    Returns a raw dict with all fragment: keys expanded — ready for FSMLoop.from_dict.
    """
```

## Related Key Documentation

- [`docs/guides/LOOPS_GUIDE.md`](../../docs/guides/LOOPS_GUIDE.md) — Loop authoring guide; needs "Reusable State Fragments" section added after the existing "Composable Sub-Loops" section (see TOC entry at line 17)
- [`docs/generalized-fsm-loop.md`](../../docs/generalized-fsm-loop.md) — FSM loop schema reference; needs `import:` and `fragments:` top-level keys documented alongside existing schema entries
- [`skills/create-loop/reference.md`](../../skills/create-loop/reference.md) — Loop authoring reference for the `/ll:create-loop` skill; needs fragment libraries listed as an authoring option alongside sub-loops
- [`scripts/little_loops/loops/README.md`](../../scripts/little_loops/loops/README.md) — Built-in loops index; should document the new `lib/common.yaml` library and its available fragments

## Labels

`feat`, `fsm`, `loops`, `dx`, `captured`

## Status

**Open** | Created: 2026-04-03 | Priority: P5

## Verification Notes

Verified 2026-04-03 by `/ll:verify-issues`. All file paths, line numbers, and code claims checked against current codebase. One stale line reference corrected: `test_fsm_executor.py:3436` → `3394` in the Tests/Similar Patterns section (Implementation Steps already had the correct value). All other references confirmed accurate.

## Session Log
- `/ll:verify-issues` - 2026-04-04T04:22:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1d17848-e950-4ccb-89e0-b0c8a73d95d2.jsonl`
- `/ll:refine-issue` - 2026-04-04T04:18:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57941e0f-80a7-42e3-8600-7abe18193082.jsonl`
- `/ll:refine-issue` - 2026-04-04T04:17:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57941e0f-80a7-42e3-8600-7abe18193082.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42c53c22-403e-4bdc-b147-7dae4ff089f6.jsonl`
- `/ll:refine-issue` - 2026-04-04T04:02:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ddb48b85-b51f-420f-ba05-37e1c4b6810b.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16657133-9de4-4706-850b-b65f32a1bda2.jsonl`
