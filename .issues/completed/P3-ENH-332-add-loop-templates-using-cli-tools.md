---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-332: Add loop templates using CLI tools

## Summary

All 5 existing loop templates in `loops/` exclusively use `/ll:` skills. None reference CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-messages`, `ll-history`, `ll-workflows`). Templates should be added that leverage these CLI tools for common automation workflows.

## Current Behavior

The 5 existing templates only use `/ll:` slash commands:
- `codebase-scan.yaml` (imperative) - `/ll:scan_codebase`, `/ll:verify_issues`, `/ll:prioritize_issues`
- `issue-readiness-cycle.yaml` (imperative) - `/ll:ready_issue`, `/ll:manage_issue`
- `issue-verification.yaml` (invariants) - `/ll:verify_issues`, `/ll:normalize_issues`
- `pre-pr-checks.yaml` (invariants) - `/ll:check_code`, `/ll:run_tests`
- `quality-gate.yaml` (invariants) - `/ll:check_code`, `/ll:run_tests`

No templates demonstrate shell-based actions using the project's CLI tools.

## Expected Behavior

Additional templates that use CLI tools where appropriate, such as:

- **Sprint execution** loop using `ll-sprint` for batch issue processing
- **Parallel processing** loop using `ll-parallel` for worktree-based parallel execution
- **Workflow analysis** loop using `ll-messages` + `ll-workflows` for pattern discovery
- **History reporting** loop using `ll-history` for retrospective analysis

These should use `action_type: shell` and demonstrate how CLI tools integrate with the FSM loop system.

## Motivation

- CLI tools are a key differentiator of little-loops but templates don't showcase them
- Users may not realize CLI tools can be orchestrated via loops
- Demonstrates the full capabilities of the FSM loop system (shell actions, not just slash commands)
- Provides ready-to-use automation for common multi-tool workflows

## Proposed Solution

Create 2-4 new loop template YAML files in `loops/` that use CLI tools via shell actions:

Example sprint execution template:
```yaml
paradigm: imperative
name: sprint-execution
steps:
  - "ll-sprint run --sprint active"
until:
  check: "ll-sprint status --sprint active --format json | jq '.remaining'"
  condition: "output_equals"
  value: "0"
```

Mix paradigms to ensure coverage — especially if goal/convergence compilers are implemented (ENH-331).

## Integration Map

### Files to Modify
- N/A (new files only)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli.py` - `ll-loop list` auto-discovers templates in `loops/`

### Tests
- Validate new templates compile: `ll-loop compile loops/<new-template>.yaml`

### Documentation
- Update any template listing in docs

### Configuration
- N/A

## Scope Boundaries

- **In scope**: Creating 2-4 new loop template YAML files using CLI tools with `action_type: shell`
- **Out of scope**: Modifying existing templates, changing the FSM loop engine, implementing new paradigm compilers

## Implementation Steps

1. Design 2-4 loop templates using CLI tools for distinct workflows
2. Create YAML files in `loops/`
3. Validate each compiles and simulates correctly with `ll-loop compile` and `ll-loop simulate`

## Impact

- **Priority**: P3 - Improves discoverability and usability of CLI tools
- **Effort**: Small - YAML authoring only, no code changes
- **Risk**: Low - Additive, no existing behavior affected
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `cli`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3

## Session Log
- `/ll:manage_issue` - 2026-02-11T22:14:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f38f197-afe1-4d5f-aac8-6babbc891bd2.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `loops/sprint-execution.yaml`: New imperative loop template using `ll-sprint` for batch sprint processing
- `loops/workflow-analysis.yaml`: New imperative loop template using `ll-messages` + `ll-workflows` pipeline
- `loops/history-reporting.yaml`: New invariants loop template using `ll-history` for retrospective analysis
- `scripts/tests/test_builtin_loops.py`: Updated expected loops set

### Verification Results
- Tests: PASS
- Lint: PASS
- Compile: PASS (all 3 templates)
- Validate: PASS (all 3 templates)

---

## Verification Notes

- **Verified**: 2026-02-11
- **Verdict**: VALID
- 5 templates confirmed in `loops/`: codebase-scan, issue-readiness-cycle, issue-verification, pre-pr-checks, quality-gate
- None use `action_type: shell` or reference CLI tools (ll-auto, ll-parallel, etc.)
- Feature is new work — additive YAML files only
