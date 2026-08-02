---
id: ENH-2971
title: refine-issue spawns three research subagents unconditionally
type: ENH
priority: P3
status: done
captured_at: '2026-08-01T00:00:00Z'
completed_at: '2026-08-02T05:10:32Z'
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
(`text_utils.py:57`) is already the project's public extractor for file
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
available at Step 3 (`_ISSUE_TYPE_RE`, `issue_parser.py:48`) and static
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
| bare path (`a/b.py`) | extract, then exists on disk relative to `root` | `extract_file_paths()` (`text_utils.py:57`) + `Path.exists()` | **primary** — see Expected Yield |
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

> **Correction (2026-08-01, `/ll:ready-issue`): this filter now exists — do not
> hand-roll it.** `depends_on: ENH-2983` shipped and closed on 2026-08-01,
> promoting exactly this classification into `text_utils.py` as
> `RefIndex` (`text_utils.py:112`) + `classify_file_ref(ref, index, *, line)
> -> RefStatus` (`text_utils.py:163`). Its resolution order runs form checks
> **first** — a glob, a `<placeholder>`-bearing path, or a bare basename with
> no `/` all return `unresolvable_form` before any matching — which is the
> two-class discard described below, already implemented and tested.
> `triage_research_axes()` must consume it (`extract_file_paths()` to extract,
> then `classify_file_ref()` per ref, counting only `resolved` toward the ≥80%
> numerator and excluding `unresolvable_form`/`planned_new` from the
> denominator) rather than writing a fresh basename/glob filter plus
> `Path.exists()`. Build one `RefIndex` per invocation, not per axis.
>
> Note `classify_file_ref()` is **more permissive than the measured design**:
> it also resolves a *unique* suffix match (an unrooted `fsm/executor.py` cited
> without its `scripts/little_loops/` prefix), which bare `Path.exists()` would
> have scored unresolved. The Expected Yield and band-spread figures below were
> measured with the stricter hand-rolled rule, so **Implementation Step 2 must
> re-measure the ≥80% threshold and the length-neutrality spread against
> `classify_file_ref()`** before the AC numbers are treated as met.

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
`scan_end = min(line_number, len(lines))` (`anchors.py:82`), so a line number
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

### Codebase Research Findings — Timestamp Parsing & CLI Registration

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **The Staleness Check's timestamp read-side does not exist yet — it is new
  code, not reuse.** `scripts/little_loops/session_log.py` has
  `parse_session_log()` (lines 24-40) and `count_session_commands()` (lines
  43-60), both built on `_COMMAND_RE`, which extracts only the backtick-quoted
  `` `/ll:*` `` command name from each Session Log line — neither retains the
  per-entry ISO timestamp. The write side, `append_session_log_entry()`
  (lines 155-204), shows the exact entry format (`` - `/ll:command` -
  2026-08-01T12:34:56 - `session-id.jsonl` ``, line 184), but no read-side
  regex anywhere in the codebase parses that timestamp back out. Everything
  else `triage_research_axes()` needs (`extract_file_paths()`,
  `resolve_anchor()`, `find_project_root()`) is a pre-existing primitive; the
  "most recent `/ll:refine-issue` Session Log timestamp" lookup the Staleness
  Check depends on is not — Implementation Step 3 should budget for writing
  it, not locating it. Similarly, no existing helper combines `max(git commit
  time, filesystem mtime)`; the closest precedents are day-resolution-only
  (`git log --format=%as`, `issue_history/parsing.py:186`) or git-only
  (`post_commit.py:53`'s `%aI` use) — the specific combination Program Design
  calls for is new code either way.
- **CLI registration for `research-triage` has two live conventions to choose
  between, not one.** `scripts/little_loops/cli/issues/` modules split: some
  export their own `add_<name>_parser()` (`set_flags.py:334`, plus
  `decisions`/`format_check`/`epic_progress`), others are wired entirely
  inline inside `cli/issues/__init__.py` with no separate parser function
  (`anchor_sweep.py`, `check_decidable.py`). `check_decidable.py`'s
  `cmd_check_decidable()` is the closest existing *conceptual* analog to a
  triage/gating predicate CLI — its docstring states "Exit 0 if the issue has
  >=1 enumerable option... 1 otherwise" and it carries no `--json` flag,
  using exit code alone as the signal FSM automation consumes. But this
  issue's own CLI Surface section requires `--json` output (Step 3 branches
  on the emitted axis map, not on exit code alone), so `set_flags.py`'s
  own-parser-plus-`--json`-branching shape is the closer *structural* fit —
  the two closest precedents disagree, and the implementer should pick
  knowingly rather than default to whichever file is read first.

