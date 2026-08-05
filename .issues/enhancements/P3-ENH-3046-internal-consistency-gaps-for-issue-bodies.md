---
id: ENH-3046
title: soft_dep_hard_edge gap kind in format-check + AC-vs-design pass in refine-issue
type: ENH
priority: P3
status: done
completed_at: '2026-08-05T04:35:00Z'
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-04
captured_at: '2026-08-04T20:47:11Z'
relates_to:
- ENH-2946
- FEAT-3048
- FEAT-2942
- ENH-3049
labels:
- cli
- issues
- gates
confidence_score: 96
outcome_confidence: 86
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
---

# ENH-3046: Internal-consistency gaps for issue bodies

## Summary

Refine and wire both look *outward* at the codebase; nothing checks an issue **against itself**.
Two statements in one file can flatly contradict each other and pass every gate. Add the
mechanical half as one `format-check` gap kind (successor to ENH-2946's pattern), and fold the
judgment half into `/ll:refine-issue` as one focused prompt.

## Current Behavior

No gate compares sections of an issue to each other.

**Evidence — FEAT-2942 as of `5186d1d5^` (frozen; see Scope Boundaries for how this is tested).**
Two contradictions lived in that file and survived refine, wire, and confidence-check:

1. **AC vs. scope.** AC 1 required *"no writes without `--apply`"* for both modes, while AC 5
   forbade EPIC creation in this subcommand — but EPIC creation is the only thing synthesize
   mode could write. An implementer resolving AC 1 literally would build exactly what AC 5
   forbids. *Judgment-class: no mechanical rule catches this — both ACs name `--apply`, which
   the stated signature does have.*
2. **Frontmatter vs. body.** Frontmatter declared `blocked_by: [FEAT-2947]` (open), while the
   body said *"Soft dep on FEAT-2947 … If FEAT-2947 has not landed, synthesize mode still ships
   proposal-only."* The hard edge keeps automation from selecting the issue for a dependency the
   body says is optional — and `deferred`/`open` blockers never resolve, so it sits there.
   *Mechanical-class: this is what `soft_dep_hard_edge` detects.*

Both were fixed by hand in `5186d1d5` (2026-08-04 15:55) — a human refine pass, not a gate.
**The staleness is itself evidence:** this issue was captured at 20:47 the same day and then run
through `/ll:refine-issue`, `/ll:wire-issue`, and `/ll:confidence-check`, none of which noticed
that its own motivating examples had been repaired five hours earlier. Nothing in the pipeline
re-reads a cited fixture, and nothing compares an issue's claims to its own citations.

## Expected Behavior

One mechanical gap kind in `check_format_gaps()`:

- `soft_dep_hard_edge` — an ID in `blocked_by` that the body describes with soft-dependency
  language ("soft dep", "optional", "if … has not landed", "nice to have"). Cheap: reuse
  `prose_deps.py`'s ID regex + fence handling, add a phrase list.

Three decisions this gap kind needs, settled here rather than at implementation time:

- **Proximity window: same paragraph, not same line.** ENH-3045's `missing_behavior_parity`
  chose same-line deliberately, but the FEAT-2942 evidence spans a full paragraph — the ID and
  the phrase "If FEAT-2947 has not landed" sit in different sentences of one block. Same-line
  would have missed the only real specimen we have. Window = the blank-line-delimited paragraph
  containing the ID, fences excluded via `_in_fence`.
- **Remedy: move the ID to `relates_to`, don't delete the prose.** The soft language is usually
  the accurate statement and the hard edge is the mistake (as in FEAT-2942, where `5186d1d5`
  resolved it exactly this way). The gap message must say so, since the alternative fix —
  deleting the soft language to justify the edge — silently hardens a dependency that was
  deliberately optional. Contrast `stale_prose_dep`, where deleting the prose *is* the remedy.
- **Suppression: none.** No frontmatter escape hatch, unlike `behavior_parity_not_applicable`
  (ENH-3045). A dependency is hard or it isn't; if the body means "hard, with a documented
  fallback," the fix is to reword the body. Revisit only if false positives show up in practice.

Plus one judgment pass in `/ll:refine-issue`: a single focused prompt — *"read only the
Acceptance Criteria and Program Design sections; list any pair of statements that cannot both be
satisfied"* — reported as findings, not auto-applied. This is the half that catches contradiction
1 above; no mechanical rule can.

## Motivation

Contradictions are the cheapest defect class to catch (no codebase knowledge needed, the
evidence is entirely in one file) and among the most expensive to hit during implementation,
because they surface only when someone tries to satisfy both statements at once. The mechanical
half is small and lands in machinery that already exists.

## Proposed Solution

Follow ENH-2946 exactly: one new field on `FormatGaps`, populated in `check_format_gaps()`,
printed by `format_check.py`, listed in `--kinds` help, covered by `scripts/tests/`.

The refine prompt is a bounded addition to `commands/refine-issue.md` (1020 lines) — keep it to a
single step near the existing Step 6.7 prose/design gate rather than a new phase, and emit
findings into the report rather than rewriting sections.

## Scope Boundaries

**In scope:**
- `soft_dep_hard_edge` gap kind end-to-end (the five sites in Program Design + docs + tests).
- One AC-vs-Program-Design contradiction step in `commands/refine-issue.md` Step 6.7, report-only.
- A frozen FEAT-2942 test fixture: copy the `## Acceptance Criteria` + frontmatter of
  `.issues/features/P2-FEAT-2942-*.md` **at `5186d1d5^`** into `scripts/tests/` as a literal
  fixture. Do **not** assert against the live issue file — it was repaired in `5186d1d5` and no
  longer contains either defect.

**Out of scope:**
- `ac_flag_drift` (an AC naming a flag absent from the issue's own stated CLI signature). Cut
  from this issue: neither FEAT-2942 contradiction is an instance of it (contradiction 1's ACs
  both name `--apply`, which the signature has), it has no reusable extractor, and its source
  section is undefined ("fenced block or `## Program Design` prose"). That is the exact
  false-positive profile ENH-3053 documents for `normalize`'s `type_mismatch`. Flag verification
  belongs to **FEAT-3048**, which already owns argparse-backed extraction; fold it in there if
  wanted.
- Any auto-fix. Both halves report only.

Boundary vs. FEAT-3048: that issue verifies claims against the **codebase**; this one verifies an
issue against **itself**. They share the extractor conventions but not the lookups, and neither
blocks the other.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `FormatGaps` fields + `check_format_gaps()`
- `scripts/little_loops/cli/issues/format_check.py` — printer + `--kinds` help
- `scripts/little_loops/issues/prose_deps.py` — reuse ID regex / `_in_fence` for the soft-dep
  phrase scan
- `commands/refine-issue.md` — one AC-vs-Program-Design consistency step
- `scripts/tests/` — per-gap-kind coverage
- `docs/reference/CLI.md` — document the new gap kinds

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:139` — third hardcoded `--kinds`/help CSV string;
  already named as site 4 of the Program Design "five sites" contract (`:119`) but was absent from
  this list [Agent 1 finding]
- `docs/reference/API.md:862`, `:878` (`check_format_gaps` reference entry) — second independent
  gap-kind enumeration; not in the original Integration Map [Agent 2 finding]. _Review correction
  2026-08-05: the wiring pass called this entry stale ("fifteen gap classes", missing
  `missing_behavior_parity`); `5fac18bc` fixed it. It now reads "sixteen" and is complete — bump
  to seventeen, don't repair._

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_design.py` — calls `check_format_gaps()` and
  `design_gate_failed()`; verify no gap-kind allowlist needs updating for the two new kinds
  [Agent 1 finding]
- `scripts/little_loops/issues/research_triage.py` — references `check_format_gaps()` /
  `program_design_nonspecific` in docstrings and analysis [Agent 1 finding]
- `scripts/little_loops/loops/autodev.yaml` — routes on `design_gate_failed()` output derived from
  `check_format_gaps()`; confirm new gap kinds don't change routing [Agent 1 finding]
- `scripts/little_loops/loops/rn-remediate.yaml` — uses format-check gaps for remediation routing
  [Agent 1 finding]
- `skills/confidence-check/SKILL.md` (Phase 1.6, `:132-150`) — functionally parses
  `program_design_nonspecific` out of `format-check --format json`; establishes the consumption
  pattern the two new kinds could plug into later, not touched by this issue [Agent 2 finding]
- `skills/format-issue/SKILL.md`, `skills/decide-issue/SKILL.md` — reference format-check gap
  concepts generally [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — references format-checking/gap concepts [Agent 1
  finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py` — `TestAmbiguousFileRef` (`:720`, ENH-2999) is the
  exact pattern to mirror for both new gap kinds (`_write_bug_with_*` helper + `--all` text
  assertion + single-ID `--format json` exact-list assertion); `test_clean_issue_json_output`
  (`:302`) and `test_every_format_gaps_field_is_rendered` (`:1730`) must gain the two new keys
  [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — direct unit-level precedent for testing
  `check_format_gaps()` without going through the CLI (`TestCheckFormatGapsTestablePopulation`,
  `:4074`; ENH-2426 block, `:3811`) [Agent 3 finding]
- `scripts/tests/test_refine_issue_command.py` — `TestProgramDesignGateExtension` (`:435`) and
  `TestSessionLogPrecedesProgramDesignGate` (`:469`) assert on Step 6.7's markdown content and
  heading order; the new judgment-pass step must extend these the same way (slice the section,
  assert new phrases/keys appear) [Agent 3 finding]
- `scripts/tests/test_program_design_gate.py` — `TestFormatGapsWiring` covers `FormatGaps`
  wiring/serialization [Agent 1 finding]
- `scripts/tests/test_ll_issues_check_design.py` — tests the `check-design` command that calls
  `check_format_gaps()` [Agent 1 finding]
- `scripts/tests/test_prose_dep_sweep_gate.py` — uses `check_format_gaps()` for prose-dependency
  validation [Agent 1 finding]

### Similar Patterns
- `ENH-2946` — the direct precedent for extending `format-check` with gap kinds
- `FEAT-2849` — extractor + gap taxonomy shape

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Types

- `FormatGaps.soft_dep_hard_edge: list[str] = field(default_factory=list)` — new field, same shape as the 16 existing `FormatGaps` fields (`scripts/little_loops/issue_parser.py:237-301`)

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None) -> FormatGaps` — `scripts/little_loops/issue_parser.py:342-347`. The new gap kind is detected as an additional block in this function's body; `soft_dep_hard_edge` belongs beside the existing `prose_dep_drift`/`stale_prose_dep` block (`:533-558`, already gated on `issue_statuses is not None` and already reading `blocked_by`/`depends_on` via `fm.get(key)`, `:543-548`).
- `_in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool` — `scripts/little_loops/issues/prose_deps.py:44-45`, pure function reusable as-is for `soft_dep_hard_edge`'s fence exclusion.
- `_ID_ONLY_RE = re.compile(_ID_RE)` — `scripts/little_loops/issues/prose_deps.py:37`, bare-ID scan reusable for locating `blocked_by`/`depends_on` IDs mentioned in body prose. No existing phrase-list-scan helper is shared across consumers — `soft_dep_hard_edge` needs its own compiled phrase regex mirroring `_PHRASE_RE`'s shape (`prose_deps.py:28-32`), not a call into a generic utility. Paragraph segmentation (blank-line split, per the proximity decision in Expected Behavior) has no existing helper either; scope it to this block.

### Call Path

`cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py`) -> `check_format_gaps()` (`issue_parser.py:342`) -> new `soft_dep_hard_edge` block reusing `_in_fence`/`_ID_ONLY_RE` (`prose_deps.py`) + a new phrase-list regex -> `FormatGaps.soft_dep_hard_edge` -> `_print_gaps()` (`format_check.py:132-164`, one `for entry in gaps.soft_dep_hard_edge: print(...)` loop)

Five sites the new field must touch, traced end-to-end on the most recent precedent (ENH-3045's `missing_behavior_parity`, fully landed at `5fac18bc` — use it, not ENH-2999, as the copy target): `FormatGaps` field (`issue_parser.py:259`) + `has_gaps` clause (`:280`) + `to_dict()` key (`:301`) + docstring `Gap classes:` paragraph (`:425`) -> `check_format_gaps()` detection block (`:621`) -> `_print_gaps()` loop (`format_check.py:163-164`, pinned by the structural guard `test_every_format_gaps_field_is_rendered`, `scripts/tests/test_ll_issues_format_check.py:1555-1577`) -> three hardcoded `--kinds`/help CSV strings (`format_check.py:65`, `:173`; `cli/issues/__init__.py:139`) -> `docs/reference/CLI.md:1872` prose + `:1900` detail + `:1950` JSON example, and `docs/reference/API.md:862` + `:878` -> `test_clean_issue_json_output` literal dict pin (`test_ll_issues_format_check.py:345`).

Both doc sites carry a self-correcting count ("sixteen gap classes … re-derive this count from `dataclasses.fields(FormatGaps)` rather than trusting the number written here") — bump to seventeen.

The judgment-pass step (AC-vs-Program-Design contradiction prompt) anchors at the existing `### 6.7. Prose Dependency & Program Design Gate (FEAT-2849, BUG-3001)` in `commands/refine-issue.md:808`, extending its `## PROSE/PROGRAM DESIGN GATE [Step 6.7]` output block (`:937`) with one more status line, matching the read-only "report, don't edit" posture already used there for `superseded_marker_count`/`duplicate_findings_block`. **These anchors drifted ~30 lines during 2026-08-04's commits — re-locate by heading text, not line number.**

## Implementation Steps

1. Freeze the fixture first: `git show 5186d1d5^:.issues/features/P2-FEAT-2942-ll-issues-link-epics-cluster-and-propose.md` — capture the frontmatter `blocked_by: [FEAT-2947]` plus the "Soft dep on FEAT-2947 …" paragraph as a literal test fixture. This is the only known real specimen; it does not exist in the working tree.
2. `soft_dep_hard_edge` gap kind + phrase list + paragraph window + tests.
3. `format-check` reporting/`--kinds` wiring (five sites above).
4. Refine-issue AC-vs-Program-Design prompt step.
5. Validate: the frozen fixture reports `soft_dep_hard_edge` for FEAT-2947, and the live
   `.issues/features/P2-FEAT-2942-*.md` reports **nothing** — a regression guard proving the
   detector tracks the repair rather than firing on any `blocked_by` edge.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/cli/issues/__init__.py:139` — third hardcoded `--kinds`/help CSV,
  alongside the two already named in `format_check.py`.
- Update `docs/reference/API.md:862` (count + enumeration) and `:878` (per-kind detail) — the
  `check_format_gaps()` reference entry, a second enumeration site independent of
  `docs/reference/CLI.md`.
- Update `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — general format-check/gap-kind references.
- Update `scripts/tests/test_ll_issues_format_check.py` — add a `soft_dep_hard_edge` fixture
  mirroring `TestMissingBehaviorParity` (`:855`, ENH-3045 — the newest and closest precedent,
  since it also gates on frontmatter state); add the key to `test_clean_issue_json_output`
  (`:302`).
- Update `scripts/tests/test_issue_parser.py` — direct `check_format_gaps()` unit coverage
  following the `TestCheckFormatGapsTestablePopulation` (`:4074`) shape.
- Update `scripts/tests/test_refine_issue_command.py` — extend `TestProgramDesignGateExtension`
  (`:435`) and `TestSessionLogPrecedesProgramDesignGate` (`:469`) for the new judgment-pass step's
  markdown and heading order.

_Superseded by the 2026-08-05 review pass:_ the wiring pass flagged `missing_behavior_parity`
(ENH-3045) as an unwired pre-existing gap needing a sweep. **That is no longer true** — ENH-3045
landed fully in `5fac18bc`: the `_print_gaps()` loop exists (`format_check.py:163-164`), all three
`--kinds` CSVs list it, `docs/reference/API.md:862`/`:878` document it, and
`test_clean_issue_json_output` + `test_every_format_gaps_field_is_rendered` both pass at HEAD. No
sweep required; it is the copy-target precedent instead.

## Impact

- **Priority**: P3 — real but narrower than FEAT-3048/ENH-3045
- **Effort**: Low — one gap kind in existing machinery plus one prompt step (was Medium before
  `ac_flag_drift` was cut to FEAT-3048)
- **Risk**: Low — reporting only; no auto-fix

## Related Key Documentation

- `.claude/CLAUDE.md` § Issue File Format — status enum and dependency semantics
- `docs/reference/DEFERRAL_CODES.md` — `deferred` is non-terminal for dependency edges

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-08-05T03:20:01 - `b93ed61c-d438-457c-84c0-8c0cd5956068.jsonl`
- `/ll:confidence-check` - 2026-08-05T02:43:49 - `373c0340-8e1f-44ea-8319-fc74f63a37a4.jsonl`
- `/ll:confidence-check` - 2026-08-05T01:56:57 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:wire-issue` - 2026-08-05T01:47:19 - `6569bf0b-4efa-4bb9-8b85-a0e909af608e.jsonl`
- `/ll:refine-issue` - 2026-08-05T01:31:38 - `eb7fedb4-0dd1-4b7c-8880-6ff7b6346575.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:27 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
