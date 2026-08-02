---
id: ENH-2983
title: Stale file path references in issue bodies are undetected
type: ENH
priority: P2
status: done
captured_at: '2026-08-01T00:00:00Z'
completed_at: '2026-08-02T03:10:07Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2971
labels:
- issues
- format-check
- data-quality
testable: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2983: Stale file path references in issue bodies are undetected

## Summary

Nothing in the toolchain checks whether the file paths an issue cites still
exist. `ll-issues anchor-sweep` only handles `file:NNN` references — the form
that is ~0% of the corpus — and none of `format-check`'s eleven gap classes
covers file-path drift. Measured on active issues: **41 of 63 (65%) contain at
least one stale file reference.**

Add a robust path-resolution primitive over issue prose, and a
`stale_file_ref` gap class in `format-check` built on it.

## Current Behavior

Three separate facts, each verified:

- `ll-issues anchor-sweep` resolves only `_FILE_LINE` matches
  (`scripts/little_loops/issues/anchor_sweep.py`), which require a `:NNN`
  suffix. Across all 2,886 issue files only 6 carry such a reference in Root
  Cause/Current Behavior and 15 in Proposed Solution — the form is effectively
  extinct, because `/ll:ready-issue`'s checklist tells authors to remove it and
  `anchor-sweep` itself rewrites it to anchor prose.
- `format-check`'s gap classes are `missing`, `renamed`, `empty`,
  `boilerplate`, `malformed_id`, `prose_dep_drift`, `stale_prose_dep`,
  `program_design_nonspecific`, `deprecated_key`, `multi_frontmatter`,
  `testable`. `prose_dep_drift`/`stale_prose_dep` concern *issue* dependency
  references, not file paths.
- No `Path.exists()` check over issue prose exists anywhere under
  `scripts/little_loops/issues/` or `scripts/little_loops/cli/issues/`.

So an Integration Map written by `/ll:refine-issue` rots silently, and an
implementer acts on it.

## Expected Behavior

A shared primitive resolves a file reference extracted from issue prose to one
of: `resolved`, `stale`, `unresolvable-form`, or `planned-new`. `format-check`
reports `stale_file_ref` for the `stale` class, and other consumers
(`/ll:refine-issue` triage, `ready-issue`) call the same primitive rather than
each hand-rolling `extract_file_paths()` + `Path.exists()`.

## Motivation

**Measured scope (2026-08-01).** Active issues only (63): **41 (65%) contain
≥1 stale qualified file reference**, 125 stale references across 99 distinct
paths. Corpus-wide the drift is heavier — `scripts/little_loops/session_store.py`
is cited 78 times and no longer exists (it became a package directory);
`scripts/little_loops/fsm/validation.py` 124 times;
`scripts/tests/test_session_store.py` 90 times.

This is the substrate other tooling stands on. It surfaced while reviewing
ENH-2971, whose triage predicate must decide whether an issue's references
still resolve — it cannot do that correctly without this primitive, and would
otherwise ship a third private copy of the extraction-and-filter logic.

## Proposed Solution

A single resolution function that classifies each extracted reference. The
work is almost entirely in the classification, because a naive
`Path(p).exists()` is wrong in three distinct ways — all measured against the
real corpus:

| Class | Example (with corpus count) | Naive verdict | Correct verdict |
|---|---|---|---|
| unrooted partial path | `fsm/executor.py`, `cli/loop/_helpers.py` | stale | **resolved** — real files cited without the `scripts/little_loops/` prefix |
| bare basename | `config-schema.json` (247), `SKILL.md` (90), `__init__.py` (69) | stale | **unresolvable-form** — a prose mention, not a location |
| glob pattern | `skills/*/SKILL.md` (46) | stale | **unresolvable-form** |
| template placeholder | `~/.codex/skills/<name>/SKILL.md` | stale | **unresolvable-form** |
| planned-new file | a path under `### Files to Modify` marked `(new)` | stale | **planned-new** — correct to not exist yet |
| genuine drift | `scripts/little_loops/session_store.py` (78) | stale | **stale** — the signal |

