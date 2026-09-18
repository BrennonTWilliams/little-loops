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
  1. One **satisfying case**: every predicate of the rule is met at once — `==` gets its literal value, `!=` gets a deterministic distinct value (or omits the key, since a missing dimension matches only `!=`), boolean `==true`/`==false` gets `true`/`false`, and a numeric comparator gets the nearest representable value on the satisfying side (`>= t` → `t`, `> t` → `t+1`, `<= t` → `t`, `< t` → `t-1`).
  2. For each numeric predicate of that rule, in predicate order, the **boundary variants** of the satisfying case with that one field at `t-1`, `t`, `t+1` (in that order), other fields unchanged.
  3. One **missing-field variant** per predicate whose dimension is omitted from the satisfying case (only emitted when the rule is single-predicate or the omission changes the outcome — i.e. the predicate is not `!=`).
  After all rules, one **fallback case**: an input that satisfies no authored rule (all dimensions omitted when no rule uses `!=` and no authored catch-all exists; otherwise a deterministic non-matching value set), omitted when every possible input matches some rule. Deduplicate; every suggestion has `expectedTarget: null` (suggestions never manufacture their own test oracle). This covers repeated targets, explicit lifecycle terminals from ENH-3492, the derived fallback, absent values, and threshold equality.

  Every suggestion for a valid model (FEAT-3488's routing-relevant definition) must pass `normalizeScenarioInput`. Decision-table numeric suggestions stay in [0,100]. Rubric suggestions are integers: for each threshold `t` emit `t-1`, `t`, `t+1` clamped to [0,100] and deduplicated (the runtime aggregate is `int()` of an `AGGREGATE:\s*(\d+)` match, so fractional neighbours are not representable — see FEAT-3488's rubric contract); the per-rule scheme above does not apply to rubric mode, which has no authored rules. Lifecycle suggestions use source fields the encoder accepts: generate `priority: Pn` for `priority_rank`, not a literal `priority_rank` field, and real lists for list-length predicates. Priority ranks and list lengths have discrete representable domains; choose representable neighbours on the intended side of a threshold and skip impossible equality/neighbour cases rather than emit invalid inputs. **Decision-table `string` dimensions are unrepresentable**: `_normalizeDecisionTableInput` accepts only booleans and numbers in [0,100] (a FEAT-3488 limitation this issue does not lift), so any decision-table rule with a predicate on a `string` dimension is skipped entirely and contributes no suggestion; the skip is a named, unit-tested rule, not silent.

  **Lifecycle suggestions serialize to frontmatter text.** Lifecycle `ScenarioInput` is only `{frontmatterText: string}`, so `suggestScenarios` must emit deterministic YAML text `parseFrontmatterBlock` accepts: one `key: value` scalar per line in dimension order, lists as flow lists (`blocked_by: [BUG-1, BUG-2]`), booleans as `true`/`false`, priority as `priority: P2`, LF line endings, no fences. Pin this format in a node test so a `parseFrontmatterBlock` change cannot silently break generated cases.

- Identity: suggestions carry a deterministic content `key`, not an `id`. `key` and dedup use the **same semantic form**: canonical JSON of `{mode, present: sorted present-dimension names, scores}` taken from `normalizeScenarioInput(model, input)` (`scores` plus the `rawPresent` set from provenance; rubric uses `{mode, aggregate}`). Text equality is not the criterion — a hand-pasted lifecycle case and a generated one with different formatting but the same encoded fields are duplicates. The template assigns each inserted case a unique `id` at insertion time by calling the existing `_newScenarioId()` (FEAT-3488 pins that generator) and fills the **full FEAT-3488 `Scenario` shape**: `{id, name, input, expectedTarget: null, expectedRuleIndex: null, expectedFallback: false, expectedRulesFingerprint: null}` — the same literal "Add case" writes. "Add suggestions" skips any suggestion whose semantic key equals an existing case's semantic key in the destination suite, so re-running the action is idempotent and never creates duplicate IDs or duplicate cases. Adding N suggestions is one committed edit; undo removes all N.

- `extractIssueFrontmatter(text) -> string` in core: accept a leading UTF-8 BOM if present, and CRLF; require a complete opening `---`-delimited block at the start of the file; return only its contents; throw a diagnostic naming the defect (missing opening fence, unclosed fence) before any suite mutation. The Markdown body is never inspected. The returned text then goes through `parseFrontmatterBlock` (which owns unsupported-subset rejection per FEAT-3488, a hard prerequisite) and `normalizeScenarioInput`. Only file import requires a fenced block; the paste path and `{frontmatterText}` scenario input keep FEAT-3488's fence-tolerant behaviour.

