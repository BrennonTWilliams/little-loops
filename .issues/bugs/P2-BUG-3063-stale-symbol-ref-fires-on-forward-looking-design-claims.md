---
id: BUG-3063
title: stale_symbol_ref fires on forward-looking design claims (46% of active issues)
type: BUG
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T17:52:25Z'
relates_to:
- FEAT-3048
- ENH-3047
- FEAT-2846
labels:
- issues
- gates
- false-positives
testable: true
decision_needed: false
confidence_score: 90
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3063: `stale_symbol_ref` fires on forward-looking design claims

## Summary

FEAT-3048's symbol-claim verifier extracts claims from the **entire** issue body with no section
scoping. Sections whose whole purpose is to name symbols the issue will **create** — `## Program
Design § Signatures`, `### Files to Modify`, `## Implementation Steps` — are read as assertions
that those symbols already exist, and every one of them is reported as a `stale_symbol_ref` gap.

Measured on this repo: **32 of 72 active issues (44%), 94 individual hits**. A full bucketization
of all 94 (see § Measured Baseline) shows **two** roughly equal false-positive classes, not one:
67% resolve nowhere in the repo (forward references and genuinely stale claims, mixed) and 33%
resolve *elsewhere* in the repo (mis-attribution — the symbol exists, just not in the nearest-cited
file). The gap is firing on issues being *well specified*, which inverts what it is meant to signal.

## Current Behavior

`scripts/little_loops/issues/symbol_claims.py` extracts backticked symbol claims across the whole
body. Its false-positive controls are all *intra-sentence*:

- `_BARE_SYMBOL_RE` requires a file attribution (a bare backticked identifier is never a claim)
- `_SENTENCE_BOUNDARY_RE` and `_MAX_ATTRIBUTION_DISTANCE` (80 chars) bound how far a symbol may
  reach for a file path
- `_SUPPORTED_SYMBOL_EXTENSIONS` fails open for unsupported languages

None of these is section-aware. There is no notion of "this section describes future state."

`check_format_gaps()` then reports each unresolved claim as a `stale_symbol_ref` entry, with no
severity or confidence distinction between "this issue asserts a function exists and it does not"
(a real defect) and "this issue plans to add a function" (expected).

## Steps to Reproduce

Both reproductions are against issues already in the repo — no fixture construction needed.

```bash
# 1. Forward-reference class: FEAT-2942 names functions it proposes to ADD.
ll-issues format-check FEAT-2942 --format json \
  | python3 -c "import json,sys; print('\n'.join(json.load(sys.stdin)['stale_symbol_ref']))"
# Observed: 6 entries, including two functions FEAT-2942's own Program Design
# section proposes to create in cli/issues/__init__.py.
# Expected: those two not reported.

# 2. Mis-attribution class: symbol resolves, but not in the nearest cited file.
ll-issues format-check ENH-3047 --format json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['stale_symbol_ref'])"
# Before ENH-3047's ll-prose-ok markers were added this reported design_gate_failed
# against check_design.py. Reproduce by deleting the two <!-- ll-prose-ok --> lines
# in ENH-3047's Program Design § Signatures and re-running.

# 3. Repo-wide baseline.
ll-issues format-check --all --format json \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
hits=[k for k,v in d.items() if v.get('stale_symbol_ref')]
tot=sum(len(v['stale_symbol_ref']) for v in d.values())
print(f'{len(hits)} of {len(d)} active issues; {tot} individual hits')"
# Observed 2026-08-05: 32 of 72 issues, 94 hits.
```

### Observed false positives

- **FEAT-2942** reports 8 claim gaps. Two of them are
<!-- ll-prose-ok: quoted as example false-positive claims, not asserted as real def-sites -->
  `add_epic_consistency_parser` and `cmd_epic_consistency`, both attributed to
  `scripts/little_loops/cli/issues/__init__.py` — and both are functions FEAT-2942 proposes to
  **add**. They appear in its Program Design and Implementation Steps sections precisely because
  it is well specified.
- **ENH-3047** reports
<!-- ll-prose-ok: quoted as an example false-positive claim, not asserted as a real def-site -->
  `design_gate_failed` attributed to `scripts/little_loops/cli/issues/check_design.py`. That is a
  *proximity* failure rather than a forward-reference one: the symbol genuinely exists, just in
  `scripts/little_loops/issues/program_design.py`, and `check_design.py` is merely the nearby file
  the sentence cites as its caller. Rewording the sentence to be strictly accurate did not clear
  the gap — only an `ll-prose-ok` marker did.

