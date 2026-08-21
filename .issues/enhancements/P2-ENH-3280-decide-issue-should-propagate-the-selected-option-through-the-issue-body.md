---
id: ENH-3280
type: ENH
title: decide-issue should propagate the selected option through the issue body
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:46:10Z'
labels:
- decide-issue
- skills
- pipeline
- consistency
blocked_by:
- BUG-3279
relates_to:
- BUG-3278
- BUG-3279
- ENH-3277
---

# ENH-3280: decide-issue should propagate the selected option through the issue body

## Summary

`/ll:decide-issue` records a decision in three places — a `> **Selected:**` callout, a
`### Decision Rationale` subsection, and `decision_needed: false` — and changes nothing else. Prose
elsewhere in the issue that recommends or is conditioned on a *losing* option survives verbatim,
so the file ships with implementation steps instructing work that was decided against.

## Current Behavior

Phases 6–7 of `skills/decide-issue/SKILL.md` define exactly those three writes. There is no phase
that reconciles the rest of the document against the selection.

Observed on ENH-3277 (2026-08-21), where Option A was selected and the body still contained the
list below. **These have since been repaired by hand** — ENH-3277 is a record of the defect, not a
reproducer. Line numbers are as-observed, pre-repair; use `git show` on the commit that captured
this issue to see the original. A fresh reproducer fixture is needed (see *Tests*).

- `**Recommendation: Option C.**` (line 193) — a direct contradiction of the callout 35 lines above
- `*If Option C is taken*, the following elsewhere in this issue change and must be updated in the
  same pass:` (line 198) followed by an explicit three-item propagation checklist
- Implementation step 3b (line 588): *"Under the recommended **Option C** they become genuine
  drop-ins via `ll-config get --raw project.<key>`, which must land … before either YAML is
  touched"* — an imperative instruction to build the rejected option
- `## Scope Boundaries` (line 695): "No new production code — **conditional on the *DECISION
  REQUIRED* outcome**", still framing the boundary as unsettled
- `## Program Design` § Signatures (lines 718–725): two entries specifying the rejected `--raw`
  surface

