---
id: ENH-2829
title: Derive superseded_by as a reverse edge of supersedes (no new status value)
type: ENH
priority: P3
status: done
captured_at: '2026-07-26T16:26:43Z'
completed_at: '2026-07-26T17:37:23Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels:
- cli
- issues
- issue-graph
relates_to:
- ENH-2535
decision_needed: false
confidence_score: 100
outcome_confidence: 75
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 12
score_change_surface: 22
---

# ENH-2829: Derive superseded_by as a reverse edge of supersedes (no new status value)

## Summary

Supersession between issues is currently only expressible in the forward
direction: an issue may declare `supersedes: [ID, ...]` in frontmatter, which
`ll-issues show` renders as a "Supersedes" relationship row. The superseded
issue itself has no machine-readable pointer back to its replacement — you can
only discover it by scanning every other issue's `supersedes` list by hand.

This issue adds the reverse edge, `superseded_by`, **derived** from the existing
forward edge rather than stored as a second hand-maintained frontmatter field.
One edge, no drift.

Explicitly out of scope: adding a `superseded` value to the issue `status` enum.
See § Motivation for why that was rejected.

## Current Behavior

- `supersedes` is read only at display time, as raw frontmatter, in
  `scripts/little_loops/cli/issues/show.py` (`_parse_card_fields`, the
  `supersedes_raw = frontmatter.get("supersedes")` line), joined via `_join_ids`
  and rendered through the `("supersedes", "Supersedes")` entry in
  `_RELATIONSHIP_KEYS`.
- `supersedes` is **not** a field on `IssueInfo` in
  `scripts/little_loops/issue_parser.py`. The parser reads `parent`,
  `relates_to`, `blocked_by`, `blocks`, and `depends_on` from frontmatter (the
  canonical-format tuple list in `_parse_issue_file`), but drops `supersedes`.
- Consequence: `find_issues(config)` returns `IssueInfo` objects with the
  supersession edge already discarded, so there is no index to reverse.
- Running `ll-issues show` on a superseded issue displays no indication that a
  replacement exists.

## Expected Behavior

- `IssueInfo` carries `supersedes: list[str]`, parsed from frontmatter alongside
  the other relationship fields and round-tripped through `to_dict`/`from_dict`.
- A helper computes the reverse edge: given an issue ID and the set of all
  issues, return the IDs of every issue whose `supersedes` list contains it.
- `ll-issues show <ID>` on a superseded issue renders a `Superseded by` row in
  the relationships block, listing the replacement issue ID(s).
- No new `status` value is introduced. A superseded issue is marked `cancelled`
  (optionally with the already-supported `cancelled_reason`), and the graph edge
  carries the "by what" information.

## Motivation

The triggering question was whether to add `superseded` to the issue status enum.
Deriving the edge is strictly better on three counts:

1. **Blast radius.** The canonical status sets live in
   `scripts/little_loops/issue_progress.py` (`_ALL_STATUSES`, `_OPEN_STATUSES`,
   `_TERMINAL_STATUSES`), but ~33 files under `scripts/little_loops/` reference
   status values and many hardcode the terminal pair inline rather than
   importing the frozenset — e.g. `issue_lifecycle.py` (`if status in ("done",
   "cancelled")`) and `issue_parser.py` (`status not in ("done", "cancelled",
   "deferred")`). A new terminal status missed at any one of those sites fails
   **silently**: the closed issue still reads as open, so `blocked_by` edges
   never clear, epic progress under-counts, and autodev re-dequeues it.
2. **A status is a label; the useful artifact is a pointer.** "Superseded" is
   only actionable if it says *by what*, which a bare enum value cannot carry.
3. **Precedent already exists in both directions.** `decisions.py` makes an
   entry inactive via a `supersedes` reference rather than a status
   (`active_entries` filters on `supersedes`, not a state field), and ENH-2664
   discriminated *kinds* of deferral with `deferred_by`/`deferred_reason`
   sidecar fields rather than new statuses. `cancelled_reason` is likewise
   already read by `show.py`.

Cost is one parsed field plus a reverse lookup, against a silent-failure risk
spread across ~33 files.

## Proposed Solution

Four pieces, only the first of which is load-bearing:

1. **`issue_parser.py`** — add `supersedes: list[str] = field(default_factory=list)`
   to the `IssueInfo` dataclass, include it in `to_dict()` and `from_dict()`, and
   append `("supersedes", supersedes)` to the canonical-format frontmatter tuple
   list in `_parse_issue_file` so it parses exactly like `relates_to`/`blocks`.
2. **Reverse-index helper** — e.g.
   `superseded_by(issue_id: str, all_issues: Iterable[IssueInfo]) -> list[str]`,
   returning every `i.issue_id` whose `i.supersedes` contains `issue_id`.
   Mirrors the shape of `active_entries()` in `decisions.py`, which already
   builds a `superseded_ids` set from the forward references.