Suggested shape:

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new"]

def classify_file_ref(ref: str, root: Path, *, context: str = "") -> RefStatus:
    """Classify one path reference extracted from issue prose."""
```

Resolution order for a `/`-containing, non-glob reference: try `root / ref`;
if absent, suffix-match against tracked files (`git ls-files`) for a unique
path ending in `/ref`; if exactly one match, `resolved`; if none, `stale`.

Then `format-check` gains a `stale_file_ref` gap class listing the `stale`
references per issue. Reporting only — auto-fix is out of scope (a moved file
cannot be re-pointed safely without knowing intent).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research:_

### Files to Modify

- `scripts/little_loops/text_utils.py` — home of `extract_file_paths()`, the
  existing extractor this issue's classifier consumes.
- `scripts/little_loops/issue_parser.py` — `FormatGaps` dataclass and
  `check_format_gaps()`, where the new `stale_file_ref` field and detection
  block land.
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()`
  and `_print_gaps()`, where the new gap class is wired into CLI output and
  the `--format json` path.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/issues/anchor_sweep.py` (`_sweep_file()`) and
  `scripts/little_loops/issues/anchors.py` (`resolve_anchor()`) — the
  adjacent `file:NNN` resolution path this issue's classifier does not
  replace or share code with (see Proposed Solution → Codebase Research
  Findings).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` (`cmd_format_check()`) —
  if `check_format_gaps()` grows a `ref_index`/`RefIndex` parameter (mirroring
  the existing `issue_statuses` parameter, per Conventions in Force), **all
  four** of `cmd_format_check()`'s call sites need the new argument threaded
  through, not just one: lines 236-240, 247-251, 274-278, 285-289 (single-ID
  path, `--all` path, and the post-`--fix` re-checks). `build_ref_index()`
  itself must be called exactly once per invocation here, ahead of any of
  these four call sites — this is also the "at most once" AC's natural home.
- `scripts/little_loops/dependency_mapper/analysis.py` (`find_file_overlaps()`,
  line ~297) and `scripts/little_loops/issue_history/parsing.py`
  (`_extract_paths_from_issue()`, line 484) both call the same
  `extract_file_paths()` this issue's classifier consumes, for unrelated
  purposes (issue-overlap detection, path listing) — confirmed via codebase
  trace they do **not** independently reimplement stale-path classification
  and need no change for this issue. Recorded here only to close out the
  issue's own "each hand-rolling `extract_file_paths()` + `Path.exists()`"
  claim: no third private copy of that anti-pattern was found anywhere under
  `scripts/little_loops/`.

### Conventions in Force

- Adding a `format-check` gap class touches exactly four places, in this
  order, for every existing class (`prose_dep_drift`/`stale_prose_dep`,
  `multi_frontmatter`, `deprecated_key`, `program_design_nonspecific`,
  `testable`): (1) a `list[str]` field on `FormatGaps`
  (`issue_parser.py:232-249`); (2) the same field added to both `has_gaps`
  (`issue_parser.py:252-266`) and `to_dict()` (`issue_parser.py:268-282`);
  (3) detection logic inline in `check_format_gaps()`
  (`issue_parser.py:308-500`); (4) a matching `for entry in gaps.<field>`
  loop in `_print_gaps()` (`format_check.py:131-153`) plus the class name
  added to the `--help` string (`format_check.py:61-64`). Skipping step 4 is
  a live, named regression — `cmd_format_check()`'s own docstring
  (`format_check.py:163-165`) calls out that a class counted by `has_gaps`
  but not rendered exits 1 with an empty report (the `testable` regression,
  ENH-2946). This is the strongest evidence the "3. Add the `stale_file_ref`
  gap class" implementation step must hit all four, not just the `FormatGaps`
  field.
