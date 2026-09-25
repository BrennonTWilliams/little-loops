---
id: ENH-3549
title: Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam
  so every reader is host-agnostic
type: ENH
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-24'
labels:
- observability
- multi-host
depends_on:
- ENH-3532
- ENH-3534
confidence_score: 65
outcome_confidence: 52
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

# Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam so every reader is host-agnostic

## Summary

The runtime-adapter seam for host log ingestion shipped in v1.162.0 (FEAT-3417, with Codex as the second implementation), and the write-side divergent-fakes acceptance landed in v1.164.0 (ENH-3456/ENH-3459). The migration itself has not: `ll-logs`, `ll-messages`, and `ll-ctx-stats` still reach directly for `~/.claude/projects/<munged-cwd>/`, so every log-derived surface remains Claude-Code-only by construction even though the seam that fixes it is in the tree. The toolkit can write a Codex session's artifacts and then cannot read a single Codex session back.

Migrate all three readers onto the session-watcher seam — detect, watch, emit typed events, stop — with per-host parsers behind it and one shared fan-in above it, so a Codex session reads back as naturally as a Claude Code one. One implementation serves many readers: `ll-logs`, `ll-messages`, `ll-ctx-stats`, and any future dashboard or export consumer attach to the same seam rather than each re-parsing host transcripts directly. Downstream, the dataset export and the quality rollups consume these readers and remain single-host until this lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Scope is narrower than the Summary states.** `cli/logs.py`, `cli/messages.py` and `cli/ctx_stats.py` contain no `.claude/projects` literal and make no calls into the `user_messages` project-folder helpers; they already route through `detect_sessions`/`iter_events` (ENH-3428/3429/3430). The direct joins remain in `user_messages._get_claude_project_folder`, `sessions._list_claude_workspaces`, `sessions._explain_encoded_dir_host`, and `writers.host_layout_for` (write-side).
- **No `SessionWatcher` symbol exists in code.** "Session-watcher seam" is the session-discovery seam (`SessionHandle`, `detect_sessions`, `iter_events`) in `session_store/sessions.py`.
- **Related open work overlaps:** ENH-3419 (adopt seam in the three readers), ENH-3546 (non-Codex cache-rate provenance, referenced in `_compute_cache_rate_from_jsonl`). Confirm which acceptance criteria these already satisfy before implementing.
- **Read-side divergent-fake gap confirmed:** the fakes (`FakeHostRunner`, `FakeMinimalHostRunner`) have no session-log discovery or parser; `_PARSERS`/`_REGISTERED_HOSTS` hold only the eight real hosts. The composition test would need read-side fake session records or an equivalent fixture.

## Current Behavior

The three CLIs already discover sessions through `detect_sessions` and read events through `iter_events` (or handle-taking extractors in `little_loops.user_messages`); ENH-3428/3429/3430 landed that. The remaining gaps are narrower than the Summary states:

- `little_loops.user_messages._get_claude_project_folder` and `little_loops.session_store.sessions._list_claude_workspaces` still join `~/.claude/projects` themselves, and `detect_sessions` reaches the former.
- `ll-ctx-stats` (`_compute_cache_rate_from_jsonl`) reads Codex through `iter_events` but keeps a raw `open(handle.path)` reader for every other host, and labels non-Codex cache figures `provenance: "unknown"`.
- `ll-ctx-stats` has no named-cause warning when no sessions are found (`explain_no_sessions` is not called).
- The composition suite (`tests/conformance/test_host_composition.py`) exercises only the write/executor side; no fake host has a read-side session record, and no test asserts source files avoid a `.claude/projects` literal.

## Expected Behavior

All three readers attach to the session-watcher seam (detect, watch, emit typed events) and consume per-host parsers behind it. A Codex session for the current workspace reads back in `ll-logs` and `ll-messages` like a Claude Code one, `ll-ctx-stats` carries per-observation provenance (authoritative vs estimate), and no migrated reader references `~/.claude/projects/` directly.

## Design constraints

