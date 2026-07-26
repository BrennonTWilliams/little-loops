---
id: ENH-2829
title: 'Derive superseded_by as a reverse edge of supersedes (no new status value)'
type: ENH
priority: P3
status: open
captured_at: '2026-07-26T16:26:43Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
labels:
- cli
- issues
- issue-graph
relates_to: [ENH-2535]
decision_needed: false
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

### Configuration
- N/A

## Implementation Steps

1. Add `supersedes` to `IssueInfo` and its serialization; confirm the frontmatter
   parse matches `relates_to` semantics (scalar or list, comma-joined strings).
2. Add the `superseded_by` reverse-lookup helper.
3. Wire it into `show.py`, reusing the existing `find_issues` scan.
4. Resolve the two open design questions above.
5. Add tests; update API.md and the CLAUDE.md issue-format note.

## Acceptance Criteria

- [ ] `IssueInfo.supersedes` is populated from frontmatter and survives a
      `to_dict()` / `from_dict()` round trip.
- [ ] A reverse-lookup helper returns the correct replacement IDs for an issue
      referenced by one, several, and zero `supersedes` lists.
- [ ] `ll-issues show <ID>` on an issue referenced by another issue's
      `supersedes` renders a `Superseded by` relationship row.
- [ ] `ll-issues show <ID>` on an issue referenced by nobody renders no
      `Superseded by` row (absent, not empty).
- [ ] No new value is added to `_ALL_STATUSES` / `_TERMINAL_STATUSES`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Session Log
- `/ll:capture-issue` - 2026-07-26T16:26:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/30266787-c0fe-410e-9ada-ca464df9e31b.jsonl`

---

## Status

open
