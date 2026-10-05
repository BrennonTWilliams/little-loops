---
id: ENH-3742
title: Persist named risk factors in confidence-check scores and report deltas on re-score
type: ENH
priority: P3
status: open
discovered_date: '2026-10-05'
labels:
- verification
- confidence-check
---

## Summary

`/ll:confidence-check`'s coarse scoring buckets can miss a real change in risk composition. FEAT-3504 was split to separate untested stateful page work from the transport change. Its re-score came back **85/64, identical to before**: the bucket totals did not move, though the Concerns prose did change (the page bullets were gone; the transport and submit-path bullets were unchanged).

Persist named risk factors alongside the scores. On re-score, compare their identities and report added, removed and retained factors, so "did my change matter?" gets an answer even when the totals are static. Retained factors distinguish unchanged metadata from rewording or reclassification. A removed factor means it is no longer reported for this issue, not that its risk has been independently verified as resolved.

This is additive to scoring: no rubric change, no threshold change, no migration and no forced re-scoring of existing issues. It is the first, separable step of a broader scoring-granularity change (continuous scoring for countable inputs, per-site depth), which will be filed separately.

## Current Behavior

- Notes are conditional: `skills/confidence-check/SKILL.md`, Phase 4.5, appends `## Confidence Check Notes` only when `HAS_FINDINGS` is true. Outcome risk prose is currently threshold-gated; a clean re-score can append no notes at all. The notes template lives in `skills/confidence-check/rubric.md`.
- `## Resolved Concerns`, written by `/ll:reconcile-issue`, tells the scorer not to re-raise a listed concern without new evidence. It does not diff factor sets.
- `cmd_set_scores()` in `scripts/little_loops/cli/issues/set_scores.py` updates only explicitly supplied scalar fields using an unlocked read/overwrite of the issue file. Its separate `clear_scores(path: Path) -> bool` helper already uses the shared issue mutation lock and atomic writing.
- Score clearing is a normal precondition of re-scoring: `scripts/little_loops/preparation_policy.py`, `_run_preconditions()`; `commands/reconcile-issue.md`; and `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` all use it. Clearing a factor baseline at those sites would prevent the intended comparison.
- `scripts/little_loops/frontmatter.py`, `parse_frontmatter()` and `update_frontmatter()`, already support nested lists/maps in the canonical identity-bearing header. Factor records made of strings fit the reader's nested-scalar contract.
- `scripts/little_loops/cli/issues/set_flags.py`, `apply_flags_from_notes()`, scans the entire latest Notes section selected by `issue_parser._section_body()`. A different subsection heading alone does not isolate removed-factor descriptions from phrase matching.
- Nothing compares one run's risk factors with the previous run's.

## Expected Behavior

- Every successful non-check assessment records the complete factor set, including an explicit empty set, independently of display thresholds. Factors identify distinct reasons for a readiness/outcome point deduction or a hard-gate failure; a full-score criterion with no override contributes no factor.
- Re-scoring against a recorded baseline reports a deterministic delta in skill output. Any membership change is also recorded in a new Notes section, including unchanged totals and a transition to no factors. Existing finding-bearing Notes include the comparison even when membership is unchanged.
- The first factor-aware assessment of an issue reports that no prior baseline exists, even when numeric scores already exist. Legacy prose is not converted into a guessed baseline.
- The stored set means **last assessment that recorded factors**. It can outlive cleared scores or a later scores-only update, and is never evidence of score freshness or a gate input.

## Motivating Example

The FEAT-3504 re-score, raw bucket sum 64:

| Criterion | Score | Why it didn't move |
| --- | --- | --- |
| Complexity | 10 | About 8 code files plus 5 docs, still in the 6–15 breadth bucket; whole-issue depth "Moderate" |
| Test coverage | 18 | "Most modules": new `policy_builder_routes.py` and `do_POST` lack tests |
| Ambiguity | 18 | The checker still flags a bare-token redirect as a minor open question |
| Change surface | 18 | 3–5 callers, unchanged by the split |

The split removed exactly the risk the rubric cannot see. The qualitative layer tracked the change; the numeric layer could not. A factor delta makes that visible without touching the numbers.

## Program Design

### Types

Store one `risk_factors` list in canonical frontmatter. Each record is a mapping with exactly four required string fields:

```yaml
risk_factors:
- id: missing-submit-tests
  domain: outcome
  criterion: test_coverage
  description: Submit route and POST handler have no regression tests.
```