The second example is a distinct sub-class worth fixing alongside the first: a symbol that resolves
*somewhere* in the repo but not in the nearest-cited file is much more likely a mis-attribution
than a stale claim.

### Measured Baseline (2026-08-05)

All 94 hits were bucketized by the nearest enclosing H2/H3 heading and by whether the symbol
resolves anywhere else in the repo. This is the audit Implementation Step 2 previously deferred as
"not yet known"; it is scripted, not hand-done, and is re-runnable as the Step 4 comparison. The
script is in § Validation.

**By resolution class:**

| Class | Hits | Share |
|---|---|---|
| Resolves **nowhere** (forward reference or genuinely stale — not separable mechanically) | 63 | 67% |
| Resolves **elsewhere** in the repo (mis-attribution) | 31 | 33% |

**By enclosing section** (top buckets; the tail is long and includes non-canonical headings such as
`Proposed Change`, `Files to Modify / Create`, `Scope`, `Children`):

| Section | Hits |
|---|---|
| Summary | 18 |
| Current Behavior | 8 |
| Expected Behavior | 7 |
| Codebase Research Findings | 6 |
| Call Path | 6 |
| Proposed Solution | 4 |
| Wiring Phase | 4 |
| Files to Modify | 4 |
| Implementation Steps | 2 |
| Dependent Files (Callers/Importers) | 2 |

Three consequences that drive the design below:

1. **A denylist of the five "future state" section names clears only 10 of 94 hits (10%).** An
   allowlist of the four "current state" section names clears 68 of 94 (73%). These are not
   equivalent rules and the difference is 7×.
2. **The largest single bucket is `Summary` (18)** — the section the original Proposed Solution
   treated as trustworthy current-state. Section scoping alone cannot make this gate trustworthy.
3. **Mis-attribution is 33%, not a minor sub-class.** Building the repo-wide symbol→files reverse
   index it needs costs **739 files / 25,388 def-sites / 0.89s** — cheap enough that the cost
   argument for deferring it does not hold.

## Expected Behavior

`stale_symbol_ref` should report only claims that assert current-state existence. Concretely, a
symbol named in a section that describes work to be done should not be reported, and a symbol that
resolves elsewhere in the repo should be reported differently (or not at all) from one that
resolves nowhere.

The gap should be trustworthy enough that a consumer can gate on it. Today it is not — see Impact.

## Motivation

`stale_symbol_ref` is a good idea executing on the wrong corpus slice. Left as-is it has two costs:

1. **It blocks its own consumers.** ENH-3047 wires claim gaps into `/ll:confidence-check`. It was
   designed to route them to a Phase 3 hard override (`STOP — ADDRESS GAPS`), and that design was
   **downgraded to a soft Criterion 4 cap** specifically because a hard override would have stopped
   51% of the active backlog, mostly on these false positives. Fixing this is the precondition for
   revisiting that decision.
2. **It trains reviewers to ignore the gap.** At a 46% hit rate dominated by expected-state noise,
   the real hits — an issue genuinely asserting a function that does not exist, which is the
   FEAT-2942 defect that motivated FEAT-3048 in the first place — are indistinguishable from the
   noise.

## Proposed Solution

**Selected: A1 + C together as one change.** The § Measured Baseline data shows neither half
reaches gateable precision alone, so they are scoped as a single fix rather than a primary and an
optional fold-in.

**A1 — allowlist-based section scoping.** Extract symbol claims *only* from an explicit allowlist of
current-state sections, and treat every other section — named or not — as out of scope. This is the
allowlist reading of the original Option A, chosen over the denylist reading for two measured
reasons: the denylist clears 10% of hits versus the allowlist's 73%, and the heading tail is long
and non-canonical (`Proposed Change`, `Files to Modify / Create`, `Scope`, `Children`, …), so any
enumeration of *excluded* names is guaranteed to be incomplete while an enumeration of *included*
names fails closed. It also matches the shape of the precedent it borrows from — the behavior-parity
scoping helper is itself an allowlist of section names, not a denylist.

Proposed allowlist (to be confirmed against the baseline during implementation):
`## Summary`, `## Current Behavior`, `## Root Cause`, `## Context`.

