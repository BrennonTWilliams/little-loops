---
id: BUG-3089
type: BUG
title: Release gate's import scan misses function-local and dotted imports, so most
  records can never be flagged
priority: P2
status: done
verify_verdict: VALID
discovered_date: 2026-08-06
discovered_by: pre-implementation-review
captured_at: '2026-08-06T18:05:00Z'
completed_at: '2026-08-06T21:34:48Z'
labels:
- learning-tests
- release
- gates
testable: true
relates_to:
- ENH-3073
- ENH-2214
- ENH-2216
- BUG-3072
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3089: Release gate's import scan misses function-local and dotted imports, so most records can never be flagged

## Summary

`run_release_gate` narrows its stale/refuted record list to packages the project
actually imports, via `r.target in imported_packages` (`release_gate.py:67`). That
intersection is the gate's whole relevance filter — and it silently discards most
records, because `get_imported_packages` cannot see the two import forms this
codebase uses most:

1. **Function-local imports are invisible.** `_PY_IMPORT_RE`
   (`import_scan.py:8`) is `^(?:import|from)\s+(...)` with `re.MULTILINE`. The `^`
   anchor means the import must begin at **column 0**. Every indented import —
   which in this codebase means every deliberate cycle-avoidance import — never
   matches.
2. **Dotted module names can never match.** The regex captures only the
   top-level segment (`[A-Za-z_][A-Za-z0-9_]*`, no `.`), so
   `imported_packages` can never contain `concurrent.futures` or `ruamel.yaml`,
   yet those are the exact strings two live records use as their `target`.
3. **The two consumers normalize differently.** `release_gate.py:67` matches
   `r.target` raw; `cmd_orphans` (`cli/learning_tests.py:157`) matches
   `r.target.split()[0].lower()`. Neither handles the dotted case, and they
   disagree on multi-word and mixed-case targets — so a record can be
   simultaneously "not imported" for the release gate and "imported" for the
   orphan report, or vice versa.

Net effect: **the pre-release audit's relevance filter is mostly a no-op in the
false-negative direction.** A genuinely refuted record for a package imported
function-locally will never appear in the audit, regardless of `release_gate:
block`.

## Current Behavior

`scripts/little_loops/learning_tests/import_scan.py:8`:

```python
_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
```

`scripts/little_loops/learning_tests/release_gate.py:67`:

```python
hits = [r for r in problem_records if r.target in imported_packages]
```

`scripts/little_loops/cli/learning_tests.py:157`:

```python
orphans = [r for r in records if r.target.split()[0].lower() not in imported]
```

### Confirmed live instances (2026-08-06)

| Record `target` | Actually imported at | Seen by scanner? |
|---|---|---|
| `anthropic` | `host_runner.py:1840`, `:1917`, `fsm/executor.py:2469` — all indented | **No** (function-local) |
| `opentelemetry` | `transport.py:359-361` — all indented | **No** (function-local) |
| `concurrent.futures` | `link_checker.py:16`, `parallel/worker_pool.py:17` — column 0 | **No** (dotted; scanner records `concurrent`) |
| `ruamel.yaml` | `cli/loop/_scaffold_core.py:19-20` — column 0 | **No** (dotted; scanner records `ruamel`) |

`ll-learning-tests orphans` reports all four as orphaned records today, which is
the same defect surfacing through the other consumer.

## Steps to Reproduce

1. `ll-learning-tests orphans` — observe `anthropic`, `opentelemetry`,
   `concurrent.futures` listed as orphans despite being imported (see table).
2. Set any of those records to `status: refuted` in `.ll/learning-tests/`.
3. Run the release gate:
   ```
   python -c "from pathlib import Path; from little_loops.learning_tests.release_gate import run_release_gate; raise SystemExit(run_release_gate(Path.cwd()))"
   ```
4. The refuted record does **not** appear in the audit table and the gate returns
   0, even with `release_gate: "block"`. Expected: the record is flagged.

## Expected Behavior

A record whose target is genuinely imported by the project is subject to the
audit, regardless of whether the import sits at module scope or inside a
function, and regardless of whether the target names a dotted submodule. The
release gate and `cmd_orphans` agree on what "imported" means.

## Root Cause

