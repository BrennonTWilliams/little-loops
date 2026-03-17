---
id: FEAT-790
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-16
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 88
---

# FEAT-790: Create evaluation-quality FSM Loop for Issues

## Summary

Add a `loops/evaluation-quality.yaml` FSM loop that performs a multi-dimensional quality health check across issue quality (confidence scores, format status), code quality (test/lint), and backlog health (size, velocity), produces a scored report, routes to targeted remediation loops when thresholds are breached, and terminates with a persisted quality snapshot. Designed to run periodically (before sprint planning or weekly).

## Current Behavior

No unified quality health check loop exists. Developers must run individual remediation tools (`/ll:confidence-check --all`, `fix-quality-and-tests`, `backlog-flow-optimizer`) independently and interpret the results themselves. There is no consolidated health report, no cross-dimension scoring, and no automated routing to the appropriate remediation loop based on the primary concern.

## Context

Derived from the [Agent-Skills-for-Context-Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering) repo's `evaluation` skill, which identifies that 95% of performance variance is explained by: token usage (~80%), tool calls (~10%), and model choice (~5%). The key adaptation: in little-loops, "performance" maps to issue quality and implementation outcome predictability — measured by confidence scores vs. actual completion rates.

The loop is designed as a **diagnostic-and-delegate** pattern, not a fix-it loop. It measures, scores, identifies the primary concern, delegates remediation to existing focused loops (`issue-refinement`, `fix-quality-and-tests`, `backlog-flow-optimizer`), and saves a health snapshot report.

## Use Case

**Who**: A developer preparing for sprint planning or reviewing project health.

**Context**: Issues have been accumulating over time. Some are unformatted, some have low confidence scores, code quality may have drifted, and backlog distribution might be skewed. Rather than running each remediation loop blindly, the developer wants a single loop that measures everything and tells them what needs attention most.

**Goal**: Run `ll-loop run evaluation-quality` and get a scored health report with the primary concern identified and remediation triggered.

**Outcome**: A `quality-report-YYYY-MM-DD.md` file in `.loops/` with per-dimension scores, primary concern identified, and top 3 remediation recommendations. If a primary concern is found, the relevant remediation loop is invoked before the report is written.

## Expected Behavior

```
sample → evaluate_code → score → route_action → [remediate_issues | remediate_code | remediate_backlog | report] → done
```

1. **sample** (shell): Collect issue quality metrics via `ll-issues list --format json` — count active/scored/unscored/unformatted, compute avg confidence scores, identify below-threshold issues.
2. **evaluate_code** (shell): Run test suite + lint, pipe results to `.loops/tmp/eval-test-results.txt`.
3. **score** (prompt): LLM synthesizes signals into per-dimension scores (0-100) and emits a structured `SCORES:` block with `PRIMARY_CONCERN` tag.
4. **route_action** (evaluate): Routes on `PRIMARY_CONCERN: NONE` → `report`, otherwise routes to the appropriate remediation state.
5. **remediate_issues** (prompt): Invokes `issue-refinement` loop (or `ll:confidence-check --all --auto`).
6. **remediate_code** (prompt): Invokes `fix-quality-and-tests` loop.
7. **remediate_backlog** (prompt): Invokes `backlog-flow-optimizer` loop.
8. **report** (prompt): Writes `.loops/quality-report-$(date +%Y-%m-%d).md` with scores, trends (if prior reports exist), and top 3 action items.
9. **done** (terminal).

## Implementation Steps

