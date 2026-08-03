---
id: ENH-2993
status: done
priority: P3
captured_at: '2026-08-02T13:43:01Z'
completed_at: '2026-08-03T01:17:15Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
- ENH-2992
testable: true
confidence_score: 100
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# Fold repeated Codebase Research Findings blocks into one per section

## Summary

Each `/ll:refine-issue` pass appends a fresh `### Codebase Research Findings`
subsection rather than merging into the one already present under the same H2.
Across repeated passes these accumulate — one issue carries **12** separate
blocks. Fold on write: one findings block per parent H2, with new bullets
merged into the existing block.

## Current Behavior

`commands/refine-issue.md` § Preservation Rule (lines 474-490) instructs each
pass to append a marked subsection:

```markdown
### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_
```

There is no instruction to detect an existing block under the same H2 and merge
into it, so every pass creates a new one.

The source file is also internally inconsistent about the heading level:
`commands/refine-issue.md:334` (§ Scope boundary) tells the pass to write gap
findings under `## Codebase Research Findings` — **H2**, not the H3 the
Preservation Rule template emits. Any fold implementation must either normalize
that variant or the line must be corrected to `###` as part of this work.

Measured across `.issues/` (2026-08-02):

| refine+wire passes | issues | median lines | ≥ share in appended blocks |
|---|---|---|---|
| 0 | 1,175 | 123 | 0% |
| 1 | 152 | 156 | 0% |
| 2 | 176 | 182 | 7% |
| 3 | 126 | 192 | 8% |
| 4 | 146 | 205 | 8% |
| 5+ | 1,119 | 263 | 17% |

(The share column is a lower bound — the measurement stops each block at the
next heading, so nested content is undercounted.)

Worst offenders by block count:

| Blocks | Issue |
|---|---|
| 12 | `ENH-2500` per-run-dir pending file and scope for prompt-across-issues |
| 12 | `ENH-2514` ll-loop flush audit trail on forced termination |
| 10 | `ENH-2511` capture mcp tool call telemetry |
| 10 | `ENH-2495` record session lifecycle handoff events |
| 9 | `ENH-2492` capture orchestration run outcomes into history db |

`ENH-2500` alone carries 5 blocks under distinct H2s plus repeats, at 364 total
lines.

## Expected Behavior

Before appending, refine checks whether a `### Codebase Research Findings`
subsection already exists under the target H2. If so, it appends its new
bullets to that block instead of creating a sibling. Result: at most one
findings block per H2, regardless of pass count.

## Motivation

Two costs, both borne by the implementer:

1. **Reading cost.** Five sibling blocks under one section means the reader
   must hold all five to know the current state of a claim — and later blocks
   frequently supersede earlier ones (24% of refined issues contain correction
   language; see ENH-2995).
2. **Context cost.** A 263-line median at 5+ passes against a 123-line
   unrefined baseline is a real token load on every headless session that reads
   the issue, and on every subsequent refine/confidence-check pass that reads
   it back.

Folding is purely additive-safe: no bullet is dropped, only relocated into the
sibling block that already exists.

## Proposed Solution

In `commands/refine-issue.md` § Preservation Rule, replace "append a
subsection" with "append to the existing subsection under this H2, or create it
if absent."

