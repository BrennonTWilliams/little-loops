---
id: ENH-3098
title: Seed /ll:refine-issue's research agents from the ll-code code graph
type: ENH
priority: P3
captured_at: '2026-08-08T02:58:00Z'
completed_at: '2026-08-08T03:44:10Z'
discovered_date: 2026-08-07
discovered_by: session
status: done
testable: true
labels:
- enhancement
- codequery
- codegraph
- refine-issue
- agents
relates_to:
- ENH-2578
- ENH-2613
- ENH-3092
parent: EPIC-2575
decision_needed: false
---

# ENH-3098: Seed `/ll:refine-issue`'s research agents from the `ll-code` code graph

## Summary

`/ll:refine-issue` dispatches `ll:codebase-locator`, `ll:codebase-analyzer`, and
`ll:codebase-pattern-finder` to research an issue. None of them consult `ll-code`,
so every refine rediscovers callers, importers, and impact sets with open-ended
Grep sweeps — even though the `codegraph` provider can answer those exactly from
its index.

Seed the agent wave from `ll-code` in the orchestrator, mirroring `/ll:wire-issue`
Phase 3.6 (ENH-2578), and extract the contract both consumers share.

## Current Behavior

- `commands/refine-issue.md` Step 3 spawns the three agents with no structural
  priors; `allowed-tools` has no `Bash(ll-code:*)`.
- `skills/wire-issue/graph-discovery-layer.md` holds the only `ll-code` seeding
  procedure, with the contract, safety rules, and staleness policy stated inline.
- That file's closing "fallback-only caveat" is stale: it claims `FallbackProvider`
  is the only registered provider, but `codegraph` (ENH-2613) is live and reports
  all six capabilities including `impact_of` (ENH-3092).

## Expected Behavior

On a project with an available provider, a refine of an issue naming concrete
symbols or files queries `ll-code` once in the orchestrator, confirms each hit with
one Grep at its `path:line`, and hands the confirmed set to the locator and analyzer
as `CONFIRMED SEEDS`. Those agents confirm coverage and extend it rather than
rediscovering the call graph. With no provider, an unavailable one, or an issue
naming no concrete target, behavior is byte-identical to before.

## Impact

Removes duplicated Grep sweeps from every refine on a graph-indexed project, and
makes the structural half of the research verifiable — a seeded caller carries a
provider and a `confidence` value, where a Grep-discovered one carried neither.
Also collapses two divergent copies of the `ll-code` contract into one, after the
wire-issue copy had already gone stale about which providers exist.

## Scope Boundaries

**In scope:** the `/ll:refine-issue` prompt surface, the shared contract doc, the
wire-issue companion's deduplication, bridge/mirror frontmatter, and tests.

**Out of scope:** any change to `ll-code`, the providers, or the `codequery`
package; granting the `ll:codebase-*` agents shell access (explicitly rejected —
see below); seeding `/ll:refine-issue`'s pattern-finder axis; and measuring the
token/latency delta, which needs a separate before/after run recording which
provider served each refine.

## Status

Done — implemented and verified in a single session on 2026-08-08. No follow-up is
required for this issue. The unrelated `.kimi-code` mirror drift surfaced during the
work (see Notes) is not tracked here.

## Why not wire `ll-code` into the agents themselves

`ll-code` is a CLI, so reaching it requires `Bash`. Agent frontmatter takes bare
tool *names* — it cannot express the `Bash(ll-code:*)` scoping a command's
`allowed-tools` can — so granting it means unrestricted shell for three read-only,
document-don't-modify agents. It is also redundant: the three run as a parallel
wave and would each re-probe `status` and re-derive the same candidate set.

The orchestrator already has scoped `Bash`. It queries once and passes confirmed
candidates into the agent prompts as established facts.

## Program Design

### Types

No new runtime types — this is prompt-surface wiring plus one shared doc. The only
Python added is the test module.

### Signatures

In `scripts/tests/test_enh3098_refine_issue_graph_seeding.py`:

```python
def _frontmatter(path: Path) -> str
def _body(path: Path) -> str
class TestRefineIssueFrontmatter:
    def test_declares_ll_code_tool(self, path: Path) -> None
class TestStep305Seeding:
    def test_step_305_precedes_agent_dispatch(self) -> None
    def test_pattern_finder_is_left_unseeded(self) -> None
    def test_provenance_recorded_outside_session_log(self) -> None
class TestSharedContractDoc:
    def test_states_safety_rule(self, rule: str) -> None
    def test_wire_issue_layer_delegates_rather_than_duplicates(self) -> None
class TestResearchAgentsStayBashFree:
    def test_agent_has_no_bash_tool(self, path: Path) -> None
```

