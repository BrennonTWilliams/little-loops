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
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
---

# References into untracked-by-design directories always report `stale`

## Summary

`build_ref_index()` indexes `git ls-files` output, so a reference to a path that
is gitignored *by design* — `thoughts/`, `postmortems/`, `.loops/` run
artifacts, `logs/`, and `.ll/` runtime-state files — cannot resolve and is
reported as drift. **267 refs** across `.issues/`, **8.3% of the 3,231
`stale_file_ref` findings** (simulated against the exact shipped default on
2026-08-19; see Corpus Measurement below). This is structural for the untracked
subset: the index cannot see those paths by construction.

**Important qualifier, measured 2026-08-19**: these directories are *partially*
tracked, not wholly untracked. `thoughts/` holds **461 git-tracked files**
(tracked before the ignore rule landed) and `.loops/` holds 11; `.gitignore`
ignores only specific `.loops/` subdirectories (`runs/`, `tmp/`, `queue/`,
`.history/`, …), not `.loops/` itself, and `.ll/` is ignored **per-file**
(`.ll/ll-context-state.json`, `.ll/ll.local.md`, …) with `.ll/decisions.d/` and
`.ll/ll-config.json` tracked. 65 refs under these prefixes resolve correctly
today. Any fix that suppresses a whole prefix unconditionally destroys those
resolutions — see Program Design § Check Ordering.

## Current Behavior

