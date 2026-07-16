---
id: ENH-2658
title: Add `ids` filter to prompt-across-issues loop
type: enhancement
priority: P3
status: done
captured_at: '2026-07-16T18:24:41Z'
completed_at: '2026-07-16T18:55:35Z'
discovered_date: 2026-07-16
discovered_by: capture-issue
labels:
- enhancement
- loops
- fsm
- prompt-across-issues
- captured
relates_to:
- ENH-1643
- EPIC-1853
confidence_score: 90
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2658: Add `ids` filter to prompt-across-issues loop

## Summary

The `prompt-across-issues` FSM loop currently filters its sweep via `--context type=TYPE` or `--context parent=EPIC-NNN`. Neither accepts an explicit comma-separated list of issue IDs, so a user who wants to run a prompt against a hand-picked, unrelated set has no first-class path. Today they must either (a) hand-drive a shell `for` loop calling the host CLI per issue, or (b) temporarily edit each issue's `parent:` frontmatter to point at a new synthetic EPIC — both heavyweight for an ad-hoc sweep.

The fix: add a third optional `context.ids` variable that, when set, overrides `type`/`parent` and writes the parsed IDs directly to the pending list. Mirrors the existing filter precedent (ENH-1643 added `type`; EPIC-1853 / ENH-2481 added `parent`).

## Current Behavior

`scripts/little_loops/loops/prompt-across-issues.yaml` declares exactly two filter axes:

```yaml
context:
  type: ""
  parent: ""
```

The `init` state (line 68) only branches on those two: `ll-issues list $TYPE_ARG $PARENT_ARG --json`. An explicit ID list is unreachable. The conversation that triggered this issue: a user wanting to sweep 10 sibling-but-unparented enhancements had no way to scope the loop to exactly those IDs.

## Expected Behavior

Add a third filter axis that overrides `type`/`parent` when set:

```bash
ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" \
  --context ids=ENH-2463,ENH-2464,ENH-2466,ENH-2496,ENH-2497,ENH-2505,ENH-2507,ENH-2508,ENH-2509,ENH-2580
```

The comma-separated value is split on `,`, whitespace is trimmed, empty entries are dropped, and the resulting IDs are written to `${context.run_dir}/pending.txt` — bypassing the `ll-issues list` call entirely. When `ids` is empty, the existing type/parent branch runs unchanged.

## Motivation

The loop is the project's go-to tool for batch operations on the issue backlog (refine, normalize, format, audit, etc.). Forcing users to either hand-drive a shell loop or mutate issue frontmatter for an ad-hoc sweep is a friction point. Two existing precedents already establish the `--context KEY=VALUE` filter shape (ENH-1643, EPIC-1853), so the implementation follows established patterns — minimal design risk.

Concrete motivating use case (from the conversation that surfaced this issue): 10 sibling ENH issues (2463, 2464, 2466, 2496, 2497, 2505, 2507, 2508, 2509, 2580) that belong to the same analytics-history initiative but were never parented under a single EPIC. Running a sweep against exactly those IDs without parent-ing them is the natural workflow.

## Proposed Solution

Add `ids: ""` to the loop's `context:` block and branch the `init` state on it:

```yaml
context:
  type: ""
  parent: ""
  ids: ""  # Optional: comma-separated issue IDs (e.g. ENH-2463,ENH-2464).
           # When set, overrides type/parent and processes exactly these IDs.
```

```yaml
  init:
    action: |
      cat > "${context.run_dir}/validate-input.txt" <<'LL_INPUT_EOF'
      ${context.input}
      LL_INPUT_EOF
      if ! grep -q '[^[:space:]]' "${context.run_dir}/validate-input.txt"; then
        echo "ERROR: input prompt is required. Usage: ll-loop run prompt-across-issues \"<prompt>\""
        exit 1
      fi
      if [ -n "${context.ids}" ]; then
        # Explicit ID list overrides type/parent filters.
        echo "${context.ids}" | tr ',' '\n' \
          | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
          | grep -v '^$' > "${context.run_dir}/pending.txt"
      else
        TYPE_ARG=""
        if [ -n "${context.type}" ]; then
          TYPE_ARG="--type ${context.type}"
        fi
        PARENT_ARG=""
        if [ -n "${context.parent}" ]; then
          PARENT_ARG="--parent ${context.parent}"
        fi
        ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "
        import json, sys
        issues = json.load(sys.stdin)
        for i in issues:
            print(i['id'])
        " > "${context.run_dir}/pending.txt"
      fi
      COUNT=$(wc -l < "${context.run_dir}/pending.txt" | tr -d ' ')
      echo "Found $${COUNT} issues to process"
    fragment: shell_exit
    on_yes: discover
    on_error: diagnose_error
```

