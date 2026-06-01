---
id: ENH-1854
title: "Wave 2a \u2014 Add `parse_tagged_json` and `ll_commit` Fragments"
type: ENH
priority: P3
captured_at: '2026-06-01T18:00:00Z'
discovered_date: 2026-06-01
discovered_by: split-from-ENH-1775
parent: EPIC-1773
relates_to:
- ENH-1775
status: open
decision_needed: false
implementation_order_risk: true
confidence_score: 85
outcome_confidence: 51
score_complexity: 13
score_test_coverage: 10
score_ambiguity: 10
score_change_surface: 18
---

# ENH-1854: Wave 2a — Add `parse_tagged_json` and `ll_commit` Fragments

## Summary

Mechanical fragment extractions split from ENH-1775. Add a `parse_tagged_json` fragment to `loops/lib/common.yaml` (eliminating 3 duplicate python3 heredoc parsing states) and create `loops/lib/prompt-fragments.yaml` with an `ll_commit` fragment (eliminating 6 duplicate commit-state implementations). All 9 caller conversions are uniform substitutions with enumerated file lists.

This issue is the low-risk "quick wins" portion of ENH-1775. It can land independently before the complex generator-evaluator sub-loop work (ENH-1775 reduced scope).

## Current Behavior

**Tagged JSON parsing** — 3 integration loops each contain a near-identical python3 heredoc that parses a tagged JSON line from LLM output:

- `adopt-third-party-api.yaml` — parses `ENUMERATE_JSON:` tag
- `integrate-sdk.yaml` — parses `ENUMERATE_JSON:` tag
- `assumption-firewall.yaml` — parses `ASSUMPTIONS_JSON:` tag

Each duplicates the python3 invocation, line-splitting, tag-matching, and JSON extraction.

**Commit states** — 6 loops each inline a near-identical `action_type: prompt` commit state:

- `dead-code-cleanup.yaml:94-99`
- `test-coverage-improvement.yaml:198-204`
- `backlog-flow-optimizer.yaml:126-131`
- `issue-staleness-review.yaml:67-72`
- `docs-sync.yaml:57-62`
- `incremental-refactor.yaml:34-37` (structural outlier: uses `slash_command` not `prompt`, state named `commit_step`)

## Expected Behavior

**`parse_tagged_json` fragment** in `loops/lib/common.yaml`:

```yaml
parse_tagged_json:
  description: Parse a tagged JSON line from LLM output via captured context variable
  action_type: shell
  action: |
    python3 -c "
    import sys, json
    text = \"\"\"${captured.${context.capture_var}.output}\"\"\"
    for line in text.splitlines():
        if '${context.json_tag}:' in line:
            print(line.split('${context.json_tag}:', 1)[1].strip())
            break
    "
```

Callers set `context.json_tag` (e.g., `ENUMERATE_JSON`, `ASSUMPTIONS_JSON`) and `context.capture_var` (e.g., `raw_enumeration`, `raw_extraction`), then supply their own `evaluate:` and routing fields. Fragment provides `action_type` and `action` only.

**`ll_commit` fragment** in `loops/lib/prompt-fragments.yaml` (new file):

```yaml
ll_commit:
  description: Commit staged changes via /ll:commit with a parameterized message
  action_type: prompt
  action: |
    /ll:commit ${context.commit_message}
```

The first 5 loops supply `context.commit_message` with a loop-specific message. `incremental-refactor.yaml` overrides `action_type: slash_command` at the state level via deep-merge (fragment provides base, state fields override).

## Motivation

Both patterns are identical across callers except for one string parameter. A bug in the parse logic or commit invocation currently requires fixing 3–6 separate files. These are the lowest-risk extractions in EPIC-1773 — pure substitution with no interface design complexity.

## Proposed Solution

1. Add `parse_tagged_json` fragment to `loops/lib/common.yaml`
2. Convert 3 integration loops to use the fragment
3. Create `loops/lib/prompt-fragments.yaml` with `ll_commit` fragment
4. Convert 6 commit loops to use the fragment
5. Add fragment tests and minimal structural loop tests
6. Run `ll-loop validate` on all modified loops
7. Run regression suite

## Codebase Research Findings

_Updated by `/ll:refine-issue` — based on direct codebase analysis._

### Fragment Resolution Pipeline