- `prose_dep_drift`/`stale_prose_dep` (`issue_parser.py:462-487`) is the
  closest existing analog to this issue's `stale`/`resolved`/etc. split: both
  need a corpus- or repo-wide index built once and threaded into
  `check_format_gaps()` as a parameter (mirroring `issue_statuses: dict[str,
  str] | None`), and both distinguish two+ outcomes from one raw extraction
  pass rather than a single boolean.
- `check_format_gaps()` fails open throughout — unreadable file, undetermined
  type, unloadable template all return an empty `FormatGaps()` early, and the
  prose-dependency block is skipped entirely when its index argument is
  `None`. A new `stale_file_ref` check should follow the same
  never-block-format-check-without-an-index convention rather than raising.

### Tests

- `scripts/tests/test_text_utils.py` — existing coverage for
  `extract_file_paths()`.
- `scripts/tests/test_ll_issues_format_check.py` — one dedicated
  `class Test<GapName>` per gap class (e.g. the `prose_dep_drift`/
  `stale_prose_dep` class at line 437), using a shared `_write_issue()` /
  `_invoke()` helper pair (lines 64, 70-75) and asserting both printed text
  and `--format json` dict shape (lines 331-332, 465) — the fixture pattern
  for the new `stale_file_ref` tests.
- `scripts/tests/test_issues_anchors.py` — `TestResolveAnchorFallback`
  (lines 110-126) is the closest existing precedent for the ordering
  assertion this issue's AC demands (bare `SKILL.md` must not
  suffix-match): one grouped test class per outcome family, each writing a
  real fixture via `tmp_path`.
- Subprocess call-count assertion idiom for the "index built at most once"
  AC: `mock_run.call_count == N` against a patched `subprocess.run` —
  established at `test_sync.py:883/1415/1631/1655`,
  `test_work_verification.py:326/397/496/507`,
  `test_session_store_lifecycle.py:1180/1194/1207/1237`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_text_utils.py` — verified this file has **no existing
  tests for `extract_file_paths()` at all** (only `TestExtractWords`,
  `TestCalculateWordOverlap`, `TestScoreBM25`). The extractor's actual
  coverage lives in `scripts/tests/test_dependency_mapper.py`
  (`class TestExtractFilePaths`, lines ~70-130), which imports it via the
  `little_loops.dependency_mapper` re-export — confirmed same underlying
  function (`text_utils.py:54` is the only definition). This issue's
  `classify_file_ref()`/`build_ref_index()`/`classify_issue_refs()` tests
  have no existing class to extend in `test_text_utils.py` — they will be a
  wholly new test class there, not an addition to an existing one.
  `test_dependency_mapper.py` itself needs no new coverage for this issue.
- `scripts/tests/test_ll_issues_format_check.py:1047-1069`
  (`test_every_format_gaps_field_is_rendered`) is a reflection-based test
  that introspects `dataclasses.fields(FormatGaps)` and asserts every field
  renders in `_print_gaps()` output — it will **automatically cover** the
  new `stale_file_ref` field once added (no test edit needed), and is the
  regression guard the `testable`-class incident (ENH-2946) should have had.
- No existing test in `scripts/tests/` mocks a `git ls-files` subprocess call
  beyond the three files already cited above — `test_codequery_fallback.py`
  (which also shells to git) uses real `tmp_path` git repos instead of a
  mocked `subprocess.run`, so it is not a fourth precedent. The "index built
  at most once" AC test has no direct existing analog to copy verbatim;
  budget time to establish the pattern, not just port it.

### Documentation

- `docs/reference/API.md` and `docs/reference/CLI.md` reference the
  `format-check` gap-class list and `text_utils`/`FormatGaps` module surface;
  both need the `stale_file_ref` class added alongside the existing eleven.

_Wiring pass added by `/ll:wire-issue`:_
- The gap-class enumeration is duplicated in **two more places** the issue
  didn't name, both needing `stale_file_ref` appended:
  - `scripts/little_loops/cli/issues/__init__.py:115` — the top-level
    `ll-issues --help` banner's `format-check` line, a third copy of the
    string independent of `format_check.py`'s own `--help` (touch-point 4).
  - `.claude/CLAUDE.md:256` (the `ll-issues` bullet under `## CLI Tools`) — a
    fourth copy of the same enumeration.