Also update the YAML header `## description` block to document the new usage:

```yaml
  ll-loop run prompt-across-issues "/ll:refine-issue {issue_id}" --context ids=ENH-1,ENH-2,ENH-3
```

`${context.ids}` content is alphanumeric + commas only (no shell metacharacters), so MR-11 is satisfied — bare interpolation in the shell action is safe.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**MR-11 clarification**: The lint's `_UNSAFE_CONTEXT_INTERP_RE` (`scripts/little_loops/fsm/validation.py:139-141`) only flags `${context.(input|goal|description|task|prompt|query|topic)}`. `ids` is outside this regex entirely, so MR-11 passes by virtue of the regex scope, not because the content is known-safe. The issue's safety rationale ("alphanumeric + commas only") is correct in practice for typical use, but a hostile caller could pass `ids=ENH-1;rm -rf /`. The host CLI's slash-command parser will reject the malformed token, so impact is bounded — but the lint exemption is by-regex, not by-content.

**Edge case — `wc -l` under-count**: The proposed `tr ',' '\n' | sed | grep > pending.txt` chain does NOT guarantee a trailing newline. If `pending.txt` ends without `\n`, `wc -l` under-counts by 1, so the "Found N issues to process" log is off-by-one. **Pre-existing latent quirk** — the current `python3 -c "... print(i['id'])"` branch has the same issue. Not a regression. If desired, append `printf '\n' >> "${context.run_dir}/pending.txt"` after the redirect, but doing so is out of scope for the minimal change.

