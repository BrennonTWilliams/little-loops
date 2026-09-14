---
id: ENH-3467
title: Warn with a named cause when sessions exist but none match, instead of rendering
  empty
type: ENH
priority: P2
status: open
verify_verdict: EVIDENCE_UNVERIFIED
reconcile_attempted: true
discovered_date: '2026-09-13'
labels:
- observability
size: Very Large
confidence_score: 90
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

## Summary

`ll-logs`' discovery munges a cwd into a `~/.claude/projects/` directory name and reads whatever it finds. A munging mismatch, a project moved on disk, or a run launched from a subdirectory all degrade to the same empty output as "this project genuinely has no sessions." Those are different states and are being rendered identically, which means the failure mode of the whole log-mining surface is silence.

Split them. When session files exist on disk but every one was rejected for the current workspace, emit a warning visible without `--verbose` that says so and names the likely cause — agent launched from a different directory, project moved since the sessions were written, unrecognized path encoding. "No data" and "I found data and rejected all of it, here is why" should never print the same thing.

## Current Behavior

Discovery collapses every rejection cause into the same silent-or-generic result. `_get_claude_project_folder()`/`_detect_claude_sessions()` return a bare `[]`/`None` whether the encoded directory never existed, existed but matched no session files, or matched only agent-type sessions — no diagnostic structure carries a reason past that point (`scripts/little_loops/session_store/sessions.py`, `scripts/little_loops/user_messages.py`). Three call sites currently surface this differently and none names a cause: `_detect_project_handles()` (`cli/logs.py:569-584`) logs a generic `"No sessions found for:"` via `logger.error()`, which happens to be visible today only because `ll-logs` leaves `Logger.verbose` at its default `True`; `main_messages()` (`cli/messages.py:191`) logs the identical generic text but constructs `Logger(verbose=args.verbose)` (default `False`), so it is silenced by default; and `main_session()`'s Codex backfill branches (`cli/session.py:694`, `:747`) have no zero-handles check at all — an empty `detect_sessions()` result is passed straight into `backfill_incremental()`/`backfill()` and silently absorbed.

## Expected Behavior

When session files exist on disk but every one was rejected for the current workspace, each of the three call sites above emits a warning — visible without `--verbose` — that names the likely cause (munging mismatch, project moved since the sessions were written, run launched from a subdirectory, or unrecognized path encoding), distinguishing that state from genuine "no sessions recorded anywhere for this cwd." The two states must never render identically again.

## Why it matters

This defends a class rather than an instance. The precedent is a multi-runtime session visualizer that hit exactly this failure: a vendor change inflated the first line of its rollout files past a fixed read buffer, cwd extraction failed, sessions were skipped, and the panel rendered empty with no error at all. Raising the buffer fixed that one instance; the named-cause warning is what makes the next break in discovery announce itself instead of presenting as absence.

Cheap, self-contained, and independent of the larger ingestion work — the session-watcher seam shipped as FEAT-3417 changes where sessions are read from, not what the zero-match path reports. Distinct from run-to-transcript pairing precision (which fixes *which* transcript is chosen, not what happens when none is) and from malformed-input tolerance (which survives bad input rather than reporting why input was rejected).

## Scope Boundaries

