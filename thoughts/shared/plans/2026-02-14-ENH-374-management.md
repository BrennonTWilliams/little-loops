# ENH-374: Add missing agents declaration to plugin.json

**Issue**: `.claude-plugin/plugin.json` declares `commands` and `skills` but omits `agents` — creating an inconsistency where some components are explicitly declared while others rely on auto-discovery.

**Date**: 2026-02-14
**Action**: improve

## Research Findings

### Schema Compatibility
- The Claude Code plugin.json schema **does** support `agents` as a valid key
- `agents` requires **explicit file paths** (array of individual .md files), NOT directory paths
- `hooks` should **NOT** be added — Claude Code v2.1+ auto-discovers `hooks/hooks.json` and adding it explicitly causes duplicate file errors

### Current State
- `plugin.json` declares: `commands`, `skills`
- 8 agent files exist in `agents/` (auto-discovered)
- 6 hooks in `hooks/hooks.json` (auto-discovered)

### Design Decision
**Add `agents` only. Do NOT add `hooks`.**

Rationale:
- Adding `agents` makes the manifest more explicit without breaking auto-discovery
- Adding `hooks` would cause duplicate file errors per community experience
- This is a pragmatic middle ground: declare what we safely can, leave `hooks` to auto-discovery

## Implementation Plan

### Phase 1: Update plugin.json
- [ ] Add `"agents"` key with explicit file paths for all 8 agents
- [ ] Preserve existing structure and formatting

**Target state:**
```json
{
  "name": "ll",
  "version": "1.12.2",
  "description": "...",
  "author": { ... },
  "repository": "...",
  "license": "MIT",
  "homepage": "...",
  "keywords": [ ... ],
  "commands": ["./commands"],
  "skills": ["./skills"],
  "agents": [
    "./agents/codebase-analyzer.md",
    "./agents/codebase-locator.md",
    "./agents/codebase-pattern-finder.md",
    "./agents/consistency-checker.md",
    "./agents/plugin-config-auditor.md",
    "./agents/prompt-optimizer.md",
    "./agents/web-search-researcher.md",
    "./agents/workflow-pattern-analyzer.md"
  ]
}
```

### Phase 2: Update issue file
- [ ] Add note about hooks exclusion rationale
- [ ] Document that only `agents` was added (not `hooks`)

### Phase 3: Verify
- [ ] Run tests
- [ ] Run lint
- [ ] Run type check

## Success Criteria
- [x] `agents` key added to plugin.json with all 8 agent file paths
- [ ] All agent paths resolve to existing files
- [ ] Plugin loads correctly (no validation errors)
- [ ] Tests pass
- [ ] Lint passes

## Risks & Mitigations
- **Risk**: Agent paths must be individual files, not directories
  - **Mitigation**: Enumerate all 8 files explicitly
- **Risk**: `hooks` addition would cause duplicate errors
  - **Mitigation**: Exclude `hooks` from declaration, document rationale in issue resolution
