---
id: ENH-3061
title: prose-dep gate flags example prose in issues that document the extractor
type: ENH
priority: P4
status: open
testable: true
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T16:06:39Z'
relates_to:
- BUG-3057
- FEAT-2849
- FEAT-2850
labels:
- issues
- gates
- authoring
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3061: prose-dep gate flags example prose in issues that document the extractor

## Summary

Writing an issue *about* the prose-dependency extractor requires quoting
dependency prose as examples, and the extractor charges those examples to the
issue as real dependency claims. `_in_fence` recognizes fenced code blocks but
not inline backticks, so the only escape hatch is a multi-line fence — heavy
markup for what is often a four-word phrase mid-sentence.

## Motivation

This is not hypothetical. BUG-3057, the issue documenting the attribution bug in
this very extractor, failed `format-check` on its own body during authoring and
needed two example phrases restructured into fenced blocks before it would pass.

The friction is narrow but self-inflicted: the subsystem's own documentation is
the corpus most likely to trip its gate, so the people best positioned to
maintain it hit the worst authoring experience.

## Current Behavior

`issues/prose_deps.py:64` builds fence spans from `_CODE_FENCE` only:

```python
fence_spans = [(m.start(), m.end()) for m in _CODE_FENCE.finditer(body)]
```

`_in_fence` (`issues/prose_deps.py:44`) then suppresses any match inside those
spans. Inline-backtick runs are not collected, so a phrase written as inline
code is still extracted and reported as `prose_dep_drift`.

BUG-3057's attribution fix helps only when the example names another issue as
its sentence subject. An example with no named subject — such as this one,
which had to be fenced for this very issue to pass its own gate:

```markdown
Depends on FEAT-109
```

is still attributed to the host.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Anchors have drifted since capture: `_in_fence` is now at `issues/prose_deps.py:78-79` (not `:44`), `extract_prose_deps` at `issues/prose_deps.py:82-131` (not `:48`), and the `fence_spans` construction at `issues/prose_deps.py:104` (not `:64`). `text_utils.py:25` for `_CODE_FENCE` is unchanged.
- `_in_fence` is duplicated verbatim (identical body) in at least two other modules in this family — `issues/cli_claims.py:43-44` and three inline test-local closures in `tests/test_ready_issue_lint.py:59-60,72-73,87-88` — rather than factored into `text_utils.py`. This is the established shape for this module family, not an anomaly specific to `prose_deps.py`.
- `fence_spans` is always rebuilt per-call as an inline list-comprehension inside the `extract_*` function (`prose_deps.py:104`, `symbol_claims.py:149`, `cli_claims.py:73`) — never cached, never split into its own named helper. Only the containment test (`_in_fence`) is factored into a helper in the existing convention.

## Expected Behavior

An issue ID inside an inline-backtick span is treated the same as one inside a
fenced block: not a dependency claim. Authors can write an example inline without
promoting it to a fenced block, and without the gate producing a finding that
must be worked around rather than fixed.

## Proposed Solution

Collect inline-code spans alongside fenced ones and pass both to `_in_fence`.

An inline span is a backtick run of length N delimiting content up to the next
run of exactly N backticks on the same line, matching CommonMark closely enough
for issue bodies. The existing `_CODE_FENCE` collection is unchanged; the two
span lists concatenate, and `_in_fence`'s containment test already generalizes
over any span list.

Worth confirming during implementation: whether this should live in
`text_utils` beside `_CODE_FENCE` rather than in `prose_deps`, since other gates
(`stale_file_ref`, `ambiguous_file_ref`) plausibly want the same treatment and
may already have the same latent defect.

Explicitly out of scope: relaxing the gate, adding a per-issue suppression key,
or exempting issues by label. The gate is correct to be strict — the problem is
only that the existing escape hatch is coarser than the common case.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issues/prose_deps.py` — add an inline-code-span collector and concatenate its spans with the existing `fence_spans` list built at line 104; `_in_fence` (line 78-79) and `extract_prose_deps` (line 82-131) are otherwise unchanged, per the Proposed Solution.
- `scripts/little_loops/text_utils.py` — candidate second location for the new collector, beside `_CODE_FENCE` (line 25), if the placement question in Program Design resolves toward the shared-module side.

### Dependent Files (Callers)
- `scripts/little_loops/issue_parser.py:646-669` — `check_format_gaps` calls `extract_prose_deps(body_only, host_id=own_id)` at line 662; this is the source of the `prose_dep_drift`/`stale_prose_dep` gate keys this issue is about.
- `scripts/little_loops/cli/issues/sequence.py:15-44` — `_unverified_prose_deps` independently calls `extract_prose_deps(body_only, host_id=issue.issue_id)` at line 38; inherits the fix automatically, no separate change needed.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py:284,298,328,342` — `cmd_format_check()` calls `check_format_gaps()`, the CLI entry point that surfaces `prose_dep_drift`/`stale_prose_dep` findings; completes the call path one hop past `issue_parser.py:662` to the actual `ll-issues format-check` surface. No code change needed here. [Agent 1 finding]

