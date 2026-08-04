---
id: ENH-3031
title: "refine-to-ready-issue has no claim-verification gate \u2014 every corrective\
  \ path is gated behind an LLM self-grade"
type: ENH
status: open
priority: P2
discovered_date: 2026-08-03
discovered_by: run-review
testable: true
labels:
- loops
- refine-to-ready-issue
- issue-quality
- verification
- self-assessment
confidence_score: 100
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
---

# ENH-3031: refine-to-ready-issue has no claim-verification gate — every corrective path is gated behind an LLM self-grade

## Summary

`refine-to-ready-issue.yaml` routes to `refine_followup`, `breakdown_issue`, and
every other corrective state **only when a confidence score falls below
threshold**. The scores are authored by the same model that wrote the issue
content, in the same run. When the model self-grades high on the first pass, the
loop takes the shortest path to `done` and no state ever re-examines what it
wrote.

The loop is named refine-to-**ready**-issue but never invokes `/ll:ready-issue`
or `/ll:verify-issues` — the two skills whose stated job is validating accuracy
and completeness, and which `commands/refine-issue.md:961` itself names as the
"After" step. It stops one state short of its own name.

## Current Behavior

Run on BUG-3025 (`refine-to-ready-issue-20260803T162851`, 12 iterations,
11m 55s, model sonnet). Each LLM state was invoked exactly once:

```
resolve_issue → check_epic_id → check_lifetime_limit → refine_issue
  → check_decision_mid_refine → check_wire_done → wire_issue → mark_wire_done
  → check_decision_mid_wire → confidence_check → check_readiness (100 ≥ 85)
  → check_outcome (92 ≥ 65) → done
```

`refine_followup` (additive `--gap-analysis`), `breakdown_issue`, and
`check_scores_from_file` were never reached. `confidence_score: 100` /
`outcome_confidence: 92` were written by `/ll:confidence-check` and immediately
consumed by `check_readiness` / `check_outcome` as the sole quality gate.

A human review of the resulting issue found three defects the loop could not
have caught. Each maps to a distinct structural hole:

| Defect in BUG-3025 | Why the loop missed it |
|---|---|
| Mis-diagnosed `test_ll_loop_execution.py:352` as "the identical vacuous-negative pattern" — in fact `ll-loop` has no `print_logo` call path at all (removed in `88db2cd0`), so it is a different defect and the proposed fix would not apply | The finding is a grep hit on `"little loops"` — genuine `codebase-locator` output. Refuting it required asking "does anything call `print_logo`?", and **absence-of-caller is not a search result**. `commands/refine-issue.md:296` assigns "Affected code paths — what other code calls/depends on" to the *locator*, so negative call-path facts fall between the two agents. No later state re-derives the claim. |
| An acceptance criterion that reads "verify by temporarily removing the `isatty()` guard" — a one-time manual step, i.e. exactly the decay mode the issue exists to fix | `/ll:confidence-check` scores complexity / test_coverage / ambiguity / change_surface. A manual AC scores *well* on all four: specific, unambiguous, small, testable-by-a-human. There is no "machine-checkable / survives this session" axis, so the defect is invisible to the only evaluator in the chain. |
| An unresolved hedge left in the body: "Worth confirming whether the marker guard belongs here rather than in the integration file" | `--gap-analysis` is additive by design ("never removes content"), so hedges accumulate and are never closed. The state that would resolve one (`refine_followup`) is score-gated and was skipped. See Prior Art for why the existing open-question probe also missed it. |

### The generalization

`check_readiness` / `check_outcome` are non-LLM evaluators, which satisfies MR-2
on paper — but they consume an **LLM-authored number about a document the same
model just wrote**. That is measurement, not verification. A high self-grade
buys an early exit, so the loop currently rewards grade inflation with the
shortest path to `done`.

Separately: no document-scoring rubric can catch the first defect at all,
because that defect is an **omission**. Detecting it required running a `grep`
the issue never mentions. Verification has to touch the codebase, not the prose.

## Expected Behavior

Every `refine-to-ready-issue` run passes through at least one state that tests
the issue's claims against the codebase, and at least one non-LLM gate that can
force another refine pass **independently of the confidence scores**. A perfect
first-pass self-grade is not sufficient to reach `done`.

Concretely, on a re-run against BUG-3025's pre-review revision:

- the `ll-loop` call-path claim is challenged by a verification state rather
  than carried forward unexamined;
- `ll-issues check-open-questions` exits 1 on the two hedge lines, routing to
  `refine_followup`;
- the manual acceptance criterion is flagged before the run terminates.

## Prior Art (existing primitives — checked before proposing)

- **`ll-issues check-open-questions`** (ENH-2446,
  `scripts/little_loops/cli/issues/check_open_questions.py`) already implements
  most of proposed change 2: a non-LLM probe that exits 1 with an
  `OPEN_QUESTIONS_REMAIN` token when unresolved options or open questions
  remain. Already wired into `autodev.yaml:543` and `rn-remediate.yaml:300` —
  but **not** into `refine-to-ready-issue.yaml`.

  It returns **exit 0** on BUG-3025 (`"BUG-3025 has no unresolved decision
  surface"`) for two verified reasons, both narrow and fixable:
  1. `_OPEN_QUESTION_SECTIONS` (`issue_parser.py:1179`) is
     `("Edge Cases", "Confidence Check Notes", "Open Questions")`. BUG-3025's
     hedges live in `## Integration Map` → `### Tests` and
     `### Codebase Research Findings`, which are not scanned.
  2. `_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:1165`) has no hedge
     vocabulary — it matches `?$`, `Q:`, `open question`, `needs decision`,
     `decision point`, etc. Confirmed empirically that both BUG-3025 hedge
     lines score `False` against it.

  So this is a **widening of an existing probe**, not a new mechanism.
