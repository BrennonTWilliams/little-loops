---
id: ENH-2918
title: Conformance + host-list plumbing for kimi-code
type: ENH
status: open
priority: P3
parent: EPIC-2910
captured_at: "2026-07-29T15:55:00Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- kimi
- host-compat
---

# ENH-2918: Conformance + host-list plumbing for kimi-code

## Summary

Host-list plumbing so the conformance harness, config validation, and session
tooling recognize `kimi-code`: a `_HOST_BINARY` entry, the config-schema enum
REAL drift fix (kimi-code plus gemini/omp), an `ll-session --host` branch
reading `~/.kimi-code/session_index.jsonl`, and `scripts/pyproject.toml`
metadata.

## Motivation

These are the small wiring points that keep the host key consistent across
the test harness, config schema, and session tooling. The config-schema enum
is REAL drift — `orchestration.host_cli` is missing the already-supported
gemini/omp as well as kimi-code, and the root `config-schema.json` no longer
exists (fix the stale pointer at `.claude/CLAUDE.md:29` in the same pass).
`ll-session --host` is capability-scoped, NOT drift: add only the kimi-code
branch — gemini/omp stay absent because no log-discovery branch exists for
them (accurate absence, not drift).

## Implementation Steps

1. Add `"kimi-code": "kimi"` to `_HOST_BINARY`
   (`scripts/tests/conformance/test_host_conformance.py:52-59`).
2. Config-schema enum drift fix: add `kimi-code` AND `gemini`/`omp` to
   `orchestration.host_cli` in `scripts/little_loops/config-schema.json:1587`;
   fix the stale root `config-schema.json` pointer at `.claude/CLAUDE.md:29`
   in the same pass.
3. `ll-session --host`: add the kimi-code branch to `get_project_folder()`
   (`user_messages.py:369`) reading `~/.kimi-code/session_index.jsonl`
   (workDir → sessionDir, per spike Q4) together with the
   `cli/session.py:173` choices entry; do NOT add gemini/omp there.
4. Update `scripts/pyproject.toml` description/keywords (lines 8/19) —
   currently claude-only.

## Integration Map

### Files to Modify

- `scripts/tests/conformance/test_host_conformance.py` — `_HOST_BINARY` entry
- `scripts/little_loops/config-schema.json` — `orchestration.host_cli` enum (incl. gemini/omp)
- `.claude/CLAUDE.md` — fix stale config-schema pointer (:29)
- `scripts/little_loops/user_messages.py` — `get_project_folder()` kimi branch
- `scripts/little_loops/cli/session.py` — `--host` choices entry (:173)
- `scripts/pyproject.toml` — description/keywords (lines 8/19)

### New Files

- None.

### Dependent Files

- `scripts/little_loops/host_runner.py` — `KimiRunner` (ENH-2912 / FEAT-2914); conformance golden paths exercise it
- `docs/reference/HOST_COMPATIBILITY.md` — orchestration CLI / discovery cells, flipped by ENH-2919

## Impact

- **Priority**: P3 — independent plumbing; no user workflow blocked on it.
- **Effort**: S — four small, well-located edits.
- **Risk**: Low — additive branches; the gemini/omp enum additions fix drift, not behavior.
- **Breaking Change**: No.

## Session Log
- `/ll:capture-issue` - 2026-07-29T15:55:00Z - kimi-code host adapter planning session

---

**Open** | Created: 2026-07-29 | Priority: P3
