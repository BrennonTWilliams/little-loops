---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-369: audit_claude_config lacks settings.json content validation

## Summary

The `/ll:audit_claude_config` command validates JSON syntax and path references in config files but does not validate `settings.json` contents against the documented Claude Code settings schema. It also has no awareness of managed settings or `~/.claude.json`. Adding content validation would catch typos in setting keys and invalid configuration values.

## Current Behavior

The Config Files Auditor (Task 3 in `commands/audit_claude_config.md:183-208`) only:
- Checks if config files exist
- Validates JSON syntax
- Checks schema compliance for `ll-config.json` (plugin-specific config)
- Verifies path references

It does not:
- Validate `settings.json` keys against the 30+ documented Claude Code settings
- Check permission rule syntax (`Tool(specifier)` format)
- Validate sandbox configuration structure
- Check for `$schema` reference in settings files
- Know about `managed-settings.json` or `managed-mcp.json`
- Know about `~/.claude.json` (preferences, OAuth, per-project state)

## Expected Behavior

The audit should optionally validate:
1. Settings keys in `settings.json` files are recognized (warn on unknown keys)
2. Permission rules follow `Tool(specifier)` syntax
3. `$schema` reference is present for IDE validation support
4. Awareness of `~/.claude.json` for completeness

## Motivation

Typos in settings keys (e.g., `permisions` vs `permissions`) silently fail with no warning. The audit is the natural place to catch these configuration errors before they cause confusion.

## Proposed Solution

Add a new validation step to the Config Files Auditor task that checks settings.json contents against a known-keys list derived from the official documentation. This could be a simple list of valid top-level keys embedded in the audit command prompt.

## Implementation Steps

1. Add a known-settings-keys reference list to the audit command or a supporting data file
2. Add settings.json content validation to the Config Files Auditor task prompt
3. Optionally add managed settings awareness for enterprise environments

## Impact

- **Priority**: P4 - Nice to have; most users won't hit this
- **Effort**: Medium - Requires maintaining a settings key reference list
- **Risk**: Low - Additive validation, no changes to existing behavior
- **Breaking Change**: No

## Scope Boundaries

- Out of scope: Full schema validation of every settings value type
- Out of scope: Validating managed settings deployment (enterprise concern)
- Out of scope: Modifying any settings files (audit only)

## Success Metrics

- Audit detects at least 1 unrecognized key in a settings file with a deliberate typo

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists configuration files |
| architecture | docs/ARCHITECTURE.md | Plugin configuration |

## Labels

`enhancement`, `captured`, `audit`, `config`

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00ffa686-5907-4ed1-8765-93f478b14da2.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-12
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: MEDIUM
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: MEDIUM

### Rationale
While catching settings typos has value, this requires maintaining a 30+ setting key reference list that will need updates as Claude Code evolves. The medium maintenance burden and complexity outweigh the utility for a P4 issue.
