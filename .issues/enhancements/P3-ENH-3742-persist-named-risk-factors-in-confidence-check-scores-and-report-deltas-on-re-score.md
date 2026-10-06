---
id: ENH-3742
title: Persist named risk factors in confidence-check scores and report deltas on
  re-score
type: ENH
priority: P3
status: open
discovered_date: '2026-10-05'
labels:
- verification
- confidence-check
reconcile_attempted: true
relates_to:
- BUG-3757
confidence_score: 98
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3742: Persist named risk factors in confidence-check scores and report deltas on re-score

## Summary

`/ll:confidence-check`'s coarse scoring buckets can miss a real change in risk composition. FEAT-3504 was split to separate untested stateful page work from the transport change. Its re-score came back **85/64, identical to before**: the bucket totals did not move, though the Concerns prose did change (the page bullets were gone; the transport and submit-path bullets were unchanged).

Persist named risk factors alongside the scores. On re-score, compare their identities and report added, removed and retained factors, so "did my change matter?" gets an answer even when the totals are static. Retained factors distinguish unchanged metadata from rewording or reclassification. A removed factor means it is no longer reported for this issue, not that its risk has been independently verified as resolved.

This is additive to scoring: no rubric change, no threshold change, no migration and no forced re-scoring of existing issues. It is the first, separable step of a broader scoring-granularity change (continuous scoring for countable inputs, per-site depth), which will be filed separately.

## Current Behavior

- Confidence-check writes scalar scores and conditionally appends Notes when `HAS_FINDINGS` is true. A clean assessment or unchanged totals can hide changed risk composition.
- `cmd_set_scores` in `scripts/little_loops/cli/issues/set_scores.py` writes supplied scalar fields without a lock/atomic writer. Its separate `clear_scores(path)` helper is locked and atomic but derives the lock with the default `.issues` basename.
- The preparation-policy clear-before-rescore path must retain a future factor baseline. For a custom `tickets` base, current clear/update mutators can take different locks.
- Frontmatter already supports nested lists/maps and legacy first-mapping/no-frontmatter updates. Factors can be stored there without an `IssueInfo` expansion or migration.
- `apply_flags_from_notes` scans the entire latest Notes body, and its co-deliverable suppressor scans the original notes for filenames. Even legal IDs can match flag phrases: `absent`, `test-first`, `unprecedented`, `co-deliverable-tests`, and `submit-tests-absent`. Open-question counting also selects the latest Notes; consult trimming stops at H3 subheadings.

## Expected Behavior

Every non-check assessment supplies the complete current factor list, including `[]`, independently of display thresholds. Successful writes persist that list beside scores and return a deterministic comparison. Re-scoring can then show changed membership even when totals stay fixed.

A baseline means the last assessment that recorded factors. It may outlive cleared scores or a later scores-only update; it never supplies freshness/gating evidence. A removed factor means no longer reported for this issue, not independently verified resolution. Legacy prose is not converted into a guessed baseline.

## Motivating Example

The FEAT-3504 re-score, raw bucket sum 64:

| Criterion | Score | Why it didn't move |
| --- | --- | --- |
| Complexity | 10 | About 8 code files plus 5 docs, still in the 6–15 breadth bucket; whole-issue depth "Moderate" |
| Test coverage | 18 | "Most modules": new `policy_builder_routes.py` and `do_POST` lack tests |
| Ambiguity | 18 | The checker still flags a bare-token redirect as a minor open question |
| Change surface | 18 | 3–5 callers, unchanged by the split |

The split removed exactly the risk the rubric cannot see. The qualitative layer tracked the change; the numeric layer could not. A factor delta makes that visible without touching the numbers.

## Proposed Solution

Use exact stable IDs and one last-recorded frontmatter list. The writer owns validation, baseline classification, comparison and atomic persistence; the skill assesses factors, reuses IDs and renders the writer's result. Keep scoring arithmetic, gates, thresholds and set-only flag behavior intact.

**Decided Notes format:** `### Risk Factor Delta` contains backticked IDs, fixed labels/baseline notices and changed-field names only. Descriptions, criterion values, filenames, quotes and questions stay in the complete frontmatter records, CLI JSON and ordinary assessment output. The narrow subsection exclusion in `set-flags` is required because legal IDs can contain flag phrases as substrings. Do not restrict the valid ID vocabulary, add a general backtick mask or broaden unrelated open-question/consult trimming in this issue.

## Program Design

### Types

One `risk_factors` list in the frontmatter update target, each mapping with exactly four required string fields:

