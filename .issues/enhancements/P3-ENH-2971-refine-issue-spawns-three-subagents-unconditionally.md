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
- ENH-2975
- ENH-2968
- ENH-2951
decision_needed: false
testable: true
labels:
- skills
- refine-issue
- cost
confidence_score: 96
outcome_confidence: 79
score_complexity: 17
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 22
depends_on:
- ENH-2983
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
with `## Root Cause` citing a resolving path and the symbol in it, spawns
fewer than three. A sparse FEAT still spawns all three.

Measured, this skips ~25% of axis-spawns corpus-wide under the ≥80% rule (see
Expected Yield in Program Design). Against 2,261 recorded refine invocations
that is on the order of 1,700 subagent calls avoided.

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

> **Selected:** Option A — cheap pre-classification. Keys on the issue's actual enrichment state (the thing that varies), not its type; scores 10/12 vs. Option B's 8/12.

**Option A — cheap pre-classification (recommended).** Insert a gap-triage
step before Step 3 that reads the issue and decides which of the three
research axes are unmet, using only what is already in the file:

| Agent | Skip when |
|---|---|
| `codebase-locator` | ≥80% of `## Integration Map`'s qualified paths resolve on disk |
| `codebase-analyzer` | `## Root Cause` (BUG) or `## Current Behavior` meets the same ≥80% bar **and** names a symbol |
| `codebase-pattern-finder` | `## Proposed Solution` meets the same ≥80% bar **and** names a symbol |

The ≥80% threshold is not a hedge — a conjunction rule ("all resolve") encodes
Integration Map size rather than currency. See "The rule must be
fraction-based" under Program Design.

