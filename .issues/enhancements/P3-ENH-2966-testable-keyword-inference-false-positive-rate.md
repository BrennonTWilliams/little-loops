---
id: ENH-2966
title: '`testable` keyword inference fires on 88% of the issues it evaluates'
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2946
testable: true
decision_needed: false
labels:
- issues
- cli
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# ENH-2966: `testable` keyword inference fires on 88% of the issues it evaluates

## Summary

`check_format_gaps`'s `testable` advisory flags an issue as
documentation-only when 2+ distinct signal keywords appear anywhere in its
title or body. In this repo — whose subject matter *is* documentation, skills,
and doc tooling — that fires on **35 of the 40 issues the rule actually
evaluates (88%)**. (The active corpus is 71; the other 31 carry an explicit
`testable:` key and are exempt by construction, so they are exempt *by
frontmatter*, not because the rule discriminated.) An advisory that fires on
nearly everything it looks at carries no information.

## Current Behavior

`issue_parser.py`:

- `_TESTABLE_SIGNAL_KEYWORDS` (`L1828-1840`): `doc`, `docs`, `documentation`,
  `broken link`, `broken anchor`, `readme`, `changelog`, `spelling`, `typo`,
  `guide`, `fix link`.
- `_TESTABLE_KEYWORD_THRESHOLD = 2` (`L1841`) — 2+ *distinct* matches.
- `_count_testable_keyword_matches` (`L1844-1847`) — plain **substring**
  containment (`kw in text.lower()`), not word-boundary matching.
- `check_format_gaps` (`L992-1001`) scans `title + strip_frontmatter(content)`
  — the **entire issue body** — and appends a `testable` gap when no explicit
  `testable:` key is present.
- `infer_testable` (`L1850-1862`) applies the same rule over the same surface
  as a separate entry point.

Measured on the current backlog (2026-08-19): of **71 active issues**, 31 carry
an explicit `testable:` key and are skipped, leaving **40 scanned — 35 of which
trip it**.

Note the scoping: `cmd_format_check --all` sweeps `find_issues(config)`, whose
default status filter is open/in_progress/blocked — `done`, `cancelled`, and
**`deferred`** issues are never scanned. Any denominator that includes deferred
issues overstates the corpus the rule actually sees.

The rule is behaving exactly as specified. The specification is the problem,
and the failure is **structural, not prose drift**. Because matching is bare
substring containment and `doc` is a substring of several ordinary words:

- The single word **`documentation` scores 2 on its own** (`doc` +
  `documentation`) — one occurrence of one word reaches the threshold.
- Any reference to a file under the repo's `docs/guides` directory scores 3
  (`doc` + `docs` + `guide`) from the path fragment alone.
- **`## Related Key Documentation` — a heading in the standard issue template —
  scores 2 by itself.** Every template-conformant issue without an explicit
  `testable:` key therefore fires *by construction*: **30 of the 40 scanned
  issues carry that heading and are guaranteed fires from it alone**,
  independent of anything the issue is actually about.

Secondary contributors:

- The scan covers the whole body, so any issue that *discusses* documentation
  in its Integration Map, Scope Boundaries, or Documentation section matches —
  regardless of whether the work itself is doc-only.
- Bare `doc`/`guide` are extremely common in a repo with `docs/guides/`,
  `LOOPS_GUIDE.md`, and `HARNESS_OPTIMIZATION_GUIDE.md`.

Concrete false positive: ENH-2946 (a pure CLI-implementation issue) began
tripping the advisory only after prose about *documentation drift* was added
to its body. The issue's testability did not change.

The advisory also **fails the gate**: `testable` is included in
`FormatGaps.has_gaps` (`L518-531`), so an advisory-only signal produces the
same non-zero `format-check` exit as a real structural gap.

## Expected Behavior

The advisory fires rarely enough that it is worth reading — it should identify
issues that are genuinely documentation-only, not issues that mention
documentation.

## Motivation

A gap class that fires on 88% of what it evaluates is indistinguishable from noise,
and the cost is not neutral:

- It trains readers to ignore `format-check` output, which also carries the
  ten real structural gap classes.
- The remedy the message suggests (`set an explicit testable:` key) makes the
  advisory disappear without anyone verifying the issue is actually testable —
  so the rule pushes toward reflexive frontmatter stamping rather than
  judgment.
- Every false positive is a non-zero exit from `format-check`, which is a
  gate other tooling consumes.

## Proposed Solution

### Measured fire counts (re-measured 2026-08-19; 70 active, 40 scanned)

Each option simulated against the live backlog before choosing. Denominator is
the **40 scanned** issues (70 active minus 30 exempt via an explicit
`testable:` key) — not the full active corpus, which the rule never evaluates.

| Option | Rule | Fires (of 40) | False positives |
|---|---|---|---|
| *(current)* | whole body, 11 keywords, substring, ≥2 | **35** | ~34 |
| **A** | title + `## Summary`, 11 keywords, substring, ≥2 | **6** | **5** |
| **B** | whole body, 8 keywords, substring, ≥2 | **6** | ≥5 |
| **A + B** | title + `## Summary`, 8 keywords, substring, ≥2 | **0** | 0 |
| **C** | whole body, 11 keywords, substring, ≥3 | **30** | ~29 |
| **A + F** *(guard `(?<![a-z0-9])`)* | title + `## Summary`, 11 keywords, **word-boundary**, ≥2 | **1** | **1** |
| **A + F′** *(adopted; guard `(?<![a-z0-9_])`)* | as above, `_` added to the leading guard | **0** | **0** |
| *(A, bare `doc` dropped)* | title + `## Summary`, 10 keywords, substring, ≥2 | 1 | 1 |
| *(A, threshold 3)* | title + `## Summary`, 11 keywords, substring, ≥3 | 1 | 1 |

**The fire count alone is the wrong criterion — see the hand-check below.** A
hits the single-digit target but 5 of its 6 fires are false positives; C barely
moves (35 → 30); A + B overshoots to zero. The three `1`-fire rows all collapse
to the same single survivor (`EPIC-3217`, itself a false positive), which
identifies the residual driver precisely: **bare `doc` matching as a substring**,
not the scan surface.

**A + F′ reaching 0 is not the same failure as A + B reaching 0.** A + B zeroes
the count while still scoring `documentation` as two hits and still scanning the
whole body — it removes data, not the defect. A + F′ removes the defect, and the
residual `EPIC-3217` it clears was itself a false positive (its two hits are
`docs` and `guide`, both from one `docs/guides/…` citation ending in
`_GUIDE.md`). Since
the backlog's one genuine doc-only issue fires under no precise variant at all
(see "The metric has no true positives"), 0 here is the expected reading of a
smoke measurement, not a signal to revert. Acceptance is the labeled fixture set.

Because A and B tie on raw fire count, **the choice between them was never a
metric argument** — it rests on implementation fit (A reuses `_section_body`,
already the helper `check_format_gaps` calls for other gap classes) and on the
fact that they cannot be combined without collapsing to zero. See Decision
Rationale.

The measurement is cheap to reproduce: `ll-issues format-check --all --format
json`, count non-empty `testable` arrays. **Reproduced 2026-08-19** — the CLI
sweep and a direct `_section_body`-based simulation agree exactly (35).

### Hand-check of Option A's survivors — performed 2026-08-19

Implementation Steps step 4 deferred this to implementation time. **It has now
been run, and A fails it.** A's 6 survivors, each read against its title and
`## Summary`:

| ID | Subject | Genuinely doc-only? |
|---|---|---|
| `EPIC-1867` | Orchestrator FSM decomposition (`ll-auto`/`ll-sprint`/`ll-parallel`) | no |
| `EPIC-3217` | `cannot_judge` abstention retrofit across built-in loops | no |
| `EPIC-3127` | `ll-mcp` — MCP server as the host-agnostic serving layer | no |
| `EPIC-1463` | Track deferred Codex CLI interop gaps | no |
| `FEAT-2797` | omp structured-output surface + agent `output:` schema wiring | no |
| `ENH-2191` | Populate the `HOST_COMPATIBILITY.md` Gemini column | **yes** |

**5 of 6 are false positives.** Every one is code work that merely *cites* a
`docs/…` path or names `HOST_COMPATIBILITY.md` in its Summary. Under the
issue's own step-4 branch this would trigger "apply B instead of A" — but B's
6 (`ENH-2923`, `EPIC-1463`, `EPIC-2178`, `EPIC-3154`, `FEAT-2186`,
`FEAT-2261`) are no better and B leaves the whole-body surface structurally
intact. **The branch is a trap and has been replaced** (see Option F and the
revised Implementation Steps).

### The metric has no true positives

The active corpus contains **roughly one** genuinely doc-only issue
(`ENH-2191`), and it drops out of every precise variant — including A + F,
because "Update `docs/reference/HOST_COMPATIBILITY.md` … populate the Gemini
column" contains no word-boundary keyword hit beyond `documentation`'s absence.
Consequence: **"single-digit but not zero" is an arbitrary proxy target.** Six
fires with five false positives is not better than zero fires; both carry the
same (zero) information.

The acceptance criterion is therefore restated as **precision against a labeled
fixture set** — synthetic doc-only issues that must fire, plus real
code-issue shapes that must not — with the backlog fire count demoted to a
smoke measurement. `_DOC_ONLY_BODY`
(`scripts/tests/test_ll_issues_format_check.py:2590`) is currently the **only
true positive anywhere in the repo**, which is itself the reason a
backlog-count target was reachable while precision stayed unmeasured.

### Options

**A. Narrow the scan surface.** Match against the title and `## Summary` only,
not the whole body. Most genuine doc-only issues announce themselves in the
title ("fix broken link in X", "update CHANGELOG"). This removes the
`## Related Key Documentation` heading and the Integration Map/Scope Boundaries
prose from the scan, which is where the structural false positives originate.

**B. Tighten the keyword list.** Drop bare `doc`/`guide`/`docs` (substrings of
ordinary prose and of each other), keep the high-signal phrases (`broken link`,
`broken anchor`, `fix link`, `typo`, `spelling`, `changelog`, `readme`,
`documentation`). This makes the distinct-match count meaningful, since the
surviving keywords are no longer near-synonyms.

**C. Raise the threshold** from 2 to 3+ distinct matches. Cheapest change, but
measurement shows it only shifts the curve (35 → 30) rather than fixing the
surface problem.

**D. Negative signals.** Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design.

**E. Demote `testable` to a non-gating advisory** so it still renders in the
report but no longer forces a non-zero `format-check` exit. (Stated originally
as "remove it from `FormatGaps.has_gaps`"; the wiring pass showed that makes it
*invisible* rather than non-gating, so the adopted shape is a
`has_gaps`/`has_blocking_gaps` split — see Program Design.) This is
**orthogonal to precision** and directly
addresses the harm named in Motivation — that every false positive fails a gate
other tooling consumes. It can be adopted alongside any of A–D, or on its own.

