---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# FEAT-557: Add `--format json` output option to `ll-workflows` — currently only YAML supported

## Summary

`ll-workflows analyze` writes output exclusively as YAML. All five dataclasses implement `to_dict()` methods that return plain Python dicts, making JSON serialization trivial. Adding a `--format json` (or `--json`) flag enables piping `ll-workflows` output directly into other tools without an intermediate conversion step.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 789–794 (output serialization block) (at scan commit: a574ea0)
- **Anchor**: `in function analyze_workflows`, `if output_file:` block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L789-L794)
- **Code**:
```python
if output_file:
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        yaml.dump(analysis.to_dict(), f, default_flow_style=False, sort_keys=False)
```

## Current Behavior

Output is always YAML. There is no way via the CLI to get JSON output.

## Expected Behavior

Users can pass `--format json` (or `-f json`) to get JSON output. The default remains YAML for backward compatibility.

## Motivation

YAML output is not directly usable in shell pipelines without an intermediate conversion step (e.g., `yq` or `python -c "import yaml, json"`). JSON is natively supported by `jq` and most shell scripting tools. Adding `--format json` enables `ll-workflows analyze | jq '.workflows[].name'` without intermediate steps, making the tool composable in automation scripts.

## Use Case

A developer writes a shell script that pipes `ll-workflows` output into `jq` for filtering. Currently they must install a YAML→JSON converter or post-process the YAML file manually. With `--format json`, they can write:
```bash
ll-workflows analyze --input msgs.jsonl --patterns p.yaml --format json | jq '.workflows[].name'
```

## Acceptance Criteria

- [ ] `--format yaml` (default) produces the same output as today
- [ ] `--format json` produces a JSON file equivalent to `json.dumps(analysis.to_dict(), indent=2)`
- [ ] Default output file extension changes to `.json` when `--format json` is used and `--output` is not specified
- [ ] Invalid `--format` value produces a clear error message

## Proposed Solution

```python
# Add to analyze_parser:
analyze_parser.add_argument(
    "-f", "--format",
    choices=["yaml", "json"],
    default="yaml",
    help="Output format (default: yaml)",
)

# Update default output path logic in main():
if args.format == "json":
    default_output = Path(".claude/workflow-analysis/step2-workflows.json")
else:
    default_output = Path(".claude/workflow-analysis/step2-workflows.yaml")

# In analyze_workflows, add format parameter:
def analyze_workflows(..., output_format: str = "yaml") -> WorkflowAnalysis:
    ...
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            if output_format == "json":
                json.dump(analysis.to_dict(), f, indent=2, default=str)
            else:
                yaml.dump(analysis.to_dict(), f, default_flow_style=False, sort_keys=False)
```

Note: `json` is already imported (used in `_load_messages`). `default=str` handles any `datetime` or `set` objects that might appear in `to_dict()` output.

## API/Interface

```python
# analyze_workflows signature addition:
def analyze_workflows(
    messages_file: Path,
    patterns_file: Path,
    output_file: Path | None = None,
    output_format: str = "yaml",   # new
) -> WorkflowAnalysis: ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `analyze_workflows` signature, `main()` arg parser and output logic

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — add test for JSON output format

### Similar Patterns
- N/A — no other ll-* tools have multiple output formats yet

### Tests
- Add `test_json_output_format` to `TestAnalyzeWorkflows`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--format` argument to `analyze_parser` in `main()`
2. Add `output_format` parameter to `analyze_workflows` with `"yaml"` default
3. Branch output serialization on `output_format` in `analyze_workflows`
4. Update default output path in `main()` based on format choice
5. Add test asserting JSON output parses correctly with `json.loads`

## Impact

- **Priority**: P4 - Quality-of-life for scripted/pipeline usage; YAML works fine for interactive use
- **Effort**: Small - ~15 lines of changes; `json` module already imported
- **Risk**: Low - Additive; default behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `workflow-analyzer`, `cli`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P4