Path resolution is not a new capability — `extract_file_paths()`
(`text_utils.py:53`) is already the project's public extractor for file
references in issue prose, and already strips code fences. ENH-2983 (this
issue's `depends_on`) promotes the surrounding classification to a shared
primitive this triage should consume rather than reimplement.

**Option B — issue-type defaults.** Fixed per-type agent sets (BUG → analyzer
+ locator; FEAT → all three; ENH → analyzer + pattern-finder). Simpler, but
wrong in both directions: a sparse BUG needs the pattern-finder, and an
enriched FEAT needs none of them.

**Recommended**: Option A — it keys on the actual state of the issue, which
is the thing that varies. Option B keys on type, which does not predict
enrichment level at all.

### Decision Rationale

**Selected: Option A — cheap pre-classification.**

Codebase evidence for Option A: `resolve_anchor()`
(`scripts/little_loops/issues/anchors.py:59-91`) already exists and is the
reusable primitive (not `_sweep_file()`/`SweepResult`, which is only an
aggregate counter). Precedent for section-scanning triage predicates that
feed a downstream decision is well established — `infer_testable()`,
`count_enumerable_options()`/`count_unresolved_options()` (explicit
cheap-pre-check-before-heavier-process comment at `issue_parser.py:543-548`),
and the `FormatGaps` dataclass shape. No single function does the full
3-axis composition today, but it follows directly-precedented shapes.

Codebase evidence against Option B: issue type (BUG/FEAT/ENH) is trivially
available at Step 3 (`_ISSUE_TYPE_RE`, `issue_parser.py:47`) and static
per-type dispatch has precedent (`load_issue_sections()`,
`issue_template.py:66-83`). But `format-check`'s content-driven gap classes
(`empty`/`boilerplate`, computed per-issue not per-type) confirm enrichment
level varies independently of type — the exact failure this issue's own
body names: "a sparse BUG needs the pattern-finder, and an enriched FEAT
needs none of them."

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 2 | 3 |
| Testability | 3 | 3 |
| Risk | 2 | 1 |
| **Total** | **10/12** | **8/12** |

Option A costs more implementation surface (composing `find_project_root` +
section extraction + `resolve_anchor` vs. a literal dict) but is the only
option that keys on the property that actually determines correct spawn
gating. Option B is simpler but systematically wrong in both directions per
the issue's own analysis.

## Program Design

The triage predicate is a pure function of (issue file, disk state), with no
network or model call: for each of the three axes, does the issue contain a
resolving reference of the kind that axis produces?

### Reference Resolution

**The primary signal is a resolving bare path, not a `file:N` anchor.** This
is the correction from Amendment 7 (see Post-Review Amendments) and it is the
single most important constraint in this section: an implementation that keys
on `file:N` ships inert. `ll-issues anchor-sweep` exists specifically to
rewrite `file.py:123` into `` `file.py` (near function `foo`) ``, and
`/ll:ready-issue`'s checklist enforces *"No `file:line` references outside
code fences"*. The corpus reflects that — across all 2,886 issue files, only
6 carry a `file:N` ref in Root Cause/Current Behavior and 15 in Proposed
Solution. Bare paths, by contrast, are ubiquitous.

Reference forms, in priority order:

| Reference form | Check | Primitive | Corpus frequency |
|---|---|---|---|
| bare path (`a/b.py`) | extract, then exists on disk relative to `root` | `extract_file_paths()` (`text_utils.py:53`) + `Path.exists()` | **primary** — see Expected Yield |
| symbol (`` `foo()` ``, `` `Cls.method` ``) | named in the same section as a resolving path | backtick-symbol regex over the fence-stripped section | strengthens analyzer / pattern-finder |
| anchor form (`` `a/b.py` (near function `foo`) ``) | path exists **and** symbol found in it | `extract_file_paths()` + symbol scan of the target | 16 files corpus-wide — accepted, not relied on |
| `file:N` | file readable, `N` in range, anchor found | `_FILE_LINE` (`anchor_sweep.py:24`) + `resolve_anchor()` + line-bound check | ~0 — **optional**, do not build the design on it |

`extract_file_paths(content: str) -> set[str]` is already public, already
strips code fences (so example paths in fenced blocks don't count as
coverage), and already normalizes `path.py:123` → `path.py`. It is the
extractor for **all three axes** as-is — **do not write a new bare-path
regex**; `_STANDALONE_PATH`/`_BACKTICK_PATH`/`_BOLD_FILE_PATH` are its
private internals.

#### Qualified-path filter (mandatory)

`extract_file_paths()` returns everything that *looks* like a path, including
references that can never resolve from the repo root no matter how current
the issue is. Triage must discard two classes before testing existence:

- **bare basenames** — no `/` in the path. Measured top offenders across
  Integration Maps: `config-schema.json` (247), `SKILL.md` (90),
  `__init__.py` (69), `executor.py` (44), `pyproject.toml` (57). These are
  prose mentions of a file by name, not locations.
- **glob patterns** — any `*` in the path, e.g. `skills/*/SKILL.md` (46).

Keep only directory-qualified, non-glob paths, then require those to exist.

This is not a tuning knob — it removes pure noise. **32.5% of all extracted
Integration Map paths do not resolve**, and this class of reference cannot
resolve for any issue however current. Filtering roughly doubles yield (see
Expected Yield).

**The filter alone does not make the predicate sound.** It raises the level
but does not remove the length bias that a conjunction rule introduces — that
is what the ≥80% fraction rule below is for. Both are required.

Genuine drift must still fail: `scripts/little_loops/session_store.py`
(78 references) correctly does not resolve because it became a package
directory. That is a real stale reference and the axis should stay uncovered.

#### The rule must be fraction-based (≥80%), not conjunction or count

**An axis is covered when ≥80% of its qualified paths resolve.** Not "all
resolve", and not "at most N unresolved".

The reason is a measured property of the corpus: **the per-path resolution
rate is flat at 83.5–87.7% across every Integration Map size band** (1–2
paths through 21+). Issue quality does not degrade with map size — a path in
a 25-path map is as likely to resolve as one in a 2-path map. Roughly 15% of
referenced paths are stale in a typical issue regardless of how enriched it
is.

Given a flat per-path failure rate, any conjunction or absolute-count rule
measures **map size**, not currency, because it compounds over `k` paths
(`0.85^k`):

| Rule | 1–2 paths | 6–10 | 11–20 | 21+ | Length-neutral? |
|---|---|---|---|---|---|
| all qualified resolve | 77.6% | 46.8% | 27.4% | 6.8% | no — `0.85^k` |
| ≤1 unresolved | 96.6% | 67.2% | 50.6% | 18.6% | no |
| **≥80% resolve** | **77.6%** | **69.4%** | **77.4%** | **69.5%** | **yes — 8.2pt spread** |
| ≥50% resolve | 91.5% | 95.3% | 96.4% | 97.2% | yes, but far too loose |

A conjunction rule would systematically respawn agents on exactly the
thorough, heavily-integrated issues — penalizing the enrichment this change
is supposed to reward. ≥80% holds within an 8.2-point band across a 10×
range of map sizes, and tolerates roughly the corpus's natural staleness rate
without tolerating outright drift the way ≥50% does.

**Caveat on discriminative power.** Because per-path staleness is ~15%
almost everywhere, "how current is this map" varies weakly across the corpus:
≥80% selects ~70–78% of issues fairly uniformly on the locator axis. The
coverage predicate is therefore a coarse filter, and the Staleness Check
below — which asks the sharper question, *did this file change since we last
looked* — carries more of the real discrimination. Sequencing matters: run
coverage first as a cheap reject, then Staleness Check as the decisive test.

**Path-only is sufficient for the locator axis; the analyzer and
pattern-finder axes additionally require a symbol.** The locator agent's
output *is* a set of file locations, so a resolving Integration Map satisfies
it. The other two produce claims about behavior and convention *inside* a
file, which a bare path alone does not evidence — requiring a co-located
symbol name keeps the skip honest. This is also what makes the
pattern-finder condition mechanically checkable: "states a convention with
evidence" is not, "cites a resolving path and names a symbol in it" is.

If `file:N` support is implemented as the optional fourth form, note that
**`resolve_anchor()` is a weaker signal than "current"**: it computes
`scan_end = min(line_number, len(lines))` (`anchors.py:80`), so a line number
well past EOF still resolves — it silently scans from the end of the file. It
also returns the nearest *preceding* definition regardless of drift. An
explicit `line_number <= len(lines)` bound is required before such a ref
counts as coverage. `_FILE_LINE` is currently private and does **not** strip
code fences on its own (`_sweep_file()` does that at the call site,
`anchor_sweep.py:63-68`), so this form costs a promotion plus fence handling
for ~0 corpus yield — defer it unless the primary path proves insufficient.

### Expected Yield — rule sensitivity (measured 2026-08-01)

**The resolution rule, not the corpus, dominates the yield.** Measured
percentage of the 3 axis-spawns skipped, across all 2,886 issue files and the
384 with 2+ recorded `/ll:refine-issue` Session Log entries:

| Resolution rule | All issues | 0 refines | 2+ refines | Notes |
|---|---|---|---|---|
| `file:N` anchors (pre-Amendment-7 design) | ~0.2% | — | ~0.2% | inert — see Amendment 7 |
| all extracted paths resolve, unfiltered | 8.0% | 8.1% | **4.8%** | noise- and length-dominated, **do not use** |
| qualified paths only, all resolve | 18.6% | 12.2% | 16.1% | still length-biased; **do not use** |
| **qualified paths, ≥80% resolve** | **25.1%** | **13.8%** | **29.3%** | **default** — length-neutral |
| qualified paths, ≥50% resolve | 27.6% | — | 33.9% | too loose — see rule table above |

Only the ≥80% rule orders the buckets the way the issue's premise predicts
(2+ refines > 0 refines). Note this ordering is **weak evidence**: 0-refine
issues are systematically smaller (median 4 qualified paths and 6.7k chars,
vs 15 paths and 19.7k chars at 2+ refines), so the buckets are confounded by
size and are not a controlled comparison. The load-bearing evidence for the
rule choice is the within-size-band table above, which removes that confound.

**Planning figure: ~25% of axis-spawns skipped.** Absolute volume is the
stronger argument: the corpus records **2,261 `/ll:refine-issue` invocations
≈ 6,800 subagent calls**, so ~1,700 avoided.

Three things this measurement does **not** establish:

- It scores each issue in its *current* (final) state, not the state it was in
  at each historical refine invocation. It is a proxy for the re-refine case,
  not a replay of it.
- The refine-count buckets are confounded by issue size (above). Only the
  within-band measurements are confound-free.
- No variant has been validated for **false skips** — an axis marked covered
  whose agent would have contributed new findings anyway. This is the gap the
  calibration step's sampling exists to close, and it is the reason ≥80% is
  the default rather than the higher-yield ≥50%.

Latency is an uncounted benefit: on a skipped axis a millisecond CLI call
replaces a subagent round-trip, which is most of Step 3's wall-clock on the
`autodev.yaml` critical path.

### Staleness Check (file change time vs. last refine)

A reference resolving is not the same as its target being unchanged since the
issue last incorporated it. Without a second check, a re-refine on a file
that changed materially after the prior pass would silently skip the agent
whose findings just went stale — the exact failure mode this issue exists to
avoid reintroducing.

For each axis whose reference resolves, compare two timestamps, both already
available with no new storage:

- **Referenced file's change time** — `max(git commit time, filesystem
  mtime)`, for every path the axis's evidence resolved against.
- **Last refine timestamp that could have written this section** — the most
  recent `/ll:refine-issue` entry in the issue's own `## Session Log`
  (`- /ll:refine-issue - <ISO timestamp> - ...`).