- `docs/reference/API.md` `#### check_format_gaps` (~lines 848-877) and
  `docs/reference/CLI.md` `#### ll-issues format-check` (~lines 1747-1775)
  are **already stale independent of this issue**: API.md says "reports nine
  gap classes" and CLI.md says "seven," and both enumerations already omit
  `multi_frontmatter` (API.md also omits `testable`) even though both classes
  already ship in code. Adding `stale_file_ref` correctly here means
  reconciling the pre-existing missing bullets in the same edit, not just
  appending one line to an already-accurate list — otherwise the doc drift
  this issue exists to detect would be re-introduced into the docs
  describing the very tool that detects it.

## Program Design

The classifier is a pure function of (reference string, repo state, line
context) with one cached side input — the tracked-file suffix index. No model
call, no network.

**Data flow.** `extract_file_paths(content)` (`text_utils.py`) stays the
extractor; it already strips code fences and normalizes `:NNN` suffixes. Each
extracted reference plus the source line it came from is passed to
`classify_file_ref()`. The line is needed because `planned_new` is a property
of the *annotation* (`(new)`, "new file"), not of the path.

**The suffix index.** Built once per invocation from `git ls-files`, as a
`dict[str, list[str]]` keyed by basename → tracked paths. Suffix matching for
`a/b.py` then checks candidates under key `b.py` for one ending in `/a/b.py`.
Basename keying keeps the lookup O(1) per reference and makes the ambiguity
case (multiple matches → not `resolved`) trivially detectable. `git ls-files`
rather than a filesystem walk so that ignored/build artifacts never satisfy a
reference.

**Ordering matters** — the four checks are not commutative. Form checks come
first (glob, `<placeholder>`, no `/`), because a bare `SKILL.md` would
otherwise suffix-match dozens of tracked files and resolve spuriously. Then
`planned_new` from line context, since a planned file legitimately fails both
existence and suffix match. Only then `root / ref`, then suffix match, then
`stale`.

**Why not reuse `anchor_sweep`.** It resolves `file:NNN` to an enclosing
symbol for *rewriting*; this classifies bare paths for *reporting*. Different
input form, different output, no shared logic worth extracting. They stay
separate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `extract_file_paths()` (`scripts/little_loops/text_utils.py`) returns a bare
  deduplicated `set[str]` — no line number, no surrounding context, and set
  ordering is discarded. A caller needing the source line (as `planned_new`
  classification does) cannot get it from this function as it stands; the
  nearest existing precedent for "extract with a resolvable line number" is
  `_locate_options_in_text()`/`LocatedOption` (`issue_parser.py:625-659`,
  `565-603`), which walks each match back to its containing line via
  `body.rfind("\n", 0, m.start()) + 1` and converts to an absolute 1-indexed
  line with `content.count("\n", 0, abs_start) + 1`.
- `anchor_sweep.py`'s `_sweep_file()`/`resolve_anchor()` (`issues/anchor_sweep.py`,
  `issues/anchors.py`) has no fallback resolution at all — it does a direct
  `Path(file_path).read_text(...)` against the literal captured string, with
  no repo-root resolution and no basename/git-index lookup. A moved file and a
  line number with no matching anchor pattern both collapse to the same
  `skipped_refs += 1` outcome; they are not distinguished. This is concrete
  confirmation of "why not reuse anchor_sweep" above — it has no resolution
  fallback to donate, not just a different input form.
