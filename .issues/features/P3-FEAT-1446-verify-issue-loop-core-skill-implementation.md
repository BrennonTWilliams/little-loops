---
id: FEAT-1446
priority: P3
type: FEAT
parent: FEAT-1310
size: Medium
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
completed_at: 2026-05-11T23:37:44Z
---

# FEAT-1446: verify-issue-loop — core skill implementation

## Summary

Scaffold and implement `skills/verify-issue-loop/SKILL.md` — the FSM loop generator that converts a single issue's acceptance criteria into a ready-to-run verification loop. Register the skill in `.claude/CLAUDE.md`. Write `scripts/tests/test_verify_issue_loop.py`.

## Parent Issue

Decomposed from FEAT-1310: verify-issue-loop skill (FSM loop generator from issue acceptance criteria)

## Motivation

`/ll:create-eval-from-issues` generates eval harnesses (which exercise a feature as a user would and judge the quality of the experience). There is no parallel command for generating an FSM loop that *verifies* the implementation by stepping through each acceptance criterion. Today, authors of verification loops have to hand-build YAML, copy boilerplate, and manually decompose acceptance criteria into checks. This child delivers the core skill that closes that gap.

## Implementation Steps

1. Scaffold `skills/verify-issue-loop/SKILL.md` by copying `skills/create-eval-from-issues/SKILL.md` as a starting point.
2. Replace harness-generation logic with FSM loop generation:
   - Reuse the issue resolution + parsing block (`ll-issues show <ID> --json`, then read file).
   - Extract Acceptance Criteria into a list (handle `- `, `* `, and `1.` styles).
   - Synthesize verify-state nodes: name (`verify-criterion-1`, `verify-criterion-2`, …), prompt scoped to that criterion, `llm_structured` evaluator with pass/fail + short reason.
   - Wire transitions: `on_yes: verify-criterion-<N+1>` and `on_no: failed` for each state; final verify state uses `on_yes: done`. Both `done` and `failed` are `terminal: true`.
3. Use existing FSM loop schema (see `.loops/` and `scripts/little_loops/loops/*.yaml` for shape — states, transitions, evaluators).
4. Write the YAML to `.loops/verify-<ISSUE-ID>-<slug>.yaml`, then run `ll-loop validate <path>` and surface validation output. If the issue has no Acceptance Criteria section (or it is empty), fail clearly with guidance to run `/ll:refine-issue` or `/ll:format-issue` first.
5. Add registration: append `verify-issue-loop` to the "Automation & Loops" line in `.claude/CLAUDE.md` Commands & Skills section (around line 56).
6. Tests: add `scripts/tests/test_verify_issue_loop.py` mirroring `test_create_eval_from_issues.py`:
   - **Fixture pattern**: declare a module-scope inline YAML string constant (e.g., `VERIFY_YAML_3_CRITERIA`) representing the *expected emitted YAML* for a 3-criterion case. Tests do **not** invoke the (LLM-driven) skill; they verify the *shape of expected output* against the FSM validator. This matches `VARIANT_A_YAML` / `VARIANT_B_YAML` in the source test file (lines 25, 67).
   - `TestVerifyLoopSingleIssue`: state presence (`verify-criterion-1` … `verify-criterion-3`, `done`, `failed`), transition routing (`on_yes: verify-criterion-<N+1>` for non-final, `on_yes: done` for final, `on_no: failed` throughout), evaluator shape (`type: llm_structured`, prompt length > 20), terminal flags (`states["done"]["terminal"] is True`, `states["failed"]["terminal"] is True`), absence of multi-issue states (`discover`, `advance` not present).
   - `TestVerifyLoopValidation`: library path — write fixture YAML to `tmp_path / ".loops" / "<name>.yaml"`, `monkeypatch.chdir(loops_dir.parent)`, call `load_and_validate(path)` then `validate_fsm(fsm)`, assert no errors at `ValidationSeverity.ERROR`. CLI path — `pytest.MonkeyPatch.context()` to set `sys.argv = ["ll-loop", "validate", "<name>"]`, import `main_loop` locally inside the `with` block, assert `main_loop() == 0`.

## Codebase Research Findings

