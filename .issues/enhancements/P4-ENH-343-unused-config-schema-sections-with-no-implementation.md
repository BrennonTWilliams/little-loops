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

## Proposed Fix

For each section, either:
1. Wire it into the relevant code so it's actually used, OR
2. Remove it from `config-schema.json` to reduce confusion

A pragmatic approach: remove sections with no near-term implementation plan, keep sections that are partially wired.

---

## Status

**Open** | Created: 2026-02-11 | Priority: P4