- Template import: a file input plus `FileReader`. **Import is lifecycle-only**: the file input, its button, and the diagnostics element live inside the scenarios fieldset and are hidden via `applyModeVisibility()` unless `state.mode === "issue_lifecycle"` (an issue file has no meaning as decision-table or rubric input). Complete extraction, parsing, and input validation before adding a scenario in one committed edit; any read/validation failure leaves the existing suite unchanged and reports the diagnostic in a dedicated element. **Diagnostic wording**: every extraction failure message contains the word `frontmatter` or `fence` (e.g. "Missing opening frontmatter fence", "Unclosed frontmatter fence"), because the browser probe asserts `/fence|frontmatter/i`; read failures and unsupported-subset rejections prefix `parseFrontmatterBlock`'s own message with "Frontmatter:". Imported cases start unasserted with the full FEAT-3488 `Scenario` shape (see Identity above), named from the file's `id` frontmatter when present, else the filename.

  The `FileReader` completion is bound to the project, destination lifecycle draft, and edit revision captured when import begins. Discard the completion with a diagnostic if that context changed before the read finishes — mode switch, Open, preset/start-blank, undo/redo, or any other committed edit. Use a monotonic session revision (incremented in `commit()`, Open, and snapshot restoration) as the invalidation token so switching away and back does not revive a pending read. A discarded completion makes no suite or history change; a successful current completion adds exactly one case in one committed edit.

- No skill, shell, LLM, or issue mutation executes from suggestions or imports.

## Integration Map

- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: `suggestScenarios`, `extractIssueFrontmatter`; export both through the browser-global bridge.
- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: "Suggest cases" button, file input + `FileReader` wiring, session revision counter, import diagnostics element; all mutations go through FEAT-3488's suite-edit path and `commit()`.
- Regenerate the golden HTML through the generator (`scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`), never by hand-editing embedded JS.
- Tests: `scripts/tests/js/policy_scenarios.test.mjs` (created by FEAT-3488; the node gate globs `scripts/tests/js/*.test.mjs`), `scripts/tests/test_policy_builder_emit.py` for the golden HTML.
- Browser probes: `.loops/probes/feat-3488-browser-probes.mjs` `local-issue-import-offline` (tagged `needs: FEAT-3503`) — **fix this probe first**: the page loads in decision-table mode (`seedExample()` default) and the probe never switches mode, so its `cases() === 1` check reads the decision-table suite and would fail against a correct lifecycle-only import; add a `#mode-switch` change to `issue_lifecycle` before `setInputFiles` — plus a new delayed-read probe that monkeypatches `FileReader` via `page.evaluate` to defer `onload` until after a mode switch/Open/undo, asserting no case and no history entry is added; and a suggest-cases probe (deterministic count, idempotent second click, one undo removes all). Run via `.loops/verify-feat-3488-browser-persistence.yaml` after filling `SCENARIO_SELECTORS`.
- Documentation: `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` gain the suggestions and import subsections.
- No server, transport, queue, MCP, or config changes.

### Dependent Files (Callers/Importers)

