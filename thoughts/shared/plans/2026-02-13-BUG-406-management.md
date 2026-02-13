# BUG-406: CONTRIBUTING.md project tree shows `cli.py` but actual structure is `cli/` package - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-406-contributing-cli-package-tree-outdated.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

CONTRIBUTING.md lines 166-168 show `cli.py` as a single file:
```
        ├── cli.py        # CLI entry points (ll-auto, ll-parallel, ll-messages,
        │                 #   ll-loop, ll-sprint, ll-sync, ll-history,
        │                 #   ll-verify-docs, ll-check-links)
```

The actual structure is a `cli/` package with 10 modules at `scripts/little_loops/cli/`.

### Key Discoveries
- ARCHITECTURE.md:136-147 already has the correct `cli/` package tree (but missing `next_id.py`)
- CONTRIBUTING.md uses the convention of NO inline comments on sub-package module files (see `fsm/` and `parallel/` patterns)
- The issue's "Expected Behavior" proposes inline comments on each module, but this differs from the CONTRIBUTING.md convention

## Desired End State

CONTRIBUTING.md lines 166-168 replaced with the `cli/` package directory tree following the existing CONTRIBUTING.md convention (directory comment, no individual module comments).

## What We're NOT Doing

- Not updating docs/ARCHITECTURE.md (separate scope, though the Mermaid diagram at line 36 is also stale)
- Not updating docs/CLI-TOOLS-AUDIT.md (separate issue, has 12 stale references)
- Not updating issue files that reference cli.py
- Not adding inline comments to individual cli/ modules (following CONTRIBUTING.md convention for sub-packages)

## Solution Approach

Replace the 3-line `cli.py` entry (lines 166-168) with a `cli/` directory tree listing all 10 modules. Follow the existing `fsm/` and `parallel/` sub-package pattern in CONTRIBUTING.md: directory gets a comment, individual files do not.

## Implementation

### Phase 1: Update CONTRIBUTING.md

**File**: `CONTRIBUTING.md`
**Changes**: Replace lines 166-168 (`cli.py` entry) with `cli/` package tree

Old (3 lines):
```
        ├── cli.py        # CLI entry points (ll-auto, ll-parallel, ll-messages,
        │                 #   ll-loop, ll-sprint, ll-sync, ll-history,
        │                 #   ll-verify-docs, ll-check-links)
```

New (12 lines):
```
        ├── cli/                 # CLI entry points
        │   ├── __init__.py
        │   ├── auto.py
        │   ├── docs.py
        │   ├── history.py
        │   ├── loop.py
        │   ├── messages.py
        │   ├── next_id.py
        │   ├── parallel.py
        │   ├── sprint.py
        │   └── sync.py
```

#### Success Criteria
- [ ] `cli.py` no longer appears in CONTRIBUTING.md project tree
- [ ] `cli/` directory with all 10 modules is listed
- [ ] Tree formatting matches existing `fsm/` and `parallel/` sub-package patterns
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`

## Testing Strategy

- Verify no broken formatting in the markdown tree
- Run existing test suite to confirm no regressions
