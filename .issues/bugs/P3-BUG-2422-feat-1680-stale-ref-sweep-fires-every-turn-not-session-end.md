---
id: BUG-2422
captured_at: '2026-07-01T02:13:42Z'
completed_at: '2026-07-01T03:23:21Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: done
priority: P3
type: BUG
relates_to:
- FEAT-1680
- BUG-2420
- ENH-2105
labels:
- hooks
- session-lifecycle
- performance
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-2422: FEAT-1680 stale-ref sweep fires every turn (`Stop`), not at session end

## Summary

The FEAT-1680 stale-cross-issue-status-ref sweep is wired to the **`Stop`** hook
event, which fires **when Claude finishes responding — i.e. at the end of every
turn**, not when the session ends. FEAT-1680's stated intent was to run the
sweep **once at session end**. Because `Stop` fires per-response, the handler
runs a full issue-tree scan on *every* assistant turn instead of once per
session: wasted work, added per-turn latency, and a naming/semantics mismatch
(the handler is named `session-end.sh` / intent `session_end` but is a turn-end
hook). Claude Code now exposes a real `SessionEnd` event ("when a session
terminates"); re-homing the sweep there makes it fire once, matching the
original intent.

Surfaced while correcting BUG-2420's conflation of `Stop` (turn end) with
`SessionEnd` (session end). BUG-2420 deliberately leaves this binding untouched
(it only adds a *new* scratch-cleanup handler); this issue tracks the sweep's
re-home separately.

## Current Behavior

`hooks/hooks.json:169` binds `hooks/adapters/claude-code/session-end.sh` (which
pipes to `python -m little_loops.hooks session_end` → `sweep_stale_refs.handle`)
under the **`Stop`** event array. `Stop` fires "when Claude finishes responding"
(per the Claude Code hooks reference) — once per assistant response.

On each such turn, `sweep_stale_refs.handle`
(`scripts/little_loops/hooks/sweep_stale_refs.py`):

1. `find_issues(config, status_filter={"done"})` — scans the whole issue tree to
   collect done IDs (`:159`).
2. If any done IDs exist (effectively always, in a mature repo),
   `find_issues(config)` — a **second** full scan for all open issues (`:166`).
3. Reads each open issue's content and regex-scans it for stale references to
   done IDs (`_scan_file`, per-file `read_text` + `_ISSUE_ID_RE`).
4. Always returns `LLHookResult(exit_code=0)` — findings are advisory only.

So every turn pays for two whole-tree `find_issues()` passes plus per-file reads
(15s hook timeout budget), when FEAT-1680 intended this to happen once, at
session termination.

## Expected Behavior

The stale-ref sweep runs **once, when the session terminates** (`SessionEnd`),
matching FEAT-1680's Motivation ("Engineer marks FEAT-1112 `done` mid-session.
At session end the hook runs, [sweeps stale refs]"). It does not run on every
turn. Its handler name and firing event agree (`SessionEnd` event ↔ a
`session_end`/session-termination handler).

## Motivation

FEAT-1680's whole design point is a *session-end* cleanup: catch cross-issue
status refs that went stale during a session, once, at the end. Running it on
`Stop` defeats that framing — it fires N times per session (once per response),
doing redundant whole-tree scans and adding latency to every turn. It is not
broken (the sweep is idempotent and always exits 0), which is exactly why it has
gone unnoticed. Now that a real `SessionEnd` event exists, the correct behavior
is cheaply available.

## Root Cause

FEAT-1680 conflated `Stop` with session end. Its own text asserts "a `Stop` hook
that fires at the end of every Claude Code session" and "A `Stop` hook fires at
the end of every Claude Code session" — but `Stop` fires at **turn end** (every
response), while `SessionEnd` ("when a session terminates") is the distinct
event that fires once per session. FEAT-1680 named the adapter `session-end.sh`
and the intent `session_end` to reflect the *intended* semantics, but bound it
to `Stop` (the only end-of-something event it used at the time). The result is a
handler whose name promises session-end semantics but whose event delivers
turn-end firing.

