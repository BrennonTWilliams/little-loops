---
id: ENH-3238
type: ENH
title: verify-issues confirms a stated cause by checking a consequence consistent
  with it
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T18:22:51Z'
completed_at: '2026-08-17T19:23:26Z'
verify_verdict: VALID
confidence_score: 98
outcome_confidence: 91
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 22
---

# ENH-3238: verify-issues confirms a stated cause by checking a consequence consistent with it

## Summary

`/ll:verify-issues` verifies that a claim's *observable consequence* holds and treats that as
confirming the claim's *stated cause*. Necessary-but-not-sufficient evidence is accepted as
sufficient, so a false causal attribution can pass with verdict `VALID` — and confirming the
symptom actively raises confidence in the false explanation.

Discovered by reviewing the `refine-to-ready-issue` run that certified BUG-3236
(run `.loops/.history/2026-08-17T170259-refine-to-ready-issue`; the `verify_issue` transcript is
session `038b6ab4-3b9f-4cfd-a4d6-dac5e7366086`, recorded as `session_jsonl` on that run's third
`action_complete` event in `events.jsonl`).

## Current Behavior

BUG-3236 asserted an identity claim: the live `issue_sessions` view "is the v16 (ENH-2462)
definition." `verify_issue` did run live-state checks — it opened `.ll/history.db` and executed:

```python
print('version:', c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
print('cols:', [r[1] for r in c.execute('PRAGMA table_info(issue_sessions)')])
# → version: 41
# → cols: ['issue_id','session_id','jsonl_path','first_message_ts','last_message_ts']
```

It also ran `ll-history sessions ENH-3195` and observed the real `no such column: issue_num`
error, reporting "Reproduction confirmed live — matches the issue exactly."

It then concluded, verbatim: "`issue_sessions` has the **pre-v36 column set** (no `issue_num`)"
— inferring the *identity of a view definition* from the *absence of one column*. Many
definitions satisfy that predicate. The live view was in fact a third variant with no committed
ancestor (a `GROUP BY issue_num` plus a `JOIN issue_events le ON le.issue_id` clause appearing in
zero commits).

The sufficient test was one line from a script it had already written, on a connection it
already held open:

```sql
SELECT sql FROM sqlite_master WHERE name='issue_sessions';
```

It compounded the error by confirming that the issue's *quotation* of the v16 source matched
`schema.py:372,386` (true) without ever diffing source-v16 against the live SQL.

Verdict: `VALID`. Downstream `confidence_check` scored 96/90.

## Expected Behavior

A causal or identity claim in an issue is verified by probing the claimed cause directly.
Observing a consequence that is merely *consistent* with the stated cause does not on its own
earn a `VALID` verdict — where the cause cannot be read directly, the verdict is `NEEDS_UPDATE`
and the unverified claim is named.

## Motivation

The `verify_issue` gate exists to be the one state in `refine-to-ready-issue` that can refute
the issue's own text. When it accepts necessary-but-not-sufficient evidence, a false root cause
is not merely missed — it is *certified*, and every downstream state inherits that certification.
BUG-3236 reached `verify_verdict: VALID`, `confidence_score: 96`, `outcome_confidence: 90` with a
central causal claim that one additional query disproved. Implementation work started from that
false cause would have targeted the wrong fix.

The change is small and well-precedented: one claim-shape rule in a file that already contains an
identically-shaped rule for negative claims.

## Integration Map

### Files to Modify

- `commands/verify-issues.md` — **the only hand-authored edit site.** Add the causal/identity-claim
  rule under `#### B. Verify Against Codebase` (heading at line 126) as the method for its check 4
  `**Test claims**: Is the described behavior accurate?` (line 130), or as its own unconditional
  subsection between §B and `#### C. Determine Verdict` (line 155).
