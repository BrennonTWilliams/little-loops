---
id: BUG-3691
type: BUG
title: verify-issues citation checking is unstable across passes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-01'
captured_at: '2026-10-01T22:03:31Z'
reconcile_attempted: true
relates_to:
- ENH-3690
- BUG-3708
blocks:
- BUG-3708
parent: EPIC-3694
epic: EPIC-3694
confidence_score: 80
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
---

# BUG-3691: verify-issues citation checking is unstable across passes

## Summary

`/ll:verify-issues <ID> --check --auto` does not check citations consistently between passes of the same loop run, so a citation defect can surface only on a late pass, after the loop's repair budgets are spent.

Observed on BUG-3689 (run `refine-to-ready-issue-20261001T151155`): passes 1 and 2 reported every cited code reference as holding and returned `DIRECTIVE_DRIFT` (Acceptance Criteria gaps). Pass 3, with no relevant citation edits in between, flagged two wrong citations and returned `NON_VALID`, which ended the run `GATE_UNMET` (see the companion ENH on NON_VALID having no repair route). In the same run `refine_followup`'s gap analysis judged the bare name `runner_spec.py` acceptable, while verify pass 3 described it under an `fsm/`-prefixed directory (a path the issue text does not contain and that does not exist; the file is `scripts/little_loops/runner_spec.py`), i.e. it misread the citation before calling it wrong.

## Current Behavior

`verify-issues` resolves `path:line` / `file:symbol` citations through the model's ad-hoc reads and greps, so coverage differs between passes over an unchanged issue. Passes 1 and 2 of the BUG-3689 run reported every citation as holding; pass 3 flagged two as wrong. Bare filenames can also be misread as a different path before being judged.

## Expected Behavior

The mechanical properties format-check actually examines produce deterministic findings over an unchanged issue and code snapshot. A bare filename citation is resolved by search rather than reported as a different path. Semantic content and premise judgments remain the model's responsibility; this issue does not promise identical whole `verify-issues` verdicts.

## Motivation

A citation defect that surfaces only on a late pass lands after the loop's repair budgets are spent, turning a fixable issue into a `GATE_UNMET` run end. Making the check deterministic moves such defects to pass 1, where the repair route can still act on them, and removes a source of run-to-run variance in `refine-to-ready-issue`.

## Proposed Solution

Extend `ll-issues format-check`; do not add a CLI. This issue owns the detectors and the `examined_refs` contract. **BUG-3708** owns check B8 in `verify-issues`. **ENH-3690** owns the subsequent citation repair/eligibility policy. Existing blocking rules retain their scope and behavior; every new-rule or newly covered-scope finding is advisory here.

### Citation coverage contract (settled in pre-implementation review, 2026-10-03)

- Emit `examined_refs` as a **sibling metadata key in single-ID JSON**, alongside `directive_gaps` and `superseded_marker_count`. Keep it **out of `FormatGaps`**, `to_dict()`, gap predicates and text rendering. A keyword-only optional collector on `check_format_gaps` lets the CLI collect it; existing callers need no change. `--all` remains a sparse mapping of issues with actual gaps, without citation metadata.
- Each serialized `CitationCheck` is `{ref, issue_line, issue_column, property, result}`. `ref` preserves the complete cited form, including `:N[-M]` or `:symbol()`, with enclosing backticks removed. For an attributed symbol/file pair, preserve the complete attribution span rather than reducing it to the bare symbol name. `issue_line` and `issue_column` are **1-based positions in the original full issue file**, including frontmatter. Match on the exact occurrence and property, not on a resolved filename or stripped path. If an extractor cannot retain an unambiguous original span, it must not publish coverage for that occurrence.
- `property` is `path_resolves` | `line_in_range` | `symbol_resolves_in` | `symbol_defined_in`. `path_resolves` means uniquely resolvable against the tracked-file index, **not disk existence**. `symbol_resolves_in` uses the existing import-inclusive existence check; `symbol_defined_in` is a distinct definition-shaped claim. An imported symbol may pass the former while failing the latter. An import-inclusive pass must never be serialized as `symbol_defined_in: ok`.
- `result` is `ok` or the exact gap-class key raised. `ok` is emitted only after that property has actually been checked. Missing/unsupported forms, absent indexes or root, unavailable reads, unsupported languages, planned-new refs, untracked-by-design refs, suppressed claims and breadth-capped claims have **no entry for the unexamined property**. A known stale/ambiguous path may have a failing `path_resolves` entry, but never a line/symbol pass. Unsuffixed bare filenames receive no new path coverage; supported attributed-symbol forms keep their existing behavior.
- Preserve source positions through section selection and fenced-block skipping using `text_utils.fence_spans` / `in_fence`; do not derive coverage from `extract_file_paths`' deduplicated, line-stripped set or from concatenated section bodies. Do not change legacy extraction behavior as a side effect. Sort entries by `(issue_line, issue_column, ref, property, result)`, deduplicate identical entries, and never publish both `ok` and failure for the same occurrence/property.

