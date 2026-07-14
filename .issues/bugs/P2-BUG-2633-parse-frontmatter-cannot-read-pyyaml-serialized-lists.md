---
id: BUG-2633
type: BUG
priority: P2
status: open
captured_at: 2026-07-14 00:12:04+00:00
discovered_date: 2026-07-14
discovered_by: capture-issue
relates_to:
- ENH-693
- BUG-836
- BUG-1258
- ENH-484
learning_tests_required:
- yaml
confidence_score: 100
outcome_confidence: 61
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
---

# BUG-2633: `parse_frontmatter` cannot read PyYAML-serialized lists, emitting spurious "Unsupported YAML list syntax" warnings

## Summary

`parse_frontmatter()` in `scripts/little_loops/frontmatter.py` hand-rolls a
line-based YAML-subset reader that cannot parse valid PyYAML output. When a
block-sequence list is serialized by PyYAML (`safe_dump`) with long items, PyYAML
wraps items across two physical lines with backslash line-continuations and emits
`—`/`\xA7` escape sequences. The mini-parser only understands single-line
`- item` entries, so a wrapped continuation line (not starting with `- `) breaks
its list-key tracking — and then every subsequent `- ` item in that block falls
through to the warning branch and is flagged as an orphan.

Observed: `ll-issues list --group-by epic` printed ~30
`Unsupported YAML list syntax in frontmatter` warnings, all tracing to
`relates_to:` lists in three enhancement files that `/ll:scope-epic` had
serialized with PyYAML. The command still produced output, but the warnings
pollute logs and, worse, the affected list values are silently dropped.

## Root Cause

- **File**: `scripts/little_loops/frontmatter.py`
- **Function**: `parse_frontmatter()`
- **Explanation**: The parser tracks `current_list_key` only while consecutive
  lines start with `- `. A PyYAML backslash-wrapped continuation line
  (e.g. `  \ Steps 6-8 …`, `  CLI content)`) does not start with `- `, so the
  non-list branch resets `current_list_key = None`. Every following `- item`
  line then hits the `logger.warning("Unsupported YAML list syntax…")` branch
  and is discarded — even trivial bare-ID items like `- ENH-057`.

