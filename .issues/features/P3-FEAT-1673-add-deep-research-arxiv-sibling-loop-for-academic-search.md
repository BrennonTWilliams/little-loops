---
id: FEAT-1673
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-24
discovered_by: capture-issue
captured_at: '2026-05-24T07:09:02Z'
completed_at: '2026-05-24T07:38:47Z'
parent: FEAT-1540
relates_to:
- FEAT-1540
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1673: Add deep-research-arxiv sibling loop for academic search

## Summary

Add a sibling built-in FSM loop `deep-research-arxiv` that specializes the existing `deep-research` loop (FEAT-1540) for arxiv-only academic research. Constrains web search to `site:arxiv.org`, replaces the credibility scoring axis with a recency axis derived from arxiv submission dates, and emits BibTeX-friendly arxiv-ID citations in the synthesis output. Structure, state graph, convergence rules, and run-dir conventions are kept identical to the parent loop so the two stay maintainable as a pair.

## Current Behavior

The existing `scripts/little_loops/loops/deep-research.yaml` is a general-purpose iterative web-research loop. When the user runs it against an arxiv-only topic, three prompts fit poorly:

- `search_web` casts too wide a net — hits blog posts, news, and marketing pages when the user only wants peer-reviewable preprints.
- `evaluate_sources` scores `credibility (1–5)`, which flattens on arxiv (everything is academic preprint) and stops differentiating sources.
- `synthesize` emits a generic URL-keyed sources table; for academic synthesis the user wants arxiv-ID citations that are BibTeX-friendly.

## Expected Behavior

Users can run:

```bash
ll-loop run deep-research-arxiv "speculative decoding for LLM inference"
```

The loop:
1. Generates academic-style search queries (method names, problem formulations) constrained to `site:arxiv.org`
2. Fetches arxiv abstract pages for metadata (arxiv ID, authors, submission date, optional Journal-ref)
3. Scores sources on relevance + recency (instead of relevance + credibility)
4. Identifies coverage gaps and iterates
5. Emits a `report.md` with an arxiv-ID-keyed source table AND a `## BibTeX` section containing `@misc{...}` entries ready to drop into a LaTeX bibliography

## Motivation

The user runs `deep-research` frequently against arxiv-only topics. Rather than fork behavior with context flags inside `deep-research.yaml` (which would bloat all three prompts and degrade both modes), a sibling loop specializes only the prompts that diverge. This keeps each loop's prompts focused while sharing the proven FSM skeleton from FEAT-1540.

## Use Case

A researcher exploring a technical subfield (e.g., "speculative decoding for LLM inference") needs to survey the relevant arxiv literature, score papers by recency and relevance, and produce a citation-ready report. Instead of running general `deep-research` and manually filtering non-academic sources, they run `ll-loop run deep-research-arxiv "<topic>"` and receive a `report.md` whose sources table is keyed by arxiv ID, with a `## BibTeX` section that drops directly into their `.bib` file.

## Acceptance Criteria

- [ ] `ll-loop list` includes `deep-research-arxiv` (auto-discovery confirmed)
- [ ] `ll-loop validate deep-research-arxiv` passes schema validation
- [ ] `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` passes with `"deep-research-arxiv"` added to the `expected` set
- [ ] `ll-loop run deep-research-arxiv "speculative decoding for LLM inference" --max-iterations 1` lands in `.loops/research/speculative-decoding-for-llm-inference/` and creates `report.md`, `knowledge-base.md`, `coverage.md`, `query-log.md`
- [ ] In a converged run, `report.md` contains a sources table with columns `arXiv ID | Title | Authors | Year | Relevance | Recency | Facet`
- [ ] In a converged run, `report.md` contains a `## BibTeX` section with at least one `@misc{...}` entry keyed by arxiv ID
- [ ] `knowledge-base.md` URLs are predominantly `arxiv.org/abs/...` (spot-check)
- [ ] Source annotations carry `recency:` (not `credibility:`) with the 1–5 scale derived from arxiv submission date
- [ ] Top-level fields match the parent loop: `category: research`, `input_key: topic`, `max_iterations: 30`, `timeout: 3600`, `context.output_dir: ".loops/research"`, `context.depth: 3`, `context.coverage_threshold_pct: 85`
- [ ] Convergence rule preserved: `avg >= 4.0 AND iter >= depth`

## Proposed Solution

