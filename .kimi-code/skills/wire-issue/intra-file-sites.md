# Wire-Issue: Intra-File Sites (ENH-3480)

Loaded by `/ll:wire-issue` Phase 3 (`known_sites` extraction), Phase 3.7
(caller-closure `key_symbols` expansion), and Phase 8a (`sites_to_add`
rendering). Closes the structural gap where Phase 4's whole-file exclusion
wording and Phase 5's file-granular `MISSING_WIRING` categories made call
sites *inside* an already-known file permanently unreportable on a first
pass — they only surfaced on a second pass, once the issue's own
first-pass writing had widened `key_symbols`.

## 1. `known_sites` extraction (Phase 3)

Parse every existing Integration Map bullet of the form
`` `path` — ... `symbol()` `` into a `known_sites: [(path, enclosing_symbol)]`
list. This is the dedup key `sites_to_add` filters against.

**Round-trip rules — required, or the key never matches what a prior pass
wrote and every site is re-reported every run:**

- Strip a trailing `:line` or `:start-end` suffix from the path before
  keying (`sites_to_add` bullets render as `` `path:line` ``).
- The key is `(path, enclosing symbol)` — **never the callee.** The seed
  `key_symbols` *are* the callees (Files to Modify bullets name them, e.g.
  `` `harness.py` — fix `_report_samples()` ``); if every backticked name
  became a known site, pass 1 would seed `harness.py:_report_samples` and
  then filter out every intra-file caller of `_report_samples()` — exactly
  the finding this companion exists to surface.
- The enclosing symbol is recovered **only** from a bullet's trailing
  `` in `enclosing()` `` form (docs: `` in `Section Heading` ``), with an
  optional trailing `[Agent N finding]` tag tolerated after it. Callee
  names elsewhere on the bullet are ignored by the parser.
- A bullet with no trailing `` in `X` `` form contributes the **bare path
  only** — this is legitimate for a file-level note with no single
  attributable symbol (e.g. "existing coverage, update for new behavior").
  **A bare-path entry suppresses nothing** — it is not a whole-file
  exclusion. Treating it as one would silently restore the bug this
  companion fixes.

**Applies to all four existing Phase 8a templates**, not only
`sites_to_add` — the callers/importers template already ends in the
`` in `X` `` form (its `[Agent N finding]` tag trails the form, tolerated by
the rule above); the docs and tests templates did not and are fixed in
Phase 8a (§3 below) so their bullets round-trip too. Without that fix,
every cross-file caller, test, and doc bullet a first pass writes becomes a
bare path, and a second pass re-reports the specific functions or sections
inside them as `sites_to_add` — the manual smoke check fails by
construction.

**Line numbers are optional, the enclosing symbol is mandatory.** Never cite
a bare path-plus-line-number with no enclosing symbol, here or in
`SKILL.md` (ENH-1299) — cite the enclosing symbol always, a `:line` suffix
only when convenient; the dedup key never depends on the line.

## 2. Caller-closure `key_symbols` expansion (Phase 3.7)

For each seed symbol in `key_symbols` (Phase 3), grep its callers **inside
`files_to_modify` only**, add the enclosing function names to the seed
set, and repeat until no new names appear. Never search files outside
`files_to_modify`.

**Why a fixpoint, not one hop:** Phase 3 re-seeds from issue text on every
pass. A one-hop scheme has pass 2 seed the hop-derived names pass 1
rendered and hop once more (`_report_samples()` → `cmd_compare()` in pass
1, `cmd_compare()` → `main()` in pass 2) — the set still grows by one hop
per pass. The fixpoint is finite (bounded by the files' own call graph) and
idempotent for names inside `files_to_modify`: a later pass's seeds are a
subset of the closure an earlier pass already computed.

**Entry-point stop-list:** exclude from the *seed set handed to agents*
(not from the closure walk itself — such names still terminate it) any
closure-derived name that is `main`, matches `cmd_*`, or is a registered
CLI entry point in `scripts/pyproject.toml`. Without this, every seed in a
file like `harness.py` closes upward to `main()` within a few hops, and
Agent 1 ends up tracing callers of `main` repo-wide before the
caller-suitability gate ([caller-suitability-gate.md](caller-suitability-gate.md))
gets a chance to prune it at render time.

**Accelerator:** use Phase 3.6's `ll-code --json` caller queries when
`available: true`; fall back to Grep otherwise, under Phase 3.6's existing
silent-fallback rule (no new primitive).

**Caveat:** pass 1 also renders cross-file caller and test-function names,
which become pass-2 seeds *outside* this closure, and Agent 1 re-traces
them repo-wide on pass 2. Those re-found cross-file callers are suppressed
only because the round-trip rule in §1 now applies to the
callers/tests/docs templates too — their `path:enclosing` pairs are already
in `known_sites` from pass 1. This is not proven to yield zero new findings
on every issue shape; the manual smoke check in the issue's Acceptance
section is the arbiter.

## 3. `sites_to_add` rendering (Phase 8a)

Phase 5's `sites_to_add` category holds `path:line` + enclosing symbol +
which known file the site lives in, filtered against `known_sites`. Route
each entry by the kind of known file it lives in, under the
`` _Wiring pass added by `/ll:wire-issue`:_ `` marker already used by the
other Phase 8a subsections:

- Site in a `files_to_modify` file → `### Files to Modify`
- Site in a `known_tests` file (a specific test function) → `### Tests`
- Site in a `known_docs` file (a specific section) → `### Documentation`

```markdown
- `path/to/known_file.py:142` — additional call to `changed_fn()` in `helper()` [Agent 1 finding]
- `tests/test_known.py:88` — covers old behavior in `test_helper_returns_none()` [Agent 3 finding]
- `docs/known.md:40` — describes the changed flag in `CLI Flags` [Agent 2 finding]
```

`sites_to_add` entries also feed Phase 8b's `### Wiring Phase` bullets, and
both [evidence-confirmation.md](evidence-confirmation.md) and
[caller-suitability-gate.md](caller-suitability-gate.md) apply to them
exactly as they do to `callers_to_add`.
