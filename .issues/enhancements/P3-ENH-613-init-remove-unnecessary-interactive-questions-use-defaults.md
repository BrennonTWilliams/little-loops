---
id: ENH-598
type: ENH
priority: P3
status: active
discovered_date: 2026-03-05
discovered_by: capture-issue
---

# ENH-598: Remove Unnecessary Interactive Questions from /ll:init and Use Defaults

## Summary

Refactor `/ll:init` to silently set sensible defaults for configuration options that don't require user input at init time. Users can still customize via `/ll:configure` or by editing `.claude/ll-config.json` directly.

## Motivation

The current `/ll:init` wizard asks too many questions, many of which have obvious "recommended" defaults and don't benefit from interactive prompting. This creates unnecessary friction during setup. Reducing the question count speeds up initialization and improves UX.

## Scope

Remove the following `AskUserQuestion` prompts from the init skill, instead setting the values silently to their defaults:

| Removed Question | Default to Set |
|---|---|
| Which automation tools do you want to configure? | Always enable: Sprint management, FSM loops, Sequential automation (ll-auto) |
| Found existing `.issues/` directory. Use it? | Always use existing `.issues/` without asking |
| Minimum outcome confidence score (outcome_confidence)? | Use existing default |
| What directory name for completed issues? | Use existing default |
| How many parallel workers for sprint waves? | **2** (currently defaults to 4 — fix this) |
| What timeout should ll-parallel use per issue? | Use existing default |
| At what context % should auto-handoff trigger? | **80%** |
| Add priority labels (P0-P5) when syncing GitHub? | **Yes** |
| Sync completed issues to GitHub (close them)? | **No** |
| Minimum readiness score (confidence_score)? | **85** |
| Configure additional advanced settings? | Skip (no advanced rounds) |

All values must still be written to `.claude/ll-config.json` on init — they just should not be prompted for.

## Scope Boundaries

- **In scope**: Removing the 11 listed `AskUserQuestion` prompts from `skills/init/SKILL.md`; silently setting correct defaults inline; fixing `parallel_workers` default from 4 → 2; auto-using existing `.issues/` directory without prompting
- **Out of scope**: Changing `/ll:configure` behavior (separate skill); adding new config options not already in the schema; changing the init completion/summary message (tracked in ENH-459)

## Implementation Steps

1. **Read `skills/init/interactive.md`** (primary file) — all 11 targeted `AskUserQuestion` calls are here, not in `SKILL.md`
2. **Remove Round 3b automation-tools question** (`interactive.md:225–239`): delete the `AskUserQuestion` block; always enable `sprints`, `loops`, and `automation` sections unconditionally (add inline comment: `# Always enable automation tools — configurable via /ll:configure`)
3. **Remove existing-`.issues/` prompt from Round 2** (`interactive.md:157–174`): replace with silent detection — if `EXISTING_ISSUES_DIR` is set, use it without asking; if not, use `.issues` default
4. **Remove the 9 Round 5 questions** at their respective line ranges (see Integration Map table above): replace each `AskUserQuestion` block with a single-line silent assignment using the listed default value and an inline `# Default: <value>` comment
5. **Fix `sprints.default_max_workers` default**: change the value at `interactive.md:560–572` from "4" to "2"; also update the omit-threshold annotation at `interactive.md:704` from "not 4" to "not 2"; update `SKILL.md:168` summary display rule similarly
6. **Remove Round 7 gate** (`interactive.md:797–806`): delete the `AskUserQuestion` block; hard-code "Skip" path so Rounds 8–10 are never reached (they remain accessible via `/ll:configure`)
7. **Verify omit-if-default rules** at `interactive.md:692–706` still match the new defaults — update any that referenced the old "4" threshold for sprint workers
8. **Verify** the generated `.claude/ll-config.json` still includes all affected keys with correct values (no template changes needed — templates do not declare these fields)

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — **primary change location** (not `SKILL.md`); all `AskUserQuestion` calls for the listed questions live here
- `skills/init/SKILL.md` — secondary; verify summary display rules at line 168 still match after sprint workers default changes

### Dependent Files (Callers/Importers)
- `config-schema.json` — all silently-set keys already exist with correct defaults; no changes expected (confirmed by research)
- `templates/*.json` — **no changes needed** (research confirmed none of the 9 project-type templates contain `parallel`, `sprints`, `commands.confidence_gate`, `context_monitor`, `sync`, or `issues.completed_dir` fields)

### Similar Patterns
- `skills/configure/SKILL.md` — uses `AskUserQuestion` for config changes; reference for consistent option naming
- `skills/format-issue/SKILL.md:54-75` — shows `--all implies --auto` silent-default pattern
- `skills/confidence-check/SKILL.md:41-66, 403-408` — shows automation-context auto-enable and "use defaults for all decisions" patterns

