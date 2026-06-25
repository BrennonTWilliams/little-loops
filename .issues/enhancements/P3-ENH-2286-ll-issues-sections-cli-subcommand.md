---
id: ENH-2286
type: ENH
priority: P3
status: open
parent: ENH-2272
relates_to:
- ENH-2285
- FEAT-2274
captured_at: '2026-06-25T00:00:00Z'
discovered_date: 2026-06-25
discovered_by: issue-size-review
---

# ENH-2286: ll-issues sections CLI subcommand

## Summary

Implement the `ll-issues sections <type>` subcommand. Depends on ENH-2285
(`resolve_templates_dir`). Produces the CLI accessor that the callsite rewrites
(ENH-2288) will invoke, and replaces the ~60s `find /` filesystem walk with a
~50ms deterministic lookup.

## Parent Issue

Decomposed from ENH-2272: ll-issues sections accessor + project-local template deploy

## Proposed Solution

### New file: `scripts/little_loops/cli/issues/sections.py`

```python
from little_loops.issue_template import resolve_templates_dir

def cmd_sections(config: BRConfig, args: argparse.Namespace) -> int:
    issue_type = args.type.lower()
    if issue_type not in ("bug", "feat", "enh", "epic"):
        print(f"Error: invalid type '{args.type}' — must be bug, feat, enh, or epic", file=sys.stderr)
        return 1
    templates_dir = resolve_templates_dir(config)
    json_path = templates_dir / f"{issue_type}-sections.json"
    if not json_path.exists():
        print(f"Error: template not found: {json_path}", file=sys.stderr)
        return 1
    if getattr(args, "path", False):
        print(json_path)
        return 0
    print(json_path.read_text())
    return 0
```

### Registration in `scripts/little_loops/cli/issues/__init__.py`

Add parser (after the `path_p` block, ~line 374):
```python
sec_p = subs.add_parser("sections", aliases=["sec"], help="Print section template JSON for an issue type")
sec_p.set_defaults(command="sections")
sec_p.add_argument("type", help="Issue type: bug, feat, enh, or epic")
sec_p.add_argument("--path", action="store_true", help="Print path to template file instead of JSON content")
add_config_arg(sec_p)
```

Add dispatch (before the final `return 1`, after `finalize-decomposition` block):
```python
if args.command == "sections":
    from little_loops.cli.issues.sections import cmd_sections
    return cmd_sections(config, args)
```

The import is deferred inside the `with cli_event_context(...)` block, following
the `from little_loops.cli.issues.path_cmd import cmd_path` pattern.

## Files to Modify/Create

- `scripts/little_loops/cli/issues/sections.py` (new) — `cmd_sections` implementation
- `scripts/little_loops/cli/issues/__init__.py` — parser registration + dispatch
- `scripts/tests/test_ll_issues_sections.py` (new) — test JSON output, `--path` flag,
  invalid type exit code, and each resolver tier (using `patch.object(sys, "argv", ...)` +
  `main_issues()` + `capsys.readouterr()`, mirroring `test_issues_path.py`)

## Acceptance Criteria

- `ll-issues sections bug` prints bug-sections.json content to stdout, exit 0
- `ll-issues sections enh --path` prints the absolute path to the JSON file, exit 0
- `ll-issues sections invalid` exits 1 with error message to stderr
- `ll-issues sections` alias `ll-issues sec` works identically
- Template not found exits 1 with a clear message
- All new tests pass; `ruff check` clean

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/sections.py` with `cmd_sections`
2. Add parser registration to `cli/issues/__init__.py`
3. Add dispatch block to `main_issues()` (before final `return 1`)
4. Create `scripts/tests/test_ll_issues_sections.py` with coverage for all four
   valid types, `--path`, invalid type, and template-missing scenarios
5. Run `python -m pytest scripts/tests/test_ll_issues_sections.py -v`

## Dependencies

- ENH-2285 must ship first (provides `resolve_templates_dir`)

## Session Log
- `/ll:issue-size-review` - 2026-06-25T00:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
