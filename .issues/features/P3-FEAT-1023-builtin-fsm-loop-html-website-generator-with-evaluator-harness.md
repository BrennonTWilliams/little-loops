---
id: FEAT-1023
priority: P3
type: FEAT
status: open
discovered_date: 2026-04-10
discovered_by: capture-issue
---

# FEAT-1023: Add Built-In FSM Loop: HTML Website Generator with Generator-Evaluator Harness

## Summary

Add a new built-in FSM loop (`html-website-generator.yaml`) that accepts a natural language description of a single-page website and autonomously generates, evaluates, and iteratively refines HTML/CSS/JS output using the GAN-inspired generator-evaluator architecture described in Anthropic's [harness design article](docs/claude-code/harness-design-long-running-apps.md). The loop uses Playwright MCP to live-view the generated page and grade it against four design criteria (design quality, originality, craft, functionality).

## Current Behavior

No built-in loop demonstrates the generator-evaluator (GAN-style) harness pattern from the harness design article. Existing example loops (`harness-single-shot.yaml`, `harness-multi-item.yaml`) show the automatic harnessing phases but don't implement a creative generation loop where the evaluator provides scored feedback to drive iterative refinement.

## Expected Behavior

A fully functional built-in loop `html-website-generator.yaml` exists in `scripts/little_loops/loops/` such that:

- `ll-loop run html-website-generator "a landing page for a Dutch art museum"` accepts a natural language website description as the positional string input (via `loop_input`)
- The loop runs a **planner** phase that expands the one-line description into a design brief with a visual design language
- A **generator** state creates/refines an `index.html` file (self-contained HTML/CSS/JS)
- An **evaluator** state uses Playwright MCP to navigate the live page and scores it on four criteria with hard thresholds:
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
- [ ] The evaluator state uses Playwright MCP (`playwright/screenshot` and `playwright/evaluate`) to navigate the live page
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
3. Demonstrate Playwright MCP as an evaluator tool (the only `mcp_tool` action in a built-in loop)
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
  iteratively generates and refines HTML/CSS/JS using Playwright MCP
  evaluation. Implements the GAN-style architecture from Anthropic's
  harness design article.
initial: plan
max_iterations: 30   # ~3 outer iterations × 10 inner states
timeout: 14400
on_handoff: spawn

context:
  description: ""    # populated from loop_input
  output_dir: "/tmp/ll-html-generator"
  pass_threshold: 6  # minimum score per criterion to pass

states:
  plan:
    action: |
      # Expand loop_input into design brief
      mkdir -p "${context.output_dir}"
      cat > "${context.output_dir}/brief.md" << 'BRIEF'
      # Design Brief

      Generate a design brief for: ${loop_input}

      Include:
      - Visual identity (color palette, typography, mood)
      - Layout structure (sections, key components)
      - Unique creative angle (what makes this design distinctive?)
      - Anti-patterns to avoid (purple gradients on white cards, stock components)
      BRIEF
    action_type: prompt   # LLM fills in the brief
    next: generate

  generate:
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
    next: serve

  serve:
    action: |
      cd "${context.output_dir}" && python3 -m http.server 18420 &
      sleep 2 && echo "Server ready"
    action_type: shell
    evaluate:
      type: output_contains
      pattern: "Server ready"
    on_yes: evaluate
    on_no: generate

  evaluate:
    action_type: mcp_tool
    action: "playwright/screenshot"
    params:
      url: "http://localhost:18420"
      fullPage: true
    capture: screenshot_result
    route:
      success: score
      tool_error: generate
      not_found: generate
      timeout: generate

  score:
    action: |
      You have a screenshot of the generated website. Score it on each criterion
      from 1-10 and write the results to ${context.output_dir}/critique.md.

      Criteria (score each 1-10):
      - design_quality: Does the design feel like a coherent whole? Strong color/typography/layout combination creates distinct mood and identity.
      - originality: Evidence of custom creative decisions? Best designs are museum-quality. Penalize: purple gradients on white cards, unmodified stock components, AI-generated patterns.
      - craft: Technical execution — typography hierarchy, spacing consistency, color harmony, contrast ratios.
      - functionality: Can users understand what the site does and complete primary tasks?

      Write JSON scores to ${context.output_dir}/critique.md:
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
    on_yes: cleanup
    on_no: generate

  cleanup:
    action: |
      pkill -f "http.server 18420" 2>/dev/null || true
      echo "Complete. Output: ${context.output_dir}/index.html"
    action_type: shell
    next: done

  done:
    terminal: true
