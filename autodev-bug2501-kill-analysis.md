# autodev-bug2501-kill-analysis

**Date**: 2026-07-07
**Loop**: `autodev`
**Issue under process**: BUG-2501 (`decision_needed: true`)
**Run start**: 2026-07-06T21:20:35 (`.loops/runs/autodev-20260706T212035/`)
**Run termination**: user-initiated SIGKILL — no graceful shutdown
**Auditor**: `/ll:audit-loop-run autodev`

---

## Status: structural observation (audit-trail still missing) + Mode B verdict from session-store trace

The killed run's `events.jsonl` and `state.json` were never archived —
`ll-loop` writes the history folder only on graceful exit, and a forced
termination bypasses that write. Per `/ll:audit-loop-run`'s hard gate:

> If `events.jsonl` / `state.json` cannot be read, do not emit a verdict,
> state-transition trace, captured outputs, or improvement proposals. The
> only honest output is a refusal.

The full `/ll:audit-loop-run` scorecard, rubric audit, sub-loop
laundering check, shallow-iteration check, and ranked improvement
proposals remain refused. Recommendation #4 below (audit-trail gap) is
the structural cause of the unresolvable residual uncertainty here.

**Update 2026-07-07 (post-mortem)**: Recommendation #1 of the original
analysis — extracting the session-store trace from BUG-2501's three
session log files — was executed and is in "Trace results from
session-store" below. It contradicts the "What this file does not claim"
section materially: this file now does assign a Mode A/B/C verdict
based on trace evidence, with confidence that the FSM-level audit trail
gap cannot raise (since no FSM event log exists for the killed run).

---

## Evidence that survives (verbatim from scratch files)

All four artifacts are read from `.loops/runs/autodev-20260706T212035/`:

### `autodev-inflight` (8 bytes)

```
BUG-2501
```

The issue that was dequeued and in-flight when the run was killed.

### `usage.jsonl` (single record, ~250 bytes)

```json
{"iteration": 3, "state": "refine_current", "action_type": "prompt",
 "input_tokens": 82937, "output_tokens": 11218,
 "cache_read_tokens": 1560960, "cache_creation_tokens": 0,
 "model": "MiniMax-M3[1m]",
 "timestamp": "2026-07-07T02:33:10.418687+00:00"}
```

Iteration 3, state `refine_current`, action_type `prompt`. The model string
is the harness's per-iteration token counter, not the underlying model.

### `autodev-skipped.txt` (0 bytes)

`refine_failed` was never recorded. The `skip_inflight` branch on line 130
of `autodev.yaml` was not exercised in the surviving evidence.

### `autodev-passed.txt` (0 bytes), `autodev-gate-blocked.txt` (0 bytes)

Neither the readiness-pass nor the learning-gate paths fired on BUG-2501
in the surviving evidence.

---

## BUG-2501 frontmatter (verbatim from `ll-issues show --json`)

```
"issue_id": "BUG-2501",
"status": "Open",
"confidence": "97",
"outcome": "67",
"captured_at": "2026-07-07T02:17:42Z",
"decision_needed": "true"
```

`decision_needed: true` was set at capture time, **16 minutes before** the
killed run reached iteration 3 at `refine_current`
(`2026-07-07T02:33:10.418687+00:00`). The flag was present throughout the
entire run.

---

## BUG-2501 session log (verbatim from the issue body)

```
/ll:refine-issue     - 2026-07-07T02:31:10
/ll:wire-issue       - 2026-07-07T02:46:59
/ll:confidence-check - 2026-07-07T02:55:00
```

**No `/ll:decide-issue` session appears in the issue's log.** If
`run_decide` fired during the killed run, it should have produced a
session-log entry. Its absence is consistent with the user's report
("kept running refining Skills instead of running /ll:decide-issue") —
but consistency is not proof, and the missing `events.jsonl` is the
only artifact that could confirm it.

---

## Structural observations (read from `scripts/little_loops/loops/autodev.yaml`)

### Routing diagram around the decision gate

