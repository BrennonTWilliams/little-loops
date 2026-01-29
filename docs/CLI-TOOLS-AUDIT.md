# CLI Tools Audit Report: ll-auto, ll-parallel, ll-sprint

**Date**: 2026-01-29
**Scope**: Quality and consistency analysis of three CLI tools

## Executive Summary

This audit analyzes three CLI tools for quality and consistency:

- **ll-auto**: Sequential issue processor (739 lines core)
- **ll-parallel**: Parallel processor with git worktrees (~4,647 lines)
- **ll-sprint**: Sprint-based execution with dependency waves (301 lines)

**Overall Finding**: High code quality with strong documentation and type safety. Several consistency gaps between tools offer standardization opportunities.

---

## Consistency Matrix

| Dimension | ll-auto | ll-parallel | ll-sprint | Score |
|-----------|---------|-------------|-----------|-------|
| **Argument Parsing** | ✅ Standard | ✅ Standard | ✅ Subcommands | 80% |
| **Config Dataclasses** | ✅ BRConfig | ✅ ParallelConfig | ✅ SprintOptions | 85% |
| **State Management** | ✅ StateManager | ✅ OrchestratorState | ❌ None | 40% |
| **Error Handling** | ✅ try/finally | ✅ try/finally | ⚠️ Basic | 60% |
| **Logging Patterns** | ✅ Logger class | ✅ Logger class | ✅ Logger class | 90% |
| **Signal Handling** | ✅ SIGINT/SIGTERM | ✅ SIGINT/SIGTERM | ❌ None | 35% |
| **Test Coverage** | ✅ 35+ tests | ✅ 251+ tests | ⚠️ 29 tests | 70% |
| **Documentation** | ✅ Full | ✅ Full | ✅ Full | 95% |

---

## Tool-by-Tool Analysis

### ll-auto (Sequential Processor)

**Entry Point**: `cli.py:25-112` (`main_auto()`)

**Strengths**:

- 3-phase workflow: ready → implement → verify (`issue_manager.py:206-552`)
- Robust path mismatch handling with fallback retry (`issue_manager.py:255-330`)
- Context continuation for long-running issues (`issue_manager.py:121-191`)
- Full state persistence with resume capability (`state.py`)
- Graceful shutdown via signal handlers (`issue_manager.py:601-604`)

**Code Quality**:

- Full mypy compliance
- Comprehensive docstrings (Google style)
- 100% type hint coverage

**Key Files**:

- `scripts/little_loops/cli.py:25-112` - Entry point
- `scripts/little_loops/issue_manager.py` - Core logic (739 lines)
- `scripts/little_loops/state.py` - State management (203 lines)

---

### ll-parallel (Parallel with Git Worktrees)

**Entry Point**: `cli.py:115-299` (`main_parallel()`)

**Strengths**:

- Thread pool with configurable workers (`worker_pool.py`)
- Sequential merge coordinator prevents conflicts (`merge_coordinator.py`)
- Git lock with exponential backoff retry (`git_lock.py:110-180`)
- Priority queue with P0 sequential processing (`priority_queue.py`)
- Pending worktree recovery (`orchestrator.py:308-360`)
- Most comprehensive test coverage (998 lines in `test_parallel_types.py`)

**Code Quality**:

- Full type hints with `TYPE_CHECKING` guards
- Extensive inline comments for complex logic
- Robust error classification (interrupted vs failed)

**Key Files**:

- `scripts/little_loops/cli.py:115-299` - Entry point
- `scripts/little_loops/parallel/orchestrator.py` - Main controller (1009 lines)
- `scripts/little_loops/parallel/worker_pool.py` - Thread pool (1068 lines)
- `scripts/little_loops/parallel/merge_coordinator.py` - Merge queue (1215 lines)
- `scripts/little_loops/parallel/git_lock.py` - Git serialization (203 lines)
- `scripts/little_loops/parallel/types.py` - Dataclasses (403 lines)

---

### ll-sprint (Sprint-Based Execution)

**Entry Point**: `cli.py:1261-1361` (`main_sprint()`)

**Strengths**:

- Clean subcommand structure (create/run/list/show/delete)
- Dependency-aware wave execution
- YAML-based sprint definitions
- ASCII visualization of dependency graphs (`cli.py:1454-1523`)

**Gaps Identified**:

1. **No state persistence** - Cannot resume interrupted sprints
2. **No signal handling** - Abrupt termination loses progress
3. **Basic error handling** - Missing try/finally cleanup pattern
4. **Limited integration tests** - Only 3 integration tests

**Code Quality**:

- Good type hints and docstrings
- Clean dataclass design (SprintOptions, Sprint)
- Consistent with project style

**Key Files**:

- `scripts/little_loops/cli.py:1261-1735` - CLI handlers
- `scripts/little_loops/sprint.py` - Core module (301 lines)
- `scripts/tests/test_sprint.py` - Unit tests (328 lines)

---

## Argument Parsing Comparison

| Argument | ll-auto | ll-parallel | ll-sprint |
|----------|---------|-------------|-----------|
| `--dry-run/-n` | ✅ | ✅ | ✅ (run only) |
| `--resume/-r` | ✅ | ✅ | ❌ |
| `--max-issues/-m` | ✅ | ✅ | ❌ |
| `--only` | ✅ | ✅ | Uses `--issues` |
| `--skip` | ✅ | ✅ | ❌ |
| `--config` | ✅ | ✅ | ✅ (partial) |
| `--quiet/-q` | ❌ | ✅ | ❌ |
| `--timeout` | ❌ | ✅ `-t` | ✅ (no short) |
| `--workers` | ❌ | ✅ `-w` | `--max-workers` |

---

## Configuration Defaults Comparison

| Setting | ll-auto | ll-parallel | ll-sprint |
|---------|---------|-------------|-----------|
| max_workers | 2 | 2 | 2 |
| timeout | 3600s | 7200s | 3600s |
| state_file | `.auto-manage-state.json` | `.parallel-manage-state.json` | N/A |

---

## Standardization Opportunities

### High Priority

1. **Add State Persistence to Sprint**
   - Create `SprintState` dataclass following `ProcessingState` pattern
   - Enable `--resume` flag for interrupted sprints
   - Files: `sprint.py`, `cli.py:1619-1735`

2. **Add Signal Handling to Sprint**
   - Implement `_signal_handler` pattern from auto/parallel
   - Graceful shutdown during wave execution
   - Files: `cli.py:1619-1735`

### Medium Priority

3. **Standardize Argument Flags**
   - Add `-t` short flag for `--timeout` in sprint
   - Add `-w` short flag for `--max-workers` in sprint
   - Consider adding `--skip` to sprint
   - Files: `cli.py:1284-1336`

4. **Add Error Handling Wrapper to Sprint**
   - Wrap `_cmd_sprint_run()` in try/except/finally
   - Add cleanup on failure
   - Files: `cli.py:1619-1735`

5. **Harmonize Timeout Defaults**
   - Currently: auto=3600s, parallel=7200s, sprint=3600s
   - Consider aligning to single default
   - Files: `config.py`, `types.py`, `sprint.py`

### Low Priority

6. **Create Shared CLI Argument Module**
   - Extract common argument definitions
   - Reduce duplication across entry points
   - Files: New `cli_args.py` module

7. **Add Quiet Mode to Auto and Sprint**
   - Parallel supports `--quiet/-q`
   - Auto and sprint always verbose
   - Files: `cli.py`

---

## Test Coverage Summary

| Tool | Unit Tests | Integration Tests | Total Lines |
|------|------------|-------------------|-------------|
| ll-auto | ~35 | Via workflow | ~800 |
| ll-parallel | ~220 | ~30 | ~1500 |
| ll-sprint | ~23 | 3 | ~475 |

**Recommendation**: Expand sprint integration tests, particularly for:

- Multi-wave execution scenarios
- Error recovery paths
- Dependency cycle handling

---

## Code Quality Scores

| Metric | ll-auto | ll-parallel | ll-sprint |
|--------|---------|-------------|-----------|
| Type Hints | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Documentation | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Error Handling | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Test Coverage | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Code Organization | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## Conclusion

All three CLI tools demonstrate professional Python development practices with strong type safety, comprehensive documentation, and consistent coding style. The main consistency gap is that **ll-sprint lacks the robustness features** (state persistence, signal handling, comprehensive error handling) that ll-auto and ll-parallel share.

**Recommended Next Steps**:

1. Add state persistence and signal handling to ll-sprint
2. Harmonize CLI argument patterns across tools
3. Expand sprint integration test coverage
