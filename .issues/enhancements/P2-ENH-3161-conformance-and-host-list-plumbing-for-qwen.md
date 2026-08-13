---
id: ENH-3161
title: Conformance + host-list plumbing for qwen
type: ENH
status: done
priority: P2
parent: EPIC-3154
depends_on:
- ENH-3156
captured_at: '2026-08-13T01:28:37Z'
discovered_date: 2026-08-12
discovered_by: capture-issue
labels:
- qwen
- host-compat
completed_at: '2026-08-13T04:40:00Z'
---

# ENH-3161: Conformance + host-list plumbing for qwen

## Summary

Register qwen in the generic EPIC-2257 infrastructure and every host-list
seam: conformance `_HOST_BINARY` entry, config-schema `host_cli` enum,
`ll-session --host` choices, and `get_project_folder()` session-log
resolution. Mirrors ENH-2918 (the Kimi plumbing child).

## Motivation

A host is only as usable as its plumbing: the conformance harness
(FEAT-2259) needs a binary entry to run golden paths for qwen, the config
schema validates `orchestration.host_cli`, and `ll-session` needs to locate
Qwen session logs (`~/.qwen/projects/<sanitized-cwd>/chats`, JSONL) for
backfill/review.

## Implementation Steps

1. `scripts/tests/conformance/test_host_conformance.py` —
   `_HOST_BINARY["qwen"] = "qwen"`; run the golden paths with
   `--conformance-host qwen` (harness validates invocation construction —
   argv/binary — not live execution, per FEAT-2259 design).
2. `scripts/little_loops/config-schema.json` — `orchestration.host_cli`
   enum += `qwen`.
3. `scripts/little_loops/cli/session.py` — `--host` choices += `qwen`.
4. `scripts/little_loops/user_messages.py` — `get_project_folder()` qwen
   branch (`~/.qwen/projects/<sanitized-cwd>/chats`). Locating session logs
   is in scope; wire-format parsing is a likely follow-up (as on Kimi, whose
   typed-event `wire.jsonl` schema still needs a parser).
5. pyproject metadata / console entrypoints if the kimi child touched them.

## Integration Map

### Files to Modify

- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry
- `scripts/little_loops/config-schema.json` — `orchestration.host_cli` enum
- `scripts/little_loops/cli/session.py` — `--host` choices entry
- `scripts/little_loops/user_messages.py` — `get_project_folder()` qwen branch

### New Files

- None.

### Dependent Files

- `ll-doctor` — host plumbing report
- `ll-session backfill` — consumes `get_project_folder()`

## Impact

- **Priority**: P2 — independent track (needs ENH-3156's runner for the conformance argv assertions).
- **Effort**: S — four small plumbing edits plus a golden-path run.
- **Risk**: Low — additive entries; wire-format parsing explicitly deferred.
- **Breaking Change**: No.

## Verification Notes

2026-08-12 (DONE): All four seams landed:
- `_HOST_BINARY["qwen"] = "qwen"` in the conformance harness; **4/4 golden
  paths pass with `--conformance-host qwen` on the real binary**
  (invocation-construction validation per FEAT-2259 design).
- `config-schema.json` `orchestration.host_cli` enum += `qwen`.
- `ll-session backfill --host qwen` choice added (gemini/omp remain
  deliberately absent — accurate absences, not drift).
- `get_project_folder()` qwen branch: dash-encoded symlink-resolved cwd
  (Claude-style) + `chats/` subdirectory (qwen nests JSONLs one level
  deeper — verified by FEAT-3155 transcript_path evidence). Wire-format
  parsing deferred (kimi wire.jsonl posture). 3 new tests in
  `test_user_messages.py` (chats-dir resolution, None without sessions,
  bare-project-dir negative); suite green (854 session-tagged tests).

## Session Log
- `/ll:capture-issue` - 2026-08-13T01:28:37Z - qwen-code host integration report capture

---

**Done** | Created: 2026-08-12 | Completed: 2026-08-12 | Priority: P2
