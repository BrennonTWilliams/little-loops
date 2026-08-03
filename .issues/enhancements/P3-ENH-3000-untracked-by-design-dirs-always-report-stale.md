---
id: ENH-3000
status: open
priority: P3
captured_at: "2026-08-02T14:06:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3023
relates_to: [ENH-2983, ENH-2971, ENH-2999]
decision_needed: true
testable: true
---

# References into untracked-by-design directories always report `stale`

## Summary

`build_ref_index()` indexes `git ls-files` output, so any reference into a
directory that is gitignored *by design* — `thoughts/`, `postmortems/`,
`.loops/`, `logs/` — can never resolve and is always reported as drift.
**315 instances** across `.issues/`, roughly 9% of all `stale_file_ref`
findings. This is structural, not a bug in any one branch: the index cannot
see these paths by construction.

## Current Behavior

```
thoughts/research/pi-headless-cli.md      -> stale   (file exists on disk)
.loops/eval-harness-feat-1516.yaml        -> stale   (run artifact, by design untracked)
postmortems/<run>.md                      -> stale   (source-repo-only, gitignored)
```

These are exactly the directories `.claude/CLAUDE.md` § Key Directories
documents as real and intentionally untracked — `postmortems/` is explicitly
"Gitignored, source-repo-only", and `thoughts/` holds plans and research the
issue workflow routinely cites.

`build_ref_index()` (`scripts/little_loops/text_utils.py`) follows the
fail-empty-never-raise `git ls-files` convention shared with
`verify_private_refs._tracked_files()` and `codequery/fallback._tracked_py_files()`.
The tracked-files-only contract is deliberate; this issue is about what to do
at its edge, not about abandoning it.

## Expected Behavior

A reference into a documented, intentionally-untracked directory is not
reported as drift. Whether it reports as `resolved`, `unresolvable_form`, or a
new status depends on which design below is chosen.

## Motivation

315 findings is the single largest false-positive class remaining after the
three narrow fixes landed (which removed 168). Every one of them trains the
reader to skim past `stale_file_ref` output, which devalues the ~73% of
findings that are genuine drift. A check that is right most of the time but
noisy in a predictable, ignorable way is worse than one with a narrower,
trusted scope.

## Proposed Solution

**This issue requires a decision before implementation** — the two designs
trade against each other and the choice is not obvious.

**Option A — filesystem-existence fallback.** When the index misses, stat the
path relative to the project root; if it exists, resolve.

- *For*: accurate for every case, including directories nobody thought to list.
- *Against*: weakens the tracked-files-only contract `build_ref_index` is built
  on, and makes the verdict depend on local working-tree state — a ref could
  resolve on the author's machine and report stale in a clean checkout or in a
  consuming project. Also adds a stat per unresolved ref on a path currently
  free of filesystem I/O after the single `git ls-files` call.

**Option B — untracked-by-design prefix allowlist.** Classify refs under a
known set of prefixes as `unresolvable_form` (or a new `untracked_by_design`).

- *For*: preserves the contract and determinism — the same input yields the same
  verdict everywhere, which matters because this classifier runs in consuming
  projects, not just here.
- *Against*: needs maintenance, and the list is project-specific. It would have
  to be config-driven (`scan.exclude_patterns` is the nearest existing surface)
  rather than hardcoded, since little-loops ships into other projects whose
  untracked-by-design directories differ.

**Recommendation**: Option B, config-driven, on the determinism argument — but
weigh it properly rather than treating this as settled. Note that Option A's
working-tree dependence is a real hazard for `research_triage`, whose ≥80%
coverage gate would then vary by machine.

## Program Design

The two options place the mechanism in different layers; the signatures below
cover both so the decision does not block on restating them.

### Signatures

```python
# Option B (recommended): the prefix list rides on the index, resolved once per
# invocation rather than re-read per reference — mirroring how by_basename is
# already threaded through every classify_file_ref call.
@dataclass(frozen=True)
class RefIndex:
    by_basename: dict[str, list[str]]
    untracked_by_design: tuple[str, ...] = ()   # e.g. ("thoughts/", "postmortems/")

def build_ref_index(root: Path, *, untracked_by_design: tuple[str, ...] = ()) -> RefIndex: ...

# Option A: no signature change; classify_file_ref gains a stat() fallback after
# the index lookup misses, introducing filesystem I/O the module currently lacks.
```

Under Option B the verdict is a form check — it runs before any lookup, next to
the glob and outside-repo checks, since a path under such a prefix is not a
resolvable repo reference regardless of index contents.

### Call Path

`build_ref_index` (gains the prefix list, sourced from config) →
`classify_file_ref` (new branch) → both consumers:

- `check_format_gaps` → `main_format_check`
- `qualified_ref_count` — same denominator question ENH-2999 raises; answer both
  the same way

Resolve the option with `/ll:decide-issue` before implementation.
`decision_needed: true` is set for that reason.

## Integration Map

### Files to Modify

- `scripts/little_loops/text_utils.py` — `classify_file_ref` / `build_ref_index`
- `scripts/little_loops/config-schema.json` — if Option B is config-driven
- `scripts/little_loops/issues/research_triage.py` — denominator membership for
  the new verdict, same question as ENH-2999 raises

### Dependent Files

- `scripts/tests/test_text_utils.py`
- `scripts/tests/test_ll_issues_format_check.py`

### Conventions in Force

- Fail-empty-never-raise for `git ls-files` call sites — evidence:
  `build_ref_index`'s docstring, `verify_private_refs._tracked_files()`
- little-loops ships into consuming projects, so anything project-shaped belongs
  in config, not a module constant — evidence: `.claude/CLAUDE.md` § Distribution

## Implementation Steps

1. The design decision above is made and recorded (`/ll:decide-issue`).
2. The chosen mechanism lands with the verdict propagated to both consumers.
3. Corpus re-measurement shows ~315 findings leaving `stale` and no ref moving
   `resolved` → anything else.
4. `python -m pytest scripts/tests/` passes.

## Impact

- **Effort**: Small once the design is chosen; the decision is the work.
- **Risk**: Medium under Option A (working-tree-dependent verdicts leaking into
  `research_triage`'s gate); Low under Option B.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: references into directories that are untracked as a matter of
  design.
- **Out of scope**: ambiguous multi-match refs — see ENH-2999.
- **Out of scope**: `postmortems/` content itself must never be carried into
  consuming projects; this issue only changes how references *to* it classify.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | § Key Directories documents these dirs as real and gitignored |
| `scripts/little_loops/text_utils.py` | `build_ref_index`'s tracked-files-only contract |

## Session Log
- `/ll:capture-issue` - 2026-08-02

## Status

- **Status**: open
