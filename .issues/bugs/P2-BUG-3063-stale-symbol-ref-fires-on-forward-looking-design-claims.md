---
id: BUG-3063
title: stale_symbol_ref fires on forward-looking design claims (46% of active issues)
type: BUG
priority: P2
status: done
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T17:52:25Z'
completed_at: '2026-08-05T21:28:41Z'
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
confidence_score: 88
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

**Section × resolution crosstab** (added 2026-08-05 after the initial bucketization; sections
assigned by H2 *span*, i.e. the semantics `_section_body()` actually implements — see § Proposed
Solution A1 for why the level must be pinned):

| | resolves elsewhere | resolves nowhere | total |
|---|---|---|---|
| **Outside** allowlist (removed by A1) | 23 | 45 | 68 |
| **Inside** allowlist (`Summary`, `Current Behavior`) | 8 | 18 | 26 |

Reading: **A1 alone leaves 26 survivors; A1 + C leaves 18** (an 81% reduction). This is the number
§ Acceptance Criteria 1 is set from. Note that 26 vs. a 25-hit ceiling would have let A1-with-no-C
pass by a single hit, which is why the criterion is pinned at the measured A1+C figure instead.

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

Four consequences that drive the design below:

1. **A denylist of the five "future state" section names clears only 10 of 94 hits (10%).** An
   allowlist of the four "current state" section names clears 68 of 94 (73%). These are not
   equivalent rules and the difference is 7×.
2. **The largest single bucket is `Summary` (18)** — the section the original Proposed Solution
   treated as trustworthy current-state. Section scoping alone cannot make this gate trustworthy.
3. **Mis-attribution is 33%, not a minor sub-class.** Building the repo-wide symbol→files reverse
   index it needs costs **739 files / 25,388 def-sites / 0.89s** — cheap enough that the cost
   argument for deferring it does not hold.
4. **A fourth false-positive class dominates the post-fix residue** — see § Survivor Analysis. Of the
   18 hits A1 + C leaves standing, roughly 13 are neither stale, forward-looking, nor mis-attributed;
   they are non-code identifiers that merely have symbol *shape*. Two sub-causes, one of which is a
   two-character resolver fix.

### Survivor Analysis (the 18 A1 + C leaves standing)

Fenced deliberately: every row below is a *quoted* claim from another issue, and rendering them as
prose would make this section fire the very gap it documents (the § Self-demonstration effect again,
this time inside an allowlisted section where A1 cannot help).

```text
ISSUE               CLAIM -> CITED FILE                          WHAT IT ACTUALLY IS
ENH-3000/EPIC-3023  stale_file_ref -> issue_parser.py,           FormatGaps dataclass field
                                      text_utils.py               (see D1)
FEAT-3040           orchestration_runs, usage_events             SQL table names
                      -> session_store/schema.py
FEAT-3043           advisor -> config/core.py                    config key
FEAT-3044           host_cli -> config/orchestration.py          config key
EPIC-2616           remove, list -> cli/loop/_helpers.py         CLI subcommand names
EPIC-1463           pre_tool_use, post_tool_use                   hook event names
                      -> bench_opencode_adapter.py
FEAT-3042 (x4)      resolve_host_named, run_blocking_json         <- the real signal:
FEAT-3043 (x2)      AdvisorConfig                                    genuinely-stale or
FEAT-1931           CommunicationAdapter                             forward-reference
EPIC-3022           on_budget_exceeded                               candidates (5 of 18)
```

Two distinct causes, only the first of which is a scoping question:

- **D1 — resolver blind spot (mechanically fixable).** `_extract_symbols()`
  (`scripts/little_loops/issues/symbol_claims.py:212`) applies `_MODULE_CONSTANT_RE.match(line)`, and
  that pattern is anchored `^([A-Za-z_]\w*)…=`. Indented lines never match, so **class attributes and
  dataclass fields are absent from the index entirely**. `FormatGaps.stale_file_ref` is a real
  attribute defined in `issue_parser.py` and still reports as stale. Allowing leading whitespace (or
  adding a dedicated attribute pattern) clears this class, is independent of both A1 and C, and also
  strengthens C — an attribute claim currently cannot even resolve *elsewhere*.