```yaml
risk_factors:
- id: missing-submit-tests
  domain: outcome
  criterion: test_coverage
  description: Submit route and POST handler have no regression tests.
```

- `id`: unique per issue, exact matching key, lowercase slug matching `^[a-z0-9][a-z0-9-]{0,47}$` by full match. Dots, slashes, underscores, whitespace and LF/CR are invalid; descriptions/locations/scores do not determine identity.
- `domain`: `readiness` or `outcome`; hard gates belong to readiness.
- `criterion`: string label matching `^[a-z][a-z0-9_-]{0,47}$` by full match, e.g. `test_coverage`/`outcome_cap`; no new CLI-enforced rubric enum.
- `description`: non-blank single-line string, at most 200 characters; reject LF/CR and invalid lengths rather than normalize silently. Preserve Unicode.
- Require concrete independently removable concerns. Two missing-test risks in one bucket have separate IDs; repeated mentions or multiple scoring effects of the same concern share one ID and a primary domain/criterion.
- Reuse an ID for the same underlying risk, omit unsupported factors and mint IDs for distinct concerns. Honor Resolved Concerns while requiring current evidence for a continuing deduction/override. Do not mechanically copy a previous set.
- Changed domain/criterion/description retains the ID; a removed then reintroduced ID is added relative to the immediately preceding recorded list. Sort storage and all comparison entries by ID. No fuzzy matching or second permanent history field.

### Decision Rules

Add planned `--risk-factors-file PATH` (`-` reads stdin) and `--json`/`-j` to `set-scores`/`ss`. Successful calls remain quiet without JSON. Existing scalar-only partial updates/no-flags warning/clear behavior remain compatible.

| Input/state | Contract |
|---|---|
| Factor option omitted | Preserve factors; JSON reports `recorded: false` and key-presence baseline `absent`/`present`, without claiming validity or comparison. |
| Valid complete array, including `[]` | Replace list; explicit empty is a known-empty baseline. Factor-only calls are allowed. |
| Prior key absent | `baseline: absent`; `added`, `removed`, `retained` are `null`, not fabricated additions. |
| Prior valid list, including `[]` | `baseline: present`; comparison fields are arrays, including empty arrays. |
| Stored key present but malformed in a parseable target mapping | Replace non-fatally; `baseline: malformed`, null comparisons, stderr `Warning: stored risk_factors baseline malformed; replaced` after successful persistence. Classify from the raw target YAML, not the lenient reader's fallback. |
| `--clear`/`clear_scores()` | Remove only the six existing scalar keys; preserve valid/invalid factors. Exclusive with score/factor updates; JSON allowed. |
| `--clear` with score/factor options | Exit 1 with an ordinary exclusivity error, without the factor-input prefix; do not read the factor payload or write the issue. |
| Factor file/read/JSON/record-input failure | Exit 1, empty stdout, unchanged issue bytes, stderr begins `Error: invalid risk factors:`. No scalar scores are written. |
| Unresolvable issue, invalid target YAML/mapping, lock/read/write failure | Exit 1, no success JSON or replacement claim, actionable stderr without the factor-input prefix, unchanged issue bytes. |

Choose the same target as `update_frontmatter`: first `id`-bearing block, else first block. A valid mapping without `id` remains supported. With no frontmatter, the baseline is absent and successful updates retain the existing prepend behavior; clear is a no-op. An unterminated opening frontmatter fence is an operational error, not an absent baseline. Parse the selected raw YAML with `yaml.safe_load`, matching the update writer, and reject parse failures/non-mappings as operational errors. Do not classify a baseline through `BaseLoader` or its permissive fallback. Hand-edited non-string IDs such as unquoted `123`, `yes`, or `null` make a stored list malformed; writer-created quoted strings remain valid. Do not merge factors from a different frontmatter block or normalize legacy block layout here.

Resolve the issue before reading input; validate caller factors before locking. One configured issue-tree lock covers baseline read → comparison → frontmatter update → atomic write. All scalar-only updates and configured clear calls use the same lock. `atomic_write(..., shared_mode=True)` preserves existing regular-file mode. Direct `clear_scores(path)` stays compatible via an optional keyword-only base-dir argument. Do not nest the non-reentrant clear helper inside an already-held lock.

Handled command failures use exit 1; argparse usage errors retain their existing exit 2. The skill branches on the fixed factor-input stderr prefix, not exit 2. No score-range validation is added. Scores-only/clear need not validate the retained factor list; unsafe target YAML still fails without a partial write. Error/no-write paths preserve exact issue bytes, including CRLF. Successful writes follow the existing writers' newline behavior; preserving newline style is not a new requirement.

