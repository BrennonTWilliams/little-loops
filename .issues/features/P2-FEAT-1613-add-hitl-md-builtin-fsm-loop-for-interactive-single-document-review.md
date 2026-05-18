---
id: FEAT-1613
title: Add hitl-md built-in FSM loop for interactive single-document review with GP-TSM
  segmentation
type: FEAT
status: done
priority: P2
captured_at: '2026-05-18T20:37:24Z'
completed_at: '2026-05-18T22:00:51Z'
discovered_date: '2026-05-18'
discovered_by: capture-issue
labels:
- feature
- loops
- harness
- human-in-the-loop
- captured
relates_to:
- FEAT-1545
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1613: Add hitl-md built-in FSM loop for interactive single-document review with GP-TSM segmentation

## Summary

Add a new built-in FSM loop `hitl-md` that mirrors the `hitl-compare` harness
process (FEAT-1545) but is specialized for reviewing a **single markdown
document** rather than comparing multiple options. The loop's purpose is to
make human review of AI-generated documents — plans, PRDs, design docs,
research notes, etc. — easier and interactive via a single self-contained
HTML artifact.

The HTML artifact decomposes the source markdown into color-coded
highlighted segments using the **GP-TSM (Grammar-Preserving Text Saliency
Modulation)** algorithm (https://github.com/ZiweiGu/GP-TSM). The user can
navigate across segments via keyboard or mouse; the selected segment is
emphasized while others slightly fade. Each selected segment exposes
inline icon-button affordances to:

1. Delete the segment
2. Insert a new segment before it
3. Insert a new segment after it
4. Edit the segment inline
5. Flag the segment for the AI

When one or more segments are flagged, a control becomes available to copy
a **prompt snippet** containing the flagged segments — ready to paste into
an AI coding agent's chat so the agent can make targeted edits to those
specific spans of the document.

After local edits (deletions, additions, flagged-and-resolved revisions),
a bottom-of-page "Copy updated markdown" affordance copies the reconstructed
markdown to the clipboard for the user to paste back over the source file.

## Current Behavior

`hitl-compare` (FEAT-1545) handles the multi-option / comparison case but
is the wrong shape for single-document reviews: it requires 2+ options per
review item and frames the human task as "pick one." There is no built-in
loop for reviewing a single markdown document with fine-grained, segment-level
human-in-the-loop editing affordances. Today the workflow for reviewing an
AI-generated plan/PRD is to open the markdown in an editor, manually scan
for issues, and either edit inline or copy specific paragraphs into chat
asking the agent to revise — losing positional/segment context each time.

## Expected Behavior

`ll-loop run hitl-md "path/to/plan.md"` (single input — file path or raw text)
should:

1. Read the input markdown (resolving as a file path, falling back to raw
   text if the path doesn't exist).
2. Segment the document using the GP-TSM algorithm into grammar-preserving,
   saliency-modulated spans with per-segment color coding reflecting
   saliency / category (heading, bullet, code, prose, etc.).
3. Generate a single self-contained HTML page `index.html` (all CSS/JS
   inline, no external deps, renders under `file://`) presenting the
   segmented document with full keyboard + mouse navigation, the
   per-segment edit affordances (delete / insert before / insert after /
   inline edit / flag for AI), a flagged-segments prompt-snippet copy
   control, and a final "Copy updated markdown" control that reconstructs
   markdown from the (possibly mutated) segment list.
4. Iteratively evaluate the rendered artifact via Playwright screenshot
   and refine it for clarity, scan-ability, segment legibility, keyboard
   reachability, and affordance discoverability — reusing the
   generator/evaluator pattern from `html-anything.yaml` /
   `html-website-generator.yaml`.
5. Report the final HTML path so the human can open it, perform their
   review, and either paste flagged-segment prompts into the agent or
   paste the updated markdown back over the source file.

## Use Case

A developer just used `/ll:recursive-refine` or a planning skill to
produce a long PRD or implementation plan markdown file. Rather than
reading the file linearly in an editor and either editing-inline or
copying paragraphs into chat one at a time, they run
`ll-loop run hitl-md path/to/PRD.md`, open the generated HTML in their
browser, and navigate the document segment by segment. They delete a
few stale paragraphs, insert a new clarifying note before a section,
inline-edit a couple of bullet points, and flag three segments where
they want the AI to dig deeper. They click "Copy AI prompt", paste it
into the coding agent chat to get those three segments rewritten, and
when satisfied click "Copy updated markdown" to paste the result back
over the source file. Round trip: a single focused review pass with
preserved segment-level context, versus what was previously a long
back-and-forth chat thread.

## Motivation

AI agents now routinely produce long structured markdown artifacts —
plans, PRDs, designs, refined issues, research summaries — and the
bottleneck has shifted to **human review of long AI-generated text**.
Reviewing such artifacts in a plain editor is high-friction:

- Hard to scan saliency / importance at a glance.
- No structural affordance for "flag this span for the AI to revise."
- Copy-pasting spans into chat loses positional context and
  bidirectional traceability.
- Sequential edits in an editor + lost reasoning about what was
  changed and why.

A single interactive HTML artifact with GP-TSM-driven segment coloring
and per-segment affordances makes the review surface focused and
scan-friendly, preserves segment identity across the
human↔agent round-trip, and turns the workflow into a clean,
copy-pasteable handoff.

This is the natural single-document counterpart to `hitl-compare`'s
multi-option comparison surface, completing the HITL harness family.

## Proposed Solution

A 7-state FSM harness modeled on `hitl-compare.yaml` and
`html-anything.yaml`:

```
init → segment → generate → evaluate → score → done (+ failed terminal)
```

**Per-state sketch:**

- `init` (shell): create timestamped run dir under
  `.loops/tmp/hitl-md/<TS>/`, `capture: run_dir` — mirrors the
  established harness init pattern (use the `harness_init_run_dir`
  fragment if extracted per FEAT-1545's recommendation).
- `segment` (prompt): read the input markdown (resolving file path or
  treating as raw text), run the GP-TSM algorithm to decompose the
  document into grammar-preserving saliency-modulated segments, write
  `${captured.run_dir.output}/segments.json` containing the ordered
  segment list with `{id, type, saliency_score, color, original_text,
  markdown_source}` per segment. The GP-TSM step is the novel core
  work for this loop — see "GP-TSM Integration" below.
- `generate` (prompt): read `segments.json` (+ any prior `critique.md`);
  write a single self-contained HTML file `index.html` with all CSS/JS
  inline, the segmented document rendered with per-segment color
  coding, keyboard and mouse navigation (Tab / arrow keys / click),
  selected-segment emphasis + others-fade styling, per-segment icon
  buttons (delete / insert-before / insert-after / inline-edit /
  flag-for-AI), a flagged-segments prompt-snippet copy control, and
  a final "Copy updated markdown" control that reconstructs markdown
  from the live (possibly mutated) segment list.
- `evaluate` (shell): Playwright screenshot of `file://...index.html`
  with `on_error: generate` for graceful degradation — pattern from
  `html-anything.yaml`.
- `score` (prompt): score the rendered page against a fixed rubric
  (segment legibility, saliency-coloring effectiveness, keyboard
  reachability, affordance discoverability, inline-only constraint,
  markdown reconstruction correctness for a small smoke set), write
  `critique.md`, gate via `output_contains: ALL_PASS`; route to
  `generate` on fail, `on_error: failed`.
- `done` (prompt + `terminal: true`): report final paths
  (`index.html`, `segments.json`, `critique.md`, `screenshot.png`)
  and tell the user how to open the page, perform their review, and
  copy either the flagged-segment AI prompt or the updated markdown
  back into their workflow.
- `failed` (`terminal: true`).

**Input handling:** `input_key: input` (singular, in contrast to
`hitl-compare`'s plural `inputs`) accepting a single token: if it
resolves to a file path on disk, read the file; otherwise treat the
literal string as raw markdown content. This matches the
single-document framing.

**Shared fragments:** If the `lib/harness.yaml` extraction recommended
in FEAT-1545 has been done by the time this issue is implemented,
import it and consume `harness_init_run_dir`,
`harness_playwright_screenshot`, and `harness_rubric_score`. Otherwise
inline the same patterns and call out the duplication in a follow-up
ENH (this would be the fourth+ harness with the same copy-paste).

## GP-TSM Integration

The novel core capability of this loop is the **Grammar-Preserving
Text Saliency Modulation (GP-TSM)** decomposition step. Reference:
https://github.com/ZiweiGu/GP-TSM.

Open questions to resolve during refinement (`/ll:refine-issue`):

1. **Implementation surface**: Is GP-TSM imported as a Python library
   (vendored or PyPI dependency), invoked as a CLI subprocess, or
   re-implemented inline in the `segment` prompt as instructions to
   the LLM? Prefer the option that keeps `little-loops` dependency-light
   while producing reproducible segment boundaries.
2. **Saliency → color mapping**: Define a small fixed palette mapping
   saliency tiers to accessible colors with sufficient contrast and
   colorblind-safe pairs.
3. **Segment granularity**: Sentence-level vs clause-level vs
   paragraph-level — likely a tunable knob; pick a default that
   matches the "review-by-segment" UX intent.
4. **Markdown ↔ segment round-tripping**: Each segment must carry
   enough source metadata that the "Copy updated markdown"
   reconstruction is lossless for unchanged segments and produces
   well-formed markdown for inserted/edited segments.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Open Question 1 resolved — Recommended: LLM-in-prompt segmentation**

Analysis of the little-loops codebase confirms no external Python ML library dependencies exist in any loop YAML or the `scripts/little_loops/` package (no scipy, numpy, transformers, or subprocess calls to ML tools). All other loops that process document text — `hitl-compare.yaml`, `html-anything.yaml`, `rn-refine.yaml` — implement analysis logic as LLM prompt instructions. The recommended approach consistent with this pattern: implement the `segment` state as a `prompt` action that instructs the model to apply GP-TSM principles inline — identifying grammar-preserving boundaries (sentence/clause level), assigning saliency scores by content type (heading, bullet, code block, prose), and writing `${captured.run_dir.output}/segments.json`. No PyPI changes required. Document the choice in the loop YAML's top-level `description:` per acceptance criteria.

**`lib/harness.yaml` status**: confirmed not yet created — the file does not exist in `scripts/little_loops/loops/lib/`. Inline the `init`/`evaluate`/`score` patterns from `hitl-compare.yaml` directly and note the duplication in a follow-up ENH as the Proposed Solution prescribes.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/README.md` — add `hitl-md` row to Harness table
- `scripts/tests/test_builtin_loops.py` — add `"hitl-md"` to the hardcoded `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist`; add new `TestHitlMdLoop` class modeled on `TestHitlCompareLoop` (once that lands from FEAT-1545)
- `docs/guides/LOOPS_GUIDE.md` — add row to Harness Examples table + `### hitl-md` subsection
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `hitl-md.yaml` bullet to Further Reading
- `README.md` — increment FSM loop count (verify current count when implementing; ensure consistency with FEAT-1545's correction to 48)
- `CONTRIBUTING.md` — directory tree entry YAML count (same drift FEAT-1545 noted at line 122)
- `CHANGELOG.md` — `### Added` entry under current release

#### Codebase Research Findings — Exact Change Locations

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `README.md:167` — currently `"50 FSM loops"` → update to `"51 FSM loops"` (FEAT-1545 already landed; current on-disk count is 50)
- `CONTRIBUTING.md:122` — currently `"49 YAML files"` → update to `"50 YAML files"`
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_expected_loops_exist` expected set (lines 67–118): add `"hitl-md"` entry; the set currently has exactly 50 names and uses `assert expected == actual` (exact equality, not subset)
- `docs/guides/LOOPS_GUIDE.md:881–893` — Harness Examples table; add `hitl-md` row following the `hitl-compare` row pattern
- `docs/guides/LOOPS_GUIDE.md:973–1024` — per-harness detailed subsection; add `### hitl-md` block following the `### hitl-compare` section shape
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:731–744` — `## See Also` section; add `hitl-md.yaml` bullet following `hitl-compare.yaml` bullet
- `scripts/tests/test_builtin_loops.py:3295` — append `class TestHitlMdLoop` immediately after `class TestHitlCompareLoop` ends

### Files to Create

- `scripts/little_loops/loops/hitl-md.yaml` — new 7-state FSM harness
- _(optional)_ `scripts/little_loops/loops/lib/harness.yaml` — if not already extracted by FEAT-1545, this is a strong forcing function

### Reference Files (patterns to follow)

- `scripts/little_loops/loops/hitl-compare.yaml` — sibling harness, primary structural template
- `scripts/little_loops/loops/html-anything.yaml` — init / evaluate / score / done / failed structural template
- `scripts/little_loops/loops/svg-image-generator.yaml` — timestamped run dir + `on_error` graceful-degrade pattern
- `scripts/little_loops/loops/lib/common.yaml` — shared fragment authoring conventions

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

Loop discovery is fully implicit — no files need modification to register `hitl-md`. The loader chain for reference:
- `scripts/little_loops/cli/loop/_helpers.py:resolve_loop_path()` — filesystem glob fallback via `get_builtin_loops_dir()`; `ll-loop run hitl-md` auto-resolves once the YAML file exists
- `scripts/little_loops/cli/loop/info.py:cmd_list()` — globs `*.yaml` and reads `category`/`labels`; `ll-loop list --category harness` auto-includes `hitl-md` when `category: harness` is declared

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_fsm_flow.py:TestBuiltinLoopRegression.test_all_builtin_loops_still_load` — auto-discovers via `loops_dir.glob("*.yaml")`; runs `load_and_validate()` on every built-in YAML including `hitl-md.yaml`; no code change needed, but any YAML structural error will cause failure here
- `scripts/tests/test_builtin_loops.py` — four parametrized tests in `TestBuiltinLoopFiles` auto-include `hitl-md.yaml` via the `builtin_loops` fixture: `test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field`, `test_no_bare_pass_token_in_output_contains` — these are silent invariant guards; the new YAML must pass all four

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/doc_counts.py:verify_documentation()` — scans `README.md` and `CONTRIBUTING.md` for loop count literals and compares against actual `scripts/little_loops/loops/*.yaml` glob count; `ll-verify-docs` exits 1 if they diverge; this is the programmatic enforcer of the count updates in README.md and CONTRIBUTING.md — those changes are mandatory, not cosmetic

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/LOOPS_GUIDE.md:897` — contains a design rule callout stating "never back to generate" for Playwright failure routing; the new `### hitl-md` section must explicitly note that `on_error: generate` in the `evaluate` state is a **deliberate divergence** from this rule, following the `svg-image-generator` pattern rather than the `hitl-compare` pattern

## Implementation Steps

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Create `scripts/little_loops/loops/hitl-md.yaml`** modeled on `scripts/little_loops/loops/hitl-compare.yaml` (lines 1–314):
   - Top-level: `name: hitl-md`, `category: harness`, `labels: [hitl, markdown, html, interactive]`, `input_key: input` (singular), `max_iterations: 20`, `timeout: 7200`
   - `context: { input: "", output_dir: ".loops/tmp/hitl-md" }`
   - `init` state: copy shell pattern from `hitl-compare.yaml:25–36` verbatim (`$(pwd)/$DIR`, `capture: run_dir`), set `next: segment`
   - `segment` state: `action_type: prompt`; reads `${context.input}` (file path or raw text), runs LLM-based GP-TSM segmentation, writes `${captured.run_dir.output}/segments.json`; `next: generate`
   - `generate` state: `action_type: prompt`; reads `segments.json` + optional `critique.md`; writes `${captured.run_dir.output}/index.html` with all CSS/JS inline; `next: evaluate`
   - `evaluate` state: Playwright shell action with `2>&1`; `output_contains: CAPTURED`; **`on_yes: score`, `on_no: score`, `on_error: generate`**. **Precision note**: this is a hybrid routing — `on_yes/on_no: score` follows hitl-compare; only `on_error: generate` borrows from svg-image-generator. Do NOT copy svg-image-generator's evaluate state verbatim: svg-image-generator also has `on_no: generate` (lines 102-104), but hitl-md intends `on_no: score`. The divergence from the LOOPS_GUIDE.md design rule (line 897: "never back to generate") is intentional and limited to `on_error` only.
   - `score` state: rubric prompt writing `${captured.run_dir.output}/critique.md`; `output_contains: ALL_PASS`; `on_yes: done`, `on_no: generate`, `on_error: failed`
   - `done` state: `action_type: prompt`, `terminal: true`; references `index.html`, `segments.json`, `critique.md`, `screenshot.png`
   - `failed` state: `action_type: prompt`, `terminal: true`; diagnostic summary

2. **Update `scripts/tests/test_builtin_loops.py`**:
   - Add `"hitl-md"` to the `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` (line ~118, after `"hitl-compare"`)
   - Add `class TestHitlMdLoop` after `TestHitlCompareLoop` ends (line 3295), modeled on `TestHitlCompareLoop` (lines 3137–3295) with these differences:
     - `LOOP_FILE = BUILTIN_LOOPS_DIR / "hitl-md.yaml"`
     - `test_required_top_level_fields`: `name == "hitl-md"`, `input_key == "input"` (singular)
     - `test_required_states_exist`: `required = {"init", "segment", "generate", "evaluate", "score", "done", "failed"}`
     - `test_init_state_is_shell_with_capture`: assert `state.get("next") == "segment"`
     - **`test_evaluate_on_error_routes_to_generate`**: assert `on_error == "generate"` (not `"score"` — differs from hitl-compare)
     - `test_context_has_input_and_output_dir`: assert `"input" in ctx`, `ctx.get("output_dir") == ".loops/tmp/hitl-md"`
     - `test_segment_action_writes_segments_json`: assert `"segments.json" in action`
     - `test_generate_action_writes_index_html`: assert `"index.html" in action`
     - `test_done_reports_all_output_files`: assert `"index.html"`, `"segments.json"`, `"critique.md"`, `"screenshot.png"` in `done.action`
     - `test_evaluate_action_has_stderr_redirect`: assert `"2>&1" in action` (same invariant as hitl-compare — Playwright errors must surface in captured output)
     - `test_max_iterations_and_timeout_defined`: assert `data.get("max_iterations", 0) > 0` and `data.get("timeout", 0) > 0`

3. **Update `scripts/little_loops/loops/README.md`**: add `hitl-md` row to Harness table (follow `hitl-compare` row format).

4. **Update `README.md:167`**: `"50 FSM loops"` → `"51 FSM loops"`.

5. **Update `CONTRIBUTING.md:122`**: `"49 YAML files"` → `"50 YAML files"`.

6. **Update `docs/guides/LOOPS_GUIDE.md`**: add `hitl-md` row to Harness Examples table (lines 881–893); add `### hitl-md` subsection following the `### hitl-compare` section pattern (lines 973–1024).

7. **Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`**: add `hitl-md.yaml` bullet to `## See Also` (lines 731–744) following the `hitl-compare.yaml` bullet.

8. **Update `CHANGELOG.md`**: add `### Added` entry under the current release section.

9. **Run `python -m pytest scripts/tests/test_builtin_loops.py -v`** to confirm all structural assertions pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis:_

10. **In `docs/guides/LOOPS_GUIDE.md` `### hitl-md` section** — explicitly call out that `on_error: generate` in the `evaluate` state is a deliberate divergence from the "never back to generate" design rule at line 897; state that this follows the `svg-image-generator.yaml` precedent and is intentional for graceful HTML regeneration on Playwright errors.

11. **After all changes, run `ll-verify-docs`** (which calls `scripts/little_loops/doc_counts.py:verify_documentation()`) to confirm the README.md and CONTRIBUTING.md count literals match the actual YAML glob count. This is a CI hard check — failure here means the count updates in steps 4 and 5 were missed or miscounted.

12. **Run `python -m pytest scripts/tests/test_fsm_flow.py::TestBuiltinLoopRegression::test_all_builtin_loops_still_load -v`** to confirm the new YAML loads and validates under `load_and_validate()` — this test auto-discovers all `*.yaml` files and is an implicit structural guard independent of `test_builtin_loops.py`.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/hitl-md.yaml` exists with 7 states (`init`, `segment`, `generate`, `evaluate`, `score`, `done`) plus a `failed` terminal state.
- [ ] Loop declares `input_key: input` (singular) accepting a single token: file path if it resolves on disk, otherwise raw markdown content.
- [ ] `init` state creates a timestamped run dir under `.loops/tmp/hitl-md/<TS>/` and captures it as `run_dir` (uses `$(pwd)` for absolute path per `test_init_action_uses_absolute_path` invariant).
- [ ] `segment` state decomposes the input markdown via GP-TSM and writes `${captured.run_dir.output}/segments.json` containing the ordered segment list with per-segment `id`, `type`, `saliency_score`, `color`, `original_text`, and `markdown_source` fields.
- [ ] `generate` state produces a single self-contained `index.html` (all CSS/JS inline, no external deps, renders under `file://`) with:
  - Per-segment color coding driven by GP-TSM saliency scores
  - Full keyboard navigation (Tab and arrow keys) and mouse selection
  - Selected-segment emphasis and others-fade visual treatment
  - Per-segment icon buttons: delete / insert-before / insert-after / inline-edit / flag-for-AI
  - A "Copy AI prompt" control that becomes active when ≥1 segment is flagged and copies a prompt snippet bundling all flagged segments
  - A bottom-of-page "Copy updated markdown" control that reconstructs markdown from the (possibly mutated) live segment list
- [ ] `evaluate` state runs a Playwright screenshot with `on_error: generate` for graceful degradation.
- [ ] `score` state evaluates against a fixed rubric (segment legibility, saliency-coloring effectiveness, keyboard reachability, affordance discoverability, inline-only constraint, markdown reconstruction correctness on a smoke segment set), writes `critique.md`, gates via `output_contains: ALL_PASS`, routes to `generate` on fail, uses `on_error: failed`.
- [ ] `done` state is `terminal: true` and reports final paths (`index.html`, `segments.json`, `critique.md`, `screenshot.png`) plus usage instructions.
- [ ] Top-level `description:` is a non-empty string; top-level `context:` declares `input: ""` and `output_dir: ".loops/tmp/hitl-md"`; top-level `category: harness` is set.
- [ ] No `output_contains` evaluator uses the bare token `"PASS"` (use `ALL_PASS` and `CAPTURED`).
- [ ] `scripts/tests/test_builtin_loops.py` expected-loops set includes `"hitl-md"` and a new `TestHitlMdLoop` class asserts structural invariants (name, input_key, state set, on_error wiring, init capture, key referenced filenames).
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py -v` passes.
- [ ] `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `README.md`, `CONTRIBUTING.md`, and `CHANGELOG.md` are updated with `hitl-md` entries and corrected loop counts.
- [ ] Functional verification: at least three sample runs across different document shapes (a long PRD, an implementation plan with code blocks, a short design note) each produce a well-formed interactive HTML artifact where the five per-segment affordances and both copy-controls work end-to-end.
- [ ] GP-TSM integration choice (library import vs subprocess vs LLM-in-prompt) is documented in the loop YAML's top-level `description:` or an inline comment so future maintainers know how segmentation is performed.

## Impact

- **Priority**: P2 — natural sibling to `hitl-compare` (FEAT-1545), completes the HITL harness family, and targets the increasingly common workflow of reviewing AI-generated long-form markdown.
- **Effort**: Medium-to-large — YAML authoring follows established harness patterns, but the GP-TSM integration and the interactive segment-edit HTML UI are both novel work with non-trivial design space (see "GP-TSM Integration" open questions).
- **Risk**: Low-medium — new file only; does not modify existing harnesses. Main risk is GP-TSM integration choice and the reconstruction-correctness invariant for "Copy updated markdown."

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/loops/hitl-compare.yaml` (FEAT-1545) | Direct sibling harness; primary structural template for this loop |
| `scripts/little_loops/loops/html-anything.yaml` | Init / evaluate / score / done / failed structural template |
| `scripts/little_loops/loops/svg-image-generator.yaml` | Timestamped run dir + `on_error` graceful-degrade pattern |
| `scripts/little_loops/loops/lib/common.yaml` | Shared fragment authoring conventions |
| https://github.com/ZiweiGu/GP-TSM | External reference: Grammar-Preserving Text Saliency Modulation algorithm used by the `segment` state |

## Session Log
- `/ll:ready-issue` - 2026-05-18T21:53:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b5a4882c-f5ea-4acf-9356-747cf2cfb33c.jsonl`
- `/ll:refine-issue` - 2026-05-18T21:10:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/25d86b78-37c7-42e1-a27c-b8b63eb3a079.jsonl`
- `/ll:confidence-check` - 2026-05-18T22:10:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/33c2dbfe-fc7c-4ba9-b148-7449686fcd60.jsonl`
- `/ll:confidence-check` - 2026-05-18T21:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b8d160ae-5eeb-4c7b-8dda-4e2a80d61151.jsonl`
- `/ll:wire-issue` - 2026-05-18T20:56:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/baa3a248-e429-40a2-a556-b0fb33f9aee4.jsonl`
- `/ll:refine-issue` - 2026-05-18T20:50:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f33a0302-b372-4124-a428-14d9d3e128b5.jsonl`
- `/ll:format-issue` - 2026-05-18T20:41:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23af1610-0691-449c-bfbd-b40d40ca1183.jsonl`
- `/ll:capture-issue` - 2026-05-18T20:37:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39518fe4-4d31-4d98-b347-41fe6101efe5.jsonl`

---

## Status

**Open** | Created: 2026-05-18 | Priority: P2