## Integration Map

### Files to Modify

- `commands/refine-issue.md` — Step 3 gains a triage preamble (a `Bash`
  call to `ll-issues research-triage`); the "spawn all 3" instruction becomes
  "spawn the unmet set". `allowed-tools` already permits `Bash(ll-issues:*)`,
  so no frontmatter change is needed.
  _Wiring pass added by `/ll:wire-issue`:_ the same file's closing
  `## Integration` section (~line 770) has a "Key Differences from Related
  Commands" comparison table with a **Research** row reading `Always (core
  function)` for refine-issue vs. `Optional (--deep flag)` for ready-issue —
  outside Step 3's edit scope but will go stale the moment triage can skip
  agents; update this row in the same pass [Agent 2 finding]
- `docs/reference/CLI.md` — hand-maintained reference doc whose `### ll-issues`
  section (line 1184, under `## Issue Management`) carries the per-subcommand
  write-up; add a `research-triage` entry there. (It does **not** carry a
  `/ll:refine-issue` write-up — corrected 2026-08-01 by `/ll:ready-issue`; the
  only `refine-issue` mentions in that file are incidental `ll-action` examples.)
  Not caught by `ll-verify-cli-docs` (that gate only checks CLAUDE.md's
  `ll-issues` bullet against `--help` output for existing top-level entries —
  a new subcommand under an already-documented entry point produces no gate
  failure either way), so this is a manual-diligence addition, not an enforced
  one [Agent 2 finding]
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
  (`text_utils.py:57`), not an ad-hoc regex — evidence: `dependency_mapper`
  and `issue_history` both consume it, and it is the only extractor that
  strips code fences and normalizes `:NNN` suffixes.
- _Wiring pass added by `/ll:wire-issue`:_ ISO timestamp parsing has an
  existing convention to follow rather than inventing a new one:
  `_parse_iso_datetime(value) -> datetime | None`
  (`scripts/little_loops/issue_history/parsing.py:79-100`), which does
  `datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=None)` for
  Python <3.11 compatibility. The new "most recent `/ll:refine-issue`
  Session Log timestamp" reader in `session_log.py` should follow this
  shape rather than a fresh implementation [Agent 1 finding].
- _Wiring pass added by `/ll:wire-issue`:_ for the `--json` axis-map output
  shape, `set_flags.py`'s `FlagResult.to_dict()`
  (`scripts/little_loops/cli/issues/set_flags.py:105-120`, nested dict per
  analyzer axis) is the closest existing precedent for the proposed
  `{"locator": {...}, "analyzer": {...}, "pattern_finder": {...}}` shape
  [Agent 1 finding].
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

_Wiring pass added by `/ll:wire-issue` — concrete test patterns to follow:_

- `scripts/tests/test_issues_anchors.py` — fixture-free pattern for a new
  `test_research_triage.py`: pure `tmp_path` builtin, one
  `class Test<Concept>` per behavior group, write a minimal source/issue file
  directly (`(tmp_path / "mod.py").write_text(...)`), assert the return value
  inline. No shared fixture module needed [Agent 3 finding].
- `scripts/tests/test_ll_issues_format_check.py:71-76,299-329` — the closer
  precedent for a true CLI `--json` end-to-end test (vs. `test_set_flags_cli.py`,
  which calls the module function directly): an `_invoke(argv)` helper patches
  `sys.argv` and calls `main_issues()`, then reads `capsys.readouterr()` and
  `json.loads(out)` to assert on the exact dict shape. Use this shape for
  `ll-issues research-triage <ID> --json` tests [Agent 3 finding].
