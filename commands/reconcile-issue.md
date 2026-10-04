---
description: Rewrite an issue's Implementation Steps, Acceptance Criteria, and Integration Map (Files to Modify, Dependent Files, Similar Patterns, Tests, Documentation) in place from its own accumulated research findings — plus, conditionally, a Scope Boundaries claim contradicted by those findings — without appending or bulldozing human prose
argument-hint: "ISSUE_ID [--check] [--from-verify-evidence]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(ll-issues:*)
  - Bash(git:*)
disable-model-invocation: true
metadata:
  short-description: Reconcile an issue's directive sections against its own research findings
arguments:
  - name: issue_id
    description: Issue ID to reconcile (e.g., FEAT-2672, BUG-004)
    required: true
  - name: flags
    description: "Optional flags: --check (report the plateau verdict without writing, for FSM evaluators); --from-verify-evidence (BUG-3695: also treat the recorded DIRECTIVE_DRIFT verify_evidence as a source, allowing entailed Acceptance Criteria / Implementation Step additions)"
    required: false
---

# Reconcile Issue

You are tasked with **reconciling an issue's directive sections against its own
accumulated research**. Over a long refine/spike/confidence-check cycle,
`/ll:refine-issue` and `/ll:confidence-check` only **append** new "Codebase
Research Findings" bullets — they never rewrite the issue's own Implementation
Steps / Acceptance Criteria / Integration Map to match. When those directive
sections contradict the findings, `/ll:confidence-check` re-flags the same
Concern every pass and the Readiness score plateaus.

Your job is a **targeted, in-place rewrite** of the unconditional directive
sections — `## Implementation Steps`, `## Acceptance Criteria`, and the whole
`## Integration Map` section (ENH-3246) — plus, conditionally, a
`## Scope Boundaries` claim the findings directly refute (ENH-2937) — so they
reflect the accumulated findings. **Not** another appended finding, and
**not** a wholesale rewrite.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.

## Contract (read this first — it is binding)

**Rewrite ONLY these directive sections, in place:**
1. `## Implementation Steps`
2. `## Acceptance Criteria`
3. `## Integration Map` — the whole section, including every `###`
   subsection (`### Files to Modify`, `### Dependent Files
   (Callers/Importers)`, `### Similar Patterns`, `### Tests`,
   `### Documentation`). All five hold the same kind of content — directive
   statements derived from `### Codebase Research Findings` — and go stale the
   same way, so none is singled out (ENH-3246).

**Conditionally rewrite-eligible — `## Scope Boundaries`:** a Scope Boundaries
claim (or any section asserting "X is not needed because Y") may be rewritten
ONLY when its stated justification is directly contradicted by a recorded
finding elsewhere in the same issue (see step 4a). This is a narrow carve-out,
not a general addition to the rewrite list above — unrefuted scope prose stays
under "Preserve untouched" below.

**Always clear the `⚠ Superseded` markers you evaluated (ENH-2992):** a
`> ⚠ Superseded — …` line under a directive line is `/ll:refine-issue`'s
annotation (ENH-2995) meaning "this pass's findings refute the line above".
Once you have adjudicated that line against the findings — whether by
rewriting it or by confirming it still holds — the annotation is consumed and
stale, so delete it. This applies to **every** directive line you evaluate, not
only the ones you rewrite, and it applies on the no-op branch too (step 4),
where clearing markers is then the pass's only edit.

This is a narrow, precedented extension of the rewrite scope, not a new
capability: `commands/refine-issue.md`'s **"Bounded marker-removal right"**
already makes a marker the one exception to that skill's "never remove
existing content" rule. Match it rule-for-rule — containment test on the
`⚠ Superseded` prefix, **only marker lines are ever deletable** (the refuted
line and every other line stay untouchable), silent deletion, no tombstone, no
`## CORRECTIONS_MADE` entry. Do not invent a second, differently-shaped marker
lifecycle.

`prepare-issue`'s reconcile rule (the `little_loops.preparation_policy` step
that autodev's preparation runs) routes on marker *presence*, so a marker that
survives a completed reconcile pass re-fires the rule until its cap of 2
contradiction-only reconciles per pass is spent.

