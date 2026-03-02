# ENH-521: INDEX.md completeness gap — unlisted documentation files

## Summary

Add all missing documentation files to `docs/INDEX.md` to match its "Complete reference" claim.

## Research Findings

**Currently listed**: ~20 unique file references across 4 sections (Quick Start, User Documentation, Developer Documentation, Advanced Topics)
**Total docs files**: 37 markdown files across 7 directories
**Missing**: 17 files (12 claude-code/, 3 demo/, 2 research/)

## Implementation Plan

### Phase 1: Add Claude Code Reference section

Add a new "Claude Code Reference" section between "Advanced Topics" and the footer. This is the largest gap — 12 files in `claude-code/` with zero coverage.

Entries:
- Automate Workflows with Hooks
- Checkpointing
- CLI Programmatic Usage
- CLI Reference
- Create Plugins
- Custom Subagents
- Hooks Reference
- Manage Claude's Memory
- Plugins Reference
- Orchestrate Agent Teams
- Settings
- Skills

### Phase 2: Add missing entries to existing sections

- Add `docs/demo/README.md`, `docs/demo/modules.md`, `docs/demo/scenarios.md` to Advanced Topics alongside existing demo entry
- Add `docs/research/LCM-Lossless-Context-Management.md` and `docs/research/LCM-Integration-Brainstorm.md` to Advanced Topics alongside existing research entries

## Success Criteria

- [ ] All 37 docs files are referenced in INDEX.md
- [ ] Format matches existing pattern: `- [Title](path) - Description`
- [ ] No broken links
- [ ] Lint passes
