---
discovered_date: 2026-04-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 71
---

# FEAT-1094: SVG Image Generator Loop

## Summary

Add a built-in `svg-image-generator` FSM loop that applies the generator-evaluator (GAN-style) harness from `html-website-generator` to SVG icon and image creation. The loop plans a visual brief, generates SVG iteratively, screenshots via Playwright, scores on four SVG-specific criteria, and iterates until passing threshold.

## Current Behavior

No SVG-specific generator-evaluator loop exists. Users who want to iteratively create and refine SVG icons or illustrations with Claude must do so manually — there is no built-in harness that applies visual feedback from screenshots to drive successive improvement.

The `html-website-generator` loop demonstrates the pattern works well for HTML pages, but SVGs have different structural properties (no external dependencies, no HTTP server needed, direct `file://` rendering) that make them a natural fit for a dedicated loop.

## Expected Behavior

A new built-in loop `svg-image-generator` is available at `scripts/little_loops/loops/svg-image-generator.yaml`. Running:

```bash
ll-loop run svg-image-generator --input "a minimalist coffee cup icon"
```

produces `/tmp/ll-svg-generator/image.svg` that iterates until all four scoring criteria score ≥ 6/10:

- **visual_clarity** (2×) — concept immediately readable, no ambiguity
- **originality** (2×) — custom creative decisions, not stock clip-art
- **craft** (1×) — clean paths, consistent stroke weights, proper proportions
- **scalability** (1×) — holds up at icon-scale given complexity

## Motivation

The `html-website-generator` harness is one of the strongest built-in demonstrations of what FSM loops can do. An SVG equivalent extends that pattern to a common creative task (icon/illustration generation) that benefits even more from visual feedback loops — SVGs are simpler to validate, self-contained by nature, and converge faster. This also provides a concrete example for users learning to build their own generator-evaluator loops.

## Use Case

A developer wants a custom icon for their project. They run:

```bash
ll-loop run svg-image-generator --input "a flat-style lightning bolt icon for a speed metric dashboard"
```

The loop plans a brief (shape language, color palette, intended size), generates `image.svg`, screenshots it with Playwright, scores it, incorporates the critique into the next iteration, and terminates when quality passes — delivering a polished, self-contained SVG without manual iteration.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/svg-image-generator.yaml` exists and is valid YAML
- [ ] Loop is auto-discovered by `ll-loop list` (no registration changes needed)
- [ ] Five states present: `plan`, `generate`, `evaluate`, `score`, `done`
- [ ] `plan` state writes `brief.md` to `output_dir` (`/tmp/ll-svg-generator` by default)
- [ ] `generate` state writes self-contained `image.svg` (no external `<image href>`, no external fonts, proper `viewBox`)
- [ ] `evaluate` state uses `playwright screenshot "file://${context.output_dir}/image.svg"` and falls back to LLM-only scoring if Playwright unavailable
- [ ] `score` state reads `screenshot.png` multimodally, writes `critique.md`, outputs `PASS`/`ITERATE`
- [ ] `score` outputs `PASS` only when all four criteria ≥ `pass_threshold` (default 6)
- [ ] `max_iterations: 20`, `timeout: 7200`
- [ ] `done` state is terminal and reports final file locations
- [ ] Running with `--input "a minimalist coffee cup icon"` produces a passing SVG within 20 iterations

## Proposed Solution

Port the `html-website-generator.yaml` loop structure directly, adapting:

1. **States**: `plan → generate → evaluate → score → done` (same shape as HTML harness)
2. **evaluate**: `playwright screenshot "file://${context.output_dir}/image.svg" "${context.output_dir}/screenshot.png" && echo "CAPTURED"` — identical mechanism, SVG renders natively in Playwright via `file://`
3. **Scoring criteria**: Replace HTML's `usability`/`functionality` with `visual_clarity`/`scalability`; keep `originality` and `craft`
4. **generate constraints**: Require proper `viewBox`, no external dependencies, aesthetic deliberateness — enforced via prompt instructions
5. **brief.md**: Shape language, color palette (hex), mood, intended use context, anti-patterns

