---
captured_at: '2026-07-01T00:04:14Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
status: open
priority: P2
type: BUG
relates_to:
- BUG-2409
- BUG-280
- BUG-1538
---

# BUG-2408: manage-issue implement flow stalls on backgrounded final test + notification wait in headless ll-auto turn

## Summary

Under `ll-auto` (headless `claude --dangerously-skip-permissions -p`), the
`/ll:manage-issue` implement phase can finish all edits and then launch the
final full-suite `pytest` with `run_in_background`, after which the agent adopts
an interactive-session pattern — *"I'll wait for the scheduled wakeup or
completion notification."* That notification/scheduled-wakeup loop does not
exist inside a single headless `-p` turn, so the turn ends before the agent
reaches its finalization steps (**git commit + `ll-issues set-status <ID>
done`**). The implementation is left uncommitted in the working tree and the
issue stays `open`, even though the work is complete and validated.

Observed in the `ll-auto --only ENH-2406` run (2026-06-30): Phase 2 completed
in 16.3 min, all 126 targeted tests passed and both loops validated clean, but
the run reported "Issues processed: 0" and left the ENH-2406 changes uncommitted
(`rn-implement.yaml`, `rn-remediate.yaml`, three docs guides, two test files).

## Current Behavior

1. The implement agent completes edits and enters a verification step.
2. It runs the full test suite via a **backgrounded** process (`run_in_background`
   / `&`-style), then narrates that it will wait for a "completion notification"
   or "scheduled wakeup."
3. In a headless `claude -p` turn there is no interactive wakeup/notification
   mechanism — that is an affordance of interactive sessions only. With no
   further output to emit, the agent ends its turn.
4. The subprocess runner (`subprocess_utils.py`, see the comment at ~line 380)
   correctly breaks on the headless result marker and logs
   `Phase 2 (implement) completed in N minutes` — a **normal** completion, not a
   timeout.
5. The agent never reached **commit** or **`ll-issues set-status done`**, so the
   working tree holds uncommitted changes and the issue frontmatter still reads
   `status: open`.

This is **not** a timeout: the default `automation.timeout_seconds` is 3600s and
`idle_timeout_seconds` is 0 (disabled) (`config/automation.py:17-18`); the phase
ran ~978s and was emitting output throughout. A timeout would have killed the
process group and raised `subprocess.TimeoutExpired`
(`subprocess_utils.py:391-411`), producing a different log signature.

## Expected Behavior

Within a single headless turn, the implement flow must reach a terminal,
self-contained finish:

- The final verification test run must be **foreground-blocking** (or routed
  through the scratch-pad redirect that pipes to a file and tails the summary),
  so the agent has the result *within the same turn*.
- The agent must not depend on an interactive "scheduled wakeup / completion
  notification" to resume — that signal never fires under `claude -p`.
- After tests pass, the agent must complete finalization in-turn: **commit the
  scoped changes** and **`ll-issues set-status <ID> done`** before the turn ends.

## Root Cause

`skills/manage-issue/SKILL.md` guidance (the implement/verify step) does not
forbid the background-test-then-await pattern and does not require the final
verification run to be foreground-blocking. The `run_in_background` + "wait for
notification" idiom is valid in interactive sessions but is a dead-end in a
single headless automation turn: the turn boundary arrives before the awaited
event, so the commit + status-update tail never executes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (all 5 issue claims verified accurate):_

- **Precise fix-surface anchors in the skill**: `skills/manage-issue/SKILL.md`
  Phase 3 "Implement" (lines ~279–376) covers only the Context-Handoff protocol,
  not test-execution mode. Phase 4 "Verify" (lines ~380–404) is where the
  configured `test_cmd` runs — this is the natural anchor for the new
  foreground-blocking rule. Phase 5 "Complete Issue Lifecycle" (lines ~426+)
  holds commit + `set-status`, and is only reached if the agent proceeds past
  Phase 4 in the same turn.
