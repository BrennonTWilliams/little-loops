---
id: FEAT-3320
type: FEAT
title: html-anything template-mode generate prompt (artifact_mode pilot)
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-25'
captured_at: '2026-08-25T16:25:58Z'
parent: EPIC-3299
labels:
- artifact
- ll-artifact
- fsm
- templates
- prompt
depends_on:
- FEAT-3318
relates_to:
- FEAT-3036
---

# FEAT-3320: html-anything template-mode generate prompt (artifact_mode pilot)

## Summary

Split out of FEAT-3318 at the 2026-08-25 pre-implementation review. FEAT-3318 lands
the `artifact_mode: template` plumbing — the schema field, the static and runtime
gates, atomic directory promotion, and a round-trip test against a hand-written
`.llat/` fixture. None of that requires an LLM to produce a template.

This issue is the other half: teach `html-anything` to actually *generate* a
`manifest.yaml` + `template.*.j2` + `data.json` triple instead of a fused
`index.html`, selected per-run via `--context artifact_mode=template`. It is the
pilot that proves the epic's design principle 1 ("loops emit template + data
natively") works in practice, and the precondition for rolling the variant out to
the remaining eight HTML-family loops.

## Current Behavior

- `html-anything.yaml:117-186` delegates to `oracles/generator-evaluator` via a
  `loop:` thin wrapper, passing a `generate_prompt` that instructs the model to
  "Write a single self-contained HTML file to `${captured.run_dir.output}/index.html`"
  (`:133`). There is one prompt and one output shape.
- The oracle's evaluate cycle is built around that single file: a Playwright
  screenshot of `file://.../${context.artifact_path}` (`generator-evaluator.yaml:82`,
  `artifact_path` defaulting to `index.html` at `:52`), then an LLM rubric score
  over `screenshot.png` (`html-anything.yaml:151-155`).
- With FEAT-3318 landed, a loop *can* declare `artifact_mode: template` and have a
  `.llat/` directory promoted and validated — but no built-in loop produces one.
  Every route from a loop to a template still runs through `ll-artifact templatize`
  (FEAT-3308), the lossy LLM-extraction path.

## Expected Behavior

`ll-loop run html-anything --context artifact_mode=template` produces a validated
`.llat/` directory that `ll-artifact render` consumes by name, with the same
iterate-until-`ALL_PASS` quality cycle the `file` mode gets today. The default
(`file`) path is byte-for-byte unchanged.

## Motivation

FEAT-3318's plumbing is inert without a producer. It is also unproven: the whole
reason this was split out is that "an LLM reliably emits a schema-valid
manifest + Jinja2 body + conforming data.json, repeatedly, under critique
iteration" is an empirical claim, not a mechanical one. Proving it on one loop
before rewriting nine prompts is the cheap ordering.

## Proposed Solution

### The evaluate cycle is the hard part, not the generate prompt

The generate prompt rewrite is mostly mechanical. The problem is that a `.llat/`
directory has nothing to screenshot, and the oracle's entire quality loop —
screenshot, rubric score, critique, iterate — is downstream of a renderable HTML
file at a fixed path.

Proposed: **render the template to HTML on each iteration, then screenshot the
render.** The oracle already parameterizes the screenshot target
(`artifact_path`, `generator-evaluator.yaml:43,52`), so the wrapper passes a
rendered path rather than the template directory. This keeps the entire
evaluate/score/critique cycle unchanged and untouched — the template becomes an
extra upstream step, not a fork of the oracle.

Open question for implementation: whether the render runs as a state inside the
wrapper or as an addition to the generate prompt's own instructions (i.e. the
model runs `ll-artifact render` itself as its last action). Prefer the former —
a deterministic shell step is cheaper and cannot be skipped by a model that
decides it is done early.

Consequence worth checking against ENH-2903: a render failure produces no HTML,
which produces no screenshot, which the oracle already models as a
screenshot-miss with a consecutive-miss abandon gate
(`generator-evaluator.yaml:89-143`). A malformed template may therefore surface
as a screenshot-miss rather than as a template error — the abandon path should
report the render failure, not a generic missing-screenshot message.

### Mode selection

Per FEAT-3318's § Mode selection: `artifact_mode` is a `context:` var on
`html-anything` (alongside `pass_threshold` / `design_tokens_context`), read by
`promote_run_artifact` with the top-level field as the default. Selection uses
the existing `ll-loop run --context artifact_mode=template`
(`cli/loop/__init__.py:294`) — no new CLI flag.

