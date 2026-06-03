---
id: FEAT-1895
title: "Decisions Log \u2014 Sync to ll.local.md and Session-Start Integration"
type: FEAT
status: done
priority: P3
parent: FEAT-1892
discovered_date: 2026-06-03
completed_at: 2026-06-03 06:36:34+00:00
depends_on:
- FEAT-1891
- FEAT-1894
decision_needed: false
labels: null
confidence_score: 100
outcome_confidence: 85
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 24
---

# FEAT-1895: Decisions Log — Sync to ll.local.md and Session-Start Integration

## Summary

Create `scripts/little_loops/decisions_sync.py` containing `sync_to_local_md(path)` to write active `required` rules into `.ll/ll.local.md`, and extend `hooks/scripts/session-start.sh` (lines 76-83 in the Python heredoc) to capture `content` before passing it to `parse_frontmatter()` and emit the `## Active Rules` body via stderr before `sys.exit(0)`. Add `TestSyncToLocalMd` class to `scripts/tests/test_decisions.py`. Can run in parallel with FEAT-1896 once FEAT-1894 is merged.

## Use Case

As a developer using `ll-issues decisions sync`, I want active required decision rules to be synced into `.ll/ll.local.md` automatically so they are surfaced at session start without manually consulting the decisions log.

## Current Behavior

`decisions_sync.py` does not exist. `ll-issues decisions sync` returns exit code 1 with an ImportError stub message (`"sync not yet available (requires FEAT-1895)"`). The session-start hook does not emit `## Active Rules` body content from `ll.local.md` to stderr.

## Expected Behavior

`decisions_sync.py` exists with `sync_to_local_md(path)`. `ll-issues decisions sync` returns exit code 0 and writes the `## Active Rules` section into `.ll/ll.local.md` containing only active required rules. The session-start hook emits the `## Active Rules` body via stderr before `sys.exit(0)`.

## Impact

Enables the decisions log sync workflow and surfaces active project rules automatically at session start, ensuring developers are reminded of required decisions without manually checking the decisions log.

## Parent Issue

Decomposed from FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Integration Map

### Files to Create
- `scripts/little_loops/decisions_sync.py` — new module containing `sync_to_local_md(path: Path | None = None)`; the existing CLI stub at `scripts/little_loops/cli/issues/decisions.py:370` already imports from `little_loops.decisions_sync` and calls `sync_to_local_md(path=path)`

### Files to Modify
- `hooks/scripts/session-start.sh` — extend the Python heredoc at lines 76-83: change `local_overrides = parse_frontmatter(local_file.read_text())` to capture `content = local_file.read_text()` first, then call `parse_frontmatter(content)`, and before `sys.exit(0)` at line 83 emit the body via stderr (see Proposed Solution § session-start.sh)
- `scripts/tests/test_decisions.py` — add `TestSyncToLocalMd` class following `TestAppendSessionLogEntry` structure in `test_session_log.py:57`
- `scripts/tests/test_hook_session_start.py` (conditional) — if Step 5's body-output logic is extended to the Python `session_start.handle()`, update `TestSessionStartLocalOverrides` (lines 115-165) to separate body text from JSON stdout before calling `json.loads()`

### Dependent Files (Callers / Importers)
- `scripts/little_loops/cli/issues/decisions.py:368-376` — `_cmd_sync(path)` calls `sync_to_local_md(path=path)` where `path = Path(config.project_root) / config.decisions.log_path` (i.e., the decisions YAML path, not project root — match the signature accordingly)

### Similar Patterns (Key Anchors)
- `scripts/little_loops/session_log.py:append_session_log_entry()` lines 119-134 — `rfind`/splice section insert-or-create pattern for `sync_to_local_md`
- `scripts/little_loops/hooks/session_start.py:_parse_frontmatter()` lines 50-71 — canonical `content.split("---", 2)` body extraction idiom (body is `parts[2]` but currently discarded)
- `scripts/little_loops/decisions.py:list_entries()` and `resolve_active()` — CRUD functions to call; both already exist; `list_entries` internally calls `load_decisions` so no separate call is needed
- `scripts/little_loops/file_utils.py:atomic_write()` — already imported in `decisions.py`; import it in `decisions_sync.py` the same way
- `scripts/tests/test_session_log.py:TestAppendSessionLogEntry` (line 57) — structural model for `TestSyncToLocalMd`; uses `tmp_path`, tests create/update/atomicity paths

