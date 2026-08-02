---
id: ENH-2972
title: Migrate occasional-knowledge sections out of .claude/CLAUDE.md into skills
type: ENH
priority: P2
status: open
captured_at: '2026-08-01T00:00:00Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2970
supersedes:
- ENH-2023
- ENH-2060
testable: true
program_design_not_applicable: true
labels:
- context
- claude-md
- skills
blocked_by:
- ENH-2970
decision_needed: false
confidence_score: 90
outcome_confidence: 66
score_complexity: 18
score_test_coverage: 8
score_ambiguity: 15
score_change_surface: 25
---

# ENH-2972: Migrate occasional-knowledge sections out of `.claude/CLAUDE.md` into skills

## Summary

`.claude/CLAUDE.md` is loaded in full on every session start and currently
costs ~10,100 estimated tokens across the nine H2 sections above the review
bar. Three sections account for ~8,000 of that (79%), and all three are
reference detail consumed by one or two specific
consumers — not always-true project facts. Move them behind skill/guide files
that `CLAUDE.md` points at, so the cost is paid on use rather than on every
turn of every session.

## Current Behavior

`ll-doctor --trim` against this repo reports the resident cost per H2 section
(re-measured 2026-08-02; the earlier column is kept to show drift):

| Section | Est. tokens | Was (2026-08-01) | Actual consumer |
|---|---|---|---|
| `## CLI Tools` | 4,723 | 3,695 | Ad-hoc; a `--help` away |
| `## Loop Authoring` | 1,939 | 1,939 | Loop authoring/validation work only |
| `## Issue File Format` | 1,360 | 1,268 | `autodev.yaml`, `rn-implement.yaml`, issue skills |
| `## Key Directories` | 505 | 426 | Occasional orientation |
| `## Commands & Skills` | 407 | 407 | Duplicates the host's own catalog listing |
| `## Automation: Scratch Pad` | 328 | — | Automation contexts only |
| `## Development` | 320 | — | Genuinely always-true |
| `## Project Configuration` | 263 | — | Genuinely always-true |
| `## Distribution` | 258 | — | Genuinely always-true |

**The drift column is itself part of the case.** `## CLI Tools` grew 1,028
tokens (+28%) in a single day — the additions came from ENH-2970's own
verification pass, which documented more of the surface rather than less.
A section whose accuracy gate makes it grow is a section that will keep
growing until it is moved. Re-capture this baseline at implementation time
rather than trusting these numbers.

Detail on the three large sections:

