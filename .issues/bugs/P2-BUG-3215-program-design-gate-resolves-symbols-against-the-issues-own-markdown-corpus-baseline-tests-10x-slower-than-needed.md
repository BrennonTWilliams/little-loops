---
id: BUG-3215
type: BUG
title: Program Design gate resolves symbols against the issue's own markdown; corpus
  baseline tests 10x slower than needed
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T20:36:52Z'
completed_at: '2026-08-16T20:38:17Z'
---

# BUG-3215: Program Design gate resolves symbols against the issue's own markdown; corpus baseline tests 10x slower than needed

## Summary

`git_grep_resolver` — the predicate backing the Program Design gate — searched the
whole repository, including the 46MB / 4109-file tracked markdown corpus. Two
consequences, one correctness and one performance, both fixed this session:

1. **The gate resolved symbols against the issue's own text.** A `## Program Design`
   signature line strips to exactly the `def foo(` / `class Foo` shape the opener
   filter accepts, so an issue *proposing* a symbol satisfied the check that the
   symbol already exists.
2. **`TestCorpusBaseline` was the test suite's long pole** at ~500s, 97% of it
   `git grep` subprocess time.

Surfaced while reviewing why `test_full_predicate_is_not_inert` took 239s to run.

## Current Behavior

`git_grep_resolver` (`scripts/little_loops/issues/program_design.py:286`) ran
`git grep -n -w -- <short>` with no pathspec, then accepted any matching line whose
stripped text starts with `def <short>(`, `async def <short>(`, or `class <short>`.
Markdown was in scope, and Program Design signature lines match those openers
verbatim.

Measured against the live corpus, symbols resolving **only** through markdown included:

| Issue | Symbol |
| --- | --- |
| ENH-3095 | `AutomationContext` |
| FEAT-3037 | `resolve_host_named`, `run_blocking_json`, `consult` |
| FEAT-3042 | `resolve_host_named`, `run_blocking_json` |
| ENH-2964, ENH-3152 | `_test_functions` |

## Expected Behavior

The gate resolves a symbol only against code. An issue cannot satisfy the gate with
its own proposal text.

## Motivation

The Program Design gate exists to stop an issue reaching implementation on a design
that names symbols nobody has written. Resolving those names against the issue's own
proposal text inverts the gate: the more thoroughly an issue specified a new API, the
more certainly it passed. That is a silent weakening — nothing fails, the gate just
stops discriminating, and every downstream consumer (`ll-issues check-design`,
`check_format_gaps`, the BUG-3003 analyzer override) inherits the false confidence.

The performance half is ordinary but not small: `TestCorpusBaseline` was the slowest
thing in a 19.5k-test suite, and `--dist loadfile` meant it blocked one worker for
~8 minutes while the rest of the fleet idled.

## Proposed Solution

Shipped in two commits, deliberately split so the behavior change is separable from
the optimization:

- **`f77aeaa3`** `fix(program-design): exclude markdown from git_grep_resolver` —
  adds the `:!*.md` pathspec plus a regression test
  (`test_markdown_only_signature_does_not_resolve`,
  `scripts/tests/test_program_design_gate.py:381`).
- **`857f097e`** `perf(research-triage): amortize corpus-baseline git greps` —
  `lru_cache` on the resolver keyed `(symbol, root)`, `_corpus_sweep` collapsing
  three sweeps into one per mode, and the `assert total > 0` guard that
  `test_full_predicate_is_not_inert` was missing (an empty corpus raised
  `ZeroDivisionError` instead of failing as an assertion).

`@pytest.mark.timeout(600)` on `TestCorpusBaseline` was **kept**, with its BUG-3056
comment rewritten to explain why: the cost stays proportional to a corpus that only
grows, so the headroom is worth retaining even at 10x under the ceiling.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/program_design.py:286` — `git_grep_resolver` pathspec + memoized `_resolve_short_symbol`
- `scripts/tests/test_research_triage.py:489` — `_corpus_sweep` / `_corpus_ref_index`, `TestCorpusBaseline` bodies

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issues/program_design.py:459` — `grade_issue_section` injects the resolver
- `scripts/little_loops/issues/research_triage.py:342` — `_program_design_unmet`, the hot path
- `scripts/little_loops/issue_parser.py` — `check_format_gaps` / `_gate_program_design`

### Similar Patterns
- `little_loops.codequery.fallback.FallbackProvider.defines_scan_for` — the
  word-boundary-grep-plus-opener-filter shape `git_grep_resolver` mirrors. Audited:
  it **carries the same defect and was deliberately left unfixed**. See Follow-up.

### Tests
- `scripts/tests/test_program_design_gate.py:363` — `TestRealRepoResolution`, new markdown case at :381
- `scripts/tests/test_research_triage.py:497` — `TestCorpusBaseline`

### Documentation
- None required — no CLI surface or config key changed; behavior is internal to the gate.

### Configuration
- N/A

## Program Design

### Signatures

```python
# scripts/little_loops/issues/program_design.py

def git_grep_resolver(symbol: str, root: Path | None = None) -> bool
    # normalizes + validates, delegates to the memoized body

@lru_cache(maxsize=4096)
def _resolve_short_symbol(short: str, cwd: Path) -> bool
    # git grep -n -w -- <short> -- ':!*.md'

def reset_resolver_cache() -> None
    # for processes that write source between gate evaluations
```

