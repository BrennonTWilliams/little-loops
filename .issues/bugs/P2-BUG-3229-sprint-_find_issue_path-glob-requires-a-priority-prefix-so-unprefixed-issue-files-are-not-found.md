---
id: BUG-3229
type: BUG
title: 'll-sprint: _find_issue_path''s glob requires a priority prefix, so an unprefixed
  issue file reports "not found" while ll-issues list shows it'
priority: P2
status: open
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-16'
labels:
- sprint
- issue-management
testable: true
confidence_score: 100
outcome_confidence: 74
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3229: ll-sprint: _find_issue_path's glob requires a priority prefix, so an unprefixed issue file reports "not found" while ll-issues list shows it

## Summary

`SprintManager._find_issue_path` (`scripts/little_loops/sprint.py:426`) locates issue files with `issue_dir.glob(f"*-{issue_id}-*.md")` (line 443). That pattern requires a literal `-` before the ID, so it matches `P2-BUG-002-slug.md` but **cannot** match `BUG-002-slug.md` — `*` may match empty, but the `-` preceding the ID is literal and has nothing to match against.

`IssueParser`'s own discovery has no such requirement: `ll-issues list` finds unprefixed files and renders them normally (defaulting them to P5). The two disagree, so an issue that is visibly present in the backlog is invisible to every sprint operation that resolves IDs through `_find_issue_path` — `validate_issues` (line 470), `load_issue_infos` (line 492), and EPIC synthesis (line 311).

The user is not left in silence, but the diagnosis they are given is false, and in the EPIC case it names the wrong noun entirely.

## Current Behavior

Probed live against a scratch project containing exactly two bug files — `BUG-001-no-priority-prefix.md` and `P2-BUG-002-has-prefix.md` — and one epic, `EPIC-100-unprefixed-epic.md`.

`ll-issues list` sees all three:

```
Bugs (2)
  P2  BUG-002  An issue with a priority prefix
  P5  BUG-001  An issue with no priority prefix

Epics (1)
  P5  EPIC-100  An epic with no priority prefix
```

`ll-sprint create probe --issues BUG-001,BUG-002` reports the existing file as missing:

```
[..] Issue IDs not found: BUG-001
[..] Created sprint: probe
[..]   Issues: BUG-001, BUG-002
[..]   Invalid issues: BUG-001
```

`ll-sprint show probe` then plans one issue instead of two and reports `Sprint health: WARNING -- 1 issue(s) not found on disk`.

The EPIC path is the worst presentation. `ll-sprint show EPIC-100` prints:

```
[..] Sprint not found: EPIC-100
```

`load_or_synthesize` (line 311) gets `None` from `_find_issue_path` and returns `None` at line 313, which the caller renders as a missing **sprint**. The epic is right there in `ll-issues list`; nothing in the message points at the epic file, let alone at its filename.

## Expected Behavior

An issue file whose **filename** carries a resolvable `TYPE-NNN` anchor should resolve for every sprint operation, regardless of whether that filename also carries a priority prefix. Failing that, the diagnostic should name the real cause ("found `BUG-001-no-priority-prefix.md`, but its filename has no `P<n>-` prefix") rather than asserting the issue does not exist — and the EPIC path should not report a missing *sprint* for a present epic.

**Scope boundary — filename resolution, not frontmatter resolution.** An earlier
draft of this criterion read "anything `ll-issues list` displays should resolve",
which is not achievable by any glob fix and would silently expand the issue.
`ll-issues list` keys on the frontmatter `id:`; every glob-based resolver keys on
the filename. A file named `notes.md` carrying `id: BUG-001` is displayed by
`ll-issues list` and cannot be found by any filename pattern. Closing *that* gap
means routing sprint resolution through `IssueParser`/`find_issues` (a full
frontmatter sweep on every lookup) — a different, larger change with a different
performance profile. **This issue is scoped to filename resolution.** The
frontmatter-only case is out of scope and should be filed separately if wanted.

