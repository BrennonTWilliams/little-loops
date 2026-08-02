---
id: BUG-3003
title: research-triage marks the analyzer axis covered while the Program Design gate
  is failing, so refine skips the enrichment BUG-3001 added
type: BUG
priority: P2
captured_at: '2026-08-02T18:20:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- refine-issue
- research-triage
- program-design-gate
relates_to:
- BUG-3001
- BUG-3002
status: open
testable: true
decision_needed: false
---

# BUG-3003: research-triage marks the analyzer axis covered while the Program Design gate is failing, so refine skips the enrichment BUG-3001 added

## Summary

BUG-3001 taught `/ll:refine-issue` to author `## Program Design` — the rule
lives in Step 5a (`commands/refine-issue.md:372-384`), sourced from the
`codebase-analyzer` agent's findings. But Step 5a is unreachable for the exact
population that needs it.

Step 3.0's research triage (`ll-issues research-triage`) evidences the
`analyzer` axis from `## Root Cause` and `## Current Behavior` only
(`scripts/little_loops/issues/research_triage.py:71`). `## Program Design` is
consulted by no axis. So an issue with a resolving, symbol-bearing Root Cause —
which describes every issue that has already been refined once, and therefore
every issue that reaches the Program Design gate a second time — triages
`analyzer: covered`. Step 3.1 (`refine-issue.md:189-193`) then says: with zero
unmet axes, "**skip Steps 4, 5a, and 5b entirely**" and proceed to 5c/6/6.5/6.7.

Step 6.7's gate fires, reports `program_design_nonspecific` still failing, and
its remedy instruction — "Revise that section (written in Step 5a above)"
(`refine-issue.md:752-756`) — has nothing to revise, because 5a was skipped and
no analyzer agent ran to source it from. Refine reports the gate as still armed
and exits without writing the section.

## Steps to Reproduce

1. In a stamped project (`.ll/program-design-cutover.json` present), take an
   issue that has been refined at least once — its `## Root Cause` cites
   resolving paths with backticked symbols — and whose `## Program Design` is
   missing, empty, or prose-only.
2. Run `ll-issues research-triage <ID> --json`. Observe
   `"analyzer": {"covered": true, ...}`.
