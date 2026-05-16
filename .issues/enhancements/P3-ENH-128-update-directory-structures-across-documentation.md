---
discovered_commit: 46b2118b5a8ca70c3eb93c69ab9f9ab14f64ddb5
discovered_branch: main
discovered_date: 2026-01-23T00:00:00Z
discovered_by: audit_docs
status: done
completed_at: 2026-02-13T00:00:00Z
---

# ENH-128: Update directory structures across documentation

## Summary

Documentation enhancement found by `/ll:audit-docs`.

Multiple documentation files have outdated directory structure diagrams that don't reflect the current project layout. Missing components include the `skills/` directory and several FSM modules.

## Affected Files

### 1. docs/ARCHITECTURE.md (Lines 60-147)

Missing from directory structure:
- `skills/` directory (4 skills: analyze-history, capture-issue, issue-workflow, workflow-automation-proposer)

Note: `fsm/signal_detector.py` and `fsm/handoff_handler.py` are already documented at lines 130-131.

### 2. CONTRIBUTING.md (Lines 71-119)

Missing from project structure:
- `skills/` directory with 4 skills
- `fsm/signal_detector.py` and `fsm/handoff_handler.py` in the fsm/ directory listing
- `issue_history.py` module

### 3. docs/API.md (Lines 16-36)

Missing from Module Overview table:
- `little_loops.issue_history` module
- `little_loops.logo` module

Note: FSM submodules (signal_detector, handoff_handler) are covered by the `little_loops.fsm` entry, following the same pattern as `little_loops.parallel`.

## Current Structure (Partial)

```
little-loops/
├── commands/             # 26 slash commands
├── agents/               # 8 agents
├── hooks/                # Lifecycle hooks
├── templates/            # Project templates
├── docs/                 # Documentation
├── scripts/              # Python package
│   └── little_loops/
│       ├── fsm/
│       │   ├── schema.py
│       │   ├── compilers.py
│       │   ├── evaluators.py
│       │   ├── executor.py
│       │   ├── interpolation.py
│       │   ├── validation.py
│       │   └── persistence.py
│       └── ...
└── ...
```

## Expected Structure

```
little-loops/
├── commands/             # 26 slash commands
├── agents/               # 8 agents
├── skills/               # 4 skills (NEW)
│   ├── analyze-history/
│   ├── capture-issue/
│   ├── issue-workflow/
│   └── workflow-automation-proposer/
├── hooks/                # Lifecycle hooks
├── templates/            # Project templates
├── docs/                 # Documentation
├── scripts/              # Python package
│   └── little_loops/
│       ├── fsm/
│       │   ├── schema.py
│       │   ├── compilers.py
│       │   ├── evaluators.py
│       │   ├── executor.py
│       │   ├── interpolation.py
│       │   ├── validation.py
│       │   ├── persistence.py
│       │   ├── signal_detector.py  # NEW
│       │   └── handoff_handler.py  # NEW
│       ├── issue_history.py        # Document in API.md
│       ├── logo.py                  # Document in API.md
│       └── ...
└── ...
```

## Implementation Notes

1. Update ARCHITECTURE.md directory structure diagram - add `skills/` directory
2. Update CONTRIBUTING.md project structure - add `skills/`, FSM modules, and `issue_history.py`
3. Add `issue_history` and `logo` module entries to API.md Module Overview table

## Impact

- **Severity**: Low (documentation completeness)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-23 | Completed: 2026-01-23 | Priority: P3

---

## Verification Notes

**Validated**: 2026-01-23 by `/ll:ready-issue`

- Confirmed `skills/` directory exists with 4 skills
- Confirmed `fsm/signal_detector.py` and `fsm/handoff_handler.py` exist
- Confirmed `issue_history.py` and `logo.py` modules exist
- Verified line numbers in affected documentation files are accurate
- Corrected issue: ARCHITECTURE.md already documents FSM modules at lines 130-131
- Corrected issue: FSM submodules follow existing pattern (covered by parent package entry)

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `docs/ARCHITECTURE.md`: Added `skills/` directory with 4 skills to directory structure
- `CONTRIBUTING.md`: Added `skills/` directory, FSM modules (signal_detector.py, handoff_handler.py, __init__.py), and Python modules (issue_history.py, sprint.py)
- `docs/API.md`: Added module entries for issue_history, logo, and dependency_graph

### Additional Fixes
- Renamed duplicate `P4-ENH-128-readme-command-naming-inconsistency.md` to `P4-ENH-133` to resolve ID collision

### Verification Results
- Documentation changes verified by visual inspection
- All referenced files/modules exist in the codebase