Zero-padding normalization (`BUG-1` resolving to `P2-BUG-001-*.md`) is likewise
**out of scope**: `_find_issue_path` compares `fid.number` to the requested
number as a string, and that behavior is unchanged here.

## Steps to Reproduce

1. In a project with `.issues/bugs/`, create `BUG-001-no-priority-prefix.md` with valid frontmatter (`id: BUG-001`, `type: BUG`, `status: open`) and a normally-named control, `P2-BUG-002-has-prefix.md`.
2. Run `ll-issues list` — both are listed.
3. Run `ll-sprint create probe --issues BUG-001,BUG-002` — observe `Issue IDs not found: BUG-001` and `Invalid issues: BUG-001`.
4. Run `ll-sprint show probe` — observe a one-issue execution plan and a `WARNING -- 1 issue(s) not found on disk` health line.
5. Create `.issues/epics/EPIC-100-unprefixed-epic.md` with `relates_to: [BUG-002]`.
6. Run `ll-sprint show EPIC-100` — observe `Sprint not found: EPIC-100`, naming the wrong noun for an epic that `ll-issues list` displays.

## Proposed Solution

### Converge on the existing correct resolver — do not author a fourth glob

There are already **three** independent ID→path resolvers in the tree, and the
drift between them is the defect. A fix that invents a fourth pattern in
`sprint.py` treats the symptom:

| Resolver | Keys on | Handles unprefixed names |
| --- | --- | --- |
| `sprint.py:444` `_find_issue_path` | `*-{issue_id}-*.md` (full ID) | **No** — this bug |
| `cli/issues/show.py:41` `_resolve_issue_id` | `*-{numeric_id}-*.md` (number only) | **Yes** |
| `issue_parser.find_issues` | frontmatter `id:` | Yes |

`cli/issues/show.py`'s `_resolve_issue_id` is the convergence target for the
*glob key*. It gets the unprefixed case right for the reason this bug exists:
because it globs on the **numeric ID alone**, the `-` preceding the number is
supplied by the type token itself (`BUG-001-slug.md` → `*` matches `BUG`,
`-001-` matches literally), so a missing priority prefix is a non-event. It then:

1. collects **all** candidates across type-scoped *and* legacy dirs, `sorted()`;
2. filters to those whose *anchored* `parse_issue_filename` position carries the
   requested number, keeping the raw glob set when nothing survives;
3. disambiguates by frontmatter identity, then by type, then by priority.

Extract that resolution into a shared helper and have `_find_issue_path` call it.
That fixes the bug and removes one of the three definitions rather than adding a
fourth — **but not by adopting show.py's fallback behavior verbatim**; see the
blocking correction immediately below.

### BLOCKING: show.py's fallback chain violates AC #5 today (probed)

An earlier draft of decision (2) below read "recommend **keep** the fallback,
matching show.py, which only falls back when *no* candidate parses — a narrower
fallback than sprint.py's per-candidate one." **That is wrong, and inverted.**
show.py falls back when no candidate *survives a filter*, which is a far wider
net than "no candidate parses," and it composes two such fallbacks in series.

Probed live, with `P2-FEAT-500-fix-BUG-001-regression.md` as the only file on
disk:

```python
>>> _resolve_issue_id(config, "BUG-001")
PosixPath('.issues/features/P2-FEAT-500-fix-BUG-001-regression.md')
```

The chain: glob `*-001-*.md` matches the file (its slug embeds `-001-`) → the
anchored filter yields `[]` because the file's anchored number is `500`, so
`candidates` stays the **raw glob set** (`show.py:170-171`, `if anchored:`) →
`_matches_type` rejects it (`FEAT != BUG`) so `pool` is empty → `if not pool:
pool = candidates` (`show.py:180-181`) hands the rejected file straight back.

