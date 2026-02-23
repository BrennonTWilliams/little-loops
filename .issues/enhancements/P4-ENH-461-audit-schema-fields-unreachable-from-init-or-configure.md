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

## Unreachable Fields

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

## Proposed Change

For each field:
1. If commonly needed → add to `/ll:configure` area flow
2. If rarely needed → document in a "Manual Configuration" section of docs
3. If never useful → consider removing from schema

## Files

- `config-schema.json` (full schema)
- `skills/configure/areas.md` (area-specific flows)
- `skills/init/interactive.md` (wizard rounds)