### Detector rules and advisory representation

1. **Definition vs import:** apply the new rule only to definition-shaped claims (`file:symbol`, explicit "defined in", or a clearly stated owner), not a usage-site mention merely containing `symbol()`. When the cited module imports but does not define the symbol and exactly one other tracked module defines it, report `advisory_mislocated_symbol_ref`, with that target. Reuse `SymbolIndex.files_with_symbol`'s eager definition-only reverse index; `symbol_resolves_elsewhere` returns only a bool and does not prove uniqueness or supply the target. Use the existing readable-file cache to fail open on unreadable files. No second definition parser/cache is needed. Multiple or missing alternative definitions do not produce a guessed target or an `ok` definition entry. Preserve `<!-- ll-prose-ok: reason -->` suppression.
2. **Line bounds:** report `stale_line_ref` when a supported `path:N[-M]` violates `1 <= N <= M <= line_count`, including zero, reversed ranges, past-EOF endpoints and empty files. Resolve against the explicit project root, never process cwd; `anchors.resolve_anchor` clamps and is not the checker. Unresolved, ambiguous, planned-new or unreadable files produce no line result. A passing range says nothing about its claimed content.
3. **Bare filename citations:** add resolution only for `name.ext:N[-M]` and `name.py:symbol()` forms, preserving complete raw citations. Reuse `suffix_match_candidates`; zero/one/multiple candidates produce `advisory_stale_file_ref` / `ok` / `advisory_ambiguous_file_ref`, with sorted candidates. Honor planned-new and untracked-by-design policy. Preserve exact mirror refs and sole-mirror matches; distinguish multiple mirror-only matches from missing files instead of treating the filtered empty candidate list as proof of absence. Unsuffixed artifact/loop names remain unchecked.
4. **Scope:** new symbol and line checks cover Integration Map (including nested Tests), standalone Tests and Wiring Phase in addition to the current-state scope. New-scope symbol findings use `advisory_stale_symbol_ref` / `advisory_mislocated_symbol_ref`; existing Summary / Current Behavior / Root Cause / Context symbol rules remain unchanged. Coverage and severity are occurrence-specific: a pass or advisory result in one section must not override a different occurrence in another.
5. **Fixed advisory keys:** `advisory_stale_file_ref`, `advisory_ambiguous_file_ref`, `advisory_stale_symbol_ref`, `advisory_mislocated_symbol_ref`, and `stale_line_ref` are real gap fields added to `_ADVISORY_GAP_CLASSES`, `has_gaps`, `to_dict()` and `_print_gaps`. None gets a `--fix` repair or changes `has_blocking_gaps`. An occurrence already reported by an existing blocking rule is not duplicated as an advisory finding for that same property. Metadata itself is never a gap.

### Scope and sequencing

Ship this detector half first, then BUG-3708's B8 consumer. ENH-3690 may consume advisory results for its explicitly scoped citation-repair policy; absent that policy they do not independently change verify's verdict. Any later promotion to a blocking format-check rule belongs to ENH-3690 and requires measured precision and a working repair route. This issue does not widen §2C's correction scope or require ENH-3690 to land before it can close.

The prior new-CLI plan was rejected on 2026-10-02: it duplicated format-check and still missed imported-only symbols. The 2026-10-02 review's 222 false stale findings for unsuffixed bare names are historical measurements, not a current precision estimate; remeasure the new citation-shaped rules during implementation.

## Integration Map

### Files to Modify

- `scripts/little_loops/issues/citations.py` (new) — small typed occurrence/coverage helper retaining complete citation forms and original source positions; reuse existing resolution owners
- `scripts/little_loops/issues/symbol_claims.py` — definition-shaped attribution and definition-vs-import checks; reuse the existing reverse index and suppression rules
- `scripts/little_loops/issue_parser.py` — optional coverage collector/project-root inputs, new advisory fields, widened occurrence-aware checks; leave existing gap rules intact
- `scripts/little_loops/cli/issues/format_check.py` — supply `config.project_root`, collect coverage for single-ID JSON, render advisory findings, document exit-code behavior
- `scripts/tests/test_symbol_claims.py`, `scripts/tests/test_issue_parser.py`, `scripts/tests/test_ll_issues_format_check.py` — detector, metadata and output compatibility tests
- `scripts/tests/test_citation_checks.py` (new) — original-span identity, line ranges and scope/fence cases
- `docs/reference/CLI.md` — update the existing format-check section with advisory keys and single-ID JSON metadata

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `normalize_structure` reads `directive_gaps`; it must not react to metadata/advisory-only findings
- `scripts/little_loops/loops/rn-remediate.yaml` — format-check exit gate must retain its existing blocking set
- `scripts/little_loops/cli/issues/next_obligation.py`, `scripts/little_loops/preparation_policy.py` and other `FormatGaps` consumers — no signature break or new obligation from metadata/advisory-only findings
- `skills/confidence-check/SKILL.md` — existing CLAIM_GAP policy for `stale_symbol_ref` must not start treating advisory counterparts as blocking
- `commands/verify-issues.md` and host mirrors — **no edit in this issue**; BUG-3708 consumes the locked coverage contract