- The seam stays at the lifecycle only. Per-host parsers live behind it and share nothing above it. Do not introduce a common abstraction over tool-call shapes or token accounting: the runtimes do not overlap enough for a forced common record to beat two honest per-host ones.
- Discovery failure and genuine absence must remain distinguishable after the migration. A workspace whose sessions exist on disk but match nothing renders a named-cause warning, not an empty result; the migration must not regress that behavior where it exists today.
- The Codex parser is tested against a captured real-shape rollout fixture, treated as perishable — vendor shape drift is one re-capture away from detection. The fixture complements, not replaces, the scripted fake hosts.

## Acceptance criteria

- The divergent fakes pass on the **read** side, not only the write side: the composition test drives both fakes' session records through the migrated readers, proving the readers host-agnostic rather than asserting it.
- A Codex session for the current workspace appears in `ll-logs` and `ll-messages` output with the same fidelity as a Claude Code session over the same period.
- `ll-ctx-stats` carries per-observation provenance for the records it counts: where a host exposes authoritative token counts they are read, and where it does not the figure is labeled an estimate (companion work: ENH-3528 and its ingestion splits ENH-3532/ENH-3534).
- No reader in the migrated set reaches for `~/.claude/projects/` directly; a mechanical check (grep or import rule) proves it.

---

## Scope Boundaries

- **In scope**: migrating `ll-logs`, `ll-messages`, and `ll-ctx-stats` onto the session-watcher seam; Codex parser behind the seam with a captured real-shape rollout fixture; read-side divergent-fake composition test; mechanical no-direct-`~/.claude/projects/` check.
- **Out of scope**: a common abstraction over tool-call shapes or token accounting; the `UsageObservation` normalization (ENH-3532, ENH-3534) and `select_usage_coverage` aggregation (ENH-3543); dataset export and quality rollups (downstream consumers).

### Scope Boundary Note

**Note** (added by `/ll:audit-issue-conflicts`): The "no common abstraction over tool-call shapes or token accounting" constraint applies to the session-watcher seam and its per-host typed events only. It does not prohibit the downstream `usage_events` contract: the shared `UsageObservation` normalization (ENH-3532, ENH-3534) and the single `select_usage_coverage` aggregation entry point (ENH-3543) are out of scope here and remain valid. `ll-ctx-stats` provenance (third acceptance criterion) consumes those stored observations; it does not re-derive token accounting in the seam.


## Impact

- **Priority**: P2 - every log-derived surface is Claude-Code-only until this lands; blocks host-agnostic dataset export and quality rollups.
- **Effort**: Large - three readers plus a Codex parser, fixture, and composition test.
- **Risk**: Medium - `user_messages` has many dependents; discovery-failure vs genuine-absence warnings must not regress.
- **Breaking Change**: No

## Program Design

### Types

- `SessionHandle`: frozen dataclass (`host: str`, `session_id: str`, `path: Path`, `cwd: Path`, `updated_at: float`, `is_agent: bool`) in `little_loops.session_store.sessions`; existing, unchanged
- `SessionEvent`: frozen dataclass (`type: str`, `timestamp: str`, `host: str`, `payload: dict[str, Any]`, `line_no: int | None`); existing, unchanged
- `NoSessionsCause`: `str` Enum naming why discovery came back empty; existing, consumed by `ll-ctx-stats` after this change

### Signatures

- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — existing seam entry point
- `iter_events(handle: SessionHandle) -> Iterator[SessionEvent]` — existing per-host parser dispatch
- `explain_no_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, home: Path | None = None) -> tuple[NoSessionsCause, str]` — existing; to be called from `ll-ctx-stats`
- `_compute_cache_rate_from_jsonl(cwd: Path, host: str | None) -> dict | None` — existing in `little_loops.cli.ctx_stats`; non-Codex branch to move onto `iter_events`
- `_get_claude_project_folder(encoded_path: str, *, home: Path | None = None) -> Path | None` — existing in `little_loops.user_messages`; the one join the seam still delegates to

### Call Path

`main_messages` -> `detect_sessions` -> `iter_events` -> `extract_user_messages`

`main_logs` -> `detect_sessions` -> `iter_events`

`main_ctx_stats` -> `_compute_cache_rate_from_jsonl` -> `detect_sessions` -> `iter_events`

### Decision Rules

