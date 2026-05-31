---
id: FEAT-948
title: Rules and Decisions Log for Issue Compliance
type: FEAT
priority: P3
discovered_date: 2026-04-04
discovered_by: capture-issue
blocked_by: []
depends_on: FEAT-1479
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

> **Graceful degradation constraint**: All integrations with `commands/ready-issue.md`,
> `commands/verify-issues.md`, and `skills/format-issue/SKILL.md` MUST gracefully skip
> decisions checks when `.ll/decisions.yaml` does not exist. The governance feature is
> opt-in — absence of the file is not an error condition. Projects that have not called
> `ll-issues decisions init` must not experience broken validation commands.

**CLI surface**: `ll-issues decisions` subcommand for CRUD.

**Auto-generation triggers**: post-`manage-issue` completion hook and pre-implementation confidence check.

**Skill-level active capture**: Three pipeline skills write `decision` entries as a side effect of their normal work — no manual step required:
- `/ll:decide-issue` — after selecting an implementation option, appends a `decision` entry containing the chosen option, scoring rationale, and `alternatives_rejected` (the other scored options). This turns every automated option selection into a structured, queryable record.
- `/ll:tradeoff-review-issues` — after completing a tradeoff analysis, appends a `decision` entry capturing the conclusion and tradeoffs evaluated.
- `/ll:go-no-go` — after rendering a verdict, appends a `decision` entry with the go/no-go result, rationale, and any blocking concerns that were resolved.

All three integrations are gated on graceful degradation: if `.ll/decisions.yaml` does not exist and `decisions.enabled` is falsy, the write is silently skipped — the skill's primary output is unchanged.

## Integration Map

### Files to Modify

**New files (create):**
- `scripts/little_loops/decisions.py` — core CRUD module (load/save/add/list/generate/sync); follow `scripts/little_loops/sprint.py:142-202` dataclass + YAML pattern
- `scripts/little_loops/cli/issues/decisions.py` — CLI subcommand handler for `ll-issues decisions`; follow `scripts/little_loops/cli/issues/next_id.py:11` pattern

**Modify existing:**
- `scripts/little_loops/cli/issues/__init__.py:95` — add `decisions` subparser after `subs = parser.add_subparsers(dest="command", ...)` at line 95; add dispatch `if args.command == "decisions": return cmd_decisions(config, args)` before `return 1`; same pattern as all other subcommands in this file
- `scripts/little_loops/config/features.py` — add `DecisionsConfig` dataclass with `enabled: bool`, `log_path: str = ".ll/decisions.yaml"`, `auto_generate: list[str]` fields; follow `IssuesConfig` at line 59
- `scripts/little_loops/config/core.py:95` — add `self._decisions = DecisionsConfig.from_dict(...)` to `_parse_config()` and expose as `@property def decisions()`
- `hooks/scripts/session-start.sh:76-83` — extend to output the body (non-frontmatter) of `ll.local.md` when it contains an `## Active Rules` section, so compliance rules surface in Claude's context at session start; currently the Python heredoc (`merge_local_config()`) only outputs JSON from frontmatter and discards the body (`sys.exit(0)` at line 83); fix is inside the Python heredoc: extract body via `content.split("---", 2)[2]` after the frontmatter parse, then print it before `sys.exit(0)`
- `commands/ready-issue.md` — add decisions log query step to suppress violations where a matching `exception` entry with `rule_ref` exists (currently at Section 2, lines 139-183)
- `commands/verify-issues.md` — add query step to surface rule violations and suppress false positives via `exception` entries (current violation categories at lines 67-80)
- `skills/format-issue/SKILL.md` — add decisions log query step; Proposed Solution explicitly lists format-issue alongside ready-issue and verify-issues as a log reader
- `config-schema.json` — add `decisions` object schema (`enabled`, `log_path`, `auto_generate`) matching `DecisionsConfig` fields

