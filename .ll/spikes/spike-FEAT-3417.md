# Spike Plan: FEAT-3417 — session-discovery lifecycle (`detect_sessions`/`iter_events`)

## Context

FEAT-3417 selected Option B: a standalone `detect_sessions`/`iter_events`
lifecycle (`SessionHandle`/`SessionEvent`, per-host parser dispatch) rather
than extending `HostLayout.normalize`. The confidence-check notes name the
core unproven mechanism directly:

> "No Duplicate Implementations (10/20): partial precedent exists
> (`get_project_folder`/`get_sessions_folder`'s Codex path probe,
> `HostLayout`) but no `detect`/`iter_events` lifecycle exists anywhere in
> the repo." (Confidence Check Notes, 2026-09-08)
>
> "Complexity (0/25): ... a brand-new `detect_sessions`/`iter_events`
> lifecycle with zero existing precedent in the repo."

Concrete failure the spike must rule out: the issue's Codex discovery
strategy (§ Codex On-Disk Layout) is a two-tier fallback — query the newest
`state_*.sqlite` `threads` table by exact `cwd`, verify each `rollout_path`
still exists on disk, and fall back to scanning `~/.codex/sessions/`
date-directories newest-first (reading only line 1 of each rollout) when the
DB is absent, unreadable, or schema-mismatched. If that fallback logic is
wrong — e.g. it silently returns stale/deleted sessions, picks the wrong
`state_*.sqlite` when several exist, or the DB-present/DB-absent paths
disagree on ordering or on how `cwd` is matched — `detect_sessions` returns
a different session set than a maintainer would get by hand, and every
downstream consumer (`ll-logs`, `ll-messages`, `ll-ctx-stats`) silently
misses or duplicates sessions. Separately, `iter_events` must dispatch
correctly between two per-host parsers with incompatible record shapes
(Claude Code per-line records vs. Codex's header-line-carries-identity
shape) without the dispatch itself leaking Claude-specific assumptions onto
Codex handles or vice versa.

This is a distinct risk from the "Learning Test Hard Override"
(`codex-rollout`, no record) also flagged in this issue: that gap is about
whether Codex's *real* sqlite schema and rollout shape match the documented
claims (an external vendor-format question, `/ll:explore-api` territory).
This spike proves the *internal* discovery-and-dispatch algorithm is
correct against synthetic fixtures built to that documented shape — it does
not re-verify the vendor's actual on-disk format.

Both canonical low-confidence drivers apply: **(a)** the `detect`/
`iter_events` lifecycle trio has zero precedent anywhere in
`scripts/little_loops/` (confirmed by the issue's own repo-wide search);
**(b)** no existing test exercises sqlite-backed session discovery with a
scan fallback, or per-host event-iterator dispatch.

## Approach

Build a small standalone library that implements the discovery/dispatch
algorithm exactly as specified in § Program Design and § Codex On-Disk
Layout, driven against **synthetic fixtures** (a temp `sqlite3` DB with a
`threads` table, and temp `rollout-*.jsonl` files under a fake
`sessions/YYYY/MM/DD/` tree) rather than a real captured Codex corpus —
proving the vendor's real shape is `codex-rollout`'s job, not this spike's.
What's faked: the actual Codex binary and its real on-disk data. What's
real: `sqlite3` (stdlib), real temp-directory file I/O, real JSONL
line-by-line parsing — the same primitives the production code will use, so
the substitution doesn't touch the risky core (the fallback/ordering/dispatch
logic runs identically against synthetic or real files of the same shape).

## Critical files

Read-only references:
- `scripts/little_loops/session_store/gemini.py:1-52` — the generator
  convention the spike's per-host parsers must match: `Iterator[dict]`
  return type from `collections.abc`, `try/except OSError: return` on file
  open, per-line `json.loads` inside a tolerant loop, bare `return` on a
  malformed header rather than a raised exception.
- `scripts/little_loops/user_messages.py:373-419` (`get_project_folder`) —
  the existing host-dispatch `if`/`elif` chain convention `detect_sessions`
  is a sibling to, and the `_get_codex_project_folder` dead-path this issue
  retires (not touched by this spike; read-only precedent only).
- `scripts/little_loops/session_store/writers.py:2527-2604`
  (`host_layout_for`) — precedent for a per-host dispatch function returning
  a frozen layout/handle-shaped object.
