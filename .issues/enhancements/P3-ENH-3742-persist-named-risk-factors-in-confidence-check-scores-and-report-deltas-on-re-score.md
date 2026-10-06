---
id: ENH-3742
title: Persist named risk factors in confidence-check scores and report deltas on re-score
type: ENH
priority: P3
status: open
discovered_date: '2026-10-05'
verify_verdict: CLAIMS_OUTDATED
verify_evidence: "Verification Notes: 'quotes the slash-joined shorthand skill/rubric/reference/CLI.md verbatim, which format-check still flags as stale_file_ref' -> reword the note so it does not contain a slash-joined path token (e.g. describe it as a slash-joined shorthand for skill, rubric, reference and CLI.md text)"
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
- `scripts/little_loops/cli/issues/set_flags.py`, `apply_flags_from_notes()`, scans the entire latest Notes section selected by `issue_parser._section_body()`. It also passes the original notes to `_co_deliverable_suppressor()`: a historical filename matching `### Files to Create` can suppress a real active `missing_artifacts` finding and spuriously set `implementation_order_risk`, even when that filename's delta text contains no signal phrase. Filtering only the phrase-matching copy is insufficient.
- `clear_scores(path)` currently derives its lock with the default `.issues` name, whereas configured mutators pass `config.issues.base_dir`. For a custom basename such as `tickets`, clearing locks the type directory while configured writes lock the issue tree.
- Nothing compares one run's risk factors with the previous run's.

## Expected Behavior

- Every non-check assessment supplies the complete factor set, including an explicit empty set, independently of display thresholds. Successful factor writes record that set; persistent validation failure follows the explicitly reported scores-only fallback below. Factors identify distinct reasons for a readiness/outcome point deduction or a hard-gate failure; a full-score criterion with no override contributes no factor.
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
- `domain` is `readiness` or `outcome`; hard-gate failures belong to readiness. `criterion` is a non-blank, single-line label for the existing criterion, cap or gate, not a new rubric enum enforced by the CLI. Descriptions are non-blank, single-line text. Reject whitespace-only labels/descriptions and embedded LF/CR rather than silently normalizing them.
- Name concrete, independently removable concerns rather than one omnibus factor per low-scoring bucket. For example, `missing-page-tests` and `missing-submit-tests` are separate factors even when both contribute to the same test-coverage deduction. Repeated mentions or multiple scoring effects of the same concern share one ID; choose its primary domain/criterion and describe other effects without duplicate records. A changed score magnitude alone does not create a new identity. A broad/deep change can itself be a factor when it explains a complexity deduction.
- The scorer assesses the issue, then reconciles identities with the prior list: reuse an ID for the same underlying risk, omit it when no longer supported, and mint a new ID only for a distinct risk. Honor existing Resolved Concerns suppression; do not mechanically carry prior factors forward.
- Rewording or changing a factor's domain/criterion retains its ID and reports the changed metadata fields. Exact ID matching only; no similarity fallback. An ID removed on one run and later reintroduced is added relative to the immediately preceding recorded set.
- Sort persisted records and delta entries by ID. Retain only the latest set; prior records needed for a removed entry come from the pre-write read, not a second permanent history field.

### Decision Rules

Extend `set-scores`/`ss` with a **planned** `--risk-factors-file PATH` option accepting a JSON array; `-` reads stdin. Add `--json`/`-j` result output. Without JSON output, successful factor-bearing calls also remain quiet; the skill requests JSON to render the comparison. The existing scalar-only invocation retains its quiet success, no-flags warning, omitted-field and exit-code behavior.

| Input/state | Behavior |
| --- | --- |
| Factor option omitted | Preserve the last recorded set; JSON reports `recorded: false`; no comparison is claimed. |
| Valid array, including `[]` | Replace the complete list; `[]` remains an explicitly present, known-empty baseline. Factor-only CLI writes are allowed. |
| Prior key absent | Record the new set; report `baseline: absent` and no comparable delta, not "everything added". |
| Prior valid list present, including `[]` | Report `baseline: present` and compare exact IDs. |
| Ordinary `--clear` / `clear_scores()` | Remove the existing six numeric fields only; preserve factors for the next re-score, including an invalid baseline. `--clear` remains exclusive with score/factor updates; `--json` is allowed. |
| Invalid caller factor input | Actionable factor-input diagnostic on stderr, exit 2 and empty stdout; no scores or factors change. Includes input-file/read/JSON and record-validation failures. |
| Malformed stored baseline or issue/read/lock/write failure | Actionable diagnostic on stderr, exit 1 and no successful JSON; no scores or factors change. Scores-only/clear calls need not validate the retained factor list. |

Validation covers file/read/JSON errors, a non-array root, record shape, required string fields, invalid IDs/domains, blank or multiline criterion/description values, and duplicate IDs. Do not add general score-range validation or new dependencies in this issue.

The read of the previous baseline, comparison, frontmatter update and write use one shared issue-tree mutation lock (`issue_lock_path(path, config.issues.base_dir)` / `acquire_lock()`) and `atomic_write()`. Use that same locked path for scalar-only updates and configured clear calls, including the preparation-policy precondition. Keep direct `clear_scores(path)` calls backwards compatible through an optional keyword-only base-directory argument. Return a successful comparison only after the write succeeds; preserve unrelated metadata and issue body text. An identical valid assessment is successful, with fully unchanged retained entries and no membership changes.

