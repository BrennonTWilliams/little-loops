---
id: ENH-2372
priority: P3
type: ENH
status: done
discovered_date: 2026-06-28
completed_at: 2026-06-28 18:20:57+00:00
discovered_by: user
confidence_score: 98
decision_needed: false
outcome_confidence: 95
---

# ENH-2372: audit-docs overflows context on multi-file scope — fan out to subagents

## Summary

The `audit-docs` skill (`skills/audit-docs/SKILL.md`) made the orchestrator (the
main conversation) read every documentation file body *and* run every
codebase-verification search in a single context. At multi-file scope this
overflows the context limit before a report can be produced. The skill was
reworked to fan out one audit subagent per file (batched, in parallel), so file
bodies and verification searches stay in subagent contexts and only compact
structured findings return to the orchestrator — mirroring the wave-based
subagent architecture already used by `audit-claude-config`.

## Current Behavior (before fix)

Running `/ll:audit-docs docs/guides/` (16 markdown files) discovered the files,
then the orchestrator read all 16 bodies into its own context and ran targeted
`Grep`/`Bash`/`Read` verification — also in the main context. Every file body
plus every search accumulated in one window and hit the context limit
("Context limit reached · /compact or /clear to continue") before the audit
report could be generated.

Root causes:

1. **No offload path.** `allowed-tools` did not include `Task`, so the skill
   had no way to delegate reading/verification to subagents.
2. **Orchestrator-side reads.** Phase 2 ("Audit each document") and Phase 3
   (verification) were written as work the main agent performs directly.
3. **Secondary bug:** the Phase 1 discovery `case` had no branch for a bare
   directory path (e.g. `docs/guides/`) or `dir:<path>` — only
   `full|readme|file:*` — so the model had to improvise file discovery.

## Expected Behavior

At `full`, `dir:`, or any multi-file scope the orchestrator discovers the file
list only, then spawns one `codebase-analyzer` subagent per file (batched ~4–6
in parallel). Each subagent reads its file and runs verification in its own
context, returning only a compact findings list (`file:line`, dimension,
severity, one-line description, and `old → new` for mechanical fixes). The
orchestrator aggregates findings — it never reads a doc body or runs
verification searches itself — so multi-file audits stay within the context
budget. Fix/issue-management phases (4.5–8) operate on the aggregated findings
unchanged.

## Changes Made

All in `skills/audit-docs/SKILL.md`:

1. Added `Task` to `allowed-tools`.
2. Added a **Context Budget** section forbidding orchestrator-side reads of doc
   bodies at multi-file scope.
3. Rewrote **Phase 2** from "orchestrator reads each file" to a subagent
   fan-out with a verbatim per-file assignment prompt; added **Phase 3** to
   merge the returned findings.
4. Added `dir:<path>` and bare-directory scope handling to the Phase 1
   discovery `case`, and documented it in the Audit Scopes, Arguments, and
   Examples sections.

## Verification

- `ll-verify-skills` — PASS (within 500-line limit).
- `ll-verify-triggers` `audit-docs` 0%/0% is pre-existing and not applicable:
  the skill is `disable-model-invocation: true` and its description was not
  touched (confirmed identical before/after via `git stash`).

## Related

- Pattern source: `skills/audit-claude-config/SKILL.md` (wave-based parallel
  subagent audit).


## Session Log
- `hook:posttooluse-status-done` - 2026-06-28T18:21:47 - `d285a275-a06e-4c97-b971-9b3d029a59d4.jsonl`
