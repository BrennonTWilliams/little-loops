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

> **Graceful degradation constraint**: All integrations with `commands/ready-issue.md`,
> `commands/verify-issues.md`, and `skills/format-issue/SKILL.md` MUST gracefully skip
> decisions checks when `.ll/decisions.yaml` does not exist. The governance feature is
> opt-in — absence of the file is not an error condition. Projects that have not called
> `ll-issues decisions init` must not experience broken validation commands.

**CLI surface**: `ll-issues decisions` subcommand for CRUD.

**Auto-generation triggers**: post-`manage-issue` completion hook and pre-implementation confidence check.

## Integration Map

### Files to Modify

**New files (create):**
- `scripts/little_loops/decisions.py` — core CRUD module (load/save/add/list/generate/sync); follow `scripts/little_loops/sprint.py:142-202` dataclass + YAML pattern
- `scripts/little_loops/cli/issues/decisions.py` — CLI subcommand handler for `ll-issues decisions`; follow `scripts/little_loops/cli/issues/next_id.py:11` pattern

**Modify existing:**
- `scripts/little_loops/cli/issues/__init__.py:84` — add `decisions` subparser after `subs = parser.add_subparsers(dest="command", ...)` at line 84; add dispatch `if args.command == "decisions": return cmd_decisions(config, args)` before `return 1` at line 433; same pattern as all other subcommands in this file
- `scripts/little_loops/config/features.py` — add `DecisionsConfig` dataclass with `enabled: bool`, `log_path: str = ".ll/decisions.yaml"`, `auto_generate: list[str]` fields; follow `IssuesConfig` at line 59
- `scripts/little_loops/config/core.py:95` — add `self._decisions = DecisionsConfig.from_dict(...)` to `_parse_config()` and expose as `@property def decisions()`
- `hooks/scripts/session-start.sh:76-83` — extend to output the body (non-frontmatter) of `ll.local.md` when it contains an `## Active Rules` section, so compliance rules surface in Claude's context at session start; currently the Python heredoc (`merge_local_config()`) only outputs JSON from frontmatter and discards the body (`sys.exit(0)` at line 83); fix is inside the Python heredoc: extract body via `content.split("---", 2)[2]` after the frontmatter parse, then print it before `sys.exit(0)`
- `commands/ready-issue.md` — add decisions log query step to suppress violations where a matching `exception` entry with `rule_ref` exists (currently at Section 2, lines 139-183)
- `commands/verify-issues.md` — add query step to surface rule violations and suppress false positives via `exception` entries (current violation categories at lines 67-80)
- `skills/format-issue/SKILL.md` — add decisions log query step; Proposed Solution explicitly lists format-issue alongside ready-issue and verify-issues as a log reader
- `config-schema.json` — add `decisions` object schema (`enabled`, `log_path`, `auto_generate`) matching `DecisionsConfig` fields

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
4. **CLI subcommand** — create `scripts/little_loops/cli/issues/decisions.py` with `cmd_decisions(config, args)`; register `decisions` subparser in `scripts/little_loops/cli/issues/__init__.py:80` following existing subcommand pattern; supports `list`, `add`, `generate`, `sync` sub-sub-commands
5. **Sync to ll.local.md** — implement `sync_to_local_md(project_root)` in `scripts/little_loops/decisions.py`; writes `## Active Rules` section; extend `hooks/scripts/session-start.sh` (after line 97) to also output the body of `ll.local.md` so `## Active Rules` surfaces in Claude's context at session start
6. **capture-issue integration** — update `skills/capture-issue/SKILL.md` to optionally log a `decision` entry when the user makes a notable architectural choice
7. **Auto-generation from completed issues** — add `generate_from_completed(config)` to `decisions.py` using `scan_completed_issues()` from `scripts/little_loops/issue_history/parsing.py:263`; the hook system has no per-command event (only `PostToolUse`/`Bash` and `Stop`) so auto-triggering from manage-issue requires detecting manage-issue invocation in the `issue-completion-log.sh` hook OR exposing this as a manual `ll-issues decisions generate --from=completed` command
8. **Validation integration** — update `commands/ready-issue.md` and `commands/verify-issues.md` to query decisions log: check active `required` rules, surface violations, suppress false positives where `exception` entry with matching `rule_ref` exists; also update `skills/format-issue/SKILL.md` (listed in Proposed Solution alongside these two)
9. **Tests** — write `scripts/tests/test_decisions.py` (CRUD, exception suppression, supersedes resolution) and `scripts/tests/test_cli_decisions.py` (CLI via `patch.object(sys, "argv")`); use `temp_project_dir` fixture from `conftest.py:56`
10. **Docs** — update `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md` Key Directories and CLI Tools sections

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

## Verification Notes

**Verdict**: NEEDS_UPDATE — One stale line reference found:

- `scripts/little_loops/cli/issues/__init__.py`: `add_subparsers(dest="command")` is at line **89** (not 84 as stated). The "add `decisions` subparser after `subs = parser.add_subparsers(...)` at line 84" instruction should reference line 89.
- `decisions.py` module does not exist — feature not implemented ✓
- No `DecisionsConfig` in `config/features.py` ✓
- `config/core.py:95` (`_parse_config`) confirmed at line 95 ✓
- `scripts/little_loops/sprint.py:142-202` dataclass + YAML pattern confirmed ✓

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:refine-issue` - 2026-04-07T18:30:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3a30dea-bcb8-4472-8595-836364d4ab19.jsonl`
- `/ll:refine-issue` - 2026-04-04T21:54:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2617058-86bb-4762-8daf-c963cd330fc4.jsonl`
- `/ll:capture-issue` - 2026-04-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d50b6641-c597-41dc-894f-47b323d241b9.jsonl`