1. Create `loops/evaluation-quality.yaml` with required top-level fields: `name: evaluation-quality`, `initial: sample`, `states:`, `max_iterations: 5`, `timeout: 3600`.
2. **sample state** (shell, `capture: metrics`): Use `ll-issues list --json` (flag is `--json`, not `--format json` — confirmed in `loops/issue-discovery-triage.yaml:12`) with inline Python. Also call `ll-history summary 2>/dev/null || echo "(no history available)"` for velocity. Set `next: evaluate_code`.
3. **evaluate_code state** (shell, `capture: code_results`): Read `test_cmd` from `.claude/ll-config.json` using exact pattern from `fix-quality-and-tests.yaml:64-81`. Run lint (`ruff check`) separately with `|| true`. Set `next: score`.
4. **score state** (prompt, **must include `capture: scores`**): Structured scoring prompt referencing `${captured.metrics.output}`, `${captured.code_results.output}`, and `${context.*_threshold}` values. Output format: `SCORES:` block + `PRIMARY_CONCERN: <NONE|ISSUES|CODE|BACKLOG>`. Set `next: route_action`.
5. **route_action / route_issues / route_code states** (evaluate, no `action:`): Chain of `output_contains` checks on `source: "${captured.scores.output}"`. Each needs `on_yes`, `on_no`, and **`on_error: done`** (required — bare route states hang without it; see `backlog-flow-optimizer.yaml:68`).
6. **remediate_* states** (prompt, `timeout: 600`): Each delegates to an existing loop via `ll-loop run <name>`. Set `next: prepare_report`.
7. **prepare_report state** (shell, `capture: report_path`): **Required intermediate state** — `$(date +%Y-%m-%d)` does NOT expand in prompt states (shell substitution is unavailable in prompt context). Compute path via: `echo ".loops/quality-report-$(date +%Y-%m-%d).md"`. Set `next: report`.
8. **report state** (prompt): Reference `${captured.report_path.output}` for the filename. Include scores from `${captured.scores.output}` and trend analysis if prior reports exist. Set `next: done`.
9. **done state**: Must have `terminal: true` — required by `ll-loop validate` (`validation.py:304-311`; hard error if absent).
10. Add `context:` block at top level: `issue_quality_threshold: 70`, `code_health_threshold: 80`, `backlog_health_threshold: 75`.

## API/Interface

New file: `loops/evaluation-quality.yaml`

Invoked via:
```bash
ll-loop run evaluation-quality
```

Produces: `.loops/quality-report-YYYY-MM-DD.md`

Reads (no changes): `.claude/ll-config.json` (for `test_cmd`), `.issues/` (via `ll-issues list`), `.loops/quality-report-*.md` (prior reports for trend calculation).

## Motivation

- **Gap**: No existing loop provides a unified health view across issues + code + backlog. The closest is `backlog-flow-optimizer`, but it only covers backlog bloat, not code quality or issue scoring quality.
- **Sprint hygiene**: Running this before `ll:create-sprint` ensures the issues being selected are high-quality and the codebase is clean.
- **LLM-as-judge pattern**: The repo's `evaluation` skill recommends combining outcome-focused scoring with LLM-as-judge for scalability. The `score` state implements this directly.

## Acceptance Criteria

- [ ] `loops/evaluation-quality.yaml` passes `ll-loop validate evaluation-quality`
- [ ] `sample` state correctly reports `total_active`, `scored`, `unscored`, and `avg_confidence_score` from `.issues/`
- [ ] `score` state emits a valid `SCORES:` block with all four fields and `PRIMARY_CONCERN` tag
- [ ] Routes correctly: `PRIMARY_CONCERN: NONE` → `report`, others → appropriate remediation state
- [ ] `report` state writes a valid markdown file to `.loops/quality-report-YYYY-MM-DD.md`
- [ ] Loop completes in `max_iterations: 5` under normal conditions
- [ ] Loop terminates cleanly even if `ll-history summary` returns no data (graceful fallback)

## Integration Map

### Files to Create
- `loops/evaluation-quality.yaml` — the FSM loop definition

### Files to Read (no changes)
- `.claude/ll-config.json` — `project.test_cmd`; read via Python: `cfg.get('project', {}).get('test_cmd', 'pytest')` (exact pattern from `loops/fix-quality-and-tests.yaml:64-81`)
- `.issues/` — via `ll-issues list --json` (note: flag is `--json`, not `--format json` — matches `loops/issue-refinement.yaml` usage)

### Files Written
- `.loops/quality-report-YYYY-MM-DD.md` — quality health snapshot

### Loops Delegated To
- `loops/issue-refinement.yaml` — invoked by `remediate_issues` state via `ll-loop run issue-refinement`
- `loops/fix-quality-and-tests.yaml` — invoked by `remediate_code` state via `ll-loop run fix-quality-and-tests`
- `loops/backlog-flow-optimizer.yaml` — invoked by `remediate_backlog` state via `ll-loop run backlog-flow-optimizer`

