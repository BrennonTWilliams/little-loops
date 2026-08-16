---
id: ENH-3000
status: open
priority: P3
captured_at: "2026-08-02T14:06:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3023
relates_to: [ENH-2983, ENH-2971, ENH-2999]
decision_needed: false
testable: true
verify_verdict: VALID
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

> **Selected:** Option B — untracked-by-design prefix allowlist, config-driven. Option A scored 0/3 on codebase consistency: no existing `git ls-files` call site (11 surveyed) layers a filesystem stat on an index miss, and `verify_private_refs.py:36-38` is a direct prior-art rejection of exactly this tradeoff ("structural rules are deterministic across machines... local name rules are not, which is why they are excluded"). See Decision Rationale below.

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

### Decision Rationale

**Selected**: Option B — untracked-by-design prefix allowlist, config-driven.

**Reasoning**: Option A introduces a failure mode this codebase has explicitly
rejected once already for the identical set of directories. `verify_private_refs.py:34-38`
articulates the only prior statement of a determinism-across-machines principle
in this codebase and resolves it by *excluding* the non-deterministic source
(local, gitignored state) from portable comparison — not by falling back to it.
An 11-site survey of every `git ls-files` call in the codebase found zero
precedent for layering a filesystem `stat()` on an index miss; the one call
site that unions tracked and untracked files (`work_verification.py:193`)
still does so via a second git call, not a raw filesystem check. Option B's
verdict-wiring half (new `RefStatus` literal, ordered form-check ahead of
lookup) matches the established pattern for `ambiguous`/`planned_new` exactly.
Its weaker half — config-sourcing the prefix list — has no existing wired
precedent (`scan.exclude_patterns` is unwired to `text_utils.py` today, and a
shape-incompatible hardcoded list `_EXCLUDED_DIRS` already covers the same
four directories in `verify_private_refs.py:75-90`) but this is new plumbing
to add, not a principle to violate, and it is explicitly named in the issue's
own Integration Map (`config-schema.json — if Option B is config-driven`).

**Scoring summary**:

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 0 | 2 |
| Simplicity | 2 | 2 |
| Testability | 1 | 3 |
| Risk | 1 | 2 |
| **Total** | **4/12** | **9/12** |

**Key evidence**:
- No `git ls-files` call site (11 surveyed) combines a tracked-file index with
  a filesystem `stat()` fallback (`text_utils.py`, `verify_private_refs.py`,
  `codequery/fallback.py:38-43`, `symbol_claims.py:356-381`,
  `work_verification.py:193`, and 6 others).
- `verify_private_refs.py:36-38` — direct prior resolution of the same
  determinism tradeoff, decided against filesystem-state dependence.
- `verify_private_refs.py:75-90` (`_EXCLUDED_DIRS`) already covers exactly
  these four directories with a static list, evidencing exclusion (Option B's
  shape) as the existing resolution, not disk-presence checking (Option A's
  shape).
- `text_utils.py:161, 272-299` — `RefStatus` `Literal` + ordered
  "Resolution order" docstring is the clean precedent Option B's verdict
  mechanics slot into, matching `ambiguous` (ENH-2999) and `planned_new`.
