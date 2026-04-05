---
id: ENH-950
type: ENH
priority: P3
status: open
discovered_date: 2026-04-04
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-950: Add ll- CLI Command State Fragments to lib/

## Summary

Create a new `scripts/little_loops/loops/lib/cli.yaml` fragment library that provides one named fragment per major ll- CLI tool (`ll-auto`, `ll-deps`, `ll-history`, `ll-loop`, `ll-parallel`, `ll-workflows`, `ll-check-links`, `ll-issues`, `ll-messages`, `ll-sprint`). Loop authors currently repeat boilerplate CLI invocations and exit-code evaluation across every loop that calls these tools; fragments give them a single, tested starting point for each tool.

## Current Behavior

Loop authors who want to call `ll-issues`, `ll-auto`, `ll-check-links`, or other ll- CLI tools must write the full `action_type: shell` + `action: "ll-<tool> ..."` + `evaluate: {type: exit_code}` block from scratch for every state. The same invocation patterns are already scattered across built-in loops (`docs-sync.yaml`, `eval-driven-development.yaml`, `issue-refinement.yaml`, `backlog-flow-optimizer.yaml`, etc.) with minor variations and no canonical form.

`lib/common.yaml` provides generic type-pattern fragments (`shell_exit`, `llm_gate`, etc.) but has no tool-specific fragments that pre-fill the `action` field.

## Expected Behavior

A new `lib/cli.yaml` file ships alongside `lib/common.yaml`:

```yaml
# lib/cli.yaml — reusable state fragments for ll- CLI tools.
# Import:
#   import:
#     - lib/cli.yaml        # tool-specific fragments
#     - lib/common.yaml     # type-pattern fragments (optional, if also needed)

fragments:
  ll_auto:
    action_type: shell
    action: "ll-auto"
    evaluate:
      type: exit_code

  ll_issues_list:
    action_type: shell
    action: "ll-issues list --json"
    evaluate:
      type: exit_code

  ll_issues_next:
    action_type: shell
    action: "ll-issues next-action"
    evaluate:
      type: exit_code

  ll_history_summary:
    action_type: shell
    action: "ll-history summary"
    evaluate:
      type: exit_code

  ll_check_links:
    action_type: shell
    action: "ll-check-links 2>&1"
    evaluate:
      type: exit_code

  ll_messages:
    action_type: shell
    action: "ll-messages --stdout"
    evaluate:
      type: exit_code

  ll_deps:
    action_type: shell
    action: "ll-deps check"
    evaluate:
      type: exit_code

  ll_sprint_list:
    action_type: shell
    action: "ll-sprint list"
    evaluate:
      type: exit_code

  ll_parallel:
    action_type: shell
    action: "ll-parallel"
    evaluate:
      type: exit_code

  ll_workflows:
    action_type: shell
    action: "ll-workflows"
    evaluate:
      type: exit_code

  ll_loop_run:
    action_type: shell
    action: "ll-loop run ${context.loop_name}"
    evaluate:
      type: exit_code
```

Loop authors can then write:

```yaml
import:
  - lib/cli.yaml

states:
  check_links:
    fragment: ll_check_links
    on_yes: done
    on_no: fix_links

  run_auto:
    fragment: ll_auto
    action: "ll-auto --priority P1,P2 --quiet"   # caller can override action
    on_yes: done
    on_no: retry
```

## Motivation

- **Reduces copy-paste**: The same `ll-issues list --json`, `ll-auto`, and `ll-check-links` invocations appear in 5+ built-in loops. A fragment makes the canonical invocation the default.
- **Prevents flag drift**: Common flags (`--json`, `--stdout`, `2>&1`) should appear consistently; fragments encode the right defaults once.
- **Consistent with `lib/common.yaml` precedent**: Tool-specific fragments follow the same library/import pattern already established for type-pattern fragments. Keeping them in a separate file avoids bloating `common.yaml` with tool-specific details.
- **Lowers the bar for new loop authors**: Instead of looking up the exact `ll-issues next-action` invocation, a new loop author can just use `fragment: ll_issues_next`.

## Success Metrics

- `TestCliYamlFragments` test class passes: all ~10 fragments assert correct `action_type`, `evaluate.type`, and absence of `fragment:` key post-resolution
- No regression in `test_builtin_loops.py` — all existing loops remain valid after the additive change
- At least 1 built-in loop updated to use a `cli.yaml` fragment as a canonical usage example
- Loop authors can implement a state that calls any ll- tool using `fragment: ll_<tool>` without writing the full `action_type`/`action`/`evaluate` block from scratch

## Scope Boundaries

- **In scope**: New `scripts/little_loops/loops/lib/cli.yaml` fragment library; `docs/guides/LOOPS_GUIDE.md` update to document the new library; optional migration of 1–2 built-in loops as usage examples
- **Out of scope**: Forced migration of any existing loop (purely additive); changes to the FSM resolver/engine (`fsm/fragments.py`); adding fragments for CLI tools not already shipped in little-loops; modifications to `lib/common.yaml`; changes to import semantics or fragment deep-merge behavior