`scripts/little_loops/fsm/fragments.py:resolve_fragments()` operates in three passes:
1. **Import loading** (lines 92-108): loads each path in `import: [...]`, last import wins on name collision
2. **Local fragment merging** (lines 111-114): loop-inline `fragments:` block merged on top of imported fragments
3. **State expansion** (lines 123-141): for each state with `fragment:`, calls `_deep_merge(frag_copy, state_dict)` — **fragment is base, state fields override**. `description` is stripped from the fragment copy before merge.

`_deep_merge()` semantics (lines 41-61): same key + both values are `dict` → recurse. All other types (str, int, bool, list, None) → state value wins outright. Consequence: `action_type: slash_command` at the state level fully replaces fragment's `action_type: prompt`.

### Confirmed: `parse_tagged_json` Does Not Yet Exist

`scripts/little_loops/loops/lib/common.yaml` currently defines 6 fragments: `shell_exit`, `retry_counter`, `llm_gate`, `with_rate_limit_handling`, `with_throttle`, `numeric_gate`. Every fragment has a non-empty `description:` field. `parse_tagged_json` is not present.

`scripts/little_loops/loops/lib/prompt-fragments.yaml` does not exist.

### ⚠ Design Constraint: stdin vs. Template-Variable Input

The proposed `parse_tagged_json` fragment reads from `sys.stdin.read()`. The actual loop states read from captured variables via heredoc interpolation: `output = """${captured.raw_enumeration.output}"""`. These are different input mechanisms.

The fragment as designed requires access to captured loop output. **Decision: Option A selected.**

> **Selected:** Option A — use `"""${captured.${context.capture_var}.output}"""` for input; callers set `context.capture_var: raw_enumeration` (or `raw_extraction`). Matches the `lib/cli.yaml` pattern of baking context variables directly into fragment actions.

- **Option A (selected)**: Change the fragment's `action:` to use a context variable for the source: `text = """${captured.${context.capture_var}.output}"""`, with callers setting `context.capture_var: raw_enumeration` (or `raw_extraction`). This matches how `ll_loop_run` in `lib/cli.yaml` bakes `${context.loop_name}` directly into the fragment action.
- **Option B** (rejected): Callers override `action:` entirely (keeping their existing complex Python), and the fragment only provides `action_type: shell`. Fragment value is minimal.

### ⚠ Design Constraint: Integration Loop Normalization Logic

The 3 integration loop parse states contain per-loop business logic beyond tag extraction that cannot be generalized:

- `adopt-third-party-api.yaml:58-95` (`parse_enumeration`): computes `fallback_domain` via `urlparse(${context.input})`, caps `targets` to 7, emits `{targets, domain, count, rationale}`. This domain-computation logic is URL-specific.
- `integrate-sdk.yaml:117-162` (`parse_enumeration`): caps `targets` to 7, extracts `branch` and `requires_credentials` from emitted JSON, emits `{targets, count, branch, requires_credentials, rationale}`.
- `assumption-firewall.yaml:53-83` (`parse_assumptions`): caps `targets` to 7, emits `{targets, rationale, count}`.

The fragment's action only does raw tag extraction (find the tagged line → print stripped JSON payload). If callers adopt the fragment for `action_type` only and keep their existing `action:`, the normalization is preserved but the fragment's `action:` is unused. If callers fully replace their action with the fragment's, the normalization logic is dropped.

The downstream `evaluate: {type: output_json, path: ".count"}` will still pass if the LLM emits a properly structured JSON — but fallback behavior (empty JSON on parse failure) and computed fields (`domain`, `branch`) would be lost. The implementer should confirm whether these fallbacks have ever fired in practice.

### ⚠ Design Constraint: `incremental-refactor.yaml` Commit Message

The current `incremental-refactor.yaml:34-37` `commit_step` state:
```yaml
commit_step:
  action: "/ll:commit"
  action_type: slash_command
  next: check_complete
```
Has no commit message. The `ll_commit` fragment's `action:` is `/ll:commit ${context.commit_message}`. After deep-merge with state-level `action_type: slash_command`, the merged state will have `action: /ll:commit ${context.commit_message}` with `action_type: slash_command`. The implementer must either:
- Set `context.commit_message:` to a loop-appropriate message in the state or loop context block
- Override `action: "/ll:commit"` at the state level (dropping the message parameter entirely)

A reasonable message for this loop: `"refactor: apply incremental refactoring step"`.

