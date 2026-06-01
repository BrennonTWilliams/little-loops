---
id: ENH-1854
title: Wave 2a — Add `parse_tagged_json` and `ll_commit` Fragments
type: ENH
priority: P3
captured_at: '2026-06-01T18:00:00Z'
discovered_date: 2026-06-01
discovered_by: split-from-ENH-1775
parent: EPIC-1773
relates_to:
  - ENH-1775
status: open
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
  description: Parse a tagged JSON line from LLM output via stdin
  action_type: shell
  action: |
    python3 -c "
    import sys, json
    text = sys.stdin.read()
    for line in text.splitlines():
        if '${context.json_tag}:' in line:
            print(line.split('${context.json_tag}:', 1)[1].strip())
            break
    "
```

Callers set `context.json_tag` (e.g., `ENUMERATE_JSON`, `ASSUMPTIONS_JSON`) and supply their own `evaluate:` and routing fields. Fragment provides `action_type` and `action` only.

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

_(Inherited from ENH-1775 `/ll:refine-issue` analysis — see that issue for full context.)_

### Fragment Resolution Pipeline

Fragments are resolved at parse time in `fragments.py:resolve_fragments()`. Fragment provides the base fields; state-level fields override via deep-merge. The `parse_tagged_json` fragment provides `action_type: shell` and `action:` — callers supply `evaluate:` and routing. The `${context.json_tag}` variable is resolved at runtime via `interpolate()`.

### Tagged-JSON Parsing Pattern

All 3 integration loops share the same algorithm (scan lines, match tag, extract JSON payload, re-emit). Tag strings: `ENUMERATE_JSON:` (adopt-third-party-api, integrate-sdk), `ASSUMPTIONS_JSON:` (assumption-firewall).

The original heredoc scans in **reverse** (`reversed()`); the fragment scans **forward**. Both are equivalent for single-match scenarios; forward-scan avoids heredoc delimiter syntax issues in YAML.

### ll_commit Fragment Design

The `ll_commit` fragment must be in `lib/prompt-fragments.yaml`, NOT `lib/cli.yaml`. Reason: `test_all_fragments_are_shell_type:879` and `test_all_fragments_have_exit_code_evaluate:886` in `test_fsm_fragments.py` assert ALL `cli.yaml` fragments have `action_type: shell` and `evaluate.type: exit_code`. Placing a `prompt`-type fragment there violates both with zero exemption precedent.

Precedents for separate lib files: `score-plan-quality.yaml` (prompt-type) and `benchmark.yaml` (non-exit_code evaluate).

`incremental-refactor.yaml:34-37` uses `action_type: slash_command` with `"/ll:commit"` literal — handle via deep-merge override at the state level.

## Integration Map

### Files to Modify

- `loops/lib/common.yaml` — add `parse_tagged_json` fragment alongside existing fragments
- `loops/adopt-third-party-api.yaml` — convert `parse_enumeration` state (line ~58)
- `loops/integrate-sdk.yaml` — convert `parse_enumeration` state (line ~117)
- `loops/assumption-firewall.yaml` — convert `extract_assumptions` state (line ~53)
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

### Configuration

- N/A — fragment resolution requires no schema or configuration changes

## Implementation Steps

1. **Add `parse_tagged_json` fragment** to `scripts/little_loops/loops/lib/common.yaml` — Insert after the `with_throttle` fragment in the `fragments:` block. Include `description:` field (required by `test_all_common_yaml_fragments_have_description`). Action uses stdin-based forward scan with `${context.json_tag}` runtime interpolation.

2. **Convert 3 integration loops** to use `parse_tagged_json` — Replace the inline python3 heredoc in each parse state with `fragment: parse_tagged_json`. Add `context.json_tag: ENUMERATE_JSON` (or `ASSUMPTIONS_JSON`) at the state level. Keep all existing `evaluate:` and routing fields on the state. Files: `adopt-third-party-api.yaml:58` (`parse_enumeration`), `integrate-sdk.yaml:117` (`parse_enumeration`), `assumption-firewall.yaml:53` (`extract_assumptions`).

3. **Create `loops/lib/prompt-fragments.yaml`** — New library file. Define `ll_commit` fragment with `action_type: prompt` and `description:`. Follow `lib/score-plan-quality.yaml` structure as template. The `action:` invokes `/ll:commit ${context.commit_message}`.

4. **Convert 6 commit loops** to use `ll_commit` fragment — Replace inline commit state with `fragment: ll_commit` + `context.commit_message: "<loop-specific message>"` on the state. For `incremental-refactor.yaml` (structural outlier): add `fragment: ll_commit` but also keep `action_type: slash_command` as an override field — deep-merge applies fragment base then state overrides. Files: `dead-code-cleanup.yaml:94`, `test-coverage-improvement.yaml:198`, `backlog-flow-optimizer.yaml:126`, `issue-staleness-review.yaml:67`, `docs-sync.yaml:57`, `incremental-refactor.yaml:34`.

5. **Add tests** — (a) `parse_tagged_json` presence test in `TestCommonYamlNewFragments`; (b) new `ll_commit` fragment test class following `TestScorePlanQualityFragment:1199` pattern; (c) minimal structural test classes for 6 ll_commit target loops (assert `commit`/`commit_step` state exists and uses `fragment: ll_commit`).

6. **Validate all loops** — `ll-loop validate` on each of the 9 modified loops. Fix any ERROR-severity issues.

7. **Run regression suite** — `python -m pytest scripts/tests/test_fsm_fragments.py scripts/tests/test_builtin_loops.py -v --tb=short`. Verify fragment tests pass and integration loop test classes are unaffected.

8. **Update documentation** — Add `parse_tagged_json` and `ll_commit` to fragment tables in `docs/guides/LOOPS_GUIDE.md` and `skills/create-loop/reference.md`.

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


## Session Log
- `/ll:format-issue` - 2026-06-01T17:28:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ac3a8d0e-1e74-47b1-9d58-b8dbb8f453b4.jsonl`
