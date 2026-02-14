# ENH-301: Integrate dependency_mapper into sprint system - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-301-integrate-dependency-mapper-into-sprint-system.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The sprint system (`_cmd_sprint_run`, `_cmd_sprint_show` in `cli.py`) and `dependency_mapper.py` have zero direct code-level integration:

- `cli.py:34` imports `DependencyGraph` and `refine_waves_for_contention` from `dependency_graph.py` but NOT `dependency_mapper`
- `_cmd_sprint_run()` at `cli.py:1826` builds `DependencyGraph.from_issues(issue_infos)` using only what's already in issue files
- `_cmd_sprint_show()` at `cli.py:1663` does the same
- `create_sprint.md` Step 4.5 (line 316) re-implements ad-hoc dependency parsing at the prompt level
- `dependency_mapper` has zero Python-level callers outside its test file

### Key Discoveries
- `analyze_dependencies()` at `dependency_mapper.py:526` takes `(issues, issue_contents, completed_ids)` and returns a `DependencyReport`
- `format_report()` at `dependency_mapper.py:555` takes a `DependencyReport` and returns a human-readable markdown string
- `IssueInfo.path` is available on all loaded issue objects for reading raw content
- CLI args follow the `add_*_arg()` pattern in `cli_args.py`
- All existing sprint test `argparse.Namespace` constructions must be updated with new flag

## Desired End State

- `ll-sprint run` runs `analyze_dependencies()` before building waves and warns about discovered dependencies
- `ll-sprint show` includes dependency analysis summary alongside wave structure
- A `--skip-analysis` flag allows skipping dependency discovery for speed
- `/ll:create-sprint` Step 4.5 references `dependency_mapper` functions instead of ad-hoc parsing

### How to Verify
- `ll-sprint run --dry-run <sprint>` shows dependency analysis warnings when issues have file overlaps
- `ll-sprint run --skip-analysis <sprint>` skips the analysis
- `ll-sprint show <sprint>` shows dependency analysis section
- All existing tests pass with `skip_analysis=False` added to Namespace
- New tests verify analysis integration and `--skip-analysis` flag behavior

## What We're NOT Doing

- Not changing `dependency_mapper.py` itself -- only wiring existing functions into sprint workflow
- Not auto-applying discovered dependencies -- only warning
- Not changing `DependencyGraph` or wave scheduling algorithms
- Not changing `refine_waves_for_contention()` behavior
- Not adding a CLI subcommand -- only adding a flag and inline analysis

## Solution Approach

Add a deferred import of `dependency_mapper` functions in the sprint command handlers. Before building the `DependencyGraph`, read issue file contents, call `analyze_dependencies()`, and display warnings using the existing `format_report()` function (adapted for CLI output). A `--skip-analysis` flag (default: run analysis) allows users to bypass this when dependencies are known to be current. Update the `create_sprint.md` command to reference `dependency_mapper` functions.

## Code Reuse & Integration

- **Reuse as-is**: `dependency_mapper.analyze_dependencies()`, `format_report()`
- **Reuse as-is**: `SprintManager.load_issue_infos()` (already called)
- **Reuse as-is**: `Logger.warning()` for display
- **Pattern to follow**: `add_skip_arg()` for new `add_skip_analysis_arg()`
- **Pattern to follow**: Deferred import like `refine_waves_for_contention` does for `file_hints`
- **New code**: `_build_issue_contents()` helper (3-line dict comprehension), `_render_dependency_analysis()` display function

## Implementation Phases

### Phase 1: Add `--skip-analysis` CLI Flag

#### Overview
Add the `--skip-analysis` flag to the sprint `run` and `show` subcommands following existing patterns.

#### Changes Required

**File**: `scripts/little_loops/cli_args.py`
**Changes**: Add `add_skip_analysis_arg()` function and export it

```python
def add_skip_analysis_arg(parser: argparse.ArgumentParser) -> None:
    """Add --skip-analysis argument to skip dependency discovery."""
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip dependency analysis (use when dependencies are known to be current)",
    )
```

Add to `__all__` list.

