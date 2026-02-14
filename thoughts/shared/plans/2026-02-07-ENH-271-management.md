# ENH-271: Extract Issue Section Checks into Shared Template File - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-271-shared-issue-template-for-section-checks.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

Six commands each define their own understanding of what sections an issue should contain per type (BUG/FEAT/ENH):

### Key Discoveries
- `commands/refine_issue.md:54-83` — Most structured: defines Required/Conditional/Nice-to-have per type with question prompts
- `commands/refine_issue.md:90-115` — Also defines content quality checks per type
- `commands/capture_issue.md:346-431` — Defines "full" and "minimal" issue templates inline
- `commands/ready_issue.md:114-149` — Simpler checklist: Required Sections, Code References, Metadata
- `commands/scan_codebase.md:196-252` — Issue creation template with Location/Anchor/Permalink sections
- `commands/scan_product.md:225-277` — Product-focused issue template with Product Context section

### Section Name Drift Across Commands
| Concept | refine_issue | ready_issue | scan_codebase | capture_issue |
|---------|-------------|-------------|---------------|---------------|
| Repro steps | "Steps to Reproduce" | "Reproduction steps" | "Reproduction Steps" | (absent) |
| Solution | (not checked) | "Proposed solution/approach" | "Proposed Solution" | "Proposed Solution" |
| Current state | (not checked) | "Current behavior" | "Current Behavior" | "Current Behavior" |

### Existing Infrastructure
- `config-schema.json:105-108` — `issues.templates_dir` field exists, defaults to `null`, unused
- `config.py:99` — `IssuesConfig.templates_dir: str | None = None` already modeled
- `templates/` directory has only project-type config templates (10 JSON files + 1 markdown)
- `init.md:447` — Only existing command that reads from `templates/` dir

## Desired End State

- A single `templates/issue-sections.json` file defines per-type section requirements
- All issue management commands reference this shared template
- Section names are consistent across all commands
- Adding/removing a section in one place updates behavior everywhere

### How to Verify
- All commands reference the shared template file instead of inline definitions
- Section names used consistently across commands (no drift)
- Existing command behavior preserved (no user-facing regression)
- Tests pass, lint passes, types pass

## What We're NOT Doing

- Not changing `capture_issue`'s "minimal" vs "full" template logic — just making both reference the shared definitions
- Not changing the quality checks in `refine_issue.md:90-115` — those are content quality, not section structure
- Not modifying Python code or `config.py` — the `templates_dir` config field exists but is not used by any Python code for section validation; all section checking is in command `.md` files which are LLM-interpreted
- Not modifying `scan_product.md` — it has its own Product Context section that is unique to product scans
- Not adding new sections to any issue type — purely extracting existing definitions
- Not modifying `normalize_issues.md` — it only checks filenames, no section awareness
- Not creating a JSON Schema for issue validation — just a shared section reference file

## Solution Approach

Create a JSON template file at `templates/issue-sections.json` that defines:
1. **Common sections** shared across all issue types
2. **Type-specific sections** for BUG, FEAT, ENH
3. **Section metadata** including requirement level, description, and prompt question
4. **Template variants** for creation ("full"/"minimal") contexts

Then update the four primary commands (`refine_issue`, `capture_issue`, `ready_issue`, `scan_codebase`) to reference this file rather than hard-coding section definitions.

## Implementation Phases

### Phase 1: Create Shared Template File

#### Overview
Create `templates/issue-sections.json` that consolidates all section definitions from the four commands, resolving naming drift.

#### Changes Required

**File**: `templates/issue-sections.json`
**Changes**: New file