`get_imported_packages` was written (ENH-2214/ENH-2216) as a cheap regex scan and
its `^`-anchored, dot-free pattern encodes two assumptions that do not hold in
this codebase: that imports live at column 0, and that record targets name
top-level packages. Neither consumer normalizes consistently against it, and
nothing tests the intersection with a realistic import layout.

## Proposed Solution

**Parse, don't regex.** Replace the regex with an `ast`-based scan:
`ast.parse` each file and walk `ast.Import` / `ast.ImportFrom` nodes, which finds
imports at any nesting depth and gives the full dotted module name for free. Fall
back to skipping files that fail to parse (the current `errors="ignore"` read
already tolerates junk). This is stdlib-only, so it adds no dependency.

Emit **both** the full dotted name and its dotted prefixes into the returned set
(`concurrent.futures` → `{"concurrent", "concurrent.futures"}`), so a record
targeted at either granularity matches. **Cap expansion at two segments**:
`little_loops.cli.loop._scaffold_core` emits `{"little_loops",
"little_loops.cli"}`, not four entries. No record in the registry targets deeper
than two segments, and unbounded expansion is pure noise for the `ctx_stats`
consumer (see below).

**Skip relative imports.** `from .foo import x` parses to
`ast.ImportFrom(module="foo", level=1)`. Naively emitting `node.module` would
inject first-party module names into the "imported packages" set — a defect the
current column-0 regex does not have. The walk must skip any `ImportFrom` with
`node.level > 0`. (Only 2 such imports exist under `scripts/little_loops/` today,
but `scan_dirs` is user-configurable and points at arbitrary trees.)

**First-party absolute imports are the larger leak, and they are *not* fixed by
the relative-import guard.** Measured on this repo (2026-08-06): the widened scan
takes `ctx_stats`'s `gaps` list from **64 entries to 431**, and **335 of those 431
are `little_loops.*` submodules**. Those come from `from little_loops.config.core
import ...` — `level == 0`, ordinary absolute imports that the `node.level > 0`
check does nothing about. Only 61 of the new entries are stdlib. Any framing that
treats relative imports as the first-party risk has the proportions backwards.

**The filter belongs in `cli/ctx_stats.py:670`, not in the scan.** Two of the
three consumers (`release_gate`, `cmd_orphans`) read the set in the
recorded-but-not-imported direction, where a wider set is strictly correct and
first-party names are harmless — no record targets `little_loops.*`. Only
`ctx_stats` reads it backwards, and only it needs the filter. Keeping
`get_imported_packages` an unopinionated "what does this tree import" function
confines the change to the one consumer that needs it and avoids teaching the
scan a project-layout concept it has no business knowing. Filter on
`sys.stdlib_module_names` plus the project's own top-level package names (AC 11).

**Decide the fate of `_PY_IMPORT_RE`** (see Dependent Files — this was flagged by
the wiring pass as an open question and is now decided here):
`hooks/learning_tests_gate.py:29` imports the private regex directly and calls it
at `:77` inside `_extract_packages()`, and
`scripts/tests/test_learning_tests_discoverability.py` fails at **collection**
(not runtime) if it disappears. That hook scans an in-flight `Write`/`Edit` tool
call's `content`/`new_string` fragment, which is frequently not independently
parseable Python — so `ast.parse` is not a safe drop-in there.

**Resolution: move `_PY_IMPORT_RE` into `hooks/learning_tests_gate.py`** (its only
remaining consumer once `get_imported_packages` stops using it) and delete it from
`import_scan.py`. One-line move plus updating the test module's import. Leaving a
now-unused private regex in `import_scan.py` solely for an out-of-module importer
is the worse option — it reads as dead code and invites a future cleanup that
breaks the hook again.

Note also that `_extract_packages()` does not lowercase (`pkg = m.group(1)` used
as-is at `:78`). Since the regex moves out of `import_scan.py`, it is unaffected
by the new lowercasing convention — but confirm the hook's matching behavior is
unchanged by the move, since it queries the same registry the gate does.

**Unify the two consumers** on one normalization helper — e.g.
`normalize_target(target: str) -> str` applying `.split()[0].lower()` — called by
both `release_gate.py:67` and `cli/learning_tests.py:157`, with the imported set
lowercased at construction. Today's divergence is itself a latent bug even after
the scan is fixed.

### Considered and rejected

**Widening the regex** to allow leading whitespace and dots. Rejected: it still
mis-fires inside strings, comments, and docstrings — which an `ast` walk is
immune to by construction — and the codebase has many `import`-mentioning
docstrings.

