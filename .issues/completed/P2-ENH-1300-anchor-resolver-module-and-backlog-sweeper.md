---

discovered_date: "2026-04-27"
discovered_by: issue-size-review
decision_needed: false
missing_artifacts: true
size: Large
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
captured_at: 2026-04-27T00:00:00Z
completed_at: 2026-04-27T20:54:41Z
parent: ENH-1298
---

# ENH-1300: Build anchor resolver module, backlog sweeper, and regression lint (`ll-issues anchor-sweep`)

## Summary

Build the new `scripts/little_loops/issues/anchors.py` module that resolves a `file:line` reference to its enclosing function/class/section anchor using a language-agnostic regex backwards-scan (no AST, works for `.py`, `.ts`, `.go`, `.rs`, `.rb`, `.java`, etc.), then build `anchor_sweep.py` — a one-shot CLI tool that rewrites `file:line` patterns in existing active issue files to anchor-based equivalents. Registers as `ll-issues anchor-sweep`. Also extends `commands/ready-issue.md` with a lint check (Step 3 of ENH-1298) that flags new `file:line` contamination using the same resolver, preventing regression after the sweep.

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

    Language-agnostic: scans lines[:line_number][::-1] for the first line
    matching a definition pattern using a set of regexes that cover common
    syntax across languages (def/fn/func/function/class etc.). Works for
    .py, .ts, .js, .go, .rs, .rb, .java, .cs and any language with
    recognizable definition syntax. For .md files: scans for ^#{1,6}\s+
    headings instead. Returns 'near function foo' / 'near class Bar' /
    'under section "Title"' or None if no anchor can be resolved.
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
  - Python `def` walk-back
  - TypeScript `function` / `async function` walk-back
  - Go `func` walk-back
  - Rust `fn` walk-back
  - `class` walk-back (universal pattern, covers Python/JS/TS/Java/C#)
  - markdown section heading lookup
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
- `commands/help.md` — add `anchor-sweep` to the static `ll-issues` parenthetical subcommand list [Wiring pass]
- `skills/init/SKILL.md` — add `anchor-sweep` to the `ll-issues` parenthetical in both CLAUDE.md template blocks (two separate locations) [Wiring pass]
- `CONTRIBUTING.md` — add `issues/` sub-package entry under `scripts/little_loops/` in the "Project Structure" directory tree [Wiring pass 2]

### Existing Infrastructure to Reuse

- `scripts/little_loops/text_utils.py` — `_STANDALONE_PATH` (captures `file.py:42`) and `_CODE_FENCE` (fence exclusion)
- `scripts/little_loops/issue_discovery/matching.py` — `_extract_line_numbers()` regex convention
- `scripts/little_loops/doc_counts.py` — `fix_counts()` two-phase sweep-and-rewrite shape
- `scripts/little_loops/dependency_mapper/operations.py` — `dry_run` parameter and `FixResult` dataclass
- `scripts/little_loops/file_utils.py` — `atomic_write()` for safe rewrites
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` / `update_frontmatter()`
- `scripts/little_loops/cli/issues/check_readiness.py` — model for `cmd_anchor_sweep()` signature

### Dependency Note

`scripts/little_loops/issues/` does not exist yet — creating `anchors.py` there requires a new `__init__.py`. The anchor resolver uses stdlib `re` only — no AST or third-party parser dependencies, keeping the implementation language-agnostic.

### Caveats / Edge Cases

- Pattern misses: unusual syntax (lambdas, arrow-function assignments, macro-generated defs) may not match any definition regex; leave original reference unchanged with a warning.
- False matches: a regex may match a definition keyword inside a string literal or comment; acceptable tradeoff for simplicity over AST-level precision.
- Non-existent files: if the cited `file_path` doesn't exist, emit a warning and leave the original reference unchanged.
- `--dry-run` is essential before first production run against 49 active issue files.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Critical: `_STANDALONE_PATH` Does Not Capture Line Numbers Separately

`_STANDALONE_PATH` in `text_utils.py` is:
```python
re.compile(
    r"(?:^|\s)([a-zA-Z_][\w/.-]*\.[a-z]{2,4})(?::\d+)?(?:\s|$|:|\))",
    re.MULTILINE,
)
```
The `:42` suffix is `(?::\d+)?` — **non-capturing**. Using it directly in `anchor_sweep.py` will find file paths but will NOT yield the line number needed to call `resolve_anchor()`. The sweeper needs a separate regex that captures both file path and line number, e.g.:
```python
_FILE_LINE = re.compile(
    r"(?:^|(?<=\s))([a-zA-Z_][\w/.-]*\.[a-z]{2,4}):(\d+)(?=\s|$|:|\))",
    re.MULTILINE,
)
```
Use `_CODE_FENCE` (which is `re.compile(r"```[\s\S]*?```", re.MULTILINE)`) to blank fence spans before applying `_FILE_LINE`, mirroring `extract_file_paths()` in `text_utils.py`.

#### `FixResult` Location Correction

The issue cites `dependency_mapper/operations.py` as the source of `FixResult` — it actually lives in `dependency_mapper/models.py` (operations.py imports it from there). The fields are:
```python
@dataclass
class FixResult:
    changes: list[str] = field(default_factory=list)
    modified_files: set[str] = field(default_factory=set)
    skipped_cycles: int = 0
```
`doc_counts.py` has its own `FixResult(fixed_count: int, files_modified: list[str])` but with no dry-run semantics. For `anchor_sweep.py`, use the `dependency_mapper` variant's shape (or define a local one with `changes` + `modified_files`).

#### `fix_counts()` Has No `dry_run`

`doc_counts.fix_counts()` signature is `def fix_counts(base_dir: Path, result: VerificationResult) -> FixResult` — no `dry_run` parameter. The dry-run pattern must be taken from `fix_dependencies()` in `dependency_mapper/operations.py`:
- Always append to `result.changes` (what *would* happen)
- Gate actual file writes with `if not dry_run:`

#### Exact `atomic_write()` Signature

```python
def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None
```
Writes to a sibling `.tmp` file then `os.replace()` for atomicity. Note: `doc_counts.fix_counts()` uses `doc_path.write_text()` directly — `anchor_sweep.py` should use `atomic_write()` as stated in the proposed solution (safer for multi-file sweeps).

#### CLI Registration Pattern in `main_issues()`

Lazy imports live at the **top of the `main_issues()` function body** (not module level). The dispatch is a linear chain of `if args.command == "..."` checks. Model `anchor-sweep` exactly after `check-readiness`:

```python
# In main_issues() — lazy imports block at top:
from little_loops.cli.issues.anchor_sweep import cmd_anchor_sweep

# Parser registration (alongside other subs.add_parser blocks):
asw = subs.add_parser(
    "anchor-sweep",
    aliases=["asw"],
    help="Rewrite file:line references in active issue files to anchor form",
)
asw.set_defaults(command="anchor-sweep")
asw.add_argument("--dry-run", action="store_true", help="Print changes without modifying files")
asw.add_argument("--issues-dir", default=".issues", metavar="DIR", help="Issues base directory (default: .issues)")
add_config_arg(asw)

# Dispatch (at end of if/elif chain):
if args.command == "anchor-sweep":
    return cmd_anchor_sweep(config, args)
```

#### `commands/help.md` Epilog Coupling

`commands/help.md` line 228 contains a static hard-coded string:
```
ll-issues         Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, clusters)
```
This is not auto-generated — it must be manually updated to include `anchor-sweep` in the parenthetical.

#### `skills/init/SKILL.md` Template Coupling

Two template blocks in `skills/init/SKILL.md` (one for "update existing CLAUDE.md", one for "create new CLAUDE.md") contain the same static `ll-issues` parenthetical:
```
- `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status)
```
Both must be updated to include `anchor-sweep`.