### Conventions in Force
- Fence-aware extractors in this family (`prose_deps.py`, `symbol_claims.py`, `cli_claims.py`) each define their own local `_in_fence` and backtick-span regex rather than sharing one from `text_utils.py` — evidence: `cli_claims.py:43-44` duplicates `_in_fence` verbatim; `symbol_claims.py:49` and `cli_claims.py:19` each independently define `_BACKTICK_SPAN_RE` with the identical pattern. A new inline-span collector following this convention would be added locally rather than imported, unless this issue explicitly chooses the shared-module route (see Program Design's `ENH-974` note).
- `symbol_claims.py` establishes a distinct suppression convention for "this is a documented example, not a real claim" — an `<!-- ll-prose-ok: reason -->` comment on the preceding line (`symbol_claims.py:90,106-113`, originating in `cli/verify_skill_prose.py:19-20,111`). This is a different mechanism (explicit opt-out) from the inline-backtick-span suppression this issue proposes (implicit, based on markup) — evidence the two are not redundant with each other, since `symbol_claims.py` needs the comment convention precisely because its extraction *targets* backtick spans and can't use "in backticks" as a suppression signal the way `prose_deps.py` can.

### Tests
- `scripts/tests/test_prose_deps.py:87-97` (`test_ignores_ids_in_fenced_code`) and `:100-111` (`test_blocked_by_section_ignores_fenced_ids`) are the existing fence-suppression tests; both cover only triple-backtick fencing. No test in this file exercises single-backtick/inline suppression today.
- Naming convention observed across the codebase for this test shape: "fence"/"fenced" plus a verb — `test_ignores_ids_in_fenced_code`, `test_no_claim_inside_fenced_code_block` (`test_symbol_claims.py`, `test_cli_claims.py:48`), `test_skips_code_fence_region`/`test_skips_code_fence` (`test_sweep_stale_refs.py:206,333`), `test_ref_inside_fence_not_flagged` (`test_ready_issue_lint.py:80`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_prose_deps.py` — add `test_ignores_ids_in_inline_code` and `test_blocked_by_section_ignores_inline_code_ids`, placed adjacent to the existing fence pair (`:87-111`), mirroring their exact structure with single backticks in place of triple-backtick fences. No existing test in this file asserts an ID *is* extracted from inline-backtick text today, so none need updating — these are pure additions. [Agent 3 finding]
- `scripts/tests/test_prose_dep_sweep_gate.py` (`test_no_prose_dependency_drift_in_repo`) — repo-wide sweep over all active `.issues/` files via `check_format_gaps`, asserted green on `main`. Semantically coupled to this fix (it's the integration test most likely to notice a behavior change) but cannot regress: it can only stay green or newly reveal a previously-masked true positive. No change needed; flagged for awareness only. [Agent 3 finding]

## Program Design

### Signatures

- `_in_fence(start: int, end: int, fence_spans: list[tuple[int, int]]) -> bool` — existing, `issues/prose_deps.py:44`; unchanged, already generalizes over any span list.
- `extract_prose_deps(body: str, host_id: str | None = None) -> set[str]` — existing, `issues/prose_deps.py:48`; span collection at line 64 gains inline spans.
- `_CODE_FENCE: re.Pattern[str]` — existing, `text_utils.py`; unchanged.
- `_inline_code_spans(body: str) -> list[tuple[int, int]]` — new, location to be decided between `prose_deps` and `text_utils`.

### Call Path

`check_format_gaps` (`issue_parser.py:396`) -> `extract_prose_deps` (`issues/prose_deps.py:48`) -> `_in_fence` (`issues/prose_deps.py:44`). The new span collector feeds the same `fence_spans` list that `_CODE_FENCE.finditer` currently populates alone, so no call-site signature changes. Second consumer `unverified_prose_deps` (`cli/issues/sequence.py:16`) inherits the behavior unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Anchor correction: `_in_fence` is at `issues/prose_deps.py:78-79` (issue currently says `:44`); `extract_prose_deps` is at `issues/prose_deps.py:82-131` (issue currently says `:48`); `fence_spans` construction is at `issues/prose_deps.py:104` (issue currently says `:64`). `text_utils.py:25` for `_CODE_FENCE` is correct as cited.
- An inline-backtick-span regex already exists in this codebase, independently defined twice with an identical pattern: `symbol_claims.py:49` and `cli_claims.py:19`, both `_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")`. Neither does CommonMark-style backtick-run matching (N backticks paired to the next run of exactly N) — both are single-backtick, non-greedy-to-newline. `program_design.py:105` has a third near-identical copy (`_BACKTICKED = re.compile(r"`([^`]+)`")`, no `\n` exclusion). No module does true run-length matching; a new `_inline_code_spans` implemented as single-backtick-only would match the codebase's existing precedent rather than deviate from it.
- On the placement question the Proposed Solution leaves open (`text_utils` vs `prose_deps`): the codebase currently has a live, filed, `deferred` (not `done`) issue — `.issues/enhancements/P4-ENH-974-code-fence-stripping-duplicated-across-modules.md` — tracking the same import-vs-duplicate split for `_CODE_FENCE` itself (`dependency_mapper/analysis.py:28` still locally duplicates `_CODE_FENCE` instead of importing it). This is direct precedent that the "shared in text_utils" placement is the codebase's stated target state for fence/span regexes in this family, though it remains unresolved elsewhere in the codebase today.
- Second consumer confirmation: `_unverified_prose_deps` (issue currently cites `cli/issues/sequence.py:16`) is at `cli/issues/sequence.py:15-44`, and independently re-derives `structured_deps` before calling `extract_prose_deps` at `sequence.py:38` — it is a separate call site, not a re-export, so it inherits the fix automatically once `extract_prose_deps` itself is corrected, with no separate code change needed there.
- `issue_parser.py:671-687` (`soft_dep_hard_edge` detection) also reuses `_in_fence`/`_CODE_FENCE` directly against paragraph spans with the same fence-only suppression. It is in scope only if a future pass confirms it shares the same false-positive exposure — Scope Boundaries already excludes it from this issue, this is supporting evidence for that boundary being correctly drawn, not a call to widen it.