The cost is real but acceptable, and earlier drafts of this issue understated it.
Measured over `scripts/` (740 files, 2026-08-06): **regex 0.14s → `ast` 2.21s, a
15× regression.** The claim that this "runs once per release, so parse cost is
irrelevant" is **wrong** — `run_release_gate` is release-time, but the other two
consumers (`ll-ctx stats`, `ll-learning-tests orphans`) are interactive CLIs that
pay this on every invocation. Neither is on a statusline or hook hot path
(verified: `ll-ctx-stats` appears only in `init/writers.py` permission/entry-point
lists), so a ~2s dashboard command is a tolerable trade for correctness — but it
is a trade, not a free win, and should not be re-justified with the false
"once per release" framing.

**Normalizing only in the consumers** and leaving the scan alone. Rejected: it
cannot recover a function-local import, which is the larger of the two misses.

## Scope Boundaries

**In scope**: `get_imported_packages`'s scan mechanism, the shared normalization
helper, updating both consumers to use it, relocating `_PY_IMPORT_RE` to its
remaining consumer (`hooks/learning_tests_gate.py`), and bounding the knock-on
effect on `ctx_stats`'s gap list (AC 11).

**Out of scope**:

- Non-Python targets (`bun-types`, `@types/bun`, `claude-code`,
  `claude-code-hooks`, `git`, `jq`, `kimi`, `oh-my-pi`, `playwright`,
  `pre-commit`). A Python import scan legitimately cannot see these, and they will
  remain permanent "orphans" under any fix here. Whether the registry should
  support non-Python targets is a separate design question — file it if it
  matters.
- **Distribution-name vs import-name mismatch.** `pyyaml` (imported as `yaml`),
  `pytest-xdist` and `pytest-json-report` (pytest plugins, never imported by
  name) stay orphaned because their record target is the PyPI distribution name,
  not the importable module name. Resolving this needs a distribution→module map
  (e.g. `importlib.metadata.packages_distributions()`), which is a separate
  design question from the scan mechanism. File it if it matters.
- **First-party targets.** `codegraph` names a module inside this repo
  (`little_loops/codequery/codegraph.py`), not a third-party package, so it
  remains orphaned. Whether the registry should hold first-party targets at all is
  out of scope here.
- Changing the staleness predicate (ENH-3073's Option B follow-up).
- Changing `release_gate` from `warn` to `block` for this project.

## Acceptance Criteria

1. `get_imported_packages` finds imports at any indentation level, verified by a
   test with a function-local `import x` inside a nested function.
2. `get_imported_packages` returns full dotted names **and** their prefixes,
   **capped at two segments**: scanning `from concurrent.futures import X` yields
   both `concurrent` and `concurrent.futures`; scanning
   `import little_loops.cli.loop._scaffold_core` yields exactly `little_loops` and
   `little_loops.cli` — not the three- and four-segment forms.
3. Imports appearing only inside string literals, comments, or docstrings are
   **not** reported — the regression the `ast` switch buys and the regex could not.
4. A file that fails to parse is skipped without raising, and the scan continues.
5. **Relative imports are not reported as packages**: scanning
   `from .foo import x` and `from ..bar import y` yields neither `foo` nor `bar`.
   `import a.b as c` *is* reported, as both `a` and `a.b` (the aliased form of
   AC 2). Note this guard covers `level > 0` only — first-party **absolute**
   imports (`from little_loops.x import y`) are still reported by the scan by
   design, and are filtered at the `ctx_stats` consumer instead (AC 11).
6. One shared normalization helper is used by both `release_gate.py:67` and
   `cli/learning_tests.py:157`; the two no longer normalize differently. A test
   asserts a record target that one consumer considers imported is considered
   imported by the other.
7. Regression test covering the four live-instance **shapes** — indented
   function-local (`anthropic`), indented function-local under a nested scope
   (`opentelemetry`), column-0 dotted `from` (`concurrent.futures`), and column-0
   dotted `import` (`ruamel.yaml`) — using a `tmp_path` source fixture, **not** by
   reading this repo's live `.ll/learning-tests/` registry (which is
   environment-dependent and will drift as records change).
