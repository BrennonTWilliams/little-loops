---
id: ENH-2578
title: wire-issue graph-first discovery phase with before/after token measurement
type: ENH
priority: P3
status: open
labels: [skills, code-intelligence, token-cost, measurement, captured]
captured_at: "2026-07-10T05:34:41Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2575
---

# ENH-2578: wire-issue graph-first discovery phase with before/after token measurement

## Summary

Wire the first skill consumer onto the `ll-code` query surface: `/ll:wire-issue` gains a graph-first discovery step that seeds its Integration Map candidates (callers, importers, impacted tests/config/docs) from one or two `ll-code --json` calls, then spends its remaining budget **confirming** those candidates with targeted Grep instead of discovering them from scratch. Ship with a before/after token/turn measurement on benchmark issues; the measured delta — not assumption — decides whether `/ll:find-dead-code`, `/ll:audit-architecture`, and `/ll:refine-issue --gap-analysis` get the same treatment.

## Current Behavior

`skills/wire-issue/SKILL.md` traces "every file that must change, every caller that may break, every config key, doc section, or test that needs touching" through open-ended Read/Glob/Grep/find exploration (allowed-tools: Read, Glob, Grep, Edit, Bash find/ls/wc/git/ll-issues, Agent). Caller and importer discovery is typically 4–8 grep rounds per planned change, interpreted by the agent, repeated for every issue — including in autodev loops where the codebase facts barely changed between runs. `ll-code` (FEAT-2576/ENH-2577) exists but nothing calls it.

## Expected Behavior

Within wire-issue's tracing phase:

```
# New sub-phase: Graph-accelerated discovery (before manual tracing)
STATUS = Bash: ll-code --json status
if provider unavailable → skip silently; proceed with current flow (zero regression)
else:
    for each planned change target (symbol or file) from the issue's Implementation Steps:
        CANDIDATES += ll-code --json callers-of / importers-of / impact-of
    # Hints, not verdicts:
    confirm each candidate with ONE targeted Grep at its path:line before it enters the Integration Map
    if STATUS.freshness == "stale": treat all candidates as leads only; widen confirmation to current flow for anything wiring-critical
    negative results ("no callers") are NEVER trusted alone → run the current exploratory pass for that target
```

The skill's written output (Integration Map) is format-identical to today — only how candidates are found changes. `--dry-run`/`--auto` behavior unchanged.

## Use Case

`/ll:wire-issue FEAT-XXXX --auto` inside an autodev triage loop: the issue re-signatures `IssueManager.load`. One `ll-code --json callers-of` returns 11 exact call sites; the agent confirms each with a single targeted Grep and finds one new site added since indexing (flagged stale). Integration Map complete in ~3 tool rounds instead of ~10, with the stale drift caught by the confirmation step rather than shipped as a gap.

## Proposed Solution

1. **SKILL.md change** — add the graph-accelerated discovery sub-phase (pseudocode above) to `skills/wire-issue/SKILL.md`'s tracing phase, and `Bash(ll-code:*)` to `allowed-tools`. Encode the three safety rules verbatim: silent fallback when unavailable; confirm-before-map for every positive hit; never trust negative results without an exploratory pass.
2. **Measurement** — define a benchmark set of 3–5 representative closed issues with known-good Integration Maps (e.g., re-run against their pre-implementation commits). Run wire-issue N times per issue with the graph phase disabled vs. enabled; pull per-run token/turn/tool-call counts from the session history db (`ll-history` / `ll-logs`, EPIC-1918-style telemetry). Record results in the issue's Session Log and epic.
3. **Decision gate** — write the go/no-go into EPIC-2575: material win (target: ≥30% discovery-phase token reduction with zero Integration Map regressions) → file the mechanical follow-ups for find-dead-code / audit-architecture / refine-issue --gap-analysis; a wash → close the epic at protocol+provider with no further skill changes.

## Scope Boundaries

- **Not** changes to any other skill — follow-ups are filed only after the measured win.
- **Not** Integration Map format changes — output contract untouched.
- **Not** find-dead-code integration — explicitly deferred: its delete-recommendation semantics make stale negatives dangerous; it goes second only after the confirm-step pattern is proven here.
- **Not** new measurement infrastructure — reuse existing history/logs telemetry; if a counter is missing, capture a separate issue.

## API/Interface

- `skills/wire-issue/SKILL.md`: new sub-phase + `Bash(ll-code:*)` in allowed-tools frontmatter.
- No Python/CLI changes.

## Integration Map

### Files to Create
- Benchmark notes/fixture list (issue IDs + commits) — location per existing eval conventions (e.g., alongside skill or in `specs/`)

### Files to Modify
- `skills/wire-issue/SKILL.md` — allowed-tools + tracing-phase sub-section
- Docs page for wire-issue if phases are documented there
- `EPIC-2575` — record measurement results and go/no-go

### Dependent Files
- Potential follow-up issues for `skills/ll-find-dead-code/`, `skills/ll-audit-architecture/`, `skills/ll-refine-issue/` (filed only on measured win)

### Similar Patterns
- `skills/wire-issue/SKILL.md` existing phase structure and `--auto`/`--dry-run` conventions
- ENH-2569's measurement-first discipline ("land alone, record fire rate") — same land-then-measure-then-route philosophy
- EPIC-1918 (ll-logs as development telemetry) — where the run metrics come from

### Tests
- Skill-lint/doc checks (`ll-verify-skills`, `ll-verify-docs`) stay green
- Manual/benchmark: Integration Map parity check between disabled/enabled runs on the benchmark set (no missing entries)

### Documentation
- CHANGELOG; wire-issue docs note the optional acceleration + fallback behavior

### Configuration
- None beyond ENH-2577's `code_query` block (skill respects whatever provider/staleness policy resolves).

## Implementation Steps

1. Add the sub-phase + allowed-tools to wire-issue SKILL.md with the three safety rules.
2. Assemble the benchmark issue set; capture baseline runs (graph phase off).
3. Capture enabled runs; compare tokens/turns/tool-calls and Integration Map parity.
4. Write results + go/no-go into EPIC-2575; file follow-up issues if the gate passes.

## Impact

- **Priority**: P3 — the payoff step; converts EPIC-2575 from plumbing into measured token savings (EPIC-2456).
- **Effort**: Small-Medium — prompt-only skill change + benchmark runs; no engine code.
- **Risk**: Low — silent fallback preserves today's flow exactly; confirm-before-map bounds stale-index damage.
- **Breaking Change**: No.

## Related Issues

- **EPIC-2575** — parent. **Blocked by FEAT-2576 and ENH-2577** (needs the CLI and a real provider for a meaningful measurement).
- **EPIC-2456** — token cost reduction; report the measured delta there.
- **EPIC-1918** — telemetry source for the measurement.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`
