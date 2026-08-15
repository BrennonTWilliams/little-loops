---
id: ENH-3185
title: Add an abstention verdict and a fixed verdict grammar to LLM-judged gates
type: ENH
priority: P2
status: open
testable: true
discovered_date: '2026-08-15'
labels:
- verification
- fsm
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

## Summary

Every LLM-judged gate in the stack forces a binary outcome. `verify-issue-loop` criteria mode, FSM LLM predicates, and `ll-harness` semantic criteria all require the judge to answer pass or fail, with no way to report that the check as written could not be evaluated from what the judge could see. An under-specified or unobservable criterion therefore resolves to whichever way the model leans, and that coin flip is persisted and acted on as a real verdict — a loop advances, an issue is marked verified, a quality trend absorbs a number that means nothing.

Add a third verdict, `cannot_judge` (displayed `CANNOT JUDGE`), as a first-class outcome alongside pass and fail, and specify the output contract that carries it.

The fixed multi-check output block originally bundled here was split out and then dropped on review; see `## Design` for why. No issue owns it today.

## Current Behavior

Every LLM judge in the stack is forced into a verdict it may have no basis for.

- `DEFAULT_LLM_SCHEMA` (`fsm/evaluators.py:74-106`) constrains `verdict` to `["yes", "no", "blocked", "partial"]`. None of these means "the check as written could not be evaluated from what I could see" — `blocked` means *cannot proceed without external help*, which is a statement about the task, not about the judge's evidence.
- `CHECK_SEMANTIC_EVIDENCE_CONTRACT` (lines 64-71) actively closes the gap the wrong way: "If you cannot quote specific text, your verdict is automatically No." Missing evidence is *coerced to failure*. An unobservable criterion and a genuinely failing one produce identical output.
- `scaffold_verify.py:_criteria_states()` routes `on_no` and `on_partial` both to `"failed"`, so a criterion the judge couldn't assess marks the issue unverified with the same authority as one that was assessed and failed.
- `cli/harness.py:432` — `if eval_result.verdict != "yes": passed = False`. Every non-`yes` verdict folds into failure; `pass_count`/`wilson_ci()` have no abstention denominator, so a run of all-abstentions and a run of all-failures are indistinguishable in the summary.
- `verdict_pass_rate()` (`history_reader.py:3146`) computes successes as `verdict IN ('pass','implement')` over all rows — a hardcoded two-value numerator with nowhere for a third outcome to go.
- Three schemas (`DEFAULT_LLM_SCHEMA`, `BLIND_COMPARATOR_SCHEMA`, the `contract` evaluator's inline schema) each declare their own verdict enum and already disagree on how many values exist.

Net: an under-specified or unobservable criterion resolves to whichever way the model leans, and that coin flip is persisted and acted on as a real verdict — a loop advances, an issue is marked verified, a quality trend absorbs a number that means nothing.

## Expected Behavior

`cannot_judge` is a first-class verdict alongside `yes`/`no`/`blocked`/`partial`, drawn from one shared vocabulary all three schemas consume. A judge that cannot evaluate a check from the evidence available says so instead of guessing.

Each consumer handles it distinctly. An FSM predicate holds rather than taking the false branch, bounded by a consecutive-abstention cap that escalates to `on_error` on exhaustion; loops that don't declare `on_cannot_judge` fall back to `on_error` and keep running. `ll-harness` reports abstentions separately from failures, and an all-abstention run is distinguishable from all-pass and all-fail in both the summary and the exit code. `.ll/history.db` persists abstention per check, excluded from the pass-rate denominator and queryable as its own rate — so a criterion that is abstained on repeatedly becomes visible as a badly written criterion rather than disappearing into a pass/fail number.

A judge emitting a verdict outside the grammar fails loudly instead of being coerced.

## Design

**Scope: this issue adds the abstention verdict only.** The multi-check output block originally specified here (old AC2) was split into ENH-3200 and then dropped when that issue was re-reviewed — every judge site in this codebase is single-verdict-per-invocation today, and `verify-issue-loop` in particular builds *one FSM state per criterion* (`scaffold_verify.py:_criteria_states()`), so an N-checks-in-one-pass block is a rearchitecture rather than an addition. The review also found it would split one investigation's evidence budget across N criteria, trading verification depth for fewer invocations — the wrong direction for a gate whose purpose is rigor, and a change that would *increase* the abstention rate this issue exists to measure. ENH-3200 now covers the separable, genuinely valuable half (criteria mode short-circuiting on first failure). Nothing owns the multi-check block; refile it if invocation cost ever becomes the actual driver.

Abstention is independently valuable and cheap in the existing one-verdict-per-state shape, and lands here.

**Wire value vs. display token.** The structured-output enum value is `cannot_judge` — lowercase snake, matching the existing `yes`/`no`/`blocked`/`partial` members. This is not cosmetic: FSM routing derives `on_<verdict>` shorthands from the literal verdict string (`fsm/schema.py:866`), so `on_cannot_judge:` only works if the value is spelled this way. `CANNOT JUDGE` is the human-facing display token in prompt text and reports. Every consumer uses `cannot_judge` on the wire.

Callers decide what abstention means for them:

- An FSM predicate holds rather than taking the false branch — **bounded**, see below.
- `ll-harness` reports it separately from failures instead of folding it into the failure count.
- `.ll/history.db` persists it per check, so abstention rate becomes a visible signal.

### Abstention must be bounded

"No-transition" taken literally re-enters the same state, the judge abstains again for the same reason, and the loop never terminates. The hold is therefore capped: after N consecutive abstentions on the same state (default small, e.g. 2), the state escalates to `on_error`. An abstention hold is a retry, and retries need a ceiling.

### Routing default is `on_error`, never `on_no`

`_route()` returns `None` when nothing matches, and `run()` turns that into `_finish("error", error="No valid transition")` (`executor.py:752-768`) unless `fsm.maintain` is set. So simply adding `cannot_judge` to `DEFAULT_LLM_SCHEMA` converts every existing loop that doesn't declare `on_cannot_judge` from passing into a hard run-terminating failure the first time a judge abstains. Since every local-editable project on this machine runs off this working tree, that regression would land silently and everywhere. An undeclared `on_cannot_judge` must fall back to `on_error` — and must never fall back to `on_no`, which would reintroduce exactly the coin-flip this issue exists to remove.

A criterion that is abstained on repeatedly is a badly written criterion. That is information the current binary shape destroys.

## Relationship to adjacent work

This is the LLM-judge counterpart to the deterministic question of what exit code 124 means — timeout is ignorance, not a verdict. It is distinct from requiring a gate to declare its scope at authoring time: that is a statement about the gate, this is a statement about one run of one check.

Where a check is abstained on because the judge lacked the artifact rather than because the criterion was vague, that is a harness bug, and the signal will surface it.

## Acceptance Criteria

- **AC1.** `cannot_judge` is a first-class verdict in the grammar (display token `CANNOT JUDGE`), not a parse failure.
- **AC2.** _Withdrawn — the fixed multi-check output block. Split to ENH-3200, then dropped when that issue was re-reviewed (see `## Design`). Unowned; not in scope here._
- **AC3.** Each of the three consumers handles abstention distinctly from failure, with the behaviour tested.
- **AC10 (blocker — evidence coercion must exempt abstention).** `evaluate_llm_structured()` rewrites the verdict before returning it (`fsm/evaluators.py:1256-1258`):

  ```python
  evidence_coerced = schema is None and not evidence.strip() and verdict not in ("error",)
  if evidence_coerced:
      verdict = "no"
  ```

  An abstention has no verbatim quote *by definition* — that is what abstaining means. On the default-schema path (which is exactly the FSM predicate path, `schema is None`), `cannot_judge` is therefore rewritten to `no` before it ever reaches `_route()`, and the entire feature is a silent no-op. `cannot_judge` must join `"error"` in the exemption tuple, with a test asserting an abstention with empty `evidence` survives the coercion step unchanged. Nothing else in this issue works until this does.
- **AC11 (blocker — the prompt contract must be rewritten, in *three* places).** Adding an enum member does not make a judge emit it while the prompt text forbids it. All three of the following instruct missing-evidence→No and must be rewritten together; any one left behind suppresses abstention on the path it governs.
  1. **`CHECK_SEMANTIC_EVIDENCE_CONTRACT`** (`fsm/evaluators.py:64-71`), appended to every LLM evaluator prompt (line 1124): *"State your verdict: Yes / No / Partial"* and *"If you cannot quote specific text, your verdict is automatically No (or Partial if context suggests partial progress)."*
  2. **`DEFAULT_LLM_SCHEMA`'s `evidence` field description** (`fsm/evaluators.py:96-99`): *"Empty string means no evidence was found; verdict will be coerced to 'no'."* This ships **inside the structured-output schema the judge is given**, so it contradicts the new grammar at the point of generation — not merely in surrounding prose. The `verdict` field's own enum descriptions (lines 79-85) also need a `cannot_judge` line.
  3. **`scaffold_verify.py:73`** — the per-criterion eval prompt: *"Answer NO if the criterion is not met **or evidence is missing/ambiguous**."* Baked into every generated `verify-issue-loop`. Because verify-issue-loop is a headline consumer of this feature, leaving this line makes the feature a no-op precisely where it was most wanted.

  The rewritten contracts keep the evidence requirement for `yes`/`no`/`partial` — abstention is the *only* verdict admissible without a quote, otherwise this becomes an escape hatch from ENH-2342. A test asserts none of the three texts still instructs missing-evidence→No, so a fourth site added later fails loudly rather than silently re-suppressing abstention.
- **AC12 (`uncertain_suffix` interaction).** When `min_confidence` is set and the judge's confidence falls below it, `evaluate_llm_structured()` returns `f"{verdict}_uncertain"` (`fsm/evaluators.py:1262`) — so an abstention can arrive at `_route()` as `cannot_judge_uncertain`, which matches no shorthand, no `extra_routes` key, and no route table entry. AC6's fallback and AC7's cap both handle the suffixed form, with a test. The issue also states the relationship between the two signals: low-confidence-uncertain means *"I evaluated it and I am unsure"*; `cannot_judge` means *"I could not evaluate it."* They are distinct, they can co-occur, and AC4's abstention rate must count a `cannot_judge_uncertain` once, not once per signal.
- **AC4.** Abstention is persisted per check and queryable as a rate, **separately from pass rate**. `verdict_pass_rate()` (`history_reader.py:3126-3181`) computes `SUM(CASE WHEN verdict IN ('pass','implement') ...)` over *all* rows (line 3146); if abstentions land in that denominator, a run of abstentions silently deflates the pass rate and reads as a quality regression. Abstentions are excluded from the pass-rate denominator and reported as their own rate. New migration is **v41** — `SCHEMA_VERSION` is currently 40 (`session_store/schema.py:21`), not 33.
- **AC5.** A judge that emits a verdict outside the grammar fails loudly rather than being coerced to pass or fail.
- **AC6.** Existing loops that do not declare `on_cannot_judge` do not regress: the verdict falls back to `on_error`, never to `on_no`. This must hold on **both** of `_route()`'s two paths (`executor.py:2609-2662`), which are separate code and fail differently:
  - **Shorthand path** (`on_yes`/`on_no`/…). A precedent for exactly this shape already exists one line up and should be mirrored: `if verdict == "no" and not state.on_no and state.on_error`. Test: a loop YAML declaring only `on_yes`/`on_no` receives an abstention.
  - **Route-table path** (`route:`) — *not covered by the original AC6 wording, and the more dangerous of the two.* `_route()` consults `state.route.default` before falling through to anything else:

    ```python
    if verdict in routes: ...
    if state.route.default: return self._resolve_route(state.route.default, ctx)
    ```

    So a loop written as `route: {yes: X, no: Y, default: Y}` routes an abstention silently into the fail branch — reintroducing precisely the coin flip this issue exists to remove, through a door AC6 left open. **Abstention must not be absorbed by `route.default`**: unless `cannot_judge` is an explicit key in `routes`, it resolves to `route.error`/`on_error`. This is a deliberate asymmetry with `default`'s normal catch-all semantics and is documented as such. Test: a loop YAML with a `route:` table carrying a `default:` receives an abstention and does **not** take the default branch.
- **AC7.** An abstention hold is bounded by a consecutive-abstention cap per state, escalating to `on_error` on exhaustion; a test proves an always-abstaining judge terminates.
- **AC8.** The verdict vocabulary has a single importable source of truth — a new module under `scripts/little_loops/fsm/` (suggested name: `verdicts`, to be created) — that `DEFAULT_LLM_SCHEMA`, `BLIND_COMPARATOR_SCHEMA`, and the `contract` evaluator's inline schema all consume. These three already declare independent enums that disagree on how many values exist; without one source the grammar drifts again as soon as a fourth site appears.
- **AC9.** `ll-harness` exit-code semantics for abstention are specified with concrete numbers and tested. "Distinguishable" is not a testable criterion; the mapping is:

  | Outcome | Exit | Notes |
  |---|---|---|
  | All checks pass | `0` | unchanged — `return 0 if pass_count == total else 1` (`cli/harness.py:725`) |
  | Any check fails | `1` | unchanged; failure dominates abstention |
  | No failures, ≥1 abstention | `3` | new — inconclusive, not a pass and not a failure |
  | Harness/infra error | `2` | unchanged and **already taken** (`harness.py:414,417,574,582,652,656,747`) — abstention must not reuse it, or an inconclusive verdict becomes indistinguishable from a crashed run |

  Precedence is fail > abstain > pass, so a mixed run reports `1`. The summary reports abstentions as their own count alongside `pass_count`, and `wilson_ci()` (lines 658-725) excludes them from its denominator rather than counting them as failures. Tests cover all-pass, all-fail, all-abstain, and mixed. Today `if eval_result.verdict != "yes": passed = False` (`cli/harness.py:432`) collapses the first three into two.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured()` (line ~1094) builds the judge prompt (`effective_prompt = (prompt or DEFAULT_LLM_PROMPT) + "\n\n" + CHECK_SEMANTIC_EVIDENCE_CONTRACT`, line 1124) and parses its response. `DEFAULT_LLM_SCHEMA` (lines 74-106) constrains `verdict` to the enum `["yes", "no", "blocked", "partial"]` — no `cannot_judge` member exists. `CHECK_SEMANTIC_EVIDENCE_CONTRACT` (lines 64-71, "State your verdict: Yes / No / Partial") is the current two-way evidence-coercion contract (missing evidence -> forced `"no"`) that AC1's grammar extends to three-way. Two other inline schemas exist independently and disagree on vocabulary: `BLIND_COMPARATOR_SCHEMA` (lines 187-212) and the `contract` evaluator's inline schema (lines 1483-1491) both use only `["yes", "no"]`.
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._route()` (lines 2609-2662) matches the verdict against `state.route.routes`, then `on_yes`/`on_no`/`on_error`/`on_partial`/`on_blocked` shorthand fields, then `state.extra_routes[verdict]`; returns `None` if nothing matches. In `run()` (lines 468+), a `None` next_state (lines 752-768) re-enters `on_maintain`/`initial` only if `fsm.maintain` is set, or terminates the whole run via `_finish("error", error="No valid transition")` — today an unroutable verdict is a hard run-terminating error, not AC's proposed "no-transition" hold behavior for `CANNOT JUDGE`.
- `scripts/little_loops/cli/loop/scaffold_verify.py` — **also carries an AC11 coercion site**: the generated per-criterion `eval_prompt` (line 73) says *"Answer NO if the criterion is not met or evidence is missing/ambiguous."* `_criteria_states()` (lines 58-87) builds **one separate FSM state per acceptance criterion**, each independently going through `evaluate_llm_structured()`/`DEFAULT_LLM_SCHEMA`, chained via `on_yes`/`on_no: "failed"`/`on_partial: "failed"` (lines 81-84) — not the single-pass, N-checks-in-one-block judge AC2 proposes. `_adversarial_states()` (lines 129-172) follows the same per-state pattern for its three probe states.
- `scripts/little_loops/cli/harness.py` — `_evaluate_and_report()` (lines 406-479): `if eval_result.verdict != "yes": passed = False` (lines 429-433) folds every non-`"yes"` verdict (including a hypothetical `cannot_judge`) into failure; `overall = "PASS" if passed else "FAIL"` (line 435) has no third bucket. `pass_count`/`wilson_ci()` (lines 658-725) has no abstention denominator — a run of all-abstentions and a run of all-failures are indistinguishable in the summary today.
- `scripts/little_loops/session_store/schema.py` — current `SCHEMA_VERSION = 40` (line 21); a new abstention column/table is **v41**. The tables cited below are the relevant existing ones, not the head of the migration chain. `harness_events` table (`v31`, lines 696-725, columns incl. `semantic_verdict TEXT`, `semantic_passed INTEGER`) stores one row per harness invocation, no abstention column. `verdict_events` table (`v33`, lines 754-779, `verdict TEXT NOT NULL`) is the verifier-outcome table for `ll-ready-issue`/`ll-verify-issues`. `loop_events` table (`v1`, lines 140-147, `transition` column) records the FSM routing outcome per state transition — the closest existing per-check ledger for `llm_structured` states, but with no abstention flag or rate query.
- `scripts/little_loops/history_reader.py` — `verdict_pass_rate()` (lines 3126-3181) is the existing per-`verdict_kind` pass-rate rollup (`{invocations, successes, success_rate}`, filterable by `target_id`/`since`) that AC4's "abstention... queryable as a rate" would extend or sit alongside; its numerator (`verdict IN ('pass', 'implement')`) is hardcoded to two known values.

### Conventions in Force
- The exit-code-124 short-circuit the issue explicitly analogizes to (`fsm/evaluators.py`, `evaluate()` dispatcher ~line 1821, tagged `BUG-1640`) routes a timed-out action to the generic `verdict="error"` (`on_error`), not to a dedicated no-transition/hold state — so even the cited analog doesn't yet implement the exact "no-transition" semantics AC3 proposes for `CANNOT JUDGE`. `evaluate_mcp_result()` has its own separate `"timeout"` verdict (lines ~1023-1027) for MCP calls specifically.
- `"error"` already functions as a de facto third bucket distinct from `"yes"`/`"no"` throughout `evaluators.py` — `evaluate_exit_code`, `evaluate_output_numeric`, `evaluate_output_json`, `evaluate_mcp_result`, `evaluate_harbor_scorer` all return `verdict="error"` for ill-defined cases, and `on_error` is already a dedicated FSM routing shorthand distinct from `on_no` — this is the nearest existing precedent for adding a fourth/fifth first-class verdict rather than inventing new machinery.
- Verdict enums are declared inline per call site, not in a shared/importable constant module (`DEFAULT_LLM_SCHEMA`, `BLIND_COMPARATOR_SCHEMA`, the `contract` evaluator's inline schema each define their own `enum` list independently, and disagree on how many values exist) — a fixed grammar spanning all three consumers has no single existing source of truth to extend.
- A separate, unrelated multi-way verdict vocabulary already exists for prose-parsed (non-structured-output) responses: `VALID_VERDICTS = ("READY", "CORRECTED", "NOT_READY", "NEEDS_REVIEW", "CLOSE", "BLOCKED")` (`output_parsing.py:24`), parsed by `_extract_verdict_from_text()` which defaults to `"UNKNOWN"` on total parse failure — a silent-coercion pattern, contrasted with AC5 ("fails loudly rather than being coerced").
- This codebase's established shape for "loud, never-swallow" parsing is a `(value, error)` tuple return — `extract_tagged_json()` (`output_parsing.py:27-71`) and `extract_between_tags()`/`parse_prefilled_json()` (`output/parse.py:30-119`) both document "Never swallows — callers must surface the error when value is None" (convention established by BUG-2383). This is the pattern AC5's "fails loudly rather than being coerced" would extend to verdict-grammar validation, as distinct from `evaluate_llm_structured()`'s own convention of returning an `EvaluationResult(verdict="error", ...)` sentinel rather than raising.
- No existing fixed numbered multi-check output block exists anywhere in this codebase's LLM-judge prompts — every current site (FSM `llm_structured`, harness `--semantic`, verify-issue-loop criteria states) is single-verdict-per-invocation. The closest analog is `confidence-check`'s two-layer contract: a human-readable table plus a single tagged `VERDICT_JSON: {...}` trailer line (`skills/confidence-check/rubric.md:361-430`) — parsed via the same `extract_tagged_json` convention `audit-loop-run`'s `REVIEW_JSON` uses, but that skill emits one verdict per report, not N per pass, and the doc notes 8 of 9 verifiers don't yet emit a tagged trailer at all.

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestLLMStructuredEvaluator` (lines 849-1025): every verdict value gets its own `test_<verdict>_verdict` method following a shared `mock_cli` fixture + `_cli_stdout()` helper that mocks `subprocess.run` and feeds a JSON CLI envelope (`test_success_verdict`, `test_blocked_verdict`, `test_partial_verdict`, `test_custom_schema`). A `test_cannot_judge_verdict` would follow this exact template.
- `scripts/tests/test_cli_harness.py`, `scripts/tests/test_verify_issue_loop.py`, `scripts/tests/test_session_store_schema.py`, `scripts/tests/test_history_reader.py` — existing coverage for the three consumers and the persistence/query layer that would each need an abstention-handling test.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-15 — based on codebase analysis:_

### Types
- `EvaluationResult` (`fsm/evaluators.py`) — `verdict: str`, `details: dict[str, Any]` — the return shape every evaluator function produces; a `CANNOT JUDGE` verdict is a new member of `verdict`'s value space, not a new field.
- `verdict: Literal["yes", "no", "blocked", "partial"]` — the current `DEFAULT_LLM_SCHEMA` enum (`fsm/evaluators.py:74-106`); AC1 adds `cannot_judge` (this exact spelling — not "or equivalent", see Design) as a fifth member here, and to the two other inline schemas (`BLIND_COMPARATOR_SCHEMA`, the `contract` evaluator's schema) that independently enumerate only `["yes", "no"]`. Per AC8 all three consume one shared constant rather than re-declaring the enum.

### Signatures
- `evaluate_llm_structured(output: str, prompt: str | None = None, schema: dict | None = None) -> EvaluationResult` — the FSM LLM-predicate entry point (`fsm/evaluators.py:1094`) whose default schema and evidence contract (`CHECK_SEMANTIC_EVIDENCE_CONTRACT`) this issue extends from two-way (Yes/No/Partial) to three-way.
- `verdict_pass_rate(verdict_kind: str | None = None, target_id: str | None = None, since: str | None = None) -> list[dict]` — the existing per-`verdict_kind` rate rollup (`history_reader.py:3126-3181`) AC4's abstention-rate query would extend or sit alongside.

### Call Path
`evaluate_llm_structured` -> `EvaluationResult` -> `_route`

### Decision Rules
- Grammar: `cannot_judge` becomes a fifth verdict value alongside the existing `yes`/`no`/`blocked`/`partial` enum (`DEFAULT_LLM_SCHEMA`). The multi-check block is no longer part of this issue, and no longer part of ENH-3200 either — it is unowned.
- **FSM routing is nearly free, and the cost is entirely in the default.** `StateConfig._from_dict()` already derives `extra_routes` from *any* unrecognized `on_*` key (`fsm/schema.py:866-870`), and `_route()` consults `state.extra_routes[verdict]` before giving up (`executor.py:2658-2660`). So `on_cannot_judge: <target>` routes correctly today with zero new machinery, provided the verdict string is exactly `cannot_judge`. The implementation work is therefore not the routing — it is the undeclared-key fallback (AC6) and the hold cap (AC7).
- Per-consumer dismissal/handling (already specified in the issue, not underspecified): FSM predicate → no-transition (today's nearest analog, the exit-124 short-circuit, instead routes to `verdict="error"`/`on_error`, which is a hard terminate-or-transition, not a hold — the two are not currently equivalent and reconciling them is part of the implementation). `ll-harness` → reported separately from `pass_count`/`wilson_ci()`, not folded into `passed = False`. `.ll/history.db` → persisted per check as a queryable rate, with no existing abstention column on `harness_events`/`verdict_events`/`loop_events` to extend from.
- Escape hatch (AC5): "a judge that emits a verdict outside the grammar fails loudly rather than being coerced to pass or fail." The codebase's existing precedent for the *opposite* polarity is `_extract_verdict_from_text()` (`output_parsing.py`), which silently defaults to `"UNKNOWN"` on parse failure — AC5 requires abandoning that coercion-on-failure convention for this grammar specifically, in favor of the `(value, error)`-tuple "never swallow" convention (`extract_tagged_json()`, BUG-2383).


## Scope Boundaries

Explicitly **out of scope**:

- **The fixed multi-check output block** — withdrawn entirely (see `## Design`), not merely deferred to another issue. Every judge site stays one-verdict-per-invocation.
- **Rearchitecting `verify-issue-loop`'s state chain.** `_criteria_states()` keeps building one FSM state per criterion; this issue only changes what verdicts those states can produce and where they route.
- **Teaching judges *when* to abstain.** This adds the verdict and the plumbing. Prompt-engineering the judgement call — and the inevitable tuning of over- vs. under-abstention — is follow-on work informed by the abstention-rate signal AC4 makes visible.
- **Acting on the abstention rate.** No auto-flagging, auto-rewriting, or gating on abstention-heavy criteria. AC4 makes the rate queryable; consuming it is a separate issue.
- **The other multi-way verdict vocabulary.** `VALID_VERDICTS` in `output_parsing.py:24` (`READY`/`CORRECTED`/`NOT_READY`/…) is a prose-parsed, non-structured-output path for a different set of consumers. It is not unified with the structured grammar here, and its silent `"UNKNOWN"` default is left alone outside this grammar's scope.
- **Retrofitting `on_cannot_judge` into existing loop YAMLs.** AC6's `on_error` fallback is what keeps them working; declaring explicit handlers per loop is optional follow-on.

## Impact

- **Priority**: P2 — this is a correctness problem in the verification layer, which makes it quieter and more corrosive than a normal bug: the failure mode is a *wrong verdict that looks right*, recorded in history and acted on. Not P1 because the incorrect verdicts are not known to be frequent and nothing is currently blocked on it; not P3 because every downstream quality signal inherits the noise.
- **Effort**: Medium — the FSM routing is nearly free (`extra_routes` already handles `on_cannot_judge` via `fsm/schema.py:866`), and the enum addition is small. The work concentrates in: the two coercion blockers (AC10 evidence exemption, AC11 prompt-contract rewrite), the shared vocabulary constant (AC8, touching three schemas), the abstention-hold cap (AC7), and the persistence/query layer with its v41 migration (AC4). Down from Large once ENH-3200 was split out.
- **Risk**: Medium, with two distinct failure modes.
  - **Silent no-op (AC10/AC11).** The likeliest failure is that this ships and does nothing: the evidence coercion at `evaluators.py:1256-1258` rewrites every evidence-free `cannot_judge` to `no`, and *three separate prompt texts* tell judges that missing evidence **is** No — including one inside `DEFAULT_LLM_SCHEMA` itself and one baked into every generated verify loop. All four must land with the enum addition. A test that only asserts the enum accepts `cannot_judge` will pass while the end-to-end path still emits `no` — the coverage has to run through `evaluate_llm_structured()`, not the schema. Note the failure is *partial-by-path*: fixing sites 1 and 2 but not `scaffold_verify.py` yields a feature that works in FSM predicates and is dead in verify-issue-loop, which is harder to notice than a total no-op.
  - **Silent regression (AC6).** Adding a fifth enum member means judges can emit a verdict existing loops have no route for, and `_route()` returning `None` terminates the run via `_finish("error", error="No valid transition")` (`executor.py:768`). Because every local-editable project on this machine runs off this working tree, that regression would land silently and everywhere at once. The `on_error` fallback plus its no-regression tests — **on both `_route()` paths**, shorthand and route-table — is the mitigation and must land in the same change as the enum addition, never after it.
  - Secondary: an unbounded hold (AC7) turns an always-abstaining judge into a non-terminating loop.
- **Breaking Change**: No, given AC6. Without AC6 it would be a silent breaking change to every existing loop.

## Session Log
- Pre-implementation review (second pass) - 2026-08-15 - expanded AC11 from one coercion site to three: added `DEFAULT_LLM_SCHEMA`'s `evidence` field description (`evaluators.py:96-99`, ships inside the schema the judge is given) and `scaffold_verify.py:73`'s generated eval prompt (kills the feature in verify-issue-loop specifically). Added a test requirement so a fourth site fails loudly. Restated the Risk section's silent-no-op mode as partial-by-path.
- `/ll:confidence-check` - 2026-08-15T20:36:42 - `4eb27027-e6df-4ea9-a6cc-2ca5e6e40c15.jsonl`
- `/ll:refine-issue` - 2026-08-15T19:49:31 - `4eb27027-e6df-4ea9-a6cc-2ca5e6e40c15.jsonl`
- Scope split to ENH-3200; review edits - 2026-08-15
- Cross-refs updated after ENH-3200 was rescoped away from the multi-check block - 2026-08-15
- Pre-implementation review - 2026-08-15 - added AC10 (evidence-coercion exemption), AC11 (prompt-contract rewrite), AC12 (`uncertain_suffix` interaction); expanded AC6 to cover the `route:`-table path and its `default:` absorption; gave AC9 concrete exit codes (`3` for inconclusive; `2` already taken by infra errors); restated Risk around the silent-no-op failure mode.

## Status

**Open** | Created: 2026-08-15 | Priority: P2
