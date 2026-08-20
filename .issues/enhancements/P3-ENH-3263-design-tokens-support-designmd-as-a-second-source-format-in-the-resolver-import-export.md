---
id: ENH-3263
type: ENH
title: 'design-tokens: support DESIGN.md as a second source format in the resolver
  (import + export)'
priority: P3
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T20:02:21Z'
parent: EPIC-1751
---

# ENH-3263: design-tokens: support DESIGN.md as a second source format in the resolver (import + export)

## Summary

Teach `load_design_tokens()` to read a root `DESIGN.md` (Google Labs' Apache-2.0
design-system spec: YAML frontmatter tokens + markdown intent body) as an
alternative front-end onto the existing resolver, and add an exporter that emits
DESIGN.md from a token profile. DESIGN.md supplements the profile format rather
than replacing it: it has no theme mechanism and no primitives/semantic split, so
it cannot back `render_as_css_vars_themed()` or the `ll-verify-design-tokens`
half-flipped-theme lint. Also injects the DESIGN.md prose body into loop context
so a project's own design guidance can replace prompt-hardcoded anti-slop rules.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```
