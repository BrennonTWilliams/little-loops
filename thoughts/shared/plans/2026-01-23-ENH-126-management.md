# ENH-126: Pre-built Working Loop Templates - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-126-pre-built-working-loop-templates.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create_loop` wizard in `commands/create_loop.md` currently guides users through:
1. Paradigm selection (goal, invariants, convergence, imperative)
2. Paradigm-specific parameter gathering
3. Loop naming with auto-suggestions
4. YAML preview with FSM compilation preview
5. Validation via `ll-loop validate`
6. Optional test iteration via `ll-loop test`

### Key Discoveries
- The wizard at `commands/create_loop.md:27-52` presents 4 paradigm options without template option
- Pre-defined check/fix pairs exist at `commands/create_loop.md:223-228` for invariants paradigm
- Example configurations exist at `commands/create_loop.md:783-821` (quick-lint-fix, full-quality-gate, improve-coverage)
- The `templates/` directory already contains project-type JSON templates with `_meta` structure
- No loop template system currently exists

### Patterns to Follow
- Project templates use `_meta` block with `name`, `description`, `detect`, `tags` (from `templates/python-generic.json`)
- Configure command uses "More areas..." pagination pattern (from `commands/configure.md`)
- Init command maps friendly labels to actual commands by project type (from `commands/init.md`)

## Desired End State

The `/ll:create_loop` wizard will:
1. First ask "Template or custom?" as step 0
2. If template: present categorized template list and apply selected template
3. After template selection: allow customization of source directory and max iterations
4. Continue with existing preview/save/validate flow

### How to Verify
- Run `/ll:create_loop` and select template mode
- Verify templates are presented with clear descriptions
- Verify template selection populates correct YAML
- Verify customization step works
- Verify existing "custom" flow still works unchanged

## What We're NOT Doing

- Not creating separate template files in `templates/loops/` - templates will be embedded inline in the command
- Not supporting template detection/auto-selection based on project type
- Not adding template editing/management commands
- Not modifying the paradigm compilers or FSM logic

## Problem Analysis

Users often make mistakes in command syntax, evaluator selection, or transition logic when configuring loops from scratch. Pre-built templates provide known-working configurations that reduce friction and errors.

## Solution Approach

Embed loop templates directly in `commands/create_loop.md` as YAML blocks, organized by use case. Add a new Step 0 that asks template vs custom, and if template, presents the template selection and customization flow before joining the existing preview/save/validate flow at Step 4.

## Implementation Phases

### Phase 1: Add Template vs Custom Selection

#### Overview
Insert a new Step 0 before paradigm selection that asks users whether to start from a template or build custom.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add new Step 0 section after line 26 (after "## Workflow")

```yaml
### Step 0: Creation Mode

Use AskUserQuestion to determine creation mode:

```yaml
questions:
  - question: "How would you like to create your loop?"
    header: "Creation mode"
    multiSelect: false
    options:
      - label: "Start from template (Recommended)"
        description: "Choose a pre-built loop for common tasks"
      - label: "Build from paradigm"
        description: "Configure a new loop from scratch"
```

**If "Start from template"**: Continue to Step 0.1 (Template Selection)
**If "Build from paradigm"**: Skip to Step 1 (Paradigm Selection) - existing flow
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax valid (no markdown parsing errors)

**Manual Verification**:
- [ ] Running `/ll:create_loop` shows the new creation mode question first
- [ ] Selecting "Build from paradigm" proceeds to existing paradigm selection flow

---

### Phase 2: Add Template Selection and Customization

#### Overview
Add Step 0.1 for template selection with 6 pre-built templates, and Step 0.2 for customization.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add Step 0.1 and Step 0.2 sections after Step 0

```yaml
### Step 0.1: Template Selection

If "Start from template" was selected:

```yaml
questions:
  - question: "Which template would you like to use?"
    header: "Template"
    multiSelect: false
    options:
      - label: "Python quality (lint + types + format)"
        description: "ruff check/fix + mypy + ruff format until clean"
      - label: "JavaScript quality (lint + types)"
        description: "eslint + tsc until clean"
      - label: "Run tests until passing"
        description: "pytest/jest with auto-fix until green"
      - label: "Full quality gate (tests + types + lint)"
        description: "All checks must pass before completing"
```

**Template Definitions:**

#### Template: python-quality

```yaml
paradigm: invariants
name: "python-quality"
constraints:
  - name: "lint"
    check: "ruff check {{src_dir}}"
    fix: "ruff check --fix {{src_dir}}"
  - name: "types"
    check: "mypy {{src_dir}}"
    fix: "echo 'Fix type errors manually or use /ll:manage_issue bug fix'"
  - name: "format"
    check: "ruff format --check {{src_dir}}"
    fix: "ruff format {{src_dir}}"
maintain: false
max_iterations: {{max_iterations}}
```

#### Template: javascript-quality

