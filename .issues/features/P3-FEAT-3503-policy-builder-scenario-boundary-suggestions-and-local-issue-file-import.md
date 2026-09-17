---
id: FEAT-3503
type: FEAT
title: Policy builder scenario boundary suggestions and local issue-file import
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T22:31:55Z'
parent: EPIC-3493
labels:
- policy-builder
blocked_by:
- FEAT-3488
relates_to:
- FEAT-3498
---

# FEAT-3503: Policy builder scenario boundary suggestions and local issue-file import

## Summary

Add deterministic boundary-case suggestions and offline local issue-file import to the policy builder's scenario suites. Extracted from FEAT-3488 on 2026-09-17 (its second natural split after FEAT-3501) so the core suite work — wrapper persistence, shared trace, verdicts, Run all, coverage — can land first. Everything here consumes FEAT-3488's `Scenario`/`ScenarioInput` contracts, `normalizeScenarioInput`, `parseFrontmatterBlock`'s supported-subset validation, and the committed-edit path; nothing here changes routing semantics.

## Current Behavior

After FEAT-3488, scenarios are authored by hand only: there is no generator for missing-field or threshold-boundary cases, and the only way to get a lifecycle case from a real issue file is to paste its frontmatter into the scenario input. `parseFrontmatterBlock` (post-FEAT-3488) rejects the unsupported YAML subset, but nothing extracts a fenced frontmatter block from a full Markdown file or guards an asynchronous `FileReader` completion against the project changing underneath it.

## Expected Behavior

Users click "Suggest cases" to add deterministic, deduplicated, unasserted boundary cases for the active draft's mode, and import a local issue `.md` file as one unasserted lifecycle case without the page reading anything but the opening frontmatter block. Both actions are single committed edits: undo removes exactly what they added, and any failure leaves the suite unchanged.

## Motivation

Hand-authored suites miss exactly the cases that matter: the value one below a threshold, the field that is absent, the fallback nobody wrote an example for. Suggestions make those boundaries one click away without inventing expectations, and file import lets a maintainer test a policy against the real issues in `.issues/` instead of retyped frontmatter. Splitting these from FEAT-3488 keeps that issue to the persistence/trace/verdict core (outcome confidence 58/100 with 22 ACs before the split) and gives the asynchronous-import invariants their own verification surface.

## Proposed Solution

- `suggestScenarios(model) -> SuggestedScenario[]` in `policy_builder_core.mjs`, pure and deterministic. Suggest missing-field cases and just-below/at/above numeric thresholds using deterministic finite values; deduplicate; every suggestion has `expectedTarget: null` (suggestions never manufacture their own test oracle). Cover repeated targets, explicit lifecycle terminals from ENH-3492, the derived fallback, absent values, and threshold equality.

  Every suggestion for a valid model (FEAT-3488's routing-relevant definition) must pass `normalizeScenarioInput`. Decision-table numeric suggestions stay in [0,100]. Rubric suggestions are integers: for each threshold `t` emit `t-1`, `t`, `t+1` clamped to [0,100] and deduplicated (the runtime aggregate is `int()` of an `AGGREGATE:\s*(\d+)` match, so fractional neighbours are not representable — see FEAT-3488's rubric contract). Lifecycle suggestions use source fields the encoder accepts: generate `priority: Pn` for `priority_rank`, not a literal `priority_rank` field, and real lists for list-length predicates. Priority ranks and list lengths have discrete representable domains; choose representable neighbours on the intended side of a threshold and skip impossible equality/neighbour cases rather than emit invalid inputs.

- Identity: suggestions carry a deterministic content `key` (canonical JSON of `{mode, input}`), not an `id`. The template assigns each inserted case a unique `id` at insertion time using the same generator as ordinary "Add case" (FEAT-3488 pins that generator); "Add suggestions" skips any suggestion whose normalized input already equals an existing case's input in the destination suite, so re-running the action is idempotent and never creates duplicate IDs or duplicate cases. Adding N suggestions is one committed edit; undo removes all N.

- `extractIssueFrontmatter(text) -> string` in core: accept a leading UTF-8 BOM if present, and CRLF; require a complete opening `---`-delimited block at the start of the file; return only its contents; throw a diagnostic naming the defect (missing opening fence, unclosed fence) before any suite mutation. The Markdown body is never inspected. The returned text then goes through `parseFrontmatterBlock` (which owns unsupported-subset rejection per FEAT-3488, a hard prerequisite) and `normalizeScenarioInput`. Only file import requires a fenced block; the paste path and `{frontmatterText}` scenario input keep FEAT-3488's fence-tolerant behaviour.

- Template import: a file input plus `FileReader`. Complete extraction, parsing, and input validation before adding a scenario in one committed edit; any read/validation failure leaves the existing suite unchanged and reports the diagnostic in a dedicated element. Imported cases start unasserted, named from the file's `id` frontmatter when present, else the filename.

  The `FileReader` completion is bound to the project, destination lifecycle draft, and edit revision captured when import begins. Discard the completion with a diagnostic if that context changed before the read finishes — mode switch, Open, preset/start-blank, undo/redo, or any other committed edit. Use a monotonic session revision (incremented in `commit()`, Open, and snapshot restoration) as the invalidation token so switching away and back does not revive a pending read. A discarded completion makes no suite or history change; a successful current completion adds exactly one case in one committed edit.

- No skill, shell, LLM, or issue mutation executes from suggestions or imports.

## Integration Map