`## Expected Behavior` is deliberately **excluded** despite sounding current-state: it carries 7
hits and describes post-fix behavior by definition. `## Codebase Research Findings` (6 hits) is a
genuine current-state section but is machine-written from verified research, and its hits are
predominantly caller-attributions rather than existence claims — C handles those, so it stays out of
the allowlist rather than being special-cased.

**C — resolves-elsewhere downgrade.** When the claimed symbol is absent from the cited file but
present somewhere else in the repo, that is a mis-attribution, not a stale claim. Report it as a
distinct, lower-severity signal or drop it. This covers 33% of current hits, including every hit in
this issue's own § Self-demonstration, and — critically — it is the only half that reaches the 18
hits sitting inside `## Summary`, which A1 leaves in scope by design.

### Rejected

**Option B — creation-verb discriminator.** Keep whole-body extraction but suppress a claim when
surrounding prose carries creation verbs ("add", "introduce", "new"), or when the cited file appears
in the issue's own Integration Map. Rejected: no creation-verb detection exists anywhere in
`scripts/little_loops/` to reuse (the nearest analog matches fixed markers like `(new)` on file-path
refs, not free-text verbs on symbol claims), and fuzzy verb matching carries real false-negative risk
("add a check" vs. "add a function"). A1 achieves the same suppression deterministically.

**Denylist scoping (the original Option A reading).** Rejected on measurement: clears 10 of 94 hits.

### Decision Rationale

| Dimension | A1 + C | Denylist-A only | Option B |
|---|---|---|---|
| Measured hits cleared | 73% + 33% overlap | 10% | unmeasured |
| Consistency with precedent | 3 | 3 | 1 |
| Simplicity | 2 | 3 | 0 |
| Testability | 3 | 3 | 1 |
| Risk | 2 | 3 | 1 |
| **Fixes the reported bug** | **yes** | **no** | unproven |

**Key evidence:**
- The behavior-parity scoping helper (`issue_parser.py:865-879`) is the direct template for A1, and
  is an allowlist of two H2 names plus one H3 name — the exact shape A1 needs.
- The per-file symbol cache has no symbol→files reverse index today, so C must build one. Measured
  cost of a full build: 739 tracked Python files, 25,388 def-sites, **0.89s** — one-time per
  invocation, amortized across all issues in an `--all` sweep, and the same order as the existing
  file-reference index build. This supersedes the earlier estimate that treated the reverse index as
  prohibitive.
- Third independent precedent for treating design sections as forward-looking: the Program Design
  grader already documents that newly-introduced identifiers are never required to resolve.

**Residual risk (unchanged, and now quantified):** A1 under-fires on a genuinely-stale claim stated
inside an excluded section — roughly where FEAT-2942's motivating defect lived. Of the 63
resolves-nowhere hits, the fraction that are genuinely stale rather than forward references is not
mechanically separable; § Acceptance Criteria requires hand-classifying the survivors, and the
survivor count is the honest measure of whether the gate still catches its motivating case.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/symbol_claims.py` — extraction scope and/or discriminator
- `scripts/little_loops/issue_parser.py` — `check_format_gaps()`, if a new gap kind or severity
  distinction is introduced
- `scripts/tests/test_symbol_claims.py`, `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py`,
  `scripts/tests/test_symbol_cli_claim_sweep.py` — FEAT-3048's existing test surface
- `docs/reference/CLI.md` and `docs/reference/API.md` — the `stale_symbol_ref` description, if
  behavior changes

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` is `check_format_gaps()`'s
  and `build_symbol_index()`'s primary caller (lines 265/277/291/321/335); `_print_gaps()` (line 133)
  renders `gaps.stale_symbol_ref` per-field at lines 176-177 and would need a new print loop **only
  if** the mis-attribution downgrade adds a new `FormatGaps` field — enforced automatically by the
  structural guard `test_every_format_gaps_field_is_rendered` in `test_ll_issues_format_check.py`,
  which fails until the loop is added. Its help-banner literal (line 66, 189) listing gap kind names
  also needs updating **only if** a new gap kind name (not just changed semantics) is introduced.
- `scripts/little_loops/cli/issues/__init__.py:139` — same help-banner literal, same conditional.
- `skills/confidence-check/SKILL.md:196-203` and `skills/confidence-check/rubric.md:242` — ENH-3047's
  Criterion 4 cap reads `stale_symbol_ref` (combined with `stale_cli_flag`) directly out of
  `format-check --format json` via a `python -c` one-liner. This is the real consumer the Motivation
  section already describes in prose; fixing false positives here directly changes Criterion 4's
  score distribution. No code change required — noted so the fix's downstream effect is traceable.