3. **`show.py`** — `_parse_card_fields` already calls `find_issues(config)` to
   resolve the parent title, so the full scan is paid for. Reuse that same
   `_all` list to compute `superseded_by`, add it to the returned fields dict via
   `_join_ids`, and add `("superseded_by", "Superseded by")` to
   `_RELATIONSHIP_KEYS`.
4. **Tests** — parse round-trip for the new `IssueInfo` field, and reverse
   lookup (single replacement, multiple replacements, none).

### Open design questions

- **Silent degradation.** The existing `find_issues` call in `_parse_card_fields`
  is wrapped in `try/except Exception` that falls back to ID-only parent display.
  Reusing it means the `Superseded by` row silently vanishes on any scan error.
  Consistent with current behavior, but decide deliberately whether the reverse
  edge should share that fallback or surface the failure.
- **Dependency semantics.** Should an issue `blocked_by` a superseded issue treat
  that blocker as resolved? `issue_parser.py` currently clears blockers only on
  `done`/`cancelled`. If superseded issues are marked `cancelled` as recommended
  above, this resolves itself and no change is needed — confirm that is the
  intent before expanding scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`find_issues()`'s default status filter can hide the forward reference.**
  `find_issues(config)` (called with no `status_filter`, as `_parse_card_fields`
  does for the parent-title lookup) uses an inner `_matches_status` closure at
  `scripts/little_loops/issue_parser.py:1344` that excludes
  `("done", "cancelled", "deferred")` by default. The replacement issue (the one
  holding the forward `supersedes` edge) is typically `open`/`in_progress`, so
  this is usually fine — but if a replacement issue is itself later closed
  (`done`), a plain unfiltered `find_issues(config)` reverse scan would silently
  stop finding it, and the `Superseded by` row would vanish even though the
  edge still exists. The reverse-lookup helper should either pass an explicit
  `status_filter` that includes all statuses, or the issue should note this as
  an accepted limitation consistent with the existing `parent_display` fallback
  behavior (see the "Silent degradation" question above — same root cause).



## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `IssueInfo` dataclass, `to_dict`, `from_dict`, `_parse_issue_file` frontmatter list
- `scripts/little_loops/cli/issues/show.py` — `_parse_card_fields`, `_RELATIONSHIP_KEYS`
- New or existing helper module for the reverse lookup (TBD — colocate with `issue_parser` or `issue_progress`)

### Dependent Files (Callers/Importers)
- TBD — grep for `IssueInfo(` construction sites and `from_dict`/`to_dict` consumers; any positional construction will need updating

### Similar Patterns
- `scripts/little_loops/decisions.py` — `active_entries()` builds the same forward-reference-to-reverse-set inversion
- `relates_to` / `blocks` parsing in `issue_parser.py` — the exact pattern the new field should follow

### Tests
- `scripts/tests/` — issue parser round-trip tests, `ll-issues show` rendering tests (locate existing ENH-2535 relationship-rendering tests and extend)

