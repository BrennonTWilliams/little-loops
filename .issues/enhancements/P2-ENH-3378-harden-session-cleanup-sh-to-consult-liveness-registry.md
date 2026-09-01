---
id: ENH-3378
type: ENH
title: harden session-cleanup.sh to consult the liveness registry before deleting
priority: P2
status: open
parent: ENH-3374
depends_on:
- ENH-3376
confidence_score: 90
outcome_confidence: 85
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 23
score_change_surface: 19
---

# ENH-3378: harden session-cleanup.sh to consult the liveness registry before deleting

## Summary

`hooks/scripts/session-cleanup.sh` (`cleanup()`, wired as a Claude Code Stop
hook) is a third, independent reimplementation of worktree liveness checking.
Its zero-marker path is stricter than the Python orchestrator's: it falls
straight through to an unconditional `git worktree remove --force` with no
registry/marker cross-check, no dry-run, and no logging gate. Once
ENH-3376 introduces an out-of-tree liveness registry, this
script must consult it before deleting, or it remains an unfixed instance of
the same BUG-3373 failure mode.

## Parent Issue

Decomposed from ENH-3374: make worktree liveness marker resilient so active
worktrees cannot be classified orphaned. Covers the parent's Wiring Phase
items "harden `hooks/scripts/session-cleanup.sh`'s `cleanup()`" and "rewrite
`test_session_cleanup_removes_worktree_with_no_marker`", plus the
`docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" doc update (and its
`ll-adapt` mirrors) since that doc describes this script's behavior
specifically. Split from ENH-3376 because it is a separate
language/tool (bash vs. Python) with its own independent test suite
(`test_hooks_integration.py`), and from ENH-3377 because it
only needs the registry, not the process-cwd fallback.

## Current Behavior

`hooks/scripts/session-cleanup.sh::cleanup()` (lines 44-52): if
`.ll-session-*` is present and the pid is alive, skip; otherwise (dead pid, or
no marker found at all) fall through unconditionally to
`git worktree remove --force "$w"` (line 52), with `cleanup || true` (line 61)
ensuring the hook never fails — but also never surfaces this as a warning.

## Expected Behavior

`cleanup()` deletes a worktree **only on positive evidence of death**, and
otherwise leaves it alone. Concretely, for each worktree:

1. Read the registry entry ENH-3376 introduces at
   `$(dirname "$w")/.registry/$(basename "$w")` — derived from the worktree
   path itself, **not** from `$WORKTREE_BASE`. The hook reads
   `parallel.worktree_base`, but FSM sub-loop worktrees (the BUG-3373 case)
   are created under `automation.worktree_base` via
   `Config.get_worktree_base()` (`scripts/little_loops/config/core.py:578`);
   the two only coincide by default. Format is plain text, line 1 = pid
   (final, decided in ENH-3376); read it with `head -n1` and require it to
   match `^[0-9]+$`.
2. If the registry pid is alive → skip. If the marker pid (existing check)
   is alive → skip.
3. If a registry entry exists but is unparseable → skip (cannot positively
   exclude liveness).
4. If a registry entry or marker exists and its pid is **dead** → delete
   (positive evidence: an ll process owned this worktree and is gone).
5. If **neither** a registry entry nor a marker exists → **skip, do not
   delete.** This reverses today's no-marker-means-delete behavior for this
   hook only. Rationale: this hook fires on every turn end of every
   unrelated project-root session (BUG-3373's confirmed root cause) and
   today deletes on *absence* of evidence, which is exactly the failure
   class. After ENH-3376 lands, every ll-managed worktree has a registry
   entry written before `git worktree add`, so a worktree with neither
   signal is pre-feature or externally created. Reaping those belongs to
   the explicit, user-invoked Python path (`ll-parallel --cleanup-orphans`,
   which gains ENH-3377's process-cwd fallback), not a Stop hook.

"Alive" for `kill -0`: bash `kill -0` fails with EPERM for a process owned
by another user, which today reads as "dead". Match the Python side
(`orchestrator.py:345-347` treats `PermissionError` as alive): a pid is
alive if `kill -0 "$PID" 2>/dev/null || ps -p "$PID" >/dev/null 2>&1`.

Preserve the "must never fail" invariant (`cleanup() || true`) — a registry
read error must not raise out of the hook.

## Motivation

A registry-only fix scoped to `_cleanup_orphaned_worktrees()` in
`orchestrator.py` leaves this second, independently-triggered deletion path
(fired on every Claude Code session Stop event, not just `ll-parallel
--cleanup-orphans`) exposed to the identical failure mode. Any worktree this
hook considers "marker-less" — including one whose registry entry says it's
still live — is deleted with no cross-check today.

## Proposed Solution

1. In `hooks/scripts/session-cleanup.sh::cleanup()`, restructure the
   per-worktree body (lines 44-52) around an explicit `EVIDENCE` /
   `ALIVE` pair: add a `pid_alive()` helper (`kill -0 ... || ps -p ...`,
   see Expected Behavior) and a `read_registry_pid()` helper that reads
   `$(dirname "$w")/.registry/$(basename "$w")`. Decision table:
   - registry or marker pid alive → `continue`
   - registry file present but line 1 not numeric → `continue`
   - registry or marker present, pid dead → `git worktree remove --force`
   - neither present → `continue` (log at debug level; no deletion)
2. Registry parsing is fixed by ENH-3376: plain text, `head -n1` is the pid.
   No JSON, no jq, no sed fallback needed. Do not reopen the format.
3. Apply the EPERM fix to the existing marker check too, so both signals use
   the same `pid_alive()` helper.
4. Rewrite `test_session_cleanup_removes_worktree_with_no_marker`
   (`scripts/tests/test_hooks_integration.py:3261`) — it currently asserts
   the unsafe no-marker-means-delete behavior as *correct*. Replace it with:
   - live registry entry, no marker → skipped;
   - dead-pid registry entry, no marker → deleted (the positive-evidence
     path; this is where BUG-579's "genuinely orphaned worktree gets
     reaped" coverage now lives for this hook);
   - neither registry nor marker → **skipped** (new behavior; name the test
     `test_session_cleanup_skips_worktree_with_no_evidence` and reference
     BUG-3373 in its docstring);
   - registry entry with non-numeric line 1 → skipped;
   - worktree under a base that is *not* `$WORKTREE_BASE` but whose
     `.registry/` sibling holds a live pid → skipped (covers the
     `automation.worktree_base` vs `parallel.worktree_base` split; the
     `git worktree list | grep` filter still needs the path to contain the
     basename pattern, so use a nested dir under the base for this case).
   Keep `test_session_cleanup_removes_worktree_with_dead_pid_marker` (3245)
   as-is: dead marker pid with no registry entry still deletes. Note that
   "marker dead but registry alive" cannot occur naturally — both are
   written by the same process with the same pid — so no test is needed for
   that combination beyond the corrupt-marker case above.

5. Optional (cheap while in the file): add an `_is_ll_worktree()`-equivalent
   name filter to the deletion loop. Today the script reaps anything under
   `<worktree_base>/` that `git worktree list` reports, including shapes the
   Python orphan path deliberately refuses to touch (e.g. `epic-refresh-*`
   worktrees, which do not match `_is_ll_worktree()` in
   `worktree_utils.py:419-430`). If skipped, that asymmetry stays open —
   note it in the doc update either way.

### Documentation

- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup" — update the
  liveness semantics prose ("skipping any worktree owned by a live parallel
  worker") to state the positive-evidence rule: the hook deletes only
  worktrees whose registry/marker pid is dead, and leaves worktrees with no
  ll ownership record to `ll-parallel --cleanup-orphans`. Mention that the
  registry path is derived per-worktree, so `automation.worktree_base`
  sub-loop worktrees are covered (confirmed: `Config.get_worktree_base()` at
  `config/core.py:578` uses `automation.worktree_base`, while this hook reads
  `parallel.worktree_base`).
- `.qwen/commands/ll/cleanup-worktrees.md`,
  `.gemini/commands/cleanup-worktrees.toml` — update if
  `commands/cleanup-worktrees.md`'s liveness prose changes as part of this
  work (these mirror it verbatim with no drift test, per ENH-2968).

_Wiring pass added by `/ll:wire-issue`:_
- `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md` — CONFIRMED (was
  unconfirmed at refine-issue time, see the Codebase Research Findings note
  below): read side-by-side against `commands/cleanup-worktrees.md`, the
  entire body is byte-for-byte identical (only frontmatter differs). Add this
  to the conditional "update if `commands/cleanup-worktrees.md` changes"
  group alongside the `.qwen`/`.gemini` mirrors above.
- `hooks/hooks.json` (Stop hook entry, lines 221-240) — confirmed no
  liveness/marker/registry prose anywhere in the file (pure wiring: command
  string, timeout, generic status message). No edit needed.
- `docs/development/TROUBLESHOOTING.md` § "Too many worktrees" — confirmed
  this describes only the Python `ll-parallel --cleanup-orphans`/`--cleanup`
  path, never names `session-cleanup.sh`, and doesn't describe its
  marker/registry logic. No edit needed for this issue (ENH-3376 already
  claims a related edit to this file's other section for its own registry
  description).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Confirmed exact `cleanup()` content (`hooks/scripts/session-cleanup.sh`, full function is lines 12-58, `return 0` at line 57): the marker check (lines 44-51) only `continue`s when a marker exists AND `kill -0 "$PID"` succeeds; the "jq-optional" block (lines 21-26, not 24-26) reads `WORKTREE_BASE` from `.ll/ll-config.json`, pre-seeded with the literal default `.worktrees` and only overwritten by `jq -r '.parallel.worktree_base // ".worktrees"'` when `jq` is on PATH — it substitutes one scalar config value and contains no JSON field-extraction fallback, confirming this issue's claim.
- Repo-wide search for a working no-jq JSON field-extraction fallback (grep/sed pulling an arbitrary key out of JSON, as opposed to a fixed default or shape-only check) found zero precedent anywhere under `hooks/scripts/` — every existing "jq-optional" block (`hooks/scripts/lib/common.sh:162-234` included) either requires jq or falls back to a caller-supplied default. If the registry-write issue lands JSON content for the registry (see Scope Boundaries), the grep/sed fallback this issue's Proposed Solution step 2 calls for would be new code with no existing shape to follow — not an adaptation of an existing pattern.
- A directly relevant precedent exists for the filename-embedded-pid registry format instead: `hooks/scripts/scratch-cleanup.sh:49` extracts a pid from a filename via `sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'`, then does `kill -0 "$pid"` at line 52 — the same two-step shape `read_registry_pid()` + `kill -0` would need, already proven working in this exact codebase for a sibling cleanup script.
- Exact `hooks/hooks.json` wiring: the Stop-hook invocation of `session-cleanup.sh` is at lines 221-230 (`bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-cleanup.sh`, timeout 15), with a separate telemetry-shim entry (`record-hook-event.sh Stop hooks/scripts/session-cleanup.sh`) at lines 231-240 — refines the issue's "lines 225, 235" reference.
- Confirmed no `_is_ll_worktree()`-equivalent name-shape filter exists in `session-cleanup.sh` today — the deletion loop (lines 39-54) applies only a substring `grep "$WORKTREE_PATTERN"` against `git worktree list` output, with no per-name regex check, matching this issue's characterization for optional item 5.
- Existing test class confirmed: `TestSessionCleanupWorktrees` (`scripts/tests/test_hooks_integration.py:3202`) uses a `cleanup_script` fixture pointing at this script; `test_session_cleanup_removes_worktree_with_no_marker` is at line 3261 as cited, alongside sibling tests `test_session_cleanup_skips_worktree_with_live_pid_marker` (3228) and `test_session_cleanup_removes_worktree_with_dead_pid_marker` (3245).

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Possible additional doc mirror not in Documentation's list above, unconfirmed: `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md` surfaced in a repo-wide search alongside the `.qwen`/`.gemini` mirrors but was not independently verified as a verbatim mirror of `commands/cleanup-worktrees.md` — worth a quick check during implementation alongside the two confirmed mirrors.