- `scripts/little_loops/loops/rn-remediate.yaml`, `ensure_formatted` state (line 98-119) — gates on
  the aggregate exit code of `ll-issues format-check "$ID"` (`evaluate: {type: exit_code}`, line
  111-116), not on `stale_symbol_ref` specifically. Since the gap currently contributes to
  `has_gaps()`'s overall truthiness (which drives the exit code), the fix changes this gate's
  pass/fail outcome for any issue currently blocked solely by a spurious `stale_symbol_ref` hit —
  routing more issues from `format_issue` back to `assess`. Behavioral side effect only; no YAML
  edit needed.

### Similar Patterns
- `missing_behavior_parity` (ENH-3045) already restricts itself to a defined section set — the
  closest precedent for A1 (and is itself allowlist-shaped, which is why A1 adopts that shape)
- `prose_deps.py` (FEAT-2846/2849) is the architectural sibling FEAT-3048 generalized from, and
  faced the analogous "temporal phrasing" question, deliberately not matching "after ID" / "once
  ID" — precedent for excluding forward-looking phrasing from a claim class

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_issues_format_check.py` — houses the exact template to mirror:
  `TestMissingBehaviorParity::test_no_gap_outside_scope_sections` (line 972) asserts a
  same-keyword-content claim placed **outside** `missing_behavior_parity`'s scope tuple does not
  fire, paired with a positive-control sibling (`test_fires_on_resolved_ref_with_replacement_keyword_same_line`,
  line 875) that asserts it **does** fire inside scope. The new `stale_symbol_ref` scoping tests
  should follow this same paired shape (new tests). This file also owns the structural guard
  `test_every_format_gaps_field_is_rendered` that any new `FormatGaps` field must satisfy (existing
  coverage, no change needed unless a new field is added).
- `scripts/tests/test_confidence_check_skill.py:520,565` — loops over
  `("missing_behavior_parity", "stale_symbol_ref", "stale_cli_flag")` reading format-check JSON;
  exercises the same consumer path as `skills/confidence-check/SKILL.md`'s `CLAIM_GAP` extraction.
  Review once the fix lands — existing coverage, may need updated fixtures if gap semantics change.
- Confirmed gap (no existing coverage): neither `test_symbol_claims.py` (14 tests, all flat headless
  bodies) nor `test_feat3048_symbol_cli_claim_gaps.py` (7 tests, one fixed `_TEMPLATE` that only ever
  substitutes the claim under `## Summary`) constructs a body with a claim inside `## Program
  Design`/`### Files to Modify`/`## Implementation Steps`/`## Proposed Solution`/`## Proposed Fix`
  and asserts the gap is suppressed — new tests needed, following the template above.
- Confirmed: no existing test asserts `stale_symbol_ref` fires specifically on a claim placed inside
  those sections, so nothing needs its expectation flipped — this is pure new-coverage, not a
  behavior-flip update.
- `scripts/tests/test_symbol_cli_claim_sweep.py` (lines 60-61) — currently only
  `assert isinstance(symbol_hits, dict)` / `assert isinstance(cli_hits, dict)` (report-only, per its
  own module docstring). Tighten to a real count/allowlist assertion against the post-fix sweep
  number once Implementation Step 4's re-run baseline is known.

### Validation

The repo-wide sweep is the measurement that matters. Baseline as of 2026-08-05: **32 of 72 active
issues carry `stale_symbol_ref` (94 individual hits)**, 7 carry `stale_cli_flag`.

The bucketization below is the Step 2 audit and the Step 4 comparison — run it before and after,
and diff. It reproduces the § Measured Baseline tables exactly.