## Proposed Solution

1. Create `scripts/little_loops/loops/lib/cli.yaml` with one fragment per major ll- CLI tool.
2. For tools with multiple useful subcommand shapes (e.g., `ll-issues list`, `ll-issues next-action`, `ll-issues show`), add separate fragments with descriptive suffixes (`ll_issues_list`, `ll_issues_next`, `ll_issues_show`).
3. For tools with parameterized invocations (e.g., `ll-loop run <name>`), use `${context.*}` interpolation in the `action` field.
4. Update `docs/guides/LOOPS_GUIDE.md` to document the new library alongside `lib/common.yaml`.

Fragment merging semantics are already correct: callers can override `action` or add flags via deep-merge (state keys win), so a fragment is always a starting point, never a constraint.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/lib/cli.yaml` — new fragment library with ~10–12 fragments

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — add `lib/cli.yaml` to the "Reusable State Fragments" section; show import example and fragment table
- `scripts/little_loops/loops/README.md` — add `lib/cli.yaml` to the lib directory listing if present

### Candidate Built-in Loop Migrations (optional)
- `scripts/little_loops/loops/docs-sync.yaml` — `ll-check-links 2>&1` → `fragment: ll_check_links`
- `scripts/little_loops/loops/eval-driven-development.yaml` — `ll-auto --priority P1,P2 --quiet` → `fragment: ll_auto` + `action:` override; also `ll-loop run ${context.harness_name}` → `fragment: ll_loop_run`
- `scripts/little_loops/loops/issue-refinement.yaml` — `ll-issues next-action --skip "$(cat ...)"` → `fragment: ll_issues_next` + `action:` override
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml` — `ll-history summary 2>/dev/null || echo "..."` embedded in multi-line shell block → standalone `fragment: ll_history_summary` state
- `scripts/little_loops/loops/evaluation-quality.yaml` — `ll-issues list --json | python3 -c "..."`, `ll-history summary`, and three `ll-loop run` calls
- `scripts/little_loops/loops/prompt-across-issues.yaml` — `ll-issues list --json | python3 -c "..."` and `ll-loop run`
- `scripts/little_loops/loops/issue-discovery-triage.yaml` — `ll-issues list --json 2>/dev/null | python3 -c "..."` (two occurrences)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — `ll-sprint list 2>/dev/null | grep -q .` → `fragment: ll_sprint_list`
- `scripts/little_loops/loops/outer-loop-eval.yaml` — `ll-loop show ${context.loop_name}` → `fragment: ll_loop_show` (if added); `ll-loop run` → `fragment: ll_loop_run`
- `scripts/little_loops/loops/examples-miner.yaml` — `ll-messages --skill ... --examples-format ...` → `fragment: ll_messages` + `action:` override
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `ll-issues next-issue` and `ll-issues show` calls

Migration is optional; fragments are additive and all existing loops remain valid.

### Tests
- `scripts/tests/test_fsm_fragments.py` — add a new `TestCliYamlFragments` class (matching `TestCommonYamlNewFragments` pattern); verify each fragment resolves correctly from `lib/cli.yaml` via the `import:` path; assert `action_type`, `evaluate.type`, and that `fragment:` key is absent post-resolution
- `scripts/tests/test_builtin_loops.py` — passes without modification (no forced migration)

#### Test Class Implementation Notes

`_write_lib()` (line 301) hardcodes `lib_dir / "common.yaml"` as the output filename — it cannot be reused for `cli.yaml`. The `TestCliYamlFragments` class should follow the **`TestCommonYamlNewFragments` pattern** (lines 500–588), not `TestResolveFragmentsImport`:

```python
class TestCliYamlFragments:
    @staticmethod
    def _load_cli_yaml() -> dict:
        import yaml
        lib_path = Path(__file__).parent.parent / "little_loops" / "loops" / "lib" / "cli.yaml"
        with open(lib_path) as f:
            return yaml.safe_load(f)

    def test_ll_auto_defined_in_cli_yaml(self) -> None: ...
    def test_ll_auto_has_correct_action_type(self) -> None: ...
    def test_ll_auto_has_correct_evaluate_type(self) -> None: ...
    # ... one set per representative fragment
    def test_ll_auto_resolves_from_real_cli_yaml(self, tmp_path: Path) -> None:
        # Uses loops_dir (real package dir) with "import": ["lib/cli.yaml"]
        # and resolve_fragments(raw, loops_dir)
        ...
```

For import-based round-trip tests, pass `loops_dir` (the real `loops/` package directory) as `loop_dir` to `resolve_fragments`, mirroring how `test_llm_gate_resolves_from_real_common_yaml` works.