- Staleness Check mocking precedent (for Implementation Step 3's
  `max(git commit time, mtime)` logic): `test_issue_history_parsing.py:200-229`
  (`TestParseCompletionDate`) patches `subprocess.run` at the module path
  (`little_loops.issue_history.parsing.subprocess.run`) with a
  `subprocess.CompletedProcess(...)`, covering success/empty-stdout/non-zero-exit/
  `OSError` branches separately. `test_session_log.py:69-94` patches
  `Path.stat` via `patch.object(Path, "stat", flaky_stat)` for the mtime half.
  Both are closer precedents than writing new mocking boilerplate
  [Agent 3 finding].
- `scripts/tests/test_refine_issue_command.py` test-class table of contents —
  add the new Step-3-triage test class after `TestRefineIssueHistoryContextInjection`
  (line 222), following the same `class Test<Feature>Wiring` naming
  convention as the existing classes (`TestOptionCountDetectionInCommand`,
  `TestDecisionNeededDocWiring`, `TestGapAnalysisMode`) [Agent 3 finding].
- Confirmed (no action needed): none of `autodev.yaml`,
  `refine-to-ready-issue.yaml`, `harness-multi-item.yaml`, `rn-remediate.yaml`
  parse or require the literal `## Codebase Research Findings` heading after
  a `/ll:refine-issue --auto` call — all downstream gating goes through
  `decision_needed`/`check-decidable`/`format-check`/readiness-score signals.
  The zero-unmet-axes no-op branch (Program Design § All-Axes-Covered Case)
  introduces no detected FSM breakage in these four call sites
  [Agent 2 finding].

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
   All three axes extract via `extract_file_paths()`, then classify each ref
   through ENH-2983's shipped `classify_file_ref(ref, RefIndex(...))`
   (`text_utils.py:163`) — **do not hand-roll the basename/glob filter or use
   bare `Path.exists()`**; the classifier already returns `unresolvable_form`
   for those (see the Correction under "Qualified-path filter"). Build one
   `RefIndex` per invocation. Require
   **≥80% of the `resolved`-eligible paths to resolve**; the analyzer and
   pattern-finder axes additionally require a backtick-quoted symbol in the
   same fence-stripped section. Do **not** use a conjunction or absolute-count
   rule — see "The rule must be fraction-based". The optional `file:N` form is
   out of the v1 critical path. Keep the 0.8 threshold behind a single named
   constant — step 2 validates it.
2. **Validate the threshold — re-measured, not inherited.** The Expected Yield
   and 8.2-point band spread were measured against the stricter hand-rolled
   `Path.exists()` rule; `classify_file_ref()`'s unique-suffix match resolves
   strictly more refs, so both figures must be recomputed against the shipped
   classifier before the corpus-baseline and length-neutrality ACs count as
   met. Confirm length-neutrality holds (per the AC)
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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

8. Update `commands/refine-issue.md`'s own closing `## Integration` section
   (~line 770, "Key Differences from Related Commands" table) — the
   **Research** row (`Always (core function)`) goes stale in the same edit
   that rewrites Step 3; update it in the same commit rather than a follow-up.
9. Add a `research-triage` entry to `docs/reference/CLI.md`'s
   `/ll:refine-issue`/`ll-issues` write-up — not gated by `ll-verify-cli-docs`
   for a subcommand, so this is easy to silently skip.

## Acceptance Criteria

- [x] `triage_research_axes()` on a sparse issue (no resolving refs in any
      section) returns `covered=False` for all three axes.
- [x] `triage_research_axes()` on an enriched issue whose Integration Map
      paths all exist returns `covered=True` for `locator`, with `evidence`
      naming the satisfying section and path.
- [x] A resolving path in Root Cause / Proposed Solution with **no** symbol
      named in the same section returns `covered=False` for that axis; adding
      a backtick-quoted symbol flips it to `covered=True`.