A no-update JSON call returns the `recorded: false` object, warns on stderr, exits 0 and writes nothing; read presence under the same lock. Factor-bearing success is emitted only after persistence succeeds. An identical assessment has unchanged retained records and no membership delta.

The JSON object has resolved full `issue_id` and `risk_factors`. Obtain identity from the resolved file using the existing `IssueParser(config).parse_file(path).issue_id` behavior, rather than echoing numeric/priority/stale-type input or requiring a frontmatter `id`. With factors recorded: `recorded: true`, `baseline: absent|present|malformed`, sorted assessed `factors`, and comparison fields above. Added entries are assessed records; removed entries are prior records. Retained entries contain the four assessed fields plus `changed_fields` in fixed `domain`, `criterion`, `description` order. Without factor input, emit only `recorded: false` and presence-based `baseline` under `risk_factors`.

The lock serializes writer transactions, not the model assessment or later Notes edits. Concurrent writes compare against the latest set at commit time. Whole-skill serialization/stale-assessment rejection/transactional Notes are outside scope.

### Signatures

- Existing `cmd_set_scores(config: BRConfig, args: argparse.Namespace) -> int` remains the writer entry point.
- Proposed extension `clear_scores(path: Path, *, base_dir: str = ".issues") -> bool`; CLI and preparation policy pass the configured base.
- Proposed private dataclasses/helpers in the writer module: `RiskFactor`, `RetainedRiskFactor`, `RiskFactorDelta`, `parse_risk_factors(raw: str) -> list[RiskFactor]`, `diff_risk_factors(previous: list[RiskFactor], assessed: list[RiskFactor]) -> RiskFactorDelta`. Pure parsing/diff helpers have no I/O; malformed/absent baselines must remain distinguishable at the caller.

### Skill, Notes and Flags

1. Collect factors from all existing readiness/outcome deductions, learning-test modifiers, criterion/aggregate caps, hard-gate overrides and applied correction-history adjustments, independently of display threshold. An active unproven-mechanism cap contributes a factor even with full dimension scores or a raw sum below the cap. No unsupported factor for a full-score criterion with no applicable cap/override.
2. Read prior IDs during gathering, assess current evidence, and in non-check mode pass the complete factors with all six scores. Use stdin or an issue/run-unique payload file. Render the writer's JSON comparison without independently recomputing it.
3. On a prefixed input rejection, repair/retry once. If still rejected, make a separate valid scores-only call, retain baseline and explicitly report `risk factors not recorded; delta unavailable`. Fallback succeeds only if that call succeeds. Other failures get no repair/fallback; report the persistence failure and continue other batch issues. Never claim a delta or write delta Notes after a failed factor write.
4. `--check` keeps its existing output/exit behavior and performs no score/factor/Notes/staging/log/flag writes; it never invokes the mutating writer or claims a persisted comparison.
5. Append one fresh Notes section when existing `HAS_FINDINGS` is true or a recorded present-baseline comparison has added/removed IDs. All-removed with unchanged totals still writes Notes. Clean first/malformed-baseline and retained-only runs report in ordinary output without empty Notes. Finding-bearing Notes include a recorded comparison even when membership is unchanged; missing/malformed baseline is labeled explicitly. Accept the existing latest-section consequence: a fresh delta-only Notes section supersedes older Notes for open-question counting. It adds no active question and does not mark any concern resolved; questions in other scanned sections still count. Clean runs that append nothing retain the previous selection.
6. Put `Risk Factor Delta` last within the new Notes section, after any ordinary findings, and pin its template in `rubric.md`, not the line-limited skill. Use flat one-line bullets with membership labels `Added`, `No longer reported`, `Retained`, and `Changed fields`. Sort comma-separated IDs and backtick each one; use literal `none` for an empty comparison category. Emit one `Changed fields` bullet per changed retained ID with only `domain`, `criterion`, `description` in that order, or `none` if nothing changed. For null comparisons, emit only `- Baseline: none recorded` or `- Baseline: malformed, replaced`; do not fabricate empty membership arrays. Keep these baseline notices inside the excluded subsection rather than echoing the raw JSON state into ordinary findings. Never restate descriptions or criterion values in this subsection. Preserve Session Log/Resolved Concerns; removals do not create Resolved Concerns entries.
7. Before both phrase matching and co-deliverable suppression, exclude every exact real H3 `Risk Factor Delta` subsection from default latest Notes and supplied `--from-notes`. Both consumers get the same filtered text. End at the next real H1/H2/H3 or EOF; H4 stays excluded. Closed fenced headings neither begin nor end exclusion. An uncertain unterminated-fence span is retained rather than swallowing later active findings. Preserve later active prose, legacy findings, numerical/direct-frontmatter prerequisites, and set-only semantics. Do not derive flags from factors or auto-clear flags on removal.