- Issue's own risk assessment (lines 176-177) independently flags Option A as
  "Medium risk" (working-tree-dependent verdicts leaking into
  `research_triage`'s ≥80% coverage gate) vs. "Low" under Option B.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- **Verdict wiring precedent**: new `classify_file_ref()` verdicts are added as a member of the `RefStatus` `Literal` (`scripts/little_loops/text_utils.py:161`), slotted into the explicitly non-commutative "Resolution order" checks documented in the function's docstring (`text_utils.py:272-299`). The most recent additions (`ambiguous` for ENH-2999, `planned_new`) both followed this shape.
- **Two wiring depths exist, and precedent does not settle which ENH-3000's new verdict needs**: `check_format_gaps()` only branches on verdicts it wants reported as drift — `resolved`/`planned_new`/`unresolvable_form` pass through with no `FormatGaps` field, no `has_gaps` change, no `to_dict()` change (`scripts/little_loops/issue_parser.py:766-774`). A verdict meant to be *reported* (e.g. `ambiguous_file_ref` for ENH-2999) instead gets 5 coordinated sites: new `FormatGaps` field, OR'd into `has_gaps`, added to `to_dict()`, a docstring "Gap classes:" bullet, and rendering in `_print_gaps()`/CLI help (`issue_parser.py:315-559`; `scripts/little_loops/cli/issues/format_check.py:61-199`). Whether `untracked_by_design` is a suppressing verdict (shallow) or a reported one (all 5 sites) is an open call the design doesn't currently pin down.
- **A hardcoded, name-based directory-exclusion list already exists for these exact four directories**, and it disagrees with `scan.exclude_patterns`' shape — directly relevant to Option B's "config-driven" framing:
  ```python
  _EXCLUDED_DIRS = frozenset({..., "postmortems", ".loops", "thoughts", "logs"})
  ```
  (`scripts/little_loops/cli/verify_private_refs.py:75-90`, rationale comment at :71-74). This is a plain Python constant, not sourced from config.
  By contrast, `scan.exclude_patterns` is glob-syntax (`**/node_modules/**`), schema-declared with `additionalProperties: false` on `scan` (`config-schema.json:739-763`), mirrored in `ScanConfig.exclude_patterns` (`config/features.py:304-324`), and matched via the gitignore-style `file_matches_pattern()` (`scripts/little_loops/git_operations.py:296-351`) — used for scan/touch relevance, not reference-resolution classification. Neither list is currently wired to `classify_file_ref`/`build_ref_index`, and no shared "is this ref under an untracked-by-design directory" helper exists that both could delegate to.
- **The filesystem-state-vs-git-tracked-state tradeoff Option A introduces has one prior resolution in this codebase**: `ll-verify-private-refs` keeps its two rule families deliberately separate on exactly this axis — "structural rules are deterministic across machines, so the baseline is portable; local name rules are not, which is why they are excluded from [full-scan] mode" (`verify_private_refs.py:36-38`). Structural rules compare against a tracked baseline file; name rules source from a gitignored local file, excluded from portable comparison (`verify_private_refs.py:22-38, 156`). No prior code path mixes a `git ls-files`-only index with a `stat()` fallback the way Option A proposes.
- **Test structure precedent**: verdict unit tests live in `class TestClassifyFileRef` (`scripts/tests/test_text_utils.py:210-315`), one method per case constructing `RefIndex(by_basename={...})` inline. Marker/corpus-driven verdicts get a `@pytest.mark.parametrize` sweep plus a paired negative-control test proving a near-miss still returns the old verdict (`test_planned_new_marker_variants` / `test_does_not_exist_marker_stays_stale`, :295-315). `build_ref_index()` itself is tested against a real throwaway git repo built via `subprocess.run(["git","init",...])` in `tmp_path` (:516-529), plus a mocked-subprocess test for the fail-empty path (:539-542).

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2966 both modify `check_format_gaps` in `scripts/little_loops/issue_parser.py` for unrelated gap classes (a new `stale_file_ref` verdict branch vs. the testable-keyword scan surface). Coordinate implementation order to avoid a merge collision in the same function.

## Session Log
- `/ll:decide-issue` - 2026-08-16T19:52:58 - `a441e649-6a94-4074-a117-b8df44bd2807.jsonl`
- `/ll:refine-issue` - 2026-08-16T19:42:17 - `658492bc-e02e-4d03-829a-fae819b3a566.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:52 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:45 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:capture-issue` - 2026-08-02

## Status

- **Status**: open

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's new `untracked_by_design` verdict/denominator status and ENH-2990's reason-code taxonomy for `AxisCoverage` both touch coverage/denominator accounting in `scripts/little_loops/issues/research_triage.py`. When implementing, reconcile both into one consistent enum rather than two independently-evolving classification schemes in the same module.