The JSON result has the resolved full `issue_id` (even when invoked with a numeric ID or `ss`) and a `risk_factors` object. With recorded factors, that object contains `recorded: true`, `baseline: absent|present`, the assessed `factors` list, and `added`, `removed`, `retained`. For an absent baseline the three comparison fields are `null`; for a present baseline they are arrays, including empty arrays. Added entries contain new records, removed entries prior records, and retained entries contain all four assessed record fields plus `changed_fields`, listed in stable `domain`, `criterion`, `description` order. An empty `changed_fields` means fully unchanged. With no factor input, including scalar-only, `--clear` and no-update calls, return only `recorded: false` and key-presence-based `baseline: absent|present` under this object; presence does not certify baseline validity. A no-update call still emits its existing warning on stderr, returns 0 and writes nothing. Read baseline presence under the same lock; `--json` never implicitly records factors.

The lock serializes individual writer transactions; it does not make the model's assessment or later Notes edits one atomic transaction. Concurrent same-issue assessments compare against the latest set at their respective commit times. Identity continuity is best assessed with one scorer per issue; whole-skill serialization, stale-assessment rejection and transactional Notes writing are outside this issue.

### Signatures

- `cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int` — existing entry point in `scripts/little_loops/cli/issues/set_scores.py`.
- `clear_scores(path: Path, *, base_dir: str = ".issues") -> bool` — proposed backwards-compatible extension to the existing clearing helper; its six-key removal contract stays intact. CLI/preparation-policy callers pass the configured base directory.
- Proposed internal data types: `RiskFactor`, `RetainedRiskFactor`, `RiskFactorDelta` dataclasses in the score-writer module; records expose string fields and delta lists rather than embedding prose parsing.
- `parse_risk_factors(raw: str) -> list[RiskFactor]` — proposed pure input helper, not an existing API.
- `diff_risk_factors(previous: list[RiskFactor] | None, assessed: list[RiskFactor]) -> RiskFactorDelta` — proposed pure comparison helper, not an existing API.

### Call Path

Confidence-check Phase 4 → `main_issues()` parser/dispatch → `cmd_set_scores()` → factor validation and locked baseline read/diff → `frontmatter.update_frontmatter()` → `file_utils.atomic_write()` → JSON result → skill rendering. Generic frontmatter support already exists; no `IssueInfo`/`show --json` expansion is required.

### Skill, Notes and Flags

