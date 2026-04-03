---
id: FEAT-937
type: FEAT
priority: P5
status: open
discovered_date: 2026-04-03
discovered_by: capture-issue
testable: true
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
  - ".loops/lib/common.yaml"

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

TBD - requires investigation

### High-Level Design

1. **Fragment libraries**: YAML files in `.loops/lib/` (or any user-specified path) with a top-level `fragments:` dict mapping names to partial `StateConfig` dicts.
2. **`import:` key**: Top-level list of library paths, resolved relative to the project root. Loaded before `states` are parsed.
3. **Merge semantics**: `fragment: <name>` in a state triggers a deep merge of the named fragment's dict into the state dict, with state-level keys taking precedence.
4. **Local override**: In-loop `fragments:` block (in-file fragments, Option B) takes precedence over imported fragments with the same name.
5. **Validation**: The validator checks that all `fragment:` references resolve to a known fragment (local or imported). Unknown fragment references are a fatal validation error.
6. **`ll-loop show`**: Display which fragments are imported and where they're used.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `imports: list[str]` and `fragments: dict[str, dict]` fields to `FSMLoop`; add `fragment: str | None` field to `StateConfig`
- `scripts/little_loops/fsm/validation.py` — validate fragment references resolve; warn on unused fragments
- `scripts/little_loops/fsm/runners.py` or `executor.py` — TBD: where `FSMLoop.from_dict` calls resolve imports
- `scripts/little_loops/cli/loop_cli.py` (or equivalent) — update `show` subcommand to display imported fragments
- `scripts/little_loops/loops/*.yaml` (built-in loops) — migrate repeated patterns to shared library fragments

### Dependent Files (Callers/Importers)
- TBD - use grep to find all callers of `FSMLoop.from_dict`

### Similar Patterns
- `context_passthrough: true` — existing mechanism for cross-loop variable sharing (different level: runtime, not parse-time)
- `LoopConfigOverrides.from_dict` — existing parse-time config merging pattern to follow
- YAML anchors (`&anchor` / `<<: *anchor`) — existing zero-cost same-file alternative; document as complementary pattern

### Tests
- `scripts/tests/fsm/` — add tests for fragment resolution, merge semantics, import loading, validation errors
- Test cases: fragment not found, circular import (if libraries can import each other), local override beats imported, deep merge correctness

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add "Reusable State Fragments" section after "Composable Sub-Loops"
- `docs/generalized-fsm-loop.md` — add `import:` and `fragments:` to the schema reference
- `skills/create-loop/reference.md` — update to mention fragment libraries as an authoring option

### Configuration
- N/A — no new config keys; library paths are specified in the loop YAML `import:` list

## Implementation Steps

1. **Schema**: Add `imports`, `fragments`, and `StateConfig.fragment` fields to `schema.py`; update `to_dict`/`from_dict` to skip these at serialization (fragments are expanded, not preserved)
2. **Resolver**: Implement a `resolve_fragments(loop_dict, project_root)` function that loads library files, merges fragment namespaces (local > imported), and expands `fragment:` references in state dicts using deep merge
3. **Validation**: Update `validation.py` to check that all `fragment:` references resolve; add warning for declared-but-unused fragments
4. **CLI**: Update `ll-loop show` to list imported libraries and which states use which fragments
5. **Built-in library**: Create `.loops/lib/common.yaml` (ships with little-loops) with canonical versions of `shell_exit`, `retry_counter`, `llm_quality_gate`; migrate matching patterns in built-in loops
6. **Docs + tests**: Add unit tests for resolver (merge semantics, missing fragment, import loading) and update `LOOPS_GUIDE.md`

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
def resolve_fragments(raw_loop_dict: dict, project_root: Path) -> dict:
    """Load imports, merge fragment namespaces, expand fragment: references.
    Returns a raw dict with all fragment: keys expanded — ready for FSMLoop.from_dict.
    """
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `fsm`, `loops`, `dx`, `captured`

## Status

**Open** | Created: 2026-04-03 | Priority: P5

## Session Log
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16657133-9de4-4706-850b-b65f32a1bda2.jsonl`