```json
{
  "_meta": {
    "name": "Issue Section Definitions",
    "description": "Shared section requirements for BUG, FEAT, and ENH issue types. Referenced by refine_issue, capture_issue, ready_issue, and scan_codebase commands.",
    "version": "1.0"
  },
  "common_sections": {
    "Summary": {
      "required": true,
      "description": "Clear description of the issue",
      "creation_template": "[Description extracted from input]"
    },
    "Context": {
      "required": false,
      "description": "How this issue was identified",
      "creation_template": "[How this issue was identified]",
      "creation_contexts": ["capture"]
    },
    "Current Behavior": {
      "required": true,
      "description": "What happens now",
      "creation_template": "[What currently happens]"
    },
    "Expected Behavior": {
      "required": true,
      "description": "What should happen instead",
      "creation_template": "[What should happen instead]"
    },
    "Proposed Solution": {
      "required": false,
      "description": "Suggested approach to fix or implement",
      "creation_template": "TBD - requires investigation"
    },
    "Impact": {
      "required": true,
      "description": "Priority, effort, and risk assessment",
      "creation_template": "- **Priority**: [P0-P5]\n- **Effort**: TBD\n- **Risk**: TBD"
    },
    "Labels": {
      "required": true,
      "description": "Issue categorization labels",
      "creation_template": "`[type-label]`, `captured`"
    },
    "Status": {
      "required": true,
      "description": "Current issue status",
      "creation_template": "**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]"
    },
    "Related Key Documentation": {
      "required": false,
      "description": "Links to relevant project documentation",
      "creation_template": "_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._"
    }
  },
  "type_sections": {
    "BUG": {
      "Steps to Reproduce": {
        "level": "required",
        "description": "Numbered steps to reproduce the bug",
        "question": "What are the steps to reproduce this bug?",
        "creation_template": "1. [Step 1]\n2. [Step 2]\n3. [Observe: description of the bug]"
      },
      "Actual Behavior": {
        "level": "required",
        "description": "What actually happens when the bug occurs",
        "question": "What actually happens when the bug occurs?"
      },
      "Error Messages": {
        "level": "conditional",
        "description": "Error messages or stack traces",
        "question": "Are there any error messages or stack traces?"
      },
      "Environment": {
        "level": "nice-to-have",
        "description": "Environment details (browser, OS, versions)",
        "question": "What environment does this occur in (browser, OS, versions)?"
      },
      "Frequency": {
        "level": "nice-to-have",
        "description": "How often the bug occurs",
        "question": "How often does this happen (always, sometimes, rarely)?"
      },
      "Location": {
        "level": "conditional",
        "description": "File, line numbers, anchor, and code snippet",
        "creation_contexts": ["scan"]
      }
    },
    "FEAT": {
      "User Story": {
        "level": "required",
        "description": "Who is the user and what do they want to achieve",
        "question": "Who is the user and what do they want to achieve?"
      },
      "Acceptance Criteria": {
        "level": "required",
        "description": "Criteria that must be met for the feature to be complete",
        "question": "What criteria must be met for this feature to be complete?"
      },
      "Edge Cases": {
        "level": "conditional",
        "description": "Edge cases or error scenarios to consider",
        "question": "Are there any edge cases or error scenarios to consider?"
      },
      "UI/UX Details": {
        "level": "conditional",
        "description": "UI/UX requirements or mockups",
        "question": "Are there UI/UX requirements or mockups?"
      },
      "Data/API Impact": {
        "level": "conditional",
        "description": "Impact on data models or API contracts",
        "question": "Does this affect data models or API contracts?"
      }
    },
    "ENH": {
      "Current Pain Point": {
        "level": "required",
        "description": "Specific problem the enhancement solves",
        "question": "What specific problem does this enhancement solve?"
      },
      "Success Metrics": {
        "level": "conditional",
        "description": "How to measure if the enhancement is successful",
        "question": "How will we measure if this enhancement is successful?"
      },
      "Scope Boundaries": {
        "level": "required",
        "description": "What is explicitly out of scope",
        "question": "What is explicitly out of scope for this enhancement?"
      },
      "Backwards Compatibility": {
        "level": "conditional",
        "description": "Backwards compatibility concerns",
        "question": "Are there backwards compatibility concerns?"
      }
    }
  },
  "creation_variants": {
    "full": {
      "description": "Complete issue template with all applicable sections",
      "include_common": ["Summary", "Context", "Current Behavior", "Expected Behavior", "Proposed Solution", "Impact", "Related Key Documentation", "Labels", "Status"],
      "include_type_sections": true
    },
    "minimal": {
      "description": "Lightweight template with core sections only",
      "include_common": ["Summary", "Context", "Related Key Documentation", "Status"],
      "include_type_sections": false
    }
  },
  "quality_checks": {
    "BUG": [
      "Steps to Reproduce should have numbered concrete steps (not \"do the thing\")",
      "Expected vs Actual should describe different specific behaviors (not just \"it should work\")",
      "Error messages should include actual error text, not just \"there's an error\""
    ],
    "FEAT": [
      "User Story should name a specific persona/role and concrete goal",
      "Acceptance Criteria should each be individually testable with clear pass/fail",
      "Edge Cases should describe specific scenarios, not just \"handle errors\""
    ],
    "ENH": [
      "Current Pain Point should describe measurable impact (frequency, severity, affected users)",
      "Success Metrics should have numeric targets or clear before/after comparison",
      "Scope Boundaries should list specific exclusions, not just \"keep it simple\""
    ]
  }
}
```

