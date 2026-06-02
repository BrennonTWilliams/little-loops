---
id: FEAT-1692
type: FEAT
priority: P3
status: done
captured_at: '2026-05-25T20:34:52Z'
completed_at: '2026-05-27T06:38:33Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- FEAT-1287
- FEAT-1283
- FEAT-1282
- EPIC-1663
- EPIC-1694
- FEAT-1695
- FEAT-1696
- FEAT-1697
decision_needed: false
confidence_score: 94
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1692: `integrate-sdk` FSM loop — proof-driven SDK integration

## Summary

Add an `integrate-sdk` FSM loop (`{{config.loops.loops_dir}}/integrate-sdk.yaml`) that, given an SDK/library name and a stated integration goal, branches between scanning existing usage (if any) or generating hypotheses from vendor docs, runs the Learning Test cycle (`type: learning`) against every required surface, and **only then** scaffolds integration code into the project. If the learning gate refutes the target hypotheses, the loop blocks with a structured diagnosis rather than writing code against unproven assumptions.

The framing is **"prove the SDK against scratch scripts before writing integration code,"** not "scan your existing usage." The codebase scan is an opportunistic bootstrap signal, not the entry point.

## Current Behavior

There is no loop today that wires `/ll:explore-api` (FEAT-1287) and `type: learning` (FEAT-1283) into a guided "integrate this SDK" workflow. When a developer wants to add a new SDK:

- They run `/ll:scrape-docs` manually (if at all).
- They write integration code directly against vendor docs, hallucinating response shapes / streaming semantics / rate-limit behavior.
- They discover divergence only when production code fails.
- The Learning Test Registry exists but is invoked ad-hoc, with no automation tying its outputs to the integration code it should be guarding.

`type: learning` (`scripts/tests/fixtures/fsm/learning-state-loop.yaml`) is a primitive state — there is no canonical loop that composes it with a scaffolding step gated on its result.

## Expected Behavior

Invoke:

```bash
ll-loop run integrate-sdk --target "anthropic-sdk" --goal "streaming completions with tool use"
```

The loop branches:

```
init
  → scan_existing_usage          (shell: grep for SDK imports, count hits)
      on_yes (hits found)  → hypothesize_from_code
      on_no  (greenfield)  → hypothesize_from_docs
                                ├─ ingest_docs (/ll:scrape-docs if not mirrored)
                                └─ enumerate_surfaces (LLM: list methods/endpoints needed for goal)
  → learning_gate                (type: learning; targets = enumerated surfaces)
      on_pass    → scaffold_integration
      on_blocked → diagnose_and_block
```

On `on_pass`, scaffolding writes integration code with `# Verified: .ll/learning-tests/<slug>.md` citations at each call site.

On `on_blocked`, the loop terminates with a structured `diagnose_and_block` artifact (failure mode taxonomy from `loop-specialist` agent) — never writes integration code against refuted assumptions.

## Motivation

- **Compounds existing primitives.** FEAT-1287 (`/ll:explore-api`), FEAT-1283 (`type: learning`), and FEAT-1285/1286 (registry + CLI) are all in place but lack a top-level entry point that turns them into a developer-visible workflow. Without this loop they are infrastructure waiting for callers.
- **Closes the "hallucinated SDK shape" failure mode.** The most expensive integration bugs come from response-shape / streaming-semantics / undocumented-edge-case assumptions written into integration code. A learning gate forces those assumptions into a falsifiable proof script *before* they touch the project.
- **Refuted targets become diagnoses, not bad code.** Today a refutation is silent — the agent retries or moves on. With this loop, refutation is a terminal `on_blocked` transition with a diagnosis artifact the human reviews.
- **Greenfield is the high-value case.** When existing call sites exist, agents can crib. The loop earns its keep on greenfield SDKs where there is no prior usage to model from — exactly where hallucination risk is highest.

## Use Case

A developer is adding the Anthropic Messages API to a project that has never used it before. They run:

```bash
ll-loop run integrate-sdk --target "anthropic" --goal "streaming completions with tool use, surfacing rate-limit headers"
```