```python
# bucketize.py — run from repo root: python3 bucketize.py
import json, re, subprocess, sys, collections
from pathlib import Path
sys.path.insert(0, "scripts")
from little_loops.text_utils import build_ref_index
from little_loops.issues.symbol_claims import (
    extract_symbol_claims, build_symbol_index, symbol_exists_in_file, _extract_symbols)

root = Path(".")
d = json.loads(subprocess.run(["ll-issues", "format-check", "--all", "--format", "json"],
                              capture_output=True, text=True).stdout)
ids = {k for k, v in d.items() if v.get("stale_symbol_ref")}
paths = {}
for f in Path(".issues").rglob("*.md"):
    m = re.search(r"((?:BUG|FEAT|ENH|EPIC)-\d+)", f.name)
    if m and m.group(1) in ids:
        paths[m.group(1)] = f

ref_index, sym_index = build_ref_index(root), build_symbol_index(root)
rev = collections.defaultdict(set)   # symbol -> files; the index C would add
for f in subprocess.run(["git", "ls-files", "*.py"], capture_output=True, text=True).stdout.split():
    for s in (_extract_symbols(root / f) or set()):
        rev[s].add(f)

def heading(body, pos):
    last = "(preamble)"
    for m in re.finditer(r"^#{2,3} +(.+)$", body[:pos], re.M):
        last = m.group(1).strip()
    return last

sec, kind = collections.Counter(), collections.Counter()
for iid, p in sorted(paths.items()):
    body = p.read_text(encoding="utf-8", errors="replace")
    for c in extract_symbol_claims(body, ref_index):
        if symbol_exists_in_file(sym_index, c.file, c.symbol) is not False:
            continue
        pos = body.find("`" + c.raw + "`")
        sec[heading(body, pos if pos >= 0 else 0)] += 1
        kind["ELSEWHERE" if c.symbol in rev else "NOWHERE"] += 1
        print(f"{iid:14s} {kind.most_common(1)[0][0]:9s} {c.symbol} -> {c.file}")

total = sum(sec.values())
print(f"\ntotal hits: {total}")
for s, n in sec.most_common():
    print(f"{n:4d}  {s}")
for k, n in kind.most_common():
    print(f"{n:4d}  {k} ({n * 100 // total}%)")
```

A fix should move the hit count substantially while keeping genuinely stale claims reported. Record
the post-fix numbers and hand-classify every survivor per § Acceptance Criteria.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Section-scoping precedent (`missing_behavior_parity`, ENH-3045)**: the scoping itself is a bespoke per-gap-kind section list — `_BEHAVIOR_PARITY_SCOPE_H2_SECTIONS = ("Summary", "Proposed Solution")` / `_BEHAVIOR_PARITY_SCOPE_HEADINGS = ("Files to Modify",)` (`scripts/little_loops/issue_parser.py:865-879`) — but the extraction machinery it composes on, `_section_body()` (`issue_parser.py:224-230`) and `_heading_bodies()` (`issue_parser.py:911-927`), is shared and already reused by other gap kinds (e.g. `superseded_marker_count`). `extract_symbol_claims(body, ref_index)` (`scripts/little_loops/issues/symbol_claims.py`) currently takes a plain body string with no heading structure, so Option A's scoping would need to happen in the caller (`issue_parser.py`, which already has `_section_body`/`_heading_bodies` in scope) rather than inside `symbol_claims.py` itself.
- **Independent third precedent for treating Program Design as forward-looking**: `grade_program_design()` (`scripts/little_loops/issues/program_design.py:303-329`) already documents "Newly-introduced identifiers are never required to resolve — and their resolving anyway never changes the verdict" (docstring, program_design.py:307-308) — a second, independent function already applies the same non-resolution stance to Program Design content that BUG-3063 wants from `extract_symbol_claims`.
- **`prose_deps.py`'s exclusion is a fixed phrase-blocklist by omission, not a creation-verb filter**: `_PHRASE_RE` (`scripts/little_loops/issues/prose_deps.py:21-32`) only matches canonical dependency phrasings ("Depends on", "Blocked by", etc.); forward-looking phrasing is excluded simply by never being matched, not by a positive verb-detection pass. There is no "add"/"introduce"/"new" verb list anywhere in `prose_deps.py` — Option B's "creation verbs" idea has no existing implementation to reuse there. The closest existing analog to a forward-reference discriminator is `_PLANNED_NEW_RE` in `scripts/little_loops/text_utils.py:127`, consumed by `classify_file_ref()`, which matches explicit markers like `(new)`/`(to be created)` — but it operates on file-path refs, not backticked symbol claims.
- **Existing "downgrade instead of drop" convention uses a new `RefStatus`/`FormatGaps` field, not a severity scalar**: `classify_file_ref()` (`scripts/little_loops/text_utils.py:201-257`) returns one of `RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]` (`text_utils.py:111`), and each non-`resolved`/non-`stale` verdict gets its own `FormatGaps` list field (`ambiguous_file_ref`, `issue_parser.py:691-699`) rather than a confidence/severity tag on the existing field. There is no severity-scalar field anywhere in `FormatGaps` (`issue_parser.py:238-316`) today. This is the precedent shape the mis-attribution downgrade (Proposed Solution) would need to follow: a new `RefStatus`-style value or a new `FormatGaps` field, not a score.
- **`SymbolIndex` cannot answer "does this symbol resolve elsewhere in the repo" today**: `SymbolIndex` (`scripts/little_loops/issues/symbol_claims.py:218-263`) is a per-file lazy cache (`symbols_in(rel_path)`), with no reverse symbol→files index anywhere in the module. The mis-attribution downgrade described in Proposed Solution would require either an on-demand repo scan or a new aggregate structure — neither exists yet.
- **No regression test currently pins the forward-looking-section false positive**: `test_symbol_claims.py` and `test_feat3048_symbol_cli_claim_gaps.py` unit/integration-test the extractor and gap-population path, but neither constructs a body with a `## Program Design`/`### Files to Modify`/`## Implementation Steps` section citing a not-yet-existing symbol and asserts the gap is suppressed. `test_symbol_cli_claim_sweep.py` is the only signal surfacing this today, and it is explicitly report-only ("does not assert zero gaps... until the precision bar is met," module docstring lines 7-12) — the assertion that Step 4 of Implementation Steps calls for has yet to be added.