The generate prompt branches by interpolating that var. FSM prompts are static
text, so this is a conditional block in the prompt body, not two prompts.

### Scope bound

`html-anything` only. The remaining eight HTML-family loops are a follow-up,
scoped once this pilot reports an actual success rate.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/html-anything.yaml:117-186` — the `generate_prompt`
  template-mode branch, the `artifact_mode` context var, the per-iteration render
  step, and the `artifact_path` passed through `with:`
- `scripts/little_loops/loops/html-anything.yaml:187-201` — `finalize_done` reports
  `index.html`; template mode reports the `.llat/` contents instead

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/generator-evaluator.yaml:43,52,82` —
  `artifact_path`; the screenshot target this issue repoints. **Do not fork the
  oracle** — eight other loops delegate to it.
- `scripts/little_loops/cli/artifact/render.py:72` — `cmd_render`, invoked per
  iteration

### Tests
- `scripts/tests/test_builtin_loops.py` — conformance for the modified
  `html-anything.yaml` (both modes parse, validate, and route)
- A `file`-mode regression asserting the default path is unchanged

### Documentation
- `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — the
  template-mode invocation

## Program Design

### Call Path

`ll-loop run html-anything --context artifact_mode=template` ->
`run_gen_eval` (`html-anything.yaml:117`) -> `oracles/generator-evaluator` with a
template-shaped `generate_prompt` + a rendered `artifact_path` ->
`ll-artifact render` (per iteration, for the screenshot) -> Playwright screenshot ->
rubric score -> `finalize_done` -> `promote_run_artifact` (FEAT-3318) ->
`<templates_dir>/{run_id}-html-anything.llat/`

## Implementation Steps

1. Add the `artifact_mode` context var to `html-anything.yaml` and thread the
   effective mode into the `with:` block.
2. Branch the `generate_prompt` on it: template mode instructs the model to write
   `manifest.yaml` + exactly one `template.*.j2` + `data.json` under a `.llat/`
   directory in `run_dir`, per the contract `artifact_templates.py` enforces.
3. Add the per-iteration `ll-artifact render` step and repoint `artifact_path` at
   its output so the screenshot/score/critique cycle runs unchanged.
4. Make a render failure surface as a render error through the ENH-2903 abandon
   path rather than a bare screenshot-miss.
5. Update `finalize_done`'s reported output paths for template mode.
6. Conformance + `file`-mode regression tests; docs.
7. **Report the observed reliability** — how often the model produced a
   schema-valid template first try, and after critique. This number is the input
   to the follow-up decision about the other eight loops.

## Impact

- **Priority**: P2 — without a producer, FEAT-3318's plumbing is inert and every
  loop→template route stays on the lossy `templatize` path.
- **Effort**: Medium — one loop file, but the per-iteration render step and its
  failure path are real work.
- **Risk**: Medium — the reliability of LLM-emitted schema-valid templates is
  unproven; that is what this issue measures. Contained: the default mode is
  untouched and the shared oracle is not forked.
- **Breaking Change**: No — new behavior is opt-in behind a context var.

## Use Case

A user runs `html-anything` in template mode over an architecture document. The
run produces a `.llat/` the user renders against an updated `data.json` next
month — no LLM call, no `templatize` round trip, no fidelity loss.

## Acceptance Criteria

- [ ] `ll-loop run html-anything --context artifact_mode=template` produces a
      `.llat/` directory that passes FEAT-3318's runtime gate and is rendered by
      `ll-artifact render` with no `templatize` step.
- [ ] The default (`file`) path is unchanged — same prompt, same `index.html`, same
      reported outputs; a regression test pins this.
- [ ] `oracles/generator-evaluator.yaml` is **not** forked or branched on artifact
      mode; template mode is expressed entirely through its existing
      `artifact_path` / `generate_prompt` parameters.
- [ ] The screenshot/rubric/critique iterate cycle works in template mode — a
      low-scoring template is critiqued and regenerated, not abandoned.
- [ ] A template that fails to render surfaces the render error, not a generic
      missing-screenshot message.
- [ ] `test_builtin_loops.py` conformance passes for both modes.
- [ ] The issue records an observed first-try and post-critique success rate for
      schema-valid template emission.

## Related Key Documentation

- `.issues/features/P2-FEAT-3318-artifact-mode-template-loops-emit-template-data-natively.md`
  — the plumbing this consumes; see its § Generate-prompt variant and § Mode selection
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design principle 1
- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md`
  — the lossy fallback this exists to avoid (**done**)

## Status

**Open** | Created: 2026-08-25 | Priority: P2