## Integration Map

- `hooks/hooks.json:169` — the `Stop`-array entry binding
  `hooks/adapters/claude-code/session-end.sh` (the mis-timed registration to
  move).
- `hooks/adapters/claude-code/session-end.sh` — thin adapter piping stdin to
  `python -m little_loops.hooks session_end`.
- `scripts/little_loops/hooks/sweep_stale_refs.py` — `handle()` (`:130`);
  double `find_issues()` scan at `:159` / `:166`; always `exit_code=0`.
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` registers
  `"session_end": sweep_stale_refs.handle`. **The Python intent name stays the
  same** (`session_end`); only the *host event* it is bound to changes. No
  dispatch change required.
- `scripts/tests/test_hooks_integration.py` — `TestSessionEndSweep` (`:3469`)
  currently only asserts `session-end.sh` exits cleanly with no project config;
  it does **not** yet assert the `hooks.json` registration. Add the
  wiring/regression tests from **Tests to Add** here (assert `session-end.sh` is
  registered under `SessionEnd` and absent from the `Stop` array).
- `docs/claude-code/hooks-reference.md` — `Stop` = "When Claude finishes
  responding"; `SessionEnd` = "When a session terminates" (with exit-reason
  matchers `clear`, `logout`, `prompt_input_exit`,
  `bypass_permissions_disabled`, `other`).
- **Related but distinct**: ENH-2105 tracks wiring `session_end` for the *Codex*
  adapter (Codex has no separate `SessionEnd` event — its end-of-turn event is
  named `Stop`, so Codex intentionally keeps the `Stop` binding). This issue is
  **Claude-Code-only**; do not change Codex or OpenCode adapters.

### Codebase Research Findings

_Added by `/ll:refine-issue` — codebase analysis (all cited anchors verified current
as of 2026-06-30):_

- **Missing doc from Implementation Step 4 — `docs/guides/BUILTIN_HOOKS_GUIDE.md`.**
  This is the most user-facing doc describing the sweep and it currently frames it
  as a `Stop` hook in three places; it must be reconciled alongside
  `HOST_COMPATIBILITY.md`:
  - `:67` — lifecycle table row `| **Stop** | sweep-stale-refs | … |` (move to a new
    `SessionEnd` row).
  - `:281` `## Stop` section → `:297` `### Sweep stale cross-issue references` →
    `:299` `**Hook:** session-end.sh → little_loops.hooks.sweep_stale_refs.handle`
    (re-home under a new `## SessionEnd` heading, mirroring the existing
    `## PreCompact` at `:310`).
  - "Session ends" narrative walkthrough (~`:100`) also calls it a `Stop` hook.
- `docs/reference/HOST_COMPATIBILITY.md:30` — precise anchor for the parity-matrix
  row `| stop → session_end | ✓ (dispatched as session_end) | (deferred) … |`;
  update the Claude Code cell to reflect the `SessionEnd` binding (Codex/OpenCode
  stay `(deferred)`, ENH-2105).
- `docs/reference/API.md:7549` — lists `session_end` **only as a built-in intent
  name** (`_dispatch_table()`), which is host-agnostic and stays correct after the
  re-home. **No API.md edit is needed** — Implementation Step 4's inclusion of
  `API.md` is over-broad; the dispatch intent name does not change.
- `docs/claude-code/hooks-reference.md:1274-1304` — already defines the
  authoritative `SessionEnd` contract (`hook_event_name: "SessionEnd"`, `reason`
  field, exit-reason matchers). Reference only — do not edit.