- Factor collection covers readiness/outcome deductions, learning-test modifiers, criterion and aggregate caps, hard-gate overrides, and any correction-history adjustment applied by the existing assessment, even above the configured display threshold. An active unproven-mechanism cap contributes an outcome factor even when the raw sum already lies below the cap or all four dimensions otherwise score fully. Membership must not disappear merely because a score crosses a display threshold. This documents existing scoring inputs without changing their arithmetic.
- Read the prior list during context gathering for identity reuse, then assess current evidence independently. Resolved Concerns suppression prevents unsupported repetition; if current evidence still justifies a deduction/override, name that evidence rather than omit its factor merely because similar historical prose was resolved.
- In non-check mode, pass factors and all six scores together and consume the CLI's comparison; the model does not independently recompute the delta. Use stdin or a uniquely allocated issue-scoped temporary file so concurrent runs cannot share payloads.
- On the factor-input rejection above (exit 2 plus its factor-input diagnostic), repair the payload and retry once. If still rejected, persist the valid numeric scores through a separate scores-only call, retain the baseline, and explicitly report `risk factors not recorded; delta unavailable`. Fallback succeeds only if that scores-only call succeeds. Do not retry or fall back after an invalid stored baseline, issue-resolution, read, lock or write failure (exit 1); report that issue's assessment could not be persisted. Continue other issues in auto/batch/sprint mode. A failed write never produces a claimed comparison or delta Notes.
- `--check` performs no score/factor/notes/staging/log/flag writes and does not call the mutating writer. Preserve existing check-mode output and exit behavior; do not claim a persisted delta in that mode.
- Append one Notes section when existing `HAS_FINDINGS` is true **or** a recorded comparison contains added/removed IDs. A clean all-removed result therefore still writes notes. Clean first-run and retained-only assessments report their baseline/comparison in normal output without adding otherwise empty notes to every legacy issue.
- Place delta details under `### Risk Factor Delta`, separate from active concerns/gaps/outcome risk prose. Label removed factors as no longer reported, with no claim of verified resolution. Keep Session Log and Resolved Concerns intact; never translate delta removals into Resolved Concerns entries.
- Exclude every exact `### Risk Factor Delta` subsection before **both** `set-flags` phrase matching and co-deliverable suppression, for default issue notes and supplied full notes via `--from-notes`. Feed the same filtered notes to the matcher and suppressors. Each excluded span ends at the next real heading of level 1–3 or end of input; nested level-4 headings remain excluded. Use existing fence-span helpers so quoted headings inside code fences neither begin nor terminate exclusion. Preserve active prose after the subsection, latest-Notes selection, legacy matching elsewhere, numeric preconditions, direct frontmatter triggers and set-only behavior. Do not derive flags from structured factors or auto-clear flags on removal.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Exit-code split is a new convention, not an inherited one.** Every existing JSON-input command in `scripts/little_loops/cli/issues/` (`create.py` `--metadata-file`, `scaffold_epic.py` `--children`, `prioritize.py` `--apply`) reports bad JSON or bad records on stderr with exit 1; `set_scores.py` itself returns 1 for `--clear` combined with score arguments. Exit 2 appears only in predicate/state helpers (`check_flag.py`, `check_gate.py`, `check_readiness.py`, `rearm_spike.py`, `clear_verify_verdict.py`, `run_record.py`, `fold_findings.py --no-create`) where 1 means "false", and it is also argparse's usage-error code, so the code alone cannot separate a factor-payload rejection from an argparse rejection; the stderr diagnostic has to. The 1-vs-2 split specified above is therefore a deliberate deviation that the skill's retry-vs-no-retry branch depends on; the existing `--clear`-with-scores error (exit 1) must stay as it is.
- **`--json` destination name is contested.** `dest="json"` (via `add_json_arg()` in `scripts/little_loops/cli_args.py`, used by `set_flags.py`, `check_gate.py`, `size.py` and the inline list/show/search parsers) versus `dest="json_output"` (`create.py`, `scaffold_epic.py`, `link.py`). `set-scores` is registered inline in `main_issues()` and currently has neither. Printing goes through `scripts/little_loops/cli/output.py` `print_json` (indent 2) in most commands; `check_gate.py` and `refine_status.py` print compact JSON. The skill parses the result either way, so the choice only needs to be internally consistent and covered by a test.
- **Frontmatter round-trip facts the record shape depends on.** `update_frontmatter()` re-dumps the whole canonical block with `yaml.dump(..., default_flow_style=False, sort_keys=False)` (so comments in that block are not preserved and a list under a key is emitted with unindented `- ` items); `parse_frontmatter()` loads with the base loader, so nested record fields come back as plain strings with no type coercion, and if the block fails YAML parsing the line-based fallback cannot represent a list of maps. The canonical block is the first block carrying an `id` key; a `risk_factors` key living in a different block would be merged on read but never updated by the writer. The `gate:` frontmatter field (`check_gate.parse_gate`) is an existing list-of-maps reader precedent, but `scripts/tests/test_frontmatter.py` has no list-of-maps write/round-trip test (only list-of-strings and nested-dict cases), so that coverage is genuinely new. Slugs that look like other YAML scalars (all digits, `null`, `true`, `yes`) must round-trip as strings.
- **`clear_scores()` removal mechanics.** `remove_frontmatter_keys()` deletes a key's line plus following indented or `- `-prefixed continuation lines; `SCORE_KEYS` (six scalars) is the removal set, so `risk_factors` must stay out of it and the clear-then-reparse path needs a test with the unindented list layout the dumper produces.
- **Fence-helper limits that bound the delta-subsection exclusion.** `text_utils.fence_spans()` pairs triple-backtick marker lines only (tilde fences are not recognised, unlike `frontmatter._mask_fenced_code`) and fails open on an odd marker count, treating the unpaired opener as unfenced. `set_flags.py` currently has no fence awareness; its default Notes body ends only at the next unfenced `##` (via `issue_parser._section_body`) so `###` subsections are inside it, and `~~struck~~` spans are stripped before phrase matching but not before `_co_deliverable_suppressor`, which receives the raw notes text. The `--from-notes` path bypasses `_section_body` entirely and may carry a full Notes section or bare body text.
- **Reuse candidates for validation.** No shared slug-validation constant exists (`issue_parser._NORMALIZED_RE` and `cli/loop/rename.py` `_KO_RE` are filename/kebab patterns with different shapes), and there is no existing `diff_*` pure helper, so `parse_risk_factors`/`diff_risk_factors` have no sibling to align with beyond `check_gate.parse_gate` (pure parse returning typed specs) and `create.validate_metadata` (pure validator raising `ValueError` with path-bearing messages).

## Implementation Steps

