---
id: ENH-3045
title: Replacement parity + negative-claim doctrine for /ll:wire-issue and /ll:refine-issue
type: ENH
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
completed_at: '2026-08-05T01:59:31Z'
relates_to:
- FEAT-3048
- FEAT-2942
- ENH-3050
- ENH-3049
labels:
- skills
- issues
- quality
testable: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3045: Replacement parity + negative-claim doctrine for wire/refine

## Summary

Two related doctrine changes to `/ll:wire-issue` and `/ll:refine-issue`, both instances of the
same blind spot — **the passes examine the codebase and the issue, but never the artifact the
issue is about to replace, and never justify a negative finding**:

1. **Replacement parity** — when an issue rewrites, deletes, or delegates away an existing
   artifact, require a `### Behavior Parity` subsection enumerating each behavior of the old
   artifact with a disposition (preserved / changed / dropped + why).
2. **Negative-claim doctrine** — a conclusion of the form "no existing implementation exists"
   must name what was searched, and must search by *capability*, not by algorithm name.
3. **Claim grounding** — the same doctrine applied to *positive* claims about existing code: an
   assertion that a symbol is reusable, unchanged, or behaves a certain way must quote the line
   that makes it true, not merely name the symbol. `FEAT-3048` is the mechanical sibling — it
   verifies that a cited symbol *exists*; this half covers whether the claim *about* it holds,
   which is not mechanically checkable and so belongs with the doctrine.

## Current Behavior

**Parity.** Nothing in either skill reads the artifact being replaced.
`skills/wire-issue/SKILL.md` Phase 5 diffs agent findings against `EXISTING_WIRING` extracted
from the *issue*; Phase 8c is literally a "Preservation Rule" protecting text already present.
`commands/refine-issue.md` researches the codebase for gaps but has no replaced-artifact step.

Measured cost on FEAT-2942, which deletes a 362-line skill — three defects, all the same shape,
all behaviors that existed only in the artifact being deleted and were never transcribed:

- Scoring corpus silently narrows from **title + `## Summary`** (`skills/link-epics/SKILL.md`)
  to **title-only** (`IssueInfo` has no summary field; `find_similar`/`batch_similarity` score
  titles only) — a real signal regression nothing flagged.
- The HIGH/MEDIUM/LOW **tier boundaries (0.7/0.4)** appear nowhere in the issue, though
  `EpicProposal.tier` is declared.
- The definition of **"orphan"** — the term the whole feature turns on — exists only in the
  skill being deleted.

**Negative claims.** `/ll:wire-issue` wrote into FEAT-2942:

> No union-find/disjoint-set implementation exists anywhere in `scripts/little_loops/` today
> (confirmed by grep) — `synthesize_clusters()` is new code.

Literally true, materially wrong: it grepped for the **algorithm name**. `batch_similarity()`
in `scripts/little_loops/cli/issues/find_similar.py` already performs the exact O(n²) pairwise
`calculate_word_overlap` scan that produces the edge list `synthesize_clusters()` needs. A grep
for *callers of the shared primitive* would have surfaced it immediately.

## Expected Behavior

**Parity.** When an issue names an existing file it will rewrite/delete/delegate away, wire and
refine emit a `### Behavior Parity` subsection under Integration Map:

```markdown
### Behavior Parity

| Artifact | Behavior | Disposition | Notes |
|---|---|---|---|
| `skills/link-epics/SKILL.md` | Scores title + `## Summary` | CHANGED | CLI scores title only — accepted regression? |
| `skills/link-epics/SKILL.md` | Tiers HIGH/MED/LOW at 0.7/0.4 | DROPPED | not carried into CLI spec |
| `skills/link-epics/SKILL.md` | Orphan = open BUG/FEAT/ENH, no `parent:` | PRESERVED | must be restated in the CLI spec |
```

**The heading is exactly `### Behavior Parity` — one section per issue, with the replaced
artifact carried as a table column, never as heading text.** Two reasons, both binding on
implementation:

1. `_heading_bodies()` (`issue_parser.py:686`) matches
   `rf"^(#{{2,3}})\s+{re.escape(heading)}\s*$"` — anchored and exact. A per-artifact heading
   (`### Behavior Parity — skills/link-epics/SKILL.md`) would not match, so the detection in
   Program Design below would report the section absent on every issue that has one. Keeping
   the heading fixed means the existing helper works unmodified and no parser change is needed.
2. An issue that replaces several artifacts gets one table, not N sibling headings.

**Negative claims.** Before concluding "no existing implementation," the agent must search by
capability — the input/output shape, and the callers of the shared primitive the new code
would call — and the resulting claim must state what was searched.

**Claim grounding.** A `### Program Design` or `### Call Path` line asserting that an existing
symbol is reusable, unchanged, or behaves a given way must quote the specific line that makes
the claim true. Naming the symbol is not grounding — an anchor that *resolves* is what
`program_design_nonspecific` already checks, and resolution says nothing about the claim.

This issue's own Call Path was the worked example: it stated that `_heading_bodies(content,
"Behavior Parity")` is "reusable to confirm no `### Behavior Parity` section exists." The symbol
resolves, so every gate passed it — refine, wire, and confidence-check (100/82). Its body
(`issue_parser.py:686`) is `rf"^(#{{2,3}})\s+{re.escape(heading)}\s*$"` — anchored and exact, so
it could not match the per-artifact heading the first draft of this issue prescribed in Expected
Behavior (`### Behavior Parity — skills/link-epics/SKILL.md`). One quoted line would have caught
it; instead the contradiction survived three passes and a human review found it.

**Resolved above** by fixing the heading to bare `### Behavior Parity`. The anecdote is retained
because it is the motivating evidence for this bullet, not an open defect.

## Motivation

Parity alone accounts for 3 of the 7 defects found reviewing FEAT-2942 after three passes; the
negative-claim fix accounts for a 4th. Both are prompt-level changes to skills that already do
the surrounding research — very high ratio of caught defects to effort. They combine because
they are the same instruction to the same two skills: *look at what you are replacing, and say
what you looked for.*

## Proposed Solution

- **Wire** (`skills/wire-issue/SKILL.md`): add a replaced-artifact extraction step alongside
  Phase 3's `EXISTING_WIRING`; emit the parity table in Phase 8a; add the capability-search
  requirement to the Agent 1 and Agent 3 prompts (Phase 4).
- **Refine** (`commands/refine-issue.md`): same parity requirement in its Integration Map
  emission (Step 5a).
- **Detection** (required, same change): a `missing_behavior_parity` gap kind in
  `check_format_gaps()` — issue cites a file it will rewrite, that file exists, no
  `### Behavior Parity` section. Follows the `ENH-2946` precedent for adding gap kinds and
  makes the doctrine enforceable rather than advisory. **Not optional**: `ENH-3047` Phase 1.6
  consumes this gap kind by name, and the evidence of this issue's own three-pass history is
  that prose doctrine in these skills does not hold on its own. The predicate is fully
  specified in **Program Design § Decision Rules** below — implement it as written; do not
  re-derive a keyword list or proximity rule at implementation time.
- **Claim grounding**: extend the same Agent 1/3 prompt change to require a quoted line behind
  any positive claim about existing code, and require refine's Program Design lines to carry
  the quote rather than only a resolving anchor.

`/ll:wire-issue` is a skill and `/ll:refine-issue` is a command — both markdown, but confirm
the wire skill's line budget (`ll-verify-skills` caps `SKILL.md` at 500 lines; it is currently
455) and extract to a companion file per the ENH-494 pattern if the addition overflows.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` — Phase 3/4/8a changes (watch the 500-line cap; 455 today)
- `commands/refine-issue.md` — Integration Map emission step
- `scripts/little_loops/issue_parser.py` + `cli/issues/format_check.py` — `missing_behavior_parity`
  gap kind (required; `ENH-3047` depends on it by name)
- `scripts/tests/test_wire_issue_static_layer.py` and
  `scripts/tests/test_refine_issue_command.py` — the existing structural test homes for these
  two artifacts; extend rather than adding a new test module
- `docs/reference/COMMANDS.md` — updated descriptions

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:139` — top-level `format-check` subcommand
  help text repeats the same gap-kind enumeration (`missing/renamed/.../ambiguous_file_ref`)
  as `format_check.py`'s own `--help` string; a third copy, easy to miss [Agent 1 finding]