### Call Path

`main_issues` → `cmd_set_scores` → factor validation → configured locked baseline/diff → `update_frontmatter` → `atomic_write` → JSON result → skill output/optional IDs-only Notes → `apply_flags_from_notes` with delta subsection excluded.

## Implementation Steps

1. First land the independently testable lock fix: scalar writer to locked atomic write; clear helper configured base/mode; preparation-policy propagation. Add score writers to the mutator atomicity gate. Keep the helper backwards compatible.
2. Add factor CLI/dataclasses/validation/diff/JSON behavior and transaction tests, retaining legacy frontmatter targeting and resolved identity. No partial scalar write or false replacement warning on rejected factor input or failed persistence.
3. Add the narrow fence-aware flag exclusion and pin the fixed Notes grammar in the rubric companion. Test legal phrase-bearing IDs and preserve matching outside the subsection. Characterize the delta-only latest-Notes effect and generated text against open-question and consult consumers; no changes to those consumers are required. Consult hashes may include ID membership changes under the existing H3 trimming behavior; this is accepted, and no claim of Notes-hash invariance is made.
4. Before growing the 499/500-line skill, extract suitable existing detail to `rubric.md`/`reference.md` while keeping pinned Phase 4/4.5/4.6 and append-log anchors. Add factor collection/writer/fallback/notes instructions in all modes. Do not add another `python3 -c` prose marker or spawn site. Regenerate tracked host mirrors through `ll-adapt`.
5. Update CLI/issue-metadata documentation and run relevant tests plus `python -m pytest scripts/tests/`. Finish with one bounded manual assessment/re-assessment proving stable IDs and removed-factor display at fixed totals; also assess an active cap with full dimension scores.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/set_scores.py`, `scripts/little_loops/cli/issues/__init__.py` — writer and parser/alias registration.
- `scripts/little_loops/cli/issues/set_flags.py` — narrow Notes exclusion applied to matching and suppression.
- `scripts/little_loops/preparation_policy.py` — configured base passed into clear precondition.
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md`, `skills/confidence-check/reference.md` — shared factor and IDs-only Notes contract.
- `docs/reference/CLI.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/reference/COMMANDS.md` — CLI/results, baseline lifecycle and metadata description.
- Tracked confidence-check host mirrors — regenerate, no hand edits.

### Dependent Files

