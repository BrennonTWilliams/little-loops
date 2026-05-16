---
type: ENH
id: ENH-461
title: Audit config-schema.json for fields unreachable from init or configure
priority: P4
status: completed
created: 2026-02-22
---

# Audit config-schema.json for fields unreachable from init or configure

## Summary

Several `config-schema.json` fields exist but are not configurable through either `/ll:init` or `/ll:configure`. Users can only set these by manually editing `ll-config.json`. For each, decide: expose in configure, or document as "advanced manual config."

## Current Behavior

Several `config-schema.json` fields exist but have no configuration path through either `/ll:init` or `/ll:configure`. Users who need to set these values must manually edit `ll-config.json` without wizard guidance. The unreachable fields are:

| Field | Section | Notes |
|-------|---------|-------|
| `scan.custom_agents` | scan | Custom scanning agents — never exposed |
| `continuation.max_continuations` | continuation | Max auto-continuations for CLI tools |
| `context_monitor.estimate_weights.*` | context_monitor | Token estimation weights (5 sub-fields) |
| `context_monitor.post_compaction_percent` | context_monitor | Post-compaction reset percentage |
| `product.analyze_user_impact` | product | Toggle user impact assessment |
| `product.analyze_business_value` | product | Toggle business value scoring |
| `product.goals_discovery.max_files` | product | Max docs to scan for goal discovery |
| `product.goals_discovery.required_files` | product | Required files for discovery |
| `prompt_optimization.bypass_prefix` | prompt_optimization | Prefix to skip optimization |

## Expected Behavior

Each unreachable field is triaged and assigned to one of three categories:
1. **Commonly needed** → added to `/ll:configure` area flow
2. **Rarely needed** → documented in a "Manual Configuration" section of docs
3. **Never useful or obsolete** → removed from schema

## Motivation

Config fields that exist but cannot be set via init or configure are effectively invisible to most users. This creates two problems: users who need the fields must discover them through docs or schema inspection, and fields that are never used clutter the schema without providing value.

## Proposed Solution

For each field:
1. If commonly needed → add to `/ll:configure` area flow
2. If rarely needed → document in a "Manual Configuration" section of docs
3. If never useful → consider removing from schema

## Scope Boundaries

- **In scope**: Auditing each unreachable field, assigning it to one of three categories, and implementing the chosen action for each
- **Out of scope**: Adding new config fields, changing field semantics, migrating existing user configs

## Integration Map

### Files to Modify
- `config-schema.json` — Remove any fields categorized as "never useful"
- `skills/configure/areas.md` — Add area-specific flows for "commonly needed" fields
- `skills/init/interactive.md` — Add wizard questions for fields promoted to "expose" category
- `docs/` — Add "Manual Configuration" section for "rarely needed" fields

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config.py` — If fields are removed from schema, verify Python config class alignment

### Similar Patterns
- Existing configure area flows in `skills/configure/areas.md`

### Tests
- N/A

### Documentation
- New "Manual Configuration" section in docs

### Configuration
- `config-schema.json` — Source of truth being audited

## Implementation Steps

1. For each unreachable field, categorize as: expose (add to configure), document (add to docs), or remove (delete from schema)
2. For fields to expose: add to the appropriate area in `skills/configure/areas.md`
3. For fields to document: add a "Manual Configuration" section to the relevant doc file
4. For fields to remove: remove from `config-schema.json` and verify `config.py` alignment
5. Update tests if any Python config classes reference removed fields

## Impact

- **Priority**: P4 — Schema hygiene and discoverability improvement; no runtime behavioral impact
- **Effort**: Small-Medium — Audit and categorization first; implementation depends on categories chosen
- **Risk**: Low — Additive for expose/document; removals need config.py verification
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `configure`, `config-schema`, `schema-hygiene`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:manage-issue` - 2026-02-24

---

## Resolution

**Completed** | 2026-02-24

All 9 unreachable fields audited and categorized:

### Exposed in `/ll:configure` (1 field)
- **`continuation.max_continuations`** — Added to continuation area as 4th question in Round 1 with options for 3 (default), 5, and 10 continuations. Also added to Current Values display.

### Documented as Manual Configuration (8 fields)
- **`scan.custom_agents`** — Added to scan section table in CONFIGURATION.md; documented in new Manual Configuration section
- **`context_monitor.estimate_weights.*`** (5 sub-fields) — Documented with full sub-field table in Manual Configuration section
- **`context_monitor.post_compaction_percent`** — Documented in Manual Configuration section
- **`product.analyze_user_impact`** / **`product.analyze_business_value`** — Documented in Manual Configuration section
- **`product.goals_discovery.max_files`** / **`product.goals_discovery.required_files`** — Added to product section table; documented in Manual Configuration section
- **`prompt_optimization.bypass_prefix`** — Documented in Manual Configuration section

### Removed from schema (0 fields)
All fields have active consumers — none removed.

### Files Changed
- `skills/configure/areas.md` — Added `max_continuations` to continuation area (Current Values + Round 1 question)
- `docs/CONFIGURATION.md` — Added Manual Configuration section (8 fields); added `custom_agents` to scan table; added `goals_discovery.*` to product table

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-24 | Priority: P4