**Skill-level decision capture (write to decisions.yaml as a side effect):**
- `skills/decide-issue/SKILL.md` — after Phase 6 (annotation), if `decisions.yaml` exists (graceful degradation), append a `decision` entry: `issue` = current issue file, `rule` = selected option title, `rationale` = Decision Rationale text, `alternatives_rejected` = comma-separated list of unselected options with their scores; follow the `update_frontmatter()` write pattern at `scripts/little_loops/frontmatter.py:106` for file I/O
- `commands/tradeoff-review-issues.md` — after the final tradeoff table is produced, if `decisions.yaml` exists, append a `decision` entry: `issue` = the issue analyzed, `rule` = recommendation text, `rationale` = key tradeoff narrative, `alternatives_rejected` = losing options
- `skills/go-no-go/SKILL.md` — after the verdict is rendered, if `decisions.yaml` exists, append a `decision` entry: `issue` = the issue evaluated, `rule` = "Go" or "No-Go", `rationale` = blocking or approving criteria met, `enforcement: advisory`

**Optional (extend if auto-generation hook is implemented):**
- `hooks/scripts/issue-completion-log.sh` — detect manage-issue completion to trigger `generate --from=completed`; currently the only viable hook-level trigger for post-implementation auto-generation (see Step 7)
- `skills/capture-issue/SKILL.md` — optionally log a `decision` entry when the user makes a notable architectural choice at capture time (see Step 6)

