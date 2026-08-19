---
id: ENH-3000
status: open
priority: P3
captured_at: '2026-08-02T14:06:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
parent: EPIC-3023
relates_to:
- ENH-2983
- ENH-2971
- ENH-2999
decision_needed: false
testable: true
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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
- *Implementation surface*: `build_ref_index` and `classify_file_ref` both
  change under this option too — the prefix list rides on `RefIndex` and is
  checked as a form check inside `classify_file_ref` (see Program Design).

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- **Verdict wiring depth resolved**: `check_format_gaps()` (`scripts/little_loops/issue_parser.py:1011-1019`) only branches on `stale` and `ambiguous` today; `resolved`, `unresolvable_form`, and `planned_new` pass through the loop with no `FormatGaps` field, no `has_gaps` change, no `to_dict()` entry — they are silently non-gaps. Since `untracked_by_design` is a suppressing verdict (its purpose is to stop being reported as `stale`, not to be reported under a new category), it needs only the shallow treatment: a new `RefStatus` Literal member plus the form check in `classify_file_ref`. It does not need the 5-site `FormatGaps`/`has_gaps`/`to_dict`/docstring/`_print_gaps()` treatment that `ambiguous_file_ref` (ENH-2999) required — that treatment is only for verdicts meant to be *surfaced* as a gap category.
- **Denominator eligibility resolved**: `qualified_ref_count()` (`research_triage.py:215`) and `_triage_axis()` (`research_triage.py:410`) both gate on the literal tuple `("resolved", "stale", "ambiguous")` — duplicated independently at each site, no shared constant. Per `qualified_ref_count`'s own docstring, eligibility means "survived the form filter"; only `unresolvable_form` and `planned_new` are excluded, both decided at the form-check stage before index lookup. `untracked_by_design` is also a form check that runs before index lookup, and there is no git-tracked target to compare against for the staleness check (`research_triage.py:431-442`) — it therefore belongs in the same excluded category as `unresolvable_form`/`planned_new`, not added to the eligible tuple. Both call sites' literal tuples need updating independently (or reconciled with ENH-2990's `AxisCoverage` reason-code work per this issue's own trailing Scope Boundary note).
- **No shared prefix-matching helper exists** — three independent, shape-incompatible mechanisms already do adjacent things: (1) `_EXCLUDED_DIRS` (`verify_private_refs.py:75-90`) — hardcoded `frozenset` of bare directory *names*, matched via `any(part in _EXCLUDED_DIRS for part in rel_path.parts)`; (2) `file_matches_pattern()` (`git_operations.py:296+`) — full gitignore-glob semantics, the natural pairing for `scan.exclude_patterns` but currently has zero production callers for that config key (grep for `.scan.exclude_patterns` / `.scan.focus_dirs` returns nothing anywhere in `scripts/little_loops/`); (3) `_mirror_prefixes()` (`text_utils.py:198-214`) — a `@cache`d `tuple[str, ...]` of directory-prefix strings matched via plain `str.startswith(tuple)`, already used inside `classify_file_ref`'s own call chain (`suffix_match_candidates`, `text_utils.py:364`), though sourced from the host-capability registry rather than project config. This last one is the closest same-file precedent for "a cached tuple of directory prefixes consulted inside `text_utils.py`'s own classification logic."
- **Config-location caveat**: `scan` is explicitly excluded from the schema-vs-code value parity walk — `_SCHEMA_PARITY_EXCLUDED_SECTIONS = {"$schema", "project", "issues", "scan"}` (`test_config_schema.py:1191`). A new key added under `scan` therefore would not get the cross-check other config sections get for free; the schema-vs-default drift that guard exists to catch would go undetected there specifically.
- **The stale "Resolve the option..." sentence at the end of this section predates the decision recorded above in Decision Rationale** — Option B was selected on 2026-08-16 (Session Log, `/ll:decide-issue`) and `decision_needed` is `false` in frontmatter; that closing sentence describes a still-open decision that no longer exists.

## Integration Map

