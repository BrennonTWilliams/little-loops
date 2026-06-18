---
id: ENH-2221
title: Eval dimension — learning_tests_required as machine-checkable criterion
type: enhancement
priority: P4
status: open
parent: EPIC-2207
depends_on: ENH-2208
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
decision_needed: false
---

# ENH-2221: Eval dimension — learning_tests_required as machine-checkable criterion

## Summary

`/ll:create-eval-from-issues` generates eval scenarios from issue specs but all evaluation criteria are LLM-judged. For issues with `learning_tests_required`, add a machine-checkable eval criterion: "All declared learning tests are proven before implementation begins." This is verifiable via `ll-learning-tests check` (exit code 0/1) — no LLM judge needed.

## Current Behavior

`/ll:create-eval-from-issues` generates eval scenarios from issue specs, but all evaluation criteria use LLM-judged (`check_semantic`) evaluators. There is no support for machine-checkable (`exit_code`) criteria, even when an issue declares `learning_tests_required` with known, shell-verifiable targets.

Learning test proof status must be verified manually or through separate tooling — the eval harness does not enforce it as part of the automated eval run.

## Expected Behavior

When an issue with `learning_tests_required` is processed by `/ll:create-eval-from-issues`, the generated eval YAML includes `exit_code` criteria that verify each required learning test is proven via `ll-learning-tests check`. These criteria are grouped separately from LLM-judged dimensions under a `## Proof-First Gates` section, producing an objective PASS/FAIL signal alongside semantic evaluations.

## Motivation

The eval harness (`ll-harness`) supports `exit_code` evaluators alongside `check_semantic`. Learning test proof status is a perfect fit: it's binary, shell-accessible, and captures a real quality gate. Adding it as a criterion means eval runs can report "proof-first gate: PASS/FAIL" objectively alongside LLM-judged dimensions.

## Proposed Solution

In `/ll:create-eval-from-issues`, after parsing issue frontmatter for `learning_tests_required`:

1. For each target in the list, construct an `exit_code` criterion using the `--stale-aware` flag (added by ENH-2208 to `ll-learning-tests check`):
   ```yaml
   - id: lt_proven_<slug>
     type: exit_code
     command: "ll-learning-tests check --stale-aware \"<target>\""
     expected_exit: 0
     label: "Learning test proven: <target>"
   ```
   `--stale-aware` exits 1 if the record is absent or date-stale (even if `status: proven` on disk), so the eval criterion agrees with the runtime gate.
2. Inject these criteria before the LLM-judged criteria in the generated eval YAML.
3. In eval output, group them under a `## Proof-First Gates` section header.
4. Gate the behavior behind `learning_tests.enabled`.

The existing `ll-harness` evaluator framework already handles `exit_code` evaluators — no changes to the harness executor are needed. This change is isolated to the eval-from-issues generation logic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Criterion YAML format correction**: The `id:`/`command:`/`expected_exit:`/`label:` list format described above does not exist in the FSM YAML schema. `ll-harness` supports `exit_code` evaluation only via FSM shell action states with `evaluate: type: exit_code` (verified at `scripts/little_loops/fsm/evaluators.py:evaluate_exit_code()` line 136). The correct representation is one FSM state per target, inserted before `check_skill`:

```yaml
check_proof_<slug>:
  action: |
    ll-learning-tests check --stale-aware "<target>"
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: check_skill   # or next proof state when chaining multiple targets
  on_no: done
  on_error: done
```

For multiple targets, chain states: `check_proof_t1 → check_proof_t2 → … → check_skill`. The `execute` state's `next:` must be updated to route to the first proof state (not `check_skill`) whenever any targets exist.

**Harness fragment note**: `scripts/little_loops/loops/lib/common.yaml:shell_exit` is the canonical shorthand (`fragment: shell_exit`), but neither Variant A nor Variant B in the generated harness has an `import:` block, so inline expansion of `action_type: shell` + `evaluate: type: exit_code` is required.

**Config reading inside the skill's Bash context**:
```bash
LT_ENABLED=$(python3 -c "
import json, pathlib
p = pathlib.Path('.ll/ll-config.json')
cfg = json.loads(p.read_text()) if p.exists() else {}
print(str(cfg.get('learning_tests', {}).get('enabled', False)).lower())")
```
If `$LT_ENABLED` is `false`, skip injection of proof states entirely.

## Implementation Steps

1. In `/ll:create-eval-from-issues`, after parsing the issue, check for `learning_tests_required`.
2. For each target in the list, add an eval criterion of type `exit_code` using `--stale-aware`:
   ```yaml
   - id: lt_proven_<slug>
     type: exit_code
     command: "ll-learning-tests check --stale-aware \"<target>\""
     expected_exit: 0
     label: "Learning test proven: <target>"
   ```
3. Inject these criteria before the LLM-judged criteria in the generated eval YAML.
4. In eval output, group them under a `## Proof-First Gates` section header.
5. Gate behind `learning_tests.enabled`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

All changes target `skills/create-eval-from-issues/SKILL.md` only — no Python files need modification:

- **`## Step 2: Extract Evaluation Context`**: Add a 5th extraction item — parse `learning_tests_required` from the `ll-issues show <ID> --json` result's `.learning_tests_required` field. `IssueParser` already populates this at `scripts/little_loops/issue_parser.py:IssueFile.learning_tests_required` (line 271), so the JSON output already contains it.
- **`### Variant A (single issue)` template**: When `learning_tests_required` is non-empty and `LT_ENABLED=true`, change `execute.next: check_skill` to `execute.next: check_proof_<first-slug>` and insert proof state(s) before `check_skill`. Slug: lowercase target with spaces/special chars replaced by underscores.
- **`### Variant B (multiple issues)` template**: Route `execute.next:` through proof states. Because Variant B iterates over multiple issues (some may lack targets), the proof state action should include a Bash guard: `[ "${captured.current_item.output}" = "<ISSUE-ID>" ] && ll-learning-tests check --stale-aware "<target>" || exit 0`.
- **`## Output Format`**: Extend the `States:` line to include proof state names when present; add a `Proof-First Gates:` count line to the summary block.

