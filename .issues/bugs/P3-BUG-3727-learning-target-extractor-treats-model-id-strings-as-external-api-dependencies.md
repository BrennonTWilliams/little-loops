---
id: BUG-3727
type: BUG
title: learning-target extractor treats Claude model-ID strings as external-API dependencies
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T17:31:16Z'
completed_at: '2026-10-04T19:21:31Z'
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3727: learning-target extractor treats Claude model-ID strings as external-API dependencies

## Summary

`extract_learning_targets()` (`scripts/little_loops/learning_tests/extractor.py`) asks an LLM to list external dependencies from issue prose. It returned `claude-sonnet-5-5` for BUG-3726, where the model ID only names the model used in a live evaluation. `/ll:explore-api` then wrote a `refuted` record (the installed SDK's `Model` literal lacks the ID; no auth for a live call), and `ll-auto` reported "Learning gate blocked: unproven external-API deps".

Proposed: add a deterministic post-filter (like `_STDLIB_EXCLUDED`) that drops targets matching Claude model-ID shapes while keeping Claude-named products (`claude-code`, `claude-code-stream-json`, `claude-agent-sdk`), and tighten the prompt (and the two prose extraction paths that write `learning_tests_required` before `ll-auto` runs) to exclude model names used as test fixtures or evaluation subjects. Non-Claude model IDs (`gpt-4o`, `gemini-2.5-pro`, `glm-5`) are out of scope — see Scope Boundaries.

Related: the frontmatter `learning_tests_required: []` escape hatch was broken because `IssueParser` collapsed `[]` to `None`; fixed alongside this issue's filing.


## Steps to Reproduce

1. Take an issue whose prose names a Claude model ID only as an evaluation subject or test fixture (e.g. BUG-3726 mentions `claude-sonnet-5-5` as the model used in a live evaluation).
2. Run `extract_learning_targets(issue_text)` (or `ll-auto` on that issue, which calls `resolve_learning_targets` when `learning_tests_required` is unset).
3. Observe: the returned list contains `claude-sonnet-5-5`; `/ll:explore-api` writes a `refuted` record for it and `ll-auto` reports "Learning gate blocked: unproven external-API deps".

## Current Behavior

`extract_learning_targets()` forwards whatever the LLM returns in `TARGETS_JSON`. Its only deterministic filter is `_STDLIB_EXCLUDED` (stdlib module names), so model-ID strings pass through as external-API dependencies. The gate then blocks the issue because the "dependency" can never be proven: the installed SDK's `Model` literal lacks the ID and no auth is available for a live call.

## Expected Behavior

Claude model-ID strings (e.g. `claude-sonnet-5-5`, including provider-prefixed and case-varied spellings) are never returned as learning targets, whether or not the LLM lists them; Claude-named products such as `claude-code` and `claude-code-stream-json` still are. The extraction prompt also tells the LLM to exclude model names used as test fixtures or evaluation subjects. Issues that mention a model ID only as an evaluation subject pass the learning gate without a `refuted` record (an all-dropped response returns `[]`, so the gate is skipped).

## Proposed Solution

In `extract_learning_targets()`, add a deterministic post-filter next to the `_STDLIB_EXCLUDED` check that drops names for which `_is_model_id(name)` is true, logging `logger.debug("extract_learning_targets: dropped model-id target %r", name)` like the stdlib branch. Match on the stripped original `name` before `slugify` (which strips dots).

The pattern must **not** be the broad `^claude-[a-z0-9.-]+$` — it would drop proven registry targets `claude-code`, `claude-code-stream-json`, `claude`, and plausible package `claude-agent-sdk`. Use a digit-keyed pattern with a product-name lookahead and optional provider prefix (decided via `/ll:advise` with Opus, 2026-10-04):

```python
_MODEL_ID_RE = re.compile(
    r"^(?:(?:[a-z]{2,4}\.)?anthropic[./])?claude-(?!(?:code|agent|cli|plugin)\b)(?:\d|[a-z]+-\d)",
    re.IGNORECASE,
)
```

Verified against: drops `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-4-5-20251001`, `claude-fable-5-1`, `claude-3-5-sonnet-20241022`, `claude-instant-1.2`, `claude-sonnet-4.5`, `Claude-Sonnet-5-5`, `anthropic/claude-sonnet-5-5`, `us.anthropic.claude-sonnet-5-5-v1:0`, `claude-sonnet-5-5@20250101`; keeps `claude-code`, `claude-code-stream-json`, `claude-code-2`, `claude-agent-sdk`, `claude-agent-sdk-0.1`, `claude`, `Claude Code CLI`. Digit-keyed (not family-keyed) so new family names (e.g. `fable`) need no code change; the `(code|agent|cli|plugin)` product list is the one place that needs manual upkeep if Anthropic ships another `claude-<word>-<digit>` product.

Tighten `_EXTRACTION_PROMPT` to exclude model names used as test fixtures or evaluation subjects, and add a comment above `_MODEL_ID_RE` recording why prompt wording alone is insufficient (as `_STDLIB_EXCLUDED` does for ENH-2843).

**Decided scope**
- **Field-first path stays unfiltered, deliberately.** `learning_tests_required` entries in frontmatter are returned verbatim by `resolve_learning_targets` / `worker_pool`: it is the escape hatch for issues whose real dependency is a model ID. Document this in the Resolution.
- **Prose paths in scope:** `commands/refine-issue.md` Step 7.5 and `skills/wire-issue/learning-targets.md` get the same exclusion wording, because they write `learning_tests_required` before `ll-auto` runs — without them the bug recurs for already-refined issues. Regenerate host mirrors.
- **Deferred:** `skills/scope-epic/SKILL.md` and `skills/confidence-check/SKILL.md` (499/500 lines) — follow-up.

## Acceptance Criteria

- [x] `extract_learning_targets` drops `claude-sonnet-5-5`, `claude-opus-5-5`, and `claude-haiku-4-5-20251001` when the injected `llm_call` returns them in `targets`
- [x] Provider-prefixed, case-varied and dotted spellings are also dropped (`anthropic/claude-sonnet-5-5`, `us.anthropic.claude-sonnet-5-5-v1:0`, `Claude-Sonnet-5-5`, `claude-sonnet-4.5`)
- [x] Claude-named products are still returned: `claude-code` and `claude-code-stream-json` (proven `.ll/learning-tests/` registry targets), `claude-code-2`, `claude-agent-sdk`, and `Claude Code CLI`, verified by regression tests in `scripts/tests/test_learning_tests_extractor.py`
- [x] Real SDK/package targets (`anthropic`, `requests`) in the same response are still returned, in order
- [x] A response containing only model IDs returns `[]`
- [x] `_EXTRACTION_PROMPT` states that model IDs used as fixtures or evaluation subjects are not dependencies (substring-asserted in a test)
- [x] `commands/refine-issue.md` Step 7.5 and `skills/wire-issue/learning-targets.md` carry the same exclusion; host mirrors regenerated and mirror/audience/line-limit gates pass
- [x] The field-first `learning_tests_required` passthrough is unchanged (a model ID declared in frontmatter is returned verbatim) and this is documented in the Resolution
- [x] Regression tests pass via `python -m pytest scripts/tests/`

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/learning_tests/extractor.py` — `extract_learning_targets()` filter loop and `_EXTRACTION_PROMPT`; the single choke point for all three runners below.
- `scripts/tests/test_learning_tests_extractor.py` — `TestExtractLearningTargets` holds the stdlib-filter contract and the `_make_llm(response)` injection helper.

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/learning_tests/extractor.py:267` — `resolve_learning_targets()` calls `extract_learning_targets()` only when `issue.learning_tests_required is None`.
- `scripts/little_loops/issue_manager.py:46` — imports `resolve_learning_targets`; ll-auto gate emits "Learning gate blocked" on verdict `blocked`.
- `scripts/little_loops/cli/sprint/run.py` — `_run_learning_gate_preflight()` calls `resolve_learning_targets(info)` and unions targets by exact string.
- `scripts/little_loops/parallel/worker_pool.py:85` — `_run_per_worktree_proof_first_gate()` calls `extract_learning_targets()` directly (function-local import); a fix inside the extractor covers all three runners.

**Conventions in Force**
- Deterministic filter backs the prompt exclusion, and a comment above the constant records why prompt wording alone was insufficient — evidence: `_STDLIB_EXCLUDED` and its comment block (ENH-2843, `extractor.py:68-73`).
- Module-level compiled regexes are private `_UPPER_SNAKE`, usually `_RE`-suffixed, placed after the string constant they relate to — evidence: `_TARGETS_JSON_RE` (`extractor.py:66`), `_CREDENTIAL_SHAPE_RE` (`host_runner.py`, passes `re.IGNORECASE` with an explanatory comment).
- Filter-drop branch logs `logger.debug("extract_learning_targets: dropped <kind> target %r", name)` then `continue`, before `slugify` dedup — evidence: `extractor.py:236-238`.
- Filter tests are one undecorated method per case, named `test_drops_*` / `test_keeps_*`, injecting `llm_call=_make_llm('TARGETS_JSON:{...}')` and asserting only on the returned list — evidence: `test_learning_tests_extractor.py:102-134`.
- Elsewhere in `scripts/little_loops/` model IDs are matched by table lookup (`host_runner.MODEL_ALIASES`, `pricing.MODEL_PRICING`, `context_window.MODEL_CONTEXT_WINDOW`), never by regex; no existing model-ID regex exists to reuse.

**Constraints the fix must respect**
- **Collision with real registry targets**: `.ll/learning-tests/claude-code.md` (`target: claude-code`, `proven`) and `claude-code-stream-json.md` exist and match the issue's example `^claude-[a-z0-9.-]+$`. A broad `claude-*` pattern would silently drop those legitimate host-CLI targets. Free-text targets such as `Claude Code CLI` contain spaces and are unaffected. `claude-agent-sdk` also matches the shape and is a plausible real package name (appears only in `docs/claude-code/structured-outputs.md`).
- **`slugify` strips dots** (`claude-sonnet-4.5` → `claude-sonnet-45`), so the match must run on the stripped original `name`, before dedup; the stdlib check lowercases but the loop does not, so the model-ID match needs its own case handling.
- **Field-first path is unfiltered**: `resolve_learning_targets()` and `worker_pool.py` return `learning_tests_required` verbatim when non-`None`; a filter in the extractor does not clean a model ID already written to frontmatter.
- **Prose-only duplicates of the extraction rules** bypass the Python entirely and have no code filter: `commands/refine-issue.md` Step 7.5, `skills/wire-issue/learning-targets.md` (Phase 9.5), `skills/scope-epic/SKILL.md` Phase 2 ("same inclusion/exclusion rules as `extract_learning_targets()`"). These write `learning_tests_required` directly, so a model ID they emit is never seen by the extractor filter. Editing `skills/` or `commands/` trips the mirror gates (see memory: `ll-adapt --host <gemini|kimi-code|qwen> --apply`).
- `gate.py:85` has a second, case-sensitive stdlib filter (`sys.stdlib_module_names`) on the gate side; it is not the model-ID path.

**Tests**
- `scripts/tests/test_learning_tests_extractor.py` — existing contract (`test_keeps_third_party_target`, `test_keeps_phrase_target_with_no_dot`) must keep passing. No existing test asserts prompt wording or debug-log output (`caplog` unused in `test_learning_tests*.py`).
- `scripts/tests/test_worker_pool.py` (lines ~3866-3932) and `scripts/tests/test_sprint_integration.py:~2106` patch `little_loops.learning_tests.extractor.extract_learning_targets` by dotted path — unaffected by internal filter changes.

**Documentation**
- `docs/guides/LEARNING_TESTS_GUIDE.md` and `docs/reference/API.md` (`### resolve_learning_targets`) describe extraction; check whether either enumerates exclusions.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:1200` — `resolve_learning_targets(info)` inside the learning-gate block (`if config.learning_tests.enabled is True and not dry_run:`), guarded by `if targets:` — if the filter drops every target the gate is skipped (no fallback into `run_learning_gate_for_issue`), which is the intended fix outcome; no edit needed [Agent 1 finding]
- `scripts/little_loops/learning_tests/gate.py:run_learning_gate_for_issue` — receives the already-resolved `targets` and joins them into `--context targets=a,b` with no filtering of its own; no edit needed, but note a model ID in frontmatter `learning_tests_required` still reaches it [Agent 2 finding]
- `scripts/little_loops/fsm/executor.py:_execute_learning_state` / `_learning_remedy_state` — builds `/ll:explore-api <target>` from `state.learning.targets` / `targets_csv` unfiltered; downstream of the extractor, not changed by this fix [Agent 2 finding]
- `scripts/little_loops/loops/assumption-firewall.yaml` (state `extract_assumptions`) — separate LLM extraction prompt with no model-ID exclusion; reached via `proof-first-task` when `targets` is empty. Out of scope for this fix; a model ID can still surface here [Agent 2 finding]
- `scripts/little_loops/loops/rn-implement.yaml` (`check_learning_ready`, ~L543/L555/L640/L1136) and `rn-remediate.yaml` (~L584) — read `learning_tests_required` from frontmatter directly and never call the extractor, so the Python filter does not cover them [Agent 1 + 2 finding]
- `scripts/little_loops/issue_parser.py:~4248` — comment documents that `[]` vs `None` governs JIT extraction in `resolve_learning_targets`; unaffected [Agent 1 finding]

### Files to Modify (prose duplicates — `refine-issue` and `wire-issue` in scope; `scope-epic` and `confidence-check` deferred)

_Wiring pass added by `/ll:wire-issue`:_
- `skills/confidence-check/SKILL.md:474` — "External-API note" paragraph says its exclusion heuristic is "mirrored from `learning_tests/extractor.py:_EXTRACTION_PROMPT`"; a fourth prose restatement of the rules (the other three are already listed above). **File is 499/500 lines** (`TestSkillLineLimit`) — extend the existing line in place, do not add a new line more than once [Agent 2 finding]
- `skills/scope-epic/SKILL.md` — note the correct anchor is `### Phase 2.5: Learning Test Detection`, `#### Step 1` (the "Phase 2" label above is imprecise); Exclude bullet at ~L167-170 [Agent 2 finding]
- Host mirrors that go stale if any of `commands/refine-issue.md`, `skills/wire-issue/learning-targets.md`, `skills/scope-epic/SKILL.md`, `skills/confidence-check/SKILL.md` is edited: `.gemini/skills/{wire-issue/learning-targets.md,scope-epic/SKILL.md,confidence-check/SKILL.md}`, `.kimi-code/skills/…` (same three plus `.kimi-code/skills/ll-refine-issue/SKILL.md`), `.qwen/skills/…` (same three plus `.qwen/commands/ll/refine-issue.md`), `.gemini/commands/refine-issue.toml` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` (codex/omp are also in `GATED_HOSTS`; include them if the gate reports drift) [Agent 1 + 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_tests_extractor.py::TestExtractLearningTargets` — new tests go after `test_keeps_phrase_target_with_no_dot` (before `_make_issue_stub`): `test_drops_model_id_targets` (three AC IDs → `[]`), `test_keeps_sdk_targets_alongside_model_ids` (`anthropic`, `requests` returned in order), `test_keeps_claude_code_registry_targets` (`claude-code`, `claude-code-stream-json` kept), plus optional case-insensitive (`Claude-Sonnet-5-5`) and dotted-ID (`claude-sonnet-4.5`) cases [Agent 3 finding]
- `scripts/tests/test_learning_tests_extractor.py::test_mock_injection_receives_prompt_with_issue_text` — extend (or add a sibling) with a substring assertion on the captured prompt for the new model-ID exclusion wording; no existing test asserts `_EXTRACTION_PROMPT` wording. Alternative idiom: `TestFinalizeRetryPrompt` in `test_issue_manager.py` (substring asserts on a module constant, `.lower()` for keywords) [Agent 3 finding]
- `scripts/tests/test_learning_tests_extractor.py` — optional debug-log test via `caplog.at_level(logging.DEBUG, logger="little_loops.learning_tests.extractor")` following `test_session_store_writers.py:571`; `caplog` is unused in `test_learning_tests*.py` today [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` and `::test_skill_mirrors_carry_companions` — will fail if any prose duplicate above is edited without regenerating the `.gemini`/`.kimi-code`/`.qwen` mirrors [Agent 2 + 3 finding]
- `scripts/tests/test_enh494_skill_companions.py::TestSkillLineLimit` — 500-line cap; `skills/confidence-check/SKILL.md` is at 499 [Agent 2 finding]
- `scripts/tests/test_refine_issue_command.py` — slices `commands/refine-issue.md` by the `### 7.5. Extract Learning Targets` heading; edit inside Step 7.5 only, do not rename/move the heading [Agent 3 finding]
- No existing test is expected to break: `test_worker_pool.py` and `test_sprint_integration.py` stub the extractor by dotted path; `TestResolveLearningTargets::test_none_field_triggers_jit_extraction` and `TestDefaultLlmCall::test_end_to_end_extraction_via_default_path` return `anthropic`/`requests` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- No doc enumerates the extraction exclusions or `_STDLIB_EXCLUDED`: `docs/guides/LEARNING_TESTS_GUIDE.md` (JIT path described only as "extracts targets from the issue text via LLM") and `docs/reference/API.md` (`### resolve_learning_targets`) stay accurate — no edit required [Agent 2 finding]
- `CHANGELOG.md` — ENH-2843 is the only precedent; per repo convention add the entry under a concrete `## [X.Y.Z]` section during release prep, not `[Unreleased]` [Agent 2 finding]
- Any new prose about the filter in `skills/` or `commands/` must satisfy `scripts/tests/test_docs_audience_gate.py`: cite `little_loops.learning_tests.extractor` as a dotted module, no `scripts/little_loops/` or `scripts/tests/` paths [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (`learning_tests` block, ~L1233) — no extraction/model-ID setting; decision records `.ll/decisions.d/1f682ece-…json` and `3f26b4ad-…json` establish that `_STDLIB_EXCLUDED` is intentionally hardcoded with no config surface, so `_MODEL_ID_RE` should follow suit — no schema edit [Agent 1 finding]

## Program Design

### Types

- `_MODEL_ID_RE: re.Pattern[str]` — module-level compiled pattern for Claude model-ID strings (digit-keyed, product-name lookahead, optional provider prefix)

### Signatures

- `_is_model_id(name: str) -> bool` — new private helper; `bool(_MODEL_ID_RE.match(name))`
- `extract_learning_targets(issue_text: str, *, llm_call: Callable[[str], str] | None = None) -> list[str]` — existing; gains the model-ID drop

### Call Path

`resolve_learning_targets` -> `extract_learning_targets` -> `_is_model_id`

`_run_per_worktree_proof_first_gate` -> `extract_learning_targets` -> `_is_model_id`

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

1. Add `_MODEL_ID_RE` / `_is_model_id` (pattern in Proposed Solution) and the drop branch in `extract_learning_targets()`, matched on the stripped original name before `slugify` dedup, so Claude model IDs never leave it while `claude-code` and `claude-code-stream-json` (proven host-CLI registry targets) are still returned.
2. `_EXTRACTION_PROMPT` states that model IDs used as fixtures or evaluation subjects are not dependencies, and the module comment records why the prompt alone is insufficient (as `_STDLIB_EXCLUDED` does for ENH-2843).
3. Filter coverage lives in `TestExtractLearningTargets` beside the stdlib cases: the three AC model IDs dropped, `anthropic`/`requests` kept, and a `claude-code` keep case guarding the collision. Verify with `python -m pytest scripts/tests/test_learning_tests_extractor.py -v`, then the full `python -m pytest scripts/tests/`.
4. Add the same exclusion wording to `commands/refine-issue.md` Step 7.5 and `skills/wire-issue/learning-targets.md` (decided: in scope). `skills/scope-epic/SKILL.md` and `skills/confidence-check/SKILL.md` are deferred to a follow-up. Re-sync the `skills/`/`commands/` mirrors.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Edit `_EXTRACTION_PROMPT` in `extractor.py` with care: it is rendered with `.format(issue_text=...)`, so any literal `{` or `}` in the new exclusion sentence must be doubled (`{{`/`}}`), as the existing `TARGETS_JSON` example lines are
- Add the new `TestExtractLearningTargets` tests (drop AC model IDs; drop prefixed/case/dotted spellings; keep `anthropic`/`requests` in order; keep `claude-code`/`claude-code-stream-json`/`claude-code-2`/`claude-agent-sdk`/`Claude Code CLI`; all-dropped → `[]`) in `scripts/tests/test_learning_tests_extractor.py` after `test_keeps_phrase_target_with_no_dot`
- Add a prompt-wording assertion in `scripts/tests/test_learning_tests_extractor.py` (extend `test_mock_injection_receives_prompt_with_issue_text` or add a sibling) so the exclusion sentence is regression-guarded
- Mirror the exclusion into prose: edit inside `commands/refine-issue.md` Step 7.5 without renaming its heading and in `skills/wire-issue/learning-targets.md` (leave `skills/confidence-check/SKILL.md` untouched — 499/500 lines, deferred), then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` and re-run `test_wiring_skills_and_commands.py`, `test_enh494_skill_companions.py`, `test_refine_issue_command.py`, `test_docs_audience_gate.py`
- Add a field-first passthrough test (a frontmatter `learning_tests_required: [claude-sonnet-5-5]` is returned verbatim by `resolve_learning_targets`)
- Record in the Resolution: the field-first path is deliberately unfiltered (escape hatch); `rn-implement.yaml`, `rn-remediate.yaml`, `assumption-firewall.yaml`'s own extraction, `scope-epic`/`confidence-check` prose, prose model names ("Claude Sonnet 5.5", prompt-only) and bare aliases (`opus`/`sonnet`) are not covered by the Python filter

## Impact

- **Priority**: P3 - false-positive gate block on issues merely mentioning a model ID; workaround exists (`learning_tests_required: []`)
- **Effort**: Small/Medium - one regex + helper, one filter branch, a prompt sentence, two prose edits with mirror regeneration, and a few tests
- **Risk**: Low - the filter only removes Claude model-ID-shaped names; product names (`claude-code*`, `claude-agent-*`, `claude-cli*`, `claude-plugin*`) are kept by the lookahead. The product list needs manual upkeep if a new `claude-<word>-<digit>` product ships
- **Breaking Change**: No

## Scope Boundaries

- **In scope:** Claude model-ID filter (incl. provider-prefixed forms) in `extract_learning_targets`, prompt exclusion, same exclusion in `commands/refine-issue.md` Step 7.5 and `skills/wire-issue/learning-targets.md`, tests, mirror regeneration.
- **Out of scope / follow-up:** non-Claude model IDs (`gpt-4o`, `gemini-2.5-pro`, `glm-5` — the registry already holds gemini/codex/kimi/qwen/pi/omp host targets, so they need their own evidence-based decision); `scope-epic` and `confidence-check` prose; filtering the field-first `learning_tests_required` path (deliberate escape hatch); `assumption-firewall.yaml`, `rn-implement.yaml`, `rn-remediate.yaml`; deterministic handling of prose names and bare aliases.

## Review Notes

Revised 2026-10-04 after pre-implementation review and `/ll:advise` with Opus: replaced the broad `^claude-[a-z0-9.-]+$` (which dropped proven `claude-code*` registry targets) with a digit-keyed pattern plus product-name lookahead and provider prefix; retitled to Claude-only; added keep/drop ACs; brought `refine-issue` and `wire-issue` prose into scope; documented the field-first path as a deliberate escape hatch.

## Status

**Open** | Created: 2026-10-04 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-10-04T19:21:31 - `80eba000-6032-41ce-81d8-5ec41e6f7753.jsonl`
- `/ll:ready-issue` - 2026-10-04T19:12:19 - `9e9543bf-5bbb-4377-a975-3dce9df01352.jsonl`
- `/ll:confidence-check` - 2026-10-04T18:47:11 - `4fcf50ed-e004-47d9-8a3c-f07dc1efb8ee.jsonl`
- `/ll:wire-issue` - 2026-10-04T18:36:53 - `6edca675-5538-495d-a946-19c5b2740bca.jsonl`
- `/ll:refine-issue` - 2026-10-04T18:29:46 - `4675b499-1b8e-4fd9-8d9d-6cf940665b02.jsonl`
- `/ll:format-issue` - 2026-10-04T18:25:17 - `b5215a77-b6b8-4e61-a154-08e850354e78.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **File**: `scripts/little_loops/learning_tests/extractor.py`
- **Anchor**: `in function extract_learning_targets()` (per-target filter loop)
- **Cause**: The loop's only deterministic filter is `name.split(".", 1)[0].lower() in _STDLIB_EXCLUDED`; everything else the LLM returns in `TARGETS_JSON` is deduped by `slugify()` and returned. `_EXTRACTION_PROMPT`'s `Include:` list ("External APIs and services", "SDKs for external platforms") has no exclusion for model names, so a model ID used as an evaluation subject is listed as a service.
- **Downstream effect**: `executor.py:_execute_learning_state` resolves each target to `.ll/learning-tests/<slugify(target)>.md`; a missing record triggers `/ll:explore-api <target>`, which can only write `refuted` for a model ID, routing to `on_blocked` → `ready-to-implement-gate` `blocked` terminal → `issue_manager.py` "Learning gate blocked: unproven external-API deps".

## Resolution

**Fixed** — 2026-10-04

- `extractor.py`: added `_MODEL_ID_RE` / `_is_model_id()` (digit-keyed, `code|agent|cli|plugin` product lookahead, optional `anthropic/` / `us.anthropic.` prefix) and a drop branch in `extract_learning_targets()` before `slugify` dedup; `_EXTRACTION_PROMPT` now excludes model IDs used as fixtures or evaluation subjects.
- Same exclusion wording added to `commands/refine-issue.md` Step 7.5 and `skills/wire-issue/learning-targets.md`; `.gemini`/`.kimi-code`/`.qwen` mirrors regenerated with `ll-adapt`.
- Tests: 5 new `TestExtractLearningTargets` cases (drop, drop prefixed/cased/dotted, keep SDKs alongside, keep Claude products, prompt wording) plus a field-first passthrough test. Full suite: 27855 passed; ruff + mypy clean.
- **Deliberate non-coverage**: the field-first `learning_tests_required` path stays unfiltered (escape hatch for issues whose real dependency is a model ID). Not covered by the Python filter: `rn-implement.yaml`, `rn-remediate.yaml`, `assumption-firewall.yaml`'s own extraction, `scope-epic`/`confidence-check` prose (follow-up), prose model names ("Claude Sonnet 5.5"), bare aliases (`opus`/`sonnet`), and non-Claude model IDs.