1. The score CLI accepts structured factors, distinguishes absent/empty/omitted data, and returns the specified deterministic comparison from the same locked atomic write that records it. Cover JSON/no-JSON, alias, no-update and clear contracts, failure classes and the configured clear lock in `scripts/tests/test_set_scores_cli.py`; pass that configuration through the preparation-policy precondition.
2. Confidence-check collects concrete deduction/cap/override factors independently of prose thresholds, reuses prior IDs and renders the CLI result. `SKILL.md`, `rubric.md` and `reference.md` agree on single, batch, sprint, clean-delta and read-only check behavior; payload failures have the bounded retry/scores-only fallback above.
3. Delta notes cannot activate or suppress flags through historical text. The default and supplied-note scans in `apply_flags_from_notes()` exclude that subsection from both matching and suppression while preserving active findings, legacy notes and fence-aware heading boundaries.
4. CLI and issue-metadata documentation describe the last-recorded baseline, identity/metadata changes, JSON contract and clear semantics. Appropriate local tests pass under `python -m pytest scripts/tests/`; no workflow or paid CI is added.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/issue_parser.py` `count_open_questions_in_sections()` — decide and implement delta handling: exclude `### Risk Factor Delta` (fence-aware, same boundary rules as `set-flags`) before `_OPEN_QUESTION_SIGNAL_RE` counting, or phrase/define delta bullets so they cannot match; otherwise a restated factor description ending in `?` or containing "open question" inflates `OPEN_QUESTIONS_REMAIN`/`HEDGES` and stalls `refine-to-ready-issue`. Add the matching case to `test_issue_parser_unresolved.py` / `test_ll_issues_check_open_questions.py`.
- Review `scripts/little_loops/cli/issues/advise_consult.py` `trim_consult_context()` — decide whether `### Risk Factor Delta` should be trimmed with its parent Notes (today only the `## Confidence Check Notes` heading line's block up to the next `#{1,3}` heading is stripped); record the decision and pin it in `test_ll_issues_advise_consult.py`.
- Add `little_loops/cli/issues/set_scores.py` to the parametrized `test_mutation_module_has_no_write_text_call` in `scripts/tests/test_bug3150_issue_mutator_atomicity.py` and add lock/atomic/`tickets` cases for `set-scores`.
- Update `docs/reference/COMMANDS.md` (Findings write-back "no write occurs" sentence, Flag write-back delta exclusion), `docs/reference/CLI.md` (`set-flags` delta exclusion; exit-2 meaning for `set-scores`), `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (Confidence Scoring) and, if `count_open_questions_in_sections` changes, `docs/reference/API.md`.
- Register `--risk-factors-file` and `risk_factors` doc presence in `scripts/tests/test_wiring_reference_docs.py`.
- Update the `ss` epilog command line and examples block in `scripts/little_loops/cli/issues/__init__.py` `main_issues()` alongside the option registration.
- After editing `skills/confidence-check/`, regenerate host mirrors with `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply` so `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` / `test_skill_mirrors_carry_companions` pass, and keep `SKILL.md` ≤ 500 lines (currently 499), pushing detail into `rubric.md`/`reference.md`.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/set_scores.py` — factor validation/diff/result, locked atomic persistence; preserve `SCORE_KEYS`/`clear_scores()` semantics.
- `scripts/little_loops/cli/issues/__init__.py`, `main_issues()` — option registration/help and existing `ss` alias/dispatch.
- `scripts/little_loops/cli/issues/set_flags.py`, `apply_flags_from_notes()` — fence-aware delta-subsection exclusion from phrase matching and co-deliverable suppression.
- `scripts/little_loops/preparation_policy.py`, `_run_preconditions()` — pass the configured base directory to score clearing so the clear/write lock agrees.
- `skills/confidence-check/SKILL.md`, Phase 4/4.5/4.6 and mode behavior — factor generation, persistence/result handling, notes and flag isolation.
- `skills/confidence-check/rubric.md`, notes/output templates, and `skills/confidence-check/reference.md`, single/batch output guidance — consistent delta presentation without rubric changes.
- `docs/reference/CLI.md`, `ll-issues set-scores` section, and `docs/reference/ISSUE_TEMPLATE.md`, frontmatter documentation — new input/result and baseline semantics.

### Dependent Files (Callers/Importers)

- `commands/reconcile-issue.md`; `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — clear-before-rescore consumers; retained baseline is required, with no new ordering dependency.
- `scripts/little_loops/frontmatter.py`, `parse_frontmatter()` / `update_frontmatter()` — nested metadata reader/writer support.
- `scripts/little_loops/issue_parser.py`, `_section_body()` — latest Notes selection. Preserve this selection contract and existing numeric score parsing.
- `scripts/little_loops/cli/issues/show.py`, `_parse_card_fields()`, and `IssueInfo` serialization — explicit numeric score projections; structured-factor display/model expansion is outside scope.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_parser.py`, `count_open_questions_in_sections()` (`_OPEN_QUESTION_SECTIONS` includes `"Confidence Check Notes"`) — reads `_section_body(content, "Confidence Check Notes")`, which spans `###` subsections, and counts any bullet matching `_OPEN_QUESTION_SIGNAL_RE` (trailing `?`, "open question", "needs decision", "worth confirming", …). A `### Risk Factor Delta` bullet restating a factor description (including a removed factor's prior one) can be counted as an open question. Feeds `cli/issues/check_open_questions.py` (`OPEN_QUESTIONS_REMAIN`), `cli/issues/next_obligation.py` `_tier1_probe` (`HEDGES`) and, through them, `refine-to-ready-issue` `check_hedges` and `oracles/resolve-decision.yaml`. Unlike `set-flags`, it has no delta exclusion in the spec.
- `scripts/little_loops/cli/issues/advise_consult.py`, `_strip_named_sections()` / `trim_consult_context()` (`_TRIM_HEADINGS`) — strips `## Confidence Check Notes` only up to the next `#{1,3}` heading, so `### Risk Factor Delta` already falls outside the stripped span and its text would enter the consult context and replay-hash input (existing `### Concerns`/`### Gaps` subsections behave the same way; confirm whether delta text should be trimmed).
- `commands/reconcile-issue.md`, step 5b — edits `### Concerns` bullets in the last Notes occurrence and places `## Resolved Concerns` immediately after the Notes section; a `### Risk Factor Delta` subsection sits inside the Notes span and must remain untouched. `skills/spike/SKILL.md` Phase 2 reads `### Outcome Risk Factors` by name (distinct from the delta subsection; no change).
- `scripts/little_loops/cli/issues/clear_verify_verdict.py` — docstring "Mirrors `set-scores --clear`"; sibling clear helper using the same frontmatter/lock helpers, a reference pattern for the configured-`base_dir` lock change (not modified).
- `scripts/little_loops/loops/rn-remediate.yaml`, `verify_scores_persisted` — greps `^confidence_score:` / `^outcome_confidence:` at column 0; list entries under `risk_factors` start with `- ` or indentation, so there is no collision. `scripts/little_loops/loops/prepare-issue.yaml` and `refine-to-ready-issue.yaml` call `/ll:confidence-check` and check score-key presence only; they never see `set-scores` exit codes (only the skill does), so exit 2 reaches the skill alone.
- `scripts/little_loops/sync.py`, `_update_issue_frontmatter()` — GitHub-sync round trip via `yaml.safe_load`/`yaml.dump` preserves unknown keys, so `risk_factors` survives; slug IDs such as `null`/`123` rely on the dumper's quoting (cover with the list-of-maps round-trip test).
- `scripts/little_loops/cli/migrate.py`, `_set_fields()` and `cli/migrate_labels.py` — line-based editors matching `^key:` at column 0 only; indented list-of-maps entries are not matched (no change needed).

### Conventions in Force

- JSON file/`-` stdin input and validation before mutation already exist in `scripts/little_loops/cli/issues/create.py`, `cmd_create()` / `validate_metadata()`; factor-specific validation must not inherit creation-only reserved-key policy.
- Nested updates target the canonical header and replace the supplied key's whole value: `frontmatter.update_frontmatter()`; do not add a second fenced store or hand-render YAML.
- Shared locked atomic mutation exists in `scripts/little_loops/cli/issues/set_status.py`, `apply_status_transition()`, and `file_utils.py`; test the score transaction's use of those helpers rather than re-testing lock algorithms.
- Fence-aware heading selection uses `scripts/little_loops/text_utils.py`, `fence_spans()` / `in_fence()`; reuse that convention for filtering delta subsections without changing the shared section parser.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md`, `/ll:confidence-check` "Findings write-back" — states "If all scores are clean, no write occurs", which no longer holds once an all-removed delta writes Notes; add `risk_factors` / `### Risk Factor Delta`. "Flag write-back (ENH-2946)" says `set-flags` reads the issue's own Confidence Check Notes — note the delta exclusion. `/ll:reconcile-issue` Flow lists Confidence Check Notes among untouched sections (delta rides inside it).
- `docs/reference/CLI.md`, `ll-issues set-flags` (`--from-notes`, ~line 3035) — note the `### Risk Factor Delta` exclusion; `check-*` exit-code convention paragraph (~line 2298) defines 2 as "cannot evaluate" — `set-scores` exit 2 (factor-input rejection) is a separate meaning and should be called out beside the `set-scores` rows.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`, "Confidence Scoring" — says both scores persist as `confidence_score`/`outcome_confidence`; add the last-recorded factor baseline and delta Notes.
- `docs/reference/ISSUE_TEMPLATE.md`, `missing_artifacts` / `implementation_order_risk` / `spike_needed` rows — describe flags set from Outcome Risk Factors phrases; the `gate` row is the list-of-maps precedent for documenting `risk_factors`.
- `docs/reference/API.md`, `count_open_questions_in_sections` (~line 1209) — lists `## Confidence Check Notes` as scanned; update only if a delta exclusion is added there.
- `docs/guides/LOOPS_REFERENCE.md`, `oracles/verify-confidence-scores` row — describes clear-then-rescore (BUG-3571); optionally note the factor baseline survives the clear.
- `CHANGELOG.md` — new entries go in a concrete release section during release prep, not `[Unreleased]`.

### Tests

- `scripts/tests/test_set_scores_cli.py` — input/result, diff, alias/JSON/no-update compatibility, invalid-input versus stored-baseline/operational failure, and transaction behavior. Verify configured clear/update calls request the same tree lock.
- `scripts/tests/test_confidence_check_skill.py` — skill wiring, all modes, threshold-independent collection, clean-delta notes and fallback instructions.
- `scripts/tests/test_set_flags_cli.py` — removed signal phrases and historical co-deliverable filenames in delta notes neither activate nor suppress flags, through both note-input paths. Cover next active heading, nested headings, repeated delta subsections and fenced heading text; active/legacy findings and direct frontmatter triggers still work.
- `scripts/tests/test_frontmatter.py` — existing nested/canonical-block coverage; add round-trip preservation coverage only where the new record shape is not already exercised.
- `scripts/tests/test_preparation_policy_writers.py`, `TestRescorePrecondition` — factor baseline survives the real clear-before-rescore flow, including configured lock propagation.
- One manual skill smoke assessment and re-assessment: remove one of two independently named test risks while keeping totals fixed; confirm prior-ID reuse, one removed factor, delta Notes and valid writer JSON. Also assess an active aggregate cap with full dimension scores. Structural skill tests verify instructions; this smoke check supplies evidence of model behavior without a new evaluation framework.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug3150_issue_mutator_atomicity.py`, `TestNoBareWriteTextRemains.test_mutation_module_has_no_write_text_call` — parametrized over `set_status.py`, `link.py`, `session_log.py`; add `little_loops/cli/issues/set_scores.py` (its scalar path still does a bare `path.write_text(new_content)` at `cmd_set_scores`, so this fails until the locked atomic write lands). Add `TestLockIsTaken`/`TestAtomicWrites`/custom `tickets` `base_dir` cases for `set-scores` and `clear_scores` here (the spy-on-`little_loops.file_utils.acquire_lock` pattern only works with in-function lock imports; a module-level import needs `patch("little_loops.cli.issues.set_scores.acquire_lock")`).
- `scripts/tests/test_wiring_reference_docs.py` — `(file, substring, issue)` registry; add `("docs/reference/CLI.md", "--risk-factors-file", "ENH-3742")` and `("docs/reference/ISSUE_TEMPLATE.md", "risk_factors", "ENH-3742")` (shape of the `ENH-3465` `--pin-baseline` entries).
- `scripts/tests/test_confidence_check_skill.py`, `TestConfidenceCheckSkillWriteBack` — three tests slice only `content[phase_4_5_start : phase_4_5_start + 2000]` for `CHECK_MODE`, `HAS_FINDINGS`, `## Confidence Check Notes`; keep those tokens inside the first 2000 chars of Phase 4.5 when adding the delta trigger text. `TestConfidenceCheckPhase4CLI._phase_text` slices Phase 4 to the next `\n###` (no new `###` heading inside it; `ll-issues set-scores` must remain, `Use the Edit tool` must not appear). `TestVerdictJsonTrailer` requires `VERDICT_JSON:` between `## Output Format (single issue)` and `## Batch Output Format` in `rubric.md`; `TestConfidenceCheckRubricOutcomeConfidenceCap._cap_section_text` requires `hard cap`, `aggregate`, `SPIKE_SUPPRESSED` inside `### Outcome Confidence Cap (ENH-3350)`.
- `scripts/tests/test_set_scores_cli.py` — keep green: `TestIssuesCLISetScores::test_set_scores_no_flags_returns_0_with_warning`, `TestSetScoresClear::test_clear_removes_all_six_keys_and_is_idempotent` (second clear leaves bytes identical), `::test_clear_with_score_argument_errors` (exit 1), `TestClearScoresHelper` (single positional `clear_scores(issue_file)` → `base_dir` must stay keyword-only with a default), `test_set_scores_verify_via_show_json`. Extend with `TestSetScoresRiskFactors` beside `TestSetScoresClear` (reuse `_run`); there is no existing `ss --json` or exit-2 test to model on.
- `scripts/tests/test_ll_issues_create.py`, `TestCreateMetadataCli` (`test_metadata_file_json`, `test_metadata_file_invalid_json_fails_cleanly`), `TestCreateCli::test_create_body_file_stdin` (`patch("sys.stdin", io.StringIO(...))` with `-`), `TestValidateMetadata`, `TestCreateMetadata::test_nested_metadata_round_trips` — patterns for file/stdin JSON input, pure-validator tests for `parse_risk_factors`, and nested-YAML round-trip fidelity.
- `scripts/tests/test_frontmatter.py`, `TestUpdateFrontmatter::test_nested_dict_value_round_trips` — only nested-writer test; add the list-of-maps sibling (slug values `123`/`null`/`true`/`yes` return as strings; `remove_frontmatter_keys` on the unindented `- ` layout; `risk_factors` in a non-canonical block).
- `scripts/tests/test_text_utils.py`, `TestFenceSpans`/`TestInFence` and `test_ll_issues_create.py::TestFullBodyMerge::test_fenced_heading_quote_not_misrouted` — patterns for fence-aware heading exclusion in `test_set_flags_cli.py`.
- `scripts/tests/test_issue_parser_unresolved.py`, `test_ll_issues_check_open_questions.py`, `test_ll_issues_advise_consult.py` (only exercises Notes with no `###` subheadings), `test_ll_issues_next_obligation.py` — add a delta-subsection case if `count_open_questions_in_sections`/`trim_consult_context` get delta handling; otherwise a characterization case documenting that delta text is/isn't counted.
- `scripts/tests/test_docs_audience_gate.py` — scans `docs/guides`, `docs/reference`, `skills`, `commands`; new skill, rubric, reference and CLI.md text must not cite `scripts/tests/` or `scripts/little_loops/` paths.
- `scripts/tests/test_prep_cli.py::TestPrepFailurePaths::test_unresolvable_issue_precondition_raises` — `_run_preconditions(..., ["clear_scores"])` on an unknown issue must still raise `RuntimeError` matching "not found" after `base_dir` is threaded through.
- `scripts/tests/test_ready_issue_lint.py` (`RUBRIC_FILE`, Auto-provision / `LT_ROWS` order checks) — rubric.md additions must not reorder or remove those anchors.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **`SKILL.md` has one spare line.** `skills/confidence-check/SKILL.md` is 499 lines against the 500-line cap enforced by `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit`. The factor-collection, delta-notes and fallback instructions cannot land in `SKILL.md` beyond a net of one line; the overflow convention is the existing companions (`rubric.md`, 658 lines, already holds the notes template; `reference.md`, 39 lines). Phase 4/4.5/4.6 in `SKILL.md` should carry the pointer and the invariants, with detail in the companions.
- **Host mirrors are gated.** Editing anything under `skills/confidence-check/` trips `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` (gated hosts: gemini, kimi-code, qwen, codex, omp) and `test_skill_mirrors_carry_companions` (byte-compares `rubric.md`/`reference.md` in the `.gemini/`, `.kimi-code/`, `.qwen/`, `.omp/` mirrors). Regenerate with `ll-adapt --host <host> --apply` after the skill edits; these mirror directories are gitignored, so the failure shows locally and in CI only where the mirrors exist.
- **Additional tests that pin touched contracts** (must keep passing): `scripts/tests/test_reconcile_issue_command.py` (asserts the reconcile step still calls `ll-issues set-scores ... --clear`); `scripts/tests/test_builtin_loops.py` (oracle `verify-confidence-scores` starts at `clear_scores` and shells out to `set-scores`); `scripts/tests/test_prep_cli.py` and `scripts/tests/test_preparation_policy.py` (both drive the `clear_scores` precondition); `scripts/tests/test_frontmatter_scores.py` (score-key encoding); `scripts/tests/test_ready_issue_lint.py` (reads `rubric.md`).
- **Lock-assertion convention lives in a different test file.** `scripts/tests/test_set_scores_cli.py` has no `acquire_lock`/`issue_lock_path` assertions. The spy-on-`little_loops.file_utils.acquire_lock`, `os.replace` capture and custom-basename (`tickets`) patterns are in `scripts/tests/test_bug3150_issue_mutator_atomicity.py` (`TestLockIsTaken`, `TestAtomicWrites`, `test_custom_base_dir_is_honoured`). Those spies only intercept callers that import the lock helpers inside the function body, as `set_status.py` and `clear_scores()` do; a module-level import in the score writer binds the name early and must be patched at that module instead.
- **Same default-lock defect class outside this issue's scope.** `scripts/little_loops/session_log.py:438` (`append_session_log_entry`) also calls `issue_lock_path(issue_path)` with the default `.issues` name, so `append-log` locks a different file than configured writers on a custom-basename tree. Phase 4.5's `append-log` runs after the score write, not inside its transaction, so this does not break the score-lock agreement specified here; it is recorded so the "one tree lock" wording is not read as covering every issue mutator.
- **Documentation surfaces located.** `docs/reference/CLI.md` `#### ll-issues set-scores / ll-issues ss` (about line 3134) describes the command as idempotent scalar writes and its `--clear` row says "Remove all six score keys"; both statements remain true but need the factor/`--json` rows and a baseline-preservation note. `docs/reference/ISSUE_TEMPLATE.md` frontmatter table rows for the score keys sit at about lines 907-912. `docs/reference/API.md` has no `clear_scores`/`set_scores` entry, so the new `base_dir` keyword needs no API.md change unless a new section is added. Documented `ll-issues` flags are checked against the real parser by the `stale_cli_flag` format-check gap (`scripts/little_loops/issues/cli_claims.py`), so a flag documented before it is registered will be flagged; `scripts/tests/test_wiring_cli_registry.py` holds substring-presence checks on CLI.md for other subcommands and is the place a registry entry would go if one is wanted.
- **Other readers of the score keys are untouched.** `show.py`, `issue_parser.py`, `check_readiness.py`, `refine_status.py`, `next_issue.py`, `next_issues.py`, `sprint/_helpers.py` and `run_record.py` read the numeric keys; none enumerates frontmatter generically, so a new `risk_factors` list key does not reach them.

## Impact

Makes risk composition changes visible when aggregate scores stay fixed, including scope splits such as FEAT-3504. The main limitation is model-assigned identity stability: re-slugging the same risk can still create a noisy add/remove pair. Prior-ID reuse instructions and metadata-aware retention reduce that noise without inventing a similarity heuristic.

## Acceptance Criteria

1. A successful factor-bearing write persists the complete last-assessed list alongside any supplied scores in canonical frontmatter. Explicit `[]`, omitted input and an absent legacy baseline have distinct behavior; unrelated frontmatter/body survive. After an unrelated status/frontmatter update, `parse_frontmatter()` still returns the factor records and the issue parser still reads the existing numeric scores correctly.
2. JSON comparison follows Program Design, is deterministic under input reordering, and distinguishes fully unchanged retained factors from metadata changes under the same ID. First assessments report an absent baseline with `null` comparison lists; a known-empty baseline produces ordinary array comparisons.
3. Re-scoring with identical totals and changed membership reports a non-empty delta in skill output and a new Notes section. Removing the final factor works when `HAS_FINDINGS` is otherwise false. Threshold crossing alone does not add/remove a factor.
4. Numeric score clearing, including the automated clear-before-rescore precondition, preserves the baseline and shares the configured issue-tree lock with score updates. Scalar-only partial updates, factor-only writes, no-update calls, aliases and JSON/clear combinations follow the specified contract. Factors never supply score freshness or gating evidence.
5. Rejected factor-bearing CLI calls (malformed JSON, invalid record shape/fields or duplicate IDs) leave issue bytes unchanged and write no scores. Input failures and invalid-baseline/operational failures have the specified distinct diagnostics and exit codes. The read/diff/write uses the shared lock and atomic writer; write failure emits no successful result. Only input failure allows the bounded repair and explicitly reported scores-only fallback, without stopping other batch issues.
6. Historical signal phrases and co-deliverable filenames inside `Risk Factor Delta` cannot activate or suppress flags through either note-input path. Filtering respects real/fenced heading boundaries and preserves later active findings and direct frontmatter triggers; existing true flags are not cleared by factor removals.
7. Single/auto/batch/sprint modes use the same factor contract. `--check` retains its existing output/exit behavior and writes nothing. Notes preserve Session Log and Resolved Concerns structure, including the latest-notes behavior used by flags.
8. Collection covers concrete risks from all existing deductions, modifiers, caps and hard gates, including an active aggregate cap with full dimension scores. Distinct removable risks in the same bucket have distinct IDs; the same underlying concern is not duplicated for multiple effects. The five readiness criteria, four outcome criteria, point allocations, caps, configured thresholds and flag preconditions are unchanged. Existing issues need no migration. Documentation, the relevant tests and the bounded manual smoke check above cover these outcomes.

## Scope Boundaries

- Scoring countable inputs (breadth, callers, coverage) by formula instead of bucket.
- Per-site depth classification with a weighted aggregate.
- Fuzzy matching, full factor history/previous-set storage, a baseline-reset option, new thresholds/gates, automatic flag clearing and deriving flags from structured factors.
- Factor display through `ll-issues show`/list or expansion of `IssueInfo`; the skill can read canonical frontmatter and the writer's JSON result.
- Changing existing score-range validation or fixing unrelated default-threshold documentation inconsistencies.
- Whole-assessment/Notes transactions, versioning or stale-assessment detection, and repairs to unrelated legacy flag-scanning behavior when no new Notes section was written.

The two scoring changes shift existing scores and need a one-time re-check of issues near the configured outcome gate. They follow this change as separate work.

## Review Notes

Pre-implementation review on 2026-10-05 confirmed the additive approach and settled storage, identity, baseline lifecycle, validation/failure handling, notes triggers and flag isolation. `/ll:advise` with `claude-opus-5-5` recommended proceeding at P3 after tightening these contracts (confidence 0.78). Its principal dissent favored omitting notes for first/retained-only runs; the bounded notes policy above retains durable membership changes for automated runs. Its heading-only isolation suggestion was rejected against the verified whole-Notes flag scan; explicit subsection exclusion is required.

Follow-up review on 2026-10-05 reproduced historical delta filenames suppressing an active missing-artifact flag and the default/configured clear-lock mismatch for `tickets`. The specification now filters both matching and suppression, preserves fence-aware boundaries, propagates the configured clear lock, defines factor granularity and cap coverage, separates repairable input failures from invalid-baseline/operational failures, and completes JSON/no-update/clear behavior. The transaction guarantee is limited to score persistence; whole-skill concurrency remains outside scope. A new `/ll:advise --model opus` critique was attempted but refused because the current session had already spent its three-consult budget; no new advisor verdict was obtained.

Review validation: 287 existing tests passed across `test_set_scores_cli.py`, `test_set_flags_cli.py`, `test_confidence_check_skill.py`, `test_frontmatter.py` and `test_preparation_policy_writers.py`. Temporary-project reproductions confirmed both integration gaps above. These checks validate the current code observations and baseline behavior; the new factor contract and regression cases remain implementation work.

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Tests bullet for `test_docs_audience_gate.py`: slash-joined shorthand `skill/rubric/reference/CLI.md` resolved as a nonexistent path (format-check `stale_file_ref`); rewritten in place as "skill, rubric, reference and CLI.md text". `ll-issues format-check` now reports no `stale_file_ref`.

## Session Log

- `/ll:verify-issues` - 2026-10-06T00:49:58 - `cfda72d4-e007-4235-a82e-7c540e94815e.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:48:25 - `02cf9236-02d6-4759-906a-966c8443cf38.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:46:42 - `8d1e98b3-e66e-4c2c-ba7a-6e5eb3103477.jsonl`
- `/ll:wire-issue` - 2026-10-06T00:44:57 - `3599d73d-15f2-44a9-8691-333e785cd0ec.jsonl`
- `/ll:refine-issue` - 2026-10-06T00:36:41 - `40746b8e-69e5-40b8-8019-c544418b7667.jsonl`
- `/ll:refine-issue` - 2026-10-05T20:38:16 - `e4d031f4-efb7-4acd-b532-6b7d02eab780.jsonl`

## Status

Open — pre-implementation review complete; implementation has not started.