**File**: `scripts/little_loops/cli.py`
**Changes**:
- Add `add_skip_analysis_arg` to the imports from `cli_args` (line ~22)
- Call `add_skip_analysis_arg(run_parser)` after line 1427
- Call `add_skip_analysis_arg(show_parser)` after line 1438

#### Success Criteria

**Automated Verification**:
- [ ] `ll-sprint run --help` shows `--skip-analysis` flag
- [ ] `ll-sprint show --help` shows `--skip-analysis` flag
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Integrate `analyze_dependencies()` into `_cmd_sprint_run()`

#### Overview
Wire `dependency_mapper.analyze_dependencies()` into the sprint run command, displaying warnings about discovered dependencies before wave execution.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: In `_cmd_sprint_run()`, after `issue_infos` are loaded (line 1823) and before `DependencyGraph.from_issues()` (line 1826):

1. Add a helper function `_build_issue_contents()` to build the contents dict:
```python
def _build_issue_contents(issue_infos: list) -> dict[str, str]:
    """Build issue_id -> file content mapping for dependency analysis."""
    return {
        info.issue_id: info.path.read_text()
        for info in issue_infos
        if info.path.exists()
    }
```

2. Add a helper function `_render_dependency_analysis()` for CLI-friendly output:
```python
def _render_dependency_analysis(report, logger: Logger) -> None:
    """Display dependency analysis results in CLI format."""
    from little_loops.dependency_mapper import DependencyReport

    if not report.proposals and not report.validation.has_issues:
        return

    logger.header("Dependency Analysis", char="-", width=60)

    if report.proposals:
        logger.warning(
            f"Found {len(report.proposals)} potential missing "
            f"dependency(ies):"
        )
        for p in report.proposals:
            conflict = "HIGH" if p.conflict_score >= 0.7 else (
                "MEDIUM" if p.conflict_score >= 0.4 else "LOW"
            )
            logger.warning(
                f"  {p.source_id} may depend on {p.target_id} "
                f"({conflict} conflict, {p.confidence:.0%} confidence)"
            )
            if p.overlapping_files:
                files = ", ".join(p.overlapping_files[:3])
                logger.info(f"    Shared files: {files}")

    if report.validation.has_issues:
        v = report.validation
        if v.broken_refs:
            for issue_id, ref_id in v.broken_refs:
                logger.warning(f"  {issue_id}: references nonexistent {ref_id}")
        if v.stale_completed_refs:
            for issue_id, ref_id in v.stale_completed_refs:
                logger.warning(f"  {issue_id}: blocked by {ref_id} (completed)")
        if v.missing_backlinks:
            for issue_id, ref_id in v.missing_backlinks:
                logger.warning(
                    f"  {issue_id} blocked by {ref_id}, "
                    f"but {ref_id} missing backlink"
                )

    logger.info(
        "Run /ll:map-dependencies to apply discovered dependencies"
    )
    print()  # blank line separator
```

3. In `_cmd_sprint_run()`, insert analysis block between lines 1823 and 1826:
```python
    # Dependency analysis (ENH-301)
    if not getattr(args, 'skip_analysis', False):
        from little_loops.dependency_mapper import analyze_dependencies
        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents)
        _render_dependency_analysis(dep_report, logger)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

### Phase 3: Integrate `analyze_dependencies()` into `_cmd_sprint_show()`

#### Overview
Add dependency analysis to the show command, displaying analysis results after the wave structure.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: In `_cmd_sprint_show()`, after the wave display (line 1677) and before options display (line 1692):

```python
    # Dependency analysis (ENH-301)
    if issue_infos and not getattr(args, 'skip_analysis', False):
        from little_loops.dependency_mapper import analyze_dependencies
        issue_contents = _build_issue_contents(issue_infos)
        dep_report = analyze_dependencies(issue_infos, issue_contents)
        _render_dependency_analysis(dep_report, Logger())
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 4: Update `/ll:create-sprint` Step 4.5

#### Overview
Update the create_sprint command's Step 4.5 to reference `dependency_mapper` functions for richer analysis.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Replace Step 4.5 (lines 316-343) to instruct Claude to use `dependency_mapper` programmatically via Bash:

Replace the ad-hoc parsing instructions with instructions to run a Python one-liner that calls `analyze_dependencies()` and prints the report. Since the skill has tool access, instruct it to use Bash to run:

```bash
python -c "
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
from little_loops.dependency_mapper import analyze_dependencies, format_report
from pathlib import Path

config = BRConfig(Path.cwd())
parser = IssueParser(config)
issue_ids = [SPRINT_ISSUE_IDS]  # filled in by the skill
issues = []
contents = {}
for iid in issue_ids:
    for cat in ['bugs', 'features', 'enhancements']:
        for p in config.get_issue_dir(cat).glob(f'*-{iid}-*.md'):
            info = parser.parse_file(p)
            issues.append(info)
            contents[iid] = p.read_text()
            break
report = analyze_dependencies(issues, contents)
print(format_report(report))
"
```

The step will also retain the existing external-blocker check and cycle detection logic, but delegate the file overlap and validation analysis to the mapper.

#### Success Criteria

**Automated Verification**:
- [ ] create_sprint.md parses correctly (no broken markdown)

**Manual Verification**:
- [ ] Running `/ll:create-sprint` with issues that have file overlaps shows richer analysis in Step 4.5

---

### Phase 5: Add Tests

#### Overview
Add unit tests for the new integration, covering both the analysis flow and the `--skip-analysis` flag.

#### Changes Required

**File**: `scripts/tests/test_sprint.py`
**Changes**:

1. Add `skip_analysis=False` to all existing `argparse.Namespace()` constructions in `TestSprintErrorHandling` that call `_cmd_sprint_run()` -- this prevents `AttributeError` from `getattr(args, 'skip_analysis', False)` (though `getattr` with default handles this, it's cleaner to be explicit).

2. Add a new test class `TestSprintDependencyAnalysis`:

```python
class TestSprintDependencyAnalysis:
    """Tests for dependency analysis integration in sprint commands (ENH-301)."""

    @staticmethod
    def _setup_overlapping_issues(tmp_path):
        """Create two issues that reference the same file."""
        # ... setup with BUG-001 and FEAT-001 both mentioning scripts/config.py
        pass

    def test_run_shows_dependency_warnings(self, tmp_path, monkeypatch, capsys):
        """Sprint run displays dependency analysis when issues overlap."""
        pass

    def test_run_skip_analysis_suppresses_warnings(self, tmp_path, monkeypatch, capsys):
        """--skip-analysis flag skips dependency analysis."""
        pass

    def test_show_includes_dependency_analysis(self, tmp_path, monkeypatch, capsys):
        """Sprint show includes dependency analysis section."""
        pass

    def test_show_skip_analysis(self, tmp_path, monkeypatch, capsys):
        """Sprint show with --skip-analysis skips analysis."""
        pass
```

3. Add `skip_analysis` attribute to all existing Namespace constructions in sprint tests.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test `_build_issue_contents()` returns correct dict from IssueInfo objects
- Test `_render_dependency_analysis()` produces output for proposals and validation issues
- Test `_render_dependency_analysis()` produces no output when no issues found
- Test `--skip-analysis` flag skips the analysis call entirely

### Integration Tests
- Test `_cmd_sprint_run()` with overlapping issues shows warnings
- Test `_cmd_sprint_show()` with overlapping issues shows analysis section
- Test that existing sprint behavior is unchanged when no overlaps exist

## References

- Original issue: `.issues/enhancements/P3-ENH-301-integrate-dependency-mapper-into-sprint-system.md`
- `analyze_dependencies()`: `scripts/little_loops/dependency_mapper.py:526`
- `format_report()`: `scripts/little_loops/dependency_mapper.py:555`
- `_cmd_sprint_run()`: `scripts/little_loops/cli.py:1779`
- `_cmd_sprint_show()`: `scripts/little_loops/cli.py:1644`
- `add_skip_arg()` pattern: `scripts/little_loops/cli_args.py:54`
- Sprint test patterns: `scripts/tests/test_sprint.py:501`
- create_sprint Step 4.5: `commands/create_sprint.md:316`
