---
id: FEAT-3503
type: FEAT
title: Policy builder scenario boundary suggestions and local issue-file import
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T22:31:55Z'
parent: EPIC-3493
labels:
- policy-builder
blocked_by:
- FEAT-3488
relates_to:
- FEAT-3498
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FEAT-3503: Policy builder scenario boundary suggestions and local issue-file import

## Summary

Add deterministic boundary-case suggestions and offline local issue-file import to the policy builder's scenario suites. Extracted from FEAT-3488 on 2026-09-17 (its second natural split after FEAT-3501) so the core suite work — wrapper persistence, shared trace, verdicts, Run all, coverage — can land first. Everything here consumes FEAT-3488's `Scenario`/`ScenarioInput` contracts, `normalizeScenarioInput`, `parseFrontmatterBlock`'s supported-subset validation, and the committed-edit path; nothing here changes routing semantics.

## Current Behavior

After FEAT-3488, scenarios are authored by hand only: there is no generator for missing-field or threshold-boundary cases, and the only way to get a lifecycle case from a real issue file is to paste its frontmatter into the scenario input. `parseFrontmatterBlock` (post-FEAT-3488) rejects the unsupported YAML subset, but nothing extracts a fenced frontmatter block from a full Markdown file or guards an asynchronous `FileReader` completion against the project changing underneath it.

## Expected Behavior

Users click "Suggest cases" to add deterministic, deduplicated, unasserted boundary cases for the active draft's mode, and import a local issue `.md` file as one unasserted lifecycle case without the page reading anything but the opening frontmatter block. Both actions are single committed edits: undo removes exactly what they added, and any failure leaves the suite unchanged.

## Motivation

Hand-authored suites miss exactly the cases that matter: the value one below a threshold, the field that is absent, the fallback nobody wrote an example for. Suggestions make those boundaries one click away without inventing expectations, and file import lets a maintainer test a policy against the real issues in `.issues/` instead of retyped frontmatter. Splitting these from FEAT-3488 keeps that issue to the persistence/trace/verdict core (outcome confidence 58/100 with 22 ACs before the split) and gives the asynchronous-import invariants their own verification surface.

## Proposed Solution

