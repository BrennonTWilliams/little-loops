---
id: FEAT-1541
title: Add html-anything generalized HTML artifact harness
type: FEAT
status: done
priority: P2
captured_at: '2026-05-17T05:27:26Z'
completed_at: '2026-05-17T05:47:01Z'
discovered_date: '2026-05-17'
discovered_by: capture-issue
decision_needed: false
labels:
- feature
- loops
- eval-harness
- captured
confidence_score: 100
outcome_confidence: 79
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
relates_to:
- FEAT-1534
---

# FEAT-1541: Add html-anything generalized HTML artifact harness

## Summary

Create a generalized eval-driven-development FSM harness (`html-anything.yaml`) inspired by the [html-anything](https://github.com/nexu-io/html-anything) project. The harness supports 9+ HTML surface types (websites, emails, social cards, presentations, résumés, invoices, dashboards, components, posters) with dynamically generated scoring rubrics tailored per artifact type. The existing `html-website-generator.yaml` is too narrow — this replaces its generality gap without removing it.

## Current Behavior

`html-website-generator.yaml` hardcodes 4 scoring criteria and assumes a website surface. There is no harness for emails (requiring inline styles + table layout), social cards (requiring dimensional accuracy), résumés (requiring print safety), or other HTML artifact types.

## Expected Behavior

Running `ll-loop run html-anything "a transactional email confirming a SaaS subscription"` should:
1. Classify the artifact type from the natural language description
2. Write a `brief.md` with platform-specific constraints for that artifact type
3. Write a `rubric.md` with 4–6 artifact-appropriate criteria (e.g. `inline_styles` with threshold 7–8 for emails)
4. Drive iterative generation/refinement using that rubric
5. Pass gate: ALL_PASS only when every criterion score ≥ its individual rubric threshold

## Motivation

The html-anything project generates 75+ HTML artifact types across 9 surfaces. Encoding platform constraints in the plan state and making evaluation criteria dynamic (written by `plan` at runtime, not hardcoded in YAML) unlocks the full range of HTML surface types without requiring a separate harness per type.

## Proposed Solution

A 6-state FSM harness: `init → plan → generate → evaluate → score → done` (+ `failed` terminal).

**Key design decisions:**
- `plan` state atomically classifies artifact type, writes `brief.md`, and writes `rubric.md` — keeping all three atomic ensures the rubric always matches the classification
- `score` state reads `rubric.md` dynamically to load per-criterion thresholds; uses per-criterion thresholds (not weighted average) to prevent strong aesthetics masking broken platform constraints
- Output goes to a timestamped subdir (isolated per run, matching `svg-image-generator` pattern)
- `evaluate` state uses Playwright screenshot with graceful degradation if not installed

**Artifact types to support:** `html-email`, `html-social-card`, `html-presentation`, `html-resume`, `html-invoice`, `html-dashboard`, `html-component`, `html-poster`, `html-website`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Top-level YAML block** (from `svg-image-generator.yaml` lines 1–20):
```yaml
name: html-anything
category: harness
input_key: description
description: |
  <multi-line description>
initial: init
max_iterations: 20
timeout: 7200

context:
  description: ""             # populated from loop_input via input_key: description
  output_dir: ".loops/tmp/html-anything"
  pass_threshold: 7           # higher than svg (6) — platform constraints are binary
```

**`init` state** — exact syntax from `svg-image-generator.yaml:24-35`:
```yaml
init:
  action_type: shell
  action: |
    TS=$(date -u +%Y%m%d-%H%M%S)
    DIR="${context.output_dir}/$TS"
    mkdir -p "$DIR"
    echo "$(pwd)/$DIR"
  capture: run_dir
  next: plan
```
Subsequent states reference the timestamped dir as `${captured.run_dir.output}`.

**`evaluate` state** — include `on_error: generate` (from `svg-image-generator.yaml:89-104`); `html-website-generator.yaml` omits it and the loop dies if Playwright is absent:
```yaml
evaluate:
  action_type: shell
  action: |
    playwright screenshot "file://${captured.run_dir.output}/index.html" "${captured.run_dir.output}/screenshot.png" 2>&1 && echo "CAPTURED"
  evaluate:
    type: output_contains
    pattern: "CAPTURED"
  on_yes: score
  on_no: generate
  on_error: generate
```

**`score` state routing** — `output_contains` with `on_error: failed` (from `svg-image-generator.yaml:106-151`):
```yaml
score:
  action_type: prompt
  action: |
    Read ${captured.run_dir.output}/rubric.md to load the artifact-specific criteria and thresholds.
    Read the screenshot at ${captured.run_dir.output}/screenshot.png ...
    Score each criterion 1–10 and write to ${captured.run_dir.output}/critique.md.
    If ALL criterion scores >= their individual rubric thresholds, output exactly: ALL_PASS
    Otherwise output: ITERATE
  evaluate:
    type: output_contains
    pattern: "ALL_PASS"
  on_yes: done
  on_no: generate
  on_error: failed
```

**`done` terminal state** — use the reporting pattern (from `svg-image-generator.yaml:153-167`), not the silent pattern from `html-website-generator.yaml`:
```yaml
done:
  action_type: prompt
  action: |
    The html-anything loop has completed successfully.
    Final output files:
    - ${captured.run_dir.output}/index.html   — the generated artifact
    - ${captured.run_dir.output}/brief.md     — platform-specific constraints
    - ${captured.run_dir.output}/rubric.md    — artifact-appropriate scoring rubric
    - ${captured.run_dir.output}/critique.md  — final evaluation scores
    - ${captured.run_dir.output}/screenshot.png — last Playwright-captured render
    Report these paths to the user and confirm the artifact is ready.
  terminal: true

failed:
  terminal: true
```

**`test_builtin_loops.py`** auto-discovers all `*.yaml` files in the loops dir via `BUILTIN_LOOPS_DIR.glob("*.yaml")` (line 25). Placing `html-anything.yaml` in `scripts/little_loops/loops/` is sufficient — no manual test registration needed. The test validates YAML parsing, FSM structural validity, and presence of `description:` field.

**Rubric format** (YAML-in-markdown fenced block):
```yaml
criteria:
  - name: inline_styles
    weight: 2
    threshold: 8
    description: All styles inline on elements — no <style> blocks or external CSS.
  - name: visual_identity
    weight: 1
    threshold: 6
    description: Distinctive color palette, readable typography, branded feel.
```

## Use Case

A developer wants to generate a polished HTML email confirming a SaaS subscription. They run `ll-loop run html-anything "a transactional email confirming a SaaS subscription"` and receive a complete `index.html` in a timestamped output directory — with all styles inline, table-based layout, and a rubric score showing every email-specific criterion passed — without needing a separate email harness or manually specifying platform constraints.

## Acceptance Criteria

- `ll-loop run html-anything "<description>"` completes without error for all 9 supported artifact types
- `plan` state writes `brief.md` capturing platform-specific constraints for the classified artifact type
- `plan` state writes `rubric.md` with 4–6 criteria, each with a `name`, `weight`, `threshold`, and `description`
- `score` state reads `rubric.md` dynamically (not hardcoded criteria) and scores each criterion 1–10
- Gate passes (`done`) only when ALL criterion scores ≥ their individual rubric thresholds
- Output files (`brief.md`, `rubric.md`, `index.html`, `critique.md`) are isolated in a timestamped subdirectory under `.loops/tmp/html-anything/`
- `evaluate` state gracefully degrades (routes to `generate`) when Playwright is not installed
- For an email description, rubric includes an `inline_styles` criterion with threshold ≥ 7
- For a social card description, rubric includes a `dimensional_accuracy` criterion
- A website description produces behavior equivalent to `html-website-generator`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/README.md` — add `html-anything` row to Harness table after `svg-image-generator`
- `scripts/tests/test_builtin_loops.py` — add `"html-anything"` to `TestBuiltinLoopFiles.test_expected_loops_exist` hardcoded expected set (lines 65–112); add `TestHtmlAnythingLoop` class following `TestSvgImageGeneratorLoop` pattern
- `docs/guides/LOOPS_GUIDE.md` — add row to Harness Examples table (~line 761) and `### html-anything` subsection following `### html-website-generator` pattern (~line 772)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `html-anything.yaml` bullet to Further Reading section (lines 739–740)
- `README.md` — increment `**44 FSM loops**` to `**45 FSM loops**` (line 167)
- `CHANGELOG.md` — add `html-anything FSM Loop` bullet under `### Added` in current release section

### Files to Create
- `scripts/little_loops/loops/html-anything.yaml` — new 6-state FSM harness

### Reference Files (patterns to follow)
- `scripts/little_loops/loops/svg-image-generator.yaml` — timestamped run dir pattern (`init` state, lines 24–35)
- `scripts/little_loops/loops/html-website-generator.yaml` — critique.md format and score routing pattern

### Dependent Files (Callers/Importers)
- N/A — new file; no existing code imports this harness

### Tests
- `scripts/tests/test_builtin_loops.py` — auto-discovers `*.yaml` files via `BUILTIN_LOOPS_DIR.glob("*.yaml")` (line 25); placing `html-anything.yaml` in the loops dir is sufficient — no manual test registration needed. The test validates YAML parsing, FSM structural validity, and presence of `description:` field.
- Verify functional correctness with three manual `ll-loop run` invocations per Implementation Steps

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopFiles.test_expected_loops_exist` — **HARD BLOCK**: uses hardcoded equality set (lines 65–112) against `BUILTIN_LOOPS_DIR.glob("*.yaml")`; adding `html-anything.yaml` without updating this set fails with `AssertionError: {'html-anything'} != set()`. Must add `"html-anything"` to the expected set.
- `scripts/tests/test_builtin_loops.py` `TestHtmlAnythingLoop` — **NEW** test class to write, following `TestSvgImageGeneratorLoop` pattern; key assertions: `name == "html-anything"`, `initial == "init"`, `input_key == "description"`, 7 required states (`init, plan, generate, evaluate, score, done, failed`), `init` has `capture: run_dir` + `$(pwd)`, `evaluate` routes `on_error: generate`, `score` uses `pattern: "ALL_PASS"` and routes `on_error: failed`, `output_dir == ".loops/tmp/html-anything"`, `rubric.md` referenced in score action, `brief.md` + `rubric.md` in plan action

### Documentation
- `scripts/little_loops/loops/README.md` — Harness table row (covered under Files to Modify)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Harness Examples table (~line 761) and GAN-style prose (~line 770) enumerate harness loops by name; add table row + `### html-anything` subsection following `### html-website-generator` / `### svg-image-generator` pattern (~line 772)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Further Reading bullet list (lines 739–740) lists GAN-style harnesses as linked entries; add `html-anything.yaml` bullet
- `README.md` (line 167) — hardcoded `**44 FSM loops**` count; increment to `**45 FSM loops**`
- `CHANGELOG.md` — convention: every new built-in harness gets an `### Added` bullet; add `html-anything FSM Loop` entry in current release section

### Configuration
- N/A — no config changes required

## Implementation Steps

1. Create `scripts/little_loops/loops/html-anything.yaml` with 6 states + `failed` terminal — follow `svg-image-generator.yaml` as the primary structural template:
   - `init` (shell): use exact `capture: run_dir` pattern from `svg-image-generator.yaml:24-35`; output_dir = `.loops/tmp/html-anything`
   - `plan` (prompt): classify artifact type from `${context.description}`, write `brief.md` with platform-specific constraints + `rubric.md` with 4–6 criteria (YAML fenced block, each with `name`, `weight`, `threshold`, `description`) — atomically in one state
   - `generate` (prompt): read `${captured.run_dir.output}/brief.md` + `rubric.md` + optional `critique.md`; write `index.html` with all CSS/JS inline (no external deps, renders under `file://`)
   - `evaluate` (shell): Playwright screenshot — include `on_error: generate` (unlike `html-website-generator.yaml` which omits it); pattern from `svg-image-generator.yaml:89-104`
   - `score` (prompt): read `rubric.md` dynamically to load per-criterion thresholds; score 1–10; write `critique.md`; route via `output_contains: ALL_PASS` → `done`, else → `generate`, `on_error: failed`; pattern from `svg-image-generator.yaml:106-151`
   - `done` (prompt + `terminal: true`): report all 5 output file paths; use reporting pattern from `svg-image-generator.yaml:153-167`
   - `failed` (`terminal: true`): silent terminal from `svg-image-generator.yaml:169-173`
   - Top-level: `max_iterations: 20`, `timeout: 7200`, `pass_threshold: 7` (higher than SVG's 6 — platform constraints are binary)
2. Update `scripts/little_loops/loops/README.md` — insert row after `svg-image-generator` (line 101) in the Harness table:
   ```
   | `html-anything` | Generalized HTML artifact harness — classifies artifact type (email, social card, résumé, dashboard, etc.) from a description, writes platform-specific brief and dynamic scoring rubric, then iteratively generates and refines `index.html` via Playwright CLI. |
   ```
3. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — `html-anything.yaml` is auto-discovered; all three tests (parse, validate, description) must pass
4. Verify functional correctness with three test runs:
   - `ll-loop run html-anything "a transactional email confirming a SaaS subscription"` → rubric should have `inline_styles` with threshold 7–8
   - `ll-loop run html-anything "a 1200x630 open graph card for a developer tool"` → rubric should have `dimensional_accuracy`
   - `ll-loop run html-anything "a single-page website for a coffee shop"` → should behave like `html-website-generator`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_builtin_loops.py` — add `"html-anything"` to `TestBuiltinLoopFiles.test_expected_loops_exist` hardcoded set (lines 65–112); add `TestHtmlAnythingLoop` class at end of file following `TestSvgImageGeneratorLoop` pattern (14+ assertions per the pattern)
6. Update `docs/guides/LOOPS_GUIDE.md` — add `html-anything` row to Harness Examples table (~line 761); add `### html-anything` subsection following `### html-website-generator` pattern (~line 772)
7. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `html-anything.yaml` bullet to Further Reading section (lines 739–740)
8. Update `README.md` (line 167) — increment `**44 FSM loops**` to `**45 FSM loops**`
9. Update `CHANGELOG.md` — add `html-anything FSM Loop` bullet under `### Added` in current release section

## Impact

- **Priority**: P2 — significant capability expansion unlocking 9 surface types from a single harness
- **Effort**: Medium — mostly YAML authoring following established patterns; no Python changes required
- **Risk**: Low — new file only; does not modify existing harnesses

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/svg-image-generator.yaml` | Timestamped run dir pattern to replicate in `init` |
| `scripts/little_loops/loops/html-website-generator.yaml` | Critique format and score routing to replicate |
| `scripts/little_loops/loops/README.md` | Harness table to update |
| `~/.claude/plans/take-a-look-at-moonlit-squid.md` | Full design plan (source of this issue) |

## Resolution

Implemented `scripts/little_loops/loops/html-anything.yaml` — a 7-state FSM harness (`init`, `plan`, `generate`, `evaluate`, `score`, `done`, `failed`) following the `svg-image-generator.yaml` structural pattern. The `plan` state atomically classifies artifact type and writes both `brief.md` and `rubric.md` in one state; the `score` state reads `rubric.md` dynamically to enforce per-criterion thresholds (not a weighted average). `evaluate` includes `on_error: generate` for Playwright-absent graceful degradation. All wiring touchpoints completed: expected-loops set updated, `TestHtmlAnythingLoop` (22 assertions) added to test suite, LOOPS_GUIDE.md subsection added, AUTOMATIC_HARNESSING_GUIDE.md and README.md counts updated, CHANGELOG.md entry added.

## Session Log
- `/ll:manage-issue` - 2026-05-17T05:47:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-17T05:42:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c484c58f-bb93-40df-ab7c-ba54e99cae31.jsonl`
- `/ll:wire-issue` - 2026-05-17T05:38:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f83462fc-6ed8-4bc4-b54c-c8a7368feb83.jsonl`
- `/ll:refine-issue` - 2026-05-17T05:34:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d0a080d4-34a9-421a-8023-f9695b34ec4b.jsonl`
- `/ll:format-issue` - 2026-05-17T05:29:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/886b380b-be9d-47e2-babe-28037613cb30.jsonl`
- `/ll:capture-issue` - 2026-05-17T05:27:26Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1abc7e22-2fd4-490d-8857-c86a64aecaa1.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/759d096e-fb8e-41c0-9a34-b8be226c415a.jsonl`

---

## Status

**Done** | Created: 2026-05-17 | Completed: 2026-05-17 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1534 (rn-plan) share a near-identical FSM harness pattern: `init (shell) → generate → iterative refinement → score → done`, using `svg-image-generator.yaml` as template. Future harness loops should consider using a canonical `harness-template.yaml` in `scripts/little_loops/loops/` rather than copying from one of these two.