- Modify `scripts/little_loops/templates/policy_builder_core.mjs`: `suggestScenarios`, `extractIssueFrontmatter`; export both through the browser-global bridge.
- Modify `scripts/little_loops/templates/policy-router-builder.html.tmpl`: "Suggest cases" button, file input + `FileReader` wiring, session revision counter, import diagnostics element; all mutations go through FEAT-3488's suite-edit path and `commit()`.
- Regenerate the golden HTML through the generator (`scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`), never by hand-editing embedded JS.
- Tests: `scripts/tests/js/policy_scenarios.test.mjs` (created by FEAT-3488; the node gate globs `scripts/tests/js/*.test.mjs`), `scripts/tests/test_policy_builder_emit.py` for the golden HTML.
- Browser probes: `.loops/probes/feat-3488-browser-probes.mjs` `local-issue-import-offline` (tagged `needs: FEAT-3503`) plus a new delayed-read probe that monkeypatches `FileReader` via `page.evaluate` to defer `onload` until after a mode switch/Open/undo, asserting no case and no history entry is added; and a suggest-cases probe (deterministic count, idempotent second click, one undo removes all). Run via `.loops/verify-feat-3488-browser-persistence.yaml` after filling `SCENARIO_SELECTORS`.
- Documentation: `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` gain the suggestions and import subsections.
- No server, transport, queue, MCP, or config changes.

## Program Design

### Types

`SuggestedScenario {key: string, name: string, input: ScenarioInput, expectedTarget: null, reason: string}` — `reason` is a short human label ("just below high threshold", "priority absent"). `ScenarioInput` per mode is FEAT-3488's.

### Signatures

- `suggestScenarios(model) -> SuggestedScenario[]` — deterministic order (dimension order, then threshold order, then below/at/above); empty for an invalid model.
- `extractIssueFrontmatter(text) -> string` — throws `Error` with a diagnostic; never returns partial text.

### Call Path

Suggest: click → `suggestScenarios(buildModel())` → filter against existing inputs → assign ids → one suite edit → `commit()`.
Import: file change → capture `{projectId, mode, revision}` → `FileReader.readAsText` → on load: revision check → `extractIssueFrontmatter` → `parseFrontmatterBlock` → `normalizeScenarioInput` → one suite edit → `commit()`; any throw before the edit reports and returns.

## Implementation Steps

1. Implement `suggestScenarios` with per-mode representable-domain rules and node tests proving every suggestion normalizes and encodes to its intended boundary.
2. Implement `extractIssueFrontmatter` with BOM/CRLF/fence fixtures.
3. Wire suggest and import into the template with the session revision token; regenerate golden HTML.
4. Add the delayed-read and suggest-cases probes, fill `SCENARIO_SELECTORS`, run the browser loop; update docs.

## Impact

- Priority: P3 — same value tier as FEAT-3488; useful only once suites exist.
- Effort: Medium — two pure helpers plus template wiring and probes; the hard invariants (representable domains, async invalidation) are already specified.
- Risk: Low — additive; no routing or persistence semantics change.
- Breaking change: No.

## Acceptance Criteria

- [ ] Suggestions are deterministic, deduplicated, unasserted, and include absent fields and numeric boundaries without nonfinite/out-of-range inputs. Every generated suggestion for a valid model passes `normalizeScenarioInput`. Decision-table bounds are respected; rubric suggestions are integers `t-1`/`t`/`t+1` clamped to [0,100]; lifecycle priority/list suggestions encode to their intended representable boundaries, and impossible neighbours/equalities are omitted.
- [ ] Coverage after adding suggestions exercises ENH-3492 terminal targets and the derived fallback for the seeded lifecycle and decision-table examples (routing coverage, not assertion coverage).
- [ ] "Add suggestions" twice yields no duplicate cases and no duplicate IDs; one undo removes every case the click added.
- [ ] A complete issue Markdown file imports successfully without parsing its body; BOM/CRLF are handled. Missing/unclosed fences, unsupported frontmatter, and read failures produce diagnostics without altering the suite. Successful import adds one unasserted case and is undoable. The lifecycle paste path still accepts fence-less frontmatter.
- [ ] Delayed-read browser checks start an import, then switch modes, Open, apply a preset/start-blank, undo/redo, or commit another edit before completion. Stale completions add no case or history entry, even after switching away and back; a current successful completion adds exactly one undoable case to the captured lifecycle draft.
- [ ] Scenarios, suggestions, and imports execute no actions and make no predictions about LLM/action effects.
- [ ] Golden HTML regenerated; Node and Python gates pass; `ll-loop run .loops/verify-feat-3488-browser-persistence.yaml` passes with the import, delayed-read, and suggest-cases probes green.
- [ ] `docs/guides/POLICY_ROUTER_GUIDE.md` and the policy-builder section of `docs/reference/CLI.md` document boundary suggestions and local issue-file import.

## Use Case

A maintainer opens the issue-lifecycle draft, clicks "Suggest cases" to get the threshold and missing-field boundaries, then imports three real issue files from `.issues/` to see where each routes — without any of them being run.

## Scope Boundaries

Includes boundary suggestions and local file import only. Excludes connected issue discovery (FEAT-3498), transition analysis (FEAT-3501), and arbitrary YAML import. Suite persistence, verdicts, coverage, and subset validation are FEAT-3488's.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Routing, lifecycle semantics, simulation limits |
| Reference | docs/reference/CLI.md | Builder usage |

## Status

**Open** | Created: 2026-09-17 | Priority: P3

## Session Log

- manual review - 2026-09-17 - extracted from FEAT-3488 (boundary suggestions, local issue-file import, `FileReader` invalidation, delayed-read probes); pinned integer rubric neighbours, suggestion `key` vs template-assigned `id`, idempotent "Add suggestions"