Create `scripts/little_loops/loops/deep-research-arxiv.yaml`. Copy the structure of `deep-research.yaml` exactly — same state names, same edges, same `captured.run_dir.output` pattern, same convergence rules — and specialize only these prompts:

1. **`search_web`** — instruct the LLM to constrain every `WebSearch` query with `site:arxiv.org` (preferring `arxiv.org/abs/` pages), and to `WebFetch` the abstract pages for metadata (arxiv ID, authors, submission date, optional Journal-ref). Drop the "blog posts, official documentation" language from the original.

2. **`evaluate_sources`** — replace the credibility axis with **recency** on a 1–5 scale derived from the arxiv submission date (5 = within 6 months of today, 4 = ≤1yr, 3 = ≤2yr, 2 = ≤5yr, 1 = >5yr). Keep the relevance axis unchanged. Annotation format becomes `[Source: <arxiv-url>] (relevance: N/5, recency: N/5, arxiv-id: YYMM.NNNNN)`. Dedup logic unchanged.

3. **`synthesize`** — replace the `| # | URL | Relevance | Credibility | Facet |` sources table with `| # | arXiv ID | Title | Authors | Year | Relevance | Recency | Facet |`, and emit a `## BibTeX` section at the end with `@misc{...}` entries keyed by arxiv ID.

4. **`generate_queries`** and **`plan_next`** — minor wording tweak: instruct the LLM to phrase queries in academic terminology (method names, problem formulations) rather than informal/how-to phrasing. No structural change.

Unchanged states (verbatim copies): `init`, `score_coverage`, `plan_next` (structure), `done`.

**Decisions ruled out** (per Q&A during planning):
- No `arxiv_category` context field — the topic string itself can mention the subfield.
- No `venue-uptake` axis — too flaky to extract reliably from the abstract page.

## Integration Map

### Files to Modify

