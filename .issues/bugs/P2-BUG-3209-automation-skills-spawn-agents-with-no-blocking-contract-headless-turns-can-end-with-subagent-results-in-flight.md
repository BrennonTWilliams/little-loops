---
id: BUG-3209
type: BUG
title: Automation skills spawn Agents with no blocking contract; headless turns can
  end with subagent results in flight
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:18Z'
completed_at: '2026-08-16T09:16:28Z'
relates_to:
- ENH-3210
decision_needed: false
confidence_score: 100
outcome_confidence: 88
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3209: Automation skills spawn Agents with no blocking contract; headless turns can end with subagent results in flight

## Summary

**Eighteen** agent-spawning line anchors — across **thirteen files** (six skills, one
skill companion file, six commands) — issue Agent/Task tool calls with no explicit
`run_in_background` value.

**The inventory table below is authoritative for scope**; every scalar count in this issue
is derived from it, not the reverse. Earlier drafts said "thirteen sites", which was the
table's *row* (file) count misread as a line-anchor count. Two corrections landed
2026-08-16 alongside the count fix: `audit-issue-conflicts:218` was removed (it is the
"Wait for all batch agents' results" line, not a spawn instruction — the detector's
imperative-verb criterion would never flag it), and `go-no-go:174` was **added** as a fix
target by Key Decision 2's Option A resolution.

**Scope corrected 2026-08-16 (third pass): `skills/manage-issue/SKILL.md:110` is an
additional site, and it is the most important one in the set.** Phase 1.5 says "Spawn
these agents in parallel using the Task tool:" (three agents), backed by a prose-only
"**CRITICAL**: Wait for ALL sub-agent tasks' results synchronously in this same turn"
at `:116` — and no directive. Earlier drafts cited this file **only** as the wording
precedent for the fix (its "Headless-Safe Final Test Run" section, `:376-398`), never
noticing that its own Agent spawn commits the defect that section exists to prevent.
Two consequences:

- **The precedent file must be fixed, not just quoted.** `manage-issue` is the most
  frequently driven skill in headless automation (`ll-auto`, `ll-parallel`, `ll-sprint`
  all run it end-to-end), so its unqualified three-agent fan-out is the highest-exposure
  site in the entire inventory — higher than `refine-issue:186`.
- **The two-sided detector flags it on landing.** Line `:110` matches criterion 1
  (`Task tool` + imperative `Spawn`) and nothing within ±3 lines carries a
  `run_in_background` value, so step 5's test **fails** unless this site is fixed or
  exempted. Exempting it is the wrong resolution: it is a real spawn, in the file this
  issue holds up as the model for headless safety.

**Scope corrected 2026-08-15 (second pass).** Earlier drafts scoped this to
`skills/**/SKILL.md` only, which is one directory too narrow on two counts:

- **`commands/*.md` have the identical defect.** Six of them spawn agents with the same
  "wait for their results in this same turn" prose and no directive. Two —
  `commands/refine-issue.md:186` and `commands/tradeoff-review-issues.md:81` — carry
  *verbatim* the wording this issue treats as the aspirational prose backstop, and
  `refine-issue` runs under `ll-auto`/FSM prompt states routinely. The bug's own
  reproduction path therefore runs through a file the original scope excluded.
