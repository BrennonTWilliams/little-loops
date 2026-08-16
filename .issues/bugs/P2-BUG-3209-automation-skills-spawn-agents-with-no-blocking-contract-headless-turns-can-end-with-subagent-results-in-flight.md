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

**Five** agent-spawning sites issue Agent/Task tool calls with no `run_in_background`
directive, across five skills: `skills/audit-docs/SKILL.md`,
`skills/audit-claude-config/SKILL.md`, `skills/audit-issue-conflicts/SKILL.md`,
`skills/wire-issue/SKILL.md`, and — **corrected 2026-08-15** —
`skills/go-no-go/SKILL.md:278`.
(`skills/confidence-check/SKILL.md` was named at capture but has **no** Agent/Task spawn
site anywhere in `SKILL.md`, `reference.md`, or `rubric.md`, and omits `Task`/`Agent`
from its `allowed-tools` frontmatter, lines 6-15 — it is not in scope. Its only
`Task tool` mention is prose in a checklist item, `SKILL.md:235`; see the detector
caveat under Tests.)

**The fifth site is inside the skill this issue otherwise treats as the exempt
precedent.** `go-no-go/SKILL.md` has *two* spawn sites, not one, and they are different
cases:

- `:174` — `run_in_background: true`, deliberate parallel fan-out. Genuinely exempt; the
  sole entry in `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`.
- `:278` — "Launch a **foreground** judge agent (no `run_in_background`) using the Agent
  tool." The stated intent is foreground, but the Agent tool **defaults to background**,
  so omitting the directive produces exactly the opposite of what the prose says. This
  is the bug verbatim, in the file cited as the precedent for exempting it.

That partly settles the question Step 2 defers: `:174` stays `true`; `:278` takes an
explicit `run_in_background: false`. Neither change touches the `true` allowlist
(`go-no-go/SKILL.md` remains its sole member).

The Agent tool defaults to background, so under a headless `claude -p` turn (ll-auto,
ll-parallel, ll-sprint, FSM prompt states) the parent turn can end with subagent results
still in flight — the completion notification never arrives, exactly the failure mode
BUG-3058 and the manage-issue "Headless-Safe Final Test Run" section
(`skills/manage-issue/SKILL.md:381-398`) guard against for Bash test runs.

The process layer does not join: `subprocess_utils.py:600-645` stops reading on the
stream-json `result` event, waits `post_stream_close_grace_seconds` (default 300,
`config/automation.py:26`), then `_kill_process_group`. A still-running subagent is
killed, not awaited — BUG-2718 raised that grace and BUG-2731 classifies the resulting
exit 143 as INFRA_RETRY, but neither is a barrier.

Only one skill enforces blocking today: `skills/decide-issue/SKILL.md:335`
(`run_in_background: false`, waits in-turn). `skills/go-no-go/SKILL.md:174,274`
deliberately backgrounds, then relies on prose "wait until both have completed" with
no mechanical backstop — a weaker guarantee, not an enforcement.