- No `basename -> tracked paths` index exists anywhere in this codebase today.
  Three independent call sites each shell out to `git ls-files` with no
  caching and no shared helper: `_tracked_files()`
  (`cli/verify_private_refs.py:338-352`, `-z`-split, manual decode),
  `_tracked_py_files()` (`codequery/fallback.py:38-47`, glob-filtered,
  `text=True`), and a single-file existence check in `issue_lifecycle.py:431`.
  All three share the same convention worth following: `capture_output=True`,
  explicit `returncode` check (not exception-based), fail-*empty* on error
  (never raise). None builds a basename-keyed dict — `build_ref_index()` is a
  genuinely new primitive, not a wrapper over an existing one, though the
  `git ls-files` invocation shape can be copied directly from either site.

### Signatures

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new"]

@dataclass(frozen=True)
class RefIndex:
    by_basename: dict[str, list[str]]  # basename -> tracked repo-relative paths

def build_ref_index(root: Path) -> RefIndex:
    """Index tracked files by basename, once per invocation."""

def classify_file_ref(ref: str, index: RefIndex, *, line: str = "") -> RefStatus:
    """Classify one path reference extracted from issue prose."""

def classify_issue_refs(content: str, index: RefIndex) -> dict[str, RefStatus]:
    """Classify every extracted reference in one issue body."""
```

### Call Path

- `ll-issues format-check` → `build_ref_index()` (once) →
  per-issue `classify_issue_refs()` → `extract_file_paths()`
  (`scripts/little_loops/text_utils.py`) → `classify_file_ref()` → the
  `stale_file_ref` gap class in the existing `FormatGaps` result
- `build_ref_index()` → `git ls-files` (single subprocess, repo root from
  `find_project_root()` in `scripts/little_loops/paths.py`)
- `/ll:refine-issue` triage (ENH-2971) → `classify_issue_refs()` — the second
  consumer, replacing its own extract-and-filter pass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `@dataclass(frozen=True)` is the established shape for a "built once,
  passed around" result/config object in this codebase (`tool_catalog.py:28`
  `ToolDefinition`, `runner_spec.py:78` `ActionSpec`, `host_runner.py:119`
  `HostCapabilities`, `issues/program_design.py:115` `DesignVerdict`,
  `codequery/core.py:47` `CodeRef`). `RefIndex` as specified matches this
  convention. No existing frozen dataclass wraps a `dict[str, list[str]]`
  git-derived index specifically — this is a new instance of the pattern,
  not a repeat of one.
- `Literal[...]`-returning classifiers already exist in this codebase with
  the same shape as `RefStatus` (`TamperPolicy` in
  `test_tamper_guard.py:26`, `Provenance` in `init/introspect.py:24`,
  `SubagentSupport` in `adapters/capabilities.py:41`) — no naming or typing
  precedent conflict.

## Implementation Steps

1. Add the classifier alongside `extract_file_paths()` (`text_utils.py`) or in
   `scripts/little_loops/issues/`, with the four-way `RefStatus` return.
2. Cache the `git ls-files` suffix index once per invocation — do not shell out
   per reference.
3. Add the `stale_file_ref` gap class to `format-check`, reporting only.
4. Refactor `/ll:refine-issue`'s triage predicate (ENH-2971) to consume the
   classifier instead of its own filter, if ENH-2971 has landed by then.
5. Tests per Acceptance Criteria.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Thread the `RefIndex` built by `build_ref_index()` through all four
   `check_format_gaps(...)` call sites in `cmd_format_check()`
   (`format_check.py:236-240, 247-251, 274-278, 285-289`), building it exactly
   once per invocation ahead of the first call — this is where the "index
   built at most once" AC is actually enforced.
7. Add the `stale_file_ref` line to the `format-check` gap-class enumeration
   in the two additional copies found beyond `format_check.py`'s own
   `--help`: `scripts/little_loops/cli/issues/__init__.py:115` (top-level
   `ll-issues --help` banner) and `.claude/CLAUDE.md:256` (`ll-issues`
   bullet).
8. Update `docs/reference/API.md` (`#### check_format_gaps`) and
   `docs/reference/CLI.md` (`#### ll-issues format-check`) — both are
   already stale independent of this issue (undercounting the gap-class
   total and omitting `multi_frontmatter`/`testable`); reconcile the
   pre-existing omissions in the same edit that adds `stale_file_ref`.
