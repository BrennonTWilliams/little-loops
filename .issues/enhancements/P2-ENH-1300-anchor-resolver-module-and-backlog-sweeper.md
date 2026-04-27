---
parent_issue: ENH-1298
discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: false
size: Large
---

# ENH-1300: Build anchor resolver module, backlog sweeper, and regression lint (`ll-issues anchor-sweep`)

## Summary

Build the new `scripts/little_loops/issues/anchors.py` module that resolves a `file:line` reference to its enclosing function/class/section anchor, then build `anchor_sweep.py` — a one-shot CLI tool that rewrites `file:line` patterns in existing active issue files to anchor-based equivalents. Registers as `ll-issues anchor-sweep`. Also extends `commands/ready-issue.md` with a lint check (Step 3 of ENH-1298) that flags new `file:line` contamination using the same resolver, preventing regression after the sweep.

## Parent Issue

Decomposed from ENH-1298: Convert issue-authoring pipelines from `file:line` to anchor-based references

## Current Behavior

~52% of active issue files (approximately 38 of 73) contain `file:line` references that were inserted by `refine-issue` and `wire-issue`. There is no tool to bulk-rewrite these to anchors. The references go stale whenever the cited files change.

## Expected Behavior

- `ll-issues anchor-sweep [--dry-run] [--issues-dir .issues]` scans all active issue files (bugs/, features/, enhancements/), finds `file:line` patterns outside code fences, resolves each to an anchor, and rewrites in-place.
- `--dry-run` prints what would change without modifying files.
- After a sweep pass, `grep -rE '\.(py|md|ts):[0-9]+' .issues/{bugs,features,enhancements}` returns zero matches.
- Each rewritten issue file gets a one-line audit note in its `Session Log`.

## Motivation

This enhancement would:
- Eliminate stale code references: ~52% of active issue files contain `file:line` references inserted by `refine-issue` and `wire-issue` that become misleading when source files change, leading agents to wrong locations.
- Automate bulk remediation: Without a sweeper tool, correcting ~38 contaminated issue files would require manual editing of each.
- Prevent future contamination: The regression lint in `ready-issue` closes the feedback loop so future authoring pipeline runs are caught before they re-contaminate the backlog.

## Proposed Solution

### 1. New package: `scripts/little_loops/issues/`

Create `scripts/little_loops/issues/__init__.py` (empty) and `scripts/little_loops/issues/anchors.py`:

```python
# scripts/little_loops/issues/anchors.py
def resolve_anchor(file_path: str, line_number: int) -> str | None:
    """Return enclosing function/class/section name for the given file:line.

    Uses stdlib ast.parse() for .py files: walks nodes to find the last
    FunctionDef/AsyncFunctionDef/ClassDef whose node.lineno <= target_line.
    For .md files: scans lines[:line_number][::-1] for ^#{1,6}\s+ headings.
    Uses _CODE_FENCE regex from text_utils.py to exclude code-fence spans.
    Returns 'in function foo()' / 'near class Bar' / 'under section "Title"'
    or None if no anchor can be resolved.
    """
```

### 2. Sweeper: `scripts/little_loops/issues/anchor_sweep.py`

Follow the two-phase pattern from `doc_counts.py`'s `fix_counts()`:
1. Scan phase: for each active issue file, use `_STANDALONE_PATH` regex from `text_utils.py` to find `file.py:42` matches outside code fences. For each match, call `resolve_anchor()`. Collect `(file_path, span, replacement)` tuples.
2. Apply phase: group by file, apply replacements using `atomic_write()` from `file_utils.py`.

Respect `--dry-run` flag following `fix_dependencies()` in `dependency_mapper/operations.py`.

### 3. CLI registration

Add to `scripts/little_loops/cli/issues/__init__.py`:
- New `subs.add_parser("anchor-sweep", ...)` block
- Lazy import of the subcommand module
- Dispatch branch in `main_issues()`
- Update epilog string