### Similar Patterns
- `loops/backlog-flow-optimizer.yaml` — `output_contains` route chain (each `on_no` falls to next route state); prompt emits single tag line; route terminates at `done` when no match; `context:` block for thresholds
- `loops/issue-discovery-triage.yaml` — `ll-issues list --json` → Python3 inline classifier; `exit_code` evaluate with `sys.exit(1)` to signal "work remains"
- `loops/fix-quality-and-tests.yaml:64-81` — exact `test_cmd` extraction pattern (Python3 reads `.claude/ll-config.json`); `tee .loops/tmp/ll-test-results.txt` for capturing output; `set -o pipefail`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`test_cmd` extraction pattern** (copy-paste from `fix-quality-and-tests.yaml:64-81`):
```yaml
evaluate_code:
  action_type: shell
  timeout: 600
  action: |
    CMD=$(python3 -c "
    import json, pathlib
    p = pathlib.Path('.claude/ll-config.json')
    cfg = json.loads(p.read_text()) if p.exists() else {}
    print(cfg.get('project', {}).get('test_cmd', 'pytest'))
    ")
    mkdir -p .loops/tmp
    set -o pipefail
    eval "$CMD" 2>&1 | tee .loops/tmp/eval-test-results.txt
    # Also run lint separately
    ruff check scripts/ 2>&1 | tee .loops/tmp/eval-lint-results.txt || true
  capture: code_results
  next: score
```

**`ll-issues list` + Python classifier pattern** (from `loops/issue-refinement.yaml`):
```yaml
sample:
  action_type: shell
  action: |
    ll-issues list --json | python3 -c "
    import json, sys
    issues = json.load(sys.stdin)
    total = len(issues)
    scored = sum(1 for i in issues if i.get('confidence_score'))
    unscored = total - scored
    avg_conf = sum(i.get('confidence_score', 0) for i in issues if i.get('confidence_score')) / max(scored, 1)
    print(f'total_active: {total}')
    print(f'scored: {scored}')
    print(f'unscored: {unscored}')
    print(f'avg_confidence_score: {avg_conf:.1f}')
    "
    ll-history summary 2>/dev/null || echo "(no history available)"
  capture: metrics
  next: evaluate_code
```

**`output_contains` route chain** (from `backlog-flow-optimizer.yaml:61-84`):
```yaml
route_action:
  evaluate:
    type: output_contains
    source: "${captured.scores.output}"
    pattern: "PRIMARY_CONCERN: NONE"
  on_yes: report
  on_no: route_issues

route_issues:
  evaluate:
    type: output_contains
    source: "${captured.scores.output}"
    pattern: "PRIMARY_CONCERN: ISSUES"
  on_yes: remediate_issues
  on_no: route_code

route_code:
  evaluate:
    type: output_contains
    source: "${captured.scores.output}"
    pattern: "PRIMARY_CONCERN: CODE"
  on_yes: remediate_code
  on_no: remediate_backlog   # fallback — backlog is the remaining case
```

**Subprocess loop delegation pattern** (prompt state approach — no direct subprocess invocation in existing loops; delegate via prompt):
```yaml
remediate_issues:
  action_type: prompt
  timeout: 600
  action: |
    Run the issue-refinement loop to address low-confidence issues:
    ```
    ll-loop run issue-refinement
    ```
    Wait for completion before proceeding.
  next: report
```

**Structured scoring prompt** (for `score` state):
```
Synthesize the following metrics into a quality health report.

Metrics:
${captured.metrics.output}

Code results:
${captured.code_results.output}

Output a structured block followed by a PRIMARY_CONCERN tag:

SCORES:
issue_quality: <0-100>
code_health: <0-100>
backlog_health: <0-100>
overall: <0-100>

PRIMARY_CONCERN: <NONE|ISSUES|CODE|BACKLOG>
```

**Critical: report file dated filename** — `$(date +%Y-%m-%d)` does NOT expand inside prompt state action text. Use a shell state to compute the path and capture it, then reference in the report prompt:
```yaml
prepare_report:
  action_type: shell
  action: |
    mkdir -p .loops
    echo ".loops/quality-report-$(date +%Y-%m-%d).md"
  capture: report_path
  next: report

report:
  action_type: prompt
  timeout: 300
  action: |
    Write a quality health report to `${captured.report_path.output}`.
    ...
  next: done
```
Source: no existing loop uses `$(date ...)` in a prompt state — all dynamic paths use shell states or static `${context.X}` values.