- **`ll-issues check-readiness`** exists and already gates on both thresholds —
  it is the CLI equivalent of the loop's inline `check_readiness` /
  `check_outcome` heredocs, and is orthogonal to this ENH (it consumes the same
  self-authored scores).
- `/ll:verify-issues` and `/ll:verify-issue-loop --mode adversarial` already
  exist as the claim-testing skills; nothing new needs authoring for change 1.

  **`/ll:verify-issues --check` (`commands/verify-issues.md:263`) is the
  FSM-evaluator mode**: check-only (applies nothing), prints
  `[ID] verify: [verdict]` per non-VALID issue, **exits 1 if any issue is
  non-VALID**, exit 0 if all valid; implies `--auto`. This is an exit-code
  contract the loop can gate on, not just an advisory pass — see change 1.

  **Precondition (must be fixed for change 1 to work as specified):**
  `commands/verify-issues.md` parses `ISSUE_ID` at `:34` and **never
  references it again** — confirmed, single occurrence in the file. Step 1
  ("Find Issues to Verify", `:47-51`) unconditionally lists *every* active
  issue. The Arguments section (`:257-259`) promises "If provided, verifies
  only that specific issue", but no executable step implements that filter.
  Since `allowed-tools` includes `Edit`, invoking the command per-run from a
  per-issue loop risks a whole-backlog verification pass that mutates
  unrelated issues.

## Proposed Solution

Four changes, in priority order. The first three are the substance; the fourth
is a smaller follow-on.

### 1. Insert a claim-verification state before `confidence_check`

Add a `verify_issue` state between `mark_wire_done` / `check_decision_mid_wire`
and `confidence_check`, invoking `/ll:verify-issues` on the run's issue (or
`verify-issue-loop --mode adversarial` as a sub-loop, matching the
`confidence_check` oracle pattern). Non-fatal on error, like `wire_issue`.

This is the state that would have asked "does anything actually call
`print_logo`?" — it tests claims against code rather than grading prose. It is
the only one of the four changes that can catch an omission.

**Two required corrections to the naive form of this state** (see Prior Art):

1. **Never invoke bare `/ll:verify-issues ${captured.issue_id.output}`.** The
   command ignores its `issue_id` argument (parsed at `:34`, never used), so
   that form verifies — and with `Edit` in `allowed-tools`, potentially
   rewrites — the entire active backlog on every loop run. Either fix
   `commands/verify-issues.md` to honor `ISSUE_ID` in its Step 1 issue-listing
   block *as part of this change*, or accept whole-backlog scope explicitly.
   Also pass `--auto` rather than relying on the implicit `LL_NON_INTERACTIVE`
   auto-enable at `:39-41`.
2. **Hard-gate via a written verdict artifact, not `fragment: shell_exit` on
   the slash command itself.** `shell_exit` forces `action_type: shell`
   (`lib/common.yaml:15-21`); `verify_issue` runs through the host CLI as
   `action_type: slash_command`, and the *host process's* exit code reflects
   whether the session completed, not `/ll:verify-issues --check`'s internal
   verdict — the `[ID] verify: [verdict]` output and the doc's own
   `exit 1`/`exit 0` contract (`verify-issues.md:148`) live inside the
   skill's own Bash/prose and do not propagate to the host CLI's process exit
   code. No shipped loop gates on a slash command's logical exit code today;
   the codebase convention for "LLM state → deterministic gate" is a verdict
   written to frontmatter or a marker file, followed by a separate shell
   probe — the `decision_needed` / `check-flag` pattern already used four
   times in this loop.

   **Respecified (resolves Q1 as (b), hard gate):** `verify_issue`
   (`action_type: slash_command`, `--check`) is extended so its `--check`
   mode also writes its verdict to the run's issue frontmatter (e.g.
   `verify_verdict: VALID|NON_VALID`, mirroring how `confidence_check`
   persists `confidence_score`/`outcome_confidence`) instead of only
   printing to stdout and setting a process exit code that never leaves the
   host session. A new `check_verify_verdict` state
   (`fragment: shell_exit`) then runs a new `ll-issues check-verify-verdict
   <ID>` CLI — mirroring `check_open_questions.py`'s shape — that reads the
   frontmatter field and exits 1 on `NON_VALID`, routing
   `on_no → check_refine_limit`. This keeps MR-2 honest: the gate is a
   deterministic shell probe over a persisted artifact, not a gate on an
   LLM process's incidental exit status.

### 2. Widen `check-open-questions` and wire it in as a hard gate

Two-part change:

- **CLI**: extend `_OPEN_QUESTION_SECTIONS` to include the sections refine and
  wire actually deposit prose into (`Integration Map`, `Codebase Research
  Findings`, `Suggested Fix Direction`, `Program Design`), and add hedge
  vocabulary to `_OPEN_QUESTION_SIGNAL_RE` (`worth confirming`, `worth
  checking`, `should be considered`, `TBD`, `to be determined`, `needs
  confirmation`, **`worth a decision`, `worth deciding`**). Keep the existing
  `RESOLVED`-marker exclusion so a deliberately-answered hedge can be marked
  closed.

  The last two entries are not hypothetical: **this issue's own change 4 defers
  its choice with "worth a decision during implementation rather than
  pre-committing here", and `ll-issues check-open-questions ENH-3031` exits 0
  today *and* would still exit 0 under the widening as first drafted** —
  `worth a decision` was absent from the vocabulary, and change 4's two options
  are prose alternatives rather than an enumerated option block, so
  `locate_unresolved_options()` does not see them either. An issue about
  unresolved hedges surviving the gate shipped with one that survives the gate.
  See Open Questions.
