---
id: BUG-3063
title: 'stale_symbol_ref fires on forward-looking design claims (46% of active issues)'
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
---

# BUG-3063: `stale_symbol_ref` fires on forward-looking design claims

## Summary

FEAT-3048's symbol-claim verifier extracts claims from the **entire** issue body with no section
scoping. Sections whose whole purpose is to name symbols the issue will **create** — `## Program
Design § Signatures`, `### Files to Modify`, `## Implementation Steps` — are read as assertions
that those symbols already exist, and every one of them is reported as a `stale_symbol_ref` gap.

Measured on this repo: **33 of 72 active issues (46%)** carry at least one `stale_symbol_ref`,
and spot-checking shows the forward-reference class dominates. The gap is firing on issues being
*well specified*, which inverts what it is meant to signal.

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
print(f'{len(hits)} of {len(d)} active issues')"
# Observed 2026-08-05: 33 of 72.
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

Two candidate approaches, not mutually exclusive. Neither is decided; this issue needs a
`/ll:decide-issue` pass.

**Option A — section scoping.** Skip claim extraction inside sections that describe future state
(`## Program Design`, `## Implementation Steps`, `### Files to Modify`, `## Proposed Solution`,
`## Proposed Fix`), extracting only from current-state sections (`## Summary`, `## Current
Behavior`, `## Root Cause`, `## Context`). Cheap, deterministic, and mirrors how
`missing_behavior_parity` already scopes itself to a section set (ENH-3045). Risk: a genuinely
false claim stated in Program Design goes unreported — which is roughly where FEAT-2942's original
defect lived, so this may under-fire on the motivating case.

**Option B — forward-reference discriminator.** Keep whole-body extraction but suppress a claim
when the cited file appears in the issue's own `### Files to Modify` / Integration Map (the issue
is declaring intent to change that file), or when surrounding prose carries creation verbs
("add", "introduce", "new"). More faithful to intent, more machinery, more tuning.

Also worth folding in regardless of A/B: **downgrade the resolves-elsewhere case**. If
`build_symbol_index()` finds the symbol in the repo but not in the cited file, that is a
mis-attribution, not a stale claim — report it as a distinct, lower-severity signal or drop it.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/symbol_claims.py` — extraction scope and/or discriminator
- `scripts/little_loops/issue_parser.py` — `check_format_gaps()`, if a new gap kind or severity
  distinction is introduced
- `scripts/tests/test_symbol_claims.py`, `scripts/tests/test_feat3048_symbol_cli_claim_gaps.py`,
  `scripts/tests/test_symbol_cli_claim_sweep.py` — FEAT-3048's existing test surface
- `docs/reference/CLI.md` and `docs/reference/API.md` — the `stale_symbol_ref` description, if
  behavior changes

### Similar Patterns
- `missing_behavior_parity` (ENH-3045) already restricts itself to a defined section set — the
  closest precedent for Option A
- `prose_deps.py` (FEAT-2846/2849) is the architectural sibling FEAT-3048 generalized from, and
  faced the analogous "temporal phrasing" question, deliberately not matching "after ID" / "once
  ID" — precedent for excluding forward-looking phrasing from a claim class

### Validation
The repo-wide sweep is the measurement that matters:

```bash
ll-issues format-check --all --format json
```

Baseline as of 2026-08-05: 33 of 72 active issues carry `stale_symbol_ref`, 7 carry
`stale_cli_flag`, 37 carry either. A fix should move the first number substantially while keeping
genuinely stale claims reported. Record the post-fix number and hand-audit a sample of the
survivors to confirm they are real.

## Implementation Steps

1. Run `/ll:decide-issue` on the Option A / Option B choice above.
2. Hand-audit a sample of the 33 current `stale_symbol_ref` carriers to establish what fraction is
   forward-reference, what fraction is mis-attribution, and what fraction is genuinely stale. This
   number is what makes the fix measurable and is not yet known.
3. Implement the selected option.
4. Re-run the sweep, compare against the 33/72 baseline, and hand-audit survivors.
5. Update `docs/reference/CLI.md` and `docs/reference/API.md` if the reported semantics change.
6. Notify ENH-3047 (or its successor) that the hard-override question can be revisited.

## Impact

- **Priority**: P2 — a shipped gate is emitting majority-noise, and it is holding back ENH-3047's
  stronger design
- **Effort**: Medium — extraction logic plus a measurement pass; the test surface already exists
- **Risk**: Medium — over-correcting makes `stale_symbol_ref` silent on the FEAT-2942-class defect
  it was built for. Step 2's audit is what keeps the fix honest.
- **Blast radius**: 33 of 72 active issues currently carry the gap. Every one of them is a
  candidate score change in `/ll:confidence-check` once ENH-3047 lands.

## Program Design

_Preliminary — the A/B choice in Proposed Solution is undecided, so the signatures below describe
the seam each option needs rather than a committed implementation._

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

### Signatures

- `extract_symbol_claims(body: str) -> list[SymbolClaim]`

  The extraction entry point in `symbol_claims.py`. **Option A** changes this signature or its
  body to take a section allowlist/denylist — the seam is here, since it is the only place the
  whole-body string is walked.

- `symbol_exists_in_file(...) -> bool`

  The per-claim resolver. **The mis-attribution downgrade lives here or immediately after it**:
  the `SymbolIndex` already knows every def-site in the repo, so "resolves elsewhere" is available
  without new indexing work — it is currently just collapsed into the same `False` as "resolves
  nowhere."

- `build_symbol_index(project_root: Path) -> SymbolIndex`

  Unchanged by either option; noted because it is what makes the mis-attribution distinction cheap.

- `check_format_gaps(...) -> FormatGaps`

  (`scripts/little_loops/issue_parser.py`) The consumer that turns unresolved claims into
  gap entries on the dataclass. Only touched if a new gap kind or severity distinction is added.

### Call Path

<!-- ll-prose-ok: call-path trace; each symbol is attributed to its caller, not its def-site — see the self-demonstration note below -->
`ll-issues format-check` -> `cmd_format_check()` (`scripts/little_loops/cli/issues/format_check.py`) -> `build_symbol_index()` -> `check_format_gaps()` (`scripts/little_loops/issue_parser.py`) -> `extract_symbol_claims()` -> `symbol_exists_in_file()` per claim -> unresolved claims appended to `FormatGaps.stale_symbol_ref` -> surfaced by `format-check` text/JSON output and, once ENH-3047 lands, by `/ll:confidence-check` Phase 1.8 as a Criterion 4 cap.

`build_symbol_index`, `extract_symbol_claims`, and `symbol_exists_in_file` are all defined in
`scripts/little_loops/issues/symbol_claims.py`; the files named above are their **callers**.

The fix seam is the `extract_symbol_claims()` step (Option A) or the `symbol_exists_in_file()`
step (mis-attribution downgrade); nothing upstream of `check_format_gaps()` changes.

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
- `/ll:capture-issue` - 2026-08-05T17:53:24 - `5e23105c-4eb4-4528-b7fe-55b105cf37c3.jsonl`
