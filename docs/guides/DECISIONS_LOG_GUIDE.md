# Decisions Log Guide

> **When to use this**: You want a durable record of implementation choices — so settled
> decisions aren't re-litigated, team rules are enforced automatically, and automation
> pauses on issues with unresolved options instead of guessing.

Record implementation choices, enforce team rules, and prevent automation from proceeding on unresolved options.

## Table of Contents

- [Why Record Decisions?](#why-record-decisions)
- [What Is the Decisions Log?](#what-is-the-decisions-log)
- [The Four Entry Types](#the-four-entry-types)
- [The Automation Workflow](#the-automation-workflow)
- [Using /ll:decide-issue Manually](#using-lldecide-issue-manually)
- [Creating Entries via CLI](#creating-entries-via-cli)
- [Rules & Active Rules Sync](#rules--active-rules-sync)
- [Auto-generating from History](#auto-generating-from-history)
- [Promoting Decisions to Rules](#promoting-decisions-to-rules)
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

The log serves two purposes: **institutional memory** (settled choices stay queryable via `ll-issues decisions list`) and **automation gating** (`ll-auto` and `ll-parallel` will not implement an issue while `decision_needed: true` is set — see [The Automation Workflow](#the-automation-workflow)).

### Storage Layout

Storage is **hybrid**. New entries are written as append-only per-entry
fragments under `.ll/decisions.d/<uuid4>.json` (one file per entry, added via
`atomic_write_json`), which sidesteps the concurrent-append id collisions that
blocked EPIC merges (BUG-2642). A legacy `.ll/decisions.yaml` flat file may also
exist. Both tiers are read as a union — `ll-issues decisions list` and
`load_decisions()` merge the flat file with all `*.json` fragments (sorted by
timestamp), so you should query through the CLI rather than `cat`/`grep`-ing a
single file. A **fresh install therefore has only `.ll/decisions.d/`** and no
`.ll/decisions.yaml` until a compaction runs. Compaction (`save_decisions()`)
folds every fragment back into the flat file and deletes the fragment directory.

Because a never-compacted install has no flat file, presence gates must accept
**either** tier — e.g. `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]`, or
simply gate on `ll-issues decisions list` returning entries. Gating on the flat
file alone silently skips governance on fresh installs.

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

**The structural-vs-semantic gap (ENH-2443):** `decision_needed: true` sometimes has *nothing to decide* — the `## Proposed Solution` section is structurally complete but has no enumerable options (no `### Option A/B`, no bullet alternatives). `ll-issues format-check` reports this as compliant, since the gap is semantic, not structural. `/ll:decide-issue`'s Phase 2.5 catches this: `OPTIONS_MISSING` on a `--validate-only` probe, or — in `--auto` mode — one bounded `/ll:refine-issue --auto` retry to deposit options before falling through to Phase 3b's inline provisional-language scan (BUG-2606), which can still lock in a clear winner from prose recommendations even without formal option blocks. Only if Phase 3b also finds nothing does `decision_needed` stay `true` — `MANUAL_REVIEW_RECOMMENDED` (distinct from `MANUAL_REVIEW_NEEDED`) is an FSM-level diagnostic derived from the deposit-attempt marker, not emitted by this phase directly. FSM (finite-state machine) loop callers (`rn-remediate`, `autodev`) pre-check with the deterministic `ll-issues check-decidable <ID>` CLI rather than paying for a full `decide` pass with nothing to score.

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

Two more flags are available: `--auto` runs non-interactively, writing the decision without prompting for confirmation, and `--validate-only` only probes whether the issue has a decidable set of options (Phases 1–2.5) — it does no scoring and makes no writes, exiting 0 if there is something to decide or exiting 1 with `OPTIONS_MISSING` otherwise. `--validate-only` is intended for direct/interactive use (not automation subprocesses).

```
/ll:decide-issue ENH-277 --auto
/ll:decide-issue FEAT-398 --auto --validate-only
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
```

`CHANGES APPLIED` reports only these three issue-file edits (each line flips to "Skipped (idempotent)" / "already false — no change" on a repeat run). The decisions.yaml log append happens separately in Phase 7b via `ll-issues decisions add` — it's a silent no-op when `decisions.yaml` doesn't exist, and isn't itself listed in the `CHANGES APPLIED` block.

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

# Stamp provenance backlinks (ENH-2667) so the entry traces back to the
# session and issue that produced it
ll-issues decisions add \
  --type decision \
  --category architecture \
  --rule "Use atomic_write for decisions.d fragments" \
  --rationale "Prevents partial writes under concurrent EPIC-branch appends" \
  --issue ENH-2667 \
  --source-session abc123-session-id \
  --source-issue-id ENH-2667
```

Entry IDs are auto-generated as a random UUID4 (e.g.
`4e1ec28d-ae1d-4af7-b32c-d084668d36b1`). Override with `--entry-id` if you need a
specific ID. The older count-based scheme (`ARCHITECTURE-005`, `TESTING-002`) was
retired in BUG-2642 — sequential ids collided when concurrent EPIC-branch appends
minted the same `{category}-{count+1}` value; UUID4s never collide, which is what
makes per-entry fragment files (see [Storage Layout](#storage-layout)) safe to
merge. Historical entries below that still carry `ARCHITECTURE-NNN` ids predate
the change; they remain valid.

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

Sync runs automatically after `ll-issues decisions promote --enforcement required` (the default). Run it manually after `ll-issues decisions add`, after editing `.ll/decisions.yaml` directly, or after `extract-from-completed`.

---

## Auto-generating from History

If you've been running issues through little-loops for a while without the decisions log, bootstrap it from completed issues:

```bash
ll-issues decisions generate
```

Creates one `DecisionEntry` per completed issue that doesn't already have an entry. Uses `.ll/history.db` when present for faster scanning. Each entry gets ID `DEC-{ISSUE_ID}`, a timestamp from `completed_at`, and labels from issue type and priority.

These auto-generated entries are minimal stubs — they record that a decision happened (an issue was completed) without knowing what the decision was. They're useful as a starting point for retroactive annotation: run `ll-issues decisions outcome DEC-FEAT-1933 --result worked --notes "..."` to enrich them.

### LLM Extraction: `extract-from-completed`

For semantic extraction that populates actual rule text, use:

```bash
ll-issues decisions extract-from-completed [--since YYYY-MM-DD] [--issue ID] [--dry-run] [--min-confidence 0.7]
```

Unlike `generate` (which creates empty stubs), `extract-from-completed` sends each completed issue to an LLM and returns concrete, imperative rules:

```bash
ll-issues decisions extract-from-completed                      # Extract from all completed issues
ll-issues decisions extract-from-completed --since 2026-01-01  # Only issues completed since date
ll-issues decisions extract-from-completed --issue ENH-2151     # One issue only
ll-issues decisions extract-from-completed --dry-run            # Preview without writing
ll-issues decisions extract-from-completed --min-confidence 0.85  # Stricter quality gate
```

Each accepted candidate becomes a `RuleEntry` with `enforcement: advisory`, labeled `extracted` and the candidate's scope value (`global` or `issue`), and linked back to the source issue via the `issue:` field.

**Deduplication** runs at two levels:
1. **Issue-level**: if any existing entry references the issue ID, that issue is skipped entirely.
2. **Content-level**: if the extracted rule shares ≥60% of significant tokens with an existing rule, it is discarded as a near-duplicate.

### Automated Extraction Loop

`.loops/distill-decisions.yaml` automates extraction on a recurring basis. Each run:

1. Captures a baseline count of current `decisions.yaml` entries.
2. Runs `extract-from-completed --since <last-checkpoint>` (checkpoint at `.loops/distill-decisions-checkpoint.txt`).
3. Verifies the count increased (`output_numeric` evaluator — non-LLM).
4. On success, writes today's date to the checkpoint so the next run skips already-processed issues.
5. On no new entries, exits cleanly without modifying the checkpoint.

Trigger manually:
```bash
ll-loop run distill-decisions
```

Or hook it into your automation pipeline to run automatically after issues transition to `done`. The `issue-completion-log.sh` hook fires `extract-from-completed --issue <ID>` in a background subshell after each issue closes, so extraction happens asynchronously without blocking the session (see [Built-in Hooks Guide](BUILTIN_HOOKS_GUIDE.md)).

---

## Promoting Decisions to Rules

After recording several decisions, patterns emerge — the same guidance recurs across multiple issues, which is a signal that it belongs as a standing rule rather than a one-off record. Two subcommands manage this lifecycle.

### Finding Candidates: `suggest-rules`

`suggest-rules` scans all `DecisionEntry` records in `.ll/decisions.yaml`, groups them by category and shared terminology, and surfaces entries that appear to encode recurring guidance:

```bash
ll-issues decisions suggest-rules
```

**Sample output:**

```
[SUGGEST][high-signal] ARCH-001, ARCH-002, ARCH-003 share category=architecture and reference sub_loop
  — consider promoting to a rule: "Use sub-loop composition always"
    • ARCH-001: Use sub-loop composition always
    • ARCH-002: Register adapters via Protocol
    • ARCH-003: Prefer file-poller for callbacks
```

The `[high-signal]` tag appears when a category has 3+ decisions sharing common tokens. Without the tag, the cluster was detected via pairwise token overlap in a smaller group.

> `suggest-rules` requires at least 3 `DecisionEntry` records to run. It exits 1 if fewer exist, or if all decisions are one-off choices (entries whose `rule` text starts with `Option A`, `Option B`, `Option C`, `NO-GO`, or `Captured:`). It operates only on `DecisionEntry` records — existing `RuleEntry` records are not considered for promotion.

### Promoting to a Standing Rule: `promote`

Once you've identified a good candidate, promote it:

```bash
ll-issues decisions promote ARCH-001                          # Promote as required rule (auto-syncs)
ll-issues decisions promote ARCH-001 --enforcement advisory   # Promote as advisory rule (no auto-sync)
```

`promote` replaces the `DecisionEntry` in-place with a `RuleEntry`, preserving the same `id`, `category`, `rationale`, and `rule` text. The `type` field changes from `"decision"` to `"rule"`, and an `enforcement` field is added.

```
Promoted ARCH-001 → rule (enforcement: required)
```

> When `--enforcement required` is used (the default), `promote` automatically runs `sync` — see [Rules & Active Rules Sync](#rules--active-rules-sync) for what that writes to `.ll/ll.local.md`. Using `--enforcement advisory` skips the auto-sync; advisory rules appear in `ll-issues decisions list --type rule` but are not propagated to `.ll/ll.local.md`.

There is no `demote` subcommand — promotion is one-way via CLI. To revert, edit `.ll/decisions.yaml` directly and change the `type:` field back to `"decision"`.

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

The decisions feature has a small config namespace in `.ll/ll-config.json`. Defaults shown below; `auto_generate` defaults to `[]` (no auto-generation) — the example sets it to `["FEAT", "ENH"]` to illustrate a common customization that skips BUG entries:

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
| `decisions.log_path` | `".ll/decisions.yaml"` | Path to the legacy flat file. The per-entry fragment directory is **derived** from this — always `log_path`'s sibling with a `.d` suffix (`.ll/decisions.d/`) — and is not independently configurable (BUG-2647, Option A) |
| `decisions.auto_generate` | `[]` | Issue type prefixes to auto-generate entries from when `ll-issues decisions generate` runs (e.g., `["FEAT", "ENH"]` skips BUG entries) |

---

## Load-Time Validation

Both storage tiers — the flat `.ll/decisions.yaml` and the
`.ll/decisions.d/*.json` fragments — are gated by `ll-verify-decisions`
(ENH-2589) at three transport layers, listed in order of when they fire.
`ll-verify-decisions` re-globs the fragment directory in a strict second pass
(bypassing the read path's silent skip), so a single malformed fragment fails the
gate:

1. **Git pre-commit hook** (ENH-2590) — `repo: local` block in
   `.pre-commit-config.yaml` invokes `ll-verify-decisions` on staged changes
   to `.ll/decisions.yaml` or `.ll/decisions.d/*.json` (matched by
   `^\.ll/decisions(\.yaml|\.d/.*\.json)$`). Blocks `git commit` on any `yaml.YAMLError`,
   missing required field, or unknown entry-type discriminator. Active after
   `pre-commit install`.
2. **Pytest CI belt** (ENH-2591) — wraps the same validator as a
   subprocess-asserting gate in `python -m pytest scripts/tests/`, so
   `git commit --no-verify` and non-hook edit paths still cannot land a
   corruption on `main`.
3. **Claude Code `PreToolUse` hook** (ENH-2592,
   [`hooks/scripts/check-decisions-yaml.sh`](../../hooks/scripts/check-decisions-yaml.sh))
   — blocks the corruption in the editor session, before the file is even
   written. Fires on `Write`/`Edit` of either `.ll/decisions.yaml` or a
   `.ll/decisions.d/*.json` fragment with `timeout: 5`. The hook stages the **candidate content**
   (`tool_input.content` for Write, or the post-Edit result reconstructed
   from `old_string` → `new_string`) in a temporary `<tmp>/.ll/decisions.yaml`
   and runs `ll-verify-decisions --config-root <tmp>` against it —
   validating the candidate before mutation, not the on-disk file.
   Corruption (any `yaml.YAMLError`/`KeyError`/`ValueError`) bubbles up
   as host-level exit 2 with the validator's single-line `ERROR:` on
   stderr; clean candidates exit 0 and let Claude write through. Skips
   gracefully when `python3` or `ll-verify-decisions` is missing — the
   pre-commit and pytest belts remain authoritative. Gated by
   [`scripts/tests/test_check_decisions_yaml_hook.py`](../../scripts/tests/test_check_decisions_yaml_hook.py).

All three layers share the validator's exit-code contract: `0` on a clean
file, `1` with a single-line `ERROR:` message on stderr pointing at the
file path for any caught corruption class. Manually re-run the validator
against an arbitrary config root with:

```bash
ll-verify-decisions --config-root /path/to/repo
```

See [`scripts/tests/test_decisions_yaml_pre_commit_gate.py`](../../scripts/tests/test_decisions_yaml_pre_commit_gate.py)
for the end-to-end pre-commit fixture pattern and
[`scripts/tests/test_decisions_yaml_gate.py`](../../scripts/tests/test_decisions_yaml_gate.py)
for the pytest CI belt (positive live-file case + negative OTHE-203
fixture case against `ll-verify-decisions`).

## See Also

- [Issue Management Guide](ISSUE_MANAGEMENT_GUIDE.md) — `decision_needed` in the full refinement pipeline
- [Loops Guide](LOOPS_GUIDE.md) — how `autodev` and `recursive-refine` handle the decision gate and skip decision-blocked issues