- `.gemini/skills/wire-issue/SKILL.md` and `.kimi-code/skills/wire-issue/SKILL.md` — host
  mirrors of `skills/wire-issue/SKILL.md`; `test_wire_issue_skill_mirror_matches_source`
  (`scripts/tests/test_wiring_skills_and_commands.py:336-346`, ENH-2996) asserts the
  post-frontmatter body is byte-identical to the source. **Any edit to
  `skills/wire-issue/SKILL.md` breaks this test until the mirrors are regenerated** via
  `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply`. `commands/refine-issue.md`
  has no equivalent mirror test (`.kimi-code/skills/ll-refine-issue/SKILL.md` is a thin
  pointer stub, not a body copy) [Agent 1/2 finding]

### Correction to stated test homes
- `scripts/tests/test_wire_issue_static_layer.py` does **not** test
  `skills/wire-issue/SKILL.md` prose despite its name — it exercises
  `little_loops.decisions.load_coupling_entries()` against `.ll/decisions.yaml` fixtures
  (Phase 3.5 Static Coupling Layer only) and never opens the SKILL.md file. The actual
  structural test home for SKILL.md content (and for `commands/refine-issue.md` via a
  separate `DOC_STRINGS_PRESENT` table) is
  `scripts/tests/test_wiring_skills_and_commands.py`, which drives parametrized
  `(doc_rel, needle, issue_id)` tuples through `test_string_present_in_doc` /
  `test_string_absent_from_doc` (e.g. the ENH-2996 entries at lines 210, 274). A new
  `### Behavior Parity` doctrine-text assertion belongs here, not in
  `test_wire_issue_static_layer.py` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1872` — "reports gaps in **fifteen** classes" + the full enumerated
  parenthetical list ending `...ambiguous_file_ref\` (each documented below)` needs
  "sixteen" + a new `missing_behavior_parity` bullet; `:1942`'s JSON example output line also
  needs the new key inserted [Agent 2 finding]
- `docs/reference/API.md:862` — same "fifteen gap classes" count + full name list; a sibling
  `- **missing_behavior_parity** (ENH-3045) — ...` bullet is needed following the
  `ambiguous_file_ref` bullet at `:875` [Agent 2 finding]