**Both clocks are required; git commit time alone is wrong here.** This repo
is developed with a persistently dirty working tree (CLAUDE.md: *"uncommitted
changes here are immediately live in every one of them, with no reinstall
step"*), so a file edited after the last refine but not yet committed reads
as unchanged under a git-only check — reintroducing precisely the
skip-a-stale-axis failure this section exists to prevent. Filesystem `mtime`
catches the working-tree case; git commit time is the fallback for fresh
clones and CI checkouts, where `mtime` is checkout time and carries no
authoring signal. Taking the max is correct in both environments.

**Batch the git call.** `git log -1 --format=%cI -- <path>` is one subprocess
per referenced path, and Integration Maps routinely list 5–10 — a fan-out of
subprocesses on the hot path of every refine, to save subagent calls. Use a
single `git log --format=%cI --name-only -n <N>` pass (or one
`git ls-files -z` + `os.stat` sweep) and index the result in memory.
`mtime` needs no subprocess at all.

If the file's change time is **after** that Session Log timestamp, the
axis is treated as `covered=False` even though the anchor resolves —
`AxisCoverage.evidence` records the reason (e.g. `"stale: <path> changed
<change_ts>, issue last refined <refine_ts>"`) instead of the satisfying
section/path. If the issue has no prior `/ll:refine-issue` Session Log entry
(first-ever refine), there is nothing to compare against and the file-mtime
check is skipped — resolution alone decides coverage, same as before this
amendment.

This mirrors a standard cache-invalidation check (source changed after cache
was written → invalidate) using data the issue already carries, so it adds
no new fields to track and no model call. It is deliberately file-grained,
not line-grained: an unrelated edit anywhere in a large referenced file
forces a re-spawn even if the anchored lines didn't move. That trades a rarer
wasted agent call for closing the actual risk this issue's own Risk section
names as dominant — silently trusting drifted findings — so the tradeoff
runs in the safer direction. `--full-rewrite` remains the escape hatch for
anything this check still misses (e.g. drift within a file whose change time
did not move).

### Signatures

Extracted to Python (see Scope Boundaries):

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

### CLI Surface (required — the command cannot call Python directly)

`commands/refine-issue.md` is markdown; its only route to Python is `Bash`,
and its `allowed-tools` permits `Bash(git:*, ll-issues:*)` and
`Bash(ll-history-context:*)` — nothing else. An extracted
`triage_research_axes()` with no CLI entry point is unreachable from Step 3
and the change ships inert.

Add a subcommand under `scripts/little_loops/cli/issues/`:

```
ll-issues research-triage <ISSUE_ID> [--json]
```

`--json` emits the axis map Step 3 branches on:

```json
{
  "locator":        {"covered": true,  "evidence": "Integration Map → commands/refine-issue.md"},
  "analyzer":       {"covered": false, "evidence": ""},
  "pattern_finder": {"covered": false, "evidence": ""}
}
```

Exit 0 whenever the issue is readable, including when every axis is unmet —
a nonzero exit would be indistinguishable from a missing issue and would push
Step 3 into an error branch on the common case. If the CLI fails for any
reason, Step 3 falls back to spawning all three agents (fail-open: the cost
regression is the current behavior, the cost of failing closed is a silently
under-researched issue).

### All-Axes-Covered Case (zero agents)

Triage can legitimately return `covered=True` on all three axes — that is the
best case for this issue's motivation, and it is currently undefined
behavior. Step 4 says *"Using the research findings from Step 3, identify what
information is missing"* and Step 5a says *"For each FILLABLE gap, update the
issue with research findings"*. With zero agents spawned there are no research
findings, and those instructions read as an invitation to write enrichment
from nothing — a fabrication risk strictly worse than the wasted agent calls
this issue set out to remove.

Step 3 must therefore branch explicitly: **zero unmet axes → skip Steps 4,
5a, and 5b entirely**, proceed to the Step 5c/6 gates, append the Session Log
entry (Step 7) noting a no-op refine, and report which axis each `evidence`
string satisfied. A refine that correctly does nothing must still be
observable as having run — otherwise a caller cannot distinguish "already
enriched" from "refine failed silently".

### Call Path

- `/ll:refine-issue` Step 3 → `Bash: ll-issues research-triage <ID> --json`
  → `triage_research_axes()` → `extract_file_paths()` + `Path.exists()`
  (+ symbol scan on the analyzer/pattern-finder axes). `resolve_anchor()`
  (`scripts/little_loops/issues/anchors.py:59`) is needed only if the optional
  `file:N` form is implemented — not on the primary path. `_sweep_file()` is
  not used at all: it only accepts a filesystem `Path` and reads the whole
  file, and its `skipped_refs` is an aggregate counter with no per-reference
  data (see Codebase Research Findings — Reference Primitives).
- `find_project_root` — resolves the repo root extracted paths are joined
  against before the per-reference `exists()` checks
- Step 3 then spawns one `Task` per axis whose `covered` is False, or takes
  the zero-agent branch above if none are

**Which invocations triage.** Triage applies on **every path except
`--full-rewrite`**, which keeps the unconditional 3-agent spawn since a full
rewrite is by definition not trusting what is already in the file. This is
deliberately broader than "only `--gap-analysis`": the dominant call sites
are plain `--auto` (`autodev.yaml:546`, `refine-to-ready-issue.yaml:125`,
`harness-multi-item.yaml:63`, `rn-remediate.yaml:314`), against only two
`--gap-analysis` sites (`autodev.yaml:770`,
`refine-to-ready-issue.yaml:142`). Plain `--auto` is already an additive path
— Step 5a is "Fill Gaps with Research Findings" — so gating triage on
`GAP_ANALYSIS` alone would exempt most invocations and deliver almost none of
the savings this issue exists to capture.

Failure mode to design against: triage skipping an agent whose findings were
stale rather than absent. A reference that resolves is not necessarily
*current* (see Reference Resolution above) — this is now bounded by the
Staleness Check, not by `--full-rewrite` alone; `--full-rewrite` remains the
backstop for drift neither clock can see (in-place drift within a file whose
change time did not move).

### Codebase Research Findings — Reference Primitives

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `_sweep_file(path: Path, dry_run: bool, result: SweepResult) -> None`
  (`scripts/little_loops/issues/anchor_sweep.py:59`) cannot be fed section
  text directly — it only accepts a filesystem `Path` and reads that file's
  full content internally (`path.read_text(...)`, line 61). There is no
  string/text entry point. Calling it against `## Integration Map` / `##
  Root Cause` / `## Proposed Solution` text (as `triage_research_axes` would
  need to) requires either writing each section's text to a temp file first,
  or splitting the regex-scan/resolve logic out of `_sweep_file()` so it can
  operate on an arbitrary string.
- `SweepResult.skipped_refs` (same file) is an **aggregate integer counter**
  across an entire sweep run, not a structured per-reference or per-axis
  result — it carries no data on which reference failed, in which file, or
  under which section heading. The per-reference detail exists only in a
  `warnings.warn(...)` call (lines 75-80), not in any field callers can read.
  Reusing `skipped_refs` as-is does not give `triage_research_axes` the
  per-axis granularity the Program Design assumes; the reusable primitive is
  `resolve_anchor()` (`scripts/little_loops/issues/anchors.py:59`), not
  `_sweep_file()`/`SweepResult` itself.
- Neither `_sweep_file()` nor `resolve_anchor()` takes a project-root
  parameter — `resolve_anchor()` resolves referenced files exactly as
  written in the issue text, relative to process CWD, with no
  root-anchoring logic. `find_project_root(start: Path) -> Path | None`
  (`scripts/little_loops/paths.py:14`) exists and is what the proposed
  `triage_research_axes(issue_path, root)` would call to obtain `root`, but
  composing it with anchor resolution (joining `root` against each
  extracted reference path before resolving) does not exist today and would
  need to be written.
- Today, `commands/refine-issue.md` Step 5c only *cites* `_sweep_file()`/
  `skipped_refs` in prose (lines 512, 516) as the conceptual definition of
  "resolves" — there is no `Bash(...)` invocation of `ll-issues anchor-sweep`
  anywhere in the command body, so this would be the first executable use of
  anchor resolution inside `refine-issue.md` rather than a second caller of
  an already-wired call.

## Integration Map

### Files to Modify

- `commands/refine-issue.md` — Step 3 gains a triage preamble (a `Bash`
  call to `ll-issues research-triage`); the "spawn all 3" instruction becomes
  "spawn the unmet set". `allowed-tools` already permits `Bash(ll-issues:*)`,
  so no frontmatter change is needed
- `scripts/little_loops/issues/research_triage.py` (new) —
  `triage_research_axes()`, `AxisCoverage`, `ResearchAxis`
- `scripts/little_loops/cli/issues/` (new subcommand module + parser
  registration) — `ll-issues research-triage <ID> [--json]`
- `scripts/little_loops/issues/anchor_sweep.py` — **only if** the optional
  `file:N` form is implemented: promote `_FILE_LINE` to an importable name
  (or move it to `text_utils.py` alongside the bare-path patterns it is
  documented against). Not required for the primary path — Amendment 7 moved
  `file:N` off it
- **All host mirrors** — regenerate via `ll-adapt`; each mirror embeds the
  command body verbatim, so a Step 3 rewrite that skips them leaves other
  hosts running the old unconditional 3-agent spawn. `ll-adapt` registers
  four hosts (`codex`, `gemini`, `kimi-code`, `omp`); run it for each rather
  than naming files, since which hosts carry a `refine-issue` artifact can
  change:

  ```bash
  for h in codex gemini kimi-code omp; do ll-adapt --host "$h" --apply; done
  ```

  Today that touches `.gemini/commands/refine-issue.toml` and
  `.kimi-code/skills/ll-refine-issue/SKILL.md`; `codex` and `omp` have no
  `refine-issue` artifact and no-op. Note `--only` restricts *agent*
  processing only — it does not filter commands, so expect unrelated
  already-drifted mirrors to regenerate in the same run.

### Dependent Files

- `scripts/little_loops/loops/autodev.yaml` — invokes `/ll:refine-issue`;
  behavior change is internal to the command, no loop edit expected
- `scripts/little_loops/issues/anchors.py:resolve_anchor()` — the reusable
  primitive `triage_research_axes` calls; Step 5c cites the "resolves"
  concept in prose today but has no executable call, so this is the first
  wired use of anchor resolution in `refine-issue.md`, not a second caller

### Conventions in Force

- Path extraction from issue prose goes through `extract_file_paths()`
  (`text_utils.py:53`), not an ad-hoc regex — evidence: `dependency_mapper`
  and `issue_history` both consume it, and it is the only extractor that
  strips code fences and normalizes `:NNN` suffixes.
- ~~Reference resolution is decided by `_sweep_file()`'s `skipped_refs`~~ —
  **retracted.** Step 5c's prose says this, but `skipped_refs` is an
  aggregate integer counter with no per-reference data (see Codebase Research
  Findings). The reusable primitive is `resolve_anchor()`. Step 5c's wording
  is stale and should not be treated as the convention to follow; correcting
  it is out of scope here (see Scope Boundaries).

### Tests

- No current test exercises `refine-issue`'s spawn set (it is a markdown
  command, not Python). The measurable gate is the triage predicate itself if
  it is extracted to Python; if it stays prose, this ships unverified — see
  Scope Boundaries.