### CRUD Layer (from FEAT-1891)
- `load_decisions(path=None) -> list[AnyEntry]` — returns `[]` if file absent; called internally by `list_entries` (no need to call both)
- `list_entries(path, *, type)` — filter by `type="rule"` to get `RuleEntry` instances
- `resolve_active(entries)` — builds superseded ID set; returns active entries only

### Tests
- `scripts/tests/test_decisions.py` — will receive new `TestSyncToLocalMd` class
- `scripts/tests/test_session_log.py` — `TestAppendSessionLogEntry` at line 57; structural model for new tests
- `scripts/tests/test_hook_session_start.py` — `TestSessionStartLocalOverrides` at lines 115-165; conditional update (Step 23)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_decisions.py` — `TestDecisionsCLISync.test_sync_stub` (line 524) asserts `result == 1` (ImportError stub path); **will break** once `decisions_sync.py` exists — must flip to `result == 0` with positive assertion that `ll.local.md` is written

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `## Module Overview` table: add `little_loops.decisions_sync` row after `little_loops.decisions` row
- `docs/reference/CLI.md` — `#### ll-issues decisions` table: remove `(stub; see FEAT-1895)` qualifier from `sync` row once implemented
- `docs/ARCHITECTURE.md` — `scripts/little_loops/` file tree: add `decisions_sync.py` entry after `decisions.py` line
- `.claude/CLAUDE.md` — `### Local Settings Override` section: note that `## Active Rules` in `ll.local.md` body is machine-written by `sync_to_local_md`

## Proposed Solution

### decisions_sync.py — New Module

Create `scripts/little_loops/decisions_sync.py`:

```python
"""Sync decisions log active rules to .ll/ll.local.md."""

from __future__ import annotations

from pathlib import Path

from little_loops.decisions import _DEFAULT_LOG_PATH, list_entries, resolve_active
from little_loops.file_utils import atomic_write


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path.cwd() / _DEFAULT_LOG_PATH


def sync_to_local_md(path: Path | None = None) -> None:
    """Write active required rules to ## Active Rules in ll.local.md.

    `path` is the decisions YAML path (e.g. .ll/decisions.yaml).
    ll.local.md is resolved as path.parent / "ll.local.md".
    """
    decisions_path = _resolve_path(path)
    ll_local_path = decisions_path.parent / "ll.local.md"

    rules = [
        e for e in list_entries(decisions_path, type="rule")
        if getattr(e, "enforcement", None) == "required"
    ]
    active_rules = resolve_active(rules)

    rules_block = "\n".join(f"- {r.rule}" for r in active_rules)
    section = f"## Active Rules\n\n{rules_block}\n"

    content = ll_local_path.read_text(encoding="utf-8") if ll_local_path.exists() else ""
    if "## Active Rules" in content:
        idx = content.rfind("## Active Rules\n")
        end = content.find("\n##", idx + 1)
        content = content[:idx] + section + (content[end:] if end != -1 else "")
    else:
        content += f"\n\n{section}"
    atomic_write(ll_local_path, content)
```

**Note on signature**: `_cmd_sync` in `cli/issues/decisions.py:368` calls `sync_to_local_md(path=path)` where `path` is the decisions YAML path (`Path(config.project_root) / config.decisions.log_path`). The function derives `ll_local_path` as `path.parent / "ll.local.md"` — this works because both files live under `.ll/`. Do NOT change the `_cmd_sync` calling convention.

**Note on redundant call**: Do NOT call `load_decisions()` separately before `list_entries()`. `list_entries()` calls `load_decisions()` internally. The earlier draft had a dead `entries = load_decisions(decisions_path)` assignment that should not appear.

### session-start.sh Body Emission (Step 5)

Extend `hooks/scripts/session-start.sh` in the `merge_local_config()` Python heredoc. Current lines 76-83:

```python
# CURRENT (lines 76-83)
local_file = Path(".ll/ll.local.md")
if local_file.exists():
    local_overrides = parse_frontmatter(local_file.read_text())
    if local_overrides:
        merged = deep_merge(base_config, local_overrides)
        print("[little-loops] Config loaded:", str(config_file), file=sys.stderr)
        print("[little-loops] Local overrides applied from:", str(local_file), file=sys.stderr)
        print(json.dumps(merged, indent=2))
        sys.exit(0)
```

Replace with (capture `content` variable first, then extract body before `sys.exit(0)`):