### Documentation
- `docs/reference/API.md` — `IssueInfo` field reference
- `.claude/CLAUDE.md` § Issue File Format — note that supersession is a graph edge, not a status value

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:3985` — exact anchor: the `ll-issues show --json` output fields list already enumerates `supersedes` among the ENH-2535 additive keys; append `superseded_by` to the same comma list
- `docs/reference/CLI.md:1199` — the `ll-issues show` card doc's `**Relationships**` bullet lists rendered fields (`parent, relates_to, depends_on, blocked_by, blocks, supersedes, decomposed_into, affects, focus_area`); append `superseded_by` [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (lines 205-233, `issues` block's relationship-field sub-schema for `parent`/`blocked_by`/`depends_on`/`relates_to`/`duplicate_of`, closed by `additionalProperties: false` at line 261) — pre-existing gap: this schema already omits the *existing* `supersedes` field, so it is not kept in lock-step with `IssueInfo`. Decide deliberately whether to add `supersedes` (and note `superseded_by` as derived/non-writable) for parity, or explicitly leave as an accepted pre-existing gap — do not silently perpetuate it without a decision [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact anchors** (line numbers as of research time; will drift):
  - `IssueInfo` dataclass field block: `scripts/little_loops/issue_parser.py:651-721` (no `supersedes` field yet). New field slots naturally after `relates_to: list[str] = field(default_factory=list)` alongside `duplicate_of`.
  - `to_dict()`: `scripts/little_loops/issue_parser.py:732-768`; `relates_to` line is `"relates_to": self.relates_to,` — add a matching `"supersedes": self.supersedes,` line.
  - `from_dict()`: `scripts/little_loops/issue_parser.py:770-807`; matching line is `relates_to=data.get("relates_to", []),`.
  - Canonical-format frontmatter merge loop (the one this issue calls "parsed... alongside relates_to/blocks/blocked_by/depends_on"): `IssueParser.parse_file()`, `scripts/little_loops/issue_parser.py:989-1015`, driven by a tuple list `for fm_key, body_ids in (("blocked_by", blocked_by), ("blocks", blocks), ("depends_on", depends_on), ("relates_to", relates_to)):` — append `("supersedes", supersedes)` here. Note `blocked_by`/`blocks` seed from parsed markdown body sections first; `relates_to`/`depends_on` (the closer analogue for `supersedes`, since it has no body-section form) start as empty lists before the loop reconciles them against frontmatter.
  - `show.py` insertion points: `_parse_card_fields()` at `scripts/little_loops/cli/issues/show.py:154-453` (`supersedes_raw` read at line 254, `_join_ids` closure at line 336); `_RELATIONSHIP_KEYS` tuple at lines 577-587 (existing `("supersedes", "Supersedes")` entry at line 583 — add `("superseded_by", "Superseded by")` alongside it); `_render_relationships_block()` at lines 590-597.
  - Reverse-edge precedent to mirror: `decisions.py:480-488`'s `resolve_active()`. **Caveat**: that function's `supersedes` field is a *singular* `str | None`, and it builds a set for *exclusion filtering* (`e.id not in superseded_ids`). ENH-2829's `supersedes` is a *list*, and the goal is *inclusion lookup* (find who references this ID), not filtering — the shape to copy is "flatten all `IssueInfo.supersedes` lists into a `{target_id: [source_id, ...]}` reverse map, then look up `issue_id`" rather than a straight port of `resolve_active`'s set-membership filter.
- **Dependent files (callers/importers) — from grep, resolving the `TBD`**:
  - `session_store.py` and `history_reader.py` consume `IssueInfo.to_dict()`/`from_dict()` for history persistence — the new field round-trips through these automatically since both serializers are flat dict builders (no reflection), but the round-trip tests below should still cover it directly.
  - `IssueInfo(...)` construction sites in tests use keyword arguments throughout (no positional-argument risk found via grep) — `test_worker_pool.py`, `test_cli.py`, `test_dependency_graph.py`, `test_dependency_mapper.py`, `test_sprint_integration.py`, `test_issue_lifecycle.py`, `test_issue_manager.py`, `test_cli_sprint_show.py`, `test_parallel_types.py`, `test_issue_progress.py`, `test_learning_tests_extractor.py`, `test_issues_search.py`. None require changes for a new keyword-only field with a default.
  - CLI modules importing `IssueInfo` for read-only consumption (no changes needed, listed for completeness): `sequence.py`, `next_issues.py`, `next_issue.py`, `set_status.py`, `format_check.py`, `deferred_triage.py`, `search.py`, `dependency_mapper/operations.py`, `cli/deps.py`.
- **Existing tests to extend rather than write from scratch**:
  - `scripts/tests/test_issue_parser.py:2058-2078` `test_parse_relates_to_from_frontmatter` — exact template for a `supersedes` frontmatter round-trip test.
  - `scripts/tests/test_issue_parser.py:2128-2167` — three tests (`test_new_relationship_fields_default_to_empty`, `test_new_relationship_fields_roundtrip_serialization`, `test_from_dict_defaults_empty_new_relationship_fields`) already establish the default/round-trip pattern for prior new relationship fields; extend the same trio for `supersedes`.
  - `scripts/tests/test_decisions.py:361-385` `TestResolveActive` — direct model for the new reverse-lookup helper's unit tests (all-active, one-excluded/one-included, empty-list cases).
  - `scripts/tests/test_show.py:369-389` `test_relationships_fields_extracted` and `:609-630` (`test_relationships_block_renders_blocked_by`, `test_blocked_status_includes_blocked_by_name`) — templates for `superseded_by` field-extraction and card-rendering tests.
  - `scripts/tests/test_show.py:453` `test_regression_no_new_fields_renders_identically` — **already iterates the existing `"supersedes"` key at line 489** as part of its baseline-issue regression guard; add `"superseded_by"` to that same iterated tuple so the regression test also covers the new derived field.

### Tests — Wiring Pass

_Wiring pass added by `/ll:wire-issue`:_

- **New test needed — the "Silent degradation" scenario is currently untested.** No existing test covers what happens when the *superseding* issue (the one holding the forward `supersedes` edge) is itself `done`/`cancelled`. `find_issues(config)` called with no `status_filter` (`_matches_status` at `scripts/little_loops/issue_parser.py:1344`) excludes `done`/`cancelled`/`deferred` by default — `test_issue_parser.py:1163-1183` (`test_find_issues_status_filter_none_preserves_default`) and `:1131-1161` confirm this default-exclusion behavior generically, but neither seeds a `supersedes`/`superseded_by` fixture. Add a test that: seeds issue B with `supersedes: [A]`, sets B's status to `done` or `cancelled`, and asserts whether the reverse-lookup helper (fed by an unfiltered `find_issues(config)` scan, per the show.py reuse plan) still finds/misses B when computing A's `superseded_by`. This directly resolves the issue's own "Silent degradation" open design question with an executable assertion instead of leaving it a judgment call [Agent 3 finding].
- Minor/optional: a `status: cancelled` variant of `test_find_issues_status_filter_none_preserves_default` (only `deferred`/`done`/`open` are currently covered) [Agent 3 finding].
- Confirmed no gap: no test asserts a closed set / exact count over `IssueInfo` fields or `_RELATIONSHIP_KEYS`, so adding the new field/key won't silently break an unrelated cardinality assertion beyond the already-known `test_regression_no_new_fields_renders_identically` update [Agent 3 finding].

## Implementation Steps

1. Add `supersedes` to `IssueInfo` and its serialization; confirm the frontmatter
   parse matches `relates_to` semantics (scalar or list, comma-joined strings).
2. Add the `superseded_by` reverse-lookup helper.
3. Wire it into `show.py`, reusing the existing `find_issues` scan.
4. Resolve the two open design questions above.
5. Add tests; update API.md and the CLAUDE.md issue-format note.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Add a test seeding a `done`/`cancelled` superseding issue and asserting whether `superseded_by` still resolves for the superseded issue — resolves the "Silent degradation" open design question with an executable assertion (`test_issue_parser.py`, near `test_find_issues_status_filter_none_preserves_default`).
7. Update `docs/reference/CLI.md:1199` and `docs/reference/API.md:3985` to append `superseded_by` to the enumerated relationship-field lists.
8. Decide and act on the `config-schema.json` (lines 205-233) parity gap for `supersedes`/`superseded_by` — either add schema entries or explicitly note it as an accepted pre-existing gap in the PR description.

## Acceptance Criteria

- [x] `IssueInfo.supersedes` is populated from frontmatter and survives a
      `to_dict()` / `from_dict()` round trip.
- [x] A reverse-lookup helper returns the correct replacement IDs for an issue
      referenced by one, several, and zero `supersedes` lists.
- [x] `ll-issues show <ID>` on an issue referenced by another issue's
      `supersedes` renders a `Superseded by` relationship row.
- [x] `ll-issues show <ID>` on an issue referenced by nobody renders no
      `Superseded by` row (absent, not empty).
- [x] No new value is added to `_ALL_STATUSES` / `_TERMINAL_STATUSES`.
- [x] `python -m pytest scripts/tests/` exits 0 (4 pre-existing failures in
      `test_cache_control.py`/`test_batch_request_path.py`, unrelated to this
      change and present on `main` before this work).

## Resolution

Implemented as scoped: `IssueInfo.supersedes` parses from frontmatter alongside
`relates_to`/`depends_on` (round-trips through `to_dict`/`from_dict`);
`issue_parser.superseded_by()` derives the reverse edge; `show.py` reuses the
existing `find_issues(config)` scan (already paid for by the parent-title
lookup) to populate a new `superseded_by` field and `("superseded_by",
"Superseded by")` relationship row. No new status value was added.

Open design questions resolved:
- **Silent degradation**: left consistent with the existing `parent_display`
  fallback — both derive from the same `find_issues(config)` scan and share its
  `try/except` wrapper, so a scan error (or a superseding issue itself being
  `done`/excluded by the default status filter) silently omits the row rather
  than erroring. Documented via
  `TestSupersededBy::test_superseding_issue_done_still_found_when_scan_unfiltered`.
- **Dependency semantics**: confirmed no change needed — superseded issues are
  marked `cancelled`, and `issue_parser.py` already clears `blocked_by` edges on
  `done`/`cancelled`.

`config-schema.json`'s relationship sub-schema gap (it already omits the
pre-existing `supersedes` field) is left as an accepted pre-existing gap, not
expanded in this issue.

## Session Log
- `/ll:manage-issue` - 2026-07-26T17:36:31Z - `c391bd3a-4d46-4e75-b129-8eb2887010e2.jsonl`
- `/ll:wire-issue` - 2026-07-26T17:23:42 - `c960e520-cdcb-4726-9530-d3ca02cc8fa0.jsonl`
- `/ll:refine-issue` - 2026-07-26T17:18:39 - `fada6467-70bc-4839-bbeb-2b054d01acd5.jsonl`
- `/ll:capture-issue` - 2026-07-26T16:26:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/30266787-c0fe-410e-9ada-ca464df9e31b.jsonl`

---

## Status

open