8. `ll-learning-tests orphans` no longer lists those four. Against this repo's
   registry as of 2026-08-06 the orphan count drops **19 → 14**; the 14 that
   remain are exactly the Scope Boundaries categories (non-Python targets,
   distribution-vs-import-name mismatches, first-party targets) and their
   continued presence is correct, not a residual defect. Assert the drop of the
   four named targets and the retention of at least one representative of each
   out-of-scope category — do **not** pin the literal count of 14, which drifts as
   records are added.
9. A refuted record for a function-locally-imported package appears in the audit
   table and, under `release_gate: "block"`, causes exit 1.
10. **`_PY_IMPORT_RE` lives in `hooks/learning_tests_gate.py`**, not
    `import_scan.py`; `test_learning_tests_discoverability.py` collects and passes
    against the new location, and the hook's `_extract_packages()` behavior is
    unchanged.
11. **`ctx_stats`'s gap list is filtered.** "Accept and document the larger list"
    is **not** an available option — measured, the unfiltered list goes 64 → 431
    on this repo, which is not a shippable dashboard. `cli/ctx_stats.py:670` must
    exclude, before computing `gaps`:
    (a) stdlib modules, via `sys.stdlib_module_names` (matched on the **top-level**
    segment, so `concurrent.futures` is excluded along with `concurrent`); and
    (b) first-party top-level package names — the top-level directory/package
    names under the configured `scan_dirs` (`little_loops`, `tests`), so
    `little_loops.*` submodules do not appear. This is a change to `ctx_stats`,
    not to `get_imported_packages` (see Proposed Solution for why).
    Pinned by a test over a `tmp_path` fixture source tree containing a
    function-local stdlib import, a dotted third-party import, and a first-party
    absolute import, asserting only the third-party name lands in `gaps`. The
    existing `test_cli_ctx_stats.py` tests at ~1019 and ~1162 patch
    `get_imported_packages` with literal `return_value`s and so cannot exercise
    this — the new test must run a real scan.
12. `import_scan.py`'s file read uses `errors="replace"`, matching the codebase's
    dominant convention (21 occurrences across 13 files) rather than the current
    lone `errors="ignore"`.
13. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — this silently defeats a shipped gate. Unlike ENH-3073's
  noise problem (a warning that never clears), this is the opposite and more
  dangerous failure: a record that *should* fire never does, so `release_gate:
  block` provides materially less protection than it appears to. It is also a
  precondition for ENH-3073 being worth anything — making remediation reachable
  does not help for rows that never print.
- **Effort**: Small-Medium — one function rewritten to `ast`, one shared helper,
  two call-site updates, one regex relocation with its test-import fixup, one
  `ctx_stats` pinning test, and the scan unit tests. Grew from "Small" when the
  wiring pass surfaced the third (`hooks/learning_tests_gate.py`) and fourth
  (`cli/ctx_stats.py`) consumers; the frontmatter `outcome_confidence: 79` /
  `score_change_surface: 18` predate that and are worth re-running.
- **Risk**: Low-Medium. The fix makes the gate flag **more** records, so a
  project sitting at `release_gate: block` could newly block on a record that was
  previously invisible. That is the gate working as intended, but call it out in
  the changelog — it will look like a regression to anyone who had silently
  benefited from the false negatives.
- **Knock-on regression — `ctx_stats` gap-list inflation (AC 11)**: the widened
  set is intersected against records by both named consumers, so widening is
  strictly good there. But `cli/ctx_stats.py:670` runs the *opposite* direction —
  `gaps = sorted(pkg for pkg in imported if slugify(pkg) not in known_slugs)`,
  i.e. imported-but-not-recorded — with **no stdlib and no first-party filter**.
  **Measured on this repo (2026-08-06): `gaps` goes 64 → 431, a 6.7× inflation of
  a user-facing dashboard list.** The composition matters and inverts the earlier
  assumption in this issue: **335 of the 431 are `little_loops.*` first-party
  submodules**, only 61 are stdlib. The dominant source is *absolute* first-party
  imports (`from little_loops.config.core import ...`, `level == 0`), which the
  relative-import guard in AC 5 does nothing about — earlier drafts treated
  relative imports as the first-party risk, which had the proportions backwards.
  At 431 entries "accept and document" is not viable, so AC 11 now mandates a
  filter at the `ctx_stats` call site rather than offering a choice.
