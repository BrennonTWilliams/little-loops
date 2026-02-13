# ENH-400: Migrate 8 oversized commands to skill directories - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-400-migrate-oversized-commands-to-skill-directories.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

8 commands in `commands/` exceed the recommended 500-line limit. Each is a single `.md` file. The plugin manifest (`plugin.json`) auto-discovers commands from `./commands` and skills from `./skills`. Existing skills are directories with a `SKILL.md` entrypoint. No existing skills use supporting files yet.

### Key Discoveries
- Plugin manifest uses directory-based auto-discovery (`plugin.json:19-20`); no per-file registration needed
- Commands and skills share the same `/ll:` invocation prefix - migration is transparent
- Existing `loop-suggester` has both command + skill (separate files, different content); this is a valid pattern but for our migration, the command is fully replaced by the skill
- Frontmatter fields (`description`, `allowed-tools`, `arguments`) work identically in skills
- `docs/claude-code/skills.md:225-232` shows the supporting file reference pattern: markdown links like `[reference.md](reference.md)`
- `help.md` references commands by `/ll:` name - no changes needed since invocation names stay the same

## Desired End State

Each oversized command is a skill directory with:
- `SKILL.md` (~300-500 lines) containing core logic and workflow
- Supporting files containing extracted templates, reference tables, examples, and configuration blocks
- Old command file deleted from `commands/`

### How to Verify
- Each `SKILL.md` is under 500 lines
- Each skill is invocable via `/ll:skill-name`
- `ruff check scripts/` passes (no Python changes, but sanity check)
- No broken references in `help.md` or `CLAUDE.md`

## What We're NOT Doing

- Not rewriting command logic or changing behavior
- Not modifying `plugin.json` (auto-discovery handles it)
- Not updating `help.md` (invocation names unchanged)
- Not migrating commands already under 500 lines
- Not creating tests (markdown files aren't Python-testable)

## Solution Approach

For each command, analyze its content to identify extractable sections (templates, reference tables, configuration blocks, examples). Move core workflow to `SKILL.md` and extract reference content to supporting files. The `SKILL.md` references supporting files using markdown links per the documented pattern.

### Naming Convention
- Directory names use kebab-case matching the command name with underscores replaced by hyphens
- e.g., `commands/create_loop.md` → `skills/create-loop/SKILL.md`

## Implementation Phases

### Phase 1: create_loop.md (1,249 lines → ~3-4 files)

**Extract to supporting files:**
- `templates.md`: Template definitions and customization (lines ~48-200) - pre-built paradigm templates
- `paradigms.md`: Paradigm-specific questions, YAML examples, and FSM compilation reference (lines ~202-700+)
- `reference.md`: Quick reference tables, paradigm decision tree, common configurations, advanced state config (lines ~1059-1225)

**SKILL.md keeps:** Frontmatter, intro, Step 0 (creation mode), Step 3-5 core workflow, save/validate logic, examples, integration.

**Directory:** `skills/create-loop/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/create_loop.md` deleted

---

### Phase 2: init.md (1,148 lines → ~2-3 files)

**Extract to supporting files:**
- `templates.md`: Project type presets and configuration templates (lines ~74-620) - Python, Node.js, Go, Rust, Java, .NET, General configs
- `interactive.md`: Interactive mode question flows and document discovery (lines ~621-930)

**SKILL.md keeps:** Frontmatter, arguments, process overview, steps 1-3 (flags, check existing, detect type), step 4 (generate config - with Read references to templates), summary/confirm/write/gitignore/completion, examples.

**Directory:** `skills/init/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/init.md` deleted

---

### Phase 3: configure.md (1,071 lines → ~2-3 files)

**Extract to supporting files:**
- `areas.md`: All area-specific configuration sections (lines ~345-975) - project, issues, parallel, automation, documents, continuation, context, prompt, scan, sync areas with their current values and question rounds

**SKILL.md keeps:** Frontmatter, arguments, process flow, area mapping, modes (--list, --show, --reset), interactive flow structure, step 3-4 (show changes, update config), examples, integration.

**Directory:** `skills/configure/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/configure.md` deleted

---

### Phase 4: manage_issue.md (754 lines → ~2 files)

**Extract to supporting files:**
- `templates.md`: Plan template, final report template, handoff template, resolution section template (lines ~209-320, 388-420, 582-700)

**SKILL.md keeps:** Frontmatter, arguments, configuration, directory structure, all phase logic (1-5), implementation guidelines, examples.

**Directory:** `skills/manage-issue/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/manage_issue.md` deleted

---

### Phase 5: format_issue.md (718 lines → ~2 files)

**Extract to supporting files:**
- `templates.md`: Template v2.0 section definitions, section inference examples, output format templates (lines ~158-340, 414-660)

**SKILL.md keeps:** Frontmatter, arguments, process overview, parse flags, locate issue, analyze content, identify gaps, content quality analysis, interactive refinement, update logic, finalize, examples, integration.

**Directory:** `skills/format-issue/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/format_issue.md` deleted

---

### Phase 6: audit_claude_config.md (635 lines → ~2 files)

**Extract to supporting files:**
- `report-template.md`: Report format template, wave output formats, fix suggestion formats (lines ~453-600)

**SKILL.md keeps:** Frontmatter, arguments, configuration files list, audit scopes, flags, process (phases 0-6), examples, related commands.

**Directory:** `skills/audit-claude-config/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/audit_claude_config.md` deleted

---

### Phase 7: capture_issue.md (620 lines → ~2 files)

**Extract to supporting files:**
- `templates.md`: Issue file template, duplicate detection prompts, similar issue handling flows, reopen logic (lines ~370-540)

**SKILL.md keeps:** Frontmatter, arguments, configuration, process phases 1-5, examples, integration.

**Directory:** `skills/capture-issue/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/capture_issue.md` deleted

---

### Phase 8: audit_docs.md (513 lines → ~2 files)

**Extract to supporting files:**
- `templates.md`: Issue template for doc issues, report format, auto-fixable findings format (lines ~263-470)

**SKILL.md keeps:** Frontmatter, arguments, configuration, process (find docs, audit, test code), direct fix option, issue management, reopen logic, user approval, execute, examples, integration.

**Directory:** `skills/audit-docs/`

#### Success Criteria
- [ ] `SKILL.md` under 500 lines
- [ ] All supporting files created
- [ ] `commands/audit_docs.md` deleted

---

### Phase 9: Final Cleanup

- Verify all 8 old command files are deleted
- Verify no broken references in `help.md` or `CLAUDE.md`
- Run lint/type checks as sanity check

#### Success Criteria
- [ ] All 8 skill directories created with SKILL.md under 500 lines
- [ ] All 8 old command files deleted
- [ ] `ruff check scripts/` passes
- [ ] `python -m mypy scripts/little_loops/` passes

## Testing Strategy

### Manual Verification
- Each skill should be invocable via `/ll:skill-name`
- Supporting files should be loadable via Read tool references

## References

- Original issue: `.issues/enhancements/P3-ENH-400-migrate-oversized-commands-to-skill-directories.md`
- Skill docs pattern: `docs/claude-code/skills.md:212-234`
- Plugin manifest: `.claude-plugin/plugin.json:19-20`
- Existing skill example: `skills/confidence-check/SKILL.md`