Note: these blocks are separate from `.claude/CLAUDE.md` (which the issue already lists). `skills/init/SKILL.md` provides the template used when scaffolding new projects — it will silently omit `anchor-sweep` from all new projects if not updated.

#### `ready-issue.md` Insertion Point

The lint check bullet belongs inside `#### Code References` under `### 2. Validate Issue Content`. The current four bullets are:
```
- [ ] File paths exist in codebase
- [ ] Line numbers are accurate (or can be corrected using anchor)
- [ ] Code snippets match current code
- [ ] Anchor field present and valid (function/class name exists)
```
Add a fifth bullet after the fourth. For the `[anchor_rewrite]` correction category in Phase 5/6 output, add it to the `**Correction categories**` block inside `## CORRECTIONS_MADE` in `### 6. Output Format`.

#### Anchor Resolver Regex Patterns

No equivalent definition-matching patterns exist in the codebase — these are new. Suggested `_ANCHOR_PATTERNS` (module-level, following the named-constant convention from `text_utils.py` and `dependency_mapper/analysis.py`):

```python
_ANCHOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Python / Ruby — def and async def
    (re.compile(r"^[ \t]*(?:async\s+)?def\s+(\w+)\s*\("), "function"),
    # JS / TS — function declaration or named function expression
    (re.compile(r"^[ \t]*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*\("), "function"),
    # JS / TS — const/let/var arrow or assigned function
    (re.compile(r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(|function\b)"), "function"),
    # Go — top-level func and methods (optional receiver before name)
    (re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*[(\[]"), "function"),
    # Rust — fn (optionally pub, async, unsafe)
    (re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*[<(]"), "function"),
    # Java / C# heuristic — access-modifier(s) + return-type + name(
    (re.compile(r"^[ \t]*(?:(?:public|private|protected|static|final|override|virtual|abstract|async|synchronized)\s+){1,4}\w[\w<>\[\]?*]*\s+(\w+)\s*\("), "function"),
    # Universal — class / struct / interface / trait / impl / enum
    (re.compile(r"^[ \t]*(?:(?:pub(?:\([^)]*\))?\s+)?(?:public|private|protected|abstract|final|sealed|static|export|default)\s+)*(?:class|struct|interface|trait|impl|enum)\s+(\w+)"), "class"),
    # Markdown heading (any level, strips trailing hashes)
    (re.compile(r"^#{1,6}\s+(.+?)(?:\s+#+)?$"), "section"),
]
```