### Confirmed: ll_commit Placement Constraint

`test_all_fragments_are_shell_type` (line 879) and `test_all_fragments_have_exit_code_evaluate` (line 886) in `scripts/tests/test_fsm_fragments.py` unconditionally iterate ALL fragments in `lib/cli.yaml` and assert `action_type == "shell"` and `evaluate.type == "exit_code"`. No exemption mechanism exists. `ll_commit` (`action_type: prompt`, no evaluate) MUST NOT go in `lib/cli.yaml`.

Template for `lib/prompt-fragments.yaml`: `scripts/little_loops/loops/lib/score-plan-quality.yaml` — starts with comment block explaining import/usage, single `fragments:` key, each fragment has `description:`, `action_type:`, and optional base fields.

### Confirmed: 6 Commit States Verified at Stated Lines

| Loop | State | Lines | `action_type` | `next` |
|------|-------|-------|---------------|--------|
| `dead-code-cleanup.yaml` | `commit` | 94-99 | `prompt` | `scan` |
| `test-coverage-improvement.yaml` | `commit` | 198-204 | `prompt` | `measure` |
| `backlog-flow-optimizer.yaml` | `commit` | 126-131 | `prompt` | `measure` |
| `issue-staleness-review.yaml` | `commit` | 67-72 | `prompt` | `find_stale` |
| `docs-sync.yaml` | `commit` | 57-62 | `prompt` | `verify_docs` |
| `incremental-refactor.yaml` | `commit_step` | 34-37 | `slash_command` | `check_complete` |

### Confirmed: Test File Structure

- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — add `parse_tagged_json` presence test here. Class uses `_load_common_yaml()` helper resolving `loops/lib/common.yaml`.
- `scripts/tests/test_fsm_fragments.py:1068` (`test_all_common_yaml_fragments_have_description`) — iterates ALL `common.yaml` fragments and asserts `"description" in frag` + non-empty. Enforces description requirement.
- `scripts/tests/test_fsm_fragments.py:TestScorePlanQualityFragment:1199-1255` — use as the exact template for `TestLlCommitFragment`. 4-test shape: `_load_yaml()`, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop` (uses `resolve_fragments` with `import: ["lib/prompt-fragments.yaml"]`).
- `scripts/tests/test_builtin_loops.py:TestLearningTestsAuditLoop:507` — use for the minimal structural test class pattern. Fragment assertion idiom: `assert state.get("fragment") == "ll_commit"`.
- Loop classes `TestAssumptionFirewallLoop:3826`, `TestAdoptThirdPartyApiLoop:3878`, `TestIntegrateSdkLoop:3923` do NOT assert on action content of parse states — confirmed safe to change.

## Integration Map

### Files to Modify

- `loops/lib/common.yaml` — add `parse_tagged_json` fragment alongside existing fragments
- `loops/adopt-third-party-api.yaml` — convert `parse_enumeration` state (line ~58)
- `loops/integrate-sdk.yaml` — convert `parse_enumeration` state (line ~117)
- `loops/assumption-firewall.yaml` — convert `parse_assumptions` state (lines 53-83)
- `loops/lib/prompt-fragments.yaml` — **new file**; add `ll_commit` fragment
- `loops/dead-code-cleanup.yaml` — convert `commit` state (lines 94-99)
- `loops/test-coverage-improvement.yaml` — convert `commit` state (lines 198-204)
- `loops/backlog-flow-optimizer.yaml` — convert `commit` state (lines 126-131)
- `loops/issue-staleness-review.yaml` — convert `commit` state (lines 67-72)
- `loops/docs-sync.yaml` — convert `commit` state (lines 57-62)
- `loops/incremental-refactor.yaml` — convert `commit_step` state (lines 34-37; structural outlier)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/fragments.py:64` — `resolve_fragments()` expands `fragment:` references at parse time; no code changes needed
- `scripts/little_loops/fsm/validation.py:1374` — `load_and_validate()` calls fragment resolution; no code changes needed
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` resolves fragments; no code changes needed

### Similar Patterns

- N/A — all loops with duplicate `parse_tagged_json` and `ll_commit` patterns are enumerated in Files to Modify above

### Tests

- `scripts/tests/test_fsm_fragments.py:TestCommonYamlNewFragments:523` — add `parse_tagged_json` presence test
- `scripts/tests/test_fsm_fragments.py:TestDescriptionStrippedFromFragments:978` — `test_all_common_yaml_fragments_have_description:1068` requires `description:` on `parse_tagged_json`
- `scripts/tests/test_fsm_fragments.py` — **new test class** for `ll_commit` in `lib/prompt-fragments.yaml`; follow `TestScorePlanQualityFragment:1199` pattern (4-test shape: `_load_yaml`, `test_ll_commit_defined`, `test_ll_commit_has_prompt_action_type`, `test_ll_commit_has_description`, `test_ll_commit_resolves_in_loop`)
- `scripts/tests/test_builtin_loops.py` — **6 ll_commit target loops have no dedicated test classes**; add minimal structural tests (state existence, fragment reference) for: `dead-code-cleanup`, `test-coverage-improvement`, `backlog-flow-optimizer`, `issue-staleness-review`, `docs-sync`, `incremental-refactor`
- `scripts/tests/test_builtin_loops.py:TestAssumptionFirewallLoop:3826`, `TestAdoptThirdPartyApiLoop:3878`, `TestIntegrateSdkLoop:3923` — do NOT assert on action content of parse states; likely will NOT break from fragment conversion, but verify

### Documentation

- `docs/guides/LOOPS_GUIDE.md` — add `parse_tagged_json` and `ll_commit` to fragment tables
- `skills/create-loop/reference.md` — add new fragments to fragment catalog

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUDIT_REPORT.md` — line 90 explicitly enumerates known fragment library files (`common.yaml`, `cli.yaml`, `benchmark.yaml`); will be stale once `prompt-fragments.yaml` exists [Agent 2 finding]
- `docs/reference/CLI.md` — two `ll-loop fragments` example blocks (lines 645–647 and 755–757) enumerate built-in libraries by name; `prompt-fragments.yaml` must be added to both examples [Agent 2 finding]

