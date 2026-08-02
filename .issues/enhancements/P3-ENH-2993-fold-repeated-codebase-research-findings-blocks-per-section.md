---
id: ENH-2993
status: open
priority: P3
captured_at: '2026-08-02T13:43:01Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
- ENH-2992
testable: true
confidence_score: 98
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
skill — `commands/refine-issue.md:546` points at
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

**Existing-corpus migration: no.**
The 1,140 already-refined issues are left alone. The `duplicate_findings_block`
format-check gap (below) surfaces them if that decision is revisited.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No Python code today implements "find an existing markdown subsection under
  a given H2, append bullets into it if present, else create it." The three
  existing section-extraction primitives are all H2-only and read-oriented:
  `_extract_section()` (`scripts/little_loops/issue_history/doc_synthesis.py:104-127`,
  first-match, returns `""` if absent), `_section_body_with_offset()`
  (`scripts/little_loops/issue_parser.py:200-219`, last-match, returns
  `(body, offset)` or `None`), and `_iter_h2_sections()`
  (`scripts/little_loops/issue_parser.py:758-773`, all H2 spans). None matches
  `###` — the one exception, `_heading_bodies()`
  (`scripts/little_loops/issue_parser.py:580-596`), already matches both `##`
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
  "Implementation Status")` (`scripts/little_loops/issue_parser.py:654`) is
  scanned by `count_enumerable_options()`/`count_unresolved_options()`
  (`issue_parser.py:941`, `:1036`) for `**Option A/B**` decision blocks —
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
  `scripts/little_loops/issues/research_triage.py` — its module docstring
  explains the CLI entry point exists specifically because
  `commands/refine-issue.md`'s only route to Python is `Bash(ll-issues:*)`,
  and without a registered subcommand "the change ships inert").

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — § Preservation Rule (lines 474-490); § Step 6
  "Update Issue File" append instruction (line 680) uses the same subsection
  marker; § Scope boundary (line 334) wrongly says `##` and must be corrected
  to `###`
- `scripts/little_loops/issue_parser.py` — add the `duplicate_findings_block`
  gap to `check_format_gaps()` (gap dataclass ~256-292, detection ~546-559)
- `scripts/little_loops/cli/issues/format_check.py` — print the new gap
  (help text line 64, print loop ~156-157)
- `scripts/little_loops/cli/issues/__init__.py` — extend the `format-check`
  gap-code list in the usage banner (line 124)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issues/fold_research_findings.py` (new) — core `find_subsection()`/`fold_research_findings()` logic, mirroring the core/CLI split used by `scripts/little_loops/issues/research_triage.py`
- `scripts/little_loops/cli/issues/fold_findings.py` (new) — CLI wrapper: `add_fold_findings_parser()`, `cmd_fold_findings()`, mirroring `scripts/little_loops/cli/issues/research_triage.py`
- `scripts/little_loops/cli/issues/__init__.py` — register the new subcommand (import block ~77-80, `add_fold_findings_parser(subs)` call ~928, dispatch branch ~1013-1014)

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — reads `### Codebase Research Findings`
  blocks as its input; must still parse correctly after folding
- TBD — use grep to find other readers of the marker string

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py` — home of `_heading_bodies()` (580-596, 2 call sites at 546/556 inside `check_format_gaps()`), `_section_body_with_offset()` (200-228, H2-only, last-match-wins), `_iter_h2_sections()` (758-773, H2-only); `find_subsection()` extends the two-level regex already used by `_heading_bodies()`
- `scripts/little_loops/session_log.py` — `append_session_log_entry()` (197-226) is the closest "find last header via `rfind`, insert in place" precedent the new fold insert should model
- `scripts/little_loops/cli/issues/__init__.py` — Shape-B subcommand wiring for the new `fold-findings` subcommand: import block (~77-80), `add_fold_findings_parser(subs)` call (~928), `if args.command == "fold-findings"` dispatch branch (~1013-1014) — same 3-point pattern used by `add_research_triage_parser`
- `skills/decide-issue/SKILL.md` — reads `### Codebase Research Findings` blocks for Phase 3 option extraction; must still parse correctly after folding
- `scripts/little_loops/loops/autodev.yaml:1734` — `reconcile_current` state comment references `Codebase Research Findings`

### Similar Patterns
- `scripts/little_loops/issue_history/doc_synthesis.py:_extract_section()` —
  the H2 slicing primitive refine already cites for section parsing
- `skills/wire-issue/SKILL.md` Phase 8c — the parallel
  `_Wiring pass added by …_` marker with the same accumulation behavior