### Similar Patterns

- Single-ID format-check JSON's existing `superseded_marker_count` / `directive_gaps` metadata, which is outside `FormatGaps`
- `ll-verify-evidence` — deterministic evidence consumed by command prose

### Tests

- Definition vs imported binding, intentional usage site, aliased import, multiple alternative definitions, unreadable/unsupported files and suppression; import-inclusive `ok` never means definition `ok`
- Slash-qualified and bare `:N[-M]` refs: zero/one/multiple matches, mirror policy, `(new)`, untracked-by-design and sorted candidates
- Boundary cases: line 1, final line, empty file, zero, reversed ranges, end beyond EOF, missing file; invocation from another cwd still checks the correct root
- Same raw citation in current-state and advisory scope; suppressed vs examined occurrence; different ranges in one file; repeated symbol names attributed to different files; original positions survive fence/scope selection
- Single-ID metadata-only output leaves both gap predicates false, text says compliant and exit code is 0; `--all` does not gain compliant rows; `--fix --apply` leaves citation text untouched
- Advisory findings render in text/JSON and set `has_gaps` only; existing blocking rules still fail as before; metadata does not enter the `_TEXT_RENDER_EXEMPT` dataclass-field guard because it is not a field
- Byte-identical JSON over unchanged issue **and code/index snapshot**; explicit tests for absent/unknown property coverage

## Program Design

### Types

- `CitationCheck` — dataclass in the new citation helper, serialized as `{ref: str, issue_line: int, issue_column: int, property: str, result: str}` with the property/result domains above
- `FormatGaps` gains the five advisory gap fields above; **no `examined_refs` field**

### Signatures

- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None, issue_statuses: dict[str, str] | None = None, ref_index: RefIndex | None = None, symbol_index: SymbolIndex | None = None, cli_index: CliSurfaceIndex | None = None, *, examined_refs: list[CitationCheck] | None = None, project_root: Path | None = None) -> FormatGaps` — existing positional inputs preserved; optional keyword-only collector and root. Without a root, a supplied `symbol_index.root` is usable; with neither, filesystem-dependent checks remain unexamined.
- Existing `SymbolIndex.files_with_symbol` supplies definition sets; existing `symbol_exists_in_file` supplies import-inclusive presence. Keep their contracts distinct.

### Call Path

Single-ID `format-check` -> build indexes once -> `check_format_gaps` with optional collector -> gap report + sorted `examined_refs` sibling -> BUG-3708 B8.

## Implementation Steps

1. Capture a baseline from the **same committed issue/code snapshot** used for the post-change comparison. Review baseline at clean HEAD `e25e2aef81fd23aa7cc1aaa506ed6b217d6ba75e` on 2026-10-03: `format-check --all --format json` exited 1; 27 issues had gaps; counts were `stale_file_ref=19`, `ambiguous_file_ref=0`, `stale_symbol_ref=0`, `mislocated_symbol_ref=0`. The three reviewed issues were compliant. This is a count baseline, not a labelled precision sample.
2. Add the typed span-aware helper and optional metadata collector; freeze the schema above before implementing BUG-3708. Preserve original positions and legacy extraction/rule behavior.
3. Add the definition/import, bare-filename, line-range and widened-scope detectors with the fixed advisory keys. Reuse indexes, fail open on unknown properties, and supply the project root explicitly.
4. Wire single-ID JSON metadata and advisory text/JSON rendering; verify metadata does not affect gap predicates, sparse sweeps, `directive_gaps`, repairs or exit status.
5. Add the detector/contract/compatibility tests above, rerun the corpus on the fixed snapshot and record blocking-set parity plus labelled new findings. Explain false positives separately from raw count deltas.
6. Update format-check documentation and run `python -m pytest scripts/tests/`. Close this detector issue independently of ENH-3690; hand off the exact payload and advisory keys to BUG-3708 and ENH-3690.

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` against an issue whose Tests section cites a symbol by the importing module rather than the defining module.
2. Compare the per-pass verify summaries in `.loops/.running/<run>.log`.

## Root Cause

Citation verification is performed by the model with ad-hoc reads/greps (the passes reported "direct reads and greps", no graph queries), not by a deterministic check, so coverage varies per pass.

