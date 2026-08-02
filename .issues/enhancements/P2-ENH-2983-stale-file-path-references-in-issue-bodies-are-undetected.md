---
id: ENH-2983
title: Stale file path references in issue bodies are undetected
type: ENH
priority: P2
status: open
captured_at: '2026-08-01T00:00:00Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2971
labels:
- issues
- format-check
- data-quality
testable: true
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

## Implementation Steps

1. Add the classifier alongside `extract_file_paths()` (`text_utils.py`) or in
   `scripts/little_loops/issues/`, with the four-way `RefStatus` return.
2. Cache the `git ls-files` suffix index once per invocation — do not shell out
   per reference.
3. Add the `stale_file_ref` gap class to `format-check`, reporting only.
4. Refactor `/ll:refine-issue`'s triage predicate (ENH-2971) to consume the
   classifier instead of its own filter, if ENH-2971 has landed by then.
5. Tests per Acceptance Criteria.

## Acceptance Criteria

- [ ] `classify_file_ref()` returns `resolved` for an unrooted partial path
      that uniquely suffix-matches a tracked file (`fsm/executor.py`).
- [ ] Returns `unresolvable_form` for a bare basename, a glob, and a
      `<placeholder>`-containing path.
- [ ] Returns `stale` for a `/`-qualified path with no suffix match
      (`scripts/little_loops/session_store.py`).
- [ ] Returns `planned_new` for a path on a line marked `(new)`.
- [ ] An ambiguous suffix match (two tracked files ending in `/utils.py`) does
      not silently resolve — asserted explicitly.
- [ ] Check ordering is enforced: a bare `SKILL.md` returns
      `unresolvable_form` and is **not** suffix-matched to one of the many
      tracked `SKILL.md` files. This is the ordering bug the design guards
      against, and it is invisible unless tested directly.
- [ ] The suffix index is built at most once per `format-check` run, asserted
      by subprocess-call count, not wall-clock.
- [ ] `ll-issues format-check --all` reports `stale_file_ref` for a fixture
      issue citing a moved path, and does not report it for one citing only
      basenames and globs.
- [ ] `python -m pytest scripts/tests/` passes.

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
- `/ll:capture-issue` - 2026-08-02T01:11:44 - `9e1e4008-8bb1-4bf8-bf7a-3910e48d40f2.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P2
