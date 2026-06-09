---
id: ENH-1717
title: Auto-commit hooks on Issue file CRUD operations
type: ENH
priority: P3
status: done
size: Very Large
captured_at: '2026-05-26T02:15:56Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
labels: []
decision_needed: false
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
implementation_order_risk: true
---

# ENH-1717: Auto-commit hooks on Issue file CRUD operations

## Summary

Add opt-in auto-commit behavior triggered whenever an issue file is created, updated, or deleted (CRUD operations). Controlled by a feature flag in `.ll/ll-config.json` so teams that prefer manual commits can leave it off.

## Motivation

Currently, capturing or modifying issues requires a separate `/ll:commit` step. In solo or low-friction workflows, forgetting to commit leaves issue changes uncommitted and invisible to CI, `ll-sprint`, or remote sync. Auto-committing on CRUD makes the issue tracker more "append-only feeling" — every issue write lands in git history immediately without a manual step.

## Proposed Solution

### Option A: PostToolUse Shell Hook (Recommended)

> **Selected:** Option A: PostToolUse Shell Hook — centralizes git commit logic in one hook script, reusing existing `lib/common.sh` utilities and `issue-completion-log.sh` as a structural template (reuse score 3/3).

Add `hooks/scripts/issue-auto-commit.sh`, registered in `hooks/hooks.json` under `PostToolUse` with `"matcher": "Write"` (and `"Edit"` for updates). The script:

1. Reads `FILE_PATH` from stdin JSON — exits if not inside `issues.base_dir` or not an issue filename
2. Calls `ll_feature_enabled "issues.auto_commit"` via `hooks/scripts/lib/common.sh` — exits 0 if disabled
3. Reads `auto_commit_prefix` from config (default `"chore(issues)"`)
4. Runs `git add "$FILE_PATH"` (idempotent if the skill already staged it)
5. Checks `git status --porcelain` — if any line does NOT match the issue file, prints a warning and exits 0 (skip commit)
6. Derives commit message from operation (Write=`capture`/`update`, Edit=`update`) and issue ID extracted from filename
7. Runs `git commit -m "<prefix>: <verb> <ISSUE-ID> <slug>"`

**Advantages**: centralized; zero skill changes; fires for all CRUD skills automatically; consistent with `issue-completion-log.sh` pattern.

**Timing note**: Claude Code PostToolUse fires after the tool executes but before the skill continues. `capture-issue` runs `git add` as a subsequent Bash call — the hook fires between the `Write` and the skill's `git add`. The hook's own `git add` makes the skill's subsequent `git add` a no-op, which is harmless.

### Option B: In-Skill Logic

Add auto-commit logic directly to each CRUD skill (`skills/capture-issue/SKILL.md`, `commands/ready-issue.md`, and others) after the `git add` step. Each skill checks `issues.auto_commit` and conditionally runs `git commit`.

**Disadvantages**: scatters commit logic across many files; any new CRUD skill must remember to include it; harder to maintain consistently.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-01.

**Selected**: Option A: PostToolUse Shell Hook

**Reasoning**: The codebase already has two PostToolUse Write hooks (`issue-completion-log.sh`, `check-duplicate-issue-id-post.sh`) implementing the identical control flow — stdin JSON parsing, `ll_resolve_config`, `ISSUES_BASE_DIR` scoping, filename-pattern guard — making `issue-auto-commit.sh` a near-copy with reuse score 3/3. Option B would scatter commit logic across 14+ skill files with no shared abstraction mechanism, contradicting the uniform convention of delegating commits to `/ll:commit` and introducing a maintenance burden that grows with every new CRUD skill.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: PostToolUse Shell Hook | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B: In-Skill Logic | 1/3 | 0/3 | 1/3 | 0/3 | 2/12 |

**Key evidence**:
- **Option A**: Two existing PostToolUse Write hooks (`issue-completion-log.sh` at `hooks/hooks.json` lines 66–76, `check-duplicate-issue-id-post.sh` at lines 77–87) share the identical stdin-parse → config-resolve → path-scope → filename-guard control flow; `TestIssueCompletionLog` in `test_hooks_integration.py` line 1030 is a direct template for `TestIssueAutoCommitHook`. Only gap: no existing hook runs git operations within the 5s PostToolUse timeout (mitigated by git add + status + commit typically completing in <1s).
- **Option B**: 14–15 CRUD skill files with 20+ `git add` blocks all delegate commits to `/ll:commit` (dominant pattern); no shared commit-helper exists in skill Markdown space; duplicating config-check + commit-guard across every file has zero abstraction support.

