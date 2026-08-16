---
id: BUG-3209
type: BUG
title: Automation skills spawn Agents with no blocking contract; headless turns can
  end with subagent results in flight
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:18Z'
confidence_score: 95
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# BUG-3209: Automation skills spawn Agents with no blocking contract; headless turns can end with subagent results in flight

## Summary

Five agent-spawning skills issue Agent/Task tool calls with no `run_in_background`
directive: `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md`,
`skills/audit-issue-conflicts/SKILL.md`, `skills/confidence-check/SKILL.md`, and
`skills/wire-issue/SKILL.md`. The Agent tool defaults to background, so under a
headless `claude -p` turn (ll-auto, ll-parallel, ll-sprint, FSM prompt states) the
parent turn can end with subagent results still in flight — the completion
notification never arrives, exactly the failure mode BUG-3058 and the
manage-issue "Headless-Safe Final Test Run" section (`skills/manage-issue/SKILL.md:381-398`)
guard against for Bash test runs.

Nothing below the prompt layer compensates:

- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (`host_runner.py:374`, documented at
  `host_runner.py:247`) is scoped to Bash `run_in_background`, not Agent-tool
  backgrounding — it never covered subagents, and ENH-3207 flipped it off by default.
- The process layer does not join: `subprocess_utils.py:600-645` stops reading on the
  stream-json `result` event, waits `post_stream_close_grace_seconds` (default 300,
  `config/automation.py:26`), then `_kill_process_group`. A still-running subagent is
  killed, not awaited — BUG-2718 raised that grace and BUG-2731 classifies the
  resulting exit 143 as INFRA_RETRY, but neither is a barrier.

Only two skills enforce blocking today: `skills/decide-issue/SKILL.md:335`
(`run_in_background: false`, waits in-turn) and `skills/go-no-go/SKILL.md:174,274`
(deliberately backgrounds, then relies on prose "wait until both have completed" with
no mechanical backstop).

Proposed fix: state the blocking contract once in the injected automation context
(when `LL_AUTOMATION=1`, every Agent spawn must be `run_in_background: false` and be
awaited in the same turn) rather than per-skill, and add the explicit directive to the
five silent skills. Consider whether go-no-go's intentional background fan-out should
be exempted or converted.


## Current Behavior

Four skills — `audit-docs/SKILL.md:120-139`, `audit-claude-config/SKILL.md:118,222`,
`audit-issue-conflicts/SKILL.md:205,218,252`, `wire-issue/SKILL.md:147-190` — instruct
Agent/Task spawns with prose like "wait for results" but no `run_in_background` value
on the tool call itself. The Agent tool defaults to background execution. Under a
headless turn, `subprocess_utils.py`'s stream-close handling (~lines 590-648) detects
the parent turn's `result` event, then waits `post_stream_close_grace_seconds` (default
300s, `config/automation.py:26`) for the OS process to exit before `_kill_process_group()`
(`subprocess_utils.py:307`) SIGKILLs the whole process group — it waits for the parent
process only, never joins individual still-running subagents.

**Correction — `confidence-check/SKILL.md` is not actually affected today**:
codebase-analyzer found no Agent/Task spawn site anywhere in `SKILL.md`, `reference.md`,
or `rubric.md`; its `allowed-tools` frontmatter (lines 6-15) omits `Task`/`Agent`
entirely. The issue names it as one of five silent skills, but only four currently spawn
subagents. Verify before including it in the fix scope.

**Correction — `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` scope claim is stale**: the Summary
states this flag "is scoped to Bash `run_in_background`... never covered subagents."
`.issues/features/P3-FEAT-3076-verify-claude-code-disable-background-tasks-scope.md` §
Findings records a verified `claude -p` test showing the flag *also* coerces Agent-tool
`run_in_background: true` to synchronous behavior on Claude Code hosts — contradicting
both the Summary and `host_runner.py`'s own docstring (lines 243-252), which is itself
stale on this point. This is Claude-Code-only; the other six `HostRunner` implementations
no-op the flag (`docs/reference/HOST_COMPATIBILITY.md:248`). Practical effect: an
operator-level flag that already covers this case exists — the gap is that ENH-3207
flipped its default to `false`, making it opt-in, not that it structurally can't reach
Agent spawns.