## Integration Map

### Files to Modify

- `skills/create-eval-from-issues/SKILL.md` — extend Step 2 (Extract Evaluation Context) to parse `learning_tests_required` from issue frontmatter; extend Step 5 (Generate Harness YAML) Variant A/B templates to inject `exit_code` criteria before the `llm_structured` evaluator in `check_skill`; add `## Proof-First Gates` section grouping in the Step 6/Output Format blocks

### Dependent Files

- `ll-harness` — already supports `exit_code` evaluators; no changes needed
- `ll-learning-tests` — the `check` subcommand is the verification mechanism; no changes needed

### Tests

- Add tests for `exit_code` criterion generation when `learning_tests_required` is present
- Add tests verifying issues without `learning_tests_required` produce identical output (unchanged behavior)

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_create_eval_from_issues.py` — existing test file with `VARIANT_A_YAML`, `VARIANT_B_YAML` fixtures and `TestEvalHarnessVariantA`, `TestEvalHarnessVariantB` classes; new tests should follow the `test_discover_uses_shell_action_type()` pattern (assert `harness["states"]["check_proof_<slug>"]` exists and has `action_type: shell` + `evaluate.type: exit_code`)
- `scripts/tests/test_cli_learning_tests.py` — existing tests for `ll-learning-tests check --stale-aware`; no new tests needed here (ENH-2208 coverage)

### Documentation

- Update eval-from-issues documentation if it describes criterion generation internals

### Configuration

- `learning_tests.enabled` config property gating the new behavior

## Acceptance Signals

- Eval generated from an issue with `learning_tests_required: [anthropic]` includes an `exit_code` criterion for `ll-learning-tests check "anthropic"`
- Running `ll-harness` on the eval returns `PASS` for a proven record and `FAIL` for missing/stale
- The criterion appears in eval output as a separate section from LLM-judged dimensions
- Issues without `learning_tests_required` are unchanged

## Success Metrics

- Eval YAML for `learning_tests_required: [anthropic]` contains an `exit_code` criterion per target
- `ll-harness` eval run reports PASS/FAIL for learning test gates distinctly from semantic criteria
- Issues without `learning_tests_required` produce identical output to current behavior
- Learning test gates are visually grouped under their own section header in eval reports

## Scope Boundaries

- **In scope**: Adding machine-checkable `exit_code` criteria to eval YAML generation; grouping criteria under "Proof-First Gates" in output
- **Out of scope**: Modifying `ll-learning-tests check` itself; adding new CLI commands; changing the LLM-judged criterion format; adding learning test record management features

## Impact

- **Priority**: P4 — valuable quality gate but non-critical; builds on existing learning test infrastructure
- **Effort**: Small — leverages existing `exit_code` evaluator support in `ll-harness`; isolated to eval generation logic
- **Risk**: Low — additive change with no breaking modifications to existing criterion generation
- **Breaking Change**: No

## Labels

`enhancement`, `captured`, `eval`, `learning-tests`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2214 (release gate) and ENH-2220 (scope-epic).

- A complementary machine-checkable gate exists at the release stage (ENH-2214). That gate uses project-wide import scans and configurable `block`/`warn` behavior. This issue's gate uses issue-frontmatter targets and `exit_code` criteria in eval YAML. They are distinct lifecycle stages with different implementations. See [[ENH-2214]].
- This issue consumes `learning_tests_required` frontmatter populated by ENH-2220's scope-epic flow. When ENH-2220 generates sub-issues with learning test prerequisites, those targets become available for eval criterion generation here. See [[ENH-2220]].

**Note** (added by `/ll:audit-issue-conflicts`; resolved by review-epic): The criterion command must use `ll-learning-tests check --stale-aware "<target>"`. ENH-2208 commits to adding `--stale-aware` to the CLI (exits 1 if absent or date-stale, regardless of `record.status` on disk). This eliminates the "either/or" hedge — no Python wrapper needed. This issue is declared `depends_on: ENH-2208` and must not ship until ENH-2208 is merged. See [[ENH-2208]].

**Note** (2026-06-18 audit): `create-eval-from-issues` is a prompt-based skill (`skills/create-eval-from-issues/SKILL.md`), not a Python CLI. There is no `scripts/little_loops/cli/create_eval_from_issues.py`. The implementation targets the SKILL.md prompt instructions directly: Step 2 gains `learning_tests_required` parsing, Step 5 Variant A/B templates gain an injected `exit_code` criterion block, and the Output Format section gains a `## Proof-First Gates` grouping note. No Python file needs to be created or modified for this issue.

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2219's per-worktree runtime gate (`ll-loop run proof-first-task`) and this issue's eval criterion use different mechanisms and will disagree on date-stale records unless both are stale-aware. A user who sees "eval: PASS" and then gets a blocked worktree will be confused about why the pre-flight passed. If this eval criterion is intended to serve as a pre-flight signal for `ll-parallel` execution (ENH-2219), the stale-aware fix above (from the ENH-2208 conflict) is a prerequisite — without it, the eval result is not a reliable indicator of what ENH-2219's gate will do. See [[ENH-2219]].

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T20:50:30 - `2a1b4900-886d-46f7-9096-478aa4b8e4b3.jsonl`
- `/ll:format-issue` - 2026-06-18T19:33:39 - `eebe5815-0f5b-4c82-acb0-64597681c904.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

## Status

**Open** | Created: 2026-06-18 | Priority: P4
