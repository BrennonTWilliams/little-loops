# BUG-274: Directory trees outdated across docs - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-274-directory-trees-outdated-across-docs.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

Three documentation files contain directory tree listings that are missing recently added modules:

### Key Discoveries
- README.md:585-632 - Missing: `loops/`, `fsm/` subdirectory, 12+ Python modules
- CONTRIBUTING.md:107-192 - Missing: `loops/`, `frontmatter.py`, `doc_counts.py`, `link_checker.py`, `__init__.py` in parallel, `tasks/` in parallel, `INDEX.md` in docs
- ARCHITECTURE.md:60-161 - Missing: `loops/`, `plugin.json` path wrong (shows root instead of `.claude-plugin/`), `concurrency.py` and `fsm-loop-schema.json` in fsm, `file_hints.py` and `overlap_detector.py` in parallel, `lib/common.sh` in hooks, `optimize-prompt-hook.md` in hooks/prompts, 7 Python modules, command count stale (34 vs 35)

## Desired End State

All three directory trees accurately reflect the current filesystem, including:
- `loops/` top-level directory with 5 YAML files
- All Python modules in `scripts/little_loops/`
- Complete `fsm/` and `parallel/` subdirectories
- `hooks/scripts/lib/common.sh`
- Correct `plugin.json` path in ARCHITECTURE.md
- Correct command count (35) in ARCHITECTURE.md

## What We're NOT Doing

- Not changing the format/style conventions of each file (each has a different level of detail)
- Not expanding sections that are currently collapsed (e.g., hooks in README stays collapsed)
- Not adding new documentation beyond directory trees

## Implementation Phases

### Phase 1: Update README.md

Add `loops/` directory, add missing Python modules, add `fsm/` subdirectory. Keep the same moderate detail level.

### Phase 2: Update CONTRIBUTING.md

Add `loops/` directory, add 3 missing Python modules, add `__init__.py` and `tasks/` to parallel, add `INDEX.md` to docs list.

### Phase 3: Update ARCHITECTURE.md

Fix `plugin.json` path, update command count to 35, add `loops/` directory, add missing Python modules, add missing fsm/parallel files, add `lib/common.sh` to hooks, add `optimize-prompt-hook.md` to hooks/prompts.

## Testing Strategy

- Visual review of tree formatting (proper box-drawing characters)
- Lint/type checks pass (no code changes, but verify)