`sprint.py:_find_issue_path` gets this case **right today**: its per-candidate
anchored check (`fid.type_prefix == expected_type and fid.number ==
expected_number`) returns `None`. So on this axis sprint.py is the *stricter*
resolver, and a naive convergence is a **regression on exactly the false-positive
guard AC #5 exists to protect**.

The implementer must not be left to discover this. Settle it here — pick one:

- **(i) Narrow the fallback inside the shared helper** (recommended): fall back
  to the raw glob set only when `parse_issue_filename` returns `None` for
  **every** candidate — a genuine legacy-name escape hatch — never merely
  because a type or priority filter emptied the pool. Keep AC #5.
- **(ii) Keep show.py's chain as-is** and delete AC #5, accepting that a slug
  embedding another issue's ID can resolve when it is the sole candidate.

Choosing (i) means `cmd_show`'s behavior **changes** for this input class, so
Implementation Step 1's "keeping `show.py` behavior byte-identical" does not
hold; that is the intended trade and should be asserted by a test on the
`cmd_show` side too. Choosing (ii) trades a real guard for zero code change.
Recommend **(i)** — the false positive is silent and points a user at an
unrelated issue file.

### Extraction boundary: the unit is the whole function, not lines 96-124

`_resolve_issue_id` spans `show.py:41-186` — 145 lines. Lines 96-124 are only
the candidate collection and anchored filter. The frontmatter disambiguation
that decision (1) requires lives at `:154-166`; the type-preference and
priority-preference passes at `:168-186`; and an input-parsing front end at
`:41-95` accepts three shapes (`518`, `BUG-518`, `P2-BUG-518`) of which sprint
only ever passes the middle one. Extracting a 29-line slice loses the
disambiguation the issue asks for. Move the whole function.

### Two widenings this fix carries, stated rather than discovered

1. **Type prefix becomes advisory.** `_find_issue_path` today *requires*
   `fid.type_prefix == expected_type`. show.py treats a mismatched type as a
   stale hint and falls back to the unambiguous numeric match. After
   convergence, `ll-sprint create --issues BUG-500` can resolve
   `P2-FEAT-500-*.md`. This is consistent with the house position that the
   numeric ID is the true unique identifier and the type token is human-readable
   shorthand — but it is a behavior change on the sprint path, not a no-op.
2. **`legacy_issue_dirs()` joins the search.** show.py scans `completed_dir` /
   `deferred_dir` in addition to `issue_categories` (BUG-2733 tolerance);
   sprint.py does not today. After convergence a sprint can resolve an issue
   parked in a legacy directory. Probably desirable; state it.

### Why the anchored re-check makes this safe (verified)

`_ANCHORED_FILENAME_RE` (`issue_parser.py:58`) is:

```python
re.compile(r"^(?:(P[0-5])-)?(BUG|FEAT|ENH|EPIC)-(\d+)-", re.IGNORECASE)
```

The priority group is **optional**, so `parse_issue_filename("BUG-001-slug.md")`
returns `FilenameId(priority=None, type_prefix="BUG", number="001")` — a real
parse, not `None`. The unprefixed file therefore resolves through the anchored
*positive* check, **not** through the `fid is None` legacy fallback. This is the
load-bearing fact for the fix's safety and is worth re-asserting in a test.

### Three decisions the implementer must not be left to make

1. **Multi-candidate ordering.** `_find_issue_path` returns the *first* glob hit
   and `Path.glob` ordering is not guaranteed. Widening the pattern strictly
   increases the chance of more than one hit, so first-match-wins gets worse, not
   better. Adopt show.py's `sorted()` + frontmatter disambiguation; do not ship a
   widened glob that still returns an arbitrary first match.