```
thoughts/research/pi-headless-cli.md      -> stale   (untracked, exists on disk)
.loops/runs/<run>/diagnosis.md            -> stale   (run artifact, by design untracked)
postmortems/<run>.md                      -> stale   (source-repo-only, gitignored)
.ll/ll-context-state.json                 -> stale   (runtime state, gitignored per-file)

thoughts/FEAT-670-layout-engine-research.md -> resolved  (tracked — must stay resolved)
.loops/rl-rlhf.yaml                         -> resolved  (tracked — must stay resolved)
.ll/standards.md                            -> stale     (proposed by ENH-2023, not yet built — must stay reported)
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

267 findings is a predictable, mechanically-identifiable false-positive class:
every one of them trains the reader to skim past `stale_file_ref` output. A
check that is right most of the time but noisy in a *predictable, ignorable*
way is worse than one with a narrower, trusted scope — and this class is
suppressible with zero judgment calls, which is what makes it worth fixing
even at 8.3%.

**Corrected sizing** (the original capture claimed "315 instances, ~9%, the
single largest false-positive class remaining"; a 2026-08-19 pass narrowed that
to 184/5.7% before the `.ll/` slice was found):

- 267 stale refs suppressed by the shipped default, spanning five prefix
  families — not 315, and not the 184 measured before `.ll/` was included.
- 8.3% of stale findings.
- **Not** the largest class. Stale refs by leading path component:
  `scripts/` 1525, `commands/` 219, `skills/` 216, `docs/` 178, `.claude/` 151,
  `.ll/` 142, `thoughts/` 99, `.loops/` 71, `hooks/` 66. Even aggregated this
  sits behind `scripts/`, and the components above it are mostly genuine drift.

This keeps ENH-3000 at P3 rather than promoting it: it is a clean, cheap,
zero-judgment suppression, not the dominant noise source.

### The `.ll/` slice — same class, different shape

`.ll/` contributes **109 of the 267** (14 unique paths), every one confirmed
via `git check-ignore`:

| ref | count | | ref | count |
|---|---|---|---|---|
| `.ll/ll-context-state.json` | 28 | | `.ll/ll-precompact-state.json` | 14 |
| `.ll/ll-continue-prompt.md` | 24 | | `.ll/ll-edit-batch-state.json` | 6 |
| `.ll/ll.local.md` | 19 | | `.ll/ll-sync-state.json` | 5 |

plus 8 more (`.ll/ll-session-state.json`, `.ll/ll-state.json`,
`.ll/ll-auto-state.json`, `.ll/ll-sprint-state.json`,
`.ll/ll-doc-drift-state.json`, `.ll/.auto-manage-state.json`,
`.ll/context-pressure-state.json`, `.ll/workflow-analysis/…`).

The other **35 `.ll/` stale refs (26 unique paths) must keep reporting**, but
*not* because they are drift — investigated 2026-08-19, and essentially none of
them are. All 26 are confirmed never-tracked, never-deleted, never-on-disk via
`git log --diff-filter=A/D`. They fall into three classes:

| class | refs | what they are |
|---|---|---|
| **Proposed-but-unbuilt** | 19 | `.ll/rubrics/*.md` (14), `.ll/standards.md` (4), `.ll/commands/publish.md` (1) — cited by open issues that *propose creating them*: ENH-1053/1057/1067/1068/1069 (rubric externalization), ENH-2023 (whose title is literally "Extract loop-authoring standards into `.ll/standards.md`"), ENH-1034 |
| **Runtime-created by design** | 10 | `.ll/learning-tests/*` (5) — `_DEFAULT_BASE_DIR = Path(".ll") / "learning-tests"` (`scripts/little_loops/learning_tests/__init__.py:23`); plus `.ll/ll-ctx-stats.json`, `.ll/doctor-full-cache.json`, `.ll/loop-suggester-dismissals.json`, `.ll/ll-session-events.json`, `.ll/sprints/epic-1234.yaml` |
| **Documented-optional, user-authored** | 6 | `.ll/program.md` (4) — `docs/reference/program-md.md`: *"The file is **optional**. If absent, affected loops fall back to their existing defaults"*; `.ll/prompts/rn-plan-planning.md` (2), documented at `docs/guides/LOOPS_REFERENCE.md:3039` |

**This is why a bare `.ll/` prefix is wrong** — not because it would suppress
drift, but because it would suppress the 19 proposed-but-unbuilt refs, which are
real signal: they point at artifacts open issues have committed to building and
should stay visible until built. They are `planned_new` in substance; the
`_PLANNED_NEW_RE` marker misses them because they are cited in prose and tables
rather than with a `(new)` marker. **That is ENH-2971's problem, not this
issue's** — do not try to fix it here, and do not add these paths to the
suppression list to make the number go down.

### `git check-ignore` is an incomplete oracle

The 10 runtime-created refs above are the *same by-design class* as the 109 in
the shipped default — they are excluded only because nobody added them to
`.gitignore`. Mirroring `.gitignore` therefore inherits `.gitignore`'s gaps.

Do **not** widen the default to close this: leaving them reported is the safer
error, and a ref like `.ll/ll-session-events.json` is a near-miss typo for the
real `.ll/ll-session-events.jsonl` (`scripts/little_loops/init/writers.py:64`)
that `stale_file_ref` is correctly catching. Recorded here so a later reader
does not mistake the residual for an implementation shortfall.

Reproduce the ignored-vs-rest split with (note this classifies *ignore status*,
not drift — the rest of the split above required reading the citing issues):

```python
import subprocess
ignored = [r for r in ll_refs if subprocess.run(["git","check-ignore","-q",r]).returncode == 0]
```

### Corpus Measurement

Reproduce with (run from repo root, counts are unique `(issue, ref)` pairs —
`classify_issue_refs` dedupes per issue, matching what `format-check` reports):

```python
from pathlib import Path
from collections import Counter
from little_loops.text_utils import build_ref_index, classify_issue_refs

index = build_ref_index(Path("."))
PREFIXES = ("thoughts/", "postmortems/", ".loops/", "logs/", ".ll/")
by_prefix, overall = Counter(), Counter()
for p in sorted(Path(".issues").rglob("*.md")):
    for ref, status in classify_issue_refs(p.read_text(errors="replace"), index).items():
        overall[status] += 1
        if ref.startswith(PREFIXES):
            by_prefix[(ref.split("/")[0], status)] += 1
```

Baseline at 2026-08-19 — `overall`: `resolved` 26745, `unresolvable_form`
17600, `stale` 3231, `planned_new` 407, `ambiguous` 44. `by_prefix`:

| prefix | resolved | stale | unresolvable_form | planned_new |
|---|---|---|---|---|
| `thoughts/` | **52** | 99 | 5 | 2 |
| `.loops/` | **13** | 71 | 99 | 1 |
| `.ll/` | (many) | 144 (109 gitignored / 35 must keep reporting) | — | — |
| `postmortems/` | 0 | 9 | 0 | 0 |
| `logs/` | 0 | 7 | 0 | 0 |

The bolded 65 `resolved` entries are the regression risk this issue must not
trip; see Program Design § Check Ordering.

**These absolute numbers drift daily** — they moved between two runs three days
apart with no code change. Treat them as illustrative only; Implementation
Step 4 gates on same-tree *deltas*, never on a number copied out of this file.

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
- *Against*: needs maintenance, and the list is project-specific. It is
  config-driven (`issues.untracked_by_design`, with a shipped non-empty
  default) rather than hardcoded, since little-loops ships into other projects
  whose untracked-by-design directories differ.
- *Against (measured)*: a prefix list is coarser than `.gitignore`. These
  directories are only *partially* untracked here, so the prefixes must be
  enumerated at gitignore granularity and the check must run **after** index
  lookup — see Program Design § Check Ordering and § Prefix Granularity.
- *Implementation surface*: `build_ref_index` and `classify_file_ref` both
  change under this option too — the prefix list rides on `RefIndex` and is
  checked as a post-lookup fallback inside `classify_file_ref`, immediately
  before the terminal `stale` return (see Program Design).

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
- **Two wiring depths exist, and precedent does not settle which ENH-3000's new verdict needs**: `check_format_gaps()` only branches on verdicts it wants reported as drift — `resolved`/`planned_new`/`unresolvable_form` pass through with no `FormatGaps` field, no `has_gaps` change, no `to_dict()` change (`scripts/little_loops/issue_parser.py`, the `if ref_index is not None:` block at ~:1022-1040 — the `:766-774` cited here originally no longer matches). A verdict meant to be *reported* (e.g. `ambiguous_file_ref` for ENH-2999) instead gets 5 coordinated sites: new `FormatGaps` field, OR'd into `has_gaps`, added to `to_dict()`, a docstring "Gap classes:" bullet, and rendering in `_print_gaps()`/CLI help (`issue_parser.py:315-559`; `scripts/little_loops/cli/issues/format_check.py:61-199`). Whether `untracked_by_design` is a suppressing verdict (shallow) or a reported one (all 5 sites) is an open call the design doesn't currently pin down. _(Resolved by the 2026-08-19 research pass below: suppressing verdict, shallow treatment.)_
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
# Option B (selected): the prefix list rides on the index, resolved once per
# invocation rather than re-read per reference — mirroring how by_basename is
# already threaded through every classify_file_ref call.
@dataclass(frozen=True)
class RefIndex:
    by_basename: dict[str, list[str]]
    untracked_by_design: tuple[str, ...] = ()   # e.g. ("thoughts/", "postmortems/")

def build_ref_index(
    root: Path, *, untracked_by_design: tuple[str, ...] = DEFAULT_UNTRACKED_BY_DESIGN
) -> RefIndex: ...

# Option A: no signature change; classify_file_ref gains a stat() fallback after
# the index lookup misses, introducing filesystem I/O the module currently lacks.
```

### Check Ordering — post-lookup fallback, NOT a form check

**The verdict runs at step 5, replacing the terminal `stale` return — it must
not run as a form check at step 1.**

An earlier draft of this issue placed it with the glob/outside-repo form checks
on the reasoning that "a path under such a prefix is not a resolvable repo
reference regardless of index contents." **That premise is false**: `thoughts/`
holds 461 tracked files and `.loops/` holds 11 (see Summary), and 63 refs under
these prefixes resolve today. A pre-lookup form check would flip all 63
`resolved` → `untracked_by_design`, violating this issue's own Implementation
Step 3 ("no ref moving `resolved` → anything else") and stripping real coverage
evidence out of `research_triage`'s numerator for every issue citing a tracked
`thoughts/` plan.

Placing it at step 5 costs nothing that Option B was chosen for: the check is
still purely index-driven and involves no filesystem `stat()`, so the
determinism-across-machines argument in Decision Rationale holds unchanged. It
only fires where the answer would otherwise have been `stale`.

Revised resolution order for `classify_file_ref`:

1. Form checks (glob, placeholder, outside-repo, bare basename, extension-like
   component) → `unresolvable_form` — **unchanged**.
2. `planned_new` from line context — **unchanged**.
3. Exact tracked-path match → `resolved` — **unchanged**.
4. Unique suffix match → `resolved`; multi-match → `ambiguous` — **unchanged**.
5. **New**: ref starts with an `untracked_by_design` prefix →
   `untracked_by_design`.
6. Otherwise `stale`.

**Docstring steps 3 and 4 are one code block.** The numbered order above is the
*docstring's* numbering (`text_utils.py:272-299`); in the body, steps 3 and 4
are a single `candidates = suffix_match_candidates(ref, index)` call
(`text_utils.py:325-330`) — the exact-match step lives inside
`suffix_match_candidates` as `if ref in candidates: return [ref]`
(`text_utils.py:356-357`). The new branch is therefore one insertion: replace
the terminal `return "stale"` at `text_utils.py:330` with a prefix test falling
through to `stale`. Do not go looking for a separate exact-match step to insert
after.

### Behavior Parity

Every existing behavior of `classify_file_ref` and of the config surface, with
its disposition:

| Current behavior | Disposition |
|---|---|
| Form checks (glob, `<placeholder>`, `~`/`/`-led, bare basename, extension-like component) return `unresolvable_form` first | **Preserved** — the new verdict is added at step 5, ahead of nothing |
| `planned_new` line-marker detection at step 2 | **Preserved** — a `(new)`-marked `thoughts/` path stays `planned_new`, not `untracked_by_design` |
| Exact tracked-path match resolves | **Preserved** — this is what keeps the 51 tracked `thoughts/` and 12 tracked `.loops/` refs `resolved` |
| Unique suffix match resolves; multi-match returns `ambiguous` | **Preserved** — an untracked-by-design path that suffix-matches a tracked file still resolves/disambiguates first |
| Unmatched `/`-qualified path returns `stale` | **Changed** — now returns `untracked_by_design` *iff* the ref starts with a configured prefix; every other unmatched ref still returns `stale` |
| `RefStatus` is a closed 5-member `Literal` | **Changed** — gains a 6th member, `untracked_by_design` |
| `check_format_gaps` reports only `stale` and `ambiguous` as gaps | **Preserved** — the new verdict falls through the same silent-non-gap path as `resolved`/`planned_new`/`unresolvable_form`; no `FormatGaps` field, no `has_gaps`/`to_dict()` change |
| `qualified_ref_count` / `_triage_axis` denominator is `("resolved", "stale", "ambiguous")` | **Changed** — `untracked_by_design` is excluded, which raises coverage ratios for prefix-heavy issues (see § Denominator Side Effect); the three listed verdicts keep their existing membership |
| `build_ref_index(root)` callable with one positional arg | **Preserved** — the new parameter is keyword-only with a non-empty default, so the two-arg call sites and `test_symbol_cli_claim_sweep.py:34` keep working unchanged |
| `RefIndex(by_basename=...)` constructible with one field | **Preserved** — `untracked_by_design` is a defaulted field, so the inline `RefIndex(by_basename={...})` constructions throughout `test_text_utils.py` keep compiling |
| `IssuesConfig` fields round-trip through `from_dict()`/`to_dict()` | **Preserved** — the new field follows the same shape; no existing key changes |
| Project configs with no `issues.untracked_by_design` key | **Changed in effect** — they inherit the shipped non-empty default rather than opting in, which is the point (see § Shipped Default). No config file needs editing; none becomes invalid |

### Prefix Matching Semantics

Copy `_mirror_prefixes()` (`scripts/little_loops/text_utils.py:198-214`) — the
closest same-file precedent: a `tuple[str, ...]` matched with plain
`ref.startswith(prefixes)`.

**Entries may be directories *or* individual files.** `_mirror_prefixes()` is
directory-only, but the `.ll/` slice (109 of the 267 refs) is gitignored
per-file, and a bare `.ll/` prefix would swallow 35 refs that must keep
reporting — chiefly artifacts open issues have committed to building. Since
`startswith` is verbatim string matching, a full file path is already a valid
entry; the only thing that has to change is the trailing-slash rule.

- **Trailing slash is appended to *directory-shaped* entries only.** A config
  entry `thoughts` must be coerced to `thoughts/` at load, or it would match
  `thoughts-archive/` and `thoughtstream.py`. But `.ll/ll.local.md` must be left
  alone — slashing it would match nothing. Normalize in
  `IssuesConfig.from_dict()`, not at each match site:

  ```python
  def _normalize_untracked_prefix(entry: str) -> str | None:
      entry = entry.strip()
      if not entry or entry == "/":
          return None                      # see "Reject empty entries" below
      if entry.endswith("/"):
          return entry                     # explicit directory — always honored
      final = entry.rsplit("/", 1)[-1]
      return entry if "." in final[1:] else entry + "/"
  ```

  `final[1:]` rather than `final` so a dotfile like `.ll/.auto-manage-state.json`
  is recognized as a file (its only `.` at position 0 is the dotfile marker, not
  an extension). This is the same distinction
  `_EXTENSION_LIKE_COMPONENT_RE` (`text_utils.py:177`) makes with its `^[^.]`
  anchor, but that regex is *not* reusable here: it rejects dotfiles outright,
  which is exactly the case this list needs to accept. **Escape hatch**: a
  directory whose own name contains a dot (`.ll/decisions.d`) must be written
  with an explicit trailing `/` in config, since the heuristic would otherwise
  classify it as a file.

- **Reject empty and root entries.** `ref.startswith(("",))` is `True` for
  *every* ref, so a single empty string in the list silently reclassifies the
  entire `stale` corpus as `untracked_by_design` with no error. This is not
  hypothetical: `ll.local.md` merge semantics **replace arrays rather than
  append** (`.claude/CLAUDE.md` § Local Settings Override), so a project
  overriding this key writes the whole list by hand. Drop empty/whitespace-only
  entries and `"/"` during normalization, and cover it with a test.
- **No leading-`./` handling needed.** `classify_file_ref` step 1 already
  returns `unresolvable_form` for anything the extractor emits with a `.`-led or
  `/`-led form before step 5 is reached; refs arrive repo-relative.
- **No glob semantics.** These are literal string prefixes, deliberately not
  `file_matches_pattern()`'s gitignore globs — `startswith` keeps the check
  allocation-free on a path that runs once per unresolved ref across a ~30k-ref
  corpus. Consequence: the glob-shaped `.gitignore` entries under `.ll/`
  (`.ll/*.lock`, `.ll/user-messages-*.jsonl`, `.ll/export*.jsonl`,
  `.ll/stray-quarantine-*/`) are **not expressible** and are deliberately out of
  scope — none of them appears in the measured corpus.

### Why an over-broad entry is safe

Because the check runs at step 5, **after** index lookup, an over-broad prefix
can only ever hide genuine drift — it can never break a resolution. A ref to a
*tracked* file resolves at step 3/4 and never reaches the prefix test, whatever
the list says.

This is the property that makes the shipped default's little-loops-shaped
entries (`thoughts/`, `logs/`) acceptable in a consuming project that happens to
track those directories: worst case there, a few real stale refs go unreported;
no correct resolution is lost. It is also why file-level `.ll/` entries carry no
risk of colliding with tracked siblings like `.ll/ll-config.json`. § Shipped
Default's "it's a *default*, overridable" framing is the weaker version of this
argument — this is the actual guarantee.

### Prefix Granularity — mirror `.gitignore`, do not coarsen

Neither `.loops/` nor `.ll/` may appear as a bare prefix.

**`.loops/`** — `.gitignore:77-85` ignores only `.loops/.running/`,
`.loops/.history/`, `.loops/.queue/`, `.loops/tmp/`, `.loops/runs/`,
`.loops/diagnostics/`, `.loops/reviews/`, `.loops/generated/`, and
`.loops/cli-anything/` — the tracked files at `.loops/*.yaml` and under
`.loops/plans/`, `.loops/research/` are real, and a deleted loop YAML like
`.loops/rl-rlhf.yaml` **should** keep reporting `stale`. The shipped default
therefore enumerates the ignored subdirectories, not the parent.

**`.ll/`** — ignored per-*file* (`.gitignore:53-57, 100-116, 132`), not per
directory: `.ll/decisions.d/` and `.ll/ll-config.json` are tracked, and 35 of
the 144 `.ll/` stale refs point at never-tracked paths that must keep
reporting — chiefly 19 refs to artifacts open issues have *committed to
building* (`.ll/rubrics/…`, `.ll/standards.md`). See Motivation § The `.ll/`
Slice for the full three-class breakdown; those 35 are not drift, but
suppressing them would still destroy real signal.

The default therefore enumerates the 13 ignored state files individually plus
the one ignored subdirectory `.ll/workflow-analysis/`. Tempting shortcuts that
are wrong: `.ll/` (swallows all 35) and `.ll/ll-` (would suppress a ref to a
deleted-but-formerly-tracked `.ll/ll-config.json`, and violates the
directory-shaped normalization rule).

### Shipped Default

The list must ship non-empty or the change is a no-op until a user hand-edits
`.ll/ll-config.json` — which would leave Implementation Step 3's corpus
re-measurement unreachable. Mirror how `ScanConfig.exclude_patterns` already
ships a populated `field(default_factory=...)`:

```python
DEFAULT_UNTRACKED_BY_DESIGN: tuple[str, ...] = (
    # Wholly-ignored directories (.gitignore:21, 122, 127)
    "thoughts/",
    "postmortems/",
    "logs/",
    # .loops/ is ignored per-subdirectory, not wholesale (.gitignore:77-85)
    ".loops/.running/",
    ".loops/.history/",
    ".loops/.queue/",
    ".loops/tmp/",
    ".loops/runs/",
    ".loops/diagnostics/",
    ".loops/reviews/",
    ".loops/generated/",
    ".loops/cli-anything/",
    # .ll/ is ignored per-*file* (.gitignore:53, 100-116); .ll/decisions.d/ and
    # .ll/ll-config.json are tracked, and .ll/standards.md, .ll/program.md,
    # .ll/prompts/, .ll/rubrics/ must keep reporting -- they are artifacts open
    # issues propose to create, not drift. See Motivation § The .ll/ Slice.
    ".ll/.auto-manage-state.json",
    ".ll/context-pressure-state.json",
    ".ll/ll-auto-state.json",
    ".ll/ll-context-state.json",
    ".ll/ll-continue-prompt.md",
    ".ll/ll-doc-drift-state.json",
    ".ll/ll-edit-batch-state.json",
    ".ll/ll-precompact-state.json",
    ".ll/ll-session-state.json",
    ".ll/ll-sprint-state.json",
    ".ll/ll-state.json",
    ".ll/ll-sync-state.json",
    ".ll/ll.local.md",
    ".ll/workflow-analysis/",
)
```

This list is **normalization-idempotent** under the rule in § Prefix Matching
Semantics — every entry either already ends in `/` or is file-shaped, so
`from_dict()` passes it through unchanged. Assert that in a test; it is the
cheapest guard against someone later adding a bare `.ll/decisions.d` and having
it silently coerced to a non-matching form.

Declare the same list as the `default` in `config-schema.json` and as the
dataclass `field(default_factory=...)`; an absent config key falls through
`data.get(key, DEFAULT)` to the dataclass default, so a project that never
opts in still gets the fix.

Note this default is little-loops-shaped (`thoughts/`, `postmortems/`, and the
whole `.ll/` block are this repo's conventions). That is acceptable on two
counts: it is a *default*, overridable per project; and per § Why an Over-Broad
Entry Is Safe, a prefix that does not apply to a consuming project can only
under-report drift there, never break a resolution.

### Config Placement — `issues.`, not `scan.`

Put the key at `issues.untracked_by_design`, not `scan.untracked_by_design`.

- **Consumer proximity**: all three production `build_ref_index()` call sites
  are issues-domain (`cli/issues/format_check.py:563`,
  `issues/research_triage.py:212`, `:317`). `scan.*` governs codebase scanning
  for `/ll:scan-codebase`, a different subsystem; `scan.focus_dirs` and
  `scan.exclude_patterns` have effectively no runtime readers outside
  `codequery/codegraph.py:_is_scan_relevant()`.
- **Semantics**: this classifies references *found inside issue prose*. It is
  not a scan-relevance filter.
- **Parity guard is a wash, not an argument either way.**
  `_SCHEMA_PARITY_EXCLUDED_SECTIONS` (`scripts/tests/test_config_schema.py:1191`)
  excludes `{"$schema", "project", "issues", "scan"}` — **both** candidate
  sections. Whichever lands, the schema-vs-code value-parity walk will not
  cover this key, so `TestDataclassSectionMapCompleteness` /
  `TestToDictSchemaParity` registration plus an explicit
  `test_config.py` round-trip test carry the whole burden. Do not assume the
  guard catches a schema-default/dataclass-default divergence here.

### Call Path

`build_ref_index` (gains the prefix list, sourced from config) →
`classify_file_ref` (new branch) → both consumers:

- `check_format_gaps` → `main_format_check`
- `qualified_ref_count` — same denominator question ENH-2999 raises; answer both
  the same way

### Config Threading — inject at the CLI boundary, do not import config into `research_triage`

**Correction (2026-08-19 pre-implementation review)**: the Wiring Phase below
originally said to "thread the config-sourced prefix list through
`research_triage.py:212` and `:317`". Taken literally that is wrong — verified:
`scripts/little_loops/issues/research_triage.py` imports **no config at all**
(no `BRConfig`, no `load_config`, no `project_root` concept beyond a `root:
Path` argument). Both of its `build_ref_index()` calls are *fallbacks* inside
`if index is None:` branches; both public entry points already accept an
`index: RefIndex | None` parameter (`qualified_ref_count`
`research_triage.py:191-195`, `triage_research_axes` `:279-283`).

The correct wiring is therefore **zero new plumbing in the core module**:

- `scripts/little_loops/cli/issues/research_triage.py:61` — the sole production
  caller — currently calls `triage_research_axes(path, config.project_root)`
  and lets the core build the index. Change it to build the index itself and
  pass it in:
  ```python
  index = build_ref_index(
      config.project_root, untracked_by_design=config.issues.untracked_by_design
  )
  coverages = triage_research_axes(path, config.project_root, index=index)
  ```
- `cli/issues/format_check.py:563` — already has `config` in scope; pass the
  keyword directly.
- The two in-module `build_ref_index()` fallbacks stay as they are and pick up
  `DEFAULT_UNTRACKED_BY_DESIGN` via the keyword default. That is the intended
  behavior for library callers with no config.

This drops `research_triage.py` from the "thread config through" list entirely;
it still appears in Files to Modify for the two denominator tuples, which is a
separate change.

**Pre-existing defect, explicitly out of scope**: `qualified_ref_count`'s
fallback does `root = issue_path.parent` (`research_triage.py:211`), so
`build_ref_index` runs `git ls-files` with `cwd=.issues/enhancements/` and
yields an index containing only issue files. That path is already near-useless
and is only reached when a caller omits `index=`; do **not** try to fix it here.
Note it so the implementer does not mistake it for wiring this issue introduced.

### Denominator Side Effect — intended, and worth stating

Excluding `untracked_by_design` from the eligible tuples in
`qualified_ref_count()` (`research_triage.py:215`) and `_triage_axis()`
(`research_triage.py:410`) **raises** coverage ratios: today those refs sit in
the denominator as `stale` and drag the ratio down, so removing them makes the
`COVERAGE_THRESHOLD` (≥80%) gate easier to clear for issues that cite many
untracked `thoughts/`/`.loops/` paths. That is the correct outcome — a ref with
no git-tracked target to compare against is not evidence either way, so it
should not count as a miss — but it means `/ll:refine-issue` will skip some
axes it currently re-researches. Expect a small drop in axis re-research volume
after this lands; that is the change working, not a regression.

Because the check now runs at step 5 (post-lookup), the 63 currently-`resolved`
refs stay `resolved` and stay in both the numerator and the denominator —
unchanged.

The design decision is closed (Option B, recorded in Decision Rationale above);
`decision_needed` is `false`. No `/ll:decide-issue` run is required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-19 — based on codebase analysis:_

- **Verdict wiring depth resolved**: `check_format_gaps()` (`scripts/little_loops/issue_parser.py`, defined at :638; the ref-classification loop is the `if ref_index is not None:` block at ~:1022-1040) only branches on `stale` and `ambiguous` today; `resolved`, `unresolvable_form`, and `planned_new` pass through the loop with no `FormatGaps` field, no `has_gaps` change, no `to_dict()` entry — they are silently non-gaps. Since `untracked_by_design` is a suppressing verdict (its purpose is to stop being reported as `stale`, not to be reported under a new category), it needs only the shallow treatment: a new `RefStatus` Literal member plus the step-5 fallback branch in `classify_file_ref` (this bullet originally said "form check"; superseded by Program Design § Check Ordering). It does not need the 5-site `FormatGaps`/`has_gaps`/`to_dict`/docstring/`_print_gaps()` treatment that `ambiguous_file_ref` (ENH-2999) required — that treatment is only for verdicts meant to be *surfaced* as a gap category.
- **Denominator eligibility resolved**: `qualified_ref_count()` (`research_triage.py:215`) and `_triage_axis()` (`research_triage.py:410`) both gate on the literal tuple `("resolved", "stale", "ambiguous")` — duplicated independently at each site, no shared constant. Per `qualified_ref_count`'s own docstring, eligibility means "survived the form filter"; only `unresolvable_form` and `planned_new` are excluded, both decided at the form-check stage before index lookup. `untracked_by_design` only fires where there is no git-tracked target at all — it replaces a would-be `stale`, so nothing exists to compare against for the staleness check (`research_triage.py:431-442`). It therefore belongs in the same excluded category as `unresolvable_form`/`planned_new`, not added to the eligible tuple. (This bullet originally justified the exclusion by "it is a form check that runs before index lookup" — that framing is superseded by Program Design § Check Ordering; the exclusion conclusion is unchanged, and its denominator consequence is spelled out in § Denominator Side Effect.) Both call sites' literal tuples need updating independently (or reconciled with ENH-2990's `AxisCoverage` reason-code work per this issue's own trailing Scope Boundary note).
- **No shared prefix-matching helper exists** — three independent, shape-incompatible mechanisms already do adjacent things: (1) `_EXCLUDED_DIRS` (`verify_private_refs.py:75-90`) — hardcoded `frozenset` of bare directory *names*, matched via `any(part in _EXCLUDED_DIRS for part in rel_path.parts)`; (2) `file_matches_pattern()` (`git_operations.py:296+`) — full gitignore-glob semantics, the natural pairing for `scan.exclude_patterns` but currently has zero production callers for that config key (grep for `.scan.exclude_patterns` / `.scan.focus_dirs` returns nothing anywhere in `scripts/little_loops/`); (3) `_mirror_prefixes()` (`text_utils.py:198-214`) — a `@cache`d `tuple[str, ...]` of directory-prefix strings matched via plain `str.startswith(tuple)`, already used inside `classify_file_ref`'s own call chain (`suffix_match_candidates`, `text_utils.py:364`), though sourced from the host-capability registry rather than project config. This last one is the closest same-file precedent for "a cached tuple of directory prefixes consulted inside `text_utils.py`'s own classification logic."
- **Config-location caveat**: `scan` is explicitly excluded from the schema-vs-code value parity walk — `_SCHEMA_PARITY_EXCLUDED_SECTIONS = {"$schema", "project", "issues", "scan"}` (`test_config_schema.py:1191`). A new key added under `scan` therefore would not get the cross-check other config sections get for free; the schema-vs-default drift that guard exists to catch would go undetected there specifically.
- ~~**The stale "Resolve the option..." sentence at the end of this section predates the decision recorded above in Decision Rationale**~~ — **fixed 2026-08-19**: the sentence was removed and replaced with an explicit "decision is closed" note.

## Integration Map

### Files to Modify

- `scripts/little_loops/text_utils.py` — `classify_file_ref` (new step-5
  fallback, ahead of the terminal `stale`), `build_ref_index` /`RefIndex`
  (carry the prefix tuple), plus the `DEFAULT_UNTRACKED_BY_DESIGN` constant and
  the new `RefStatus` Literal member
- `scripts/little_loops/config-schema.json` — declare
  `issues.untracked_by_design` (array of strings) with the shipped default
- `scripts/little_loops/config/features.py` — `IssuesConfig` (lines 204-219)
  gains the field + `from_dict()` entry, including the trailing-slash
  normalization described in Program Design § Prefix Matching Semantics
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()`'s hardcoded
  `"issues"` block (lines 737-748) enumerates keys by name; the new field is
  invisible outside `IssuesConfig` until a line is added there
- `scripts/little_loops/issues/research_triage.py` — denominator membership for
  the new verdict, same question as ENH-2999 raises. **Denominator tuples only**
  — no config import (§ Config Threading)
- `scripts/little_loops/cli/issues/research_triage.py` — line 61 builds and
  injects the config-sourced index via the existing `index=` parameter

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` line
  563 calls `build_ref_index(config.project_root)` with no config-sourced arg;
  confirmed via `ll-code callers-of build_ref_index` this is the third
  production call site (alongside `research_triage.py:212,317`) and is not
  currently in this list — without threading the new prefix list through here
  the verdict never reaches production `format-check` output
- _(superseded — the `ScanConfig`/`scan` plumbing this pass originally listed
  moved to `IssuesConfig`/`issues` per Program Design § Config Placement; see
  Files to Modify above, which now carries `config/features.py` and
  `config/core.py` directly. Note `config-schema.json`'s
  `additionalProperties: false` applies to `issues` as well, so the key must
  be pre-declared there either way.)_

### Dependent Files

- `scripts/tests/test_text_utils.py`
- `scripts/tests/test_ll_issues_format_check.py`

_Wiring pass added by `/ll:wire-issue`:_
- ~~`scripts/little_loops/issues/research_triage.py:212` and `:317` — both need
  the config-sourced prefix list threaded in~~ — **superseded**: both are
  `if index is None:` fallbacks, not the production path. The production path
  is `cli/issues/research_triage.py:61` → `triage_research_axes(..., index=)`.
  See Program Design § Config Threading
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
- `docs/reference/CONFIGURATION.md` — the full-config example's `"issues"`
  section should show `untracked_by_design` with its shipped default

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — `IssuesConfig` cases: `from_dict()` default
  (absent key yields the shipped non-empty tuple), explicit-override
  round-trip, and the normalization rule from § Prefix Matching Semantics:
  - `"thoughts"` → `"thoughts/"` (directory-shaped gets slashed)
  - `".ll/ll.local.md"` → unchanged (file-shaped does not)
  - `".ll/.auto-manage-state.json"` → unchanged (dotfile is file-shaped — the
    `final[1:]` case; a naive `"." in final` or a reuse of
    `_EXTENSION_LIKE_COMPONENT_RE` gets this wrong)
  - `".ll/decisions.d/"` → unchanged (explicit trailing slash always honored,
    the documented escape hatch for dotted directory names)
  - **`DEFAULT_UNTRACKED_BY_DESIGN` is normalization-idempotent** — normalizing
    the shipped default returns it unchanged, element for element
- **Empty-entry guard** — `from_dict()` with `[""]`, `["  "]`, and `["/"]` drops
  those entries. Pair it with a `classify_file_ref` assertion that an ordinary
  drift ref still returns `stale` under such a config: `ref.startswith(("",))`
  is `True` for every ref, so the un-guarded failure mode is silent
  whole-corpus suppression, and a config-layer-only test would not prove the
  classifier is safe
- Since `issues` is inside `_SCHEMA_PARITY_EXCLUDED_SECTIONS`, add an explicit
  assertion that the `config-schema.json` `default` array equals
  `DEFAULT_UNTRACKED_BY_DESIGN` — the parity walk will not catch that drift
- **Regression guard for the 63 resolved refs** — a test asserting a ref to a
  *tracked* file under an untracked-by-design prefix still returns `resolved`
  (e.g. `thoughts/FEAT-670-layout-engine-research.md`, `.loops/rl-rlhf.yaml`).
  This is the negative control for the step-5-not-step-1 ordering and is the
  single most important test in this issue; mirror the
  `test_does_not_exist_marker_stays_stale` negative-control pattern
  (`test_text_utils.py:295-315`)
- **Granularity guards** — two, one per family, pinning that the default
  enumerates precisely rather than reaching for the parent:
  - a ref to a deleted `.loops/*.yaml` at the top level still returns `stale`
    (not `untracked_by_design`), pinning the ignored-subdirectory enumeration
    over a bare `.loops/`
  - a ref to `.ll/rubrics/confidence-check.md` still returns `stale`, pinning
    the per-file enumeration over a bare `.ll/`. This is the guard for the 35
    must-keep-reporting `.ll/` refs; without it a later "simplification" to
    `.ll/` would look like a 35-finding improvement while hiding 19 refs to
    artifacts open issues have committed to building. Use a `.ll/rubrics/`
    path rather than `.ll/standards.md` — the latter is what ENH-2023 exists to
    create, so the test would start failing the day that issue lands
- **`.ll/` file-entry coverage** — a ref to `.ll/ll-context-state.json` (the
  single highest-count entry at 28 refs) returns `untracked_by_design`, proving
  a full file path works as a `startswith` entry and that normalization left it
  unslashed
- `scripts/tests/test_research_triage.py::TestReferenceFiltering` (~lines
  227-287) — new test mirroring
  `test_ambiguous_ref_is_denominator_eligible_but_not_covering` (lines
  262-287), asserting `qualified_ref_count(...) == 0` for an issue whose only
  ref is under an untracked-by-design prefix
- `scripts/tests/test_text_utils.py::TestClassifyFileRef` (lines 210-315) —
  new parametrized sweep, one case per entry in `DEFAULT_UNTRACKED_BY_DESIGN`
  (directory *and* file entries), each asserting
  `classify_file_ref(...) == "untracked_by_design"`. Parametrizing off the
  constant itself keeps the sweep honest when the list grows
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
- **Placement resolved (2026-08-19)**: the key lands at `issues.untracked_by_design`, not under `scan` — see Program Design § Config Placement. The two bullets above should be read with that substitution: the config-plumbing path is the same shape but runs through `IssuesConfig` (`config/features.py:204-219`) and `BRConfig.to_dict()`'s `"issues"` block (`config/core.py:737-748`). Critically, `_SCHEMA_PARITY_EXCLUDED_SECTIONS` excludes **both** `"issues"` and `"scan"`, so the parity-guard gap noted above applies identically to the chosen placement and must be covered by an explicit test.

## Implementation Steps

1. ~~The design decision above is made and recorded~~ — **done** (Option B,
   2026-08-16; `decision_needed: false`).
2. The mechanism lands as a **post-lookup step-5 fallback** with the verdict
   propagated to all three production `build_ref_index()` call sites.
3. The config key ships with a **non-empty default** so the fix is live without
   any project opting in.
4. Corpus re-measurement (script in Motivation § Corpus Measurement).

   **Run the script on the pre-change tree first and diff against the
   post-change run — do not compare against a number written in this file.**
   The corpus moves daily as issues are edited and files are tracked: the
   baseline recorded on 2026-08-16 (`resolved` 26728, `unresolvable_form`
   17577, 63 in-prefix resolved) had already drifted to `resolved` 26733,
   `unresolvable_form` 17585, 65 in-prefix resolved when re-run three days
   later, with no code change in between. An absolute assertion here would fail
   spuriously.

   Gates, expressed as deltas on one tree:
   - **`stale` drops by ~267**, simulated against the exact
     `DEFAULT_UNTRACKED_BY_DESIGN` list above on 2026-08-19: `thoughts/` 99,
     `.ll/` 109, `.loops/` 43, `postmortems/` 9, `logs/` 7.
   - **`untracked_by_design` rises by the same ~267**, and every other verdict's
     delta is 0 — i.e. the change is a pure `stale` → `untracked_by_design`
     reclassification with no collateral movement. Verified by simulation.
   - **`resolved` delta is exactly 0** — the in-prefix tracked refs must not
     move. This is the hard gate.
   - `unresolvable_form`, `planned_new`, and `ambiguous` deltas are 0.

   **Expected residuals — these are the granularity guards working, not
   shortfalls.** Do not "fix" them by broadening a prefix:
   - **28 `.loops/` refs across 12 unique paths stay `stale`** — deleted
     top-level loop YAMLs (`.loops/general-task.yaml`,
     `.loops/issue-refinement-git.yaml`) plus never-tracked `.loops/audits/`
     and `.loops/lib/`, all confirmed *not* gitignored via `git check-ignore`.
   - **35 `.ll/` refs across 26 unique paths stay `stale`** — 19 proposed-but-
     unbuilt (`.ll/rubrics/…`, `.ll/standards.md`), 10 runtime-created but
     missing from `.gitignore`, 6 documented-optional user-authored. None are
     drift, but all must keep reporting; see Motivation § The `.ll/` Slice.
5. `python -m pytest scripts/tests/` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Thread the config-sourced prefix list through `research_triage.py:212`,
  `research_triage.py:317`, and `format_check.py:553`~~ — **superseded, see
  Program Design § Config Threading.** `research_triage.py` has no config
  access and needs none: inject the index from
  `cli/issues/research_triage.py:61` via the existing `index=` parameter, and
  pass the keyword directly at `format_check.py:553`. The two in-module
  fallbacks keep the default
- Add the new `IssuesConfig` field (`config/features.py:204-219`) plus its
  `from_dict()` update and trailing-slash normalization, and add the matching
  key to `BRConfig.to_dict()`'s hardcoded `"issues"` block
  (`config/core.py:737-748`), since neither happens automatically from a
  `config-schema.json` entry alone
- Update both independent denominator tuples in `research_triage.py`
  (`qualified_ref_count()` line 215, `_triage_axis()` line 410) to exclude
  `untracked_by_design` — no shared constant exists between them today, so
  each literal tuple needs editing separately
- Update `classify_file_ref`'s "Resolution order" docstring
  (`text_utils.py:272-299`) to add the new **step-5 fallback** (not a form
  check) and its `**Returns:**` list; the ordering described there is
  explicitly non-commutative and authoritative, not just descriptive — state
  in the docstring *why* it sits after lookup (tracked files exist under these
  prefixes), so a later reader does not "tidy" it up next to the other
  early-return checks and silently regress the 63 resolutions
- Update `docs/reference/API.md`, `docs/reference/CLI.md`, and
  `docs/reference/CONFIGURATION.md` per the Documentation subsection above
- Confirm `scripts/tests/test_symbol_cli_claim_sweep.py`'s corpus-pinned
  `build_ref_index()` call stays inert under the new verdict — it only
  asserts on `stale_symbol_ref`/`mislocated_symbol_ref`/`stale_cli_flag`, not
  `stale_file_ref`

## Impact

- **Effort**: Small — one branch in `classify_file_ref`, one config field, and
  the plumbing through three call sites. The design is now settled.
- **Risk**: Low under Option B **as ordered here**. Two hazards, both with a
  dedicated gate:
  1. *Ordering* — placing the check before index lookup silently regresses 65
     currently-`resolved` refs. Caught by the `resolved`-delta-is-0 corpus gate
     (Step 4) and the negative-control test in Tests.
  2. *An empty config entry* — `startswith("")` matches everything, silently
     suppressing the whole `stale` corpus. Caught by the empty-entry guard in
     Tests. This is the only way the change can fail loudly-wrong rather than
     quietly-incomplete.

  Option A's risk (working-tree-dependent verdicts leaking into
  `research_triage`'s gate) does not apply. Note that over-broad *non-empty*
  entries are structurally safe — see § Why an Over-Broad Entry Is Safe.
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
| `.gitignore` | lines 21, 53-57, 77-85, 100-116, 122, 127, 132 — the authoritative granularity the default prefix list must mirror; `.loops/` is ignored only per-subdirectory and `.ll/` only per-file |

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-2966 both modify `check_format_gaps` in `scripts/little_loops/issue_parser.py` for unrelated gap classes (a new `stale_file_ref` verdict branch vs. the testable-keyword scan surface). Coordinate implementation order to avoid a merge collision in the same function.

## Session Log
- `/ll:confidence-check` - 2026-08-19T22:36:34 - `783bfe67-e43b-4aa3-9685-9db5e496d2c0.jsonl`
- `/ll:confidence-check` - 2026-08-19T22:18:20 - `0e6d0c6a-b043-41cd-9b71-7ebe3558528f.jsonl`
- pre-implementation review (correction) - 2026-08-19 - investigated the
  residual `.ll/` refs the entry below had labelled "genuine drift". That label
  was **wrong**: all 26 unique paths are never-tracked/never-deleted per
  `git log --diff-filter=A/D`, and split into 19 proposed-but-unbuilt (cited by
  ENH-1053/1057/1067/1068/1069/2023/1034, which propose *creating* them), 10
  runtime-created-by-design but absent from `.gitignore`, and 6
  documented-optional user-authored (`.ll/program.md` has its own reference
  doc). The "no bare `.ll/` prefix" conclusion is unchanged but re-justified:
  suppression would hide committed-to-build artifacts, not drift. Also recorded
  that `git check-ignore` is an incomplete oracle for this class, and changed
  the granularity-guard test fixture from `.ll/standards.md` to
  `.ll/rubrics/confidence-check.md` — the former is exactly what ENH-2023 will
  create, which would have made the test fail the day that issue landed.
- pre-implementation review - 2026-08-19 - found the `.ll/` slice (109 refs /
  14 paths of the same gitignored-by-design class, vs. 35 `.ll/`
  refs that must keep reporting) and extended the shipped default with
  file-level entries, raising the suppressed total 158 → 267; relaxed the
  "trailing slash always required" normalization rule to directory-shaped
  entries only (with a `final[1:]` dotfile carve-out and an explicit-slash
  escape hatch for dotted directory names); added an empty-entry guard
  (`startswith("")` matches every ref, and `ll.local.md` array-replace
  semantics make a hand-written list likely); stated the post-lookup safety
  property explicitly; corrected `format_check.py:553` → `:563` and the stale
  `issue_parser.py:766-774` citation. Delta re-simulated on the live tree:
  `stale` −267, `untracked_by_design` +267, every other verdict 0.
- `/ll:confidence-check` - 2026-08-19T21:28:41 - `52d05086-bbdc-462a-bb68-03d6d46c8ec9.jsonl`
- pre-implementation review - 2026-08-19 - corrected the config-threading
  instruction (`research_triage.py` has no config access; inject via the
  existing `index=` param from the CLI layer), replaced the absolute
  `resolved == 26728` corpus gate with a same-tree delta gate after confirming
  the baseline drifted in 3 days with no code change, pinned the simulated
  `stale` drop at 158 with the 26-ref `.loops/` residual explained, and noted
  that docstring steps 3-4 are a single code block
- `/ll:confidence-check` - 2026-08-19T21:11:29 - `dec92251-b998-49e4-be5e-639ddba20e86.jsonl`
- pre-implementation review - 2026-08-19 - corrected check ordering to a
  post-lookup fallback (63 tracked refs would have regressed), re-measured the
  corpus (315→184, 9%→5.7%, not the largest class), added a shipped non-empty
  default, moved the config key from `scan.` to `issues.`, and removed the
  stale `/ll:decide-issue` directive
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