The loop:
1. Greps for `import anthropic` / `from anthropic` — finds 0 hits → greenfield branch.
2. Checks `docs/external/anthropic/` for mirrored docs; finds none → invokes `/ll:scrape-docs https://docs.anthropic.com/en/api/messages-streaming`.
3. Enumerates surfaces from docs + goal: `["streaming event shape (MessageStreamEvent types)", "tool_use content blocks", "anthropic-ratelimit-* response headers"]`.
4. Invokes `/ll:explore-api` for each surface; each writes a `LearnTestRecord` to `.ll/learning-tests/`.
5. Two of three pass; one (`tool_use content blocks`) fails because the proof script gets `tool_use` blocks with different shape than hypothesized.
6. Loop terminates `on_blocked` with diagnosis: *"Refuted: tool_use content blocks. Expected `{type, name, input}`; actual `{type, id, name, input}` (extra `id` field). Update hypothesis and rerun, or accept refutation and design integration around the actual shape."*
7. The developer reads the diagnosis, updates the hypothesis, reruns; this time all three pass. Loop transitions to `scaffold_integration`, which writes `src/llm/anthropic_client.py` with `# Verified: .ll/learning-tests/anthropic-streaming.md` citations next to every API call.

The developer never wrote a hallucinated assumption into production code. The proof records remain as living documentation for the next agent that touches this integration.

## Proposed Solution

### Loop YAML (skeleton — `scripts/little_loops/loops/integrate-sdk.yaml`)

```yaml
name: integrate-sdk
description: >
  Proof-driven SDK integration: prove required surfaces via Learning Tests
  before scaffolding any integration code.
inputs:
  target:
    type: string
    required: true
    description: SDK or library name (e.g., "anthropic", "stripe")
  goal:
    type: string
    required: true
    description: What the integration needs to do (e.g., "streaming completions with tool use")
  scaffold_dir:
    type: string
    default: "src/integrations/"

states:
  - name: init
    type: noop
    next: scan_existing_usage

  - name: scan_existing_usage
    type: exit_code
    shell: |
      hits=$(grep -rln "import {{inputs.target}}\|from {{inputs.target}}" --include="*.py" --include="*.ts" --include="*.js" . 2>/dev/null | wc -l)
      echo "$hits"
      [ "$hits" -gt 0 ] && exit 0 || exit 1
    on_exit_0: hypothesize_from_code
    on_exit_1: hypothesize_from_docs

  - name: hypothesize_from_code
    type: llm_structured
    prompt_file: prompts/hypothesize_from_code.md
    schema:
      surfaces: list[str]
    next: learning_gate

  - name: hypothesize_from_docs
    type: llm_structured
    prompt_file: prompts/hypothesize_from_docs.md
    pre_step: ensure_docs_mirrored
    schema:
      surfaces: list[str]
    next: learning_gate

  - name: learning_gate
    type: learning
    targets: "{{state.hypothesize_from_code.surfaces || state.hypothesize_from_docs.surfaces}}"
    on_pass: scaffold_integration
    on_fail: diagnose_and_block

  - name: scaffold_integration
    type: llm_structured
    prompt_file: prompts/scaffold_integration.md
    # Required: every API call site in generated code must include
    # `# Verified: .ll/learning-tests/<slug>.md` citation
    next: verify_scaffold

  - name: verify_scaffold
    # Non-LLM evaluator (meta-loop rule MR-1): citations must resolve
    type: exit_code
    shell: scripts/lib/verify_learning_citations.sh "{{inputs.scaffold_dir}}"
    on_exit_0: done
    on_exit_1: diagnose_and_block

  - name: diagnose_and_block
    type: llm_structured
    prompt_file: prompts/diagnose_and_block.md
    terminal: true
    # Emits a structured failure-mode classification per loop-specialist taxonomy
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical FSM YAML syntax corrections** (the skeleton above uses incorrect syntax that differs from all production loops):

1. **`inputs:` / `{{inputs.xxx}}` is wrong for FSM loops.** That Handlebars syntax belongs to `scripts/little_loops/parallel/tasks/` definitions. FSM loops use `context:` + `${context.xxx}` for parameterization. CLI positional binding uses `input_key:`. Correct form:
   ```yaml
   input_key: target          # binds first CLI positional to context.target
   context:
     target: ""               # required — SDK name (e.g., "anthropic")
     goal: ""                 # required — integration goal
     scaffold_dir: "src/integrations/"
   ```
   All `{{inputs.target}}` etc. in shell actions must be `${context.target}`.

