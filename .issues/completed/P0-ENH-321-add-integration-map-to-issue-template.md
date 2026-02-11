---
discovered_date: 2026-02-10
discovered_by: user_feedback
completed_date: 2026-02-10
implementation_session: 2026-02-10
parent_issue: ENH-320
---

# ENH-321: Add Integration Map Section to Issue Template

## Summary

Add "Integration Map" section to v2.0 issue template to enumerate all affected files, callers, tests, documentation, and configuration - preventing isolated changes that break other parts of the codebase.

## Current Behavior

Template v2.0 (after ENH-320) has sections for:
- **Proposed Solution** - Suggests what to change
- **Implementation Steps** - High-level phases (3-8 steps)
- **Root Cause** (BUG) - Points to WHERE bug is
- **API/Interface** (FEAT/ENH) - Documents contract changes

**Gap**: None of these sections require comprehensive enumeration of:
- Files that call/import the changed code
- Files with similar patterns that should be updated consistently
- Test files that need updates
- Documentation files that reference changed behavior
- Configuration files affected

**Result**: Common failure pattern reported by user:
```
Fix one file → Deploy → Breaks callers → Breaks tests → Stale docs
```

## Expected Behavior

Template should include "Integration Map" section that forces developers/agents to:
1. Use grep to find ALL callers/importers
2. Identify similar patterns for consistency
3. Enumerate test files needing updates
4. List documentation needing updates
5. Note configuration changes

**Result**: Comprehensive change checklist BEFORE writing code.

## Motivation

**Critical Gap Identified**: User reported "missing integrations with changes from the issue with the rest of the codebase" as a common bad pattern.

**Evidence of Problem**:
- Template v2.0 audit shows NO section requires comprehensive file enumeration
- Implementers add custom "Files" sections because template lacks it
- AI agents particularly struggle with "what else breaks?" without explicit guidance
- Implementation Steps designed to be high-level (3-8 phases), not detailed file lists

**Quantified Impact**:
- Prevents most common implementation failure mode
- Reduces post-deployment breakage from isolated changes
- Improves AI agent success rate by providing complete change map
- Enables human reviewers to verify completeness at a glance

**Urgency**: P0 because we're implementing v2.0 NOW - better to fix before creating issues with the gap than to need v2.1 later.

## Root Cause

- **File**: `templates/issue-sections.json`
- **Anchor**: Template structure after ENH-320 implementation
- **Cause**: Template optimization focused on removing unused sections and adding high-level guidance, but didn't address the critical "what else needs to change?" question. Implementation Steps section explicitly designed to be high-level (not file enumeration), leaving no section for comprehensive integration mapping.

## Proposed Solution

Add "Integration Map" section to `common_sections` in template, positioned between "Proposed Solution" and "Implementation Steps".

**Section Definition**:
```json
{
  "Integration Map": {
    "required": false,
    "description": "Files, modules, and systems that interact with or depend on the changed code",
    "ai_usage": "HIGH",
    "human_value": "HIGH",
    "quality_guidance": [
      "Identify files that call/import the changed code (use grep to find references)",
      "List files with similar patterns that should be updated consistently",
      "Enumerate test files that need updates or new tests",
      "Identify documentation files that reference this behavior",
      "Note configuration files, constants, or settings affected",
      "Consider integration points with external systems",
      "Think: what breaks if I change this in isolation?",
      "Use N/A for categories with no changes, don't leave blank"
    ],
    "creation_template": "### Files to Modify\n- TBD\n\n### Dependent Files (Callers/Importers)\n- TBD - use grep\n\n### Similar Patterns\n- TBD\n\n### Tests\n- TBD\n\n### Documentation\n- TBD\n\n### Configuration\n- N/A or list files"
  }
}
```

**Template Structure**:
```markdown
## Integration Map

### Files to Modify
- `path/to/file.py` - What changes here

### Dependent Files (Callers/Importers)
- `path/to/caller.py` - Imports function_name(), needs update
- Use grep -r "function_name" . to find references

### Similar Patterns
- `path/to/similar.py` - Same pattern, update for consistency

### Tests
- `tests/test_file.py` - Update existing tests
- `tests/test_integration.py` - Add integration tests

### Documentation
- `docs/API.md` - Update function documentation
- N/A - No doc changes needed

### Configuration
- `config/settings.yaml` - Update defaults
- N/A - No config changes
```

## Integration Map

### Files to Modify
- `templates/issue-sections.json` - Add Integration Map to common_sections
- `docs/ISSUE_TEMPLATE.md` - Add comprehensive section documentation
- `CONTRIBUTING.md` - Add to quality checklist
- `IMPLEMENTATION_SUMMARY.md` - Update with new section

### Dependent Files (Callers/Importers)
- All commands reading template (already dynamic, no changes needed):
  - `/ll:capture_issue` - Reads template, will auto-include Integration Map
  - `/ll:refine_issue` - Reads template, will prompt for Integration Map
  - `/ll:ready_issue` - Reads template, will validate Integration Map

### Similar Patterns
- N/A - Integration Map is unique concept, no similar sections exist

### Tests
- Manual verification: Template JSON valid after addition
- Manual verification: Integration Map appears in full creation variant
- Manual verification: Quality checks include Integration Map validation