## Acceptance Criteria

- [ ] Single-ID JSON emits the exact occurrence/property schema above; metadata alone leaves `has_gaps` and `has_blocking_gaps` false, exit code 0 and compliant text output unchanged; sparse `--all` output does not gain compliant issues.
- [ ] Repeated format-check calls over an unchanged issue and code/index snapshot are byte-identical, including sorted metadata and candidate lists.
- [ ] Coverage is honest: import-inclusive presence cannot become definition proof; planned-new, untracked, suppressed, unsupported, unreadable and otherwise unexamined properties never receive `ok`.
- [ ] Same-file different-range refs and repeated refs across current-state/advisory scope keep distinct identities and results; a pass cannot demote a finding about another occurrence/property.
- [ ] New bare-filename citations resolve zero/one/multiple matches deterministically; ambiguous and mirror-only results retain their candidates; unsuffixed bare filenames are not newly checked.
- [ ] The imported-only definition claim `cli/loop/feed.py:terminal_size()` produces `advisory_mislocated_symbol_ref` in Tests/Wiring Phase; intentional usage-site claims remain eligible for import-inclusive presence without false definition coverage.
- [ ] Line range validity is `1 <= N <= M <= line_count`, rooted at the project rather than cwd; invalid ranges report advisory `stale_line_ref`, with boundary/fail-open tests.
- [ ] All five new advisory keys render without changing the existing blocking set/exit status, `directive_gaps`, obligation selection or `rn-remediate` routing; `--fix --apply` does not repair citations.
- [ ] The fixed-snapshot before/after counts and blocking-set diff, plus labelled new-rule findings, are recorded; later promotion/repair remains ENH-3690's responsibility.
- [ ] `python -m pytest scripts/tests/` exits 0; BUG-3708 receives the implemented payload contract.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3

---

## Scope Boundary

**Pre-implementation review, 2026-10-03:** this issue owns deterministic mechanical detection and occurrence/property coverage only. BUG-3708 consumes that coverage: checked passes may demote conflicting mechanical model findings; unexamined, content and premise findings remain model-decidable. All new-rule/new-scope failures remain advisory until ENH-3690 explicitly defines repair eligibility or promotes a key. Finding absence alone is never proof that a citation passed. No command mirrors or verdict/correction-scope changes are included here.

## Confidence Check Notes

Historical `/ll:confidence-check` scores from 2026-10-03: readiness 80, outcome 67. These predate the contract corrections above and have not been recomputed.

### Concerns addressed in this review

- Metadata-as-gap failure is eliminated by keeping `examined_refs` outside `FormatGaps`, using the existing sibling-metadata pattern.
- Advisory representation is fixed to separate gap keys; no per-finding severity marker plumbing is required.
- Definition-only parsing already exists in the eager reverse index; no second cache is needed. Readability/unsupported checks remain fail-open.
- Existing set extraction loses line suffixes, original positions and scope; the new helper must retain them rather than incorrectly claiming full coverage.

### Outcome Risk Factors

- Definition-shaped attribution can still be ambiguous, especially import usage vs ownership; advisory rollout and labelled findings are required.
- Original-span coverage adds a small extractor surface. Retain existing index, suppression, breadth-cap and fence contracts; unknown spans must not get `ok`.
- Backlog count parity proves no new blocking gates, not citation precision or repeatability of semantic LLM verdicts.

## Session Log
- `/ll:confidence-check` - 2026-10-03T17:18:04 - `e655cd0c-0c5d-446b-bee6-c9fe4cf5573e.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:00 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:38:30 - `481f71a6-8878-4664-a5d1-327d85ef26ef.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-01T22:36:37 - `b3ad147a-1b97-4e9e-9ff4-48d129540768.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:29:42 - `a49c8713-7686-4a9e-bacf-5deb614f716c.jsonl`
- `/ll:reconcile-issue` - 2026-10-01T22:27:31 - `63eca4e2-7910-4f8b-a85d-8d3e1f5ace32.jsonl`
- `/ll:verify-issues` - 2026-10-01T22:26:30 - `92efd7c9-cd87-454a-b212-dd9b0cf0e924.jsonl`
- `/ll:wire-issue` - 2026-10-01T22:23:51 - `5e15de52-8cf2-472b-9798-f3ad06f6968f.jsonl`
- `/ll:refine-issue` - 2026-10-01T22:13:27 - `ddfc7f67-a67f-4b84-ae24-829db8cff1f4.jsonl`
- `/ll:format-issue` - 2026-10-01T22:07:09 - `ab89f402-e50e-4f70-99ea-6014766a7a2a.jsonl`
- `/ll:capture-issue` - 2026-10-01T22:03:38 - `8a253271-7b3f-4496-adff-dcad85be0bc1.jsonl`