### Similar Patterns
- `scripts/little_loops/loops/lib/common.yaml` — direct precedent; match its comment style ("State must supply: ..." convention)
- `scripts/tests/test_fsm_fragments.py:500` (`TestCommonYamlNewFragments`) — correct test class pattern for `TestCliYamlFragments` (uses `_load_cli_yaml()` static method loading real file from disk, not `_write_lib()`)
- `scripts/tests/test_fsm_fragments.py:301` (`_write_lib` in `TestResolveFragmentsImport`) — note: hardcodes `"common.yaml"` filename; cannot be reused for cli.yaml tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — confirmed exact `action:` strings from existing built-in loops:_

| Fragment | Confirmed `action:` (from loop) | Source loop |
|---|---|---|
| `ll_check_links` | `"ll-check-links 2>&1"` | `docs-sync.yaml:22` |
| `ll_auto` | `ll-auto` (bare; callers add `--priority P1,P2 --quiet` via override) | `eval-driven-development.yaml:21` |
| `ll_issues_list` | `"ll-issues list --json"` (`--json` appears in 4+ loops consistently) | `evaluation-quality.yaml:21` |
| `ll_issues_next` | `"ll-issues next-action"` (bare; `--skip "..."` added via override in `issue-refinement.yaml:16`) | `issue-refinement.yaml:16` |
| `ll_issues_next_issue` | `"ll-issues next-issue"` | `refine-to-ready-issue.yaml:18` |
| `ll_history_summary` | `"ll-history summary"` (bare; `2>/dev/null \|\| echo "(no history available)"` is caller logic) | `backlog-flow-optimizer.yaml:30` |
| `ll_sprint_list` | `"ll-sprint list"` | `sprint-build-and-validate.yaml:40` |
| `ll_loop_run` | `"ll-loop run ${context.loop_name}"` | `eval-driven-development.yaml:38`, `evaluation-quality.yaml:130` |
| `ll_messages` | `"ll-messages --stdout"` (bare; callers add `--skill`, `--examples-format`, etc.) | `examples-miner.yaml:31` |

**Verified ll-issues subcommands**: `next-id`, `list`, `search`, `count`, `show`, `sequence`, `impact-effort`, `refine-status`, `append-log`, `next-action`, `next-issue`, `next-issues` (`scripts/little_loops/cli/issues/__init__.py:80–411`)

**Verified ll-history subcommands**: `summary`, `analyze`, `export` (`scripts/little_loops/cli/history.py:12`)

**ll-messages**: no subcommands; key flags are `--stdout`, `--skill`, `--examples-format`, `--context-window`, `--since` (`scripts/little_loops/cli/messages.py:11`)

### Configuration
- N/A — library paths are specified in loop YAML `import:` lists; no config changes needed

## Implementation Steps

1. **Create `lib/cli.yaml`** at `scripts/little_loops/loops/lib/cli.yaml` with fragment definitions for all 10 requested ll- CLI tools; include comment blocks documenting required caller fields (`on_yes`, `on_no`, any context vars)
2. **Add tests** in `scripts/tests/test_fsm_fragments.py` — new `TestCliYamlFragments` class using `_write_lib()` + `load_and_validate` or direct `resolve_fragments` calls; assert field values for representative fragments
3. **Update docs** in `docs/guides/LOOPS_GUIDE.md` — add `lib/cli.yaml` to the fragment libraries section with an import example and fragment table
4. **Optional migration** — update 1–2 built-in loops as usage examples

## API/Interface

N/A — no Python API or CLI argument changes; new behavior is YAML-configuration only. Loop authors opt in by adding `lib/cli.yaml` to their loop's `import:` list; no existing interface is modified.

## Impact

- **Priority**: P3 — directly reduces loop authoring friction; commonly needed patterns have no canonical form today
- **Effort**: Small — one new YAML file + tests + doc update; no schema or engine changes
- **Risk**: Low — additive; existing loops unaffected
- **Breaking Change**: No

## Related Key Documentation

- [`docs/guides/LOOPS_GUIDE.md`](../../docs/guides/LOOPS_GUIDE.md) — Reusable State Fragments section; needs `lib/cli.yaml` added
- [`scripts/little_loops/loops/lib/common.yaml`](../../scripts/little_loops/loops/lib/common.yaml) — existing fragment library; model comment style and structure after this file
- [`scripts/little_loops/fsm/fragments.py`](../../scripts/little_loops/fsm/fragments.py) — resolver; no changes needed, handles arbitrary library files

## Labels

`enh`, `fsm`, `loops`, `dx`, `captured`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-04-05T02:38:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49da5993-75c6-4b4d-93c4-ba9bc4ef448c.jsonl`
- `/ll:confidence-check` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7bc55c4-b62b-4d59-8a1c-6a95345cac75.jsonl`
- `/ll:refine-issue` - 2026-04-05T02:35:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95ce988b-f206-41ae-85d4-9555453395d7.jsonl`
- `/ll:format-issue` - 2026-04-05T02:31:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/640c5857-8f87-4989-9daa-c473686be6fc.jsonl`
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8e9b42f4-37e6-4e91-aec1-c44dae744686.jsonl`