**F. Word-boundary matching.** Replace bare substring containment
(`kw in text.lower()`) with a word-boundary match, so `doc` no longer matches
inside `documentation`, `docs`, or a `docs/guides/…` path fragment. **Added
2026-08-19**, after the hand-check above showed A's residual false positives
are driven entirely by that artifact — not by the scan surface. Measured
**A + F = 1 fire** (from A's 6), and **A + F′ = 0** once the leading guard also
excludes `_` — the corrected form adopted by the fourth review; see Program
Design. Orthogonal to A–E in the same way E is: it
changes *how* a keyword matches, not *what is scanned* or *whether the class
gates*.

This option was previously excluded by Scope Boundaries on the premise that
"narrowing the surface (A) is sufficient to hit the target." **The hand-check
falsifies that premise** — A hits the count target while remaining 83%
false-positive. `documentation` scoring 2 on its own (`doc` + `documentation`)
is a defect in the matcher, not a tuning parameter, and no surface narrowing
can remove it.

Cost is bounded: one regex in `_count_testable_keyword_matches`, no change to
the keyword tuple, threshold, or call graph. Two cheaper near-equivalents were
measured and also land at 1 fire — dropping the bare `doc` keyword (Option B's
mechanism, applied surgically) and raising the threshold to 3 (Option C) — but
both leave the underlying substring semantics in place to resurface on the next
keyword added.

**Recommended**: **Option A + Option F + Option E.** A narrows the surface and
reuses the helper `check_format_gaps` already calls; F removes the substring
artifact that A alone leaves behind (6 fires → 0 with the corrected `_` guard,
1 without it); E fixes the gate-failure
complaint independently of how precise the keyword rule becomes. B is **no
longer held as a contingent alternative** — the hand-check that would have
triggered it has been run, and B's own survivors are equally imprecise.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis. The alternatives
above are restated here in the `**Option X**` heading form the
`check-decidable` probe (`locate_enumerable_options`,
`scripts/little_loops/issue_parser.py`) scans for — the `**A.**`-prefix form
above does not match its heading regex, so it was invisible to the decision
gate despite being a genuine 4-option decision point._

**Option A**: Narrow the scan surface to title + `## Summary` only. Measured:
**6 fires** (from 35, of 40 scanned). Hits the single-digit target on its own.

Reuses `_section_body`, the exact helper `check_format_gaps` already calls for
its other gap classes, and two other gap classes already implement the identical
allowlist-of-sections-via-`_section_body` pattern. **Necessary but not
sufficient** — see the single `> **Selected:**` block below, which records the
adopted A + F + E combination.

**Option B**: Tighten the keyword list — drop bare `doc`/`docs`/`guide`, keep
`broken link`, `broken anchor`, `fix link`, `typo`, `spelling`, `changelog`,
`readme`, `documentation`. Measured: **6 fires** — ties Option A. Combined with
A: **0 fires** (over-corrects), so the two are mutually exclusive in practice.

**Option C**: Raise the threshold from 2 to 3+ distinct matches. Measured:
**30 fires** — barely moves, because the template's own `## Related Key
Documentation` heading plus one `docs/` path already clears any small fixed
count.

**Option D**: Negative signals. Suppress when the issue names code artifacts
(`.py` paths, `def `/`class `, a `## Program Design` section with real
signatures). A doc-only issue rarely has a populated Program Design. Not
measured — highest effort of the five, and A already meets the target.

**Option E**: Demote `testable` to a non-gating advisory by splitting
`FormatGaps.has_gaps` (`issue_parser.py:517-544`) into a reporting predicate
(unchanged) and a new `has_blocking_gaps` exit-code predicate. Report the class,
but stop failing `format-check` on it. Orthogonal to A–D and F; composable with
any of them.