## Program Design

### Types

- Registry entry: plain text, line 1 = `pid` (lines 2-3 `create_time` /
  `run_id` unused by this consumer) — read-only, format final per ENH-3376.

### Signatures

- `cleanup()` (existing, `hooks/scripts/session-cleanup.sh`) — per-worktree
  body rewritten as the decision table in Proposed Solution step 1
- `pid_alive PID` (new bash helper) — `kill -0 "$1" 2>/dev/null || ps -p "$1" >/dev/null 2>&1`
- `read_registry_pid WORKTREE_PATH` (new bash helper) — prints line 1 of
  `$(dirname "$1")/.registry/$(basename "$1")` if it matches `^[0-9]+$`;
  prints `INVALID` if the file exists but line 1 does not; prints nothing
  if the file is absent

### Call Path

Claude Code `Stop` hook -> `session-cleanup.sh::cleanup()` ->
`read_registry_pid()` + marker glob -> `pid_alive()` on each ->
`continue` (alive / invalid / no evidence) or `git worktree remove --force`
(dead pid), exercised by the rewritten `TestSessionCleanupWorktrees` cases
(Proposed Solution step 4)

## Scope Boundaries

- The registry write/remove and its on-disk format are decided in ENH-3376, a
  hard dependency of this issue — not reopened here.

