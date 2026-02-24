# ENH-461: Audit config-schema.json for fields unreachable from init or configure

## Issue Summary
Several `config-schema.json` fields are not configurable through `/ll:init` or `/ll:configure`. Each must be triaged as: expose in configure, document as manual config, or remove from schema.

## Research Findings

### Field Audit & Categorization

| Field | Active Consumers | Category | Rationale |
|-------|-----------------|----------|-----------|
| `scan.custom_agents` | config.py, show-output.md | Document | Power-user feature; custom scanning agents rarely needed |
| `continuation.max_continuations` | worker_pool.py, issue_manager.py, show-output.md | **Expose** | Controls ll-auto/ll-parallel retries; users frequently adjust |
| `context_monitor.estimate_weights.*` | context-monitor.sh | Document | Advanced token estimation tuning; 5 sub-fields, niche |
| `context_monitor.post_compaction_percent` | context-monitor.sh | Document | Advanced compaction tuning; niche |
| `product.analyze_user_impact` | scan-product.md, product-analyzer | Document | Product sub-toggle; defaults to true, rarely changed |
| `product.analyze_business_value` | scan-product.md, product-analyzer | Document | Product sub-toggle; defaults to true, rarely changed |
| `product.goals_discovery.max_files` | schema only | Document | Fine-tuning for goal discovery |
| `product.goals_discovery.required_files` | schema only | Document | Fine-tuning for goal discovery |
| `prompt_optimization.bypass_prefix` | user-prompt-check.sh, show-output.md | Document | Default `*` works well; well-documented already |

### Decisions
- **1 field to expose**: `continuation.max_continuations` → add to configure continuation area
- **8 fields to document**: All others → add "Manual Configuration" section to docs/CONFIGURATION.md
- **0 fields to remove**: All have active consumers

## Implementation Plan

### Phase A: Expose `max_continuations` in configure
1. Edit `skills/configure/areas.md`:
   - Add `max_continuations` to continuation area Current Values display
   - Add 4th question to continuation Round 1 for max_continuations (currently 3 questions, max is 4)

### Phase B: Document "Manual Configuration" fields
1. Edit `docs/CONFIGURATION.md`:
   - Add new `## Manual Configuration` section after the `documents` section (before Variable Substitution)
   - Document all 8 rarely-needed fields grouped by config section
   - Include JSON examples for each field showing how to set it manually

### Phase C: Update scan section table
1. Edit `docs/CONFIGURATION.md`:
   - Add `custom_agents` to the scan section's config table (currently missing)

### Phase D: Add product sub-fields to docs
1. Edit `docs/CONFIGURATION.md`:
   - Add `goals_discovery.max_files` and `goals_discovery.required_files` to product section table

## Success Criteria
- [ ] `continuation.max_continuations` configurable via `/ll:configure continuation`
- [ ] All 8 manual-config fields documented in CONFIGURATION.md
- [ ] `scan.custom_agents` in scan section table
- [ ] `product.goals_discovery.*` fields in product section table
- [ ] Tests pass
- [ ] Lint passes

## Files to Modify
- `skills/configure/areas.md` — Add max_continuations to continuation area
- `docs/CONFIGURATION.md` — Add Manual Configuration section, update section tables