Backwards-scan skeleton for `resolve_anchor()`:

```python
def resolve_anchor(file_path: str, line_number: int) -> str | None:
    try:
        lines = Path(file_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    scan_end = min(line_number, len(lines))  # line_number is 1-based; scan up through it
    for i in range(scan_end - 1, -1, -1):
        for pattern, kind in _ANCHOR_PATTERNS:
            m = pattern.match(lines[i])
            if m:
                name = m.group(1).strip()
                if kind == "section":
                    return f'under section "{name}"'
                return f"near {kind} {name}"
    return None
```

#### Sweeper Fence Exclusion — Use Span Intersection, Not Sub-Blanking

`extract_file_paths()` uses `_CODE_FENCE.sub("", content)` (blanking) before matching. The sweeper **cannot** do this — blanking shifts character positions and breaks span-based in-place replacements. Use fence-span intersection instead:

```python
fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(content)]

def _in_fence(start: int, end: int) -> bool:
    return any(fs <= start and end <= fe for fs, fe in fence_spans)

replacements: list[tuple[int, int, str]] = []
for m in _FILE_LINE.finditer(content):
    if _in_fence(m.start(), m.end()):
        continue
    anchor = resolve_anchor(m.group(1), int(m.group(2)))
    if anchor is None:
        continue  # leave original unchanged; emit warning
    replacements.append((m.start(), m.end(), _format_anchor_ref(m.group(1), anchor)))

# Apply in reverse order to preserve upstream positions
for start, end, replacement in reversed(replacements):
    content = content[:start] + replacement + content[end:]
```

