---
id: BUG-3727
type: BUG
title: learning-target extractor treats model-ID strings as external-API dependencies
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T17:31:16Z'
---

# BUG-3727: learning-target extractor treats model-ID strings as external-API dependencies

## Summary

`extract_learning_targets()` (`scripts/little_loops/learning_tests/extractor.py`) asks an LLM to list external dependencies from issue prose. It returned `claude-sonnet-5-5` for BUG-3726, where the model ID only names the model used in a live evaluation. `/ll:explore-api` then wrote a `refuted` record (the installed SDK's `Model` literal lacks the ID; no auth for a live call), and `ll-auto` reported "Learning gate blocked: unproven external-API deps".

Proposed: add a deterministic post-filter (like `_STDLIB_EXCLUDED`) that drops targets matching Claude/other model-ID patterns (e.g. `^claude-[a-z0-9.-]+$`), and tighten the prompt to exclude model names used as test fixtures or evaluation subjects.

Related: the frontmatter `learning_tests_required: []` escape hatch was broken because `IssueParser` collapsed `[]` to `None`; fixed alongside this issue's filing.


## Steps to Reproduce

1. Take an issue whose prose names a Claude model ID only as an evaluation subject or test fixture (e.g. BUG-3726 mentions `claude-sonnet-5-5` as the model used in a live evaluation).
2. Run `extract_learning_targets(issue_text)` (or `ll-auto` on that issue, which calls `resolve_learning_targets` when `learning_tests_required` is unset).
3. Observe: the returned list contains `claude-sonnet-5-5`; `/ll:explore-api` writes a `refuted` record for it and `ll-auto` reports "Learning gate blocked: unproven external-API deps".

## Current Behavior

`extract_learning_targets()` forwards whatever the LLM returns in `TARGETS_JSON`. Its only deterministic filter is `_STDLIB_EXCLUDED` (stdlib module names), so model-ID strings pass through as external-API dependencies. The gate then blocks the issue because the "dependency" can never be proven: the installed SDK's `Model` literal lacks the ID and no auth is available for a live call.

## Expected Behavior

Model-ID strings (e.g. `claude-sonnet-5-5`) are never returned as learning targets, whether or not the LLM lists them. The extraction prompt also tells the LLM to exclude model names used as test fixtures or evaluation subjects. Issues that mention a model ID only as an evaluation subject pass the learning gate without a `refuted` record.

## Proposed Solution

In `extract_learning_targets()`, add a deterministic post-filter next to the `_STDLIB_EXCLUDED` check that drops names matching a compiled `_MODEL_ID_RE` (e.g. `^claude-[a-z0-9.-]+$`, case-insensitive), logging a debug line like the stdlib branch. Tighten `_EXTRACTION_PROMPT` to exclude model names used as test fixtures or evaluation subjects.

## Acceptance Criteria

- [ ] `extract_learning_targets` drops `claude-sonnet-5-5`, `claude-opus-5-5`, and `claude-haiku-4-5-20251001` when the injected `llm_call` returns them in `targets`
- [ ] Real SDK/package targets (`anthropic`, `requests`) in the same response are still returned
- [ ] `_EXTRACTION_PROMPT` states that model IDs used as fixtures or evaluation subjects are not dependencies
- [ ] Regression tests in `scripts/tests/test_learning_tests_extractor.py` cover the filter and pass via `python -m pytest scripts/tests/`

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

## Program Design

### Types

- `_MODEL_ID_RE: re.Pattern[str]` — module-level compiled pattern for model-ID strings

### Signatures

- `extract_learning_targets(issue_text: str, *, llm_call: Callable[[str], str] | None = None) -> list[str]` — existing; gains the model-ID drop

### Call Path

`resolve_learning_targets` -> `extract_learning_targets` -> `_MODEL_ID_RE.match`

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

1. Model-ID strings never leave `extract_learning_targets()`, matched on the stripped original name before `slugify` dedup, while `claude-code` and `claude-code-stream-json` (proven host-CLI registry targets) are still returned. The pattern's scope must be chosen against that collision — `^claude-[a-z0-9.-]+$` as written in the Proposed Solution does not satisfy it.
2. `_EXTRACTION_PROMPT` states that model IDs used as fixtures or evaluation subjects are not dependencies, and the module comment records why the prompt alone is insufficient (as `_STDLIB_EXCLUDED` does for ENH-2843).
3. Filter coverage lives in `TestExtractLearningTargets` beside the stdlib cases: the three AC model IDs dropped, `anthropic`/`requests` kept, and a `claude-code` keep case guarding the collision. Verify with `python -m pytest scripts/tests/test_learning_tests_extractor.py -v`, then the full `python -m pytest scripts/tests/`.
4. Decide knowingly whether the prose-only extraction paths (`commands/refine-issue.md` Step 7.5, `skills/wire-issue/learning-targets.md`, `skills/scope-epic/SKILL.md`) get the same exclusion wording; they bypass the Python filter. If edited, the `skills/`/`commands/` mirror gates must be re-synced.

## Impact

- **Priority**: P3 - false-positive gate block on issues merely mentioning a model ID; workaround exists (`learning_tests_required: []`)
- **Effort**: Small - one regex, one filter branch, a prompt sentence, and a few tests
- **Risk**: Low - the filter only removes `claude-*`-shaped names from the returned list
- **Breaking Change**: No

## Status

**Open** | Created: 2026-10-04 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-10-04T18:29:46 - `4675b499-1b8e-4fd9-8d9d-6cf940665b02.jsonl`
- `/ll:format-issue` - 2026-10-04T18:25:17 - `b5215a77-b6b8-4e61-a154-08e850354e78.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-04 — based on codebase analysis:_

- **File**: `scripts/little_loops/learning_tests/extractor.py`
- **Anchor**: `in function extract_learning_targets()` (per-target filter loop)
- **Cause**: The loop's only deterministic filter is `name.split(".", 1)[0].lower() in _STDLIB_EXCLUDED`; everything else the LLM returns in `TARGETS_JSON` is deduped by `slugify()` and returned. `_EXTRACTION_PROMPT`'s `Include:` list ("External APIs and services", "SDKs for external platforms") has no exclusion for model names, so a model ID used as an evaluation subject is listed as a service.
- **Downstream effect**: `executor.py:_execute_learning_state` resolves each target to `.ll/learning-tests/<slugify(target)>.md`; a missing record triggers `/ll:explore-api <target>`, which can only write `refuted` for a model ID, routing to `on_blocked` → `ready-to-implement-gate` `blocked` terminal → `issue_manager.py` "Learning gate blocked: unproven external-API deps".