- **Scope the ban — do not make it blanket.** Phase 4 already contains one
  *legitimate* `run_in_background` use at line ~397: the `run_cmd` smoke test for
  long-running server processes ("start in background, wait briefly for startup,
  then terminate"). The new rule must forbid backgrounding **only the
  result-blocking final test suite** (where the agent's next action depends on
  the result), not backgrounding in general, or it will contradict the existing
  smoke-test guidance.
- **Turn-end mechanism (confirmed, not a timeout).** `run_claude_command`
  (`scripts/little_loops/subprocess_utils.py`, lines ~449–498) breaks the reader
  loop on the stream-json `"result"` event (`result_seen = True` → `break`), a
  normal non-exceptional return. The two `TimeoutExpired`-raising paths (wall-clock
  ~391–400; idle ~402–411) never fire here because the backgrounded pytest keeps
  the process group alive within budget and `idle_timeout_seconds` defaults to 0.
- **Why the finalization tail is skipped.** `run_with_continuation`
  (`scripts/little_loops/issue_manager.py`, loop starting line ~201) only
  continues the session when `detect_context_handoff(result.stdout)` matches the
  literal `CONTEXT_HANDOFF: Ready for fresh session` string. A "wait for
  wakeup/notification" narration prints no such marker, so the loop falls through
  to its terminal `break` (~line 478) after one round. The
  `Phase 2 (implement) completed in N minutes` line is logged unconditionally by
  `timed_phase`'s `finally` block — it signals turn-end, not task-completion.

## Integration Map

- `skills/manage-issue/SKILL.md` — implement/verify phase; add a headless-safe
  rule for the final test run and finalization ordering.
- `scripts/little_loops/subprocess_utils.py:~380` — existing comment documents
  why background child processes hang pipe EOF; corroborates the mechanism.
- `scripts/little_loops/issue_manager.py:880-920` — Phase 2 invocation via
  `run_with_continuation`; the turn ends here without a `CONTEXT_HANDOFF` marker.
- `.claude/CLAUDE.md` § Automation: Scratch Pad — the scratch-pad-redirect
  pattern is the intended vehicle for large foreground command output.

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrected paths and additional integration points:_

- **Path correction**: the automation defaults are at
  `scripts/little_loops/config/automation.py:17-18` (`timeout_seconds: int = 3600`,
  `idle_timeout_seconds: int = 0`), not `config/automation.py` — there is no
  `config/` dir at repo root.
- **`scripts/little_loops/parallel/worker_pool.py`** — `ll-parallel` also drives
  issues through `run_with_continuation`, so this same headless stall affects
  parallel runs, not just `ll-auto`. The skill-guidance fix covers both; no
  separate runner change is needed for parity.
- **`scripts/tests/test_wiring_skills_and_commands.py`** — the SKILL.md
  content-lint home (see "Tests to Add"). `skills/manage-issue/SKILL.md` is
  already a target in its `DOC_STRINGS_PRESENT` / `DOC_STRINGS_ABSENT` tables;
  new rows extend the most-worn path rather than adding a new test file.
- **`detect_context_handoff`** — the marker check consumed by
  `run_with_continuation` (regex `CONTEXT_HANDOFF:\s*Ready for fresh session`),
  surfaced via `scripts/little_loops/subprocess_utils.py` (~lines 59/72) and
  `scripts/little_loops/fsm/signal_detector.py`. No automated emitter exists — it
  is purely agent-narrated per the SKILL.md Handoff Protocol.
- **`hooks/scripts/scratch-pad-redirect.sh`** — the foreground-blocking redirect
  vehicle already exists (PreToolUse hook, active in automation/`bypassPermissions`
  contexts). The fix leans on it rather than inventing a new mechanism.

### Wiring Pass (added by `/ll:wire-issue`)

_Additional integration points surfaced by the wiring pass (3 parallel agents):_

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/sprint/run.py` — `ll-sprint` also drives issues through
  `AutoManager` / `run_with_continuation`, so the same headless stall affects sprint
  runs, not just `ll-auto` and `ll-parallel`. The skill-guidance fix covers all three
  paths; no separate runner change is needed. [Agent 1]

**Runtime-consumption constraint on the edit (not an edit target, but binding)**
- `scripts/little_loops/skill_expander.py` `expand_skill()` — `skills/manage-issue/SKILL.md`
  is not merely documentation: for `ll-auto`'s **initial** turn its prose is read,
  frontmatter-stripped, and `{{config.x}}` / relative `(*.md)` links are substituted to
  build the literal headless prompt string. New Phase 4 prose must **not** accidentally
  form a `{{config.something}}` token (silently blanked if unresolvable) or a
  `(something.md)` pattern (rewritten to an absolute path). [Agent 2]
- `scripts/little_loops/parallel/types.py` `ParallelConfig.get_manage_command()` —
  `ll-parallel` sends a plain slash-command template (`/ll:manage-issue …`) with **no**
  pre-expansion, so only `ll-auto`'s first turn is subject to `expand_skill` substitution
  quirks. Both paths ultimately execute the same SKILL.md content. [Agent 2]

**Finalization-ordering decision — resolving evidence**
- `scripts/little_loops/issue_lifecycle.py` `complete_issue_lifecycle()` — the
  Python-driven fallback completion path writes `status: done` **first**
  (`update_frontmatter` + `write_text`), then calls `_commit_issue_completion()` (git add
  + commit) **second** — i.e. set-status→commit, the **same order Phase 5 currently
  documents**. This is direct precedent for resolving the discrepancy per option (a):
  keep Phase 5's existing set-status→commit order so the interactive SKILL.md path and
  the automated fallback stay in parity, and add the headless-safety rule to **Phase 4
  only** — do not introduce a contradictory commit→set-status statement. [Agent 2]

**Documentation / hook coupling (advisory — no change required)**
- `docs/ARCHITECTURE.md` § "Session Log Auto-Linking" + `hooks/scripts/issue-completion-log.sh`
  — Phase 5 sets status via the `ll-issues set-status` **Bash CLI** (not the Write tool),
  so this PostToolUse hook (fires only on a `Write` to `.issues/*.md` whose frontmatter
  reads `status: done`) does **not** trigger from that step. Whichever finalization order
  Phase 5 keeps, it does not interact with this hook — no hook change is implied. [Agent 2]
- `hooks/scripts/scratch-pad-redirect.sh` clarification — the hook auto-redirects
  `python -m pytest …` **output size** (it unwraps `python -m <module>` against
  `scratch_pad.command_allowlist`), but it does **not** inspect or block the
  `run_in_background` tool parameter. The SKILL.md prose rule is therefore the **only**
  mechanism that can prevent the background-then-await stall — the hook and the new
  guidance address orthogonal concerns. [Agent 2]

**Confirmed no-change surface (noise filtered from Agent 1's broad trace)**
- The ~13 importers of `run_with_continuation` / `detect_context_handoff` /
  `run_claude_command` and the ~13 skill files that merely reference `/ll:manage-issue`
  as a next step need **no** change — this is a prose + test-row fix with no Python
  signature or behavior change. `output_parsing.py`, `skills/manage-issue/templates.md`,
  `config-schema.json`, and `.ll/ll-config.json` are likewise untouched.

## Steps to Reproduce

1. Pick an issue whose implementation ends with a long full-suite test run.
2. Run `ll-auto --only <ID>`.
3. Observe the implement agent background the final `pytest` and narrate waiting
   for a wakeup/notification.
4. Observe Phase 2 "completed" normally, the issue left `status: open`, and the
   changes uncommitted in the working tree.

## Proposed Solution

In `skills/manage-issue/SKILL.md`, add an explicit headless-safety rule:

- Run the final verification suite **foreground-blocking**, e.g. via the
  scratch-pad redirect (`... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 ...`),
  never `run_in_background` when the agent's next action depends on the result.
- Never wait on an interactive "scheduled wakeup" / "completion notification"
  inside a headless turn.
- Enforce finalization ordering: tests pass → commit scoped files →
  `ll-issues set-status <ID> done`, all within the same turn.

### Codebase Research Findings

_Added by `/ll:refine-issue` — implementation constraints the plan must resolve:_

- **⚠ Finalization-ordering discrepancy — resolve deliberately.** This issue
  proposes `commit scoped files → set-status done`, but Phase 5 "Complete Issue
  Lifecycle" *currently documents the reverse*: step 2 is
  `ll-issues set-status <ID> done`, step 3 is "Commit All Changes" (i.e.
  set-status **before** commit, and the commit's `git add` even includes the
  updated issue file). Decide one of: (a) the "same turn, no dead-end" property
  is what matters and either order is fine — then keep Phase 5's existing
  set-status→commit order to avoid churn and stale-status-in-commit changes; or
  (b) genuinely reorder Phase 5 to commit→set-status. Do **not** add
  commit→set-status guidance in Phase 4 while leaving Phase 5 saying the opposite,
  or the skill will contradict itself.
- **Reuse existing foreground vocabulary** for consistency: `skills/go-no-go/SKILL.md`
  (Steps 3b–3d) and `skills/decide-issue/SKILL.md` (Phase 4) already use
  `**foreground**`, `run_in_background: false`, and "wait … before proceeding".
  Mirror that phrasing rather than inventing new terms.
- **Prefer the documented redirect idiom** verbatim from `.claude/CLAUDE.md`
  § Automation: Scratch Pad —
  `... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 .loops/tmp/scratch/test-results.txt`
  — so the guidance matches the already-hooked `scratch-pad-redirect.sh` behavior.

## Implementation Steps

1. Edit `skills/manage-issue/SKILL.md` implement/verify step: require the final
   verification suite to run foreground-blocking (scratch-pad redirect), never
   `run_in_background` when the next action depends on the result.
2. Add an explicit prohibition on the "background test → await scheduled
   wakeup / completion notification" idiom inside a headless `-p` turn.
3. Codify finalization ordering in the skill: tests pass → commit scoped files →
   `ll-issues set-status <ID> done`, all within the same turn.
4. Add a SKILL.md lint/guard assertion (mirroring existing skill-content checks)
   verifying the implement/verify section carries the foreground-blocking +
   no-background-wait guidance.
5. Verify with a headless `ll-auto --only <ID>` run on an issue whose
   implementation ends in a long full-suite test: confirm the turn finishes with
   changes committed and the issue `status: done`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were surfaced by wiring analysis and must be honored during implementation:_

6. Resolve the finalization-ordering discrepancy per option (a): **keep** Phase 5's
   existing set-status→commit order (matches `issue_lifecycle.complete_issue_lifecycle()`)
   and add the headless-safety rule to **Phase 4** only — do not add a contradictory
   commit→set-status statement in Phase 4.
7. When writing the new Phase 4 prose, avoid any `{{config.…}}` token or `(name.md)`
   link pattern — `expand_skill()` substitutes both when building `ll-auto`'s headless
   prompt (`skill_expander.py`).
8. After editing, run `python -m pytest scripts/tests/test_skill_expander.py -v` (the
   `test_manage_issue_expansion_has_no_raw_tokens` guard) to confirm the new prose left
   no unresolved template token, plus
   `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` for the new rows.

## Tests to Add

- A SKILL.md lint/guard assertion (mirroring existing skill-content checks) that
  the implement/verify section contains the foreground-blocking + no-background-wait
  guidance.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete test target and pattern:_

- **Home**: extend the parametrized tables in
  `scripts/tests/test_wiring_skills_and_commands.py`
  (`test_string_present_in_doc` / `test_string_absent_from_doc`, rows are
  `(doc_rel, needle, issue_id)`). `skills/manage-issue/SKILL.md` is already a
  target there — add:
  - a `DOC_STRINGS_PRESENT` row for the foreground-blocking phrase (e.g. the
    chosen `**foreground**` / scratch-redirect marker), tagged `"BUG-2408"`.
  - a `DOC_STRINGS_ABSENT` row forbidding the failure idiom (e.g. a
    "scheduled wakeup" / "completion notification" phrase in the verify section),
    tagged `"BUG-2408"` — but only if that phrase can't appear legitimately
    elsewhere in the file; otherwise scope the check to Phase 4.
- **If a scoped/ordering assertion is needed** (verify Phase 4 contains the rule,
  or that finalization order is X-before-Y), model a bespoke test on the
  `_phase_text()` section-slicing + `.find()` ordering idiom in
  `scripts/tests/test_confidence_check_skill.py` and
  `scripts/tests/test_ready_issue_lint.py` (`pos_a < pos_b` ordering asserts).
  Both use the session-scoped `project_root` fixture from
  `scripts/tests/conftest.py`. Note: no `test_manage_issue_skill.py` exists yet;
  prefer extending the shared table file over creating a new one.
- Run with:
  `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v`

## Acceptance Criteria

- `ll-auto --only <ID>` on an issue with a long final test run finishes the turn
  with the changes **committed** and the issue **`status: done`**.
- The implement flow never narrates waiting for a wakeup/notification under `-p`.

## Impact

Silent under-completion: an issue is fully implemented and validated but reported
as "0 processed," left `open`, and its changes stranded uncommitted in the working
tree — where a subsequent re-run would re-plan from a dirty tree and risk
duplicate/conflicting edits. Wastes a full implement slot and erodes trust in the
run summary.

## Related Issues

- **BUG-2409** — the Phase-3 verify heuristic that *masks* this by parking the
  issue as "plan awaiting approval" instead of surfacing the completed-but-
  uncommitted state.
- **BUG-280** (done) — false verification failure when a plan is *genuinely*
  awaiting approval (inverse case; agent stopped at planning).
- **BUG-1538** (done) — verification missed *committed* work + rejected a status
  synonym (different failure mode; work was committed).

## Out of Scope

- Changing `ll-auto` timeout/idle-timeout defaults (not the cause here).
- The Phase-3 detection fix (tracked separately in BUG-2409).

## Labels

manage-issue, ll-auto, headless, automation, finalization

## Session Log
- `/ll:refine-issue` - 2026-07-01T00:18:04 - `3fb8d5dc-1928-4342-8cac-be6c5066aa24.jsonl`
- `/ll:format-issue` - 2026-07-01T00:09:07 - `ac278041-8972-4118-8e20-9572ae7f75f4.jsonl`
- `/ll:capture-issue` - 2026-07-01T00:04:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/50bef1ad-9ed2-44c2-9376-d53bca2305b4.jsonl`

---

## Status

**Current Status**: open
