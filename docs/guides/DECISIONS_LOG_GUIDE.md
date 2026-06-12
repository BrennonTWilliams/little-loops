# Decisions Log Guide

> **When to use this**: You want a durable record of implementation choices — so settled
> decisions aren't re-litigated, team rules are enforced automatically, and automation
> pauses on issues with unresolved options instead of guessing.

Record implementation choices, enforce team rules, and prevent automation from proceeding on unresolved options.

## Table of Contents

- [What Is the Decisions Log?](#what-is-the-decisions-log)
- [The Four Entry Types](#the-four-entry-types)
- [The Automation Workflow](#the-automation-workflow)
- [Using /ll:decide-issue Manually](#using-lldecide-issue-manually)
- [Creating Entries via CLI](#creating-entries-via-cli)
- [Rules & Active Rules Sync](#rules--active-rules-sync)
- [Auto-generating from History](#auto-generating-from-history)
- [Recording Outcomes](#recording-outcomes)
- [Superseding Old Entries](#superseding-old-entries)
- [Configuration](#configuration)
- [See Also](#see-also)

---

## Why Record Decisions?

- **Prevents re-litigating settled choices.** When a question comes up again ("why didn't we use approach B?"), `ll-issues decisions list` answers it in seconds instead of `git log` spelunking.
- **Drives implementation constraints automatically.** Required rules (`enforcement: required`) are propagated to `.ll/ll.local.md` and injected into every planning session — Claude sees them without you having to repeat them.
- **Creates an audit trail.** The `outcome:` field closes the loop: after a decision ages 3+ months in production, you can record whether it worked, mixed, or was reversed.
- **Gates automation on unresolved options.** When `confidence-check` detects competing approaches, it sets `decision_needed: true`. Automation won't implement until `/ll:decide-issue` clears the flag.

---

## What Is the Decisions Log?

`.ll/decisions.yaml` is a project-level governance file that records four types of entries: architectural decisions made, rules the team enforces, exceptions granted to those rules, and coupling contracts that tell `wire-issue` what to audit when specific files change.

The log serves two purposes:

1. **Institutional memory** — "why did we pick Option A?" has an answer you can `ll-issues decisions list` instead of `git log` for.
2. **Automation gating** — when `confidence-check` detects unresolved options in an issue, it sets `decision_needed: true` in the frontmatter. `ll-auto` and `ll-parallel` will not implement that issue until `/ll:decide-issue` clears the flag and records the chosen option in this file.

---

## The Four Entry Types

### Decision

Records a choice made with rationale and the alternatives considered. Optionally accepts an `outcome` later once the decision has been measured in production.

```yaml
- id: ARCHITECTURE-004
  type: decision
  timestamp: '2026-06-04T23:32:01Z'
  category: architecture
  labels: [design, fsm]
  rationale: >
    Option A scored 11/12 vs Option B 5/12. _config_candidates() is a
    near-identical precedent in the codebase.
  rule: 'Option A: Host-aware get_project_folder()'
  alternatives_rejected: 'Option B: New resolve_session_dir() wrapper'
  scope: issue
  issue: ENH-1945
```

After the change ships, record whether it worked. Here's what the same entry looks like after 3 months in production:

```yaml
- id: ARCHITECTURE-004
  type: decision
  timestamp: '2026-06-04T23:32:01Z'
  category: architecture
  labels: [design, fsm]
  rationale: >
    Option A scored 11/12 vs Option B 5/12. _config_candidates() is a
    near-identical precedent in the codebase.
  rule: 'Option A: Host-aware get_project_folder()'
  alternatives_rejected: 'Option B: New resolve_session_dir() wrapper'
  scope: issue
  issue: ENH-1945
  outcome:
    result: worked          # worked | did_not_work | mixed | reversed
    measured_at: '2026-09-01T00:00:00Z'
    notes: >
      No call-site breakage in 90 days. The backward-compatible parameter
      addition held through three subsequent refactors. Would make the same
      call again.
```

### Rule

An enforced team invariant. Rules marked `enforcement: required` are propagated automatically to `.ll/ll.local.md` via `ll-issues decisions sync`.

```yaml
- id: RULE-TESTING-001
  type: rule
  timestamp: '2026-05-15T12:00:00Z'
  category: testing
  labels: [mandatory, test-coverage]
  rationale: Prevents shipping CLI commands without regression coverage.
  rule: All new CLI commands must have corresponding tests in scripts/tests/.
  enforcement: required     # required | advisory
```

### Exception

A one-time override of a rule, linked back to the rule it excepts.

```yaml
- id: EXCEPTION-2026-001
  type: exception
  timestamp: '2026-06-01T09:00:00Z'
  category: testing
  labels: [one-time]
  rationale: >
    ll-gitignore is a thin wrapper over an existing, well-tested library.
    The exception is bounded to this one command.
  rule_ref: RULE-TESTING-001   # links to the rule being excepted
  issue: FEAT-700
  alternatives_rejected: Writing tests that only test the underlying library
```

### Coupling

Declares a file-change → audit-target contract. When `wire-issue` sees that a proposed change touches a file matching `if_changed`, it flags the `then_check` targets as required review. Used to automate wiring gap detection.

```yaml
- id: COUPLING-ARCH-CLI-001
  type: coupling
  timestamp: '2026-05-20T10:00:00Z'
  category: architecture
  labels: [add-cli-command]
  rationale: New CLI commands always need test coverage and reference docs.
  if_changed: 'scripts/little_loops/cli/**/*.py'
  then_check:
    - scripts/tests/test_*_cli.py
    - docs/reference/CLI.md
  tier: soft                  # hard | soft | fyi
  archetype: add-cli-command
  enforcement: advisory
```

`tier` controls how `wire-issue` treats the gap: `hard` blocks implementation, `soft` warns, `fyi` notes only.

---

## The Automation Workflow

This is the end-to-end flow when you're running issues through `ll-auto`, `ll-parallel`, or the `autodev` loop:

```
┌─ Issue captured ──────────────────────────────────────────────────┐
│                                                                   │
│  /ll:refine-issue                                                 │
│      Deposits multiple options in "## Proposed Solution"          │
│      (e.g., "Option A: ... Option B: ...")                        │
│          ↓                                                        │
│  /ll:confidence-check                                             │
│      Detects signal phrases in Outcome Risk Factors:              │
│      "unresolved decision", "Option A or B", "either/or", etc.    │
│      → sets decision_needed: true in frontmatter                  │
│          ↓                                                        │
│  ll-auto / ll-parallel / autodev loop                             │
│      Reads decision_needed: true                                  │
│      → pauses implementation                                      │
│      → invokes /ll:decide-issue ISSUE_ID --auto                   │
│          ↓                                                        │
│  /ll:decide-issue                                                 │
│      Scores each option: Consistency / Simplicity /               │
│      Testability / Risk (0–3 each, max 12)                        │
│      → inserts > **Selected:** callout into issue                 │
│      → sets decision_needed: false                                │
│      → appends DecisionEntry to .ll/decisions.yaml               │
│          ↓                                                        │
│  Automation resumes with the decided issue                        │
└───────────────────────────────────────────────────────────────────┘
```

The `decision_needed` flag is the handshake. `confidence-check` sets it when it sees ambiguity; `decide-issue` clears it after selecting an option. Automation never implements an issue while the flag is set.

**Signal phrases that trigger `decision_needed: true`:**

- "open decision"
- "unresolved decision"
- "resolve before implementing"
- "decision point"
- "either/or" / "either...or"
- "Option A or" / "Option A/B"

---

## Using /ll:decide-issue Manually

You don't have to wait for automation to reach the issue. Run `decide-issue` yourself as soon as you see multiple options in the Proposed Solution:

```
/ll:decide-issue FEAT-1933
```

Use `--dry-run` to preview the scoring table and selected option without modifying the issue file:

```
/ll:decide-issue FEAT-1933 --dry-run
```

**Sample output:**

```
DECIDE ISSUE: FEAT-1933

OPTIONS FOUND (2 total)
  Option A: Host-aware get_project_folder()
  Option B: New resolve_session_dir() wrapper

SCORING

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A      | 3/3         | 3/3        | 2/3         | 3/3  | 11/12 |
| B      | 2/3         | 1/3        | 1/3         | 1/3  |  5/12 |

DECISION
✓ Selected: Option A (score: 11/12)

Reasoning: Option A reuses _config_candidates() precedent pattern with
zero call-site breakage. Backward-compatible parameter addition.

CHANGES APPLIED
  - Annotated issue with > **Selected:** callout
  - Appended ### Decision Rationale section
  - decision_needed: set to false
  - Appended decision entry to .ll/decisions.yaml
```

---

## Creating Entries via CLI

Use `ll-issues decisions add` to create entries directly, without going through the issue workflow:

```bash
# Record an architectural decision
ll-issues decisions add \
  --type decision \
  --category architecture \
  --rule "Use SQLite for the session store (not PostgreSQL)" \
  --rationale "No server to manage; project scope is single-user local" \
  --issue FEAT-324

# Create a required rule
ll-issues decisions add \
  --type rule \
  --category testing \
  --rule "All new CLI commands must have corresponding tests in scripts/tests/" \
  --enforcement required

# Create a coupling contract
ll-issues decisions add \
  --type coupling \
  --category architecture \
  --if-changed "scripts/little_loops/cli/**/*.py" \
  --then-check "scripts/tests/test_*_cli.py,docs/reference/CLI.md" \
  --tier soft \
  --archetype add-cli-command \
  --rationale "New CLI commands need test coverage and reference docs"

# Grant a one-time exception to a rule
ll-issues decisions add \
  --type exception \
  --category testing \
  --rule-ref RULE-TESTING-001 \
  --rationale "Thin wrapper over well-tested library; exception bounded to ll-gitignore" \
  --issue FEAT-700
```

Entry IDs are auto-generated based on type and category (e.g., `ARCHITECTURE-005`, `RULE-TESTING-002`). Override with `--id` if you need a specific ID.

**List all entries with filtering:**

```bash
ll-issues decisions list
ll-issues decisions list --type rule
ll-issues decisions list --type decision --category architecture
ll-issues decisions list --active-only    # exclude superseded entries
ll-issues decisions list --format json
```

---

## Rules & Active Rules Sync

Required rules (those with `enforcement: required`) are automatically propagated to `.ll/ll.local.md` so they're visible to every developer and to Claude without requiring a manual read of the YAML file.

```bash
ll-issues decisions sync
```

This rebuilds the `## Active Rules` section in `.ll/ll.local.md`:

**Before sync:**
```markdown
# Local Settings Notes

Personal development preferences.
```

**After sync:**
```markdown
# Local Settings Notes

Personal development preferences.

## Active Rules

- All new CLI commands must have corresponding tests in scripts/tests/
- Config changes must be backward-compatible for at least two releases
```

> The `## Active Rules` section is machine-written. Don't hand-edit it — it will be overwritten on the next `sync`. Advisory rules (`enforcement: advisory`) are not included.

Sync runs automatically at session start and after `ll-issues decisions add --enforcement required`. Run it manually after editing `.ll/decisions.yaml` directly.

---

## Auto-generating from History

If you've been running issues through little-loops for a while without the decisions log, bootstrap it from completed issues:

```bash
ll-issues decisions generate
```

Creates one `DecisionEntry` per completed issue that doesn't already have an entry. Uses `.ll/history.db` when present for faster scanning. Each entry gets ID `DEC-{ISSUE_ID}`, a timestamp from `completed_at`, and labels from issue type and priority.

These auto-generated entries are minimal stubs — they record that a decision happened (an issue was completed) without knowing what the decision was. They're useful as a starting point for retroactive annotation: run `ll-issues decisions outcome DEC-FEAT-1933 --result worked --notes "..."` to enrich them.

---

## Recording Outcomes

After a decision has been in production long enough to evaluate, record what happened:

```bash
ll-issues decisions outcome ARCHITECTURE-004 --result worked
ll-issues decisions outcome ARCHITECTURE-004 --result mixed --notes "Worked for the common case; edge cases needed a follow-up patch"
ll-issues decisions outcome ARCHITECTURE-004 --result reversed --notes "Reverted in ENH-2100 — the API changed and the assumption broke"
```

Results: `worked` | `did_not_work` | `mixed` | `reversed`

Recording outcomes builds a searchable record of which approaches held up. Over time, `ll-issues decisions list --type decision` shows you which categories of decisions tend to get reversed — a useful signal for where to slow down and explore more options.

Use `--force` to overwrite an existing outcome.

---

## Superseding Old Entries

When a rule or decision is replaced by a newer one, mark the old entry as superseded rather than deleting it:

```bash
ll-issues decisions add \
  --type rule \
  --category testing \
  --rule "All new CLI commands must have tests AND type annotations" \
  --enforcement required \
  --supersedes RULE-TESTING-001
```

The old entry stays in the YAML for audit trail purposes. `--active-only` filters it out of list results. `decisions sync` excludes superseded rules from `.ll/ll.local.md`.

---

## Configuration

The decisions feature has a small config namespace in `.ll/ll-config.json`:

```json
{
  "decisions": {
    "enabled": false,
    "log_path": ".ll/decisions.yaml",
    "auto_generate": ["FEAT", "ENH"]
  }
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `decisions.enabled` | `false` | Feature gate; the log still works when false, but automation gating on `decision_needed` requires this to be true |
| `decisions.log_path` | `".ll/decisions.yaml"` | Path to the decisions YAML file |
| `decisions.auto_generate` | `[]` | Issue type prefixes to auto-generate entries from when `ll-issues decisions generate` runs (e.g., `["FEAT", "ENH"]` skips BUG entries) |

---

## See Also

- [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) — `decision_needed` in the full refinement pipeline
- [Loops Guide](LOOPS_GUIDE.md) — how `autodev` and `recursive-refine` handle the decision gate and skip decision-blocked issues
