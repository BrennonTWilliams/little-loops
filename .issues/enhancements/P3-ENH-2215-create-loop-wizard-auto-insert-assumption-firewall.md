---
id: ENH-2215
title: create-loop wizard auto-insert assumption-firewall gate for external API loops
type: enhancement
priority: P3
status: open
parent: EPIC-2207
depends_on: ENH-2220
captured_at: '2026-06-18T15:38:06Z'
discovered_date: '2026-06-18'
discovered_by: capture-issue
---

# ENH-2215: create-loop wizard auto-insert assumption-firewall gate for external API loops

## Summary

The `/ll:create-loop` wizard generates loop templates based on the user's intent but does not ask whether the loop involves external APIs. Add a wizard question in the "Harness a skill" branch: "Does this loop invoke external packages or third-party APIs?" If yes, auto-insert a pre-wired `assumption-firewall` sub-loop call before the main implementation state, with a `targets` context variable placeholder.

## Motivation

Loop authors writing integration loops currently must manually wire assumption-firewall if they want proof-first gating. The wizard is the ideal place to shift this left: ask once, insert the boilerplate, and leave only the `targets` list for the author to fill in.

## Implementation Steps

1. In the `/ll:create-loop` skill (wizard branch for "Harness a skill"), after the loop name/description questions, add: "Does this loop call external packages or APIs (e.g., Anthropic SDK, HTTP APIs, database drivers)? [y/n]"
2. If yes:
   - Inject an `assumption_gate` state before the first implementation state:
     ```yaml
     assumption_gate:
       type: shell
       action: "ll-loop run assumption-firewall --context issue_file=${context.issue_file}"
       on_exit:
         0: implement   # done
         1: blocked     # blocked
     blocked:
       type: terminal
       message: "External API assumptions unproven. Run /ll:explore-api for each dependency."
     ```
   - Set `context.issue_file` as a required context variable in the loop header comment.
3. Add to `create-loop` skill docs: "The assumption-firewall gate requires the issue file path in context (`issue_file`)."

## Scope Boundaries

- **In scope**: Adding a question to the create-loop wizard's "Harness a skill" branch about external API usage; auto-inserting assumption-firewall gate state and blocked terminal state when answer is yes; documenting `issue_file` context variable requirement
- **Out of scope**: Changes to the assumption-firewall loop itself; modifications to other wizard branches; retroactive insertion of gates into existing loops; changes to how existing loops are stored or migrated

## Impact

- **Priority**: P3 - Medium priority; quality-of-life improvement for loop authors using external APIs
- **Effort**: Small - Single wizard question + conditional YAML injection in the create-loop skill
- **Risk**: Low - Non-breaking change; only affects generated output when user answers "yes"
- **Breaking Change**: No

## Acceptance Signals

- A loop created with "yes" to external APIs includes an `assumption_gate` state
- `ll-loop validate` passes on the generated YAML
- The `blocked` terminal state is reachable (MR-4 compliant — `on_no`/`on_partial` covered)
- A loop created with "no" to external APIs is unchanged from current output

## Labels

`enhancement`, `wizard`, `create-loop`, `assumption-firewall`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue coordinates with ENH-2220 (scope-epic). When the wizard is run from a sub-issue created by ENH-2220's scope-epic flow, it should read `learning_tests_required` from the issue's frontmatter (already populated by ENH-2220) rather than asking the user a duplicate "does this involve external APIs?" question. See [[ENH-2220]] for the scope-epic data pipeline.

**Note** (added by `/ll:audit-issue-conflicts`): The wizard must skip the "does this involve external APIs?" question whenever `learning_tests_required` is present and non-empty in the issue's frontmatter — regardless of which skill populated it. ENH-2220 (scope-epic) and ENH-2209 (refine-issue/wire-issue) are both valid sources. The prior scope note's "when the wizard is run from a sub-issue created by ENH-2220" phrasing is too narrow: a user who refines an issue via ENH-2209 and then runs create-loop would still be asked the redundant question. Check: if `learning_tests_required` is non-empty in frontmatter, auto-insert the assumption-firewall gate without prompting. See [[ENH-2209]].

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2215 and ENH-2217 both parse `learning_tests_required` from issue frontmatter independently. To prevent divergent field-name handling or fallback logic, both should use the same read mechanism: either `ll-issues show --json <ISSUE_ID> | jq '.learning_tests_required // []'` or a shared Python helper. Coordinate with [[ENH-2217]] to avoid two divergent parsing implementations.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-18T21:17:06 - `23eb26e5-163c-41e9-bc83-173b75524706.jsonl`
- `/ll:format-issue` - 2026-06-18T19:32:29 - `0ad50852-04aa-49ce-b1bf-d489adb4f465.jsonl`
- `/ll:capture-issue` - 2026-06-18T15:38:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a36b2894-cd5b-4d62-9c0f-f69cbebc76de.jsonl`

**Open** | Created: 2026-06-18 | Priority: P3