**Preserve untouched — never edit, reorder, or delete:**
- `## Summary`, `## Motivation`, `## Current Behavior`, `## Expected Behavior`
- `## Proposed Solution` and any `### Option …` / `### Decision Rationale`
  (human-authored prose and recorded decisions)
- `### Codebase Research Findings`, `### Wiring Phase`, `### Constraints`,
  `## Session Log`, `## Status`
- `## Confidence Check Notes`, except that step 5b moves *resolved* Concern
  bullets out of its last occurrence; unresolved bullets and the rest of the
  section stay untouched.
- `## Scope Boundaries`, except for the narrow contradicted-claim carve-out above
- Every other section not in the rewrite list above.

**Wiring-marker preservation (ENH-3246, by provenance not location):** a
`_Wiring pass added by \`/ll:wire-issue\`:_` or `_Added by
\`/ll:refine-issue\` …:_` block is machine-deposited research reconcile
*reads*, not a directive it may rewrite — this holds even when the block sits
inside a now-rewritable `## Integration Map` subsection (`### Dependent Files
(Callers/Importers)`, `### Similar Patterns`, `### Tests`, `### Documentation`).
Preservation follows the block's provenance marker, not the section it
happens to be nested in. Leave every such block byte-for-byte untouched; rewrite
only the directive bullets around it.