## Expected Behavior

Every Agent/Task spawn in an automation-driven skill either declares
`run_in_background: false` and is awaited synchronously in the same turn, or is a
documented, deliberate exception (as `go-no-go/SKILL.md` already is). No headless turn
ends with a subagent whose result the parent turn never reads.

## Motivation

Without a blocking contract, headless runs (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM
prompt states) can silently drop subagent findings — the parent turn ends, the
notification never arrives, and up to `post_stream_close_grace_seconds` (300s) later the
still-running agent is killed rather than awaited. This is the same failure class
BUG-3058 and `manage-issue/SKILL.md`'s "Headless-Safe Final Test Run" section already
guard against for Bash test runs; these four skills have no equivalent guard.

## Proposed Solution

State the blocking contract either per-skill (declare `run_in_background: false` at each
spawn site, following the pattern at `decide-issue/SKILL.md:335`) or centrally (extend
the existing `_STAY_IN_TURN_INSTRUCTION` injection in `session_start.py`, the one
host-agnostic mechanism that already puts automation-only context into every headless
session). Both are viable; which one the implementer picks determines whether the four
skill files or `session_start.py` (or both) get edited. Resolve explicitly whether
`go-no-go/SKILL.md`'s intentional background fan-out stays exempted or converts — the
issue defers this decision rather than assuming an answer.

## Integration Map

### Files to Modify
- `skills/audit-docs/SKILL.md:120-139` — Task spawn instruction, no `run_in_background` directive
- `skills/audit-claude-config/SKILL.md:118,222` — two Task spawn sites, no directive
- `skills/audit-issue-conflicts/SKILL.md:205,218,252` — Task spawn sites, no directive
- `skills/wire-issue/SKILL.md:147-190` — Agent spawn sites (3 agents); has a "wait...in
  this same turn" prose instruction but no mechanical `run_in_background: false`
- `skills/confidence-check/SKILL.md` — **not currently in scope**; no Agent/Task spawn
  exists (see Current Behavior correction above)

### Dependent Files (Existing Precedent)
- `skills/decide-issue/SKILL.md:335,340` — the one skill with a mechanical
  `run_in_background: false` directive plus a prose backstop
- `skills/go-no-go/SKILL.md:174,272-278` — intentional background fan-out; prose-only
  wait, no mechanical backstop; the one entry in
  `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` (`scripts/tests/test_wiring_skills_and_commands.py:442-464`)
- `scripts/little_loops/hooks/session_start.py:57-61,88-102,258-269` —
  `_STAY_IN_TURN_INSTRUCTION`, the sole existing host-agnostic mechanism that injects
  automation-only context into every headless session (gated on the `LL_AUTOMATION` env
  var); today a generic "don't end your turn" instruction, not a per-Agent-call blocking
  directive
- `scripts/little_loops/subprocess_utils.py` (stream-close loop ~590-648,
  `_kill_process_group()` :307) — kills the whole process group after
  `post_stream_close_grace_seconds` with no join/await of individual subagents
- `scripts/little_loops/host_runner.py:374` (gate), `:243-252` (docstring, stale per
  FEAT-3076) — `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`; default `false` since ENH-3207
  (`config-schema.json:1759-1761`, `.ll/ll-config.json:134`)
- `skills/manage-issue/SKILL.md:376-398` — "Headless-Safe Final Test Run" section; the
  wording precedent for this class of guard. Its exact strings are pinned by
  `scripts/tests/test_wiring_skills_and_commands.py`'s `DOC_STRINGS_PRESENT` list
  (~lines 202-203) — reflowing that paragraph (vs. appending) is test-caught.