3. Run `/ll:refine-issue <ID> --auto` (or `--auto --gap-analysis`).
4. Observe the no-op-triage report ("No research needed — all three axes already
   covered"), then Step 8's `## PROSE/PROGRAM DESIGN GATE` block reporting the
   gate still failing.
5. `git diff` the issue file: `## Program Design` is unchanged.

## Current Behavior

`triage_research_axes` (`scripts/little_loops/issues/research_triage.py:250`)
returns one `AxisCoverage` per axis from `_triage_axis` (`:303`), scored purely
from `_AXIS_SECTIONS` / `_AXIS_NEEDS_SYMBOL` reference resolution and staleness.
Nothing in that path reads the Program Design gate verdict.

`--full-rewrite` is the only mode that escapes it (`refine-issue.md:165-167`
sets `TRIAGE=""`, "a full rewrite does not trust what is already in the file"),
but it is the wrong instrument: it consumes `max_refine_count` budget
(`:684`), it re-derives all three axes, and it rewrites sections wholesale —
re-running it on a repeatedly-deferred issue is a rewrite cycle, not a fix.

## Expected Behavior

When the Program Design gate is active for an issue and the section is
missing/empty/non-specific, the `analyzer` axis is reported **uncovered**, with
an evidence string naming the gate as the reason. Refine then spawns the
analyzer agent, Step 5a runs, and the section gets written from real findings —
on the additive `--auto` / `--auto --gap-analysis` paths, with no budget
consumed and nothing removed.

## Root Cause

The ENH-2971 triage was designed to answer "is this axis already evidenced by
the issue's own resolving references?" and its section map predates ENH-2852's
`## Program Design` requirement and BUG-3001's enrichment rule. Adding the
section to `_AXIS_SECTIONS["analyzer"]` would be the wrong repair in the
opposite direction — it would let a Program Design section *evidence* analyzer
coverage. The gate verdict has to act as an override that un-covers the axis,
not as another coverage source.

## Program Design

### Signatures

- `triage_research_axes(issue_path: Path, root: Path, *, index: RefIndex | None = None, change_times: ChangeTimeIndex | None = None, check_staleness: bool = True) -> tuple[AxisCoverage, ...]`
  (`scripts/little_loops/issues/research_triage.py:250`) — unchanged signature;
  gains a post-pass over the computed tuple before returning
- `AxisCoverage(axis: ResearchAxis, covered: bool, evidence: str)`
  (`:89`) — frozen dataclass; the override constructs a replacement instance
  rather than mutating
- `program_design_gate_active(issue_path: Path, content: str) -> bool`
  (`scripts/little_loops/issues/program_design.py:415`) — existing per-project
  stamp + grandfathering check, reused verbatim
- `grade_issue_section(issue_path: Path, body: str) -> DesignVerdict`
  (`:444`) — existing grader; `DesignVerdict.is_specific` is the failing
  predicate, matching `issue_parser.py:487-490`'s `program_design_nonspecific`
  semantics exactly
- New private helper:
  `_program_design_unmet(issue_path: Path, content: str) -> str` — returns an
  evidence string when the gate is active and the section is
  missing/empty/non-specific, `""` otherwise

### Call Path

`cmd_research_triage` (`scripts/little_loops/cli/issues/research_triage.py:45`)
→ `triage_research_axes` (`:250`) → per-axis `_triage_axis` (`:303`) →
**`_program_design_unmet`** (new) → `program_design_gate_active` /
`grade_issue_section` → override the `analyzer` entry to
`covered=False, evidence="Program Design gate: <reason>"`

Consumer side (unchanged code, changed behavior): `/ll:refine-issue` Step 3.0
reads the JSON → analyzer unmet → Agent 2 spawns → Step 4/5a run → Step 5a's
Program Design rule (`refine-issue.md:372-384`) writes the section → Step 6.7's
gate confirms it clears.

## Integration Map

### Files to Modify
- `scripts/little_loops/issues/research_triage.py` — `triage_research_axes`
  (`:250-300`) post-pass and the new `_program_design_unmet` helper; the
  module docstring (`:1-10`) describes the triage contract and should note the
  override
- `commands/refine-issue.md` — Step 3.0 (`:160-187`) should state that a
  failing Program Design gate forces the analyzer axis unmet, so the skill's
  prose matches the CLI's behavior; Step 3.1's "skip 5a" carve-out (`:189-193`)
  needs a sentence noting this case cannot arise while the gate is failing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/research_triage.py:45` — `cmd_research_triage`,
  the `--json` surface refine reads; no change expected
- `scripts/little_loops/issue_parser.py:487-490` — the
  `program_design_nonspecific` producer whose predicate this override must
  mirror; if the two drift, refine and format-check disagree about the same
  issue

### Similar Patterns
- `_gate_program_design` (`scripts/little_loops/issue_parser.py:129-145`) — the
  established shape for "consult the gate, then adjust a computed set", with a
  local import of `program_design` to avoid a module cycle. The new helper
  should follow it, including the deferred import.

### Tests
- `scripts/tests/test_research_triage.py` — unit coverage for
  `triage_research_axes`; add: gate active + section missing → analyzer
  uncovered with non-empty evidence; gate active + section specific → analyzer
  coverage unchanged; gate **inactive** (unstamped/grandfathered project) →
  analyzer coverage unchanged even with no Program Design section (the
  regression that would otherwise fire on every legacy issue)
- `scripts/tests/test_ll_issues_research_triage.py` — CLI/JSON surface; assert
  the override is visible in `--json` output
- `scripts/tests/test_program_design_gate.py` — gate semantics; unchanged, but
  the predicate-parity assertion (override agrees with
  `program_design_nonspecific`) belongs here or in the triage tests

### Documentation
- `docs/reference/API.md` — the `research_triage` section describing axis
  coverage rules
- `docs/reference/CLI.md` — `ll-issues research-triage` description, if it
  enumerates what makes an axis covered

### Configuration
- N/A — the override is gated by the existing
  `.ll/program-design-cutover.json` stamp; no new setting.

## Implementation Steps

1. Add `_program_design_unmet(issue_path, content) -> str` to
   `research_triage.py`, modeled on `_gate_program_design`
   (`issue_parser.py:129`) including the deferred import: return `""` unless
   `program_design_gate_active(issue_path, content)`; otherwise return an
   evidence string when the `## Program Design` section is absent, empty, or
   `grade_issue_section(...).is_specific` is False.
2. In `triage_research_axes`, apply the result as a post-pass over the computed
   tuple: replace the `analyzer` entry with
   `AxisCoverage(axis="analyzer", covered=False, evidence=<gate reason>)` when
   the helper returns non-empty. Leave `locator` and `pattern_finder` alone.
3. Keep the predicate in lockstep with `issue_parser.py:487-490` — reuse
   `grade_issue_section`, do not re-implement the specificity rules.
4. Update Step 3.0 of `commands/refine-issue.md` to document the override, and
   add the carve-out sentence to Step 3.1.
5. Add the triage unit tests and the CLI/JSON assertion listed above,
   including the gate-inactive no-regression case.
6. Update `docs/reference/API.md` (and `CLI.md` if it enumerates coverage
   rules).

## Acceptance Criteria

- [ ] `ll-issues research-triage <ID> --json` reports
      `analyzer.covered == false` with a non-empty `evidence` naming the gate,
      for a stamped-project issue whose Root Cause is fully covered but whose
      `## Program Design` is missing, empty, or prose-only.
- [ ] The same command reports `analyzer` coverage **unchanged** when the gate
      is inactive (unstamped or grandfathered project), so legacy issues see no
      behavior change.
- [ ] The override's failing-predicate agrees with `format-check`'s
      `program_design_nonspecific` on the same issue — no case where one flags
      and the other does not.
- [ ] `/ll:refine-issue <ID> --auto --gap-analysis` on a gate-failing issue
      spawns the analyzer agent, runs Step 5a, and leaves `## Program Design`
      non-identical (`git diff`) — without consuming `max_refine_count` and
      without removing any existing content.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

This is the reachability half of BUG-3001: the enrichment logic landed but is
skipped for the population it was written for. Until it is fixed, every
`/ll:refine-issue` invocation against an already-refined, gate-failing issue is
a no-op on the section — which is precisely what BUG-3002's Option A remedy
depends on working. **BUG-3002 should not land before this.**

It also removes the pressure to reach for `--full-rewrite` as a workaround,
which would consume refinement budget and risk rewrite cycles on repeatedly
deferred issues.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `scripts/little_loops/issues/research_triage.py` | The axis-coverage rules being overridden |
| `commands/refine-issue.md` | Steps 3.0/3.1/5a/6.7 — the skipped-enrichment path |
| `scripts/little_loops/issues/program_design.py` | The gate and grader the override reuses |

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