- **Performance regression (accepted, not free)**: measured over `scripts/` (740
  files), the scan goes **0.14s → 2.21s (15×)**. `run_release_gate` pays this once
  per release, but `ll-ctx stats` and `ll-learning-tests orphans` pay it per
  invocation. Neither is on a statusline or hook hot path (verified), so a ~2s
  interactive command is an acceptable trade for correctness — recorded here so
  the trade is visible rather than rediscovered.
- **Breaking Change**: No (behavioral only; no API or wire-format change).

## Program Design

**Invariant.** A record whose target names a module the project imports is subject to the
audit — independent of that import's indentation, dotted depth, or the target string's case
and spacing.

### Types

No new types. `get_imported_packages` keeps its `set[str]` return; the set's *contents*
widen to include dotted names and their prefixes.

### Signatures

Unchanged public surface:

```python
def get_imported_packages(source_dirs: list[Path]) -> set[str]:
```

New shared helper, to be placed alongside it so both consumers can import it without
either depending on the other:

```python
def normalize_target(target: str) -> str:   # .split()[0].lower()
```

Consumers become `normalize_target(r.target) in imported_packages` at
`release_gate.py:67` and `normalize_target(r.target) not in imported` at
`cli/learning_tests.py:157`, with the scan lowercasing at construction so both sides of
the comparison share one convention.

### Call Path

`commands/manage-release.md` → `run_release_gate` (`release_gate.py:36`) →
`get_imported_packages` (`import_scan.py:11`) → per-file `ast.parse` → walk
`ast.Import` / `ast.ImportFrom` (skipping `ImportFrom.level > 0`) → emit dotted
name + prefixes, lowercased → intersect with `normalize_target(r.target)` at
`release_gate.py:67`.

Independently: `ll-learning-tests orphans` → `cmd_orphans`
(`cli/learning_tests.py:~150`) → the same `get_imported_packages` and the same
`normalize_target`.

Also independently, and inheriting the widened set without being unified:
`ll-ctx stats` → `_learning_tests_stats` (`cli/ctx_stats.py:670`) → the same
`get_imported_packages`, used in the imported-but-not-recorded direction (AC 11).

Not on any of these paths after this change: `hooks/learning_tests_gate.py`'s
`_extract_packages()`, which keeps the regex for in-flight tool-call fragments
(AC 10).

### Decision Rules

- **`ast` over regex** — the miss is structural (indentation, dots), and an `ast` walk
  additionally excludes imports named inside strings/comments/docstrings, which the regex
  cannot. Stdlib-only, so no new dependency. Cost is a measured 15× (0.14s → 2.21s over
  740 files) and is paid per-invocation by two interactive CLIs, not once per release —
  accepted deliberately, not dismissed.
- **Prefix expansion, capped at two segments** — `from concurrent.futures import X` emits
  `{"concurrent", "concurrent.futures"}` so records targeted at either granularity match.
  Emitting only the dotted name would break `anthropic`-style top-level targets; emitting
  only the prefix reproduces today's bug for `concurrent.futures`. Expanding *every* depth
  is unbounded noise — no record targets deeper than two segments, so depth 2 is the
  natural cap.
- **The first-party/stdlib filter lives in `ctx_stats`, not in the scan** — only that
  consumer reads the set in the imported-but-not-recorded direction, where first-party and
  stdlib names are noise. For `release_gate` and `cmd_orphans` a wider set is strictly
  correct and those names are inert. Pushing the filter into `get_imported_packages` would
  teach a generic scanner a project-layout concept and narrow the set for the two consumers
  that want it wide.
- **Unparseable files are skipped, not fatal** — matches the existing tolerant-read
  posture; a syntax error in one file must not blank the whole scan. The read itself moves
  to `errors="replace"` (AC 12) to match the codebase's dominant spelling.
- **Relative imports emit nothing** — `ImportFrom.level > 0` names a first-party sibling
  module, not a package. Emitting `node.module` for these would be a *new* false positive
  the current regex does not produce (AC 5).
- **`_PY_IMPORT_RE` moves to its consumer rather than being kept alive in place** — the
  hook's fragment-scanning use case genuinely cannot use `ast` (an `Edit` `new_string` is
  often not parseable in isolation), so the regex must survive; but a private regex left in
  `import_scan.py` with no in-module caller is dead code by inspection and will be deleted
  by a future cleanup, breaking the hook a second time (AC 10).