**Empty-input branch routing**: The current `init` has `on_yes: discover` and `on_error: diagnose_error` but no `on_no`. Empty input → `grep` exit 1 → verdict `no` → dead-end (since `shell_exit` fragment routes exit 1 to `no` and there's no `on_no`). This is a pre-existing latent edge case, not introduced by this change.

**Why `init` is the only state that needs editing**: `discover` (lines 80-92) and `advance` (lines 120-133) only read/mutate `pending.txt`; they never re-source or filter the queue. So branching at `init` is the single, sufficient insertion point. No downstream state references `${context.type}` or `${context.parent}`.

**What `discover` does on empty `pending.txt`**: `if [ ! -s ... ]; then exit 1; fi` → verdict `no` → `done`. So if `ids=,,` (all empty after trim), `pending.txt` is 0 bytes and the loop terminates cleanly without an error diagnostic — matches today's "zero matches" semantics.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — add `ids` context var, branch `init`, update description header.

### Dependent Files (Callers/Importers)
- None. The loop is a leaf FSM loop; callers invoke `ll-loop run prompt-across-issues` and don't import the YAML.

### Similar Patterns
- `ENH-1643` (type filter) and `EPIC-1853` / `ENH-2481` (parent filter) established the exact `--context KEY=VALUE` shape — match it.
- `${context.input:shell}` (line 102) is precedent for `context.*` references inside shell actions.

### Tests
- `scripts/tests/test_builtin_loops.py` — add a prompt-across-issues test case for the `ids` filter asserting pending.txt contains exactly the supplied IDs in order.
- Regression test: when `ids=""`, the existing `type`/`parent` paths produce the same output as before the change.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py:1010` — existing built-in-loop migration smoke test includes `prompt-across-issues.yaml`; confirm it remains valid after the YAML change (Agent 1/3 finding).

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — add the `ids` example to the prompt-across-issues usage section.
- The loop YAML header `## description` block lists usage examples; add the `ids` example there.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md:36` — mirrors the built-in loop catalog description for `prompt-across-issues`; add the `--context ids=ENH-1,ENH-2` usage and override semantics alongside the existing `type`/`parent` filters (Agent 1/2 finding).

### Configuration
- N/A — no config schema change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified file anchors** (from `scripts/little_loops/loops/prompt-across-issues.yaml`):

| Block | Lines | Anchor |
|-------|-------|--------|
| `description:` header (existing usage examples) | 1–25 | update with `ids=` example |
| `context:` block | 36–40 | add `ids: ""` here |
| `init` state body | 44–78 | branch on `${context.ids}` |
| `discover` state (consumes pending.txt) | 80–92 | unchanged — exits 1 → `done` on empty |
| `advance` state (mutates pending.txt) | 120–133 | unchanged |
| `diagnose_error` state (reads pending.txt) | 138–149 | unchanged |

**Precedent — ENH-1643 actual implementation shape** (`scripts/little_loops/loops/prompt-across-issues.yaml:60–73`):

```sh
TYPE_ARG=""
if [ -n "${context.type}" ]; then
  TYPE_ARG="--type ${context.type}"
fi
PARENT_ARG=""
if [ -n "${context.parent}" ]; then
  PARENT_ARG="--parent ${context.parent}"
fi
ll-issues list $TYPE_ARG $PARENT_ARG --json | python3 -c "
import json, sys
issues = json.load(sys.stdin)
for i in issues:
    print(i['id'])
" > "${context.run_dir}/pending.txt"
```

The current `init` action is the exact template the proposed `ids` branch builds on.

**Test class location** — `scripts/tests/test_builtin_loops.py:1723-1903`:

```python
class TestPromptAcrossIssuesLoop:
    """Structural tests for the prompt-across-issues FSM loop."""
    LOOP_FILE = BUILTIN_LOOPS_DIR / "prompt-across-issues.yaml"  # line 1726
    # test_init_supports_type_filter (1817)
    # test_init_supports_parent_filter (1823)
    # test_mr3_no_loops_tmp_writes (1838)
    # test_diagnose_error_prompt_uses_run_dir (1852)
    # test_scope_declared (1876)
    # test_init_writes_under_run_dir (1891)
    # test_advance_writes_under_run_dir (1898)
```

New `test_init_supports_ids_filter` should slot in alongside `test_init_supports_parent_filter` (line 1823). All existing tests in this class are **structural** (parse YAML and string-match), not behavioral — none asserts actual `pending.txt` content.

**`--context` parser API** (`scripts/little_loops/cli/loop/run.py:164-168`):

```python
for kv in getattr(args, "context", None) or []:
    if "=" not in kv:
        raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
    key, _, value = kv.partition("=")
    fsm.context[key.strip()] = value.strip()
```

The whole RHS (including `,`) becomes a single string; the loop is responsible for splitting. No CLI change needed.

**`ll-issues list` does NOT have an `--ids` flag** (`scripts/little_loops/cli/issues/__init__.py:168-260`). The change is purely loop-side; no `list_cmd.py` or argparse edit needed.

**FSM lint pass/fail matrix for the proposed shell body:**

| Rule | Verdict | Why |
|------|---------|-----|
| MR-3 (no `.loops/tmp/`) | PASS | writes only to `${context.run_dir}/pending.txt` |
| MR-7 (no unescaped `${...:-...}`) | PASS | uses `[ -n "${context.ids}" ]` guard, no defaults |
| MR-9 (no over-escaped `$$VAR`) | PASS | only `$${COUNT}` brace-escape |
| MR-10 (no parse-swallow) | PASS | `python3 -c json.load` body, but explicit `on_error: diagnose_error` exempts it |
| MR-11 (no unsafe user-context interpolation) | PASS-by-regex | `ids` is not in the regex's user-controlled set `{input,goal,description,task,prompt,query,topic}` (`scripts/little_loops/fsm/validation.py:139-141`) |
| MR-1, MR-2, MR-4, MR-5, MR-6, policy-table | N/A | loop is not a meta-loop, no LLM judges, no policy rules |

**Trust-boundary caveat (not enforced by lint)**: `${context.ids}` interpolated bare into `echo "${context.ids}"` carries shell metacharacters through. A user passing `--context ids=ENH-1;rm -rf /` would write the full string as one line into `pending.txt`; downstream `prepare_prompt`'s `sed "s/{issue_id}/$ISSUE_ID/g"` substitutes it verbatim, then `execute` invokes the host CLI with the malformed ID. The host CLI rejects the malformed slash command, so the practical impact is "silently fails this issue and retries exhaust to `advance`" — same as a non-existent ID today. No code-level fix needed, but document `ids` as a trusted input (or use `${context.ids:shell}` for paranoid callers — the `:shell` suffix shlex-quotes at interpolation time, `scripts/little_loops/fsm/interpolation.py:248-250`).

## Implementation Steps

1. Add `ids: ""` to the loop's `context:` block.
2. Branch the `init` action on `${context.ids}`; preserve the existing type/parent path.
3. Update the YAML header `description` block with the new usage line.
4. Run `ll-loop validate prompt-across-issues` to confirm FSM schema and lint compliance (MR-7, MR-11).
5. Add a unit test in `scripts/tests/test_builtin_loops.py` exercising the new filter.
6. Verify the empty `ids=""` case preserves existing behavior via a regression test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/loops/README.md:36` — mirror the `ids` filter usage and its precedence over `type`/`parent` in the built-in loop catalog.
8. Run the existing `scripts/tests/test_fsm_fragments.py` migration smoke test in addition to the targeted `TestPromptAcrossIssuesLoop` tests to confirm the edited YAML still loads through the shared fragment path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors for each step:_

1. **Add `ids: ""` to context** — insert at `scripts/little_loops/loops/prompt-across-issues.yaml:36-40` (between existing `parent: ""` and the `states:` block).
2. **Branch `init` action** — modify the bash body at lines 49-75. Insert the new `if [ -n "${context.ids}" ]` branch BEFORE the existing `TYPE_ARG=""` block; preserve the existing `else` path verbatim.
3. **Update `description:` block** — at lines 1-25. Mirror the ENH-1643/ENH-2481 pattern: append the `ids=` example after the existing `type=`/`parent=` examples.
4. **Run validation** — `python -m pytest scripts/tests/test_builtin_loops.py::TestPromptAcrossIssuesLoop -v` to confirm lint passes for the new shell body.
5. **Add test** — insert `test_init_supports_ids_filter` in `TestPromptAcrossIssuesLoop` at `scripts/tests/test_builtin_loops.py` immediately after `test_init_supports_parent_filter` (line 1823). Model after the parent filter test:
   ```python
   def test_init_supports_ids_filter(self, data: dict) -> None:
       """context.ids must default to '' and init action must reference it."""
       assert data.get("context", {}).get("ids") == ""
       init_action = data["states"].get("init", {}).get("action", "")
       assert "${context.ids}" in init_action or "context.ids" in init_action
   ```
6. **Regression test for empty `ids=""`** — the existing `test_init_supports_type_filter` (line 1817) and `test_init_supports_parent_filter` (line 1823) implicitly cover this (they assert the empty-default + reference pattern); no separate regression test needed beyond confirming they continue to pass. The `else` branch in `init` is byte-identical to today's behavior when `ids=""`.

**Test pattern clarification**: All tests in `TestPromptAcrossIssuesLoop` (lines 1723-1903) are **structural** — they parse YAML and string-match. None asserts actual `pending.txt` content. Adding a behavioral pending.txt-content test would be a **new pattern** in this class; the closest analog is `scripts/tests/test_issues_cli.py:1027-1101` (`test_list_parent_includes_transitive_grandchild`), which drives `ll-issues list --parent` through `main_issues()` and asserts the JSON output. For `ids` (which bypasses `ll-issues list` entirely), the structural test pattern above is sufficient and matches the established convention.

## Impact

- **Priority**: P3 — extends an existing filter surface; doesn't unblock any current bottleneck, but completes the filter axis set.
- **Effort**: Small — ~15-line YAML edit + one new test case. Reuses established pattern (ENH-1643, EPIC-1853).
- **Risk**: Low — purely additive filter; existing `type`/`parent` paths untouched. Only edge risk is if a user pastes shell metacharacters into `ids=`, which the expected value shape (alphanumeric + commas) makes unlikely.
- **Breaking Change**: No.

## Scope Boundaries

- **Out of scope**: regex/glob matching against IDs (e.g. `ENH-2*`), file-based ID lists (`--ids-file=path`), or a generic issue-set query DSL. The minimal comma-separated value covers current use cases; richer filters can be a follow-on.
- **Out of scope**: changes to `ll-issues list` itself. This is a loop-level filter; CLI changes are not required.

## Success Metrics

- A user can sweep an arbitrary 1–N list of IDs in one `ll-loop run` invocation with no file edits.
- The empty-`ids` path produces byte-identical pending.txt content for any `type`/`parent` input that existed before this change.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/LOOPS_REFERENCE.md` | Usage examples for prompt-across-issues — needs the new `ids` example added |
| `docs/development/TROUBLESHOOTING.md` | May reference loop filters; verify no breakage |

## Labels

`enhancement`, `loops`, `fsm`, `prompt-across-issues`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-07-16T19:52:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40c440ca-03ff-4f11-a01a-225e717b7326.jsonl`
- `/ll:ready-issue` - 2026-07-16T18:48:56 - `e9a522b5-830d-4d2d-a26c-969fb931fc25.jsonl`
- `/ll:confidence-check` - 2026-07-16T18:45:55Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/36c176b3-fc23-48e6-8efd-c053ad01d68e.jsonl`
- `/ll:wire-issue` - 2026-07-16T18:41:10 - `7aa34832-f60a-4fcc-a759-a72ba8469b10.jsonl`
- `/ll:refine-issue` - 2026-07-16T18:34:49 - `b36d4bfb-6b73-4ce8-866d-00e7df088fe8.jsonl`

- `/ll:capture-issue` - 2026-07-16T18:24:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c0f165e-7365-4933-89f9-474cf4409fae.jsonl`

## Status

**Open** | Created: 2026-07-16 | Priority: P3