### Conventions in Force
- Skills that want synchronous behavior state `run_in_background: false` explicitly next
  to the spawn instruction plus a "wait for results" sentence; skills that want
  concurrency state `run_in_background: true` explicitly — evidence:
  `decide-issue/SKILL.md:335`, `go-no-go/SKILL.md:174`. Nothing is left implicit except
  the sites this bug names.
- The only existing mechanism for conditionally injecting automation-state-dependent text
  into a headless session's context is hook stdout (`session_start.py`'s
  `LLHookResult.stdout`) — there is no in-skill-markdown conditional-branching mechanism
  for this.
- `test_skill_run_in_background_true_inventory_pinned`
  (`scripts/tests/test_wiring_skills_and_commands.py:442`) enforces a set-equality
  allowlist for `run_in_background: true` occurrences across `skills/*.md`, currently
  `{"skills/go-no-go/SKILL.md"}`. Adding `run_in_background: false` to the four named
  skills doesn't touch this test; changing go-no-go's carve-out status would.
- Mirror-file drift: `skills/wire-issue/SKILL.md` has a test-guarded mirror
  (`SKILL_MIRRORS_MUST_MATCH_SOURCE`, same test file :372-394);
  `skills/audit-issue-conflicts` and `skills/confidence-check` have mirror files on disk
  but are **not** in that guarded list — editing their sources without
  `ll-adapt --host {gemini,kimi-code,qwen} --apply` would not be test-caught.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` —
  `test_skill_run_in_background_true_inventory_pinned` (:442), `DOC_STRINGS_PRESENT`
  (Headless-Safe Final Test Run pinned strings, ~:202-203),
  `SKILL_MIRRORS_MUST_MATCH_SOURCE` (:372-394)
- `scripts/tests/test_enh494_skill_companions.py` — 500-line-per-`SKILL.md` cap; relevant
  if new wording pushes any of the four skills over budget

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `SKILL_MIRRORS_MUST_MATCH_SOURCE`
  (:372-382) is missing three tuples for `skills/audit-issue-conflicts/SKILL.md` against
  its `.gemini`/`.kimi-code`/`.qwen` mirrors — those mirror files already exist on disk
  (confirmed, each with 4 companion files) but drift is currently uncaught; add tuples
  mirroring the `wire-issue`/`manage-issue` block structure [Agent 1 + Agent 3 finding]
- New `DOC_STRINGS_PRESENT` tuples for each of the four skills' new
  `run_in_background: false` spawn-site wording, following the `decide-issue`/BUG-2408
  `(doc_rel, needle, issue_id)` tuple-append pattern [Agent 3 finding]
- `scripts/tests/test_audit_issue_conflicts_skill.py` — phase-scoped substring-slicing
  pattern (keys on `## Phase 4b`/`## Phase 5` headings) is the alternative to a whole-file
  `DOC_STRINGS_PRESENT` needle if a phase-scoped assertion is preferred for this skill's
  spawn-site wording; no existing test in this file references the Task/Agent spawns
  today [Agent 3 finding]
- Confirmed no test breakage risk: neither `test_skill_run_in_background_true_inventory_pinned`
  nor any existing `DOC_STRINGS_PRESENT` entry is disturbed by adding
  `run_in_background: false` text to the four target skills [Agent 3 finding]