- **Acceptance Criteria parsing is LLM-driven**: the agent reads the issue file directly and extracts `## Acceptance Criteria` by markdown heading. No reusable Python parser exists for freeform AC bullet text. Mirror the SKILL-embedded LLM extraction pattern from `skills/create-eval-from-issues/SKILL.md`.
- **YAML emission is template-string Write**: authors YAML as a literal template inside SKILL.md, filled in by the LLM and written via the `Write` tool.
- **`action_type: prompt` is the right shape** for verify states (no shell action needed). See `scripts/little_loops/loops/fix-quality-and-tests.yaml:13-25`.
- **Routing convention**: `on_yes: verify-criterion-<N+1>` / `on_no: failed` per verify state; `done` and `failed` are `terminal: true`. Pattern confirmed in `harness-single-shot.yaml`, `refine-to-ready-issue.yaml`, `eval-driven-development.yaml`.
- **Validation library import**: `from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm` — confirmed at `scripts/little_loops/fsm/validation.py`. `ValidationSeverity` is an `Enum` with values `ERROR` and `WARNING`; `load_and_validate(path)` returns `tuple[FSMLoop, list[ValidationError]]`; `validate_fsm(fsm)` returns `list[ValidationError]`.
- **Output directory**: `.loops/verify-<ISSUE-ID>-<slug>.yaml` (project-local). Do NOT write to `scripts/little_loops/loops/`.
- **FEAT-1308 confirmed complete**: at `.issues/completed/P3-FEAT-1308-loop-yaml-template-inheritance-via-from-field.md`. Inheritance is implemented in `scripts/little_loops/fsm/fragments.py` via `resolve_inheritance()`. Live examples: `scripts/little_loops/loops/apo-beam.yaml:2` and `scripts/little_loops/loops/apo-textgrad.yaml:2` both use `from: lib/apo-base`. **However, no `verify-issue-base.yaml` exists yet under `scripts/little_loops/loops/lib/`** — using `from:` requires authoring that parent first. See Proposed Solution for the decision.
- **Source skill has no `disable-model-invocation` field**: `skills/create-eval-from-issues/SKILL.md` frontmatter omits it. Mirror should match (omit, not set to `false`).
- **`ll-issues show <ID> --json` is the canonical resolution call**: source skill uses it (lines 54–59), not `ll-issues path`. The `path` field of the JSON is then passed to the `Read` tool.
- **Slug pattern in source**: shell-only — `SLUG=$(echo "${ISSUE_IDS[*]}" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')` (lines 113–118). A Python `slugify()` exists at `scripts/little_loops/issue_parser.py:99` but is not used by the source skill. For verify-issue-loop, lowercase the issue ID and join with a kebab-cased title slug: e.g., `verify-feat-1446-verify-issue-loop-core-skill-implementation.yaml`.
- **Single-issue scope (no Variant B)**: `create-eval-from-issues` supports multiple IDs (Variants A and B). verify-issue-loop is single-issue only — drop the discover/advance multi-issue branch entirely. `argument-hint: "<issue-id>"` (no `[issue-id...]`).

## Similar Patterns

- `skills/create-eval-from-issues/SKILL.md` — **Primary template**. Mirror its frontmatter (`allowed-tools: Bash(ll-issues:*, ll-loop:*, mkdir:*)`, `Read`, `Write`), `## Arguments` parser, `## Step 1`, `## Step 2`, `## Step 5`, `## Step 6` blocks. Drop Variant B (multi-issue discover/advance) entirely — verify-issue-loop is single-issue.
- `scripts/little_loops/loops/apo-beam.yaml:1-13` and `apo-textgrad.yaml:1-13` — **`from:` inheritance examples** if Option A is selected. Both use `from: lib/apo-base`; child supplies its own `name`, `description`, `initial`, `context`, and `states`.
- `scripts/little_loops/fsm/fragments.py` — `resolve_inheritance()` implements the merge. `from:` is stripped before the engine sees the merged dict.
- `scripts/little_loops/loops/harness-single-shot.yaml` (lines 113–131) — Canonical `llm_structured` evaluator shape with `source:`, `prompt:`, and `on_yes`/`on_no`/`on_partial` routing.
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` (lines 13–25) — `action_type: prompt` with embedded `llm_structured` evaluator (the closest single-state analog to a verify-criterion state).
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (lines 196–258, terminals at 335–339) — Linear pass-chain with shared `failed: terminal: true` and `done: terminal: true`.
- `scripts/tests/test_create_eval_from_issues.py` — **Test template**. Mirror assertion patterns (state presence lines 159–171, evaluator shape 173–181, routing 183–189, terminal 191–194, FSM validation 339–342, CLI validation 356–367). Note: fixtures are **inline YAML output strings at module scope** (`VARIANT_A_YAML`, `VARIANT_B_YAML`), not synthetic input issue files. Tests verify the *shape of expected output*; they do not invoke the (LLM-driven) skill.
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()` entry point used by the CLI validation tests via `sys.argv` injection (`["ll-loop", "validate", <name>]`).