2. **The `fid is None` fallback at line 449 — and show.py's two wider ones.**
   Today `if fid is None or (type/number match)` returns the path for *any*
   filename the anchor regex cannot parse. Under a widened pattern this admits
   names where the ID is not `-`-preceded (e.g. `xBUG-001-y.md`). Recommend
   **keep** a fallback, but scoped as option (i) in the BLOCKING section above:
   set-level, and conditioned on *nothing parsing* rather than on a filter
   emptying the pool. Do **not** carry over show.py's `if not pool: pool =
   candidates` (`:180-181`) — that is the clause that returns a rejected
   wrong-type file and breaks AC #5.
3. **The EPIC branch.** "Distinguish 'no such epic' from 'epic found but
   unusable'" is not yet actionable: `load_or_synthesize` (line 311) returns a
   bare `None` for *three* distinct outcomes — arg is not EPIC-shaped (line 304),
   epic file not found (line 313), epic file unparseable (line 322) — and the
   caller renders all of them as `Sprint not found: <arg>`. Pick one:
   - **(a)** Have `load_or_synthesize` raise a distinct exception (or return a
     sentinel) for the epic-specific failures, and have the caller render "EPIC
     not found: EPIC-100" / "EPIC-100 found at <path> but could not be parsed".
   - **(b)** Leave the return type alone and have the *caller* pre-check
     `_EPIC_ID_RE` before falling through to the sprint-not-found message.

   Recommend **(a)** — (b) duplicates the EPIC-shape test at the call site, which
   is how the resolvers drifted in the first place.

## Impact

- **Priority**: P2 — Not a silent data loss (a warning is printed), but a false diagnosis on a path users act on: they are told an issue does not exist while `ll-issues list` shows it, so the natural next step is to re-create an issue that is already there. The EPIC case misdirects entirely, pointing at sprints rather than at the epic file.
- **Effort**: Medium. A bare glob widening is one line, but the recommended
  shape — moving the whole 145-line `_resolve_issue_id` (`show.py:41-186`) into
  a shared helper, narrowing its fallback chain per option (i), and calling it
  from `_find_issue_path` — touches two call sites plus the EPIC message change,
  and changes `cmd_show` behavior for the sole-candidate wrong-type case. The
  larger number is the honest one; the one-line version leaves the
  arbitrary-first-match and three-resolver problems in place.
- **Risk**: Low-to-Medium. The anchored `parse_issue_filename` re-check is the
  arbiter and the regex's priority group is optional, so unprefixed names
  resolve through the positive check rather than the legacy fallback. The
  medium component is show.py's composed fallbacks, which today return a
  wrong-type file when it is the sole candidate (see BLOCKING above) — adopting
  them unchanged would regress a guard sprint.py currently holds.
- **Breaking Change**: No for the *unprefixed* case — strictly widens what
  resolves, and files that resolve today continue to. Two adjacent widenings do
  change sprint behavior, deliberately: a mismatched type prefix becomes
  advisory rather than disqualifying, and `legacy_issue_dirs()` enters the
  search path. Neither removes a resolution that works today.

## Root Cause

Two independent definitions of "an issue file on disk" drifted apart:

- `_find_issue_path` (`sprint.py:443`): `glob(f"*-{issue_id}-*.md")` — requires a prefix token before the ID.
- `IssueParser` / `find_issues`: no prefix requirement; a missing priority prefix is tolerated and defaulted to P5 at display time.

The glob's leading `*-` encodes an assumption that every issue filename is normalized to `P<n>-TYPE-NNN-slug.md`. `ll-issues normalize` exists precisely because that is not guaranteed, and `ll-issues list` renders unprefixed files as first-class — so the assumption is not one the rest of the system makes.

`cli/issues/show.py` avoided the same trap only incidentally: it globs on the
numeric ID rather than the full `TYPE-NNN`, so the `-` its pattern requires is
supplied by the type token instead of by the priority prefix. Nothing about the
sprint resolver's *intent* differed — only its choice of glob key.

## Integration Map

| Site | Role |
| --- | --- |
| `scripts/little_loops/sprint.py:426-451` `_find_issue_path` | The defect. Sole ID→path resolver for the sprint subsystem. |
| `scripts/little_loops/sprint.py:311-313` `load_or_synthesize` | Caller; converts `None` into a "Sprint not found" message for EPIC args. |
| `scripts/little_loops/sprint.py:470` `validate_issues` | Caller; produces `Issue IDs not found` / `Invalid issues`. |
| `scripts/little_loops/sprint.py:492` `load_issue_infos` | Caller; silently drops unresolved IDs from the execution plan. |
| `scripts/little_loops/cli/issues/show.py:96-124` | The correct resolver; extraction source for the shared helper. |
| `scripts/little_loops/issue_parser.py:58` `_ANCHORED_FILENAME_RE` | Optional-priority regex that makes the anchored re-check work for unprefixed names. |
| `scripts/little_loops/issue_parser.py:70` `parse_issue_filename` | The arbiter both resolvers already share. |

## Program Design

### Signatures
- `resolve_issue_path(config: BRConfig, issue_id: str) -> Path | None` — new shared helper; globs on the **numeric** ID across type-scoped and legacy dirs, filters candidates by anchored `parse_issue_filename` position, and disambiguates a multi-hit by frontmatter identity, then type, then priority. Extraction source is the **whole** of `_resolve_issue_id`, `scripts/little_loops/cli/issues/show.py:41-186` — not the `:96-124` slice, which omits the frontmatter disambiguation at `:154-166` and the type/priority passes at `:168-186`. Its fallback chain must be narrowed per option (i) before reuse.
- `_resolve_issue_id(config: BRConfig, user_input: str) -> Path | None` — becomes a thin delegation to the helper (or is deleted in favour of it); its input-parsing front end at `:41-95` accepts `518` / `BUG-518` / `P2-BUG-518`, a superset of what sprint passes, so the helper must keep accepting all three; see `scripts/little_loops/cli/issues/show.py:41`.
- `SprintManager._find_issue_path(self, issue_id: str) -> Path | None` — becomes a thin delegation to the helper, preserving its `None`-on-missing contract so all three callers are untouched; currently at `scripts/little_loops/sprint.py:426-451`.
- `parse_issue_filename(filename: str) -> FilenameId | None` — unchanged arbiter; its optional priority group is what lets an unprefixed name resolve through the positive branch rather than the legacy fallback; see `scripts/little_loops/issue_parser.py:70` and the regex at `:58`.
- `SprintManager.load_or_synthesize(self, arg: str, name: str) -> Sprint | None` — return contract widens (or raises) so the EPIC-specific failures are distinguishable from "not a sprint"; see `scripts/little_loops/sprint.py:311-322`.

### Types
`FilenameId(priority: str | None, type_prefix: str, number: str)` — already exists (`scripts/little_loops/issue_parser.py`), frozen dataclass, no change. No new data shape is introduced: the helper returns `Path | None`, matching what `_find_issue_path` returns today. The only type-level change is on the EPIC branch, where `load_or_synthesize`'s three-way-collapsed `None` must gain a discriminator — either a raised `EpicNotFoundError` / `EpicUnparseableError` or a sentinel; see decision (3) in Proposed Solution.

### Call Path
`ll-sprint create --issues BUG-001` → `SprintManager.validate_issues()` (`sprint.py:470`) → `_find_issue_path("BUG-001")` → `issue_dir.glob("*-BUG-001-*.md")` → the leading `*-` requires a `-` before `BUG` that an unprefixed filename cannot supply → zero candidates → `None` → `validate_issues` omits the ID from its `valid` dict → CLI renders `Issue IDs not found: BUG-001`. After the fix the same path calls `resolve_issue_path()`, which globs `*-001-*.md` (the `-` supplied by the `BUG` token itself), parses each candidate's anchor, matches `number == "001"`, and returns the path. The EPIC variant enters at `load_or_synthesize()` (`sprint.py:311`) instead, whose `None` return is rendered by the caller as `Sprint not found: EPIC-100`.

### Decision Rules
Candidate acceptance is unchanged in *kind* — anchored parse remains the arbiter — but four rules are now stated rather than implied: (a) a candidate is accepted when its anchored `FilenameId.number` equals the requested number, regardless of whether a `P<n>-` prefix is present; (b) fall back to the raw glob set only when **no** candidate parses at all (set-level legacy escape hatch), not per-candidate as `sprint.py:449` does today; (c) a filter emptying the pool is **not** a fallback trigger — show.py's `if not pool: pool = candidates` (`:180-181`) must not be carried over, since it is what returns a wrong-type sole candidate and breaks AC #5; (d) when more than one candidate survives, order `sorted()` and disambiguate by frontmatter identity rather than returning an arbitrary `glob` hit. Zero-padding equivalence (`BUG-1` ≡ `BUG-001`) is explicitly **not** a rule here — comparison stays string equality. A mismatched type prefix demotes a candidate but does not, on its own, resurrect one that the anchored filter already rejected.

## Implementation Steps

1. Move the whole of `cli/issues/show.py:_resolve_issue_id` (`:41-186`) into a
   shared helper (suggest `issue_parser.resolve_issue_path(config, issue_id)`),
   and have `show.py` delegate to it. Behavior is preserved **except** for the
   fallback narrowing in step 3, which is an intended `cmd_show` change.
2. Reimplement `sprint.py:_find_issue_path` as a call to that helper.
3. Apply the BLOCKING decision — option (i) unless overridden: fall back to the
   raw glob set only when no candidate parses, and drop
   `if not pool: pool = candidates`. Both call sites then get the same answer,
   and AC #5 holds for `cmd_show` as well as for sprint.
4. Apply decision (3) to `load_or_synthesize` + its caller so an existing-but-
   unresolvable EPIC no longer renders as a missing sprint.
5. Add the regression tests below.

## Acceptance Criteria

- [ ] `ll-sprint create <name> --issues BUG-001` resolves `BUG-001-no-prefix.md`
      (no `P<n>-`) — no `Issue IDs not found`, no `Invalid issues`.
- [ ] `ll-sprint show <name>` for that sprint plans the issue and reports no
      `not found on disk` health warning.
- [ ] `ll-sprint show EPIC-100` against an unprefixed
      `.issues/epics/EPIC-100-*.md` synthesizes the epic sprint.
- [ ] `ll-sprint show EPIC-999` (genuinely absent) reports a message naming the
      **EPIC**, not a missing sprint.
- [ ] A file whose slug embeds another issue's `TYPE-NNN` (e.g.
      `P2-FEAT-500-fix-BUG-001-regression.md`) does **not** resolve for
      `BUG-001` — the existing false-positive guard still holds under the wider
      pattern. Assert this with that file as the **sole** candidate on disk,
      which is the configuration that fails today (probed: `_resolve_issue_id`
      returns it, `sprint._find_issue_path` correctly returns `None`).
- [ ] The same assertion holds for `ll-issues show BUG-001` — the shared helper
      fixes `cmd_show`'s sole-candidate false positive rather than importing it
      into sprint.
- [ ] A genuinely legacy filename that `parse_issue_filename` cannot parse at
      all still resolves (set-level fallback preserved), pinning rule (b)
      against rule (c)'s narrowing.
- [ ] Two files legitimately matching the same number resolve deterministically
      (sorted + frontmatter disambiguation), not by arbitrary `glob` order.
- [ ] A direct unit assertion that
      `parse_issue_filename("BUG-001-slug.md")` returns a non-`None`
      `FilenameId` with `type_prefix == "BUG"` and `number == "001"`, pinning the
      optional-priority group the fix depends on.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Found while auditing `little-loops-hermes`, which shells out to these CLIs; the defect is entirely upstream and reproduces with the CLIs alone.

## Status

**Open** | Created: 2026-08-16 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-17T04:01:08 - `03558def-29ef-40d7-87ba-66fe5fe13be8.jsonl`