- **D2 — non-code namespaces (scoping question, not a resolver bug).** SQL table names, config keys,
  CLI subcommand names, and hook event names live in string literals and dict keys, not def-sites.
  No resolver change makes them resolve. They are **declared out of scope for this issue**: the
  suppression they need is a different discriminator (claim-shape or namespace-aware), tracked
  separately rather than bolted onto A1 + C. § Acceptance Criteria 2 carries them as their own
  survivor bucket so they are enumerated rather than silently absorbed.

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

**Scoping level — pin it explicitly.** Two helpers exist and they are not interchangeable:
`_section_body()` (`issue_parser.py:224-230`) returns the **H2 span**, swallowing every nested H3;
`_heading_bodies()` (`issue_parser.py:911-927`) matches a heading by name at H2 *or* H3 and stops at
the next equal-or-higher level. **Use `_section_body()` (H2-span) for the allowlist**, matching the
behavior-parity helper's H2 branch. Consequences, both intended:

- `### Codebase Research Findings` and `### Dependent Files` are excluded via their `## Integration
  Map` parent; `### Call Path` and `### Signatures` via `## Program Design`. No H3 needs naming.
- Conversely, an H3 nested under an allowlisted H2 **is in scope**. In this issue that is
  load-bearing: `### Observed false positives` and `### Measured Baseline` sit inside
  `## Current Behavior`, so their two `<!-- ll-prose-ok -->` markers must **stay** — see
  § Implementation Steps 9, which scopes marker removal to § Signatures and § Call Path only.

Note that the § Measured Baseline "by enclosing section" table buckets by *nearest* H2-or-H3 heading,
which is a third semantics, matching neither helper. On the current corpus all three agree at 26
in-allowlist hits (no H3-nested hits fall under `Summary`/`Current Behavior` today), so the
divergence is latent — but the Step 7 re-run must bucket by H2 span to compare like with like.

`## Expected Behavior` is deliberately **excluded** despite sounding current-state: it carries 7
hits and describes post-fix behavior by definition. `## Codebase Research Findings` (6 hits) is a
genuine current-state section but is machine-written from verified research, and its hits are
predominantly caller-attributions rather than existence claims — C handles those, so it stays out of
the allowlist rather than being special-cased.

**C — resolves-elsewhere downgrade.** When the claimed symbol is absent from the cited file but
present somewhere else in the repo, that is a mis-attribution, not a stale claim. Report it as a
distinct, lower-severity signal or drop it. This covers 33% of current hits overall, including every
hit in this issue's own § Self-demonstration, and — critically — it is the only half that reaches
inside the allowlist, where it clears **8 of the 26 hits A1 leaves standing** (§ Measured Baseline
crosstab).

**Index the same language set the resolver does.** Build the reverse index by iterating
`_SUPPORTED_SYMBOL_EXTENSIONS` (10 extensions), **not** `git ls-files '*.py'` as the § Validation
prototype script does. The repo tracks 38 non-`.py` files in that set. No current hit cites one, so
the asymmetry is latent — but a Python-only index would downgrade a mis-attributed Python symbol and
silently keep firing on the identical TypeScript case. Cost impact is negligible against the measured
739-file / 0.89s Python-only build.

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
- `scripts/little_loops/issues/symbol_claims.py` — three seams: the reverse symbol→files index (C,
  on `SymbolIndex`/`build_symbol_index`), and `_MODULE_CONSTANT_RE` / `_extract_symbols()` (D1, the
  indentation fix at lines 32 and 195/212)
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

**Two known biases in this prototype script, both to correct in the Step 7 re-run:**

1. It attributes a hit by ``body.find("`" + c.raw + "`")`` — the **first** occurrence only. A symbol
   claimed in two sections is bucketed to whichever appears earlier in the file, so a bucket shift
   between the before and after runs can reflect re-ordering rather than suppression. Prefer
   resolving each claim's own offset, or at minimum bucket by H2 span (see below) where the
   ambiguity is coarser and rarer.
2. It buckets by *nearest* H2-or-H3 heading and builds the reverse index from `git ls-files '*.py'`.
   The implementation uses H2 span and all of `_SUPPORTED_SYMBOL_EXTENSIONS`. Align both before
   diffing, or the comparison is not like-for-like.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-05 — based on codebase analysis:_

