# ENH-896: Migrate ll Runtime Files from `.claude/` to `.ll/`

## Plan Summary

Migrate all `.claude/ll-*` path references to `.ll/` across the entire codebase. This is a mechanical find-replace with ~80 files affected. No behavioral changes — only path constants and documentation references change.

## Key Decisions

1. **Out of scope**: `.claude/settings.local.json`, `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/workflow-analysis/` — these are Claude Code core files, not ll runtime files
2. **No backward compat**: Per issue scope, no fallback/shim for old paths
3. **`common.sh` creates `.ll/`**: Add `mkdir -p .ll` guard so hooks work on fresh clones
4. **`ll_resolve_config()` fallback**: Keep the root-level `ll-config.json` fallback, change primary from `.claude/ll-config.json` to `.ll/ll-config.json`
5. **`.gitignore`**: Runtime state files ignored, `ll-config.json` tracked at `.ll/ll-config.json`

## Implementation Phases

### Phase 0: Tests (Red) — TDD
Update test assertions to expect `.ll/` paths. Run tests — they should FAIL (Red).

Files:
- `scripts/tests/test_subprocess_utils.py` — CONTINUATION_PROMPT_PATH assertion + fixture
- `scripts/tests/test_hooks_integration.py` — config path assertion
- `scripts/tests/test_config.py` — state_file assertion
- `scripts/tests/test_merge_coordinator.py` — fixture directory

### Phase 1: Python Source (Core Runtime)
4 files with path constants/defaults:

- `scripts/little_loops/config/core.py:75` — `CONFIG_DIR = ".claude"` → `".ll"`
- `scripts/little_loops/subprocess_utils.py:32` — `CONTINUATION_PROMPT_PATH` path
- `scripts/little_loops/config/features.py:213,226` — `state_file` defaults
- `scripts/little_loops/config/__init__.py:4` — docstring

### Phase 2: Hook Scripts (Core Runtime)
5 files:

- `hooks/scripts/lib/common.sh` — `ll_resolve_config()` + add `mkdir -p .ll`
- `hooks/scripts/session-start.sh` — CONFIG_FILE, LOCAL_FILE, inline Python, goals default
- `hooks/scripts/session-cleanup.sh` — lock file, state file, config file
- `hooks/scripts/context-monitor.sh` — STATE_FILE default, precompact, handoff, continue prompt
- `hooks/scripts/precompact-state.sh` — STATE_DIR, CONTINUE_PROMPT

### Phase 3: YAML Loop Files
7 files — all have `pathlib.Path('.claude/ll-config.json')` inline Python:

- `fix-quality-and-tests.yaml`, `evaluation-quality.yaml`, `rl-coding-agent.yaml`
- `dead-code-cleanup.yaml`, `harness-single-shot.yaml`, `harness-multi-item.yaml`
- `context-health-monitor.yaml` (also `.claude/ll-context-state.json`)

### Phase 4: Config & Settings
- `config-schema.json` — 3 defaults (lines 502, 582, 795)
- `.gitignore` — 5 patterns
- `.claude/settings.local.json` — 1 permission entry

### Phase 5: Skills, Commands, Agents, Prompts (~40 files)
Mechanical replacement of `.claude/ll-` with `.ll/` in instruction text.

### Phase 6: Documentation (~15 files)
Same mechanical replacement across docs/, README.md, CONTRIBUTING.md, .claude/CLAUDE.md.

### Phase 7: CHANGELOG
Add migration note for existing users.

## Success Criteria
- [ ] `python -m pytest scripts/tests/ -v` — all pass
- [ ] `ruff check scripts/` — clean
- [ ] `python -m mypy scripts/little_loops/` — clean
- [ ] `grep -r "\.claude/ll-" . --include="*.py" --include="*.sh" --include="*.yaml"` — 0 results in source
- [ ] `grep -r "\.claude/ll-" . --include="*.md" --include="*.json"` — 0 results (excluding completed issues, plans, .issues/)
