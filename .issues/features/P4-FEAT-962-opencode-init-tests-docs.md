---
id: FEAT-962
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-05
discovered_by: issue-size-review
parent_issue: FEAT-769
---

# FEAT-962: OpenCode ll:init Support, Tests, and Docs

## Summary

Update `ll:init` to detect OpenCode and offer plugin registration, fix missing `.gitignore` entries, add integration tests for OpenCode config paths in hook scripts, and update architecture/contributing documentation.

## Parent Issue

Decomposed from FEAT-769: Add OpenCode Plugin Compatibility

## Current Behavior

- `skills/init/SKILL.md` has no OpenCode detection or plugin registration logic
- `.gitignore` block at `skills/init/SKILL.md:313-319` is missing `.claude/ll-precompact-state.json` and `.claude/ll-continue-prompt.md`
- No documentation covers OpenCode compatibility
- Hook integration tests only cover Claude Code config paths

## Expected Behavior

- `ll:init --opencode` detects OpenCode (via `opencode.json` or `opencode` in PATH) and offers to register `@ll/opencode-plugin` in `opencode.json`
- `ll:init` creates `.opencode/ll-config.json` when OpenCode is detected
- `.gitignore` block includes all missing entries (2 Claude Code + 6 OpenCode variants)
- `docs/ARCHITECTURE.md` has an OpenCode compatibility section
- `CONTRIBUTING.md` has OpenCode setup instructions
- Hook integration tests cover `.opencode/` config path

## Acceptance Criteria

- `skills/init/SKILL.md` has `--opencode` flag documentation and detection logic
- Detection checks for `opencode.json` in project root OR `opencode` binary in PATH
- Plugin registration adds `"plugin": ["@ll/opencode-plugin"]` to `opencode.json` (uses `"plugin"` singular key)
- `ll:init` creates `.opencode/ll-config.json` if absent (using same defaults as `.claude/ll-config.json`)
- `.gitignore` additions include: `.claude/ll-precompact-state.json`, `.claude/ll-continue-prompt.md` (currently missing), plus `.opencode/ll-context-state.json`, `.opencode/ll-sync-state.json`, `.opencode/ll-precompact-state.json`, `.opencode/ll-continue-prompt.md`, `.opencode/ll-context-state.json`, `.opencode/.ll-lock`
- `test_hooks_integration.py` has OpenCode config path fixture and tests
- `docs/ARCHITECTURE.md` documents the OpenCode compatibility layer
- `CONTRIBUTING.md` has OpenCode development setup section

## Proposed Solution

### `skills/init/SKILL.md` changes

Add `--opencode` flag to the init skill's argument parsing section. Detection logic:

```bash
# Detect OpenCode
OPENCODE_DETECTED=false
if [ -f "opencode.json" ] || command -v opencode &>/dev/null; then
    OPENCODE_DETECTED=true
fi
```

If detected (or `--opencode` flag passed):
1. Create `.opencode/ll-config.json` if absent (copy `.claude/` defaults)
2. Offer to add `"plugin": ["@ll/opencode-plugin"]` to `opencode.json`
3. Add `.opencode/` gitignore entries

**Fix missing gitignore entries** at lines 313-319. Currently absent:
- `.claude/ll-precompact-state.json` (written by `precompact-state.sh`)
- `.claude/ll-continue-prompt.md` (written by `context-monitor.sh`)

Add all 6 OpenCode variants:
- `.opencode/ll-context-state.json`
- `.opencode/ll-sync-state.json`
- `.opencode/ll-precompact-state.json`
- `.opencode/ll-continue-prompt.md`
- `.opencode/ll-context-state.json`
- `.opencode/.ll-lock`

### `test_hooks_integration.py`

Fixtures at lines 33,104 create `.claude/ll-config.json` inside `tmp_path` (used when invoking `context-monitor.sh` as subprocess). Add parallel `.opencode/` variant fixture:

```python
@pytest.fixture
def opencode_config_dir(tmp_path):
    opencode_dir = tmp_path / ".opencode"
    opencode_dir.mkdir()
    config = opencode_dir / "ll-config.json"
    config.write_text(DEFAULT_CONFIG_JSON)
    return tmp_path
```

Add tests that run hook scripts with `LL_STATE_DIR=".opencode"` set and verify they read from `.opencode/`.

### Documentation

- `docs/ARCHITECTURE.md` — add "OpenCode Compatibility" section covering: platform abstraction approach, event mapping table, `LL_STATE_DIR` mechanism, config path fallback chain
- `CONTRIBUTING.md` — add "OpenCode Development" subsection: how to test with OpenCode, Bun setup for plugin development, `opencode.json` registration

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — `--opencode` flag + detection + gitignore fix

### Files to Modify (Tests)
- `scripts/tests/test_hooks_integration.py` — OpenCode fixture + tests

### Files to Modify (Docs)
- `docs/ARCHITECTURE.md` — OpenCode compatibility section
- `CONTRIBUTING.md` — OpenCode setup instructions

## Impact

- **Priority**: P4 — Completion layer; makes the feature user-facing
- **Effort**: Small-Medium — `ll:init` addition is mechanical; docs are straightforward
- **Risk**: Low — All changes are additive
- **Breaking Change**: No

## Notes

This issue depends on FEAT-959, FEAT-960, and FEAT-961 being substantially complete (the init skill should reference working paths, and the docs should describe the actual implementation).

The missing `.gitignore` entries (`.claude/ll-precompact-state.json`, `.claude/ll-continue-prompt.md`) are a bug in the current Claude Code init path — fix them here regardless of OpenCode status.

## Session Log
- `/ll:issue-size-review` - 2026-04-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e591ecf6-7232-42fc-b4c4-903ec2858064.jsonl`

---

**Open** | Created: 2026-04-05 | Priority: P4