9. Add a `stale_file_ref:` paragraph to `check_format_gaps()`'s own
   "Gap classes:" docstring block (`issue_parser.py:321-355`) — a distinct
   sub-touch inside step 3 above, separate from the field/detection-logic
   edits.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Step 3's "add the gap class" touches four places, not one — see Integration
  Map → Conventions in Force for the full four-touch-point list
  (`FormatGaps` field, `has_gaps`/`to_dict()`, `check_format_gaps()`
  detection block, `_print_gaps()` loop + `--help` string). The `testable`
  regression (ENH-2946, cited in `format_check.py:163-165`) is a class that
  was counted by `has_gaps` but never rendered — verifying `_print_gaps()`
  output, not just `to_dict()`, is what would have caught it.
- Step 5's test fixtures have direct existing precedent: see Integration Map
  → Tests for the exact files and grouped-class pattern
  (`test_ll_issues_format_check.py`, `test_issues_anchors.py`) and the
  `mock_run.call_count` idiom for the "index built once" AC.

## Acceptance Criteria

- [x] `classify_file_ref()` returns `resolved` for an unrooted partial path
      that uniquely suffix-matches a tracked file (`fsm/executor.py`).
- [x] Returns `unresolvable_form` for a bare basename, a glob, and a
      `<placeholder>`-containing path.
- [x] Returns `stale` for a `/`-qualified path with no suffix match
      (`scripts/little_loops/session_store.py`).
- [x] Returns `planned_new` for a path on a line marked `(new)`.
- [x] An ambiguous suffix match (two tracked files ending in `/utils.py`) does
      not silently resolve — asserted explicitly.
- [x] Check ordering is enforced: a bare `SKILL.md` returns
      `unresolvable_form` and is **not** suffix-matched to one of the many
      tracked `SKILL.md` files. This is the ordering bug the design guards
      against, and it is invisible unless tested directly.
- [x] The suffix index is built at most once per `format-check` run, asserted
      by subprocess-call count, not wall-clock.
- [x] `ll-issues format-check --all` reports `stale_file_ref` for a fixture
      issue citing a moved path, and does not report it for one citing only
      basenames and globs.
- [x] `python -m pytest scripts/tests/` passes.

## Impact

- **Effort**: Medium — the classifier's edge cases are the work; the
  `format-check` wiring is small.
- **Risk**: Low — reporting only, no rewrites. The failure mode is a
  false `stale` on an exotic reference form, which is visible and harmless.
- **Breaking Change**: No. Adds a gap class; existing classes unaffected.

## Scope Boundaries

- **In scope**: classification primitive, `stale_file_ref` reporting, wiring
  ENH-2971's triage onto it.
- **Out of scope**: auto-fixing stale references (needs intent); extending
  `anchor-sweep`; back-filling the ~125 existing stale refs in active issues —
  that is a cleanup pass to run *after* the gate exists.

## Related Key Documentation

_No documents linked._

## Session Log
- `/ll:manage-issue` - 2026-08-02T03:09:09 - `3393826b-429e-4a99-966c-c4eff91a4a81.jsonl`
- `/ll:confidence-check` - 2026-08-02T02:48:20 - `e3e414c6-4f76-426a-bbfa-a5e6aa4966f4.jsonl`
- `/ll:wire-issue` - 2026-08-02T02:46:33 - `3f249c91-800b-4cc1-b707-d5e908f8ee51.jsonl`
- `/ll:refine-issue` - 2026-08-02T02:38:08 - `70aac82a-9945-426e-b13e-546fa705b440.jsonl`
- `/ll:capture-issue` - 2026-08-02T01:11:44 - `9e1e4008-8bb1-4bf8-bf7a-3910e48d40f2.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
