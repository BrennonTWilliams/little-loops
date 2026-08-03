---
id: ENH-3030
title: Prose dependency extractor misses blocker synonyms; authoring passes emit unparseable paraphrases
type: ENH
priority: P3
status: done
captured_at: '2026-08-03T21:11:15Z'
discovered_date: 2026-08-03
discovered_by: manual-analysis
relates_to:
- FEAT-2849
- BUG-3029
- BUG-3028
testable: true
labels:
- issues
- dependencies
- skills
completed_at: '2026-08-03T21:11:15Z'
---

# ENH-3030: Prose dependency extractor misses blocker synonyms; authoring passes emit unparseable paraphrases

## Summary

`extract_prose_deps()` (FEAT-2849) matched only three exact phrasings, so an
issue could document a hard blocker in prose and still carry no `blocked_by`
frontmatter edge. Widened the extractor to the unambiguous synonyms and — the
durable half of the fix — taught the three passes that *write* this prose to
phrase blockers canonically in the first place.

## Current Behavior

BUG-3029 documented a genuine blocking dependency on BUG-3028 three separate
times ("Blocking dependency unmet: BUG-3028's fallback-convention decision has
not landed", "blocked on that decision landing first", "Confirm BUG-3028's
... decision has landed"). None matched
`\b(?:Depends on|Blocked by|Requires)\s+<ID>`, so:

- `ll-issues format-check BUG-3029` returned an empty `prose_dep_drift`,
- `/ll:refine-issue` Step 6.7's gate had nothing to act on,
- `/ll:wire-issue` Phase 3.7 relies on the same drift path and also stayed silent,
- no `blocked_by` edge was ever written — the issue read as unblocked to
  `ll-issues ready` and sprint scheduling despite `/ll:confidence-check`
  correctly scoring it Readiness 68 / Outcome 59 *because* of that blocker.

The prose was written by our own refine/wire passes, so the recall gap is
self-inflicted and recurring, not an authoring accident.

## Expected Behavior

Blocker phrasings that a reader would unambiguously call a dependency are
extracted and reconciled into frontmatter; temporal/narrative phrasings are
still ignored.

## Motivation

Measured across `.issues/` before the change:

| phrasing | occurrences | verdict |
|---|---|---|
| canonical (`Depends on`/`Blocked by`/`Requires`) | 200 files | already matched |
| `blocked on <ID>` | 42 | unambiguous — now matched |
| `gated on <ID>` | 15 | unambiguous — now matched |
| `contingent on` / `waiting on` / `blocking dependency on` | 6 | unambiguous — now matched |
| `after <ID>` | 474 | ambiguous — deliberately excluded |
| `once <ID>` | 139 | ambiguous — deliberately excluded |
| `pending` / `needs <ID>` | 34 | ambiguous — deliberately excluded |

The split is clean: ~63 real missed edges recoverable at near-zero
false-positive cost, versus 613 mostly-historical mentions whose inclusion
would inject *wrong* `blocked_by` edges. FEAT-2849's "recall matters less than
not crying wolf" tradeoff is preserved — a wrong edge silently hides an issue
from `ll-issues ready`, which is worse than a missed one. The crying-wolf risk
is further bounded by `check_format_gaps()` routing done/cancelled targets to
`stale_prose_dep` (no edge) rather than `prose_dep_drift`.

## Proposed Solution

Two halves, read-side and write-side:

1. **Read side** — extend `_PHRASE_RE` with `blocked on | gated on | waiting on
   | contingent on | predicated on | depends upon`; leave the temporal set out,
   with the rationale recorded inline so it reads as a decision, not an
   omission.
2. **Write side** — a canonical-phrasing rule in every pass that authors
   dependency prose, so future issues are parseable at birth rather than
   depending on extractor recall.

## Program Design

### Types

No new types. The change is confined to one module-level compiled pattern;
`FormatGaps.prose_dep_drift` / `FormatGaps.stale_prose_dep`
(`scripts/little_loops/issue_parser.py:249-250`, `list[str]`) are unchanged.

### Signatures

```python
# scripts/little_loops/issues/prose_deps.py — unchanged signature, wider _PHRASE_RE
def extract_prose_deps(body: str) -> set[str]
```

### Call Path

`ll-issues format-check <ID>` → `check_format_gaps()`
(`scripts/little_loops/issue_parser.py:535`) → `extract_prose_deps(body_only)`
(`:551`) → per-ID status split into `stale_prose_dep` (`:556`, done/cancelled
target) or `prose_dep_drift` (`:558`, active target) → consumed by
`/ll:refine-issue` Step 6.7, `/ll:wire-issue` Phase 3.7, and
`scripts/tests/test_prose_dep_sweep_gate.py`.

## Integration Map

### Files to Modify

- `scripts/little_loops/issues/prose_deps.py` — `_PHRASE_RE` (`:23`) and module docstring
- `scripts/tests/test_prose_deps.py` — positive/negative parametrized cases
- `commands/refine-issue.md` — Step 6 authoring rule; Step 6.7 phrasing list
- `skills/wire-issue/prose-dependency-gate.md` — authoring-side paragraph
- `commands/reconcile-issue.md` — Step 5 rewrite rules
- `docs/reference/API.md` — `extract_prose_deps` entry
- `docs/reference/CLI.md` — `format-check` `prose_dep_drift` description

### Dependent Files

- `scripts/little_loops/issue_parser.py:551-558` — `check_format_gaps()`, sole
  consumer; splits active targets into `prose_dep_drift` and done/cancelled
  into `stale_prose_dep`. Unchanged; inherits the wider match set.
- `scripts/tests/test_prose_dep_sweep_gate.py` — repo-wide sweep; surfaced
  three latent stale references once the pattern widened.
- `.kimi-code/skills/ll-refine-issue/`, `.kimi-code/skills/ll-ready-issue/` —
  `ll-adapt`-generated mirrors, intentionally not hand-edited.

## Implementation Steps

1. Widen `_PHRASE_RE` to the six synonyms; document the temporal exclusion in a
   comment beside the pattern and in the module docstring.
2. Add parametrized tests: one positive per synonym, one negative per excluded
   temporal phrasing.
3. Add the canonical-phrasing rule to `refine-issue` (Step 6, at the point of
   writing — not only in the Step 6.7 check), `wire-issue`'s gate companion,
   and `reconcile-issue` Step 5.
4. Update `API.md` / `CLI.md` phrasing lists and the exclusion rationale.
5. Resolve the sweep-gate fallout (see Verification Notes).
6. Write the missing edge for the issue that motivated this:
   `ll-issues link BUG-3029 --blocked-by BUG-3028`.

## Scope Boundaries

- **No third `prose_dep_suspect` tier.** A soft-signal key over the ambiguous
  set would carry ~613 candidates — noise that agents learn to ignore.
- **No subject-attribution parsing.** Prose of the form "ENH-x — open
  (blocked on ENH-y)" states a dependency *of another issue*; the extractor
  cannot see the subject. Not hit in practice here (all three sweep findings
  resolved to `stale_prose_dep`), so left alone rather than guessed at.
- **Generated `.kimi-code/` mirrors not hand-edited** — regenerated by `ll-adapt`.

## Impact

Closes the recall gap that let BUG-3029 sit un-wired despite three prose
statements of its blocker, and stops the refine/wire/reconcile passes from
generating the unparseable phrasing that caused it.

## Verification Notes

Widening turned `test_prose_dep_sweep_gate.py` red with three hits — EPIC-2575,
EPIC-2178, FEAT-2263. All three resolved to `stale_prose_dep`, not drift: each
used blocker phrasing about an issue that has since completed (ENH-2578,
ENH-2184, FEAT-1850 are all `done`; FEAT-2263 already carried its `depends_on`
edge). Per existing policy that is a prose fix, not a new edge, so the three
lines were corrected — including EPIC-2178's child list, which still described
ENH-2184 and ENH-2185 as open when both are done. No frontmatter edges were
added anywhere except BUG-3029.

Post-change: `ll-issues format-check BUG-3029 --format json` reports
`prose_dep_drift: []` / `stale_prose_dep: []`.

Full suite: 18,148 passed, 42 skipped, 4 failed. All four failures
(`test_logo.py::test_get_logo_returns_logo_content`,
`test_des_audit.py::test_real_tree_passes`,
`test_des_audit.py::test_clean_real_tree_returns_zero`,
`test_init_e2e.py::test_yes_run_prints_logo_banner_on_tty`) reproduce on a
stashed clean tree and are unrelated to this change — but two are "real tree"
assertions, suggesting independent drift on `main` worth its own issue.

`ruff check`, `ruff format --check`, and `mypy` clean on the changed Python
files (format scoped to changed files only).

## Related Key Documentation

- `docs/reference/API.md#extract_prose_deps`
- `docs/reference/CLI.md` — `ll-issues format-check`
- FEAT-2849 — original prose-dependency gate and its conservatism rationale

## Session Log
- `hook:posttooluse-status-done` - 2026-08-03T21:12:19 - `b2718da1-84ab-4936-9349-0419a7d4185b.jsonl`
- manual - 2026-08-03T21:11:15 - interactive session

---

## Status

**Done** | Created: 2026-08-03 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-03
- **Status**: Completed

### Files Changed
- `scripts/little_loops/issues/prose_deps.py`
- `scripts/tests/test_prose_deps.py`
- `commands/refine-issue.md`
- `commands/reconcile-issue.md`
- `skills/wire-issue/prose-dependency-gate.md`
- `docs/reference/API.md`
- `docs/reference/CLI.md`
- `.issues/epics/P3-EPIC-2575-code-knowledge-graph-adapter-query-protocol-providers-skill-integration.md`,
  `.issues/epics/P4-EPIC-2178-gemini-cli-host-adapter-tracking.md`,
  `.issues/features/P4-FEAT-2263-omp-hook-event-parity-audit.md` (stale prose references)
- `.issues/bugs/P3-BUG-3029-unguarded-gather-all-issue-ids-crash-risk.md`
  (`blocked_by: BUG-3028` edge)

### Verification Results
- `test_prose_deps.py`, `test_prose_dep_sweep_gate.py`,
  `test_ll_issues_format_check.py`, `test_refine_issue_command.py`,
  `test_issues_cli.py`, `test_wiring_skills_and_commands.py` — 551 passed
- Full suite — 18,148 passed; 4 pre-existing unrelated failures

### Commits
- Uncommitted at time of writing