- **Anchor verification**: `hooks/hooks.json:169` (session-end.sh, 3rd of 3 groups
  in the `Stop` array at `:144-175`), `sweep_stale_refs.py` `handle()` `:130` with
  the double `find_issues()` at `:159`/`:166` (guard `if not done_ids` between them
  at `:162`), `__init__.py` `_dispatch_table()` `"session_end"` entry `:89`, and
  `test_hooks_integration.py:3469` `TestSessionEndSweep` — all confirmed current;
  no stale line numbers.
- **BUG-2420 coordination — current state (updated by `/ll:ready-issue`
  2026-06-30)**: BUG-2420's uncommitted work is now present in the working tree —
  `hooks/hooks.json` **already has a `SessionEnd` key** containing
  `hooks/scripts/scratch-cleanup.sh` (unstaged diff). `session-end.sh` is still
  under the `Stop` array (bug unfixed). So BUG-2422 is **no longer first-mover**:
  the fix must **append** the sweep as a *second* `hooks` group inside the existing
  `SessionEnd` array (not create the key) and remove `session-end.sh` from `Stop`.
  Caveat: BUG-2420's `SessionEnd` block is uncommitted and could be reverted — if
  the `SessionEnd` key is absent at implementation time, create it (per Proposed
  Solution step 1). Either branch is already covered by "or append to it if
  BUG-2420 already created it" below.
- **Codex confirmed untouched**:
  `scripts/little_loops/hooks/adapters/codex/hooks.json` has neither a `Stop` nor a
  `SessionEnd` key and no `session-end`/`session_end` reference — nothing to disturb
  there.

### Wiring Pass Findings

_Wiring pass added by `/ll:wire-issue` (3-agent trace: caller/importer, side-effect
surface, test-gap). Net result: the edit targets above are already complete — **no new
file needs to change** as part of this fix. The pass surfaced one downstream
coordination consequence, one report-only historical doc, and a set of verified
negatives:_

- **Downstream coordination — ENH-2105's `hooks.json:144` anchor goes stale [Agent 2
  finding].** ENH-2105 (still `open`, P5) Option A step 2 instructs wiring Codex's `Stop`
  event to `session-end.sh` "mirroring the Claude Code `Stop` block in
  `hooks/hooks.json:144`". After this fix moves `session-end.sh` out of the `Stop` array
  (its command is at `:169`; the array opens at `:144`) into a new `SessionEnd` key, the
  `Stop` block no longer contains a `session-end.sh` registration to mirror. ENH-2105 must
  be re-pointed to the new `SessionEnd` block before it is implemented. No shipped file
  changes here — this only affects ENH-2105's own body text; recorded so the Codex wiring
  isn't later copied from a stale anchor.
- **`CHANGELOG.md:246` — report-only, no edit [Agent 2 finding].** The released
  `## [1.126.0]` entry already describes the sweep as running "at session close"
  (FEAT-1680) — the behavior this bug finally makes true. It is a shipped, already-released
  entry (repo convention does not hand-edit released CHANGELOG sections retroactively) and
  it *becomes* accurate once this fix lands. No action.
- **Verified negatives (checked and ruled out — do not re-investigate):**
  - `docs/ARCHITECTURE.md:91` — mentions the hook only in a directory-tree listing; the
    file path is unchanged, only its `hooks.json` event key moves. No edit.
  - `docs/reference/EVENT-SCHEMA.md:83` — documents the `session_end` **intent**
    payload/behavior, not its `hooks.json` event binding; the intent name is host-agnostic
    and unchanged. No edit (same rationale as the `API.md` note above).
  - `agents/plugin-config-auditor.md` — already lists `SessionEnd` among the recognized
    command-only event types and encodes only generic per-event field rules; it has no
    hardcoded expectation that `session-end.sh` lives under `Stop`, so it validates
    correctly after the move. No edit.
  - No JSON-schema file governs `hooks/hooks.json` (only `config-schema.json`, which
    validates `.ll/ll-config.json` — e.g. the unrelated `hooks.stale_ref_fix` enum at
    `:1242-1246`). Nothing to update for the new `SessionEnd` key.
  - `ll-doctor` (`scripts/little_loops/cli/doctor.py`) builds its Hooks table from
    `runner.describe_capabilities()` (host-capability probing), not by parsing `hooks.json`
    — no `Stop`-array assumption to fix.
  - No test pins the `"Sweeping stale cross-issue status references..."` `statusMessage`
    string (grepped project-wide) — confirms Impact assumption 5 (no error/log-string
    coupling).
  - Codex-adapter surfaces flagged by the caller trace
    (`scripts/little_loops/init/writers.py`, `test_codex_adapter.py`,
    `test_wheel_smoke.py`, `package_data.py`) all touch the *separate*
    `scripts/little_loops/hooks/adapters/codex/hooks.json`, which this Claude-Code-only fix
    does not modify (per Out of Scope).