- `scripts/little_loops/frontmatter.py` — existing canonical nested-list/map support; preserve unrelated fields/body and string-like slugs.
- `scripts/little_loops/file_utils.py` — existing tree lock and mode-preserving atomic writer.
- `scripts/little_loops/issue_parser.py` and `scripts/little_loops/cli/issues/advise_consult.py` — reuse existing resolved identity and characterize IDs-only notes, including the delta-only latest-Notes effect on open-question consumers; no broader parser/trim change.
- `commands/reconcile-issue.md` and `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — clear preserves baseline; no rewrite required.
- BUG-3757 shares the skill/rubric/flag writer. Prefer its small threshold correction first, then rebase this work; neither is a semantic blocker and no dependency cycle is added.

### Tests and Documentation

- `scripts/tests/test_set_scores_cli.py`: file/stdin, alias, factor-only/scalar-only/no-update/clear, all JSON shapes, input reordering, changed metadata, absent/empty/malformed raw baselines, exact prefix/warning, invalid target YAML/mappings or unterminated headers, operational failure and unchanged bytes. Cover first mappings without `id`, no frontmatter, canonical target behind a score block, and the same full JSON identity for numeric/priority/stale-type inputs. Mixed clear/factor arguments must fail without reading stdin or using the repair prefix; failed writes must not claim a malformed baseline was replaced. Validation rejects duplicate IDs, extra/missing/non-string fields, bad slugs/domains/criteria and multiline/long/blank descriptions. Include Unicode, file modes and CRLF error/no-write byte checks; success uses existing newline behavior.
- `scripts/tests/test_frontmatter.py`: list-of-maps round trips (string IDs such as `123`, `null`, `true`, `yes`), unrelated status updates, noncanonical blocks and numeric-score parsing. Test quoted IDs remain strings through later updates, while an unquoted non-string ID in a hand-edited stored list is classified malformed. Clear must preserve unindented factor lists and invalid baselines.
- `scripts/tests/test_bug3150_issue_mutator_atomicity.py` and `scripts/tests/test_preparation_policy_writers.py`: scalar/clear shared lock, configured `tickets` base, actual clear-before-rescore baseline preservation, no nested lock, atomic/read/write/lock failure handling.
- `scripts/tests/test_set_flags_cli.py`: both note-input paths, legal IDs `absent`, `test-first`, `co-deliverable`, `unprecedented` and compound `submit-tests-absent` inside the delta must not fire rules; the same phrases outside must still fire with existing prerequisites satisfied. Cover historical descriptions/co-deliverable filenames against template drift, baseline notices, repeated/fenced/unterminated subsections, H4/next active heading, default latest Notes, direct frontmatter and set-only behavior.
- `scripts/tests/test_issue_parser_unresolved.py`, `scripts/tests/test_ll_issues_advise_consult.py`: fixed delta grammar adds no open-question signal or description/filename to consult context. An older question-bearing Notes section followed by a clean delta-only section yields zero Notes questions; a question in another scanned section remains counted. Pin the accepted membership/hash behavior without changing trim semantics. This does not claim arbitrary description-bearing delta text is safe for every consumer.
- `scripts/tests/test_confidence_check_skill.py`: threshold-independent collection, all modes, bounded repair versus operational failure, no-write check, clean membership-delta notes, companion template wiring, final-subsection placement, fixed labels/baseline notices and field vocabulary. Assert no filename tokens or question signals; legal IDs need not be flag-phrase-free, so flag safety is verified behaviorally in the CLI tests.
- Existing skill/companion/host freshness, docs-audience, prose, reference-wiring, ready-rubric and session-log gates. Keep Phase 4.5's existing check/findings/Notes tokens within its tested first 2000 chars and Phase 4/4.6 anchors intact. Mark proposed APIs/flags as planned until implemented rather than weakening citation gates.

## Acceptance Criteria

1. Factor-bearing success persists the complete sorted list with supplied scores; absent, empty and omitted factor states are distinct. Legacy no-frontmatter/first-mapping writes and resolved full identity remain supported. Unrelated metadata/body/mode survive, including later ordinary frontmatter updates; successful newline behavior follows existing writers.
2. JSON is deterministic and follows the baseline/comparison contract; retained metadata changes differ from unchanged retained IDs. Output is emitted only after persistence succeeds.
3. Fixed totals with membership changes render a real delta and fresh IDs-only Notes, including the final removal when `HAS_FINDINGS` is false. Threshold crossing alone never changes factor identity.
4. Clear and scalar updates share the configured issue lock, preserve factors, remain compatible, and never make factors freshness/gate evidence.
5. Invalid factor input writes nothing, exits 1 with the exact prefix; malformed stored baseline is replaced visibly/non-fatally only after successful persistence. Operational/target-YAML failure gets no input-repair fallback, replacement claim or success JSON. Mixed clear/update arguments use an ordinary exit-1 error. Argparse usage errors retain exit 2; all error/no-write paths preserve exact bytes.
6. Delta history, including legal IDs containing flag phrases, cannot activate/suppress flags through either note path; boundary controls preserve active findings and direct triggers. Generated text has no open-question/filename effects; its flag-phrase effects are neutralized by subsection exclusion. Existing true flags are not cleared.
7. Single/auto/batch/sprint modes share the contract; check mode writes nothing. Existing Notes/Session Log/Resolved Concerns structure and latest-section selection rule remain intact. A new delta-only Notes section becomes the selected current assessment and drops older Notes questions from the count, while questions in other scanned sections remain; no concern is automatically marked resolved.
8. Existing scoring dimensions/allocations/caps/gates/thresholds stay unchanged. Collection covers active caps/hard gates with concrete independent risks. Relevant local tests and the bounded manual assessment/re-assessment pass; legacy issues need no migration.

## Impact

Additive qualitative comparison makes composition changes visible without changing score arithmetic. Model-assigned ID stability still needs a bounded smoke check; exact ID reuse instructions reduce noise without similarity heuristics.

## Scope Boundaries

No continuous/weighted scoring, fuzzy matching, full factor history/reset, factor-driven flags/automatic clearing, new gates/thresholds, `IssueInfo`/show expansion, broader question/context parsers, whole-assessment transaction or stale-assessment detector. The separate scoring-granularity proposals remain separate work.

## Review Notes

Reviewed on 2026-10-06 on `main` against the writer, raw frontmatter targeting, configured locks and Notes consumers. Read-only probes showed legal phrase-bearing IDs require subsection exclusion and a delta-only latest Notes section changes the open-question count from one to zero. Corrected the impossible lexical flag-safety requirement, pinned the companion template and baseline notices, preserved legacy writer shapes/resolved identity, and clarified error-prefix, replacement-warning and CRLF contracts. The latest-Notes consequence is accepted and explicitly characterized, without broadening parsers or interpreting removal as resolution.

An Opus `/ll:advise` consult supported these corrections (confidence 0.80). Its dissent was that pinning the exact template might be overly prescriptive; retained because leaking raw baseline labels into ordinary findings can create flags. Remaining implementation risks are model adherence/ID stability and the documented latest-Notes effect on automation. The focused baseline passed all 486 tests; format/design checks passed, no required decision rules conflicted, and no proof requirement or hard blocker is declared. Cached scores/verdict remain absent; run a fresh confidence assessment before automated implementation. No implementation edits were made.

## Status

**Open** | Reviewed: 2026-10-06 | Priority: P3

## Session Log

- `/ll:confidence-check` - 2026-10-06T19:12:05 - `29fac8c6-a710-46f3-a018-797c39cd9a98.jsonl`
- `/ll:ready-issue` - 2026-10-06T18:21:33 - `225d913b-150f-4f37-9e25-fcb3cb3d0b0e.jsonl`
- `/ll:confidence-check` - 2026-10-06T10:30:37 - `b5d4e644-cd2f-4e8d-a10e-c42db195622e.jsonl`
- `/ll:verify-issues` - 2026-10-06T10:28:24 - `dc732f3d-151b-4f4f-aac7-173ab3aca287.jsonl`
- `/ll:reconcile-issue` - 2026-10-06T10:26:19 - `eb8411d3-8f35-40aa-bced-e5eedef94d5f.jsonl`
- `/ll:verify-issues` - 2026-10-06T10:25:05 - `b5347bf7-6511-4c59-a3da-2555e9e4b542.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T10:22:52 - `b801aa43-cc62-4a40-a4d3-a54e0f8977d3.jsonl`
- `/ll:verify-issues` - 2026-10-06T10:19:56 - `1aca29d8-7386-4b5c-8507-9f548472a7f5.jsonl`
- `/ll:wire-issue` - 2026-10-06T10:18:13 - `3418fef5-fd05-4554-a83e-2f9e675d8b1c.jsonl`
- `/ll:refine-issue` - 2026-10-06T10:09:06 - `3aab45c8-8cbb-4076-b6d1-d7e3f1e910ac.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:59:14 - `1818b290-082b-4212-989c-998c67f30af5.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:57:28 - `cf7a65e7-4f46-4a35-9bec-f661a873d14a.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-06T01:54:58 - `2fc077e6-f247-45dc-97b8-6729a8243496.jsonl`
- `/ll:confidence-check` - 2026-10-06T01:54:26 - `9a2e0567-0b6b-414f-842d-143d055be361.jsonl`
- `/ll:verify-issues` - 2026-10-06T01:45:43 - `d9653535-6a8c-40af-9568-56ab082e7acd.jsonl`
- `/ll:wire-issue` - 2026-10-06T01:43:50 - `44fa6979-0950-4bce-9ee2-1ff1e8ab5b7c.jsonl`
- `/ll:refine-issue` - 2026-10-06T01:26:27 - `983da9fa-ef13-48f2-8c32-e186cb43049a.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:49:58 - `cfda72d4-e007-4235-a82e-7c540e94815e.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:48:25 - `02cf9236-02d6-4759-906a-966c8443cf38.jsonl`
- `/ll:verify-issues` - 2026-10-06T00:46:42 - `8d1e98b3-e66e-4c2c-ba7a-6e5eb3103477.jsonl`
- `/ll:wire-issue` - 2026-10-06T00:44:57 - `3599d73d-15f2-44a9-8691-333e785cd0ec.jsonl`
- `/ll:refine-issue` - 2026-10-06T00:36:41 - `40746b8e-69e5-40b8-8019-c544418b7667.jsonl`
- `/ll:refine-issue` - 2026-10-05T20:38:16 - `e4d031f4-efb7-4acd-b532-6b7d02eab780.jsonl`
