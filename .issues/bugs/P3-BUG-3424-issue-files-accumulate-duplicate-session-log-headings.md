---
id: BUG-3424
type: BUG
title: Issue files accumulate duplicate Session Log headings
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:37:59Z'
---

# BUG-3424: Issue files accumulate duplicate Session Log headings

## Summary

54 issue files under `.issues/` at HEAD contain two or more line-anchored `## Session Log` H2 headings. The session-log readers in `scripts/little_loops/session_log.py` (`session_log_body`, `parse_session_log`, `count_session_commands`, `last_command_timestamp`) read only the **last** non-fenced section, so every entry in an earlier block is invisible to them — stale-refine detection, per-command timestamps, and command counts all under-report on those files.

Two observed shapes produce the duplicate:

1. **LLM hand-append at EOF.** A command pass writes `\n\n## Session Log\n- <entry>` at end of file even though a `## Session Log` heading already exists earlier. Reproduced in commit 98dbbaf83 on ENH-3423: the `/ll:verify-issues --auto` pass inserted `## Verification Notes` above the existing Session Log, then started a fresh `## Session Log` at EOF for its own entry. The manual-fallback instruction in `commands/verify-issues.md` section 4.5 (mirrored in `skills/capture-issue/SKILL.md:292`, `skills/decide-issue/SKILL.md:452`, `commands/scan-codebase.md:314`, `commands/ready-issue.md:365`) tells the model how to format the entry and where to put a *new* heading, but never says to reuse an existing heading when one is present.
2. **Post-Resolution restart.** In 7 of 12 sampled duplicate files the second heading immediately follows a `## Resolution` block. The Resolution templates in `scripts/little_loops/issue_lifecycle.py:355-415` and `scripts/little_loops/parallel/orchestrator.py:1960-1985` are appended at EOF *below* the existing Session Log, and a later pass then opened a new Session Log under the Resolution footer instead of returning to the original heading.

`append_session_log_entry` (`scripts/little_loops/session_log.py:281-343`) is **not** the writer at fault: it correctly finds the last fence-excluded, line-anchored heading (BUG-3202) and inserts under it. But it silently tolerates a duplicate and keeps feeding only the last block, so the file never self-heals and the earlier entries stay orphaned.

## Relationships

- ENH-3423 documents this pattern as out of scope for its own fix.
- BUG-3202 (line-anchored heading match) and BUG-3150 (append lock) are the prior fixes in the same function; this extends, not reverts, them.

## Current Behavior

An issue file can end up with more than one non-fenced `## Session Log` H2 heading (see Summary for the two shapes that produce this). Once that happens, `session_log_body`, `parse_session_log`, `count_session_commands`, and `last_command_timestamp` all read only the section under the **last** heading — every entry recorded under an earlier heading becomes invisible to stale-refine detection, command counts, and per-command timestamps. `append_session_log_entry` inserts new entries under the last heading too, so the file never self-heals; the orphaned entries stay orphaned indefinitely.

## Expected Behavior

An issue file has at most one `## Session Log` heading. When `append_session_log_entry` finds more than one non-fenced heading, it merges every section's entries into a single block (preserving entry order, at the first heading's position) before inserting the new entry — so a single subsequent `ll-issues append-log` call repairs the file and all four readers see the complete history.

## Motivation

This bug matters because it silently corrupts an automation signal, not just a cosmetic one:
- Stale-refine detection, `count_session_commands`, and `last_command_timestamp` under-report on all 54 already-affected files, which can make an issue look less-refined (or more stale) than its real session history shows.
- The corruption is self-perpetuating: `append_session_log_entry` keeps writing under the last heading, so the file never self-heals without an explicit fix.
- It closes a gap left by BUG-3202 (heading *matching*) and BUG-3150 (append *locking*) — both hardened `append_session_log_entry` against related failure modes but neither addressed heading *duplication*.

## Proposed Solution

- (a) In `append_session_log_entry`, when more than one non-fenced `## Session Log` heading exists, merge every section's entries into a single block (preserving entry order, first heading's position) before inserting the new entry — so any subsequent `ll-issues append-log` repairs the file.
- (b) Tighten every manual-fallback instruction listed above to: "append under the existing `## Session Log` heading if one exists; create the heading only when none does."
- (c) One-shot normalization of the 54 existing files, either via `/ll:normalize-issues` or a new `ll-issues` subcommand that reuses the merge logic from (a).
- (d) Regression test: start from a fixture with two `## Session Log` blocks (one above a `## Resolution` footer, one below), call `append_session_log_entry`, assert exactly one heading remains with all prior entries plus the new one preserved in order.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_log.py` (`append_session_log_entry` — add merge-before-insert logic)
- `commands/verify-issues.md` (§4.5 manual-fallback instruction)
- `skills/capture-issue/SKILL.md:292`
- `skills/decide-issue/SKILL.md:452`
- `commands/scan-codebase.md:314`
- `commands/ready-issue.md:365`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/append_log.py` (`cmd_append_log`)
- `scripts/little_loops/issue_lifecycle.py:1161`
- `scripts/little_loops/parallel/orchestrator.py:1999`
- `scripts/little_loops/mcp_server/tools.py:468`

