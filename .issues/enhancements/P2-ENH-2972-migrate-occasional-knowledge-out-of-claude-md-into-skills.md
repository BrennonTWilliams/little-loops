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
confidence_score: 95
outcome_confidence: 71
score_complexity: 16
score_test_coverage: 10
score_ambiguity: 22
score_change_surface: 23
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

- `## CLI Tools` → replaced by a `CLAUDE.md` pointer line naming
  `docs/reference/CLI.md` as the reference and `<cmd> --help` as authoritative
  over any prose. **The durable home already exists** — see the "CLI.md is the
  existing destination" finding below; an earlier revision of this issue
  asserted the section had "no durable home worth building," which is wrong.
  **This migration must also resolve what happens to `ll-verify-cli-docs` —
  see the blocking finding below; dropping the section without touching the
  verifier turns ENH-2970's gate into a silent no-op.**
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
- **Harvest from the cancelled ENH-2023 while the MR table is open — the MR-1
  evaluator list is missing six types, not one.** `NON_LLM_EVALUATOR_TYPES`
  lives at `scripts/little_loops/fsm/validation/_base.py:65` (an earlier
  revision of this issue cited `scripts/little_loops/fsm/validation.py:81` —
  that module is now a package and the path no longer resolves). It is
  *derived* (`frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {llm_structured,
  comparator, contract}`), so it currently resolves to twelve types:
  `action_stall`, `classify`, `convergence`, `diff_stall`, `exit_code`,
  `harbor_scorer`, `mcp_result`, `open_question_stall`, `output_contains`,
  `output_json`, `output_numeric`, `score_stall`. The MR-1 prose list in *both*
  `.claude/CLAUDE.md` and `HARNESS_OPTIMIZATION_GUIDE.md` names only six
  (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `score_stall`,
  `mcp_result`), omitting the other six. **Source the list from
  `NON_LLM_EVALUATOR_TYPES` at rewrite time rather than adding names
  individually** — because the set is derived from
  `EVALUATOR_REQUIRED_FIELDS`, a hand-maintained prose copy re-drifts every
  time an evaluator type is added.
- **`docs/reference/CLI.md` is the existing destination for `## CLI Tools` —
  the section is a duplicate, not an original.** `docs/reference/CLI.md` is a
  3,961-line complete reference covering 48 of the 52 `[project.scripts]`
  entry points, registered in `mkdocs.yml:83` under the nav title
  "CLI Tools", and `CONTRIBUTING.md:423-425` already instructs contributors to
  update *both* it and `.claude/CLAUDE.md` when adding a tool. The resident
  4,723-token section is therefore a second copy maintained in parallel with a
  published reference — which also explains the observed drift. Consequences:
  - The migration is a *pointer swap*, not a content relocation. Nothing needs
    writing; `CLAUDE.md` names `docs/reference/CLI.md`.
  - **Disposition (1) "repoint" becomes the strongest option**, not the weakest
    — see the revised recommendation in the blocking finding below.
  - **Backfill gap (blocking for a repoint)**: four entry points are absent
    from `CLI.md` — `ll-compact-session`, `ll-help`, `ll-verify-cli-docs`,
    `ll-verify-host-map`. A gate repointed before these are added fails on
    landing. Inversely, `mcp-call` is documented in `CLI.md` but not in
    `CLAUDE.md`, so the two surfaces are asymmetric in both directions today.
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
  Also` normativity flip at line 501, plus sourcing the MR-1 evaluator list
  from `NON_LLM_EVALUATOR_TYPES` (six types missing, not one)
- `docs/reference/DEFERRAL_CODES.md` — **new**; destination for the five
  deferral reason codes
- `docs/reference/CLI.md` — under a repoint, backfill the four missing entry
  points (`ll-compact-session`, `ll-help`, `ll-verify-cli-docs`,
  `ll-verify-host-map`) *before* the gate is repointed at it
- `CONTRIBUTING.md:423-425` — the "adding a CLI tool" checklist row reads
  `` `.claude/CLAUDE.md` | One-line entry in the CLI Tools list ``. Removing
  the section leaves this row instructing contributors to edit something that
  no longer exists; it must be updated in the same change. (Not caught by
  `ll-check-links` — it is table prose, not a link.)
- `scripts/little_loops/cli/verify_cli_docs.py` — **blocking, see below**

**Inbound links into the migrated sections** (none of these break loudly;
`ll-check-links` resolves them because the target *file* still exists):

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:501` — `## See Also` entry
- `docs/guides/LOOPS_GUIDE.md:602` (`haiku-gen`), `:636` (MR-12), `:901`
  (meta-loop blockquote) — all three link `[Loop Authoring](../../.claude/CLAUDE.md#loop-authoring)`
- `agents/loop-specialist.md:48` — `evaluator-trivial` remediation cell cites
  "CLAUDE.md § Loop Authoring". **Regenerate the host copies via `ll-adapt`
  rather than hand-editing** — there are *three*, not two:
  `.gemini/agents/loop-specialist.md:45`,
  `.kimi-code/agents/loop-specialist.md:48`, and
  `.codex/agents/loop-specialist.toml:39` (an earlier revision of this issue
  omitted the codex copy).

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

