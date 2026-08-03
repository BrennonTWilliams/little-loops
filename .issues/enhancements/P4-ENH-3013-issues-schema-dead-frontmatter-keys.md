---
id: ENH-3013
title: config-schema.json issues object declares dead per-issue-frontmatter keys
type: ENH
status: open
priority: P4
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
program_design_not_applicable: true
testable: false
labels:
- config-schema
- cleanup
---

# ENH-3013: `config-schema.json`'s `issues` object declares dead per-issue-frontmatter keys

## Summary

`config-schema.json`'s top-level `issues` object (`config-schema.json:74-269`)
declares 8 properties — `status`, `parent`, `blocked_by`, `depends_on`,
`relates_to`, `duplicate_of`, `labels`, `milestone` (roughly lines 111-249) —
that read as per-issue-file frontmatter field definitions accidentally
declared inside the *global* `issues` config object, rather than as project
settings a user would actually set once in `ll-config.json`.

## Current Behavior

`IssuesConfig.from_dict()` (`scripts/little_loops/config/features.py:207-243`)
only reads `base_dir, categories, completed_dir, deferred_dir, priorities,
templates_dir, capture_template, duplicate_detection, next_issue, auto_commit,
auto_commit_prefix` — it never reads any of the 8 keys above. Grep confirms
nothing else in the codebase reads `config["issues"]["status"]`, `["parent"]`,
etc. as global config either. Since `issues` has `additionalProperties: false`
in the schema, these 8 keys are pure schema noise: they can't actually be set
meaningfully by a user, and (per BUG-3009's sibling finding about missing
validation) nothing currently rejects them if a user tried anyway.

## Scope Boundaries

**File-contention note:** ENH-3014 edits the same two files — it adds a
`skill_budget` object to `config-schema.json` and a new parity assert to
`scripts/tests/test_config_schema.py`. Different regions, so no `depends_on` is
declared, but do not run these two as concurrent epic branches under
`parallel.epic_branches` — land one, then the other.

In scope: removing the 8 unused properties from the `issues` object in
`config-schema.json` and updating `test_config_schema.py` if it asserts on
the current property list. Out of scope: changing the per-issue frontmatter
field definitions documented in `.claude/CLAUDE.md`'s "Issue File Format"
section (those are correct as-is) or migrating any existing issue files.

## Danger: "not in `IssuesConfig.from_dict()`" does NOT mean dead

The `issues` schema object declares **20** properties. `IssuesConfig.from_dict()`
reads 11 of them. The 8 above are dead. **The 20th — `deploy_templates` — is
absent from `from_dict()` and is nonetheless fully live**, read straight off the
raw config dict at three call sites, with its own tests and its own schema guard:

- `scripts/little_loops/init/cli.py:516`, `:689` — `config.get("issues", {}).get("deploy_templates")`
- `scripts/little_loops/init/tui.py:892` — same
- `scripts/tests/test_init_core.py:2108`, `:2280` — behavioral coverage
- `scripts/tests/test_config_schema.py:108-120` — asserts it stays declared

The same pattern appears for other `issues` keys outside `IssuesConfig`:
`scripts/little_loops/hooks/post_tool_use.py:100-106` reads `base_dir` and
`auto_commit_prefix` directly from raw config.

**An implementer who applies the "not in `from_dict()` ⇒ delete" rule literally
will delete `deploy_templates` and break `ll-init`'s issue-template deployment.**
Liveness must be established by grepping raw reads, not by reading `from_dict()`.

## Expected Behavior

The global `issues` schema object should only declare properties that some part
of the codebase actually reads — whether via `IssuesConfig.from_dict()` or via a
raw `config["issues"][...]` access. Per-issue frontmatter field documentation
(status/parent/blocked_by/etc. — already documented in `.claude/CLAUDE.md`'s
"Issue File Format" section) belongs there, not in the project-wide config schema.

## Suggested Fix Direction

1. **Establish liveness for all 20 declared properties** before deleting
   anything. Run all three sweeps, not just the first:
   - `IssuesConfig.from_dict()` (`config/features.py:207-243`) — typed reads.
   - `grep -rn 'get("issues"' scripts/` and `grep -rn '\["issues"\]' scripts/` —
     raw-config reads (this is the sweep that catches `deploy_templates`).
   - `grep -rn 'issues\.<key>' docs/ skills/ commands/` — documented-as-real.
2. Remove only the properties that all three sweeps find unreferenced — expected
   to be exactly the 8 named above.
3. Update `scripts/tests/test_config_schema.py` if it asserts on the property
   list. Note `test_issues_deploy_templates_in_schema` (`:108-120`) will fail
   loudly if `deploy_templates` is removed — treat that failure as the guard
   working, not as a test to update.

## Acceptance Criteria

- [ ] The 8 dead keys (`status`, `parent`, `blocked_by`, `depends_on`,
      `relates_to`, `duplicate_of`, `labels`, `milestone`) are gone from the
      `issues` object in `config-schema.json`.
- [ ] `deploy_templates` is **retained** and `test_issues_deploy_templates_in_schema`
      still passes.
- [ ] The remaining 12 properties are each traceable to a real read (typed or raw).
- [ ] `.claude/CLAUDE.md`'s "Issue File Format" section is unchanged.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P4

## Impact

- **Priority**: P4 — pure cleanup, no functional impact (the keys already do
  nothing).
- **Effort**: Small.
- **Risk**: Low — removing unused schema properties; verify no doc reference
  first.
- **Breaking Change**: No (these keys were never functional).
