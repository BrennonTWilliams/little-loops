---
type: ENH
id: ENH-461
title: Audit config-schema.json for fields unreachable from init or configure
priority: P4
status: open
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

---

## Status

**Open** | Created: 2026-02-22 | Priority: P4
