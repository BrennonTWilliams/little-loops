---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-343: Unused config schema sections with no implementation

## Summary

Several config schema sections are defined in `config-schema.json` but have no corresponding implementation in any Python module, command, or skill. This creates confusion about what's actually configurable.

## Context

Identified during a config consistency audit. These sections suggest features that were planned but never wired up.

## Unused Schema Sections

- `issues.capture_template` - defined but `capture_issue` skill doesn't read it
- `issues.duplicate_detection` - defined but duplicate detection doesn't read thresholds from config
- `workflow.phase_gates` - defined, no implementation
- `workflow.deep_research` - defined, no implementation
- `workflow.plan_template` - defined, no implementation
- `prompt_optimization` - defined, no implementation (settings exist but aren't read by code)

## Current Behavior

Six config schema sections are defined in `config-schema.json` but have no corresponding implementation: `issues.capture_template`, `issues.duplicate_detection`, `workflow.phase_gates`, `workflow.deep_research`, `workflow.plan_template`, `prompt_optimization`.

## Expected Behavior

Each schema section should either be wired into relevant code or removed from the schema to avoid confusion about what's actually configurable.

## Motivation

This enhancement would:
- Reduce confusion: users may configure these settings expecting them to work
- Clean up technical debt: unused schema sections suggest abandoned features
- Improve config documentation accuracy

## Proposed Solution

For each section, either:
1. Wire it into the relevant code so it's actually used, OR
2. Remove it from `config-schema.json` to reduce confusion

A pragmatic approach: remove sections with no near-term implementation plan, keep sections that are partially wired.

## Scope Boundaries

- **In scope**: Auditing each unused section and either wiring or removing it
- **Out of scope**: Implementing the features these sections were designed for

## Implementation Steps

1. Audit each unused section to determine if any code partially references it
2. Remove sections with no implementation or near-term plan
3. Wire sections that are partially implemented
4. Update any documentation referencing removed sections

## Integration Map

### Files to Modify
- `config-schema.json` - Remove or annotate unused sections
- `scripts/little_loops/config.py` - Remove corresponding unused dataclass fields if any

### Dependent Files (Callers/Importers)
- `.claude/ll-config.json` - May have values for unused keys

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_config.py` - Verify config loading still works after removal

### Documentation
- N/A

### Configuration
- `config-schema.json` - Primary file being cleaned up

## Impact

- **Priority**: P4 - Cleanup, no functional impact
- **Effort**: Small - Audit and delete/wire 6 sections
- **Risk**: Low - Removing unused schema sections has no runtime effect
- **Breaking Change**: No

## Labels

`enhancement`, `config`, `tech-debt`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P4