Key design decision: `image.svg` not `icon.svg` — supports both icons and larger illustrations. Same `pass_threshold: 6` as HTML harness for consistent quality bar.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/svg-image-generator.yaml` (new file) — the loop definition itself
- `scripts/tests/test_builtin_loops.py:48-88` — **CRITICAL**: `test_expected_loops_exist` uses an equality assertion (`expected == actual`) with a hardcoded set; add `"svg-image-generator"` to the `expected` set or the test suite will fail
- `scripts/little_loops/loops/README.md:94-100` — Harness/Templates table; add a row for `svg-image-generator` (see html-website-generator row at line 100 as the model)
- `docs/guides/LOOPS_GUIDE.md:617-618` — Harness table; add `svg-image-generator` row alongside `html-website-generator`
- `docs/guides/LOOPS_GUIDE.md:675` — Add a new `### svg-image-generator — GAN-Style SVG Creation Loop` section immediately after the `html-website-generator` section (which ends at line 675)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:739` — Bullet-list of real-world harness examples; add `svg-image-generator` alongside `html-website-generator`

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:91` — update `**39 FSM loops**` count to `**40 FSM loops**` [Wiring pass]
- `CONTRIBUTING.md:124` — update `(34 YAML files)` count to `(40 YAML files)` (fixing existing staleness from 34 → actual 39 → 40) [Wiring pass]
- `CHANGELOG.md` — add `[Unreleased] > ### Added` entry for `svg-image-generator` (FEAT-1094) [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:88-114` — `get_builtin_loops_dir()` and `resolve_loop_path()` auto-discover all `*.yaml` files from the package `loops/` directory; no changes needed — auto-discovery is filename-based

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml:1-135` — exact YAML to port from; the SVG loop is a direct adaptation of this file's structure

### Tests
- `scripts/tests/test_builtin_loops.py:29-43` — `test_all_parse_as_yaml` and `test_all_validate_as_valid_fsm` automatically cover all `*.yaml` files in the loops dir; no new test class needed
- `scripts/tests/test_builtin_loops.py:46-90` — `test_expected_loops_exist` requires explicit update (see Files to Modify above)
- Manual acceptance test: `ll-loop run svg-image-generator --input "a minimalist coffee cup icon"`
- Inspect `/tmp/ll-svg-generator/brief.md`, `image.svg`, `critique.md` after run

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` after line 1358 — add `TestSvgImageGeneratorLoop` structural test class mirroring `TestHtmlWebsiteGeneratorLoop` (11 state-by-state YAML dict assertions: required top-level fields, required states, done terminal, evaluate shell action, evaluate output_contains evaluator, evaluate routing on yes/no, score routing on yes/no, context keys, max_iterations/timeout); note: existing claim "no new test class needed" conflicts with the established pattern — every generator-evaluator harness loop has a dedicated structural test class [Agent 3 finding]
- `scripts/tests/test_review_loop.py:187-198` — `test_builtin_loops_are_valid` parametrize auto-covers new YAML via glob; no changes needed [Agent 3 finding]

### Documentation
- `scripts/little_loops/loops/README.md` — primary built-in loops index; Harness section at line 94
- `docs/guides/LOOPS_GUIDE.md` — main loops guide with harness table at line 617 and per-loop sections starting at line 622
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:739` — real-world harness examples list

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:91` — `**39 FSM loops**` hard-coded count becomes `**40 FSM loops**` after adding new loop; no automated check catches this (ENH-1038 still open) [Agent 2 finding]
- `CONTRIBUTING.md:124` — `"(34 YAML files)"` already stale vs. actual 39 files; update to `"(40 YAML files)"` [Agent 2 finding]
- `CHANGELOG.md` — add bullet under `[Unreleased] > ### Added` following the precedent at line 106 for `html-website-generator` (FEAT-1023) [Agent 1+2 finding]
- `docs/guides/LOOPS_GUIDE.md:620` — prose sentence `"For background on the GAN-style generator-evaluator architecture used by \`html-website-generator\`..."` names only the HTML loop; consider generalizing to cover both harnesses after adding `svg-image-generator` [Agent 2 finding]

### Configuration
- N/A — pure YAML addition, no Python changes needed