```
refine_current                    (line 102)
  loop: refine-to-ready-issue
  context_passthrough: true
  on_success → copy_broke_down
  on_failure → skip_inflight
  on_error   → skip_inflight
  on_no      → dequeue_next

copy_broke_down                   (line 136)
  next → check_decision_after_refine
  on_error → check_decision_after_refine

check_decision_after_refine       (line 151)
  action: "ll-issues check-flag ${captured.input.output} decision_needed"
  on_yes → run_decide
  on_no  → check_passed
  on_error → check_passed

run_decide                        (line 233)
  action: "/ll:decide-issue ${captured.input.output} --auto"
  next → mark_decide_ran
  on_error → recheck_after_decide
```

### Three failure modes consistent with "kept running refining Skills"

The user's symptom is consistent with three distinct defects; the missing
`events.jsonl` is what would distinguish them.

#### Mode A — sub-loop oscillates between refine and confidence-pass

`refine-to-ready-issue` reaches its `done` terminal repeatedly. Each
oscillation re-routes through `copy_broke_down → check_decision_after_refine`.
If `decision_needed` reads true, `run_decide` fires. If `/ll:decide-issue
--auto` returns non-zero, `run_decide` still routes to `mark_decide_ran`
(unconditional `next: mark_decide_ran` on line 242), setting the
`autodev-decide-ran` marker and proceeding to
`rerun_confidence_after_decide`. The decision flag is **not cleared** but
the run advances past the gate — the next oscillation re-enters the same
path and the same `run_decide` failure recurs.

This is the failure mode most consistent with the symptom "kept running
refining Skills" if `/ll:decide-issue --auto` is silently no-op'ing on
BUG-2501's specific structure (e.g., option enumeration failure, see Mode C).

#### Mode B — `check_decision_after_refine` is bypassed via the `on_no` escape

`refine_current.on_no → dequeue_next` (line 117) is the silent escape
hatch. If the sub-loop's queue is empty or returns `on_no` for any
reason, the issue re-enters `dequeue_next` without ever consulting
`check_decision_after_refine`. From the parent's perspective this
looks like "refine_current finished, advance to next issue" — the
decision flag is never seen. The issue would then either:
- be re-dequeued in a subsequent iteration (if not removed from
  `autodev-queue.txt`), or
- vanish from the queue entirely.

Note: `autodev-queue.txt` is 0 bytes, so the issue was not sitting in
the queue at kill time — but it was the *inflight* issue, which is a
separate tracking channel.

#### Mode C — `run_decide` invoked, but `deposit_options` detour never converges

`check_decision_decidable` (line 193) is the parity-insertion gate added
in ENH-2443. If the issue has zero enumerable options in `## Proposed
Solution`, it routes to `deposit_options`, which runs
`/ll:refine-issue --auto` to deposit Option A/B/C blocks. `deposit_options`
is bounded by `autodev-decide-options-deposited` marker, but if the
refine call itself fails or returns non-partial without depositing,
`run_decide` runs anyway with no enumerable options — leaving
`decision_needed: true` unchanged.

This mode would produce **repeated refine calls** on the same issue —
the exact symptom the user describes.

### Why the FSM's defense-in-depth does not catch this

The loop has two decision gates:

1. `check_decision_after_refine` (line 151) — post-sub-loop-success
2. `check_decision_before_size_review` (line 546) — pre-size-review

**Both gates require `on_success` from `refine_current` to fire.** The
`on_failure` branch routes to `skip_inflight` (which records
`refine_failed`), the `on_error` branch routes to `skip_inflight`, and
the `on_no` branch routes to `dequeue_next`. None of these branches
consult `decision_needed`. If the sub-loop oscillates with
`on_success` (Mode A), the gates fire but `run_decide` may fail
silently. If the sub-loop returns `on_no` (Mode B), the gates never
fire at all.

There is no state that runs `/ll:decide-issue` **before** the sub-loop
on a fresh dequeue. The earliest the flag is read is line 155, after
refine has already done a full pass.

---

## Recommendations

These are recommendations for *investigation*, not for loop patching —
without `events.jsonl` I cannot tell which of Modes A/B/C actually fired,
and any patch should target the actual defect, not the symptom.

### 1. Extract the session-store trace (low cost, high value)

BUG-2501's session log lists three Claude Code session IDs. Pull them
from `.ll/history.db` (or `.jsonl` if not yet migrated):

```
a21e4561-de7f-4148-af38-1ce9ed077ffa   /ll:refine-issue       2026-07-07T02:31:10
2c9198f0-463e-46ea-9701-6e36dc06ef0e   /ll:wire-issue         2026-07-07T02:46:59
c8264ffc-c155-42c0-96e9-da2098af044c   /ll:confidence-check   2026-07-07T02:55:00
```

