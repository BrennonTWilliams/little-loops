---
id: ENH-3560
type: ENH
title: Remove interpolated innerHTML sinks from policy builder
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
completed_at: '2026-09-24T21:36:04Z'
parent: EPIC-3556
labels:
- security
- artifacts
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3560: Remove interpolated innerHTML sinks from policy builder

## Summary

Replace the three `innerHTML` assignments in `policy-router-builder.html.tmpl` that interpolate model state (dimension name/type, outcome names) with `createElement` + `textContent`. Add a Node test that renders a hostile project through the stubbed-DOM `vm` harness, plus a static check that fails on any `innerHTML` / `insertAdjacentHTML` right-hand side that is not a constant string literal.

Carved out of cancelled ENH-3540 (Scope §6); see that file for the full research trail.

## Current Behavior

Script-context-safe JSON splices (ENH-3557) only protect the HTML parser. The builder's client JS then interpolates model state into `innerHTML`:

- `scripts/little_loops/templates/policy-router-builder.html.tmpl:832,839` (`renderDimensions`): builds `` let html = `<strong>${norm}</strong> <em>(${d.type})</em>` `` (plus constant `<small>` suffixes for built-ins), then assigns `row.innerHTML = html`.
- `:926` (`renderOutcomes`) and `:1038` (`renderLifecycleOutcomes`): `` title.innerHTML = `<strong>${oc.name}</strong>` ``.

That state arrives from **Open project** (`parseBuilderProject`, called at `:2264`; its `validateProjectStructure` in `policy_builder_core.mjs:993` checks shape only, never names), from localStorage drafts, and from serve-mode revisions. A shared project file with an outcome named `<img src=x onerror=alert(1)>` executes script on open. `normalizeDimName` (`policy_builder_core.mjs:320`) only trims, lowercases, and hyphenates whitespace; it does not sanitize.

The skill catalog is already safe client-side: it reaches the DOM only via `textContent` / `title`. All other `innerHTML` / `insertAdjacentHTML` uses in the template assign constant strings (`= ""`, fixed `<label>` markup).

## Expected Behavior

- The builder's client JS never passes model-derived strings to `innerHTML` or `insertAdjacentHTML`; a hostile project opened in the builder renders as inert text.
- A static check prevents new interpolated sinks, including the indirect form (build a string in a variable, then assign the variable).

## Motivation

Builder project files are meant to be shared. Opening someone else's project should not run their script. This is client-side DOM XSS, independent of the server-side escaping in ENH-3557/ENH-3558.

## Proposed Solution

1. **Rewrite the three sinks** with `createElement` + `textContent`: a `<strong>` whose `textContent` is the name; for dimensions, an `<em>` whose `textContent` is `(${d.type})` and the constant `<small class="help">` hints built the same way. Keep the visible output identical for benign names. Leave the constant-string assignments alone.
2. **Static check** in a new Node test: scan `policy-router-builder.html.tmpl` for every `.innerHTML =`, `.innerHTML +=`, `.outerHTML =`, and `insertAdjacentHTML(` call. The right-hand side (or the second argument) must be a single constant string literal: `"..."`, `'...'`, or a backtick literal with no `${`. Any identifier, concatenation, call, or interpolated template literal fails. A site the scanner can't classify fails closed. (A check that only flags template literals containing `${` would pass the current `:839` sink, which assigns a variable.)
3. **Hostile-project render test** using the existing stubbed-DOM `vm` harness (the suite has no jsdom and must stay zero-dependency):
   - Pull `renderDimensions`, `renderOutcomes`, and `renderLifecycleOutcomes` source out of the template with `_extractBetween` (`scripts/tests/js/policy_validator.test.mjs:1519`, template path at `:1514`), and run it in `vm.createContext` with a stub `document` / `$` like the BUG-3516 sandbox (`policy_validator.test.mjs:1873`).
   - The stub `createElement` returns element objects that record `innerHTML` assignments, `textContent`, and children.
   - Build `state` from a project parsed with `parseBuilderProject` (the Open path) whose outcome name, dimension name, and dimension type are `<img src=x onerror=alert(1)>`.
   - Assert: no recorded `innerHTML` assignment contains `<img`, and the payload appears verbatim in some element's `textContent`. Note `renderDimensions` renders the *normalized* dimension name (`normalizeDimName` hyphenates whitespace, so `<img src=x onerror=alert(1)>` becomes `<img-src=x-onerror=alert(1)>`); the verbatim assertion holds for the outcome name and the dimension type, not the dimension name. For the dimension name, assert the normalized text is in `textContent` and no `<img` reaches `innerHTML`.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — `renderDimensions`, `renderOutcomes`, `renderLifecycleOutcomes`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/policy_builder.py` (`render_policy_builder_html`) and `cli/artifact/serve.py` emit the template; no change.
- `scripts/tests/test_policy_builder_node_gate.py` — runs every `scripts/tests/js/*.test.mjs` under `node --test`, so a new test file is picked up automatically.

### Similar Patterns
- `_extractBetween` and the stub-`document` `vm` sandboxes in `scripts/tests/js/policy_validator.test.mjs` (BUG-3502 bootstrap, BUG-3516 try-it).
- The skill-catalog rendering in the same template (`textContent` / `title`) is the target idiom.

### Tests
- `scripts/tests/js/policy_builder_dom_sinks.test.mjs` (new) — the static check and the hostile-project render test.
- `scripts/tests/test_policy_builder_node_gate.py` — the pytest wrapper that enforces it in the default suite (skips gracefully without Node ≥ 22).

