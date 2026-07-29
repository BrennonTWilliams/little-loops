---
id: ENH-2900
type: enhancement
priority: P4
status: done
captured_at: '2026-07-28T22:29:06Z'
completed_at: '2026-07-29T02:41:47Z'
discovered_date: 2026-07-28
discovered_by: capture-issue
relates_to:
- BUG-2897
- BUG-2898
- BUG-2899
depends_on:
- BUG-2897
- BUG-2899
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current code confirmed stale.** `scripts/little_loops/cli/issues/sequence.py`
  `cmd_sequence()`'s `--json` dict literal (lines 144–161) is unchanged from
  what this issue describes: `"blocks": issue.blocks` at line 156, sibling to
  `"blocked_by": sorted(graph.blocked_by.get(issue.issue_id, set()))` (line
  150), `"deferred_blockers"` (151–155, graph-derived), and
  `"depends_on": sorted(graph.get_pending_prerequisites(issue.issue_id))`
  (157). A fourth sibling, `"in_cycle": issue.issue_id in cycle_ids` (line
  159, from BUG-2899), already landed in the same literal — confirming the
  "land in one commit with BUG-2899" ordering note below is now moot (BUG-2899
  is done) and this really is a single-line change to an existing literal, not
  a coordinated multi-field rewrite.
- **Both hard-ordering dependencies have landed.** BUG-2897 and BUG-2899 (this
  issue's `depends_on`) both show `status: done`. BUG-2898 (which BUG-2897
  absorbed, per this issue's own Scope Boundary note) has also landed. This
  issue is unblocked for implementation.
- **`graph.blocks` is correctly scoped, verified against current code.**
  `DependencyGraph.from_issues()` (`dependency_graph.py:56–152`) populates
  `graph.blocks` bidirectionally with `graph.blocked_by` in both the
  `blocked_by:`-declaration pass (lines 103–118) and the one-sided
  `blocks:`-declaration reconciliation pass (124–134) — every edge write to
  `blocked_by` has a paired write to `blocks`, so there is no code path that
  populates one without the other. Non-terminal filtering (done/cancelled
  excluded, deferred included) comes from the caller's input list
  (`find_issues_for_graph()`, called at `sequence.py:68`), not from
  `from_issues()` itself — `graph.blocks` inherits the same non-terminal scope
  as `graph.blocked_by` for free.
- **`--type` filtering confirmed NOT applied at graph-construction time**
  (`sequence.py:64–68`): the graph is always built from the full non-terminal
  issue set; `--type` only narrows the `display` list afterward (lines
  111–112). Adopting `graph.blocks` will not be silently truncated under
  `--type`, matching current `blocked_by`/`depends_on` behavior.
- **Existing test gap, concrete location.** `test_sequence_json_output`
  (`test_issues_cli.py:1480–1512`) asserts `"blocks" in item` and
  `isinstance(item["blocked_by"], list)` but has **no** `isinstance` check on
  `blocks` itself, and no sort/graph-derivation assertion. The class
  `TestSequenceDeferredAndCrossTypeBlockers` (`test_issues_cli.py:1678+`,
  which already contains `test_sequence_json_deferred_blockers_field` at
  1715–1747) is the natural home for the new `blocks`-specific tests this
  issue calls for — it already has the deferred-target fixture pattern to
  adapt (flip `blocked_by:`/`blocks:` roles: give the blocker issue no
  frontmatter `blocks:` field and assert `graph.blocks` derives it from the
  blocked issue's `blocked_by:` declaration).
- **Two additional raw-`blocks` consumers found beyond `ll-issues show --json`**
  (already listed above): `scripts/little_loops/cli/issues/show.py` uses
  `frontmatter.get("blocks")` directly at line 253/450 (confirmed, no
  `DependencyGraph` constructed in that code path at all — a larger follow-up
  than a one-line swap), and
  `scripts/little_loops/cli/issues/clusters.py:306–307,411–414` also reads raw
  `issue.blocks` for edge-type filtering (elsewhere in the same file,
  `clusters.py` also correctly uses `graph.blocks` for color annotation,
  giving a same-file example of both the bug pattern and the fix pattern to
  reference in a follow-up issue).
- **Consumer grep confirmed clean.** No caller of `sequence --json` reading a
  `blocks` field was found under `.claude/`, `skills/`, `commands/`, or
  `scripts/little_loops/loops/` — Implementation Step 1's grep is satisfied;
  the JSON output has no known in-repo consumer of the raw semantics.

### Documentation
- `docs/reference/API.md` — `ll-issues sequence --json` field descriptions, if
  the schema is documented there
- `docs/reference/CLI.md` — `#### \`ll-issues sequence\` / \`ll-issues seq\``
  section (lines 1249–1286, confirmed by `/ll:wire-issue`) documents the
  `--json` flag's added fields — `unverified_prose_deps`, `in_cycle`,
  `blocked_by`/`depends_on` ordering — but never describes `blocks`'
  semantics at all. Not broken by this change, but the natural place to add a
  one-line note now that `blocks` shares `blocked_by`'s non-terminal-filtered,
  sorted contract, matching how its siblings are documented in the same
  section.

### Configuration
- N/A

## Implementation Steps

1. Grep for `sequence --json` consumers; confirm none rely on raw `blocks`.
2. Add a test asserting `blocks` excludes closed targets and is sorted.
3. Change the `"blocks"` entry to `sorted(graph.blocks.get(...))`.
4. Spot-check sibling JSON emitters for the same mismatch; file follow-ups if found.
5. Update `docs/reference/CLI.md`'s `ll-issues sequence` `--json` section to
   describe `blocks`' non-terminal-filtered, sorted semantics alongside its
   documented siblings (added by `/ll:wire-issue`).
6. Run `python -m pytest scripts/tests/`.

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
- `/ll:manage-issue` - 2026-07-29T02:41:20Z - `c47096c9-6c91-42e9-95a4-d19ac29cd14b.jsonl`
- `/ll:confidence-check` - 2026-07-29T02:35:16Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ed43db14-1397-48e6-bdce-3bfec2b6bd95.jsonl`
- `/ll:wire-issue` - 2026-07-29T02:33:48 - `b8c451e1-3b1e-4664-aecc-2d17cdcc6ec3.jsonl`
- `/ll:refine-issue` - 2026-07-29T02:27:59 - `a0bd30bd-5609-470e-b72c-eb9b2ccd37b5.jsonl`
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