This is the **next occurrence in a recurring class of failures**. The same
hand-rolled parser has been patched case-by-case before:
- **ENH-693** added the warnings and *explicitly deferred* the PyYAML migration
  ("only warranted if a future frontmatter field needs list or block-scalar
  support"). That future has now arrived: the parser can't read PyYAML's own
  valid output.
- **BUG-836** added block-sequence (`- item`) support.
- **BUG-1258** added inline-array (`[a, b, c]`) support.

Each patch handled one more syntax the mini-parser didn't. This bug proposes
retiring the whole class instead of adding a fourth special case.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of `scripts/little_loops/frontmatter.py`:_

- **All core claims verified.** Warning branch is `frontmatter.py:69`; list tracking
  is `:65-70`; `current_list_key` is only *set* at `:105` (the bare `key:` /
  empty-value branch), so any `- item` that precedes a bare-key line — or follows a
  broken block — hits `:69` and is dropped. Caller count is exactly **24** and test
  files referencing the parser are exactly **16** (grep-confirmed) — the estimates in
  the Integration Map are accurate.
- **Failure is worse than just warnings — it silently drops the continuation line too.**
  A PyYAML backslash-continuation line (e.g. `  continue on the next line`) has no
  `:` and does not start with `- `, so it falls through `:75`'s `if ":" in line` guard
  and is skipped with *no* warning at all (pure data loss). It *also* resets
  `current_list_key = None` at `:74`, which is what cascades the visible `:69` warning
  onto every subsequent real `- ` item in that block.
- **`coerce_types=False` int divergence — the main behavioral trap for the swap.**
  Today, with `coerce_types=False` (the default), a bare digit value like
  `priority: 2` stays a **string** `"2"` (line 108 only coerces when
  `coerce_types=True`). `yaml.safe_load` yields an `int` **unconditionally**. The
  golden-equivalence test (Step 1) must cover this, and the `safe_load`-first rewrite
  must re-stringify digit scalars when `coerce_types=False` to preserve the current
  contract, or explicitly accept the behavior change (audit the 24 callers first —
  several read `priority`).
- **Sibling pattern to copy is `parse_skill_frontmatter:146-159`, not `update_frontmatter`.**
  `parse_skill_frontmatter` uses the exact `try: yaml.safe_load / except yaml.YAMLError:
  → line-based fallback` shape this fix wants (`:146-149`), and its fallback also
  triggers on a *successfully-parsed non-dict* result (scalar/`None`) — worth mirroring.
  `update_frontmatter:211` calls `yaml.safe_load` with **no** `except` guard (uncaught
  `YAMLError`), so it is *not* a safe fallback model — copy from `parse_skill_frontmatter`.
- **Post-processing to re-apply on the `safe_load` path** (all confirmed present today):
  `STATUS_SYNONYMS` (`:118-119`), empty-value → `[]`/`None` normalization
  (`:102-107`, `:116-117`), block scalars `| >` (`:79-97` — `safe_load` does this
  natively), inline flow-lists `[a,b,c]` (`:98-101` — native), quote-stripping
  (`:111-113` — native). Only `STATUS_SYNONYMS` and the `coerce_types=False`
  string-preservation are genuinely non-native and must be re-applied after `safe_load`.

## Expected Behavior

`parse_frontmatter` reads any valid YAML frontmatter — including PyYAML's own
serialized output — without warnings or silent data loss.

## Proposed Fix

Make `parse_frontmatter` **`yaml.safe_load`-first, with the existing mini-parser
as a fallback** on `yaml.YAMLError` — mirroring the two functions in this *same
file* that already do it right:
- `parse_skill_frontmatter` (uses `yaml.safe_load` with a line-based fallback)
- `update_frontmatter` (uses `yaml.safe_load` / `yaml.dump` for round-trips)

Preserve `parse_frontmatter`'s post-processing that a raw `safe_load` doesn't
give:
- `STATUS_SYNONYMS` coercion
- `coerce_types` int coercion (safe_load yields ints natively; keep behavior on
  the fallback path)
- empty-value `key:` → `[]`/`None` list normalization
- block scalar (`|` / `>`) handling — `safe_load` does this natively and better

## Implementation Steps

1. **Guard the swap with a golden-equivalence test.** Before changing behavior,
   add a test that parses every `.md` under `.issues/` (and the existing
   `test_frontmatter.py` fixtures) with both the old mini-parser and the new
   `safe_load`-first path, asserting equivalent results. This locks in behavior
   across the ~24 call sites before the switch.
2. Rewrite `parse_frontmatter` to try `yaml.safe_load` first; on `YAMLError`,
   fall back to the current line-based loop.
3. Re-apply post-processing (status synonyms, coerce_types, empty-list
   normalization) to the `safe_load` result.
4. Update the docstring — it currently advertises the "simple subset" limitation
   that no longer applies.
5. Run the full suite (`python -m pytest scripts/tests/`) — 16 test files
   reference `parse_frontmatter`; all must stay green.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/API.md:5961` — replace the stale "Parses simple `key: value`
   pairs" limitation with the new `safe_load`-first behavior.
7. Revise `docs/reference/API.md:5986` — the `parse_skill_frontmatter` cross-reference
   sentence claiming `parse_frontmatter` "deliberately drops block scalars" is false
   after this fix; correct or remove it.
8. Verify the `coerce_types=True` consumer `cli/issues/check_flag.py:31` still receives
   an `int` (part of the coerce_types contract check in Step 2).

## Integration Map

- **Modify**: `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` +
  docstring
- **Callers** (~24; no signature change, return type unchanged): `issue_parser.py`,
  `sync.py`, `issue_manager.py`, `issue_lifecycle.py`, `session_store.py`,
  `recursive_finalize.py`, `parallel/orchestrator.py`, `parallel/worker_pool.py`,
  `issue_history/parsing.py`, `issue_discovery/search.py`, `hooks/session_start.py`,
  `learning_tests/__init__.py`, and CLI subcommands under `cli/issues/`,
  `cli/sprint/`, `cli/migrate*`
- **Tests**: `test_frontmatter.py` (primary; add golden-equivalence + wrapped-list
  regression tests) + 15 other test files that exercise the parser indirectly

### Codebase Research Findings

_Added by `/ll:refine-issue` — caller/test map (codebase-locator):_

- **Golden-equivalence corpus for Step 1**: besides `.issues/**`, there are **20
  frontmatter fixtures** under `scripts/tests/fixtures/issues/` (e.g.
  `bug-with-asterisk-bullets.md`, `bug-with-none-blockers.md`,
  `bug-null-product-fields.md`, `FEAT-2339-mixed-resolved-unresolved.md`) — these
  deliberately exercise null/empty-list/bullet edge cases and should be included in
  the old-vs-new equivalence assertion.
- **Two local `_parse_frontmatter` variants are NOT the shared function** and are
  out of scope for this fix (do not assume the swap touches them): a private
  `_parse_frontmatter()` at `hooks/session_start.py:51` and one exercised by
  `test_generate_skill_descriptions.py`. If we want them unified too, that's a
  separate ENH (aligns with ENH-484/ENH-241 consolidation), not this bug.
- **Highest-fanout production callers** (backward-compat blast radius): `sync.py`
  (10 calls), `issue_lifecycle.py` (6), `issue_history/parsing.py` (4),
  `session_store.py` / `recursive_finalize.py` (3 each). These are the modules whose
  tests most tightly pin current return shapes — prioritize them when auditing the
  `coerce_types=False` int-vs-string divergence noted above.

### Documentation (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5961` — `parse_frontmatter` doc entry still advertises the
  stale limitation "Parses simple `key: value` pairs." (already out of date pre-fix;
  predates BUG-836/BUG-1258 list support). Update after the rewrite. [Agent 2 finding]
- `docs/reference/API.md:5986` — the `parse_skill_frontmatter` entry's cross-reference
  asserts current `parse_frontmatter` behavior as a reason to prefer the skill parser:
  "`parse_frontmatter` deliberately drops block scalars (logs a warning and sets the
  value to `None`)". After the `safe_load`-first rewrite `parse_frontmatter` resolves
  block scalars natively, so this sentence becomes **factually wrong** and must be
  revised. This is the one doc-coupling item not covered by the generic "docstring"
  entry in the Integration Map. [Agent 2 finding]

### Configuration / Consumers of `coerce_types`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/check_flag.py:31` — calls
  `parse_frontmatter(..., coerce_types=True)`, a live consumer of the int-coercion
  path. Include in the audit of the `coerce_types` divergence (Root Cause note): the
  `safe_load`-first rewrite must keep `coerce_types=True` yielding ints and
  `coerce_types=False` re-stringifying digit scalars. (Under `cli/issues/*` glob but
  the only caller passing `coerce_types=True` explicitly.) [Agent 1 finding]

### Tests (named — the "15 other test files")

_Wiring pass added by `/ll:wire-issue` (concrete names for the golden-equivalence corpus + regression sweep):_
- `test_cli_sprint.py` — mocks `parse_frontmatter()` (`:805`, `:1012`); verify the mock
  signature still matches after the rewrite. [Agent 1 finding]
- `test_set_status_cli.py` (`:106`, `:143`), `test_issue_discovery.py` (`:476`, `:491`),
  `test_interceptor_extension.py` (`:179`), `test_link_epics_skill.py` (`:81-130`),
  `test_migrate_status.py` (imports `STATUS_SYNONYMS`; `:70`, `:167-168`),
  `test_migrate_relationships.py` (`:72-181`), `test_issue_migration.py` (`:105-203`)
  — all call `parse_frontmatter()` to pin return shape; must stay green. [Agent 1 finding]
- **Warning-assertion tests keep passing (no update needed):**
  `test_frontmatter.py::test_list_item_emits_warning` (`:100-106`) and
  `test_orphaned_list_item_still_warns` (`:197-203`) feed *genuinely invalid* YAML
  (bare `- item` after a scalar key) that `yaml.safe_load` rejects with `ScannerError`,
  so they still exercise the fallback path and still warn. Only fixtures using *valid*
  PyYAML block sequences move to the fast path. The `caplog` warning-text assertions at
  `test_frontmatter.py:106/:128/:203` are the ONLY warning-string assertions in the repo
  (grep-confirmed); no other test file asserts on the message. [Agent 3 + Agent 2 findings]
- **New fixture confirmed genuinely absent:** no `backslash`/`continuation` fixture exists
  in `test_frontmatter.py` (existing list fixtures are single-line only). Step 1's
  golden-equivalence test must author a new `relates_to:` list with long items serialized
  via `yaml.safe_dump` to reproduce the line-wrap. [Agent 3 finding]

### Out of Scope (confirmed)

_Wiring pass added by `/ll:wire-issue`:_
- `cli/generate_skill_descriptions.py:31` + `test_generate_skill_descriptions.py`
  define a **local** `_parse_frontmatter()` mini-parser that does NOT call the canonical
  function — out of scope (aligns with the existing session_start.py note; a separate
  ENH-484/ENH-241 consolidation, not this bug). [Agent 1 finding]
- No config-schema / `.ll/ll-config.json` / `LLEvent` schema references the function —
  it is a pure internal utility with no schema-declared contract. [Agent 2 finding]

## Reproduction

1. Create an issue file whose `relates_to:` block-sequence has long items and
   serialize it with PyYAML `safe_dump` (as `/ll:scope-epic` does), producing
   backslash line-continuations.
2. Run `ll-issues list --group-by epic`.
3. Observe `Unsupported YAML list syntax in frontmatter` warnings and dropped
   list values.

## Related Context

- Surfaced from plan `~/.claude/plans/investigate-the-warnings-in-curried-peacock.md`
  (a peer session in the ll-marketing repo, where the immediate unblock was to
  normalize the three offending issue files' `relates_to` to bare IDs — a
  band-aid; the durable fix is here in this repo).
- **ENH-484 / ENH-241** track consolidating duplicated frontmatter parsing; this
  fix aligns `parse_frontmatter` with the `safe_load` approach already used by
  the file's other two parsers, reducing that duplication.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-14_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 61/100 → MODERATE

### Outcome Risk Factors
- 24 production callers reference `parse_frontmatter` (a wide caller count on the
  Pattern A blast-radius scale) — the signature and return type stay unchanged,
  but a subtle behavioral divergence such as the `coerce_types=False` int-vs-string
  edge case could still propagate silently across those callers. Mitigated by the
  golden-equivalence test gating the swap in Implementation Step 1; prioritize
  running it against the highest-fanout callers (`sync.py`, `issue_lifecycle.py`)
  before the broader suite.

## Session Log
- `/ll:confidence-check` - 2026-07-14T00:35:00 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:wire-issue` - 2026-07-14T00:21:38 - `2314f375-7ee7-43eb-8eea-3a80f925de17.jsonl`
- `/ll:refine-issue` - 2026-07-14T00:16:39 - `e06448c4-fd2c-4a12-b427-6a28ee594989.jsonl`
- `/ll:capture-issue` - 2026-07-14T00:12:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00d887fa-9561-4d1f-9dc3-a8ba5775d31e.jsonl`

---

## Status
open
