---
name: ll-prioritize-issues
description: Analyze issues and prepend priority levels (P0-P5) to filenames
allowed-tools:
  - Read
  - Bash(ll-issues:*)
arguments:
  - name: flags
    description: "Optional flags: --auto (non-interactive), --check (check-only for FSM evaluators)"
    required: false
---

# Prioritize Issues

You are tasked with assigning priority prefixes to issue filenames. Discovery,
rename mechanics, and the `--check` gate are handled by `ll-issues prioritize`
(ENH-2953) — this command owns only the judgment step.

## Priority Levels

| Priority | Description | Criteria |
|----------|-------------|----------|
| P0 | Critical | Production outages, data loss, security vulnerabilities |
| P1 | High | Major functionality broken, affects many users |
| P2 | Medium | Important improvements, moderate impact |
| P3 | Low | Nice-to-have, minor improvements |
| P4 | Backlog | Future consideration, low urgency |
| P5 | Wishlist | Ideas, long-term vision items |

Judge on: user/business impact (including `business_value`/`goal_alignment`/
`persona_impact` frontmatter when present), technical debt/blocking risk, and
effort (quick win vs. major undertaking).

## Process

1. Parse `${flags}` for `--auto`/`--check` (also auto-mode when
   `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS` is set).
2. `--check`: run `ll-issues prioritize --check` and exit with its exit code —
   no narration, this is the FSM-usable gate.
3. Run `ll-issues prioritize --json` to list unprioritized issues.
   - **If non-empty**: `Read` each issue, judge its priority per the table
     above, then pipe the resulting `{"ID": "P[X]", ...}` map to
     `ll-issues prioritize --apply -`. Report the applied renames.
   - **If empty** (all active issues already prioritized): unless
     `AUTO_MODE`, call `AskUserQuestion` — header "Re-prioritize", options
     "Re-evaluate all" (re-assess every active issue) / "View current" (show
     `ll-issues prioritize --all --json` grouped by priority, then stop). In
     `AUTO_MODE`, or on "Re-evaluate all": run
     `ll-issues prioritize --all --json`, re-judge each issue, build a map of
     only the entries whose priority changed, and pipe it to
     `ll-issues prioritize --apply -`. Report old → new priority per change,
     and how many were unchanged.

## Examples

```bash
/ll:prioritize-issues
/ll:prioritize-issues --check
/ll:prioritize-issues --auto
```
