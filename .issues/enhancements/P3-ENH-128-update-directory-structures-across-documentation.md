---
discovered_commit: 46b2118b5a8ca70c3eb93c69ab9f9ab14f64ddb5
discovered_branch: main
discovered_date: 2026-01-23T00:00:00Z
discovered_by: audit_docs
---

# ENH-128: Update directory structures across documentation

## Summary

Documentation enhancement found by `/ll:audit_docs`.

Multiple documentation files have outdated directory structure diagrams that don't reflect the current project layout. Missing components include the `skills/` directory and several FSM modules.

## Affected Files

### 1. docs/ARCHITECTURE.md (Lines 60-147)

Missing from directory structure:
- `skills/` directory (4 skills: analyze-history, capture-issue, issue-workflow, workflow-automation-proposer)
- `fsm/signal_detector.py`
- `fsm/handoff_handler.py`

### 2. CONTRIBUTING.md (Lines 71-119)

Missing from project structure:
- `skills/` directory with 4 skills

### 3. docs/API.md (Lines 16-36)

Missing from Module Overview table:
- `little_loops.issue_history` module
- `little_loops.logo` module
- `little_loops.fsm.signal_detector` module
- `little_loops.fsm.handoff_handler` module

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

1. Update ARCHITECTURE.md directory structure diagram
2. Update CONTRIBUTING.md project structure
3. Add module entries to API.md Module Overview table
4. Consider adding basic documentation for new modules in API.md

## Impact

- **Severity**: Low (documentation completeness)
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P3