- **Section-scoping precedent (`missing_behavior_parity`, ENH-3045)**: the scoping itself is a bespoke per-gap-kind section list — `_BEHAVIOR_PARITY_SCOPE_H2_SECTIONS = ("Summary", "Proposed Solution")` / `_BEHAVIOR_PARITY_SCOPE_HEADINGS = ("Files to Modify",)` (`scripts/little_loops/issue_parser.py:865-879`) — but the extraction machinery it composes on, `_section_body()` (`issue_parser.py:224-230`) and `_heading_bodies()` (`issue_parser.py:911-927`), is shared and already reused by other gap kinds (e.g. `superseded_marker_count`). `extract_symbol_claims(body, ref_index)` (`scripts/little_loops/issues/symbol_claims.py`) currently takes a plain body string with no heading structure, so Option A's scoping would need to happen in the caller (`issue_parser.py`, which already has `_section_body`/`_heading_bodies` in scope) rather than inside `symbol_claims.py` itself.
- **Independent third precedent for treating Program Design as forward-looking**: `grade_program_design()` (`scripts/little_loops/issues/program_design.py:303-329`) already documents "Newly-introduced identifiers are never required to resolve — and their resolving anyway never changes the verdict" (docstring, program_design.py:307-308) — a second, independent function already applies the same non-resolution stance to Program Design content that BUG-3063 wants from `extract_symbol_claims`.
- **`prose_deps.py`'s exclusion is a fixed phrase-blocklist by omission, not a creation-verb filter**: `_PHRASE_RE` (`scripts/little_loops/issues/prose_deps.py:21-32`) only matches canonical dependency phrasings ("Depends on", "Blocked by", etc.); forward-looking phrasing is excluded simply by never being matched, not by a positive verb-detection pass. There is no "add"/"introduce"/"new" verb list anywhere in `prose_deps.py` — Option B's "creation verbs" idea has no existing implementation to reuse there. The closest existing analog to a forward-reference discriminator is `_PLANNED_NEW_RE` in `scripts/little_loops/text_utils.py:127`, consumed by `classify_file_ref()`, which matches explicit markers like `(new)`/`(to be created)` — but it operates on file-path refs, not backticked symbol claims.
- **Existing "downgrade instead of drop" convention uses a new `RefStatus`/`FormatGaps` field, not a severity scalar**: `classify_file_ref()` (`scripts/little_loops/text_utils.py:201-257`) returns one of `RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]` (`text_utils.py:111`), and each non-`resolved`/non-`stale` verdict gets its own `FormatGaps` list field (`ambiguous_file_ref`, `issue_parser.py:691-699`) rather than a confidence/severity tag on the existing field. There is no severity-scalar field anywhere in `FormatGaps` (`issue_parser.py:238-316`) today. This is the precedent shape the mis-attribution downgrade (Proposed Solution) would need to follow: a new `RefStatus`-style value or a new `FormatGaps` field, not a score.
- **`SymbolIndex` cannot answer "does this symbol resolve elsewhere in the repo" today**: `SymbolIndex` (`scripts/little_loops/issues/symbol_claims.py:218-263`) is a per-file lazy cache (`symbols_in(rel_path)`), with no reverse symbol→files index anywhere in the module. The mis-attribution downgrade described in Proposed Solution would require either an on-demand repo scan or a new aggregate structure — neither exists yet.
- **No regression test currently pins the forward-looking-section false positive**: `test_symbol_claims.py` and `test_feat3048_symbol_cli_claim_gaps.py` unit/integration-test the extractor and gap-population path, but neither constructs a body with a `## Program Design`/`### Files to Modify`/`## Implementation Steps` section citing a not-yet-existing symbol and asserts the gap is suppressed. `test_symbol_cli_claim_sweep.py` is the only signal surfacing this today, and it is explicitly report-only ("does not assert zero gaps... until the precision bar is met," module docstring lines 7-12) — the assertion that Step 4 of Implementation Steps calls for has yet to be added.

## Acceptance Criteria

1. **Volume.** A post-fix `--all` sweep reports **≤ 18 of the current 94 hits** (an ≥ 81% reduction),
   the figure the § Measured Baseline crosstab measures for A1 + C. Both halves must contribute:
   A1 removes the 68 hits outside the allowlist, C removes the 8 resolves-elsewhere hits inside it.
   The threshold is deliberately set below A1's standalone 26 so that a C-less implementation cannot
   satisfy this criterion.