### Documentation
- `docs/ISSUE_TEMPLATE.md` - Add full section guide with BUG and FEAT examples
- `CONTRIBUTING.md` - Add to quality checklist and best practices
- `IMPLEMENTATION_SUMMARY.md` - Update counts and benefits

### Configuration
- N/A - No configuration changes needed

## Implementation Steps

1. Add "Integration Map" to `common_sections` in template
2. Position after "Proposed Solution", before "Implementation Steps"
3. Update changelog in _meta to include Integration Map
4. Add to "full" creation_variant include_common list
5. Add 4 quality checks for Integration Map validation
6. Update `docs/ISSUE_TEMPLATE.md` with comprehensive section guide
7. Add Integration Map to both complete issue examples (BUG and FEAT)
8. Update `CONTRIBUTING.md` quality checklist
9. Update `IMPLEMENTATION_SUMMARY.md` with new counts
10. Verify JSON validity

## Success Metrics

**Immediate verification**:
- ✅ Template JSON valid after addition
- ✅ Integration Map in common_sections with HIGH ai_usage
- ✅ Integration Map in full creation variant
- ✅ 4 quality checks added
- ✅ Documentation includes examples and guidance

**Target metrics** (to measure after deployment):
- Integration Map present in >70% of new issues
- Reduction in post-deployment breakage from isolated changes
- AI agents identify all affected files before implementation
- Human reviewers can verify completeness at a glance

## Scope Boundaries

**In scope**:
- Adding Integration Map section to template
- Comprehensive documentation with examples
- Quality checks for validation
- Updating all v2.0 documentation

**Out of scope**:
- Automated population of Integration Map (future: grep/analysis tools)
- Integration with codebase-locator agent (future enhancement)
- Enforcement of Integration Map (remains optional)
- Changes to Python issue parser (already handles arbitrary sections)

## Impact

- **Priority**: P0 - Critical gap identified in v2.0 template during implementation session
- **Effort**: Small - Single section addition + documentation (~15 minutes implementation)
- **Risk**: Very Low - Optional section, backward compatible, no breaking changes
- **Breaking Change**: No - Optional section, existing issues unaffected

## Related Key Documentation

- ENH-320 - Parent issue (Issue Template v2.0 optimization)
- `docs/ISSUE_TEMPLATE.md` - Template documentation
- `templates/issue-sections.json` - Template definition

## Labels

`enhancement`, `template`, `ai-agent-quality`, `integration`, `completed`

## Status

**Completed** | Created: 2026-02-10 | Completed: 2026-02-10 | Priority: P0

---

## Implementation Notes

### Files Modified
- ✅ `templates/issue-sections.json` - Added Integration Map section
- ✅ `docs/ISSUE_TEMPLATE.md` - Added comprehensive documentation with examples
- ✅ `CONTRIBUTING.md` - Added to quality checklist and best practices
- ✅ `IMPLEMENTATION_SUMMARY.md` - Updated counts and benefits

### Verification Results
- ✅ Template JSON valid (version 2.0)
- ✅ Common sections: 12 total (11 active + 1 deprecated)
- ✅ Integration Map metadata: ai_usage=HIGH, human_value=HIGH, required=false
- ✅ Integration Map in full creation variant: True
- ✅ Integration Map in minimal creation variant: False
- ✅ Quality checks added: 4 checks for Integration Map validation

### Section Order (Full Template)
1. Summary
2. Current Behavior
3. Expected Behavior
4. Motivation
5. Proposed Solution
6. **Integration Map** ← NEW (position #6)
7. Implementation Steps
8. Impact
9. Related Key Documentation
10. Labels
11. Status

### Quality Checks Added
1. Integration Map should identify callers/importers (use grep to find references)
2. Integration Map should list test files that need updates for each changed file
3. Integration Map should note similar patterns to keep consistent across codebase
4. Integration Map should use 'N/A' for categories with no changes, not leave them as 'TBD'

### Key Achievements

1. **Addresses critical gap**: User-identified "common bad pattern" of missing integrations
2. **Prevents isolated changes**: Forces comprehensive thinking about affected files
3. **Enhances AI agent success**: Provides complete change map before implementation
4. **Improves review process**: Human reviewers can verify completeness
5. **Backward compatible**: Optional section, no breaking changes

### Why This Section Matters

**Common failure pattern WITHOUT Integration Map**:
```
Fix auth.py → Deploy → Breaks API routes → Breaks background jobs →
Stale tests pass → Docs outdated → Users confused
```

**Success pattern WITH Integration Map**:
```
Identify all 4 callers → Fix all 4 → Update all 4 tests →
Update docs → Complete change → No breakage
```

### Template v2.0 Final Stats (with Integration Map)

**New sections**: 5
- Motivation (common)
- Integration Map (common) ← Added in this issue
- Implementation Steps (common)
- Root Cause (BUG)
- API/Interface (FEAT/ENH)

**Total sections per issue**: ~20 (down from 21 in v1.0)
**Common sections**: 12 (11 active + 1 deprecated)

### User Feedback

> "How well does our v2 template that we just created account for integration points?
> I don't want to prematurely optimize/fix what isn't broken, but if there really is a gap we should fix it now"

**Assessment**: Real gap, not premature optimization
**Evidence**: Template audit showed no section requires comprehensive file enumeration
**Decision**: Fixed immediately during v2.0 implementation session
**Result**: Integration Map section addresses the gap completely