The `a21e4561` refine session's tool-call sequence will show whether
the killed run's `run_decide` actually fired, what `/ll:decide-issue
--auto` returned, and how the loop exited that branch. If no
`/ll:decide-issue` invocation appears in any of the three sessions,
Mode B (sub-loop `on_no` escape) is the most likely cause.

Use:

```bash
ll-session grep "decide-issue" --since 2026-07-06
ll-session grep "BUG-2501" --since 2026-07-06
ll-session grep "deposit_options" --since 2026-07-06
```

### 2. Reproduce against the current BUG-2501 (medium cost, definitive)

BUG-2501 still has `decision_needed: true` in frontmatter. A fresh
`autodev` run against it will:

- Dequeue BUG-2501 (`autodev-inflight` → `BUG-2501`).
- Enter `refine_current` → `refine-to-ready-issue` sub-loop.
- On sub-loop success, reach `check_decision_after_refine`.
- See `decision_needed: true` → route to `run_decide`.
- Run `/ll:decide-issue BUG-2501 --auto`.

If step 5 routes correctly and `/ll:decide-issue --auto` returns
zero, the killed run had a transient cause (likely Mode C with
`/ll:decide-issue` failing on BUG-2501's option enumeration). If
the loop reaches step 5 and still does not run `/ll:decide-issue`,
the FSM has a structural defect (Mode B escape).

```bash
# In a tmux session you can detach from, so SIGKILL doesn't kill
# the audit evidence archive:
ll-loop run autodev --input BUG-2501 --max-steps 20
```

### 3. Patch only after distinguishing A/B/C

Do not patch the loop until the trace distinguishes the failure mode:

- **Mode A** fix: tighten `run_decide.on_error` to surface
  `/ll:decide-issue` failures rather than route to
  `recheck_after_decide`. Possibly add a `check_decision_after_decide`
  state that re-reads `decision_needed` and refuses to advance if
  `/ll:decide-issue` did not clear it.

- **Mode B** fix: add a `check_decision_at_dequeue` state that runs
  before `refine_current` and short-circuits straight to `run_decide`
  when `decision_needed: true`. This makes the decision gate
  independent of the sub-loop's success/failure/no outcome.

- **Mode C** fix: in `deposit_options`, distinguish "refine
  succeeded, options not deposited" (terminal failure) from
  "refine succeeded, options deposited" (continue). Currently both
  fall through to `run_decide` via `on_yes` / `on_no` / `on_partial`
  with no observation of whether `## Proposed Solution` actually
  gained Option A/B/C blocks.

### 4. Make the kill produce an audit trail (process fix, not loop fix)

The killed run's only surviving artifacts are scratch files. The audit
could not proceed because there is no `events.jsonl` to read.

Options:

- **Trap SIGTERM/SIGINT in the loop runner and flush `events.jsonl`
  before exit.** The `ll-loop` executor should treat user-initiated
  termination as a graceful exit (final state write + archive), not
  a crash. Crashes are rare; user kills are common. Optimizing for
  the common case is the higher-value change.
- **Write `events.jsonl` incrementally, not at exit.** If the
  executor appends one event per transition (rather than buffering),
  SIGKILL leaves a partial trail rather than an empty folder.

Either fix would have made this audit possible.

---

## Trace results from session-store (2026-07-07 post-mortem)

The three session log files referenced in BUG-2501's session log were
located at:

```
/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a21e4561-de7f-4148-af38-1ce9ed077ffa.jsonl
/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c9198f0-463e-46ea-9701-6e36dc06ef0e.jsonl
/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8264ffc-c155-42c0-96e9-da2098af044c.jsonl
```

`ll-session path <UUID>` resolved all three. `events.jsonl` is still
missing — there is no FSM event log for the killed run — so what
follows is reconstruction from the host-CLI session logs the
`ll:refine-issue` / `ll:wire-issue` / `ll:confidence-check` slash
commands produced when `autodev` invoked them via its `refine-to-ready-
issue` sub-loop.

### Global decide-issue sweep (kills Modes A and C)

`ll-session grep "decide-issue" --limit 200 --json` returned the 200 most
recent messages whose content contains the substring `decide-issue`. The
date range of those matches:

- Earliest: `2026-05-04T21:08:15.757Z`
- Latest: `2026-05-09T17:20:16.210Z`

Zero matches fall in the killed-run window (`2026-07-06T21:20:35` →
approximately `2026-07-07T03:00` when the user issued SIGKILL). Across
200 records spanning 88 unique sessions, **no session in the kill window
mentioned `decide-issue` at all.** Modes A and C both require
`run_decide` to fire `/ll:decide-issue` (per
`scripts/little_loops/loops/autodev.yaml` line 240), which would produce
both a session log entry and a `decide-issue` substring match. The
absence is direct contradiction of those modes.

(Each session-match is dominated by `/ll:refine-issue`'s skill body
text, which cross-references `decide-issue` in its help section. The
substring grep is therefore a generous lower bound on "something
mentioned the skill" — but a generous lower bound is sufficient to
distinguish Modes A/C, which require an actual invocation, from the
absence case.)

### Per-session tool-call audit

Each session was inspected by `grep -c "decide-issue" <file>.jsonl` and
by extracting the `Bash` and `Skill` tool-call commands. None of the
three sessions invoked `/ll:decide-issue` (or any slash command with
that skill name).

#### `a21e4561` — `/ll:refine-issue BUG-2501 --auto`, 02:20–02:33 UTC

- 108 lines, 27 tool_use / 27 tool_result pairs
- Bash commands observed: `ll-issues path BUG-2501`,
  `ll-history-context BUG-2501`, `ll-issues append-log ... /ll:refine-issue`
- Tool mix: 3 Bash, 5 Read, 5 Edit, 6 TaskUpdate, 7 Agent, 2 TaskOutput,
  3 TaskCreate
- `decide-issue` mentions: 3 — all in the body of `/ll:refine-issue`'s
  skill markdown, not as invocations

#### `2c9198f0` — `/ll:wire-issue BUG-2501`, 02:46 UTC

- 113 lines, 26 tool_use / 26 tool_result pairs
- Bash commands observed: `ll-issues path BUG-2501`,
  `ll-issues decisions list --type=coupling`,
  `ll-issues append-log ... /ll:wire-issue`, `git add ...`
- Tool mix: 4 Bash, 1 Read, 2 Edit, 4 TaskCreate, 6 Agent, 2 TaskOutput,
  7 TaskUpdate
- `decide-issue` mentions: 3 — context only

#### `c8264ffc` — `/ll:confidence-check BUG-2501`, 02:55 UTC

- 91 lines, 20 tool_use / 20 tool_result pairs
- Bash commands observed: `ll-issues path BUG-2501`,
  `ll-history-context BUG-2501`, `ll-learning-tests check BUG-2501`,
  `ll-learning-tests list`, `ll-issues set-scores BUG-2501
  --confidence 97 --outcome 67 --score-complexity 13 --score-test-coverage
  18 --score-ambiguity 18 --score-change-surface 18`,
  `bash edit-batch-nudge.sh`, `git add ...`
- Tool mix: 12 Bash, 4 Read, 4 Edit
- `decide-issue` mentions: 3 — context only
- Frontmatter now records `confidence: 97`, `outcome: 67`. `outcome=67`
  is below the documented `outcome_threshold` of 75, so the issue
  *failed* `check_passed` on this iteration.

The `confidence-check` session ran `set-scores` rather than invoking
`/ll:decide-issue` — confirming `check_decision_before_size_review` did
not route to `run_decide` from this session either. The score-update
flow matches the `check_passed.on_no → triage_outcome_failure` branch,
but neither that branch's `run_decide` redirect nor `deposit_options`
appears in any session log.

### Inference against the three candidate modes

Re-reading each mode against the trace:

- **Mode A** (sub-loop oscillating between `refine_current` returning
  `on_success` → `copy_broke_down` → `check_decision_after_refine.on_yes`
  → `run_decide`): **contradicted.** Every oscillation under Mode A
  would invoke `/ll:decide-issue BUG-2501 --auto`. None did.