- **Loop**: add a `check_hedges` state after `verify_issue` that runs
  `ll-issues check-open-questions`; on exit 1, route to `check_refine_limit`
  (→ `refine_followup`) **regardless of confidence score**.

This is the measurable external signal the loop is missing — deterministic,
no LLM budget, and it would have caught the third defect on this run.

### 3. Gate acceptance criteria on automatability

Add a non-LLM probe (new `ll-issues check-acceptance-criteria`, or a flag on the
existing `format-check`) that scans `## Acceptance Criteria` items for
manual-verification verbs — `temporarily`, `manually`, `by hand`, `verify by`,
`visually confirm` — and exits 1 with a token naming the offending criteria.
Wire it alongside change 2 with the same score-independent routing.

**Two scoping constraints, measured (see Codebase Research Findings):**

- **Scan only checkbox items (`- [ ]` / `- [x]`), not every line under the
  heading.** The measured hits include prose lines such as "Can be run manually
  on any issue even without the `decision_needed` flag" (FEAT-1236, FEAT-1238)
  — descriptive notes under the heading, not criteria.
- **Drop the bare `looks` token** from the `check that ... looks` pattern; it
  fires on unrelated prose. Keep the full phrase or omit the rule.

This encodes "acceptance criteria must be re-runnable" where the confidence
rubric structurally cannot reach it.

### 4. Treat an unchallenged first-pass perfect score as suspicious

`confidence_score: 100` on a first pass with zero refine iterations means
nothing was ever contested, not that the issue is perfect. Two options:

- **4a — mandatory contest**: require at least one `refine_followup` before
  `check_readiness` can terminate. Note this **adds a guaranteed LLM pass to
  every run**, contradicting the Notes claim that changes 1-3 add no budget
  beyond one `verify_issue` invocation; that line must be updated if 4a wins.
- **4b — score damping**: damp a first-pass score above some ceiling (e.g. 95)
  unless a verification state has run. No added budget; weaker signal.

**Resolved (Q2): 4b, or drop change 4 entirely.** 4a contradicts this issue's
own "no added budget" claim in Notes. More importantly, once changes 1-3 ship,
an unchallenged 100 can no longer buy the shortest path to `done` anyway —
`verify_issue`/`check_hedges`/`check_ac_automatable` sit between every run and
`confidence_check` regardless of score, so the score itself stops being the
gate that change 4 was designed to distrust. That leaves 4b as a weak,
optional signal on top of gates that already do the real work; implement it
only if it's cheap, otherwise drop change 4 and note the reason in Notes.

## Scope Boundaries

**In scope**: `refine-to-ready-issue.yaml` routing; the
`check-open-questions` section/signal widening; a new acceptance-criteria
automatability probe; the `refine-issue.md` agent-assignment note for negative
call-path facts; **`commands/verify-issues.md`'s unimplemented `ISSUE_ID`
filter, fixed inside this issue (Q3 resolved — not split out)**: change 1 is
not safely implementable while `/ll:verify-issues <ID>` silently means "all
issues", and the fix is a one-edit change to Step 1's issue-listing block
(`:47-51`), not large enough to justify a separate `blocked_by` edge; also in
scope, `commands/verify-issues.md`'s `--check` mode gains a verdict-write
step (frontmatter `verify_verdict` field, see Program Design change 1) and a
new `ll-issues check-verify-verdict` CLI.

**Out of scope**:

- Changing `/ll:confidence-check`'s rubric or its four score dimensions. The
  scores are not wrong — they measure scope and clarity, which is what they
  claim to measure. This ENH adds evaluators beside them, it does not retune
  them.
- The `verify-confidence-scores` oracle's persistence check. It verifies scores
  were *written*, which is a real and separate guarantee.
- `autodev.yaml` / `rn-remediate.yaml` routing changes. They are affected only
  as consumers of the widened probe (see Dependent Files); their own state
  graphs stay as-is.
- Retroactively re-refining issues already marked ready by this loop.

## Program Design

### New loop states (`refine-to-ready-issue.yaml`)

```yaml
verify_issue:
  action: "/ll:verify-issues ${captured.issue_id.output} --check"
  action_type: slash_command
  pruning_profile: {enabled: true, name: verify-issues-auto, suppress_claude_md: true}
  next: check_verify_verdict
  on_error: check_verify_verdict  # verification failure is non-fatal, like wire_issue

check_verify_verdict:
  action: "ll-issues check-verify-verdict ${captured.issue_id.output}"
  fragment: shell_exit
  on_yes: check_hedges           # exit 0 = verdict VALID
  on_no: check_refine_limit      # exit 1 = VERIFY_VERDICT_NON_VALID → force refine
  on_error: check_hedges

check_hedges:
  action: "ll-issues check-open-questions ${captured.issue_id.output}"
  fragment: shell_exit
  on_yes: check_ac_automatable  # exit 0 = no hedges
  on_no: check_refine_limit     # exit 1 = OPEN_QUESTIONS_REMAIN → force refine
  on_error: check_ac_automatable

check_ac_automatable:
  action: "ll-issues check-acceptance-criteria ${captured.issue_id.output}"
  fragment: shell_exit
  on_yes: confidence_check
  on_no: check_refine_limit
  on_error: confidence_check
```