#### Replacement Format for `_format_anchor_ref()`

When `file.py:42` is resolved, replace the entire `file.py:42` token with backtick-quoted path + parenthesised anchor:

- `file.py:42` → `` `file.py` (near function `foo`) ``
- `file.py:42` → `` `file.py` (near class `Bar`) ``
- `file.py:42` → `` `file.py` (under section "Title") ``

The anchor string from `resolve_anchor()` already has the form `"near function foo"` / `"near class Bar"` / `"under section Title"`. Strip the first word (`near`/`under`) and reconstruct:

```python
def _format_anchor_ref(file_path: str, anchor: str) -> str:
    # anchor: "near function foo" | "near class Bar" | 'under section "Title"'
    return f"`{file_path}` ({anchor})"
```

#### `ready-issue.md` Exact Insertion Text

**5th bullet under `#### Code References`** — insert after `- [ ] Anchor field present and valid (function/class name exists)`:

```
- [ ] No `file:line` references outside code fences (flag any found; auto-fix: run `ll-issues anchor-sweep --dry-run` to preview anchor replacements)
```

**`[anchor_rewrite]` correction category** — insert after `- \`[issue_status]\` - Related issue status updated` in the `**Correction categories**` block in `### 6. Output Format`:

```
- `[anchor_rewrite]` - `file:line` reference rewritten to enclosing function/class/section anchor
```

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `commands/help.md` — static `ll-issues` parenthetical on the CLI tools section line; `anchor-sweep` is absent and must be appended [Agent 2 finding]
- `skills/init/SKILL.md` — "update existing CLAUDE.md" template block and "create new CLAUDE.md" template block both hard-code the `ll-issues` subcommand list without `anchor-sweep` [Agent 2 finding]
- `CONTRIBUTING.md` — "Project Structure" directory tree under `scripts/little_loops/` does not list the new `issues/` sub-package; add `issues/` (with `__init__.py`, `anchors.py`, `anchor_sweep.py`) as a sibling entry alongside `cli/` [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issues_cli.py` — add new `TestIssuesCLIAnchorSweep` class following the existing per-subcommand pattern (`TestIssuesCLINextId`, `TestIssuesCLIHelp`, etc.); cover `--dry-run`, `--issues-dir`, and alias `asw`; no existing tests will break but the new subcommand has no coverage until this class is added [Agent 3 finding]
  - **Break risk**: if `anchor-sweep` is wired into `cli/issues/__init__.py` (Step 5) before `cli/issues/anchor_sweep.py` exists, all tests in `test_issues_cli.py` will fail at import time — create the module file before wiring the import
- `scripts/tests/test_issues_anchors.py` — new file (already planned) [Agent 3 pattern note]: follow `test_ll_issues_atomic_write.py` conventions: module docstring `"""Tests for issues.anchors — ENH-1300."""`, `from __future__ import annotations`, one class per logical unit, `tmp_path` for I/O
- `scripts/tests/test_ready_issue_lint.py` — new file (already planned); the three `sample_ready_issue_output_*` fixtures in `conftest.py` are pre-staged for this file
- `scripts/tests/test_issues_anchors.py` — also add a `TestFileLinkRegex` class testing the new `_FILE_LINE` regex directly (no existing coverage precedent for `_STANDALONE_PATH` in `test_text_utils.py`; cover: captures both path and line number, requires `:NNN` unlike optional form in `_STANDALONE_PATH`, ignores matches inside code fences) [Agent 3 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Update `commands/help.md` — append `anchor-sweep` to the static `ll-issues` parenthetical subcommand list in the "CLI TOOLS" section
12. Update `skills/init/SKILL.md` — append `anchor-sweep` to the `ll-issues` parenthetical in both CLAUDE.md template blocks (update existing and create new)
13. Add `TestIssuesCLIAnchorSweep` class to `scripts/tests/test_issues_cli.py` — cover `--dry-run`, `--issues-dir`, alias `asw`, and a basic sweep pass with a fixture issue file containing a `file.py:42` reference
14. Update `CONTRIBUTING.md` — add `issues/` package entry (`__init__.py`, `anchors.py`, `anchor_sweep.py`) under `scripts/little_loops/` in the "Project Structure" directory tree
15. In Step 5 (`cli/issues/__init__.py` registration): also update the `epilog` string's `Sub-commands:` list and `Examples:` block inside `main_issues()`'s `ArgumentParser` to include `anchor-sweep` — this epilog is rendered by `ll-issues --help` and is not auto-generated from registered subparsers

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

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-04-27 (scores unchanged from prior run)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **File count / multi-subsystem span**: 18 files (5 new + 13 modified) across Python module, CLI registration, markdown commands, docs, and tests — implement in order (module → tests pass → CLI wire → commands → docs) to catch integration issues early
- **Batch rewrite risk**: The sweeper will rewrite ~49 active issue files in-place; `--dry-run` is mandatory before production run; a wrong anchor is harder to recover than a stale line number
- **`scripts/little_loops/issues/` does not exist** — must be created (Step 1) before any imports work; wiring the import in `cli/issues/__init__.py` before `anchors.py`/`anchor_sweep.py` exist will break all 3,504 lines of `test_issues_cli.py` at import time

## Resolution

Implemented as specified. All 5 new files created (`issues/__init__.py`, `issues/anchors.py`, `issues/anchor_sweep.py`, `cli/issues/anchor_sweep.py`, `tests/test_issues_anchors.py`). All 13 files modified. 30 new tests pass; zero pre-existing regressions introduced.

Key decisions:
- Fixed `pub struct` matching by restructuring the universal class pattern to handle `pub` as a standalone modifier prefix.
- Used span intersection (not content blanking) for fence exclusion to preserve character positions for in-place replacement.
- `_FILE_LINE` regex only matches relative paths (starting `[a-zA-Z_]`), so absolute paths are intentionally excluded.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-27T20:55:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/564c5e37-eac4-477b-965f-3f220acda028.jsonl`
- `/ll:manage-issue` - 2026-04-27T20:54:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6db6f9a8-f94e-4fa1-8d9a-d6bac325f1f6.jsonl`
- `/ll:ready-issue` - 2026-04-27T20:37:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6db6f9a8-f94e-4fa1-8d9a-d6bac325f1f6.jsonl`
- `/ll:confidence-check` - 2026-04-27T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac825fad-b8ee-45c2-8945-487043d3bba9.jsonl`
- `/ll:wire-issue` - 2026-04-27T20:14:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ae96759-c3f2-4177-a13a-8f6ee414e468.jsonl`
- `/ll:refine-issue` - 2026-04-27T19:33:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f03c07e-76a1-42e2-9978-4ffb6684e484.jsonl`
- Design revision - 2026-04-27 - Replaced `ast.parse()` walk-back design with language-agnostic regex backwards-scan. Motivation: little-loops is language-agnostic and the AST approach would silently skip `.ts`/`.go`/`.rs` references on non-Python projects. The regex approach uses stdlib `re` only, covers all common definition syntaxes, and treats misses as safe no-ops (leave original reference unchanged).
- `/ll:confidence-check` - 2026-04-27T19:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/347d3186-75d2-471b-9e21-c66817ddf731.jsonl`
- `/ll:wire-issue` - 2026-04-27T19:14:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a6e5401e-6c0b-44a1-9668-5e9e34d7fcb7.jsonl`
- `/ll:refine-issue` - 2026-04-27T19:08:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3b7185f-23b7-4f5d-a4fb-ef3170ad3e77.jsonl`
- `/ll:format-issue` - 2026-04-27T16:24:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55b2ae6b-cfb7-490c-a90a-55c58082ceb5.jsonl`
- `/ll:issue-size-review` - 2026-04-27T17:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---

**Open** | Created: 2026-04-27 | Priority: P2