Counts and scope statements keyed to the pre-decision option set also go stale ("nine files,
eleven inline reads, ten live" describes work Option A reduces to seven files).

## Expected Behavior

After `/ll:decide-issue` completes, the issue reads as a document that only ever advocated the
selected option. No recommendation names a loser, no implementation step instructs rejected work,
and no scope boundary is still framed as conditional on the decision. Rejected options survive
only as the alternatives they now are — in the option list and the Decision Rationale's
scoring table.

## Motivation

`/ll:decide-issue` sits at `refine → **decide** → wire → ready → manage`. `/ll:manage-issue` reads
the whole file, not just the Decision Rationale. A document whose imperative steps and its
decision callout disagree is a document that can be implemented wrongly by following it
faithfully — and the contradiction is *introduced* by the decision pass, since before it ran the
body was internally consistent.

That the propagation work is expected is not an inference: ENH-3277's own text (line 198) wrote
the checklist of what must change if a given option won. The skill had that list in front of it
and had no phase in which to act on it.

### Half of this already exists — `format-check`'s `unapplied_decision` (found 2026-08-21)

`issue_parser._unapplied_decision` (`:1392`) already **detects** this defect: it enumerates option
blocks, and reports rejected-option identifiers still present in directive sections as
`unapplied_decision` gaps. So the missing capability is narrower than "notice the problem" — it is
**acting on it at decision time**.

Two consequences for this issue:

1. **Reuse the detector rather than writing a second one.** Phase 7c should drive off the same
   rejected-identifier extraction, so detection and remediation cannot drift apart.
2. **The detector must be fixed first, or Phase 7c inherits its noise.** On ENH-3277 it currently
   emits ~40 findings, nearly all false — `pytest`, `lint_cmd`, `ll-config get` — because the
   rejected option's block absorbs the section's trailing analysis prose (**BUG-3279**, which
   documents this as its second confirmed consumer). A propagation phase driven off that signal
   today would rewrite correct prose. **BUG-3279 is a hard prerequisite.**

## Proposed Solution

Add **Phase 7c: Propagate Selection** after Phase 7b, before the session log.

Scan the full file (not just `## Proposed Solution`) for text keyed to the option set and rewrite
it to the decided state:

1. **Recommendation markers naming a loser** — `Recommendation: <X>`, `Recommended: <X>`,
   `we should take <X>` where `<X>` is not the winner. Rewrite to name the selection, or strike and
   fold into the Decision Rationale as a "considered and rejected" line.
2. **Conditional blocks keyed to an option** — `If <X> is taken, …`, `Under <X>, …`,
   `conditional on the DECISION REQUIRED outcome`. For the winner: unwrap the condition and state
   it declaratively. For a loser: delete, or demote to a parenthetical under the rejected option.
3. **Imperative steps referencing a loser** — any `## Implementation Steps` item naming a rejected
   option. These are the highest-risk instances (an implementer executes them) and should be
   rewritten to the winner's shape or marked not-applicable, never left as-is.
4. **Sections the issue itself flags** — when the body contains an explicit propagation checklist
   for the selected option, apply it item by item and report each edit.

Report every propagated edit in Phase 9 with its line reference, so the pass is auditable rather
than silent.

**Bounded scope.** Phase 7c rewrites prose *keyed to the option set only*. It does not restate
counts, re-derive scope, or re-run analysis — a decision pass must not become a refine pass. Where
propagation implies a downstream change it cannot safely make (stale counts, an untouched
`## Scope Boundaries` figure), it flags the location in the report rather than editing.

**Idempotency.** Mirroring Phase 7a: if `### Decision Rationale` already exists and no
loser-keyed prose remains, log `✓ Phase 7c: no unpropagated references — skipping` and write
nothing.

## Integration Map

### Files to Modify

- `skills/decide-issue/SKILL.md` — new Phase 7c; Phase 9 report gains a propagated-edits block
- `skills/decide-issue/reference.md` — the Phase 9 output template lives here

### Tests

- A fixture whose body recommends the losing option: assert the marker is rewritten and reported
- A fixture with an `If <loser> is taken` conditional block: assert it is removed or demoted
- A fixture with an implementation step naming the loser: assert the step no longer instructs the
  rejected work
- An already-propagated fixture: assert a second run writes nothing (idempotency)
- `_unapplied_decision` test coverage: `scripts/tests/test_issue_parser.py:4757-4965`, class
  `TestUnappliedDecision`, using an inline `_issue()` builder helper (`:4765-4770`) rather than
  on-disk `.md` fixtures — no fixture file for this detector exists under
  `scripts/tests/fixtures/issues/`
- A live-corpus sweep test already exists and documents a known precision limit:
  `scripts/tests/test_issue_parser.py:4968`, `TestUnappliedDecisionLiveCorpusSweep.test_corpus_sweep_does_not_crash`
  — asserts `_unapplied_decision` never raises across `.issues/`, and is explicitly
  report-only/non-blocking due to ~40% false-positive rate on the real corpus (this is the noise
  BUG-3279 is fixing)
- `decide-issue`'s own test file, `scripts/tests/test_decide_issue_skill.py`, tests SKILL.md as
  prose/documentation (the skill has no executable binary) via a `_phase_text()` slice-and-assert
  helper reused across five phase test classes (e.g. lines 233-238, 290-295, 402-406). A Phase 7c
  test class should follow this same slicing convention against the new `### 7c` heading rather
  than attempting to execute the skill.

### Documentation

- `skills/decide-issue/reference.md` — Phase 9 output report template

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- `_unapplied_decision(content: str) -> list[str]` (`scripts/little_loops/issue_parser.py:1392`) returns only formatted reason strings — `"{section} still specifies \`{identifier}\` (rejected option)"` (`:1513`) — not a structured `(section, identifier)` tuple. Phase 7c must parse this string to recover the section name and identifier, since no structured API exists.
- Surfaced today via `ll-issues format-check <ID> --format json` → `unapplied_decision` key (`scripts/little_loops/cli/issues/format_check.py:672-685`, JSON serialization at `issue_parser.py:594`) — a skill-authored Phase 7c can consume this over subprocess without new Python glue.
- `unapplied_decision` is **not** in the `--fix`/`--apply` dispatch list (`format_check.py:98-113`, which covers `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`, `template_placeholders`) — there is no existing auto-repair path; Phase 7c must perform its own edits.
- `check_format_gaps` (`issue_parser.py:1114`) is the sole caller of `_unapplied_decision`; `unapplied_decision` is a **blocking** (non-advisory) gap class on `FormatGaps.has_blocking_gaps` (`issue_parser.py:555-565`) — so the pre-fix state already fails `format-check`, independent of this issue.
- `_DECISION_DIRECTIVE_SECTIONS = ("Proposed Solution", "Program Design", "Implementation Steps", "Files to Modify", "Acceptance Criteria")` (`issue_parser.py:1302-1308`) is the closed list of sections `_unapplied_decision` scans — Phase 7c's sweep scope should match this list, not invent a broader one.
- Supporting extraction helpers Phase 7c may need for finer-grained matching beyond the formatted-string output: `_option_block_spans` (`:1371`), `_selected_option_title` (`:1322`), `_option_label` (`:1335`), `_decision_identifiers` (`:1341`) — all private module functions with no CLI wrapper; only reachable in aggregate via `_unapplied_decision`'s output.

### Conventions in Force
- Lettered sub-phases (`### 7a`, `### 7b`, ...) nest under one `## Phase N` parent, each a discrete ordered write — evidence: `skills/decide-issue/SKILL.md:399-424` (7a/7b under Phase 7) and `skills/wire-issue/SKILL.md:336-452` (8a/8b/8c under Phase 8). No skill in the repo goes past a `c` suffix; Phase 7c would be the first `c`-level sub-phase in `decide-issue`.
- Idempotency guards are phrased "**Idempotency [rule]**: if `<condition>`, skip the write and log `<marker> <message>`" — evidence: `skills/decide-issue/SKILL.md:409` (uses `⚠` for "content already present") and `:424` (uses `✓` for "flag already at target value"). The two symbols are not interchangeable within this skill; ENH-3280's own "Mirroring Phase 7a" points at the `⚠` form since Phase 7c is a content-presence check, not a flag check.
- `/ll:reconcile-issue` (`commands/reconcile-issue.md:46-117`) is the only existing precedent in this codebase for rewriting (not just appending to) issue prose, and it bounds itself with an explicit rewrite allowlist, a preserve-untouched list, and a rule that "every rewritten claim must trace to an existing finding" (`:112-117`). Every other prose-touching skill (`wire-issue`, `refine-issue`) is append-only or marker-only. Phase 7c's "Bounded scope" language should be understood as adopting this same shape, not a novel one.
- Audit-trail reporting of edits made during a rewrite pass uses a dedicated report subsection, one bullet per edit, each citing its driving evidence — evidence: `commands/reconcile-issue.md:288-296` (`## CORRECTIONS_MADE`, `[reconcile]`-tagged bullets citing a quoted finding) and `skills/decide-issue/reference.md:125-128` (`## CHANGES APPLIED`, fixed-choice bullets). No existing report block cites literal `file:line` per edit — reconcile-issue's closest analog cites step numbers, not line numbers; ENH-3280's "with its line reference" requirement has no direct precedent to copy.

## Program Design

### Signatures

- `_unapplied_decision(content: str) -> list[str]` — the sole existing entry point Phase 7c drives
  off; returns formatted reason strings only, one per `(section, identifier)` pair, never a
  structured tuple (`scripts/little_loops/issue_parser.py:1392`)
- `check_format_gaps(content: str) -> FormatGaps` — sole caller of `_unapplied_decision`; invoked
  from `ll-issues format-check <ID> --format json`, which serializes the list under the JSON key
  `"unapplied_decision"` (`issue_parser.py:1114`, CLI at `scripts/little_loops/cli/issues/format_check.py:672-685`,
  JSON key at `issue_parser.py:594`) — the subprocess-callable surface Phase 7c uses; no new Python
  glue is required
- `_DECISION_DIRECTIVE_SECTIONS: tuple[str, ...]` — the closed set of section names
  `_unapplied_decision` scans; Phase 7c's sweep scope must match it, not invent a broader one
  (`issue_parser.py:1302-1308`)

### Call Path

`/ll:decide-issue` Phase 7c (new `### 7c` under `## Phase 7: Apply Changes`,
`skills/decide-issue/SKILL.md:399`, inserted after `### 7b` at `:439`) runs after Phase 7a/7b have
already written the callout and frontmatter, so `_unapplied_decision`'s own precondition (a
resolvable `> **Selected:**` callout) is satisfied by the time Phase 7c fires ->
shells out to `ll-issues format-check <ID> --format json` -> `cmd_format_check`
(`format_check.py:476`) -> `check_format_gaps` (`issue_parser.py:1114`) -> `_unapplied_decision`
(`issue_parser.py:1392`) -> JSON `unapplied_decision` list returned to the skill -> skill parses
each `"<Section> still specifies \`<identifier>\` (rejected option)"` string to locate the
identifier's occurrence in that section -> Edit tool rewrites/demotes/strikes the matched prose
per the four categories in `## Proposed Solution` -> skill re-invokes `format-check` to confirm
`unapplied_decision` is now empty before proceeding to Phase 8.