**Critical: `score` state must include `capture: scores`** — route states reference `${captured.scores.output}` (see `route_action` state). Without `capture: scores` on the `score` prompt state, interpolation will fail at runtime.

**Critical: `done` state must have `terminal: true`** — `ll-loop validate` requires at least one terminal state (`validation.py:304-311`). Without it, validation fails with error: "No terminal state found."

**Critical: route states need `on_error:` routing** — bare route states (no `action:`) that fail evaluation will hang without `on_error:`. Pattern from `backlog-flow-optimizer.yaml:66`: use `on_error: done` as fallback.

**Required top-level YAML fields** (`validation.py:443-449` — hard errors if missing):
- `name:` — loop identifier string
- `initial:` — name of the first state
- `states:` — dict of all states

Optional but recommended for this loop:
```yaml
name: evaluation-quality
description: "Multi-dimensional quality health check for issues, code, and backlog"
initial: sample
max_iterations: 5
timeout: 3600
on_handoff: spawn
```

**`context:` block for score thresholds** (referenced in `score` state prompt via `${context.X}`):
```yaml
context:
  issue_quality_threshold: 70
  code_health_threshold: 80
  backlog_health_threshold: 75
```
Pattern: `sprint-build-and-validate.yaml:7-10` uses `${context.readiness_threshold}` and `${context.outcome_threshold}` in prompt action bodies.

**`ll-loop validate` checks summary** — what must pass for acceptance criteria:
- `name`, `initial`, `states` all present
- `initial` value exists in `states` dict
- At least one state has `terminal: true`
- All `on_yes`/`on_no`/`on_error`/`next` targets exist in `states`
- All `output_contains` evaluates have `pattern:`
- No state missing all transitions (each needs `on_yes`/`on_no`/`next`/`terminal` or `route`)
- `max_iterations > 0`, `timeout > 0`

## Impact

- **Priority**: P3 — Useful sprint-hygiene loop; not blocking
- **Effort**: Small — single YAML file, no code changes
- **Risk**: Low — additive, delegates to existing loops for remediation
- **Breaking Change**: No

## Labels

`loop`, `evaluation`, `issues`, `quality`, `fsm`

---

## Status

- [ ] Not started

## Verification Notes

Verified 2026-03-16 against codebase. Core guidance confirmed valid. Two line reference corrections applied:
- Step 2 cited `loops/issue-refinement.yaml:14` for `ll-issues list --json` — corrected to `loops/issue-discovery-triage.yaml:12`. Line 14 of `issue-refinement.yaml` uses `ll-issues refine-status --json` (different subcommand). The `list --json` pattern is in `issue-discovery-triage.yaml`.
- Step 5 cited `backlog-flow-optimizer.yaml:66` for `on_error: done` — corrected to line 68. Line 66 is `on_yes: close_dead_weight`; `on_error: done` is at line 68.
- `validation.py:304-311` (terminal state check) and `validation.py:443-449` (required fields) confirmed accurate.
- `fix-quality-and-tests.yaml:64-81` test_cmd pattern confirmed accurate (state is named `check-tests`, not `evaluate_code`, but the pattern is valid).

## Session Log
- `/ll:verify-issues` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6845dcb9-5d3d-4e87-aaff-4382e49ef209.jsonl`
- `/ll:verify-issues` - 2026-03-17T03:55:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5cd3087-827b-4f96-b97c-87f26d20ce04.jsonl`
- `/ll:refine-issue` - 2026-03-17T03:44:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4bff4ea7-c43c-4570-a757-562d16159166.jsonl`
- `/ll:refine-issue` - 2026-03-16T23:24:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f41b047-87a9-4dc6-bd79-b70fcba93e87.jsonl`
- `/ll:format-issue` - 2026-03-16T23:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03ef4a48-cdf1-402c-a6f3-262d76f4c071.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f7bf6f5-8d0a-49aa-a2dc-02169a6d3f97.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5d2a676-504a-430c-a0d5-b6a5a25cb87d.jsonl`