### Documentation
- N/A

### Configuration
- N/A

## Program Design

### Signatures
- `renderDimensions() -> void` — existing, inline in `policy-router-builder.html.tmpl`. Builds the dimension row with `createElement` + `textContent`.
- `renderOutcomes() -> void` / `renderLifecycleOutcomes() -> void` — existing, inline in the same template. Build the outcome title with `createElement` + `textContent`.
- `parseBuilderProject(text: string) -> object` — existing, exported from `policy_builder_core.mjs`. Unchanged; the test uses it as the Open path.

### Call Path
`cmd_policy_builder` -> `render_policy_builder_html` (emits the template) -> browser: `parseBuilderProject` -> `renderAll` -> `renderDimensions` / `renderOutcomes` / `renderLifecycleOutcomes` -> `createElement` + `textContent`
`test_node_conformance_suite_passes` -> `node --test` -> `policy_builder_dom_sinks.test.mjs` -> `_extractBetween` -> `vm.runInContext`

### Decision Rules
- Client DOM rule: builder JS writes model-derived strings only via `textContent`, attribute setters, or `createElement`; `innerHTML`, `outerHTML`, and `insertAdjacentHTML` take constant string literals only.

## Implementation Steps

1. Write `policy_builder_dom_sinks.test.mjs` with the static check and the hostile-project render test; confirm both fail against the current template.
2. Rewrite the three sinks; confirm both tests pass and benign names render the same text as before.
3. Run `node --test scripts/tests/js/*.test.mjs` and `python -m pytest scripts/tests/test_policy_builder_node_gate.py scripts/tests/test_policy_builder_emit.py`.

## Impact

- **Priority**: P1 — opening a shared project file runs the author's script.
- **Effort**: Small — three sinks, one new Node test file.
- **Risk**: Low — client-only change; visible output unchanged for benign names.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: the three interpolating sinks; the static constant-literal check; the hostile-project render test.
- **Out of scope**: server-side JSON splices (ENH-3557); template data escaping (ENH-3558); write paths (ENH-3559); name validation in `validateProjectStructure` (rendering as text is the fix; names stay free-form); `policy_builder_core.mjs` (no `innerHTML` use).

## Acceptance Criteria

- [ ] `renderDimensions`, `renderOutcomes`, and `renderLifecycleOutcomes` assign no model-derived string to `innerHTML`.
- [ ] A Node test renders a project (parsed via `parseBuilderProject`) whose outcome name, dimension name, and dimension type are `<img src=x onerror=alert(1)>` through the three render functions in a stub-DOM `vm` sandbox, and asserts no recorded `innerHTML` assignment contains `<img` and the payload appears verbatim in `textContent`.
- [ ] A static check fails on any `innerHTML` / `outerHTML` assignment or `insertAdjacentHTML` call in `policy-router-builder.html.tmpl` whose value is not a constant string literal, including a bare variable; it fails against the pre-fix template (the `:839` variable assignment).
- [ ] Both run in the default `python -m pytest scripts/tests/` tier via `test_policy_builder_node_gate.py`.

## Related

- EPIC-3556 (parent); ENH-3540 (cancelled, original spec)

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Verified against code 2026-09-24: sinks at `policy-router-builder.html.tmpl:832,839,926,1038`; `parseBuilderProject` call at `:2264`; `validateProjectStructure` (`policy_builder_core.mjs:993`) and `normalizeDimName` (`:320`); `_extractBetween` and `TEMPLATE_PATH` in `policy_validator.test.mjs`; every other `innerHTML`/`insertAdjacentHTML` in the template assigns a constant string; `policy_builder_core.mjs` has no `innerHTML` use.
- Corrected: the Proposed Solution's "payload appears verbatim in `textContent`" assertion does not hold for the dimension name, which is normalized before rendering (see §3 note).
- Evidence-quote check: clean. Decisions log: no active required rules.

## Status

**Open** | Created: 2026-09-24 | Priority: P1


## Session Log
- `/ll:manage-issue` - 2026-09-24T21:36:04 - `6ccc1d18-22f1-45e0-8c52-048e322d5f5e.jsonl`
- `/ll:ready-issue` - 2026-09-24T21:26:48 - `b6953986-b219-42cc-bc3f-27862cccccee.jsonl`
- `/ll:confidence-check` - 2026-09-24T21:21:37 - `2c0fb02b-c823-4a59-94a2-1bc2d90ae255.jsonl`
- `/ll:verify-issues` - 2026-09-24T19:13:36 - `27bdfde5-d1ef-4e98-b8ff-2728ac43d651.jsonl`
- `/ll:scope-epic` - 2026-09-24T18:30:40 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - ported ENH-3540 Scope §6 and ACs into this child; widened the static check to constant-literal-only (the `${`-only rule missed the `:839` variable assignment); specified the stub-DOM `vm` harness (no jsdom in the zero-dependency suite)

## Resolution

- Rewrote the three interpolated `innerHTML` sinks in `renderDimensions`, `renderOutcomes`, `renderLifecycleOutcomes` with `createElement` + `textContent`.
- Added `scripts/tests/js/policy_builder_dom_sinks.test.mjs`: fail-closed constant-literal scan of every `innerHTML`/`outerHTML`/`insertAdjacentHTML` write, plus a stub-DOM `vm` hostile-project render test.
- Regenerated `golden_policy_router_builder.html` (pinned render inputs).
- Full suite: 25473 passed; 2 pre-existing unrelated failures (`test_no_new_unverifiable_evidence` on BUG-1688, `test_autodev_topology` state count).
