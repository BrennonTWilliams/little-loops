---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# ENH-301: Integrate dependency_mapper into create_sprint and ll-sprint

## Summary

The sprint system (`ll-sprint` CLI and `/ll:create_sprint` command) and the dependency mapper (`dependency_mapper.py`) have zero direct code-level integration. The sprint system only consumes dependency data already written to issue files — it never calls `dependency_mapper.analyze_dependencies()` or `find_file_overlaps()` to discover missing dependencies before building execution waves. Meanwhile, `/ll:create_sprint` re-implements basic dependency parsing in its Step 4.5 rather than leveraging the mapper's richer analysis (file overlap detection, semantic conflict scoring, validation). This enhancement would wire the dependency mapper into the sprint workflow so missing dependencies are automatically discovered before sprint execution.

## Context

Identified from conversation analyzing the relationship between the sprint system and dependency mapper. Key findings:

- Both systems independently consume `IssueInfo` and `DependencyGraph` but neither imports the other
- The only connection is file-mediated: mapper writes `## Blocked By`/`## Blocks` → issue parser reads them → sprint builds waves
- FEAT-261 added prompt-level integration to `create_sprint.md` (Step 4.5) but no Python-level integration
- ENH-144 added wave-based execution to `ll-sprint` using `DependencyGraph` but not `dependency_mapper`
- Completed ENH-300 explicitly marked changes to `ll-sprint` scheduling logic as out of scope

## Current Behavior

- `ll-sprint run` builds execution waves from whatever `blocked_by`/`blocks` data is already in issue files — it does not discover missing dependencies
- `/ll:create_sprint` Step 4.5 does ad-hoc parsing of `## Blocked By`/`## Blocks` sections without calling `dependency_mapper` functions
- Users must manually run `/ll:map-dependencies` before sprint creation/execution to get dependency discovery
- Sprint execution can produce conflicting parallel waves when undiscovered dependencies exist between issues

## Expected Behavior

- `ll-sprint run` optionally runs `dependency_mapper.analyze_dependencies()` before building waves, warning about discovered but unapplied dependencies
- `ll-sprint show` includes dependency analysis summary (missing deps, conflict scores) alongside wave structure
- `/ll:create_sprint` Step 4.5 calls `dependency_mapper.find_file_overlaps()` and `compute_conflict_score()` instead of re-implementing dependency parsing
- A `--skip-analysis` flag allows skipping dependency discovery for speed when dependencies are known to be current

## Proposed Solution

### 1. Add dependency analysis to `_cmd_sprint_run()` in `cli.py`

Before building the `DependencyGraph`, call `analyze_dependencies()` on the sprint's issues. If new dependencies are discovered, warn the user and optionally apply them before computing waves.

### 2. Add dependency summary to `_cmd_sprint_show()` in `cli.py`

After displaying wave structure, run `find_file_overlaps()` and show any potential missing dependencies between sprint issues.

### 3. Update `/ll:create_sprint` Step 4.5

Replace the ad-hoc dependency parsing with calls to `dependency_mapper` functions — specifically `find_file_overlaps()`, `validate_dependencies()`, and `compute_conflict_score()` — to provide richer analysis during sprint creation.

## Current Pain Point

Sprint execution can schedule conflicting issues in the same wave because dependencies between them were never discovered. Users must remember to run `/ll:map-dependencies` manually before every sprint, and even then the sprint command re-implements simpler analysis rather than using the mapper's capabilities.

## Scope Boundaries

- **Out of scope**: Changes to `dependency_mapper.py` itself — this enhancement only wires existing functions into the sprint workflow
- **Out of scope**: Auto-applying discovered dependencies without user confirmation
- **Out of scope**: Changes to `DependencyGraph` or wave scheduling algorithms

## Impact

- **Priority**: P3
- **Effort**: Medium — wiring existing functions into existing workflows, plus CLI flag additions
- **Risk**: Low — `dependency_mapper` functions are already tested; this is integration work

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint and dependency system design |
| architecture | docs/API.md | dependency_mapper and sprint module APIs |

## Blocked By

None

## Blocks

None

## Labels

`enhancement`, `cli`, `ll-sprint`, `dependency-management`, `captured`

---

## Status

**Completed** | Created: 2026-02-09 | Completed: 2026-02-09 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli_args.py`: Added `add_skip_analysis_arg()` function and export
- `scripts/little_loops/cli.py`: Added `_build_issue_contents()` and `_render_dependency_analysis()` helpers; integrated `analyze_dependencies()` into `_cmd_sprint_run()` and `_cmd_sprint_show()`; added `--skip-analysis` flag to `run` and `show` subparsers
- `commands/create_sprint.md`: Updated Step 4.5 to use `dependency_mapper` functions instead of ad-hoc parsing
- `scripts/tests/test_sprint.py`: Added `TestSprintDependencyAnalysis` test class with 4 tests

### Verification Results
- Tests: PASS (61/61)
- Lint: PASS
- Types: PASS
- Integration: PASS