### Codebase Research Findings — Testing & Precedent

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_refine_issue_command.py` already exercises
  `commands/refine-issue.md`'s prose structure directly, without any Python
  extraction — e.g. `test_option_count_detection_block_present` and
  `test_section_5c_exists_after_5b` locate a step by `content.index(...)`
  and assert on substrings within that slice. This is precedent that a
  prose-only triage rule in Step 3 is independently testable the same way
  (assert the triage table/predicate text is present, and that the spawn
  instruction is conditioned on it) — it does not require Python extraction
  to get *a* real test, only to get a test of the triage predicate's actual
  *behavior* on a given issue file (which a prose-structure assertion cannot
  verify).
- `scripts/little_loops/cli/verify_skill_prose.py`'s `PROSE_MARKERS` is a
  curated tuple of exactly six regex markers (jaccard word-overlap,
  inline stopword list, session-JSONL scan, inline `python3 -c`, `git mv`
  glob loop, union-find/cluster-merge) — none matches gap-triage or
  conditional-spawn phrasing. Leaving the triage predicate as prose would
  **not** trip `ll-verify-skill-prose`'s exit code either way; the
  extraction-to-Python convention this issue's Scope Boundaries invokes is
  followed by precedent elsewhere in the codebase (`prose_deps.py`,
  `anchor_sweep.py`), not enforced by this specific gate.
- `scripts/little_loops/issue_history/models.py` has no `TestGap` class —
  the actual dataclass is `Gap` (`models.py:259-281`, not frozen, `priority`
  typed `str` with an inline comment rather than `Literal`, always paired
  with a hand-written `to_dict()`). If `AxisCoverage` is modeled after it,
  match `Gap`'s shape (plain `@dataclass`, `to_dict()`) rather than the
  frozen/`Literal` shape the current Program Design signature proposes —
  though `@dataclass(frozen=True)` does have precedent elsewhere
  (`ProseMarker` in `verify_skill_prose.py:42-49`), so both shapes exist in
  the codebase and neither is the sole convention.
- No existing command conditions which subset of parallel research subagents
  it spawns on a computed predicate — `scan-codebase.md`, `manage-release.md`,
  `analyze-workflows.md`, and `refine-issue.md` itself all spawn their full
  agent set unconditionally today. This confirms the proposed per-axis gating
  is a new pattern in this codebase, not one with an existing spawn-gating
  template to follow.

## Implementation Steps

1. Write `scripts/little_loops/issues/research_triage.py`:
   `ResearchAxis`, `AxisCoverage`, `triage_research_axes(issue_path, root)`.
   All three axes extract via `extract_file_paths()`, apply the mandatory
   qualified-path filter (drop bare basenames and globs), then require
   **≥80% of the remaining paths to resolve** against `root`; the analyzer and
   pattern-finder axes additionally require a backtick-quoted symbol in the
   same fence-stripped section. Do **not** use a conjunction or absolute-count
   rule — see "The rule must be fraction-based". The optional `file:N` form is
   out of the v1 critical path. Keep the 0.8 threshold behind a single named
   constant — step 2 validates it.
2. **Validate the threshold.** Confirm length-neutrality holds (per the AC)
   and check false skips: sample ~20 issues the rule marks covered and confirm
   the corresponding agent would not have contributed new findings. Adjust the
   threshold only if the sample shows a problem; ≥80% is the measured default,
   not a placeholder. Record the outcome in this issue before rewriting the
   command body.
3. Add the Staleness Check to `triage_research_axes()`: for each resolving
   path, `max(git commit time, os.stat().st_mtime)` vs. the most recent
   `/ll:refine-issue` Session Log timestamp; batch the git lookup into one
   pass rather than one subprocess per path.
4. Add the `ll-issues research-triage <ID> [--json]` subcommand under
   `scripts/little_loops/cli/issues/`, exit 0 on any readable issue.
5. Rewrite `commands/refine-issue.md` Step 3: call the CLI, parse the axis
   map, spawn one `Task` per uncovered axis. Gate on
   `FULL_REWRITE == false`. Fall back to all three agents if the CLI fails.
   Add the zero-unmet-axes branch that skips Steps 4/5a/5b and reports a
   no-op refine (see All-Axes-Covered Case).
6. Regenerate all host mirrors via `ll-adapt` — one `--apply` run per
   registered host (`codex`, `gemini`, `kimi-code`, `omp`), not just
   `.gemini`.
7. Add tests (see Acceptance Criteria).

## Acceptance Criteria

- [ ] `triage_research_axes()` on a sparse issue (no resolving refs in any
      section) returns `covered=False` for all three axes.
- [ ] `triage_research_axes()` on an enriched issue whose Integration Map
      paths all exist returns `covered=True` for `locator`, with `evidence`
      naming the satisfying section and path.
- [ ] A resolving path in Root Cause / Proposed Solution with **no** symbol
      named in the same section returns `covered=False` for that axis; adding
      a backtick-quoted symbol flips it to `covered=True`.
- [ ] A ref appearing only inside a fenced code block does not count as
      coverage on any axis.
- [ ] A bare basename (`executor.py`) and a glob (`skills/*/SKILL.md`) are
      excluded by the qualified-path filter — neither counts toward coverage
      nor causes an otherwise-covered axis to fail.
- [ ] **Corpus baseline** — `triage_research_axes()` run over the full
      `.issues/` corpus skips ≥20% of axis-spawns overall.
- [ ] **Length neutrality** (the load-bearing gate) — locator-axis coverage
      measured within Integration Map size bands (1–2, 3–5, 6–10, 11–20, 21+
      qualified paths) varies by **no more than 15 percentage points** between
      the smallest and largest band. Measured ≥80% spread is 8.2 points; a
      conjunction rule spreads 70.8 points and must fail this. This is the
      gate that catches a predicate which encodes map size rather than
      currency — a raw overall threshold does not, and neither does a
      refine-count comparison, since those buckets are confounded by size.
- [ ] The threshold validation from Implementation Step 2 is recorded in this
      issue — measured skip rate, band spread, and false-skip sample outcome —
      before the command body is rewritten.
- [ ] A resolving reference whose target file was modified in the working
      tree (uncommitted) after the issue's most recent `/ll:refine-issue`
      Session Log entry returns `covered=False` — mtime, not just git commit
      time, drives staleness.
- [ ] A resolving reference whose target file's last commit time is *after*
      the issue's most recent `/ll:refine-issue` Session Log entry returns
      `covered=False`, with `evidence` naming it stale rather than unmet.
- [ ] A resolving reference whose target file's change time is *before* the
      issue's most recent `/ll:refine-issue` Session Log entry still returns
      `covered=True` (staleness check does not produce false negatives on
      genuinely current references).
- [ ] An issue with no prior `/ll:refine-issue` Session Log entry skips the
      staleness comparison and falls back to resolution-only coverage.
- [ ] `ll-issues research-triage <ID> --json` emits the three-key object and
      exits 0 when every axis is unmet.
- [ ] `ll-issues research-triage` on a nonexistent issue ID exits nonzero.
- [ ] `commands/refine-issue.md` Step 3 conditions its spawn set on the
      triage output, preserves the unconditional 3-agent spawn under
      `--full-rewrite`, and contains the zero-unmet-axes branch that skips
      Steps 4/5a/5b — asserted structurally, in the style of
      `scripts/tests/test_refine_issue_command.py`'s
      `test_option_count_detection_block_present`.
- [ ] Every host mirror matches the updated command body — verified by
      re-running `ll-adapt --host <h>` (dry-run) for each registered host and
      confirming no pending changes for `refine-issue`.
- [ ] `python -m pytest scripts/tests/` passes.

## Scope Boundaries

- **In scope**: gating which agents spawn, and the CLI surface needed to
  reach the triage predicate from a markdown command.
- **Out of scope**: changing what any agent is asked for, or the prompts
  themselves.
- **Already fixed (2026-08-01, pre-implementation)**: Step 5c's stale
  `_sweep_file()`/`skipped_refs` and `models.py:TestGap` references. Step 5c
  now states the `resolve_anchor()` + line-bound rule this issue's triage
  predicate must also use, so the two share one definition of "resolves"
  rather than each growing its own. `commands/refine-issue.md` and both
  mirrors (`.gemini`, `.kimi-code`) are updated.
- **Decided**: extract the triage predicate into `scripts/little_loops/issues/`
  as a testable function rather than leaving it as prose in the command.
  Extraction is the only path to a test that verifies the predicate's actual
  output on a given issue file (a prose-only rule only supports structural
  assertions, à la `test_option_count_detection_block_present`) —
  `ll-verify-skill-prose` exists specifically to push algorithms out of skill
  prose, and the Confidence Check's Outcome Risk Factors flagged the untested
  path as the dominant risk. This raises the effort estimate to Medium (see
  Impact).

## Impact

- **Effort**: Medium — the triage predicate is extracted to Python and tested
  (see Scope Boundaries).
- **Expected benefit**: ~25% of research subagent calls avoided under the
  ≥80% rule (see Expected Yield). Against the 2,261 refine invocations the
  corpus records, that is ~1,700 subagent calls. Latency benefit exceeds the
  token benefit on skipped axes, since a millisecond CLI call replaces a
  subagent round-trip on `autodev.yaml`'s critical path.
- **Risk**: Medium — the failure mode is skipping an agent whose findings
  were needed, producing a quieter refine that looks successful. The
  Staleness Check (Program Design) closes the dominant case — target file
  changed since the last refine — using `max(git commit time, mtime)` and
  timestamps the issue already carries; `--full-rewrite` remains the escape
  hatch for drift neither clock can see.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 62/100 → LOW

### Outcome Risk Factors
- ~~Test coverage depends on an unresolved implementation choice~~ —
  **resolved 2026-08-01.** Scope Boundaries now decides extraction to Python;
  Acceptance Criteria specify behavioral tests on the predicate plus a
  structural assertion on the command body.
- ~~The Scope Boundaries section leaves an open question unresolved~~ —
  **resolved 2026-08-01.** Effort is Medium.

### Post-Review Amendments (2026-08-01)

**Amendment 9 (2026-08-01)** — Amendment 8 diagnosed the length bias
correctly but prescribed a fix that does not remove it, and cited confounded
evidence.

Two errors:

1. **The qualified-path filter does not "restore the expected direction"**, as
   Amendment 8 claimed. Filtering raises the level but leaves the conjunction
   bias intact: post-filter, all-resolve coverage still runs 77.6% at 1–2
   paths down to 6.8% at 21+, and still orders the refine buckets 59.4% /
   50.1% / 28.6%. The claim was asserted without being measured.
2. **The refine-count buckets are confounded by issue size.** 0-refine issues
   have median 4 qualified paths and 6.7k chars; 2+-refine issues have 15 and
   19.7k. Issues that skip refinement are systematically smaller (small
   issues, or ones implemented directly by a human operator), so that
   comparison was never a controlled test and should not have been used as
   evidence. The directional AC Amendment 8 added on that basis was invalid —
   it measured size, and would have failed under every rule except the
   too-loose ≥50%.

Root cause, measured confound-free within size bands: **the per-path
resolution rate is flat at 83.5–87.7% across all Integration Map sizes.**
Issue quality does not degrade with map size; ~15% of referenced paths are
stale everywhere. Given a flat per-path failure rate, any conjunction
(`0.85^k`) or absolute-count rule necessarily encodes map size rather than
currency — which is why both the unfiltered *and* filtered all-resolve rules
fail, and why count-based rules (`≤1 unresolved`: 96.6% → 18.6%) fail too.
Only a fraction-based rule is length-neutral.

Changes: default rule is now **≥80% of qualified paths resolve** (8.2-point
spread across a 10× size range, vs 70.8 for conjunction), documented in a new
"The rule must be fraction-based" subsection with the within-band evidence;
corrected the filter subsection's false claim; Expected Yield updated to
25.1% overall / 29.3% on 2+-refines, with the bucket confound stated inline
so the ordering is not read as strong evidence; replaced the invalid
directional AC with a **length-neutrality AC** (≤15-point spread across size
bands); Implementation Step 2 narrowed from open calibration to threshold
validation.

Also recorded a design caveat: because per-path staleness is ~15% almost
everywhere, the coverage predicate discriminates weakly (≥80% selects
~70–78% of issues fairly uniformly on the locator axis). The Staleness Check
asks the sharper question and should be sequenced as the decisive test, with
coverage as a cheap pre-reject.

**Amendment 8 (2026-08-01)** — Amendment 7's yield figure was overconfident
and its resolution rule was wrong in a way that hid the error.

The reported "~10–12%" was one point in a **4× range** that depends entirely
on the resolution rule, presented as if it were a property of the corpus:

| Rule | All issues | 2+ refines |
|---|---|---|
| all extracted paths resolve (Amendment 7's rule) | 8.0% | 4.8% |
| qualified paths only, all resolve | 18.6% | 16.1% |
| ≥50% of qualified paths resolve | 27.6% | 33.9% |
| any qualified path resolves | 34.2% | 46.1% |

Amendment 7 picked the strictest variant arbitrarily. That rule also produced
a result that should have been caught as a tell: issues refined 2+ times
scored **lower** (4.8%) than issues never refined (8.1%), inverting this
issue's own premise that savings concentrate on re-refines.

Root cause: **32.5% of extracted Integration Map paths never resolve
regardless of drift** — bare basenames (`config-schema.json` ×247,
`SKILL.md` ×90, `__init__.py` ×69) and glob patterns (`skills/*/SKILL.md`
×46). Under "all must resolve", that noise scales with Integration Map
length, so richer issues score worse. The mandatory qualified-path filter
(Reference Resolution) removes it and restores the expected direction.
*(Superseded by Amendment 9 — the filter removes the noise but not the
length bias; only the ≥80% fraction rule does. The bucket comparison cited
here is also confounded by issue size.)*

Changes: added the qualified-path filter as a non-optional preprocessing
step; replaced the Expected Yield table with the sensitivity table plus
explicit statements of what the measurement does *not* establish (it scores
current state, not state-at-invocation; no variant is false-skip validated);
added Implementation Step 2 to calibrate the rule against the corpus with a
false-skip sample; added a directional AC (rate on 2+-refine issues must not
be *lower* than on never-refined ones) since a raw threshold would not have
caught the inversion. Also recorded absolute volume — 2,261 refine
invocations ≈ 6,800 subagent calls — which is the stronger case for the
change than the percentage.

**Amendment 7 (2026-08-01, pre-implementation review)** — four findings, one
of which invalidated the design's central mechanism.

1. **Blocking — the triage keyed on a reference form this repo deliberately
   removes.** The analyzer and pattern-finder axes resolved via `_FILE_LINE`
   (`anchor_sweep.py:24`), which requires a `:NNN` suffix. But `ll-issues
   anchor-sweep` exists to rewrite `file.py:123` → `` `file.py` (near
   function `foo`) ``, and `/ll:ready-issue`'s checklist enforces *"No
   `file:line` references outside code fences"*. Measured across all 2,886
   issue files: **6** carry a `file:N` ref in Root Cause/Current Behavior,
   **15** in Proposed Solution, **16** carry anchor form anywhere. Two of
   three axes would have been dead on arrival, all ACs would still have
   passed (they were written against synthetic `file:N` fixtures), and the
   change would have shipped measurably inert. Reference Resolution is
   rewritten around bare-path resolution (`extract_file_paths()` +
   `Path.exists()`, viable at 15%/15%/7% per axis) plus a co-located symbol
   requirement on the two behavioral axes; `file:N` is demoted to an optional
   form. A corpus-baseline AC now gates against this class of regression.
   This also makes the pattern-finder condition mechanically checkable —
   "states a convention with evidence" was never a computable predicate.
2. **Amendment 6's staleness check used the wrong clock.** `git log -1` alone
   misses working-tree edits, and this repo is developed with a persistently
   dirty tree where uncommitted changes are live in every consuming project
   — the exact case most likely to strand a stale axis. Now
   `max(git commit time, filesystem mtime)`, with an AC for the uncommitted
   case. Also flagged the per-path subprocess fan-out; the git lookup must be
   batched.
3. **The all-covered case was undefined.** Zero unmet axes means zero
   research findings, while Steps 4/5a still instruct the model to fill gaps
   "using the research findings from Step 3" — a fabrication risk worse than
   the wasted calls being removed. Added the All-Axes-Covered Case section
   and an AC.
4. **Expected benefit was unstated and assumed larger than it is.** Added the
   Expected Yield table: ~10–12% of subagent calls avoided, not "fewer than
   three on most re-refines". Recorded in Impact so scope stays proportionate.
   *(Superseded by Amendment 8 — that figure was the strictest of four rule
   variants spanning 8%–34%, and the rule producing it was noise-dominated.)*
   Also disambiguated the two identically-named
   `### Codebase Research Findings` headings.