### Configuration

- N/A — fragment resolution requires no schema or configuration changes

## Implementation Steps

1. **Add `parse_tagged_json` fragment** to `scripts/little_loops/loops/lib/common.yaml` — Insert after the `with_throttle` fragment in the `fragments:` block. Include `description:` field (required by `test_all_common_yaml_fragments_have_description`). Action uses stdin-based forward scan with `${context.json_tag}` runtime interpolation.

2. **Convert 3 integration loops** to use `parse_tagged_json` — Replace the inline python3 heredoc in each parse state with `fragment: parse_tagged_json`. Add `context.json_tag: ENUMERATE_JSON` (or `ASSUMPTIONS_JSON`) and `context.capture_var: raw_enumeration` (or `raw_extraction`) at the state level. Keep all existing `evaluate:` and routing fields on the state. Files: `adopt-third-party-api.yaml:58` (`parse_enumeration`), `integrate-sdk.yaml:117` (`parse_enumeration`), `assumption-firewall.yaml:53` (`parse_assumptions`). Note: the fragment handles raw tag extraction only — each caller must preserve its per-loop normalization logic (`action:` fields for `fallback_domain`, `branch`/`requires_credentials` computation) by keeping those fields on the state, overriding the fragment's `action:` via deep-merge.

3. **Create `loops/lib/prompt-fragments.yaml`** — New library file. Define `ll_commit` fragment with `action_type: prompt` and `description:`. Follow `lib/score-plan-quality.yaml` structure as template. The `action:` invokes `/ll:commit ${context.commit_message}`.

4. **Convert 6 commit loops** to use `ll_commit` fragment — Replace inline commit state with `fragment: ll_commit` + `context.commit_message: "<loop-specific message>"` on the state. For `incremental-refactor.yaml` (structural outlier): add `fragment: ll_commit` and keep `action_type: slash_command` as an override field (deep-merge scalar override). Because the current `commit_step` state has no commit message, also either add `context.commit_message: "refactor: apply incremental refactoring step"` or override `action: "/ll:commit"` (without message parameter) at the state level. Files: `dead-code-cleanup.yaml:94`, `test-coverage-improvement.yaml:198`, `backlog-flow-optimizer.yaml:126`, `issue-staleness-review.yaml:67`, `docs-sync.yaml:57`, `incremental-refactor.yaml:34`.

5. **Add tests** — (a) `parse_tagged_json` presence test in `TestCommonYamlNewFragments`; (b) new `ll_commit` fragment test class following `TestScorePlanQualityFragment:1199` pattern; (c) minimal structural test classes for 6 ll_commit target loops (assert `commit`/`commit_step` state exists and uses `fragment: ll_commit`).