### Tests
- TBD — identify test files to update

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_log.py::TestAppendSessionLogEntry` (`test_appends_to_existing_section`, `test_duplicate_session_log_headers_only_inserts_once`, `test_multiple_appends_create_multiple_entries`) — direct test-shape template for the new fold test module: single-existing-section, duplicate-headers-already-present, multi-call idempotency
- `scripts/tests/test_fold_research_findings.py` (new) — unit tests for `find_subsection()`/`fold_research_findings()`, following the template above
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

- `find_subsection(content: str, parent_heading: str, sub_heading: str) -> tuple[str, int, int] | None`
  — locates an existing `sub_heading` (H3) nested inside the slice bounded by
  `parent_heading` (H2); returns `(body, start_offset, end_offset)` or `None`
  if absent. Extends the two-level regex already used by
  `_heading_bodies()` (`scripts/little_loops/issue_parser.py:580-596`,
  `rf"^(#{{2,3}})\s+{{heading}}\s*$"`) with an H2-scoping pass borrowed from
  `_iter_h2_sections()` (`scripts/little_loops/issue_parser.py:758-773`).

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
- `fold_research_findings(content: str, parent_heading: str, new_bullets: list[str], marker: str = "_Added by `/ll:refine-issue` — based on codebase analysis:_") -> str`
  — if `find_subsection()` locates an existing
  `### Codebase Research Findings` block under `parent_heading`, appends
  `new_bullets` to it in place (same insert-after-header shape as
  `append_session_log_entry()`, `scripts/little_loops/session_log.py:197-226`);
  otherwise creates the heading + marker + bullets block, same as the current
  refine-issue.md prose template.
- `add_fold_findings_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser`
  — registers the CLI entry point, following the current convention (Shape B)
  demonstrated by `add_research_triage_parser()`
  (`scripts/little_loops/cli/issues/research_triage.py:25`), whose own module
  docstring states the reason this class of entry point exists:
  `commands/refine-issue.md`'s only route into Python is `Bash(ll-issues:*)`.

### CLI Input Channel

**Bullets arrive on stdin, never in argv.** The bullet text is LLM-authored
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
- stdin is the bullet list, one bullet per line, taken verbatim; the command
  supplies the dated provenance line itself (see § Decisions) so the caller
  never hand-writes the marker.
- Exit 1 only on unresolvable issue ID or unknown `--section`; creating a
  missing block is the ordinary success path, not an error.

### Call Path

`commands/refine-issue.md` Step 5a -> `Bash("ll-issues fold-findings ...")`
-> `cmd_fold_findings()` (new, `scripts/little_loops/cli/issues/`) ->
`fold_research_findings()` -> `find_subsection()` -> `append_session_log_entry()`
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
  parent-scoped. `find_subsection()` cannot reuse it as-is — it needs
  `_heading_bodies()`'s regex approach instead
  (`scripts/little_loops/issue_parser.py:580-596`,
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

## Implementation Steps

1. `find_subsection()` and `fold_research_findings()` exist in
   `scripts/little_loops/` (not `commands/refine-issue.md` prose) per the
   Proposed Solution's constraint that merge/dedup logic belongs in Python
   behind an `ll-issues` subcommand — a plain "find and append" instruction is
   the only part that may stay as prose.
2. A new `ll-issues fold-findings` (or similarly named) subcommand is
   registered via the current `add_X_parser(subs)` convention (Shape B, per
   `add_research_triage_parser()` in
   `scripts/little_loops/issues/research_triage.py`), reachable from
   `commands/refine-issue.md`'s `Bash(ll-issues:*)` allowed-tools scope.
3. `commands/refine-issue.md` § Preservation Rule (Step 5a, lines 474-490) and
   Step 6 "Update Issue File" (line 680) are updated to call the new subcommand
   instead of unconditionally emitting the `### Codebase Research Findings`
   template — both currently point at the same marker convention and must
   change together, per the Codebase Research Findings note above. The prose
   must state the CLI is the *only* route and that the heading and provenance
   line are never hand-written, or the change ships inert (§ Adoption risk).
   § Scope boundary (line 334) is corrected from `##` to `###` in the same
   pass.
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
   `find_subsection()`/`fold_research_findings()` logic) and
   `scripts/little_loops/cli/issues/fold_findings.py` (CLI wrapper:
   `add_fold_findings_parser()`, `cmd_fold_findings()`), mirroring the
   `research_triage.py` / `cli/issues/research_triage.py` core+CLI split.
