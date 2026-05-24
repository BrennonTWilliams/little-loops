---
id: FEAT-1673
type: FEAT
priority: P3
status: open
discovered_date: 2026-05-24
discovered_by: capture-issue
captured_at: '2026-05-24T07:09:02Z'
parent: FEAT-1540
relates_to:
  - FEAT-1540
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
- `scripts/little_loops/loops/README.md` — add a bullet/row for `deep-research-arxiv` in the "Research & Knowledge" section adjacent to the existing `deep-research` entry (around line 58)

No code changes outside these three files.

### Dependent Files (Callers/Importers)

This is a **new built-in loop** with no callers at v1. Discovery happens automatically — the file is found at runtime by:

- `scripts/little_loops/cli/loop/info.py:127` — auto-discovery via `rglob("*.yaml")`
- `scripts/little_loops/fsm/validation.py:897` — accepts any YAML with `name`, `initial`, `states`

No code changes required for registration.

### Similar Patterns

**Primary reference (parent loop — copy as starting template):**
- `scripts/little_loops/loops/deep-research.yaml` (FEAT-1540) — same structural pattern: shell `init` captures `run_dir`, prompt states cycle through query generation → web search → evaluation → coverage scoring → planning → synthesis with sentinel-based convergence.

**Convergence pattern (preserved verbatim):**
- `scripts/little_loops/loops/rn-plan.yaml:228-266` — inline sentinel convergence via `output_contains` (Option A from FEAT-1540)

### Tests

- **Update** `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — add `"deep-research-arxiv"` to the `expected` set. This file also exercises the bare-`PASS` check, `description:` presence, and pre-terminal `diagnose` validation against any new loop file, so adding the loop YAML automatically gets it covered by those generic structural checks.
- **No new dedicated test file required** — the sibling shares structure with `deep-research`, and dedicated `test_deep_research.py` tests already cover the FSM skeleton. Author may opt to add a small `test_deep_research_arxiv.py` later if the BibTeX synthesis output needs structural assertions; out of scope for v1.

### Documentation

- `scripts/little_loops/loops/README.md` — add a bullet for `deep-research-arxiv` in the "Research & Knowledge" section adjacent to the existing `deep-research` entry (around line 58)

### Configuration

- N/A — no new config keys required. Inherits `--context KEY=VALUE` mechanism from parent loop.

## Implementation Steps

1. **Scaffold YAML** — copy `scripts/little_loops/loops/deep-research.yaml` to `scripts/little_loops/loops/deep-research-arxiv.yaml`. Update `name:` and `description:` only.
2. **Preserve top-level fields verbatim** — `category: research`, `input_key: topic`, `max_iterations: 30`, `timeout: 3600`, `context.output_dir: ".loops/research"`, `context.depth: 3`, `context.coverage_threshold_pct: 85`. Convergence rule preserved: `avg >= 4.0 AND iter >= depth`.
3. **Preserve `init` state verbatim** — same shell action, same `capture: run_dir`, same `$(pwd)/$DIR` absolute-path pattern.
4. **Specialize `generate_queries`** — minor wording: instruct LLM to phrase queries in academic terminology (method names, problem formulations) rather than informal/how-to phrasing. No structural change.
5. **Specialize `search_web`** — instruct LLM to constrain every `WebSearch` query with `site:arxiv.org` (preferring `arxiv.org/abs/` pages), and to `WebFetch` abstract pages for arxiv ID, authors, submission date, optional Journal-ref. Drop "blog posts, official documentation" language from the original.
6. **Specialize `evaluate_sources`** — replace credibility axis with recency on a 1–5 scale derived from arxiv submission date (5 = within 6 months of today, 4 = ≤1yr, 3 = ≤2yr, 2 = ≤5yr, 1 = >5yr). Keep relevance axis unchanged. Annotation format: `[Source: <arxiv-url>] (relevance: N/5, recency: N/5, arxiv-id: YYMM.NNNNN)`.
7. **Preserve `score_coverage` verbatim** — convergence rule and sentinel tokens unchanged.
8. **Specialize `plan_next`** — minor wording tweak for academic terminology; structure unchanged.
9. **Specialize `synthesize`** — replace sources table columns with `| # | arXiv ID | Title | Authors | Year | Relevance | Recency | Facet |`. Emit a `## BibTeX` section at the end with `@misc{...}` entries keyed by arxiv ID.
10. **Preserve `done` state verbatim** — `terminal: true`.
11. **Validate registration** — `ll-loop list | grep deep-research-arxiv` and `ll-loop validate deep-research-arxiv`. Per project memory `feedback_nested_loops_runnable`, use `validate` (not `list`) as the canonical runnability check.
12. **Update test set** — edit `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` and add `"deep-research-arxiv"` to the `expected` set. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to confirm.
13. **Update loops README** — add a row for `deep-research-arxiv` in `scripts/little_loops/loops/README.md` "Research & Knowledge" section adjacent to the existing `deep-research` entry.
14. **End-to-end smoke run** — `ll-loop run deep-research-arxiv "speculative decoding for LLM inference" --max-iterations 1`. Spot-check `knowledge-base.md` URLs are predominantly `arxiv.org/abs/...` and annotations carry `recency:` not `credibility:`.
15. **Synthesis output check (after a converged run)** — open the final `report.md` and confirm the sources table columns are `arXiv ID | Title | Authors | Year | Relevance | Recency | Facet`, and that a `## BibTeX` section appears with at least one `@misc{...}` entry.

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

**Open** | Created: 2026-05-24 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-24T07:09:02Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e118fada-be27-4510-9c7c-e66238684c9d.jsonl`