## Proposed Solution

_Added by `/ll:refine-issue` — codebase research surfaced a real choice that needs resolution before implementation._

Two implementation options for the emitted YAML shape:

### Option A — Use `from: lib/verify-issue-base` inheritance

1. Author a new parent at `scripts/little_loops/loops/lib/verify-issue-base.yaml` that defines the shared scaffolding: `max_iterations`, `timeout`, terminal `done` / `failed` states, and any boilerplate context.
2. The generator emits a small child YAML containing only `from: lib/verify-issue-base`, `name`, `description`, `initial: verify-criterion-1`, and the N `verify-criterion-N` states.
3. **Pros**: per-issue YAML is short; future scaffolding changes apply to all verify loops by editing one base file; consistent with `apo-beam.yaml` / `apo-textgrad.yaml` precedent.
4. **Cons**: adds a new file under `scripts/little_loops/loops/lib/` that ships in the package; readers of generated YAML must follow the `from:` link to understand the full FSM; modest scope creep beyond a "core skill" issue.

### Option B — Emit fully-expanded YAML

> **Selected:** Option B — Emit fully-expanded YAML — dominant codebase pattern (40/42 loops self-contained); zero new infrastructure; mirrors `create-eval-from-issues` exactly; test fixture maps directly to `VARIANT_A_YAML`.

1. The generator emits a self-contained YAML with all states (verify-criterion-1..N, done, failed) and all scaffolding fields inline.
2. **Pros**: zero new files in `scripts/little_loops/loops/lib/`; generated YAML is fully readable in isolation; smallest blast radius for a "core skill" change.
3. **Cons**: every emitted file repeats the terminal/scaffolding boilerplate; later scaffolding edits require regenerating every existing verify loop.

**Recommendation**: lean toward **Option B** for this issue (matches the "core skill implementation" scope; FEAT-1447 handles wiring/docs; a future enhancement can extract a base if duplication becomes painful). But this is a judgment call worth confirming via `/ll:decide-issue` before implementation.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option B — Emit fully-expanded YAML

**Reasoning**: Option B is the dominant codebase pattern — 40 of 42 existing loop files define all states inline, and the only other YAML-emitting skill (`create-eval-from-issues`) emits fully self-contained YAML with zero inheritance. Option A would require authoring a new `lib/verify-issue-base.yaml` (scope creep) and would make the `VERIFY_YAML_3_CRITERIA` test fixture diverge from the `VARIANT_A_YAML` mirror template that the implementation steps explicitly cite.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Inheritance | 1/3 | 1/3 | 1/3 | 2/3 | 5/12 |
| Option B — Fully-expanded | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: `from:` mechanism works (`fragments.py:resolve_inheritance`) and FEAT-1308 anticipated this use, but only 2/44 loops use inheritance; no skill generator emits `from:` children; test fixture shape diverges from cited mirror (`test_create_eval_from_issues.py:25–65`). Reuse score: 2/3.
- **Option B**: Matches `create-eval-from-issues/SKILL.md` emission pattern exactly; `VERIFY_YAML_3_CRITERIA` fixture maps directly to `VARIANT_A_YAML`; zero new files under `scripts/little_loops/loops/lib/`. Reuse score: 3/3.

## Integration Map

### Files to Create

- `skills/verify-issue-loop/SKILL.md` — new skill scaffold (mirror `skills/create-eval-from-issues/SKILL.md`).
- `scripts/tests/test_verify_issue_loop.py` — new test file (mirror `scripts/tests/test_create_eval_from_issues.py`).
- `scripts/little_loops/loops/lib/verify-issue-base.yaml` — **only if Option A** is selected; otherwise skip.