#### Success Criteria
- [ ] File created at `templates/issue-sections.json`
- [ ] Contains all sections from `refine_issue`, `capture_issue`, `ready_issue`, `scan_codebase`
- [ ] Section names standardized (no drift variants)
- [ ] Includes `_meta` block following existing template convention

---

### Phase 2: Update `refine_issue.md` to Reference Shared Template

#### Overview
Replace inline section checklists with a reference to the shared template file.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Replace lines 52-83 (inline BUG/FEAT/ENH section tables) with a directive to read from `templates/issue-sections.json`, and update lines 100-115 (type-specific quality checks) similarly.

Replace the inline tables with:

```markdown
Analyze content against type-specific checklists defined in `templates/issue-sections.json`:

1. Read `templates/issue-sections.json` (relative to the little-loops plugin directory)
2. For the issue's type (BUG/FEAT/ENH), check `type_sections.[TYPE]` for type-specific sections
3. Also check `common_sections` for universal required sections
4. For each section, use its `level` (required/conditional/nice-to-have) and `question` field

Present gaps as a table:

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| [section name] | [level] | [question from template] |
```

For quality checks (lines 100-115), replace with:

```markdown
#### Type-Specific Quality Checks

Read the `quality_checks.[TYPE]` array from `templates/issue-sections.json` for type-specific content quality standards.
```

#### Success Criteria
- [ ] Inline section tables removed from `refine_issue.md`
- [ ] Inline quality checks replaced with template reference
- [ ] Command references `templates/issue-sections.json`
- [ ] Behavior is equivalent (same sections, same questions, same levels)

---

### Phase 3: Update `capture_issue.md` to Reference Shared Template

#### Overview
Replace inline "full" and "minimal" templates with references to the shared template's `creation_variants`.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Replace the inline template definitions (lines 346-431) with directives to construct the issue from the shared template.

Replace with:

```markdown
4. **Create issue file:**

**Determine template style:**

```
IF QUICK_MODE is true:
  TEMPLATE_STYLE = "minimal"
ELSE IF config.issues.capture_template is set:
  TEMPLATE_STYLE = {{config.issues.capture_template}}
ELSE:
  TEMPLATE_STYLE = "full"
```

**Build issue from shared template:**

1. Read `templates/issue-sections.json` (relative to the little-loops plugin directory)
2. Use the `creation_variants.[TEMPLATE_STYLE]` to determine which sections to include
3. For each section in `include_common`, use `common_sections.[name].creation_template` as placeholder content
4. If `include_type_sections` is true, also include sections from `type_sections.[TYPE]` that have a `creation_template`
5. Always include YAML frontmatter with `discovered_date` and `discovered_by: capture_issue`
6. Write the assembled template to `{{config.issues.base_dir}}/[category]/[filename]`

The assembled file follows this structure:

```bash
cat > "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## [Section 1 from template]
[creation_template content]

## [Section 2 from template]
[creation_template content]

...

---

[Status footer from template]
EOF
```
```

#### Success Criteria
- [ ] Inline "full" and "minimal" templates removed from `capture_issue.md`
- [ ] Command references `templates/issue-sections.json` creation_variants
- [ ] Both template styles produce equivalent output to current behavior

