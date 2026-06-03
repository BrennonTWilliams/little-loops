---
id: ENH-1886
title: File-level mtime pre-filter in extract_conversation_turns() for incremental
  harvesting
type: ENH
priority: P4
status: done
captured_at: '2026-06-03T00:48:04Z'
completed_at: '2026-06-03T06:22:00Z'
discovered_date: '2026-06-03'
discovered_by: capture-issue
parent: EPIC-1880
confidence_score: 98
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
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
- `scripts/little_loops/cli/messages.py:242` — `main_messages()` calls `extract_conversation_turns()` when the `--sft-format` flag is provided; no other callers exist

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:30` — uses `--since $(cat corpus.last_harvested)` harvest sentinel; benefits automatically from this fix without code changes
- `scripts/little_loops/session_store.py:_mtime()` + `backfill_incremental()` (L950, L990) — **canonical model**: module-level `_mtime(path)` helper with `OSError → 0.0` guard, list-comprehension pre-filter `[f for f in files if _mtime(f) >= since_ts]` before the file loop; `since_ts` is a Unix float from `since.timestamp()`

### Tests
- `scripts/tests/test_user_messages.py` — existing mtime-unaware tests at `test_extract_conversation_turns_basic()` (L1608) and `test_extract_conversation_turns_windowing()` (L1645); add a third test for mtime skipping
- Use `os.utime(path, (ts, ts))` to back-date a fixture file (pattern from `test_pre_compact.py:TestRecentPlanFiles.test_excludes_old_files()` L140); confirm only the newer file's turns are returned

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/user_messages.py:extract_conversation_turns()` (L765), convert the glob generator to a list and apply the mtime pre-filter before the file loop. Follow the `session_store.py:_mtime()` pattern:
   ```python
   jsonl_files = list(project_folder.glob("*.jsonl"))
   if since is not None:
       grace = timedelta(seconds=60)
       cutoff_ts = (since - grace).timestamp()
       jsonl_files = [f for f in jsonl_files if _mtime(f) >= cutoff_ts]
   ```
   Add a module-level `_mtime()` helper (same as `session_store.py:_mtime()`, L950):
   ```python
   def _mtime(path: Path) -> float:
       try:
           return path.stat().st_mtime
       except OSError:
           return 0.0
   ```
   The per-record filter in `_extract_turn_pairs()` (L721) and `_parse_user_record()` (L604) remains unchanged — the mtime filter is purely additive.
2. `timedelta` is NOT currently imported in `user_messages.py`; update the import to `from datetime import datetime, timedelta`. `os` is not used; keep using `pathlib.Path.stat()`.
3. Ensure existing tests still pass (`since=None` path skips the filter block entirely).
4. Add `test_extract_conversation_turns_skips_old_files()` in `scripts/tests/test_user_messages.py` after L1645:
   - Create two `.jsonl` fixtures with valid `"user"` + `"assistant"` records
   - Use `os.utime(old_file, (old_ts, old_ts))` to back-date the first file to before `since - 60s`
   - Call `extract_conversation_turns(tmp_dir, since=since)`
   - Assert turns from the old file are absent; turns from the new file are present
   - Pattern reference: `test_pre_compact.py:TestRecentPlanFiles.test_excludes_old_files()` (L140)

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
- `/ll:ready-issue` - 2026-06-03T06:17:06 - `efd3c066-dede-460b-8b1f-364b55af688a.jsonl`
- `/ll:confidence-check` - 2026-06-03T07:30:00Z - `fdc2cb4c-8eba-4dc9-92e6-d372e98a71d3.jsonl`
- `/ll:refine-issue` - 2026-06-03T06:08:32 - `cf827d57-4db9-48f7-ada6-1ca3c16ac826.jsonl`
- `/ll:format-issue` - 2026-06-03T01:14:02 - `6440d944-a7d1-441a-bc55-42e0d5f7c1f8.jsonl`
- `/ll:capture-issue` - 2026-06-03T00:48:04Z - `dd96413d-220c-449b-8e81-593defe00fdc.jsonl`

---
## Status

`open`