- **In scope**: distinguishing "sessions exist, none matched this cwd" from "no sessions recorded anywhere" at the three call sites named in Current Behavior (`_detect_project_handles()`, `main_messages()`, `main_session()`'s Codex backfill branches); making that warning visible without `--verbose` for `ll-logs`/`ll-messages`; preserving the `"No sessions found for:"` grep contract `ll-logs-telemetry-digest.yaml` depends on.
- **Out of scope**: the session-watcher/ingestion seam shipped as FEAT-3417 (changes where sessions are read from, not what the zero-match path reports); run-to-transcript pairing precision (which transcript is chosen, not what happens when none is); malformed-input tolerance (surviving bad input rather than reporting why it was rejected); the exact cause taxonomy, precedence among causes, and any "how close counts as a match" threshold — explicitly left to implementer judgment per Program Design → Decision Rules.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- Discovery collapses two distinct causes into one signal today: `_get_claude_project_folder()`/`_detect_claude_sessions()` return the same empty result whether the encoded directory never existed or existed but had no matching session files (`scripts/little_loops/session_store/sessions.py`, `scripts/little_loops/user_messages.py`).
- `_detect_project_handles()` (`scripts/little_loops/cli/logs.py:569-584`) already applies a two-tier detection contract one layer up — it queries `detect_sessions(..., include_agents=True)` first specifically so "sessions exist but are all agent-type" is distinguishable from "no sessions of any kind." A named-cause split for cwd-mismatch is the same shape applied one layer earlier in the same call chain, not a new pattern for this codebase.
- `list_workspaces()` (`scripts/little_loops/session_store/sessions.py`) already recovers each project directory's own recorded cwd from its first session record. That is the only existing source of "sessions exist somewhere with a nearby cwd" — nothing today reads it to compare against the queried cwd.
- This codebase's precedent for pairing a classification with an explanation is `classify_failure() -> tuple[FailureType, str]` (`scripts/little_loops/issue_lifecycle.py:141-159`) and `MatchClassification` (`scripts/little_loops/issue_discovery/matching.py:24-35`) — an enum plus a free-text reason, not a single message string.
- `Logger.warning()`/`Logger.error()` (`scripts/little_loops/logger.py:91-99`) are both gated by the same `self.verbose` flag; "visible without `--verbose`" is a property of how the CLI constructs `Logger`, not of which method is called. `ll-logs` has no `--verbose` flag at all and constructs `Logger(use_color=use_color_enabled())`, leaving `verbose` at its default `True` — so anything written through `logger.warning()`/`logger.error()` in `ll-logs` is already unconditionally visible today. `ll-messages` constructs `Logger(verbose=args.verbose)` (default `False`), so the identical message there is silenced by default (`scripts/little_loops/cli/messages.py:191`) — this is the sharper instance of the issue's own failure class.
- The literal string `"No sessions found for:"` is load-bearing for automation: `scripts/little_loops/loops/ll-logs-telemetry-digest.yaml:64-71` greps stderr for it to route an FSM outcome, and `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:177-189` locks that grep's ordering. Any change to this message's wording or placement must keep that grep passing or update both together.
- The exact cause taxonomy, precedence among causes, and any "how close counts as a match" threshold are not fixed by the issue text or by any existing code — open to implementer judgment (see Program Design → Decision Rules).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/logs.py` — `_detect_project_handles()` (lines 569-584) is the shared zero-match call site for `_cmd_sequences`, `_cmd_extract`, `_cmd_scan_failures`; currently calls `logger.error(f"No sessions found for: {cwd_path}")` unconditionally on an empty `detect_sessions()` result.
- `scripts/little_loops/cli/logs.py` — `_cmd_eval_export()` duplicates the same check independently via `print(f"No sessions found for: {cwd_path}", file=sys.stderr)` rather than through `logger`.
- `scripts/little_loops/cli/logs.py` — `_discover_workspace_handles()` / `discover_all_projects()` (the `--all` path) never reaches any "no sessions" branch per-workspace; a workspace whose cwd doesn't match anything silently never enters `decoded_by_key`/`handles_by_key` — true silence, the issue's failure mode in its most literal form.
- `scripts/little_loops/session_store/sessions.py` — `_detect_claude_sessions()`, `_detect_layout_sessions()`, `detect_sessions()` — the point where "directory doesn't exist for this cwd's encoding" and "directory exists but is empty" both degrade to the same `[]`; no diagnostic structure carries a reason today.
- `scripts/little_loops/user_messages.py` — `get_project_folder()`, `_get_claude_project_folder()`, `encode_project_path()`, `_cwd_spellings()` — the cwd-to-directory munging logic named in the issue; each probe returns `Path | None` from a pure `.exists()` check with no accompanying explanation of why a spelling missed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py` — `main_session()`'s `ll-session backfill` command (both `--host codex` branches, lines 694 and 747, and the non-codex `get_project_folder` branches, lines 704 and 759) needs the same cause-aware handling applied to `_detect_project_handles()` — see Dependent Files below for the confirmed silent-empty behavior.

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

> ⚠ Stale path — the automation dependency cited above as `scripts/little_loops/loops/ll-logs-telemetry-digest.yaml:64-71` does not exist at that path; the file is a project-local loop at `.loops/ll-logs-telemetry-digest.yaml`, and the grep is at line 68 (`if grep -q "No sessions found for:" "$ERR"; then`), not 64-71. Verify against current codebase before editing.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/messages.py:191` — `main_messages()` duplicates the identical message text via `logger.error(f"No sessions found for: {cwd}")`, but constructs `Logger(verbose=args.verbose)` (default `False`) — silenced by default, the sharpest existing instance of the issue's failure class.
- `scripts/little_loops/cli/ctx_stats.py:413-415` — `_compute_cache_rate_from_jsonl` hits the same zero-handles case and returns `None` with no warning/error call at all.
- `.loops/ll-logs-telemetry-digest.yaml:68` — greps stderr for the literal string `"No sessions found for:"` (`if grep -q "No sessions found for:" "$ERR"; then`) to route `FAILURES_NO_DATA` vs `FAILURES_ERROR` — automation depends on this exact text.
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:177-189` — `test_scan_failures_no_data_grep_precedes_rc_check` locks the grep-vs-rc-check ordering against the loop YAML's own source text.

**Conventions in Force**
- `Logger.warning()`/`Logger.error()` are both gated on the same `self.verbose` flag, with no "always visible" tier — evidence: `scripts/little_loops/logger.py:91-99`, tests `scripts/tests/test_logger.py:290-313`. Visibility without `--verbose` is controlled entirely by how the calling CLI constructs `Logger`, not by which method is called.
- No single settled level for "named-cause, zero-result" sites in this file: `_detect_project_handles` uses `logger.error` (`logs.py:582`) while `_cmd_stats`/`_cmd_dead_skills` use `logger.warning` for analogous cases (`logs.py:1540-1545`, `:1006-1010`) — a contested convention across the same file, not a settled rule.
- When this codebase needs to name *why* something happened rather than just that it happened, the established shape is `classify_X(...) -> tuple[EnumType, str]` — evidence: `classify_failure()` (`scripts/little_loops/issue_lifecycle.py:141-159`), `MatchClassification` (`scripts/little_loops/issue_discovery/matching.py:24-35`).
- A two-tier "exists but filtered" vs "doesn't exist at all" split already exists one layer up the same call chain: `_detect_project_handles` calls `detect_sessions(..., include_agents=True)` first specifically to distinguish "sessions exist but all agent-type" from "no sessions at all" (`logs.py:569-584`).
- `_cmd_extract`'s `zero_match` boolean (`logs.py:766,779,784-787`) is this codebase's existing precedent for surfacing a filtered-vs-absent distinction as a derived boolean in JSON output, alongside separate human-readable print strings.

**Tests**
- `scripts/tests/test_ll_logs.py` — no existing test locks `_detect_project_handles`'s exact message text or exercises the mismatch-vs-empty distinction; `test_stale_worktree_path_emits_no_warning` (lines 344-380) is the closest existing shape — it passes a stdlib `logging.Logger` into the `Logger`-typed parameter and asserts via `caplog`.
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:177-189` — asserts the grep-ordering contract on the literal `"No sessions found for:"` string; changing that string's wording or removing it requires updating this test and the loop YAML together.
- `scripts/tests/test_logger.py:290-313` (`TestLoggerWarning`) — the direct unit-test shape for asserting warning output goes to stderr, uses YELLOW color, and is silent when `verbose=False`.
- `scripts/tests/test_user_messages.py`, `scripts/tests/test_session_discovery.py` — existing coverage of the munging (`encode_project_path`/`_cwd_spellings`/`get_project_folder`) and matching (`detect_sessions`/`_detect_claude_sessions`) logic this change builds on.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/session.py` — `main_session()`'s `ll-session backfill --host codex` branches call `codex_handles = detect_sessions(Path.cwd(), "codex")` at lines 694 and 747, then pass the result straight into `backfill_incremental()`/`backfill()` with no zero-handles check; both unconditionally log `logger.success(f"Backfilled {N} rows ...")` even when 0 handles were found — a third silent instance of this issue's failure class, on the exact command (`ll-session backfill`) named in the issue title. The adjacent non-codex path in the same function (`get_project_folder(host=args.host)` at lines 704 and 759) also collapses "no project folder" into one generic message (`"No session project folder found; cannot discover JSONL files."`, lines 706-708) or a silent `None` fallthrough (759-766) with no cause distinction. [Agent 1 + Agent 2 finding, confirmed by direct read]
- `scripts/little_loops/hooks/session_start.py:151-171` — `get_project_folder(root, host=_backfill_host)` (line 170) runs inside `with contextlib.suppress(Exception):` (line 151), explicitly documented as "Best-effort" session-store bootstrap (comment lines 128-130); a `None` result silently becomes `_backfill_path = None` (line 171) with no warning. No edit needed — this is a deliberate best-effort suppression guard around a non-user-facing hook, not the CLI-visible path this issue targets. [Agent 1 finding; caller-suitability gate: guard branch]
- `scripts/little_loops/session_store/__init__.py` (re-exports `detect_sessions` at line 137/281, `list_workspaces` at line 139/280) and `scripts/little_loops/cli/__init__.py` (re-exports `main_messages` at line 77/138) — no edit needed unless the implementation adds a new public symbol (e.g. a cause-classification helper) or changes `detect_sessions`'s return shape, in which case these export lists must be updated in lockstep. [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_ conditional on the still-open return-shape decision (see Program Design → Decision Rules) — only load-bearing if the implementation changes `detect_sessions()`'s/`_detect_project_handles()`'s return contract.
- `docs/reference/API.md:9580-9583` — documents `detect_sessions()`'s current `-> list[SessionHandle]` signature; update if the return shape changes.
- `docs/reference/HOST_COMPATIBILITY.md:546,564-567` — per-host `detect_sessions()` discovery semantics, including the Codex-specific fallback chain; update if a cause taxonomy changes host-specific behavior.
- `docs/ARCHITECTURE.md` § "Session-Discovery Seam" (~line 1506) — conceptual narrative of `detect_sessions()`/`list_workspaces()`; update if the seam's contract changes.
- `docs/codex/usage.md:95-100` — documents Codex's `detect_sessions()` fallback chain (DB absent/unusable/missing columns); relevant if the cause taxonomy needs a Codex-specific reason.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py:751-777` (`test_backfill_host_codex_discovers_via_detect_sessions`) — only covers a non-empty `codex_handles` result; add a new test (e.g. `test_backfill_host_codex_zero_handles_warns`) for the empty-handles case once `session.py`'s codex branches gain a zero-handles check.
- `scripts/tests/test_cli_messages.py` — no existing test covers `main_messages()`'s zero-handles path (the "sharper," currently-silenced-by-default instance the issue's own research calls out); new test needed.
- `scripts/tests/test_ll_logs.py:1294-1309` (`test_sequences_project_not_found_returns_1`) and `:1892-1907` (`test_extract_project_not_found_returns_1`) — assert only `result == 1` today, with no assertion on message content or visibility; extend once the named-cause distinction lands.
- `scripts/tests/test_cli_ctx_stats.py` (14 sites, e.g. lines 693, 697, 734, 758, 800, 840, 855, 880, 906, 989, 1005, 1035, 1066) and `scripts/tests/test_cli_messages.py` / `scripts/tests/test_cli.py` (`TestMainMessagesIntegration`, e.g. lines 676, 710, 730, 749) — all mock `detect_sessions()` as returning a bare `list[SessionHandle]`; will break if the implementation changes it to a tuple/classification return shape.
- `scripts/tests/spike/enh3430_workspace_union/{union.py,test_union.py,fixtures.py}` — spike module calls `detect_sessions`/`list_workspaces` directly and asserts on call conventions; would break under the same return-shape change. Conditional — only if that decision is made.
- `scripts/tests/test_issue_lifecycle.py:1050-1116` (`classify_failure` tests) and `scripts/tests/test_issue_discovery.py:679-980` (`TestMatchClassification`) — existing convention to follow if the implementer adopts the `tuple[Enum, str]` classification shape this issue's own research names as precedent: a `Test<EnumName>` class asserting `.value` strings, plus scenario tests unpacking `classification, reason = fn(...)`.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Types**
- No new persisted data shape is confirmed by research. Whether a cause is represented as an enum, a `tuple[Enum, str]` (the codebase's existing precedent — see Conventions in Force above), or a plain boolean is undecided (see Decision Rules).

**Signatures**
- `_detect_project_handles(cwd_path: Path, host: str | None, logger: Logger) -> list[SessionHandle] | None` — `scripts/little_loops/cli/logs.py:569-584`
- `detect_sessions(cwd, host=None, include_agents=False, limit=None) -> list[SessionHandle]` — `scripts/little_loops/session_store/sessions.py`, the union-across-hosts entry point every affected CLI (`ll-logs`, `ll-messages`, `ll-ctx-stats`) calls
- `get_project_folder(cwd=None, host=None) -> Path | None` — `scripts/little_loops/user_messages.py`
- `_get_claude_project_folder(encoded_path, home=None) -> Path | None` — `scripts/little_loops/user_messages.py`, a pure `.exists()` check with no accompanying reason on miss
- `list_workspaces(host, existing_only=True, home=None) -> list[Path]` — `scripts/little_loops/session_store/sessions.py`, the only existing function that recovers each project directory's own recorded cwd (via `_first_record_cwd`); nothing today reads that recovered cwd to compare against the queried cwd

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Analyzer pass — exact data availability per layer (the "no diagnostic structure carries a reason" claim, made concrete):**

| Layer | Local data available on miss | What is actually returned |
|---|---|---|
| `_cwd_spellings(cwd) -> list[str]` (`user_messages.py:407-416`) | both candidate strings (`str(cwd.resolve())`, `str(cwd.absolute())`; collapses to 1 entry when they're equal) | both strings — this layer loses nothing |
| `encode_project_path(path_str) -> str` (`user_messages.py:368-376`) | pure `re.sub` transform, no filesystem access | the encoded string — this layer loses nothing |
| `_get_claude_project_folder(encoded_path, *, home=None) -> Path \| None` (`user_messages.py:501-504`) | the full constructed `Path` and its `.exists()` boolean | bare `None` on miss — the attempted path itself is discarded |
| `_detect_claude_sessions(cwd, home, limit, include_agents) -> list[SessionHandle]` (`session_store/sessions.py:250-290`) | which of the (≤2) encodings from `_cwd_spellings` was tried, whether a `project_dir` was ever found, whether a found dir's `*.jsonl` glob (line 269) came back empty | bare `[]` on every failure branch — "no directory for any encoding" and "directory exists but glob matched nothing" are the same return value |
| `_detect_project_handles(cwd_path, host, logger) -> list[SessionHandle] \| None` (`cli/logs.py:569-584`) | `all_handles` from `detect_sessions(..., include_agents=True)`; already has one two-tier check (agent-only vs. none-at-all) | `None` + `logger.error(...)` (gated on `Logger.verbose`) when `all_handles` is falsy — the upstream cause is already lost by this point |

No comparison of a found project directory's own recorded `cwd` (via `_first_record_cwd`) against the queried `cwd` exists anywhere in `session_store/` or `cli/logs.py` today — confirmed by repo-wide search, no hits.

**`_first_record_cwd()` is not a cheap per-query lookup** (`session_store/sessions.py:666-688`): it takes an already-located `project_dir: Path` and reads that one directory's JSONL files for the first recorded `cwd`. Its only caller is `_list_claude_workspaces()` (`sessions.py:608-621`), which iterates *every* entry under `<home>/.claude/projects` and calls `_first_record_cwd()` once per directory — i.e. a full `list_workspaces()`-equivalent scan. There is no narrower "look up this one cwd's neighborhood" primitive. A "project moved / run from a subdirectory" cause that wants to surface *which* other project looks like a match must either (a) call `_first_record_cwd()` directly on the one candidate directory already known to exist from the current probe (cheap, single directory), or (b) pay for the full `_list_claude_workspaces()`/`list_workspaces()` scan (the same cost `_discover_workspace_handles()` already pays for its `--all` path at `cli/logs.py:148`) — nothing today makes (b) cheap for a single-`--project` invocation. This is a real cost tradeoff, not a detail research can resolve in the implementer's favor.

**Path C (`main_session`'s Codex backfill branches, `cli/session.py:694` and `:747`) has no zero-check at all**, distinct from Path A/B: `codex_handles = detect_sessions(Path.cwd(), "codex")` is passed straight into `backfill_incremental()`/`backfill()` (`session.py:695-702`, `:748-757`) with no `if not codex_handles` branch — an empty result is silently absorbed by the backfill functions, it never reaches a `logger.error`/`logger.warning` call at all. This is a third, structurally different shape from Path A's `None`-return-plus-log and Path B's direct `if not handles` check, not a variant of either.

**Confirmed exact signatures** (supersedes any prior approximation):
- `detect_sessions(cwd: Path, host: str | None = None, *, include_agents: bool = False, limit: int | None = None, home: Path | None = None) -> list[SessionHandle]` — `session_store/sessions.py:310-317`. Docstring states it "Never raises for a missing host home; returns `[]`." When `host=None` it recurses into itself once per entry in `_REGISTERED_HOSTS` (`sessions.py:336-339`) and merges — a cause classification added at this layer must survive being merged across hosts, not just propagate from one.
- `_get_claude_project_folder(encoded_path: str, *, home: Path | None = None) -> Path | None` — `user_messages.py:501-504`
- `encode_project_path(path_str: str) -> str` — `user_messages.py:368-376`
- `_cwd_spellings(cwd: Path) -> list[str]` — `user_messages.py:407-416`
- `_first_record_cwd(project_dir: Path, session_glob: str = "*.jsonl") -> Path | None` — `session_store/sessions.py:666-688`
- `list_workspaces(host: str, *, existing_only: bool = True, home: Path | None = None) -> list[Path]` — `session_store/sessions.py:553-555`

**Searched, no hits**: `_extract_cwd_from_project` — the docstring at `session_store/sessions.py:565-567` states this function "was deleted in ENH-3430" once `_first_record_cwd`/`_list_claude_workspaces` became the seam; do not reintroduce it under that name.

**Full call chain, Path A** (`_cmd_sequences`/`_cmd_extract`/`_cmd_scan_failures`, `cli/logs.py:612`/`:696`/`:1436`): `_detect_project_handles` (`logs.py:569`) → `detect_sessions(cwd_path, host, include_agents=True)` (`logs.py:580`) → `_detect_claude_sessions` (`sessions.py:345`) → loop over `_cwd_spellings(cwd)` (`sessions.py:261`) → `encode_project_path` (`sessions.py:262`) → `_get_claude_project_folder(encoded, home=home)` (`sessions.py:263`) → on `project_dir is None` or empty glob, bare `[]` back up every layer → `_detect_project_handles` sees falsy `all_handles`, logs + returns `None` (`logs.py:581-583`) → each of the three callers does `if handles is None: return 1` (`logs.py:613-614`, `:697-698`, `:1437-1438`) with no cause carried into the exit path.

**Full call chain, Path B** (`main_messages`, `cli/messages.py:188`): `detect_sessions(cwd, host=host, include_agents=not args.exclude_agents)` (`messages.py:188`) → same `_detect_claude_sessions` chain as Path A → `if not handles: logger.error(...); return 1` (`messages.py:190-192`). Note this path has no two-tier agent/non-agent check unlike `_detect_project_handles` — a single `detect_sessions` call decides the outcome directly.

**Full call chain, Path C** (`main_session`, `cli/session.py:694`/`:747`, Codex-only): `detect_sessions(Path.cwd(), "codex")` dispatches to `_detect_codex_sessions()` (`sessions.py:343` → `sessions.py:234`) — a separate DB-query/date-dir-scan path from the Claude-Code chain above — with the zero-check gap described above.

### Call Path

`_cmd_sequences` / `_cmd_extract` / `_cmd_scan_failures` -> `_detect_project_handles()` -> `detect_sessions()` -> `_detect_claude_sessions()` -> `get_project_folder()` / `_get_claude_project_folder()` -> `encode_project_path()` / `_cwd_spellings()`

**Decision Rules**
- The issue names three example causes (munging mismatch, project moved on disk, run launched from a subdirectory) plus "unrecognized path encoding" as warning-worthy states, but pins no exact taxonomy, no precedence order when multiple causes could apply, and no threshold for how close a `list_workspaces()`-recovered cwd must be to the queried cwd to count as "likely the same project."
- No existing enum or classification function names these causes today — the nearest precedent shape is `classify_failure() -> tuple[FailureType, str]` (`scripts/little_loops/issue_lifecycle.py:141-159`), but adopting that shape is not mandated by any existing contract.
- Escape hatch / dismissal: not specified by the issue or by any existing code. This is genuinely open to implementer judgment, not a gap research can close.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

1. Discovery reports which of "no sessions recorded anywhere for this cwd" vs "sessions exist but none matched this cwd" occurred; covered by a new/updated test in `scripts/tests/test_ll_logs.py` that exercises both branches distinctly (closest existing shape: `test_stale_worktree_path_emits_no_warning`, `scripts/tests/test_ll_logs.py:344-380`).
2. The rejected-sessions case is visible on stderr for `ll-logs` without any `--verbose` flag (none exists today), and is no longer silenced by default for `ll-messages` (`scripts/little_loops/cli/messages.py:191`, whose `Logger(verbose=args.verbose)` defaults to `False`); covered by `scripts/tests/test_logger.py`-style `capsys` assertions.
3. The literal string `"No sessions found for:"` that `.loops/ll-logs-telemetry-digest.yaml:68` greps for either stays intact or is updated together with `scripts/tests/test_bug_3216_telemetry_digest_invocations.py:177-189`; covered by that test continuing to pass.
4. `python -m pytest scripts/tests/test_ll_logs.py scripts/tests/test_logger.py scripts/tests/test_bug_3216_telemetry_digest_invocations.py scripts/tests/test_session_discovery.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/session.py:694,704,747,759` — add cause-aware handling (warn/log) when `detect_sessions()`/`get_project_folder()` return empty/None in `main_session()`'s `ll-session backfill` branches, matching the fix applied to `_detect_project_handles()`.
- Add test `scripts/tests/test_ll_session.py::test_backfill_host_codex_zero_handles_warns` (or equivalent) covering the empty-`codex_handles` path — no existing test exercises it.
- Add a zero-handles test to `scripts/tests/test_cli_messages.py` for `main_messages()` — the currently-silenced-by-default instance the issue's own research calls "the sharper instance."
- Extend `scripts/tests/test_ll_logs.py::test_sequences_project_not_found_returns_1` and `::test_extract_project_not_found_returns_1` to assert on the new named-cause message/visibility, not just the return code.
- If a return-shape change is adopted for `detect_sessions()`/`_detect_project_handles()` (see Program Design → Decision Rules), update the mocks in `test_cli_ctx_stats.py`, `test_cli_messages.py`, `test_cli.py`, and the `enh3430_workspace_union` spike tests, plus the signature doc at `docs/reference/API.md:9580-9583`.

## Impact

- **Priority**: P2 - a diagnostic gap, not a functional regression; the failure mode it masks (silent data loss presenting as "no data") is what makes it worth fixing ahead of lower-priority backlog
- **Effort**: Very Large - per frontmatter `size`; touches three independently-shaped call sites (`logs.py`, `messages.py`, `session.py`) across two failure-surfacing patterns (`None`-return-plus-log vs. no check at all), plus an open return-shape decision that, if taken, requires updating mocks in `test_cli_ctx_stats.py`, `test_cli_messages.py`, `test_cli.py`, and the `enh3430_workspace_union` spike tests
- **Risk**: Low - additive diagnostic surface with no behavior change to the success path; the one hard constraint is preserving the `"No sessions found for:"` grep contract in `ll-logs-telemetry-digest.yaml`
- **Breaking Change**: No, unless the implementer opts into changing `detect_sessions()`'s/`_detect_project_handles()`'s return shape (see Program Design → Decision Rules), which is explicitly left open rather than mandated

## Status

**Open** | Created: 2026-09-13 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-14_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 48/100 → LOW

### Outcome Risk Factors
- Breadth/depth: touches 5+ distinct sites across `logs.py` (three sub-paths), `sessions.py`, `user_messages.py`, `session.py`, and `messages.py`, with moderate cross-module coupling; the still-open return-shape decision (tuple/enum vs. boolean) would push several sites from local edits toward deeper, contract-changing ones if adopted.
- Ambiguity: four design questions are explicitly left to implementer judgment — cause taxonomy, precedence among causes, match-closeness threshold, and escape-hatch/dismissal — expect iteration to settle these before the change lands.
- Change surface: if the return-shape decision is taken, it cascades to 11+ mock/assertion sites (`test_cli_ctx_stats.py`, `test_cli_messages.py`, `test_cli.py`, the `enh3430_workspace_union` spike tests) — a broad blast radius specific to that path.
- Test coverage: adjacent discovery/munging logic is tested, but none of the three target call sites has coverage for the exact new zero-handles/named-cause behavior yet — new tests are unwritten.

## Session Log
- `/ll:confidence-check` - 2026-09-14T18:51:10 - `773a7d89-19ad-4a67-9526-f3658a21a035.jsonl`
- `/ll:reconcile-issue` - 2026-09-14T18:44:38 - `14a77021-cd98-4426-bab7-79ff2ffc015d.jsonl`
- `/ll:refine-issue` - 2026-09-14T18:23:22 - `83d2895b-9b1c-4543-8457-386ded6cffca.jsonl`
- `/ll:format-issue` - 2026-09-14T18:18:23 - `4b1da6cb-cda6-4875-933f-04e458d61037.jsonl`
- `/ll:verify-issues` - 2026-09-13T18:24:25 - `c49d7797-7184-419e-a2e8-da9638c4b681.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-13T18:19:14 - `c9fb0170-7dbc-4578-b415-f8d274a2d15e.jsonl`
- `/ll:verify-issues` - 2026-09-13T18:12:57 - `3d7594a5-487a-4a88-b194-74b9a2895ed5.jsonl`
- `/ll:wire-issue` - 2026-09-13T18:08:55 - `b76265c8-9770-4227-81d1-5a2389d472c3.jsonl`
- `/ll:refine-issue` - 2026-09-13T17:59:21 - `71a3006b-e80b-44c1-97dd-9c2b4c7543cd.jsonl`