**An operator-level mechanical fix already exists and is switched off.** FEAT-3076
verified empirically (real `claude -p` invocations, `claude --version` 2.1.219, raw
transcripts in `postmortems/feat-3076-verify/`) that
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` covers **both** Bash `run_in_background` *and*
Agent-tool spawns: with the flag set, an Agent call returns the subagent's full final
response synchronously in the same turn. So `orchestration.disable_background_tasks:
true` fixes all four skills at once, mechanically, with no skill edits. ENH-3207
(2026-08-15, direct user decision) flipped that default `true → false`, making it
opt-in. Resolving that tension is Step 1 below — see **Key Decision**.

## Key Decision — SETTLED: route (b), the prose route

**Decided 2026-08-15.** Recorded here per this section's own requirement that the
rejected route's reason be stated.

**(a) Config route (REJECTED)** — automation runs set
`orchestration.disable_background_tasks: true`. Mechanical, covers all five spawn sites
plus any skill added later, zero prose edits. Rejected on four costs, the first of which
is decisive:

1. **It breaks the carve-outs that depend on backgrounding working.** FEAT-3076's own
   conclusion (`postmortems/feat-3076-verify/README.md:52-66`), from the same empirical
   run that established the flag reaches Agent spawns: *"the async launch/notify
   mechanism `ll-parallel` and the `go-no-go`/`manage-issue` carve-outs depend on is
   unavailable under the flag."* The flag's breadth is exactly why it cannot be used as
   a blanket fix — it would serialize `go-no-go`'s deliberate parallel fan-out (`:174`)
   and defeat `manage-issue`'s carve-out, converting a correctness fix into a
   throughput regression plus two broken skills.
2. It re-disables Bash backgrounding too — the `project.run_cmd` smoke-test case
   ENH-3207 was flipped to restore.
3. It reverses a direct user decision made on 2026-08-15 (ENH-3207).
4. It is **Claude-Code-only** (the other runners no-op the flag,
   `docs/reference/HOST_COMPATIBILITY.md:250`) and only fires when `automation_profile
   is not None` (`host_runner.py:374`), so it never covers an interactive
   `/ll:audit-docs` run.

**(b) Prose route (SELECTED)** — the flag stays off; each of the five spawn sites
declares an explicit `run_in_background` value (`false` everywhere except
`go-no-go:174`, which stays `true`). Accepted cost: prose is **advisory to the model,
not mechanical** — nothing enforces compliance at the tool layer, and it is per-site, so
a new skill silently regresses. That regression risk is what the two-sided inventory
test under Tests exists to close; it is the mechanical half of this route and is not
optional.


## Current Behavior

Five sites — `audit-docs/SKILL.md:120-139`, `audit-claude-config/SKILL.md:118,222`,
`audit-issue-conflicts/SKILL.md:205,218,252`, `wire-issue/SKILL.md:147-190`, and
`go-no-go/SKILL.md:278` — instruct
Agent/Task spawns with prose like "wait for results" (or, at `go-no-go:278`, the
explicit word "**foreground**") but no `run_in_background` value
on the tool call itself. The Agent tool defaults to background execution. Under a
headless turn, `subprocess_utils.py`'s stream-close handling (~lines 590-648) detects
the parent turn's `result` event, then waits `post_stream_close_grace_seconds` (default
300s, `config/automation.py:26`) for the OS process to exit before `_kill_process_group()`
(`subprocess_utils.py:307`) SIGKILLs the whole process group — it waits for the parent
process only, never joins individual still-running subagents.

Seven places in the codebase and docs describe `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`'s
reach with a Bash-only example and no mention of Agent-tool spawns — incomplete against
FEAT-3076 § Findings (one of the seven, `host_runner.py:243-252`, is exclusively worded
and genuinely misleading; the rest say "e.g."). This under-description is what mis-framed
this bug at capture, and correcting it is unconditional scope (see Documentation below).

## Expected Behavior

Every Agent/Task spawn in an automation-driven skill either declares
`run_in_background: false` and is awaited synchronously in the same turn, or declares
`run_in_background: true` as a documented, deliberate exception (as
`go-no-go/SKILL.md:174` is). No spawn site relies on the tool's default, and no headless
turn ends with a subagent whose result the parent turn never reads. In particular, a
skill that says "foreground" states `run_in_background: false` rather than omitting the
directive.

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
session). Both are viable; which one the implementer picks determines whether the five
skill files or `session_start.py` (or both) get edited. Note the central option cannot
fully replace the per-site one: `_STAY_IN_TURN_INSTRUCTION` is gated on `LL_AUTOMATION`,
so it never reaches an interactive `/ll:audit-docs` run, and it cannot express the
per-site distinction `go-no-go` needs (`:174` background, `:278` foreground). Treat
centralization as reinforcement, not a substitute. `go-no-go:174`'s fan-out stays
exempted — settled under Key Decision, no longer deferred.

## Integration Map

### Files to Modify
- `skills/audit-docs/SKILL.md:120-139` — Task spawn instruction, no `run_in_background` directive
- `skills/audit-claude-config/SKILL.md:118,222` — two Task spawn sites, no directive
- `skills/audit-issue-conflicts/SKILL.md:205,218,252` — Task spawn sites, no directive
- `skills/wire-issue/SKILL.md:147-190` — Agent spawn sites (3 agents); has a "wait...in
  this same turn" prose instruction but no mechanical `run_in_background: false`
- `skills/go-no-go/SKILL.md:278` — the judge-agent spawn. Prose says "Launch a
  **foreground** judge agent (no `run_in_background`)"; because the tool defaults to
  background, omitting the directive yields the opposite of the stated intent. Takes an
  explicit `run_in_background: false`. **Do not touch `:174`** — that one is the
  deliberate `true` fan-out and must stay as-is to keep
  `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` satisfied.
- `skills/confidence-check/SKILL.md` — **not currently in scope**; no Agent/Task spawn
  exists (see Current Behavior correction above)

### Dependent Files (Existing Precedent)
- `skills/decide-issue/SKILL.md:335,340` — the one skill with a mechanical
  `run_in_background: false` directive plus a prose backstop
- `skills/go-no-go/SKILL.md:174` — intentional background fan-out; prose-only
  wait at `:274`, no mechanical backstop; the one entry in
  `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` (`scripts/tests/test_wiring_skills_and_commands.py:442-464`).
  Precedent only — `:278` in the same file is a fix target, not precedent (see above)
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

**Primary test requirement (supersedes the `DOC_STRINGS_PRESENT` approach below).**
Pinning new wording via `DOC_STRINGS_PRESENT` needles pins *phrasing*, not the
invariant, and catches nothing for a skill added later. Instead, make
`test_skill_run_in_background_true_inventory_pinned`
(`test_wiring_skills_and_commands.py:442`) **two-sided**: every Agent/Task spawn site
across `skills/**/SKILL.md` must carry an explicit `run_in_background` value, with
`skills/go-no-go/SKILL.md` the sole entry in the `true` allowlist. A new skill that
spawns an Agent with no directive then fails the suite. `DOC_STRINGS_PRESENT` tuples
remain optional belt-and-braces, not the gate.

**The detector must be specified in this issue, not invented at implementation time.**
"Agent/Task spawn site" has no reliable syntactic marker in markdown prose — there is no
tool-call AST to walk, only English. A naive `grep -l 'Task tool'` over `skills/**/SKILL.md`
**fails `confidence-check`**, whose only match is the non-spawning checklist line
`SKILL.md:235` ("Integration points use established mechanisms (Skill tool, Task tool,
config references)") — a skill this issue explicitly rules out of scope. Ship the
detector as:

1. **Candidate match** — a line containing `Agent tool`, `Task tool`, `subagent_type`,
   or `` `Agent` `` **and** an imperative spawn verb (`Launch`, `Spawn`, `Dispatch`,
   `Invoke`, `Run ... agent`). The verb requirement is what excludes `:235`-style
   descriptive prose.
2. **Satisfied** — an explicit `run_in_background: true|false` appears within ±3 lines
   of the candidate, or in the same markdown paragraph.
3. **Exempt list** — a module-level `SPAWN_DETECTOR_EXEMPT` set of
   `(path, line_substring)` pairs for descriptive-prose false positives, seeded with the
   `confidence-check/SKILL.md:235` line. Each entry carries a one-line comment saying
   why it is not a spawn. An empty-by-default exempt list is wrong here; the false
   positive is already known to exist.
4. **Assertion** — every unexempted candidate is satisfied, and the set of files with a
   `true` value equals `{"skills/go-no-go/SKILL.md"}` (the existing one-sided check,
   retained unchanged).

The detector is deliberately conservative: it under-detects rather than over-detects, so
a genuinely novel spawn phrasing can slip through. That is the accepted residual risk of
route (b) and is stated in Impact.

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

**Unconditional scope** — **seven** locations (not six; `API.md` was missed at wiring)
describe `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`'s reach in terms that omit Agent-tool
spawns. This is not contingent on which Key Decision route is taken. Correct all seven,
or split them into a standalone P3 docs issue and mark it `blocks:` this one — do not
leave them as conditional side-scope.

**Framing correction (2026-08-15).** An earlier draft called these seven "factually
wrong" assertions that the flag is "scoped to Bash `run_in_background`". Re-reading the
actual text, that overstates the defect and would draw pushback at review:

- Five of them say *"tool-level background tasks (**e.g.** `Bash run_in_background:
  true`)"* — an illustrative example, not an exclusive claim. They are **incomplete**,
  not wrong: correct by naming Agent-tool spawns alongside the Bash example.
- Only `host_runner.py:243-252` reads exclusively ("via tool-level backgrounding
  (`Bash run_in_background: true`)" as the sole mechanism named in a docstring whose job
  is to be the definitive description). That one is genuinely misleading.

The fix is the same edit in all seven — add Agent-tool spawns — but the issue should not
claim a factual error where the text says "e.g.".

- `scripts/little_loops/host_runner.py:243-252` — the runner docstring; the one
  exclusively-worded site
- `docs/reference/API.md:9514` — **missing from the original list**; same
  `disable_background_tasks` description, Bash-only example
- `docs/reference/HOST_COMPATIBILITY.md:250` — `[^bgtasks]` footnote [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:1236` — `orchestration.disable_background_tasks` table
  row [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:638` — "Automation-Context Pruning" section, second
  paragraph [Agent 2 finding]
- `docs/ARCHITECTURE.md:738` — `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` component-table
  row [Agent 2 finding]
- `scripts/little_loops/config-schema.json:1762` — `disable_background_tasks` property's
  schema-embedded `description` string [Agent 2 finding]

**Pre-existing inconsistency to sweep while in these files.** The runner count
disagrees across the same set of docs — `HOST_COMPATIBILITY.md:250` says "the other
**six** runners"; `host_runner.py:251`, `ARCHITECTURE.md:738`, `API.md:9514`, and
`scripts/tests/test_host_runner.py:90` all say "**five**". Pick the correct count
against the actual `HostRunner` implementations and make all five sites agree. This
issue's own Environment section currently repeats the "six" figure and must be corrected
to match.

### Configuration
- N/A — no config file governs this; `LL_AUTOMATION` (env var) and
  `orchestration.disable_background_tasks` (`.ll/ll-config.json`) are the two related
  signals, both already wired

## Implementation Steps

0. **DONE** — the Key Decision is recorded above: route (b), with route (a)'s rejection
   reasons stated (chiefly that the flag would break the `ll-parallel`/`go-no-go`/
   `manage-issue` carve-outs per FEAT-3076's conclusion).
1. All five spawn sites declare an explicit `run_in_background: false` —
   `audit-docs`, `audit-claude-config`, `audit-issue-conflicts`, `wire-issue`, and
   `go-no-go:278` — following the wording at `decide-issue/SKILL.md:335`.
   Not `confidence-check`, which has no spawn site today.
2. `go-no-go/SKILL.md:174`'s deliberate `true` fan-out is left unchanged and documented
   in-place as an explicit carve-out. Its sibling at `:278` is **not** part of that
   carve-out — it is fixed under step 1. The file remains the sole member of
   `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`, so that test needs no edit.
3. Any wording reused from `skills/manage-issue/SKILL.md`'s "Headless-Safe Final Test
   Run" section preserves the exact strings pinned in `DOC_STRINGS_PRESENT`
   (`test_wiring_skills_and_commands.py` ~:202-203).
4. If `skills/wire-issue/SKILL.md` or `skills/audit-issue-conflicts/SKILL.md` are
   edited, their mirrors are regenerated
   (`ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply`)
   — only `wire-issue`'s mirror is currently test-guarded, so drift in the other would go
   uncaught otherwise.
5. `test_skill_run_in_background_true_inventory_pinned` is extended to its two-sided form
   using the four-part detector specified under Tests (candidate match requires an
   imperative spawn verb; ±3-line satisfaction window; `SPAWN_DETECTOR_EXEMPT` seeded
   with `confidence-check/SKILL.md:235`; `true`-set equality retained) — this is the
   gate, not `DOC_STRINGS_PRESENT` needles. A test asserting the detector does **not**
   flag `confidence-check` is part of this step, since that false positive is already
   known.
6. The seven incomplete `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`-scope descriptions are
   corrected to name Agent-tool spawns (or split to a linked docs issue), the
   five-vs-six runner-count inconsistency is reconciled across all five sites, and
   `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` passes.

## Impact

- **Priority**: P2 — silent loss of subagent findings in headless automation; wrong
  results rather than a crash, but no operator-visible signal when it happens.
- **Effort**: Medium — five spawn sites across five skill files, three mirror
  regenerations, a two-sided inventory test with a specified detector, and seven doc
  corrections. (Route a, rejected, would have been Small.)
- **Risk**: Medium — the selected route (b) ships an advisory-only contract that nothing
  enforces at the tool layer; the inventory test closes the regression path but is a
  deliberately conservative detector, so a novel spawn phrasing can still slip through.
  Mirror drift in `audit-issue-conflicts` is currently uncaught. Editing
  `go-no-go/SKILL.md` requires care not to disturb `:174`, whose `true` value the
  allowlist test pins.
- **Breaking Change**: No. `go-no-go`'s judge agent (`:278`) becomes genuinely
  foreground, which is the behavior its own prose already promises.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-16 | Priority: P2

## Steps to Reproduce

1. Ensure `orchestration.disable_background_tasks` is `false` (the default since
   ENH-3207; it is set explicitly to `false` in this repo's `.ll/ll-config.json:134`).
2. Run one of the four skills under a headless turn — e.g. `ll-auto` or an FSM prompt
   state that invokes `/ll:audit-docs`, which spawns Task agents at
   `skills/audit-docs/SKILL.md:120-139` with no `run_in_background` value.
3. Observe: the Agent tool defaults to background, so the parent turn can emit its
   stream-json `result` event while a subagent is still running. `subprocess_utils.py`
   waits `post_stream_close_grace_seconds` (300s) for the parent OS process only, then
   `_kill_process_group()` SIGKILLs the group — the subagent's findings are never read
   into the parent turn and no error is surfaced.

## Root Cause

- **Files**: `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md`,
  `skills/audit-issue-conflicts/SKILL.md`, `skills/wire-issue/SKILL.md`,
  `skills/go-no-go/SKILL.md`
- **Anchor**: Agent/Task spawn instructions at audit-docs:120-139,
  audit-claude-config:118,222, audit-issue-conflicts:205,218,252, wire-issue:147-190,
  go-no-go:278
- **Cause**: these skills instruct Agent/Task spawns with prose ("wait for results",
  "**foreground**") but no `run_in_background: false` directive on the tool call itself.
  At `go-no-go:278` the prose is self-refuting — it names the desired mode ("foreground")
  while parenthetically instructing the omission ("no `run_in_background`") that produces
  the opposite. The Agent tool
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
  one named carve-out (`SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`) and **stays exempted**
  — settled, not deferred. The carve-out is scoped to `:174` alone; the judge spawn at
  `:278` in the same file is a fix target.
- `confidence-check/SKILL.md` is not in scope — no Agent/Task spawn site exists today;
  confirm before treating it as one of the fix's targets.

## Error Messages

None — this failure is silent by construction. The nearest observable symptom is an
exit-143 (SIGKILL) automation run, which BUG-2731 already classifies as INFRA_RETRY, so
it is attributed to infrastructure rather than to a dropped subagent result.

## Environment

Claude Code host only (the other `HostRunner` implementations no-op
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `docs/reference/HOST_COMPATIBILITY.md:250`).
Deliberately unnumbered here: the docs disagree on whether that count is five or six
(see Documentation § Pre-existing inconsistency); fill in the verified number when that
sweep lands.
Headless `claude -p` turns: `ll-auto`, `ll-parallel`, `ll-sprint`, FSM prompt states.

## Frequency

Every headless invocation of the four named skills is exposed; whether the result is
actually lost depends on whether the subagent outlives the parent turn's `result` event.

## Session Log
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:20:15 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:51 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
