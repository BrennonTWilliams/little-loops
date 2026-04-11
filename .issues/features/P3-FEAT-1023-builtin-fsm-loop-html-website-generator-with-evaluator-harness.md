---
id: FEAT-1023
priority: P3
type: FEAT
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-1023: Add Built-In FSM Loop: HTML Website Generator with Generator-Evaluator Harness

## Summary

Add a new built-in FSM loop (`html-website-generator.yaml`) that accepts a natural language description of a single-page website and autonomously generates, evaluates, and iteratively refines HTML/CSS/JS output using the GAN-inspired generator-evaluator architecture described in Anthropic's [harness design article](docs/claude-code/harness-design-long-running-apps.md). The loop uses Playwright CLI to screenshot the generated page and grade it against four design criteria (design quality, originality, craft, functionality).

## Current Behavior

No built-in loop demonstrates the generator-evaluator (GAN-style) harness pattern from the harness design article. Existing example loops (`harness-single-shot.yaml`, `harness-multi-item.yaml`) show the automatic harnessing phases but don't implement a creative generation loop where the evaluator provides scored feedback to drive iterative refinement.

## Expected Behavior

A fully functional built-in loop `html-website-generator.yaml` exists in `scripts/little_loops/loops/` such that:

- `ll-loop run html-website-generator "a landing page for a Dutch art museum"` accepts a natural language website description as the positional string input (via `loop_input`)
- The loop runs a **planner** phase that expands the one-line description into a design brief with a visual design language
- A **generator** state creates/refines an `index.html` file (self-contained HTML/CSS/JS)
- An **evaluator** state uses Playwright CLI to screenshot the page (via `file://` URL — no HTTP server required) and scores it on four criteria with hard thresholds:
  - **Design quality** (coherent visual identity): weight 2×
  - **Originality** (no AI-slop patterns, custom creative decisions): weight 2×
  - **Craft** (typography, spacing, color harmony): weight 1×
  - **Functionality** (usability, primary actions findable): weight 1×
- If any criterion falls below its threshold, the evaluator writes detailed critique to a handoff file and routes back to generator for another iteration
- Loop runs up to 10 generator-evaluator cycles, then exits with the best version
- The generated `index.html` is saved to a configurable output path (default: `/tmp/ll-html-generator/index.html`)

## Use Case

**Who**: Developer exploring little-loops' harness capabilities, or someone wanting to generate a polished single-page website from a one-liner.

**Context**: User reads the harness design article, wants to see the generator-evaluator pattern in action, and runs `ll-loop run html-website-generator "portfolio site for a jazz musician"`. The loop autonomously generates, critiques, and improves the site through multiple iterations without human intervention.

**Goal**: Get a production-quality, visually distinctive single-page website from a sentence, while understanding how the generator-evaluator pattern works from reading the loop YAML.

**Outcome**: A fully rendered, self-contained `index.html` after 5-10 iterations, demonstrably more polished than a single-pass generation.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/html-website-generator.yaml` exists and passes `ll-loop validate`
- [ ] `ll-loop run html-website-generator "a landing page for a coffee shop"` runs without error
- [ ] The planner state expands the `loop_input` string into a design brief written to a context file
- [ ] The generator state produces a self-contained `index.html` that renders in a browser
- [ ] The evaluator state runs `playwright screenshot "file://..."` (Playwright CLI) and saves a screenshot to `${context.output_dir}/screenshot.png`
- [ ] The evaluator writes a structured critique file scoring all four criteria (design_quality, originality, craft, functionality) as integers 1-10 with explanations
- [ ] When any criterion score < threshold (default: 6), loop routes back to generator with the critique as context
- [ ] When all criteria ≥ threshold OR max_iterations reached, loop exits via `done` terminal state
- [ ] The loop includes `# HARNESS:` inline comments explaining each state's role relative to the article
- [ ] `ll-loop test html-website-generator` passes structural validation
- [ ] README or loop README.md references this loop as a harness pattern demonstration

## Motivation

The harness design article describes a powerful generator-evaluator architecture but no runnable little-loops example implements it. This loop would:
1. Serve as a canonical, runnable demonstration of the GAN-style harness pattern in the FSM executor
2. Show `loop_input` (positional string arg) used as the creative prompt
3. Demonstrate Playwright CLI as a lightweight screenshot evaluator tool (shell action — no MCP server required)
4. Give users a high-value practical tool (website generation) that doubles as a pedagogical reference

