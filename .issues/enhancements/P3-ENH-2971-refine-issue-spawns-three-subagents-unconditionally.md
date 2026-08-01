---
id: ENH-2971
title: refine-issue spawns three research subagents unconditionally
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T00:00:00Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2972
testable: true
labels:
- skills
- refine-issue
- cost
---

# ENH-2971: `refine-issue` spawns three research subagents unconditionally

## Summary

`/ll:refine-issue` Step 3 always spawns `codebase-locator`,
`codebase-analyzer`, and `codebase-pattern-finder` in parallel, regardless of
what the issue already contains. For a small BUG whose root cause is already
located in the issue, two of the three return findings the issue already has.
Gate the spawn set on what the issue is missing.

## Current Behavior

`commands/refine-issue.md` Step 3 reads, verbatim:

> **IMPORTANT**: Spawn all 3 agents in a SINGLE message with multiple Task
> tool calls, and wait for their results in this same turn before proceeding.

There is no branch. The agent set is fixed for every issue type and every
level of existing enrichment. Step 4 ("Identify Knowledge Gaps") — which
decides what is actually missing — runs *after* the research, so its verdict
cannot influence what gets spawned.

Note the ordering problem: the command already has a gap-classification step;
it just runs too late to gate anything.

## Expected Behavior

Step 3 spawns only the agents whose findings correspond to a gap the issue
actually has. A re-refine of an already-enriched issue, or a BUG that arrives
with `## Root Cause` populated with a resolving anchor, spawns fewer than
three. A sparse FEAT still spawns all three.

## Motivation

Each subagent is a separate request with its own context and output. Three
per refine, and `refine-issue` is invoked on nearly every issue that reaches
`autodev.yaml` — often more than once per issue, since gap-analysis mode is
explicitly designed for repeated use ("Gap-analysis runs do NOT count against
`max_refine_count` — they are additive-only … designed for repeated
iterative use"). The repeat case is where fixed fan-out costs most: the second
and third pass re-derive findings the first pass already deposited.

Subagent-heavy sessions are a known cost concentration; the fix is being
deliberate about spawning, not spawning less carefully.

## Proposed Solution

**Option A — cheap pre-classification (recommended).** Insert a gap-triage
step before Step 3 that reads the issue and decides which of the three
research axes are unmet, using only what is already in the file:

| Agent | Skip when |
|---|---|
| `codebase-locator` | `## Integration Map` lists files that all resolve on disk |
| `codebase-analyzer` | `## Root Cause` (BUG) or `## Current Behavior` cites an anchor that resolves |
| `codebase-pattern-finder` | `## Proposed Solution` already states a convention with evidence |

Anchor resolution is not a new capability —
`scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` already returns
`skipped_refs` for non-resolving references, and Step 5c already uses it.

**Option B — issue-type defaults.** Fixed per-type agent sets (BUG → analyzer
+ locator; FEAT → all three; ENH → analyzer + pattern-finder). Simpler, but
wrong in both directions: a sparse BUG needs the pattern-finder, and an
enriched FEAT needs none of them.

**Recommended**: Option A — it keys on the actual state of the issue, which
is the thing that varies. Option B keys on type, which does not predict
enrichment level at all.

## Program Design

The triage predicate is a pure function of (issue file, disk state), with no
network or model call: for each of the three axes, does the issue contain a
resolving reference of the kind that axis produces? Reusing
`_sweep_file()`'s `skipped_refs` means "resolves" has one definition across
the command rather than two.

### Signatures

If extracted to Python (see Scope Boundaries' open question):

```python
ResearchAxis = Literal["locator", "analyzer", "pattern_finder"]

@dataclass(frozen=True)
class AxisCoverage:
    axis: ResearchAxis
    covered: bool
    evidence: str  # section + resolving anchor that satisfied it, or "" when unmet

def triage_research_axes(issue_path: Path, root: Path) -> tuple[AxisCoverage, ...]:
    """Which research axes the issue already covers with resolving references."""
```

### Call Path

- `/ll:refine-issue` Step 3 → `triage_research_axes` → `_sweep_file`
- `_sweep_file` — supplies the per-reference resolution verdict, in
  `anchor_sweep.py`; already called by Step 5c, so this adds a second caller
  rather than a new dependency
- `find_project_root` — resolves the repo root the sweep is relative to
- Step 3 then spawns one `Task` per axis whose `covered` is False

Failure mode to design against: triage skipping an agent whose findings were
stale rather than absent. A reference that resolves is not necessarily
*current*. Mitigation — treat resolution as sufficient only for the additive
`--gap-analysis` path; `--full-rewrite` keeps the unconditional spawn, since
a full rewrite is by definition not trusting what is there.

## Integration Map

### Files to Modify

- `commands/refine-issue.md` — Step 3 gains a triage preamble; the "spawn
  all 3" instruction becomes "spawn the unmet set"
- `.gemini/commands/refine-issue.toml` — regenerate via `ll-adapt` (the
  mirror embeds the command body verbatim)

### Dependent Files

- `scripts/little_loops/loops/autodev.yaml` — invokes `/ll:refine-issue`;
  behavior change is internal to the command, no loop edit expected
- `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` — supplies
  `skipped_refs`, already consumed by Step 5c

### Conventions in Force

- Reference resolution is decided by `_sweep_file()`'s `skipped_refs`, not by
  an ad-hoc path check — evidence: `commands/refine-issue.md` Step 5c uses it
  for both Integration Map and Proposed Solution checks

### Tests

- No current test exercises `refine-issue`'s spawn set (it is a markdown
  command, not Python). The measurable gate is the triage predicate itself if
  it is extracted to Python; if it stays prose, this ships unverified — see
  Scope Boundaries.

## Implementation Steps

1. The triage predicate has one definition, shared with Step 5c's staleness
   check, rather than a second inline notion of "resolves".
2. `--full-rewrite` still spawns all three agents; only the additive paths
   triage.
3. A refine of a sparse issue still spawns all three — verified against a
   real sparse issue, not asserted.
4. The `.gemini` mirror matches the updated command body.
5. `python -m pytest scripts/tests/` passes.

## Scope Boundaries

- **In scope**: gating which agents spawn.
- **Out of scope**: changing what any agent is asked for, or the prompts
  themselves.
- **Open question**: whether the triage predicate should be extracted into
  `scripts/little_loops/issues/` as a testable function, or left as prose in
  the command. Extraction is the only way this gets a real test, and
  `ll-verify-skill-prose` exists specifically to push algorithms out of skill
  prose — so extraction is likely correct, but it enlarges the change from a
  prose edit to a module. Decide before implementing.

## Impact

- **Effort**: Small if prose-only; Medium if the predicate is extracted and
  tested.
- **Risk**: Medium — the failure mode is skipping an agent whose findings
  were needed, producing a quieter refine that looks successful. The
  `--full-rewrite` escape hatch bounds this.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked._

## Session Log
- `/ll:capture-issue` - 2026-08-01

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
