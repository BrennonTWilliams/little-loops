---
id: BUG-1416
type: BUG
priority: P2
status: open
captured_at: '2026-05-10T15:06:51Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
---

# BUG-1416: decide-issue --auto asks interactive questions instead of resolving provisional decisions

## Problem

`/ll:decide-issue ENH-1390 --auto` left `decision_needed: true` unchanged and asked an interactive question ("Want me to edit Step 11?") instead of acting. The issue had a provisional `(e.g., completed_at:)` marker in Step 11 — a single named approach in parenthetical form — which `--auto` mode should lock in and clear without user interaction.

## Root Cause

Phase 3 of `skills/decide-issue/SKILL.md` exits when `OPTIONS = 0` (no formal `Option A / Option B` blocks found). It has no fallback for provisional-language patterns (`(e.g., ...)`, `TBD`, `"fundamental rethink"`) that name a clear approach inline. In `--auto` mode this causes the skill to fall through to interactive output.

**Anchor:** Phase 3 in `skills/decide-issue/SKILL.md`

## Expected Behavior

In `--auto` mode, when no formal option blocks are found, the skill should scan all sections for provisional decision language and, if a single clear approach is named, lock it in (edit the issue text to make it declarative, run `ll-issues set-flag ISSUE_ID decision_needed false`) and report what was resolved. If no clear winner can be inferred, record it as unresolvable and exit — no interactive questions in `--auto` mode.

## Steps to Reproduce

1. Create/find an issue where a step uses `(e.g., field_name:)` instead of a formal `Option A / B` block, and `decision_needed: true` is set.
2. Run `/ll:decide-issue ISSUE_ID --auto`.
3. Observe: skill asks "Want me to edit Step N?" instead of acting.

## Impact

`--auto` mode is broken for issues with inline provisional decisions. In `ll-loop run autodev`, this causes `rerun_confidence_after_decide` to see an unchanged score, which (before ENH-1415) dead-ends the loop. Even with ENH-1415 applied, it wastes a decide invocation and routes unnecessarily to size review.

## Implementation Steps

Extend **Phase 3** of `skills/decide-issue/SKILL.md` with a new sub-phase that activates only in `--auto` mode when `OPTIONS = 0`:

> **Phase 3b — Inline decision scan (AUTO_MODE only, triggers when OPTIONS = 0)**
>
> Search ALL sections of the issue for provisional decision language:
> - `(e.g., ...)` where the parenthetical names a concrete approach
> - `"fundamental rethink"` / `"must be replaced with"` followed by a concrete proposal
> - Inline `TBD` in a design context (not a research gap)
>
> For each candidate:
> 1. Read surrounding context to determine if one approach is clearly superior (stated, not merely listed).
> 2. If a clear winner is identifiable:
>    - Edit the issue text to make the approach definitive (remove `e.g.`/parenthetical qualifier; convert provisional wording to declarative).
>    - Run `ll-issues set-flag ISSUE_ID decision_needed false`.
>    - Report what was resolved and why.
> 3. If no clear winner (genuinely ambiguous): record unresolvable in summary, leave `decision_needed: true`, and exit — **no interactive questions**.

The ENH-1390 case is the canonical example: Step 11 had `(e.g., completed_at: frontmatter field)` — one named approach in a provisional wrapper. Phase 3b should lock in `completed_at:` as the definitive field name.

## Related

- `skills/decide-issue/SKILL.md` — Phase 3 (OPTIONS check)
- `scripts/little_loops/loops/autodev.yaml` — `run_decide`, `rerun_confidence_after_decide`
- `.issues/enhancements/ENH-1390` — original issue where this manifested
- ENH-1415 — companion fix: autodev loop routing after decide fails outcome

---

## Status

Open

## Session Log
- `/ll:capture-issue` - 2026-05-10T15:06:51Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