## Implementation Steps

1. **Add feature flag to config schema** — add `issues.auto_commit` (bool, default `false`) to `config-schema.json` and document it in `.ll/ll-config.json` template.
2. **Hook point in capture-issue / CRUD paths** — after the `git add` step in `capture-issue`, `ready-issue`, and any other skill that mutates issue files, check the flag and run `git commit -m "chore(issues): <auto-generated message>"` if enabled.
3. **Auto-generate commit message** — derive a concise message from the operation type and issue ID (e.g., `chore(issues): capture ENH-1717 auto-commit-hooks`).
4. **PostToolUse hook alternative** — evaluate whether a PostToolUse hook on `Write`/`Edit` targeting `.issues/**` paths is a cleaner integration point than in-skill logic, to avoid scattering commit calls across every skill.
5. **Guard: only when working tree is clean except the issue file** — avoid auto-committing when there are other staged/unstaged changes that should be batched separately.
6. **Docs** — add `auto_commit` to config reference and `CONTRIBUTING.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (Config schema)**: `config-schema.json` has `"issues": { "additionalProperties": false, "properties": { ... } }` — add `"auto_commit": { "type": "boolean", "default": false }` and `"auto_commit_prefix": { "type": "string", "default": "chore(issues)" }` inside `issues.properties`. Update `IssuesConfig` in `scripts/little_loops/config/features.py` — follow the `LearningTestsConfig.from_dict()` pattern at line 385; the existing `IssuesConfig` dataclass in `features.py` must receive `auto_commit: bool = False` and `auto_commit_prefix: str = "chore(issues)"` fields plus matching `from_dict()` keys. `BRConfig` in `scripts/little_loops/config/core.py` already exposes `issues` as a property — no change needed there.
- **Step 2 (Hook registration)**: Add a new entry to `hooks/hooks.json` `PostToolUse` array with `"matcher": "Write"`. Follow the `issue-completion-log.sh` entry shape exactly (type, command, timeout, statusMessage).
- **Step 3 (Hook script)**: Create `hooks/scripts/issue-auto-commit.sh`. Use `hooks/scripts/issue-completion-log.sh` as the template for stdin parsing, `ll_resolve_config`, path scoping (`ISSUES_BASE_DIR` from config), filename-pattern guard (`^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}`), and exit codes. For commit message format follow `issue_lifecycle.py:_commit_issue_completion()` at line 311: `verb(TYPE): ISSUE-ID slug`.
- **Step 4 (Evaluation)**: PostToolUse hook approach (Option A above) wins — avoids scattering logic across skills. `capture-issue` SKILL.md does NOT need modification; its subsequent `git add` after Write becomes a no-op when the hook pre-stages the file.
- **Step 5 (Guard)**: Use `git status --porcelain` then filter output to lines NOT matching the issue file path. Pattern in `git_operations.py:check_git_status()` at line 161 shows the `git diff --cached --quiet` idiom; adapt in bash with `git status --porcelain | grep -v "^[AM]  <escaped-path>" | grep -c .` — if count > 0, skip and warn.
- **Step 6 (Doctor)**: Extend `scripts/little_loops/cli/doctor.py` — add a `_print_issues_section(issues_cfg)` function following the `_print_capture_section()` pattern at line 23; call it from `main_doctor()` after `_print_capture_section()` at line 128. Report `auto_commit` as enabled/disabled using `_STATUS_SYMBOLS["full"]` / `_STATUS_SYMBOLS["unsupported"]`.
- **Tests to add**: `scripts/tests/test_config_schema.py` (new fields validated), `scripts/tests/test_config.py` (`IssuesConfig` parses new fields), `scripts/tests/test_hook_post_tool_use.py` (follows `TestFileEventsWrite` class pattern), `scripts/tests/test_cli_doctor.py` (auto_commit shown in output).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/config/core.py` — extend `BRConfig.to_dict()` to include `auto_commit` and `auto_commit_prefix` in the `issues` sub-dict so template variable resolution (`{{config.issues.auto_commit}}`) works correctly
8. Update `skills/configure/areas.md` — (a) add `issue-auto-commit.sh` row to the hardcoded PostToolUse hooks table in `## Area: hooks`; (b) expose `auto_commit` and `auto_commit_prefix` in the `## Area: issues` Current Values display block
9. Update `docs/ARCHITECTURE.md` — add subsection documenting `issue-auto-commit.sh` hook alongside `issue-completion-log.sh`; correct existing matcher label (`Bash` → `Write`)
10. Add `TestIssueAutoCommitHook` class to `scripts/tests/test_hooks_integration.py` for bash script behavioral tests