- **`## CLI Tools`** — a prose enumeration of every `ll-*` entry point with
  full flag documentation. Every name in it is declared in
  `scripts/pyproject.toml [project.scripts]` and every flag is available from
  `<cmd> --help`. It has already drifted far enough that it contains a
  correction to itself ("**Not yet shipped, despite prior entries here
  claiming otherwise**"), which is the observable symptom of a section too
  large for anyone to verify on edit. ENH-2970 covers verifying the surface;
  this issue covers not paying for it every session.
- **`## Loop Authoring`** — the MR-1..MR-14 rule table. Its own text already
  names `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as "the source of truth
  this table summarizes", so the resident copy is a duplicate of a file that
  is one Read away.
- **`## Issue File Format`** — the status enum (always-true, small) plus the
  deferral-discriminator machinery: `blocked_by_unmet`, `remediation_stalled`,
  `low_readiness`, `oversized_atomic`, `readiness_stagnated`, and the
  BUG-2734 / BUG-2803 / FEAT-2751 remedy chains. The enum is always-true; the
  remedy chains are autodev-internal state-machine detail needed by one loop.

## Expected Behavior

`.claude/CLAUDE.md` retains only what is true every session and not derivable
from the repo: what the project is, the local-editable blast radius, the
testing/CI policy, code style, the host-CLI abstraction rule, the status enum,
and pointers to where the detail lives. Everything else loads on demand.

Target: `## CLI Tools`, `## Loop Authoring`, and the deferral-discriminator
half of `## Issue File Format` reduced to a pointer line each, with the detail
reachable from a skill or existing guide.

## Motivation

Two independent costs, both compounding:

1. **Residency.** ~6,900 tokens injected into every session regardless of
   task. On a codebase-navigation session none of it is read; the cost is
   paid anyway.
2. **Unverifiability.** A section large enough that nobody re-reads it on
   edit drifts silently. The self-correcting paragraph in `## CLI Tools` is
   direct evidence this already happened, and its failure mode is worse than
   absence: a confidently-wrong CLI surface sends every reader down a dead
   end. Smaller, on-demand files are ones a reader actually checks.

The placement rule this follows: always-true and short → `CLAUDE.md`; long or
occasional → a skill the `CLAUDE.md` points at. Same instruction, but one
costs every turn and the other costs nothing until used.

**Why this attempt, after two cancelled ones.** ENH-2023 (extract
loop-authoring standards into `.ll/standards.md`) and ENH-2060 (split
`CLAUDE.md` into a co-located hierarchy) both proposed a version of this
migration and were both cancelled with no recorded reason. This issue
`supersedes:` them. Two things differ now: (1) `ll-doctor --trim` exists, so
the cost per section is measured rather than asserted, and the change has a
falsifiable target instead of a stylistic one; (2) the scope is three named
sections with named destinations, not a whole-file restructure — each lands
independently and each is revertible on its own. Neither predecessor
proposed inventing a new file layout (`.ll/standards.md`, nested
`CLAUDE.md`s); this one reuses the `docs/guides/*.md` pointer pattern that
`CLAUDE.md` already uses twice.

## Proposed Solution

Three migrations, independently landable.

**Option A — skill-per-domain (recommended).** Each migrated section becomes
(or joins) a skill whose description is a one-line trigger:

> **Selected:** Option A — reuses the existing docs/guides pointer pattern; Option B has no precedent for a reference-only skill in this codebase.

- `## CLI Tools` → drop entirely, replaced by a `CLAUDE.md` line stating that
  `ll-*` entry points are declared in `scripts/pyproject.toml` and documented
  by `--help`, and that `--help` is authoritative over any prose list. This
  section has no durable home worth building: its content is generated by the
  code it describes. **This migration must also resolve what happens to
  `ll-verify-cli-docs` — see the blocking finding below; dropping the section
  without touching the verifier turns ENH-2970's gate into a silent no-op.**
- `## Loop Authoring` → the MR table already lives in
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`. Reduce the `CLAUDE.md` section
  to the three shape rules (~150 tokens) plus a pointer, since the shape rules
  are the part an author needs *before* knowing they need the guide.
- Deferral discriminators → **`docs/reference/DEFERRAL_CODES.md`** (decided
  2026-08-02, closing the open destination question). Rationale: the
  "companion file next to `autodev.yaml`" option has no precedent —
  `scripts/little_loops/loops/` contains no sibling `.md` docs — whereas
  `docs/reference/` already holds exactly this kind of lookup table
  (`API.md`, `HOST_COMPATIBILITY.md`, `schemas/`). The content is a code
  glossary, not loop-authoring guidance, so it does not belong in
  `docs/guides/`. `ll-issues deferred-triage` is the runtime consumer and
  the natural place to reference it from. The new file is the first
  single-index home for all five codes, which today exist only as inline
  comments at each emission site.

**Option B — single `reference` skill.** One skill holding all three, split
across companion files. Cheaper to build, but a coarser trigger: the model
loads loop rules when it wanted issue-status detail.

**Recommended**: Option A — the consumers are genuinely different, and
Option B's single trigger reintroduces over-fetching at the skill layer.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- ~~**Blocking gap for the Loop Authoring migration**: `HARNESS_OPTIMIZATION_GUIDE.md`
  does not yet cover three rows that exist only in `.claude/CLAUDE.md`'s MR table
  today — `haiku-gen`, `capture-reachability`, and `session-mode-eval` have no
  counterpart anywhere in the guide (confirmed via zero-match grep for each
  term).~~ **Stale — resolved as of 2026-08-02.** All three terms now resolve in
  `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`, as do `MR-12`, `MR-13`, `MR-14`,
  `terminal-action-ok`, and `policy-table`. Rule-ID diff between the two files
  is now empty in both directions (`MR-1`…`MR-14` in each). **Implementation
  Step 2's precondition passes as written** — still run the diff, but expect it
  to succeed rather than to block.
- **The guide's `## See Also` asserts the opposite normativity direction, and
  that must be flipped in the same change.** `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:501`
  currently reads "`.claude/CLAUDE.md § Loop Authoring` — **the normative**
  compact rule table this guide's rationale expands on", while
  `.claude/CLAUDE.md`'s own Loop Authoring prose calls the guide "the source of
  truth this table summarizes". Today that is merely circular; after this
  migration it is actively wrong, since the surviving `CLAUDE.md` text will be
  three shape rules and a pointer. Rewrite the See Also entry so the guide is
  normative and `CLAUDE.md` is the pointer. (An earlier revision of this issue
  reported the entry as saying "the normative MR-1…MR-11 rules" — that text no
  longer exists; the problem is the direction, not the range.)
- **Harvest from the cancelled ENH-2023 while the MR table is open**:
  `action_stall` is a valid MR-1-satisfying evaluator type per
  `scripts/little_loops/fsm/validation.py:81` (`NON_LLM_EVALUATOR_TYPES`) and
  per the MR-1 error message itself, but it is missing from the MR-1 prose list
  in *both* `.claude/CLAUDE.md` and `HARNESS_OPTIMIZATION_GUIDE.md`. Source the
  list from `NON_LLM_EVALUATOR_TYPES` when rewriting either.
- **"Skill" is not the established destination pattern — a `docs/guides/*.md`
  file already is.** No `SKILL.md` in this codebase is purely reference/lookup
  content; every companion-file precedent (ENH-494, `scripts/tests/test_enh494_skill_companions.py`)
  is intra-skill (a companion file split out of an existing *operational*
  skill, e.g. `skills/confidence-check/rubric.md`), not a standalone
  reference-only skill. The pattern `.claude/CLAUDE.md` already uses for
  exactly this kind of migration is a doc guide, not a skill: `## Loop
  Authoring` already points at `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
  (`.claude/CLAUDE.md:165-169`, phrased "the source of truth this table
  summarizes") and `## Automation: Scratch Pad`-adjacent content points at
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (`.claude/CLAUDE.md:204`). Two
  pointer-phrasing variants coexist in `CLAUDE.md` today, both current: a
  full-sentence "source of truth" framing (lines 165-169, 204) and a bare
  bullet/parenthetical with no justification prose (`## Important Files`
  block, lines 217-220; line 227). This is relevant to the Option A vs B
  choice above — it doesn't resolve it, since Option A's "skill" framing and
  the observed "guide" convention aren't the same destination type, but
  whichever is chosen should follow one of these two existing phrasings
  rather than inventing a third.

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected: Option A — skill-per-domain**, with the caveat that its concrete
destinations should follow the codebase's actual established pattern
(`docs/guides/*.md` pointers) rather than its own "skill" framing where the
two diverge — the `## Loop Authoring` migration already does this correctly
(pointing at `HARNESS_OPTIMIZATION_GUIDE.md`, which exists today).

Two independent `ll:codebase-pattern-finder` agents searched the repo for
precedent on each option:

| Dimension | Option A | Option B |
|---|---:|---:|
| Consistency | 2 | 0 |
| Simplicity | 2 | 1 |
| Testability | 2 | 1 |
| Risk | 2 | 1 |
| **Total** | **8/12** | **3/12** |

**Key evidence:**
- Option A's `docs/guides` pointer half is a direct rerun of the existing
  Loop Authoring precedent (`.claude/CLAUDE.md` already points at
  `HARNESS_OPTIMIZATION_GUIDE.md` and `AUTOMATIC_HARNESSING_GUIDE.md` this
  way) — reuse_score 2.
- Option A's "companion file next to `autodev.yaml`" piece for deferral
  discriminators has no precedent (`scripts/little_loops/loops/` has no
  sibling `.md` docs today) — the one weak spot in an otherwise
  well-precedented option.
- Option B has no precedent anywhere: no `SKILL.md` in this repo is
  purely reference/lookup content with no operational steps, and every
  skill `description:` observed is a single-intent trigger — a single
  "reference" skill spanning three unrelated topics would either over-fire
  or force the model to guess, reintroducing the over-fetching the issue
  exists to eliminate — reuse_score 0.

## Program Design

Not applicable — this is content relocation, not new behavior. No new module,
no new data structure. The one design decision (Option A vs B) is resolved
above.

## Integration Map

### Files to Modify

- `.claude/CLAUDE.md` — remove three sections, add pointer lines
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — rule-ID coverage now confirmed
  complete (see Codebase Research Findings); the edit needed is the `## See
  Also` normativity flip at line 501, plus the `action_stall` addition to the
  MR-1 evaluator list
- `docs/reference/DEFERRAL_CODES.md` — **new**; destination for the five
  deferral reason codes
- `scripts/little_loops/cli/verify_cli_docs.py` — **blocking, see below**

**Inbound links into the migrated sections** (none of these break loudly;
`ll-check-links` resolves them because the target *file* still exists):

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:501` — `## See Also` entry
- `docs/guides/LOOPS_GUIDE.md:602` (`haiku-gen`), `:636` (MR-12), `:901`
  (meta-loop blockquote) — all three link `[Loop Authoring](../../.claude/CLAUDE.md#loop-authoring)`
- `agents/loop-specialist.md:48` — `evaluator-trivial` remediation cell cites
  "CLAUDE.md § Loop Authoring". **Regenerate the host copies via `ll-adapt`
  rather than hand-editing** `.gemini/agents/loop-specialist.md:45` and
  `.kimi-code/agents/loop-specialist.md:48`.

### Dependent Files

- `scripts/tests/test_enh494_skill_companions.py` — enforces the 500-line
  SKILL.md cap; any new skill must respect it
- `scripts/little_loops/cli/doctor_trim.py` — the measurement; re-run
  `ll-doctor --trim` to confirm the reduction

### Blocking finding: dropping `## CLI Tools` silently retires ENH-2970's gate

`parse_cli_section` (`scripts/little_loops/cli/verify_cli_docs.py:213-217`)
locates its section by exact header match on `_SECTION_HEADER = "## CLI Tools"`
and **returns `([], [])` when the header is absent** — the same early return it
uses for a missing file. Downstream of an empty claim list:

- `verify_claims([])` produces no drifts → `_run` computes `exit_code = 0`.
- `scripts/tests/test_verify_cli_docs.py::TestRunOnRealClaudeMd::test_no_error_severity_drift`
  asserts `errors == []` and `exit_code == 0` — both hold **vacuously**. The
  test stays green while checking nothing.
- `find_undocumented_entry_points([])` emits one WARN per entry point (~40),
  and warns do not affect the exit code, so nothing surfaces the change.

Net effect: the verification gate that landed under ENH-2970 becomes a
permanent no-op the moment this migration lands, with no failing test and no
non-zero exit to signal it. The issue must pick one and record it before
implementation:

1. **Repoint** — set `_SECTION_HEADER` to the migrated section's new heading
   and keep the gate operating on the relocated prose. Preserves ENH-2970's
   value, but only works if the CLI surface keeps a prose home somewhere,
   which contradicts "drop entirely".
2. **Fail loudly on absence** — make a missing section an error-severity drift
   rather than an empty parse, so deleting the section without a deliberate
   decision fails the suite. Cheapest change; forces the choice to be explicit
   at the moment it is made.
3. **Retire deliberately** — delete `verify_cli_docs.py` and its tests along
   with the section, and remove the `ll-doctor --full` registration and the
   `## CLI Tools` bullet describing it. Honest, but discards work landed the
   same week.

Recommended: **(2) then (3)** — land the absence-is-an-error change first so
the gate cannot rot unnoticed, then make the retirement an explicit,
reviewable commit if the section is in fact dropped.

### Conventions in Force

- A `SKILL.md` over 500 lines splits into a companion file — evidence:
  `ll-verify-skills`, `scripts/tests/test_enh494_skill_companions.py:71-81`
- Skill descriptions are budgeted in aggregate — evidence:
  `ll-verify-skill-budget`, `doc_counts.check_skill_budget()`

### Tests

- No behavioral test applies directly. The measurable gate is
  `ll-doctor --trim` reporting the target sections below the review bar.
- **Add a resident-cost regression test.** The `## CLI Tools` growth measured
  above (+1,028 tokens in one day) is the failure mode this issue exists to
  stop, and nothing currently catches it. A test that asserts each
  `.claude/CLAUDE.md` H2 section stays under a recorded per-section ceiling —
  reusing `doctor_trim._memory_components()` so there is no second token
  estimator — makes regrowth fail the suite instead of accumulating silently.
  This also answers the "no automated drift gate exists for `## Loop
  Authoring` or `## Issue File Format`" finding below: it does not verify
  pointer *accuracy*, but it does bound pointer *inflation*, which is the
  observed failure. Per the project CI policy this is a pytest test, not a
  workflow file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current section locations in `.claude/CLAUDE.md`**: `## Loop Authoring`
  lines 151-204 (contains the MR-1..MR-14 table), `## Issue File Format`
  lines 206-213, `## CLI Tools` starting line 222.
- **The 250-token review bar is a real, programmatic constant**, not just
  issue prose: `_SECTION_REVIEW_TOKENS = 250` in
  `scripts/little_loops/cli/doctor_trim.py`. For a memory-file H2 section,
  `_memory_components()` verdicts `"review"` when `tokens >= 250`, else
  `"keep"` — there is no separate `"trim"` verdict for `CLAUDE.md` sections
  (unlike catalog/skill entries, which can get `"trim"` on zero invocations).
  So Implementation Step 5's target state is the tool reporting `verdict ==
  "keep"` for the migrated sections, not a distinct "passed" state.
  Additionally, memory sections get no usage signal at all — `invocations`
  is always `None` for them, since `_usage_counts()` only reads
  `skill_events` from `.ll/history.db`, which has no per-`CLAUDE.md`-section
  granularity.
- **No automated drift gate exists for `## Loop Authoring` or
  `## Issue File Format` today** — only `## CLI Tools` has one
  (`scripts/little_loops/cli/verify_cli_docs.py`, gated by
  `scripts/tests/test_verify_cli_docs.py::TestRunOnRealClaudeMd::test_no_error_severity_drift`,
  which runs directly against the real `.claude/CLAUDE.md`). After migrating
  the other two sections to pointer lines, nothing will catch future drift
  between the pointer and its target beyond a manual `ll-doctor --trim` rerun
  — a risk this issue's own `## Impact` section already names ("the failure
  mode is deleting something the model genuinely needed... and not
  noticing").
- **Deferral-discriminator codes are already documented, but only inline at
  each emission site, with no centralized glossary**: `blocked_by_unmet` and
  `remediation_stalled` in `scripts/little_loops/loops/rn-implement.yaml`
  (~lines 1348-1357, adjacent `REASON=`/`REASON_CODE=` strings);
  `gate_blocked` (~line 853), `decision_unresolved` (~line 690),
  `oversized_atomic` (~lines 1572-1661), and `readiness_stagnated` (~lines
  1755-1916) in `scripts/little_loops/loops/autodev.yaml`, each preceded by a
  multi-line comment block. `.claude/CLAUDE.md`'s `## Issue File Format`
  deferral paragraph is currently the only place all five codes are
  enumerated together with a one-line meaning each — moving that summary out
  means either building the companion glossary the Proposed Solution already
  suggests, or accepting there is no single cross-code index left anywhere.

## Implementation Steps

1. `ll-doctor --trim` output records the pre-change per-section baseline,
   re-measured at implementation time (the table above is a snapshot, not a
   contract).
2. `HARNESS_OPTIMIZATION_GUIDE.md` covers every MR rule currently in the
   `CLAUDE.md` table — verified by diffing rule IDs, not assumed. Expected to
   pass on the current tree; treat a failure as new drift, not as the
   previously-reported gap.
3. The `ll-verify-cli-docs` disposition (repoint / fail-on-absence / retire) is
   decided and implemented in the same change that touches `## CLI Tools`. A
   green `test_no_error_severity_drift` against a `CLAUDE.md` with no
   `## CLI Tools` section is a *failure* of this criterion, not a pass.
4. Every inbound link listed under Files to Modify resolves to the content it
   names, and `HARNESS_OPTIMIZATION_GUIDE.md`'s `## See Also` no longer calls
   `CLAUDE.md` normative. Host-adapter agent copies are regenerated, not
   hand-edited.
5. Each migrated section is reachable from its new home by a reader who
   started from `CLAUDE.md` alone.
6. `python -m pytest scripts/tests/` passes, including the skill-size and
   skill-budget gates, and `ll-check-links` passes.
7. `ll-doctor --trim` shows: no `## CLI Tools` row at all (the section is
   deleted, so it does not appear in the report — "below the bar" is not the
   right assertion for it), `## Loop Authoring` below the 250-token review
   bar, and `## Issue File Format` below the bar.

   **Note on step 7's third clause — it is not reachable by removing the
   deferral bullet alone.** `ll-doctor --trim` verdicts whole H2 sections, and
   the deferral discriminator is only part of `## Issue File Format`. Measured
   split of that section's 1,360 tokens:

   | Bullet | Est. tokens |
   |---|---:|
   | Deferral discriminator | 1,005 |
   | Status values | 196 |
   | Supersession | 117 |
   | filename pattern / types / priorities | 34 |

   Removing the deferral bullet leaves ~350 — still above the 250 bar. Either
   the status-values bullet is also trimmed to its enum (dropping the
   `deferred`-is-non-terminal and `DependencyGraph` prose, which is
   `issue_parser` detail rather than an always-true project fact), or this
   clause is restated as a per-bullet target rather than a section verdict.
   Decide which at implementation time; do not leave step 7 asserting an
   outcome the tool cannot report.

## Scope Boundaries

- **In scope**: relocating existing content, adding pointer lines.
- **Out of scope**: correcting the *accuracy* of the CLI surface — that is
  ENH-2970. This issue moves the section; ENH-2970 decides what is true.
  If ENH-2970's resolution is to delete the prose list, these two converge
  and should be sequenced with ENH-2970 first.

  > **Update (`/ll:refine-issue`, additive)**: ENH-2970 is now `status: done`.
  > Its resolution was to add a verifier (`ll-verify-cli-docs`, backed by
  > `scripts/little_loops/cli/verify_cli_docs.py`, gated by
  > `scripts/tests/test_verify_cli_docs.py::TestRunOnRealClaudeMd::test_no_error_severity_drift`)
  > that checks the `## CLI Tools` prose against real `--help` output — not a
  > deletion of the prose list. The convergence condition above therefore does
  > not apply: this issue's `blocked_by: ENH-2970` edge is satisfied, and the
  > CLI Tools migration can proceed on its own schedule, same as Loop
  > Authoring and Issue File Format.
- **Out of scope**: the user-level `~/.claude/CLAUDE.md`.

## Impact

- **Effort**: Medium — mechanical relocation, but requires confirming the
  guide's coverage is complete before deleting the resident copy.
- **Risk**: Medium — the failure mode is deleting something the model
  genuinely needed every session and not noticing, since nothing fails
  loudly. Mitigate by migrating one section at a time.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- ~~`blocked_by: ENH-2970` is still `status: open` — the CLI Tools migration's
  final shape depended on ENH-2970's resolution per this issue's own Scope
  Boundaries.~~ **Resolved** (`/ll:refine-issue`, 2026-08-01): ENH-2970 is now
  `status: done`, resolved via a verifier rather than deletion — see the Scope
  Boundaries update note. The `blocked_by` edge is satisfied for all three
  migrations, which can now proceed independently.
- ~~The deferral-discriminator destination is undecided at the file level~~
  **Resolved** (review, 2026-08-02): `docs/reference/DEFERRAL_CODES.md`, with
  rationale in Proposed Solution.
- ~~No automated test asserts the token-reduction outcome~~ **Addressed**
  (review, 2026-08-02): a per-section resident-cost ceiling test is now in
  scope — see `### Tests`.

### Concerns added by review (2026-08-02)

- **Blocking**: dropping `## CLI Tools` turns `ll-verify-cli-docs` into a
  vacuously-passing no-op. Disposition must be decided in the same change —
  see the Integration Map's blocking finding and Implementation Step 3.
- Five live inbound links point *into* the migrated sections and resolve
  silently after the content leaves; two are generated host-adapter copies
  that must be regenerated via `ll-adapt`.
- Implementation Step 7's `## Issue File Format` clause is unreachable by the
  planned edit alone — the section stays ~350 tokens after the deferral bullet
  is removed. Needs either a wider trim or a restated criterion.
- Two predecessors (ENH-2023, ENH-2060) proposed this migration and were
  cancelled with no recorded reason. Now declared via `supersedes:`, with the
  difference argued in Motivation — but the absence of a recorded cancellation
  rationale means the reason they failed is unknown and may still apply.

## Session Log
- pre-implementation review - 2026-08-02 - baseline re-measured; MR-coverage
  gap found stale; `ll-verify-cli-docs` no-op finding added; inbound links
  mapped; deferral destination decided; `supersedes:` recorded
- `/ll:decide-issue` - 2026-08-02T04:55:31 - `eed617dd-9d98-46a5-a9cc-9c89ee0c8db9.jsonl`
- `/ll:refine-issue` - 2026-08-02T04:52:10 - `476fce3f-841f-433c-abf2-0393d9faea2d.jsonl`
- `/ll:confidence-check` - 2026-08-02T02:53:00 - `47f63775-3826-4312-a632-2c36b5b799e8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-01T17:54:54 - `0f6b2c2e-0cc5-4e86-8aeb-792632143f0e.jsonl`
- `/ll:capture-issue` - 2026-08-01

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