### Files to Modify

- `scripts/little_loops/text_utils.py` — `classify_file_ref` / `build_ref_index`
- `scripts/little_loops/config-schema.json` — if Option B is config-driven
- `scripts/little_loops/issues/research_triage.py` — denominator membership for
  the new verdict, same question as ENH-2999 raises

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` line
  553 calls `build_ref_index(config.project_root)` with no config-sourced arg;
  confirmed via `ll-code callers-of build_ref_index` this is the third
  production call site (alongside `research_triage.py:212,317`) and is not
  currently in this list — without threading the new prefix list through here
  the verdict never reaches production `format-check` output
- `scripts/little_loops/config/features.py` — `ScanConfig` (lines 304-324)
  needs a new field (e.g. `untracked_by_design: tuple[str, ...]`) plus a
  `from_dict()` update; `config-schema.json`'s `additionalProperties: false`
  on `scan` requires the key to be pre-declared there too
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()`'s hardcoded
  `"scan"` block (lines 807-811) enumerates keys by name; the new field is
  invisible outside `ScanConfig` itself until a line is added there

### Dependent Files

- `scripts/tests/test_text_utils.py`
- `scripts/tests/test_ll_issues_format_check.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issues/research_triage.py:212` and `:317` — two
  independent `build_ref_index()` call sites; both need the config-sourced
  prefix list threaded in, not just one, or `/ll:refine-issue`'s coverage
  gate only gets the fix on one code path
- `scripts/tests/test_symbol_cli_claim_sweep.py:34` — a fifth `build_ref_index()`
  call site (corpus sweep pinning a real hit-count ceiling on
  `stale_symbol_ref`/`mislocated_symbol_ref`/`stale_cli_flag`, not
  `stale_file_ref`); should stay inert under the new verdict but worth
  confirming rather than assuming

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `RefStatus` literal block (~line 7452), the
  `build_ref_index`/`RefIndex` signature blocks (~lines 7454-7464), and
  `classify_file_ref`'s prose description + `**Returns:**` line (~lines 7480,
  7487) all restate the closed five-member verdict set and need the new
  member appended