Follow the `check_readiness` / `check_flag` pattern added in the recent commit.

Thin CLI wrapper: `scripts/little_loops/cli/issues/anchor_sweep.py` with `cmd_anchor_sweep(config: BRConfig, args: argparse.Namespace) -> int` signature.

### 4. Documentation

- `docs/reference/CLI.md` — add `anchor-sweep` section under `### ll-issues` with flag table and example (mirror the `check-readiness` entry pattern).
- `docs/reference/API.md` — add `anchor-sweep` row in the `main_issues` subcommands table (around line 2976).
- `docs/ARCHITECTURE.md` — add `anchor_sweep.py` entry to the `cli/issues/` directory tree block (around line 208).
- `README.md` — add `anchor-sweep` example line to the `### ll-issues` section (around line 466).
- `.claude/CLAUDE.md` line 116 — add `anchor-sweep` to the `ll-issues` parenthetical subcommand list.

### 5. Regression lint in `ready-issue` (Step 3 of ENH-1298)

Extend `commands/ready-issue.md` to flag new contamination after the sweep:

- Insert a new bullet under the `### Code References` block in the `### 2. Validate Issue Content` section: scan the issue body for `_STANDALONE_PATH` matches (reuse regex from `text_utils.py`) outside code fences; treat any hit as a quality finding (not a hard block) with an auto-fix suggestion that names the enclosing function via `resolve_anchor()`.
- Add a new `[anchor_rewrite]` entry to the `CORRECTIONS_MADE` list in Phase 5 auto-correction.
- Note: `skills/ready-issue/SKILL.md` does not exist — the implementation lives at `commands/ready-issue.md`.

### 6. Tests

- `scripts/tests/test_issues_anchors.py` — unit tests for `resolve_anchor()`:
  - function walk-back (FunctionDef)
  - class walk-back (ClassDef)
  - async function walk-back
  - markdown section heading lookup
  - code-fence exclusion
  - no-anchor-found fallback (returns None)
  - Follow pattern from `test_ll_issues_atomic_write.py` (one class per logical unit, `tmp_path` for I/O, module docstring citing ENH-1300).
- `scripts/tests/test_ready_issue_lint.py` (or add to existing ready-issue test file if one exists) — fixture-based test asserting the lint flags an issue file containing `file.py:42` and passes one with only anchor-style references.

## API/Interface

```python
# scripts/little_loops/issues/anchors.py
def resolve_anchor(file_path: str, line_number: int) -> str | None:
    """Return enclosing function/class/section name for the given file:line."""

# scripts/little_loops/cli/issues/anchor_sweep.py
def cmd_anchor_sweep(config: BRConfig, args: argparse.Namespace) -> int: ...
```

CLI: `ll-issues anchor-sweep [--dry-run] [--issues-dir .issues]`

## Integration Map

### Files to Create

- `scripts/little_loops/issues/__init__.py`
- `scripts/little_loops/issues/anchors.py`
- `scripts/little_loops/issues/anchor_sweep.py`
- `scripts/little_loops/cli/issues/anchor_sweep.py`
- `scripts/tests/test_issues_anchors.py`

### Files to Modify

- `scripts/little_loops/cli/issues/__init__.py` — register `anchor-sweep` subcommand
- `commands/ready-issue.md` — add `file:line` lint check and `[anchor_rewrite]` correction category
- `docs/reference/CLI.md`
- `docs/reference/API.md`
- `docs/ARCHITECTURE.md`
- `README.md`
- `.claude/CLAUDE.md`

### Existing Infrastructure to Reuse