**Amendment 6** — the original design tolerated stale-but-resolving
references by design, bounded only by the manual `--full-rewrite` opt-in.
That left the dominant repeat-use case (gap-analysis re-runs, this issue's
own stated motivation) unprotected against skipping an agent whose target
file changed materially since the last refine. Added a git-mtime Staleness
Check to Program Design: compare each resolving reference's target file's
last commit time (`git log -1 --format=%cI`) against the issue's most recent
`/ll:refine-issue` Session Log timestamp; treat the axis as uncovered if the
file changed after that pass. Uses only data the issue already carries (no
new stored state, no model call). Three ACs added.

Pre-implementation review found and fixed five gaps:

1. **Blocking** — the extracted function had no CLI entry point, so
   `refine-issue.md` (markdown, `Bash(ll-issues:*)` only) could not call it.
   Added `ll-issues research-triage`.
2. The mitigation gated triage on `--gap-analysis`, which is 2 of 6 call
   sites; the dominant path is plain `--auto`. Restated as "every path except
   `--full-rewrite`".
3. `resolve_anchor()` alone cannot serve the locator axis — it requires a
   line number, and Integration Map entries are usually bare paths. Reference
   Resolution now specifies `extract_file_paths()` + `Path.exists()` for
   bare paths and `_FILE_LINE` + `resolve_anchor()` for anchors.
   *(Superseded by Amendment 7 — the `_FILE_LINE` half is now optional; bare
   paths are the primary signal on all three axes.)*
