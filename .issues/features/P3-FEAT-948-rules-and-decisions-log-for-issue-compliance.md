---
discovered_date: 2026-04-04
discovered_by: capture-issue
---

# FEAT-948: Rules and Decisions Log for Issue Compliance

## Summary

Add a tracked and maintained rules and decisions log to ensure issues are compliant with project standards. Each entry records a timestamp, associated issue file, category, and labels. The log can be populated manually, auto-generated from completed or active issues, and used during automated validation, review, or refactoring passes.

## Current Behavior

There is no centralized log of project rules and decisions. Standards are encoded in templates and CLAUDE.md but are not tracked as individual, timestamped entries associated with specific issues. Compliance is verified informally during review commands.

## Expected Behavior

A dedicated rules and decisions log exists at `.ll/decisions.yaml` with structured, typed entries. Three distinct entry types are supported:

- **`rule`** — Standing project standards with indefinite lifetime (e.g., "all issue files must use `P[N]-TYPE-NNN` naming"). Authored at the project level, not tied to a single issue. Has an `enforcement` level (`required` or `advisory`).
- **`decision`** — Per-issue or per-feature choices made during implementation (e.g., "for FEAT-948, we chose YAML over Markdown for the log format"). Scoped to a specific issue, shorter lifetime.
- **`exception`** — A deliberate, documented violation of a standing rule. Must include `rule_ref` (the ID of the rule being broken), `rationale`, and `alternatives_rejected`. Prevents `verify-issues` from surfacing false-positive violations.

Every entry has:
- Stable, machine-readable ID in `CATEGORY-NNN` format (e.g., `NAMING-001`, `WORKFLOW-003`)
- `timestamp` of when the rule/decision was established
- `category` (e.g., naming, template-structure, workflow, tooling)
- `labels[]` for filtering and querying
- `rationale` — why the rule/decision exists (required on all types)
- `supersedes` — ID of any prior rule this replaces (for rule evolution)

The log can be created/updated through four paths:
1. Manually by the user
2. Auto-generated from completed issues (post-implementation learnings)
3. Auto-generated from open/active issues before implementation (pre-implementation decisions)
4. Auto-generated as part of automated validation, review, or refactoring workflows

Key rules are surfaced as ambient context via `ll-decisions sync`, which writes active `required` rules to an `## Active Rules` section in `.ll/ll.local.md` — making compliance present in every session without requiring a query at runtime.

## Motivation

As the issue count grows and workflows become more automated (ll-auto, ll-parallel, ll-sprint), there is increasing risk that newly captured or generated issues drift from established standards. A decisions log creates a machine-readable source of truth that automated commands can query during validation, making compliance enforceable rather than advisory.

## Proposed Solution

**Storage**: Single `.ll/decisions.yaml` with a `type` field (`rule | decision | exception`). One file is sufficient — the type field provides the constitution/research distinction without the overhead of managing multiple files.

**IDs**: `CATEGORY-NNN` format where `CATEGORY` is a short uppercase token matching the `category` field (e.g., `NAMING-001`, `WORKFLOW-003`, `TEMPLATE-002`). IDs are stable and never reused; superseded rules retain their ID with a `supersedes` pointer on the replacement.

**Rule evolution**: When a rule is refined or reversed, add a new entry with `supersedes: PRIOR-ID`. Tools treat superseded entries as inactive. This avoids editing history in place.

**CLAUDE.md sync delivery**: A new `ll-decisions sync` command reads all active `required` rules and writes them to an `## Active Rules` section in `.ll/ll.local.md`. This makes compliance ambient (always in context) rather than requiring explicit validation calls at runtime — the same mechanism SpecKit uses with `update-agent-context.sh`.

**Integration points**: `capture-issue`, `ready-issue`, `verify-issues`, `format-issue` should read the log. `ready-issue` must suppress violations where a matching `exception` entry with `rule_ref` exists.

**CLI surface**: `ll-issues decisions` subcommand for CRUD.

**Auto-generation triggers**: post-`manage-issue` completion hook and pre-implementation confidence check.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — may need to log decisions at capture time
- `skills/ready-issue/` — validation step could check against log
- `skills/verify-issues/` — can surface rule violations
- `scripts/little_loops/` — CLI entry point(s) for the new log

### Similar Patterns
- `.ll/ll-config.json` — structured config as a model for the log format
- `scripts/little_loops/issues.py` — existing issue management CLI patterns

### Tests
- TBD — unit tests for log CRUD; integration tests for auto-generation from completed issues

### Documentation
- `docs/ARCHITECTURE.md` — document new log as a persistence layer
- `.claude/CLAUDE.md` — update Key Directories and CLI Tools sections

### Configuration
- `.ll/ll-config.json` — may need a `decisions` config block (enabled, log path, auto-generate triggers)

## Implementation Steps

1. Design log schema (entry format per `type: rule | decision | exception`, storage at `.ll/decisions.yaml`, ID allocation strategy)
2. Implement core CRUD for the log (Python module in `scripts/little_loops/decisions.py`)
3. Add CLI surface (`ll-issues decisions` subcommand: `list`, `add`, `generate`, `sync`)
4. Implement `ll-decisions sync`: reads active `required` rules, writes `## Active Rules` section to `.ll/ll.local.md`
5. Integrate manual entry creation into `capture-issue` workflow
6. Add auto-generation from completed issues (post-`manage-issue` hook or `ll-history` integration)
7. Add auto-generation from active issues (pre-implementation step in `confidence-check` or `ready-issue`)
8. Add validation/query support to `verify-issues` and `ready-issue`, including exception suppression (suppress violations where a matching `exception` entry with `rule_ref` exists) and supersedes resolution (treat superseded rules as inactive)
9. Update docs and CLAUDE.md

