---
discovered_commit: a574ea0ec555811db2490fece9aaf0819b3e3065
discovered_branch: main
discovered_date: 2026-03-04T02:11:48Z
discovered_by: scan-codebase
---

# ENH-552: `--verbose` flag only gates path echo — add per-stage progress output during analysis

## Summary

The `--verbose` / `-v` flag is registered and documented as "Print verbose progress information" but currently only gates a 3-line path echo before analysis begins. The four pipeline stages run silently. The post-analysis summary is printed unconditionally regardless of `--verbose`. This makes the flag practically useless for its stated purpose and prevents silent/piped usage.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 857–860, 883–886, 896–900 (at scan commit: a574ea0)
- **Anchor**: `in function main`, `if args.verbose:` block and summary print block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a574ea0ec555811db2490fece9aaf0819b3e3065/scripts/little_loops/workflow_sequence_analyzer.py#L883-L900)
- **Code**:
```python
if args.verbose:
    print(f"Input: {args.input}")    # only pre-analysis path echo
    print(f"Patterns: {args.patterns}")
    print(f"Output: {output_path}")

analysis = analyze_workflows(...)

# Always printed — no verbose gate:
print(f"Analyzed {analysis.metadata['message_count']} messages")
print(f"Found {len(analysis.session_links)} session links")
...
```

## Current Behavior

`--verbose` shows input/output paths before analysis. All four analysis stages run silently. The summary is always printed regardless of flag.

## Expected Behavior

Two behaviors should be possible:
1. **Non-verbose (default):** Only the output file path is printed (or nothing, for piped use).
2. **Verbose:** Per-stage progress is shown during analysis (e.g., `"Linking sessions..."`, `"Clustering entities..."`, etc.), with stage result counts.

## Motivation

Users running `ll-workflows analyze` in a pipeline (e.g., scripted after `ll-messages`) may want silent mode for clean output redirection. Users debugging or running interactively want to see stage-level progress to understand what the tool is doing on large inputs.

## Proposed Solution

**Option A — gate summary under verbose (enables silent mode):**
```python
if args.verbose:
    print(f"Analyzed {analysis.metadata['message_count']} messages")
    print(f"Found {len(analysis.session_links)} session links")
    ...
```

**Option B — add per-stage progress (fulfills stated purpose):**
Pass `verbose=args.verbose` to `analyze_workflows`, add progress prints around each pipeline stage:
```python
if verbose:
    print(f"[1/4] Linking sessions across {len(sessions)} session(s)...", file=sys.stderr)
session_links = _link_sessions(sessions)
if verbose:
    print(f"      → {len(session_links)} link(s) found")
```

**Recommended:** Implement Option B (per-stage progress to stderr), keep summary print under verbose gate (Option A). Use stderr for progress so stdout can carry only the output path for piping.

## Scope Boundaries

- In scope: add `verbose` param to `analyze_workflows`, add per-stage progress prints, gate summary
- Out of scope: changing the YAML output format or adding new analysis stages

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — `main`, `analyze_workflows`, optionally stage functions

### Dependent Files (Callers/Importers)
- `scripts/tests/test_workflow_sequence_analyzer.py` — `analyze_workflows` signature change (backward compatible if `verbose=False` default)

### Similar Patterns
- `ll-auto` and `ll-parallel` emit per-stage progress to stderr in their CLIs

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — test that `verbose=True` emits progress lines, `verbose=False` is quiet

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `verbose: bool = False` parameter to `analyze_workflows`
2. Add per-stage progress prints around the four pipeline calls in `analyze_workflows`
3. Pass `args.verbose` from `main()` into `analyze_workflows`
4. Gate the summary `print` block under `if args.verbose:` in `main()`

## Impact

- **Priority**: P4 - UX improvement for CLI; non-blocking but the current behavior is misleading
- **Effort**: Small - ~15 lines of changes across two functions
- **Risk**: Low - Additive change; `verbose` defaults to `False` so existing callers are unaffected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocked By

- FEAT-558

## Blocks

- FEAT-557 — overlapping files `scripts/little_loops/workflow_sequence_analyzer.py`, `scripts/tests/test_workflow_sequence_analyzer.py`; same priority but lower ID should land first

## Labels

`enhancement`, `ux`, `workflow-analyzer`, `captured`

## Session Log

- `/ll:scan-codebase` - 2026-03-04T02:11:48Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5ddf56-1cf2-4ecc-a316-e01380324f20.jsonl`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P4