- **Non-Python targets stay unmatched** — see Scope Boundaries. This is correct behavior,
  not a residual defect, and AC 8 pins it so a later "fix" does not paper over it.

## Integration Map

### Files to Modify

- `scripts/little_loops/learning_tests/import_scan.py` — `get_imported_packages`
  (`:11-31`) rewritten to an `ast` walk; `_PY_IMPORT_RE` (`:8`) **removed** (moved,
  see below); read switched to `errors="replace"` (`:26`); new `normalize_target`
  helper added.
- `scripts/little_loops/hooks/learning_tests_gate.py` — receives `_PY_IMPORT_RE`
  as a module-local regex; drops the `from little_loops.learning_tests.import_scan
  import _PY_IMPORT_RE` at `:29`. `_extract_packages()` (`:77-78`) otherwise
  unchanged.
- `scripts/little_loops/learning_tests/release_gate.py:67` — raw `in` match.
- `scripts/little_loops/cli/learning_tests.py:157` — divergent normalization.
- `scripts/little_loops/cli/ctx_stats.py:670` — `gaps` computation; **change
  required** (not conditional): add the stdlib + first-party filter per AC 11.
  Without it this dashboard list goes 64 → 431 entries.

### Dependent Files (Callers/Importers)

- Any other caller of `get_imported_packages` — grep before editing; ENH-2214 and
  ENH-2216 both introduced consumers.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/learning_tests_gate.py:29` — imports the private
  `_PY_IMPORT_RE` regex directly (`from little_loops.learning_tests.import_scan
  import _PY_IMPORT_RE`) and calls it at `:77` inside `_extract_packages()`. This is
  a **third consumer of the regex** not named anywhere in the issue's Summary,
  Proposed Solution, or Scope Boundaries. It is structurally different from the two
  named consumers: it scans the `content`/`new_string` of a single in-flight
  `Write`/`Edit` tool call for the PreToolUse discoverability nudge (FEAT-1742),
  not a full file on disk — so an `ast.parse` replacement is not a safe drop-in
  here, since an `Edit` tool's `new_string` fragment is frequently not
  independently parseable Python (e.g. a single indented line inserted into an
  existing function). If the `ast` rewrite deletes `_PY_IMPORT_RE` as part of
  replacing it in `import_scan.py`, this hook breaks at import time. Also:
  `_extract_packages()` does not lowercase (`pkg = m.group(1)` used as-is at
  `:78`), so if the new `normalize_target`/lowercasing convention were applied to
  `_PY_IMPORT_RE`'s output without updating this call site, this hook's matching
  behavior would diverge from the release gate's.
  **→ Decided (AC 10)**: the regex moves into `hooks/learning_tests_gate.py` and is
  deleted from `import_scan.py`, so the hook owns it outright and is insulated from
  both the `ast` rewrite and the lowercasing convention. See Proposed Solution.

### Tests

- `scripts/tests/test_release_gate.py` — the `block`-mode exit-1 case for a
  function-locally-imported refuted record (AC 9).
- `scripts/tests/test_cli_learning_tests.py` — `cmd_orphans` behavior (AC 8).
- A test module for `import_scan` itself if none exists — AC 1-5 are pure unit
  tests of the scan and belong there rather than in the gate's tests.
- `scripts/tests/test_learning_tests_discoverability.py` — update the import path
  after `_PY_IMPORT_RE` moves (AC 10); this file fails at **collection**, not
  runtime, if the move is made without it.
- `scripts/tests/test_cli_ctx_stats.py` — new `gaps` pinning test (AC 11). Note
  its existing tests at ~1019 and ~1162 patch `get_imported_packages` with literal
  `return_value`s, so the new test must use a real scan over a `tmp_path` fixture
  to exercise the widening at all.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no separate `test_import_scan.py` exists (`Glob "**/test_import_scan.py"`
  — no matches); AC 1-5 tests belong in
  `scripts/tests/test_release_gate.py::TestGetImportedPackages` (lines 73-123),
  which already exists — the "if none exists" framing above does not apply. Add,
  following the class's existing 3-line `tmp_path`/`write_text`/assert pattern:
  a function-local (indented) import test, a dotted-import-normalizes-to-both
  the full and top-level name test, a strings/comments/docstrings non-detection
  test, an unparseable-file-skipped test, and a relative-import-not-reported test.
- `scripts/tests/test_release_gate.py::TestReleaseGateBlockMode.test_returns_1_on_refuted_imported_package`
  (lines 170-175) is the existing block-mode template for AC 9 — the new test
  swaps its top-level `import anthropic\n` source fixture for an indented,
  function-local one and keeps the rest identical.
- `scripts/tests/test_cli_learning_tests.py::TestMainLearningTestsOrphans` (lines
  456-648, ~15 tests) **already exists** covering `cmd_orphans` — correcting this
  section's earlier framing. Every test in it except
  `test_scope_flag_uses_custom_directory` (lines 604-620) mocks
  `get_imported_packages` directly, so they are isolated from the `ast` rewrite
  and need no changes; AC 8's actual new coverage is narrower than "entirely new"
  — it's specifically a real-scan (non-mocked) case exercising the four import
  shapes from the table above.
- `scripts/tests/test_learning_tests_discoverability.py::TestExtractPackages`
  (~line 345 onward) exercises `_extract_packages()` — and therefore
  `_PY_IMPORT_RE` — via `hooks/learning_tests_gate.py`'s import chain. This test
  file will fail at collection (not just at runtime) if `_PY_IMPORT_RE` is removed
  without resolving the hook's dependency on it (see Dependent Files above). Its
  existing cases use only column-0 imports, matching the current regex's scope; no
  new *behavioral* test is required here — but the module's import path must be
  updated when `_PY_IMPORT_RE` moves into the hook (AC 10). Teaching the hook to
  detect function-local/dotted imports remains out of scope.
- `scripts/tests/test_cli_ctx_stats.py` (patches at ~1019, ~1162) and the mocked
  majority of `TestMainLearningTestsOrphans` need no changes — both patch
  `get_imported_packages` with literal `return_value`s, fully isolated from the
  scan's internal implementation.

### Documentation

- `docs/guides/LEARNING_TESTS_GUIDE.md` — the `## Release Gate` section describes
  the relevance filter; state that the scan is AST-based and matches dotted names.