`/ll:verify-issues`'s `--check` mode must additionally be extended to persist
`verify_verdict: VALID|NON_VALID` to the target issue's frontmatter as part of
this change (today it only prints `[ID] verify: [verdict]` and sets a process
exit code — see change 1 correction 2 above); `check_verify_verdict` reads
that field rather than any process exit code.

Entry: five mid-chain routes retarget from `confidence_check` to
`verify_issue` — every path that currently skips straight to
`confidence_check` must instead re-enter the verification chain:
`check_wire_done.on_no` (`:174`), `check_wire_done.on_error` (`:175`),
`wire_issue.on_error` (`:185`), `mark_wire_done.on_error` (`:191`), and
`check_decision_mid_wire.on_no` / `.on_error` (`:202-203`). This closes the
loopback bypass: the gate-driven corrective pass
(`check_refine_limit → refine_followup → check_decision_mid_refine →
check_wire_done`) re-enters at `check_wire_done`, whose `on_no` previously
routed straight to `confidence_check` on the second pass (wire-done marker
already `1`), skipping `verify_issue`, `check_hedges`, and
`check_ac_automatable` entirely — the exact bypass this issue's own AC #1
("on every run") requires closing. All five routes point at the same
`verify_issue` entry state, so `check_verify_verdict` → `check_hedges` →
`check_ac_automatable` → `confidence_check` is now the only path forward,
regardless of which mid-chain state fires. `check_refine_limit`'s existing
cap prevents spinning; `max_steps: 30` still holds.

`max_steps` must rise from 20 to **30**: the happy path already used 12
iterations, the four new states (`verify_issue`, `check_verify_verdict`,
`check_hedges`, `check_ac_automatable`) add 4, and a gate-driven
`refine_followup` cycle costs roughly 6 more (`check_refine_limit →
refine_followup → wire → the three gates`) — ~22 worst case, leaving headroom
without slackening the phantom-convergence guard.

**Ordering assumption (validated by the Entry retarget above):** because all
five mid-chain routes now point at `verify_issue`, a gate-driven
`refine_followup` cycle always re-enters through `verify_issue` → the two
probes, not at `confidence_check` — so prose deposited by `refine_followup`
is re-scanned by `check_hedges`/`check_ac_automatable` on every pass, not
only the first.

### Signatures

```python
# scripts/little_loops/issue_parser.py — widened, same signature
_OPEN_QUESTION_SECTIONS: tuple[str, ...]   # +Integration Map, Codebase Research
                                           #  Findings, Suggested Fix Direction,
                                           #  Program Design
_OPEN_QUESTION_SIGNAL_RE: re.Pattern[str]  # +hedge vocabulary; compiled
                                           #  re.IGNORECASE, each new phrase
                                           #  wrapped in \b...\b word
                                           #  boundaries (e.g. r"\bworth
                                           #  confirming\b"), matching the
                                           #  existing signal set's style
def count_open_questions_in_sections(content: str) -> int: ...   # unchanged

# scripts/little_loops/cli/issues/check_acceptance_criteria.py — new (change 3)
def add_check_acceptance_criteria_parser(subs) -> argparse.ArgumentParser: ...
def cmd_check_acceptance_criteria(config: BRConfig, args) -> int: ...
    # 0 = all criteria machine-checkable; 1 + MANUAL_CRITERIA_REMAIN token otherwise

# scripts/little_loops/cli/issues/check_verify_verdict.py — new (change 1, respecified)
def add_check_verify_verdict_parser(subs) -> argparse.ArgumentParser: ...
def cmd_check_verify_verdict(config: BRConfig, args) -> int: ...
    # 0 = verify_verdict == VALID; 1 + VERIFY_VERDICT_NON_VALID token otherwise;
    # mirrors check_open_questions.py's _resolve_issue_id / exit-code-plus-
    # stderr-token contract
```

Mirror `check_open_questions.py` exactly — same parser shape, same
`_resolve_issue_id` lookup, same exit-code-plus-stderr-token contract — so
`fragment: shell_exit` consumes it identically.

### Call Path

Gate invocation (both new gates share this chain):

`executor` runs `check_hedges` (`action_type: shell` via `fragment: shell_exit`)
-> `ll-issues check-open-questions <ID>`
-> `cli/issues/__init__.py:995` dispatch
-> `check_open_questions.cmd_check_open_questions()`
   (`check_open_questions.py:39`)
-> `show._resolve_issue_id()` → issue path
-> `issue_parser.locate_unresolved_options()` (`issue_parser.py:1049` region)
   **+ `issue_parser.count_open_questions_in_sections()`
   (`issue_parser.py:1204`)** ← the widened path
-> `_section_body()` per heading in `_OPEN_QUESTION_SECTIONS`
   (`issue_parser.py:1179`) ← **widened**
-> `_count_unresolved_items_in_text()` (`issue_parser.py:1182`)
-> `_OPEN_QUESTION_SIGNAL_RE.search()` (`issue_parser.py:1165`) ← **widened**
-> exit 0/1 → `fragment: shell_exit` verdict → `on_yes` / `on_no` routing.

The verification state's chain is the existing slash-command path, unchanged:
`executor._execute_slash_command()` -> `host_runner.resolve_host()` ->
`/ll:verify-issues`.