2. **`on_exit_0`/`on_exit_1` are wrong routing keys.** All production loops use `on_yes` (exit 0) / `on_no` (non-zero) with `evaluate: type: exit_code`. The `on_exit_0`/`on_exit_1` key names do not exist in the schema. Example from `scan_existing_usage`:
   ```yaml
   scan_existing_usage:
     action_type: shell
     action: |
       hits=$(grep -rln "import ${context.target}\|from ${context.target}" ...)
       [ "$hits" -gt 0 ] && exit 0 || exit 1
     evaluate:
       type: exit_code
     on_yes: hypothesize_from_code
     on_no: hypothesize_from_docs
   ```

3. **`prompt_file:` is not a valid field inside `evaluate: type: llm_structured`.** The `llm_structured` evaluator takes an inline `prompt:` string and optional `source:` (the text to evaluate). There is no `prompt_file:` field. For `hypothesize_from_code`/`hypothesize_from_docs`, use `action_type: prompt` with an inline `action:` prompt string, plus a `capture:` key to store the surfaces list — not `type: llm_structured`.

4. **`pre_step:` is not a supported FSM hook.** `FSMExecutor` has no pre-state hook; `ensure_docs_mirrored` must be a separate state before `hypothesize_from_docs`, not a `pre_step` annotation.

5. **`terminal: true` states do not execute actions.** `_execute_state` is never reached for terminal states — they immediately call `_finish("terminal")`. The `diagnose_and_block` state cannot be both `terminal: true` and `type: llm_structured`. Correct design: `diagnose_and_block` must be a non-terminal action state (running the diagnosis prompt), followed by a separate `terminal: true` `blocked` state.

6. **`learning_gate` targets cannot be a dynamic `||` expression.** The `learning:` sub-block expects a YAML list, not a jinja expression. To use dynamic surfaces from a prior state, capture that state's output to `context` and inject via `${captured.hypothesize_from_code.output}` — but the FSM interpolation system doesn't splat strings into YAML lists. The practical solution is to write the surface list to a file in the capture step and read it in the `learning_gate` pre-action, or represent them as a newline-delimited `${context.surfaces}` string. See `adopt-third-party-api.yaml` for the production pattern — it uses an `output_json` evaluator to parse the enumeration output before passing it to a sub-loop.

**Closest existing analog:** `scripts/little_loops/loops/adopt-third-party-api.yaml` implements `scrape → enumerate surfaces → prove (sub-loop) → write playbook` — the nearest complete pipeline. Study its state graph before authoring `integrate-sdk.yaml`.

### Meta-loop compliance (CLAUDE.md § Loop Authoring)

This loop **does scaffold project source files**, which puts it at the edge of "meta-loop" territory. Mitigation:

- **MR-1 (non-LLM evaluator on every `check_semantic`):** `verify_scaffold` is `exit_code`, not LLM. The `learning_gate` itself is non-LLM (FSM-driven `type: learning` runs scripts and reads pass/fail from the registry).
- **Diagnosis-first shape:** `scan → hypothesize → learning_gate → scaffold` follows the `diagnose → propose → apply → measure-externally` shape required for meta-loops.
- **Set `meta_self_eval_ok: false`** in the loop top-level (default) — there is no LLM self-grade in the loop.

### When this loop pays off vs. doesn't

**Pays off:**
- SDKs with subtle response shapes (streaming events, polymorphic content blocks, undocumented headers).
- SDKs whose docs lag the implementation.
- Greenfield integrations where there is no prior code to crib from.