## Acceptance Criteria

1. **Volume.** A post-fix `--all` sweep reports **≤ 25 of the current 94 hits** (a ≥ 73% reduction).
   Both halves contribute: A1 removes hits outside the allowlist, C removes resolves-elsewhere hits
   inside it.
2. **Every survivor is hand-classified.** Each remaining hit is recorded in this issue as
   *genuinely stale*, *forward reference*, or *mis-attribution*. Zero mis-attribution survivors is
   required (that is C's whole job); a residue of forward references inside allowlisted sections is
   acceptable and must be enumerated, not waved through.
3. **Positive control holds.** A claim asserting a non-existent symbol inside `## Summary` or
   `## Current Behavior`, attributed to a file where it does not and cannot resolve anywhere in the
   repo, still fires `stale_symbol_ref`. Covered by a paired test (see § Tests).
4. **Negative control holds.** The same claim inside `## Program Design`, `### Files to Modify`,
   `## Implementation Steps`, `## Proposed Solution`, `## Proposed Fix`, `## Expected Behavior`, or
   an arbitrary unlisted heading does **not** fire. The unlisted-heading case is the one that proves
   allowlist-not-denylist semantics and must be an explicit test.
5. **This issue passes its own gate.** `ll-issues format-check BUG-3063` reports zero
   `stale_symbol_ref` with the `<!-- ll-prose-ok -->` markers in § Call Path and § Signatures
   **removed** — the § Self-demonstration case resolves without suppression.
6. **Sweep test tightened.** `scripts/tests/test_symbol_cli_claim_sweep.py`'s two report-only
   `isinstance` assertions are replaced with a real count/allowlist assertion against the post-fix
   number.
7. **No performance regression.** C's reverse index adds < 2s to a full `--all` sweep (measured
   baseline for the index build alone: 0.89s).
8. Full suite green: `python -m pytest scripts/tests/`.

## Implementation Steps

1. ~~Run `/ll:decide-issue`~~ — done 2026-08-05; A1 + C selected (see § Decision Rationale).
2. ~~Hand-audit the carriers~~ — done 2026-08-05, scripted rather than by hand; results in
   § Measured Baseline, script in § Validation.
3. Implement A1: add the allowlist scope tuple and a scoping helper in `issue_parser.py`, mirroring
   the behavior-parity scoping helper. No signature change to the extractor.
4. Implement C: add the symbol→files reverse index and route resolves-elsewhere claims to a distinct
   signal (a new `FormatGaps` field, per the convention in § Codebase Research Findings) or drop
   them. If a new field is added, follow the Wiring Phase checklist below.
5. Add the paired scoping tests for Acceptance Criteria 3–4, including the unlisted-heading case.
6. Re-run the § Validation bucketization, compare against the 94-hit baseline, and record the
   post-fix table plus the survivor classification in this issue.