**Optional (if adding top-level CLI):**
- `scripts/pyproject.toml:48` — add `ll-decisions = "little_loops.decisions:main"` entry point if a standalone `ll-decisions` binary is needed (vs. all ops under `ll-issues decisions`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:9` — `main_issues()` dispatches all `ll-issues` subcommands; decisions handler added here
- `scripts/little_loops/cli/__init__.py:24` — re-exports `main_issues`, no change needed
- `hooks/scripts/session-start.sh:21` — already sets `LOCAL_FILE=".ll/ll.local.md"`; needs extension to output the body content
- `skills/capture-issue/SKILL.md` — optional: log decisions at capture time
- `commands/ready-issue.md` — validation command (not a skill); add decisions log query for exception suppression
- `commands/verify-issues.md` — violation-surfacing command (not a skill); add rule violation query and false-positive suppression

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/sprint.py:142-202` — YAML persistence pattern (to_dict/from_yaml/save); closest model for `decisions.py` CRUD
- `scripts/little_loops/workflow_sequence/io.py:35` — `yaml.safe_load(f)` load pattern; `yaml.dump(data, f, default_flow_style=False, sort_keys=False)` write pattern
- `scripts/little_loops/config/features.py:59` — `IssuesConfig` dataclass + `from_dict()` factory; model for `DecisionsConfig`
- `scripts/little_loops/cli/issues/next_id.py:11` — minimal subcommand handler pattern (`cmd_next_id(config)`)
- `scripts/little_loops/sync.py:176-181` — `yaml.dump` / `yaml.safe_load` for updating frontmatter YAML in-place
- `scripts/little_loops/sprint.py:206-373` — `SprintManager` class: CRUD manager with `create`/`load`/`list_all`/`delete` over `.yaml` files; closest model for `DecisionsManager`
- `scripts/little_loops/state.py:134-155` — atomic write pattern (`tempfile.mkstemp` + `os.replace`); use if log corruption risk is a concern
- `scripts/little_loops/session_log.py:112-128` — markdown section insert-after pattern (for writing `## Active Rules` into `ll.local.md`)
- `scripts/little_loops/issue_history/parsing.py:263-287` — `scan_completed_issues(completed_dir: Path) -> list[CompletedIssue]` is the entry point for auto-generation from completed issues; returns `CompletedIssue` dataclass list; integrate here for `generate --from=completed`

### Tests

_Added by `/ll:refine-issue` — based on codebase analysis:_

**New test files (create):**
- `scripts/tests/test_decisions.py` — unit tests for `decisions.py`: load empty log, add entries per type, list with filters, exception suppression (rule_ref lookup), supersedes resolution (inactive entries), auto-generation stub
- `scripts/tests/test_cli_decisions.py` — CLI tests using `patch.object(sys, "argv", ["ll-issues", "decisions", ...])` pattern from `scripts/tests/test_issues_cli.py:29`

**Fixtures to use:**
- `temp_project_dir` (conftest.py:56) — tmpdir with `.ll/` folder; write `decisions.yaml` to `temp_project_dir / ".ll" / "decisions.yaml"` in tests
- `sample_config` (conftest.py:66) — base config dict; add `decisions` key with test config

### Documentation
- `docs/ARCHITECTURE.md` — document new log as a persistence layer
- `.claude/CLAUDE.md` — update Key Directories and CLI Tools sections

### Configuration

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/config/features.py` — add `DecisionsConfig` with `enabled`, `log_path`, `auto_generate` fields; loaded from `ll-config.json` under a `"decisions"` key
- `scripts/little_loops/config/core.py:95` — `_parse_config()` adds `self._decisions = DecisionsConfig.from_dict(self._raw_config.get("decisions", {}))`
- `config-schema.json` — add `decisions` object schema (enabled, log_path, auto_generate) matching `DecisionsConfig` fields
- `pyyaml>=6.0` is already a dependency (`scripts/pyproject.toml:38`) — no new deps needed

## Implementation Steps

1. **Design + schema** — define `@dataclass` entry types (`RuleEntry`, `DecisionEntry`, `ExceptionEntry`) in `scripts/little_loops/decisions.py`; storage at `.ll/decisions.yaml` using `yaml.safe_load` / `yaml.dump(default_flow_style=False, sort_keys=False)` pattern from `scripts/little_loops/sprint.py:184`
2. **Config** — add `DecisionsConfig` to `scripts/little_loops/config/features.py` (after `IssuesConfig:59`); wire into `BRConfig._parse_config()` at `scripts/little_loops/config/core.py:95`; update `config-schema.json`
3. **Core CRUD** — implement `load_decisions()`, `save_decisions()`, `add_entry()`, `list_entries(type, category, label)`, `resolve_active()` (supersedes-aware) in `scripts/little_loops/decisions.py`
4. **CLI subcommand** — create `scripts/little_loops/cli/issues/decisions.py` with `cmd_decisions(config, args)`; register `decisions` subparser in `scripts/little_loops/cli/issues/__init__.py:95` following existing subcommand pattern; supports `list`, `add`, `generate`, `sync` sub-sub-commands
5. **Sync to ll.local.md** — implement `sync_to_local_md(project_root)` in `scripts/little_loops/decisions.py`; writes `## Active Rules` section; extend `hooks/scripts/session-start.sh` (after line 97) to also output the body of `ll.local.md` so `## Active Rules` surfaces in Claude's context at session start
6. **Skill-level decision capture bridges** — update three skills to append `decision` entries as a side effect:
   - `skills/decide-issue/SKILL.md`: after Phase 6 annotation, call `ll-issues decisions add --type=decision --issue=$FILE --rule="<chosen option title>" --rationale="<Decision Rationale text>" --alternatives-rejected="<other options + scores>"` (or equivalent Python call); guard with `[ -f .ll/decisions.yaml ]` or `decisions.enabled` check
   - `commands/tradeoff-review-issues.md`: after final output, append `decision` entry with recommendation text and tradeoff narrative
   - `skills/go-no-go/SKILL.md`: after verdict, append `decision` entry with Go/No-Go result and rationale
7. **capture-issue integration** — update `skills/capture-issue/SKILL.md` to optionally log a `decision` entry when the user makes a notable architectural choice
8. **Auto-generation from completed issues** — add `generate_from_completed(config)` to `decisions.py` using `scan_completed_issues()` from `scripts/little_loops/issue_history/parsing.py:263`; the hook system has no per-command event (only `PostToolUse`/`Bash` and `Stop`) so auto-triggering from manage-issue requires detecting manage-issue invocation in the `issue-completion-log.sh` hook OR exposing this as a manual `ll-issues decisions generate --from=completed` command
9. **Validation integration** — update `commands/ready-issue.md` and `commands/verify-issues.md` to query decisions log: check active `required` rules, surface violations, suppress false positives where `exception` entry with matching `rule_ref` exists; also update `skills/format-issue/SKILL.md` (listed in Proposed Solution alongside these two)
10. **Tests** — write `scripts/tests/test_decisions.py` (CRUD, exception suppression, supersedes resolution) and `scripts/tests/test_cli_decisions.py` (CLI via `patch.object(sys, "argv")`); use `temp_project_dir` fixture from `conftest.py:56`
11. **Docs** — update `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md` Key Directories and CLI Tools sections

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
- [ ] `/ll:decide-issue` appends a `decision` entry to `.ll/decisions.yaml` after selecting an option; entry includes `rule` (chosen option), `rationale` (scoring summary), and `alternatives_rejected` (other options with scores); silently skipped if `decisions.yaml` does not exist
- [ ] `/ll:tradeoff-review-issues` appends a `decision` entry after completing analysis; silently skipped if `decisions.yaml` does not exist
- [ ] `/ll:go-no-go` appends a `decision` entry after rendering a verdict; silently skipped if `decisions.yaml` does not exist
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

## PM-Layer Carry-Over (Schema Extension)

_Added 2026-05-29 from PM-layer integration discussion. Additive on top of the MVP; existing entries remain valid without modification._

Two optional fields on `decision` entries that let `decisions.yaml` carry medium-horizon (roadmap/quarter) decisions and post-ship outcome data — closing the loop between *what we decided* and *did it work*. Without these, the planned `/ll:pm-tick` conductor would either need a parallel store or lose the structured-decision benefit of FEAT-948.

**Rationale**: today a `decision` entry anchors to a single `issue:`. Roadmap-level bets (e.g., "Q3 focus: multi-host CLI parity") and outcome tracking ("we shipped FEAT-X but the metric didn't move") have no clean home. Rather than a new entry type or a parallel YAML store, extending the existing schema keeps one queryable substrate for all decision data. Auto-capture pipelines (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) remain unchanged for the MVP; `/ll:pm-tick` (separate ENH) is the primary writer of the new shapes.

### New Fields on `decision` Entries

| Field | Type | Default | Purpose |
|---|---|---|---|
| `scope` | enum: `issue \| sprint \| quarter \| project` | `issue` | Horizon/anchor of the decision. `issue` preserves current behavior. |
| `outcome` | object (optional) | `null` | Post-fact record of what happened. Populated after enough time has passed to judge. |
| `outcome.result` | enum: `worked \| did_not_work \| mixed \| reversed` | required if `outcome` present | Coarse verdict. |
| `outcome.measured_at` | ISO-8601 timestamp | required if `outcome` present | When the verdict was recorded. |
| `outcome.notes` | string | optional | Free-text explanation; what evidence supported the verdict. |

**Backward compatibility**: existing entries without `scope` or `outcome` are valid and treated as `scope: issue, outcome: null`. The `issue:` field becomes optional iff `scope != issue`; for `scope: issue` (default), `issue:` is still required.

### Updated YAML Examples

```yaml
# Roadmap-scope decision (no single issue anchor)
- id: "ROADMAP-001"
  type: decision
  timestamp: "2026-05-29T00:00:00Z"
  category: roadmap
  labels: [pm-review, quarterly]
  scope: quarter
  issue: null
  rule: "Q3 focus: multi-host CLI parity (claude/codex/opencode)."
  rationale: "Three of last quarter's top-five user complaints were host-specific bugs."
  alternatives_rejected: "Continued plugin-feature investment; deferred until host parity stabilizes."
  enforcement: advisory

# Issue-scope decision with outcome populated post-ship
- id: "TOOLING-002"
  type: decision
  timestamp: "2026-04-04T00:00:00Z"
  category: tooling
  labels: [persistence]
  scope: issue
  issue: "P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md"
  rule: "Single YAML file with type field rather than separate rules.yaml / decisions.yaml."
  rationale: "One file is sufficient; type field provides the constitution/research distinction."
  alternatives_rejected: "Two-file split adds overhead without benefit at current scale."
  enforcement: advisory
  outcome:
    result: worked
    measured_at: "2026-07-15T00:00:00Z"
    notes: "Six months in: zero migration friction; queries remain fast under 200 entries."
```

### New CLI Surface

```
ll-issues decisions outcome <ID> --result=worked|did_not_work|mixed|reversed \
    [--notes="..."] [--measured-at=<ISO-8601>] [--force]
    # Default measured-at = now. Refuses to overwrite an existing outcome without --force.

ll-issues decisions list --no-outcome [--before=<date>] [--scope=<scope>]
    # Find decisions lacking outcome records; primary consumer is /ll:pm-tick,
    # which surfaces decisions that need follow-up after enough time has passed.
```

### Addendum Acceptance Criteria

- [ ] `decision` entries support optional `scope` field with values `issue | sprint | quarter | project`; defaults to `issue` when absent
- [ ] When `scope != issue`, the `issue` field MAY be `null`; validation does not require an issue anchor
- [ ] When `scope == issue` (default), the `issue` field remains required
- [ ] `decision` entries support optional `outcome` object with required `result` (enum) and `measured_at` (ISO-8601), and optional `notes`
- [ ] `ll-issues decisions outcome <ID> --result=... [--notes=...] [--measured-at=...]` populates the outcome on an existing decision
- [ ] `outcome` overwrite is refused without `--force`
- [ ] `ll-issues decisions list --no-outcome [--before=<date>] [--scope=<s>]` filters decisions missing outcome records
- [ ] Existing decision entries without `scope` or `outcome` continue to load and validate without modification (backward compatible)

### Implementation Step Adjustments

The existing 11-step plan stands. Affected steps:

- **Step 1 (Design + schema)** — add `scope: Optional[str]` and `outcome: Optional[DecisionOutcome]` to `DecisionEntry`; add `@dataclass DecisionOutcome` with `result: str`, `measured_at: str`, `notes: Optional[str]`.
- **Step 3 (Core CRUD)** — add `set_outcome(entry_id, result, measured_at, notes, force=False)` to `decisions.py`; respect the no-overwrite-without-force contract.
- **Step 4 (CLI subcommand)** — add `outcome` sub-sub-command (`ll-issues decisions outcome`) and `--no-outcome`, `--before`, `--scope` flags to `list`.
- **Step 6 (Skill-level capture)** — `/ll:tradeoff-review-issues` and `/ll:go-no-go` continue to write `scope: issue` decisions; no change needed for MVP. The planned `/ll:pm-tick` (separate ENH) is the primary writer of `scope: quarter | project` entries.
- **Step 10 (Tests)** — add coverage for: optional fields load/save round-trip; `scope: quarter` entries omitting `issue`; outcome population; outcome overwrite refusal without `--force`; `list --no-outcome --before=...` filtering.

### Out of Scope (for this addendum)

- `supersedes` on `decision` entries — `outcome.result: reversed` covers the explicit-undo case; rule-style supersession for decisions is a separate refinement if needed.
- `/ll:pm-tick` itself — separate ENH; this addendum only ensures FEAT-948's schema can carry what `/ll:pm-tick` will write and query.
- Outcome-result taxonomy beyond the four values listed — keeping the enum small avoids bikeshedding; finer-grained evidence belongs in `notes`.

---

## Status

**Open** | Created: 2026-04-04 | Priority: P3

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- `scripts/little_loops/cli/issues/__init__.py:95` — add_subparsers confirmed at line 95; issue body already references line 95 ✓
- `decisions.py` module does not exist — feature not implemented ✓
- No `DecisionsConfig` in `config/features.py` ✓
- `scripts/little_loops/sprint.py:142-202` dataclass + YAML pattern confirmed ✓

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T19:45:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6d630f0d-2126-4eb0-8da2-2057ea37658f.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:refine-issue` - 2026-04-07T18:30:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3a30dea-bcb8-4472-8595-836364d4ab19.jsonl`
- `/ll:refine-issue` - 2026-04-04T21:54:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2617058-86bb-4762-8daf-c963cd330fc4.jsonl`
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50b6641-c597-41dc-894f-47b323d241b9.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): Both this issue and FEAT-1112 modify `hooks/scripts/session-start.sh` independently (FEAT-948 adds `ll-decisions sync` output; FEAT-1112 adds event ingestion wiring). Apply FEAT-948's `session-start.sh` changes after FEAT-1112 (and FEAT-1263) have merged, and re-verify the hook's exit-code behavior to ensure FEAT-948's body-output extension is additive and does not conflict with FEAT-1112's ingestion wiring.

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-11): `.ll/decisions.yaml` is a user-edited, human-authored YAML file and must remain as such — it is not a candidate for migration into FEAT-1112's `.ll/session.db`. The two stores serve different purposes: `decisions.yaml` holds standing rules, per-issue decisions, and exceptions authored by a developer; `session.db` holds machine-generated tool-event and session data. FEAT-1112 is a prerequisite only for the query/sync infrastructure (e.g., `ll-decisions sync` writing to `.ll/ll.local.md` may benefit from FTS5 lookups); it does not imply decisions data moves to SQLite. When implementing, treat decisions.yaml as the source of truth and SQLite as a read-only index if used at all.

**Sequencing note** (added by `/ll:audit-issue-conflicts` 2026-05-14): BUG-1461 should resolve before this issue is implemented. Both touch `config-schema.json` and the session-start hook path. BUG-1461 either removes `continuation.auto_detect_on_session_start` from the schema or adds an implementation in `session_start.py`; this issue adds a `decisions` block to the same schema and extends `session-start.sh`. Resolving BUG-1461 first provides a stable schema baseline. Related: BUG-1461.