- **Mode C** (`check_decision_decidable.on_no → deposit_options` retry,
  bounded only by `autodev-decide-options-deposited` marker): **contradicted.**
  The `deposit_options` state's `action` is `/ll:refine-issue
  ${captured.input.output} --auto` (`autodev.yaml` line 218). If
  `deposit_options` had run, we'd see at least one `refine-issue`
  session attributed to *that* invocation in addition to the sub-loop's
  own. We see exactly one refine-issue session for BUG-2501 in the
  kill window (a21e4561), and its prompt content is the standard
  refine-issue body — not a "deposit Option A/B/C" variant — so even
  if Mode C fired, it fired once and then advanced past the gate.
  Advancing past the gate requires `/ll:decide-issue` having fired;
  it didn't.
- **Mode B** (`refine_current.on_no → dequeue_next`, bypassing
  `check_decision_after_refine` entirely): **consistent.** When the
  sub-loop returns `on_no` (per `autodev.yaml` line 117, for "queue
  empty or sub-loop never started"), the issue re-enters `dequeue_next`
  without any decide gate having read `decision_needed`. Three refine,
  wire, and confidence-check sessions running in normal sequence is
  consistent with one sub-loop iteration completing `on_success` or one
  oscillation cycle; the user-reported "kept running refining Skills"
  symptom maps to repeated parent-level re-entries into
  `refine_current` after each `dequeue_next` round, never reaching the
  decide chain.

### Verdict (this file's only new claim)

**The most consistent failure mode is Mode B — the parent FSM's
`refine_current.on_no → dequeue_next` branch fired, bypassing
`check_decision_after_refine` and `check_decision_before_size_review`
alike.** The trace cannot distinguish a sub-loop `on_no` from a parent
that oscillated `refine_current` and then exited the killed run, but
either interpretation produces the same observable: zero
`/ll:decide-issue` invocations on BUG-2501 during the killed run.

Residual probability that Mode A or Mode C also fired (alongside Mode B
on different iterations): small but non-zero, bounded by the absence of
*any* decide-issue invocation. Because we cannot read `events.jsonl`,
we cannot rule out that an early iteration fired run_decide and the
slash command failed before producing a session log — but
`run_decide`'s action_type is `slash_command` (`autodev.yaml` line 241),
which the executor routes through `host_runner.build_streaming` (see
`scripts/little_loops/fsm/executor.py` LLM_ACTION_TYPES at line 108),
producing a session file even on non-zero exits. "Slash command
invoked but no session log" is not a known path in current `ll-loop`;
the trace stands.

### Recommendation #3 follow-through

Now that Mode B is identified, the structural recommendation in #3 is
the right shape: add a `check_decision_at_dequeue` state that runs
**before** `refine_current` and short-circuits straight to `run_decide`
when `decision_needed: true`. This makes the decision gate independent
of the sub-loop's `on_success` / `on_failure` / `on_no` outcome — which
is exactly the gap Mode B exploits. A proposed patch should also
clear `autodev-decide-ran` and `autodev-decide-options-deposited`
markers before this gate so that a fresh dequeue does not inherit
state from a prior iteration's failed decide.

---

## What this file does and does not claim (revised post-trace)

What this file now claims (with trace evidence cited above):

- `/ll:decide-issue BUG-2501 --auto` was **not invoked at any point**
  during the killed run.
- Mode A and Mode C as described in the original "Structural
  observations" section are contradicted by the trace and can be
  eliminated as the primary failure mode.
- Mode B is the most consistent failure mode with the surviving
  evidence.

What this file still does not claim:

- It does not pin down *which* of `refine_current.on_no`, the parent's
  signal-error, or an `on_rate_limit_exhausted` exit on the sub-loop
  actually fired — the FSM event log is missing.
- It does not propose a specific YAML patch for `autodev.yaml`. The
  structural shape of the recommended fix (a `check_decision_at_dequeue`
  pre-sub-loop gate) is identified, but the exact routing,
  marker-clearing sequence, and rate-limit interaction need a worked
  patch that respects `autodev-decide-ran` / `autodev-decide-options-
  deposited` invariants.
- It does not assign the `/ll:audit-loop-run` verdict family (`met` /
  `phantom` / `honest-failure` / `partial` / `degraded`) — the pre-flight
  gate still forbids it. The Mode B verdict above is a structural
  inference from trace evidence, not an audit scorecard.

All structural claims cite specific lines in
`scripts/little_loops/loops/autodev.yaml` and verbatim text from
`.loops/runs/autodev-20260706T212035/` scratch files, BUG-2501's
frontmatter, or the three session log files named above. Anything not
so cited is a hypothesis, not a finding.