## Implementation Steps

1. Read `scripts/little_loops/loops/html-website-generator.yaml` (135 lines) — the direct template to port from
2. Create `scripts/little_loops/loops/svg-image-generator.yaml` with the five-state FSM:
   - Top-level fields: `name: svg-image-generator`, `category: harness`, `input_key: description`, `description: |` (multi-line), `initial: plan`, `max_iterations: 20`, `timeout: 7200`
   - Context block: `description: ""`, `output_dir: "/tmp/ll-svg-generator"`, `pass_threshold: 6`
   - States: `plan → generate → evaluate → score → done` using `${context.output_dir}` and `${context.description}` interpolation
   - `evaluate` state: `action_type: shell`, command: `playwright screenshot "file://${context.output_dir}/image.svg" "${context.output_dir}/screenshot.png" && echo "CAPTURED"`, fallback on_no: generate
   - `done` state design choice: html-website-generator uses `terminal: true` only (no action); this issue specifies the done state "reports final file locations" — use a `prompt` action that outputs the file paths before `terminal: true`
3. Adapt `score` state criteria: replace `design_quality`/`functionality` with `visual_clarity` (2×) and `scalability` (1×); keep `originality` (2×) and `craft` (1×)
4. Update `scripts/tests/test_builtin_loops.py:48-88` — add `"svg-image-generator"` to the `expected` set in `test_expected_loops_exist`
5. Update `scripts/little_loops/loops/README.md:94-100` — add row to Harness/Templates table
6. Update `docs/guides/LOOPS_GUIDE.md` — add `svg-image-generator` row to harness table (line 617) and add a new `### svg-image-generator` section after line 675
7. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:739` — add `svg-image-generator` to the real-world harness examples list
8. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` — verify all builtin loop tests pass
9. Run `ll-loop run svg-image-generator --input "a minimalist coffee cup icon"` — verify end-to-end

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Add `TestSvgImageGeneratorLoop` class to `scripts/tests/test_builtin_loops.py` after line 1358 — 11 state-by-state structural assertions mirroring `TestHtmlWebsiteGeneratorLoop` (YAML dict inspection, no execution)
11. Update `README.md:91` — change `**39 FSM loops**` to `**40 FSM loops**`
12. Update `CONTRIBUTING.md:124` — change `(34 YAML files)` to `(40 YAML files)` (fixing pre-existing staleness)
13. Add entry to `CHANGELOG.md` under `[Unreleased] > ### Added` for `svg-image-generator` (FEAT-1094), following the html-website-generator precedent at line 106

## API/Interface

```yaml
# Loop invocation
ll-loop run svg-image-generator --input "description of SVG to generate"

# Context variables
description: ""          # populated from loop_input
output_dir: "/tmp/ll-svg-generator"
pass_threshold: 6        # 1–10 scale, applied to all four criteria

# Output files
/tmp/ll-svg-generator/brief.md       # visual planning brief
/tmp/ll-svg-generator/image.svg      # generated SVG (final output)
/tmp/ll-svg-generator/screenshot.png # Playwright-captured render
/tmp/ll-svg-generator/critique.md    # scoring + issues to address
```

## Impact

- **Priority**: P3 - Standard feature; extends proven html-website-generator pattern to SVG, good showcase value but not blocking
- **Effort**: Small - Pure YAML addition, direct port of existing loop structure, no Python changes
- **Risk**: Low - Self-contained new file, no changes to existing code, auto-discovered by existing resolver
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feature`, `loops`, `harness`, `svg`, `captured`

## Session Log
- `/ll:confidence-check` - 2026-04-13T15:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d22c48e-5d04-4aa3-8512-55595e860c13.jsonl`
- `/ll:wire-issue` - 2026-04-13T14:49:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d22c48e-5d04-4aa3-8512-55595e860c13.jsonl`
- `/ll:refine-issue` - 2026-04-13T14:38:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3402160-b653-4d97-830f-c84897abb872.jsonl`

- `/ll:capture-issue` - 2026-04-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67c8ca0c-f335-4cea-9728-0ea006ddfcfc.jsonl`

---

**Open** | Created: 2026-04-13 | Priority: P3
