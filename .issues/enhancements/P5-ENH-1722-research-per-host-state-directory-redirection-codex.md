---
id: ENH-1722
title: Research and decide per-host state directory redirection for Codex
type: ENH
priority: P5
status: open
captured_at: "2026-05-26T02:23:05Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
parent: EPIC-1463
labels: [codex, host-compat, research]
testable: false
---

# ENH-1722: Research and decide per-host state directory redirection for Codex

## Summary

`LL_STATE_DIR=.codex` currently scopes only the config probe path. All other state surfaces (`.issues/`, `.loops/`, `.loops/tmp/scratch/`, `.ll/ll-continue-prompt.md`) remain at their default paths regardless of host. EPIC-1463 explicitly deferred this decision pending a research note. This issue produces that note and a concrete decision.

## Motivation

The decision is implicit — nobody wrote down whether a Codex user is better served by `.codex/issues/`, `.codex/loops/` etc., or by the current shared-path behavior. Without a written decision, the question recurs in every conversation touching Codex state. A one-time research note closes the loop and either confirms the status quo is correct or opens a concrete implementation path.

## Acceptance Criteria

- A research note (`thoughts/research/codex-state-dir-redirection.md`) enumerating each state surface and the per-surface recommendation:
  - `.issues/` — share (project issues are host-independent) or scope to `.codex/issues/`?
  - `.loops/` — share or scope?
  - `.loops/tmp/scratch/` — share or scope?
  - `.ll/ll-continue-prompt.md` — share or scope?
  - `.ll/history.db` — share or scope?
- An explicit **Decision** section: "leave shared" or "scope per host" with rationale
- If decision is "scope per host" for any surface: a child FEAT/ENH issue filed with the implementation plan, referencing the research note
- `HOST_COMPATIBILITY.md` `[^state]` footnote updated to reference this issue's decision rather than "file a separate issue if needed"

## Implementation Steps

1. Read `docs/reference/HOST_COMPATIBILITY.md` `[^state]` footnote and EPIC-1463 per-host state section for existing framing
2. For each state surface, consider: does a Codex user sharing `.issues/` with Claude Code create friction? Does scoping help or add complexity?
3. Draft `thoughts/research/codex-state-dir-redirection.md` with per-surface analysis and a Decision section
4. Update `HOST_COMPATIBILITY.md` `[^state]` footnote with decision + link
5. If any surface warrants scoping: capture a child issue with implementation plan

## Notes

- Strong prior: the current EPIC-1463 text says "likely the latter (a project's `.issues/` is host-independent), but worth confirming rather than assuming." The research note may simply confirm this and close the gap by documenting the decision.
- This is a research-only issue; no code change is required unless the decision warrants it.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.MD` | `[^state]` footnote to update |
| `scripts/little_loops/config/core.py` | `_config_candidates()` — existing Codex state-dir scoping for reference |

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Research not yet performed; acceptance criteria unmet:
- `thoughts/research/codex-state-dir-redirection.md` does NOT exist (only 4 other Codex research notes present)
- No decision documented in `docs/reference/HOST_COMPATIBILITY.md`
- Issue remains open as a research task; no progress since capture

2026-06-18 (OUTDATED): `thoughts/research/codex-state-dir-redirection.md` still does not exist. `HOST_COMPATIBILITY.md` `[^state]` footnote still unresolved. No progress since capture (2026-05-26). Research task accurately described; no changes needed to issue body.

## Status

**Open** | Created: 2026-05-26 | Priority: P5

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): This issue scopes its research to Codex as the reference case, but the state-scoping decision applies equally to all future host runners. FEAT-1714 (Pi) and FEAT-1850 (omp) are both P5 and have no state-dir scoping of their own. If the research concludes "scope per host," Pi and omp will each need follow-on child issues. Add a note to the **Decision** section (Acceptance Criterion 2) explicitly stating whether the decision applies to Pi/omp as well, so the Pi/omp implementers have guidance without having to re-research the rationale.

## Session Log
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:35 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:17 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:23:05Z - `1e210ff4-bcab-4372-9c8c-a0ba98da62d5.jsonl`