```python
# scripts/tests/test_research_triage.py

@lru_cache(maxsize=1)
def _corpus_ref_index() -> RefIndex

@lru_cache(maxsize=2)
def _corpus_sweep(check_staleness: bool) -> tuple[tuple[Path, tuple[AxisCoverage, ...]], ...]
    # one sweep per predicate mode, shared across all three gates
```

### Call Path

The gate's entry points both funnel into the memoized resolver:

- `check_format_gaps` → `_gate_program_design` → `grade_issue_section` →
  `grade_program_design` → `git_grep_resolver` → `_resolve_short_symbol`
- `triage_research_axes` → `_program_design_unmet` → `grade_issue_section` →
  (same tail)

`_corpus_sweep` sits above `triage_research_axes` in the test harness only, and
`reset_resolver_cache` clears `_resolve_short_symbol`.

## Implementation Steps

1. **Scope the grep** — add `:!*.md` to `git_grep_resolver`, with a regression test
   asserting a markdown-only signature does not resolve. Committed alone (`f77aeaa3`)
   because it changes gate outcomes for real issues.
2. **Amortize** — `lru_cache` the resolver body keyed `(short, cwd)`, expose
   `reset_resolver_cache()`, and collapse the three `TestCorpusBaseline` sweeps into
   `_corpus_sweep(check_staleness)`. Committed separately (`857f097e`).
3. **Verify** — targeted files first, then the full suite; re-measure both corpus
   gate rates to confirm the markdown exclusion did not push either below its floor.

## Follow-up — NOT fixed by this issue

`little_loops/codequery/fallback.py` carries the same defect and was left alone:
`_git_grep_word` (`:50`) runs `git grep -n -w` with no pathspec, and
`defines_scan_for` (`:169`) applies the identical opener filter. So
`FallbackProvider.defines_scan_for` will report a symbol as defined when only an
issue's Program Design block names it, and `callers_of` (`:180`) will return issue
markdown as call sites.

Not folded in here: it is a different subsystem with its own callers and test
surface, and this issue's commits were scoped to the Program Design gate. Worth its
own issue — the fix is likely the same one-line pathspec, but the blast radius on
`codequery` consumers needs checking first.

## Impact

| Measure | Before | After |
| --- | --- | --- |
| `test_full_predicate_is_not_inert` (solo) | 239s | 6.9s warm / 58s cold |
| `TestCorpusBaseline` (class) | ~500s | 58s |
| `git grep` calls per sweep | 1822 | 1045 unique, memoized |
| `git grep -w run` | 0.22s | 0.066s |

Gate thresholds retain real margin after the markdown exclusion — the aggregate
barely moved, since the exclusion only reaches the analyzer axis via the Program
Design override:

- coverage predicate: **34.5%** against the 20% floor
- full predicate: **8.5%** against the 5% floor (still matching the 8.6% ENH-2971
  recorded)

## Steps to Reproduce

1. Write an issue whose `## Program Design` section declares a signature for a
   symbol that does not exist in the codebase, e.g. `def proposed_helper(path: Path) -> None`.
2. Commit it (the resolver reads tracked files via `git grep`).
3. Run `ll-issues check-design <ID>`.

The gate passes. The symbol is defined nowhere but the issue asking for it to be written.

## Root Cause

Two independent contributors, addressed separately:

- **Unscoped pathspec.** No `:!*.md` exclusion, so the corpus the gate is *run over*
  was also inside the corpus it *searched*. A definition can never live in markdown,
  so the exclusion is strictly behavior-improving as well as cheaper.
- **No memoization, repeated sweeps.** A corpus sweep issued 1822 `git grep` calls
  over 1045 unique symbols (`run` and `check_format_gaps` were each grepped 26
  times). On top of that, all three `TestCorpusBaseline` gates walked the same
  corpus independently, differing only in what they tallied — three identical
  subprocess storms. `--dist loadfile` pins the class to a single xdist worker, so
  it serialized while the other workers idled.

## Acceptance Criteria

- [x] A symbol declared only in a `## Program Design` signature line does not resolve
      (`test_markdown_only_signature_does_not_resolve`)
- [x] `git_grep_resolver` memoizes per `(symbol, root)` with an explicit
      `reset_resolver_cache()` escape hatch
- [x] All three `TestCorpusBaseline` gates share one sweep per predicate mode
- [x] `test_full_predicate_is_not_inert` asserts `total > 0` before dividing
- [x] Corpus gates still pass: >=20% coverage predicate, >=5% full predicate
- [x] Full suite green — `python -m pytest scripts/tests/`: 19555 passed, 46 skipped, 289s

## Environment

macOS (darwin 25.5.0), Python 3.12.10, pytest 8.4.2 + xdist 3.8.0, `--dist loadfile`.
Corpus at time of measurement: 3118 issue files, 9354 axis-spawns scored.

## Frequency

Always — the false positive fired for every issue whose Program Design proposed a
not-yet-written symbol; the slow path ran on every full test-suite invocation.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-issues check-design`
- ENH-2971 — the research-triage predicate and its calibrated corpus gates
- BUG-3056 — the prior timeout-ceiling raise on `TestCorpusBaseline`
- BUG-3003 — the Program Design override this predicate feeds

## Status

**Open** | Created: 2026-08-16 | Priority: P2
