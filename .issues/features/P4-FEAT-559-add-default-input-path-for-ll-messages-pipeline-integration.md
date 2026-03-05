---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
confidence_score: 95
outcome_confidence: 93
---

# FEAT-559: Add default `--input` path for `ll-messages` pipeline integration

## Summary

`ll-workflows analyze` requires `--input` as a mandatory argument with no default. The `--output` argument defaults to `.claude/workflow-analysis/step2-workflows.yaml`, establishing a convention for output placement. The natural companion — a default input path matching `ll-messages` output — is absent. Users must specify the full path to the JSONL file on every invocation.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 834–843 (at scan commit: a574ea0)
- **Anchor**: `in function main`, `analyze_parser.add_argument("-i", "--input", ...)`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L834-L843)
- **Code**:
```python
analyze_parser.add_argument(
    "-i",
    "--input",
    type=Path,
    required=True,    # no default
    help="Input JSONL file with user messages",
)
```

## Current Behavior

`--input` is required. The user must always provide the JSONL path. `--output` defaults to `.claude/workflow-analysis/step2-workflows.yaml`.

## Expected Behavior

`--input` has a sensible default that matches the output convention of `ll-messages`. The user can run `ll-workflows analyze --patterns p.yaml` in a project directory and have the tool auto-discover the messages JSONL.

## Motivation

`ll-workflows analyze` is designed to follow `ll-messages` in a pipeline, yet it requires the user to explicitly specify the path that `ll-messages` just wrote. This breaks the ergonomic "run two commands" pipeline pattern. A default input path matching the `ll-messages` output convention eliminates repetitive argument typing and enables simple shell aliases for routine analysis runs.

## Use Case

A developer sets up a recurring shell alias that runs `ll-messages` followed by `ll-workflows analyze`. Today they must store and pass the JSONL path:
```bash
ll-messages --output .claude/messages.jsonl && ll-workflows analyze --input .claude/messages.jsonl --patterns ...
```

With a default input path, the pipeline simplifies to:
```bash
ll-messages && ll-workflows analyze --patterns ...
```

## Acceptance Criteria

- [ ] `--input` is no longer `required=True` — it defaults to a discoverable path (e.g., `.claude/workflow-analysis/messages.jsonl` or the most recently modified `.jsonl` in `.claude/workflow-analysis/`)
- [ ] If the default path does not exist and `--input` is not provided, a clear error message names the expected path
- [ ] Explicit `--input` overrides the default
- [ ] `ll-messages` documentation / help text mentions the default path convention

## Proposed Solution

**Option A — fixed default path (simplest):**
```python
analyze_parser.add_argument(
    "-i", "--input",
    type=Path,
    default=Path(".claude/workflow-analysis/step1-patterns.jsonl"),
    help="Input JSONL file with user messages (default: .claude/workflow-analysis/step1-patterns.jsonl)",
)
```
Change `required=True` to `required=False`. Add validation in `main()`:
```python
if not args.input.exists():
    print(f"Error: input file not found: {args.input}", file=sys.stderr)
    print("Run 'll-messages' first to generate the input file.", file=sys.stderr)
    return 1
```

**Option B — auto-discover most recent JSONL (more flexible):**
Scan `.claude/workflow-analysis/` for the most recently modified `.jsonl` file if `--input` is not provided.

**Recommended:** Option A for predictability; it pairs with a convention that `ll-messages --output .claude/workflow-analysis/step1-patterns.jsonl` becomes the standard invocation.

## API/Interface

No changes to `analyze_workflows()` public API. Change is only in `main()` CLI argument parsing.

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_parser` in `main()`

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — may need update if any test passes `--input` explicitly

### Similar Patterns
- `ll-auto`, `ll-parallel` have default paths for their working directories

### Tests
- Add test verifying that missing default input path produces a helpful error message

### Documentation
- Update `ll-messages` help text to mention the expected output path convention

### Configuration
- N/A

## Implementation Steps

1. Change `--input` from `required=True` to `required=False` with a default path
2. Add existence check in `main()` before calling `analyze_workflows` when using the default
3. Update `--input` help text to document the default
4. Coordinate with `ll-messages` output path convention (or document the expected convention)

## Impact

- **Priority**: P4 - Pipeline ergonomics; reduces friction for the most common usage pattern
- **Effort**: Small - ~5 lines in `main()`
- **Risk**: Low - Additive; explicit `--input` still works identically
- **Breaking Change**: No

## Blocked By

- BUG-547 — overlapping file `scripts/little_loops/workflow_sequence_analyzer.py`; higher priority bug should land first
- FEAT-555 — overlapping file `scripts/little_loops/workflow_sequence_analyzer.py`; higher priority feature should land first
- FEAT-557 — overlapping files `scripts/little_loops/workflow_sequence_analyzer.py`, `scripts/tests/test_workflow_sequence_analyzer.py`; higher priority feature should land first
- FEAT-558

## Verification Notes

- **Verified**: 2026-03-05
- **Verdict**: VALID
- **Details**: `analyze_parser.add_argument("-i", "--input", ..., required=True)` confirmed at `workflow_sequence_analyzer.py:850-856` (shifted from L834-843 at scan commit). The feature gap is accurate — `--input` remains required with no default. `--output` has `default=None` at L864-870 (with documented default applied at runtime). No dependency issues found.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `workflow-analyzer`, `cli`, `pipeline`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06c58b54-ce27-447a-8683-f1add2d8414b.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06c58b54-ce27-447a-8683-f1add2d8414b.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06c58b54-ce27-447a-8683-f1add2d8414b.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06c58b54-ce27-447a-8683-f1add2d8414b.jsonl`

---

## Status

**Open** | Created: 2026-03-04 | Priority: P4
