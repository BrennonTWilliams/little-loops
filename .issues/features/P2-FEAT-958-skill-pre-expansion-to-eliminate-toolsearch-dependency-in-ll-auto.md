---
discovered_date: 2026-04-05
discovered_by: capture-issue
---

# FEAT-958: Skill pre-expansion to eliminate ToolSearch dependency in ll-auto

## Summary

When `ll-auto` spawns Claude subprocesses, it passes slash commands like `/ll:manage-issue bug implement BUG-001` as the `-p` prompt. To handle a slash command, Claude must invoke the `Skill` tool — but `Skill` is a **deferred tool** whose schema must first be fetched via `ToolSearch`. In subprocess contexts, `ToolSearch` intermittently fails, causing the entire ll-auto run to fail for that issue (hard blocker).

The fix: pre-expand skill/command Markdown content in Python — substituting `{{config.xxx}}` placeholders and the `$ARGUMENTS` marker — and pass the expanded content directly as the `-p` prompt. No `Skill` tool, no `ToolSearch`.

## Current Behavior

`ll-auto` passes slash commands (e.g., `/ll:manage-issue bug implement BUG-001`) as the `-p` prompt to Claude subprocesses. Claude must:
1. Recognise the slash command
2. Invoke the `Skill` deferred tool
3. First fetch `Skill`'s schema via `ToolSearch`

`ToolSearch` intermittently fails with:

> "I'm having trouble discovering tools through search. Let me try direct selections."

When this happens, `Skill` is never invoked and the entire subprocess run fails — a **hard blocker**.

## Expected Behavior

Python reads the skill/command Markdown file, substitutes `{{config.xxx}}` placeholders and the `$ARGUMENTS` marker, and passes the fully-expanded content directly as the `-p` prompt. The Claude subprocess starts executing the skill body immediately with no deferred-tool discovery required.

**Limitation**: Deferred tools within the skill's own execution (e.g., `Agent` in Phase 1.5 deep research, `Skill` in Phase 2.5 confidence check) still need ToolSearch. But those phases are optional/advisory, converting a **hard blocker → graceful degradation**.

## Motivation

`ll-auto` is the primary automation driver for issue processing. Every subprocess failure due to this intermittent ToolSearch bug halts work on that issue with no useful output. The fix unblocks the automation pipeline reliably without requiring any Claude-side changes.

## Proposed Solution

### New file: `scripts/little_loops/skill_expander.py`

Public API:

```python
def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None:
    """Pre-expand a skill or command into a self-contained prompt string.

    Returns expanded content, or None on any failure (caller falls back to slash command).
    """
```

Internal helpers:

- `_find_plugin_root()` — checks `CLAUDE_PLUGIN_ROOT` env var, falls back to `Path(__file__).parent.parent.parent`
- `_resolve_content_path(plugin_root, name)` — tries `skills/{name}/SKILL.md` then `commands/{name}.md`
- `_substitute_config(content, config)` — replaces `{{config.xxx}}` via `config.resolve_variable()`; leaves unresolvable placeholders as-is
- `_substitute_relative_refs(content, content_dir)` — converts `(templates.md)` → `(/abs/path/skills/manage-issue/templates.md)` for files that exist
- `_substitute_arguments(content, args)` — replaces `$ARGUMENTS` with the joined args string

**Reuses (no changes needed):**
- `scripts/little_loops/frontmatter.py:81` — `strip_frontmatter()`
- `scripts/little_loops/config/core.py:489` — `BRConfig.resolve_variable(var_path)`

### Modify: `scripts/little_loops/issue_manager.py`

**Fix `run_with_continuation` resume bug** (line ~133):

The current code `current_command = f"{initial_command} --resume"` breaks when `initial_command` is expanded skill content (hundreds of lines). Add `resume_command: str | None = None` parameter; use it for continuation rounds.

**Three call sites to update:**

1. Phase 1 ready-issue (~line 326) — expand `ready-issue` skill or fall back to `/ll:ready-issue {info.issue_id}`
2. Phase 1 retry with file path (~line 376) — same pattern with relative path
3. Phase 2 manage-issue (~line 541) — expand `manage-issue` skill; always pass `resume_command=_slash_cmd` for continuation rounds