- `id` is unique within the issue and is the sole matching key. It is a lowercase slug matching `^[a-z0-9][a-z0-9-]{0,47}$`, independent of description wording, file line numbers and numeric scores.
- `domain` is `readiness` or `outcome`; hard-gate failures belong to readiness. `criterion` is a non-empty label for the existing criterion or gate, not a new rubric enum enforced by the CLI. Descriptions are non-empty, single-line text.
- The scorer assesses the issue, then reconciles identities with the prior list: reuse an ID for the same underlying risk, omit it when no longer supported, and mint a new ID only for a distinct risk. Honor existing Resolved Concerns suppression; do not mechanically carry prior factors forward.
- Rewording or changing a factor's domain/criterion retains its ID and reports the changed metadata fields. Exact ID matching only; no similarity fallback. An ID removed on one run and later reintroduced is added relative to the immediately preceding recorded set.
- Sort persisted records and delta entries by ID. Retain only the latest set; prior records needed for a removed entry come from the pre-write read, not a second permanent history field.

### CLI and Baseline Contract

Extend `set-scores`/`ss` with a **planned** `--risk-factors-file PATH` option accepting a JSON array; `-` reads stdin. Add optional JSON result output. The existing scalar-only invocation retains its quiet success, no-flags warning, omitted-field and exit-code behavior.

| Input/state | Behavior |
| --- | --- |
| Factor option omitted | Preserve the last recorded set; JSON reports `recorded: false`; no comparison is claimed. |
| Valid array, including `[]` | Replace the complete list; `[]` remains an explicitly present, known-empty baseline. Factor-only CLI writes are allowed. |
| Prior key absent | Record the new set; report `baseline: absent` and no comparable delta, not "everything added". |
| Prior valid list present, including `[]` | Report `baseline: present` and compare exact IDs. |
| Ordinary `--clear` / `clear_scores()` | Remove the existing six numeric fields only; preserve factors for the next re-score. `--clear` remains exclusive with score/factor updates. |
| Malformed input or malformed stored baseline | Actionable stderr and nonzero exit; no scores or factors change. Scores-only calls need not validate the retained factor list. |

Validation covers file/read/JSON errors, a non-array root, record shape, required string fields, invalid IDs/domains, multiline or empty descriptions, and duplicate IDs. Do not add general score-range validation or new dependencies in this issue.

The read of the previous baseline, comparison, frontmatter update and write use one shared issue-tree mutation lock (`issue_lock_path(path, config.issues.base_dir)` / `acquire_lock()`) and `atomic_write()`. Use that same locked path for scalar-only updates. Return a successful comparison only after the write succeeds; preserve unrelated metadata and issue body text.

The JSON result has `issue_id` and a `risk_factors` object. With recorded factors, that object contains `recorded: true`, `baseline: absent|present`, the assessed `factors` list, and `added`, `removed`, `retained`. For an absent baseline the three comparison fields are `null`; for a present baseline they are arrays, including empty arrays. Added entries contain new records, removed entries prior records, and retained entries contain the assessed record plus a `changed_fields` list drawn from `domain`, `criterion`, `description`. An empty `changed_fields` means fully unchanged. With no factor input, return only `recorded: false` and baseline presence under this object.

### Signatures

- Existing entry point: `cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int` in `scripts/little_loops/cli/issues/set_scores.py`.
- Existing clearing helper: `clear_scores(path: Path) -> bool`; its six-key removal contract stays intact.
- Proposed internal data types: `RiskFactor`, `RetainedRiskFactor`, `RiskFactorDelta` dataclasses in the score-writer module; records expose string fields and delta lists rather than embedding prose parsing.
- Proposed pure helpers: `parse_risk_factors(raw: str) -> list[RiskFactor]` and `diff_risk_factors(previous: list[RiskFactor] | None, assessed: list[RiskFactor]) -> RiskFactorDelta`. These names describe new helpers, not existing APIs.

### Call Path

Confidence-check Phase 4 → `main_issues()` parser/dispatch → `cmd_set_scores()` → factor validation and locked baseline read/diff → `frontmatter.update_frontmatter()` → `file_utils.atomic_write()` → JSON result → skill rendering. Generic frontmatter support already exists; no `IssueInfo`/`show --json` expansion is required.

### Skill, Notes and Flags

