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
parent: EPIC-3694
epic: EPIC-3694
---

# BUG-3691: verify-issues citation checking is unstable across passes

## Summary

`/ll:verify-issues <ID> --check --auto` does not check citations consistently between passes of the same loop run, so a citation defect can surface only on a late pass, after the loop's repair budgets are spent.

Observed on BUG-3689 (run `refine-to-ready-issue-20261001T151155`): passes 1 and 2 reported every cited code reference as holding and returned `DIRECTIVE_DRIFT` (Acceptance Criteria gaps). Pass 3, with no relevant citation edits in between, flagged two wrong citations and returned `NON_VALID`, which ended the run `GATE_UNMET` (see the companion ENH on NON_VALID having no repair route). In the same run `refine_followup`'s gap analysis judged the bare name `runner_spec.py` acceptable, while verify pass 3 described it under an `fsm/`-prefixed directory (a path the issue text does not contain and that does not exist; the file is `scripts/little_loops/runner_spec.py`), i.e. it misread the citation before calling it wrong.

## Current Behavior

`verify-issues` resolves `path:line` / `file:symbol` citations through the model's ad-hoc reads and greps, so coverage differs between passes over an unchanged issue. Passes 1 and 2 of the BUG-3689 run reported every citation as holding; pass 3 flagged two as wrong. Bare filenames can also be misread as a different path before being judged.

## Expected Behavior

Citation resolution is deterministic: repeated `--check` passes over an unchanged issue produce identical citation findings, and a bare filename citation is resolved by search rather than reported as a different path.

## Motivation

A citation defect that surfaces only on a late pass lands after the loop's repair budgets are spent, turning a fixable issue into a `GATE_UNMET` run end. Making the check deterministic moves such defects to pass 1, where the repair route can still act on them, and removes a source of run-to-run variance in `refine-to-ready-issue`.

## Proposed Solution

Make citation findings deterministic **by extending `ll-issues format-check`** and making `verify-issues` consume its keys as ground truth; the model keeps only semantic claims.

> **Rescoped 2026-10-02 (EPIC-3694 review, Opus second opinion).** The original plan — a brand-new `ll-verify-citations` CLI — is dropped. It duplicated `ll-issues format-check` (which already runs `stale_file_ref` / `ambiguous_file_ref` / `stale_symbol_ref` / `mislocated_symbol_ref` right before `verify_issue` and which `verify-issues` ignores), carried ~20 registration touchpoints, and still would not have caught the real defect (a symbol cited via its *importing* module: `symbol_exists_in_file` is satisfied by the import at `feed.py:44`). Pre-rescope research about a new CLI (registration surface, `extract_citations`, exit-code contract) was pruned on 2026-10-02; the findings kept below are post-rescope only.