### Decision Rules

The four rewrite categories (recommendation markers, conditional blocks, imperative steps, explicit
checklists) are already fully specified with their trigger patterns and per-category disposition in
`## Proposed Solution` above — no separate decision table is needed here. The one rule not yet
pinned down: the **input** to those categories is `_unapplied_decision`'s per-identifier findings
(closed section set above), not a fresh full-text scan — Phase 7c only acts where the detector
already reports a hit. Escape hatch: Phase 7c's own idempotency check (`## Proposed Solution`,
"Idempotency") — skip and log if a post-7a/7b `format-check` shows `unapplied_decision` already
empty.

## Implementation Steps

1. **Land BUG-3279 first** — Phase 7c drives off `_unapplied_decision`, which is unusable until
   its span bug is fixed.
2. Write Phase 7c into `skills/decide-issue/SKILL.md` with the four reference categories and the
   explicit bounded-scope statement (option-keyed prose only, never a re-refine).
3. Extend the Phase 9 report template in `skills/decide-issue/reference.md` with a propagated-edits
   block and a flagged-but-not-edited block.
4. Verify against a fixture reconstructed from ENH-3277's pre-repair state (`git show` the capture
   commit): after a run, the `Recommendation: Option C` marker, step 3b's `--raw` instruction, and
   the two `--raw` Signatures entries are gone or demoted, and the stale counts are *flagged*
   rather than silently rewritten. The hand-repaired ENH-3277 doubles as the expected output —
   compare against it rather than inventing an oracle.

## Impact

- **Priority**: P2 — the pass currently introduces the contradiction it should resolve, and the
  affected text is imperative (an implementer acts on it)
- **Effort**: Medium — no code, but the propagation rules need care to stay bounded
- **Risk**: Medium — this is the first phase that rewrites arbitrary issue prose rather than
  appending to it. Over-reach turns a decision pass into an unreviewed refine pass; the
  bounded-scope rule and the auditable edit report are the mitigations
- **Breaking Change**: No

## Related Key Documentation

- `skills/decide-issue/SKILL.md` — Phases 6–7 define the current three-write contract
- ENH-3277 — the observed case, including its own line-198 propagation checklist
- BUG-3278 — `decision_needed` cleared while other decision points stay open; same pass, adjacent
  defect

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-08-21T17:19:06 - `ea08ee55-36d8-4ff2-b8d4-2a20e7e2ad81.jsonl`
- `/ll:capture-issue` - 2026-08-21T16:00:38 - `826fb04a-1812-4193-be3d-c48a972bd311.jsonl`
- `/ll:capture-issue` - 2026-08-21T15:46:43 - `da526826-2179-460f-b823-35695378ac55.jsonl`