```yaml
paradigm: invariants
name: "javascript-quality"
constraints:
  - name: "lint"
    check: "npx eslint {{src_dir}}"
    fix: "npx eslint --fix {{src_dir}}"
  - name: "types"
    check: "npx tsc --noEmit"
    fix: "echo 'Fix type errors manually'"
maintain: false
max_iterations: {{max_iterations}}
```

#### Template: tests-until-passing

```yaml
paradigm: goal
name: "tests-until-passing"
goal: "All tests pass"
tools:
  - "{{test_cmd}}"
  - "/ll:manage_issue bug fix"
max_iterations: {{max_iterations}}
```

#### Template: full-quality-gate

```yaml
paradigm: invariants
name: "full-quality-gate"
constraints:
  - name: "tests"
    check: "{{test_cmd}}"
    fix: "/ll:manage_issue bug fix"
  - name: "types"
    check: "{{type_cmd}}"
    fix: "/ll:manage_issue bug fix"
  - name: "lint"
    check: "{{lint_cmd}}"
    fix: "{{lint_fix_cmd}}"
maintain: false
max_iterations: {{max_iterations}}
```

### Step 0.2: Template Customization

After template selection, ask for customization:

```yaml
questions:
  - question: "What source directory should the loop check?"
    header: "Source dir"
    multiSelect: false
    options:
      - label: "src/ (Recommended)"
        description: "Standard source directory"
      - label: "."
        description: "Project root"
      - label: "lib/"
        description: "Library directory"
      - label: "Custom path"
        description: "Specify your own directory"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick fixes only"
      - label: "50"
        description: "For complex issues"
```

**Apply substitutions:**
- Replace `{{src_dir}}` with selected source directory
- Replace `{{max_iterations}}` with selected max iterations
- Replace `{{test_cmd}}` with `pytest` (Python) or `npm test` (JavaScript) based on template
- Replace `{{lint_cmd}}` with appropriate lint command for template
- Replace `{{type_cmd}}` with appropriate type check command for template
- Replace `{{lint_fix_cmd}}` with auto-fix command if available

**After customization**: Skip to Step 3 (Loop Name) with auto-suggested name from template.
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax valid

**Manual Verification**:
- [ ] Template selection presents 4 template options
- [ ] Selecting a template proceeds to customization
- [ ] Customization allows source dir and max iterations selection
- [ ] Template YAML is correctly populated with substituted values

---

### Phase 3: Update Step References and Flow

#### Overview
Update step numbering references and ensure the flow correctly routes template users to Step 3 (naming) while custom users continue through Step 1 (paradigm selection).

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**:
1. Update "Step 1" header to clarify it's for custom/paradigm mode
2. Add routing note after Step 0.2 to join at Step 3
3. Ensure Step 3 (naming) handles template-originated flows

Add after Step 0.2:

```markdown
**Flow after template customization:**
- The generated YAML and auto-suggested loop name are ready
- Continue directly to Step 4 (Preview and Confirm) with the template-populated configuration
- Skip Step 1 (Paradigm Selection), Step 2 (Paradigm-Specific Questions), and Step 3 (Loop Name) since template provides all configuration
```

Update Step 1 header:
```markdown
### Step 1: Paradigm Selection (Custom Mode Only)

If user selected "Build from paradigm" in Step 0, use this flow:
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Template flow skips paradigm selection and goes to preview
- [ ] Custom flow still follows original paradigm selection path

---

### Phase 4: Add Quick Reference Section

#### Overview
Update the Quick Reference section to include template selection guidance.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add template quick reference before "Paradigm Decision Tree"

```markdown
### Template Quick Reference

| Template | Paradigm | Best For |
|----------|----------|----------|
| Python quality | invariants | Python projects with ruff + mypy |
| JavaScript quality | invariants | JS/TS projects with eslint + tsc |
| Tests until passing | goal | Any project with test suite |
| Full quality gate | invariants | CI-like multi-check validation |

**When to use templates:**
- You want a working loop quickly
- Your use case matches a common pattern
- You're new to loop creation

**When to build custom:**
- You have unique check/fix commands
- You need convergence (metric-based) loops
- You need imperative (step sequence) loops
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax valid

**Manual Verification**:
- [ ] Quick reference section is readable and accurate

---

## Testing Strategy

### Manual Tests
1. Run `/ll:create_loop` and select "Start from template"
2. Select each template in turn and verify YAML generation
3. Verify customization (source dir, max iterations) applies correctly
4. Verify "Build from paradigm" still works as before
5. Verify preview shows correct FSM structure for templates
6. Verify validation passes for all templates
7. Verify test iteration works for template-created loops

### Integration Tests
- Existing test suite should continue passing (no Python changes)

## References

- Original issue: `.issues/enhancements/P3-ENH-126-pre-built-working-loop-templates.md`
- Create loop command: `commands/create_loop.md`
- Template pattern: `templates/python-generic.json:1-7` (_meta structure)
- Example configurations: `commands/create_loop.md:783-821`
