---
id: ENH-1886
title: File-level mtime pre-filter in extract_conversation_turns() for incremental harvesting
type: ENH
priority: P4
status: open
captured_at: '2026-06-03T00:48:04Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
parent: EPIC-1880
---

# ENH-1886: File-level mtime pre-filter in `extract_conversation_turns()` for incremental harvesting

## Summary

`extract_conversation_turns()` in `user_messages.py` fully reads every `.jsonl` file under `project_folder` before applying the `since` cutoff — making the harvest sentinel in `sft-corpus` (and `examples-miner`) a per-turn filter only, not a per-file skip. Add a file-level mtime pre-check so sessions whose last-modified time predates `since` are skipped entirely without reading.

## Current Behavior

`extract_conversation_turns(project_folder, since=<datetime>)` globs all `*.jsonl` files under `project_folder`, reads every file completely, then filters out turn pairs where `timestamp < since` in `_extract_turn_pairs()`. On a corpus of hundreds of sessions, all files are read regardless of the sentinel.

Relevant code: `scripts/little_loops/user_messages.py:extract_conversation_turns()` (L765).

## Expected Behavior

When `since` is provided, skip any `.jsonl` file whose `os.path.getmtime()` is earlier than `since.timestamp()` (with a configurable grace period, e.g., 60 s, to avoid skipping files that were modified just before the cutoff). Files that pass the mtime check are read and filtered as before.

## Motivation

Harvest sentinels are written after each successful publish run. Re-runs therefore know exactly how far back they need to look. Reading every historical `.jsonl` file is wasteful and will become noticeably slow as the corpus grows (each Claude Code session produces a separate JSONL file; a year of active use could mean thousands of files).

## API/Interface

N/A — No public API changes. `extract_conversation_turns()` signature is unchanged; only internal file-list filtering is added.

## Integration Map

### Files to Modify
- `scripts/little_loops/user_messages.py` — `extract_conversation_turns()` (~L765): add mtime pre-filter before reading file contents

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "extract_conversation_turns" scripts/`

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml` — also uses harvest sentinel + `--since`; verify it benefits automatically

### Tests
- `scripts/tests/test_user_messages.py` — add fixture test for mtime-based skipping (two JSONL fixtures with different mtimes)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `extract_conversation_turns()`, after globbing `.jsonl` files, filter the list:
   ```python
   if since is not None:
       grace = timedelta(seconds=60)
       cutoff_ts = (since - grace).timestamp()
       files = [f for f in files if f.stat().st_mtime >= cutoff_ts]
   ```
2. Ensure existing tests still pass (no behavior change when `since=None`)
3. Add a test in `scripts/tests/test_user_messages.py`: write two `.jsonl` fixtures with different mtimes; confirm that only the newer file's turns are returned when `since` is set to a value between them.

## Acceptance Criteria

- [ ] Calling `extract_conversation_turns(folder, since=<dt>)` reads only files whose mtime ≥ `since - 60s`
- [ ] Behavior is unchanged when `since=None` (all files read as before)
- [ ] Existing `test_user_messages.py` tests continue to pass
- [ ] New test confirms mtime-based skipping with two fixture files

## Impact

- **Priority**: P4 — minor optimization; corpus is small today but degrades linearly with active use
- **Effort**: Small — single function change plus one test fixture
- **Risk**: Low — `since=None` behavior is unchanged; the mtime filter is additive only
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Mtime pre-filter in `extract_conversation_turns()` when `since` is provided; 60-second hardcoded grace period
- **Out of scope**: Making the grace period configurable via `.ll/ll-config.json`; changes to `examples-miner` harvest orchestration logic; per-turn timestamp filtering in `_extract_turn_pairs()` (remains unchanged)

## Related

- FEAT-1826 — sft-corpus harvest state uses `--since` flag routed through this function
- `scripts/little_loops/loops/examples-miner.yaml` — also uses harvest sentinel + `--since`
- EPIC-1880 — parent epic

## Labels

`performance`, `sft`, `user-messages`, `incremental`

## Session Log
- `/ll:format-issue` - 2026-06-03T01:14:02 - `6440d944-a7d1-441a-bc55-42e0d5f7c1f8.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:48:04Z - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`

---
## Status

`open`