- `docs/reference/COMMANDS.md` — two separate `/ll:wire-issue` descriptions need the new
  category, not just "descriptions" generically: the **"Wiring categories searched" bullet
  list** (~line 265-270: Callers/Config/Tests/Docs/Side effects — no Behavior Parity entry)
  and the standalone summary sentence at line 259 ("traces the _where_: every caller,
  importer, config entry, doc section, test file...") [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:306` — a second, independent prose description of
  what `wire-issue` traces ("callers, config, docs, tests") in the pipeline guide, separate
  from the CLI reference and equally stale once a parity category is added [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py:326-347` — the hardcoded full-`to_dict()`
  JSON-equality assertion (each key carries an `# ENH-XXXX:` comment per convention) needs a
  `"missing_behavior_parity": [...] # ENH-3045` line added
- `scripts/tests/test_ll_issues_format_check.py` — new `TestMissingBehaviorParity`-style
  class, CLI-integration level, following `TestAmbiguousFileRef` (718-838, `--all` and
  `--format json` variants) or the duplicate-block tests (1680-1717)
- `scripts/tests/test_issue_parser.py` — new class near `TestStackedFindingsBlocks` (4269),
  direct unit test of `_heading_bodies(content, "Behavior Parity")` returning `[]` when the
  section is absent — the absence case is not currently covered by any existing
  `_heading_bodies` test
- `scripts/tests/test_wiring_skills_and_commands.py` — append `(doc_rel, needle, issue_id)`
  tuples to `DOC_STRINGS_PRESENT` for both `skills/wire-issue/SKILL.md` and
  `commands/refine-issue.md` asserting the `### Behavior Parity` doctrine text is present
  (e.g. `("skills/wire-issue/SKILL.md", "### Behavior Parity", "ENH-3045")`) — this is the
  only test surface possible for the capability-search doctrine itself, since it is pure
  agent-prompt prose with no Python code path to unit test
- `scripts/tests/test_wiring_skills_and_commands.py::test_wire_issue_skill_mirror_matches_source`
  (336-346) — will fail as soon as `skills/wire-issue/SKILL.md` is edited; run
  `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply` before this test is green

### Configuration
_Checked: `scripts/little_loops/config-schema.json` and `.ll/decisions.yaml` coupling
entries — no `FormatGaps` field names appear in either; this axis is clean, no edits needed._

### Similar Patterns
- `ENH-2946` — extending `format-check` with new gap kinds
- `ENH-494` — SKILL.md companion-file extraction when over the line cap
- `ENH-2996` — host-mirror sync test pattern (`test_wiring_skills_and_commands.py`) that any
  `skills/wire-issue/SKILL.md` edit must satisfy

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

### Types
- `missing_behavior_parity: list[str]` — new `FormatGaps` field, `scripts/little_loops/issue_parser.py:236-259`; alongside `stale_file_ref`/`ambiguous_file_ref`/`duplicate_findings_block`, each of which is also a plain `list[str]`.
- `RefStatus` — `"resolved" | "stale" | "unresolvable_form" | "planned_new" | "ambiguous"`, `scripts/little_loops/text_utils.py`; a parity-gap check filters for `"resolved"` refs near rewrite/delete/delegate language.

### Signatures
- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None) -> FormatGaps` — `scripts/little_loops/issue_parser.py:342-347`; unchanged signature, the new gap kind is an added field plus a detection block inside the existing body.
- `build_ref_index(root: Path) -> RefIndex` — `scripts/little_loops/text_utils.py:161`
- `classify_file_ref(ref: str, index: RefIndex, *, line: str = "") -> RefStatus` — `scripts/little_loops/text_utils.py:201`
- `classify_issue_refs(content: str, index: RefIndex) -> dict[str, RefStatus]` — `scripts/little_loops/text_utils.py:313`
- `_heading_bodies(content, "Behavior Parity")` — `scripts/little_loops/issue_parser.py:677-693`; existing H2/H3 section-body lookup already used by `unmarked_superseded_directive`/`superseded_marker_count`. Its body is `rf"^(#{{2,3}})\s+{re.escape(heading)}\s*$"` — **anchored and exact**, which is why Expected Behavior fixes the heading to bare `### Behavior Parity`. Used unmodified: a non-empty return means the section is present.

### Decision Rules

_The `missing_behavior_parity` predicate, specified in full. Implement as written._

**Fires when** all four hold:

1. **Scope** — the file ref appears in `## Summary`, `## Proposed Solution`, or
   `### Files to Modify` (under `## Integration Map`). Refs in `### Similar Patterns`,
   `### Documentation`, `### Tests`, `## Current Behavior`, or the Session Log are ignored;
   those cite files as evidence or precedent, not as replacement targets.
2. **Ref resolves** — `classify_issue_refs()` returns `"resolved"` for the ref. A
   `planned_new` / `stale` / `unresolvable_form` / `ambiguous` ref has no live behavior to
   preserve, so it cannot produce a parity obligation.
3. **Replacement keyword** — a closed, case-insensitive list, matched as whole words on the
   **same line** as the ref: `delete`, `deletes`, `deleted`, `remove`, `removes`, `removed`,
   `replace`, `replaces`, `replaced`, `rewrite`, `rewrites`, `rewritten`, `supersede`,
   `supersedes`, `superseded`, `delegate`, `delegates`, `delegated`. Same-line-only is the
   deliberate conservative start — no multi-line proximity window in v1. If the sweep in
   Acceptance Criteria shows same-line is too tight, widening to "the bullet containing the
   ref" is the pre-approved next step; widening further is not.
4. **No parity section** — `_heading_bodies(content, "Behavior Parity")` returns `[]`.

**Escape hatch** — `behavior_parity_not_applicable: true` in frontmatter suppresses the gap
unconditionally, mirroring the `program_design_not_applicable` precedent
(`issue_parser.py:377`, `issues/program_design.py:435`, the three `*-sections.json` templates).
Per that precedent it is a **human decision**: refine and wire must never set it themselves.
Unknown frontmatter keys are not flagged by any existing check (only the deprecated-key
registry at `issue_parser.py:53-92` is consulted), so no registry work is required.

**Explicitly does not fire on**: an issue that only *reads* or *calls* the cited file; a file
named solely as a test/doc/config touchpoint by the wiring pass; an issue whose replacement
target is a directory or a glob rather than a concrete resolved path.

### Call Path
- **wire-issue**: Phase 3 `EXISTING_WIRING` extraction (`skills/wire-issue/SKILL.md:100-127`) gains a sibling `REPLACED_ARTIFACTS` block → Phase 4 Agent 1 (codebase-locator, `SKILL.md:145-182`) and Agent 3 (codebase-pattern-finder, `SKILL.md:215-244`) prompts get the capability-search instruction appended after their existing boilerplate close → Phase 8a Integration Map Updates (`SKILL.md:330-380`) emits a `### Behavior Parity` subsection alongside the existing `### Documentation`/`### Tests` subsections, following the same heading + `_Wiring pass added by \`/ll:wire-issue\`:_` provenance-line shape → Phase 8c Preservation Rule (`SKILL.md:400-406`) governs it identically (append-only).
- **refine-issue**: Step 5a Integration Map enrichment template (`commands/refine-issue.md:338-365`) gains a sixth `### Behavior Parity` subsection → written via `ll-issues fold-findings [ID] --section "Integration Map"` (`commands/refine-issue.md:485-516`), same append-only, `--dry-run`-aware route already used for every other subsection.
- **gap-kind detection**: `check_format_gaps()` (`scripts/little_loops/issue_parser.py:342-582`) gains a detection block after the existing `ref_index` handling (`:571-582`) and before `_duplicate_findings_blocks` (`:599`) → checks the frontmatter escape hatch first, then applies the four conditions in § Decision Rules above via `classify_issue_refs()` and `_heading_bodies(content, "Behavior Parity")` → populates `FormatGaps.missing_behavior_parity` → rendered by `cli/issues/format_check.py`'s `_print_gaps()` (`:132-162`) and help text (`:61-65`), following the ENH-2999/ENH-2993 precedent for adding a gap kind.

## Implementation Steps

1. Add the parity step + table emission to wire and refine.
2. Add the capability-search and claim-grounding requirements to wire's Agent 1/3 prompts and to
   refine's Program Design emission.
3. `missing_behavior_parity` gap kind + tests, implementing § Decision Rules verbatim (required
   — see the four-site note in the Wiring Phase below; `ENH-3047` consumes it by name).
4. Validate against FEAT-2942 and sweep the backlog — see Acceptance Criteria.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Inside `scripts/little_loops/issue_parser.py`, the new `missing_behavior_parity` field
  needs edits at **four** distinct sites, not one: the `FormatGaps` dataclass field
  (`:236-259`), the `has_gaps` OR-chain (`:260-279`), `to_dict()` (`:281-299`), and the
  detection block itself — missing any of the first three silently drops the gap from the
  exit-code signal or JSON output even though detection ran correctly
- Update `scripts/little_loops/cli/issues/format_check.py` in three places: `_print_gaps()`
  (132-162), the `add_format_check_parser` `--help` string (61-65), and the
  `cmd_format_check()` docstring (168-175) — three separate copies of the same enumeration
- Update `scripts/little_loops/cli/issues/__init__.py:139` — the top-level subcommand help
  text repeats the gap-kind list a third time
- Update `docs/reference/CLI.md` and `docs/reference/API.md` — "fifteen" → "sixteen" gap
  classes, plus a new per-kind bullet in each
- Update `docs/reference/COMMANDS.md`'s wiring-categories bullet list and summary sentence,
  and `docs/guides/ISSUE_MANAGEMENT_GUIDE.md:306` — both independently describe what
  wire-issue traces and go stale together
- Add `_heading_bodies(content, "Behavior Parity") == []` absence-case unit test in
  `scripts/tests/test_issue_parser.py`, plus its positive counterpart asserting a bare
  `### Behavior Parity` heading **is** matched (the fixed-heading contract from Expected
  Behavior — a regression here silently disables the whole gate), and `DOC_STRINGS_PRESENT`
  doctrine-text entries in `scripts/tests/test_wiring_skills_and_commands.py` (not
  `test_wire_issue_static_layer.py` — see correction note in Integration Map)
- Read `behavior_parity_not_applicable` from frontmatter in the `check_format_gaps()`
  detection block as the first condition checked; add its guidance line to
  `scripts/little_loops/templates/bug-sections.json`,
  `scripts/little_loops/templates/feat-sections.json`, and
  `scripts/little_loops/templates/enh-sections.json` alongside the existing
  `program_design_not_applicable` line (`:90` in each)
- After editing `skills/wire-issue/SKILL.md`, run
  `ll-adapt --host gemini --apply && ll-adapt --host kimi --apply` to regenerate
  `.gemini/skills/wire-issue/SKILL.md` / `.kimi-code/skills/wire-issue/SKILL.md` before
  `test_wire_issue_skill_mirror_matches_source` will pass
- Cross-issue check (no action needed): `ENH-3047`'s Phase 1.6 already assumes the field
  name `missing_behavior_parity` and frames its dependency on this issue as soft — confirmed
  consistent with this issue's proposal, no reconciliation needed

## Acceptance Criteria

**Doctrine (wire + refine)**

1. `skills/wire-issue/SKILL.md` and `commands/refine-issue.md` both instruct emission of a
   `### Behavior Parity` subsection — bare heading, artifact as a table column — under
   `## Integration Map`, and both are asserted by `DOC_STRINGS_PRESENT` entries in
   `scripts/tests/test_wiring_skills_and_commands.py`.
2. `skills/wire-issue/SKILL.md` stays under the 500-line `ll-verify-skills` cap (455 today), or
   the overflow is extracted to a companion file per the ENH-494 pattern.
3. `.gemini/` and `.kimi-code/` mirrors are regenerated and
   `test_wire_issue_skill_mirror_matches_source` passes.
4. Wire's Agent 1 and Agent 3 prompts require capability-shaped search (input/output shape and
   callers of the shared primitive) before any "no existing implementation" conclusion, and
   require the resulting claim to state what was searched.