---

### Phase 4: Update `ready_issue.md` to Reference Shared Template

#### Overview
Replace the inline "Required Sections" checklist with a reference to the shared template.

#### Changes Required

**File**: `commands/ready_issue.md`
**Changes**: Replace lines 114-119 (Required Sections checklist) with a template reference.

Replace with:

```markdown
#### Required Sections

Read `templates/issue-sections.json` (relative to the little-loops plugin directory) and check:
- All `common_sections` where `required: true` are present and non-empty
- For the issue's type (BUG/FEAT/ENH), all `type_sections.[TYPE]` sections where `level: "required"` are present and non-empty
- For BUG issues specifically, also verify "Steps to Reproduce" (required) and "Actual Behavior" (required) sections
```

Note: Lines 121-149 (Code References, Dependency Status, Metadata) are not section-structure checks and should remain unchanged.

#### Success Criteria
- [ ] Inline Required Sections checklist removed from `ready_issue.md`
- [ ] Command references `templates/issue-sections.json`
- [ ] Code References, Dependency Status, and Metadata checks unchanged

---

### Phase 5: Update `scan_codebase.md` to Reference Shared Template

#### Overview
Replace the inline issue creation template with a reference to the shared template.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Changes**: Replace the inline template (lines 195-253) with a directive to use the shared template for issue structure, keeping the scan-specific frontmatter and Location section.

Replace with:

```markdown
For each finding, create an issue file using the structure from `templates/issue-sections.json`:

1. Read `templates/issue-sections.json` (relative to the little-loops plugin directory)
2. Use `creation_variants.full` to determine which sections to include
3. For BUG issues, include `type_sections.BUG` sections (especially "Steps to Reproduce" and Location)
4. For ENH issues, include `type_sections.ENH` sections
5. Always include the scan-specific YAML frontmatter and Location section

The assembled file follows this structure:

```markdown
---
discovered_commit: [COMMIT_HASH]
discovered_branch: [BRANCH_NAME]
discovered_date: [SCAN_DATE]
discovered_by: scan_codebase
---

# [PREFIX]-[NUMBER]: [Title]

## Summary
[Clear description of the issue]

## Location
- **File**: `path/to/file.py`
- **Line(s)**: 42-45 (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function process_issue()` or `in class IssueManager` or `near string "unique marker"`
- **Permalink**: [View on GitHub](...)
- **Code**:
```[language]
# Relevant code snippet
```

[Remaining sections from template: Current Behavior, Expected Behavior, type-specific sections, Proposed Solution, Impact, Labels, Status]
```

**Note**: Only include Permalink if `PERMALINKS_AVAILABLE` is true.
```

#### Success Criteria
- [ ] Inline issue template trimmed in `scan_codebase.md`
- [ ] Command references `templates/issue-sections.json` for section structure
- [ ] Scan-specific sections (frontmatter, Location) preserved
- [ ] Section naming matches shared template (e.g., "Steps to Reproduce" not "Reproduction Steps")

---

## Testing Strategy

### Verification
- All existing tests pass: `python -m pytest scripts/tests/`
- Lint passes: `ruff check scripts/`
- Types pass: `python -m mypy scripts/little_loops/`
- No Python code changes needed — all changes are in `.md` and `.json` files

### Manual Verification
- Read `templates/issue-sections.json` and verify it covers all section definitions from all four commands
- Diff each modified command against git history to confirm no behavioral regression

## References

- Original issue: `.issues/enhancements/P3-ENH-271-shared-issue-template-for-section-checks.md`
- refine_issue sections: `commands/refine_issue.md:54-83`
- refine_issue quality checks: `commands/refine_issue.md:90-115`
- capture_issue templates: `commands/capture_issue.md:346-431`
- ready_issue checklist: `commands/ready_issue.md:114-119`
- scan_codebase template: `commands/scan_codebase.md:195-253`
- Config schema templates_dir: `config-schema.json:105-108`
- Precedent: ENH-269 shared function extraction in `hooks/scripts/lib/common.sh`