- **Create** `scripts/little_loops/loops/deep-research-arxiv.yaml` — the new sibling loop (~290 lines, paralleling `deep-research.yaml`)
- `scripts/tests/test_builtin_loops.py` — add `"deep-research-arxiv"` to the `expected` set in `TestBuiltinLoopFiles::test_expected_loops_exist` (~line 65). The auto-discovery scan picks the file up, but this hardcoded set is the canary that fails CI if a new loop is forgotten.
- `scripts/little_loops/loops/README.md` — add a **table row** for `deep-research-arxiv` in the "Research & Knowledge" section adjacent to the existing `deep-research` entry. The section is a 3-column markdown table with header `| Loop | Description | Primary Inputs |`; the existing `deep-research` row is at line 58 (insert the new row at line 59).

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — increment "52 FSM loops" → "53 FSM loops" (line 167). Enforced by `doc_counts.py:verify_documentation()` — `ll-verify-docs` exits 1 without this update. [Agent 1 / Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — add `deep-research-arxiv` row to the "Research & Knowledge" named table (~line 344) adjacent to the existing `deep-research` row. [Agent 2 finding]
- `scripts/tests/test_deep_research_arxiv.py` — new dedicated test file following the `test_deep_research.py` pattern (see Tests section below). Established sibling convention; escalated from "out of scope" in the Tests section. [Agent 3 finding]

### Dependent Files (Callers/Importers)

This is a **new built-in loop** with no callers at v1. Discovery happens automatically — the file is found at runtime by:

- `scripts/little_loops/cli/loop/info.py:127,137` — auto-discovery via `rglob("*.yaml")` filtered by `is_runnable_loop()`
- `scripts/little_loops/cli/loop/_helpers.py:395` — `get_builtin_loops_dir()` returns `Path(__file__).parent.parent.parent / "loops"`, so top-level placement at `scripts/little_loops/loops/deep-research-arxiv.yaml` is sufficient
- `scripts/little_loops/fsm/validation.py:897` — accepts any YAML with `name`, `initial`, `states`

No code changes required for registration.

### Similar Patterns

**Primary reference (parent loop — copy as starting template):**
- `scripts/little_loops/loops/deep-research.yaml` (FEAT-1540) — same structural pattern: shell `init` captures `run_dir`, prompt states cycle through query generation → web search → evaluation → coverage scoring → planning → synthesis with sentinel-based convergence.

**Convergence pattern (preserved verbatim):**
- `scripts/little_loops/loops/rn-plan.yaml:231-268` (state `score`) — inline sentinel convergence via `output_contains` (Option A from FEAT-1540). In `deep-research.yaml`, this same pattern lives in the `score_coverage` state at lines 135–177: the prompt instructs the LLM to emit exactly `COVERAGE_SUFFICIENT` or `NEED_MORE`, and the state routes via `evaluate.type: output_contains` / `pattern: "COVERAGE_SUFFICIENT"` / `on_yes: synthesize` / `on_no: plan_next` / `on_error: synthesize`. **Both sentinel tokens and the routing block must be preserved verbatim** in the arxiv sibling — only the surrounding prompt text changes.

**Existing sibling-loop pairs (precedent for the FEAT-1673 pattern):**
- `rn-plan` / `rn-plan-apo` — base planner + APO variant
- `harness-single-shot` / `harness-multi-item` / `harness-optimize` — harness family
- `apo-feedback-refinement` / `apo-contrastive` / `apo-opro` / `apo-beam` / `apo-textgrad` — APO family
- `issue-refinement` / `refine-to-ready-issue` / `recursive-refine` — refinement family

The "sibling loop that specializes a few prompts of a parent" pattern is established convention here, not novel.

### Tests

- **Update** `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"deep-research-arxiv"` to the `expected` set (unordered Python set literal, currently 51 entries; this is the 52nd). The `expected` set's matching `actual` comes from `{f.stem for f in BUILTIN_LOOPS_DIR.glob("*.yaml")}`, so dropping the YAML without updating the set fails the assertion.
- **Auto-coverage from generic structural tests** — adding the new loop YAML automatically gets it covered by these tests in the same file (no edits needed):
  - `test_all_parse_as_yaml` (line 29) — YAML parsing
  - `test_all_validate_as_valid_fsm` (line 36) — FSM schema validation
  - `test_all_have_description_field` (line 46) — `description:` field presence
  - `test_no_bare_pass_token_in_output_contains` (line 124) — guards against bare `PASS` sentinels
  - `test_all_failure_terminals_have_diagnostic_action` (line 144) — pre-terminal `diagnose` validation
- `scripts/tests/test_deep_research.py` — existing dedicated test file (22 tests, 5 classes) for the parent loop; serves as the template for the sibling. Covers: `TestDeepResearchYaml` (16 structural assertions), `TestDeepResearchShellStates` (init shell execution), `TestDeepResearchEvaluators` (sentinel unit tests), `TestDeepResearchResolution` (builtin resolver), `TestDeepResearchDryRun` (CLI smoke). [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_deep_research_arxiv.py` — **recommended new test file** (escalated from "out of scope for v1"). The established sibling-loop pattern (`test_rn_plan_apo.py`, `test_rn_refine.py`) always produces a dedicated test file per loop. Follow the `test_deep_research.py` pattern: 5 classes, ~22 tests. Key adaptations: replace `"deep-research"` → `"deep-research-arxiv"` throughout, fallback slug `"deep-research-run"` → `"deep-research-arxiv-run"`, update `test_required_top_level_fields` to assert `name == "deep-research-arxiv"`, update `test_required_states_exist` if any state names change, add assertions for `recency:` annotations (not `credibility:`). [Agent 3 finding]

### Documentation

- `scripts/little_loops/loops/README.md` — add a bullet for `deep-research-arxiv` in the "Research & Knowledge" section adjacent to the existing `deep-research` entry (around line 58)

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` — increment "52 FSM loops" → "53 FSM loops" (line 167). Enforced by `doc_counts.py:verify_documentation()` — `ll-verify-docs` exits 1 without this update. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — add `deep-research-arxiv` row to the "Research & Knowledge" named table (~line 344) adjacent to the existing `deep-research` row. [Agent 2 finding]
- `docs/reference/loops.md` — optional: add a reference entry for `deep-research-arxiv` consistent with the existing `## \`deep-research\`` section (state graph, context variables, convergence description). [Agent 2 finding]

### Configuration

- N/A — no new config keys required. Inherits `--context KEY=VALUE` mechanism from parent loop.

## Implementation Steps

1. **Scaffold YAML** — copy `scripts/little_loops/loops/deep-research.yaml` to `scripts/little_loops/loops/deep-research-arxiv.yaml`. Update `name:` and `description:` only.
2. **Preserve top-level fields verbatim** — `category: research`, `input_key: topic`, `max_iterations: 30`, `timeout: 3600`, `context.output_dir: ".loops/research"`, `context.depth: 3`, `context.coverage_threshold_pct: 85`. Convergence rule preserved: `avg >= 4.0 AND iter >= depth`.
3. **Preserve `init` state verbatim** — same shell action, same `capture: run_dir`, same `$(pwd)/$DIR` absolute-path pattern.
4. **Specialize `generate_queries`** — minor wording: instruct LLM to phrase queries in academic terminology (method names, problem formulations) rather than informal/how-to phrasing. No structural change.
5. **Specialize `search_web`** — instruct LLM to constrain every `WebSearch` query with `site:arxiv.org` (preferring `arxiv.org/abs/` pages), and to `WebFetch` abstract pages for arxiv ID, authors, submission date, optional Journal-ref. Drop "blog posts, official documentation" language from the original.
6. **Specialize `evaluate_sources`** — replace credibility axis with recency on a 1–5 scale derived from arxiv submission date (5 = within 6 months of today, 4 = ≤1yr, 3 = ≤2yr, 2 = ≤5yr, 1 = >5yr). Keep relevance axis unchanged. Annotation format: `[Source: <arxiv-url>] (relevance: N/5, recency: N/5, arxiv-id: YYMM.NNNNN)`.
7. **Preserve `score_coverage` verbatim** — convergence rule and sentinel tokens unchanged. Specifically, keep the `evaluate.type: output_contains` / `pattern: "COVERAGE_SUFFICIENT"` / `on_yes: synthesize` / `on_no: plan_next` / `on_error: synthesize` routing block, and keep the prompt instruction that the LLM must output exactly `COVERAGE_SUFFICIENT` or `NEED_MORE` (lines 135–177 of the parent loop, with the routing block at the tail).
8. **Specialize `plan_next`** — minor wording tweak for academic terminology; structure unchanged.
9. **Specialize `synthesize`** — replace sources table columns with `| # | arXiv ID | Title | Authors | Year | Relevance | Recency | Facet |`. Emit a `## BibTeX` section at the end with `@misc{...}` entries keyed by arxiv ID.
10. **Preserve `done` state verbatim** — `terminal: true`.
11. **Validate registration** — `ll-loop list | grep deep-research-arxiv` and `ll-loop validate deep-research-arxiv`. Per project memory `feedback_nested_loops_runnable`, use `validate` (not `list`) as the canonical runnability check.
12. **Update test set** — edit `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` and add `"deep-research-arxiv"` to the `expected` set. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to confirm.
13. **Update loops README** — add a row for `deep-research-arxiv` in `scripts/little_loops/loops/README.md` "Research & Knowledge" section adjacent to the existing `deep-research` entry.
14. **End-to-end smoke run** — `ll-loop run deep-research-arxiv "speculative decoding for LLM inference" --max-iterations 1`. Spot-check `knowledge-base.md` URLs are predominantly `arxiv.org/abs/...` and annotations carry `recency:` not `credibility:`.
15. **Synthesis output check (after a converged run)** — open the final `report.md` and confirm the sources table columns are `arXiv ID | Title | Authors | Year | Relevance | Recency | Facet`, and that a `## BibTeX` section appears with at least one `@misc{...}` entry.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

16. **Update `README.md`** — increment "52 FSM loops" → "53 FSM loops" (line 167). Required: `doc_counts.py:verify_documentation()` scans `README.md` for the loop count pattern and `ll-verify-docs` exits 1 without this update.
17. **Update `docs/guides/LOOPS_GUIDE.md`** — add `deep-research-arxiv` row to the "Research & Knowledge" named table (~line 344), adjacent to the existing `deep-research` row. Keeps the guide's enumeration of the research family complete.
18. **Write `scripts/tests/test_deep_research_arxiv.py`** — new dedicated test file following `test_deep_research.py` pattern (5 classes, ~22 tests). Established sibling-loop convention overrides the earlier "out of scope" note. Adapt all hardcoded name strings; add assertion that `recency:` appears in evaluate annotations (not `credibility:`).
19. **(Optional) Update `docs/reference/loops.md`** — add `deep-research-arxiv` reference entry consistent with the existing `## \`deep-research\`` section. Not CI-blocking, but keeps the reference doc complete for the research loop family.

## Impact

- **Priority**: P3 — useful specialization with clear repeated workflow; not blocking other work
- **Effort**: Small — single YAML file paralleling an existing loop; no engine changes
- **Risk**: Low — sibling pattern keeps both loops independent; failures isolated to the new file
- **Breaking Change**: No — purely additive

## API/Interface

```yaml
# scripts/little_loops/loops/deep-research-arxiv.yaml (sketch)
name: deep-research-arxiv
category: research
input_key: topic
max_iterations: 30
timeout: 3600
context:
  output_dir: ".loops/research"
  depth: 3
  coverage_threshold_pct: 85
# (identical state graph to deep-research; specialized prompts in
#  search_web, evaluate_sources, synthesize, generate_queries, plan_next)
```

## Related Key Documentation

| Document | Relevance | Why |
|----------|-----------|-----|
| `.claude/CLAUDE.md` | High | Built-in loop conventions, FSM structure, file layout |
| `docs/reference/API.md` | Medium | Loop discovery API surface (no changes needed but reference) |

## Labels

`feat`, `loops`, `built-in-loop`, `research`, `arxiv`, `captured`

## Status

**Done** | Created: 2026-05-24 | Completed: 2026-05-24 | Priority: P3

## Resolution

Implemented as planned. Created `scripts/little_loops/loops/deep-research-arxiv.yaml` paralleling the parent `deep-research` loop structurally — same state graph (`init` → `generate_queries` → `search_web` → `evaluate_sources` → `score_coverage` → `plan_next` / `synthesize` → `done`), same `COVERAGE_SUFFICIENT` / `NEED_MORE` sentinel routing, same top-level fields (`category: research`, `input_key: topic`, `max_iterations: 30`, `timeout: 3600`, `context.output_dir: .loops/research`, `depth: 3`, `coverage_threshold_pct: 85`). Specialized only the five prompts that diverge:

- `search_web` constrains every WebSearch query with `site:arxiv.org` and instructs WebFetch on `arxiv.org/abs/<id>` for metadata extraction (arxiv ID, authors, submission date, optional Journal-ref).
- `evaluate_sources` replaces the credibility axis with **recency** (1–5 from arxiv submission date) and includes `arxiv-id:` in the annotation format so dedup is keyed by paper, not URL.
- `synthesize` swaps the sources table for `| # | arXiv ID | Title | Authors | Year | Relevance | Recency | Facet |` and appends a `## BibTeX` section with `@misc{...}` entries ready to drop into a `.bib` file. Used a 4-backtick outer markdown fence to unambiguously nest the inner `bibtex` code fence.
- `generate_queries` and `plan_next` carry a wording tweak nudging the LLM toward academic terminology (method names, problem formulations) instead of informal/how-to phrasing.

Wired in: `scripts/tests/test_builtin_loops.py` expected set (52 → 53 entries), new dedicated `scripts/tests/test_deep_research_arxiv.py` (31 tests across 5 classes — adds arxiv-specific assertions for `site:arxiv.org`, recency-not-credibility, arxiv-ID annotations, BibTeX section), `scripts/little_loops/loops/README.md` "Research & Knowledge" table row, `docs/guides/LOOPS_GUIDE.md` named table row, and root `README.md` loop count (52 → 54 — actual count was off by one in the wiring estimate because `doc_counts.py` rglobs nested loops).

All verification passed: `ll-loop validate deep-research-arxiv`, `ll-loop list` (loop visible with `[built-in]` tag), `ll-verify-docs` (all 10 counts match), and the full builtin-loops + deep-research test suite (495 passed).

## Session Log
- `/ll:manage-issue` - 2026-05-24T07:38:47Z - `92f99b2b-14c2-4ff7-94e7-d8d309f75b40.jsonl`
- `/ll:ready-issue` - 2026-05-24T07:33:03 - `995aa695-3c58-4826-8afa-21cb7bcdc032.jsonl`
- `/ll:confidence-check` - 2026-05-24T08:00:00Z - `2aaa4e23-87ed-4641-85ed-a9de682a4d82.jsonl`
- `/ll:wire-issue` - 2026-05-24T07:28:39 - `6928f817-2322-4383-8ed6-d30877fc7d71.jsonl`
- `/ll:refine-issue` - 2026-05-24T07:23:20 - `a811c0d3-136c-4394-b80a-ab4435a7e6a2.jsonl`
- `/ll:format-issue` - 2026-05-24T07:12:16 - `1faf9a9a-9e72-4c6e-95c6-08c2d631638f.jsonl`
- `/ll:capture-issue` - 2026-05-24T07:09:02Z - `e118fada-be27-4510-9c7c-e66238684c9d.jsonl`