### Tests
- N/A — no test files exist for the init skill (it's a markdown/prompt file, not a Python module)

### Documentation
- `docs/ARCHITECTURE.md` — references `interactive.md` in directory tree at line 128; update if it describes the interactive wizard question flow
- `CONTRIBUTING.md` — verify if it describes init as interactive
- `docs/reference/CONFIGURATION.md` — documents the affected fields; no changes expected but validate

### Configuration
- `.claude/ll-config.json` — output artifact of init; ensure all removed-question keys still appear with correct defaults after the change

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Exact Locations of All 11 Targeted Questions in `interactive.md`

| Question (ENH-598 table) | File | Line Range | Variable Set | Default |
|---|---|---|---|---|
| Which automation tools to configure? (Round 3b) | `interactive.md` | 225–239 | `sprints`, `loops`, `automation` sections | None (multi-select, no pre-selection) |
| Found existing `.issues/`. Use it? (Round 2) | `interactive.md` | 157–174 | `issues.base_dir` | "Yes, use [dir]/" |
| outcome_confidence minimum (Round 5b, q10) | `interactive.md` | 548–558 | `commands.confidence_gate.outcome_threshold` | "70 (Recommended)" |
| Completed issues directory name (Round 5a, q2) | `interactive.md` | 449–459 | `issues.completed_dir` | "completed (Recommended)" |
| Sprint parallel workers (Round 5b, q11) | `interactive.md` | 560–572 | `sprints.default_max_workers` | "4 (Recommended)" → change to 2 |
| ll-parallel timeout per issue (Round 5a, q5) | `interactive.md` | 485–495 | `parallel.timeout_per_issue` | "3600 (Recommended)" |
| Context % for auto-handoff (Round 5a, q6) | `interactive.md` | 497–507 | `context_monitor.auto_handoff_threshold` | "80%" |
| Add priority labels for GitHub (Round 5a, q7) | `interactive.md` | 509–518 | `sync.github.priority_labels` | "Yes (Recommended)" |
| Sync completed issues to GitHub (Round 5b, q8) | `interactive.md` | 526–534 | `sync.github.sync_completed` | "No (Recommended)" |
| Minimum readiness score (Round 5b, q9) | `interactive.md` | 536–546 | `commands.confidence_gate.readiness_threshold` | "85 (Recommended)" |
| Configure additional advanced settings? (Round 7) | `interactive.md` | 797–806 | Gates Rounds 8–10 | "Skip (Recommended)" |

#### `parallel_workers` Default Clarification

The issue states "currently defaults to 4 — fix this" but this applies specifically to `sprints.default_max_workers`, not `parallel.max_workers`:
- `parallel.max_workers` (ll-parallel): already defaults to **2** at `config-schema.json:170-172` ✓
- `sprints.default_max_workers`: schema default is **4** at `config-schema.json:579-585` — this is the value to change to 2 (will diverge from schema's declared default)

The `interactive.md:704` annotation already notes: "Only include `sprints.default_max_workers` if user selected a non-default value (not 4)". After the fix, this omit-threshold should be updated to "not 2".

#### Round 7 Implication

Removing the "Configure additional advanced settings?" gate (`interactive.md:797–806`) silently hard-codes "Skip (Recommended)", meaning Rounds 8–10 (`interactive.md:817-990`) are never reached. These cover test directory, build command, continuation behavior, and prompt optimization — all have sensible schema defaults and are accessible via `/ll:configure`.

## Acceptance Criteria

- [ ] Running `/ll:init` on a new project no longer asks any of the listed questions
- [ ] All removed questions still result in correct values written to `.claude/ll-config.json`
- [ ] `parallel_workers` defaults to `2`, not `4`
- [ ] If `.issues/` exists, it is used automatically without prompting
- [ ] Automation tools (sprint, loops, ll-auto) are always enabled without prompting
- [ ] Users can still override any value via `/ll:configure` or direct config edits

## Impact

- **Priority**: P3 — UX improvement; reduces init friction but no core functionality is blocked
- **Effort**: Small — finding and removing `AskUserQuestion` calls in a markdown skill file; some conditional branching logic may need untangling
- **Risk**: Low-Medium — template files confirmed to contain none of the affected fields; schema defaults confirmed correct for all fields except `sprints.default_max_workers` (intentional divergence from schema's `4`). Scope is confined to `interactive.md` with minor `SKILL.md` summary-display rule update.
- **Breaking Change**: No — users can override any silently-set value via `/ll:configure` or direct config edits

## Related

- Completed: ENH-101 (init-wizard-advanced-setup-rounds)
- Completed: ENH-451 (add-sprints-loops-automation-to-init-wizard)
- Active: ENH-459 (mention-ll-local-md-in-init-completion)

## Labels

`enhancement`, `ux`, `init`, `automation`

## Verification Notes

- **2026-03-05** — VALID. `skills/init/interactive.md` and `skills/init/SKILL.md` both exist. All 11 targeted `AskUserQuestion` calls still present; `sprints.default_max_workers` still defaults to 4; no changes to this behavior in current HEAD.

## Session Log
- `/ll:capture-issue` - 2026-03-05T00:00:00Z - captured from user description
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72d6d2c3-8058-4ace-9531-afaf02c4d8af.jsonl`
- `/ll:refine-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5ab8beb-daac-4b0a-bbba-56295f1d683b.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`

---

**Open** | Created: 2026-03-05 | Priority: P3