- Issue § Codex On-Disk Layout and § Program Design (this issue,
  FEAT-3417) — the authoritative spec for `SessionHandle`, `SessionEvent`,
  `detect_sessions` signature, and the sqlite-then-scan-fallback algorithm.

New spike paths:
- `scripts/tests/spike/session_discovery_lifecycle/__init__.py`
- `scripts/tests/spike/session_discovery_lifecycle/lifecycle.py`
- `scripts/tests/spike/session_discovery_lifecycle/test_lifecycle.py`

## Implementation

```
scripts/tests/spike/session_discovery_lifecycle/
├── __init__.py
├── lifecycle.py             # SessionHandle, SessionEvent, detect_sessions, iter_events
└── test_lifecycle.py        # AC test class + isolation guard
```

API sketch (`lifecycle.py`):

```python
from __future__ import annotations
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class SessionHandle:
    host: str
    session_id: str
    path: Path
    cwd: Path
    updated_at: float

@dataclass(frozen=True)
class SessionEvent:
    type: str
    timestamp: str
    host: str
    payload: dict

def detect_sessions(
    cwd: Path, host: str, *, home: Path, limit: int | None = None
) -> list[SessionHandle]:
    """Newest-first SessionHandles for cwd under host, rooted at `home`
    (a fake HOME for test isolation, not os.path.expanduser).
    host == "codex": query newest home/.codex/state_*.sqlite by filename
    sort desc; on missing/unreadable DB or missing `threads` columns, fall
    back to scanning home/.codex/sessions/**/rollout-*.jsonl newest-first,
    reading only line 1 for payload.cwd. Every returned rollout_path is
    verified to exist. host == "claude-code": glob home/.claude/projects/
    for *.jsonl (existing convention, reimplemented minimally here)."""

def iter_events(handle: SessionHandle) -> Iterator[SessionEvent]:
    """Dispatch to the per-host parser by handle.host."""

def parse_codex_rollout(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse; line 1 carries session_meta (id, cwd, cli_version)."""

def parse_claude_transcript(path: Path) -> Iterator[SessionEvent]:
    """Per-line parse; no shared header-line dependency."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_detect_sessions_codex_uses_sqlite_when_present` | Risk (a): sqlite `threads`-table query path has no precedent | behavior |
| `test_detect_sessions_codex_picks_newest_state_db_by_name` | Risk (a): "newest `state_*.sqlite`" selection ordering is unverified | behavior |
| `test_detect_sessions_codex_filters_stale_rollout_paths` | Risk (a): a `threads` row whose `rollout_path` no longer exists must be dropped, not returned | behavior |
| `test_detect_sessions_codex_falls_back_to_date_scan_when_db_missing` | Risk (a)/(b): DB-absent fallback path is untested and must match the DB path's ordering/cwd-matching contract | behavior |
| `test_detect_sessions_codex_falls_back_when_db_schema_mismatched` | Risk (a): a `threads` table missing expected columns must trigger fallback, not raise | behavior |
| `test_iter_events_dispatches_by_host_without_cross_contamination` | Risk (a)/(b): per-host parser dispatch with zero shared content code | behavior |
| `test_lifecycle_module_has_no_production_imports` | isolation guard | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/session_discovery_lifecycle/ -v
python -m pytest scripts/tests/test_user_messages.py -k codex -v
```

## Out of Scope

- Real Codex sqlite schema/rollout-shape verification — that is the
  `codex-rollout` learning-test target (`/ll:explore-api`), not this spike.
- Rewiring `cli/logs.py`, `user_messages.py`, `cli/ctx_stats.py` onto the
  new lifecycle — FEAT-3417's real integration point, done after this spike.
- `watch`/`stop` — explicitly deferred in the issue (§ Live watch is
  deferred); not part of v1's lifecycle and not spiked here.
- `ll-ctx-stats`'s Codex usage-reader decision (step 5) — depends on real
  rollout content the `codex-rollout` learning test resolves, not this
  spike's synthetic fixtures.

## Promotion

On acceptance, promote `lifecycle.py`'s `SessionHandle`/`SessionEvent`/
`detect_sessions`/`iter_events`/`parse_codex_rollout`/
`parse_claude_transcript` into `scripts/little_loops/session_store/sessions.py`
per § Program Design, in a **separate PR** that also does the Wiring Phase
rewire — this spike proves the discovery/dispatch algorithm, it does not
ship it.
