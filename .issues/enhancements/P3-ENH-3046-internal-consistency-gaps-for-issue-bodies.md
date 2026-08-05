---
id: ENH-3046
title: Internal-consistency gap kinds in format-check + AC-vs-design pass in refine-issue
type: ENH
priority: P3
status: open
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
---

# ENH-3046: Internal-consistency gaps for issue bodies

## Summary

Refine and wire both look *outward* at the codebase; nothing checks an issue **against itself**.
Two statements in one file can flatly contradict each other and pass every gate. Add the
mechanical half as `format-check` gap kinds (successor to ENH-2946's pattern), and fold the
judgment half into `/ll:refine-issue` as one focused prompt.

## Current Behavior

No gate compares sections of an issue to each other. Two live contradictions in FEAT-2942, both
of which survived refine, wire, and confidence-check:

1. **AC vs. scope.** AC 1 requires *"no writes without `--apply`"* for both modes, while AC 5
   forbids EPIC creation in this subcommand — but EPIC creation is the only thing synthesize
   mode could write. An implementer resolving AC 1 literally would build exactly what AC 5
   forbids.
2. **Frontmatter vs. body.** Frontmatter declares `blocked_by: [FEAT-2947]` (open), while the
   body says *"Soft dep on FEAT-2947 … If FEAT-2947 has not landed, synthesize mode still ships
   proposal-only."* The hard edge keeps automation from selecting the issue for a dependency the
   body says is optional — and `deferred`/`open` blockers never resolve, so it sits there.

## Expected Behavior

Two mechanical gap kinds in `check_format_gaps()`:

- `soft_dep_hard_edge` — an ID in `blocked_by` that the body describes with soft-dependency
  language ("soft dep", "optional", "if … has not landed", "nice to have"). Cheap: reuse
  `prose_deps.py`'s ID regex + fence handling, add a phrase list.
- `ac_flag_drift` — an acceptance criterion referencing a flag or mode absent from the CLI
  signature stated elsewhere in the same issue. Overlaps FEAT-3048's argparse work but is
  purely intra-document: compare ACs against the issue's own stated signature, no codebase
  lookup.

Plus one judgment pass in `/ll:refine-issue`: a single focused prompt — *"read only the
Acceptance Criteria and Program Design sections; list any pair of statements that cannot both be
satisfied"* — reported as findings, not auto-applied.

## Motivation

Contradictions are the cheapest defect class to catch (no codebase knowledge needed, the
evidence is entirely in one file) and among the most expensive to hit during implementation,
because they surface only when someone tries to satisfy both statements at once. The mechanical
half is small and lands in machinery that already exists.

## Proposed Solution

Follow ENH-2946 exactly: new fields on `FormatGaps`, populated in `check_format_gaps()`,
printed by `format_check.py`, listed in `--kinds` help, covered by `scripts/tests/`.

The refine prompt is a bounded addition to `commands/refine-issue.md` (987 lines) — keep it to a
single step near the existing Step 6.7 prose/design gate rather than a new phase, and emit
findings into the report rather than rewriting sections.

Scope boundary vs. FEAT-3048: that issue verifies claims against the **codebase**; this one
verifies an issue against **itself**. They share the extractor conventions but not the lookups,
and neither blocks the other.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `FormatGaps` fields + `check_format_gaps()`
- `scripts/little_loops/cli/issues/format_check.py` — printer + `--kinds` help
- `scripts/little_loops/issues/prose_deps.py` — reuse ID regex / `_in_fence` for the soft-dep
  phrase scan
- `commands/refine-issue.md` — one AC-vs-Program-Design consistency step
- `scripts/tests/` — per-gap-kind coverage
- `docs/reference/CLI.md` — document the new gap kinds

### Similar Patterns
- `ENH-2946` — the direct precedent for extending `format-check` with gap kinds
- `FEAT-2849` — extractor + gap taxonomy shape

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

### Types

- `FormatGaps.soft_dep_hard_edge: list[str] = field(default_factory=list)` — new field, same shape as the 15 existing `FormatGaps` fields (`scripts/little_loops/issue_parser.py:237-299`)
- `FormatGaps.ac_flag_drift: list[str] = field(default_factory=list)` — new field, same shape

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None) -> FormatGaps` — `scripts/little_loops/issue_parser.py:342-347`. Both new gap kinds are detected as additional blocks in this function's body (`:444-601`); `soft_dep_hard_edge` belongs beside the existing `prose_dep_drift`/`stale_prose_dep` block (`:533-558`, already gated on `issue_statuses is not None` and already reading `blocked_by`/`depends_on` via `fm.get(key)`, `:543-548`).
- `_in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool` — `scripts/little_loops/issues/prose_deps.py:44-45`, pure function reusable as-is for `soft_dep_hard_edge`'s fence exclusion.
- `_ID_ONLY_RE = re.compile(_ID_RE)` — `scripts/little_loops/issues/prose_deps.py:37`, bare-ID scan reusable for locating `blocked_by`/`depends_on` IDs mentioned in body prose. No existing phrase-list-scan helper is shared across consumers — `soft_dep_hard_edge` needs its own compiled phrase regex mirroring `_PHRASE_RE`'s shape (`prose_deps.py:28-32`), not a call into a generic utility.
- `_SIG_CALL` / `_SIG_FIELD` (`scripts/little_loops/issues/program_design.py:79-90`) — analogous signature-shape regexes for the `program_design_nonspecific` gate, but Python-signature-shaped, not CLI-flag-shaped; `ac_flag_drift` has no reusable extractor and must parse flag/mode tokens (e.g. `--apply`, `--dry-run`) directly out of `## Acceptance Criteria` and whatever section states the CLI signature (fenced block or `## Program Design` prose).