```python
# UPDATED
local_file = Path(".ll/ll.local.md")
if local_file.exists():
    content = local_file.read_text()
    local_overrides = parse_frontmatter(content)
    if local_overrides:
        merged = deep_merge(base_config, local_overrides)
        print("[little-loops] Config loaded:", str(config_file), file=sys.stderr)
        print("[little-loops] Local overrides applied from:", str(local_file), file=sys.stderr)
        print(json.dumps(merged, indent=2))
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else ""
        if body:
            print(f"\n{body}", file=sys.stderr)
        sys.exit(0)
```

Emit to `stderr` to keep `stdout` clean for the JSON config merge output (same convention as all existing feedback lines in this heredoc). The body extraction follows the same `content.split("---", 2)` idiom used in `session_start.py:_parse_frontmatter()`.

> **Scope boundary**: Apply after FEAT-1112 and FEAT-1263 have merged; verify hook's exit-code behavior is additive and does not conflict with FEAT-1112's ingestion wiring.

### Tests (Step 19)

Add `TestSyncToLocalMd` to `scripts/tests/test_decisions.py` following `TestAppendSessionLogEntry` structure. Import `sync_to_local_md` from `little_loops.decisions_sync` (not `little_loops.decisions`). Use `tmp_path` fixture (same as `TestAppendSessionLogEntry`) and a `decisions_path` fixture pointing to `tmp_path / ".ll" / "decisions.yaml"`.

- `test_creates_section` — creates `## Active Rules` when ll.local.md has no such section
- `test_replaces_existing_section` — replaces existing `## Active Rules` content
- `test_filters_advisory_rules` — advisory rules are excluded (only `required` appear)
- `test_excludes_superseded_rules` — superseded rules are excluded via `resolve_active()`
- `test_uses_atomic_write` — patch `os.replace` and assert called exactly once targeting `ll.local.md`

**Step 23 (Conditional)**: If body-output logic is extended to the Python `session_start.handle()` beyond the shell script, update `scripts/tests/test_hook_session_start.py:TestSessionStartLocalOverrides` (lines 124-152) to separate body text from JSON stdout before calling `json.loads()`. Skip if Python handler remains unchanged.

## Acceptance Criteria

- [ ] `scripts/little_loops/decisions_sync.py` created with `sync_to_local_md(path: Path | None = None)`
- [ ] `sync_to_local_md` called correctly by `_cmd_sync` in `cli/issues/decisions.py:368` without modification
- [ ] `sync` writes active `required` rules to `## Active Rules` in `.ll/ll.local.md`
- [ ] Advisory and superseded rules are excluded from the sync output
- [ ] `hooks/scripts/session-start.sh` heredoc captures `content` variable and emits `## Active Rules` body via stderr before `sys.exit(0)`
- [ ] `TestSyncToLocalMd` class added to `test_decisions.py` covering all 5 scenarios, importing from `little_loops.decisions_sync`
- [ ] Step 23 conditional test update addressed (or documented as skipped with reason)

## Implementation Steps (Wiring Phase)

_Added by `/ll:wire-issue`:_

These touchpoints were identified by wiring analysis and must be included in the implementation:

1. Update `scripts/tests/test_cli_decisions.py` — flip `TestDecisionsCLISync.test_sync_stub` from stub-failure assertion (`result == 1`, `"FEAT-1895" in stderr`) to success assertion (`result == 0`); assert `ll.local.md` was written with active rules
2. Update `docs/reference/API.md` — add `little_loops.decisions_sync` row to `## Module Overview` table after `little_loops.decisions` row
3. Update `docs/reference/CLI.md` — remove `(stub; see FEAT-1895)` from `sync` row in `#### ll-issues decisions` section
4. Update `docs/ARCHITECTURE.md` — add `decisions_sync.py` line after `decisions.py` in `scripts/little_loops/` file tree
5. Update `.claude/CLAUDE.md` — add note to `### Local Settings Override` section: `## Active Rules` body section is machine-written by `sync_to_local_md`

## Session Log
- `/ll:ready-issue` - 2026-06-03T06:30:09 - `31e6af08-e74a-4142-89b8-3944b9306863.jsonl`
- `/ll:wire-issue` - 2026-06-03T06:23:34 - `60011e24-009d-4340-b6bd-7789943993bb.jsonl`
- `/ll:refine-issue` - 2026-06-03T06:18:35 - `ec82f1df-d177-4d0f-a7ae-753dd56e03ee.jsonl`
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `5f914107-0943-49b0-99a7-e92d954a4bd1.jsonl`
