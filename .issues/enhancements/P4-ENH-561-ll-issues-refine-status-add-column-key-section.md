---
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-561: Add column key section to `ll-issues refine-status` output

## Summary

Update `ll-issues refine-status` to print a "Key" section below the table mapping each truncated column header to its full command name.

## Motivation

The `refine-status` table truncates command column headers (e.g., `scan-cod…`, `format-i…`, `refine-i…`) to fit terminal width. Without a legend, users must guess what each column refers to. A "Key" section below the table removes the ambiguity at a glance, making the output self-documenting.

## Acceptance Criteria

- [ ] A "Key" section is printed after the table whenever `refine-status` runs in table mode
- [ ] Each line maps the truncated column label to the full command name (e.g., `scan-cod… → /ll:scan-codebase`)
- [ ] `OutConf` and `Ready` are also listed with plain-English explanations (e.g., `Ready → Readiness score (0–100)`, `OutConf → Outcome confidence score (0–100)`)
- [ ] Key is omitted from `--json` output (JSON consumers use full field names)
- [ ] Key is suppressed by a `--no-key` flag (or equivalent) for scripting/piping
- [ ] Existing tests are updated; a new test asserts the "Key" section appears in default output

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/refine_status.py` — primary implementation; add `_print_key()` helper that prints the mapping section after the table body; call it at the end of `cmd_refine_status()` unless `--json` or `--no-key` is set
- `scripts/little_loops/cli/issues/__init__.py` — if `--no-key` becomes a new CLI flag, register it here in the `refine-status` subcommand arg definition

### Dependent Files (Reference Only)

- `scripts/tests/test_refine_status.py` — extend `TestRefineStatusTable` with a test asserting "Key" appears in stdout

## Implementation Steps

1. **Define column-to-command mapping** in `refine_status.py` — create a module-level list/dict pairing each column label (as it appears in the header) to its full name:
   ```python
   _KEY_LINES = [
       ("scan-cod…",  "/ll:scan-codebase"),
       ("format-i…",  "/ll:format-issue"),
       ("refine-i…",  "/ll:refine-issue"),
       ("verify-i…",  "/ll:verify-issues"),
       ("capture-…",  "/ll:capture-issue"),
       ("audit-ar…",  "/ll:audit-architecture"),
       ("Ready",      "Readiness score (0–100)"),
       ("OutConf",    "Outcome confidence score (0–100)"),
       ("Total",      "Count of command columns with ✓"),
   ]
   ```
   Adjust entries to match actual truncated labels produced by `_row()`.

2. **Add `_print_key()` helper** — formats and prints the section:
   ```python
   def _print_key() -> None:
       print("\nKey:")
       for short, full in _KEY_LINES:
           print(f"  {short:<12} {full}")
   ```

3. **Call `_print_key()` in `cmd_refine_status()`** — after the table is printed, before returning, if not in JSON mode (and not suppressed by `--no-key` if that flag is added).

4. **Update tests** — in `test_refine_status.py`, capture stdout and assert `"Key:"` appears and at least one mapping line (e.g., `"/ll:scan-codebase"`) is present.

## Related Key Documentation

- `scripts/little_loops/cli/issues/refine_status.py` — primary implementation target
- `scripts/tests/test_refine_status.py` — test patterns to follow
- `docs/reference/CLI.md` — documents `ll-issues refine-status`; mention the Key section

## Status

Open

---

## Session Log
- `/ll:capture-issue` - 2026-03-04T03:38:39Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/57effe1c-b988-485d-9160-c576120a0097.jsonl`