### Codebase Research Findings

_Added by pre-implementation review — 2026-08-06 — measured against the live tree
(740 `.py` files under `scripts/`, registry as of this date):_

- **The fix works, verified end to end.** Running the proposed `ast` walk against
  the real registry drops all four named targets from the orphan list:
  `anthropic`, `opentelemetry`, `concurrent.futures`, `ruamel.yaml` all resolve.
  Orphan count 19 → 14.
- **`ctx_stats` gaps: 64 → 431.** Composition: 335 `little_loops.*` first-party,
  61 stdlib-rooted, remainder third-party. Drives the AC 11 rewrite and the
  correction that absolute (not relative) first-party imports are the main leak.
- **Scan cost: 0.14s → 2.21s (15×)**, 0 parse failures across all 740 files — so
  the AC 4 unparseable-file path is untested by the live tree and genuinely needs
  the synthetic `tmp_path` fixture.
- **The five newly-identified permanent orphans** beyond the originally-listed
  non-Python targets: `pyyaml`, `pytest-xdist`, `pytest-json-report` (distribution
  vs import name), `claude-code-hooks`, `playwright`, `pre-commit` (non-Python),
  and `codegraph` (first-party). Now enumerated in Scope Boundaries so AC 8 is
  satisfiable.

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Third caller not covered by Scope Boundaries**: `scripts/little_loops/cli/ctx_stats.py:670` (ENH-2218 dashboard stats) also calls `get_imported_packages` and will inherit the widened dotted/prefix output set from this fix, even though it isn't named as a consumer to unify. Its usage runs the opposite direction from the two named consumers — it computes `gaps` (imported-but-not-recorded, via `slugify(pkg) not in known_slugs`) rather than the recorded-but-not-imported check at `release_gate.py:67`/`cli/learning_tests.py:157`. **Amended**: this was originally filed as "no code change required, worth a sanity note" — that understates it. `gaps` has no stdlib or first-party filter, so the widened set inflates a user-facing dashboard list. **Re-amended after measurement**: the inflation is 64 → 431, and its dominant source is neither of the two mechanisms guessed here (function-local stdlib imports, dotted prefixes) but *absolute first-party* `little_loops.*` imports — 335 of the 431. Now tracked as AC 11 as a **required** filter at the `ctx_stats` call site; see Impact.
- **Existing scanner test suite, not a from-scratch module**: `TestGetImportedPackages` (`scripts/tests/test_release_gate.py:73-123`) already covers `get_imported_packages` with 8 tests (`test_finds_simple_import`, `test_finds_from_import`, `test_multiple_files`, `test_recursive_subdirs`, `test_multiple_source_dirs`, `test_missing_dir_returns_empty`, `test_non_py_files_skipped`, `test_deduplicates_across_files`) — all using column-0, single-segment imports only (no indentation, no dots). This is the class to extend for AC 1-4; the Tests subsection's "if none exists" framing does not apply — one already exists, embedded in `test_release_gate.py`.
- **`cmd_orphans` has zero existing test coverage**: confirmed via grep of `scripts/tests/test_cli_learning_tests.py` — no test name matches "orphan". AC 7's coverage is entirely new, not an extension of existing tests.
- **Reusable `ast` walk precedent already in this codebase**: `scripts/little_loops/codequery/fallback.py:79-87` (`_parse_ast(path)`) and its `ast.Import`/`ast.ImportFrom` walk at `:240-269` (`impact_of()`) already implement the tolerant-parse-and-walk shape this fix needs — `try/except OSError` around the file read, `try/except SyntaxError` around `ast.parse`, skipping the file on either failure. `scripts/little_loops/observability/audit.py:75-90` and `scripts/little_loops/test_tamper_guard.py:311-317` repeat the same shape independently; no shared helper is extracted codebase-wide, so this fix inlining its own try/except pair matches convention rather than being an outlier.
- **Tolerant-read encoding convention**: the codebase's dominant spelling for a possibly-mixed-encoding source read is `errors="replace"` (21 occurrences across 13 files, including `codequery/fallback.py` and `observability/audit.py`); `import_scan.py:26`'s current `errors="ignore"` is the only occurrence of that spelling anywhere in the codebase. Now tracked as AC 12 — cheap to fix while the function is being rewritten anyway.
- **Helper placement precedent**: shared helpers used by exactly the modules that need them live in the module that owns the concept they compute (e.g. `normalize_issue_id` in `session_store/writers.py:135`, used by 3 other modules) rather than a generic utils file — consistent with the issue's own Program Design placing `normalize_target` in `import_scan.py` alongside `get_imported_packages`.
- **Existing import style for the two named consumers**: `release_gate.py:20` imports `get_imported_packages` at module top-level; `cli/learning_tests.py:135` imports it lazily inside `cmd_orphans`'s body, matching that file's broader per-command lazy-import convention (`cmd_list`, `cmd_mark_stale` do the same at `:107-108`, `:116-117`). No change needed here; noted so the new `normalize_target` import follows the same per-file convention at each call site.
- **`LearnTestRecord.target` is a plain `str`** with no built-in normalization (`scripts/little_loops/learning_tests/__init__.py:44-61`) — normalization is entirely call-site logic today, confirming there is no dataclass-level hook to normalize at instead of adding the standalone `normalize_target` helper.