- **A companion file holds the real spawn instruction for an in-scope skill.**
  `skills/audit-claude-config/SKILL.md:118` says "Spawn all 3 agents in a SINGLE
  message," but the verbatim prompt bodies and the operative spawn line live in
  `skills/audit-claude-config/wave1-prompts.md:9` ("Spawn all three Wave-1 agents in a
  SINGLE message with multiple Task tool calls"), which `SKILL.md` explicitly points to
  "so each Task can be issued with its full prompt without inflating the main skill
  file." Fixing `SKILL.md` alone leaves the operative instruction unqualified.

Full site inventory:

| File | Sites |
| --- | --- |
| `skills/audit-docs/SKILL.md` | :120-139 (operative spawn sentence wraps :122-123) |
| `skills/audit-claude-config/SKILL.md` | :118, :222 |
| `skills/audit-claude-config/wave1-prompts.md` | :9 |
| `skills/audit-issue-conflicts/SKILL.md` | :205, :252 (**not** :218 — that is wait-prose, not a spawn) |
| `skills/wire-issue/SKILL.md` | :147-190 (`:147` is the phase heading; operative line is **:149**) |
| `skills/manage-issue/SKILL.md` | :110 (Phase 1.5, 3 agents; wait-prose at :116) |
| `skills/go-no-go/SKILL.md` | :174, :278 — **both take `false`** (Key Decision 2, Option A) |
| `commands/refine-issue.md` | :186 |
| `commands/tradeoff-review-issues.md` | **:79** (spawn), :81 (single-message rule) |
| `commands/manage-release.md` | :134 |
| `commands/scan-codebase.md` | :95, :97, :101 |
| `commands/audit-architecture.md` | :68 |
| `commands/analyze-workflows.md` | :102 |

**Anchor granularity — corrected 2026-08-16.** The table is accurate at *file* granularity
and was, in three rows, one line off at *instruction* granularity. The distinction matters
because step 1 edits a sentence, not a file, and because the detector's inventory-superset
test (Tests § part 5) pins these anchors:

- `audit-docs`: `:120` is the section heading `### 2. Audit Each Document (Fan Out to
  Subagents)`. The operative sentence wraps across `:122-123` — "For each discovered file,
  spawn a\n`codebase-analyzer` subagent via the `Task` tool."
- `wire-issue`: `:147` is the heading `## Phase 4: Run Wiring Research (3 Parallel
  Agents)`; the spawn instruction is at `:149`.
- `tradeoff-review-issues`: `:79` is the spawn ("For each wave, launch a subagent using the
  Task tool:"); `:81` is the separate single-message/wait rule. **Both** lines are in the
  same paragraph-scoped candidate, so one directive attached at `:79` satisfies the
  detector — but `:79` is the line to edit, not `:81`.

The scalar count is unchanged at **eighteen anchors**: none of the three corrections adds a
spawn site, they relocate an existing one within its own paragraph. `tradeoff-review-issues`
`:79`/`:81` are two lines of one spawn instruction, not two spawns.

**Tool-name drift — decided: leave the names alone, widen the detector instead.** Most
sites say "Task tool"; the tool this host actually exposes is `Agent`, which is what carries
the `run_in_background` parameter. The names are historical and the model maps them without
trouble, so renaming eighteen anchors is scope this fix does not need — and it would churn
two mirror-guarded skills (`wire-issue`, `manage-issue`) plus several `DOC_STRINGS_PRESENT`
needles for no behavioral gain. The consequence is a hard requirement on the detector: its
marker set must keep **both** spellings permanently (see Tests § criterion 1), because the
corpus will keep mixing them. If a future issue does normalize the naming, it must not
narrow the marker set on the way through.

(`skills/confidence-check/SKILL.md` was named at capture but has **no** Agent/Task spawn
site anywhere in `SKILL.md`, `reference.md`, or `rubric.md`, and omits `Task`/`Agent`
from its `allowed-tools` frontmatter, lines 6-15 — it is not in scope. Its only
`Task tool` mention is prose in a checklist item, `SKILL.md:235`; see the detector
caveat under Tests.)

**`go-no-go/SKILL.md` has *two* spawn sites, not one, and both are fix targets.** Earlier
drafts treated this file as the exempt precedent; Key Decision 2 (Option A, settled) ends
that exemption.

- `:174` — currently `run_in_background: true`, stated as a deliberate parallel fan-out;
  today the sole entry in `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`. **Flips to `false`**
  per Key Decision 2: the exemption rested on backgrounding being required for a parallel
  fan-out, which step 1b denies, and `:174` is itself a single-message fan-out whose only
  barrier is prose 100 lines away at `:274`.
- `:278` — "Launch a **foreground** judge agent (no `run_in_background`) using the Agent
  tool." The stated intent is foreground, but the Agent tool **defaults to background**,
  so omitting the directive produces exactly the opposite of what the prose says. This
  is the bug verbatim. Takes an explicit `run_in_background: false`.

Consequence: `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` becomes **empty**, and this issue
has no `true` carve-out anywhere.

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
true` fixes every site at once, mechanically, with no prose edits. ENH-3207
(2026-08-15, direct user decision) flipped that default `true → false`, making it
opt-in. Resolving that tension is Step 1 below — see **Key Decision**.

## Key Decision — SETTLED: route (b), the prose route

**Decided 2026-08-15.** Recorded here per this section's own requirement that the
rejected route's reason be stated.

**(a) Config route (REJECTED)** — automation runs set
`orchestration.disable_background_tasks: true`. Mechanical, covers every spawn site in the inventory table
plus any skill added later, zero prose edits. Rejected on four costs, the first of which
is decisive:

1. **It breaks the carve-outs that depend on backgrounding working.** (Recorded as the
   decisive cost when route (a) was rejected. Note Key Decision 2 later removed the
   `go-no-go:174` carve-out itself; the `ll-parallel` async launch/notify cost below is
   unaffected and still decisive.) FEAT-3076's own
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

**(b) Prose route (SELECTED)** — the flag stays off; every spawn site in the inventory
table declares an explicit `run_in_background: false` (Key Decision 2 removed the last
`true` carve-out). Accepted cost: prose is **advisory to the model,
not mechanical** — nothing enforces compliance at the tool layer, and it is per-site, so
a new skill silently regresses. That regression risk is what the two-sided inventory
test under Tests exists to close; it is the mechanical half of this route and is not
optional.


## Key Decision 2 — SETTLED: Option A, `go-no-go:174` flips to `false`

**Contradiction found 2026-08-16, pre-implementation review; resolved the same day. The
resolution was swept through the whole issue on 2026-08-16 — no section should still
describe `:174` as an exemption. If you find one, it is a stale edit, not a competing
decision.**

- **Step 1b's premise:** "'Parallel fan-out' is not a reason to background: multiple Agent
  calls issued in a *single message* already run concurrently while still blocking the
  turn," citing `decide-issue/SKILL.md:335` as the settling precedent. The issue applies
  this to force `false` on five command-level fan-outs
  (`scan-codebase`/`audit-architecture`/`manage-release`/`refine-issue`).
- **The exemption:** `go-no-go/SKILL.md:174` keeps `run_in_background: true` as a
  "deliberate parallel fan-out."

But `:174` is *itself* a single-message multi-Agent fan-out — verbatim: "In a **single
message**, launch both agents concurrently using the `Agent` tool with
`run_in_background: true`." If step 1b's premise is true, the `true` there buys nothing
that `false` would not also give, **and `:174` is a live instance of the exact defect this
issue exists to fix**: two backgrounded agents whose only barrier is prose at `:274`
("Wait until both background agents have completed and returned their full outputs"), in a
skill driven headlessly by `ll-auto`. The issue names that prose-only pattern as "a weaker
guarantee, not an enforcement" in the Summary, then exempts the site that has it.

Two coherent resolutions; pick one before implementing (Option A recommended):

> **Selected:** Option A — flip `:174` to `false`; the `true` allowlist becomes empty.

**Option A: flip `:174` to `false`; the `true` allowlist becomes empty — RECOMMENDED.**
Consistent with step 1b, removes the last prose-only barrier, and collapses the two-sided
detector's assertion to the much stronger and simpler "every spawn site declares
`run_in_background: false`" with no allowlist to maintain. Costs: it reverses a deliberate
existing choice, so it needs a recorded rationale; `test_skill_run_in_background_true_inventory_pinned`
changes from a set-equality check against `{"skills/go-no-go/SKILL.md"}` to an
empty-set assertion (the constant and its message still get renamed per Tests § Widening);
and `go-no-go`'s Step 3c wait-prose at `:274` should be folded into the `:174` sentence
since it becomes redundant. If concurrency measurably regresses, that falsifies step 1b —
in which case the five command fan-outs are also mis-specified and **(b)** is the correct
answer for all of them.

**Option B: keep `:174` at `true`.** Then step 1b's premise must be qualified rather than
asserted flatly, and this issue must state the property `:174` gets from `true` that a
single-message `false` fan-out does not — measured, not assumed. It must also state why
the prose-only barrier at `:274` is acceptable there when the Summary rejects that same
pattern everywhere else, and pair the carve-out with a mechanical backstop or an explicit
accepted-risk note.

Whichever is chosen, record it here the way Key Decision records route (a)/(b) — with the
rejected option's reason — because the two-sided detector's allowlist shape depends on it.

### Decision Rationale

**Selected: Option A** — flip `go-no-go/SKILL.md:174` to `run_in_background: false`; the
`true` allowlist becomes empty.

Two independent codebase-evidence passes (`ll:codebase-pattern-finder`, one per option)
converged on Option A:

- **Pattern precedent (`decide-issue/SKILL.md:335`)** is structurally identical to
  `go-no-go:174` — a single-message, multi-Agent fan-out — and already uses
  `run_in_background: false` with an in-turn wait, not a separated prose-only barrier
  like `go-no-go`'s `:174`/`:274` split. Option A brings the sole outlier into
  conformance with the only other multi-agent fan-out site in the codebase.
- **FEAT-3077 (done, 2026-08-08) is the prior decision on this exact line**, and its own
  rationale undercuts Option B: it kept `true` because the carve-out was "latent, not
  live" (unreachable under automation today, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` never
  reaches `/ll:go-no-go` via its CLI invocation path), and it explicitly states that under
  the flag, `run_in_background: true` "would lose *concurrency*... not correctness" — i.e.
  `true` was never claimed to provide a property `false` lacks, only that leaving it alone
  cost nothing at the time. BUG-3209's Key Decision 2 reopens exactly this: step 1b's
  premise (single-message fan-out is already concurrent under `false`) applies here as much
  as it does to the five command fan-outs, and no functional-necessity evidence (timeout
  avoidance, streaming/progress requirement, auth/isolation fix) was found tied to `true`
  specifically at `:174` (BUG-1514's fix at this same file addressed `isolation: "worktree"`,
  unrelated to backgrounding).
- **Simplicity/testability**: Option A collapses
  `test_skill_run_in_background_true_inventory_pinned`'s `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`
  from a one-member set to an empty-set assertion — no allowlist to maintain, no per-site
  exemption to justify to future readers.

**Scoring summary** (Consistency / Simplicity / Testability / Risk, 0–3 each):

| Option | Consistency | Simplicity | Testability | Risk | Total |
| --- | --- | --- | --- | --- | --- |
| A (flip to `false`) | 3 | 3 | 3 | 2 | 11/12 |
| B (keep `true`) | 1 | 2 | 2 | 1 | 6/12 |

**Rejected: Option B** — keep `:174` at `true`. Rejected because its only supporting
evidence (FEAT-3077) is a reachability argument, not a functional-necessity argument, and
it is the sole precedent for itself in the codebase — the one structurally identical
pattern elsewhere (`decide-issue:335`) already uses `false`. Per Implementation Step 2,
`go-no-go`'s Step 3c wait-prose at `:274` is folded into the `:174` sentence since it
becomes redundant once `:174` states `run_in_background: false` and waits in-turn like
`decide-issue:335`/`:340`.

## Current Behavior

Every site in the Summary's inventory table — across `skills/**/*.md` and
`commands/*.md` — instruct
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

Every Agent/Task spawn in an automation-driven skill or command declares
`run_in_background: false` and is awaited synchronously in the same turn. No spawn site
relies on the tool's default, and no headless turn ends with a subagent whose result the
parent turn never reads. In particular, a skill that says "foreground" states
`run_in_background: false` rather than omitting the directive.

There is **no `true` carve-out** after this issue lands (Key Decision 2, Option A). A
future one is permitted, but only as a deliberate allowlist append with a recorded
FEAT-3077-style rationale — never as a silent omission of the directive.

## Motivation

Without a blocking contract, headless runs (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM
prompt states) can silently drop subagent findings — the parent turn ends, the
notification never arrives, and up to `post_stream_close_grace_seconds` (300s) later the
still-running agent is killed rather than awaited. This is the same failure class
BUG-3058 and `manage-issue/SKILL.md`'s "Headless-Safe Final Test Run" section already
guard against for Bash test runs; none of them has an equivalent guard.

The `commands/` half of the scope is the higher-exposure half: `refine-issue`,
`tradeoff-review-issues`, and `manage-release` are invoked from FSM prompt states and
`ll-auto` runs far more often than the audit skills are.

**Downstream link to ENH-3210 — mechanism sound, measurement RETRACTED 2026-08-16.**
When a spawn is backgrounded and the parent turn ends, the process group is reaped before
`SubagentStop` fires, so the `subagent_runs` row opened by `SubagentStart` is never closed
and stays `running`. ENH-3210 catalogues 40 such rows. That mechanism is sound and remains
the most likely explanation for them.

**The evidence this issue previously offered for the link does not hold.** An earlier draft
claimed `.ll/history.db` held 43 `running` rows whose three newest were the `/ll:wire-issue`
fan-out run while wiring this very issue, "orphaned":

    2026-08-16T03:57:21Z  ll:codebase-locator
    2026-08-16T03:57:30Z  ll:codebase-analyzer
    2026-08-16T03:57:38Z  ll:codebase-pattern-finder

Those three rows were sampled **mid-flight**. All three closed normally roughly two minutes
later (`ended_at` 03:59:05Z / 03:59:37Z / 03:59:09Z, `status = completed`), verified directly
against the DB. Re-measured after they closed: 40 `running` / 2,741 `completed`, newest
`running` row **2026-08-15T03:48:55Z** — nothing from 2026-08-16 is stuck, and the stale
population is July-heavy with ≤1 new row per day since 2026-08-01.

Consequences:

- **Do not restate "this bug is the generator" as measured fact.** No individual stale
  `subagent_runs` row has been traced to a specific site in the inventory table. The claim
  is a well-supported hypothesis, not an observation.
- The Steps to Reproduce below are the reproduction path for this issue — there is no
  stronger observed artifact to point at.
- `relates_to: ENH-3210` (on both issues) stands.
- **Sequencing this issue before ENH-3210 is still the sensible order** — it plausibly cuts
  the generation rate at the source while ENH-3210 reconciles the backlog — but it is a
  preference, not a dependency, and ENH-3210 is explicitly designed to stand alone.
- Landing this issue does **not** make ENH-3210 unnecessary: the 40 accumulated rows stay
  `running` regardless.
- Note the retraction cuts the other way too, in ENH-3210's favour: three *live* subagents
  presenting exactly the "orphaned" signature is the concrete justification for that issue's
  minimum-age guard.

## Proposed Solution

State the blocking contract either per-skill (declare `run_in_background: false` at each
spawn site, following the pattern at `decide-issue/SKILL.md:335`) or centrally (extend
the existing `_STAY_IN_TURN_INSTRUCTION` injection in `session_start.py`, the one
host-agnostic mechanism that already puts automation-only context into every headless
session). Both are viable; which one the implementer picks determines whether the twelve
skill/command files or `session_start.py` (or both) get edited. Note the central option
cannot fully replace the per-site one: `_STAY_IN_TURN_INSTRUCTION` is gated on
`LL_AUTOMATION`,
so it never reaches an interactive `/ll:audit-docs` run, and it is a blanket instruction
that cannot express per-site intent. Treat centralization as reinforcement, not a
substitute. Both `go-no-go` sites (`:174` and `:278`) take `false` — Key Decision 2,
Option A.

## Integration Map

### Files to Modify
- `skills/audit-docs/SKILL.md:120-139` — Task spawn instruction, no `run_in_background`
  directive. Operative sentence wraps `:122-123`; that is where the directive attaches.

  **This site has an existing concurrency contract the directive must not weaken.**
  `:126-136` specify a *required sequential batch loop*: split the file list into batches of
  **at most 6**, send one batch's `Task` calls per message, "**Wait for every result in that
  batch to return** before sending the next batch's `Task` calls," repeat. The bound exists
  to keep `full`/`dir:` scopes from exhausting the concurrent-agent API limit (`:138-139`).

  A generic "…and wait for all results in this same turn," appended verbatim from the
  `decide-issue:335` precedent, reads as license to fan out every file at once — the exact
  behavior the batch loop forbids. Word it **per batch**: the directive belongs on the
  batch's spawn (`run_in_background: false` on each `Task` call in the batch), and the
  existing "wait for every result in that batch" sentence already supplies the barrier, so
  no second wait sentence is needed here. Leave `:126-136`'s numbered steps untouched.
- `skills/audit-claude-config/SKILL.md:118,222` — two Task spawn sites, no directive
- `skills/audit-claude-config/wave1-prompts.md:9` — the **operative** Wave-1 spawn line;
  `SKILL.md:118` delegates the full prompt bodies here by design ("so each Task can be
  issued with its full prompt without inflating the main skill file"). Editing `SKILL.md`
  without this file leaves the instruction the model actually follows unqualified
- `skills/audit-issue-conflicts/SKILL.md:205,218,252` — Task spawn sites, no directive
- `skills/wire-issue/SKILL.md:147-190` — Agent spawn sites (3 agents); has a "wait...in
  this same turn" prose instruction but no mechanical `run_in_background: false`. `:147` is
  the phase heading; the spawn instruction is at **`:149`**
- `skills/manage-issue/SKILL.md:110` — Phase 1.5 "Deep Research", "Spawn these agents in
  parallel using the Task tool:" (locator / analyzer / pattern-finder). Prose-only
  backstop at `:116` ("**CRITICAL**: Wait for ALL sub-agent tasks' results synchronously
  in this same turn"), no directive. Highest-exposure site in the inventory — `ll-auto`,
  `ll-parallel`, and `ll-sprint` drive this skill end-to-end. Note this file is *also* the
  wording precedent (`:376-398`); it is both a source and a target, and the two roles must
  not be confused when editing. Its detailed agent prompts live in
  `skills/manage-issue/templates.md`, which contains **no** spawn line of its own
  (verified) — unlike `audit-claude-config`, the operative instruction really is in
  `SKILL.md` here, so no companion edit is needed
- `skills/go-no-go/SKILL.md:174,:278` — **both sites are fix targets** (Key Decision 2,
  Option A). `:278` is the judge-agent spawn: prose says "Launch a **foreground** judge
  agent (no `run_in_background`)"; because the tool defaults to background, omitting the
  directive yields the opposite of the stated intent. `:174` is the adversarial fan-out,
  flipping `true → false`; fold the now-redundant Step 3c wait-prose at `:274` into the
  `:174` sentence, mirroring `decide-issue/SKILL.md:335,:340`. Editing `:174` **requires**
  updating `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` to the empty set in the same commit —
  the allowlist test fails otherwise. 19 lines of headroom under the 500-line cap, so the
  `:274` fold is net-negative on line count.
- `commands/refine-issue.md:186` — "Spawn them in a SINGLE message with multiple Task
  tool calls, and wait for their results in this same turn"; no directive. Highest-
  exposure site in the set — invoked from FSM prompt states and `ll-auto`. (`:338`
  repeats the wait instruction as a standalone heading; keep both consistent.)
- `commands/tradeoff-review-issues.md:79,:81` — `:79` is the spawn ("For each wave, launch
  a subagent using the Task tool:"), `:81` the single-message/wait rule carrying the same
  verbatim wording as `refine-issue:186`. Neither has a directive; attach it at `:79`
- `commands/manage-release.md:134` — "Spawn all 3 agents in a SINGLE message with
  multiple Task tool calls"; no directive
- `commands/scan-codebase.md:95,97,101` — `--quick` single-agent spawn and the default
  3-agent parallel fan-out; no directive on either. Both take `false`
- `commands/audit-architecture.md:68` — `--deep` branch, "Launch applicable agents in
  parallel"; no directive. Takes `false`
- `commands/analyze-workflows.md:102` — "Spawn the workflow-pattern-analyzer agent using
  the Task tool"; single agent, no directive. Takes `false`

**None of the new command sites is a `true` carve-out candidate, and the parallel ones
must not be read as such.** "Parallel fan-out" is not a reason to background: multiple
Agent calls issued in a *single message* already run concurrently while still blocking
the turn. `skills/decide-issue/SKILL.md:335` is the precedent that settles this — it
spawns "one Agent **per option** in a **single message** with multiple Agent tool calls
(parallel spawn)" and pairs that with `run_in_background: false`. So
`scan-codebase`/`audit-architecture`/`manage-release`/`refine-issue`'s fan-outs keep
their concurrency under `false`. Key Decision 2 applies the identical reasoning to
`go-no-go:174`, so `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` becomes the **empty set**.
- `skills/confidence-check/SKILL.md` — **not currently in scope**; no Agent/Task spawn
  exists (see Current Behavior correction above)

### Dependent Files (Existing Precedent)
- `skills/decide-issue/SKILL.md:335,340` — the one skill with a mechanical
  `run_in_background: false` directive plus a prose backstop
- `skills/go-no-go/SKILL.md:174` — **not precedent; a fix target.** Today it is the one
  entry in `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`
  (`scripts/tests/test_wiring_skills_and_commands.py:445-464`), an intentional background
  fan-out whose only barrier is prose 100 lines away at `:274`. Key Decision 2 flips it to
  `false`. Listed here only because the allowlist constant must be emptied in the same
  commit. Note this file is **not** in `SKILL_MIRRORS_MUST_MATCH_SOURCE`, so no mirror
  regeneration is needed for it
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
  **Precedent only — the spawn at `:110` in the same file is a fix target** (same
  source-and-target split as `go-no-go`'s `:174` / `:278`).

  Two traps specific to this file:

  1. **It already contains the literal string `run_in_background: false`** at `:381`, but
     that one is about the *Bash* final test suite, not the Phase 1.5 Agent spawn 270
     lines earlier. A file-level "does this file mention a directive?" check would wrongly
     pass it. This is concrete justification for the detector's ±3-line / same-paragraph
     scoping (criterion 2) over any file-scoped shortcut.
  2. **`:389` reads ``no `run_in_background:\n  true` ``** — the value is split across a
     line wrap, so the `true`-inventory substring scan does **not** match today and the
     file is correctly absent from `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`. Reflowing
     that paragraph would join the tokens, silently add `skills/manage-issue/SKILL.md` to
     the discovered `true` set, and fail the allowlist assertion. That is a second,
     independent reason not to reflow it (step 3 already forbids it for
     `DOC_STRINGS_PRESENT` reasons) — append, never rewrap.

### Conventions in Force
- Skills that want synchronous behavior state `run_in_background: false` explicitly next
  to the spawn instruction plus a "wait for results" sentence — evidence:
  `decide-issue/SKILL.md:335,:340`, the only conforming site in the corpus today.
  `go-no-go/SKILL.md:174` is the sole `true`, and Key Decision 2 removes it. Nothing is
  left implicit except the sites this bug names.
- The only existing mechanism for conditionally injecting automation-state-dependent text
  into a headless session's context is hook stdout (`session_start.py`'s
  `LLHookResult.stdout`) — there is no in-skill-markdown conditional-branching mechanism
  for this.
- `test_skill_run_in_background_true_inventory_pinned` enforces a set-equality allowlist
  for `run_in_background: true` occurrences across `skills/*.md`, currently
  `{"skills/go-no-go/SKILL.md"}`. Adding `run_in_background: false` to the other named
  files doesn't touch this test; flipping `go-no-go:174` does — **keep the constant and
  set it to `set()`**, do not delete it, so a future `true` still requires a deliberate
  append with a recorded rationale rather than an unguarded reintroduction.

  **Line citations re-verified 2026-08-16 and drifted by 2-3 lines.** Actual anchors:
  `SKILL_MIRRORS_MUST_MATCH_SOURCE` `:372`, `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST`
  **`:445`** (this issue cites `:442`/`:443` in several places),
  `def test_skill_run_in_background_true_inventory_pinned` `:450`, the set-equality
  assertion `:458`, the assertion message `:461`. All are named symbols, so the risk is
  low — but re-anchor by symbol name at implementation rather than trusting any line
  number in this issue.
- Mirror-file drift. `SKILL_MIRRORS_MUST_MATCH_SOURCE`
  (`test_wiring_skills_and_commands.py:372-382`) contains nine tuples covering **three**
  skills × three hosts: `wire-issue`, **`manage-issue`**, and `explore-api`. Two of this
  issue's fix targets are in that guarded list:

  | Skill | Guarded? | Consequence of editing without `ll-adapt` |
  |---|---|---|
  | `skills/wire-issue/SKILL.md` | **yes** (×3 mirrors) | `test_skill_mirror_matches_source` **fails** |
  | `skills/manage-issue/SKILL.md` | **yes** (×3 mirrors) | `test_skill_mirror_matches_source` **fails** |
  | `skills/go-no-go/SKILL.md` | no | no mirror step needed |
  | `skills/audit-issue-conflicts/SKILL.md` | no (mirrors exist on disk) | silent drift, not test-caught |
  | `skills/audit-docs`, `skills/audit-claude-config` | no | silent drift if mirrors exist |

  **`manage-issue` is a hard suite failure, not a drift risk** — it was missing from
  step 4 in earlier drafts, which named only `wire-issue` and `audit-issue-conflicts`.
  Both guarded skills are edited by this issue, so the `ll-adapt` regeneration in step 4
  is mandatory, not conditional.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` —
  `test_skill_run_in_background_true_inventory_pinned` (:442), `DOC_STRINGS_PRESENT`
  (Headless-Safe Final Test Run pinned strings, ~:202-203),
  `SKILL_MIRRORS_MUST_MATCH_SOURCE` (:372-394)
- `scripts/tests/test_enh494_skill_companions.py` —
  `TestSkillLineLimit::test_all_skills_within_limit` (:74), the 500-line-per-`SKILL.md` cap.
  **This is a near-certain failure, not a contingency.** Measured 2026-08-16:

  | File | Lines | Headroom | Sites to edit |
  |---|---|---|---|
  | `skills/manage-issue/SKILL.md` | **499** | **1** | 1 (`:110`) |
  | `skills/wire-issue/SKILL.md` | 493 | 7 | 3 (`:147-190`) |
  | `skills/go-no-go/SKILL.md` | 481 | 19 | 2 (`:174` flip, `:278`) + `:274` fold (net −2) |
  | `skills/audit-claude-config/SKILL.md` | 485 | 15 | 2 (`:118`, `:222`) |
  | `skills/audit-issue-conflicts/SKILL.md` | 474 | 26 | 2 (`:205`, `:252`) |
  | `skills/audit-docs/SKILL.md` | 433 | 67 | 1 (`:120-139`) |

  `manage-issue` has **one line of headroom** and the highest-exposure site in the inventory.
  The wording precedent this issue points at (`decide-issue/SKILL.md:335`) is a directive
  *plus* a "wait for results" sentence — two lines — so a literal copy breaks the cap.
  `wire-issue` at 493 with three sites is the second risk.

  Budget the wording accordingly: for the tight files, fold the directive into the existing
  spawn sentence as an inline clause (e.g. append "… using the Task tool with
  `run_in_background: false`, and wait for all results in this same turn.") rather than adding
  new lines. `manage-issue:116` already carries the "**CRITICAL**: Wait for ALL sub-agent
  tasks' results synchronously in this same turn" prose, so only the directive itself is new
  there — attach it to `:110`'s existing sentence and add no line at all. If any file still
  cannot fit, extract to a flat companion per the ENH-494 pattern rather than deleting
  existing content.

**Primary test requirement (supersedes the `DOC_STRINGS_PRESENT` approach below).**
Pinning new wording via `DOC_STRINGS_PRESENT` needles pins *phrasing*, not the
invariant, and catches nothing for a skill added later. Instead, make
`test_skill_run_in_background_true_inventory_pinned`
(`test_wiring_skills_and_commands.py:442`) **two-sided**: every Agent/Task spawn site
across the scanned corpus must carry an explicit `run_in_background` value, with
`skills/go-no-go/SKILL.md` the sole entry in the `true` allowlist. A new skill or command
that spawns an Agent with no directive then fails the suite. `DOC_STRINGS_PRESENT` tuples
remain optional belt-and-braces, not the gate.

**Scanned corpus — `skills/**/*.md` plus `commands/*.md`, not `skills/**/SKILL.md`.**
Two reasons the narrower glob is wrong:

1. It misses the six `commands/*.md` sites entirely, which is half the bug.
2. It is narrower than the test it amends. The existing one-sided check already scans
   `skills_dir.rglob("*.md")` (`test_wiring_skills_and_commands.py:450`) — companion
   files included. Specifying `SKILL.md` for the new two-sided half would leave
   `audit-claude-config/wave1-prompts.md:9` uncovered by the very assertion added to
   cover it, while the `true`-side of the same test already reaches that file.

Use one glob for both halves of the assertion.

**Widening the glob also widens the `true`-side check — verify and rename.** The existing
one-sided assertion scans `skills_dir.rglob("*.md")` only (`:450`) and its allowlist constant
is named `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` (`:443`). Running the *same* glob for both
halves means the `true`-set equality is now asserted over `commands/*.md` as well.

That is safe today — verified 2026-08-16, `grep -rn "run_in_background" commands/` returns
**zero** matches, so the discovered `true` set is unchanged and the allowlist still equals
`{"skills/go-no-go/SKILL.md"}` with no edit. But it must be stated, because otherwise a
reviewer reads a skills-scoped allowlist being asserted over a corpus its name excludes.
Rename the constant to drop the `SKILL_` prefix (e.g. `RUN_IN_BACKGROUND_TRUE_ALLOWLIST`) so
the name matches the corpus, and update the assertion message, which currently says
"skills/ run_in_background: true inventory drifted".

**The detector must be specified in this issue, not invented at implementation time.**
"Agent/Task spawn site" has no reliable syntactic marker in markdown prose — there is no
tool-call AST to walk, only English. A naive `grep -l 'Task tool'` over the corpus
**fails `confidence-check`**, whose only match is the non-spawning checklist line
`SKILL.md:235` ("Integration points use established mechanisms (Skill tool, Task tool,
config references)") — a skill this issue explicitly rules out of scope. Ship the
detector as:

1. **Candidate match** — a **markdown paragraph** containing a spawn marker **and** an
   imperative spawn verb (`Launch`, `Spawn`, `Dispatch`, `Invoke`, `Run ... agent`). The
   verb requirement is what excludes `:235`-style descriptive prose.

   **Corrected 2026-08-16 — an earlier spec said "a *line* containing `Agent tool`,
   `Task tool`, `subagent_type`, or `` `Agent` ``", and that detector misses five of this
   issue's own eighteen anchors.** Measured against the real files:

   | Missed site | Why the line-scoped, four-marker detector misses it |
   |---|---|
   | `audit-docs:122-123` | "spawn a\n`codebase-analyzer` subagent via the `Task` tool" — verb and marker split by a line wrap |
   | `audit-issue-conflicts:205` | markers are "per Task **call**" / "Task **calls**", not "Task tool" |
   | `audit-issue-conflicts:252` | "spawn one **Task agent**" — not in the marker list |
   | `scan-codebase:95` | "Spawn a single combined **agent** that scans…" — no marker token on the line at all |
   | `scan-codebase:97` | "Launch 3 **sub-agents** in parallel" — same |

   Shipping that detector would leave the regression gate — the mechanical half of route
   (b), and the entire justification for accepting an advisory-only contract — **inert for
   five anchors**: delete the directive from any of them later and the suite stays green.
   Two changes close it:

   - **Widen the marker set** to `Agent tool`, `Task tool`, `` `Agent` ``, `Task call`,
     `Task calls`, `Task agent`, `subagent_type`, `subagent`, `sub-agent`, `sub-agents`.
   - **Scope candidate detection to the markdown paragraph, not the line**, so a marker
     and its verb may sit on different wrapped lines of the same sentence.

   **The two scopes are different and both are deliberate.** Paragraph scope applies to
   *candidate* detection (criterion 1). The `true`-**value** scan stays line-oriented, for
   the `manage-issue:389` reason given under criterion 2's second caveat — a paragraph-scoped
   value scan would join that prohibition's wrapped ``run_in_background:\n  true`` and
   wrongly add the file to the `true` set. Do not unify them.
2. **Satisfied** — an explicit `run_in_background: true|false` appears within ±3 lines
   of the candidate, or in the same markdown paragraph. **Scoping is load-bearing, not a
   nicety:** `skills/manage-issue/SKILL.md` already contains `run_in_background: false` at
   `:381` — about the *Bash* final test suite — 270 lines away from its unqualified Agent
   spawn at `:110`. Any file-scoped shortcut ("does this file mention a directive?") passes
   that file and misses the highest-exposure site in the inventory. Match per-candidate,
   never per-file.

   Second caveat on the `true` side: match the value token, not a bare mention.
   `manage-issue:389` reads ``no `run_in_background:\n  true` `` — a *prohibition*, split
   across a line wrap. It does not match today's substring scan and must not start
   matching. If the detector normalizes whitespace before searching (a natural
   implementation choice for the ±3-line window), it will join those tokens and wrongly
   add `manage-issue` to the `true` set, failing the allowlist assertion. Either keep the
   scan line-oriented or exclude negated forms (`no `/`never` immediately preceding).
3. **Exempt list** — a module-level `SPAWN_DETECTOR_EXEMPT` set of
   `(path, line_substring)` pairs for descriptive-prose false positives. Each entry
   carries a one-line comment saying why it is not a spawn. An empty-by-default exempt
   list is wrong here; the false positives are already known. Seed with:

   - `skills/confidence-check/SKILL.md:235` — checklist prose naming the Task tool as an
     "established mechanism," not a spawn
   - **The flag-documentation class**, which the `commands/` corpus introduces and the
     skills-only corpus did not have: `commands/scan-codebase.md:64`
     (`` `--quick`: Spawn a single combined scan agent… ``),
     `commands/audit-architecture.md:17` (frontmatter `description:` string),
     `commands/audit-architecture.md:438` (usage-block flag list), and
     `commands/analyze-workflows.md:135` ("Manually run: spawn … agent" — a recovery
     instruction to the *user*, not a tool call). These are flag/usage documentation that
     happens to contain an imperative verb, so criterion 1's verb requirement does not
     exclude them.
   - **`commands/audit-architecture.md:51` — SETTLED 2026-08-16: exempt it.** It is a
     flag description that happens to carry an operative-sounding directive ("use the Task
     tool to launch analysis agents in parallel"), in the same flag-documentation class as
     `:17` and `:438` in the same file. The operative spawn instruction the model actually
     follows is `:68`, which step 1 qualifies. Exempting `:51` keeps the whole
     flag-documentation class consistent — qualifying one member of it and not the others
     would be the arbitrary outcome. Every other item in this issue is settled; this one
     was the last "resolve at implementation" and is now closed.
4. **Assertion** — every unexempted candidate is satisfied, and the set of files with a
   `true` value equals **`set()`** (Key Decision 2, Option A). The existing one-sided
   check is retained in structure, with `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` emptied
   rather than deleted — see Conventions in Force.
5. **Detector self-validation — the detector must be tested against the inventory, not
   only used on it.** A detector that flags nothing passes criterion 4 vacuously, which is
   exactly the failure mode the correction under criterion 1 uncovered. Pin the Summary's
   inventory table as a module-level constant of `(path, line)` anchors and assert the
   detector's **candidate set is a superset of it** — i.e. every known spawn site is still
   *detected* as a candidate after the fix, not merely satisfied. This is a separate test
   from criterion 4's assertion and is the one that would have caught the five misses.
   Keeping the constant also gives a future reader the inventory in executable form rather
   than only in this issue's prose.

The detector is deliberately conservative: it under-detects rather than over-detects, so
a genuinely novel spawn phrasing can slip through. That is the accepted residual risk of
route (b) and is stated in Impact.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — `SKILL_MIRRORS_MUST_MATCH_SOURCE`
  (:372-382) is missing three tuples for `skills/audit-issue-conflicts/SKILL.md` against
  its `.gemini`/`.kimi-code`/`.qwen` mirrors — those mirror files already exist on disk
  (confirmed, each with 4 companion files) but drift is currently uncaught; add tuples
  mirroring the `wire-issue`/`manage-issue` block structure [Agent 1 + Agent 3 finding]
- New `DOC_STRINGS_PRESENT` tuples for each of the edited files' new
  `run_in_background: false` spawn-site wording, following the `decide-issue`/BUG-2408
  `(doc_rel, needle, issue_id)` tuple-append pattern [Agent 3 finding]
- `scripts/tests/test_audit_issue_conflicts_skill.py` — phase-scoped substring-slicing
  pattern (keys on `## Phase 4b`/`## Phase 5` headings) is the alternative to a whole-file
  `DOC_STRINGS_PRESENT` needle if a phase-scoped assertion is preferred for this skill's
  spawn-site wording; no existing test in this file references the Task/Agent spawns
  today [Agent 3 finding]
- Confirmed no test breakage risk: neither `test_skill_run_in_background_true_inventory_pinned`
  nor any existing `DOC_STRINGS_PRESENT` entry is disturbed by adding
  `run_in_background: false` text to the target files [Agent 3 finding]

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

**Pre-existing inconsistency to sweep while in these files — the answer is SEVEN, and
every existing site is wrong.** The runner count disagrees across the same set of docs:
`HOST_COMPATIBILITY.md:250` says "the other **six** runners"; `host_runner.py:251`,
`ARCHITECTURE.md:738`, `API.md:9514`, and `scripts/tests/test_host_runner.py:90` all say
"**five**".

Resolved 2026-08-15 by counting the registry rather than leaving it to the implementer.
`host_runner.py:1758-1765` maps **eight** concrete runners:

    claude-code -> ClaudeCodeRunner    gemini    -> GeminiRunner
    codex       -> CodexRunner         omp       -> OmpRunner
    opencode    -> OpenCodeRunner      kimi-code -> KimiRunner
    pi          -> PiRunner            qwen      -> QwenRunner

Excluding `claude-code`, the correct phrasing is "the other **seven** runners." Neither
"five" nor "six" is right, so all five sites change — this is not a matter of making the
outliers agree with the majority. Note `test_host_runner.py:90` is a docstring, so the
sweep is doc-only and breaks no assertion.

### Configuration
- N/A — no config file governs this; `LL_AUTOMATION` (env var) and
  `orchestration.disable_background_tasks` (`.ll/ll-config.json`) are the two related
  signals, both already wired

## Implementation Steps

0. **DONE** — the Key Decision is recorded above: route (b), with route (a)'s rejection
   reasons stated (chiefly that the flag would break the `ll-parallel`/`go-no-go`/
   `manage-issue` carve-outs per FEAT-3076's conclusion).
1. Every spawn site in the Summary's inventory table declares an explicit
   `run_in_background: false` — the six skills (`audit-docs`, `audit-claude-config`,
   `audit-issue-conflicts:205,:252`, `wire-issue`, `manage-issue:110`,
   `go-no-go:174,:278`), the companion file
   `audit-claude-config/wave1-prompts.md:9`, and the six commands (`refine-issue`,
   `tradeoff-review-issues`, `manage-release`, `scan-codebase`, `audit-architecture:68`,
   `analyze-workflows`) — following the wording at `decide-issue/SKILL.md:335`.
   Not `confidence-check`, which has no spawn site today; not
   `audit-issue-conflicts:218`, which is wait-prose rather than a spawn; not
   `audit-architecture:51`, exempted as flag documentation (see Tests § exempt list).
1b. The parallel fan-out sites take `false`, not `true`. `decide-issue/SKILL.md:335`
   establishes that a single-message multi-Agent spawn is already concurrent while
   blocking; backgrounding is not required for parallelism. If the implementer concludes
   otherwise for any site, that is a new carve-out requiring a recorded FEAT-3077-style
   rationale, not a silent allowlist append.

   **Key Decision 2 applies this same premise to `go-no-go:174`**, which is also a
   single-message fan-out. Its resolution (Option A) sets the allowlist's final contents:
   **empty**. That is the input step 5's two-sided test is written against.
1c. **The added wording fits the 500-line `SKILL.md` cap** — `python -m pytest
   scripts/tests/test_enh494_skill_companions.py -v` passes. `skills/manage-issue/SKILL.md`
   is at 499 of 500 lines and `skills/wire-issue/SKILL.md` at 493 with three sites, so the
   directive is folded into each existing spawn sentence as an inline clause rather than
   added as new lines (see the measured table under Tests). Copying
   `decide-issue/SKILL.md:335`'s two-line directive-plus-wait-sentence verbatim into
   `manage-issue` breaks the cap.
2. **`go-no-go/SKILL.md:174` flips `true → false`** per Key Decision 2 (Option A,
   recorded with Option B's rejection reason), the now-redundant Step 3c wait-prose at
   `:274` is folded into the `:174` sentence, and
   `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` is set to `set()` **in the same commit** —
   the allowlist test fails on the flip otherwise. Its sibling at `:278` is fixed under
   step 1. This file is not mirror-guarded, so no `ll-adapt` step applies to it.
3. Any wording reused from `skills/manage-issue/SKILL.md`'s "Headless-Safe Final Test
   Run" section preserves the exact strings pinned in `DOC_STRINGS_PRESENT`
   (`test_wiring_skills_and_commands.py` ~:202-203). When fixing `:110` in that same
   file, **append** the directive at the Phase 1.5 spawn and leave `:376-398` untouched —
   do not rewrap `:389`, whose line-split `run_in_background:\n true` would otherwise join
   and trip the `true`-inventory allowlist (see Dependent Files).
4. **Mirrors are regenerated — mandatory, not conditional.** Step 1 edits
   `skills/wire-issue/SKILL.md` **and `skills/manage-issue/SKILL.md`**, and *both* are in
   `SKILL_MIRRORS_MUST_MATCH_SOURCE` (`test_wiring_skills_and_commands.py:372-378`,
   three host mirrors each). Skipping regeneration is a hard
   `test_skill_mirror_matches_source` failure, not silent drift. Run:

   ```
   ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply
   ```

   `skills/audit-issue-conflicts/SKILL.md` also has mirrors on disk but is **not** in the
   guarded list, so its drift would go uncaught — regenerate it in the same pass anyway.
   `go-no-go`, `audit-docs`, and `audit-claude-config` are unguarded; the single
   `ll-adapt` invocation above covers whatever mirrors exist.
5. `test_skill_run_in_background_true_inventory_pinned` is extended to its two-sided form
   using the **five**-part detector specified under Tests, scanning `skills/**/*.md` **and**
   `commands/*.md` for **both** halves (candidate match is paragraph-scoped over the widened
   marker set and requires an imperative spawn verb; the `true`-value scan stays
   line-oriented; ±3-line satisfaction window; part 5's superset-of-inventory
   self-validation test lands with it; `SPAWN_DETECTOR_EXEMPT` seeded with the
   `confidence-check/SKILL.md:235` line plus the flag-documentation class listed there,
   including `audit-architecture.md:51`; `true`-set equality retained but now asserting
   `set()`) — this is the gate, not `DOC_STRINGS_PRESENT` needles.
   A test asserting the detector does **not** flag `confidence-check` is part of this
   step, since that false positive is already known. The allowlist constant is renamed off
   its `SKILL_` prefix, emptied (not deleted), and its assertion message updated, since
   the `true`-side is now asserted over `commands/` too (verified empty there today) —
   see Tests § Widening.
6. The seven incomplete `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`-scope descriptions are
   corrected to name Agent-tool spawns (or split to a linked docs issue), all five
   runner-count sites are corrected to "**seven**" (not reconciled to five or six — both
   are wrong; see Documentation), and
   `python -m pytest scripts/tests/test_wiring_skills_and_commands.py -v` passes.

## Impact

- **Priority**: P2 — silent loss of subagent findings in headless automation; wrong
  results rather than a crash, but no operator-visible signal when it happens.
- **Effort**: Medium-Large — eighteen spawn line-anchors across thirteen files (six
  skills, one skill companion, six commands), six mandatory mirror regenerations
  (`wire-issue` and `manage-issue` × three hosts), a two-sided inventory test
  with a specified detector over two corpora, seven doc corrections, and a five-site
  runner-count sweep. Revised up from Medium when the `commands/` half of the scope was
  found, and again when `manage-issue:110` was. (Route a, rejected, would have been
  Small.)
- **Risk**: Medium — the selected route (b) ships an advisory-only contract that nothing
  enforces at the tool layer; the inventory test closes the regression path but is a
  deliberately conservative detector, so a novel spawn phrasing can still slip through.
  Mirror drift in `audit-issue-conflicts` is currently uncaught. Editing
  `go-no-go/SKILL.md:174` and emptying `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` must land
  in one commit, or the allowlist test fails.
- **Breaking Change**: No. `go-no-go`'s judge agent (`:278`) becomes genuinely
  foreground, which is the behavior its own prose already promises. Its adversarial
  fan-out (`:174`) becomes blocking-but-still-concurrent; if concurrency measurably
  regresses there, that falsifies step 1b's premise and the five command fan-outs are
  mis-specified too (Key Decision 2, Option A).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-16 | Priority: P2

## Steps to Reproduce

1. Ensure `orchestration.disable_background_tasks` is `false` (the default since
   ENH-3207; it is set explicitly to `false` in this repo's `.ll/ll-config.json:134`).
2. Run any site from the inventory table under a headless turn — e.g. `ll-auto` or an FSM prompt
   state that invokes `/ll:audit-docs`, which spawns Task agents at
   `skills/audit-docs/SKILL.md:120-139` with no `run_in_background` value. The
   highest-frequency path is `/ll:refine-issue` (`commands/refine-issue.md:186`), which
   FSM prompt states invoke routinely.
3. Observe: the Agent tool defaults to background, so the parent turn can emit its
   stream-json `result` event while a subagent is still running. `subprocess_utils.py`
   waits `post_stream_close_grace_seconds` (300s) for the parent OS process only, then
   `_kill_process_group()` SIGKILLs the group — the subagent's findings are never read
   into the parent turn and no error is surfaced.

## Root Cause

- **Files**: `skills/audit-docs/SKILL.md`, `skills/audit-claude-config/SKILL.md`,
  `skills/audit-claude-config/wave1-prompts.md`,
  `skills/audit-issue-conflicts/SKILL.md`, `skills/wire-issue/SKILL.md`,
  `skills/manage-issue/SKILL.md`,
  `skills/go-no-go/SKILL.md`, `commands/refine-issue.md`,
  `commands/tradeoff-review-issues.md`, `commands/manage-release.md`,
  `commands/scan-codebase.md`, `commands/audit-architecture.md`,
  `commands/analyze-workflows.md`
- **Anchor**: Agent/Task spawn instructions at audit-docs:122-123 (within :120-139),
  audit-claude-config:118,222, wave1-prompts:9, audit-issue-conflicts:205,252,
  wire-issue:149 (within :147-190), manage-issue:110, go-no-go:174,278,
  refine-issue:186, tradeoff-review-issues:79,
  manage-release:134, scan-codebase:95,97,101, audit-architecture:68,
  analyze-workflows:102. (`go-no-go:174` declares `true` rather than omitting the
  directive — a different defect shape, fixed under the same rule per Key Decision 2.)
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
  `os.environ.get("LL_AUTOMATION")`), every Agent/Task spawn in the affected
  sites must declare `run_in_background: false` and be awaited synchronously in the
  same turn.
- Escape hatch: **none.** Key Decision 2 (Option A) removed the last carve-out —
  `go-no-go:174` flips to `false` and `SKILL_RUN_IN_BACKGROUND_TRUE_ALLOWLIST` becomes
  `set()`. Both `go-no-go` sites (`:174`, `:278`) are fix targets. A future `true`
  requires a deliberate allowlist append with a recorded FEAT-3077-style rationale.
- `confidence-check/SKILL.md` is not in scope — no Agent/Task spawn site exists today;
  confirm before treating it as one of the fix's targets.

## Error Messages

None — this failure is silent by construction. The nearest observable symptom is an
exit-143 (SIGKILL) automation run, which BUG-2731 already classifies as INFRA_RETRY, so
it is attributed to infrastructure rather than to a dropped subagent result.

## Environment

Claude Code host only — the other **seven** `HostRunner` implementations no-op
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` (`docs/reference/HOST_COMPATIBILITY.md:250`).
Count verified 2026-08-15 against the registry at `host_runner.py:1758-1765` (eight
runners total); the docs' existing "five"/"six" figures are both wrong and are corrected
under Documentation § Pre-existing inconsistency.
Headless `claude -p` turns: `ll-auto`, `ll-parallel`, `ll-sprint`, FSM prompt states.

## Frequency

Every headless invocation of the inventoried sites is exposed; whether the result is
actually lost depends on whether the subagent outlives the parent turn's `result` event.

## Session Log
- `/ll:manage-issue` - 2026-08-16T09:16:10 - `dea36e5a-c462-4b43-a17f-8f28449e32a6.jsonl`
- `/ll:confidence-check` - 2026-08-16T05:31:27 - `bb755dcf-6087-41b3-80d2-a79a3aba782e.jsonl`
- `/ll:confidence-check` - 2026-08-16T04:59:11 - `8af101e8-440c-4dfd-9d90-99c46a875466.jsonl`
- `/ll:decide-issue` - 2026-08-16T04:47:54 - `d03fba4d-011e-4873-ac13-79314b2ef1a9.jsonl`
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:20:15 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:51 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