## Steps to Reproduce

1. In a repo with ≥1 `status: done` issue, enable the FEAT-1680 sweep (shipped;
   `session-end.sh` bound under `Stop` in `hooks/hooks.json`).
2. Add a temporary log line (or `stat`/timestamp write) at the top of
   `sweep_stale_refs.handle`.
3. Have a multi-turn conversation. Observe the handler fires **once per
   assistant response**, not once at session close — each firing re-scanning the
   whole issue tree.

## Proposed Solution

Re-home the sweep from `Stop` to a genuine `SessionEnd` event on Claude Code:

1. **Add a `SessionEnd` event block** to `hooks/hooks.json` bound to
   `hooks/adapters/claude-code/session-end.sh` (the adapter and Python handler
   are reused verbatim — only the event key changes), e.g.:

   ```jsonc
   "SessionEnd": [
     {
       "hooks": [
         {
           "type": "command",
           "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh",
           "timeout": 15,
           "statusMessage": "Sweeping stale cross-issue status references..."
         }
       ]
     }
   ]
   ```

2. **Remove** the `session-end.sh` entry from the `Stop` array in
   `hooks/hooks.json` (leave the other `Stop` handlers — `context-handoff-sentinel.sh`,
   `session-cleanup.sh` — in place).

3. No change to `sweep_stale_refs.py` or the `session_end` dispatch registration
   — the handler is host-agnostic and already exits 0 unconditionally.

Note the coordination with **BUG-2420**: that fix also introduces a `SessionEnd`
block (for scratch cleanup). If both land, they should share a single
`SessionEnd` array with two `hooks` entries rather than two competing blocks —
whichever merges second appends its handler to the existing `SessionEnd` key.

## Implementation Steps

1. Add a `SessionEnd` key to `hooks/hooks.json` (or append to it if BUG-2420
   already created it) bound to `session-end.sh`.
2. Delete the `session-end.sh` entry from the `Stop` array.
3. Update tests: the FEAT-1680 integration/adapter tests that assert the sweep
   is registered under `Stop` must be updated to assert `SessionEnd`.