### Similar Patterns
- `grep -rn "## Session Log\|## Resolution" scripts/little_loops/issue_lifecycle.py scripts/little_loops/parallel/orchestrator.py` finds the other footer-template sites (Resolution blocks) that append below an existing Session Log heading and should be checked for the same reuse-existing-heading fix.

### Tests
- `scripts/tests/test_session_log.py` (add the two-heading merge fixture from Proposed Solution item (d))

### Documentation
- `docs/reference/API.md` (`little_loops.session_log` reference, around line 7691) — document the merge behavior once implemented

### Configuration
- N/A

## Program Design

### Types

- (none — extends existing behavior; no new data types)

### Signatures

- `append_session_log_entry(issue_path: Path, command: str, session_jsonl: Path | None = None) -> bool` (existing; gains a merge step when more than one `## Session Log` heading is found)
- `_merge_session_log_headings(content: str, headings: list[re.Match[str]]) -> str` (new, private helper in `session_log.py`)

### Call Path

`cli/issues/append_log.py::cmd_append_log` -> `append_session_log_entry` -> `_merge_session_log_headings` (new, invoked when `len(headings) > 1`) -> `atomic_write`

## Implementation Steps

1. Add `_merge_session_log_headings` to `session_log.py` and call it from `append_session_log_entry` when more than one non-fenced heading is found, before the existing insert-under-last-heading logic runs.
2. Tighten the manual-fallback instructions in `commands/verify-issues.md`, `skills/capture-issue/SKILL.md`, `skills/decide-issue/SKILL.md`, `commands/scan-codebase.md`, and `commands/ready-issue.md` to reuse an existing `## Session Log` heading instead of unconditionally creating a new one.
3. One-shot normalize the 54 already-affected files via `/ll:normalize-issues` or a new `ll-issues` subcommand that reuses the merge logic from step 1.
4. Add the two-heading regression fixture (Proposed Solution item (d)) to `scripts/tests/test_session_log.py`.
5. Run `python -m pytest scripts/tests/test_session_log.py` and verify the fix resolves the issue.

## Impact

- **Priority**: P3 - matches frontmatter; corrupts an automation signal (stale-refine detection, command counts) on 54 files but is not user-facing or blocking.
- **Effort**: Medium - one core-function change plus five manual-fallback doc call sites, a one-shot normalization pass, and a new regression test.
- **Risk**: Low - `append_session_log_entry` already holds a per-file lock (BUG-3150); the merge only triggers when more than one heading is found, so single-heading files are unaffected.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3

## Steps to Reproduce

1. Run a flow whose manual-fallback session-log instructions add a `## Session Log` heading unconditionally after another footer section (e.g. `## Resolution` or `## Verification Notes`) was appended below the existing heading — e.g. `/ll:verify-issues --auto` on an issue that already has a Session Log.
2. Trigger `append_session_log_entry` again on the same file (e.g. via `ll-issues append-log`).
3. Observe: the file now has two non-fenced `## Session Log` H2 headings; `session_log_body`/`parse_session_log`/`count_session_commands`/`last_command_timestamp` report only the entries under the *last* heading. Concretely reproduced in commit `98dbbaf83` on ENH-3423.

## Root Cause

- **File**: `scripts/little_loops/session_log.py`
- **Anchor**: `in function append_session_log_entry()` (lines 281-343)
- **Cause**: `append_session_log_entry` finds only the *last* non-fenced, line-anchored `## Session Log` heading and inserts under it (correct per BUG-3202), but never checks whether more than one such heading already exists. The duplicate is introduced upstream: the manual-fallback instructions in `commands/verify-issues.md` §4.5, `skills/capture-issue/SKILL.md:292`, `skills/decide-issue/SKILL.md:452`, `commands/scan-codebase.md:314`, and `commands/ready-issue.md:365` tell the model to add a `## Session Log` heading without checking whether one already exists, and the Resolution templates in `issue_lifecycle.py:355-415` / `parallel/orchestrator.py:1960-1985` append below the existing heading, so a later pass opens a fresh one under the Resolution footer instead of returning to the original.

## Error Messages

## Environment

## Frequency

## Location

- **File**: `scripts/little_loops/session_log.py`
- **Line(s)**: 281-343 (at scan commit: 7e5d8c91e)
- **Anchor**: `in function append_session_log_entry()`
- **Code**:
```python
spans = fence_spans(content)
headings = [
    m
    for m in _SESSION_LOG_HEADING_RE.finditer(content)
    if not in_fence(m.start(), m.end(), spans)
]

if headings:
    # Insert entry after the last real (fence-excluded, line-anchored
    # H2) ## Session Log heading — never one quoted inside a fence,
    # and never an ### Session Log H3 (BUG-3202).
    match = headings[-1]
    ...
```

## Session Log
- `/ll:format-issue` - 2026-09-09T19:43:04 - `aa20b4a6-c20a-46a5-892f-bfa653566c50.jsonl`
- `/ll:capture-issue` - 2026-09-09T19:38:06 - `43a86a4b-030b-4f3d-98cb-3c4b4bf26ccd.jsonl`