**Doesn't pay off — fall back to `/ll:scrape-docs` + manual integration:**
- SDKs requiring paid credentials the agent cannot obtain (the proof script can't run without a real account).
- SDKs whose behavior only manifests in full app context (rare for well-designed SDKs; common for framework-coupled ones).
- Trivial SDKs where reading the README is faster than running a proof.

The loop should detect the first case (auth errors in the proof script) and surface "requires credentials" as a `diagnose_and_block` failure mode rather than retrying indefinitely.

## API/Interface

```bash
# Greenfield
ll-loop run integrate-sdk \
  --target "anthropic" \
  --goal "streaming completions with tool use"

# With existing usage (loop will branch to hypothesize_from_code)
ll-loop run integrate-sdk \
  --target "stripe" \
  --goal "subscription webhooks"

# Override scaffold location
ll-loop run integrate-sdk \
  --target "openai" \
  --goal "embeddings" \
  --scaffold-dir "src/llm/"
```

Outputs:
- `.ll/learning-tests/<target>-<surface-slug>.md` — one `LearnTestRecord` per proven/refuted surface
- `{{scaffold_dir}}/<target>_client.*` — scaffolded integration code with `# Verified:` citations (only on `on_pass`)
- `.loops/runs/integrate-sdk/<ts>/diagnosis.md` — failure-mode diagnosis (only on `on_blocked`)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/integrate-sdk.yaml` — **new** (the loop)
- `scripts/little_loops/loops/prompts/hypothesize_from_code.md` — **new**
- `scripts/little_loops/loops/prompts/hypothesize_from_docs.md` — **new**
- `scripts/little_loops/loops/prompts/scaffold_integration.md` — **new** (must instruct: emit `# Verified:` comments)
- `scripts/little_loops/loops/prompts/diagnose_and_block.md` — **new** (follow `loop-specialist` failure-mode taxonomy)
- `scripts/verify_learning_citations.sh` — **new** (`scripts/lib/` does not exist; place as a standalone script in `scripts/`; model after `hooks/scripts/check-duplicate-issue-id.sh` for null-safe `find -print0 | while IFS= read -r -d ''` traversal; greps scaffolded files for `# Verified:` lines, asserts each cited `.ll/learning-tests/<slug>.md` exists and `status: proven`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/states/learning.py` — `type: learning` state implementation; loop relies on its `on_pass`/`on_fail` transitions (FEAT-1283)
- `skills/explore-api/SKILL.md` — `learning_gate` invokes this skill per surface (FEAT-1287)
- `skills/scrape-docs/SKILL.md` (or `scrape-docs` skill at `~/.claude/skills/`) — `pre_step: ensure_docs_mirrored` invokes this when docs are missing
- `scripts/little_loops/learning_tests.py` — `LearnTestRecord`, `read_record()`, `check_learning_test()` used by `verify_learning_citations.sh`
- `scripts/little_loops/fsm/executor.py` — **actual FSM runtime** (`scripts/little_loops/loops/runner.py` does not exist); `FSMExecutor._execute_learning_state` (lines 602–673) handles `type: learning` dispatch; `FSMExecutor._execute_state` (line 772; learning routing at line 798) routes to it; no changes needed
- `scripts/little_loops/fsm/schema.py` — `LearningConfig` dataclass (lines 271–305) defines `targets: list[str]` and `max_retries: int`; `StateConfig` holds the `learning:` sub-block
- `commands/help.md` — Quick Reference Table should list `ll-loop run integrate-sdk` once stable

### Similar Patterns
- `scripts/tests/fixtures/fsm/learning-state-loop.yaml` — canonical `type: learning` usage; copy structure
- `skills/create-loop/loop-types.md` — "Optimize a harness" branch shape (`diagnose → propose → apply → measure-externally`) is the meta-loop template this issue follows
- `agents/loop-specialist.md` — failure-mode taxonomy for `diagnose_and_block` prompt (seven modes: `ambiguous-output`, `infinite-cycle`, `premature-termination`, `feature-stubbing`, `drift`, `self-evaluation bias`, `evaluator-trivial`)
- `scripts/little_loops/loops/adopt-third-party-api.yaml` — **closest existing analog**: `scrape → enumerate surfaces → prove via sub-loop → write playbook`; study its state graph before authoring `integrate-sdk.yaml`, especially the `output_json` evaluator for parsing enumerated surfaces
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — shows how to drive `ll-action invoke explore-api` per surface in a shell loop and check `ll-learning-tests check` for registry status
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` and `harness-optimize.yaml` — production `exit_code` branching patterns with `evaluate: type: exit_code` / `on_yes` / `on_no` (not `on_exit_0`/`on_exit_1`)
- `scripts/little_loops/loops/loop-router.yaml` — `input_key: goal` pattern for binding CLI positional to `${context.goal}`

### Tests
- Manual e2e: `ll-loop run integrate-sdk --target "anthropic" --goal "streaming"` against a clean tempdir; expect either `done` (scaffold + citations exist) or `on_blocked` (diagnosis exists); never silent success without citations.
- `ll-loop validate scripts/little_loops/loops/integrate-sdk.yaml` — must pass meta-loop rule MR-1 (non-LLM evaluator paired with `check_semantic`).
- New unit test `scripts/tests/test_integrate_sdk_loop.py` — load YAML, assert state graph is well-formed, assert `verify_scaffold` uses `evaluate: type: exit_code` (not LLM), assert `learning_gate.on_no` points to a terminal state, not a retry loop.
- `scripts/tests/test_verify_learning_citations.py` — verify the citation-checker script: passes when every `# Verified: <path>` resolves to a `status: proven` record; fails when path missing or status `refuted` / `stale`.
- `scripts/tests/test_builtin_loops.py` — **existing test that validates all built-in loop YAMLs are well-formed; must be updated to include `integrate-sdk.yaml`** (it validates loops from `scripts/little_loops/loops/`).
- Model new loop tests after `scripts/tests/test_learning_state.py` (uses `_MockRunner` and `_learning_fsm()` helper) and `scripts/tests/test_fsm_executor.py` (uses `MockActionRunner`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_expected_loops_exist` — has a **hardcoded exact-equality set** of all expected loop names (lines 66–125); the parametric `builtin_loops` fixture auto-discovers via glob but this test uses `assert expected == actual` (set equality); adding `integrate-sdk.yaml` without adding `"integrate-sdk"` to the `expected` set will **hard-break this test**
- `TestIntegrateSdkLoop` (new class inside `test_builtin_loops.py`) — add loop-specific structural assertions following the `TestAdoptThirdPartyApiLoop` pattern (lines 3847–3890): `LOOP_FILE = BUILTIN_LOOPS_DIR / "integrate-sdk.yaml"`, assert `learning_gate` routes to `scaffold_integration` on `on_yes`, assert a terminal blocked/diagnose path exists

### Documentation
- `docs/ARCHITECTURE.md` — add `integrate-sdk` to the "canonical loops" or "Learning Test Registry" section as the worked example of `type: learning` in a real loop.
- `commands/help.md` — Quick Reference Table entry (after loop is stable).
- `README.md` — only if loop count is tracked; otherwise skip.
- `.claude/CLAUDE.md` § Loop Authoring — add `integrate-sdk` as a referenced example of a compliant meta-adjacent loop.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — loop catalog index (manually maintained); add `integrate-sdk` row in the `## API Adoption` section alongside `adopt-third-party-api`
- `CONTRIBUTING.md` — directory layout comment reads `N YAML files` for `loops/`; tracked by `ll-verify-docs` via `doc_counts.py`; must increment count when loop is added
- `README.md` — **required, not optional**: `ll-verify-docs` / `doc_counts.py` checks the `N FSM loops` count against actual `*.yaml` files; adding `integrate-sdk.yaml` will cause a mismatch unless the count is updated

### Configuration
- N/A — uses existing `scripts/little_loops/loops/` (built-in loops directory); no new config keys needed.

## Implementation Steps

1. **Draft the YAML** at `scripts/little_loops/loops/integrate-sdk.yaml` — start from `scripts/little_loops/loops/adopt-third-party-api.yaml` (closest analog) and `scripts/tests/fixtures/fsm/learning-state-loop.yaml` (canonical `type: learning` fixture); use `input_key: target` + `context:` + `${context.xxx}` syntax (NOT `inputs:` / `{{inputs.xxx}}`); use `evaluate: type: exit_code` with `on_yes`/`on_no` (NOT `on_exit_0`/`on_exit_1`); run `ll-loop validate` and iterate until it passes (including meta-loop rule MR-1).
2. **Author the four prompt files** under `{{config.loops.loops_dir}}/prompts/`; the `scaffold_integration` prompt must explicitly require `# Verified:` citations on every generated API call site.
3. **Write `scripts/verify_learning_citations.sh`** (`scripts/lib/` does not exist — place in `scripts/`); model shell structure on `hooks/scripts/check-duplicate-issue-id.sh` (null-safe `find -print0 | while IFS= read -r -d ''` traversal, `set -euo pipefail`); it greps the scaffold dir for `# Verified: <path>` lines, parses each path via `scripts/little_loops/learning_tests.py` `read_record()` or YAML frontmatter extraction, asserts `status: proven`; exits 1 on any missing/refuted/stale citation.
4. **Test on a tractable greenfield target** (e.g., `python-pathlib` — no auth, well-documented, deterministic). Confirm full flow: scan → hypothesize_from_docs → learning_gate → scaffold → verify → done. Inspect scaffolded code for citations.
5. **Test the `on_blocked` path** by giving the loop a target with an intentionally wrong hypothesis (or one whose API has changed since training). Confirm `diagnose_and_block` emits a structured failure-mode classification, not generic prose.
6. **Test the existing-usage branch** by running against a target already imported in the repo (e.g., `pytest` if it's used). Confirm `hypothesize_from_code` cribs from real call sites.
7. **Test the credentialed-SDK failure mode** by targeting an SDK whose proof script needs an API key that isn't set. Confirm `diagnose_and_block` classifies as "requires credentials" rather than retrying or claiming success.
8. **Add the loop to `docs/ARCHITECTURE.md`** as the canonical `type: learning` worked example.
9. **Update `commands/help.md`** Quick Reference Table once the loop is stable.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_expected_loops_exist` — add `"integrate-sdk"` to the hardcoded `expected` set (exact-equality assertion; the auto-discovering `builtin_loops` fixture does not update this set automatically — the test **will fail** without this change)
11. Update `README.md` — increment the `N FSM loops` count (enforced by `ll-verify-docs` / `doc_counts.py`; **required, not optional**)
12. Update `CONTRIBUTING.md` — increment the `N YAML files` count in the `loops/` directory layout comment (enforced by `ll-verify-docs` / `doc_counts.py`)
13. Update `scripts/little_loops/loops/README.md` — add `integrate-sdk` row in the `## API Adoption` section alongside `adopt-third-party-api`

## Acceptance Criteria

- `ll-loop validate scripts/little_loops/loops/integrate-sdk.yaml` passes (including meta-loop rule MR-1).
- Greenfield e2e: running against `python-pathlib` (or equivalent zero-auth target) produces `.ll/learning-tests/<slug>.md` for each enumerated surface and scaffolded code with at least one `# Verified: .ll/learning-tests/<slug>.md` comment per API call site.
- Existing-usage e2e: running against an already-imported library exercises the `hypothesize_from_code` branch (verifiable in run logs).
- `on_blocked` path produces a `diagnose_and_block` artifact with a failure-mode classification from the `loop-specialist` taxonomy; **no scaffolded code is written**.
- `verify_scaffold` (non-LLM) blocks the loop from reaching `done` if any `# Verified:` citation is missing, points to a non-existent record, or points to a `refuted`/`stale` record.
- Credentialed SDK without credentials surfaces as `diagnose_and_block` with classification "requires credentials" — does not retry indefinitely, does not silently succeed.

## Impact

- **Priority**: P3 — Composes existing primitives (FEAT-1287, FEAT-1283, FEAT-1285/1286) into a developer-facing workflow. High strategic value (closes the "hallucinated SDK shape" class of bugs) but not blocking any in-flight work. Not P2 because there's a working manual fallback (`/ll:explore-api` + manual scaffolding).
- **Effort**: Medium — One YAML, four prompt files, one shell verifier, two test files. No new Python primitives needed; the loop is pure composition. The hard work is in the prompt design (especially `enumerate_surfaces` and `diagnose_and_block`).
- **Risk**: Low — New isolated loop; touches no existing automation. Scaffolded output is plain source code the developer reviews before merging. The non-LLM `verify_scaffold` gate prevents silent citation drift.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `sdk-integration`, `meta-loop-adjacent`, `captured`

---

**Open** | Created: 2026-05-25 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-27T06:30:27 - `4f51b3be-f04b-431b-a48d-86d79a52239d.jsonl`
- `/ll:confidence-check` - 2026-05-27T13:22:00 - `540d9d58-9859-451e-a1a9-6f40ea21c360.jsonl`
- `/ll:wire-issue` - 2026-05-27T06:22:05 - `5a5cf255-802c-4a93-983b-a058df40ad59.jsonl`
- `/ll:refine-issue` - 2026-05-27T06:15:09 - `a21261b4-cb01-4c3d-99db-c1129c637920.jsonl`
- `/ll:format-issue` - 2026-05-25T20:44:43 - `10e5eccd-bc85-4eab-9876-27a2c27b8c25.jsonl`
- `/ll:capture-issue` - 2026-05-25T20:34:52Z
- `/ll:capture-issue` - 2026-05-25T20:53:43Z - retrofitted as child of EPIC-1694 (4-loop LT stack) - `810cf8d1-477c-42da-bb20-b577b2ee3ad9.jsonl`
