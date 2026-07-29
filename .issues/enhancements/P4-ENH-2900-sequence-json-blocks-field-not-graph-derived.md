---
id: ENH-2900
type: enhancement
priority: P4
status: open
captured_at: '2026-07-28T22:29:06Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2897
- BUG-2898
- BUG-2899
depends_on:
- BUG-2897
- BUG-2899
---

# ENH-2900: `ll-issues sequence --json` `blocks` is raw frontmatter while `blocked_by` is graph-derived

## Summary

In `cmd_sequence()`'s `--json` branch, three of the four dependency fields are
read from the constructed `DependencyGraph` and one is not:

```python
"blocked_by":  sorted(graph.blocked_by.get(issue.issue_id, set())),   # graph-derived
"blocks":      issue.blocks,                                          # raw frontmatter
"depends_on":  sorted(graph.get_pending_prerequisites(issue.issue_id)),# graph-derived
```

The graph-derived fields are filtered to active issues — `done`/`cancelled`
targets are excluded at `from_issues()` time. `issue.blocks` is the unfiltered
frontmatter list, so it can name closed issues that `blocked_by` would never
report. It is also unsorted, unlike its siblings.

A consumer reading both fields gets two different filtering semantics under
field names that read as symmetric counterparts.

## Current Behavior

- `blocked_by` — active-only, sorted, graph-derived
- `blocks` — all declared targets regardless of status, frontmatter order,
  not graph-derived
- `depends_on` — active-only pending prerequisites, sorted, graph-derived

An issue declaring `blocks: [FEAT-100]` where `FEAT-100` is `done` reports
`"blocks": ["FEAT-100"]`, while the reciprocal relationship is correctly absent
from `FEAT-100`'s `blocked_by` (it isn't even in the graph). Round-tripping the
JSON to reconstruct the graph therefore yields edges the tool itself doesn't
honor.

Note the graph *does* maintain a `blocks` mapping (`graph.blocks`), populated
bidirectionally in `from_issues()` and already filtered — it simply isn't the
one being serialized.

## Expected Behavior

`blocks` matches its siblings' semantics and shape:

```python
"blocks": sorted(graph.blocks.get(issue.issue_id, set())),
```

All four dependency fields then describe the same active-issue graph, sorted
consistently, and the JSON becomes a faithful serialization of what the ordering
logic actually used.

## Motivation

The value here is contract coherence rather than a user-visible bug: no current
consumer is known to be broken. But `--json` exists (FEAT-701) to be consumed
programmatically, and a field that silently uses different filtering from its
apparent counterpart is the kind of inconsistency that produces a confusing
downstream bug long after the fact — most likely in a loop YAML or skill that
reasons over both directions of an edge and finds them disagreeing.

Fixing it while the surrounding sequencing defects (BUG-2897/2898/2899) are being
worked is cheap; fixing it after something depends on the current shape is not.

No failure has been observed in practice — this is a latent inconsistency found
during a review of `ll-issues sequence`, not a reported bug. Priority is set
accordingly.

## Scope Boundaries

**In scope:**
- The `"blocks"` field in `ll-issues sequence --json` output
- A confirmation grep that no consumer depends on the raw frontmatter semantics
- A test asserting the four dependency fields share filtering and sort semantics

**Explicitly out of scope:**
- The text output of `ll-issues sequence` — it does not render `blocks` at all
- The ordering logic itself; `graph.blocks` is already what `from_issues()`
  maintains, so no behavioural change to sequencing results
- Fixing the same raw-vs-graph mismatch in sibling emitters (`ll-issues show
  --json`, `ll-deps`, `impact-effort`). The audit in Implementation Steps flags
  them; each becomes its own follow-up issue rather than being fixed here.
- The `ll-issues show --json` status display-casing quirk — a separate known
  inconsistency, unrelated to dependency fields
- Any change to the top-level JSON array contract established by FEAT-701; if
  the raw list turns out to be needed, it gets an additive `declared_blocks`
  field rather than a restructure

## Proposed Solution

One-line change in the `--json` branch of `cmd_sequence()`:

```python
"blocks": sorted(graph.blocks.get(issue.issue_id, set())),
```

`graph.blocks` is populated in `from_issues()` from both `blocked_by`
declarations (first pass) and one-sided `blocks:` declarations (second pass), so
it is a superset of what the raw field captures for *active* targets — the
change loses only closed-issue references, which is the intent.

**Before changing it, confirm no consumer depends on the raw semantics.** If some
caller genuinely wants the declared-including-closed list, add a separate
explicitly-named field (`declared_blocks`) rather than keeping the mismatch under
the current name.

Consider also whether the text output needs a matching change — it doesn't
currently render `blocks` at all, so no.

## API/Interface

`ll-issues sequence --json` array element:

```jsonc
{
  "id": "BUG-2898",
  "priority": "P2",
  "title": "...",
  "path": ".issues/bugs/...",
  "blocked_by": ["FEAT-010"],           // unchanged: active-only, sorted
  "blocks": ["ENH-2900"],               // CHANGED: now active-only, sorted
  "depends_on": [],                     // unchanged: active-only, sorted
  "unverified_prose_deps": []           // unchanged
}
```