- `policy-router-builder.html.tmpl:1110` — `updateFrontmatterTryIt()` calls `parseFrontmatterBlock(text)` directly on a pasted frontmatter block (read-only Try-it evaluation; never calls `commit()`).
- `policy_builder_core.mjs:2356` — `parseFrontmatterBlock` is exported through the browser-global bridge (`window.PolicyBuilderCore = {...}`); a new `suggestScenarios`/`extractIssueFrontmatter` export follows the same bridge convention.
- `scripts/tests/js/policy_validator.test.mjs` — the sole existing test coverage of `parseFrontmatterBlock` (fence tolerance, comment/quote stripping, nested-mapping/anchor/block-scalar rejection); no BOM/CRLF cases exist there because none of `parseFrontmatterBlock`'s current callers feed it a full file.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/policy_builder.py:101-115` — `cmd_policy_builder` reads both `policy_builder_core.mjs` and `policy-router-builder.html.tmpl` as raw text and embeds them verbatim (`html.replace("/*__BUILDER_CORE_JS__*/", core_js)`); no code change needed, new exports/markup are picked up automatically. [Agent 1 finding]
- `scripts/little_loops/cli/artifact/__init__.py:48,197` — registers and dispatches `cmd_policy_builder` for the `ll-artifact policy-builder` subcommand; no change needed, listed for completeness of the assembly path. [Agent 1 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3035_artifact_template_kit.py` — `test_policy_builder_renders_byte_identically_to_golden_fixture()` (line 62-68) is the actual byte-for-byte comparison against `golden_policy_router_builder.html`, distinct from `test_policy_builder_emit.py` (which only asserts structural element ids); it will fail until the golden fixture is regenerated as part of this issue's implementation. [Agent 2 + Agent 3 finding]
- `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json` — closest existing corpus shape (`cases`/`js_reject_cases` arrays consumed by `policy_validator.test.mjs`) to extend with the BOM/CRLF/fence fixtures Implementation Step 2 calls for; no BOM/CRLF cases exist anywhere in the repo today. [Agent 2 + Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- Neither `Scenario`/`ScenarioInput` types, `normalizeScenarioInput`, `suggestScenarios`, nor `extractIssueFrontmatter` exist anywhere in `policy_builder_core.mjs` or `policy-router-builder.html.tmpl` today (repo-wide search, zero hits outside the two issue markdown files) — confirms FEAT-3488 has not yet landed and this issue's `blocked_by` dependency is live, not stale.
- `parseFrontmatterBlock`'s only production caller today is `policy-router-builder.html.tmpl:1110`, inside `updateFrontmatterTryIt()` — a read-only "Try it" flow that never calls `commit()`. Its existing test coverage lives in `scripts/tests/js/policy_validator.test.mjs` (`scripts/tests/js/policy_scenarios.test.mjs` has not been created yet, consistent with FEAT-3488 not having landed).
- Convention (generator shape): the closest existing precedent for a `fn(collection) -> Array<{...identity fields, reason: string}>` generator is `detectShadows(rules)` (`policy_builder_core.mjs:481-513`) — pure, exported, unit-tested against a JSON conformance corpus. `taskPresets()` (`policy_builder_core.mjs:1246-1320`) is a second generator-shaped export but takes no model argument and labels items `label`/`description`, not `reason` — the two disagree on field naming; `detectShadows`'s `reason` convention matches `SuggestedScenario.reason` exactly.
- Convention (dedup): every existing uniqueness/dedup check in `policy_builder_core.mjs` (`detectShadows`'s predicate-tuple `Set`, `_doneStateName`, `_checkDuplicateOutcomes`) builds its `Set` key from a small number of scalar fields joined by a delimiter (a NUL-joined tuple, or a bare name string) — never by serializing an object to JSON. `JSON.stringify` appears 14 times in the file but always for error-message interpolation or whole-object cloning (`_deepClone`, `serializeBuilderProject`), never key-sorted, never used as a dedup key. No existing "canonical JSON" (key-sorted) helper exists to reuse for the proposed `key: canonical JSON of {mode, input}`.
- Convention (commit batching): every structural mutation handler in the template (`add-rule`, `applyPreset`, mode switch, undo/redo) mutates `state`/`drafts` synchronously, re-renders, then calls `commit()` exactly once in the same event-handler tick — this is the precedent for "one committed edit" but it is a synchronous-batching convention, not an async-completion guard; the revision-check step for the async `FileReader` completion has no analog among these callers.

> ⚠ Superseded — FEAT-3488's core + template scenario UI has since landed (uncommitted); see re-verification below.

_Re-verified `/ll:wire-issue` (on explicit request) — 2026-09-18, later same day — the working tree changed materially between the original refine pass and this check:_

- **FEAT-3488's implementation now exists in the working tree** (uncommitted — `git status` shows `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` as modified, +1066/-39 lines combined): `normalizeScenarioInput`, `traceModel`, `evaluateScenario`, `runScenarioSuite`, `withScenariosDefaulted`, and `rulesFingerprint` are all exported (core.mjs:1111,1304,1438,1468,1543) and wired into the bridge under a `// FEAT-3488 (offline scenario suites)` comment (core.mjs:3000-3005); the template now has 83 case-insensitive `scenario` hits — a `#scenarios-fieldset`/`#scenario-list`/`#add-scenario-btn` UI, a `scenarios` live variable mirrored into the `{model, scenarios}` draft wrapper, and `scripts/tests/js/policy_scenarios.test.mjs` (446 lines, `node:test`, named-imports `normalizeScenarioInput`/`traceModel`/`evaluateScenario`/`runScenarioSuite`) already exists on disk. **`suggestScenarios` and `extractIssueFrontmatter` — this issue's own two additions — still do not exist anywhere** (repeat repo-wide search, zero hits outside issue markdown); only the prerequisite surface has landed, not this issue's own scope.
- **The `blocked_by: FEAT-3488` dependency is now fully resolved** (superseding the prior "code-satisfied but not tracker-satisfied" note below): FEAT-3488 landed in commit `cf0ad35a7` ("feat(policy-builder): add offline scenario suites and trace explanations", "Closes FEAT-3488") and `ll-issues show FEAT-3488` now reports `status: Completed` — the `blocked_by` edge resolves per this repo's Issue File Format (`done`/`cancelled` only). `suggestScenarios` and `extractIssueFrontmatter` — this issue's own two additions — still do not exist anywhere in the committed code (repeat repo-wide search, zero hits outside issue markdown); only the prerequisite surface has landed.
- Convention (ID generation) — **fulfilled, not just precedent**: `_newScenarioId()` now exists in the template (line 328, immediately after `_newProjectId()`) and follows exactly the fallback shape this issue's Proposed Solution named as the template (`crypto.randomUUID()` else `"scn-" + Date.now().toString(36) + "-" + Math.random()...`). `suggestScenarios`'s planned "assign ids at insertion time using the same generator as ordinary 'Add case'" should call this existing `_newScenarioId()` directly — no new generator needed.
- Convention (file import + async completion) — **still accurate, re-confirmed**: the only `FileReader` usage in the template is still the single "Open project" handler (now at `policy-router-builder.html.tmpl:1843`/`:1844` `onclick`/`onchange` post-commit — shifted 4 lines from the `:1839-1840` pre-commit citation above — input markup at `:264-265`, unchanged). It still unconditionally reassigns state on `onload` with no staleness/revision guard of any kind; the repo-wide `AbortController`/`revision`-guard search finding (zero authored hits outside vendored `htmx.js`) still holds — this issue's planned monotonic session-revision counter remains genuinely new logic.
- Convention (tests) — **fulfilled**: `scripts/tests/js/policy_scenarios.test.mjs` is no longer a planned sibling file, it exists (446 lines) with exactly the described conventions (`node:test`/`assert/strict`, named imports, a `// FEAT-3488 node:test — ...` banner comment). This issue's own new tests append to this now-real file, not a to-be-created one.
- The `Draft {model: Model}` wrapper's earmarked `scenarios` sibling key — **fulfilled**: the draft wrapper is now literally `{model: state, scenarios}` throughout the template (e.g. lines 313, 409, 421, 497), confirming the seam was used as planned.
- `parseFrontmatterBlock` still has exactly one production caller (`policy-router-builder.html.tmpl:1187`, the same `updateFrontmatterTryIt()`-equivalent read-only "Try it" flow, line number shifted from `:1110`) — this claim is unaffected by the FEAT-3488 landing.

## Program Design

### Types

`SuggestedScenario {key: string, name: string, input: ScenarioInput, expectedTarget: null, reason: string}` — `reason` is a short human label ("just below high threshold", "priority absent"). `ScenarioInput` per mode is FEAT-3488's.

### Signatures

- `suggestScenarios(model) -> SuggestedScenario[]` — deterministic order (rule order, then satisfying case, then per numeric predicate in predicate order below/at/above, then missing-field variants, then the trailing fallback case; rubric: `thresholdHigh` neighbours then `thresholdMedium` neighbours); empty for an invalid model.
- `_serializeLifecycleFrontmatter(fields) -> string` (core, private) — deterministic frontmatter text for lifecycle suggestions; the format pinned in Proposed Solution.
- `scenarioSemanticKey(model, input) -> string` (core, exported) — canonical JSON of `{mode, present, scores}` (rubric: `{mode, aggregate}`) from `normalizeScenarioInput`; used for both `SuggestedScenario.key` and the template's dedup against existing cases.
- `extractIssueFrontmatter(text) -> string` — throws `Error` with a diagnostic; never returns partial text.

### Call Path

Suggest: click → `suggestScenarios(buildModel())` → filter by `scenarioSemanticKey` against existing cases → assign ids via `_newScenarioId()` with the full `Scenario` shape → one suite edit → `commit()`.
Import: file change → capture `{projectId, mode, revision}` → `FileReader.readAsText` → on load: revision check → `extractIssueFrontmatter` → `parseFrontmatterBlock` → `normalizeScenarioInput` → one suite edit → `commit()`; any throw before the edit reports and returns.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-18 — based on codebase analysis:_

- `model.mode` is one of `"decision_table" | "rubric" | "issue_lifecycle"` (`_SUPPORTED_MODES`, `policy_builder_core.mjs` module scope) — the enum `suggestScenarios(model)` must switch on.
- `opsForType(type)` (`policy_builder_core.mjs`) returns the legal comparator set per dimension type: `boolean` -> `["==true","==false"]`; `string` -> `["==","!="]`; `numeric`/`list` -> `["==","!=",">=","<=","<",">"]` — the boundary-relevant operator set per dimension type a threshold-neighbour suggestion must respect.
- `evalPredicate()` (unexported, called by `evaluateRules`/`evaluateModel`) treats a missing dimension (`raw === undefined || raw === null`) specially: only the `!=` operator matches. A missing-field suggestion must omit the dimension key entirely (not set it to `null`/`""`) to exercise this exact branch.
- Rubric mode's only threshold fields are `model.thresholdHigh`/`model.thresholdMedium`, enforced by `_checkRubricThresholds(model)` to satisfy `thresholdHigh > thresholdMedium` — there is no other numeric-threshold source in the model for rubric mode.
- The runtime aggregate these thresholds gate against is parsed Python-side by `_AGGREGATE_RE = re.compile(r"AGGREGATE:\s*(\d+)", re.IGNORECASE)` and `aggregate = int(agg_match.group(1))` (`scripts/little_loops/fsm/policy_parse_scores.py:29,48`) — a non-negative digit sequence only, so no fractional aggregate is ever produced. There is no JS-side mirror of this regex in `policy_builder_core.mjs`; the JS side only emits the `AGGREGATE:` instruction text (`_scoreActionBody()`, line 2164 as of the FEAT-3488 working-tree change — was line 1597 pre-landing) and validates `thresholdHigh`/`thresholdMedium` ordering — it never re-parses an `AGGREGATE:` line itself.
- `parseFrontmatterBlock` (`policy_builder_core.mjs:2806-2888` as of the FEAT-3488 working-tree change — was `:2198-2264` pre-landing, both cite the same function) returns `Record<string, string|string[]|null>` — scalars stay strings (never coerced to number/boolean), `""`/`null`/`~` normalize to `null`, flow-lists and dash-lists both normalize to `string[]`, and `status` is canonicalized through `STATUS_SYNONYMS_JS` before returning. It already tolerates `---` fence lines, strips `#` end-of-line comments outside quotes, and keeps quoted commas inside a flow-list element (`scripts/tests/js/policy_validator.test.mjs:456,485,491`); it rejects (throws `"Can't read line N: ..."`) a nested mapping, a YAML anchor/alias, and a multi-line block-scalar continuation. It has no BOM or CRLF handling anywhere — confirmed by an unfiltered repo grep for a leading BOM character and CRLF sequences across `scripts/little_loops/templates/` (zero hits in authored code) — `extractIssueFrontmatter`'s BOM-strip/CRLF-normalize step is genuinely new logic with no existing precedent to reuse or duplicate.

**Decision Rules**
- Rubric threshold-neighbour suggestions are anchored to `model.thresholdHigh`/`model.thresholdMedium` (the only two threshold fields that exist); because the runtime aggregate is `int()`-parsed from `AGGREGATE:\s*(\d+)` with no fractional representation, `t-1`/`t`/`t+1` integer neighbours (clamped to [0,100]) are the complete representable domain — there is no smaller-than-integer boundary to generate.
- Missing-field suggestions must omit the key (not null/empty-string it) to land in `evalPredicate()`'s missing-value branch, which matches only `!=`; a dimension with no rule using `!=` against it produces no missing-field suggestion (nothing to boundary-test) — this is the escape hatch for that suggestion kind.
- Suggestions are generated per authored rule (satisfying case + per-numeric-predicate boundary variants + missing-field variants) plus one trailing fallback case; per-dimension generation is rejected because it cannot reach string-equality or compound rules (the seeded lifecycle example's `status == done` terminal and its `severity`/`review_status` rule).
- Decision-table rules with any predicate on a `string` dimension are skipped: `_normalizeDecisionTableInput` only accepts boolean/number values, so no valid scenario input can satisfy them. Lifecycle string dimensions are fine (frontmatter scalars stay strings).
- `SuggestedScenario.key` and the template's dedup both use `scenarioSemanticKey` (encoded `scores` + present-key set), never raw input text or canonical JSON of the raw input — so a hand-pasted lifecycle case with different formatting is still recognized as a duplicate.
- Import is enabled only in `issue_lifecycle` mode; the destination draft is always the lifecycle draft.
- `extractIssueFrontmatter`'s fence/BOM/CRLF handling must stay outside `parseFrontmatterBlock` — that function's existing fence-tolerant, comment-stripping, and rejection behavior (nested mapping/anchor/block-scalar) is already tested and must not change; BOM-strip and CRLF-normalize happen before the text reaches `parseFrontmatterBlock`.

## Implementation Steps

1. Implement `suggestScenarios` with per-mode representable-domain rules and node tests proving every suggestion normalizes and encodes to its intended boundary.
2. Implement `extractIssueFrontmatter` with BOM/CRLF/fence fixtures.
3. Wire suggest and import into the template with the session revision token; regenerate golden HTML.
4. Add the delayed-read and suggest-cases probes, fill `SCENARIO_SELECTORS`, run the browser loop; update docs.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_enh3035_artifact_template_kit.py` — regenerate the golden HTML fixture it compares byte-for-byte so `test_policy_builder_renders_byte_identically_to_golden_fixture()` passes after `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` change.
- Extend `scripts/tests/fixtures/policy_builder/frontmatter_encoding_corpus.json` with BOM/CRLF/fence cases for `extractIssueFrontmatter`.

## Impact

- Priority: P3 — same value tier as FEAT-3488; useful only once suites exist.
- Effort: Medium — two pure helpers plus template wiring and probes; the hard invariants (representable domains, async invalidation) are already specified.
- Risk: Low — additive; no routing or persistence semantics change.
- Breaking change: No.

## Acceptance Criteria

- [ ] Suggestions are deterministic, deduplicated, unasserted, and generated per authored rule (satisfying case, per-numeric-predicate `t-1`/`t`/`t+1` boundary variants, missing-field variants) plus one trailing fallback case, without nonfinite/out-of-range inputs. Every generated suggestion for a valid model passes `normalizeScenarioInput`. Decision-table bounds are respected and rules touching a `string` dimension are skipped by a named, tested rule; rubric suggestions are integers `t-1`/`t`/`t+1` clamped to [0,100]; lifecycle suggestions are serialized frontmatter text in the pinned format and priority/list suggestions encode to their intended representable boundaries, with impossible neighbours/equalities omitted.
- [ ] Coverage after adding suggestions exercises ENH-3492 terminal targets and the derived fallback for the seeded lifecycle and decision-table examples (routing coverage, not assertion coverage) — for the seeded lifecycle example this means the `status == done` rule, the compound `severity`/`review_status` rule, both `confidence_score` rules, and the `gate` fallback each win at least one case.
- [ ] "Add suggestions" twice yields no duplicate cases and no duplicate IDs; dedup is by `scenarioSemanticKey`, so a pre-existing hand-authored case with the same encoded fields is not re-added; every inserted case carries the full FEAT-3488 `Scenario` shape (`expectedRuleIndex: null`, `expectedFallback: false`, `expectedRulesFingerprint: null`); one undo removes every case the click added.
- [ ] Import controls are visible only in `issue_lifecycle` mode. A complete issue Markdown file imports successfully without parsing its body; BOM/CRLF are handled. Missing/unclosed fences, unsupported frontmatter, and read failures produce diagnostics containing `frontmatter` or `fence` without altering the suite. Successful import adds one unasserted case with the full `Scenario` shape and is undoable. The lifecycle paste path still accepts fence-less frontmatter. The `local-issue-import-offline` probe switches to lifecycle mode before importing.
- [ ] Delayed-read browser checks start an import, then switch modes, Open, apply a preset/start-blank, undo/redo, or commit another edit before completion. Stale completions add no case or history entry, even after switching away and back; a current successful completion adds exactly one undoable case to the captured lifecycle draft.
- [ ] Scenarios, suggestions, and imports execute no actions and make no predictions about LLM/action effects.
- [ ] Golden HTML regenerated; Node and Python gates pass; `ll-loop run .loops/verify-feat-3488-browser-persistence.yaml` passes with the import, delayed-read, and suggest-cases probes green.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` document boundary suggestions and local issue-file import.

## Use Case

A maintainer opens the issue-lifecycle draft, clicks "Suggest cases" to get the threshold and missing-field boundaries, then imports three real issue files from `.issues/` to see where each routes — without any of them being run.

## Scope Boundaries

Includes boundary suggestions and local file import only. Excludes connected issue discovery (FEAT-3498), transition analysis (FEAT-3501), and arbitrary YAML import. Suite persistence, verdicts, coverage, and subset validation are FEAT-3488's.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Routing, lifecycle semantics, simulation limits |
| Reference | docs/reference/CLI.md | Builder usage |

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

- `blocked_by: FEAT-3488` is now fully resolved: FEAT-3488 was committed as `cf0ad35a7` ("Closes FEAT-3488") and `ll-issues show FEAT-3488` reports `status: Completed`. The issue's prior "code-satisfied but not tracker-satisfied" note (written while FEAT-3488 was still uncommitted) is stale and has been superseded in place above.
- Re-confirmed this issue's own scope is still unimplemented: `suggestScenarios` and `extractIssueFrontmatter` do not exist anywhere in the now-committed `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` (repo-wide search, zero hits outside issue markdown).
- Corrected a minor line-number drift: the "Open project" `FileReader` handler's `onclick`/`onchange` wiring is at `policy-router-builder.html.tmpl:1843`/`:1844` post-commit (was cited as `:1839-1840`, a 4-line drift from further edits before the commit landed). All other cited line numbers were re-verified against the committed code and are accurate: `parseFrontmatterBlock` definition at `policy_builder_core.mjs:2806`, its sole production caller (`updateFrontmatterTryIt`) at `policy-router-builder.html.tmpl:1187`, `_newScenarioId` at `:328`, `_scoreActionBody` at `policy_builder_core.mjs:2164`, file input markup at `:264-265`.
- `ll-verify-evidence --json` on this file: clean (`"ok": true`, 0 findings) — no fabricated evidence quotes.
- Dependency integrity: FEAT-3488's frontmatter carries the `Blocks: FEAT-3503` backlink (line 32) — no missing-backlink or broken-ref issue. No active required decision-log rules to check against (`ll-issues decisions list --type rule --enforcement required --active-only` returned empty).
- Proposed Solution traced against current code (ENH-3250 check): no exception-handler gaps, test-fixture invalidation, or AC/Integration-Map coverage gaps found — the spec's existing per-mode representable-domain rules and async-invalidation design already account for the codebase's actual constructs (`evalPredicate`'s missing-value branch, `_AGGREGATE_RE`'s integer-only domain, the single `FileReader` call site).

## Status

**Open** | Created: 2026-09-17 | Priority: P3

## Session Log

- manual pre-implementation review - 2026-09-18 - switched suggestion generation from per-dimension to per-rule (coverage AC was unreachable for string-equality/compound rules); pinned lifecycle frontmatter serialization; unified `key`/dedup on `scenarioSemanticKey`; named the decision-table string-dimension skip; made import lifecycle-only and flagged the probe's missing mode switch; required the full `Scenario` shape on inserted cases; pinned `frontmatter|fence` diagnostic wording

- `/ll:verify-issues` - 2026-09-18T01:28:10 - `fde0dad3-9a6e-441c-b000-482ef8deced9.jsonl`
- `manual re-verification: FEAT-3488 core+template scenario suite has landed (uncommitted); corrected stale Codebase Research Findings claims` - 2026-09-18T00:53:01 - `7da57693-0c13-427c-bc37-9f39217b53a5.jsonl`
- `/ll:wire-issue` - 2026-09-18T00:45:12 - `21c0e3c4-8c4c-4bed-a96b-f58ee9e4dbd4.jsonl`
- `/ll:refine-issue` - 2026-09-18T00:29:03 - `5ba6e946-9d5c-4e37-bd48-7b8a54faec76.jsonl`
- manual review - 2026-09-17 - extracted from FEAT-3488 (boundary suggestions, local issue-file import, `FileReader` invalidation, delayed-read probes); pinned integer rubric neighbours, suggestion `key` vs template-assigned `id`, idempotent "Add suggestions"