- `suggestScenarios(model) -> SuggestedScenario[]` in `policy_builder_core.mjs`, pure and deterministic. Generation is **per authored rule, not per dimension** (review 2026-09-18: per-dimension missing-field/threshold cases can never satisfy a string-equality rule like the seeded lifecycle example's `status == done`, nor a compound rule like `severity == critical AND review_status == approved`, so the coverage AC would be unreachable). For each authored rule, in rule order:
  1. One **satisfying case**, selected by the domain-specific candidate algorithm below. Group predicates by their **source field**, not just dimension name, and require the final normalized/encoded input to satisfy every predicate of the originating rule using the existing predicate evaluator. An empty constraint intersection, unsupported domain, nonfinite ordered-comparator literal, or failed serialization round-trip skips the rule by a named, unit-tested rule. A skipped rule contributes no variants.
  2. For each numeric predicate, in predicate order, emit **boundary variants** of that witness at `t-1`, `t`, `t+1`, in that order, retaining the other source fields. These are one-unit boundary probes, not claims about nearest floating-point neighbours; witness selection must not depend on them. For discrete priority/list domains, use the greatest representable integer strictly below `t`, `t` only if representable, and the least representable integer strictly above `t`. Changing a source field recomputes all dimensions derived from it.
  3. One **missing-field variant** per predicate whose op is not `!=`, omitting its source key. Skip lifecycle boolean/list dimensions because omission encodes zero rather than missing. Deduplicate variants that omit the same source field.

  **Deterministic satisfying-witness selection:** candidates are selected jointly within each source-field group, then the whole input is normalized and checked against all originating predicates. This is independent of first-match routing: an earlier rule may still capture the witness.
  - Numeric source fields: use finite JavaScript numbers (decision-table domain [0,100]; lifecycle numeric fields are not implicitly bounded to that range). Build a finite candidate set from zero, finite domain endpoints, every finite numeric predicate literal, and the immediately adjacent finite IEEE-754 values below/above each literal. Private, unit-tested next-up/next-down helpers must handle zero, negative values, and finite extrema without emitting infinity/NaN. Filter to the domain and retain candidates satisfying every predicate in the group; choose by ascending absolute magnitude, then numeric value. Thus `score > 50 AND score < 50.5` has a witness; `<= 50` does not promise a globally lowest value. Test strict intervals with no representable value as well as narrow satisfiable ones.
  - Boolean source fields: enumerate `false`, `true` in that order, encoding to 0 and 100. Use the existing model-to-predicate conversion for authored boolean operators. Never fabricate scores such as 1 or 99 as boolean witnesses; test encoded inequality wherever the predicate contract permits it.
  - Lifecycle priority-rank groups: enumerate `P0` through `P9`, encode each against **all** declared dimensions sharing `priority`, and choose the first satisfying candidate. `priority == P2 AND priority_rank >= 1` must produce `priority: P2`; `priority == P2 AND priority_rank == 1` must be skipped. Serialize the shared source key once, at its first occurrence in dimension order.
  - Lifecycle list lengths: generate non-negative safe-integer candidates from zero and each finite literal's floor/ceiling and their immediate integer neighbours, then choose the smallest candidate satisfying the group; serialize an actual list of that length. Impossible fractional equalities are skipped.
  - Strings: try the group's equality literals in predicate order, then `not-` prefixed variants of all its literals in predicate order. Extend the prefix deterministically when necessary to avoid the group's finite set of excluded values. Apply source encoding (including status synonyms), serialization round-trip, and every predicate before accepting a candidate. A required equality that cannot round-trip is skipped.

  **`!=` is never satisfied by omission**: choose an emitted candidate satisfying the entire source-field group, and assert encoded inequality. In particular, `status != done` cannot use `completed`, and `blocked_by != 0` requires a nonempty list. Do not apply a separate `t+1`/`t-1` witness rule that can contradict other predicates.
  After all rules, the **fallback case**, chosen by tracing rather than by solving (third pass: "a deterministic non-matching value set" was an unspecified solver, and in lifecycle mode even the all-omitted input matches rules like `blocked_by == 0` or `flag ==false`): run `traceModel` over every candidate generated so far; if any already reaches the derived fallback, add nothing; otherwise add the all-omitted input if *it* traces to the fallback; otherwise emit no fallback case. The same trace pass sets each suggestion's `reason` from the rule it **actually** wins ("satisfies rule 3 → implement", "rule 2 boundary: confidence_score just below 85 → refine"), because an earlier rule — typically one using `!=` — can capture a later rule's satisfying case. `suggestScenarios` does not try to defeat earlier rules; a captured case is still emitted (it is a valid boundary input) with the truthful reason. Deduplicate; every suggestion has `expectedTarget: null` (suggestions never manufacture their own test oracle). This covers repeated targets, explicit lifecycle terminals from ENH-3492, the derived fallback, absent values, and threshold equality.

  Every suggestion for a valid model (FEAT-3488's routing-relevant definition) must pass `normalizeScenarioInput`. Decision-table numeric suggestions stay in [0,100] by **skipping, not clamping**: a boundary variant whose value falls outside [0,100] is dropped (clamping would duplicate the `t` case under a misleading "above/below" reason), and a rule whose satisfying case is impossible (`> 100`, `< 0`) is skipped entirely per the joint-solve rule above. Rubric suggestions are integers: for each threshold `t` emit `t-1`, `t`, `t+1` clamped to [0,100] and deduplicated (the runtime aggregate is `int()` of an `AGGREGATE:\s*(\d+)` match, so fractional neighbours are not representable — see FEAT-3488's rubric contract); the per-rule scheme above does not apply to rubric mode, which has no authored rules. Lifecycle suggestions use source fields the encoder accepts: generate `priority: Pn` for `priority_rank`, not a literal `priority_rank` field, and real lists for list-length predicates. Priority ranks and list lengths have discrete representable domains; choose representable neighbours on the intended side of a threshold and skip impossible equality/neighbour cases rather than emit invalid inputs. **Lifecycle `boolean` and `list` missing-field variants are unrepresentable**: `encodeFrontmatterScores` always emits a score for those types (`"0"` for an absent boolean, the count `"0"` for an absent list), so omitting the key never reaches `evalPredicate`'s missing-value branch — it collapses into the `==false` / length-0 case. Skip missing-field variants for lifecycle boolean/list predicates (a named, unit-tested rule like the string-dimension skip). Decision-table omission is genuinely absent and stays. `priority` and `priority_rank` share the single `priority` source key, so omitting either omits both. **Decision-table `string` dimensions are unrepresentable**: `_normalizeDecisionTableInput` accepts only booleans and numbers in [0,100] (a FEAT-3488 limitation this issue does not lift), so any decision-table rule with a predicate on a `string` dimension is skipped entirely and contributes no suggestion; the skip is a named, unit-tested rule, not silent.

  **Lifecycle suggestions serialize to frontmatter text.** Lifecycle `ScenarioInput` is only `{frontmatterText: string}`, so `suggestScenarios` must emit deterministic YAML text `parseFrontmatterBlock` accepts: one `key: value` scalar per source key in first-occurrence dimension order, lists as flow lists (`blocked_by: [BUG-1, BUG-2]`), booleans as `true`/`false`, priority as `priority: P2`, LF line endings, no fences. **Quoting rule**: a string scalar is double-quoted when it contains `#`, `:`, `,`, `"`, `'`, starts with `[`/`-`/whitespace, ends with whitespace, or is one of `null`/`~`/empty — `parseFrontmatterBlock` strips `#` comments outside quotes and normalizes unquoted `null`/`~` and quoted empty strings to `null`, while quoted `"null"`/`"~"` remain strings, so a bare rule literal like `needs: review` or `a #1` would be mangled. Every serialized field is round-trip asserted inside `suggestScenarios` (`parseFrontmatterBlock` → `encodeFrontmatterScores` yields the intended encoded value); a rule with a literal that cannot round-trip (for example, an empty string that the parser normalizes to null) is skipped by the same named skip rule. Pin this format in a node test so a `parseFrontmatterBlock` change cannot silently break generated cases.

- Identity: suggestions carry a deterministic content `key`, not an `id`. `key` and dedup use the **same semantic form**: canonical (key-sorted) JSON of `{mode, scores}` taken from `normalizeScenarioInput(model, input)` (rubric uses `{mode, aggregate}`). Raw key presence is deliberately **not** part of the key (third pass): routing sees only `scores`, and a lifecycle boolean/list that is absent encodes identically to an explicit `false`/`[]`, so including `rawPresent` would keep two routing-identical cases from deduplicating. Text equality is not the criterion — a hand-pasted lifecycle case and a generated one with different formatting but the same encoded fields are duplicates. The template assigns each inserted case a unique `id` at insertion time by calling the existing `_newScenarioId()` (FEAT-3488 pins that generator) and fills the **full FEAT-3488 `Scenario` shape**: `{id, name, input, expectedTarget: null, expectedRuleIndex: null, expectedFallback: false, expectedRulesFingerprint: null}` — the same literal "Add case" writes. "Add suggestions" skips any suggestion whose semantic key equals an existing case's semantic key in the destination suite, so re-running the action is idempotent and never creates duplicate IDs or duplicate cases. **All valid existing cases participate in dedup, including empty inputs and rubric `{aggregate: 0}`.** An existing empty case already exercises that input and may suppress an equivalent generated fallback; do not infer placeholder status from input bytes and do not add a new Scenario metadata field. Invalid cases are retained but excluded from the key set. Adding N > 0 suggestions is one committed edit; undo removes all N. Adding zero suggestions makes no history entry. Repeated clicks remain idempotent after reload and undo/redo.

  **Numeric spelling is deliberately preserved in the key.** This contract is equality of normalized encoded scores, not equivalence of all routing outcomes: lifecycle `"85"`, `"85.0"`, and `"8.5e1"` remain distinct keys, even when numeric predicates compare them equally. No additional numeric coercion is applied to string scores. Pin this limitation in tests and describe it without promising universal routing-equivalence dedup. Formatting differences that parse to the same score still deduplicate.

- `extractIssueFrontmatter(text) -> string` in core: accept a leading UTF-8 BOM if present, and CRLF; require a complete opening `---`-delimited block at the start of the file; return only its contents; throw a diagnostic naming the defect (missing opening fence, unclosed fence) before any suite mutation. The Markdown body is never inspected. The returned text then goes through `parseFrontmatterBlock` (which owns unsupported-subset rejection per FEAT-3488, a hard prerequisite) and `normalizeScenarioInput`. Only file import requires a fenced block; the paste path and `{frontmatterText}` scenario input keep FEAT-3488's fence-tolerant behaviour.

  **Non-dimension multi-line values are tolerated on import** (review 2026-09-18: running `parseFrontmatterBlock` over every frontmatter block in this repo's `.issues/` rejected 490 of 3408 files; 482 of those are `title:` values that `ll-issues` itself wraps onto an indented continuation line, the rest `cancelled_reason: |`/`decision:` block scalars — none on a routing dimension, and the diagnostic was "Can't read line N: <title fragment>", naming neither key nor cause). Add `dropNonDimensionContinuations(text, dimensionSourceKeys) -> string` in core (private, exported through the bridge for the template): walk lines; when a top-level `key:` line's key is **not** a dimension source key (`priority` for `priority_rank`), drop every following line that is indented (starts with whitespace) or is a block-scalar continuation until the next top-level `key:` line, and if the key's value is a bare `|`/`>`/`|-`/`>-` indicator, drop the indicator too so the key normalizes to `null`. Lines under a dimension key are passed through untouched so `parseFrontmatterBlock` still rejects unsupported shapes on fields that route. Import applies this **between** `extractIssueFrontmatter` and `parseFrontmatterBlock`; the paste path and `{frontmatterText}` scenario input do not use it. `parseFrontmatterBlock` itself does not change. Unit-test with a wrapped-`title` fixture and a `cancelled_reason: |` fixture taken from real repo files (routing fields intact), plus a wrapped-`status` fixture that must still be rejected.

- Template import: a file input plus `FileReader`. **Import is lifecycle-only**: the file input, its button, and the diagnostics element live inside the scenarios fieldset and are hidden via `applyModeVisibility()` unless `state.mode === "issue_lifecycle"` (an issue file has no meaning as decision-table or rubric input). **The import input must be excluded from the delegated `change` listener** (third pass): `#scenarios-fieldset` is inside `#form-panel`, whose delegated listener (`policy-router-builder.html.tmpl:1817`) calls `commit()` on every bubbled `change`. The file input's own `onchange` runs first and captures the revision; the bubble then commits, bumping the revision and pushing a no-op history entry — so every import would be discarded as stale and "one undo removes the case" would break. Add the input's id to that listener's exclusion selector (alongside `#tryit-fieldset, #frontmatter-tryit-fieldset`); "Open project" is unaffected only because its input sits outside `#form-panel`. Selecting a file must push no history entry by itself. Complete extraction, parsing, and input validation before adding a scenario in one committed edit; any read/validation failure leaves the existing suite unchanged and reports the diagnostic in a dedicated element. **Diagnostic wording**: every extraction failure message contains the word `frontmatter` or `fence` (e.g. "Missing opening frontmatter fence", "Unclosed frontmatter fence"), because the browser probe asserts `/fence|frontmatter/i`; read failures and unsupported-subset rejections prefix `parseFrontmatterBlock`'s own message with "Frontmatter:". Because `dropNonDimensionContinuations` has already removed every non-dimension continuation, a surviving "Can't read line N" rejection is by construction under a routing key: import names it ("Frontmatter: multi-line value under routing field `deferred_reason` is not supported — Can't read line N: …") by scanning back from line N to the nearest top-level `key:` line. The one real repo file that still fails after the drop (ENH-2738, a wrapped `deferred_reason`) is the fixture for this message. Imported cases start unasserted with the full FEAT-3488 `Scenario` shape (see Identity above), named from the file's `id` frontmatter when present, else the filename.

  The `FileReader` completion is bound to the project, destination lifecycle draft, and edit revision captured when import begins. Discard the completion with a diagnostic if that context changed before the read finishes — mode switch, Open, preset/start-blank, undo/redo, or any other committed edit. Use a monotonic session revision (incremented in `commit()`, Open, and snapshot restoration) as the invalidation token so switching away and back does not revive a pending read. **Starting a new import (or Open) also increments the revision**, cancelling any read still pending — otherwise two quick selections share a revision, the first completion's `commit()` invalidates the second, and the user sees a confusing "stale" diagnostic for a file they just chose; last selection wins, and a superseded read is discarded silently (no diagnostic). A discarded completion makes no suite or history change; a successful current completion adds exactly one case in one committed edit.

  **The existing "Open project" `FileReader` gets the same guard** (`policy-router-builder.html.tmpl:1902` `onchange`, `FileReader` at `:1906`; it currently reassigns `projectId`/`drafts`/`state`/`history` unconditionally on `onload`). Capture the session revision when the Open read begins; on load, if the revision has moved (any commit, undo/redo, mode switch, preset, Start blank, or a completed import/Open), discard the result with a live-region diagnostic and leave the project untouched. Same token, same semantics; a delayed-read probe for Open (monkeypatched `FileReader`, edit before load, assert project unchanged and no history reset) sits beside the import one.

- No skill, shell, LLM, or issue mutation executes from suggestions or imports.

## Integration Map

- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: `suggestScenarios`, `scenarioSemanticKey`, `extractIssueFrontmatter`, `dropNonDimensionContinuations`; export all through the browser-global bridge in a new `// FEAT-3503` group appended after the last existing group (FEAT-3501 landed in `9114ca1b6`, so there is no longer an in-flight bridge conflict to plan around).
- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: "Suggest cases" button, file input + `FileReader` wiring, session revision counter, import diagnostics element; revision guard added to the existing "Open project" `FileReader` `onload` (`:1902`); the import input added to the delegated `#form-panel` `change` listener's exclusion selector (`:1817`); all mutations go through FEAT-3488's suite-edit path and `commit()`.
- Regenerate the golden HTML through the generator (`scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`), never by hand-editing embedded JS.
- Tests: `scripts/tests/js/policy_scenarios.test.mjs` (created by FEAT-3488; the node gate globs `scripts/tests/js/*.test.mjs`), `scripts/tests/test_policy_builder_emit.py` for the golden HTML.
- Browser probes: `.loops/probes/feat-3488-browser-probes.mjs` `local-issue-import-offline` (tagged `needs: FEAT-3503`) — **fix this probe first**: the page loads in decision-table mode (`seedExample()` default) and the probe never switches mode, so its `cases() === 1` check reads the decision-table suite and would fail against a correct lifecycle-only import; add a `#mode-switch` change to `issue_lifecycle` before `setInputFiles` — plus a new delayed-read probe that monkeypatches `FileReader` via `page.evaluate` to defer `onload` until after a mode switch/Open/undo, asserting no case and no history entry is added; a matching delayed-read probe for "Open project" (edit before the deferred load; assert the project, active mode, and undo stack are unchanged); the import probe additionally asserts the undo stack depth is unchanged between selecting a file and the read completing (guards the delegated-`change` regression) and that a second selection before the first completes imports only the second; and a suggest-cases probe (deterministic count, idempotent second click, one undo removes all). Run via `.loops/verify-feat-3488-browser-persistence.yaml` after filling `SCENARIO_SELECTORS`.
- Documentation: `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` gain the suggestions and import subsections.
- No server, transport, queue, MCP, or config changes.

### Dependent Files (Callers/Importers)

- `policy-router-builder.html.tmpl:1177` — `updateFrontmatterTryIt()` calls `parseFrontmatterBlock(text)` directly on a pasted frontmatter block (read-only Try-it evaluation; never calls `commit()`).
- `policy_builder_core.mjs:3096` — `parseFrontmatterBlock` is exported through the browser-global bridge (`window.PolicyBuilderCore = {...}`); a new `suggestScenarios`/`extractIssueFrontmatter` export follows the same bridge convention.
- `scripts/tests/js/policy_validator.test.mjs` — the sole existing test coverage of `parseFrontmatterBlock` (fence tolerance, comment/quote stripping, nested-mapping/anchor/block-scalar rejection); no BOM/CRLF cases exist there because none of `parseFrontmatterBlock`'s current callers feed it a full file.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/policy_builder.py:101-115` — `cmd_policy_builder` reads both `policy_builder_core.mjs` and `policy-router-builder.html.tmpl` as raw text and embeds them verbatim (`html.replace("/*__BUILDER_CORE_JS__*/", core_js)`); no code change needed, new exports/markup are picked up automatically. [Agent 1 finding]
- `scripts/little_loops/cli/artifact/__init__.py:48,197` — registers and dispatches `cmd_policy_builder` for the `ll-artifact policy-builder` subcommand; no change needed, listed for completeness of the assembly path. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py` — `test_policy_builder_renders_byte_identically_to_golden_fixture()` (line 62-68) is the actual byte-for-byte comparison against `golden_policy_router_builder.html`, distinct from `test_policy_builder_emit.py` (which only asserts structural element ids); it will fail until the golden fixture is regenerated as part of this issue's implementation. [Agent 2 + Agent 3 finding]
- `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json` — closest existing corpus shape (`cases`/`js_reject_cases` arrays consumed by `policy_validator.test.mjs`) to extend with the BOM/CRLF/fence fixtures Implementation Step 2 calls for; no BOM/CRLF cases exist anywhere in the repo today. [Agent 2 + Agent 3 finding]

### Codebase Research Findings

_Current evidence, consolidated 2026-09-18; earlier pre-landing research is superseded._

- FEAT-3488 is done (commit `cf0ad35a7`): `normalizeScenarioInput`, `traceModel`, the `{model, scenarios}` draft wrapper, `_newScenarioId`, and `scripts/tests/js/policy_scenarios.test.mjs` exist. The retained `blocked_by` edge is resolved. This issue's suggestion/import helpers remain unimplemented.
- `detectShadows` provides the pure exported generator / `reason` convention. Existing structural handlers batch changes into one `commit()`; asynchronous import/Open invalidation remains new work.
- `parseFrontmatterBlock` serves both Try-it and lifecycle scenario normalization. The current Open handler uses `FileReader` without a revision guard. Use function-name anchors rather than historical line offsets.
- Direct Node probes confirmed that decision-table input accepts `50.25`, quoted `"null"` remains a string, and `priority: P2` encodes both `priority: "P2"` and `priority_rank: "2"` when both dimensions are declared. Lifecycle numeric spellings `85`, `85.0`, and `8.5e1` remain distinct encoded strings.

## Program Design

### Types

`SuggestedScenario {key: string, name: string, input: ScenarioInput, expectedTarget: null, reason: string}` — `reason` is a short human label derived from the `traceModel` result, naming the rule/target the case actually wins ("rule 3 boundary: confidence_score just below 85 → refine", "priority absent → gate (fallback)"). `ScenarioInput` per mode is FEAT-3488's.

### Signatures

- `suggestScenarios(model) -> SuggestedScenario[]` — deterministic order (rule order, then satisfying case, then per numeric predicate in predicate order below/at/above, then missing-field variants, then the trailing fallback case only when no earlier candidate already traces to the fallback; rubric: `thresholdHigh` neighbours then `thresholdMedium` neighbours); empty for an invalid model.
- `_nextUp(value) -> number` / `_nextDown(value) -> number` (core, private, new) — adjacent IEEE-754 candidate values; discard nonfinite results before constructing inputs.
- `_serializeLifecycleFrontmatter(fields) -> string` (core, private) — deterministic frontmatter text for lifecycle suggestions; the format pinned in Proposed Solution.
- `scenarioSemanticKey(model, input) -> string` (core, exported) — canonical key-sorted JSON of `{mode, scores}` (rubric: `{mode, aggregate}`) from `normalizeScenarioInput`; used for both `SuggestedScenario.key` and the template's dedup against existing cases.
- `extractIssueFrontmatter(text) -> string` — throws `Error` with a diagnostic; never returns partial text.
- `dropNonDimensionContinuations(text, dimensionSourceKeys) -> string` (core, exported) — removes indented/block-scalar continuation lines under keys not in `dimensionSourceKeys`; lines under dimension keys pass through unchanged. Pure; never throws.

### Call Path

Suggest: click → `suggestScenarios(buildModel())` → filter by `scenarioSemanticKey` against all valid existing cases (including empty inputs) → assign ids via `_newScenarioId()` with the full `Scenario` shape → if any cases remain, one suite edit → `commit()`; otherwise no mutation/history entry.
Import: file change (excluded from the delegated `#form-panel` commit listener) → increment revision, then capture `{projectId, mode, revision}` → `FileReader.readAsText` → on load: revision check → `extractIssueFrontmatter` → `dropNonDimensionContinuations` → `parseFrontmatterBlock` → `normalizeScenarioInput` → one suite edit → `commit()`; any throw before the edit reports and returns.
Open: file change → increment revision, then capture `revision` → `FileReader.readAsText` → on load: revision check (stale → diagnostic, return) → existing `parseBuilderProject` path unchanged.

### Codebase Research Findings

- `evalPredicate` treats missing values specially: only `!=` matches. Lifecycle boolean/list encoders emit zero even for absent source keys.
- Rubric aggregates are non-negative integers from `_AGGREGATE_RE` in `scripts/little_loops/fsm/policy_parse_scores.py`; scenario aggregates are constrained to [0,100]. Numeric decision-table inputs accept finite fractions in [0,100].
- `parseFrontmatterBlock` preserves scalar strings, parses flow/dash lists, canonicalizes status synonyms, and rejects unsupported nested/multiline shapes. Quoted `"null"` and `"~"` are strings; quoted empty strings and unquoted null markers become null. Import fence extraction remains a separate concern.

**Decision Rules**
- Rubric threshold-neighbour suggestions are anchored to `model.thresholdHigh`/`model.thresholdMedium` (the only two threshold fields that exist); because the runtime aggregate is `int()`-parsed from `AGGREGATE:\s*(\d+)` with no fractional representation, `t-1`/`t`/`t+1` integer neighbours (clamped to [0,100]) are the complete representable domain — there is no smaller-than-integer boundary to generate.
- Missing-field suggestions must omit the key (not null/empty-string it) to land in `evalPredicate()`'s missing-value branch, which matches only `!=`; one variant is emitted per predicate whose op is not `!=` (a `!=` predicate is satisfied by omission, so omitting it changes nothing). Lifecycle `boolean`/`list` predicates get no missing-field variant because `encodeFrontmatterScores` always emits a score for those types. (Supersedes the earlier per-dimension rule that keyed emission on the presence of a `!=` rule — that rule was a leftover of the rejected per-dimension design.)
- The `!=` distinct value is chosen by encoded inequality, not text inequality: never a `STATUS_SYNONYMS_JS` synonym of the literal, never a value that encodes to the same score. It is always an emitted value selected by the source-field candidate algorithm, never key omission — omission encodes as `"0"` for lifecycle boolean/list dimensions.
- Predicates sharing a source field are solved jointly using the domain-specific candidate order above. Verify the entire encoded witness against every originating predicate before emitting it; empty intersections and unsupported literals skip the rule (named, tested).
- Decision-table boundary variants outside [0,100] are skipped, not clamped; rubric neighbours are clamped and deduplicated (its domain is the closed integer range, so clamping cannot mislabel a case).
- The fallback case is found by `traceModel`, not solved for: none if an earlier candidate already reaches the fallback, else all-omitted if it reaches the fallback, else none. `reason` always reports the rule a suggestion actually wins; `suggestScenarios` never tries to defeat earlier rules.
- Lifecycle string scalars are double-quoted per the pinned quoting rule and round-trip asserted; an unrepresentable literal skips the rule.
- The import file input is excluded from the delegated `#form-panel` `change` → `commit()` listener; selecting a file pushes no history entry.
- Starting an import or Open increments the session revision (last selection wins; a superseded read is dropped silently).
- Dedup includes all valid existing inputs, including empty/zero inputs; zero insertions do not commit. Numeric spelling remains part of encoded-score identity.
- Import tolerates multi-line values only under non-dimension keys (`dropNonDimensionContinuations`), applied between `extractIssueFrontmatter` and `parseFrontmatterBlock`; routing fields keep strict rejection.
- Both `FileReader` call sites (import and Open) check the session revision on load and discard stale completions.
- Suggestions are generated per authored rule (satisfying case + per-numeric-predicate boundary variants + missing-field variants) plus one trailing fallback case; per-dimension generation is rejected because it cannot reach string-equality or compound rules (the seeded lifecycle example's `status == done` terminal and its `severity`/`review_status` rule).
- Decision-table rules with any predicate on a `string` dimension are skipped: `_normalizeDecisionTableInput` only accepts boolean/number values, so no valid scenario input can satisfy them. Lifecycle string dimensions are fine (frontmatter scalars stay strings).
- `SuggestedScenario.key` and the template's dedup both use `scenarioSemanticKey` (encoded `scores` only — raw key presence is excluded because routing never sees it), never raw input text or canonical JSON of the raw input — so a hand-pasted lifecycle case with different formatting is still recognized as a duplicate.
- Import is enabled only in `issue_lifecycle` mode; the destination draft is always the lifecycle draft.
- `extractIssueFrontmatter`'s fence/BOM/CRLF handling must stay outside `parseFrontmatterBlock` — that function's existing fence-tolerant, comment-stripping, and rejection behavior (nested mapping/anchor/block-scalar) is already tested and must not change; BOM-strip and CRLF-normalize happen before the text reaches `parseFrontmatterBlock`.

## Implementation Steps

1. Implement `suggestScenarios` with per-mode representable-domain rules (joint source-field candidate selection, named skip rule, `traceModel`-driven fallback and `reason`s, lifecycle quoting + round-trip) and node tests for narrow fractional intervals, boolean domains, shared priority constraints, and every witness satisfying its originating rule after serialization/encoding. Test dedup including empty/zero inputs and distinct numeric spellings.
2. Implement `extractIssueFrontmatter` with BOM/CRLF/fence fixtures, and `dropNonDimensionContinuations` with wrapped-`title`, `cancelled_reason: |`, and rejected wrapped-`status` fixtures.
3. Wire suggest and import into the template with the session revision token; exclude the import input from the delegated `#form-panel` `change` listener; add the same revision guard to the existing "Open project" `onload`; regenerate golden HTML.
4. Add the delayed-read (import and Open) and repeated-suggest probes (including empty inputs, rubric zero, no-op history, reload, and undo/redo), fill `SCENARIO_SELECTORS`, run the browser loop; update docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_enh3035_artifact_template_kit.py` — regenerate the golden HTML fixture it compares byte-for-byte so `test_policy_builder_renders_byte_identically_to_golden_fixture()` passes after `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` change.
- Extend `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json` with BOM/CRLF/fence cases for `extractIssueFrontmatter`.

## Impact

- Priority: P3 — same value tier as FEAT-3488; useful only once suites exist.
- Effort: Medium — domain-specific candidate selection, four exported helpers, shared-source serialization, template wiring, and browser probes. Fractional witnesses and asynchronous invalidation need focused tests.
- Risk: Medium — additive with no routing semantics change, but candidate-domain correctness, shared-source encoding, and asynchronous history guards require the specified regression coverage.
- Breaking change: No.

## Acceptance Criteria

- [ ] Suggestions follow the deterministic source-field candidate algorithm, are unasserted and deduplicated, and all normalize successfully. Witnesses satisfy every originating predicate after serialization/encoding; earlier-rule capture is allowed and reported truthfully by `traceModel`. Test `> 50 AND < 50.5`, an interval with no representable float, finite extrema/zero, boolean 0/100 domains, compatible and incompatible `priority`/`priority_rank` constraints, contradictory equalities, and nonfinite/unsupported literals. No invalid scores or duplicate source keys are emitted.
- [ ] Boundary variants are distinct from witness selection: numeric one-unit probes, representable discrete neighbours, and rubric integer neighbours follow their specified domain rules. Decision-table out-of-range variants are skipped. Lifecycle boolean/list missing-field variants and decision-table string rules are skipped by named tests. Every `!=` witness is present and encodes unequal; fallback/reason selection follows the actual trace. Lifecycle quoted `"null"`/`"~"` and supported punctuation round-trip; unrepresentable literals are skipped.
- [ ] Coverage after adding suggestions exercises ENH-3492 terminal targets and the derived fallback for the seeded lifecycle and decision-table examples (routing coverage, not assertion coverage) — for the seeded lifecycle example this means the `status == done` rule, the compound `severity`/`review_status` rule, both `confidence_score` rules, and the `gate` fallback each win at least one case.
- [ ] Repeated "Add suggestions" clicks produce no duplicate cases/IDs, including empty decision-table/lifecycle inputs and rubric aggregate zero, after reload and undo/redo. All valid existing cases participate; invalid inputs do not prevent adding valid suggestions. Same encoded scores deduplicate despite formatting differences or absent versus explicit lifecycle false/empty-list values; numeric strings `"85"`, `"85.0"`, and `"8.5e1"` deliberately remain distinct. New cases carry the full Scenario shape; one undo removes all additions, and a zero-addition click creates no history entry.
- [ ] Import controls are visible only in `issue_lifecycle` mode. A complete issue Markdown file imports successfully without parsing its body; BOM/CRLF are handled. A real repo issue file with a wrapped multi-line `title:` or a `cancelled_reason: |` block imports successfully (routing fields intact), while a multi-line value under a routing dimension is still rejected with a diagnostic naming that key. Selecting a file pushes no history entry on its own (the import input is excluded from the delegated `#form-panel` commit listener), so an immediate import is not discarded as stale and one undo removes exactly the imported case. Missing/unclosed fences, unsupported frontmatter, and read failures produce diagnostics containing `frontmatter` or `fence` without altering the suite. Successful import adds one unasserted case with the full `Scenario` shape and is undoable. The lifecycle paste path still accepts fence-less frontmatter. The `local-issue-import-offline` probe switches to lifecycle mode before importing.
- [ ] Delayed-read browser checks start an import, then switch modes, Open, apply a preset/start-blank, undo/redo, or commit another edit before completion. Stale completions add no case or history entry, even after switching away and back; a current successful completion adds exactly one undoable case to the captured lifecycle draft. Selecting a second file before the first read completes imports only the second (the first is dropped silently). The same guard covers "Open project": a stale Open completion leaves the project, active mode, and undo stack untouched and reports a diagnostic.
- [ ] Scenarios, suggestions, and imports execute no actions and make no predictions about LLM/action effects.
- [ ] Golden HTML regenerated; Node and Python gates pass; `ll-loop run .loops/verify-feat-3488-browser-persistence.yaml` passes with the import, delayed-read, and suggest-cases probes green.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` document boundary suggestions and local issue-file import.

## Use Case

A maintainer opens the issue-lifecycle draft, clicks "Suggest cases" to get the threshold and missing-field boundaries, then imports three real issue files from `.issues/` to see where each routes — without any of them being run.

## Scope Boundaries

Includes boundary suggestions and local file import only. Excludes connected issue discovery (FEAT-3504), transition analysis (FEAT-3501), and arbitrary YAML import. Suite persistence, verdicts, coverage, and subset validation are FEAT-3488's.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Routing, lifecycle semantics, simulation limits |
| Reference | docs/reference/CLI.md | Builder usage |

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (2026-09-18 `/ll:verify-issues --auto`; the line-anchor corrections below were applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was fixed, not an outstanding action item)

- Stale anchors corrected: delegated `#form-panel` change-listener exclusion `:1816` → `:1817`; `updateFrontmatterTryIt()` `:1110` → `:1177`; `window.PolicyBuilderCore` bridge `:2356` → `:3096` (`parseFrontmatterBlock` itself is at `policy_builder_core.mjs:2944`). Open-project `onchange`/`FileReader` (`:1902`/`:1906`) still exact.
- Confirmed: FEAT-3488, FEAT-3501 done; `normalizeScenarioInput`, `traceModel`, `_newScenarioId`, `encodeFrontmatterScores` exist; `suggestScenarios`, `extractIssueFrontmatter`, `scenarioSemanticKey`, `dropNonDimensionContinuations` do not yet exist (feature unimplemented, as stated). `ll-verify-evidence`: clean. Proposal-vs-code check found no contradiction.
- Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

Current review (2026-09-18): FEAT-3488 is resolved and the suggestion/import implementation remains outstanding. Previous format/design checks passed, but did not detect the behavioral conflicts corrected here. Historical confidence scores predate these revisions and should be refreshed before implementation.

Prior import prototype evidence: filtering non-dimension continuations reduced parser rejections from 490 of 3408 issue files to one wrapped routing field (`deferred_reason` in ENH-2738), which must remain rejected. Preserve the wrapped-title/block-scalar fixtures and routing-field rejection test.

## Status

**Open** | Created: 2026-09-17 | Priority: P3

## Session Log

- `/ll:confidence-check` - 2026-09-18T16:55:48 - `1dd00bcd-82df-4b59-9698-5d10270eb77e.jsonl`
- `/ll:verify-issues` - 2026-09-18T16:32:56 - `8bffa950-7522-4c88-bac6-c0f5c79c2f1a.jsonl`
- manual review applied - 2026-09-18 - resolved blank-input dedup, separated fractional/discrete witness selection from boundary probes, coupled shared source fields, corrected quoted-null and numeric-key contracts, and consolidated superseded research; implementation and acceptance sections updated together

- manual pre-implementation review (third pass) - 2026-09-18 - found the import input would bubble `change` into the delegated `#form-panel` `commit()` listener (every import stale + spurious history entry) and required its exclusion; specified joint solving for same-dimension predicates with a named skip for empty/NaN/unrepresentable rules; pinned `!=` to an emitted value (`not-`/`t+1` else `t-1`), never omission; replaced the unspecified fallback "non-matching value set" with a `traceModel`-driven choice and trace-derived `reason`s; added a lifecycle quoting rule with round-trip assertion; dropped `present` from `scenarioSemanticKey`; decision-table out-of-range variants skip rather than clamp; new import/Open bumps the revision (last selection wins); routing-key rejection diagnostic names the key; prototyped `dropNonDimensionContinuations` on all 3408 repo issue files (490 → 1 rejections); refreshed line anchors after FEAT-3501 landed
- manual pre-implementation review (second pass) - 2026-09-18 - measured real-file import failure rate (490/3408 repo issue files rejected by `parseFrontmatterBlock`, 482 on wrapped `title:`) and added `dropNonDimensionContinuations` for non-dimension keys; removed the contradictory per-dimension missing-field Decision Rule and simplified step 3 to "one per non-`!=` predicate"; named the lifecycle boolean/list missing-field skip (encoder always emits a score); required `!=` distinct values to encode unequal (status synonyms); excluded blank cases from suggestion dedup; extended the session-revision guard to the existing "Open project" `FileReader` with its own delayed-read probe; noted the FEAT-3501 bridge-group conflict
- `/ll:confidence-check` - 2026-09-18T02:32:48 - `e584dde7-f5fe-4489-bdc6-695a16a084be.jsonl`
- manual pre-implementation review - 2026-09-18 - switched suggestion generation from per-dimension to per-rule (coverage AC was unreachable for string-equality/compound rules); pinned lifecycle frontmatter serialization; unified `key`/dedup on `scenarioSemanticKey`; named the decision-table string-dimension skip; made import lifecycle-only and flagged the probe's missing mode switch; required the full `Scenario` shape on inserted cases; pinned `frontmatter|fence` diagnostic wording

- `/ll:verify-issues` - 2026-09-18T01:28:10 - `fde0dad3-9a6e-441c-b000-482ef8deced9.jsonl`
- `manual re-verification: FEAT-3488 core+template scenario suite has landed (uncommitted); corrected stale Codebase Research Findings claims` - 2026-09-18T00:53:01 - `7da57693-0c13-427c-bc37-9f39217b53a5.jsonl`
- `/ll:wire-issue` - 2026-09-18T00:45:12 - `21c0e3c4-8c4c-4bed-a96b-f58ee9e4dbd4.jsonl`
- `/ll:refine-issue` - 2026-09-18T00:29:03 - `5ba6e946-9d5c-4e37-bd48-7b8a54faec76.jsonl`
- manual review - 2026-09-17 - extracted from FEAT-3488 (boundary suggestions, local issue-file import, `FileReader` invalidation, delayed-read probes); pinned integer rubric neighbours, suggestion `key` vs template-assigned `id`, idempotent "Add suggestions"