N/A — no new decision logic

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/ctx_stats.py` — non-Codex branch of `_compute_cache_rate_from_jsonl` opens `handle.path` directly; no `explain_no_sessions` on empty discovery
- `scripts/little_loops/user_messages.py` — `_get_claude_project_folder` and sibling per-host joins; module docstring line 4
- `scripts/little_loops/session_store/sessions.py` — `_list_claude_workspaces` and `_explain_encoded_dir_host` carry their own `home / ... / "projects"` joins
- `scripts/tests/conformance/test_host_composition.py` — write-side only today

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — non-Codex `backfill` paths still call `get_project_folder(host=...)` (lines 710, 769)
- `scripts/little_loops/hooks/session_start.py` — `get_project_folder(root, host=...)`
- `scripts/little_loops/session_log.py`, `scripts/little_loops/fsm/continuity.py` — `get_sessions_folder`
- `scripts/little_loops/session_store/writers.py` — `host_layout_for` `projects_root` table (write-side layout, not a reader)

### Conventions in Force
- Readers take `SessionHandle`s from `detect_sessions` and parse only through `iter_events`; `home=` is threaded so tests pass `tmp_path` — evidence: `cli/logs.py`, `cli/messages.py`, `cli/ctx_stats.py`
- `session_store` never imports from `cli` — evidence: `list_workspaces` docstring (ENH-3430)
- Mechanical "must not reference X" gates are pytest tests with a reasoned allowlist that fails when an entry goes stale — evidence: `test_history_store_chokepoint_gate.py`, `test_usage_selection_chokepoint_gate.py`
- Codex fixtures are committed captures with a version-keyed re-capture rule — evidence: `scripts/tests/fixtures/codex/README.md`, `.ll/learning-tests/codex-rollout.md`
- Token provenance is `Literal["measured","estimated","unknown"]`, components `None` when unreported — evidence: `subprocess_utils.TokenUsage`, `token_provenance.py`

### Tests
- `scripts/tests/test_cli_ctx_stats.py`, `test_ll_logs.py`, `test_cli_messages.py`, `test_session_discovery.py`, `test_user_messages.py` — existing reader coverage that must keep passing
- `scripts/tests/conformance/test_host_composition.py` — hosts the read-side composition test

### Documentation
- `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md` — reader host-coverage statements

### Configuration
- N/A

## Implementation Steps

1. The three readers reach transcripts only through `detect_sessions`/`iter_events`, including `ll-ctx-stats` for non-Codex hosts; `test_cli_ctx_stats.py` keeps passing.
2. `ll-ctx-stats` surfaces `explain_no_sessions` output when discovery is empty, matching `ll-messages`/`ll-logs`.
3. A read-side composition test drives both divergent fakes' session records through the migrated readers, alongside the existing write-side suite.
4. A gate test asserts no reader module carries a `.claude/projects` literal, with an allowlist for the seam's own path resolvers that fails when stale.
5. `pytest scripts/tests/` passes.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 52/100 → LOW

### Concerns
- `depends_on` ENH-3532 and ENH-3534 are not yet done; the ctx-stats provenance criterion consumes their observations.

### Gaps to Address
- Program Design gate fails: `## Program Design` is missing. Populate it with the seam types, signatures and call path (`/ll:refine-issue` or `/ll:reconcile-issue`), or set `program_design_not_applicable: true`.
- No Integration Map, Files to Modify, or implementation steps. Which reader modules migrate (e.g. `little_loops/user_messages.py`, the ll-logs and ll-ctx-stats CLIs) and which session-watcher entry points they attach to are not enumerated.
- Missing sections: Current Behavior, Expected Behavior, Impact, Scope Boundaries, Status.

### Outcome Risk Factors
- Broad enumeration across three readers plus a Codex parser, with an unspecified per-reader migration design (moderate per-site complexity).
- Wide blast radius: `user_messages` has many dependents.

## Session Log
- `/ll:refine-issue` - 2026-09-25T01:12:50 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:format-issue` - 2026-09-25T01:06:51 - `4d305eb6-e0ad-4528-8217-7edc572927c3.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:51 - `f35cbaf1-740e-46e5-84c9-0ecf04a645f4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-24T23:55:45 - `2bb94109-d967-427c-a647-9b0a7a8e368e.jsonl`

---

## Status

**Open** | Created: 2026-09-24 | Priority: P2