## Related Issues

- ENH-3073 — surfaced this as an "adjacent defect noticed during review, not fixed
  here"; that note is now this issue. ENH-3073's value depends on this landing.
- ENH-2214 / ENH-2216 — introduced the gate and the import scan.
- BUG-3072 — failing assertions invisible under `proven` status; a different
  false-negative on the same audit.

## Status

**Open** | Created: 2026-08-06 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-06T21:34:26 - `f5480c50-da98-4b22-a4fd-8c1a946cc856.jsonl`
- `/ll:confidence-check` - 2026-08-06T21:07:38 - `4d056033-a5b1-40d2-9e37-2ea3bc0a3a8f.jsonl`
- `/ll:confidence-check` - 2026-08-06T19:56:13 - `eb8636a6-46bc-4112-9372-8e2c5095cc16.jsonl`
- `/ll:confidence-check` - 2026-08-06T19:15:45 - `b7d3f312-b65f-41c2-b355-e4dab95a731c.jsonl`
- `/ll:verify-issues` - 2026-08-06T19:13:13 - `b168ef6f-5044-4563-8573-1f22ba59fc28.jsonl`
- `/ll:wire-issue` - 2026-08-06T19:11:53 - `04f01577-89f8-431d-b260-2ea1afcfdcd3.jsonl`
- `/ll:refine-issue` - 2026-08-06T19:05:46 - `4b0f00e2-4dd5-4bc3-9b30-63e795cc853a.jsonl`