4. `resolve_anchor()` clamps `scan_end = min(line_number, len(lines))`, so
   out-of-range line numbers resolve anyway. An explicit line-bound check is
   now required, with an AC covering it.
5. Conventions in Force contradicted the issue's own research findings
   (`skipped_refs` as the resolution primitive); retracted. Implementation
   Steps contained assertions rather than steps; split into real steps plus
   an Acceptance Criteria section.

## Session Log
- `/ll:confidence-check` - 2026-08-02T00:45:03 - `b0869093-304a-4a68-b09f-0b4e513fe075.jsonl`
- `/ll:confidence-check` - 2026-08-02T00:04:35 - `f987e26d-d7db-45bc-8a17-37251e0f4d3b.jsonl`
- `/ll:confidence-check` - 2026-08-01T23:34:48 - `36118e03-b486-4fd8-bdce-33c07200425f.jsonl`
- `/ll:decide-issue` - 2026-08-01T23:24:00 - `c8f05642-0169-4b49-b2f7-0a9516878297.jsonl`
- `/ll:confidence-check` - 2026-08-01T23:21:03 - `36613d49-6819-46cd-9429-73065b652d56.jsonl`
- `/ll:decide-issue` - 2026-08-01T23:17:07 - `e793519f-51e2-493d-bf78-f52d7aa3a13c.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:15:33 - `ff34935c-8665-404f-842a-5e8bdb323ccc.jsonl`
- `/ll:capture-issue` - 2026-08-01

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