2. **Every survivor is hand-classified** into one of **four** buckets: *genuinely stale*,
   *forward reference*, *mis-attribution*, or *non-code identifier* (§ Survivor Analysis D2 — config
   keys, SQL table names, CLI subcommand names, hook event names). Zero mis-attribution survivors is
   required (that is C's whole job). Zero *class-attribute* survivors is required (that is D1's job —
   `FormatGaps.stale_file_ref` must resolve after the fix). A residue of forward references inside
   allowlisted sections, and the D2 non-code-identifier bucket, are both acceptable and must be
   enumerated in this issue, not waved through.
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
3. [x] Implement A1: add the allowlist scope tuple and a scoping helper in `issue_parser.py`, mirroring
   the behavior-parity scoping helper and using `_section_body()` (H2-span) per § Proposed Solution's
   scoping-level note. No signature change to the extractor. — `_STALE_SYMBOL_SCOPE_H2_SECTIONS` /
   `_symbol_claim_scope_text()` in `issue_parser.py`.
4. [x] Implement D1 (§ Survivor Analysis): make `_MODULE_CONSTANT_RE` tolerate leading indentation in
   `_extract_symbols()` so class attributes and dataclass fields enter the index. Independent of A1
   and C — landed with its own regression test (`test_extract_symbols_indented_class_attribute_resolves`).
   Blast radius accepted and documented: the widened pattern also admits indented local-variable
   assignments (`test_extract_symbols_indented_local_variable_also_resolves` pins this explicitly).
5. [x] Implement C: add the symbol→files reverse index — over `_SUPPORTED_SYMBOL_EXTENSIONS`, not `*.py`
   — and route resolves-elsewhere claims to a distinct signal (new `FormatGaps.mislocated_symbol_ref`
   field, per the convention in § Codebase Research Findings). Wiring Phase checklist below completed.
   The reverse index is built **eagerly** inside `build_symbol_index()` itself (not lazily on first
   query) so `check_format_gaps()` keeps its "never shells out" contract
   (`test_check_format_gaps_spawns_no_subprocess`).
6. [x] Add the paired scoping tests for Acceptance Criteria 3–4, including the unlisted-heading case —
   `TestStaleSymbolRefScoping` in `test_feat3048_symbol_cli_claim_gaps.py`.
7. [x] Re-run the § Validation bucketization (bucketing by H2 span) — see § Post-Fix Results below.
   Measured **7** combined hits (2 `stale_symbol_ref` + 5 `mislocated_symbol_ref`, across 6
   issue-occurrences of 77 active issues as of 2026-08-05), well under the 18-hit A1+C projection.
8. [x] Tighten the sweep test to the post-fix number — `test_symbol_cli_claim_sweep.py` now asserts
   `stale_symbol_ref + mislocated_symbol_ref <= 18` instead of only `isinstance` checks.
9. [x] Remove the `<!-- ll-prose-ok -->` markers in **§ Signatures and § Call Path only** from this
   issue, plus ENH-3047's two markers, and verify both still report clean. The two markers in
   § Observed false positives and § Measured Baseline are inside `## Current Behavior`'s H2 span,
   which A1 keeps in scope — they stay, and removing them is a regression, not a cleanup. Confirmed:
   `ll-issues format-check BUG-3063` and `ll-issues format-check ENH-3047` both report zero
   `stale_symbol_ref`/`mislocated_symbol_ref` post-removal.
10. [x] Update `docs/reference/CLI.md` and `docs/reference/API.md` for the changed semantics and the
    new `mislocated_symbol_ref` gap kind.
11. [x] Notify ENH-3047 (or its successor) that the hard-override question can be revisited — noted
    inline in ENH-3047's § Why Claims Are a Cap, Not an Override (its two example false positives no
    longer fire post-fix).
12. Capture the D2 non-code-identifier class (§ Survivor Analysis) as a follow-up issue — deferred:
    the post-fix sweep (§ Post-Fix Results) found **zero** D2 survivors on the current corpus (the
    13-of-18 estimate no longer holds now that A1+C measured 7 total hits, not 18), so there is
    nothing to size a follow-up from yet. Revisit if a future sweep surfaces the class.

### Post-Fix Results (2026-08-05)

Repo-wide sweep via `check_format_gaps()` with real `ref_index`/`symbol_index`, 77 active issues:

| Class | Issues | Hits |
|---|---|---|
| `stale_symbol_ref` | 2 | 2 |
| `mislocated_symbol_ref` | 4 | 5 |
| **Total** | **6** | **7** |