- `docs/reference/CLI.md` — `ll-issues research-triage`'s denominator prose
  (~line 1800: "`resolved`, `stale`, and `ambiguous`... stay
  denominator-eligible") is the doc mirror of the two Python literal tuples
  this issue changes; `ll-issues format-check`'s `stale_file_ref` prose
  (~lines 2074-2087) enumerates the non-reported verdicts and should gain a
  clause for `untracked_by_design`
- `docs/reference/CONFIGURATION.md` — the full-config example's `"scan"`
  section (~lines 96-99) should show the new key if it's added there

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py::TestScanConfig` (lines 605-623) — new case
  for the new `ScanConfig` field's `from_dict()` default/round-trip
- `scripts/tests/test_research_triage.py::TestReferenceFiltering` (~lines
  227-287) — new test mirroring
  `test_ambiguous_ref_is_denominator_eligible_but_not_covering` (lines
  262-287), asserting `qualified_ref_count(...) == 0` for an issue whose only
  ref is under an untracked-by-design prefix
- `scripts/tests/test_text_utils.py::TestClassifyFileRef` (lines 210-315) —
  new parametrized case(s), one per configured prefix, each asserting
  `classify_file_ref(...) == "untracked_by_design"`
- `scripts/tests/test_text_utils.py::TestBuildRefIndex` (lines 513-542) — new
  real-git-repo test with a file under an untracked-by-design prefix left
  uncommitted, confirming `classify_file_ref` still returns
  `"untracked_by_design"` despite the path being absent from
  `index.by_basename`
- `scripts/tests/test_ll_issues_format_check.py::TestStaleFileRef` (lines
  568-761) — new integration test mirroring
  `test_all_does_not_report_for_basenames_and_globs_only` (lines 631-650),
  asserting `stale_file_ref` is not reported for a ref under an
  untracked-by-design prefix

### Conventions in Force

- Fail-empty-never-raise for `git ls-files` call sites — evidence:
  `build_ref_index`'s docstring, `verify_private_refs._tracked_files()`
- little-loops ships into consuming projects, so anything project-shaped belongs
  in config, not a module constant — evidence: `.claude/CLAUDE.md` § Distribution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- **Config-plumbing path is longer than the current Files-to-Modify list**: a new `config-schema.json` key alone does not reach consumers. The established path for every existing config section is schema entry → dataclass `from_dict()` (`ScanConfig` lives in `scripts/little_loops/config/features.py:304-324`) → assignment in `BRConfig._parse_config()` and a `to_dict()` entry (`scripts/little_loops/config/core.py:306, 375-377, 808-810`) → a completeness-guard registration in `scripts/tests/test_config_schema.py` (`_DATACLASS_SECTION_MAP`, `TestDataclassSectionMapCompleteness`, `TestToDictSchemaParity`). If Option B's config surface is added as a new `ScanConfig` field (or a new dataclass), `config/features.py` and `config/core.py` belong in Files to Modify alongside `config-schema.json`, and `scripts/tests/test_config_schema.py` belongs in Dependent Files alongside the two test files already listed.
- **`scan` is excluded from the schema-vs-code parity guard** (`_SCHEMA_PARITY_EXCLUDED_SECTIONS` in `test_config_schema.py:1191` includes `"scan"`), and `scan.exclude_patterns`/`scan.focus_dirs` currently have zero runtime consumers anywhere in `scripts/little_loops/` — only `scan.exclude_patterns` reaches one consumer, `codequery/codegraph.py:_is_scan_relevant()`, for scan/touch relevance, not reference classification. A key added under `scan` inherits neither the parity check nor an existing reader; this is a fact for whichever design lands the config key, not a recommendation for where to put it.

## Implementation Steps

1. The design decision above is made and recorded (`/ll:decide-issue`).
2. The chosen mechanism lands with the verdict propagated to both consumers.
3. Corpus re-measurement shows ~315 findings leaving `stale` and no ref moving
   `resolved` → anything else.
4. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Thread the config-sourced `untracked_by_design` prefix list through all
  three production `build_ref_index()` call sites — `research_triage.py:212`,
  `research_triage.py:317`, and `format_check.py:553` — not just the
  function's own definition in `text_utils.py`
- Add the new `ScanConfig` field (`config/features.py:304-324`) plus its
  `from_dict()` update, and add the matching key to `BRConfig.to_dict()`'s
  hardcoded `"scan"` block (`config/core.py:807-811`), since neither happens
  automatically from a `config-schema.json` entry alone
- Update both independent denominator tuples in `research_triage.py`
  (`qualified_ref_count()` line 215, `_triage_axis()` line 410) to exclude
  `untracked_by_design` — no shared constant exists between them today, so
  each literal tuple needs editing separately
- Update `classify_file_ref`'s "Resolution order" docstring
  (`text_utils.py:272-299`) to add the new form-check step; the ordering
  described there is explicitly non-commutative and authoritative, not just
  descriptive
- Update `docs/reference/API.md`, `docs/reference/CLI.md`, and
  `docs/reference/CONFIGURATION.md` per the Documentation subsection above
- Confirm `scripts/tests/test_symbol_cli_claim_sweep.py`'s corpus-pinned
  `build_ref_index()` call stays inert under the new verdict — it only
  asserts on `stale_symbol_ref`/`mislocated_symbol_ref`/`stale_cli_flag`, not
  `stale_file_ref`

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
- `/ll:confidence-check` - 2026-08-19T20:40:45 - `bcacfe91-5c56-4df7-84f7-9ce41b394975.jsonl`
- `/ll:wire-issue` - 2026-08-19T20:38:04 - `6e6a91fc-ee4b-4b69-a901-52cc2ea54f9e.jsonl`
- `/ll:refine-issue` - 2026-08-19T20:15:03 - `0d2916d2-f9ec-408b-ba0e-bbe68b7d2760.jsonl`
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