8. Register the new subcommand in `scripts/little_loops/cli/issues/__init__.py`:
   import block (~lines 77-80), `add_fold_findings_parser(subs)` call (~line
   928), and `if args.command == "fold-findings"` dispatch branch (~lines
   1013-1014) — the same 3-point wiring used by `add_research_triage_parser`.
9. Add `scripts/tests/test_fold_research_findings.py` following the
   `TestAppendSessionLogEntry` shape (`test_session_log.py:133-256`):
   single-existing-section fold, duplicate-headers-already-present fold,
   multi-call idempotency.
10. Add a pre-fold baseline test in `scripts/tests/test_issue_parser.py`
    constructing an issue body with 3 stacked `### Codebase Research Findings`
    blocks under one H2, asserting `_heading_bodies()` returns 3 bodies before
    folding lands (no such fixture exists today).
11. Update `docs/reference/CLI.md` with the new `ll-issues fold-findings`
    entry.
12. Confirm `skills/decide-issue/SKILL.md`'s Phase 3 option extraction still
    parses correctly against a folded issue file (manual or scripted check
    against the scratch issue file from Implementation Step 4).
13. Add the `duplicate_findings_block` gap to `check_format_gaps()`
    (`scripts/little_loops/issue_parser.py`, gap dataclass ~256-292, detection
    beside the existing `_heading_bodies()` call at ~546-559 — which already
    returns all N bodies, so the detector is `len(bodies) > 1` per H2), surface
    it in `scripts/little_loops/cli/issues/format_check.py` (help text line 64,
    print loop ~156-157) and in the usage banner
    (`scripts/little_loops/cli/issues/__init__.py:124`). Test alongside
    `scripts/tests/test_ll_issues_format_check.py::TestUnmarkedSupersededDirective`.
14. Verify bullets survive the stdin round-trip verbatim: a fold whose bullets
    contain backticks, `$`, `!` and an em-dash produces byte-identical text in
    the file (guards the § CLI Input Channel decision).
15. Verify the ENH-2995 interaction: after two folds into one block, the
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

- **No *newly written* findings block creates a second
  `### Codebase Research Findings` heading under an H2 that already has one.**
  Scoped to writes made after this change lands — the existing corpus is
  explicitly not migrated (§ Decisions), so a corpus-wide assertion would be
  false on day one and unmeasurable.
- Measured by the new `duplicate_findings_block` gap in `ll-issues
  format-check`: its count over issues refined after the change stays at 0.
  This also catches the adoption failure mode below.
- Zero bullets lost across a fold (verifiable by bullet count before/after).
- Per-batch provenance lines are preserved: after N folds the block contains
  N `_Added by …_` lines under one heading (§ Decisions).

### Adoption risk this metric guards

Per the Codebase Research Findings above, this write is **100% prose-instructed
`Edit` today** — routing it through `ll-issues fold-findings` is the first
CLI-mediation of this path. If the skill prose is updated but the model keeps
hand-writing the heading, the change ships inert and silently. The
`duplicate_findings_block` gap is what makes that visible rather than assumed,
which is why it is in scope here and not a follow-up.

## Scope Boundaries

- Does **not** delete, summarize, or dedupe findings content — folding is
  relocation only.
- Does **not** amend the Preservation Rule's overwrite prohibition
  (that is ENH-2995).
- Does **not** migrate the existing corpus — decided, not deferred
  (§ Decisions). The `duplicate_findings_block` gap makes the backlog of
  already-stacked blocks visible if that call is revisited.
- Does **not** fold `/ll:wire-issue`'s `_Wiring pass added by …_` markers —
  follow-up issue; the primitive is parameterized so wire-issue becomes a
  caller (§ Decisions).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/refine-issue.md` | Contains the append instruction being changed |
| `commands/reconcile-issue.md` | Downstream consumer of these blocks |

## Session Log
- `/ll:confidence-check` - 2026-08-02T21:57:18 - `122b9e35-a883-466b-b221-9c07cbc675a2.jsonl`
- `/ll:confidence-check` - 2026-08-02T21:29:09 - `a19bb83d-629a-488d-832c-2afbb30f5117.jsonl`
- `/ll:refine-issue` - 2026-08-02T21:18:58 - `5927db07-ad5f-4874-b0e1-25eb77fc4c20.jsonl`
- `/ll:wire-issue` - 2026-08-02T21:06:13 - `fa4f5cf7-5457-4423-9741-a8025cdbaf37.jsonl`
- `/ll:refine-issue` - 2026-08-02T20:56:54 - `bc3cf078-a345-4297-857c-b20009b9e1f3.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:57 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
