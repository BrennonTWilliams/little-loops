---
id: FEAT-1895
title: "Decisions Log — Sync to ll.local.md and Session-Start Integration"
type: FEAT
priority: P3
parent: FEAT-1892
discovered_date: 2026-06-03
depends_on:
- FEAT-1891
- FEAT-1894
decision_needed: false
---

# FEAT-1895: Decisions Log — Sync to ll.local.md and Session-Start Integration

## Summary

Implement `sync_to_local_md(project_root: Path)` in `decisions.py` to write active `required` rules into `.ll/ll.local.md`, and extend `hooks/scripts/session-start.sh` to emit the `## Active Rules` body at session start. Add `TestSyncToLocalMd` class to `test_decisions.py`. Can run in parallel with FEAT-1896 once FEAT-1894 is merged.

## Parent Issue

Decomposed from FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Integration Map

### Files to Modify
- `scripts/little_loops/decisions.py` — add `sync_to_local_md(project_root: Path)` function using `append_session_log_entry()` insert-or-create pattern
- `hooks/scripts/session-start.sh` — extend `merge_local_config()` Python heredoc to extract `parts = content.split("---", 2)` body and emit after frontmatter merge (after line 97)
- `scripts/tests/test_decisions.py` — add `TestSyncToLocalMd` class following `TestAppendSessionLogEntry` structure in `test_session_log.py:57`
- `scripts/tests/test_hook_session_start.py` (conditional) — if Step 5's body-output logic is extended to the Python `session_start.handle()`, update `TestSessionStartLocalOverrides` (lines 124-152) to separate body text from JSON stdout before calling `json.loads()`

### Similar Patterns (Key Anchors)
- `scripts/little_loops/session_log.py:append_session_log_entry()` lines 119-134 — `rfind`/splice section insert-or-create pattern for `sync_to_local_md`
- `scripts/little_loops/hooks/session_start.py:handle()` lines 98-109 — `ll.local.md` read with `split("---", 2)` body extraction
- `scripts/tests/test_session_log.py:TestAppendSessionLogEntry` (line 57) — structural model for `TestSyncToLocalMd`

### CRUD Layer (from FEAT-1891)
- `load_decisions(path=None) -> list[AnyEntry]` — returns `[]` if file absent
- `list_entries(path, *, type)` — filter by `type="rule"` to get rules
- `resolve_active(entries)` — builds superseded ID set; returns active entries

## Proposed Solution

### sync_to_local_md Implementation (Step 5)

Implement in `scripts/little_loops/decisions.py`:

```python
def sync_to_local_md(project_root: Path) -> None:
    """Write active required rules to ## Active Rules in ll.local.md."""
    decisions_path = project_root / ".ll" / "decisions.yaml"
    ll_local_path = project_root / ".ll" / "ll.local.md"
    
    entries = load_decisions(decisions_path)
    rules = [e for e in list_entries(decisions_path, type="rule") 
             if getattr(e, "enforcement", None) == "required"]
    active_rules = resolve_active(rules)
    
    rules_block = "\n".join(f"- {r.rule}" for r in active_rules)
    section = f"## Active Rules\n\n{rules_block}\n"
    
    content = ll_local_path.read_text() if ll_local_path.exists() else ""
    if "## Active Rules" in content:
        idx = content.rfind("## Active Rules\n")
        end = content.find("\n##", idx + 1)
        content = content[:idx] + section + (content[end:] if end != -1 else "")
    else:
        content += f"\n\n{section}"
    atomic_write(ll_local_path, content)
```

### session-start.sh Body Emission (Step 5)

Extend `hooks/scripts/session-start.sh` after line 97 inside the `merge_local_config()` Python heredoc:

```python
# After frontmatter merge, before sys.exit(0):
parts = content.split("---", 2)
body = parts[2].strip() if len(parts) >= 3 else ""
if body:
    print(f"\n{body}", file=sys.stderr)
```

Note: emit to `stderr` to keep `stdout` clean for the JSON config merge output.

> **Scope boundary**: Apply after FEAT-1112 and FEAT-1263 have merged; verify hook's exit-code behavior is additive and does not conflict with FEAT-1112's ingestion wiring.

### Tests (Step 19)

Add `TestSyncToLocalMd` to `scripts/tests/test_decisions.py` following `TestAppendSessionLogEntry` structure:

- `test_creates_section` — creates `## Active Rules` when ll.local.md has no such section
- `test_replaces_existing_section` — replaces existing `## Active Rules` content
- `test_filters_advisory_rules` — advisory rules are excluded (only `required` appear)
- `test_excludes_superseded_rules` — superseded rules are excluded via `resolve_active()`
- `test_uses_atomic_write` — verify `atomic_write` is called (not direct write)

**Step 23 (Conditional)**: If body-output logic is extended to the Python `session_start.handle()` beyond the shell script, update `scripts/tests/test_hook_session_start.py:TestSessionStartLocalOverrides` (lines 124-152) to separate body text from JSON stdout before calling `json.loads()`. Skip if Python handler remains unchanged.

## Acceptance Criteria

- [ ] `sync_to_local_md(project_root)` implemented in `scripts/little_loops/decisions.py`
- [ ] `sync` writes active `required` rules to `## Active Rules` in `.ll/ll.local.md`
- [ ] Advisory and superseded rules are excluded from the sync output
- [ ] `hooks/scripts/session-start.sh` emits `## Active Rules` body content at session start (via stderr)
- [ ] `TestSyncToLocalMd` class added to `test_decisions.py` covering all 5 scenarios
- [ ] Step 23 conditional test update addressed (or documented as skipped with reason)

## Session Log
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