The section-locating primitive already exists and is already cited by this
skill — `commands/refine-issue.md:622` (§ 5c Gap-Analysis Mode, "Parse
Existing Issue into Section Map") points at
`scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()` for H2
extraction. The same approach locates an existing H3 within a sliced H2.

Note the constraint from `.claude/CLAUDE.md` § Automation: Scratch Pad and from
`ll-verify-skill-prose`: if this becomes a real merge algorithm (dedup, bullet
ordering, provenance-marker handling), it belongs in
`scripts/little_loops/` behind an `ll-issues` subcommand, not as prose in the
skill. A plain "find the existing H3 and append under it" instruction is fine
as prose; anything with dedup logic is not.

### Decisions (resolved during review)

**Provenance: one heading, one provenance line per merged batch, dated.**
The fold collapses the `### Codebase Research Findings` *heading* to one per
H2, but each merged batch keeps its own
`_Added by \`/ll:refine-issue\` — <YYYY-MM-DD> — based on codebase analysis:_`
line above its bullets. Rationale: pass boundaries are load-bearing downstream
and must survive the fold —

- ENH-2995's superseded-line carve-out
  (`commands/refine-issue.md:503-506`) fires **"same pass only … never from
  re-reading a prior pass's appended `### Codebase Research Findings` block"**.
  That rule currently keys on block boundaries; collapsing to a single
  undifferentiated bullet list would erase the discriminator it depends on.
- ENH-2992's contradiction/correction detection reads these blocks and relies
  on later findings superseding earlier ones — i.e. on chronology.

Per-batch provenance preserves both signals while still yielding one heading
per H2, which is all the reading/token cost this issue is about.

**`/ll:wire-issue` marker folding: out of scope, follow-up issue.**
`fold_research_findings()` parameterizes `sub_heading` and `marker` precisely
so wire-issue becomes a later *caller*, not a rewrite. Folding its four
subsections (9,377 bullets across 1,140 issues) has its own placement questions
(its blocks sit under H3 parents, not H2) and should not gate this change.

**Existing-corpus migration: no bulk sweep — but fold-on-touch, yes.**
No pass is made over the 1,140 already-refined issues to collapse their stacked
blocks. That decision stands, and it is about a *sweep*.

It does not settle the on-touch case, which is distinct: when
`fold-findings` writes into an H2 that **already** carries N stacked blocks,
it collapses all N into one, rather than appending to one and leaving N-1
siblings beside it. Rationale:

- Leaving them makes the fold a no-op on exactly the issues that motivated
  this issue. The corpus that has the problem is the refined corpus, and
  refine is what touches it.
- It is the only thing that makes `duplicate_findings_block` a usable in-pass
  signal. Without it the gap fires on pre-existing stacks the pass did not
  cause and cannot clear, and a permanently-red check trains the model to skim
  past § 6.7 entirely — degrading the three keys there that do work.
- It is within the operation this issue already sanctions. Collapsing N
  existing blocks is the same relocation-only transform as folding a new batch
  into one existing block: every bullet and every provenance line survives, in
  order. § Scope Boundaries' "no delete, no summarize, no dedup" is unchanged.

The backlog therefore drains as issues are worked, without a migration script
and without a flag day. Issues never refined again keep their stacks; that is
the accepted cost of no-sweep.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No Python code today implements "find an existing markdown subsection under
  a given H2, append bullets into it if present, else create it." The three
  existing section-extraction primitives are all H2-only and read-oriented:
  `_extract_section()` (`scripts/little_loops/issue_history/doc_synthesis.py:104-127`,
  first-match, returns `""` if absent), `_section_body_with_offset()`
  (`scripts/little_loops/issue_parser.py:200-219`, last-match, returns
  `(body, offset)` or `None`), and `_iter_h2_sections()`
  (`scripts/little_loops/issue_parser.py:787-802`, all H2 spans). None matches
  `###` — the one exception, `_heading_bodies()`
  (`scripts/little_loops/issue_parser.py:609-625`), already matches both `##`
  and `###` via `rf"^(#{{2,3}})\s+{{heading}}\s*$"` and returns **all**
  occurrence bodies as a list — i.e. it already surfaces the "N repeated
  blocks" symptom, read-only, consumed by
  `scripts/little_loops/cli/issues/check_decidable.py:546`.
- The closest write-side precedent for "find existing, merge in place" is
  `update_frontmatter()` (`scripts/little_loops/frontmatter.py:439-471`), but
  it operates on the YAML frontmatter block, not markdown body sections.
  `append_session_log_entry()` (`scripts/little_loops/session_log.py:197-226`)
  is the closest *body*-writing precedent and models exactly the merge shape
  this issue wants: `content.rfind("## Session Log\n")` locates the existing
  header, a new line item is inserted directly under it (no new header
  created), and `session_log.py` docs this as the same "last one wins"
  contract used by `_section_body_with_offset()`. Tested by
  `scripts/tests/test_session_log.py::TestAppendSessionLogEntry` — see
  `test_appends_to_existing_section` and
  `test_duplicate_session_log_headers_only_inserts_once`, which assert
  `content.count("## Session Log") == 1` after append. This is the pattern to
  extend for H3-under-H2 folding, not a bullet-accumulation merge.
- `commands/reconcile-issue.md` reads `### Codebase Research Findings`
  prose-instructed (no regex): it lists the heading as protected content it
  must never edit/reorder/delete (§ "Preserve untouched", lines 56-63) and as
  a read-only source of truth (§ "Source of truth for the rewrite", lines
  65-68; Step 3, lines 107-114 — "Every bullet under
  `### Codebase Research Findings`"). It reads "every bullet" with no
  occurrence-count assumption, so folding multiple sibling blocks into one
  (same heading, merged bullets) does not change what reconcile sees — it
  simply reads one block with more bullets instead of N blocks with fewer.
  Separately, `_OPTION_FALLBACK_SECTIONS = ("Codebase Research Findings",
  "Implementation Status")` (`scripts/little_loops/issue_parser.py:683`) is
  scanned by `count_enumerable_options()`/`count_unresolved_options()`
  (`issue_parser.py:970`, `:1065`) for `**Option A/B**` decision blocks —
  folding does not change this either, since a merged block is a strict
  superset of scannable content.
- `skills/wire-issue/SKILL.md` §§ 8a/8c (lines 325-404) confirm the same
  accumulation shape under a different marker
  (`_Wiring pass added by \`/ll:wire-issue\`:_`) across four subsections
  (`### Dependent Files (Callers/Importers)`, `### Documentation`,
  `### Tests`, `### Configuration`) plus a `### Wiring Phase` block under
  `## Implementation Steps`. Grepping the codebase for `Wiring pass added by`
  returns only that one skill file — no Python consumer exists, same as
  `### Codebase Research Findings` before this issue.
- `ll-issues` subcommands use one of two coexisting registration shapes in
  `scripts/little_loops/cli/issues/__init__.py`: inline-in-`main_issues()`
  (older, e.g. `append-log`) or an exported `add_X_parser(subs)` from the
  subcommand's own module (current convention for everything added in the
  ENH-2900s range, e.g. `add_research_triage_parser()` in
  `scripts/little_loops/cli/issues/research_triage.py:25` — its module docstring
  explains the CLI entry point exists specifically because
  `commands/refine-issue.md`'s only route to Python is `Bash(ll-issues:*)`,
  and without a registered subcommand "the change ships inert").

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — **three** write sites emit the subsection
  marker, not two; all must change together:
  - **line 427** (§ 5a, option-block placement) — writes a
    `### Codebase Research Findings` subsection into `## Proposed Solution`
    and carries two hard constraints the CLI must honor: the block *must*
    live under that exact H2 (it is the only section
    `count_enumerable_options()`/`count_unresolved_options()` scan), and the
    heading text takes **no `— suffix` decoration** because the probes match
    headings by exact name.
  - **lines 474-490** (§ Preservation Rule, Step 5a) — the canonical template.
  - **line 680** (§ 5c Gap-Analysis Mode → "#### 5. Apply Additive Changes
    Only") — a *distinct mode* with its own rules (additive-only, never
    removes, `--gap-analysis` does not consume `max_refine_count`). This is
    **not** § Step 6 "Update Issue File", which sits at line 710 and contains
    no findings-marker instruction at all.
  - § Scope boundary (line 334) wrongly says `##` and must be corrected
    to `###`
  - § 6.7 Prose Dependency & Program Design Gate (line 741) — add
    `duplicate_findings_block` to the inspected `format-check` keys (see
    § Adoption risk)
- `.kimi-code/skills/ll-refine-issue/SKILL.md` — a **fourth** write site
  (line 485 carries the identical `_Added by \`/ll:refine-issue\` — based on
  codebase analysis:_` template). This is a maintained host mirror, not dead
  weight: commit `cf1c8e52` (ENH-2996) updated `skills/wire-issue/`,
  `.gemini/skills/wire-issue/` and `.kimi-code/skills/wire-issue/` in one
  commit. No test enforces parity, so a stale mirror fails silently — and
  failing silently on one host is exactly the inert-adoption shape
  § Adoption risk exists to prevent, just scoped to Kimi. Note the fan-out is
  asymmetric: there is **no** `.gemini/skills/*refine*` mirror, so this is one
  extra file, not two. The `ll-issues` CLI is host-agnostic (pip package), so
  the mirrored prose can call the same subcommand verbatim.
  gap to `check_format_gaps()` (gap dataclass ~256-292, detection ~546-559).
  **The detector cannot reuse the existing `_heading_bodies()` call** — see
  Implementation Step 13.
- `scripts/little_loops/cli/issues/format_check.py` — print the new gap
  (help text line 64, print loop ~156-157)
- `scripts/little_loops/cli/issues/__init__.py` — extend the `format-check`
  gap-code list in the usage banner (line 124)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issues/fold_research_findings.py` (new) — core `find_subsections()`/`fold_research_findings()` logic, mirroring the core/CLI split used by `scripts/little_loops/issues/research_triage.py` + `scripts/little_loops/cli/issues/research_triage.py`
- `scripts/little_loops/cli/issues/fold_findings.py` (new) — CLI wrapper: `add_fold_findings_parser()`, `cmd_fold_findings()`, mirroring `scripts/little_loops/cli/issues/research_triage.py`
- `scripts/little_loops/cli/issues/__init__.py` — register the new subcommand (import block ~77-80, `add_fold_findings_parser(subs)` call ~928, dispatch branch ~1013-1014)

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — reads `### Codebase Research Findings`
  blocks as its input; must still parse correctly after folding
- TBD — use grep to find other readers of the marker string

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` — home of `_heading_bodies()` (609-625, 2 call sites at 546/556 inside `check_format_gaps()`), `_section_body_with_offset()` (200-228, H2-only, last-match-wins), `_iter_h2_sections()` (787-802, H2-only); `find_subsections()` extends the two-level regex already used by `_heading_bodies()`
- `scripts/little_loops/session_log.py` — `append_session_log_entry()` (197-226) is the closest "find last header via `rfind`, insert in place" precedent the new fold insert should model
- `scripts/little_loops/cli/issues/__init__.py` — Shape-B subcommand wiring for the new `fold-findings` subcommand: import block (~77-80), `add_fold_findings_parser(subs)` call (~928), `if args.command == "fold-findings"` dispatch branch (~1013-1014) — same 3-point pattern used by `add_research_triage_parser`
- `skills/decide-issue/SKILL.md` — reads `### Codebase Research Findings` blocks for Phase 3 option extraction; must still parse correctly after folding
- `scripts/little_loops/loops/autodev.yaml:1864` — `reconcile_current` state comment references `Codebase Research Findings`

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()` —
  the H2 slicing primitive refine already cites for section parsing
- `skills/wire-issue/SKILL.md` Phase 8c — the parallel
  `_Wiring pass added by …_` marker with the same accumulation behavior

### Tests
- TBD — identify test files to update

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_log.py::TestAppendSessionLogEntry` (`test_appends_to_existing_section`, `test_duplicate_session_log_headers_only_inserts_once`, `test_multiple_appends_create_multiple_entries`) — direct test-shape template for the new fold test module: single-existing-section, duplicate-headers-already-present, multi-call idempotency
- `scripts/tests/test_fold_research_findings.py` (new) — unit tests for `find_subsections()`/`fold_research_findings()`, following the template above
- `scripts/tests/test_issue_parser.py` — no existing test constructs multiple stacked `### Codebase Research Findings` blocks under one H2; add a pre-fold baseline test (current N-blocks behavior via `_heading_bodies()`) alongside the new fold coverage
- `scripts/tests/test_ll_issues_research_triage.py` — closest CLI round-trip template (`_invoke(argv)` → `main_issues()`, real git + `.issues/` fixture) for testing `ll-issues fold-findings` end-to-end
- `scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective` — exercises `_heading_bodies()` indirectly via `check_format_gaps()`; fixtures use single-occurrence blocks so folding shouldn't change assertions, but re-run to confirm
- `scripts/tests/test_reconcile_issue_command.py`, `scripts/tests/test_decide_issue_skill.py` — doc-text assertions that `commands/reconcile-issue.md` / `skills/decide-issue/SKILL.md` mention the heading; unaffected by folding logic but re-run to confirm

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_session_log.py::TestAppendSessionLogEntry` is the
  closest existing test shape for this behavior — it asserts
  `content.count("## Session Log") == 1` after repeated appends
  (`test_appends_to_existing_section`,
  `test_duplicate_session_log_headers_only_inserts_once`). A new fold-on-write
  primitive should follow the same assertion shape:
  `content.count("### Codebase Research Findings") <= 1` per parent H2 after
  N appends, plus a bullet-count-preserved check (Success Metrics already
  states this).

### Documentation
- TBD — docs that need updates

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — full `ll-*` CLI reference; needs a new `ll-issues fold-findings` entry (including its stdin contract) and the new `duplicate_findings_block` code in the `format-check` gap list
- `docs/reference/API.md` — documents the section-extraction primitives and heading structure; needs a note on the new fold primitive
- `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/COMMANDS.md` — mention "Codebase Research Findings"; confirm still accurate after folding lands
- `docs/observability/realized-savings-verification.md` — mentions "Codebase Research Findings"; confirm still accurate after folding lands

### Configuration
- N/A

## Program Design

### Types

- No new dataclasses — this is a pure text-transform on existing markdown
  strings, matching `_extract_section()`'s and `append_session_log_entry()`'s
  own signatures (both take/return `str`).

### Signatures

- `find_subsections(content: str, parent_heading: str, sub_heading: str) -> list[tuple[str, int, int]]`
  — locates **every** existing `sub_heading` (H3) nested inside the slice
  bounded by `parent_heading` (H2); returns a list of
  `(body, start_offset, end_offset)` spans in document order, empty if absent.

  **Returns all matches, not one.** A singular
  `-> tuple[...] | None` cannot express the corpus's common case: ~1,140
  already-refined issues carry N>1 stacked blocks under a single H2, one of
  them 12. The two primitives cited as precedent disagree on which one a
  singular return would pick — `_extract_section()`
  (`scripts/little_loops/issue_history/doc_synthesis.py:104-127`) is
  first-match, `_section_body_with_offset()`
  (`scripts/little_loops/issue_parser.py:200-219`) is last-match-wins — so a
  singular signature does not merely under-specify the multi-match case, it
  invites the implementer to inherit whichever convention they read last.
  Returning the full list makes the fold-on-touch collapse (§ Decisions)
  expressible and makes the `duplicate_findings_block` detector fall out of
  the same call (`len(spans) > 1` **within one H2 slice**).

  Extends the two-level regex already used by
  `_heading_bodies()` (`scripts/little_loops/issue_parser.py:609-625`,
  `rf"^(#{{2,3}})\s+{{heading}}\s*$"`) with an H2-scoping pass borrowed from
  `_iter_h2_sections()` (`scripts/little_loops/issue_parser.py:787-802`).

  **End boundary**: `end_offset` is the start of the next heading of level
  **≤ 3** (`##` or `###`), or EOF. This is not academic — a findings block is
  routinely followed by a *sibling* H3 (in this very file, the Integration Map
  block is followed by `### Documentation`), so an end boundary that scans only
  to the next `##` would splice new bullets past unrelated subsections.

  **Scoping rule**: findings blocks are addressed by their nearest **H2**
  ancestor, even when the bullets logically belong to an H3 beneath it (e.g.
  `### Files to Modify` under `## Integration Map`). One block per H2 is the
  invariant; H3-parented markers are `/ll:wire-issue`'s shape and are out of
  scope (see § Decisions).
- `fold_research_findings(content: str, parent_heading: str, new_content: str, sub_heading: str = "Codebase Research Findings", marker: str = "_Added by `/ll:refine-issue` — based on codebase analysis:_") -> str`
  — three cases, on the spans `find_subsections()` returns for
  `parent_heading`:

  **`new_content` is an opaque markdown block, not a parsed bullet list.**
  A `new_bullets: list[str]` signature cannot carry the § 5a payload:
  `commands/refine-issue.md:409-416` writes `**Option A**: …` /
  `**Option B**: …` / `**Recommended**: …` blocks at column 0, which are not
  `- ` bullets, and it is precisely that text
  `count_enumerable_options()`/`count_unresolved_options()` must still find
  afterward. Any bullet-parsing step therefore either drops the option labels
  or glues them onto a neighbouring bullet, breaking the one consumer this
  site exists to serve. The transform appends the block verbatim (trailing
  newlines normalized, nothing else touched), which also makes the
  multi-line-continuation hazard structurally impossible rather than a rule
  the implementer must remember. "Zero bullets lost" stays measurable by
  counting `^- ` lines before/after — the function simply never needs that
  count itself.

  `sub_heading` is parameterized (not hard-coded) so `/ll:wire-issue` becomes
  a later *caller* rather than a rewrite (§ Decisions); this issue's callers
  all pass the default.

  - **0 spans** — create the heading + dated marker + content block, same as
    the current refine-issue.md prose template. **Position: at the end of the
    `parent_heading` H2 slice**, after any nested H3 subsections, immediately
    before the next `##` (or EOF). This must be pinned, not left to the
    implementer: for an H2 like `## Integration Map` that owns
    `### Files to Modify` … `### Configuration`, "end of slice", "after the
    last H3" and "before the first H3" produce three different files, and
    non-deterministic placement across passes would defeat the one-block-per-H2
    invariant this issue is about. End-of-slice also matches
    `append_session_log_entry()`'s insert-relative-to-a-known-anchor shape.
  - **1 span** — append `new_content` beneath it under a fresh dated
    provenance line (same insert-after-header shape as
    `append_session_log_entry()`,
    `scripts/little_loops/session_log.py:197-226`).
  - **N>1 spans (fold-on-touch, § Decisions)** — collapse all N into the
    **first** span's position, concatenating their bodies in document order,
    then append the new batch. Every bullet and every existing provenance
    line is carried over verbatim; the N-1 later headings are removed and
    nothing else is. First position, not last, because it is the one whose
    surrounding prose was written to introduce the block.

  Pure function on `str` — file I/O and the `--dry-run` branch live in the CLI
  wrapper, so the dry-run path is "call the transform, print instead of write"
  rather than a second code path.

  **Not idempotent on bullets, by design.** § Scope Boundaries forbids dedup,
  so two calls with identical bullets legitimately yield the bullets twice.
  The invariants are the **heading count** (exactly 1 per H2 after any call)
  and **provenance-line conservation** (folding a batch into a section that
  held M provenance lines leaves M+1; collapsing N pre-existing blocks
  carrying M lines total leaves M+1, never fewer). Tests assert those, not
  bullet-set equality.
- `add_fold_findings_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser`
  — registers the CLI entry point, following the current convention (Shape B)
  demonstrated by `add_research_triage_parser()`
  (`scripts/little_loops/cli/issues/research_triage.py:25`), whose own module
  docstring states the reason this class of entry point exists:
  `commands/refine-issue.md`'s only route into Python is `Bash(ll-issues:*)`.
  Flags: `--section` (required), `--dry-run`, `--no-create`.

### CLI Input Channel

**Content arrives on stdin, never in argv.** The findings text is LLM-authored
markdown containing backticks, `$`, `!`, em-dashes and newlines; routing it
through an argv-quoted `Bash(ll-issues:*)` invocation is the single most likely
way for this change to ship broken. `ll-issues prioritize` already establishes
stdin as the in-repo convention for structured input ("apply a priority map
from stdin JSON", `cli/issues/__init__.py:128`).

Shape:

```bash
ll-issues fold-findings ENH-2993 --section "Program Design" <<'EOF'
- [Finding 1 with file path and anchor reference]
- [Finding 2 with file path and anchor reference]
EOF
```

- `issue_id` positional, resolved via `_resolve_issue_id()` like
  `cmd_research_triage()`.
- `--section` names the parent H2 by exact heading text (without the `## `),
  matched case-insensitively with surrounding whitespace stripped.
- stdin is a **verbatim markdown block** and is never parsed into bullets. It
  is inserted byte-for-byte apart from trailing-newline normalization; the
  blank line between the provenance marker and the block is supplied by the
  command, which also supplies the dated provenance line itself (see
  § Decisions) so the caller never hand-writes the marker. Two payload shapes
  must both survive and neither is a flat bullet list: findings bullets wrap
  across multiple lines with a 2-space continuation indent (every bullet in
  this issue does), and the § 5a site (`commands/refine-issue.md:409-416`)
  sends `**Option A**` / `**Option B**` / `**Recommended**` blocks at column 0
  with no leading `- ` at all. Verbatim passthrough is what makes both work;
  see § Signatures for why `new_bullets: list[str]` cannot.
- Exit 1 only on unresolvable issue ID. Creating a missing findings block is
  the ordinary success path, not an error.

**Missing parent H2 must not be a hard error.** Refine *creates* sections that
do not yet exist — § Enrichment Rules populates `## Integration Map`,
`## Program Design` and `## Root Cause` on issues that lack them. A contract of
"exit 1 on unknown `--section`" errors on exactly that path and pushes the model
back to hand-`Edit`, which is precisely the inert-adoption failure mode
§ Adoption risk exists to prevent. Resolution: when `--section` names an H2 that
is absent, **create it** in v2.0 template order (the same ordering Step 6 point
4 already requires of refine) and write the findings block beneath it. Reserve a
distinct nonzero exit (2) for "section absent and `--no-create` was passed", so
the prose fallback is reachable but never the default.

**`--dry-run` is required, and its absence is a regression.**
`commands/refine-issue.md:712` — "Skip file modifications if `DRY_RUN` is true"
— is enforceable today only because this write goes through the
`Edit(.issues/**)` tool, which the command's `allowed-tools` constrains. A
Bash-mediated `ll-issues fold-findings` sits entirely outside that restriction,
so absent an explicit flag, `/ll:refine-issue --dry-run` would begin mutating
issue files. The subcommand takes `--dry-run` (print the resulting block to
stdout, write nothing — precedent: `ll-issues anchor-sweep --dry-run`,
`scripts/little_loops/cli/issues/anchor_sweep.py:38-45`), and the Step 5a prose
must gate the Bash invocation on `DRY_RUN`.

### Call Path

`commands/refine-issue.md` Step 5a -> `Bash("ll-issues fold-findings ...")`
-> `cmd_fold_findings()` (new, `scripts/little_loops/cli/issues/`) ->
`fold_research_findings()` -> `find_subsections()` -> `append_session_log_entry()`
(existing precedent for the insert-after-header shape,
`scripts/little_loops/session_log.py:197`) -> file write.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `append_session_log_entry()` (`scripts/little_loops/session_log.py:197-246`)
  operates on raw string content via literal substring search
  (`content.rfind("## Session Log\n")`) and simple splicing — it is a
  two-branch existence check (section present vs. absent) with **no
  merge/dedup logic**: it inserts exactly one new line directly under a fixed,
  single top-level heading text. It is not itself heading-level-aware or
  parent-scoped. `find_subsections()` cannot reuse it as-is — it needs
  `_heading_bodies()`'s regex approach instead
  (`scripts/little_loops/issue_parser.py:609-625`,
  `rf"^(#{{2,3}})\s+{{heading}}\s*$"` plus an end-boundary scan to the next
  equal-or-higher-level heading), because it must locate an H3 *nested inside*
  a variable H2 parent, not a single fixed H2 anywhere in the file.
- `_heading_bodies()`'s two call sites in `check_format_gaps()`
  (`issue_parser.py:546-559`) already tolerate N>1 matching
  `### Codebase Research Findings` blocks today with no malfunction — both
  flatten all returned bodies through a single `any(...)` (existence-based,
  not per-block), so today's duplicate-block accumulation causes document
  bloat but does not break the `unmarked_superseded_directive` gap
  computation. This confirms folding is purely a readability/token-cost fix,
  not a correctness fix for the read side.
- Confirmed mechanism gap: the current `### Codebase Research Findings` write
  (`commands/refine-issue.md` § Preservation Rule, lines 474-490, and Step 6
  "Update Issue File", lines 710-718) is **100% prose-instructed direct `Edit`
  tool use** by the LLM — no Python primitive or CLI call is invoked for this
  specific write today (unlike Step 6.5's `## Session Log` append, which
  already routes through `ll-issues append-log` -> `append_session_log_entry()`
  with prose-Edit only as its documented fallback). Routing findings-block
  writes through a new `ll-issues fold-findings` CLI call, as this section's
  Call Path proposes, is therefore a first-time introduction of CLI-mediation
  for this write path, not a swap between two existing mechanisms.

### Deviations

_2026-08-02 — implementation departed from the design above in one place:_

- **Empty stdin exits 1, not 0.** § CLI Input Channel pins "Exit 1 only on
  unresolvable issue ID". Implemented as: unresolvable ID **or empty stdin**
  exits 1. Rationale: the likeliest way this command is mis-invoked is a
  botched heredoc, and the "only" clause was written to keep the *create* paths
  (missing findings block, missing H2) off the error branch — which they are.
  Exiting 0 on an empty payload would render a corrupted invocation as a
  successful fold in the caller's transcript, defeating the same adoption
  signal § Adoption risk exists to protect. Exit 2 stays reserved for
  "section absent under `--no-create`" as specified.
- **`ensure_section()` is a separate exported function**, not folded into
  `fold_research_findings()`. § Signatures pins `fold_research_findings()` as a
  pure `str` transform; deriving v2.0 template order requires reading the
  per-type sections JSON via config, so H2 creation lives in its own pure-`str`
  helper (`ensure_section(content, heading, order)`) that the CLI calls first
  with the order it resolved. Behavior matches the spec exactly; only the
  seam moved.

## Implementation Steps

1. `find_subsections()` and `fold_research_findings()` exist in
   `scripts/little_loops/` (not `commands/refine-issue.md` prose) per the
   Proposed Solution's constraint that merge/dedup logic belongs in Python
   behind an `ll-issues` subcommand — a plain "find and append" instruction is
   the only part that may stay as prose.
2. A new `ll-issues fold-findings` (or similarly named) subcommand is
   registered via the current `add_X_parser(subs)` convention (Shape B, per
   `add_research_triage_parser()` in
   `scripts/little_loops/cli/issues/research_triage.py:25`), reachable from
   `commands/refine-issue.md`'s `Bash(ll-issues:*)` allowed-tools scope.
3. All **three** `### Codebase Research Findings` write sites in
   `commands/refine-issue.md` are updated to call the new subcommand instead of
   emitting the template by hand — they share the marker convention and must
   change together or the fold is only partial:
   - **line 427** (§ 5a option-block placement into `## Proposed Solution`) —
     the call must preserve this site's two constraints: the block stays under
     that exact H2 (`count_enumerable_options()` scans only there) and the
     heading takes no `— suffix` decoration.
   - **lines 474-490** (§ Preservation Rule, Step 5a).
   - **line 680** (§ 5c Gap-Analysis Mode → "#### 5. Apply Additive Changes
     Only") — a separate mode, *not* Step 6 "Update Issue File" (line 710,
     which carries no marker instruction). Its additive-only guarantee is
     unchanged by the fold, since folding is relocation.

   The prose must state the CLI is the *only* route and that the heading and
   provenance line are never hand-written, or the change ships inert
   (§ Adoption risk). Each call site is gated on `DRY_RUN` (or passes
   `--dry-run`), preserving `commands/refine-issue.md:712`'s "Skip file
   modifications if `DRY_RUN` is true" — which the Bash-mediated write no
   longer inherits from the `Edit(.issues/**)` tool restriction.
   § Scope boundary (line 334) is corrected from `##` to `###` in the same
   pass.
   The same three prose changes are mirrored into
   `.kimi-code/skills/ll-refine-issue/SKILL.md` (its template lives at line
   487), per the mirror-maintenance precedent in commit `cf1c8e52`, which
   updated the plugin skill and both host mirrors together. No `.gemini`
   refine mirror exists, so this is one additional file, not two. If the
   mirror is deliberately skipped, say so in § Scope Boundaries rather than
   leaving it silently stale — nothing tests parity.
4. After a second `/ll:refine-issue --auto` pass against the same H2 in a
   scratch issue file, `content.count("### Codebase Research Findings")`
   under that H2 is 1, and the bullet count equals the sum of both passes'
   contributions — mirroring the assertion shape of
   `test_duplicate_session_log_headers_only_inserts_once` in
   `scripts/tests/test_session_log.py`.
5. `commands/reconcile-issue.md`'s "every bullet under
   `### Codebase Research Findings`" read (Step 3, lines 107-114) still finds
   all bullets after folding — verified by running reconcile against the same
   scratch issue file and confirming its extracted bullet count is unchanged.
6. `python -m pytest scripts/tests/ -k research_findings` (or the equivalent
   new test module) passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Create `scripts/little_loops/issues/fold_research_findings.py` (core
   `find_subsections()`/`fold_research_findings()` logic) and
   `scripts/little_loops/cli/issues/fold_findings.py` (CLI wrapper:
   `add_fold_findings_parser()`, `cmd_fold_findings()`), mirroring the
   `research_triage.py` / `cli/issues/research_triage.py` core+CLI split.
8. Register the new subcommand in `scripts/little_loops/cli/issues/__init__.py`:
   import block (~lines 77-80), `add_fold_findings_parser(subs)` call (~line
   928), and `if args.command == "fold-findings"` dispatch branch (~lines
   1013-1014) — the same 3-point wiring used by `add_research_triage_parser`.
9. Add `scripts/tests/test_fold_research_findings.py` following the
   `TestAppendSessionLogEntry` shape (`test_session_log.py:133-256`):
   single-existing-section fold, duplicate-headers-already-present fold, and
   **heading-count invariance across N calls** — after N folds with identical
   bullets, `content.count("### Codebase Research Findings")` under the target
   H2 is 1 and the provenance-line count is N. Do **not** assert bullet-set
   idempotency: § Scope Boundaries forbids dedup, so repeated identical bullets
   are the specified behavior, not a defect.
10. Add a pre-fold baseline test in `scripts/tests/test_issue_parser.py`
    constructing an issue body with 3 stacked `### Codebase Research Findings`
    blocks under one H2, asserting `_heading_bodies()` returns 3 bodies before
    folding lands (no such fixture exists today).
11. Update `docs/reference/CLI.md` with the new `ll-issues fold-findings`
    entry, including the stdin contract, `--section`, `--dry-run`,
    `--no-create`, and the exit-code table (0 success / 1 unresolvable issue /
    2 section absent under `--no-create`).
12. Confirm `skills/decide-issue/SKILL.md`'s Phase 3 option extraction still
    parses correctly against a folded issue file (manual or scripted check
    against the scratch issue file from Implementation Step 4).
13. Add the `duplicate_findings_block` gap to `check_format_gaps()`
    (`scripts/little_loops/issue_parser.py`, gap dataclass ~256-292, detection
    near the existing `_heading_bodies()` call at ~546-559), surface
    it in `scripts/little_loops/cli/issues/format_check.py` (help text line 64,
    print loop ~156-157) and in the usage banner
    (`scripts/little_loops/cli/issues/__init__.py:124`). Test alongside
    `scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective`.

    **The detector cannot reuse that `_heading_bodies()` call.**
    `_heading_bodies()` (`issue_parser.py:609-625`) is document-wide and
    returns bodies with **no parent-section information**, so `len(bodies) > 1`
    cannot express "per H2": a compliant document with one findings block under
    each of three H2s returns 3 and would be flagged. The detector must slice
    with `_iter_h2_sections()` (`issue_parser.py:787-802`) and count matching
    H3s **within each slice**, flagging only slices with count > 1. Two further
    traps: `_heading_bodies()`'s regex `rf"^(#{{2,3}})\s+{{heading}}\s*$"`
    matches `##` *and* `###`, so the line-334 `## Codebase Research Findings`
    variant this issue corrects would also register as a duplicate; and the
    slice end boundary must be the next `##` while the H3 end boundary is the
    next heading of level ≤ 3 (see § Signatures).
14. Add `duplicate_findings_block` to the `format-check` keys inspected by
    `commands/refine-issue.md` § 6.7 (line 741). Without it the adoption metric
    is corpus-wide and after-the-fact; inside 6.7 it catches an inert pass **in
    the same pass that caused it**, which is what § Adoption risk needs.

    **Model the prose on `superseded_marker_count`, not on `prose_dep_drift`.**
    § 6.7's other keys all promise a clearing remedy — "add the missing edge …
    re-run `format-check` to confirm the drift clears", "revise that section
    **once** … confirm it clears". `duplicate_findings_block` cannot promise
    that: fold-on-touch (§ Decisions) clears duplicates in the H2s this pass
    wrote to, but an issue may carry stacks under H2s the pass never touched,
    and those are not this pass's to fix. `superseded_marker_count` is the
    existing precedent for exactly this shape — "refine **annotates** but never
    rewrites … Do not attempt the rewrite here. Surface it: report the count in
    Step 8's output." Follow it:

    - Non-empty **and the pass wrote to that H2** → the model hand-wrote the
      heading instead of calling `fold-findings`; re-issue that write through
      the CLI and confirm it clears. This is the adoption failure the gate
      exists for.
    - Non-empty **under an H2 the pass did not touch** → pre-existing stack,
      not caused here. Report the count in Step 8's output and do not edit.
      Folding it is a side effect of a future pass that touches that section,
      per the no-sweep decision.

    Write the two branches explicitly. Collapsed into one instruction the model
    will either fix nothing (reading it as informational) or reach past
    `fold-findings` to hand-edit untouched sections (violating no-sweep).
15. Verify fold-on-touch: fold a new batch into an H2 carrying 3 stacked
    blocks; assert the result has 1 heading, 4 provenance lines, and a bullet
    count equal to the 3 originals plus the new batch — in document order,
    positioned where the **first** original block stood. Assert
    `duplicate_findings_block` is empty for that H2 afterward, and still
    non-empty for a second, untouched H2 in the same file (the no-sweep
    boundary).
16. Verify the stdin payload survives byte-for-byte, on both shapes the callers
    actually send:
    - a bullet list containing backticks, `$`, `!` and an em-dash, including a
      bullet whose text wraps across three lines with a 2-space continuation
      indent, lands byte-identical (no re-wrapping, no bullet splitting);
    - an `**Option A**` / `**Option B**` / `**Recommended**` block at column 0
      — the § 5a payload, which contains **no** `- ` bullets — lands
      byte-identical under `--section "Proposed Solution"`, and
      `count_enumerable_options()` returns 2 against the resulting file.
      This is the regression test for the verbatim-passthrough decision
      (§ Signatures); a bullet-parsing implementation fails exactly here.
17. Verify `--dry-run` writes nothing: fold into a scratch issue with
    `--dry-run`, assert the block is printed to stdout and the file's bytes are
    unchanged. Then verify `/ll:refine-issue --dry-run` end-to-end leaves the
    issue file untouched — the prose gate, not just the flag. Include the
    N>1-collapse case: dry-run against a stacked section must not collapse it.
18. Verify the missing-H2 path: fold with `--section "Program Design"` into an
    issue lacking that heading creates it in template order and exits 0;
    the same call with `--no-create` exits 2 and writes nothing.
19. Verify the ENH-2995 interaction: after two folds into one block, the
    superseded-annotation carve-out still fires only on the current pass's
    bullets — the per-batch provenance line is what makes "this pass's
    findings" identifiable once block boundaries are gone.

## Impact

- Reduces refined-issue length growth; the 5+-pass median (263 lines) should
  fall toward the 2-3 pass range.
- Makes the findings block a single readable statement of current knowledge per
  section rather than a chronological log.
- Improves the input quality for `/ll:reconcile-issue` and for ENH-2992's
  contradiction detection.

## Success Metrics

- **Any H2 written to by a post-change pass carries exactly one
  `### Codebase Research Findings` heading afterward** — whether the pass
  appended to one existing block or collapsed N stacked ones (fold-on-touch,
  § Decisions). Scoped to *touched* H2s: untouched sections in the un-migrated
  corpus keep their stacks by decision, so a corpus-wide assertion would be
  false on day one and unmeasurable.
- Measured by the new `duplicate_findings_block` gap in `ll-issues
  format-check`, evaluated per-H2: for every H2 a pass wrote to, the gap is
  empty afterward. This also catches the adoption failure mode below.
- Zero bullets lost across a fold or a collapse (verifiable by bullet count
  before/after).
- Provenance lines are conserved, never merged: folding a batch into a section
  holding M `_Added by …_` lines leaves M+1 under one heading — including the
  N>1 collapse case, where the M lines come from the pre-existing stacked
  blocks (§ Decisions).
- Secondary, not a gate: the count of issues carrying stacked blocks trends
  down over time as refine touches them. No target — it is the observable that
  tells us fold-on-touch is actually draining the backlog rather than the gate
  being permanently red.

### Adoption risk this metric guards

Per the Codebase Research Findings above, this write is **100% prose-instructed
`Edit` today** — routing it through `ll-issues fold-findings` is the first
CLI-mediation of this path. If the skill prose is updated but the model keeps
hand-writing the heading, the change ships inert and silently. The
`duplicate_findings_block` gap is what makes that visible rather than assumed,
which is why it is in scope here and not a follow-up.

The gap must be wired into **§ 6.7's** in-pass `format-check` inspection
(Implementation Step 14), not only into corpus-wide reporting. A corpus-wide
count is measured after the fact by whoever happens to run `format-check`; the
6.7 hook fails the pass that hand-wrote the heading, in that pass, which is the
only feedback loop tight enough to actually prevent inert adoption. Note the
three-site fan-out (§ Files to Modify): partial adoption — CLI at Step 5a,
hand-`Edit` at line 427 or 680 — is the likeliest failure shape, and is exactly
what a per-H2 duplicate count detects.

Fold-on-touch is what keeps that gate honest. Without it the gap is non-empty
on most refined issues from day one for reasons the pass did not cause, the
model learns the key is noise, and the adoption signal is lost inside it —
which is why the two are decided together (§ Decisions) rather than the
collapse being deferred as a nicety.

## Scope Boundaries

- Does **not** delete, summarize, or dedupe findings content — folding is
  relocation only. This holds for the N>1 collapse too: every bullet and every
  provenance line from the collapsed blocks survives in document order.
- Does **not** amend the Preservation Rule's overwrite prohibition
  (that is ENH-2995).
- Does **not** sweep the existing corpus — no migration script, no flag day;
  decided, not deferred (§ Decisions). Pre-existing stacks are collapsed only
  as a side effect of a pass that writes to that H2 (fold-on-touch), so an
  issue never refined again keeps its stack indefinitely. The
  `duplicate_findings_block` gap keeps the remaining backlog visible.
- Does **not** fold `/ll:wire-issue`'s `_Wiring pass added by …_` markers —
  follow-up issue; the primitive is parameterized so wire-issue becomes a
  caller (§ Decisions).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/refine-issue.md` | Contains the append instruction being changed |
| `commands/reconcile-issue.md` | Downstream consumer of these blocks |

## Resolution

**Implemented 2026-08-02.**

- `scripts/little_loops/issues/fold_research_findings.py` (new) —
  `find_subsections()` (all H3 spans inside a named H2 slice, end-boundary at
  the next heading of level ≤ 3), `fold_research_findings()` (0 / 1 / N>1
  cases, relocation-only), `ensure_section()`, `dated_marker()`.
- `scripts/little_loops/cli/issues/fold_findings.py` (new) — `ll-issues
  fold-findings`, stdin-verbatim, `--section` / `--dry-run` / `--no-create`,
  exit table 0/1/2. Registered in `cli/issues/__init__.py` (import, parser,
  dispatch, usage banner).
- `duplicate_findings_block` gap added to `FormatGaps` and
  `check_format_gaps()` via `_duplicate_findings_blocks()` — per-H2, `###`-only,
  deliberately *not* built on `_heading_bodies()` (both traps in Step 13
  avoided). Surfaced in `cli/issues/format_check.py` and the usage banner.
- All four prose write sites updated to route through the CLI:
  `commands/refine-issue.md` § Scope boundary (`##` → `###`), § 5a option-block
  placement, § Preservation Rule (new § Writing Findings Blocks), § 5c
  Gap-Analysis; plus the new `duplicate_findings_block` branch pair in § 6.7.
  Mirrored verbatim into `.kimi-code/skills/ll-refine-issue/SKILL.md`.
- Docs: `docs/reference/CLI.md` (new subcommand entry + gap class + JSON
  payload example), `docs/reference/API.md` (subpackage note).
- Tests: `scripts/tests/test_fold_research_findings.py` (35),
  `scripts/tests/test_ll_issues_fold_findings.py` (11 CLI round-trips),
  `TestDuplicateFindingsBlock` in `test_ll_issues_format_check.py` (3),
  `TestStackedFindingsBlocks` in `test_issue_parser.py` (3). Full suite:
  18,067 passed, 42 skipped.
- Validated end-to-end against real corpus data (`ENH-2500`, dry-run).

See § Program Design → Deviations for the two departures from the pinned design.

## Session Log
- `/ll:manage-issue` - 2026-08-03T01:17:07 - `0fce812c-d523-4ea4-b4dd-42b9b206b67c.jsonl`
- `/ll:ready-issue` - 2026-08-03T00:40:02 - `0d47f54d-0d51-4508-89b2-eddb78936892.jsonl`
- `/ll:confidence-check` - 2026-08-03T00:32:36 - `ee2cf08a-9d4e-4629-b2ec-7211d56b5a4e.jsonl`
- `/ll:confidence-check` - 2026-08-02T23:53:12 - `42a54472-d0ba-4ed3-ba41-1bd83e5ba46c.jsonl`
- `/ll:confidence-check` - 2026-08-02T21:57:18 - `122b9e35-a883-466b-b221-9c07cbc675a2.jsonl`
- `/ll:confidence-check` - 2026-08-02T21:29:09 - `a19bb83d-629a-488d-832c-2afbb30f5117.jsonl`
- `/ll:refine-issue` - 2026-08-02T21:18:58 - `5927db07-ad5f-4874-b0e1-25eb77fc4c20.jsonl`
- `/ll:wire-issue` - 2026-08-02T21:06:13 - `fa4f5cf7-5457-4423-9741-a8025cdbaf37.jsonl`
- `/ll:refine-issue` - 2026-08-02T20:56:54 - `bc3cf078-a345-4297-857c-b20009b9e1f3.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