### Call Path

`cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py`) -> `check_format_gaps()` (`issue_parser.py:342`) -> new `soft_dep_hard_edge` block reusing `_in_fence`/`_ID_ONLY_RE` (`prose_deps.py`) + a new phrase-list regex -> `FormatGaps.soft_dep_hard_edge` -> `_print_gaps()` (`format_check.py:132-162`, one `for entry in gaps.soft_dep_hard_edge: print(...)` loop)

`cmd_format_check` -> `check_format_gaps()` -> new `ac_flag_drift` block (direct fence/prose parse, no shared extractor) -> `FormatGaps.ac_flag_drift` -> `_print_gaps()` (same shape)

Five sites every new field must touch, traced end-to-end on the most recent precedent (ENH-2999's `ambiguous_file_ref`): `FormatGaps` field + `has_gaps` clause (`issue_parser.py:278`) + `to_dict()` key (`:298`) + docstring `Gap classes:` paragraph (`:356-421`) -> `check_format_gaps()` detection block -> `_print_gaps()` loop (`format_check.py:161-162`, pinned by the structural guard `test_every_format_gaps_field_is_rendered`, `scripts/tests/test_ll_issues_format_check.py:1555-1577`) -> three hardcoded `--kinds`/help CSV strings (`format_check.py:60-65`, `:168-171`; `cli/issues/__init__.py:139`) -> `docs/reference/CLI.md:1872-1898` prose + `:1942` JSON example -> `test_clean_issue_json_output` literal dict pin (`test_ll_issues_format_check.py:299-347`).

The judgment-pass step (AC-vs-Program-Design contradiction prompt) anchors at the existing `### 6.7. Prose Dependency & Program Design Gate` in `commands/refine-issue.md:781-831`, extending its `## PROSE/PROGRAM DESIGN GATE [Step 6.7]` output block (`:910-914`) with one more status line, matching the read-only "report, don't edit" posture already used there for `superseded_marker_count`/`duplicate_findings_block`.

## Implementation Steps

1. `soft_dep_hard_edge` gap kind + phrase list + tests.
2. `ac_flag_drift` gap kind + tests.
3. `format-check` reporting/`--kinds` wiring.
4. Refine-issue AC-vs-Program-Design prompt step.
5. Validate against FEAT-2942: both contradictions reported.

## Impact

- **Priority**: P3 — real but narrower than FEAT-3048/ENH-3045
- **Effort**: Low — two gap kinds in existing machinery plus one prompt step
- **Risk**: Low — reporting only; no auto-fix

## Related Key Documentation

- `.claude/CLAUDE.md` § Issue File Format — status enum and dependency semantics
- `docs/reference/DEFERRAL_CODES.md` — `deferred` is non-terminal for dependency edges

## Status

**Open** | Created: 2026-08-04 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-05T01:31:38 - `eb7fedb4-0dd1-4b7c-8880-6ff7b6346575.jsonl`
- `/ll:capture-issue` - 2026-08-04T20:50:27 - `2a9240a9-e6df-4ed5-ad2a-73a280bc7d8b.jsonl`