`check-acceptance-criteria` (change 3) reuses the identical chain with a new
`cmd_check_acceptance_criteria()` leaf and an AC-section scan in place of the
open-question scan.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- Anchor correction: `locate_unresolved_options()` is defined at `issue_parser.py:1091`, not the "1049 region" cited in the Call Path — line 1049 falls inside `count_enumerable_options()`'s docstring/helper region (`_iter_option_blocks`/`_is_option_resolved`), a different function. All other Call Path/Signatures line citations (`_OPEN_QUESTION_SECTIONS:1179`, `_OPEN_QUESTION_SIGNAL_RE:1165`, `count_open_questions_in_sections():1204`, `_count_unresolved_items_in_text():1182`) were confirmed exact against current `issue_parser.py`.
- Confirmed live and accurate: `check_decision_mid_wire`'s current `on_no`/`on_error` both route to `confidence_check` (`refine-to-ready-issue.yaml:193-203`) — the exact retarget point change 1's Entry note describes. `check_refine_limit` (`:319-339`) caps loopbacks at target `2` (1 initial + 1 retry) via `output_numeric lt 2`, matching the "cannot spin" claim.
- Confirmed `fragment: shell_exit` (from `lib/common.yaml`, already imported at `refine-to-ready-issue.yaml:22`) maps exit 0 → `on_yes`, exit 1 → `on_no`, other codes → `on_error` (`fsm/evaluators.py:220-238`, `evaluate_exit_code()`). The Program Design's proposed `check_hedges`/`check_ac_automatable` snippets are schema-valid against this mapping, and `verify_issue`'s use of `action_type: slash_command` (not `fragment: shell_exit`) is consistent with the existing `wire_issue`/`refine_issue` states in this same file.
- Confirmed `pruning_profile.name` is purely informational (no registry/allowlist consumes it — `schema.py:440-474` docstring, confirmed via grep) — `name: verify-issues-auto` needs no pre-registration; it follows the same ad hoc `<command>-<suffix>` convention as the file's existing `refine-issue-repair`, `wire-issue-auto` names. No `verify-issues-auto` name exists anywhere in the codebase yet, so this would be a new, not a reused, profile name.
- `cli/issues/check_open_questions.py` exit-code/token contract confirmed exact: 0 = pass, 1 = `OPEN_QUESTIONS_REMAIN:` token to stderr + suggested `/ll:refine-issue --auto` remediation, via `cmd_check_open_questions()` at line 40. Two coexisting subparser registration conventions were found in `cli/issues/__init__.py`: a standalone `add_check_open_questions_parser(subs)` helper (what `check_open_questions.py` itself uses, and what the issue's Signatures section proposes mirroring for `check-acceptance-criteria`), versus subcommands like `check-decidable`/`check-readiness`/`check-flag`/`check-design` that build their subparser inline in `main_issues()` (`__init__.py:694-708`) with no standalone helper. The issue's plan to mirror `check_open_questions.py`'s shape (standalone helper) is the correct choice of the two existing conventions, not an arbitrary one.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new `verify_issue`,
  `check_verify_verdict`, `check_hedges`, `check_ac_automatable` states;
  rerouting all five mid-chain `confidence_check` references (see Program
  Design Entry note); `max_steps` raise (currently 20; the happy path already
  consumed 12).
- `commands/verify-issues.md` — fix the unimplemented `ISSUE_ID` filter in
  Step 1 (`:47-51`) so `/ll:verify-issues <ID>` verifies only that issue
  (Q3, resolved in scope); extend `--check` mode (`:148`) to persist
  `verify_verdict: VALID|NON_VALID` to the target issue's frontmatter instead
  of only printing and exiting.
- `scripts/little_loops/cli/issues/` — new `check_verify_verdict.py`
  subcommand (change 1, respecified), registered in `cli/issues/__init__.py`
  alongside the change-3 subcommand below.
- `scripts/little_loops/issue_parser.py` — `_OPEN_QUESTION_SECTIONS:1179`,
  `_OPEN_QUESTION_SIGNAL_RE:1165` (widened, case-insensitive, `\b`-bounded
  hedge phrases).
- `scripts/little_loops/cli/issues/check_open_questions.py` — docstring/help
  text if the scanned-section set widens.
- `scripts/little_loops/cli/issues/` — new `check-acceptance-criteria`
  subcommand (change 3), registered in `cli/issues/__init__.py` (parser at
  :719, dispatch at :995, usage epilog at :100-129 — see the Documentation
  correction below: `check-acceptance-criteria` and `check-verify-verdict`
  are new epilog coverage, not an existing precedent).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/autodev.yaml:543` and
  `rn-remediate.yaml:300` already call `check-open-questions`. **Widening its
  section list and signal vocabulary makes it fire more often in both loops** —
  this is the main blast radius of change 2 and must be assessed, not assumed
  benign. Both route an exit 1 into a decision/refine path, so a false positive
  costs an extra LLM pass rather than a wrong terminal state.
- `commands/refine-issue.md:296` — consider reassigning "Affected code paths" to
  `codebase-analyzer`, or adding an explicit "confirm the call path exists"
  instruction, so negative call-path facts stop falling between the two agents.
  Addresses the first defect at its source rather than only catching it downstream.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml:229` — invokes
  `refine-to-ready-issue` as its `loop:` sub-loop. Its own comments (lines 7,
  223, 239) describe the delegated pipeline as "format → refine → wire →
  confidence-check" and reference `refine-to-ready-issue`'s
  `check_missing_artifacts` state by name — both go stale once
  `verify_issue`/`check_verify_verdict`/`check_hedges`/`check_ac_automatable`
  are spliced into the chain ahead of `confidence_check`. [confirmed via grep]
- `scripts/little_loops/loops/issue-refinement.yaml:5,18` — delegates through
  `recursive-refine` (`loop: recursive-refine`) and repeats the same
  "format → refine → wire → confidence-check" pipeline description in a
  comment; same staleness. [confirmed via grep]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:140-144` — a distinct "Three-stage threshold
  check" passage (separate from the line ranges already cited elsewhere in
  this issue) that spells out the *current* chain
  `verify_scores_persisted → check_readiness → check_outcome` and each state's
  exact failure-routing target. Goes stale once the new gates are spliced in
  before `confidence_check`.
- Correction to this issue's own Signatures/Integration Map: the CLI "usage
  banner" in `cli/issues/__init__.py` is the epilog subcommand list at
  **lines 100-129** (not ~117), and `check-open-questions` itself is **not
  currently listed there** — only `check-decidable`/`check-design`/
  `check-readiness`/`check-flag`/`locate-options` are. Adding
  `check-acceptance-criteria` to that epilog is new coverage, not following an
  existing `check-open-questions` precedent there.

### Tests

- `scripts/tests/test_builtin_loops.py` — validates shipped loop YAMLs; new
  states must pass `ll-loop validate` (MR-1..MR-14).
- Existing ENH-2446 tests for `count_open_questions_in_sections` /
  `check-open-questions` — extend with the two BUG-3025 hedge lines as
  regression fixtures (both currently score `False`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestRefineToReadyIssueLoop` — two
  existing tests hard-assert the **current** routing and will fail once
  `check_decision_mid_wire` reroutes to `verify_issue`:
  `test_check_decision_mid_wire_on_no_routes_to_confidence_check` (~2039-2045,
  asserts `on_no == "confidence_check"`) and
  `test_check_decision_mid_wire_on_error_routes_to_confidence_check`
  (~2047-2054, asserts `on_error == "confidence_check"`). Both must be updated
  to assert `"verify_issue"`. A third test breaks under the five-route
  retarget: `test_wire_issue_on_error_is_confidence_check` (`:1813-1818`,
  asserts `wire_issue.on_error == "confidence_check"`) — same update. The
  other two retargeted routes (`check_wire_done.on_no`/`.on_error`,
  `mark_wire_done.on_error`) have no existing routing assertions; add them
  in the same class asserting `"verify_issue"`, so the loopback-bypass
  closure is pinned by tests, not just by the YAML.
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget::test_deterministic_warning_categories_do_not_regrow`
  (~12768-12869) — a global cross-loop WARNING ratchet over every built-in
  loop. The four new states need full `on_yes`/`on_no`/`on_error` routing,
  declared `required_inputs`, and guarded `${captured...}` interpolation, or
  this test fails and a new allowlist entry
  (`("refine-to-ready-issue", category)`, ~12801-12815) is required.
- `scripts/tests/test_issue_parser_unresolved.py::TestCountOpenQuestionsInSections`
  (lines 260-328) — extend with cases for the new hedge vocabulary ("worth
  confirming", "TBD", "needs confirmation") and the four newly-scanned
  sections (Integration Map, Codebase Research Findings, Suggested Fix
  Direction, Program Design), following the existing per-signal test shape
  (e.g. `test_edge_cases_section_counted`, `test_confidence_check_notes_counted`).
- New file `scripts/tests/test_ll_issues_check_acceptance_criteria.py` —
  mirror `scripts/tests/test_ll_issues_check_open_questions.py`'s exact
  structure (`_cli()`, `temp_project_dir`, `_write_issue()`, `_invoke()`,
  `_clean_feature()` helpers; `TestCheckOpenQuestionsHappyPath`/`Unresolved`/
  `ErrorHandling`/`TestCliRegistration`-shaped classes) with a
  `MANUAL_CRITERIA_REMAIN` stderr-token assertion in place of
  `OPEN_QUESTIONS_REMAIN`.
- New file `scripts/tests/test_ll_issues_check_verify_verdict.py` — same
  mirrored structure for the change-1 CLI: `verify_verdict: VALID` → exit 0,
  `NON_VALID` → exit 1 + `VERIFY_VERDICT_NON_VALID` stderr token, field
  absent → the documented fallback (see the field-absent AC).
- New fixture `scripts/tests/fixtures/issues/<ID>-manual-verification-criteria.md`
  — a full-issue-shape fixture (frontmatter + body, following
  `FEAT-2339-mixed-resolved-unresolved.md`'s convention) containing a
  manual-verification-style acceptance criterion, for the new CLI test file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- `scripts/tests/test_builtin_loops.py` — `test_all_validate_as_valid_fsm` (loop-wide gate, `:32-55`) already exercises every shipped loop including `refine-to-ready-issue.yaml` in-process via `little_loops.fsm.validation.load_and_validate`/`validate_fsm`, asserting zero ERROR-severity findings — this is what the Acceptance Criteria's `ll-loop validate refine-to-ready-issue` bullet is anchored to. A loop-specific `TestRefineToReadyIssueLoop` class (starting `:1243`) already asserts individual named states exist and are wired correctly (e.g. `"State 'check_wire_done' not found ..."` at `:1783`, `"State 'check_decision_mid_refine' not found ..."` at `:1961`) — new states (`verify_issue`, `check_verify_verdict`, `check_hedges`, `check_ac_automatable`) get equivalent existence/wiring assertions in this same class, following its existing per-state test pattern rather than a new one.
- `fragment: shell_exit` gate states that call `ll-issues check-*` and route `on_yes`/`on_no`/`on_error` on exit code already exist beyond this file: `autodev.yaml:529-548` (`check_decision_decidable`) and `rn-remediate.yaml:279-304` (same-named state, comment explicitly notes it "mirrors check_decision_needed_post's failure philosophy"). Both — and all four existing `check-flag` gates already inside `refine-to-ready-issue.yaml` itself (`check_decision_mid_refine`, `check_decision_mid_wire`, `check_decision_needed`, `check_missing_artifacts`) — route `on_error` to whichever branch keeps the loop moving forward (never to `diagnose`/`failed`), confirming the new `check_hedges`/`check_ac_automatable` gates' `on_error` should follow the same non-fatal convention already used throughout this file, not a stricter one.
**Blast radius of change 2, measured 2026-08-03 (pre-review):** simulated
`_OPEN_QUESTION_SECTIONS + (Integration Map, Codebase Research Findings,
Suggested Fix Direction, Program Design)` and the widened
`_OPEN_QUESTION_SIGNAL_RE` against every active (`open`/`in_progress`/
`blocked`) issue in `.issues/`, calling the real
`_section_body`/`_count_unresolved_items_in_text`:

| | issues firing |
|---|---|
| today | **0 / 65 (0%)** |
| widened | 4 / 65 (6%) |
| newly firing | 4 (FEAT-2123, ENH-2991, EPIC-2663, EPIC-2455) |

Two conclusions. (a) The widening's cost to `autodev.yaml` / `rn-remediate.yaml`
is ~4 extra LLM passes across the whole backlog — inside the "extra pass, not
wrong terminal state" framing, so **Risk drops from Medium to Low** and the
corresponding acceptance criterion becomes confirm-the-number rather than
open-ended assessment. (b) More interesting: the existing probe fires on
**zero** active issues, so both shipped loops currently pay for a gate that
never trips — evidence the current section/signal set is too narrow to be doing
any work at all, independent of this issue's motivating defect.

**Blast radius of change 3, measured the same way:** the proposed
manual-verification verb list matches **13 / 1401 (0.9%)** of issues with an
`## Acceptance Criteria` section. Sampled hits are mostly legitimate manual ACs
(FEAT-1697 "manually verifiable", FEAT-2189 "validated manually"), but two
(FEAT-1236, FEAT-1238) are non-criterion prose under the heading — hence the
checkbox-only scoping constraint recorded in change 3.

- A second independent loopback-cap example exists at `rn-remediate.yaml:887-905` (`check_remediation_budget`, counter file + `output_numeric lt target`) and a stall-based variant at `rn-remediate.yaml:333-339` (`check_open_question_progress`, `max_stall: 2`) — corroborating that `refine-to-ready-issue.yaml`'s own `check_refine_limit` counter-file pattern is this codebase's established shape for capping a specific loopback, separate from the loop-wide `circuit.repeated_failure` backstop already declared at `refine-to-ready-issue.yaml:33-36`.

_Wiring pass added by `/ll:wire-issue`:_
- FYI, not a required change: the four sections being added to
  `_OPEN_QUESTION_SECTIONS` already have other independent readers —
  `Integration Map` is scanned by `cli/issues/fingerprint.py` (extracts
  `files_to_modify`) and `research_triage.py`'s `"locator"` research-axis
  check; `Codebase Research Findings` is the merge target for
  `fold_findings.py`/`fold_research_findings.py`; `Program Design` is a
  required `common_sections` entry gated by the `check-design` family
  (`test_program_design_gate.py`, `test_ll_issues_check_design.py`). None of
  these existing consumers scan for the hedge/`?` signal regex, so no direct
  test collision was found, but these sections are prose-heavy and the most
  likely to produce false-positive hedge hits once
  `count_open_questions_in_sections` becomes a second reader of them.

## Open Questions

All three questions below are resolved pre-implementation; kept here with
their resolutions for traceability rather than deleted.

- **Q1** — **RESOLVED**: (b), `--check` hard gate, respecified as a
  write-verdict-then-shell-probe pair (`verify_issue` writes
  `verify_verdict` to frontmatter; `check_verify_verdict` reads it) rather
  than a `fragment: shell_exit` gate on the slash command's own process exit
  code, which does not carry the skill's internal verdict. See Proposed
  Solution change 1 and Program Design.
- **Q2** — **RESOLVED**: 4b (score damping), or drop change 4. 4a contradicts
  the "no added LLM budget" claim; and once changes 1-3 ship, an unchallenged
  100 can no longer buy the shortest path to `done` regardless, which removes
  most of change 4's original motivation. See Proposed Solution change 4.
- **Q3** — **RESOLVED**: fixed inside this issue, not split out. The `ISSUE_ID`
  filter is a one-edit change to `verify-issues.md`'s Step 1 issue-listing
  block; a `blocked_by` edge for a two-line fix would add more overhead than
  it saves. See Scope Boundaries.

## Acceptance Criteria

- [ ] `refine-to-ready-issue.yaml` invokes a claim-verification skill on every
      run, before `confidence_check`, on a path not gated by any score.
- [ ] `ll-issues check-open-questions` exits 1 on BUG-3025's pre-review revision
      (both hedge lines detected); regression fixtures cover both lines.
      Extract the fixture from `git show bf80f3df:<BUG-3025 path>` (original
      pre-review text) — do not hand-reconstruct from memory of "before the
      review".
- [ ] At least one corrective route in `refine-to-ready-issue.yaml` is reachable
      with `confidence_score: 100` / `outcome_confidence: 92` — i.e. a perfect
      self-grade no longer guarantees the shortest path to `done`.
- [ ] Acceptance-criteria automatability probe exits 1 on the pre-review
      BUG-3025 criterion "verify by temporarily removing the `isatty()` guard".
      Extract the fixture from `git show d85f49b5:<BUG-3025 path>`
      (reviewed-but-uncorrected state) — same rationale as above.
- [ ] The widened probe's effect on `autodev.yaml` and `rn-remediate.yaml` is
      re-measured against the implemented regex/section set and matches the
      pre-review baseline recorded in Codebase Research Findings (0/65 → 4/65
      active issues) within a small margin; a materially higher rate is a
      signal the vocabulary over-widened.
- [ ] The acceptance-criteria probe scans only checkbox items, and does not
      fire on FEAT-1236 / FEAT-1238's non-criterion prose ("Can be run manually
      on any issue...").
- [ ] `ll-issues check-open-questions ENH-3031` exits 1 on this issue's own
      pre-review revision (the change-4 "worth a decision" hedge) — the loop's
      gates catch the defect class this issue was filed about, including in
      this issue.
- [ ] `verify_issue` does not invoke `/ll:verify-issues` in a form that
      verifies or edits issues other than the run's own issue.
- [ ] All five retargeted mid-chain routes (`check_wire_done.on_no`/`.on_error`,
      `wire_issue.on_error`, `mark_wire_done.on_error`,
      `check_decision_mid_wire.on_no`/`.on_error`) point at `verify_issue`,
      asserted by routing tests — a gate-forced `refine_followup` cycle
      re-enters through the gates, not at `confidence_check`.
- [ ] `/ll:verify-issues <ID> --check` persists `verify_verdict:
      VALID|NON_VALID` to that issue's frontmatter; `ll-issues
      check-verify-verdict <ID>` exits 1 with a `VERIFY_VERDICT_NON_VALID`
      stderr token on `NON_VALID`, exit 0 on `VALID`, and exit 0 (fail-open,
      matching the loop's non-fatal `on_error` convention) when the field is
      absent.
- [ ] `ll-loop validate refine-to-ready-issue` passes.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — not a crash, but the loop's entire quality apparatus is
  currently a self-report. Every issue it marks ready inherits that. The three
  BUG-3025 defects reached a human reviewer with a 100/92 score attached.
- **Effort**: Medium — changes 1 and 2 are a loop edit plus a regex/list
  widening. Change 3 and the change-1 respec each add a new CLI subcommand
  (`check-acceptance-criteria`, `check-verify-verdict`) plus a
  `verify-issues.md` edit. Change 4 is resolved (Q2): 4b or drop.
- **Risk**: Low for change 2 (was Medium) — measured at 4/65 active issues
  newly firing, i.e. ~4 extra LLM passes across the whole backlog, and the
  failure mode is an extra pass rather than a wrong terminal state. Change 1's
  original risk — the naive form ran a mutating whole-backlog verification per
  loop run (see Prior Art precondition) — is retired by the in-scope
  `ISSUE_ID` fix plus `--check`; the residual change-1 risk is the new edit
  surface in `commands/verify-issues.md` (verdict-write step) and the
  fail-open `on_error` routes around the gates.
- **Breaking Change**: No.

## Notes

Surfaced by reviewing the `refine-to-ready-issue` run on BUG-3025 after a human
pass found three defects in its output. All three were verified against the
codebase before filing; the `88db2cd0` / `print_logo` call-path facts and the
`check-open-questions` exit-0 behavior were confirmed empirically.

Changes 1-3 add no LLM budget beyond the single `verify_issue` invocation —
the three gates (`check_verify_verdict`, `check_hedges`,
`check_ac_automatable`) are shell states running probes/regexes. This holds
now that change 4/Q2 resolved to 4b-or-drop, not 4a; 4a would have added a
guaranteed `refine_followup` pass to every run.

Pre-implementation review (2026-08-03) corrected the change-1 action (the
`ISSUE_ID` no-op and the missing `--check` prior art), fixed `max_steps` at 30,
scoped the change-3 verb scan to checkbox items, and replaced the change-2/3
"assess the blast radius" hand-wave with measured numbers.

Second pre-implementation review (2026-08-03) found the loopback bypass was
only partially closed (four of five mid-chain routes still skipped straight
to `confidence_check` on a gate-forced second pass) and that the proposed
`shell_exit` gate on `/ll:verify-issues --check` cannot work as specified —
a slash command's internal verdict doesn't reach the host CLI's process exit
code. Both are fixed above: all five routes retarget to `verify_issue`, and
change 1 is respecified as a write-verdict/read-verdict pair
(`verify_issue` → `check_verify_verdict`). Q1, Q2, and Q3 are resolved rather
than left open, and the two BUG-3025 regression fixtures are pinned to
`bf80f3df` (original) / `d85f49b5` (reviewed-but-uncorrected) so they're
extracted from a stable ref.

## Status

**Open** | Created: 2026-08-03 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-04T02:13:32 - `bf431c8e-9360-452f-ad2d-3353ebec0f47.jsonl`
- `/ll:confidence-check` - 2026-08-03T22:42:41 - `45ffda97-3031-45d5-b9ae-4e6a5274c6b7.jsonl`
- `/ll:wire-issue` - 2026-08-03T22:40:21 - `26597b53-279a-4c3f-b58f-74c43bfa7741.jsonl`
- `/ll:refine-issue` - 2026-08-03T22:32:09 - `ce4fd0b4-588c-496a-899f-5a7706ee3176.jsonl`