## Scope Boundaries

**In scope**: inline-backtick span collection feeding the existing `_in_fence`
suppression, for `prose_dep_drift` and `stale_prose_dep`.

**Out of scope**: relaxing the gate's phrase list, per-issue suppression keys,
label-based exemptions, and any change to attribution (BUG-3057's concern).
Extending the same treatment to `stale_file_ref` / `ambiguous_file_ref` is a
plausible follow-up but should be confirmed as a real defect first, not assumed.

## Impact

Authoring friction on a narrow but recurring class of issue. No correctness
impact: the gate's findings on real dependency claims are unaffected, and the
current workaround (fenced blocks) does work.

Low priority because the corpus of affected issues is small — those documenting
`prose_deps`, `format-check`, and the issue-gate family. It earns capture because
the workaround is invisible to the next author, who will rediscover it the same
way.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/reference/CLI.md` § format-check | Documents `prose_dep_drift` and its remedies |
| `docs/reference/API.md` § check_format_gaps | Gap-class reference including fence behavior |

## Status

**Open**

## Session Log
- `/ll:confidence-check` - 2026-08-06T02:49:04 - `8261be84-d0d0-4d57-8c61-d48eb1009eae.jsonl`
- `/ll:verify-issues` - 2026-08-06T02:47:05 - `49441385-227b-43ee-a778-cf10f3432c0e.jsonl`
- `/ll:wire-issue` - 2026-08-06T02:44:00 - `ac96a421-ca52-45fc-a963-abd2a97d00f4.jsonl`
- `/ll:refine-issue` - 2026-08-06T02:33:50 - `10629b96-50aa-4228-aa81-f7e02d80af10.jsonl`
- `/ll:capture-issue` - 2026-08-05T16:09:36 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- `/ll:capture-issue` - 2026-08-05 - Captured from the ENH-3046 run forensics
  session, after BUG-3057 tripped its own gate during authoring.