7. Tighten the sweep test to the post-fix number.
8. Remove the now-unnecessary `<!-- ll-prose-ok -->` markers from this issue and from ENH-3047, and
   verify both still report clean.
9. Update `docs/reference/CLI.md` and `docs/reference/API.md` for the changed semantics and any new
   gap kind.
10. Notify ENH-3047 (or its successor) that the hard-override question can be revisited.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add paired scoping tests mirroring `TestMissingBehaviorParity::test_no_gap_outside_scope_sections`
  / `test_fires_on_resolved_ref_with_replacement_keyword_same_line` in
  `scripts/tests/test_ll_issues_format_check.py` (or `test_feat3048_symbol_cli_claim_gaps.py`).
  Because A1 is an **allowlist**, the negative cases must include an *arbitrary unlisted heading*
  (e.g. `## Rollout Notes`) alongside the named forward-looking sections — a denylist implementation
  passes the named cases and fails that one, which is what makes it the load-bearing test.
  Positive control: the same claim inside `## Summary`/`## Current Behavior` must still fire.
- Add a C-specific test pair: a symbol that exists in the repo but not in the cited file must **not**
  land in `stale_symbol_ref`, while a symbol that exists nowhere still must.
- C adds a new `FormatGaps` field (unless the mis-attribution case is dropped silently): update
  `has_gaps()`, `to_dict()`, and add a print loop in `format_check.py`'s `_print_gaps()` — the last
  is enforced by the existing `test_every_format_gaps_field_is_rendered` structural guard, which will
  fail until the loop exists.
- A new gap-kind *name* means updating the help-banner literal in
  `scripts/little_loops/cli/issues/__init__.py:139` and `format_check.py:66,189`.
- Tighten `scripts/tests/test_symbol_cli_claim_sweep.py`'s two `isinstance` assertions (lines 60-61)
  to a real count/allowlist assertion against the post-fix sweep number from Step 4.
- No edit needed, but confirm as expected: `scripts/little_loops/loops/rn-remediate.yaml`'s
  `ensure_formatted` state will route more issues from `format_issue` back to `assess` once spurious
  `stale_symbol_ref` hits stop tripping its exit-code gate — a behavioral side effect, not a bug.

## Impact

- **Priority**: P2 — a shipped gate is emitting majority-noise, and it is holding back ENH-3047's
  stronger design
- **Effort**: Medium — two seams (scoping helper + reverse index); the measurement pass is already
  done and the test surface already exists
- **Risk**: Medium — over-correcting makes `stale_symbol_ref` silent on the FEAT-2942-class defect
  it was built for. Acceptance Criteria 2's survivor classification is what keeps the fix honest.
- **Blast radius**: 32 of 72 active issues carry the gap (94 hits). Every one is a candidate score
  change in `/ll:confidence-check` once ENH-3047 lands.

## Program Design

_Signatures below are verified against the current source as of 2026-08-05 and describe the two
seams the selected A1 + C fix touches._

### Types

- `SymbolClaim` (`scripts/little_loops/issues/symbol_claims.py`) — the frozen dataclass carrying
  one extracted claim: `symbol: str`, `file: str` (resolved repo-relative path), `raw: str`. A
  fix that distinguishes claim *kinds* (forward-reference, mis-attribution, genuinely stale) would
  most likely add a field here rather than a parallel structure.
- `FormatGaps` (`scripts/little_loops/issue_parser.py`) — 20 `list[str]` gap-kind fields, one of
  which is the gap-kind list this issue is about. If the mis-attribution case becomes its
  own signal rather than a suppression, it lands here as a 21st field, mirrored in `has_gaps` and
  `to_dict()`, and documented in `docs/reference/CLI.md` and `docs/reference/API.md` per that
  dataclass's existing convention.

  _Wiring pass added by `/ll:wire-issue`:_ both `has_gaps()` (line 268) and `to_dict()` (line 293)
  enumerate every field by name (not reflection-based), so a new field must be added to both
  explicitly. All confirmed `FormatGaps(...)` construction sites outside `issue_parser.py`/
  `format_check.py` (`test_program_design_gate.py:703`, `test_issue_parser.py:3989-4025`,
  `test_ll_issues_format_check.py:1900`) use kwargs, not positional args, so field-insertion order
  is not a live break risk for existing callers.

### Signatures