**Source of truth for the rewrite:** the issue's own `### Codebase Research
Findings` and `### Wiring Phase` (and any `### Decision Rationale` that selected
an option). You are reconciling the issue *against itself* — do not go re-research
the codebase (that is `/ll:refine-issue`'s job) and do not verify paths against
the tree (that is `/ll:ready-issue`'s job).

**Every rewritten claim must trace to an existing finding** — with one
exception: a Scope Boundaries claim rewritten into an explicit decision
directive (step 5's branch 2b) is new imperative prose describing an open scope
call, not a factual correction, so it is carved out of the tracing requirement.
Outside that one branch (and the `--from-verify-evidence` source extension
below), do not invent new requirements — if a directive bullet has no supporting
finding, leave it as-is and note it under `## CONCERNS`.

**Source extension — `--from-verify-evidence` (BUG-3695):** an explicit caller
flag, never inferred from frontmatter (same pattern as `/ll:verify-issues
--from-evidence`, BUG-3637). Eligible **only when ALL of**: the flag is passed,
the issue's `verify_verdict` is `DIRECTIVE_DRIFT`, and `verify_evidence` is
nonempty. A missing flag, any other verdict, or absent/empty evidence leaves the
ordinary contract above fully in force. `--check` stays read-only even when
eligible. When eligible:
- Treat each `; `-separated item of `verify_evidence`
  (`<section>: '<specific drift>' -> <entailed correction>`) as an additional
  recorded source alongside the findings. Every added or rewritten item must
  trace to one concrete evidence item and be **entailed by the selected
  mechanism**. If an item would demand a new behavior or option, do not add it —
  note it under `## CONCERNS` (that finding belongs to `PROPOSAL_UNSOUND`, not a
  license to invent requirements).
- You MAY add or rewrite Acceptance Criteria and Implementation Steps, and
  correct *existing* `## Integration Map` entries. **Never add new Integration Map
  entries** under this extension — that would create a new coverage obligation.
- Behavior/API/compatibility drift → an Acceptance Criterion stating the expected
  outcome and how it is verified (a bare "X is covered" is not coverage).
  Fixture/mock invalidation drift → a concrete Implementation Step, not an
  invented AC. Context-only inventory items create no requirement.
- **Target classification wins over the correction tail (BUG-3726).** The
  `-> <correction>` tail of an evidence item is verify's *proposal*, not an
  instruction. Classify each named *target* (per target, not per item or per
  subsection) from the selected mechanism and the issue's recorded findings,
  using the roles `/ll:verify-issues` check B6 defines: observable
  behavior/API/compatibility contract, required fixture/mock update, or
  context-only (an unchanged caller, test or documentation inventory entry with
  no behavior or contract consequence). The classification wins: a tail such as
  "add an AC for each listed … entry" cannot upgrade a context-only target into
  a coverage obligation. Keep the tail as a proposed correction for the targets
  that classify as applicable, still subject to entailment.
- **Anti-pattern.** An inventory listing alone does not entail "file X is
  unchanged" / "test Y passes with no edits" criteria. An explicit
  behavior/compatibility requirement in the selected mechanism *can* entail a
  preservation criterion — do not reject a target on its wording alone. "For
  each listed entry" triggers scrutiny of each target, not automatic rejection
  of every target. Triage filters the evidence source only: it never authorizes
  removing an existing AC or Step, including a legitimate preservation criterion
  whose wording contains "unchanged".
- A refused (context-only) target is reported under `## CONCERNS`, one line per
  target. Other targets in the same evidence item may still justify an AC or
  Step. Refusing evidence never skips a repair justified by the issue's own
  findings.
- All other sections stay preserved; provenance/wiring-marker protections hold.

## Process

### 0. Parse Flags

```bash
FLAGS="${flags:-}"
CHECK_MODE=false
if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi
FROM_VERIFY_EVIDENCE=false
if [[ "$FLAGS" == *"--from-verify-evidence"* ]]; then FROM_VERIFY_EVIDENCE=true; fi
```

### 1. Find Issue File

```bash
ISSUE_FILE=$(ll-issues path "${issue_id}" 2>/dev/null)
```

If no file is found, print `## VERDICT` / `NOT_READY` and stop.

### 2. Arm the one-shot guard

**Immediately** (before any rewrite, and even in `--check` mode's absence),
set `reconcile_attempted: true` in the issue's YAML frontmatter using the Edit
tool. This mirrors `/ll:spike`'s `spike_attempted` convention and arms
the one-shot guard on `prepare-issue`'s reconcile rule, so its readiness-driven
fires (plateau, fresh-below-threshold) run at most once per issue — set it
whether or not any section actually needs rewriting, so a no-op reconcile still
disarms the guard. (The contradiction fire is not gated by this flag; it is
bounded by marker clearing plus its per-pass cap of 2.)

Skip this write only when `CHECK_MODE` is true (check mode never writes).

### 3. Read the issue and its findings

Read the full issue file. Extract:
- The current text of the directive sections: `## Implementation Steps`,
  `## Acceptance Criteria`, and every `## Integration Map` subsection.
- Every bullet under `### Codebase Research Findings` and `### Wiring Phase`.
- The selected option / decision under `### Decision Rationale` (if present) —
  the directive sections must describe the **selected** mechanism, not a
  superseded one.
- Only when `FROM_VERIFY_EVIDENCE` is true: the frontmatter `verify_verdict`
  and `verify_evidence`. The extension (see Contract) is active only if the
  verdict is exactly `DIRECTIVE_DRIFT` and the evidence is nonempty; otherwise
  ignore both fields and proceed under the ordinary contract.

### 3b. Triage evidence targets (`--from-verify-evidence` only)

Skip this step unless the extension is eligible. For each `; `-separated
evidence item, list every target it names (files, tests, docs, behaviors) and
classify **each target** per the Contract ("Target classification wins over the
correction tail"): contract AC, fixture Step, or context-only. Classify from the
selected mechanism and the issue's recorded findings — do not re-research project
code. Then:
- **Context-only** target → refused; record it for `## CONCERNS` as a
  `[refused-evidence]` line. It creates no AC, Step, or Integration Map entry.
  Decide the role *first*: a context-only target is refused (and reported) even
  when an existing AC could be read as covering it — "already covered" is a
  status only for *applicable* targets. An unchanged test or documentation
  inventory entry whose own text states no behavior/contract/fixture consequence
  (e.g. "exercises X and is unaffected", "mentions Y; unaffected") is
  context-only. Never fold a context-only target into a "covered" note.
- **Applicable** target already covered by an existing AC/Step → no duplicate
  addition and no `[refused-evidence]` line (covered is distinct from refused).
- **Applicable** target not yet covered → an *accepted uncovered target*; only
  these participate in the evidence-based stale-section detection of step 4.

All-refused evidence is **not** an early-return condition: continue with step 4
and 4a so ordinary contradiction detection still runs.

### 4. Detect contradictions

For each directive section (`## Implementation Steps`, `## Acceptance
Criteria`, and each `## Integration Map` subsection), compare its claims
against the findings. A section is **stale** when it describes a mechanism,
file, step, or acceptance condition that a later finding corrected,
superseded, or contradicted.

### 4a. Detect contradicted Scope Boundaries claims

For each `## Scope Boundaries` claim with a stated justification ("X is not
needed because Y"), verify Y against `### Codebase Research Findings`,
`### Wiring Phase`, and `## Integration Map` content in the same issue. A
claim is **contradicted** when a recorded finding directly refutes the stated
justification (e.g. "no separate stamp is needed because it delegates to Z"
refuted by a finding that a distinct code path bypasses Z). Classify each
contradiction as:
- **factual mismatch**: the justification is simply wrong (a delegation claim,
  a "does not exist" claim, etc.) — rewrite the claim from the findings
  (step 5, branch 2a).
- **open scope call**: resolving the contradiction requires a decision, not a
  correction (e.g. "should this path also be stamped, or excluded on
  purpose?") — rewrite as an imperative decision directive instead (step 5,
  branch 2b).

When the `--from-verify-evidence` extension is eligible, a directive section
that is **missing an entailed criterion or step** for an *accepted uncovered
target* (step 3b) also counts as stale for this step (a coverage gap, not only a
contradiction). Refused and already-covered targets never make a section stale.

If **no** section is stale, no accepted uncovered target remains, and no Scope
Boundaries claim is contradicted (directives already match findings), this is a
no-op: emit verdict `RECONCILED` with an empty `## CORRECTIONS_MADE` (`None`) and
stop after the session-log append. Any refused targets are still listed under
`## CONCERNS` (one `[refused-evidence]` line each). Do not manufacture edits.

**Except (ENH-2992): still clear the markers.** Before stopping, use the Edit
tool to delete every `> ⚠ Superseded — …` line under a directive line in the
three sections above — you have just adjudicated those lines against the
findings and confirmed they still hold, which consumes the annotation. On this
branch marker removal is the pass's only edit; `## CORRECTIONS_MADE` still
reports `None` (a cleared marker is never a correction). Skipping this leaves
`prepare-issue`'s reconcile rule re-firing on the same marker until its
per-pass cap is spent.

### 5. Rewrite the stale sections in place

Using the Edit tool, rewrite only the stale directive sections so they reflect
the findings. Rules:
- Under the eligible `--from-verify-evidence` extension, additions are placed in
  the existing section: a new AC is a `- [ ]` checkbox that states an observable
  outcome and how it is verified; a new step continues the numbering. Never
  add an Integration Map entry. Do not edit `verify_verdict`/`verify_evidence`
  yourself (the loop's `clear_verify_verdict` removes them before re-verifying).
- Keep the section's heading and overall shape (numbered steps stay numbered;
  AC stays a `- [ ]` checklist; every `## Integration Map` subsection stays a
  bulleted file/pattern list).
- Replace superseded content; do not append a parallel "corrected" block beside
  the stale one (that reproduces the append-only bug this skill exists to fix).
- Preserve any bullets that are still accurate.
- **Skip past wiring-marker blocks.** When rewriting an `## Integration Map`
  subsection, never edit or remove a `_Wiring pass added by
  \`/ll:wire-issue\`:_` or `_Added by \`/ll:refine-issue\` …:_` block nested
  inside it (Contract's wiring-marker preservation rule) — rewrite only the
  directive bullets around it.
- Cite the driving finding inline where it clarifies (e.g. a short parenthetical),
  but keep the section directive and terse — this is not a findings dump.
- **Canonical dependency phrasing.** If a rewritten line asserts that this issue
  is blocked by another issue, phrase it as `Blocked by <ID>` / `Depends on
  <ID>` / `Requires <ID>` (or `blocked on`, `gated on`, `waiting on`,
  `contingent on`, `predicated on`). Paraphrases are invisible to
  `extract_prose_deps()`, so `format-check`'s `prose_dep_drift` gate never fires
  and no `blocked_by` frontmatter edge is written.
- **Clear the `⚠ Superseded` markers (ENH-2992).** When rewriting a marked
  line, extend the Edit's `old_string` span to include the trailing
  `> ⚠ Superseded — …` line so the marker goes with the text it annotated —
  the removal is a byproduct of a rewrite you are already performing. For a
  marked line you *preserved* under the rule above, delete its marker line on
  its own. Either way the deletion is silent: no tombstone, no
  `## CORRECTIONS_MADE` entry, and only the marker line is ever removed.

**Scope Boundaries branch (step 4a contradictions):**
- **2a. Factual mismatch**: rewrite the contradicted claim in place, replacing
  the refuted justification with the corrected one from the findings (e.g.
  "ll-sprint's `_run_issue_with_wall_clock_timeout()` path calls
  `process_issue_inplace()` directly and needs its own stamp"). Trace to the
  finding as usual.
- **2b. Open scope call**: rewrite the claim into an explicit imperative
  decision directive using the same bold-label / imperative-marker shape
  `/ll:decide-issue`'s Provisional Pattern E scans for (e.g. "stamp it or
  exempt it — decide before implementation"), naming the concrete
  alternatives verbatim from the existing text. This branch does not need a
  tracing finding (see Contract carve-out above). Immediately after the
  edit, use the Edit tool to set `decision_needed: true` in the issue's YAML
  frontmatter — without this flag `/ll:decide-issue` never picks the
  directive up.

### 5b. Clear resolved Concerns and stale scores

Runs **only** when step 5 rewrote at least one directive section, and **never**
under `--check`. A no-op run leaves scores, Confidence Check Notes and outcome
flags untouched.

1. **Move resolved Concerns.** In the **last** `## Confidence Check Notes`
   occurrence (the one `ll-issues set-flags` scans), remove each `### Concerns`
   bullet that the rewrite resolved and record it under a `## Resolved Concerns`
   section placed immediately after that Notes section (before `## Session
   Log`), one line each:
   `- [resolved <YYYY-MM-DD> by /ll:reconcile-issue] <original concern text> — <how the rewrite resolved it>`.
   If `## Resolved Concerns` already exists, append to it — never write a second
   heading. Leave earlier Notes occurrences and unresolved Concerns in place.
   Strikethrough in place is not enough: move, don't strike.
2. **Clear the six scores** deterministically:
   `ll-issues set-scores "${issue_id}" --clear`
   (removes `confidence_score`, `outcome_confidence` and the four `score_*`
   keys; consumers read a missing score as "never assessed").
3. Never clear `decision_needed` or other outcome flags — that stays owned by
   `/ll:decide-issue`. The §2b branch that *sets* `decision_needed: true` is
   unaffected.

### 6. Append Session Log entry

```bash
ll-issues append-log "$ISSUE_FILE" /ll:reconcile-issue
```

If `ll-issues` is unavailable, append manually with exactly this format
(backticks required):

```
- `/ll:reconcile-issue` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```

### 7. Check Mode Behavior (--check)

When `CHECK_MODE` is true: run steps 3-4a only, **including the step 3b
evidence-target triage** when the extension is eligible (no frontmatter write, no
rewrite, no score clearing, no session log, **and no marker clearing** — check
mode never writes, so the ENH-2992 clearing rule does not apply here). Then:
- If ≥1 section is stale (including a coverage gap for an accepted uncovered
  target), OR ≥1 Scope Boundaries claim is contradicted (step 4a) — a
  reconcilable plateau exists: print `[ID] reconcile: NEEDED` and `exit 0`.
  Context-only evidence with no other drift is **not** a plateau.
- Otherwise: print `[ID] reconcile: CLEAN` and `exit 1`.

This integrates with FSM `evaluate: type: exit_code` routing.

## Output Format

```markdown
## VERDICT
[RECONCILED|NOT_READY]

## VALIDATED_FILE
[REQUIRED for ALL verdicts — absolute path to the reconciled issue file]

## SECTIONS_REWRITTEN
- Implementation Steps: [rewritten | added | unchanged]
- Acceptance Criteria: [rewritten | added | unchanged]
- Files to Modify: [rewritten | unchanged]
- Dependent Files (Callers/Importers): [rewritten | unchanged]
- Similar Patterns: [rewritten | unchanged]
- Tests: [rewritten | unchanged]
- Documentation: [rewritten | unchanged]
- Scope Boundaries: [rewritten | decision-directive | unchanged]

## CORRECTIONS_MADE
- [reconcile] Rewrote Implementation Steps 1-3 to describe the corrected <X>
  mechanism (per Codebase Research Finding: "<short quote>")
- [reconcile] Updated AC bullet 2 to match the <Y> finding
- [reconcile] Added AC "<outcome + how verified>" for verify_evidence item "<section: drift>" (--from-verify-evidence)
- [reconcile] Added Implementation Step <N> for fixture-invalidation evidence item "<drift>" (--from-verify-evidence)
- [reconcile] Removed superseded "Files to Modify" entry <path> (finding: <…>)
- [reconcile] Rewrote Scope Boundaries claim to match the <Z> finding (factual mismatch)
- [reconcile] Rewrote Scope Boundaries claim into a decision directive: "<X> or
  <Y> — decide before implementation" (decision_needed set to true)
- [Or "None" if nothing was stale]

## CONCERNS
- [Any directive bullet with no supporting finding, left as-is]
- [refused-evidence] <evidence item / section>: <target> — context-only — <reason from selected mechanism>
  (one line per refused target, including on a normal no-op pass; repairs are
  listed under `## CORRECTIONS_MADE`, never here)
- [Or "None"]

## NEXT_STEPS
- [If any section was rewritten: "scores cleared — re-run `/ll:confidence-check [ISSUE_ID]`"; otherwise scores were left as-is]
```

**Correction category** (new with this command):
- `[reconcile]` — a directive section (Implementation Steps / Acceptance
  Criteria / Files to Modify) rewritten in place to match the issue's own
  accumulated research findings, OR a contradicted Scope Boundaries claim
  rewritten (factual correction or decision-directive-ization) per the
  conditional carve-out above.

**IMPORTANT**: The `## VALIDATED_FILE` section is REQUIRED for all verdicts so
automation can confirm the correct file was processed. Never omit it.

---

## Arguments

$ARGUMENTS

- **issue_id** (required): Issue ID to reconcile (e.g., `FEAT-2672`).
- **flags** (optional): `--check` — report the plateau verdict without writing
  (exit 0 if a reconcilable plateau exists, exit 1 if the body is already clean).
  `--from-verify-evidence` — (BUG-3695) additionally treat a persisted
  `DIRECTIVE_DRIFT` `verify_evidence` as a source so entailed Acceptance Criteria
  / Implementation Steps may be added (never Integration Map entries). Only
  `refine-to-ready-issue`'s `reconcile_issue` state passes it.

---

## Examples

```bash
# Reconcile a plateaued issue's directive sections against its findings
/ll:reconcile-issue FEAT-2672

# Check-only: does a reconcilable plateau exist? (for FSM evaluators)
/ll:reconcile-issue FEAT-2672 --check

# Repair a DIRECTIVE_DRIFT verify finding (adds entailed ACs / Steps; used by refine-to-ready-issue)
/ll:reconcile-issue FEAT-2672 --from-verify-evidence
```

---

## Integration

- Called by the `prepare-issue` loop (autodev's preparation step) when the
  preparation policy's reconcile rule (`little_loops.preparation_policy`)
  detects a post-spike Readiness plateau (ENH-2689) or a fresh issue scored
  below the readiness threshold — or, since ENH-2992, a **contradiction**: a
  `⚠ Superseded` marker standing in one of the three directive sections,
  regardless of what the readiness score did. That branch is bounded by this
  command clearing the markers it evaluated (see the Contract) plus a cap of 2
  contradiction-only reconciles per pass. The policy also uses this command as
  a pre-deferral remedy before deferring an issue `low_readiness`.
- User-invocable directly to unstick an issue whose directive sections have
  drifted from its accumulated research.
- Distinct from `/ll:refine-issue` (appends research), `/ll:ready-issue`
  (reconciles issue ↔ codebase accuracy), and `/ll:wire-issue` (adds integration
  touchpoints). This command reconciles the issue **against itself**.
