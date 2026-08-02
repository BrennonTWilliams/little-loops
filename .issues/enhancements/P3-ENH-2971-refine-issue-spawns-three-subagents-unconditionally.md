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

> **Selected:** Option A — cheap pre-classification. Keys on the issue's actual enrichment state (the thing that varies), not its type; scores 10/12 vs. Option B's 8/12.

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

Two kinds of reference appear in issue sections and they need different
checks. A bare path (`commands/refine-issue.md`) resolves iff it exists on
disk; a `file:N` anchor resolves iff `resolve_anchor()` returns non-`None`
**and** `N` is within the file. `resolve_anchor()` alone is not sufficient
for either case — see Reference Resolution below.

### Reference Resolution

Three primitives compose into "resolves", not one:

| Reference form | Check | Primitive |
|---|---|---|
| bare path (`a/b.py`) | extract, then exists on disk | `extract_file_paths()` (`text_utils.py:53`) + `Path.exists()` after joining `root` |
| `file:N` anchor | extract, then file readable, `N` in range, anchor found | `_FILE_LINE` (`anchor_sweep.py:24`) + `resolve_anchor()` + explicit line-bound check |

`extract_file_paths(content: str) -> set[str]` is already public, already
strips code fences (so example paths in fenced blocks don't count as
coverage), and already normalizes `path.py:123` → `path.py`. It is the
locator axis's extractor as-is — **do not write a new bare-path regex**;
`_STANDALONE_PATH`/`_BACKTICK_PATH`/`_BOLD_FILE_PATH` are its private
internals.

`_FILE_LINE` (`anchor_sweep.py:24`) is the anchor-form extractor — it
requires a `:NNN` suffix and captures path and line separately, which
`extract_file_paths()` discards. It is currently private; implementation must
promote it (or a shared equivalent) to an importable name. Note it does
**not** strip code fences on its own — `_sweep_file()` does that separately
at the call site (`anchor_sweep.py:63-68`), so the triage predicate must do
the same or it will count fenced examples as coverage.

**`resolve_anchor()` is a weaker signal than "current".** It computes
`scan_end = min(line_number, len(lines))` (`anchors.py:80`), so a line number
well past EOF still resolves — it silently scans from the end of the file.
It also returns the nearest *preceding* definition regardless of drift, so a
reference pointing hundreds of lines off its original target still returns
non-`None`. The triage predicate must therefore add an explicit
`line_number <= len(lines)` bound before treating a `file:N` ref as
covering an axis. Even with that bound, triage tolerates stale-but-resolving
references by design; `--full-rewrite` is the only correction path.

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

### Call Path

- `/ll:refine-issue` Step 3 → `Bash: ll-issues research-triage <ID> --json`
  → `triage_research_axes()` → `Path.exists()` / `resolve_anchor()`
  (`scripts/little_loops/issues/anchors.py:59`) — not `_sweep_file()`; see
  Codebase Research Findings below, which found `_sweep_file()` only accepts
  a filesystem `Path` and reads the whole file, and its `skipped_refs` is an
  aggregate counter with no per-reference data. This is the first executable
  use of anchor resolution in `refine-issue.md` — Step 5c today only *cites*
  `_sweep_file()`/`skipped_refs` in prose (lines 512, 516), with no
  `Bash(...)` invocation anywhere in the command body.
- `find_project_root` — resolves the repo root anchor paths are joined
  against before the per-reference checks
- Step 3 then spawns one `Task` per axis whose `covered` is False

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
*current* (see Reference Resolution above). `--full-rewrite` bounds this.

### Codebase Research Findings

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
- `scripts/little_loops/issues/anchor_sweep.py` — promote `_FILE_LINE` to an
  importable name (or move it to `text_utils.py` alongside the bare-path
  patterns it is documented against)
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

### Codebase Research Findings

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

1. Promote `_FILE_LINE` (`anchor_sweep.py:24`) to an importable name; leave
   `_sweep_file()`'s behavior unchanged.
2. Write `scripts/little_loops/issues/research_triage.py`:
   `ResearchAxis`, `AxisCoverage`, `triage_research_axes(issue_path, root)`.
   Locator axis uses `extract_file_paths()` + `Path.exists()`; analyzer and
   pattern-finder axes use `_FILE_LINE` + `resolve_anchor()` with the
   `line_number <= len(lines)` bound. Strip code fences before extracting on
   the anchor path.
3. Add the `ll-issues research-triage <ID> [--json]` subcommand under
   `scripts/little_loops/cli/issues/`, exit 0 on any readable issue.
4. Rewrite `commands/refine-issue.md` Step 3: call the CLI, parse the axis
   map, spawn one `Task` per uncovered axis. Gate on
   `FULL_REWRITE == false`. Fall back to all three agents if the CLI fails.
5. Regenerate all host mirrors via `ll-adapt` — one `--apply` run per
   registered host (`codex`, `gemini`, `kimi-code`, `omp`), not just
   `.gemini`.
6. Add tests (see Acceptance Criteria).

## Acceptance Criteria

- [ ] `triage_research_axes()` on a sparse issue (no resolving refs in any
      section) returns `covered=False` for all three axes.
- [ ] `triage_research_axes()` on an enriched issue whose Integration Map
      paths all exist returns `covered=True` for `locator`, with `evidence`
      naming the satisfying section and path.
- [ ] A `file:N` ref whose `N` exceeds the target file's line count returns
      `covered=False` — the `resolve_anchor()` EOF-clamp does not count as
      coverage.
- [ ] A ref appearing only inside a fenced code block does not count as
      coverage on either axis.
- [ ] `ll-issues research-triage <ID> --json` emits the three-key object and
      exits 0 when every axis is unmet.
- [ ] `ll-issues research-triage` on a nonexistent issue ID exits nonzero.
- [ ] `commands/refine-issue.md` Step 3 conditions its spawn set on the
      triage output and preserves the unconditional 3-agent spawn under
      `--full-rewrite` — asserted structurally, in the style of
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
- **Risk**: Medium — the failure mode is skipping an agent whose findings
  were needed, producing a quieter refine that looks successful. The
  `--full-rewrite` escape hatch bounds this.
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
4. `resolve_anchor()` clamps `scan_end = min(line_number, len(lines))`, so
   out-of-range line numbers resolve anyway. An explicit line-bound check is
   now required, with an AC covering it.
5. Conventions in Force contradicted the issue's own research findings
   (`skipped_refs` as the resolution primitive); retracted. Implementation
   Steps contained assertions rather than steps; split into real steps plus
   an Acceptance Criteria section.

## Session Log
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