- `skills/ll-verify-issues/SKILL.md` — bridge skill that invokes the command; keep in sync with any
  frontmatter/tool-declaration changes (precedent:
  `test_enh3126_verify_issues_graph_seeding.py::TestVerifyIssuesFrontmatter` already asserts the
  command and this skill mirror each other's `Bash(ll-code:*)` declaration). No body change expected
  here unless tool declarations change.

**Do NOT place the rule in §2B.0 "Graph-assisted checks" (lines 109-124).** The refine pass
originally proposed that site by structural analogy to the **Negative claims** rule (lines 113-116),
without checking the block's activation gate. §2B.0 opens with "Active only when the issue names
concrete symbols/files and `ll-code --json status` reports `available: true`" and closes with
"Provider absent, `status.available: false`, or a query exiting `2` → silent fallback to today's
flow, **zero behavior change**." A rule filed there is silently inert on every graph-absent or
stale-index run — precisely the fallback path. The rule is also not graph-derived: the bullets it
would join are introduced by "Wire the **results** into the checks below", i.e. they consume
`ll-code` query output, which this rule does not. It must be unconditional.

### Generated Host Mirrors (do not hand-edit)

Three host-specific copies carry the full prompt body and all contain the §B.0 block and the
**Negative claims** rule:

- `.gemini/commands/verify-issues.toml`
- `.qwen/commands/ll/verify-issues.md`
- `.kimi-code/skills/ll-verify-issues/SKILL.md`

All three are **generated**, not authored. `scripts/little_loops/adapters/core.py:55` registers
`"gemini": ("little_loops.adapters.gemini", "GeminiEmitter")`, and the docstring at
`adapters/core.py:360` names qwen, kimi-code, and gemini together as the SKILL.md-mirroring
emitters. `/ll:wire-issue` concluded `.gemini/commands/verify-issues.toml` was "confirmed
non-generated (no 'DO NOT EDIT'/auto-generated banner)" — absence of a banner is not evidence of
hand-authorship, and that conclusion is **wrong**. Hand-editing any of these three produces drift
that the next `ll-adapt` run silently reverts.

Correct procedure: edit `commands/verify-issues.md`, then regenerate:

```bash
ll-adapt --host gemini --apply
ll-adapt --host qwen --apply
ll-adapt --host kimi-code --apply
```

### Similar Patterns
- **Negative claims** rule, `commands/verify-issues.md:113-116` — the claim-shape → required probe →
  sufficiency-note → verdict-consequence structure this rule mirrors. Mirror its *structure*, not
  its *location*.
- ENH-3045 (done) — established negative-claim doctrine in `/ll:wire-issue` and `/ll:refine-issue`.
  See Scope Boundaries for why this issue does not follow it into those two passes.

### Documentation
- None required. The rule is prompt text in the command file itself; `docs/reference/CLI.md` does
  not enumerate verify-issues' internal checks.

### Configuration
- N/A

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:279-287` — the `verify_issue` state invokes `/ll:verify-issues ${captured.issue_id.output} --check --auto`; non-fatal on error (`on_error: check_verify_verdict`), same as `wire_issue`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:289-299` — `check_verify_verdict` gate (`fragment: shell_exit`) routes on the exit code of `ll-issues check-verify-verdict`.
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict()` reads `verify_verdict` from frontmatter; exit 0 (routes to `check_hedges`) when absent or `VALID` (fail-open by design); exit 1 (routes to `check_refine_limit`, forcing `refine_followup`) for any other value.
- Verdict collapse: Section 2.5's `--check` mode logic (`commands/verify-issues.md:212-230`) writes only the binary `verify_verdict: VALID|NON_VALID` to frontmatter — the FSM gate never sees which of the nine verdict-table values (`#### C. Determine Verdict`, lines 157-169) was actually assigned.
- `confidence_check` (downstream state) consumes the issue text/frontmatter as already certified by `verify_issue` and does not itself re-probe the codebase (per this issue's own Scope Boundaries section) — a `VALID` verdict propagates unquestioned.

### Tests
- `scripts/tests/test_enh3126_verify_issues_graph_seeding.py` — closest existing precedent for content-assertion tests against this file; `TestSection2B0GraphAssistedChecks` already asserts the Negative-claims/Anchor-relocation rules' presence and structure by flattened-body string matching (`" ".join(body.split())`). A new causal/identity-claim rule test should follow this same pattern; no existing test currently asserts on check 4 ("Test claims") or the verdict table by name.
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — CLI subprocess tests for the `check-verify-verdict` exit-code contract; unaffected by this change but exercises the consuming side of `verify_verdict`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py` — table-driven substring-presence convention already carries three `("commands/verify-issues.md", "<substring>", "<issue-id>")` rows (lines 210, 248, 304) for prior ENH/BUG changes to this same file (BUG-2423, ENH-3126). Optionally add a fourth row anchoring the new causal/identity-claim rule's key phrase under `ENH-3238`, matching the file's existing per-issue-touch convention.

## Program Design

### Signatures
- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/check_verify_verdict.py:41`; reads `verify_verdict` from frontmatter and returns 0 (VALID or absent, fail-open) or 1 (any other verdict, routes the loop to `check_refine_limit`).

### Decision Rules

- **Gap kind**: a new claim-shape detection rule inside `commands/verify-issues.md` **§B (check 4's method), unconditional** — structured identically to the existing **Negative claims** rule (lines 113-116): claim shape → required direct probe → necessary-vs-sufficient statement → verdict consequence. Structure is borrowed from §2B.0's rule; location is not (see Integration Map → Files to Modify for why §2B.0 is the wrong site).
- **Trigger phrases (inputs)**: issue text attributing observed state to a named cause, origin, or version — "is the vN definition", "caused by", "because", "the result of", "introduced by", "this is the pre-X form".
- **Firing constraint (scope the trigger)**: the rule fires only on a claim that is **load-bearing for the fix** — the issue's stated root cause, an artifact-identity assertion, or a version/origin attribution that determines what gets changed. It does **not** fire on incidental causal connectives in narrative prose ("we filed this because the reader was empty"). Without this constraint the trigger list — which includes the bare words "because" and "caused by" — over-fires on nearly every issue, and over-firing is not free (see Impact → Risk).
- **Required probe**: read the claimed cause directly, in its own terms, over an inferred/consequence-only signal — e.g. `SELECT sql FROM sqlite_master WHERE name=...` (stored DDL) is sufficient where `PRAGMA table_info(...)` (inferred column shape) is not; the actual file/commit content over a symptom merely consistent with it.
- **Sufficiency rule**: observing a consequence consistent with the stated cause is necessary but not sufficient to confirm it — it only fails to refute it.
- **Escape hatch / dismissal**: if the cause can be read directly and the direct read confirms it, `VALID` is available as before. If the cause cannot be read directly, the verdict is `NEEDS_UPDATE` (glossed in the verdict table, `commands/verify-issues.md:157-169`, as "Valid but needs clarification") rather than `VALID`, and the unverified claim is named in the output.

### Call Path

`verify_issue` -> `cmd_check_verify_verdict` -> `check_verify_verdict`

Expanded, with anchors:

- `verify_issue` state (`scripts/little_loops/loops/refine-to-ready-issue.yaml:279-287`) invokes
  `/ll:verify-issues ${captured.issue_id.output} --check --auto`.
- `/ll:verify-issues` runs §B (`commands/verify-issues.md:126-130`) — **the new causal/identity-claim
  rule's site**, unconditional — then §C's verdict table (`commands/verify-issues.md:157-169`).
- §2.5 `--check` mode (`commands/verify-issues.md:212-230`) collapses the nine-value verdict to
  binary `verify_verdict: VALID|NON_VALID` in frontmatter; `NEEDS_UPDATE` becomes `NON_VALID`.
- `cmd_check_verify_verdict` (`scripts/little_loops/cli/issues/check_verify_verdict.py:41`) reads
  that field and exits 0 or 1.
- `check_verify_verdict` gate (`scripts/little_loops/loops/refine-to-ready-issue.yaml:289-299`)
  routes on that exit code: 0 -> `check_hedges`, 1 -> `check_refine_limit` -> `refine_followup`.

## Implementation Steps

1. **Add the rule.** `commands/verify-issues.md` gains a causal/identity-claim rule under
   `#### B. Verify Against Codebase` — as the method for check 4 (`**Test claims**`, line 130), or
   as its own subsection between §B and `#### C. Determine Verdict` (line 155). Shape it like the
   existing **Negative claims** rule (lines 113-116): claim shape → required direct probe →
   necessary-vs-sufficient statement → `NEEDS_UPDATE` when the cause cannot be read directly.
   Include the load-bearing firing constraint. See Program Design → Decision Rules for exact inputs
   and probe. **Not** in §2B.0 — see Integration Map → Files to Modify.
2. **Regenerate the host mirrors.** Run `ll-adapt --host gemini --apply`,
   `ll-adapt --host qwen --apply`, `ll-adapt --host kimi-code --apply`. Do not hand-edit
   `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, or
   `.kimi-code/skills/ll-verify-issues/SKILL.md`.
3. **Add the content-assertion test.** Assert the new rule's presence and structure in
   `commands/verify-issues.md`, following `scripts/tests/test_enh3126_verify_issues_graph_seeding.py::TestSection2B0GraphAssistedChecks`
   (flattened-body string matching). Assert it appears **outside** the §2B.0 block, so a later
   refactor cannot silently move it back under the `ll-code`-availability gate.
4. **Optionally** add a `("commands/verify-issues.md", "<new rule anchor phrase>", "ENH-3238")` row
   to `scripts/tests/test_wiring_skills_and_commands.py`, per that file's per-issue-touch
   convention (see Tests subsection above).
5. **Behavioral check (manual, not a pytest gate).** Extract the pre-correction BUG-3236 text and
   re-verify it — see Acceptance Criteria for the exact commands and expected outcome.
6. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - The gate is the loop's only refutation state; when it certifies a false
  cause, downstream states inherit the certification and implementation starts from the wrong
  target. Not P1: prevalence is unestablished (n=1) and no released behavior is broken.
- **Effort**: Small - one claim-shape rule added to a markdown command file, mirroring the
  structure of a rule already in the same section.
- **Risk**: Medium (not Low) - additive prompt guidance, but over-triggering is not merely a time
  cost. §2.5's verdict collapse (`commands/verify-issues.md:212-230`) maps `NEEDS_UPDATE` →
  `verify_verdict: NON_VALID` → `ll-issues check-verify-verdict` exit 1 →
  `refine-to-ready-issue.yaml:289-299` routes to `check_refine_limit`, forcing a
  `refine_followup` iteration. Every spurious trigger therefore consumes refine budget and can
  push an otherwise-sound issue against the refine limit. The trigger list includes the bare words
  "because" and "caused by", which appear in most issue prose — the load-bearing firing constraint
  in Program Design → Decision Rules is what keeps this from over-firing, and is **not optional**.
- **Breaking Change**: No

## Root Cause

`commands/verify-issues.md`, section `#### B. Verify Against Codebase` (lines 126-130). Four of
its five checks are artifact existence and location — files exist, line numbers resolve, quoted
snippets match, decisions-log gate. The fifth is `4. **Test claims**: Is the described behavior
accurate?` — a bare instruction with no method attached and no notion of claim *shape*.

The section therefore has no rule distinguishing:
- **consequence claims** ("reader X throws `no such column`") — directly observable, and
  correctly verified here; from
- **identity / causal claims** ("the live view IS the v16 definition", "this is caused by Y") —
  where observing a consistent consequence does not establish the attribution.

The file already contains exactly the right pattern for the missing rule. Lines 113-116 define a
claim-shape-triggered method for **negative claims**, including the sufficiency reasoning that is
absent for causal claims:

> **Negative claims**: for issue text asserting "X is never called" ... run `ll-code
> callers-of`/`references` on the named symbol before falling back to Grep-only reasoning. A hit
> refutes the claim outright; a miss is a lead that the normal exploratory pass must still confirm.

## Proposed Solution

Add an identity/causal-claim rule to `commands/verify-issues.md` **§B** (unconditional; *not*
§2B.0 — see Integration Map), mirroring the negative-claims rule's structure (claim shape →
required probe → sufficiency note):

1. **Detect the shape.** Issue text attributing observed state to a specific named cause,
   origin, or version — "is the vN definition", "caused by", "because", "the result of",
   "introduced by", "this is the pre-X form" — **where that attribution is load-bearing for the
   fix** (stated root cause, artifact identity, version/origin that determines what changes).
   Incidental causal prose does not trigger the rule.
2. **Probe the cause directly, not a consequence.** Where the artifact can be read in its own
   terms, read it: stored DDL (`SELECT sql FROM sqlite_master`) over inferred shape
   (`PRAGMA table_info`); the actual file/commit content over a symptom consistent with it.
3. **State the sufficiency test explicitly.** Confirming a consequence consistent with the
   stated cause does not confirm the cause; it only fails to refute it. If the cause cannot be
   read directly, the verdict is `NEEDS_UPDATE`, not `VALID`.
4. Consider a distinct verdict or a Verification Notes annotation recording which claims were
   directly verified vs. only corroborated, so a later reader can tell them apart — the same
   motivation as the existing provider/freshness recording requirement at lines 118-124.

## Acceptance Criteria

- [ ] `commands/verify-issues.md` §B contains a causal/identity-claim rule naming the claim
      shape, the required direct probe, and the necessary-vs-sufficient distinction.
- [ ] The rule states that a consequence consistent with a stated cause does not on its own
      support a `VALID` verdict.
- [ ] The rule sits **outside** the §2B.0 "Graph-assisted checks" block, so it runs regardless of
      `ll-code` availability or index freshness. Asserted by test, not by inspection.
- [ ] The rule names the load-bearing firing constraint (root cause / artifact identity /
      version attribution only — not incidental causal prose).
- [ ] The three generated host mirrors are regenerated via `ll-adapt`, not hand-edited, and carry
      the new rule: `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`,
      `.kimi-code/skills/ll-verify-issues/SKILL.md`.
- [ ] `python -m pytest scripts/tests/` exits 0.

### Behavioral check (manual — not a pytest gate)

This one is an LLM-judgment outcome and is deliberately **not** wired as an automated assertion; it
is a one-time spot-check performed during implementation and recorded in the PR/commit body.

The corrected BUG-3236 now states the true cause, so the check must run against the prior revision.
Pinned SHAs (verified present in this repo's history):

- `be5868c8` — `issues(BUG-3236): file issue_sessions view drift…` — **pre-correction** text
  carrying the false "is the v16 (ENH-2462) definition" claim.
- `91968400` — `issues(BUG-3236): pin exact root cause of issue_sessions view drift` — the
  correction.

```bash
git show be5868c8 --stat            # locate the BUG-3236 path at that revision
git show be5868c8:<path> > /tmp/BUG-3236-pre.md
```

- [ ] Verifying that pre-correction text surfaces the root-cause/identity claim as unverified
      (`NEEDS_UPDATE`) rather than `VALID`, and names the unverified claim in its output.

**Consider promoting this to a real signal.** This issue's own Scope Boundaries invokes the
MR-1/MR-2 principle — pair an LLM judgment with a measurable external signal — yet every automated
AC above only asserts that prompt text exists, i.e. that the rule was *written*, not that it
*changes a verdict*. `be5868c8` is a ready-made fixture with a known-correct expected outcome.
`/ll:create-eval-from-issues ENH-3238` over that revision would turn this section into a
regression check. Out of scope for the minimal fix; worth filing as a follow-up if not done here.

## Scope Boundaries

Two adjacent things are deliberately **not** part of this issue:

- **`confidence_check` is not the fix site.** Its transcript
  (`83adf706-3c34-48ba-adbd-2ccf3898278d.jsonl`) shows zero live queries: document, source, and
  `ll-issues format-check` only, scoring complexity / test-coverage / ambiguity / change-scope.
  96 was correctly computed against what it measures. It is structurally incapable of catching
  this and should not be taught to.
- **Do not widen meta-loop detection.** `refine-to-ready-issue` is correctly *not* a meta-loop:
  `_is_meta_loop` (`scripts/little_loops/fsm/validation/meta_rules.py:48-70`) keys on actions
  touching `loops/*.yaml`, `skills/`, `agents/`, `commands/`, `.claude/`, and this loop writes
  `.issues/`. Capturing it would also impose the diagnose-first shape and benchmark
  requirements, which do not fit an issue-refinement loop. The MR-1/MR-2 *principle* (pair an
  LLM judgment with a measurable external signal) is what transfers here; the classification is not.

## Notes

A third candidate mitigation was considered and **refuted by the evidence**: a hard gate refusing
`ready` while a Steps to Reproduce block has no recorded execution output. The reproduction *was*
executed in this run, so that gate would have passed BUG-3236 unchanged.

Prevalence is unestablished, deliberately: BUG-3236 is the only `open` issue among 106 carrying
`verify_verdict: VALID`; the other 24 verified BUGs are all completed, so their claims cannot be
re-tested without confounding. A grep across them for post-hoc root-cause corrections returned one
hit (BUG-3102) whose "turned out" is narrative, not a correction. **n=1** — the fix is justified by
the mechanism being clear and the change being small, not by a demonstrated pattern.

Follows ENH-3031, which added the `verify_issue` gate to this loop; this refines the gate's method
rather than its placement.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-17T19:23:08 - `35d64d8e-092e-4c90-875f-40feb688fbd4.jsonl`
- `/ll:confidence-check` - 2026-08-17T19:10:24 - `1c7713ed-8915-4fd7-8992-b696cbcef42b.jsonl`
- `/ll:confidence-check` - 2026-08-17T18:58:30 - `96129ae9-f1da-4ee1-bce0-e86f5c24bd56.jsonl`
- `/ll:verify-issues` - 2026-08-17T18:56:27 - `99964d33-7f49-497c-aa7c-9d0d86522353.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:52:59 - `4e8f8734-194a-4c20-b801-eb0c8e45c841.jsonl`
- `/ll:verify-issues` - 2026-08-17T18:51:05 - `23b9a5d1-9d07-4c63-9fa5-d1902a7d2050.jsonl`
- `/ll:wire-issue` - 2026-08-17T18:49:03 - `76f03f4e-0cb6-4ac4-854d-39324ba951e8.jsonl`
- `/ll:refine-issue` - 2026-08-17T18:41:21 - `4f89a7a6-a58a-4734-9b7f-4ae8ccdb2cd4.jsonl`
- `/ll:capture-issue` - 2026-08-17T18:23:56 - `66dab8b6-e923-43d4-9f0e-eccb97176e0f.jsonl`