### Documentation
- N/A — no docs describe per-skill blocking behavior beyond the skills themselves and
  `manage-issue/SKILL.md`'s guard section

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md:250` — `[^bgtasks]` footnote restates the same
  stale "scoped to Bash `run_in_background`" claim the issue flags in `host_runner.py`'s
  docstring [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:1236` — `orchestration.disable_background_tasks` table
  row, same stale claim [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:638` — "Automation-Context Pruning" section, second
  paragraph, same stale claim [Agent 2 finding]
- `docs/ARCHITECTURE.md:738` — `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` component-table
  row, same stale claim [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1762` — `disable_background_tasks` property's
  schema-embedded `description` string, same stale claim [Agent 2 finding]

  Only in scope if the implementer also corrects `host_runner.py`'s stale docstring as
  part of this fix; otherwise these five are unaffected. Not independently required by
  the issue's core fix (per-skill or `session_start.py` blocking directive).

### Configuration
- N/A — no config file governs this; `LL_AUTOMATION` (env var) and
  `orchestration.disable_background_tasks` (`.ll/ll-config.json`) are the two related
  signals, both already wired

## Implementation Steps

1. Each of the four skills that spawn Agent/Task calls with no blocking directive
   (`audit-docs`, `audit-claude-config`, `audit-issue-conflicts`, `wire-issue` — not
   `confidence-check`, which has no spawn site today) declares `run_in_background: false`
   at every spawn site, following the wording at `decide-issue/SKILL.md:335` — or the
   contract is centralized in `session_start.py`'s injected automation context instead of
   duplicated per-skill. Either route satisfies the same outcome; pick one.
2. `go-no-go/SKILL.md`'s intentional background fan-out is either documented as a
   deliberate, explicit carve-out or converted to blocking — a decision this issue
   defers, not a default to assume.
3. Any wording reused from `skills/manage-issue/SKILL.md`'s "Headless-Safe Final Test
   Run" section preserves the exact strings pinned in `DOC_STRINGS_PRESENT`
   (`test_wiring_skills_and_commands.py` ~:202-203).
4. If `skills/wire-issue/SKILL.md` or `skills/audit-issue-conflicts/SKILL.md` are
   edited, their mirrors are regenerated
   (`ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply`)
   — only `wire-issue`'s mirror is currently test-guarded, so drift in the other would go
   uncaught otherwise.
5. `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` passes,
   including the `run_in_background: true` inventory-pinned test.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **Files**: `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md`,
  `skills/audit-issue-conflicts/SKILL.md`, `skills/wire-issue/SKILL.md`
- **Anchor**: Agent/Task spawn instructions at audit-docs:120-139,
  audit-claude-config:118,222, audit-issue-conflicts:205,218,252, wire-issue:147-190
- **Cause**: these skills instruct Agent/Task spawns with prose ("wait for results")
  but no `run_in_background: false` directive on the tool call itself. The Agent tool
  defaults to background execution. Nothing downstream compensates by default:
  `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is off by default since ENH-3207, and
  `subprocess_utils.py`'s grace-then-kill logic
  (`post_stream_close_grace_seconds` default 300s, `_kill_process_group()`) waits for
  the parent OS process only, not individual subagent completions.

## Program Design

### Types
N/A — a skill-markdown/prose change, not a data-shape change.

### Signatures
No new signatures. If centralizing, the fix extends the existing entry point below
(`scripts/little_loops/hooks/session_start.py:64`) — specifically the text of the
`_STAY_IN_TURN_INSTRUCTION` constant its `LLHookResult.stdout` field already carries
(`session_start.py:57-61`), not a new field or function:

`handle(event: LLHookEvent) -> LLHookResult`

### Call Path
`session_start.py:handle()` (`:64`) `-> LLHookResult(stdout=_STAY_IN_TURN_INSTRUCTION, ...)`
(`:57-61`, `:88-102`, `:258-269`) `-> Claude Code session context` — the existing,
host-agnostic injection path if the fix centralizes the blocking contract. Per-skill
alternative: the skill body's Agent/Task call takes `run_in_background: false` directly
(as at `skills/decide-issue/SKILL.md:335`).

### Decision Rules
- Gate: when `LL_AUTOMATION` is set (the same signal `session_start.py:88` reads via
  `os.environ.get("LL_AUTOMATION")`), every Agent/Task spawn in the four affected
  skills must declare `run_in_background: false` and be awaited synchronously in the
  same turn.
- Escape hatch: `go-no-go/SKILL.md`'s intentional background fan-out (`:174`) is the
  one named carve-out precedent
  (`SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`); whether it stays exempted or converts is
  an open call the issue defers.
- `confidence-check/SKILL.md` is not in scope — no Agent/Task spawn site exists today;
  confirm before treating it as one of the fix's targets.

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:20:15 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:51 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