### Files to Modify

- `.claude/CLAUDE.md:56` — append `verify-issue-loop`^ to the "Automation & Loops" line. Current contents: `` - **Automation & Loops**: `create-loop`^, `loop-suggester`, `review-loop`^, `debug-loop-run`^, `audit-loop-run`^, `rename-loop`^, `cleanup-loops`^, `workflow-automation-proposer`^ ``.

### Files Read (template / reference, not modified)

- `skills/create-eval-from-issues/SKILL.md` — frontmatter (lines 1–12), Step 1 issue resolution (lines 54–59), Step 2 extraction logic, Step 5 YAML emission template (Variant A lines 124–158), slug derivation (lines 113–118), Step 6 mkdir + Write + `ll-loop validate`.
- `scripts/tests/test_create_eval_from_issues.py` — imports (lines 11–19), `VARIANT_A_YAML` (lines 25–66), `TestEvalHarnessVariantA` (lines 142–209), `TestEvalHarnessValidation` (lines 309–380) including `loops_dir` fixture, `monkeypatch.chdir(loops_dir.parent)`, and `main_loop()` invocation pattern.
- `scripts/little_loops/fsm/validation.py` — `ValidationSeverity` (line 32), `validate_fsm()` (line 616), `load_and_validate()` (line 783).
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()` definition.

### Tests

- New: `scripts/tests/test_verify_issue_loop.py` — see Implementation Steps §6.
- No changes to existing tests.

### Sibling / Wiring

- `FEAT-1447` (`.issues/features/P3-FEAT-1447-verify-issue-loop-wiring-and-doc-count-updates.md`) handles `commands/help.md`, README/CONTRIBUTING/ARCHITECTURE skill-count updates, and the alphabetical skill tree. **Do not** modify those files in this issue.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1287_doc_wiring.py` — contains `TestReadmeSkillCount`, `TestContributingWiring`, and `TestClaudeMdWiring` classes that hardcode `"29 skills"` / `"29 skill definitions"` / `"(29 skills)"` assertions. These will break once FEAT-1447 updates the count strings to `30`. **FEAT-1447 must include updating these test assertions** (not in FEAT-1447's current acceptance criteria — flag that issue).

### Documentation

- `.claude/CLAUDE.md` registration is in scope here (acceptance criterion above).
- All other docs are owned by FEAT-1447.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — contains a full `### /ll:create-eval-from-issues` section (line 466) and Quick Reference Table row (line 790). A parallel `### /ll:verify-issue-loop` section and table row are the expected parity addition. **Currently not claimed by FEAT-1446 or FEAT-1447** — FEAT-1447 should be updated to include this.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `create-eval-from-issues` and has a See Also pattern for parallel skills. A See Also entry for `/ll:verify-issue-loop` follows this pattern. **Currently not claimed by FEAT-1446 or FEAT-1447** — FEAT-1447 should be updated to include this.

### Configuration

- No config changes. No new entries in `.ll/ll-config.json` or `config-schema.json`.

## API/Interface

New skill: `skills/verify-issue-loop/SKILL.md`

```
/ll:verify-issue-loop <issue-id>
```

- `argument-hint: "<issue-id>"`
- `allowed-tools`: `Bash(ll-issues:*, ll-loop:*, mkdir:*)`, `Read`, `Write`
- Output file path: `.loops/verify-<ISSUE-ID>-<slug>.yaml`

## Acceptance Criteria

- [ ] `skills/verify-issue-loop/SKILL.md` exists with frontmatter, description, trigger keywords, and argument-hint mirroring `create-eval-from-issues`.
- [ ] Running `/ll:verify-issue-loop <ID>` against an issue with N acceptance criteria writes a YAML with exactly N verify-states.
- [ ] Each verify-state has a prompt scoped to one criterion and an `llm_structured` pass/fail evaluator.
- [ ] Verify-states transition linearly on pass; any failure transitions to a shared `failed` terminal state with reason captured.
- [ ] Final verify-state transitions to `done` on pass.
- [ ] Generated YAML passes `ll-loop validate` without errors.
- [ ] Issue with no Acceptance Criteria section produces a clear error referencing `/ll:refine-issue` / `/ll:format-issue`, and writes no file.
- [ ] `verify-issue-loop` is added to the "Automation & Loops" line in `.claude/CLAUDE.md`.
- [ ] `scripts/tests/test_verify_issue_loop.py` covers a multi-criterion fixture and asserts state count, transitions, and `ll-loop validate` success.

## Impact

- **Priority**: P3
- **Effort**: Medium — New SKILL.md scaffold + FSM logic + tests
- **Risk**: Low — Purely additive; no existing skills or runtime modified
- **Breaking Change**: No

### Wiring Phase (added by `/ll:wire-issue`)

_These constraints and touchpoints were identified by wiring analysis:_

7. **Skill description budget** — when authoring `skills/verify-issue-loop/SKILL.md`, keep the `description:` frontmatter field ≤ 100 chars. The `check_skill_budget()` function in `scripts/little_loops/doc_counts.py` auto-scans all `skills/*/SKILL.md` description fields and `ll-verify-skill-budget` will exit non-zero if the total token footprint exceeds the threshold.
8. **FEAT-1447 gap flags** (no action required in this issue, but raise in FEAT-1447 review): `docs/reference/COMMANDS.md` and `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` need `verify-issue-loop` entries; `scripts/tests/test_feat1287_doc_wiring.py` hardcoded count assertions need bumping from `29` to `30`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- **Open decision on YAML emission shape** (Option A vs Option B) — `decision_needed: true` is set; resolve via `/ll:decide-issue FEAT-1446` before authoring the `VERIFY_YAML_3_CRITERIA` fixture constant, or the inline YAML string in `test_verify_issue_loop.py` may require rewriting after the option is confirmed.
- **Skill markdown has no automated unit test path** — SKILL.md logic errors in AC extraction instructions or state-wiring template will only surface via `ll-loop validate` on generated output; no unit-level guard exists. Plan a manual trial run as part of acceptance.

## Session Log
- `/ll:manage-issue` - 2026-05-11T23:37:44Z - `0010190c-509e-453e-bb85-c00575d1e590.jsonl`
- `/ll:ready-issue` - 2026-05-11T23:31:27 - `51603bf2-bd9e-4041-ab9b-526ee32c757d.jsonl`
- `/ll:confidence-check` - 2026-05-11T23:45:00 - `d3aeece8-8901-48e9-a34b-03dc3708fc2f.jsonl`
- `/ll:decide-issue` - 2026-05-11T23:28:17 - `9d5860c5-be18-42f4-af78-becc0b286f63.jsonl`
- `/ll:wire-issue` - 2026-05-11T23:21:55 - `7a42072e-b27a-4b35-adec-dc671315063a.jsonl`
- `/ll:refine-issue` - 2026-05-11T23:17:30 - `d17dc8fc-73c0-4fc8-8a5f-b5831ed2b3d2.jsonl`
- `/ll:issue-size-review` - 2026-05-11T00:00:00Z - `03785380-ad15-4700-be73-f3d5f0c746ce.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `b19cf837-b335-4341-b153-e605d94bca56.jsonl`

---

## Status
- **Status**: Done
- **Discovered**: 2026-05-11
- **Discovered by**: issue-size-review
- **Completed**: 2026-05-11

## Resolution

Implemented FEAT-1446 — core `verify-issue-loop` skill:

- Created `skills/verify-issue-loop/SKILL.md` mirroring `create-eval-from-issues` frontmatter and step structure; emits fully-expanded YAML (Option B, per decision rationale).
- Created `scripts/tests/test_verify_issue_loop.py` with module-scope `VERIFY_YAML_3_CRITERIA` fixture; 18 tests covering state presence, linear pass-routing (`on_yes` forward, final → `done`), shared `on_no: failed`, terminal flags, single-issue scope (no `discover`/`advance`), and FSM validation via both library and CLI paths.
- Registered `verify-issue-loop`^ on the "Automation & Loops" line in `.claude/CLAUDE.md`.
- All 18 new tests pass. `ruff check` clean on new file. `ll-verify-skill-budget` under budget (description = 99 chars). Smoke-tested generated YAML shape with `ll-loop validate` (PASS).

FEAT-1447 owns the docs/skill-count updates (out of scope here).