Well under both the 26-hit A1-only projection and the 18-hit A1+C projection (§ Measured Baseline) —
the live corpus changed since the pre-fix 94-hit measurement (issues completed/added since), and the
allowlist + resolves-elsewhere downgrade together clear effectively all of the measured false-positive
classes on the current backlog.

**Hand-classification of all 7 survivors** (§ Acceptance Criteria 2's four buckets):

- `stale_symbol_ref` (genuinely stale or forward-reference, not mechanically separable — 2 hits):
  `orchestration_runs` (FEAT-3040, SQL table name — D2 non-code-identifier, not code-shape stale) and
  `omp` (FEAT-2787, short bare token, likely a non-code abbreviation misparsed as a symbol).
- `mislocated_symbol_ref` (mis-attribution — C's whole job, all correctly downgraded — 5 hits):
  `CodexEmitter`/`GeminiEmitter` (ENH-2968), `stale_file_ref` (EPIC-3023, a `FormatGaps` field name —
  the same class D1 targets, now correctly resolving as a mislocated attribute-name reference rather
  than stale), `_dispatch_table` (ENH-1718), `usage_events` (FEAT-3040, SQL table name resolving
  elsewhere).

Zero mis-attribution survivors landed in `stale_symbol_ref` (C's AC2 requirement) and zero
class-attribute survivors remain unresolved (D1's AC2 requirement — `FormatGaps.stale_file_ref` now
resolves via `mislocated_symbol_ref`'s own resolution path, confirming D1 widened the index as
intended). The D2 non-code-identifier bucket (SQL table names, short abbreviations) accounts for the
2 `stale_symbol_ref` survivors — consistent with § Survivor Analysis's original prediction, just at a
much smaller absolute count than the pre-fix 94-hit corpus implied.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-05_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 78/100 → moderate-high

### Concerns
- Criterion 4 (Issue Well-Specified) is capped at 10/20 by the Phase 1.8 Parity/Claim Cap
  (ENH-3047): `ll-issues format-check BUG-3063` currently reports 3 `stale_symbol_ref` hits —
  `build_symbol_index` and `check_format_gaps` (mis-attributed to `format_check.py`, their
  caller, not their def-site in `symbol_claims.py`/`issue_parser.py`) and `isinstance`
  (a builtin, claimed in `test_symbol_cli_claim_sweep.py`). These are exactly the
  mis-attribution/non-code-identifier false-positive classes this issue exists to fix — the
  `<!-- ll-prose-ok -->` markers on § Signatures and § Call Path suppress the issue's own
  worked self-demonstration example but not these three, which sit outside those markers'
  spans. This is advisory (the cap does not force STOP) and does not block implementation.
- Minor line-number drift: § Files to Modify cites `_MODULE_CONSTANT_RE` / `_extract_symbols()`
  "at lines 43 and 212"; current source has `_MODULE_CONSTANT_RE` at
  `scripts/little_loops/issues/symbol_claims.py:32` (line 43 is `_DOTTED_RE`) and
  `_extract_symbols()` still at line 195/212 as cited. Cosmetic — worth a quick fix during
  implementation, not a blocker.

## Status

**Open** | Created: 2026-08-05 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-05T21:28:23 - `8d77dccf-ef30-45d9-90b1-5eb5712e679b.jsonl`
- `/ll:ready-issue` - 2026-08-05T21:02:02 - `071e2716-dde5-4aff-a87c-b914645405b3.jsonl`
- `/ll:confidence-check` - 2026-08-05T20:53:33 - `f597033d-3e30-4b6d-a49f-8ff2ffd933a3.jsonl`
- `/ll:confidence-check` - 2026-08-05T20:34:50 - `61e02669-4d4b-44ef-a675-d0cf8741eee7.jsonl`
- `/ll:wire-issue` - 2026-08-05T20:11:44 - `7780f328-a190-442c-b6cd-b985cc9efb9b.jsonl`
- `/ll:decide-issue` - 2026-08-05T20:03:01 - `355401d9-91ae-45a7-a85f-ac489c0e4268.jsonl`
- `/ll:refine-issue` - 2026-08-05T19:39:27 - `8e56a72d-7086-4e23-9bb7-21ff252fa839.jsonl`
- `/ll:capture-issue` - 2026-08-05T17:53:24 - `5e23105c-4eb4-4528-b7fe-55b105cf37c3.jsonl`