<!-- ll-prose-ok: verified signatures quoted for the fix seam; symbols are attributed to their def-site module in prose below, not to the caller files named in Call Path -->
- `extract_symbol_claims(body: str, ref_index: RefIndex) -> set[SymbolClaim]`

  The extraction entry point. Takes a plain body string and returns a **set**, not a list — the
  caller sorts. **A1 does not change this signature**: the caller passes an already-scoped body
  substring, exactly as the behavior-parity gap kind does, so the scoping helper lives in
  `issue_parser.py` where the heading-splitting helpers are already in scope.

- `symbol_exists_in_file(index, file, symbol) -> bool | None`

  The per-claim resolver. Returns `None` (fail-open, no gap) for unsupported extensions or unreadable
  files — the tri-state matters, since the gap fires only on an explicit `False`. **C's seam is here
  or immediately after it.**

  Correction to an earlier draft of this section: the per-file symbol cache does **not** already know
  every def-site in the repo. It is lazily populated per *cited* file and has no reverse index, so C
  must build one — see § Codebase Research Findings, which states this correctly, and § Decision
  Rationale for the measured 0.89s build cost.

- `build_symbol_index(root: Path) -> SymbolIndex`

  Parameter is `root`, not `project_root`. Cheap today (it only records the root); C extends it with
  the reverse index, making this the one place the added cost lands.

- `check_format_gaps(...) -> FormatGaps`

  (`scripts/little_loops/issue_parser.py`) The consumer that turns unresolved claims into
  gap entries on the dataclass. Only touched if a new gap kind or severity distinction is added.

### Call Path

<!-- ll-prose-ok: call-path trace; each symbol is attributed to its caller, not its def-site — see the self-demonstration note below -->
`ll-issues format-check` -> `cmd_format_check()` (`scripts/little_loops/cli/issues/format_check.py`) -> `build_symbol_index()` -> `check_format_gaps()` (`scripts/little_loops/issue_parser.py`) -> `extract_symbol_claims()` -> `symbol_exists_in_file()` per claim -> unresolved claims appended to `FormatGaps.stale_symbol_ref` -> surfaced by `format-check` text/JSON output and, once ENH-3047 lands, by `/ll:confidence-check` Phase 1.8 as a Criterion 4 cap.

`build_symbol_index`, `extract_symbol_claims`, and `symbol_exists_in_file` are all defined in
`scripts/little_loops/issues/symbol_claims.py`; the files named above are their **callers**.

The fix has two seams: the body passed *into* the extraction step (A1, scoped in the caller) and the
per-claim resolution step (C). Nothing upstream of the gap-check entry point changes.

### Self-demonstration (2026-08-05)

Before the `<!-- ll-prose-ok -->` marker above was added, this section made `BUG-3063` report three
`stale_symbol_ref` gaps of its own — `build_symbol_index` and `extract_symbol_claims` attributed to
their calling files, and `stale_symbol_ref` itself (a `FormatGaps` field name, not a def-site).

All three are the mis-attribution sub-class this issue describes, produced by an ordinary Call Path
trace — the section format `ll-verify-*` and the Program Design gate actively require issues to
have. That the bug report cannot state its own call path without tripping its own subject is the
sharpest available evidence for the resolves-elsewhere downgrade in Proposed Solution. Reproduce by
deleting the marker line above and re-running `ll-issues format-check BUG-3063`.

## Related Key Documentation

- `docs/reference/CLI.md` — `ll-issues format-check` gap-class reference (`stale_symbol_ref`)
- `docs/reference/API.md` — `check_format_gaps()` and `FormatGaps`
- `.claude/CLAUDE.md` — Issue File Format

## Status

**Open** | Created: 2026-08-05 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-05T20:34:50 - `61e02669-4d4b-44ef-a675-d0cf8741eee7.jsonl`
- `/ll:wire-issue` - 2026-08-05T20:11:44 - `7780f328-a190-442c-b6cd-b985cc9efb9b.jsonl`
- `/ll:decide-issue` - 2026-08-05T20:03:01 - `355401d9-91ae-45a7-a85f-ac489c0e4268.jsonl`
- `/ll:refine-issue` - 2026-08-05T19:39:27 - `8e56a72d-7086-4e23-9bb7-21ff252fa839.jsonl`
- `/ll:capture-issue` - 2026-08-05T17:53:24 - `5e23105c-4eb4-4528-b7fe-55b105cf37c3.jsonl`