**Option F**: Word-boundary matching in `_count_testable_keyword_matches`
(`issue_parser.py:1844-1847`) instead of bare substring containment, so `doc`
stops matching inside `documentation` / `docs` / `docs/guides/…`. Measured
**A + F = 1 fire** (from A's 6); **A + F′ = 0** with the corrected
`(?<![a-z0-9_])` leading guard, which is the adopted form (fourth review).
Orthogonal to the scan-surface choice.

> **Selected:** Option A + Option F + Option E — A narrows the scan surface via
> `_section_body` (the helper `check_format_gaps` already calls); F removes the
> substring artifact that the 2026-08-19 hand-check proved A alone leaves behind
> (5 of A's 6 survivors are false positives); E makes the class non-gating
> without making it invisible. Option B is rejected outright rather than held
> contingent — the hand-check that would have triggered it has been run and its
> survivors are equally imprecise.

**Recommended**: **Option A + Option F + Option E**. Re-measure with
`ll-issues format-check --all --format json` after each step, but gate
acceptance on the labeled fixture set (see "The metric has no true positives"),
not on the backlog count.

### Additional decisions required

**Decision 1 — Option A's fallback when `## Summary` is absent.** 5 active
issues have no `## Summary` section or an empty one (`ENH-3035`, `EPIC-2149`,
`EPIC-2087`, `FEAT-2379`, `FEAT-3036` — re-confirmed 2026-08-19). Under A the
scan silently degrades to title-only for these.

**Implementation note:** `_section_body` returns **`None`**, not `""`, when the
heading is absent (signature `(content: str, heading: str) -> str | None`). The
obvious `_section_body(content, "Summary").lower()` raises `AttributeError`, and
an unguarded f-string interpolates the literal text `None` into the scan
surface. Whichever branch is chosen must write the fallback explicitly
(`_section_body(content, "Summary") or ""` for A1).

- **A1** — title-only is fine (a doc-only issue announces itself in the title);
  simplest.
- **A2** — fall back to the whole body when `## Summary` is missing, preserving
  today's behavior for those issues.

> **Resolved 2026-08-19 (fifth review): A1.**

**Measured argument for A1, re-measured against the adopted A + F1c rule:**
under A1 none of the 5 fires (**A1 + F1c = 0/40**); under A2 three of them —
`EPIC-2087`, `EPIC-2149`, `FEAT-2379` — immediately refire (**A2 + F1c =
3/40**). So A2 reintroduces 3 of the 35 false positives this issue exists to
remove, in exchange for preserving behavior nobody wants. This replaces the
original rationale ("EPICs are never doc-only in practice"), which sits
awkwardly beside the hand-check finding that **4 of Option A's 6 false
positives are EPICs**.

**Note on the provenance of the "3" (fifth review).** The third review recorded
this number while measuring with the *old substring* matcher, where A2 actually
refires **4** — `FEAT-3036` as well. The recorded three IDs are correct for the
**adopted** F1c rule and wrong for the matcher they were measured with; F1c
drops `FEAT-3036` back below threshold. The conclusion is unchanged and in fact
strengthened (A1 lands at 0 either way), but do not reuse the "3" as evidence
about any pre-F1c variant.

A1 must be pinned by a test; today nothing covers it (see Implementation Steps
step 8).

**Decision 2 — delete `infer_testable` rather than keep it in lockstep.**
`infer_testable` (`issue_parser.py:1850-1862`) has **zero production callers** —
a repo-wide search finds only its own tests (`test_issue_parser.py:4098-4136`),
`skills/format-issue/SKILL.md:176` naming it in prose, and
`docs/reference/CLI.md:2069` naming it in prose. The Call Path section below
frets that its two entry points are "kept in sync only by convention"; deleting
the unused one collapses that risk to nothing and removes a second surface to
update. The two branches considered:
- **D1** — delete `infer_testable` and its tests; `check_format_gaps` becomes
  the single call site.
- **D2** — keep it, and change both entry points in lockstep.

> **Resolved 2026-08-19 (fifth review): D1.**

**Zero production callers re-confirmed by full `git grep`.** Every reference is
either the definition, its own tests, or prose. The complete reference set —
larger than the three this section previously listed, and every item is an edit
target or explicitly cleared:

| Reference | Disposition |
|---|---|
| `scripts/little_loops/issue_parser.py:1850` | the definition itself — goes away under D1 |
| `scripts/tests/test_issue_parser.py:4098-4136` (`TestInferTestable`) | the whole class goes away with it |
| `scripts/tests/test_issue_parser.py:4140-4146` (sibling class docstring) | **rewrite** — see Dependent Files |
| `skills/format-issue/SKILL.md:176` + its 3 mirrors (`.gemini/`, `.kimi-code/`, `.qwen/` `:175`) | **update + regenerate** |
| `docs/reference/CLI.md:2069` | **update** |
| `.issues/…/P2-ENH-2946-*.md:60,176,211,221` | **cleared** — ENH-2946 is `done` |
| `.issues/…/P3-ENH-2971-*.md:123` | **cleared** — ENH-2971 is `done` |
| `.ll/decisions.d/7920ac07-*.json:7` | **cleared** — historical decision rationale, append-only; never edit |

The two sibling *issue* files are the reason this was worth re-checking: had
either been open, deleting `infer_testable` would have stranded an active
issue's Program Design on a function that no longer exists. **Both are `done`,
so their references are historical records and need no coordination** — but note
that ENH-2946 is this issue's `relates_to` target and its `:221` paragraph is
written entirely on the two-call-path premise D1 removes. Leave it; it documents
what was true when that issue shipped.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — the scan-surface construction in
  `check_format_gaps` (`L992-1001`) for Option A; the matcher body of
  `_count_testable_keyword_matches` (`L1844-1847`) for Option F;
  `_TESTABLE_SIGNAL_KEYWORDS` (`L1828-1840`) and `_TESTABLE_KEYWORD_THRESHOLD`
  (`L1841`) are **unchanged** under the adopted A + F + E (they change only
  under the rejected B/C); a new `_ADVISORY_GAP_CLASSES` constant and
  `FormatGaps.has_blocking_gaps` property beside `has_gaps` (`L517-544` —
  **corrected**, was cited as `L518-531`; the property now spans 25 fields, and
  `QuestionGaps` carries a second, unrelated `has_gaps` at `L609` that must not
  be touched) for Option E; `infer_testable` (`L1850-1862`) — deleted under
  Decision D1.
- `skills/format-issue/SKILL.md:174-188` — the "Testable Inference" section.
  Its prose says the match runs "against title + body" (`L186-187`), which
  Option A makes wrong. It also names `infer_testable` (`L176`), which
  Decision D1 removes.
- `skills/capture-issue/SKILL.md:233-237` — Phase 4 step 2 lists all 11
  keywords and the 2+ threshold and instructs the model to **re-scan** them at
  capture time. Note this already **contradicts** `format-issue/SKILL.md:177`
  ("do not re-scan for keywords here") — a pre-existing inconsistency to
  resolve while here, not just a mechanical keyword-list update.
- `docs/reference/CLI.md:2069-2072` — **third copy of the rule**, documenting
  `infer_testable`'s "signal-keyword tuple, 2+ distinct matches" and the
  advisory's semantics. Was missing from this list. Under Option E its
  "advisory only" wording must also state that it no longer affects exit code.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — **missing from this
  list entirely**, despite being the CLI implementation that actually reads
  `FormatGaps.has_gaps` to decide the process exit code (`cmd_format_check`,
  calls to `check_format_gaps` at `:566,582,612,626`; `has_gaps` checks at
  `:590,660,662`). Tracing its gating logic surfaces a **contradiction with
  this issue's own Program Design claim** (below, `L360-362`) that "the class
  is still reported, just non-gating" under Option E: that claim is only true
  for single-ID `--format json` (`:647-660`, unconditional `payload =
  dict(gaps.to_dict())`). In **single-ID text mode** (`:662-668`), `if not
  gaps.has_gaps: print("...compliant"); return 0` — `_print_gaps` is only
  called in the `else` branch, so a testable-only issue prints "structurally
  compliant" and the testable line never appears. In **`--all` sweep, both
  formats** (`:590-607`), `if gaps.has_gaps: results[info.issue_id] = gaps`
  drops testable-only issues from `results` before either the text loop or
  the `--all --format json` payload — they vanish from the sweep report and
  sweep JSON, not just the exit code. If the intended UX is "always visible,
  just non-blocking" (as Program Design states), this file's gating logic
  needs a change beyond `has_gaps`, not just the `has_gaps` computation
  itself — otherwise "non-gating" silently becomes "invisible" in two of
  three surfaces.
- `docs/reference/API.md:906` — a **fourth prose copy** of the rule (missed
  by the "three prose copies" count in Scope Boundaries), in the
  `check_format_gaps()` docstring's gap-class table: *"the body trips 2+
  doc-only keyword signals... while frontmatter has no explicit `testable:`
  key."* Says "the body" (whole-body scan) — wrong under Option A, needs the
  same title + `## Summary` correction as the other three copies.

_Second pre-implementation review, 2026-08-19 — three more edit targets:_
- **Host adapter mirrors of the two skills.** `skills/format-issue/SKILL.md`
  and `skills/capture-issue/SKILL.md` are mirrored **git-tracked and verbatim**
  into `.gemini/skills/`, `.kimi-code/skills/`, and `.qwen/skills/`. So the
  "four prose copies" are really four sources **plus six mirrors**. Critically,
  the `VERBATIM_MIRRORS` pin list in
  `scripts/tests/test_wiring_skills_and_commands.py:378-386` covers only
  `wire-issue`, `manage-issue`, and `explore-api` — **no test catches
  `format-issue`/`capture-issue` body drift**, so a missed mirror ships
  silently. Regenerate rather than hand-edit:
  `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply`.
- `scripts/little_loops/cli/issues/format_check.py:486-488` —
  `cmd_format_check`'s `Returns:` block states *"0 when structurally compliant
  …, 1 when gaps were found"*. Under Option E that is **factually wrong**, not
  merely stale: an advisory-only issue has gaps and exits 0. This is a contract
  statement and must be rewritten, not filed under the "low risk, check for
  staleness" note below.
- `scripts/little_loops/cli/issues/format_check.py:480-482` — the `_print_gaps`
  contract comment: *"a class counted by `has_gaps` but not rendered exits 1
  with an empty report (the `testable` regression, ENH-2946)"*. The
  `has_gaps` → exit-1 implication it asserts stops holding under Option E;
  reword to name `has_blocking_gaps` as the exit predicate while keeping the
  render-parity requirement it exists to state.

### Dependent Files
- `scripts/tests/test_issue_parser.py:4097-4136` — `TestInferTestable`'s
  true/false unit tests. Under Decision D1 these are deleted with the function;
  under D2 both fixtures need revisiting.
- `scripts/tests/test_issue_parser.py:4140-4146` — **added by the fourth
  pre-implementation review; a missed D1 edit target.**
  `TestCheckFormatGapsTestablePopulation`'s class docstring is written entirely
  around the two-entry-point premise: *"Distinct code path from TestInferTestable
  above: check_format_gaps re-derives its own scan_text and threshold check
  inline rather than calling infer_testable() (issue_parser.py:489-498 vs
  :528-540) — the two call sites share only the keyword tuple and threshold
  constant."* Under D1 there is no second call site and no `TestInferTestable`
  class to be distinct from, so the whole paragraph becomes false; its line
  citations (`:489-498`, `:528-540`) are already stale besides. Rewrite it —
  deleting `TestInferTestable` without touching this docstring leaves a dangling
  reference to a class that no longer exists.
- `scripts/tests/test_ll_issues_format_check.py:2590-2674`
  (`_DOC_ONLY_BODY` / `TestFormatCheckTestableRendering`) — the regression
  anchor. **Verified to survive every option**, including A+B and A+F: its
  title ("Fix broken link in the docs guide") and Summary ("The documentation
  guide has a broken link and a typo in the readme") score 4 restricted to
  title + Summary. It must not be weakened.

  **Correction 2026-08-19 — there are three `== 1` assertions in this class,
  not one.** The previous note ("its `assert result == 1` will need to change")
  undercounts:
  - `test_testable_gap_is_printed_in_text_mode:2645` — `assert result == 1`.
  - `test_text_output_reports_every_class_json_reports:2653` — `assert
    _invoke([*argv, "--format", "json"]) == 1`.
  - `test_text_output_reports_every_class_json_reports:2660` — `assert
    _invoke(argv) == 1`.

  All three run against a testable-only fixture and all three flip to `== 0`
  under Option E. **Preserve the second test's substance deliberately**: its
  json/text parity assertion (every class present in the JSON payload must also
  appear in the text report) is precisely the "non-gating ≠ invisible" property
  Option E must not break — change only its exit-code expectations, never its
  parity check.
  `test_every_format_gaps_field_is_rendered:2676-2699` asserts
  `FormatGaps`-fields ↔ `_print_gaps` parity and is unaffected by Option E
  (which adds no field).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml:100-121` — the
  `ensure_formatted` state runs `ll-issues format-check "$ID"` with
  `evaluate: type: exit_code`, routing `on_yes: assess` / `on_no:
  format_issue`. Under Option E a testable-only issue currently routes to
  `format_issue` (`/ll:format-issue --auto`) and will instead flow straight to
  `assess` — a real routing-behavior change to this loop, not just a metric
  shift. The state's own comment block already omits `testable` from the gap
  classes it names as gated, so no comment text becomes wrong, but the
  behavior does change silently unless this is verified as intended.
- `skills/confidence-check/SKILL.md:138` — calls `ll-issues format-check
  --format json` and consumes the JSON payload; confirm it does not read
  `has_gaps` directly in a way Option E's change would silently affect.
- `scripts/little_loops/cli/issues/format_check.py:63-70,472-482` — CLI
  `--help` text and `cmd_format_check`'s own docstring both enumerate
  `testable` among the gap classes with no gating/non-gating distinction;
  low risk, but check for staleness after Option E lands. (The `Returns:` block
  and `_print_gaps` contract comment in the same docstring are **not** low
  risk — see Files to Modify.)

_Second pre-implementation review, 2026-08-19:_
- **Other `format-check` consumers cleared — no action needed.**
  `scripts/little_loops/loops/autodev.yaml:1613` captures
  `ll-issues format-check "$ID" --format json` into a shell variable (with
  `|| echo '{}'`) and reads the `superseded_marker_count` key;
  `scripts/little_loops/loops/refine-to-ready-issue.yaml:316` runs
  `--fix --apply || true` (pass-through, no `evaluate:`) and `:419` pipes
  `--format json` into a `template_placeholders` length count, with an inline
  comment already noting *"cmd_format_check's own exit code is not usable here
  — it returns 1 for ANY gap"*. **None of the three reads the exit code**, so
  Option E cannot affect them. `rn-remediate.yaml`'s `ensure_formatted` is the
  **only** exit-code consumer in the repo; the verification below is the
  complete list, not a sample.
- **Add a guard test for `_ADVISORY_GAP_CLASSES`**: assert every member is a
  real `FormatGaps` field name
  (`{f.name for f in dataclasses.fields(FormatGaps)}`). A typo'd string would
  silently make *nothing* advisory and Option E would be a no-op that still
  passes its other tests. No `has_gaps` ↔ fields parity test exists today —
  only the `_print_gaps` one at
  `test_ll_issues_format_check.py:2676` — so nothing else would catch it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to the section-extractor lead below**: `ll-issues sections`
  (`cmd_sections` in `scripts/little_loops/cli/issues/sections.py:16-48`) is
  **not** an issue-body section extractor — it prints/resolves the path of a
  static per-type template JSON (`{type}-sections.json`) used when
  *scaffolding a new issue*. It never reads an existing issue's markdown body.
  Following this reference would cost the implementer a dead-end.
- **The actual reusable helper** is `_section_body_with_offset(content,
  heading)` / `_section_body(content, heading)`
  (`scripts/little_loops/issue_parser.py:427-475` — **corrected 2026-08-19**;
  the previously cited `:199-223` is now unrelated ID-resolution code) — locates a `^## {heading}$`
  line and returns text up to the next `^## ` line. `check_format_gaps`
  already calls this (`body = _section_body(content, name)`) for its
  `empty`/`boilerplate`/`program_design_nonspecific` gap checks, so
  `_section_body(content, "Summary")` is the same-pattern call to reuse for
  Option A — no new regex, no new module. **Confirmed 2026-08-19**: the
  Option A / A+B fire counts in Proposed Solution were measured using exactly
  this helper, so the numbers reflect the real implementation, not an
  approximation. It returns **`None`** for a missing heading (not `""`, as this
  section previously stated) — hence Decision 1, and see the implementation note
  there.
- Two other section-splitting implementations exist elsewhere in the codebase
  (`issue_history/doc_synthesis.py:104-127`'s `_extract_section`, and
  `issue_parser.py:662-677`'s `_iter_h2_sections` for multi-section
  enumeration) but neither is what `check_format_gaps` itself already uses —
  `_section_body` is the one already in the same call path.
- **Pre-existing scope discrepancy** (independent of this issue, but relevant
  context): both `skills/format-issue/SKILL.md:174-176` and
  `skills/capture-issue/SKILL.md:233-235` (**corrected 2026-08-19**; `:261-263`
  is an unrelated `append-log` snippet) already describe the scan surface
  as "title + description text," not "title + entire body" — the Python
  implementation (`scan_text = f"{title}\n{_strip_fm(content)}"`,
  `issue_parser.py:496`) already scans more than either skill's prose
  documents. The skills and the code disagree *today*, before any fix here.
- **Test coverage gap**: neither `test_issue_parser.py:4097-4136`
  (`TestInferTestable`) nor `test_ll_issues_format_check.py`'s `_DOC_ONLY_BODY`
  fixture (line **2590**) places any keyword hits outside the title/`##
  Summary` — every existing assertion passes unchanged whether the scan
  surface is the whole body or just title+Summary. Applying Option A alone
  would not fail any current test, but no current test would catch a
  regression in the narrowing either; a new case (keyword hits only in a
  later section like Impact/Steps to Reproduce, with title+Summary
  keyword-free) is needed to actually pin the Option A behavior change.
  (**Citations corrected 2026-08-19**: this bullet previously cited
  `:3950-3989` and `960-991`, contradicting the correct `:4097` / `:2590`
  anchors used elsewhere in this issue.)
- For Option D (negative signals), no `_has_code_signals`-shaped helper
  exists anywhere in the codebase today. The closest prior art `check_format_gaps`
  already imports from a sibling module for a similar purpose is
  `program_design.py`'s `grade_issue_section`/`DesignVerdict` (wired in at
  `issue_parser.py:446-451` for the `program_design_nonspecific` gap) and
  `text_utils.py:14-90`'s `extract_file_paths` (path detection, not `def
  `/`class ` keyword detection) — Option D would compose from these, not
  start from scratch.

_Wiring pass added by `/ll:wire-issue`:_
- **A test not previously flagged will break silently under Option E**:
  `scripts/tests/test_issue_parser.py:4139-4196`
  (`TestCheckFormatGapsTestablePopulation`, distinct from `TestInferTestable`)
  — `test_doc_only_issue_reports_testable_gap` (`:4148-4163`) asserts
  `gaps.has_gaps is True` for a fixture whose only gap is `testable`. That
  assertion fails once `testable` is dropped from `has_gaps`; the sibling
  `issue_file.name in gaps.testable` assertion still passes unchanged.
- ~~`scripts/tests/test_issue_parser_properties.py` and
  `scripts/tests/test_issue_parser_unresolved.py`~~ — **cleared 2026-08-19**.
  `test_issue_parser_properties.py` touches `testable` only as a frontmatter
  field in a round-trip property (`:102,140,175,210`), never the inference or
  the scan surface; `test_issue_parser_unresolved.py` has no `testable`
  reference at all. Neither is affected by Option A or E; no action needed.
- `scripts/tests/test_builtin_loops.py:1835-1858,7178-7187` — validate loop
  states (`normalize_structure`, `check_reconcile_needed`) that consume
  `format-check`'s exit code / JSON output; confirm neither depends on
  `testable`'s current contribution to `has_gaps`.
- **Concrete pattern precedent for Implementation Steps 7-8's new regression
  tests** (renumbered from 6-7 by the third review): two established section-scoping test
  shapes already exist and should be followed rather than inventing a new
  one — `TestStaleSymbolRefScoping`
  (`scripts/tests/test_feat3048_symbol_cli_claim_gaps.py:229-284`, uses a
  `_write_scoped_issue`/`_SCOPE_TEMPLATE` helper, one test method per
  section, including a negative control in an arbitrary unlisted heading to
  prove allowlist-not-denylist semantics) and
  `TestMissingBehaviorParity.test_no_gap_outside_scope_sections`
  (`scripts/tests/test_ll_issues_format_check.py:1018-1038`, string-replace
  on a `_CLEAN_BUG_BODY` constant, CLI-integration level). Both already use
  `_section_body` as the shared primitive — the same helper this issue plans
  to reuse for `testable`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-19.

**Selected**: Option A — Narrow the scan surface to title + `## Summary` only — paired with the two orthogonal options **F** (word-boundary matching, added 2026-08-19 by the third review) and **E** (demote `testable` to a non-gating advisory). Adopted combination: **A + F + E**.

**Reasoning**: Option A meets the issue's stated single-digit fire-count target on its own (35 → 6 of 40 scanned) by reusing `_section_body` (`issue_parser.py:427-475`) — the exact helper `check_format_gaps` already calls for its other gap classes, and the identical pattern two other gap classes (`missing_behavior_parity`, `stale_symbol_ref`) already implement as a section-name allowlist. Option C (30 fires) leaves the structural false-positive source — the template's own `## Related Key Documentation` heading — intact, since it does not narrow the scan surface that heading lives in. Option D has no existing lightweight helper matching its required flat-text signature and is unmeasured against the backlog. Option E is orthogonal and composable with A, and is adopted alongside it per the issue's own recommendation rather than scored as a competing alternative.

**Amended 2026-08-19 (re-measurement):** the original reasoning called A "the only option that meets the target," on the strength of B measuring 14. Re-measurement puts **B at 6 — tied with A**, so that discriminator no longer holds and the selection rests entirely on the remaining grounds: A reuses an existing in-call-path helper and follows an established two-gap-class precedent, whereas B is an unprincipled keyword-list trim that leaves the whole-body surface (and thus the template-heading false positive) structurally intact — it merely stops *counting* the heading's words. A and B cannot be combined (A+B = 0 fires). **The selection of A stands.**

**Amended 2026-08-19 (hand-check + Option F):** step 4's hand-check of A's 6
survivors has now been performed rather than deferred, and **5 of the 6 are
false positives** (see Proposed Solution § Hand-check). Two consequences for
this decision:

1. **A is retained but is no longer sufficient.** Its selection grounds —
   `_section_body` reuse, established two-gap-class precedent, removing the
   `## Related Key Documentation` structural hit — are all unaffected by the
   hand-check. What the hand-check falsifies is the *fire-count target* as a
   proxy for precision, not A's implementation fit.
2. **Option F (word-boundary matching) is added and adopted alongside A and
   E.** A's residual false positives are driven by bare-substring `doc`
   matching inside `documentation` / `docs` / `docs/guides/…`, not by the scan
   surface; A + F measures **1 fire** (**0** with the corrected `_` guard the
   fourth review adopted). F was previously excluded by Scope
   Boundaries on the premise "narrowing the surface is sufficient," which the
   hand-check disproves. F is orthogonal to A in the same way E is — it changes
   *how* a keyword matches, not what is scanned or whether the class gates.

**B is now rejected outright** rather than held as a contingent alternative:
the hand-check that step 4 said would trigger it has been run, and B's own 6
survivors (`ENH-2923`, `EPIC-1463`, `EPIC-2178`, `EPIC-3154`, `FEAT-2186`,
`FEAT-2261`) are no more precise while leaving the whole-body surface intact.
**Adopted: A + F + E.**

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Narrow scan surface | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| B — Tighten keyword list | 3/3 | 3/3 | 3/3 | 0/3 | 9/12 |
| C — Raise threshold | 2/3 | 3/3 | 2/3 | 0/3 | 7/12 |
| D — Negative signals | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |
| E — Demote to non-gating | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| F — Word-boundary matching | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence** (fire counts corrected 2026-08-19; denominators are the 40
scanned issues, not the full active corpus):
- A: `_section_body` reuse score 3/3 — two existing gap classes (`_behavior_parity_scope_text`, `_symbol_claim_scope_text`) already implement the identical section-allowlist pattern; measured **6/40** fires, of which **5 are false positives** (hand-checked 2026-08-19) — hits the count target, misses precision.
- B: pure data-tuple edit (reuse score 3/3), measured **6/40** — ties A on fire count, but does not narrow the scan surface, so the template-heading false positive survives structurally; combined with A over-corrects to 0/40. **Rejected** after the hand-check (previously held as a contingent alternative).
- F: single-regex edit inside `_count_testable_keyword_matches`, no change to the keyword tuple, threshold, or call graph; measured **A + F = 1/40**, and **A + F′ = 0/40** with the corrected `(?<![a-z0-9_])` leading guard (fourth review — the lone survivor was a false positive produced by the guard's `_` hole). Risk 2/3 rather than 3/3 because the trailing `(?![a-z])` guard also drops plural forms (`guides`, `typos`) — recorded as sub-decision F1.
- C: cheapest mechanical edit but simulation shows it barely moves the fire rate (**35→30/40**) because the false positives are structural to the scan surface, not the threshold.
- D: no existing `_has_code_signals`-shaped helper; the closest prior art (`grade_program_design`) requires a git-grep resolver a flat-text signature can't supply — highest effort, unmeasured.
- E: no existing gating/non-gating split inside `FormatGaps` to copy. Scoped at decision time as "a single self-contained `has_gaps` edit"; the wiring pass showed that is insufficient (it makes `testable` invisible, not just non-gating), so the adopted shape is a `has_gaps` / `has_blocking_gaps` split — still small and self-contained, but touching **six** call sites in `format_check.py` (`:589`, `:593`, `:606`, `:660`, `:662`, `:668`) rather than one property; **corrected 2026-08-19** from "five", and two of the exit-code sites turn out not to be `has_gaps` expressions at all (see Program Design). Existing tests to update: the **three** `== 1` assertions in `TestFormatCheckTestableRendering`, plus `test_doc_only_issue_reports_testable_gap`'s `has_gaps is True`.

## Program Design

### Types

**No new dataclass.** Option A is a tuning change to one scan-surface
expression. Option E adds one module-level constant, not a type:

```python
# issue_parser.py, beside FormatGaps
_ADVISORY_GAP_CLASSES: frozenset[str] = frozenset({"testable"})
```

Introducing a dataclass for either would be over-structure.

### Signatures

`_count_testable_keyword_matches(text: str) -> int` (`issue_parser.py:1844`)
keeps its shape. What changes is what it is fed:

- The scan-surface expression in `check_format_gaps` (`L992-1001`) — currently
  `f"{title}\n{_strip_fm(content)}"`. Under Option A this becomes title +
  `## Summary` body only, reusing `_section_body` (see Research Findings), with
  an explicit `or ""` for the `None` return. The no-`## Summary` fallback is
  Decision 1 above.
- `_TESTABLE_SIGNAL_KEYWORDS: tuple[str, ...]` — unchanged under the
  recommendation; under Option B drop bare `doc`, `docs`, `guide`.

**Option F — one regex, same signature.** `_count_testable_keyword_matches`
(`issue_parser.py:1844-1847`) keeps `(text: str) -> int`; only its body changes:

```python
# was: return sum(1 for kw in _TESTABLE_SIGNAL_KEYWORDS if kw in lowered)
return sum(
    1
    for kw in _TESTABLE_SIGNAL_KEYWORDS
    if re.search(rf"(?<![a-z0-9_]){re.escape(kw)}(?![a-z])", lowered)
)
```

**Corrected 2026-08-19 (fourth pre-implementation review) — the leading guard
must exclude `_`.** The previously recorded expression used `(?<![a-z0-9])`,
which is the variant behind the "A + F = 1 fire" number. That variant is wrong,
and its single survivor is the proof: `EPIC-3217`'s two hits are `docs` **and
`guide`**, both drawn from one path citation —

```
docs  →  ' the documented copy-paste examples in `docs/guid…'
guide →  '…AUTOMATIC_HARNESSING_GUIDE.md` — so the shape '
```

(Both hits come from `EPIC-3217`'s single citation of
`docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, lowercased by the matcher.)

`_` is not in `[a-z0-9]` and `.` is not in `[a-z]`, so `guide` matches inside
`..._GUIDE.md`. Two statements in the previous revision of this section were
therefore false and are corrected below: the path fragment scores **2**, not 1,
and `ll_doc2` is **not** blocked (`subdoc` is). Adding `_` to the class closes
both holes. **Re-measured with the corrected guard: A + F = 0 fires of 40** (see
Implementation Steps step 5 for why 0 is the expected, correct outcome here and
not the A + B over-correction).

Both guards are load-bearing:

- Leading `(?<![a-z0-9_])` — blocks matches inside an identifier or an
  underscore-separated filename (`subdoc`, `ll_doc2`,
  `HARNESS_OPTIMIZATION_GUIDE.md`). **The `_` is the load-bearing character**:
  without it, every `*_GUIDE.md` / `*_README.md` citation still scores a hit.
- Trailing `(?![a-z])` — blocks a keyword matching the head of a longer word.
  `doc` no longer matches `documentation` or `docs`, so the single word
  `documentation` scores **1**, not 2.
- `/`, `.`, and `-` are still not letters, so `docs` alone still matches inside
  the path `docs/guides/…`. The path fragment therefore contributes **1**
  (`docs` only — `doc` blocked by the trailing guard, `guide` by the leading
  one in `_GUIDE.md` and by the trailing one in `guides`), not the 3 it
  contributes today.
- **Corrected 2026-08-19 (fifth review): keywords containing a space are
  _not_ unaffected.** The previous revision claimed `broken link` / `fix link`
  are untouched. That is true of the *leading* guard only — the *trailing*
  `(?![a-z])` blocks their plurals exactly as it blocks single-word plurals,
  because `s` is in `[a-z]`. `broken links` scores 0 against the `broken link`
  keyword. See sub-decision F1, where this is now load-bearing.

Precompile the 11 patterns into a module-level tuple beside
`_TESTABLE_SIGNAL_KEYWORDS` rather than calling `re.search` with an f-string
pattern per keyword per call — an `--all` sweep otherwise recompiles 11 patterns
per issue. The function stays four lines.

**Sub-decision F1 — plural handling. Rewritten 2026-08-19 (fifth review): both
previously recorded branches are wrong, and a third is added and adopted.**

The trailing `(?![a-z])` means `guide` misses `guides`, `typo` misses `typos`,
`readme` misses `readmes` — **and `broken link` misses `broken links`, `fix
link` misses `fix links`, `broken anchor` misses `broken anchors`.** The
multi-word keywords are the *highest*-signal members of the tuple, so calling
every plural loss "a low-signal keyword" (the F1a rationale) was false.

Measured consequence — a textbook doc-only title, scored against title +
`## Summary`:

| Fixture | F1a | F1b | F1c |
|---|---|---|---|
| *(pos)* "Fix typos and broken links in the guides" | **0 — misses** | 3 | **2 ✓** |
| *(pos)* "Update the READMEs and fix broken links" | **0 — misses** | 2 | **2 ✓** |
| *(pos)* "Update the CHANGELOG and README for the 2.x release" | 2 ✓ | 2 ✓ | 2 ✓ |
| *(pos)* `_DOC_ONLY_BODY` | 6 ✓ | 7 ✓ | 6 ✓ |
| *(neg)* code issue citing `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` | 1 ✓ | **3 — fires** | 1 ✓ |
| *(neg)* code issue whose Summary says `documentation` once | 1 ✓ | 1 ✓ | 1 ✓ |

- **F1a** — accept the plural loss as measured. **Rejected.** It silently
  false-negatives on plural phrasings of the three highest-signal keywords, and
  plural phrasing ("fix broken links", "fix typos") is at least as common in
  issue titles as the singular. Its 0-fire backlog number is unaffected only
  because the backlog contains no such issue today.
- **F1b** — optional trailing `s` on every keyword (`(?:s)?(?![a-z])`).
  **Rejected.** It re-opens the exact hole the `_` guard was added to close:
  `guides` becomes a `guide` hit again, so a `docs/guides/` path ending in
  `_GUIDE.md` scores 3 and the step-3 negative fails. F1b is not a safe toggle
  away from F1a.
- **F1c — optional trailing `s` on the high-signal keywords only**, never on
  `doc`/`docs`/`guide`/`documentation`. *Adopted.*

```python
_PLURAL_SAFE = frozenset(
    {"broken link", "broken anchor", "fix link", "typo", "readme", "changelog"}
)
_TESTABLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(
        rf"(?<![a-z0-9_]){re.escape(kw)}"
        rf"{'s?' if kw in _PLURAL_SAFE else ''}(?![a-z])"
    )
    for kw in _TESTABLE_SIGNAL_KEYWORDS
)
```

`guide` stays plural-blocked deliberately — `guides` is overwhelmingly a path
fragment (`docs/guides/`), not a doc-only signal, which is precisely why F1b
regresses. **Re-measured: A + F1c = 0 fires of 40** (same as F1a), so the
adopted variant costs nothing on the backlog and recovers both plural true
positives on the fixture set.

Pin the chosen variant with fixture tests in both directions: the word
`documentation` alone scores 1 (not 2), and a citation of
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` scores 1 (not 3). **This second
assertion only holds with the corrected `(?<![a-z0-9_])` guard** — under the
previously recorded `(?<![a-z0-9])` it scores 2 and the test fails, which is
exactly the defect the fourth review found. **Under F1b it scores 3 and the
same test fails again** — which is why F1b is rejected rather than offered as a
toggle. Add the two plural positives from the F1 table as assertions too;
they are what distinguishes F1c from the rejected F1a.

**Option E — a two-property split, not a one-line deletion.** Simply dropping
`or self.testable` from `has_gaps` (`L517-544`) makes `testable` *invisible*,
not merely non-gating, because `has_gaps` is overloaded as both the exit-code
predicate **and** the report-inclusion predicate (see the Wiring Phase analysis
of `format_check.py`). Split the two roles:

- `FormatGaps.has_gaps` (`L517-544`) — **unchanged**. Keeps meaning "any gap
  class is non-empty"; remains the *reporting* predicate. (Note `QuestionGaps`
  has its own unrelated `has_gaps` at `L609`; do not edit that one.)
- `FormatGaps.has_blocking_gaps` — **new** property: true when any non-empty
  class is absent from `_ADVISORY_GAP_CLASSES`. This becomes the *exit-code*
  predicate.
- `to_dict` (`L547`) and the `_print_gaps` loop (`format_check.py:421-422`) stay
  as-is, so the class is still rendered.

**Corrected 2026-08-19 — the exit-code call sites are four, not three, and two
of them are not `has_gaps` expressions at all.** The previous list (`:592`
sweep JSON, `:606` sweep text, `:660` single-ID JSON) is not implementable as
written. Verified against live code:

| Site | Current code | Change |
|---|---|---|
| `:590` sweep accumulation | `if gaps.has_gaps: results[...] = gaps` | **unchanged** (inclusion) |
| `:595` sweep JSON return | `return 1 if results else 0` | → `return 1 if any(g.has_blocking_gaps for g in results.values()) else 0` |
| `:607` sweep text return | bare `return 1` | → same `any(...)` expression |
| `:660` single-ID JSON return | `return 1 if gaps.has_gaps else 0` | → `gaps.has_blocking_gaps` |
| `:662` single-ID text early return | `if not gaps.has_gaps:` | **unchanged** (inclusion) |
| `:668` single-ID text final return | bare `return 1` | → `return 1 if gaps.has_blocking_gaps else 0` |

The sweep sites carry no `has_gaps` expression to swap — the exit code is
derived from whether `results` is non-empty, so the fix is an `any(...)` over
the accumulated values, not a property rename.

**`:668` was missing from the previous list entirely, and it is the load-bearing
one.** Single-ID text mode is exactly the surface `rn-remediate.yaml:114-121`
gates on (`ll-issues format-check "$ID"` with `evaluate: type: exit_code`).
Omitting it would have shipped Option E as a no-op for the only consumer the
Wiring Phase identifies.

**Sweep header wording.** With `has_gaps` still driving inclusion, an
advisory-only issue enters `results`, so the sweep prints
`Needs formatting — structural gaps in N/M issue(s):` and then exits 0 — a
report that contradicts its own exit code. Split the count in the header
(blocking vs advisory) or reword; do not fix this by dropping the issue from
`results`, which is the invisibility failure mode this whole split exists to
avoid.

Precedent for the gating/non-gating distinction already exists in prose: the
`superseded_marker_count` comment (`format_check.py:647-656`) reasons explicitly
that a non-gap "must not feed has_gaps (and hence the exit code)". Option E
makes that distinction structural rather than a matter of which fields anyone
remembered to add.

**Blast radius (measured 2026-08-19): 3 issues.** Only 3 active issues are
`testable`-only, so Option E changes the exit code — and the `rn-remediate`
`ensure_formatted` routing — for exactly those 3.

`infer_testable(issue: IssueInfo) -> bool` is **deleted** under Decision D1.

If Option D (negative signals) is adopted, add
`_has_code_signals(text: str) -> bool` alongside the existing counter and
require `count >= threshold and not _has_code_signals(...)`.

### Call Path

**D1 is adopted**, so there is a **single** call path:
`check_format_gaps` → `_count_testable_keyword_matches` → `gaps.testable`,
and (Option E) `gaps.testable` still feeds `has_gaps` → *rendering*, but no
longer feeds `has_blocking_gaps` → exit code.

(Under the rejected D2 the second entry point `infer_testable` → same counter
would survive, and both call sites would have to see the same rule — kept in
sync only by convention. That standing risk is what D1 removes.)

## Implementation Steps

_Revised 2026-08-19 (second pre-implementation review): step 4's hand-check has
already been performed — its "branch to Option B" is deleted and replaced by
Option F, and the acceptance gate is now the fixture set rather than the
backlog count._

1. Baseline: record the current fire count
   (`ll-issues format-check --all --format json`, count non-empty `testable`).
   Expected: **35** (of 40 scanned / 70 active).
2. **No decisions remain open.** All four are resolved as of the fifth review:
   **Decision 1 = A1** (title-only when `## Summary` is absent), **Decision 2 =
   D1** (delete `infer_testable`), **sub-decision F1 = F1c** (selective plural
   matching — see Program Design), **sub-decision N = N1** (pin the two
   ≥2-scoring code-issue negatives as known-fires — see step 3). Implement
   directly; do not re-open these without new measurement.
3. **Build the labeled fixture set first** — this is the acceptance gate, not
   the backlog count (see "The metric has no true positives"). Positives that
   **must** fire: `_DOC_ONLY_BODY` plus at least two more doc-only shapes
   ("Update the CHANGELOG and README for the 2.x release", "Fix typo and broken
   anchor in README"). **Score every positive fixture against the threshold
   before writing it down** — the fourth review found the previously recorded
   first positive ("Update CHANGELOG for the 2.x release") hits exactly **one**
   keyword (`changelog`) against `_TESTABLE_KEYWORD_THRESHOLD = 2`, so it can
   never fire under *any* option in this issue; adding `README` brings it to 2.
   The second positive scores 3 (`typo`, `broken anchor`, `readme`) and is
   correct as written. Negatives that **must not** fire: a code issue citing
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` in its Summary; a code issue
   whose Summary contains the word `documentation` once; an issue carrying the
   standard `## Related Key Documentation` heading and nothing else doc-shaped.
   Every negative here is a real shape drawn from the 35 current fires.

   **Added 2026-08-19 (fifth review) — the negative set as listed does not
   exercise the rule.** All three negatives above score **≤ 1** under
   A + F1c, so every one of them is cleared by the *regex and scan surface
   alone*; `_TESTABLE_KEYWORD_THRESHOLD = 2` and the 11-keyword tuple are never
   tested in the negative direction. That is the same "the metric measures
   something other than precision" failure this issue's third review already
   caught once. Add at least one **discriminating negative** — a code issue
   that legitimately scores ≥ 2 and must still be judged. Two measured shapes:

   - *"The CLI docs and the README drift when the command signature changes"* —
     scores **2** (`docs`, `readme`) → **fires**.
   - *"Add a changelog entry and update the migration guide when the flag
     lands"* — scores **2** (`changelog`, `guide`) → **fires**.

   Both are code work. Neither is fixable by A, F, or F1c: they are threshold /
   keyword-tuple failures, not surface or matcher failures.

   **Resolved 2026-08-19 (fifth review): N1 — accept them as fires and pin them
   as _known-fires_ in the fixture set.** The three branches, measured:

   | Fixture | Score | thr 2 (N1) | thr 3 (N2) |
   |---|---|---|---|
   | *(pos)* "Update the CHANGELOG and README for the 2.x release" | 2 | fires ✓ | **misses** |
   | *(pos)* "Fix typo and broken anchor in README" | 3 | fires ✓ | fires ✓ |
   | *(pos)* `_DOC_ONLY_BODY` | 6 | fires ✓ | fires ✓ |
   | *(pos)* "Fix typos and broken links in the guides" | 2 | fires ✓ | **misses** |
   | *(pos)* "Update the READMEs and fix broken links" | 2 | fires ✓ | **misses** |
   | *(neg)* "The CLI docs and the README drift when the command signature changes" | 2 | fires ✗ | suppressed |
   | *(neg)* "Add a changelog entry and update the migration guide when the flag lands" | 2 | fires ✗ | suppressed |

   **N2 (threshold 3) is rejected on measurement: it loses 3 of 5 positives to
   suppress 2 negatives.** The two negatives score *identically* to three of the
   positives, so no threshold can separate them — at 2 hits the keyword signal
   is genuinely ambiguous, and raising the bar only trades false positives for
   false negatives at a worse ratio. **N3 (Option D negative signals) is the
   only branch that could separate them**, since the discriminator is "does this
   issue name code artifacts," not "how many doc words." It stays out of scope
   (see Scope Boundaries); capture as a follow-up.

   **Why accepting these fires is cheap: Option E already removes their cost.**
   The two harms Motivation names are (a) the advisory fires on 88% of what it
   evaluates, and (b) every false positive fails a gate other tooling consumes.
   A + F1c takes the backlog from 35 fires to **0**, retiring (a); E makes the
   class non-gating, retiring (b) outright. What remains is a rare, non-gating,
   single-line advisory on an issue whose Summary genuinely does discuss two
   distinct documentation artifacts — which is a defensible thing to surface for
   a human to judge, and is the residual this rule is *supposed* to have.

   Pin both negatives as **known-fires** (asserting they *do* fire, with a
   comment naming them as accepted residual imprecision), not as must-not-fires.
   The assertion is a guard against over-correction: it fails loudly if a future
   change tightens the rule into the false-negative regime — the failure mode
   this issue has already flirted with twice (A + B → 0 fires, and F1a/F1b).
4. Apply Option A — narrow the scan surface to title + `## Summary`, reusing
   `_section_body` with an explicit `or ""` for its `None` return. Re-measure;
   expect **6**. The fixture set will still show false positives at this point;
   that is expected and is why step 5 exists.
5. Apply Option F — word-boundary matching in
   `_count_testable_keyword_matches` (see Program Design for the exact regex
   and its two guards, including the `_` in the leading guard). Re-measure;
   expect **0** — and **0 is the correct outcome here, not the A + B
   over-correction the table at the top of Proposed Solution rejects.** Do not
   revert on seeing it. The two are different situations: A + B lands at 0 while
   still counting `documentation` as two hits and still scanning the whole body,
   i.e. it zeroes the count by trimming data rather than by fixing the matcher;
   A + F′ lands at 0 because the backlog's *only* genuinely doc-only issue
   (`ENH-2191`) has never fired under any precise variant — see "The metric has
   no true positives", which already demoted the backlog count to a smoke
   measurement and made the labeled fixture set the acceptance gate. Judge this
   step by step 3's fixtures, which must now all pass in both directions.
   (`EPIC-3217` was A + F's lone survivor under the *uncorrected* guard and is
   itself a false positive; it disappears once `_` is added.) ~~Re-measure;
   expect **1** (`EPIC-3217`)~~ — superseded by the fourth review.
   ~~Hand-check A's 6 survivors and, if they are
   still false positives, apply Option B instead of A~~ — **performed
   2026-08-19; 5 of 6 were false positives and Option B was rejected rather
   than substituted.** Do not re-run this branch.
6. Apply Option E — add `_ADVISORY_GAP_CLASSES` and `has_blocking_gaps`, leave
   `has_gaps` alone, and update the **four** exit-code sites in
   `format_check.py`: `:595` and `:607` (sweep — **line numbers corrected by
   the fifth review from `:593-594`/`:606`, which are off by one to two lines
   against live code; verify by content, not by number** — these are
   `return 1 if results else 0` / bare `return 1`, so they need an
   `any(g.has_blocking_gaps for g in results.values())` expression, **not** a
   property rename), `:660` (single-ID JSON, a real `has_gaps` swap), and
   **`:668`** (single-ID text final return — omitted from the previous
   revision of this step, and the only site `rn-remediate` actually observes).
   Leave `:589` and `:662` on `has_gaps` (inclusion). Fix the sweep header
   wording so an advisory-only sweep does not print "Needs formatting" and then
   exit 0. Update all **three** `== 1` assertions in
   `TestFormatCheckTestableRendering` and
   `test_doc_only_issue_reports_testable_gap`'s `has_gaps is True`, and add a
   test asserting a testable-only issue is **still printed** in single-ID text
   mode and **still present** in the `--all` sweep while exiting 0.
7. Add the missing regression test: keyword hits placed **only** in a later
   section (e.g. Impact or Steps to Reproduce) with a keyword-free title and
   `## Summary` must **not** fire. Without this, Option A's narrowing is
   untested (see Research Findings).
8. Add a test pinning the Decision 1 fallback (issue with no `## Summary`), and
   the `_ADVISORY_GAP_CLASSES` ⊆ `FormatGaps` field-names guard.
9. Update `format-issue/SKILL.md`, `capture-issue/SKILL.md`,
   `docs/reference/CLI.md:2069-2072`, and `docs/reference/API.md:906` in
   lockstep — including resolving the pre-existing re-scan contradiction
   between the two skills — then **regenerate the six host mirrors**:
   `ll-adapt --host gemini --apply && ll-adapt --host kimi-code --apply && ll-adapt --host qwen --apply`.
   No test catches drift in these two skills' mirrors, so a skipped
   regeneration ships silently.
10. Rewrite `cmd_format_check`'s `Returns:` block
    (`format_check.py:486-488`) and the `_print_gaps` contract comment
    (`:480-482`), both of which assert the has-gaps ⇒ exit-1 implication that
    Option E breaks.
11. Confirm `_DOC_ONLY_BODY` still trips, and run the full suite
    (`python -m pytest scripts/tests/`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Decide how `format_check.py` should surface a testable-only issue under
  Option E~~ — **resolved 2026-08-19**, see Program Design § Signatures. The
  analysis was correct: `has_gaps` is overloaded as both the report-inclusion
  and exit-code predicate, so the naive one-line edit makes `testable` invisible
  in single-ID text mode (`:662-664`) and in the `--all` sweep, both formats
  (`:588-590`), leaving only single-ID `--format json` visible. Resolution:
  split the predicates — `has_gaps` (unchanged) keeps driving inclusion,
  a new `has_blocking_gaps` drives the exit code. ~~at `:592`, `:606`,
  `:660`~~ — **that call-site list was wrong; corrected 2026-08-19 to
  `:593-594`, `:606`, `:660`, and `:668`.** Two of them are not `has_gaps`
  expressions at all, and `:668` — single-ID text mode, the only surface
  `rn-remediate` observes — was missing entirely. See Program Design.
- Update `docs/reference/API.md:906` — a fourth prose copy of the rule,
  saying "the body" where Option A requires title + `## Summary`.
- Verify `scripts/little_loops/loops/rn-remediate.yaml`'s `ensure_formatted`
  gate (`:100-121`) — confirm that a testable-only issue no longer routing to
  `format_issue` (routing straight to `assess` instead) is the intended
  outcome of Option E, or adjust the gate.
- Update `scripts/tests/test_issue_parser.py:4148-4163`
  (`test_doc_only_issue_reports_testable_gap`) — its `has_gaps is True`
  assertion breaks under Option E; update while keeping the `testable`
  list-membership assertion.
- Check `skills/confidence-check/SKILL.md`,
  `scripts/tests/test_issue_parser_properties.py`, and
  `scripts/tests/test_issue_parser_unresolved.py` for assumptions tied to
  today's testable behavior.
- Follow `TestStaleSymbolRefScoping`
  (`scripts/tests/test_feat3048_symbol_cli_claim_gaps.py:229-284`) or
  `TestMissingBehaviorParity.test_no_gap_outside_scope_sections`
  (`scripts/tests/test_ll_issues_format_check.py:1018-1038`) as the pattern
  for the new section-scoping regression tests in steps 7-8, rather than a
  novel shape.

_Second pre-implementation review, 2026-08-19 — added:_
- **Regenerate the `.gemini/`, `.kimi-code/`, and `.qwen/` mirrors** of
  `format-issue/SKILL.md` and `capture-issue/SKILL.md` (`ll-adapt --host <h>
  --apply`). Untested surface — `VERBATIM_MIRRORS`
  (`test_wiring_skills_and_commands.py:378-386`) does not cover these two
  skills, so drift ships silently.
- **The `format-check` exit-code consumer list is complete, not a sample.**
  `autodev.yaml:1613` and `refine-to-ready-issue.yaml:316,419` read the JSON
  payload or discard the status (`|| true`); `rn-remediate.yaml:114-121` is the
  only exit-code gate in the repo. No further sweep needed.
- **Rewrite `cmd_format_check`'s `Returns:` block and the `_print_gaps`
  contract comment** — both assert has-gaps ⇒ exit 1, which Option E breaks.
- **Guard `_ADVISORY_GAP_CLASSES` against `FormatGaps` field names** — a typo'd
  member makes Option E a silent no-op that still passes every other test.

## Scope Boundaries

**In scope:**
- The keyword list, threshold, and scan surface for the `testable` inference.
- **Word-boundary matching in place of substring containment (Option F)** —
  **moved in scope 2026-08-19**; see below.
- Whether `testable` contributes to `format-check`'s exit code (Option E).
- Deleting the unused `infer_testable` entry point (Decision 2).
- Keeping `check_format_gaps` consistent with the **four** prose copies of the
  rule (`format-issue/SKILL.md`, `capture-issue/SKILL.md`,
  `docs/reference/CLI.md`, `docs/reference/API.md:906`) **and their six
  host-adapter mirrors** under `.gemini/`, `.kimi-code/`, and `.qwen/`,
  including the pre-existing re-scan contradiction between the two skills.

**Out of scope:**
- The `testable` frontmatter field's *semantics* (`False` skips TDD, `None`
  treated as testable) — unchanged.
- Whether `testable` should be a `format-check` gap class at all — it should;
  this is about precision and gating, not existence. Option E demotes it to
  non-gating; it does not remove it.
- ~~Introducing word-boundary/regex matching in place of substring containment.
  Narrowing the surface (A) is sufficient to hit the target; a matcher rewrite
  is a larger change with its own regression surface.~~ **Reversed 2026-08-19 —
  moved IN scope as Option F.** Both premises failed: (1) the
  hand-check shows A hits the *count* target while leaving 5 of 6 fires false —
  so surface narrowing is not sufficient; (2) it is not a "matcher rewrite" but
  a single `re.search` in one 4-line function, with the keyword tuple,
  threshold, and call graph untouched. `documentation` scoring 2 on its own is
  a defect in the matcher that no scan-surface change can reach.
- **Option D (negative signals) — confirmed out of scope 2026-08-19 (fifth
  review), with a follow-up owed.** Sub-decision N established that two
  realistic code-issue shapes score 2 under the adopted A + F1c and fire, that
  no threshold separates them from genuine doc-only issues at the same score,
  and that Option D's "does this issue name code artifacts" discriminator is
  the only thing that would. N1 accepts those fires as pinned known-fires
  because Option E makes them non-gating. **If the advisory later proves noisy
  again in practice, Option D is the next move — open a follow-up ENH rather
  than reaching for the threshold or the keyword tuple, both of which are now
  measured dead ends.**
- Other `format-check` gap classes.
- ENH-2946's outstanding work (`set-flags`, `format-check --next`, skill
  slimming).

## Impact

- **Priority**: P3 — noise, not breakage. The advisory is correct-by-spec and
  nothing downstream misbehaves; it just wastes attention and erodes trust in
  `format-check`'s output.
- **Effort**: Small-to-Medium — **revised 2026-08-19.** The behavior change is
  three small edits (a scan-surface expression, one regex, one new property),
  but Option E touches six call sites in `format_check.py` plus four test
  assertions, and the doc lockstep is ten files (four prose copies + six host
  mirrors), not four.
- **Risk**: Low-to-Medium — **revised 2026-08-19.** The rule is duplicated in
  **four** prose copies (two SKILL.md files, `docs/reference/CLI.md`,
  `docs/reference/API.md`) **plus six git-tracked host-adapter mirrors** under
  `.gemini/`, `.kimi-code/`, `.qwen/`, and **no test covers mirror drift for
  these two skills** — so a missed regeneration ships silently. That
  duplication is itself the kind of prose-reimplementation
  `ll-verify-skill-prose` (ENH-2951) exists to catch. Option E additionally
  changes `rn-remediate`'s `ensure_formatted` routing for 3 issues; the
  consumer sweep is complete (see Wiring Phase), so that is the whole blast
  radius.
- **Breaking Change**: No — advisory only.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues`:_ Core behavior and premise still accurate —
`_TESTABLE_SIGNAL_KEYWORDS`, `_TESTABLE_KEYWORD_THRESHOLD = 2`,
`_count_testable_keyword_matches`, and the whole-body scan surface
(`scan_text = f"{title}\n{_strip_fm(content)}"`) all still match verbatim.
Line-number citations are stale: the constants and functions now live around
`issue_parser.py:550-716`, not the originally cited `L489-528`.

**2026-08-19** (fifth pre-implementation review): Every metric from the fourth
review independently reproduced against live code — 70 active, 40 scanned, 35
current fires, A = 6 (**the same six IDs**), A + F with the old `(?<![a-z0-9])`
guard = 1 (`EPIC-3217`), A + F′ with the corrected `(?<![a-z0-9_])` guard = 0,
and the 5 no-`## Summary` issues. Two structural claims also cleared: `Summary`
is a `common_sections` member of **all four** type templates (bug/enh/epic/feat),
so Option A's surface does not silently degrade for any issue type; and
`_REPAIR_DISPATCH` (`format_check.py:358-364`) has **no `testable` fixer**, so
`--fix`/`--apply` — including `refine-to-ready-issue.yaml:316` — is untouched by
this issue. `_count_testable_keyword_matches` has exactly the two callers the
issue names. Four changes made:

- **Option F's stated rationale is wrong about multi-word keywords, and the
  error changes the adopted sub-decision.** Program Design claimed *"keywords
  containing a space (`broken link`, `fix link`) are unaffected."* The trailing
  `(?![a-z])` blocks their plurals identically — `broken links` scores 0
  against `broken link`. So F1a's rationale ("every plural loss is a
  low-signal keyword") is false: it loses the three *highest*-signal keywords
  in plural form. Measured — "Fix typos and broken links in the guides", a
  textbook doc-only title, scores **0 under the adopted F1a and would not
  fire.**
- **F1b is not a safe toggle away from F1a.** An unrestricted optional `s`
  makes `guides` a `guide` hit again, so a `docs/guides/` path ending in
  `_GUIDE.md` scores **3** and step 3's own negative fixture fails — reopening
  the exact hole the `_`
  guard was added to close by the fourth review.
- **Sub-decision F1c added and adopted**: optional trailing `s` on the
  high-signal keywords only (`broken link`, `broken anchor`, `fix link`,
  `typo`, `readme`, `changelog`), never on `doc`/`docs`/`guide`/
  `documentation`. Recovers both plural true positives, holds every negative at
  ≤ 1, and re-measures at **A + F1c = 0 fires of 40** — identical backlog cost
  to F1a.
- **Step 3's negative set does not exercise the rule.** All three listed
  negatives score **≤ 1** under A + F1c, so each is cleared by the regex and
  scan surface alone — the threshold and the keyword tuple are never tested in
  the negative direction, which is the same "measuring something other than
  precision" failure the third review caught. Added **sub-decision N** with two
  measured ≥2-scoring code-issue negatives ("The CLI docs and the README
  drift…", "Add a changelog entry and update the migration guide…", both
  scoring 2 and firing) that no option in this issue can fix. **Sub-decision N
  resolved to N1** (pin both as *known-fires*): N2 (threshold 3) measures out
  at **3 of 5 positives lost to suppress 2 negatives** — the negatives score
  identically to three positives, so no threshold separates them — and N3
  (Option D) is the only real discriminator but stays out of scope. Accepting
  the fires is cheap because Option E already makes the class non-gating, which
  was the actual harm Motivation named. Also corrected two sweep line citations
  (`:593-594`→`:595`, `:606`→`:607`).
- **Decisions 1 and 2 pinned; the issue now has no open decisions.**
  **Decision 1 = A1**, re-measured against the *adopted* F1c rule rather than
  the substring matcher its rationale was written from: **A1 + F1c = 0/40**,
  **A2 + F1c = 3/40**. Provenance correction — the third review's "three refire
  under A2" was measured with substring matching, where the true count is
  **4** (`FEAT-3036` as well); the three recorded IDs are right for F1c and
  wrong for the variant they were measured on. Conclusion unchanged and
  strengthened. **Decision 2 = D1**, with zero production callers re-confirmed
  by full `git grep` and the reference set expanded from the three previously
  listed to eight, each dispositioned. The two *issue-file* references
  (ENH-2946, ENH-2971) were the live risk — an open sibling would have been
  stranded on a deleted function — but **both are `done`**, so they need no
  coordination.

**2026-08-19** (fourth pre-implementation review): Every metric from the third
review independently reproduced against live code — 70 active, 40 scanned, 35
current fires, A = 6 (**the same six IDs**), A + F = 1 (`EPIC-3217`),
`_section_body` semantics, and every `issue_parser.py` / `format_check.py` line
citation including the six Option E call sites. Four changes made:

- **Option F's regex is wrong and the error is load-bearing.** The recorded
  `(?<![a-z0-9])` leading guard does not exclude `_`, so `guide` still matches
  inside `HARNESS_OPTIMIZATION_GUIDE.md`. Verified: `EPIC-3217`, A + F's lone
  survivor, scores 2 entirely from one path citation (`docs` + `guide` from
  `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, lowercased by the matcher). Two
  consequences the previous
  revision got backwards — Program Design claimed that path scores **1** and
  told the implementer to pin it with a fixture, and step 3 listed that exact
  shape as a must-**not**-fire negative; both would have **failed at step 5**.
  The stated rationale was also wrong on its own example: `ll_doc2` is *not*
  blocked by `(?<![a-z0-9])` (`subdoc` is). Corrected to `(?<![a-z0-9_])`
  throughout; re-measured **A + F′ = 0/40**.
- **Step 3's first positive fixture could never fire.** "Update CHANGELOG for
  the 2.x release" hits exactly one keyword (`changelog`) against a threshold of
  2 — unfireable under every option in this issue. Replaced with "Update the
  CHANGELOG and README for the 2.x release" (2 hits). The second positive
  scores 3 and was already correct.
- **Step 5's expected value restated 1 → 0, with the reversion trap called
  out.** An implementer landing on 0 would otherwise read the option table's
  "A + B overshoots to zero" and revert a correct change. The two zeros are
  different: A + B removes data (still scores `documentation` as 2, still scans
  the whole body), A + F′ removes the defect, and the backlog's one genuine
  doc-only issue (`ENH-2191`) fires under no precise variant regardless — which
  the third review already established when it made the fixture set the
  acceptance gate.
- **One missed D1 edit target added**: `test_issue_parser.py:4140-4146`,
  `TestCheckFormatGapsTestablePopulation`'s class docstring, is written entirely
  around the two-entry-point premise and names `TestInferTestable` — the class
  D1 deletes. Also noted: precompile F's 11 patterns at module level rather than
  rebuilding them per keyword per call.

**2026-08-19** (third pre-implementation review): Every metric from the second
review independently reproduced against live code — 35 fires / 40 scanned / 3
testable-only (`ENH-2923`, `EPIC-2856`, `FEAT-2123`), A = 6, B = 6, A+B = 0,
`_section_body` returning `None`, all 5 no-`## Summary` issues, and every line
citation. Active corpus is **70** today, not 71 (drift; the 40-scanned
denominator is unchanged). Seven changes made:

- **Option E's call-site plan did not match the code.** The recorded list
  (`:592`, `:606`, `:660`) is not implementable: `:593-594` is
  `return 1 if results else 0` and `:606` is a bare `return 1` — neither is a
  `has_gaps` expression, so both need an `any(g.has_blocking_gaps …)` over the
  accumulated results. **`:668`, the single-ID text-mode final `return 1`, was
  missing entirely** — and it is the only surface `rn-remediate.yaml:114-121`
  observes, so Option E as previously written would have been a no-op for its
  one consumer. Also flagged: with `has_gaps` still driving inclusion, the
  sweep prints "Needs formatting" and exits 0 for an advisory-only issue.
- **Step 4's hand-check was performed rather than deferred, and Option A
  fails it** — 5 of its 6 survivors are code issues that merely cite a
  `docs/…` path (only `ENH-2191` is genuinely doc-only). The step's "branch to
  Option B" was a trap: B's own survivors are equally imprecise. Branch deleted.
- **Option F (word-boundary matching) added and adopted.** A's residual false
  positives are driven by bare-substring `doc` matching inside `documentation`
  / `docs` / `docs/guides/…`. Measured **A + F = 1 fire**; two cheaper
  near-equivalents (drop bare `doc`; threshold 3) land at the same 1 but leave
  substring semantics in place. Scope Boundaries' exclusion of word-boundary
  matching is reversed — both of its stated premises failed.
- **Acceptance criterion changed from backlog fire count to a labeled fixture
  set.** The active corpus contains ~1 genuinely doc-only issue, and it drops
  out of every precise variant, so "single-digit but not zero" is an arbitrary
  proxy: 6 fires with 5 false positives carries the same information as 0.
  `_DOC_ONLY_BODY` is currently the only true positive in the repo.
- **Test breakage undercounted.** `TestFormatCheckTestableRendering` has
  **three** `== 1` assertions (`:2645`, `:2653`, `:2660`), not one — the second
  test asserts exit 1 in both JSON and text mode. Its json/text parity check
  must be preserved deliberately: it is exactly the "non-gating ≠ invisible"
  property Option E must not break.
- **Three edit targets added.** (1) The two skills are mirrored git-tracked
  into `.gemini/`, `.kimi-code/`, and `.qwen/`, and `VERBATIM_MIRRORS`
  (`test_wiring_skills_and_commands.py:378-386`) does not cover them — so
  nothing catches drift; regenerate with `ll-adapt --host <h> --apply`.
  (2) `cmd_format_check`'s `Returns:` block (`:486-488`) and (3) the
  `_print_gaps` contract comment (`:480-482`) both assert has-gaps ⇒ exit 1,
  which Option E makes false. Also added: a guard test that
  `_ADVISORY_GAP_CLASSES` ⊆ `FormatGaps` field names (a typo'd member makes
  Option E a silent no-op; no `has_gaps`↔fields parity test exists).
- **Consumer sweep completed and citations corrected.** `autodev.yaml:1613`
  and `refine-to-ready-issue.yaml:316,419` read the JSON payload or discard
  the status — `rn-remediate` is the *only* exit-code consumer in the repo.
  `has_gaps` spans `L517-544`, not `L518-531`, and `QuestionGaps` carries a
  second unrelated `has_gaps` at `L609`. Two internally contradictory
  citations fixed (`TestInferTestable` `:3950-3989` → `:4097`;
  `_DOC_ONLY_BODY` `960-991` → `2590`). Decision 1's rationale replaced with a
  measured one: A2 would refire `EPIC-2087`, `EPIC-2149`, `FEAT-2379`.

**2026-08-19** (second pre-implementation review): Every metric re-measured
against live code by two independent methods — the `ll-issues format-check
--all --format json` sweep the issue names as its reproduction, and a direct
`_section_body`-based simulation. **The two agree with each other and disagree
with the previously recorded numbers.** Changes made:

- **Corpus restated**: 125 active → **71 active**, of which 31 carry an
  explicit `testable:` key, leaving **40 scanned**. The old 125 denominator
  included `deferred` issues, which `cmd_format_check --all` never scans
  (`find_issues(config)` defaults to open/in_progress/blocked).
- **Fire counts restated**: current 80 → **35**; A 9 → **6**; B 14 → **6**;
  C 70 → **30**; A+B **0** (unchanged, confirmed). The headline framing changes
  from "64% of the corpus" to "**88% of what the rule actually evaluates**" —
  a stronger statement of the same problem.
- **Decision Rationale amended**: B now ties A at 6 fires, so "A is the only
  option that meets the target" no longer holds. The selection of A stands on
  helper reuse and the structural-vs-cosmetic distinction instead; recorded
  inline in Decision Rationale.
- **`_section_body` returns `None`, not `""`**, for a missing heading — this
  section previously asserted `""`. The naive call raises `AttributeError`;
  Decision 1 now carries an explicit implementation note.
- **Option E specified concretely**: the wiring pass's contradiction is resolved
  with a `has_gaps` / `has_blocking_gaps` split plus `_ADVISORY_GAP_CLASSES`,
  rather than the one-line `or self.testable` deletion (which would make the
  class invisible in two of three output surfaces). Blast radius measured: only
  **3** active issues are testable-only.
- **Citations refreshed**: `_section_body` `:199-223` → **`:427-475`**;
  `capture-issue/SKILL.md` `:261-263` → **`:233-235`**. All other citations
  (constants `1828-1847`, scan surface `992-1001`, `infer_testable`
  `1850-1862`, `has_gaps` `518-531`, all six test anchors, `API.md:906`,
  `CLI.md:2069`) re-verified as correct.
- **Wiring check cleared**: `test_issue_parser_properties.py` /
  `test_issue_parser_unresolved.py` confirmed unaffected — struck from the
  verify list.
- `infer_testable`'s zero production callers re-confirmed (Decision D1 stands),
  as were the 5 no-`## Summary` issues named in Decision 1.

**2026-08-19** (pre-implementation review) — _**numbers in this entry are
superseded by the second review above**; retained for provenance. Its
conclusions (A alone + E, Decisions 1 and 2) all still stand._ Premise
re-verified against live code and re-measured against the backlog. Changes
made:

- Fire count restated 36/58 (62%) → **80/125 (64%)**; all line citations
  refreshed (constants `1828-1847`, scan surface `992-1001`, `infer_testable`
  `1850-1862`, `has_gaps` `518-531`, tests `4098-4136` and `2590-2650`).
- Root cause restated as **structural, not prose drift**: substring matching
  makes the single word `documentation` score 2, and the standard template's
  own `## Related Key Documentation` heading score 2 — **48 of 125 active
  issues fire from that heading alone**.
- All four options simulated. **The previously recommended A+B yields 0 fires**
  — over-corrects into a dead rule. Recommendation changed to **A alone (9
  fires)**, with B held as a contingent follow-up.
- Added **Option E** (demote `testable` out of `has_gaps` so it stops failing
  the gate) — Motivation named this harm but no option addressed it.
- Added **Decision 1** (Option A's fallback for the 5 active issues with no
  `## Summary`) and **Decision 2** (`infer_testable` has **zero production
  callers**; delete rather than maintain in lockstep).
- Added `docs/reference/CLI.md:2069-2072` as a third prose copy of the rule,
  missing from Files to Modify; flagged the pre-existing contradiction where
  `capture-issue/SKILL.md` tells the model to re-scan keywords while
  `format-issue/SKILL.md` says not to.
- Confirmed `_DOC_ONLY_BODY` survives every option (scores 4 under A+B), so the
  regression anchor holds regardless of choice.

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: logic unchanged
(`_TESTABLE_SIGNAL_KEYWORDS`, `_TESTABLE_KEYWORD_THRESHOLD = 2` confirmed
verbatim in issue_parser.py), but cited line numbers have drifted again — code
is now around lines 976-1010, not the ~550-716 previously noted. Cosmetic
only; core claim and fix options remain accurate.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and ENH-3000 both modify `check_format_gaps` in `scripts/little_loops/issue_parser.py` for unrelated gap classes (testable-keyword scan surface vs. a new `stale_file_ref` verdict branch). Coordinate implementation order to avoid a merge collision in the same function.

**Resolved 2026-08-19**: the ENH-3247 collision note previously here is stale —
ENH-3247 is `done`, so there is no longer an ordering constraint against it.
The ENH-3000 note above still stands (ENH-3000 is `open`).

## Session Log
- `/ll:confidence-check` - 2026-08-19T21:37:55 - `cf3e2d12-3055-4e63-9084-0c161f05830e.jsonl`
- `/ll:decide-issue` - 2026-08-19T21:28:42 - `52d05086-bbdc-462a-bb68-03d6d46c8ec9.jsonl`
- `/ll:confidence-check` - 2026-08-19T21:27:27 - `5c491ecb-85ee-4e96-982b-ddd1e098374d.jsonl`
- `/ll:confidence-check` - 2026-08-19T21:11:46 - `269b3d16-be6a-4a46-ae97-70118282e5d4.jsonl`
- `/ll:confidence-check` - 2026-08-19T20:49:56 - `eb8a877e-7bde-4104-acd7-9d002765976f.jsonl`
- `/ll:confidence-check` - 2026-08-19T20:13:52 - `0d2916d2-f9ec-408b-ba0e-bbe68b7d2760.jsonl`
- `/ll:confidence-check` - 2026-08-19T19:57:26 - `bd3f0a41-ce07-4c04-acd5-8a401b968303.jsonl`
- `/ll:wire-issue` - 2026-08-19T19:54:38 - `bd3f0a41-ce07-4c04-acd5-8a401b968303.jsonl`
- `/ll:decide-issue` - 2026-08-19T18:53:08 - `e7d6e805-7841-446d-b324-acab354e3e8f.jsonl`
- `/ll:confidence-check` - 2026-08-19T18:46:55 - `16de750d-d4f0-4fa9-ba37-ac3244bf63ce.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:55 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:45 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
- `/ll:verify-issues` - 2026-08-03T04:54:47 - `d03f8e53-9873-4f8d-8cfd-bbc50704a66b.jsonl`
- `/ll:refine-issue` - 2026-08-01T19:58:05 - `f7d70fe6-d3b1-4443-814c-32eee6e8b043.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:04:25 - `f9ef973a-acd3-40a7-a313-5e7a001f9a16.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