1. **Repoint at `docs/reference/CLI.md`** — retarget the parser at the existing
   published CLI reference and keep the gate operating there. **This is the
   recommended option.** An earlier revision rated it weakest on the premise
   that no prose home would survive; that premise was wrong (see the
   `docs/reference/CLI.md` finding above). Repointing preserves ENH-2970's
   value *and* improves it, moving verification onto the doc that is actually
   published and read, at zero session-token cost. Two real costs, neither a
   blocker:
   - `_BULLET_RE` (`verify_cli_docs.py:33`,
     `^- \`(ll-[a-z0-9-]+)\` - (.*)$`) matches `CLAUDE.md`'s bullet shape and
     will match nothing in `CLI.md`, which uses `### ll-<tool>` headings plus
     prose. This is a parser change, not a constant swap — budget for it.
   - The four-tool backfill listed under Files to Modify must land first, or
     `find_undocumented_entry_points` fails the gate immediately.
2. **Fail loudly on absence** — make a missing section an error-severity drift
   rather than an empty parse, so deleting the section without a deliberate
   decision fails the suite. Cheapest change; forces the choice to be explicit
   at the moment it is made. Worth landing regardless of which option wins, as
   a standalone guard.
3. **Retire deliberately** — delete `verify_cli_docs.py` and its tests along
   with the section, and remove the `ll-doctor --full` registration and the
   `## CLI Tools` bullet describing it. Honest, but discards work landed the
   same week — and now unnecessary, since (1) has a viable target.

Recommended: **(2) then (1)** — land the absence-is-an-error guard first so the
gate cannot rot unnoticed, then backfill `CLI.md` and repoint. (3) is retained
only as a fallback if repointing proves disproportionate to its value.

**Additional string coupling to fix under any option.** Four more sites
hardcode the section name beyond `_SECTION_HEADER`: the module docstring
(`verify_cli_docs.py:1`), the drift detail
`f"{tool} has no CLAUDE.md § CLI Tools entry"` (`:429`), the argparse
description (`:456`), and the success message `"OK: no CLAUDE.md CLI Tools
drift found."` (`:479`). Harmless under (2); under a repoint they emit
actively misleading guidance pointing readers at a section that no longer
holds the surface.

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
3. The `ll-verify-cli-docs` disposition is implemented in the same change that
   touches `## CLI Tools` — recommended path **(2) then (1)**: land
   absence-is-an-error, backfill the four missing tools into
   `docs/reference/CLI.md`, then repoint the parser (including `_BULLET_RE`)
   and the four hardcoded section-name strings at it. A green
   `test_no_error_severity_drift` against a `CLAUDE.md` with no `## CLI Tools`
   section is a *failure* of this criterion, not a pass; after a repoint the
   test must exercise the new target, with a fixture proving a fabricated
   drift in `CLI.md` is caught.
3a. `CONTRIBUTING.md:423-425`'s "adding a CLI tool" checklist reflects the new
   arrangement — no row instructs contributors to update a section that no
   longer exists.
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

   Removing the deferral bullet leaves ~350 — still above the 250 bar.

   **Decided (review, 2026-08-02): trim the status-values bullet to its bare
   enum as well.** The `deferred`-is-non-terminal explanation and the
   `DependencyGraph` / `find_issues_for_graph()` prose are `issue_parser`
   implementation detail, not always-true project facts, and belong with the
   deferral codes in `docs/reference/DEFERRAL_CODES.md`. That removes a further
   ~190 tokens, landing `## Issue File Format` near ~160 and genuinely under
   the bar — so step 7's third clause stands as written and needs no
   restatement. The surviving bullet is the enum itself plus the "do not use
   synonyms" rule.

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
  **Direction settled (review round 2, 2026-08-02)**: repoint at
  `docs/reference/CLI.md` rather than retire; remaining work is the
  `_BULLET_RE` reshape and the four-tool backfill, both scoped above.
- ~~Five live inbound links point *into* the migrated sections~~ **Six** —
  round 2 added `.codex/agents/loop-specialist.toml:39` (a third generated
  host-adapter copy, all regenerated via `ll-adapt`) and
  `CONTRIBUTING.md:423-425` (prose, invisible to `ll-check-links`).
- ~~Implementation Step 7's `## Issue File Format` clause is unreachable~~
  **Resolved** (round 2): the status-values bullet is trimmed to its enum as
  well, landing the section near ~160 tokens. Step 7 stands as written.
- Two predecessors (ENH-2023, ENH-2060) proposed this migration and were
  cancelled with no recorded reason. Now declared via `supersedes:`, with the
  difference argued in Motivation — but the absence of a recorded cancellation
  rationale means the reason they failed is unknown and may still apply.

## Session Log
- `/ll:confidence-check` - 2026-08-02T15:25:29 - `a1358346-8ae5-42ad-a887-83c483295720.jsonl`
- pre-implementation review (round 2) - 2026-08-02 - `docs/reference/CLI.md`
  identified as the existing destination (flips the `ll-verify-cli-docs`
  disposition from retire to repoint, + four-tool backfill and `_BULLET_RE`
  reshape scoped); `CONTRIBUTING.md:423-425` and
  `.codex/agents/loop-specialist.toml:39` added as missed inbound refs;
  `NON_LLM_EVALUATOR_TYPES` path corrected to
  `fsm/validation/_base.py:65` and the MR-1 gap widened from one type to six;
  four extra hardcoded section-name strings in `verify_cli_docs.py` recorded;
  step 7's `## Issue File Format` clause resolved by also trimming the
  status-values bullet. Baseline table re-confirmed against live
  `ll-doctor --trim` (all nine rows match exactly).
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