6. **Validate all loops** — `ll-loop validate` on each of the 9 modified loops. Fix any ERROR-severity issues.

7. **Run regression suite** — `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`. Verify fragment tests pass and integration loop test classes are unaffected.

8. **Update documentation** — Add `parse_tagged_json` and `ll_commit` to fragment tables in `docs/guides/LOOPS_GUIDE.md` and `skills/create-loop/reference.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `docs/guides/AUDIT_REPORT.md` — add `prompt-fragments.yaml` to the fragment library enumeration at line 90
10. Update `docs/reference/CLI.md` — add `lib/prompt-fragments.yaml` to the two `ll-loop fragments` example blocks (lines 645–647 and 755–757)

**Out-of-scope context** (loops with additional inline commit states not targeted by this issue — candidates for a future cleanup wave):
- `loops/issue-refinement.yaml:58-61` — inline `/ll:commit` state named `commit`
- `loops/sprint-build-and-validate.yaml` — has commit-related states
- `loops/issue-discovery-triage.yaml` — has commit state

## Success Metrics

- `parse_tagged_json` fragment eliminates 3 duplicate python3 heredoc parsing states
- `ll_commit` fragment eliminates 6 duplicate commit-state implementations
- All 9 modified loops pass `ll-loop validate`
- `test_all_common_yaml_fragments_have_description` passes (description field present)
- `test_all_fragments_are_shell_type` and `test_all_fragments_have_exit_code_evaluate` still pass (ll_commit is NOT in cli.yaml)
- Test suite passes with no regressions

## Scope Boundaries

- Fragment addition and mechanical state conversion only — no behavioral changes
- Does NOT include `playwright_screenshot` fragment or `generator-evaluator` sub-loop (those are ENH-1775)
- Does NOT convert the 5 harness loops (ENH-1775)
- `svg-textgrad.yaml` and other candidate loops are out of scope

## Impact

- **Priority**: P3 — Low risk, clear ROI deduplication
- **Effort**: Small — all changes are mechanical substitutions across enumerated files
- **Risk**: Low — each conversion is independent; fragment resolution is well-tested; no interface design complexity
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `fragments`, `deduplication`

## Status

**Open** | Created: 2026-06-01 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 51/100 → LOW

### Concerns
- **Step 1 / Step 2 contradiction on stdin mechanism**: The "Expected Behavior" spec and Step 1 both use `sys.stdin.read()`, but the research findings flag stdin as incompatible with FSM capture variable output; Option A (`"""${captured.${context.capture_var}.output}"""`) is the recommended resolution. Update the spec before writing the fragment.
- **Normalization logic preservation**: Three integration loops embed per-loop business logic (URL domain computation, branch/credentials extraction) beyond raw tag extraction. Decide whether to keep caller `action:` fields (preserving logic) or fully replace them (dropping logic) before converting.

### Outcome Risk Factors
- **Broad change surface across 17 sites (Pattern B fanout)**: Sites are fully enumerated and changes are mechanical, but no standalone verification grep exists. Tests from Step 5 are the only completeness check and are co-deliverables — implement tests first so any missed site is caught during the implementation pass.
- **Test coverage gap for 6 commit loops**: `dead-code-cleanup`, `test-coverage-improvement`, `backlog-flow-optimizer`, `issue-staleness-review`, `docs-sync`, and `incremental-refactor` have no existing test classes; write structural tests alongside each conversion, not at the end.
- **Unresolved design decision — stdin vs. context variable in parse_tagged_json action**: The fragment's `action:` as specified in Expected Behavior will be non-functional. Adopt Option A and update the Expected Behavior section before writing the fragment code.

## Session Log
- `/ll:decide-issue` - 2026-06-01T18:04:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67e4d4e4-1440-479f-9406-ecd40fa28a8b.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75cef0b3-af02-4e85-a2ba-442a86576bc9.jsonl`
- `/ll:wire-issue` - 2026-06-01T17:56:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/420a5560-0b8d-425f-aeee-14be30fc4b7b.jsonl`
- `/ll:refine-issue` - 2026-06-01T17:51:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dfa382d0-dd02-477b-b6ac-1ce77830448d.jsonl`
- `/ll:format-issue` - 2026-06-01T17:28:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