- Factor collection covers both readiness and outcome deductions/overrides, even above the configured display threshold. Membership must not disappear merely because a score crosses that threshold.
- In non-check mode, pass factors and all six scores together and consume the CLI's comparison; the model does not independently recompute the delta. Use stdin or a uniquely allocated issue-scoped temporary file so concurrent runs cannot share payloads.
- On input-validation rejection, repair the payload and retry once. If still rejected, persist the valid numeric scores through the existing scores-only call, retain the baseline, and explicitly report `risk factors not recorded; delta unavailable`. Continue other issues in auto/batch/sprint mode. Other write/lock/issue-resolution failures remain reported failures, not successful comparisons.
- `--check` performs no score/factor/notes/staging/log/flag writes and does not call the mutating writer. Preserve existing check-mode output and exit behavior; do not claim a persisted delta in that mode.
- Append one Notes section when existing `HAS_FINDINGS` is true **or** a recorded comparison contains added/removed IDs. A clean all-removed result therefore still writes notes. Clean first-run and retained-only assessments report their baseline/comparison in normal output without adding otherwise empty notes to every legacy issue.
- Place delta details under `### Risk Factor Delta`, separate from active concerns/gaps/outcome risk prose. Label removed factors as no longer reported, with no claim of verified resolution. Keep Session Log and Resolved Concerns intact; never translate delta removals into Resolved Concerns entries.
- Exclude the entire exact `### Risk Factor Delta` subsection from `set-flags` phrase matching, both for default issue notes and supplied full notes via `--from-notes`. A heading choice alone is insufficient because the scanner reads the full latest Notes section. Preserve legacy note matching elsewhere, existing numeric preconditions and set-only flag behavior; do not derive flags from the structured list or auto-clear flags on removal.

## Implementation Steps