## Integration Map

### Files to Modify

- `scripts/little_loops/skill_expander.py` — **new** module
- `scripts/little_loops/issue_manager.py` — add import, fix `run_with_continuation` signature, update 3 call sites
- `scripts/tests/test_skill_expander.py` — **new** test file

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issue_manager.py` imports `expand_skill` (new import)
- `run_with_continuation` callers inside `issue_manager.py` (all internal)

### Similar Patterns

- `scripts/little_loops/frontmatter.py` — `strip_frontmatter()` reused as-is
- `scripts/little_loops/config/core.py` — `BRConfig.resolve_variable()` reused as-is

### Tests

- `scripts/tests/test_skill_expander.py` — unit + integration tests (new)
- `scripts/tests/test_issue_manager.py` — regression check (no changes needed)
- `scripts/tests/test_subprocess_utils.py` — regression check (no changes needed)

### Documentation

- N/A — internal automation plumbing; no user-facing docs needed

### Configuration

- `CLAUDE_PLUGIN_ROOT` env var (optional override for plugin root detection)

## Implementation Steps

1. **Create `skill_expander.py`** with `expand_skill()` and all private helpers
2. **Add import** to `issue_manager.py`: `from little_loops.skill_expander import expand_skill`
3. **Fix `run_with_continuation`** resume bug: add `resume_command` parameter, use it at line ~203
4. **Update call site 1**: Phase 1 ready-issue (~line 326)
5. **Update call site 1b**: Phase 1 retry with file path (~line 376)
6. **Update call site 2**: Phase 2 manage-issue (~line 541) with `resume_command=_slash_cmd`
7. **Create `test_skill_expander.py`** with unit tests for all helpers and integration test against real `manage-issue` skill
8. **Verify**: run all test suites and smoke check (see Verification section below)

## Verification

```bash
# Unit tests
python -m pytest scripts/tests/test_skill_expander.py -v

# No regressions
python -m pytest scripts/tests/test_issue_manager.py scripts/tests/test_subprocess_utils.py -v

# All FSM tests
python -m pytest scripts/tests/ -k "fsm" -v

# Manual smoke check
python -c "
from pathlib import Path
from little_loops.config import BRConfig
from little_loops.skill_expander import expand_skill
config = BRConfig(Path('.'))
r = expand_skill('manage-issue', ['bug', 'implement', 'BUG-001'], config)
assert r and '{{config.' not in r and '\$ARGUMENTS' not in r and '(templates.md)' not in r
print('OK', len(r), 'chars')
"
```

## Out of Scope

- **`ll-parallel` worker pool** (`parallel/types.py`) also passes slash commands to Claude subprocesses — the same `expand_skill` fix applies but is deferred to a follow-up issue.
- **ToolSearch failures for `Agent` (Phase 1.5) and `Skill` (Phase 2.5)** within the skill's own execution remain; those phases are optional/advisory and can be skipped with `--quick`.

## API/Interface

```python
# skill_expander.py public API
def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None: ...

# run_with_continuation updated signature
def run_with_continuation(
    initial_command: str,
    logger: Logger,
    timeout: int = 3600,
    stream_output: bool = True,
    max_continuations: int = 3,
    repo_path: Path | None = None,
    idle_timeout: int = 0,
    resume_command: str | None = None,   # NEW: used for --resume rounds
) -> subprocess.CompletedProcess[str]: ...
```

## Impact

- **Priority**: P2 - Fixes a hard blocker in `ll-auto` subprocess invocations; automation pipeline unreliable without this
- **Effort**: Small/Medium - ~3 new files/modifications, well-scoped
- **Risk**: Low - falls back gracefully to slash command on any expansion failure; no behavioral change when expansion succeeds
- **Breaking Change**: No — `run_with_continuation` gets a new optional parameter with a safe default

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `automation`, `ll-auto`, `captured`

## Status

**Open** | Created: 2026-04-05 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f1dbb90-1979-4e86-8aa0-5606a0e91771.jsonl`