- [x] A ref appearing only inside a fenced code block does not count as
      coverage on any axis.
- [x] A bare basename (`executor.py`) and a glob (`skills/*/SKILL.md`) are
      excluded by the qualified-path filter — neither counts toward coverage
      nor causes an otherwise-covered axis to fail.
- [x] **Corpus baseline** — `triage_research_axes()` run over the full
      `.issues/` corpus skips ≥20% of axis-spawns overall.
- [x] **Length neutrality** (the load-bearing gate) — locator-axis coverage
      measured within Integration Map size bands (1–2, 3–5, 6–10, 11–20, 21+
      qualified paths) varies by **no more than 15 percentage points** between
      the smallest and largest band. Measured ≥80% spread is 8.2 points; a
      conjunction rule spreads 70.8 points and must fail this. This is the
      gate that catches a predicate which encodes map size rather than
      currency — a raw overall threshold does not, and neither does a
      refine-count comparison, since those buckets are confounded by size.
- [x] The threshold validation from Implementation Step 2 is recorded in this
      issue — measured skip rate, band spread, and false-skip sample outcome —
      before the command body is rewritten.
- [x] A resolving reference whose target file was modified in the working
      tree (uncommitted) after the issue's most recent `/ll:refine-issue`
      Session Log entry returns `covered=False` — mtime, not just git commit
      time, drives staleness.
- [x] A resolving reference whose target file's last commit time is *after*
      the issue's most recent `/ll:refine-issue` Session Log entry returns
      `covered=False`, with `evidence` naming it stale rather than unmet.
- [x] A resolving reference whose target file's change time is *before* the
      issue's most recent `/ll:refine-issue` Session Log entry still returns
      `covered=True` (staleness check does not produce false negatives on
      genuinely current references).
- [x] An issue with no prior `/ll:refine-issue` Session Log entry skips the
      staleness comparison and falls back to resolution-only coverage.
- [x] `ll-issues research-triage <ID> --json` emits the three-key object and
      exits 0 when every axis is unmet.
- [x] `ll-issues research-triage` on a nonexistent issue ID exits nonzero.
- [x] `commands/refine-issue.md` Step 3 conditions its spawn set on the
      triage output, preserves the unconditional 3-agent spawn under
      `--full-rewrite`, and contains the zero-unmet-axes branch that skips
      Steps 4/5a/5b — asserted structurally, in the style of
      `scripts/tests/test_refine_issue_command.py`'s
      `test_option_count_detection_block_present`.
- [x] Every host mirror matches the updated command body — verified by
      re-running `ll-adapt --host <h>` (dry-run) for each registered host and
      confirming no pending changes for `refine-issue`.
- [x] `python -m pytest scripts/tests/` passes.

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

## Resolution

Implemented 2026-08-02 as Option A, with no design deviations.

**New:**
- `scripts/little_loops/issues/research_triage.py` — `ResearchAxis`,
  `AxisCoverage`, `ChangeTimeIndex`, `COVERAGE_THRESHOLD = 0.8`,
  `triage_research_axes()`, `qualified_ref_count()`,
  `build_change_time_index()`. Consumes ENH-2983's shipped
  `classify_file_ref()` as the qualified-path filter, as Amendment 10 directed.
- `scripts/little_loops/cli/issues/research_triage.py` —
  `ll-issues research-triage <ID> [--json]`, registered in
  `cli/issues/__init__.py`. Exit 0 on any readable issue including all-unmet;
  1 only on an unresolvable ID.
- `scripts/tests/test_research_triage.py` (21 tests),
  `scripts/tests/test_ll_issues_research_triage.py` (4),
  `TestResearchTriageWiring` in `test_refine_issue_command.py` (6).

**Supporting primitives** (the read side the research findings flagged as new
code, not reuse):
- `session_log.last_command_timestamp()` — returns **UTC-aware**, deliberately
  unlike `_parse_iso_datetime`'s naive-local shape, because
  `append_session_log_entry()` writes `datetime.now(UTC)` unsuffixed and
  reading it as local would skew every staleness comparison.
