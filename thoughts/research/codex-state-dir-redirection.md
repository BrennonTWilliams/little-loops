# Research: Per-Host State Directory Redirection for Codex

**Date**: 2026-09-02
**Issue**: ENH-1722
**Verdict**: Leave all five non-config state surfaces (`.issues/`, `.loops/`,
`.loops/tmp/scratch/`, `.ll/ll-continue-prompt.md`, `.ll/history.db`) shared
at their default project-root paths. Do not extend `LL_STATE_DIR` scoping
beyond the config probe. This decision generalizes to all hosts routed
through `_config_candidates()` (codex, gemini, omp, kimi-code, qwen), not
just Codex.

---

## Summary

`LL_STATE_DIR=.codex` (and its gemini/omp/kimi-code/qwen equivalents)
currently redirects only the config-file probe (`_config_candidates()`,
`scripts/little_loops/config/core.py:120-154`). EPIC-1463 deferred a decision
on whether the four other state surfaces plus the session store should
receive the same per-host treatment. This note enumerates each surface,
evaluates the case for scoping it, and records the decision.

## Per-Surface Analysis

### `.issues/`

**Resolution path**: `IssuesConfig.base_dir` (`scripts/little_loops/config/features.py`,
default `".issues"`) → `BRConfig.get_issue_dir()` (`config/core.py:512-525`).

Issues describe the *project* — bugs, features, and enhancements are true
regardless of which AI host a given session happens to run under. A user who
drives some sessions through Claude Code and others through Codex on the
same checkout expects to see the same backlog either way. Scoping this to
`.codex/issues/` would fork the backlog per host, so an issue captured in
one host silently disappears from the other's view — the opposite of what
either host's user wants. **Leave shared.**

### `.loops/`

**Resolution path**: `LoopsConfig.loops_dir` (`config/features.py:998,1007`,
default `".loops"`) → `BRConfig.get_loops_dir()` (`config/core.py:570-572`).

FSM run definitions and run history are also project-level: a loop created
under Claude Code should be runnable (and its history visible) from Codex,
since loops are host-agnostic automation, not host-specific state. Per-host
scoping would require duplicating loop YAMLs per host directory or forcing
every consuming tool (`ll-loop`, `ll-auto`, `ll-parallel`) to resolve a
host-branched path with no corresponding user benefit. **Leave shared.**

### `.loops/tmp/scratch/`

**Resolution path**: hardcoded literal, not config-driven —
`scripts/little_loops/subprocess_utils.py:296-298` (`_list_scratch_files()`),
`hooks/scripts/scratch-pad-redirect.sh:105,119`, `hooks/scripts/scratch-cleanup.sh`.

Scratch is derivative of `.loops/` (it lives under it) and exists purely to
keep large command output out of conversation context within a single run.
It has no cross-host identity concern — a scratch file from a Codex-driven
loop run and one from a Claude-Code-driven run never need to be
distinguished by host, only by run/PID, which the `-<pid>` suffix already
handles. Scoping it per host would also require converting a hardcoded
literal into a config-driven, host-aware path in four call sites for no
functional gain. **Leave shared.**

### `.ll/ll-continue-prompt.md`

**Resolution path**: hardcoded literal —
`CONTINUATION_PROMPT_PATH = Path(".ll/ll-continue-prompt.md")`
(`subprocess_utils.py:103`); also built inline in
`scripts/little_loops/hooks/pre_compact.py:100,127,180` and
`scripts/little_loops/hooks/pre_compact_handoff.py:153,160`.

The continuation prompt is a single-slot handoff artifact: whichever host
picks up a `CONTEXT_HANDOFF` is expected to read the one file left behind by
whichever host wrote it. Handoffs are explicitly designed to be
host-crossing (e.g. a Claude Code session hands off, a fresh session — same
or different host — resumes). Scoping this per host would break exactly the
handoff case it exists to serve. **Leave shared.**

### `.ll/history.db`

**Resolution path**: the one surface with an existing override chain, but
the chain itself is host-blind — `_resolve_db_path()` / `resolve_history_db()`
(`scripts/little_loops/session_store/db.py:72-132`), precedence
`LL_HISTORY_DB` env → `history.db_path` config key (which *does* route
through the host-aware `resolve_config_path()`, so a hand-written
host-specific config file could redirect it today) → `.ll/history.db`
default. Most call sites bypass the resolver entirely with a hardcoded
`cwd / ".ll" / "history.db"`: `scripts/little_loops/hooks/session_start.py:135,147`,
`hooks/user_prompt_submit.py:113,128,134`, `hooks/subagent_stop.py:43`,
`hooks/sweep_stale_refs.py:163,231`, `decisions.py:575`.