- `scripts/little_loops/text_utils.py` — `_STANDALONE_PATH` (captures `file.py:42`) and `_CODE_FENCE` (fence exclusion)
- `scripts/little_loops/issue_discovery/matching.py` — `_extract_line_numbers()` regex convention
- `scripts/little_loops/doc_counts.py` — `fix_counts()` two-phase sweep-and-rewrite shape
- `scripts/little_loops/dependency_mapper/operations.py` — `dry_run` parameter and `FixResult` dataclass
- `scripts/little_loops/file_utils.py` — `atomic_write()` for safe rewrites
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` / `update_frontmatter()`
- `scripts/little_loops/cli/issues/check_readiness.py` — model for `cmd_anchor_sweep()` signature

### Dependency Note

`scripts/little_loops/issues/` does not exist yet — creating `anchors.py` there requires a new `__init__.py`. No `ast_utils.py` exists in the package; the anchor resolver must use Python stdlib `ast` module.

### Caveats / Edge Cases

- Nested closures: the `ast` walk-back finds the outermost enclosing def; add `(approx)` suffix when nesting > 1.
- Decorators: `node.lineno` in ast includes the def line, not decorator lines; handle accordingly.
- Non-existent files: if the cited `file_path` doesn't exist, emit a warning and leave the original reference unchanged.
- `--dry-run` is essential before first production run against 49 active issue files.

## Implementation Steps

1. Create `scripts/little_loops/issues/__init__.py`.
2. Implement `resolve_anchor()` in `scripts/little_loops/issues/anchors.py`.
3. Write unit tests in `scripts/tests/test_issues_anchors.py` — pass before proceeding.
4. Implement `anchor_sweep.py` (module) and `cli/issues/anchor_sweep.py` (CLI wrapper).
5. Register in `cli/issues/__init__.py`.
6. Extend `commands/ready-issue.md` with the `file:line` lint check and `[anchor_rewrite]` correction category.
7. Write `scripts/tests/test_ready_issue_lint.py` (or extend existing) — verify lint flags contaminated fixtures.
8. Run `ll-issues anchor-sweep --dry-run` against `.issues/` and review output.
9. Run for real; verify grep returns zero matches.
10. Update docs: CLI.md, API.md, ARCHITECTURE.md, README.md, CLAUDE.md.

## Impact

- **Priority**: P2 — Upstream dependency for issue quality improvement; doesn't block daily development but affects agent implementation accuracy.
- **Effort**: Medium-Large — new Python module with `ast` walk-back logic; sweeper and lint both reuse existing patterns; lint requires understanding `ready-issue` phase structure.
- **Risk**: Medium — sweeper rewrites 49 files; `--dry-run` first is mandatory. Anchor resolver may produce wrong name for edge cases. Lint is advisory (not blocking), so false-positive risk is low.
- **Breaking Change**: No — new subcommand and module; lint addition is advisory, not blocking.
- **Ordering**: Run after ENH-1299 (source file fixes) to avoid re-contamination after sweep. Lint lands with this issue regardless of ordering.

## Success Metrics

- `grep -rE '\.(py|md|ts):[0-9]+|line [0-9]+' .issues/{bugs,features,enhancements}` returns zero matches after a sweep.
- All `test_issues_anchors.py` tests pass.
- `ll-issues anchor-sweep --dry-run` runs without exceptions.
- `ready-issue` flags a contaminated fixture and passes a clean one (verified by `test_ready_issue_lint.py`).

## Scope Boundaries

- **In scope**: `anchors.py` resolver module, `anchor-sweep` CLI subcommand (scan + rewrite active issues), regression lint in `commands/ready-issue.md`, unit tests for resolver and lint.
- **Out of scope**: Modifying how `refine-issue` or `wire-issue` generate references going forward (ENH-1299's scope); sweeping completed or deferred issues; file types beyond `.py` and `.md`; making the lint check a hard blocker (advisory-only per this issue).

## Labels

`enhancement`, `issue-management`, `cli`, `captured`

## Session Log
- `/ll:format-issue` - 2026-04-27T16:24:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55b2ae6b-cfb7-490c-a90a-55c58082ceb5.jsonl`
- `/ll:issue-size-review` - 2026-04-27T17:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