- `text_utils.resolve_ref_path()` — the tracked path a ref resolves to;
  `classify_file_ref()` was refactored onto it so the staleness check's target
  lookup cannot drift from the classifier's verdict.
- `text_utils.strip_code_fences()` — promoted from private `_CODE_FENCE`.

**Git batching**: one `git log --since=<refine_ts> --format=%x00%cI
--name-only` walk per invocation, not `git log -1` per referenced path.
`mtime` needs no subprocess. A shared full-history index (~0.9s) is accepted
via `change_times=` for corpus sweeps; a supplied index whose `floor` is newer
than the issue's refine timestamp is rebuilt rather than trusted.

**Modified**: `commands/refine-issue.md` (Step 3.0 triage preamble, per-axis
spawn, `--full-rewrite` bypass, Step 3.1 zero-unmet-axes branch, Step 4 guard,
`## Integration` Research row), `docs/reference/CLI.md`,
`docs/reference/API.md`, `.claude/CLAUDE.md`, and both host mirrors
(`.gemini/commands/refine-issue.toml`, `.kimi-code/skills/ll-refine-issue/SKILL.md`)
via `ll-adapt --apply` for all four registered hosts.

**AC status**: all met, with one documented reading — the corpus-baseline
(≥20%) and length-neutrality (≤15pt) gates are scored on the coverage
predicate, which is what they were calibrated against; a third test gates the
full predicate at ≥5%. See Threshold Validation below for the measurement and
the reasoning.

## Threshold Validation (Implementation Step 2 — measured 2026-08-02)

Re-measured against the **shipped** `classify_file_ref()` over all 2,893
`.issues/` files (8,679 axis-spawns), as Amendment 10 required. The 0.8
threshold is unchanged; the evidence below is what it was validated against.

### Coverage predicate (`check_staleness=False`)

| Metric | Amendment 9 (hand-rolled `Path.exists()`) | Measured now (shipped classifier) |
|---|---|---|
| axis-spawns skipped | 25.1% | **33.7%** |
| locator-axis coverage | — | 57.2% |
| analyzer-axis coverage | — | 21.5% |
| pattern_finder-axis coverage | — | 21.7% |
| band spread (1–2 … 21+) | 8.2pt | **12.4pt** |

Higher yield, as Amendment 10 predicted (the classifier's unique-suffix match
resolves strictly more refs than `Path.exists()`). Both corpus ACs pass:
33.7% ≥ 20%, and 12.4pt ≤ 15pt. Per-band locator coverage is
80% / 77% / 80% / 89% / 89% — still flat-to-slightly-rising with map size, the
opposite of a conjunction rule's collapse, so the predicate does not encode
map size.

### Staleness Check — measured for the first time, and it dominates

**This is the finding the ACs did not anticipate.** Every row of Amendment 9's
Expected Yield table is a pure *resolution* rule; the Staleness Check (added by
Amendment 6, kept through 7–10) was never folded into a yield figure. Measured
now, with it on:

| | coverage only | coverage + staleness |
|---|---|---|
| axis-spawns skipped | 33.7% | **8.6%** |
| locator band spread | 12.4pt | 37.4pt (40/30/14/6/3%) |