1. The score CLI accepts structured factors, distinguishes absent/empty/omitted data, and returns the specified deterministic comparison from the same locked atomic write that records it. Existing scalar-only and clear behavior remains covered in `scripts/tests/test_set_scores_cli.py`.
2. Confidence-check collects deduction/override factors independently of prose thresholds, reuses prior IDs and renders the CLI result. `SKILL.md`, `rubric.md` and `reference.md` agree on single, batch, sprint, clean-delta and read-only check behavior; payload failures have the bounded retry/scores-only fallback above.
3. Delta notes cannot activate flags from historical text. The default and supplied-note scans in `apply_flags_from_notes()` exclude that subsection while preserving matching of active findings and legacy notes.
4. CLI and issue-metadata documentation describe the last-recorded baseline, identity/metadata changes, JSON contract and clear semantics. Appropriate local tests pass under `python -m pytest scripts/tests/`; no workflow or paid CI is added.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/set_scores.py` — factor validation/diff/result, locked atomic persistence; preserve `SCORE_KEYS`/`clear_scores()` semantics.
- `scripts/little_loops/cli/issues/__init__.py`, `main_issues()` — option registration/help and existing `ss` alias/dispatch.
- `scripts/little_loops/cli/issues/set_flags.py`, `apply_flags_from_notes()` — explicit delta-subsection exclusion from phrase matching.
- `skills/confidence-check/SKILL.md`, Phase 4/4.5/4.6 and mode behavior — factor generation, persistence/result handling, notes and flag isolation.
- `skills/confidence-check/rubric.md`, notes/output templates, and `skills/confidence-check/reference.md`, single/batch output guidance — consistent delta presentation without rubric changes.
- `docs/reference/CLI.md`, `ll-issues set-scores` section, and `docs/reference/ISSUE_TEMPLATE.md`, frontmatter documentation — new input/result and baseline semantics.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/preparation_policy.py`, `_run_preconditions()`; `commands/reconcile-issue.md`; `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — clear-before-rescore consumers; retained baseline is required, with no new ordering dependency.
- `scripts/little_loops/frontmatter.py`, `parse_frontmatter()` / `update_frontmatter()` — nested metadata reader/writer support.
- `scripts/little_loops/issue_parser.py`, `_section_body()` — latest Notes selection. Preserve this selection contract and existing numeric score parsing.
- `scripts/little_loops/cli/issues/show.py`, `_parse_card_fields()`, and `IssueInfo` serialization — explicit numeric score projections; structured-factor display/model expansion is outside scope.

### Conventions in Force

- JSON file/`-` stdin input and validation before mutation already exist in `scripts/little_loops/cli/issues/create.py`, `cmd_create()` / `validate_metadata()`; factor-specific validation must not inherit creation-only reserved-key policy.
- Nested updates target the canonical header and replace the supplied key's whole value: `frontmatter.update_frontmatter()`; do not add a second fenced store or hand-render YAML.
- Shared locked atomic mutation exists in `scripts/little_loops/cli/issues/set_status.py`, `apply_status_transition()`, and `file_utils.py`; test the score transaction's use of those helpers rather than re-testing lock algorithms.

### Tests

- `scripts/tests/test_set_scores_cli.py` — input/result, diff, compatibility and transaction behavior.
- `scripts/tests/test_confidence_check_skill.py` — skill wiring, all modes, threshold-independent collection, clean-delta notes and fallback instructions.
- `scripts/tests/test_set_flags_cli.py` — removed signal phrases in delta notes are excluded, while active/legacy findings still match.
- `scripts/tests/test_frontmatter.py` — existing nested/canonical-block coverage; add round-trip preservation coverage only where the new record shape is not already exercised.
- `scripts/tests/test_preparation_policy_writers.py`, `TestRescorePrecondition` — factor baseline survives the real clear-before-rescore flow.

## Impact

Makes risk composition changes visible when aggregate scores stay fixed, including scope splits such as FEAT-3504. The main limitation is model-assigned identity stability: re-slugging the same risk can still create a noisy add/remove pair. Prior-ID reuse instructions and metadata-aware retention reduce that noise without inventing a similarity heuristic.

## Acceptance Criteria

1. A successful factor-bearing write persists the complete last-assessed list alongside any supplied scores in canonical frontmatter. Explicit `[]`, omitted input and an absent legacy baseline have distinct behavior; unrelated frontmatter/body survive. After an unrelated status/frontmatter update, `parse_frontmatter()` still returns the factor records and the issue parser still reads the existing numeric scores correctly.
2. JSON comparison follows Program Design, is deterministic under input reordering, and distinguishes fully unchanged retained factors from metadata changes under the same ID. First assessments report an absent baseline with `null` comparison lists; a known-empty baseline produces ordinary array comparisons.
3. Re-scoring with identical totals and changed membership reports a non-empty delta in skill output and a new Notes section. Removing the final factor works when `HAS_FINDINGS` is otherwise false. Threshold crossing alone does not add/remove a factor.
4. Numeric score clearing, including the automated clear-before-rescore precondition, preserves the baseline; scalar-only partial updates and factor-only CLI writes follow the specified omitted-field behavior. Factors never supply score freshness or gating evidence.
5. Malformed JSON, invalid record shape/fields and duplicate IDs leave issue bytes unchanged and write no scores. The read/diff/write uses the shared lock and atomic writer; write failure emits no successful result. Skill validation failure has the bounded repair and explicitly reported scores-only fallback, without stopping other batch issues.
6. Removed/historical signal phrases inside `Risk Factor Delta` cannot set flags through either note-input path. Active findings elsewhere still match; existing true flags are not cleared by factor removals.
7. Single/auto/batch/sprint modes use the same factor contract. `--check` retains its existing output/exit behavior and writes nothing. Notes preserve Session Log and Resolved Concerns structure, including the latest-notes behavior used by flags.
8. The five readiness criteria, four outcome criteria, point allocations, caps, configured readiness/outcome thresholds and flag preconditions are unchanged. Existing scored issues need no migration and retain their numeric behavior. Documentation covers the new CLI/metadata contract, and the relevant tests above exercise these outcomes.

## Scope Boundaries

- Scoring countable inputs (breadth, callers, coverage) by formula instead of bucket.
- Per-site depth classification with a weighted aggregate.
- Fuzzy matching, full factor history/previous-set storage, a baseline-reset option, new thresholds/gates, automatic flag clearing and deriving flags from structured factors.
- Factor display through `ll-issues show`/list or expansion of `IssueInfo`; the skill can read canonical frontmatter and the writer's JSON result.
- Changing existing score-range validation or fixing unrelated default-threshold documentation inconsistencies.

The two scoring changes shift existing scores and need a one-time re-check of issues near the configured outcome gate. They follow this change as separate work.

## Review Notes

Pre-implementation review on 2026-10-05 confirmed the additive approach and settled storage, identity, baseline lifecycle, validation/failure handling, notes triggers and flag isolation. `/ll:advise` with `claude-opus-5-5` recommended proceeding at P3 after tightening these contracts (confidence 0.78). Its principal dissent favored omitting notes for first/retained-only runs; the bounded notes policy above retains durable membership changes for automated runs. Its heading-only isolation suggestion was rejected against the verified whole-Notes flag scan; explicit subsection exclusion is required.

## Session Log

- `/ll:refine-issue` - 2026-10-05T20:38:16 - `e4d031f4-efb7-4acd-b532-6b7d02eab780.jsonl`

## Status

Open — pre-implementation review complete; implementation has not started.
