# ENH-368: plugin-config-auditor missing hook event types and handler types - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-368-plugin-config-auditor-missing-hook-event-and-handler-types.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `plugin-config-auditor` agent (`agents/plugin-config-auditor.md`) validates hooks configuration but has incomplete knowledge:

### Key Discoveries
- `agents/plugin-config-auditor.md:57` - Lists only 8 event types, missing 6
- `agents/plugin-config-auditor.md:58` - Timeout recommendation "<5s" contradicts official defaults (600s/30s/60s)
- `agents/plugin-config-auditor.md:89-97` - Hook checklist only validates basic structure, no handler type awareness
- `commands/audit_claude_config.md:191` - Also states incorrect "<5s recommended"
- `docs/claude-code/hooks-reference.md:27-42` - Authoritative list of all 14 event types
- `docs/claude-code/hooks-reference.md:242-277` - Authoritative handler types and fields

## Desired End State

1. All 14 official hook event types recognized in the auditor
2. All 3 hook handler types (`command`, `prompt`, `agent`) validated
3. Handler fields (`async`, `statusMessage`, `once`, `model`) included in validation
4. Timeout recommendations are type-specific and aligned with official defaults
5. Audit command prompt also updated for consistency

### How to Verify
- Run `/ll:audit-claude-config` and confirm no false positives on valid hook configurations
- Review the updated agent file for completeness against `docs/claude-code/hooks-reference.md`

## What We're NOT Doing

- Not adding runtime validation logic (this is agent prompt content only)
- Not modifying the consistency-checker agent (it handles cross-reference validation, not structure)
- Not changing the output format (already supports Type column)

## Solution Approach

Update the agent prompt text in two locations to reflect complete, accurate hook knowledge.

## Implementation Phases

### Phase 1: Update plugin-config-auditor.md

#### Changes Required

**1. Line 57 - Event types list**: Replace 8 types with all 14
**2. Line 58 - Timeout recommendation**: Replace blanket "<5s" with type-specific defaults
**3. Lines 89-97 - Hook checklist**: Expand with handler types and fields validation

### Phase 2: Update audit_claude_config.md

**Line 191 - Timeout recommendation**: Align with type-specific defaults

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] No broken markdown structure in modified files

**Manual Verification**:
- [ ] Event types list matches `docs/claude-code/hooks-reference.md:27-42`
- [ ] Handler types match `docs/claude-code/hooks-reference.md:242-246`
- [ ] Timeout defaults match `docs/claude-code/hooks-reference.md:255`

## References

- Official hook reference: `docs/claude-code/hooks-reference.md`
- Original issue: `.issues/enhancements/P3-ENH-368-plugin-config-auditor-missing-hook-event-and-handler-types.md`