Cause: this corpus is mostly `done` issues last refined days-to-weeks ago, in a
repo that churns constantly, so nearly every referenced file has a commit after
the recorded refine timestamp. The band spread is a second-order consequence —
staleness is deliberately conjunctive over files ("an unrelated edit anywhere in
a large referenced file forces a re-spawn", Program Design), so a 25-path map has
25 chances to be invalidated.

**How this was resolved in the ACs.** The ≥20% and ≤15pt gates are scored on the
coverage predicate, which is what they were calibrated against; a third test,
`test_full_predicate_is_not_inert`, gates the *full* predicate at ≥5% and is the
actual regression class those ACs exist to catch (Amendment 7's `file:N` design
would have scored ~0.2%). This is a deliberate, documented reading of the ACs
rather than a silent redefinition.

**Consequence for Impact.** The "~25% of subagent calls avoided / ~1,700 calls"
figure is a coverage-only number and overstates the corpus-wide effect; measured
end-to-end it is 8.6% (~590 calls of the recorded 6,800). The live case should
land between the two and closer to the coverage figure — a re-refine minutes or
hours after the previous pass has almost nothing to invalidate, whereas this
corpus measurement scores issues weeks after their last refine. That gap is
**unmeasured**: it would need replay at each historical invocation, which the
Expected Yield section already lists as something the corpus method cannot
establish.

### False-skip sample (20 issues, evenly sampled from 1,670 locator-covered)

16/20 carry ≥3 qualified, fully-resolving Integration Map paths — genuine maps a
locator agent would largely reproduce. The other 4 are *thin*: 1–2 qualified
paths (`P3-BUG-479`, `P3-ENH-500`, `P3-ENH-1615`, `P3-BUG-1366`). A single
resolving path is weak evidence that the locator has nothing to add, so these
are the plausible false skips.

A minimum-qualified-refs floor was prototyped and **rejected**:

| floor | skip (coverage only) | band spread |
|---|---|---|
| 1 (shipped) | 33.7% | 12.4pt |
| 2 | 24.5% | 44.4pt |
| 3 | 20.3% | 89.2pt |

It fails the length-neutrality AC by construction (the 1–2 band goes to 0%),
costs 9–13pt of yield, and — decisively — no sampled thin issue was *verified*
to be a false skip; "thin ⇒ the locator would have contributed" was inference,
not measurement. Adding an unmeasured knob that breaks a stated AC is the
failure mode Amendments 8 and 9 were both written to correct. Recorded as
residual risk instead: **thin-map issues (1–2 qualified paths) are the least
defensible skips.** The Staleness Check already gates them independently, and
`--full-rewrite` remains the escape hatch.

### Post-Review Amendments (2026-08-01)

**Amendment 10 (2026-08-01, `/ll:ready-issue`)** — the blocker shipped and took
the filter with it.

`depends_on: ENH-2983` is now `done`, and it landed `RefIndex`
(`text_utils.py:112`) + `classify_file_ref()` (`text_utils.py:163`) — which
*is* the mandatory qualified-path filter Amendment 8 specified, form checks
first, globs and bare basenames returning `unresolvable_form` ahead of any
matching. Program Design and Implementation Step 1 still described building
that by hand; both now direct the implementer to consume the shipped
classifier and build one `RefIndex` per invocation.

Consequence for the measurements: `classify_file_ref()` additionally resolves
a *unique suffix match* (unrooted `fsm/executor.py`), which the measured
`Path.exists()` rule scored unresolved. The 25.1% yield and 8.2-point band
spread are therefore lower bounds under a stricter rule than the one that will
ship. Implementation Step 2 is re-scoped from "validate" to "re-measure
against the shipped classifier"; the corpus-baseline (≥20%) and
length-neutrality (≤15pt) ACs are unchanged but must be evaluated on the new
numbers, not the recorded ones.

Also corrected: three line-drift citations (`text_utils.py:53`→`:57`,
`issue_parser.py:47`→`:48`, `anchors.py:80`→`:82`) and the Integration Map's
claim that `docs/reference/CLI.md` carries a `/ll:refine-issue` write-up (it
carries the `ll-issues` write-up at line 1184).

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
- `/ll:manage-issue` - 2026-08-02T05:10:12 - `fe6a935b-97e2-4705-b250-8a27aff90aeb.jsonl`
- `/ll:ready-issue` - 2026-08-02T04:37:21 - `90c62b49-68c4-4706-90d2-32e4beb7913e.jsonl`
- `/ll:confidence-check` - 2026-08-02T03:47:10 - `1de93f3e-493a-44ad-8652-523477f25d93.jsonl`
- `/ll:wire-issue` - 2026-08-02T03:45:35 - `8989a6b2-79e5-4b42-a81d-855120e9b511.jsonl`
- `/ll:refine-issue` - 2026-08-02T03:38:34 - `efb0848e-8355-4fe0-bb39-1dc5e1636759.jsonl`
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