4. Reconcile docs that describe the sweep as a "`Stop` hook" / "session_end is
   the dispatch intent for the Claude Code `Stop` event"
   (`docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/API.md`,
   FEAT-1680's own references) to say `SessionEnd` for Claude Code — while
   preserving the note that Codex maps `session_end` onto its `Stop` event
   (ENH-2105).
5. Verify: add a temporary firing log and confirm the sweep runs once at session
   end, not per turn.

## Tests to Add

- Wiring test: `hooks/hooks.json` registers `session-end.sh` under `SessionEnd`,
  **not** under `Stop`.
- Regression test: the `Stop` array no longer references `session-end.sh`.
- Behavior test (or documented manual check): the sweep handler is invoked once
  per session rather than once per turn.

### Codebase Research Findings

_Added by `/ll:refine-issue` — idiomatic wiring-test location and assertion style:_

The canonical `hooks.json` wiring-test pattern lives in
`scripts/tests/test_claude_code_adapter.py` — `TestClaudeCodeAdapterIntegration`
(`:32-90`), which loads `HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"`, parses
with `json.loads(...)`, flattens commands across matcher groups, and asserts
`assert any("<script>.sh" in cmd for cmd in all_commands)`. Model the two new
wiring assertions on `test_hooks_json_has_precompact_handoff` (`:76-90` — the
"second entry in an event array" precedent):

```python
data = json.loads(HOOKS_JSON.read_text())
# Positive: session-end.sh is registered under SessionEnd
assert "SessionEnd" in data["hooks"]
se_cmds = [h["command"] for g in data["hooks"]["SessionEnd"]
           for h in g.get("hooks", []) if h.get("type") == "command"]
assert any("session-end.sh" in c for c in se_cmds)
# Regression: session-end.sh is gone from Stop (repo idiom: assert not any(...))
stop_cmds = [h["command"] for g in data["hooks"]["Stop"]
             for h in g.get("hooks", []) if h.get("type") == "command"]
assert not any("session-end.sh" in c for c in stop_cmds)
```

Placement: put the JSON-parse wiring assertions in `test_claude_code_adapter.py`
(where the existing hooks.json-registration tests already live), not in
`TestSessionEndSweep` (`test_hooks_integration.py:3255`), which is a subprocess
*behavior* test asserting the adapter exits 0 — keep that one as-is. The dispatch
tests (`test_hook_intents.py:81`, `:380-387`) exercise the `session_end` intent
directly and need no change (host-agnostic).

_Wiring pass added by `/ll:wire-issue` — test-gap trace (Agent 3) result:_

- **No existing test breaks.** No test in `scripts/tests/` parses `hooks.json` and asserts
  `session-end.sh` under `Stop` by name, nor counts/enumerates the `Stop`-array length, nor
  does any `conftest.py`/fixture bake in a `Stop` array containing `session-end.sh`
  (`test_sweep_stale_refs.py` references the sweep only in a module docstring at `:3`, with
  no wiring assertion). The move is safe on the test axis — the wiring assertion drafted
  above is the only new test needed.
- **First `SessionEnd` wiring test in the repo.** `grep "SessionEnd" scripts/tests/` finds
  no prior `hooks.json` `SessionEnd` wiring test to model from — the drafted assertions
  will be the first. Confirming the template choice above: model on
  `test_hooks_json_has_precompact_handoff` (`:76-90`), **not**
  `test_hooks_json_has_post_tool_use` (`:47-74`) — the `Stop`/`SessionEnd` groups carry
  **no `matcher` key** (unlike the `PostToolUse`/`PreCompact` `"matcher": "*"` groups), so
  the flatten-and-substring shape (no matcher-group check) is the correct precedent.

## Impact

- **Priority**: P3 — Real per-turn overhead (two whole-tree `find_issues()`
  scans + per-file reads on every response) and a semantic/naming mismatch, but
  non-breaking: the sweep is idempotent and always exits 0, so no output or
  status is corrupted — only wasted work and mistimed firing.
- **Effort**: Small — move one `hooks.json` entry from `Stop` to `SessionEnd`,
  update a few tests and docs; no handler-logic change.
- **Risk**: Low — the handler is unchanged and already fail-safe; the only
  behavioral change is *when* it fires (once vs. per-turn).
- **Breaking Change**: No.

## Related Issues

- **FEAT-1680** — introduced the sweep and the `Stop`-as-session-end conflation
  this issue corrects.
- **BUG-2420** — the scratch-pad race whose fix first surfaced this; also adds a
  `SessionEnd` block (coordinate to share one `SessionEnd` array).
- **ENH-2105** — wires `session_end` for the Codex adapter; Codex's end-of-turn
  event is named `Stop` and has no separate `SessionEnd`, so its binding stays on
  `Stop`. This issue must not touch the Codex adapter.

## Out of Scope

- Codex / OpenCode adapters (Codex intentionally binds `session_end` to its
  `Stop` event — ENH-2105).
- The `session-cleanup.sh` (`Stop`) lock/worktree cleanup behavior — separate
  from the FEAT-1680 sweep.
- Any change to what the sweep *does* (its scan/report logic is correct; only
  its firing cadence is wrong).

## Resolution

Re-homed the FEAT-1680 stale-ref sweep from the per-turn `Stop` event to the
session-terminal `SessionEnd` event on Claude Code. The `session-end.sh` adapter
and `sweep_stale_refs.handle` Python handler are reused verbatim — only the
`hooks.json` event key changed. BUG-2420's `SessionEnd` block was already
committed, so the sweep was **appended** as a second `hooks` group inside the
existing `SessionEnd` array (sharing it with `scratch-cleanup.sh`) and removed
from the `Stop` array. The sweep now fires once per session instead of once per
assistant turn, eliminating the double whole-tree `find_issues()` scan on every
response.

**Changes:**
- `hooks/hooks.json` — moved `session-end.sh` from the `Stop` array into the
  existing `SessionEnd` array (appended as the 2nd group). Other `Stop` handlers
  (`context-handoff-sentinel.sh`, `session-cleanup.sh`) left in place.
- `scripts/tests/test_claude_code_adapter.py` — added two wiring tests
  (`test_hooks_json_registers_sweep_under_session_end` positive,
  `test_hooks_json_stop_no_longer_references_sweep` regression), modeled on the
  existing `test_hooks_json_has_precompact_handoff` "second entry in an event
  array" precedent. TDD: both were confirmed Red before the `hooks.json` edit.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — moved sweep from `Stop` to a new
  `## SessionEnd` section; updated the lifecycle table row, the "session from
  hook's perspective" walkthrough, the `## Stop` intro (2 hooks, per-turn), and
  the `hooks.stale_ref_fix` config-table event column.
- `docs/reference/HOST_COMPATIBILITY.md` — relabeled the parity row to
  `session_end` and set the Claude Code cell to `✓ (SessionEnd event → session_end)`;
  Codex/OpenCode stay `(deferred)` (ENH-2105).

No change to `sweep_stale_refs.py`, the `session_end` dispatch intent (host-agnostic),
or any Codex/OpenCode adapter. Verified negatives from the wiring pass
(`ARCHITECTURE.md`, `API.md`, `EVENT-SCHEMA.md`, `CHANGELOG.md`) confirmed — no edits.

**Verification:** Full suite `python -m pytest scripts/tests/` — 13285 passed, the
2 new wiring tests among them. One pre-existing, unrelated failure
(`skills/manage-issue/SKILL.md` = 523 > 500-line limit, unchanged at HEAD, not
touched by this fix).

## Session Log
- `/ll:manage-issue` - 2026-07-01T03:23:21 - `f2b563fe-acae-472f-942a-b6cf769740e2.jsonl`
- `/ll:ready-issue` - 2026-07-01T02:47:14 - `965f9d28-0986-4224-a4e8-137bcdd66c4d.jsonl`
- `/ll:confidence-check` - 2026-07-01T02:44:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6191c231-16b2-4dc2-b059-585b404f1916.jsonl`
- `/ll:wire-issue` - 2026-07-01T02:39:34 - `bb26fac8-dafb-4bb9-8850-4e2c32747581.jsonl`
- `/ll:refine-issue` - 2026-07-01T02:29:42 - `56f1c100-090c-42bb-89ac-389b65092f77.jsonl`
- `/ll:format-issue` - 2026-07-01T02:18:47 - `8da409e8-6185-4be8-aaae-a039c7c68aef.jsonl`
- `/ll:capture-issue` - 2026-07-01T02:13:42Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8da409e8-6185-4be8-aaae-a039c7c68aef.jsonl`

---

## Status

**Current Status**: done
