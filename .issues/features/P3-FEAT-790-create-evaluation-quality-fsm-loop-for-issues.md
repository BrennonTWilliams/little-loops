---
id: FEAT-790
type: FEAT
priority: P3
status: active
discovered_date: 2026-03-16
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 78
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

1. Create `loops/evaluation-quality.yaml`.
2. **sample state** (shell): Use `ll-issues list --format json` with inline Python to compute: `total_active`, `scored`, `unscored`, `unformatted`, `avg_confidence_score`, `avg_outcome_confidence`, `below_threshold` count. Also call `ll-history summary` for completion velocity.
3. **evaluate_code state** (shell): Read `test_cmd` from `.claude/ll-config.json` (same pattern as `fix-quality-and-tests.yaml`). Run lint (`ruff check`) separately from tests to get independent signals.
4. **score state** (prompt): Structured scoring prompt with exact output format — `SCORES:` block with `issue_quality`, `code_health`, `backlog_health`, `overall`, and `PRIMARY_CONCERN:` tag. Use `output_contains` on `PRIMARY_CONCERN: NONE` to route.
5. **route_* states** (evaluate): Chain of `output_contains` checks on `captured.scores.output` — same pattern as `backlog-flow-optimizer.yaml`'s route chain.
6. **remediate_* states** (prompt): Each delegates to an existing loop via subprocess (`ll-loop run <name>`) or prompt. Keep timeouts generous (600s) since sub-loops are long.
7. **report state** (prompt): Writes markdown report to `.loops/quality-report-$(date +%Y-%m-%d).md`. If prior reports exist in `.loops/`, compute trend direction (↑↓→) per dimension.
8. Set `max_iterations: 5` (diagnostic loop, not iterative fixer), `timeout: 3600`.

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
- `loops/issue-refinement.yaml` — `ll-issues list --json` → Python3 inline classifier; `exit_code` evaluate with `sys.exit(1)` to signal "work remains"
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

## Session Log
- `/ll:refine-issue` - 2026-03-16T23:24:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2f41b047-87a9-4dc6-bd79-b70fcba93e87.jsonl`
- `/ll:format-issue` - 2026-03-16T23:15:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/03ef4a48-cdf1-402c-a6f3-262d76f4c071.jsonl`
- `/ll:capture-issue` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f7bf6f5-8d0a-49aa-a2dc-02169a6d3f97.jsonl`