## Proposed Solution

**Loop architecture** (mirrors article's three-agent structure collapsed into FSM states):

```yaml
name: html-website-generator
category: harness
input_key: description
description: |
  Generator-evaluator harness for single-page HTML website creation.
  Accepts a natural language website description via loop_input and
  iteratively generates and refines HTML/CSS/JS using Playwright CLI
  screenshot evaluation. Implements the GAN-style architecture from
  Anthropic's harness design article.
initial: plan
max_iterations: 30   # ~3 outer iterations × 10 inner states
timeout: 14400

context:
  description: ""    # populated from loop_input
  output_dir: "/tmp/ll-html-generator"
  pass_threshold: 6  # minimum score per criterion to pass

states:
  plan:
    # HARNESS: Planner phase — expands the one-line description into a design brief
    action: |
      mkdir -p "${context.output_dir}"
      Write a design brief to ${context.output_dir}/brief.md for: ${context.description}

      Include:
      - Visual identity (color palette, typography, mood)
      - Layout structure (sections, key components)
      - Unique creative angle (what makes this design distinctive?)
      - Anti-patterns to avoid (purple gradients on white cards, stock components)
    action_type: prompt
    next: generate

  generate:
    # HARNESS: Generator phase — creates/refines the HTML file based on brief and critique
    action: |
      Read ${context.output_dir}/brief.md and any critique at
      ${context.output_dir}/critique.md (if it exists).

      Create a single self-contained HTML file at ${context.output_dir}/index.html
      implementing the design brief. Requirements:
      - All CSS and JS inline (no external dependencies)
      - Distinctive, museum-quality aesthetic — avoid AI-slop patterns
      - Responsive layout
      If critique exists, address all flagged issues specifically.
    action_type: prompt
    next: evaluate

  evaluate:
    # HARNESS: Screenshot gate — Playwright CLI captures the rendered file:// page as an image.
    # Self-contained HTML (all CSS/JS inline) renders correctly under file:// without an HTTP server.
    # Routes back to generate if playwright is not installed or the page fails to render.
    action: |
      playwright screenshot "file://${context.output_dir}/index.html" "${context.output_dir}/screenshot.png" && echo "CAPTURED"
    action_type: shell
    evaluate:
      type: output_contains
      pattern: "CAPTURED"
    on_yes: score
    on_no: generate

  score:
    # HARNESS: Evaluator phase — LLM judges the screenshot against four design criteria
    # and writes structured critique for the generator's next iteration.
    action: |
      Read the screenshot at ${context.output_dir}/screenshot.png to view the generated website.
      Score it on each criterion from 1-10 and write the results to ${context.output_dir}/critique.md.

      Criteria (score each 1-10):
      - design_quality: Does the design feel like a coherent whole? Strong color/typography/layout combination creates distinct mood and identity.
      - originality: Evidence of custom creative decisions? Best designs are museum-quality. Penalize: purple gradients on white cards, unmodified stock components, AI-generated patterns.
      - craft: Technical execution — typography hierarchy, spacing consistency, color harmony, contrast ratios.
      - functionality: Can users understand what the site does and complete primary tasks?

      Write scores to ${context.output_dir}/critique.md:
      ```
      # Evaluation

      design_quality: N/10 — [explanation]
      originality: N/10 — [explanation]
      craft: N/10 — [explanation]
      functionality: N/10 — [explanation]

      ## Issues to Address
      [Specific actionable critique for the generator]
      ```

      If ALL scores >= ${context.pass_threshold}, output exactly: PASS
      Otherwise output: ITERATE
    action_type: prompt
    evaluate:
      type: output_contains
      pattern: "PASS"
    on_yes: done
    on_no: generate

  done:
    terminal: true
```

**Key design decisions**:
- `evaluate` uses `playwright screenshot` with a `file://` URL — self-contained HTML (all CSS/JS inline) renders correctly without an HTTP server, eliminating background process lifecycle issues entirely
- `score` uses `output_contains: "PASS"` to route — simple and robust vs JSON parsing
- Critique written to file so it persists across the `generate → evaluate → score` sub-cycle
- `file://` approach removes the need for `serve` and `cleanup` infrastructure states, giving a clean 5-state FSM: `plan → generate → evaluate → score → done`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-website-generator.yaml` — New file (built-in loop)
- `scripts/little_loops/loops/README.md` — Add entry for new loop
- `scripts/tests/test_builtin_loops.py` — Add `"html-website-generator"` to `test_expected_loops_exist()` expected set (~line 47); add `TestHtmlWebsiteGeneratorLoop` structural test class [Wiring pass added by `/ll:wire-issue`]
- `docs/guides/LOOPS_GUIDE.md` — Add row to built-in loops table (lines 219–235) and to harness examples sub-table (lines 506–511) [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)
- `ll-loop run` / `scripts/little_loops/cli/loop/runner.py` — resolves loop by name; `loop_input` populates `context.description` via `input_key`
- `ll-loop validate` / `scripts/little_loops/fsm/validation.py` — validates YAML structure, terminal reachability, evaluator configs
- `ll-loop test` / `scripts/little_loops/cli/loop/testing.py` — structural validation command

### Similar Patterns
- `scripts/little_loops/loops/greenfield-builder.yaml` — Multi-phase builder loop; uses `context.spec` (file path). Different: no generator-evaluator cycle, no screenshot evaluation.
- `scripts/little_loops/loops/harness-single-shot.yaml` — Shows `check_stall → check_concrete → check_semantic` phases. Different: evaluates correctness, not design quality.
- `scripts/little_loops/loops/harness-multi-item.yaml` — Shows `check_mcp` with `mcp_tool` action type. Not used here (this loop uses Playwright CLI shell action instead), but relevant if migrating to MCP-based evaluation in future.
- `scripts/little_loops/loops/agent-eval-improve.yaml` — Prompt-based eval loop (LLM judges LLM output). Closest structural relative.

### Tests
- `ll-loop validate scripts/little_loops/loops/html-website-generator.yaml` — Structural validation (terminal reachability, evaluator configs, required fields)
- `ll-loop test html-website-generator` — Same via name resolution

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:47-86` — `test_expected_loops_exist()` has a hard-coded expected set; **will fail immediately** without adding `"html-website-generator"` to the set [hard break — must update]
- `scripts/tests/test_builtin_loops.py:29,36` — `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` use `glob("*.yaml")` and auto-cover the new file — no changes needed
- `scripts/tests/test_builtin_loops.py` (new) — Add `TestHtmlWebsiteGeneratorLoop` class: verify required states exist (`plan`, `generate`, `evaluate`, `score`, `done`), `done` is terminal, `input_key` equals `"description"`, `evaluate` state has `action_type == "shell"` and an `evaluate` block with `pattern: "CAPTURED"` — follow pattern of `TestEvaluationQualityLoop` at line 281

### Documentation
- `scripts/little_loops/loops/README.md` — Add loop to index
- `docs/claude-code/harness-design-long-running-apps.md` — Source article; could add back-reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:506-511` — Harness Examples sub-table (line 506 bold header, line 508 table header, lines 510-511 data rows) lists `harness-single-shot` and `harness-multi-item`; append a third row after line 511. NOTE: `harness-*` loops do NOT appear in the General-Purpose sub-table (lines 229-235) — they are only listed here. [Agent 2 finding + refine verification]

### Configuration
- Requires `playwright` CLI installed and on PATH. Install: `npm install -g playwright && npx playwright install chromium`. If absent, the `evaluate` state's shell action returns non-zero and routes back to `generate`; the loop cycles without making progress.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`input_key` mechanism** (`cli/loop/run.py:60-78`) — plain string CLI arg goes to `fsm.context[fsm.input_key]` via the `except json.JSONDecodeError` branch. `input_key: description` stores the positional arg at `context.description`, accessible as `${context.description}` in state actions. Confirmed correct for this loop.

**`file://` URL choice** (decided in design review) — self-contained HTML (all CSS/JS inline, per generator requirements) renders correctly under `file://` in Playwright's Chromium without CORS or resource-loading issues. Using `file://` eliminates the need for an HTTP server, avoiding the port-conflict and orphan-process problems that a `serve` state would introduce. Playwright CLI (`playwright screenshot`) accepts `file://` URLs.

**`score` state reads PNG via multimodal** — the `score` state is `action_type: prompt` and its action text says "Read the screenshot at ${context.output_dir}/screenshot.png to view the generated website." This works because Claude is multimodal and can read image files via the Read tool. No extra tooling required — the PNG produced by the `evaluate` state is directly accessible to Claude in the next state's prompt context.

**`output_contains` evaluator confirmed valid** (`fsm/validation.py:66`, `fsm/evaluators.py:269`) — used by both `shell` and `prompt` action types throughout the built-in loops. The `evaluate` state (shell + `output_contains: "CAPTURED"`) and the `score` state (prompt + `output_contains: "PASS"`) both follow established conventions.

**`input_key` convention** — only `greenfield-builder.yaml` sets `input_key` explicitly (uses `input_key: spec`). The proposed `input_key: description` follows the same pattern: declare `input_key: description` at the top level and set `context.description: ""` as the default. This is rare but fully supported (schema.py:495, default is `"input"`).

## Implementation Steps

1. Create `scripts/little_loops/loops/html-website-generator.yaml` following the proposed YAML above. The 5-state FSM (`plan → generate → evaluate → score → done`) uses Playwright CLI with a `file://` URL — no HTTP server or MCP configuration required. `input_key` mechanism is documented in Codebase Research Findings above.
2. Run `ll-loop validate html-website-generator` and fix any schema errors
3. Run `ll-loop test html-website-generator` to confirm structural validation passes
4. Update `scripts/little_loops/loops/README.md` to reference the new loop

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/tests/test_builtin_loops.py` — add `"html-website-generator"` to the `expected` set in `test_expected_loops_exist()` (line 46-88, uses `set` equality so missing entry fails immediately). Add a `TestHtmlWebsiteGeneratorLoop` class following the pattern of `TestEvaluationQualityLoop` (line 281-382): use a class-level `LOOP_FILE = BUILTIN_LOOPS_DIR / "html-website-generator.yaml"`, a `data` fixture via `yaml.safe_load(LOOP_FILE.read_text())`, then assert: required states `{plan, generate, evaluate, score, done}`, `done` is terminal, `input_key == "description"`, `evaluate` state has `action_type == "shell"` and an `evaluate` block containing `pattern: "CAPTURED"`
6. Update `docs/guides/LOOPS_GUIDE.md` — append a row to the Harness Examples sub-table only (after line 511, which currently ends with `harness-multi-item`). Harness loops are NOT listed in the General-Purpose sub-table (lines 229-235); only the Harness Examples section (lines 506-511) applies. Table format: `| \`html-website-generator\` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI |`

## API/Interface

```yaml
# Invocation
ll-loop run html-website-generator "a landing page for a Dutch art museum"

# context.description populated from loop_input via input_key: description
# Output: /tmp/ll-html-generator/index.html (configurable via context.output_dir)
# Critique: /tmp/ll-html-generator/critique.md
# Brief: /tmp/ll-html-generator/brief.md
```

## Impact

- **Priority**: P3 — Valuable demonstration and practical tool; not blocking anything
- **Effort**: Small — Single YAML file plus README/test/docs updates; no Python changes. Complexity is in the prompt design for the evaluator and generator states.
- **Risk**: Low — New file only; no existing code changes. Playwright CLI must be installed; if absent the loop cycles at the evaluate gate without progress (detectable immediately on first run).
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/claude-code/harness-design-long-running-apps.md` | Source architecture article this loop implements |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | FSM harness phase patterns and evaluator types |

## Labels

`feat`, `loops`, `harness`, `harnessing`, `playwright-cli`, `generator-evaluator`, `frontend`, `captured`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/761f2624-ecc1-499c-ac48-e18b3e383406.jsonl`
- `/ll:refine-issue` - 2026-04-11T04:58:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db48a35e-dc5e-4578-b3f1-212165c748a3.jsonl`
- `/ll:confidence-check` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ea2245e-b201-46b7-a15d-81c084e20c95.jsonl`
- `/ll:refine-issue` - 2026-04-11T04:35:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a695a0b4-55df-4b40-9759-8d3eeda245c7.jsonl`
- `/ll:wire-issue` - 2026-04-11T04:30:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32154347-e8f6-4756-b187-425c7a06970e.jsonl`
- `/ll:format-issue` - 2026-04-11T04:23:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3be8bdda-d42f-491e-8a93-0f32e4fd87aa.jsonl`
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe9849b2-c9ca-4d60-92fc-cfd769be2923.jsonl`