Breaking only for a consumer relying on closed-issue IDs appearing in `blocks`,
or on frontmatter declaration order. Both seem unlikely; verify rather than
assume.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()`, `--json`
  branch, the `"blocks"` entry

### Dependent Files (Callers/Importers)
- TBD — grep `.claude/`, `skills/`, `commands/`, `scripts/little_loops/loops/`
  for `sequence --json` consumers reading a `blocks` field
- `scripts/little_loops/dependency_graph.py` — `graph.blocks` is the replacement
  source; no change needed

### Similar Patterns
- Audit sibling JSON emitters for the same raw-vs-graph mismatch:
  `ll-issues show --json`, `ll-deps`, `ll-issues impact-effort` — anywhere an
  `IssueInfo` field is serialized alongside graph-derived data
- `ll-issues show --json` already has a known display-casing quirk on `status`;
  worth checking its dependency fields in the same pass

### Tests
- `scripts/tests/test_issues_cli.py` — assert `blocks` excludes a `done` target
  and is sorted; assert `blocked_by`/`blocks` are reciprocal across two active
  issues in the same output
- **Also assert a `deferred` target is _included_ in `blocks`.** This is the
  behaviour that actually changes relative to today under BUG-2897's widened
  graph, and it is the assertion that would catch a regression where the graph
  silently narrows back to active-only. The `done`-exclusion test above passes
  both before and after BUG-2897, so it does not pin the new contract on its own.

### Documentation
- `docs/reference/API.md` — `ll-issues sequence --json` field descriptions, if
  the schema is documented there

### Configuration
- N/A

## Implementation Steps

1. Grep for `sequence --json` consumers; confirm none rely on raw `blocks`.
2. Add a test asserting `blocks` excludes closed targets and is sorted.
3. Change the `"blocks"` entry to `sorted(graph.blocks.get(...))`.
4. Spot-check sibling JSON emitters for the same mismatch; file follow-ups if found.
5. Run `python -m pytest scripts/tests/`.

## Impact

- **Severity**: Low — latent inconsistency, no known broken consumer
- **Scope**: `ll-issues sequence --json` only
- **Risk of fix**: Low, contingent on the Step 1 grep coming back clean
- **User-visible**: Only to `--json` consumers; text output is unaffected
- **Sequencing**: Best landed alongside BUG-2897/2898/2899, which touch the same
  function — as a standalone change the overhead exceeds the payoff

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | `ll-issues` CLI surface and `dependency_graph` module reference |
| `.claude/CLAUDE.md` § Issue File Format | `blocked_by` / `blocks` frontmatter semantics and status enum |
| `docs/ARCHITECTURE.md` | Consumers of dependency data across orchestration layers |

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-29T00:04:13 - `00aa385f-3c68-486e-aadc-2dadfb4a2e42.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-28T23:18:36 - `139954b3-6523-4f66-ba64-f2917d895a02.jsonl`
- `/ll:capture-issue` - 2026-07-28T22:29:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73139eea-b48b-4fa0-a6fa-0b390a284d9f.jsonl`

---

## Status

**Status**: open

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, conflicts C4/C5): this issue is
now `depends_on: BUG-2897`, and two of its stated premises change once that
lands.

**1. "active-only" is the wrong term after BUG-2897.** This issue's Summary,
Current Behavior, Expected Behavior, and API/Interface sections all describe the
graph-derived fields as *"filtered to active issues"*. BUG-2897 deliberately
widens graph membership to the **non-terminal** set — `done`/`cancelled` are
still excluded, but `deferred` issues become graph nodes. When implementing,
rewrite that wording throughout from "active-only" to **"non-terminal (excludes
`done`/`cancelled`; includes `deferred`)"**. The `// CHANGED: now active-only,
sorted` comment in the API/Interface block is likewise stale.

This is a real contract change, not just wording: after BUG-2897, adopting
`graph.blocks` means deferred IDs newly appear in `blocks` where the raw
frontmatter list would have shown them regardless — but `blocked_by` will now
show them too, which is the symmetry this issue wants. The acceptance test
("`blocks` excludes a `done` target") remains valid as written.

**2. `graph.blocks` is only trustworthy once the graph is built unfiltered.**
BUG-2897 absorbed BUG-2898, which fixes `--type` being applied at graph-
construction time. Adopting `graph.blocks` *before* that fix would convert
`blocks` from "complete but unfiltered" into "silently truncated under
`--type`" — strictly worse than today for the exact case BUG-2898 documented as
already broken for `blocked_by`/`depends_on`. Hence the hard ordering.

**3. Co-edited `--json` dict literal** (conflict C6, low severity): BUG-2899
also adds a per-item field (`"in_cycle": true`) to the same dict literal, and
independently reached the same conclusion as this issue about preferring
additive per-item fields over restructuring FEAT-701's top-level array. No
design conflict — land them in one commit, or sequence this issue after
BUG-2899, to avoid a trivial merge conflict.
