# ENH-073: capture_issue Lightweight Template Option - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-073-capture-issue-lightweight-template-option.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `capture_issue` command creates issues with a comprehensive 8-section template (lines 305-357 in `commands/capture_issue.md`). The template includes: Summary, Context, Current Behavior, Expected Behavior, Proposed Solution, Impact, Labels, and Status.

### Key Discoveries
- Template is hardcoded in `commands/capture_issue.md:305-357`
- Config access pattern uses `{{config.issues.*}}` interpolation (`capture_issue.md:15-17`)
- The `issues` section of `config-schema.json:58-111` has `templates_dir` property but no template style config
- Pattern for enum config options found at `config-schema.json:336-342` (mode: quick/thorough)

## Desired End State

Users can choose between a full (current) or minimal template when capturing issues:

1. **Config option**: `config.issues.capture_template` with values "full" (default) or "minimal"
2. **Flag override**: `--quick` flag forces minimal template regardless of config

### Minimal Template
```markdown
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[Description]

## Context

[Source context]

---

**Priority**: [P0-P5] | **Created**: [YYYY-MM-DD]
```

### How to Verify
- Running `/ll:capture_issue "test bug"` uses full template by default
- Adding `capture_template: "minimal"` to ll-config.json uses minimal template
- Running `/ll:capture_issue "test bug" --quick` uses minimal template regardless of config

## What We're NOT Doing

- Not changing the ready_issue command - it can expand minimal templates later
- Not adding templates_dir functionality - that's a separate enhancement
- Not modifying the skill wrapper - it passes arguments through unchanged

## Solution Approach

Follow existing patterns from the codebase:
1. Add enum config option following the `mode` pattern from `config-schema.json:336-342`
2. Add flag parsing following the `init.md:24-35` pattern
3. Add conditional template following the `handoff.md:119-198` pattern

## Implementation Phases

### Phase 1: Add Config Schema Entry

#### Overview
Add `capture_template` option to the issues section of config-schema.json.

#### Changes Required

**File**: `config-schema.json`
**Changes**: Add `capture_template` property after `templates_dir` (line 109)

```json
"capture_template": {
  "type": "string",
  "enum": ["full", "minimal"],
  "description": "Default template style for captured issues (full includes all sections, minimal includes only Summary, Context, and footer)",
  "default": "full"
}
```

#### Success Criteria

**Automated Verification**:
- [ ] JSON is valid: `python -c "import json; json.load(open('config-schema.json'))"`
- [ ] Schema validates: `python -c "import jsonschema; jsonschema.Draft7Validator.check_schema(json.load(open('config-schema.json')))"`

---

### Phase 2: Update capture_issue.md Configuration Section

#### Overview
Document the new config option in the command's configuration section.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Add template config reference to lines 15-17

```markdown
## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Template style**: `{{config.issues.capture_template}}` (full or minimal)
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

---

### Phase 3: Add Flag Argument

#### Overview
Add `--quick` flag to command arguments.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Update arguments section (lines 1-7) and add flag parsing

Update frontmatter:
```yaml
---
description: Capture issues from conversation or natural language description
arguments:
  - name: input
    description: Natural language description of the issue (optional - analyzes conversation if omitted)
    required: false
  - name: flags
    description: Optional flags (--quick for minimal template)
    required: false
---
```

Add flag parsing after line 38:
```markdown
**Parse flags:**
```bash
FLAGS="${flags:-}"
QUICK_MODE=false
if [[ "$FLAGS" == *"--quick"* ]]; then QUICK_MODE=true; fi
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Frontmatter YAML is valid
- [ ] File is valid markdown

---

### Phase 4: Add Conditional Template Logic

#### Overview
Replace single template with conditional full/minimal templates.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Replace template section (lines 305-357) with conditional logic

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

**If TEMPLATE_STYLE is "minimal":**

```bash
cat > "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[Description extracted from input]

## Context

[How this issue was identified]

**Direct mode**: User description: "[original description]"

**Conversation mode**: Identified from conversation discussing: "[brief context]"

---

**Priority**: [P0-P5] | **Created**: [YYYY-MM-DD]
EOF
```

**If TEMPLATE_STYLE is "full" (default):**

```bash
cat > "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[Description extracted from input]

## Context

[How this issue was identified]

**Direct mode**: User description: "[original description]"

**Conversation mode**: Identified from conversation discussing: "[brief context]"

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Proposed Solution

[If mentioned in the description, otherwise:]
TBD - requires investigation

## Impact

- **Priority**: [P0-P5]
- **Effort**: TBD
- **Risk**: TBD

## Labels

`[type-label]`, `captured`

---

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
EOF
```
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown
- [ ] Both heredoc templates have matching EOF markers

---

### Phase 5: Update Examples Section

#### Overview
Add examples showing the --quick flag usage.

#### Changes Required

**File**: `commands/capture_issue.md`
**Changes**: Add quick flag examples to the Examples section (around line 473)

Add after existing examples:
```markdown
# Capture with minimal template (quick mode)
/ll:capture_issue "Quick note: cache is slow" --quick

# Analyze conversation and use minimal templates
/ll:capture_issue --quick
```

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

---

## Testing Strategy

### Manual Verification
1. Run `/ll:capture_issue "test bug"` - should create full template
2. Add `"capture_template": "minimal"` to `.claude/ll-config.json`
3. Run `/ll:capture_issue "test bug 2"` - should create minimal template
4. Run `/ll:capture_issue "test bug 3" --quick` - should create minimal template regardless of config
5. Remove config addition and verify default is full template

### Cleanup
- Delete any test issue files created during verification

## References

- Original issue: `.issues/enhancements/P4-ENH-073-capture-issue-lightweight-template-option.md`
- Config pattern: `config-schema.json:336-342` (mode enum)
- Flag pattern: `commands/init.md:24-35`
- Template pattern: `commands/handoff.md:119-198`