## Use Case

**Compliance check**: A user runs `/ll:ready-issue 948`. The command queries the log, finds `NAMING-001` (enforcement: required), and confirms the issue filename matches `P[0-5]-TYPE-NNN-slug.md` — surfaces as a passing check, no manual cross-referencing needed.

**Exception suppression**: A user runs `/ll:verify-issues` after a hotfix is merged with a non-standard filename. Without the log, `verify-issues` flags it as a violation. With the log, it finds `exception` entry `NAMING-002` pointing `rule_ref: NAMING-001` for that issue, suppresses the false positive, and surfaces the exception note instead: "NAMING-001 exception documented (BUG-312): emergency hotfix, retroactive rename rejected."

**Ambient compliance**: The user runs `ll-issues decisions sync`. The command writes all active `required` rules to `.ll/ll.local.md`. In the next session, Claude reads `ll.local.md` at startup and these rules are already in context — no query required for routine issue work.

## Acceptance Criteria

- [ ] `.ll/decisions.yaml` exists with schema-validated entries
- [ ] Schema supports `type: rule | decision | exception`
- [ ] Each entry has a stable ID in `CATEGORY-NNN` format
- [ ] `rationale` field is present and required on all entry types
- [ ] `alternatives_rejected` field is supported on `decision` and `exception` entries
- [ ] `supersedes` field is supported on `rule` entries for rule evolution; superseded rules are treated as inactive
- [ ] `rule_ref` field on `exception` entries links back to the rule being violated
- [ ] `enforcement: required | advisory` field on `rule` entries
- [ ] Manual entry creation is supported via CLI or capture-issue flow
- [ ] Auto-generation from completed issues is triggered post-implementation
- [ ] Auto-generation from active issues is available as a pre-implementation step
- [ ] `verify-issues` and/or `ready-issue` can query the log, surface violations, and suppress false positives where a matching `exception` entry exists
- [ ] `ll-decisions sync` writes active `required` rules to `## Active Rules` in `.ll/ll.local.md`
- [ ] Automated validation, review, and refactoring passes can read the log
- [ ] Tests cover CRUD, auto-generation, exception suppression, and supersedes resolution

## API/Interface

```yaml
# .ll/decisions.yaml

# Standing project rule (type: rule)
- id: "NAMING-001"
  type: rule
  timestamp: "2026-04-04T00:00:00Z"
  category: naming
  labels: [issue-compliance, automation]
  rule: "All issue files must use P[0-5]-TYPE-NNN-slug.md format."
  rationale: "Enables priority-sorted CLI output and stable cross-references."
  issue: "P3-FEAT-200-issue-naming.md"   # optional origin issue
  supersedes: null
  enforcement: required   # required | advisory

# Per-feature technical choice (type: decision)
- id: "TOOLING-001"
  type: decision
  timestamp: "2026-04-04T00:00:00Z"
  category: tooling
  labels: [decisions-log, storage]
  rule: "decisions.yaml uses a single file with a type field rather than separate rules.yaml and decisions.yaml."
  rationale: "One file is sufficient; the type field provides the constitution/research distinction without managing multiple files."
  alternatives_rejected: "Two-file split adds overhead without benefit at current scale."
  issue: "P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md"
  supersedes: null
  enforcement: advisory

# Deliberate rule violation (type: exception)
- id: "NAMING-002"
  type: exception
  timestamp: "2026-04-10T00:00:00Z"
  category: naming
  labels: [issue-compliance]
  rule_ref: "NAMING-001"              # ID of the rule being violated
  issue: "P1-BUG-312-hotfix.md"       # issue that violates the rule
  rationale: "Emergency hotfix created before issue tracking was set up."
  alternatives_rejected: "Retroactive renaming would break existing references in sprint file."
```

```
# Example CLI
ll-issues decisions list [--type=rule] [--category=naming] [--label=automation]
ll-issues decisions add --type=rule --category=naming --rule="..." --rationale="..." [--issue=FEAT-948]
ll-issues decisions add --type=exception --rule-ref=NAMING-001 --issue=BUG-312 --rationale="..." --alternatives-rejected="..."
ll-issues decisions generate --from=completed  # auto-generate from completed issues
ll-issues decisions sync                        # write active required rules to .ll/ll.local.md
```

## Impact

- **Priority**: P3 - Governance improvement; important for scaling automation but not blocking current workflows
- **Effort**: Large - New persistence layer, CLI, schema design, and multi-command integration
- **Risk**: Low - Additive feature; no changes to existing issue files or commands required for MVP
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | System design context for new persistence layer |
| `.claude/CLAUDE.md` | Key Directories and CLI Tools need updates |
| `CONTRIBUTING.md` | Development guidelines for new module |

## Labels

`feature`, `issue-management`, `automation`, `compliance`, `captured`

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50b6641-c597-41dc-894f-47b323d241b9.jsonl`
