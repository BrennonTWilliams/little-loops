---
id: ENH-2923
type: ENH
priority: P3
status: open
captured_at: "2026-07-30T02:14:15Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
relates_to:
- ENH-2925
parent: EPIC-1918
---

# ENH-2923: Scope `ll-logs scan-failures` to a specific skill

## Summary

`ll-logs scan-failures --project <path>` reports failure clusters keyed by
tool+error signature across the entire project, with no way to filter to a
single skill (e.g. `review-epic`). Getting skill-specific analytics currently
requires running the full scan and manually grepping the output for the
skill name.

## Current Behavior

`ll-logs scan-failures --project <path>` accepts only `--project`/`--all`,
`--window-days`, `--capture`, `--capture-foreign`, and `-j/--json`. There is
no `--skill NAME` filter, so a user asking "what's failing for skill X"
must run the unfiltered scan and grep the (potentially large) output
themselves.

## Expected Behavior

`scan-failures` should accept an optional `--skill NAME` flag that limits
reported failure clusters to those attributable to the named skill,
mirroring how `ll-history-context --for-skill NAME` already gates on a
skill name for a related CLI.

## Motivation

Skill-scoped failure analytics let a maintainer check the health of one
skill (e.g. after a change to `review-epic`) without wading through
unrelated `ll-issues`/other-tool noise in the full project scan.

## Proposed Solution

Add `--skill NAME` to `scan-failures`. Failure clusters are keyed by
tool+error signature (`_cmd_scan_failures`, `scripts/little_loops/cli/logs.py` —
`raw_clusters` keyed `(cwd_path, tool_name, normalized_sig)`), not skill name,
so a simple string match on the cluster's tool name cannot answer "what's
failing under skill X."

**Attribution mechanism.** Session JSONL records carry no per-tool-call
"enclosing skill" field, so attribution is a stream-tracking pass inside the
existing single-pass file walk in `_cmd_scan_failures`:

1. Maintain `current_skill: str | None` per JSONL file (reset per file, like
   the existing `pending` dict).
2. Update it from two marker sources as records stream by:
   - **user records** whose message content contains a
     `<command-name>/ll:NAME</command-name>` marker (slash-command/skill
     invocation) — set `current_skill = NAME`; a user record with plain prose
     and no marker resets it to `None` (a new user turn ends the skill's
     attribution window);
   - **assistant `tool_use` blocks with `name == "Skill"`** — set
     `current_skill = input.skill` (strip any `ll:` prefix for consistency).
3. When a failing tool_result is folded into a cluster, record the
   `current_skill` in effect when its `tool_use` was *issued* — i.e. extend
   the `pending` map's value tuple to `(tool_name, ts, skill)` so attribution
   survives interleaved records.
4. Extend the cluster key/value to carry a per-skill breakdown (or simplest:
   add `skill` to the cluster key so clusters split by skill), and thread a
   `skill` field through `_FailureCluster` and the `--json` payload.
5. `--skill NAME` filters clusters to `skill == NAME` (accept with or without
   the `ll:` prefix). Failures with no enclosing skill attribute to `None`
   and are excluded by any `--skill` filter.

Known limitation to state in `--help`: attribution is heuristic — a tool call
made after a skill's turn completes but before the next user message may be
mis-attributed to that skill. Acceptable for triage analytics.

Sequencing: the consolidated parser (shared target/window parent parsers,
`--limit`) has already landed on `scan-failures`; this flag lands on top of
that existing surface rather than waiting on it.

## Acceptance Criteria

- [ ] `ll-logs scan-failures --skill review-epic` reports only clusters whose
      failures occurred while `review-epic` (via `<command-name>` marker or
      `Skill` tool_use) was the enclosing skill; `ll:review-epic` is accepted
      as an equivalent spelling.
- [ ] Unfiltered output is unchanged in cluster counts except where a
      tool+signature previously merged across skills now splits by skill (if
      the key-split approach is taken, note it in the changelog).
- [ ] `--json` rows include a `skill` field (`null` when unattributed).
- [ ] `--skill` composes with `--window-days`/`--since`/`--until` and
      `--limit`.
- [ ] Tests cover: marker-based attribution, `Skill` tool_use attribution,
      reset on a plain user message, unattributed failures excluded under
      `--skill`, and the prefix-equivalence acceptance — using synthetic JSONL
      fixtures (no live session logs).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

**In scope:** attribution tracking inside `_cmd_scan_failures`'s existing
stream walk; `--skill` flag; `skill` in `_FailureCluster` and JSON output;
tests.

**Out of scope:** `--skill` on `stats`/`dead-skills` (evaluated and dropped
during the shared-flags scope review); attribution via `.ll/history.db` session-store
queries (scan-failures is deliberately JSONL-direct and cross-project — the
history DB is per-project and not guaranteed backfilled); changing clustering
signatures or `--capture` behavior.

## Impact

- **Priority**: P3 - convenience/analytics improvement, not blocking any workflow
- **Effort**: Medium - requires wiring skill attribution into cluster data, not just an argparse flag
- **Risk**: Low - additive, optional flag
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-07-30T02:14:15Z - `b1cb0370-8b55-4a10-a364-649e81045dd0.jsonl`

---

## Status

**Open** | Created: 2026-07-29 | Priority: P3