- The process-cwd fallback (ENH-3377) has no bash equivalent and is out of
  scope for this issue. Worktrees with no ownership record at all are
  deliberately left for the Python path (which gets that fallback) rather
  than approximated here.
- Changing which config key the hook reads for `WORKTREE_BASE` is out of
  scope; the per-worktree registry-path derivation makes it unnecessary for
  liveness, though the `grep "$WORKTREE_PATTERN"` filter still only sees
  worktrees whose path contains that basename.
- The `_is_ll_worktree()`-equivalent name filter (Proposed Solution
  item 5) is explicitly discretionary in this issue's own scope — implement only if
  cheap while already in the file; its absence does not block closing this
  issue.

## Files to Modify

- `hooks/scripts/session-cleanup.sh`
- `scripts/tests/test_hooks_integration.py` (`TestSessionCleanupWorktrees::test_session_cleanup_removes_worktree_with_no_marker`)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md`

## Impact

Closes the second, hook-triggered instance of the BUG-3373 misclassification
mechanism, so a dispatched Claude Code session's own Stop hook cannot delete
its sibling worktrees out from under still-running work.

## Related Key Documentation

- `hooks/hooks.json:225,235` (Stop hook wiring for `session-cleanup.sh`)
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` § "Session cleanup"

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-01T19:10:49 - `9df9cefa-f639-494c-867c-39fd1ac3ff91.jsonl`
- Pre-implementation review - 2026-09-01 - switched the hook to positive-evidence-only deletion (no marker + no registry → skip, not delete), registry path derived from the worktree path (covers `automation.worktree_base` sub-loop worktrees), EPERM-safe `pid_alive` helper for both signals, test matrix rewritten accordingly, format question closed (plain text, decided in ENH-3376).
- `/ll:wire-issue` - 2026-09-01T18:47:09 - `79009b58-7363-45db-90f1-4e47ed1282ba.jsonl`
- `/ll:refine-issue` - 2026-09-01T18:27:47 - `f0c0abcb-9bb0-4011-99a7-b965b2d4e8f5.jsonl`
- `/ll:format-issue` - 2026-09-01T18:11:45 - `a022c67c-3828-4e2e-96d1-3bcdf7adfc60.jsonl`
- `/ll:issue-size-review` - 2026-09-01T15:20:23 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