```

**Key design decisions**:
- `serve` uses `python3 -m http.server` so Playwright can access the file via HTTP (not `file://`)
- `evaluate` uses Playwright MCP screenshot so the evaluator sees the rendered page visually
- `score` uses `output_contains: "PASS"` to route — simple and robust vs JSON parsing
- Critique written to file so it persists across the `generate → serve → evaluate → score` sub-cycle

**Simplification option**: Skip the `serve` state and use `playwright/navigate` with a `file://` URL if Playwright MCP supports it — reduces infrastructure complexity.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-website-generator.yaml` — New file (built-in loop)
- `scripts/little_loops/loops/README.md` — Add entry for new loop

### Dependent Files (Callers/Importers)
- `ll-loop run` / `scripts/little_loops/cli/loop/runner.py` — resolves loop by name; `loop_input` populates `context.description` via `input_key`
- `ll-loop validate` / `scripts/little_loops/fsm/validation.py` — validates YAML structure, terminal reachability, evaluator configs
- `ll-loop test` / `scripts/little_loops/cli/loop/testing.py` — structural validation command

### Similar Patterns
- `scripts/little_loops/loops/greenfield-builder.yaml` — Multi-phase builder loop using `on_handoff: spawn`; uses `context.spec` (file path). Different: no generator-evaluator cycle, no MCP tool usage.
- `scripts/little_loops/loops/harness-single-shot.yaml` — Shows `check_stall → check_concrete → check_semantic` phases. Different: evaluates correctness, not design quality.
- `scripts/little_loops/loops/harness-multi-item.yaml` — Shows `check_mcp` with `mcp_tool` action type (currently only example-file instance of this pattern). **Key reference for Playwright MCP state syntax.**
- `scripts/little_loops/loops/agent-eval-improve.yaml` — Prompt-based eval loop (LLM judges LLM output). Closest structural relative.

### Tests
- `ll-loop validate scripts/little_loops/loops/html-website-generator.yaml` — Structural validation (terminal reachability, evaluator configs, required fields)
- `ll-loop test html-website-generator` — Same via name resolution

### Documentation
- `scripts/little_loops/loops/README.md` — Add loop to index
- `docs/claude-code/harness-design-long-running-apps.md` — Source article; could add back-reference

### Configuration
- Requires Playwright MCP configured in user's `.mcp.json`; loop should degrade gracefully when absent (route `not_found: generate` already handles this)

## Implementation Steps

1. Read `scripts/little_loops/loops/harness-multi-item.yaml` to extract the correct `mcp_tool` state syntax
2. Read `scripts/little_loops/fsm/validation.py` to confirm `route:` keys for `mcp_tool` evaluator (`success`, `tool_error`, `not_found`, `timeout`)
3. Create `scripts/little_loops/loops/html-website-generator.yaml` following the proposed YAML above
4. Run `ll-loop validate html-website-generator` and fix any schema errors
5. Run `ll-loop test html-website-generator` to confirm structural validation passes
6. Update `scripts/little_loops/loops/README.md` to reference the new loop

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
- **Effort**: Small-Medium — Single YAML file plus README update; no Python changes. Complexity in getting the `mcp_tool` + Playwright state correct and handling the HTTP server lifecycle within FSM states.
- **Risk**: Low — New file only; no existing code changes. Playwright MCP dependency is optional (graceful fallback already in design).
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/claude-code/harness-design-long-running-apps.md` | Source architecture article this loop implements |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | FSM harness phase patterns and evaluator types |

## Labels

`feat`, `loops`, `harness`, `harnessing`, `mcp-tool`, `generator-evaluator`, `frontend`, `captured`

---

## Status

**Open** | Created: 2026-04-10 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe9849b2-c9ca-4d60-92fc-cfd769be2923.jsonl`