## API / Interface

```jsonc
// .ll/ll-config.json
{
  "issues": {
    "auto_commit": false,          // opt-in; default off
    "auto_commit_prefix": "chore(issues)"  // optional commit message prefix
  }
}
```

## Acceptance Criteria

- [ ] `auto_commit: false` (default) — no behavior change from today.
- [ ] `auto_commit: true` — after each issue file CRUD, a git commit is created automatically with a message derived from the operation.
- [ ] Guard fires if working tree has other unstaged changes — auto-commit is skipped and a warning is printed.
- [ ] Config flag is validated by `config-schema.json`.
- [ ] `ll-doctor` reports the flag's current value.

## Related

- `/ll:commit` skill (manual commit path)
- `capture-issue` skill (primary CRUD entry point)
- `hooks/hooks.json` PostToolUse hook system

## Integration Map

### Files to Modify
- `config-schema.json` — add `auto_commit` and `auto_commit_prefix` under `issues.properties`; `additionalProperties: false` is already set so schema must be updated or new keys are ignored at runtime
- `scripts/little_loops/config/features.py` — add `auto_commit: bool = False` and `auto_commit_prefix: str = "chore(issues)"` to `IssuesConfig` dataclass and `IssuesConfig.from_dict()`
- `hooks/hooks.json` — add new `PostToolUse` entry with `"matcher": "Write"` pointing to new script
- `hooks/scripts/issue-auto-commit.sh` — new script (create); follow `issue-completion-log.sh` exactly for stdin parsing and path scoping
- `scripts/little_loops/cli/doctor.py` — add `_print_issues_section()` function and call it from `main_doctor()` at line 128
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict` currently serializes only `base_dir`, `categories`, `completed_dir`, `deferred_dir`, `priorities`, `templates_dir`, and `capture_template` under `issues`; must add `auto_commit` and `auto_commit_prefix` or template variable resolution (via `resolve_variable`) will silently return `None` for `{{config.issues.auto_commit}}` [Wiring pass]
- `skills/configure/areas.md` — two locations: (1) `## Area: hooks` section contains a hardcoded PostToolUse table (rows for `context-monitor.sh`, `issue-completion-log.sh`, `check-duplicate-issue-id-post.sh`) that becomes stale when `issue-auto-commit.sh` is added; (2) `## Area: issues` Current Values display block uses `{{config.issues.base_dir}}` etc. but won't show `auto_commit` or `auto_commit_prefix` — users running `/ll:configure issues` won't see the new flags [Wiring pass]

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — runs `git add` after Write; hook fires first (hook's git add makes the skill's subsequent git add a harmless no-op when auto_commit=true)
- `commands/ready-issue.md` — uses Edit on issue files; hook fires after each Edit, but guard prevents commit if other changes are staged
- `skills/manage-issue/SKILL.md` — may Edit issue files during status updates; auto-covered by hook [Wiring pass]
- `skills/format-issue/SKILL.md` — uses Edit on issue files for template restructuring; auto-covered by hook [Wiring pass]
- `skills/wire-issue/SKILL.md` — uses Edit on issue files for integration map updates; auto-covered by hook [Wiring pass]
- `skills/refine-issue/SKILL.md` — uses Edit on issue files for research additions; auto-covered by hook [Wiring pass]
- `skills/link-epics/SKILL.md` — uses Write/Edit on issue files for epic relationship linking; auto-covered by hook [Wiring pass]