1. **Defined-in vs imported-in rule** (`symbol_claims`): a symbol claimed in file F that F only *imports* (no `def`/`class`/assignment) while exactly one other tracked module defines it → `mislocated_symbol_ref` (use `symbol_resolves_elsewhere` for the target). Be conservative to avoid false positives where citing the importer is the intended usage-site claim: trigger only on definition-shaped claims (`file:symbol`, "defined in", `symbol()` as owner), and honor the existing `<!-- ll-prose-ok -->` suppression marker.
2. **Line past end of file**: new gap key `stale_line_ref` for a cited `path:N[-M]` whose line exceeds the file length; `anchors.resolve_anchor` clamps today, so this needs its own check relative to the project root, not process cwd. **Advisory**: add it to `issue_parser._ADVISORY_GAP_CLASSES` (report-only, no repair, no exit-code effect) so it cannot turn into a gate on its own.
3. **Bare-filename citations**: resolve slash-less refs (BUG-3689's `runner_spec.py:335`) through `text_utils.suffix_match_candidates` — 0 / 1 / >1 tracked paths → `stale_file_ref` / ok / `ambiguous_file_ref`, candidates sorted; report mirror-only matches distinctly; honor `(new)` planned-new markers. **Restrict to citation-shaped forms** — `name.ext:N` and `name.py:symbol()` — and leave unsuffixed bare names unchecked (as today). The 2026-10-02 Opus review measured 222 zero-match false `stale_file_ref` findings across 58 open issues for unsuffixed bare names (mostly artifact/loop names), versus 0 zero-match and 5 ambiguous for line-suffixed ones; re-measure when implementing (step 1 baseline).
4. **Scope**: widen the symbol/line checks beyond `_symbol_claim_scope_text` (Summary / Current Behavior / Root Cause / Context) to cover Integration Map, Tests and Wiring Phase — the BUG-3689 pass-3 defect sat in Tests/Wiring Phase — keeping fenced-block skipping (`text_utils.fence_spans`).
5. **`verify-issues` wiring**: new check **B8** (after check 7) reads `ll-issues format-check <ID> --format json` and treats its ref keys as authoritative **only for the properties format-check actually decides**: path existence/ambiguity, line-in-range, and symbol definition location. The model must not raise a finding of those kinds that format-check does not back up (demote it to an advisory note that does not affect the verdict). A cited line whose claimed *content* is absent or different, and any premise-changing citation finding, stays verdict-bearing: format-check cannot express it, and demoting it would make format-check a single point of failure that silently hides real defects. Fail-open wording matches B7: invocation failure → silent fallback.
6. **Routing (ENH-3690 is the repair route)**: pass-1 detection only pays off if the finding is repairable. §2C's `CLAIMS_OUTDATED` correctable scope covers Integration Map / Tests citations but not Wiring Phase, Summary or Root Cause, so a defect found there on pass 1 still ends `NON_VALID` → `GATE_UNMET` unless ENH-3690's route exists. This issue does **not** widen §2C (BUG-3637 deliberately limited auto-rewrite scope); ENH-3690 is the route for those cases.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/symbol_claims.py` — defined-in vs imported-in rule (`symbol_exists_in_file` / `symbol_resolves_elsewhere` callers)
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` (add `stale_line_ref`; bare-filename resolution; widened scope next to `_symbol_claim_scope_text`) and the gap dataclass
- `scripts/little_loops/text_utils.py` — slash-less ref handling in `classify_file_ref` (or a sibling resolver using `suffix_match_candidates`); sorted candidates
- `scripts/little_loops/cli/issues/format_check.py` — report/`--format json` surface for the new key(s)
- `commands/verify-issues.md` — new check **B8** after §2B check 7; keep the `test_enh3250` anchors (`#### B. Verify Against Codebase`, `#### C. Determine Verdict`, `Persist the verdict to frontmatter`, `### 3. Request User Approval`) present and in order; `Bash(ll-issues:*)` is already granted
- Host mirrors of `commands/verify-issues.md` — regenerate with `ll-adapt --host <gemini|qwen|kimi-code|codex> --apply` (never hand-edit)

No new CLI: nothing to change in `scripts/pyproject.toml`, `cli/__init__.py`, `init/writers.py` (`_LL_PERMISSIONS`), `skills/configure/areas.md`, or `docs/reference/CLI.md` entry-point coverage.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - runs `verify-issues --check --auto` each pass and routes on its verdict (a root `loops/` directory does not exist)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the real location of the `refine-to-ready-issue` loop (a root `loops/` directory does not exist); states `verify_issue` (runs `/ll:verify-issues ... --check --auto`) and `route_pre_score_obligation`; no edit needed while no new verdict value is added [Agent 1 finding]
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` maps persisted `verify_verdict`; unchanged as long as citation findings reuse existing verdicts (§2.5 precedence); a new verdict value would also touch `next_obligation.py`, the `route:` table, `test_builtin_loops.py::TestRefineToReadyDispatch` and `test_ll_issues_next_obligation.py::TestVerify` [Agent 2 finding]
- `scripts/little_loops/text_utils.py` — `build_ref_index`, `suffix_match_candidates`, `classify_file_ref` are the bare-filename resolution primitives the extended check reuses; read-only reuse, no signature change [Agent 1 finding]
- `scripts/little_loops/cli/issues/format_check.py` — existing deterministic file-ref linter (`stale_file_ref` / `ambiguous_file_ref`) over the same `RefIndex`; this is the surface being extended, and it deliberately skips slash-less refs today [Agent 1 finding]
- `scripts/little_loops/issues/anchor_sweep.py` and `scripts/little_loops/issues/symbol_claims.py` — adjacent `file:line` / symbol extractors (`_FILE_LINE`, `_EXPLICIT_RE`) the line-past-EOF and widened-scope checks must either reuse or stay consistent with (their path regexes disagree on extension length and `:N-M` ranges) [Agent 1 finding]
- `commands/refine-issue.md` and `skills/ll-refine-issue/SKILL.md` — grant `Bash(ll-verify-evidence:*)` and call `/ll:verify-issues`; no edit (no new CLI is added; `test_refine_issue_command.py` pins its grant) [Agent 1 finding]
- Consumers of the new/changed gap keys (advisor review 2026-10-02): `normalize_structure` in `refine-to-ready-issue.yaml` reads only `directive_gaps`, so loop gating is unaffected; **but** `/ll:confidence-check` CLAIM_GAP (a `stale_symbol_ref` caps Criterion 4) will fire more often once scope widens, and `scripts/little_loops/loops/rn-remediate.yaml` (~L114, `ll-issues format-check "$ID"` exit-code gate → `format_issue`) can route a futile format-issue pass for a ref gap it cannot fix. `stale_line_ref` stays advisory precisely to avoid adding to this

### Similar Patterns
- `ll-verify-evidence` (`scripts/little_loops/cli/verify_evidence.py`) - deterministic CLI check consumed by a skill/loop as ground truth

### Tests
- `scripts/tests/test_symbol_claims.py` / `test_issue_parser.py` / `test_format_check*.py` (locate the existing `stale_symbol_ref` / `stale_file_ref` suites): importing-module claim → `mislocated_symbol_ref`; defining-module claim → clean; line past EOF; bare filename 0/1/>1 matches with sorted candidates; mirror-only match; `(new)` planned file not flagged; `ll-prose-ok` suppression
- Determinism: run `check_format_gaps` / `format-check --format json` twice over an unchanged fixture issue (`tmp_path` git repo; helpers in `test_verify_evidence.py` style) and assert byte-identical output
- `scripts/tests/test_bug3691_verify_issues_citations.py` (new) — B8 present between check 7 and `#### C. Determine Verdict`; consumes `ll-issues format-check`; modelled on `test_enh3126_verify_issues_graph_seeding.py`
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — slices on the §2B/§C/§3 anchors via `body.index(...)`; must stay green
- `scripts/tests/test_verify_skill_prose.py::TestBaselineNeverIncreases` (`BASELINE_COUNT = 17`) — B8 prose must not add `python3 -c` / union-find wording; name the CLI as owner, do not describe the resolution steps (EPIC-2938 invariant)
- `scripts/tests/test_docs_audience_gate.py` — B8 prose must not cite `scripts/` paths (use `little_loops.<module>`)
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` — fails until mirrors are regenerated

### Documentation
- `docs/reference/CLI.md` — the `ll-issues format-check` section: new gap key(s) and bare-filename behavior
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` — optional note under `/ll:verify-issues` that citation checks are deterministic

### Codebase Research Findings

_Pruned to post-rescope content on 2026-10-02 (the pre-rescope new-CLI findings were removed)._

- **Basename-search primitives exist in `text_utils.py`:** `build_ref_index(root)` (one `git ls-files -z`, `RefIndex.by_basename`), `suffix_match_candidates(ref, index)` (exact hit, else paths ending `"/" + ref`, then drops host-adapter mirror prefixes), `classify_file_ref(ref, index, line="")`. `classify_file_ref` returns `unresolvable_form` for any ref with no `/` before any lookup, so bare filenames are unchecked today — the BUG-3689 `runner_spec.py` case. `suffix_match_candidates` returns `[]` when every match is a mirror path, so that case reads as stale, not ambiguous; candidates come back in `git ls-files` order, so the check must impose its own sort. `verify_evidence.resolve_artifact` is exact-match only and cannot serve this.
- **Planned-new hazard.** `_PLANNED_NEW_RE` (`(new)`, `(new file)`, `(to be created)`, `**new**`) is applied only inside `classify_file_ref`; a resolver built on `suffix_match_candidates` alone would report every planned-new Integration Map file as stale.
- **Symbol and line coverage today:** `issues/symbol_claims.py` (`extract_symbol_claims`, `symbol_exists_in_file`, `symbol_resolves_elsewhere`) already surfaces `stale_symbol_ref` / `mislocated_symbol_ref` through `ll-issues format-check`, scoped by `issue_parser._symbol_claim_scope_text` to Summary / Current Behavior / Root Cause / Context only. `symbol_exists_in_file` is satisfied by an import, which is why BUG-3689's `cli/loop/feed.py:terminal_size()` (imported at `feed.py:44`) passed. Nothing reports a cited line beyond EOF; `issues/anchors.py:resolve_anchor` reads relative to process cwd and clamps.
- **`verify-issues` consumes none of this.** `commands/verify-issues.md` §2A/§2B does the citation work with model reads/greps; its only deterministic CLI calls are `ll-verify-evidence` (check B7, quoted spans) and `ll-issues format-check` for prose-dependency keys (§C step 3). `refine-to-ready-issue.yaml` already runs `ll-issues format-check <ID> --fix --apply` then `--format json` in `normalize_structure` immediately before `verify_issue`; the ref keys exist in that payload but only `directive_gaps` is read. `check_format_gaps` iterates refs and symbol claims in sorted order, which is why those keys are stable across passes.
- **B8 placement.** Check 7 (`ll-verify-evidence`) is the only deterministic CLI step in §2B and it uses `$ISSUE_FILE`, which the §0/§1 shell blocks never assign (they set `ISSUE_ID`, `FLAGS`, `AUTO_MODE`, `CHECK_MODE`); B8 should invoke format-check by `<ID>` and need no file path.
- **Loop routing / verdict mapping.** The verdict is persisted as `verify_verdict` (§2.5 precedence `NON_VALID` > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`) and read by `route_pre_score_obligation` via `classify_verify_verdict`; `NON_VALID` maps to `other` → `check_gate_refine_limit`. The sections-to-verdict rule lives only in `verify-issues.md` §C/§2.5 prose, so a citation finding reaches routing solely through the model's verdict write. ENH-3690 owns the repair route for citation-only `NON_VALID`.
- **Suppression marker.** `<!-- ll-prose-ok -->` (preceding line only, `symbol_claims._SUPPRESS_RE`) is the existing marker; new symbol rules must honor it. `verify_skill_prose` lints prose that reimplements a CLI-owned algorithm (EPIC-2938 invariant): B8 wording should name format-check as the owner, not describe the resolution steps.
- **Fence handling and ordering.** `text_utils.fence_spans`/`in_fence` is line-anchored and offset-preserving (BUG-3202); `extract_file_paths`, `anchor_sweep` and `symbol_claims` use the unanchored `_CODE_FENCE` regex, so mixing them can give different findings on one body. `extract_file_paths` returns a `set` and `build_tracked_index` a `frozenset`: findings need an explicit total sort key for the byte-identical-JSON criterion.
- **Reconcile guard.** This issue has `reconcile_attempted: true`; `preparation_policy.py` (`if s.reconcile_attempted: return ""`, ~L639-640) then skips reconcile, so the body does not self-heal and stale prose must be removed by hand (done 2026-10-02).

## Program Design

### Types

- `FormatGaps.stale_line_ref: list[str]` — new gap key (cited `path:N` beyond end of file), added to `_ADVISORY_GAP_CLASSES`; existing `stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref` reused

### Signatures

- `symbol_defined_in_file(index: SymbolIndex, file: str, symbol: str) -> bool | None` — new in `issues/symbol_claims.py`: True only for a definition (not an import); `None` when the file cannot be read/parsed
- `check_format_gaps(...)` — unchanged signature; emits the new/changed keys

### Call Path

`verify-issues` check B8 -> `ll-issues format-check <ID> --format json` -> `check_format_gaps` -> `symbol_claims` / `text_utils.suffix_match_candidates`

## Implementation Steps

1. **Baseline first:** run `ll-issues format-check --all --format json` and record per-key counts (`stale_file_ref`, `ambiguous_file_ref`, `stale_symbol_ref`, `mislocated_symbol_ref`) in this issue, so the later delta is measurable and the Opus-reported flood figures (222 false stale refs for unsuffixed bare names) can be re-checked.
2. Add the defined-in vs imported-in rule in `symbol_claims` (`symbol_defined_in_file`), routed to `mislocated_symbol_ref` (definition-shaped claims only; honor `ll-prose-ok`).
3. Add `stale_line_ref` (advisory, via `_ADVISORY_GAP_CLASSES`) and line-suffixed bare-filename resolution (0/1/>1, sorted candidates, mirror-only distinct, `(new)` markers skipped, unsuffixed bare names left unchecked) in `check_format_gaps` / `text_utils`; widen scope to Integration Map, Tests and Wiring Phase with fence skipping.
4. Surface the new key(s) in `ll-issues format-check` text/JSON output.
5. Add check B8 to `commands/verify-issues.md` (format-check keys authoritative only for existence/line-range/definition-location; content and premise findings stay verdict-bearing; fail-open; name format-check as owner); regenerate host mirrors.
6. Tests per the Tests section, including the run-twice byte-identical determinism test; run `python -m pytest scripts/tests/`.
7. **After:** re-run the `--all` per-key counts, record the before/after delta here, and confirm `rn-remediate.yaml`'s format-check exit-code gate and confidence-check CLAIM_GAP do not regress materially.
8. Replay the BUG-3689 case: a fixture with `runner_spec.py:335` (bare, line-suffixed) and `cli/loop/feed.py:terminal_size()` must surface on pass 1.
9. **Sequencing:** land before BUG-3695 (both edit `commands/verify-issues.md`, host mirrors and the prose baseline; serialize them). Wiring Phase / Root Cause citation defects surfaced on pass 1 are repaired only via ENH-3690's route (see Proposed Solution item 6).

## Impact

- **Priority**: P3 - causes a late-pass `GATE_UNMET` run end, but only when a citation defect exists
- **Effort**: Medium–Large - extend format-check (3 rules + scope widening), one verify-issues check, a before/after backlog measurement, mirrors and tests (no new CLI)
- **Risk**: Medium - the defined-in rule can false-positive on usage-site citations (mitigated by conservative trigger + suppression marker); widened scope and bare-name resolution can flood existing issues with new stale refs (mitigated by suffix-only resolution and the baseline/delta step); demoting unbacked model findings is limited to format-check-decidable properties so content/premise defects stay verdict-bearing
- **Breaking Change**: No

## Steps to Reproduce

1. Run `ll-loop run refine-to-ready-issue BUG-3689` against an issue whose Tests section cites a symbol by the importing module rather than the defining module.
2. Compare the per-pass verify summaries in `.loops/.running/<run>.log`.

## Root Cause

Citation verification is performed by the model with ad-hoc reads/greps (the passes reported "direct reads and greps", no graph queries), not by a deterministic check, so coverage varies per pass.

## Acceptance Criteria

- Repeated `--check` passes over an unchanged issue yield the same citation findings (byte-identical `format-check --format json` across two runs; `verify-issues` raises no citation finding that format-check does not back up).
- A bare filename citation is resolved by search (0 / 1 / >1 tracked paths), never reported as a different path.
- A symbol cited via a module that only imports it (BUG-3689's `cli/loop/feed.py:terminal_size()`) is reported `mislocated_symbol_ref` on pass 1, including in Tests / Wiring Phase sections.
- A cited line beyond end of file is reported as `stale_line_ref` (advisory: no exit-code or gate effect).
- Planned-new (`(new)`) files are not reported stale.
- Unsuffixed bare names (no `:N` / `:symbol()`) are not newly flagged; a line-suffixed bare name resolving to 0 / 1 / >1 tracked paths is reported stale / ok / ambiguous with sorted candidates.
- B8 treats format-check as authoritative only for existence, line-in-range and definition location; a citation finding about claimed line *content* or a premise stays verdict-bearing.
- The per-key `ll-issues format-check --all` counts before and after the change are recorded in this issue, with no unexplained rise in `rn-remediate` format-issue routing.
- Pass-1 citation defects in Wiring Phase / Root Cause are explicitly routed via ENH-3690 (routing recorded), not silently left to end the run `NON_VALID`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-01 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Scope vs ENH-3690: B8 governs only a path/line/symbol-location finding that `ll-issues format-check` does not back up — it is demoted to an advisory note and does not affect the verdict. Format-check-backed findings feed ENH-3690's repair route; premise-changing non-citation findings stay `NON_VALID` (ENH-3690).

**Note** (2026-10-02 advisor review): B8's demotion covers only format-check-decidable properties (existence, line-in-range, definition location). Citation findings about claimed line content stay verdict-bearing. This issue does not widen §2C's correctable scope; repair of pass-1 Wiring Phase / Root Cause defects is ENH-3690's route.

## Session Log
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