Existing signatures this work reads but does not change:

- `issue_design_timestamp(content: str) -> date | None`
  (`scripts/little_loops/issues/program_design.py:406`) — the parser whose line
  format kept provenance out of the Session Log.
- `program_design_gate_active(issue_path: Path, content: str) -> bool`
  (`scripts/little_loops/issues/program_design.py:430`) — arms off the above.
- `build_ref_index(root: Path) -> RefIndex`
  (`scripts/little_loops/text_utils.py:161`) — why untracked new files read as
  `stale_file_ref` until staged.

### Call Path

`/ll:refine-issue` Step 3.0 (triage) → **Step 3.05 (new: seed)** → Step 3 agent
wave → Step 4 (gaps) → Step 8 output report (`Graph seeds:` provenance line).

Step 3.05 shells out to `ll-code`, whose CLI entry is `main_code()`
(`scripts/little_loops/cli/code.py`), resolving a provider through
`scripts/little_loops/codequery/core.py` (`codegraph` via
`scripts/little_loops/codequery/codegraph.py`, else
`scripts/little_loops/codequery/fallback.py`).

### Decision Rules

- Seed `locator` with `importers-of` / `impact-of` / `defines`; seed `analyzer`
  with `callers-of` / `callees-of`; seed `pattern_finder` with nothing (graph edges
  do not express semantic similarity).
- Query only axes Step 3.0 actually spawns, and only subcommands present in
  `status.capabilities`.
- Skip the step when Step 3.1 applied, the provider is unavailable, or the issue
  names no concrete target.
- Omit the `CONFIRMED SEEDS` block entirely when there are no confirmed hits —
  an empty list reads as "there are none", the negative the safety rules forbid.
- Provenance goes on the Step 8 report, never the Step 6.5 Session Log, whose line
  format `issue_design_timestamp()` parses.

## Files Modified

- `docs/guides/GRAPH_DISCOVERY_GUIDE.md` — new; canonical `ll-code` seeding
  contract, three safety rules, staleness policy, provider note.
- `skills/wire-issue/graph-discovery-layer.md` — reduced to wire-issue specifics;
  links the shared doc; stale fallback-only caveat removed.
- `commands/refine-issue.md` — `Bash(ll-code:*)`; Step 3.05; `CONFIRMED SEEDS`
  slots in the locator and analyzer prompts; `Graph seeds:` report line.
- `skills/ll-refine-issue/SKILL.md` — bridge frontmatter sync.
- `.kimi-code/skills/ll-refine-issue/SKILL.md` — regenerated via
  `ll-adapt --host kimi-code --apply` (not hand-edited).
- `docs/reference/CLI.md` § `ll-code` — consumer pointer to the shared doc.
- `scripts/tests/test_enh3098_refine_issue_graph_seeding.py` — new, 18 tests.

## Verification

`python -m pytest scripts/tests/` → **18578 passed, 42 skipped** (403s).

## Notes for the next reader

- **No CHANGELOG entry.** This repo writes CHANGELOG sections only at release time
  (see the `docs(release):` commit pattern); feature commits do not touch it.
- **`ll-adapt` wanted to rewrite two unrelated mirrors** —
  `.kimi-code/skills/ll-manage-release/SKILL.md` and
  `.kimi-code/skills/scope-epic/SKILL.md` — from pre-existing source drift. Those
  were reverted to keep this diff scoped; the drift is real and still unaddressed.
- **The three `ll:codebase-*` agents were deliberately left unchanged.** The
  regression test in this issue's test file exists to keep it that way; if a future
  change needs graph access inside an agent, the constraint to solve first is that
  agent frontmatter cannot scope `Bash` to one binary.

## Acceptance Criteria

- [x] `refine-issue` and its bridge declare `Bash(ll-code:*)`.
- [x] Step 3.05 exists, precedes the agent wave, and links the shared doc.
- [x] Locator and analyzer prompts carry a non-exhaustive `CONFIRMED SEEDS` slot.
- [x] `pattern_finder` is documented as unseeded.
- [x] The three `ll:codebase-*` agents remain Bash-free (regression-tested).
- [x] `wire-issue/graph-discovery-layer.md` no longer restates the contract.
- [x] `python -m pytest scripts/tests/` passes.

## Session Log
- `hook:posttooluse-status-done` - 2026-08-08T03:24:31 - `ae6e7f4d-97a8-4346-9389-1f696b64f224.jsonl`