### Similar Patterns
- `hooks/scripts/issue-completion-log.sh` — full path-scoping and filename-pattern guard pattern to follow
- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()` at line 311 — commit message format and `git add`/`git commit` subprocess pattern
- `scripts/little_loops/git_operations.py` — `check_git_status()` at line 161 — working-tree guard pattern
- `scripts/little_loops/config/features.py` — `LearningTestsConfig.from_dict()` at line 385 — boolean flag config pattern

### Tests
- `scripts/tests/test_config_schema.py` — add `test_issues_auto_commit_in_schema` asserting `auto_commit` (boolean, default false) and `auto_commit_prefix` (string) are present under `issues.properties`; follow `test_issues_next_issue_in_schema` pattern
- `scripts/tests/test_config.py` — update `TestIssuesConfig.test_from_dict_with_defaults` and `test_from_dict_with_all_fields` to include `auto_commit` and `auto_commit_prefix`; add new test with explicit values
- `scripts/tests/test_hook_post_tool_use.py` — add `TestIssueAutoCommitPostToolUse` class following `TestFileEventsWrite` pattern; gate-off test patches subprocess commit and asserts 0 calls when `issues.auto_commit: false`
- `scripts/tests/test_cli_doctor.py` — add test in `TestMainDoctor` setting `mock_config.issues.auto_commit = True/False` and asserting `auto_commit` label appears in output; follow `test_analytics_capture_section_all_enabled` pattern with `_capture_print()` + `_make_runner()` helpers
- `scripts/tests/test_hooks_integration.py` — add `TestIssueAutoCommitHook` class for bash script behavioral tests; follow `TestIssueCompletionLog` pattern (subprocess.run with JSON stdin + tmp_path git repo); cover: non-issue file exit 0, `auto_commit` disabled exits 0 without git, enabled runs `git add` + `git commit`, custom `auto_commit_prefix` in commit message [Wiring pass]

### Documentation
- `docs/reference/CONFIGURATION.md` — document `issues.auto_commit` (bool, default false) and `issues.auto_commit_prefix` (string); update both the `### \`issues\`` table and the "Full Configuration Example" block (around line 25) which shows a representative `"issues": { ... }` JSON snippet
- `CONTRIBUTING.md` — mention auto_commit in workflow section
- `docs/ARCHITECTURE.md` — add new subsection (parallel to existing `### Session Log Auto-Linking`) documenting `issue-auto-commit.sh` as a PostToolUse hook on `Write` events; correct existing `issue-completion-log.sh` entry which incorrectly states matcher `Bash` (it actually uses `Write`) [Wiring pass]

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-01_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Broad auto-trigger surface** — 7 dependent skills/commands fire the hook on every Write/Edit to `.issues/`; a bug in the bash guard silently affects all CRUD workflows. Implement tests first: write `TestIssueAutoCommitHook` in `test_hooks_integration.py` validating non-issue file exit, disabled-flag exit, and guard-against-other-staged-changes before enabling the hook live.
- **Working-tree guard bash logic** — the `git status --porcelain | grep -v` path-escape pattern is the highest-risk site; test edge cases: issue paths with spaces, already-staged files from a prior command, and concurrent hook invocations.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-01
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-1843: Auto-commit config layer: auto_commit and auto_commit_prefix feature flags
- ENH-1844: Auto-commit hook script (issue-auto-commit.sh) and PostToolUse registration
- ENH-1845: Auto-commit doctor UI, configure areas display, and documentation

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `e4837d03-e4ce-4492-b86b-4f74c879e76b.jsonl`
- `/ll:decide-issue` - 2026-06-01T08:02:59 - `c4629f4c-0850-443f-846b-0e92b36a9504.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `4344aff9-0824-4016-a232-00c716ad88cf.jsonl`
- `/ll:wire-issue` - 2026-06-01T07:53:34 - `c98dca55-eae5-4922-a76d-f5738e5366d9.jsonl`
- `/ll:refine-issue` - 2026-06-01T07:47:42 - `fd90d199-24ff-478f-80a5-4ac233159309.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:15 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:15:56Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