**Gap kind**

5. `missing_behavior_parity` is present in the `FormatGaps` dataclass, the `has_gaps` OR-chain,
   `to_dict()`, and `_print_gaps()` — the last enforced automatically by the existing parity
   test at `scripts/tests/test_ll_issues_format_check.py:1559-1577`.
6. The predicate matches § Decision Rules exactly: unit tests cover each of the four firing
   conditions in isolation, each of the three explicit non-firing cases, and the
   `behavior_parity_not_applicable: true` escape hatch.
7. `ll-issues format-check FEAT-2942 --format json` reports `missing_behavior_parity`
   non-empty before FEAT-2942 gains a parity table, and empty after.

**Validation against the motivating defects**

8. Running the updated wire/refine over FEAT-2942 produces a parity table that names all three
   originally-missed behaviors: the title+`## Summary` → title-only scoring-corpus narrowing,
   the 0.7/0.4 HIGH/MEDIUM/LOW tier boundaries, and the definition of "orphan".
9. FEAT-2942's union-find negative claim is either retracted or restated naming
   `batch_similarity()` (`scripts/little_loops/cli/issues/find_similar.py`) and the search
   performed.

**False-positive sweep (gates the autodev risk)**

10. `ll-issues format-check --all --format json` across the active backlog is triaged
    issue-by-issue for `missing_behavior_parity` hits; every hit is either a genuine missing
    parity table or an accepted escape-hatch case. Zero unexplained hits — `format-check` exits
    1 on any gap and `autodev.yaml:1538` routes on this JSON, so an untriaged false positive
    mis-routes real issues.
11. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — 4 of 7 observed defects, and `ENH-3047` is blocked on the gap kind
- **Effort**: Medium — the doctrine half is markdown, but the now-required gap kind is a
  four-site change in `issue_parser.py` (dataclass field, `has_gaps` OR-chain, `to_dict()`,
  detection block), three enumeration copies across `format_check.py` and
  `cli/issues/__init__.py`, four doc files, and three test surfaces. Re-rated up from
  "Low-Medium" once the gap kind stopped being optional.
- **Risk**: Low-Medium — the doctrine half is additive (worst case: a parity table on an issue
  that doesn't need one), but `format-check` exits 1 on any gap and `autodev.yaml:1538` reads
  its JSON in a routing gate, so a false-positive parity gap mis-routes real issues. The
  detection rule's keyword list, proximity rule, scope limit, and escape hatch are pinned in
  **Program Design § Decision Rules** — deliberately specified *here* rather than deferred to
  `ENH-3050`, which is P3 and sits behind `ENH-3047` → `FEAT-3048`, while `ENH-3047` in turn
  consumes this issue's gap kind by name. Waiting on 3050 for the spec would be circular.
  `ENH-3050` remains the right home for generalizing a `### Decision Rules` slot across all
  issues; it is not a prerequisite for this one.

## Scope Boundaries

**In scope**: the three doctrine changes to `skills/wire-issue/SKILL.md` and
`commands/refine-issue.md`; the `missing_behavior_parity` gap kind and its escape hatch; the
doc/test/mirror updates those two require.

**Out of scope**:

- **Not parented to `EPIC-2938`.** That epic's Scope excludes rewriting reasoning-heavy skills
  like `refine-issue`, and these are prompt/doctrine changes, not prose→CLI conversions.
- **No generalized `### Decision Rules` slot.** This issue pins *its own* predicate under
  Program Design. Making Decision Rules a first-class template section for all issues — with
  its own gap kind and refine emission — is `ENH-3050`.
- **No mechanical verification of claims.** Checking that a cited symbol exists is `FEAT-3048`;
  this issue's claim-grounding bullet is prose doctrine only, with no gate and no new
  `program_design_nonspecific` behavior.
- **No confidence-check scoring changes.** Feeding these gaps into Criterion 4 deductions is
  `ENH-3047`, which consumes `missing_behavior_parity` by name.
- **No intra-issue contradiction detection.** `ENH-3049`.
- **No auto-population of parity tables.** Wire and refine *prompt for* and *emit* the table
  from research findings; nothing infers behaviors from the replaced artifact's source
  automatically.
- **No retroactive backfill.** Existing issues are not swept and amended; the sweep in
  Acceptance Criteria is a false-positive triage, not a remediation campaign.

## Related Key Documentation

- `.claude/CLAUDE.md` § Development Preferences — prefer Skills over Agents
- `docs/reference/COMMANDS.md` — `/ll:wire-issue`, `/ll:refine-issue` descriptions

## Status

**Open** | Created: 2026-08-04 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-05T01:59:02 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:ready-issue` - 2026-08-05T01:37:17 - `32d58794-1548-4ea3-85e2-be0181a88760.jsonl`
- `/ll:confidence-check` - 2026-08-04T21:22:57 - `e8e39a33-2d58-481a-aabd-651cc7d53758.jsonl`
- `/ll:wire-issue` - 2026-08-04T21:20:39 - `90ea35aa-80f8-414c-acb5-630c56fbc5e6.jsonl`
- `/ll:refine-issue` - 2026-08-04T21:02:31 - `51b5dc42-42bc-4a42-9db0-7c590083bc0b.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:27 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