History aggregates session metadata (effort scores, cycle times, decision
logs) across an issue's *entire* lifecycle, which routinely spans multiple
hosts — an issue refined under Claude Code and implemented under Codex is
the common case this database is meant to report on
(`ll-history-context --for-skill`). Splitting it per host would break
cross-host effort tracking, which is the feature's entire purpose. This is
also the surface with the highest migration cost (most call sites bypass
the resolver chain entirely), reinforcing that the case for change is weak
relative to the cost. **Leave shared.**

## Cross-Cutting Considerations

**Precedent for "leave shared" being the default, not the exception**: four
of the five currently-integrated hosts already carry their own
config-probe-only precedent issue — `ENH-2187` (gemini), `FEAT-2262` (omp),
`ENH-3157` (qwen), `ENH-2913` (kimi) — each independently extended
`_config_candidates()`'s config-probe-only redirection to their own host
without touching any other surface. `FEAT-1479` (Pi) wired
`LL_STATE_DIR=.pi` at the schema level with the same scope limit. No prior
issue attempted to extend redirection past the config probe. This note's
decision is consistent with, not a departure from, that pattern.

**Architectural alternative considered and rejected**: `host_layout_for()` /
`HostLayout` (`scripts/little_loops/session_store/writers.py`) is a
table-driven per-host pattern already in the codebase, but it serves a
structurally different purpose — *reading* each host's own native
session-transcript directory (e.g. `~/.codex/projects/<dash-encoded cwd>/`),
not scoping a little-loops-owned state surface. Its ~15 call sites
(`session_store/lifecycle.py`, `session_store/__init__.py`,
`user_messages.py`, `cli/session.py`, `cli/logs.py`,
`cli/backfill_worker.py`, `hooks/session_start.py`, `hooks/__init__.py`)
each independently re-read `LL_HOOK_HOST` rather than receiving it from a
shared boundary — the opposite of `_config_candidates()`'s single-choke-point
design. Since this note's decision is "leave shared," neither pattern needs
to be extended to the four non-config surfaces, but if a future issue
reopens this question, `_config_candidates()`'s branch-per-host style is the
cheaper adaptation: it needs one new host-aware branch per resolver behind a
single env-read boundary (callers already route through `BRConfig`/shared
constants), whereas adopting `host_layout_for()`'s table-driven style would
require threading `host` into every one of those ~15 call sites plus the
now-host-blind `.issues/`/`.loops/`/scratch/continuation-prompt resolvers,
since no single choke point exists for those surfaces today the way
`resolve_config_path()` is for config.

**Generalization beyond Codex**: this decision is not Codex-specific. It
applies uniformly to all five hosts currently routed through
`_config_candidates()` — codex, gemini, omp, kimi-code, qwen — and to Pi
(`FEAT-1479`) if/when it gains state-dir scoping beyond its config probe.
None of these hosts' project-level artifacts (issues, loops, scratch,
handoff prompts, history) have any host-specific identity; the rationale
above (shared backlog, cross-host handoffs, cross-host effort tracking) is
host-agnostic by construction.

## Decision

**Leave shared** — for all five surfaces (`.issues/`, `.loops/`,
`.loops/tmp/scratch/`, `.ll/ll-continue-prompt.md`, `.ll/history.db`) and for
all currently-integrated hosts (codex, gemini, omp, kimi-code, qwen) plus Pi.
`LL_STATE_DIR` scoping remains bounded to the config probe
(`_config_candidates()`) exactly as FEAT-957 originally scoped it for Codex.
No child implementation issue is filed, since no surface's decision is
"scope per host."

This confirms rather than overturns the "Strong prior" the issue captured at
capture time: a project's `.issues/`/`.loops/` (and, per this note's
extended analysis, scratch/continuation-prompt/history) are host-independent
project artifacts, and multi-host users depend on that sharing for a
coherent backlog, cross-host handoffs, and cross-host effort tracking.

## Related Issues

| Issue | Status | Relevance |
|-------|--------|-----------|
| FEAT-957 | Completed | Landed the original config-probe-only `LL_STATE_DIR=.codex` scoping this note evaluates extending |
| EPIC-1463 | Open | Parent epic; deferred this decision pending this note |
| ENH-2187 / FEAT-2262 / ENH-3157 / ENH-2913 | Completed | Sibling config-probe-only precedents for gemini/omp/qwen/kimi — none extended past the config probe |
| FEAT-1479 | — | Pi's config-candidate schema and tests; same config-probe-only scope |
| FEAT-2122 | — | Codex native spawn model research (worktree/state-isolation semantics); paired research session per this issue's Notes |

## Conclusion

No code changes are needed. The four non-config state surfaces plus the
session store remain correctly unscoped by host. The only follow-up is
documentation: updating `HOST_COMPATIBILITY.md`'s `[^state]` footnote and
the Codex adapter README's `State Directory` section to record this as a
resolved decision rather than an open question.
