---
id: FEAT-1892
title: "Decisions Log \u2014 CLI Subcommand, Sync, and Skill Bridges"
type: FEAT
priority: P3
parent: FEAT-948
size: Very Large
discovered_date: 2026-06-02
depends_on:
- FEAT-1891
decision_needed: false
confidence_score: 98
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
status: done
---

# FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Summary

Build the `ll-issues decisions` CLI subcommand with full CRUD sub-sub-commands, implement `ll-decisions sync` to surface active rules in `.ll/ll.local.md`, extend `hooks/scripts/session-start.sh` to emit `## Active Rules` at session start, and wire three skills (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to append `decision` entries as a side effect. Depends on FEAT-1891 (core CRUD layer).

## Parent Issue

Decomposed from FEAT-948: Rules and Decisions Log for Issue Compliance

## Integration Map

### Files to Create
- `scripts/little_loops/cli/issues/decisions.py` — `add_decisions_parser(subs)` + `cmd_decisions(config, args)` following `epic_progress.py` dual-function pattern
- `scripts/tests/test_cli_decisions.py` — CLI tests using `patch.object(sys, "argv", ["ll-issues", "decisions", ...])` pattern from `test_issues_cli.py:TestIssuesCLINextId`

### Files to Modify
- `scripts/little_loops/decisions.py` — add `sync_to_local_md(project_root: Path)` function using `append_session_log_entry()` insert-or-create pattern
- `scripts/little_loops/cli/issues/__init__.py` — import `add_decisions_parser`/`cmd_decisions` in lines 21-46 block, call `add_decisions_parser(subs)` after line 674 (`add_epic_progress_parser` call), dispatch `if args.command == "decisions": return cmd_decisions(config, args)` before line 733 fallthrough
- `hooks/scripts/session-start.sh` — extend `merge_local_config()` Python heredoc to extract `parts = content.split("---", 2)` body and emit after frontmatter merge (after line 97)
- `skills/decide-issue/SKILL.md` — add `ll-issues decisions add` bash call after Phase 6 annotation; guard with `[ -f .ll/decisions.yaml ]`
- `commands/tradeoff-review-issues.md` — add `ll-issues decisions add` bash call after final output; guard with `[ -f .ll/decisions.yaml ]`
- `skills/go-no-go/SKILL.md` — add `ll-issues decisions add` bash call after verdict; guard with `[ -f .ll/decisions.yaml ]`
- `skills/capture-issue/SKILL.md` — optional: add `ll-issues decisions add` for notable architectural choices at capture time
- `commands/help.md` — append `decisions` to `ll-issues` subcommand description in CLI TOOLS block
- `docs/reference/CLI.md` — add `#### ll-issues decisions` subsection
- `CONTRIBUTING.md` — add `cli/issues/decisions.py` to `cli/issues/` directory tree listing
- `.claude/CLAUDE.md` — append `decisions` to `ll-issues` subcommand parenthetical on line 177 (currently lists `epic-progress` as last entry); parallel update to `commands/help.md`

_Wiring pass added by `/ll:wire-issue`:_

### Similar Patterns (Key Anchors)
- `scripts/little_loops/cli/issues/epic_progress.py:add_epic_progress_parser()` — externalized parser factory model; the exact template for `decisions` due to sub-sub-command complexity
- `scripts/little_loops/session_log.py:append_session_log_entry()` lines 119-134 — `rfind`/splice section insert-or-create pattern for `sync_to_local_md`
- `scripts/little_loops/hooks/session_start.py:handle()` lines 98-109 — `ll.local.md` read with `split("---", 2)` body extraction
- `scripts/little_loops/cli/issues/anchor_sweep.py:cmd_anchor_sweep()` — error-on-missing-path and `sys.stderr` + `return 1` pattern

### Tests
- `scripts/tests/test_issues_cli.py:TestIssuesCLINextId` and `TestIssuesCLIList` — `patch.object(sys, "argv", [...])` test class structure and fixture usage; use `TestIssuesCLIEpicProgress` (line 4467) as the closest structural match since `epic_progress` uses the same externalized two-function parser pattern
- `scripts/tests/test_decisions.py` — `decisions_path`, `sample_rule`, `sample_decision`, `sample_exception` fixtures available for reuse in `test_cli_decisions.py`; also add a new `TestSyncToLocalMd` class here (following `TestAppendSessionLogEntry` in `test_session_log.py:57` for structure) covering: creates section, replaces existing section, filters advisory rules, excludes superseded rules, uses `atomic_write`
- `scripts/tests/conftest.py` — `temp_project_dir`, `sample_config` fixtures needed by CLI tests

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers of decisions.py CRUD layer)
- `scripts/little_loops/cli/issues/decisions.py` (new) → calls `load_decisions()`, `add_entry()`, `list_entries()`, `resolve_active()`, `set_outcome()` from `decisions.py`
- `sync_to_local_md()` → reads `ll.local.md` via `split("---", 2)` body extraction, writes `## Active Rules` section using `atomic_write`

## Proposed Solution

### Step 4 — CLI Subcommand

Create `scripts/little_loops/cli/issues/decisions.py` with `cmd_decisions(config, args)`.

Follow `scripts/little_loops/cli/issues/next_id.py:11` minimal handler pattern.

Register `decisions` subparser after line 124 in `scripts/little_loops/cli/issues/__init__.py` (where `add_subparsers` is called). Add dispatch in the chain at lines 689-733:
```python
if args.command == "decisions":
    return cmd_decisions(config, args)
```

Supported sub-sub-commands:
- `list [--type=rule|decision|exception] [--category=...] [--label=...] [--no-outcome] [--before=<date>] [--scope=<scope>]`
- `add --type=... --category=... --rule="..." --rationale="..." [--issue=...] [--enforcement=required|advisory] [--rule-ref=...] [--alternatives-rejected="..."] [--supersedes=...]`
- `generate --from=completed` (stub; full implementation in FEAT-1893)
- `sync` (writes `## Active Rules` to `.ll/ll.local.md`)
- `outcome <ID> --result=worked|did_not_work|mixed|reversed [--notes="..."] [--measured-at=<ISO-8601>] [--force]`

### Step 5 — Sync to ll.local.md

Implement `sync_to_local_md(project_root: Path)` in `scripts/little_loops/decisions.py`:
- Read active `required` rules from `.ll/decisions.yaml` via `load_decisions()` + `resolve_active()`
- Write `## Active Rules` section to `.ll/ll.local.md` using markdown section insert-after pattern from `scripts/little_loops/session_log.py:119-132`

Extend `hooks/scripts/session-start.sh` (after line 97) to also output the body of `ll.local.md` so `## Active Rules` surfaces in Claude's context at session start:
- Extract body via `content.split("---", 2)[2]` after the frontmatter parse inside the Python heredoc
- Print body before `sys.exit(0)`

> **Scope boundary note**: Apply after FEAT-1112 and FEAT-1263 have merged; verify the hook's exit-code behavior is additive and does not conflict with FEAT-1112's ingestion wiring.

### Step 6 — Skill-Level Decision Capture Bridges

All three integrations are gated on graceful degradation: if `.ll/decisions.yaml` does not exist and `decisions.enabled` is falsy, the write is silently skipped.

**`skills/decide-issue/SKILL.md`** — after Phase 6 annotation, call:
```bash
ll-issues decisions add --type=decision --issue=$FILE \
  --rule="<chosen option title>" \
  --rationale="<Decision Rationale text>" \
  --alternatives-rejected="<other options + scores>"
```
Guard: `[ -f .ll/decisions.yaml ]` or `decisions.enabled` check.

**`commands/tradeoff-review-issues.md`** — after final output, append `decision` entry:
- `issue` = issue analyzed, `rule` = recommendation text, `rationale` = key tradeoff narrative, `alternatives_rejected` = losing options

**`skills/go-no-go/SKILL.md`** — after verdict, append `decision` entry:
- `issue` = issue evaluated, `rule` = "Go" or "No-Go", `rationale` = blocking or approving criteria met, `enforcement: advisory`

### Step 7 — capture-issue Integration (Optional)

Update `skills/capture-issue/SKILL.md` to optionally log a `decision` entry when the user makes a notable architectural choice at capture time. Gate on `[ -f .ll/decisions.yaml ]`.

### Wiring (included per TDD mode)

- Step 14: Update `commands/help.md` — append `decisions` to the `ll-issues` subcommand description in the CLI TOOLS block
- Step 17: Update `docs/reference/CLI.md` — add `#### ll-issues decisions` subsection documenting `list`, `add`, `generate`, `sync`, and `outcome` sub-sub-commands and their flags
- Step 18: Update `CONTRIBUTING.md` — add `cli/issues/decisions.py` to the `cli/issues/` directory tree listing
- Step 23 (Conditional): If Step 5's body-output logic is extended to the Python `session_start.handle()` beyond the shell script, update `scripts/tests/test_hook_session_start.py:TestSessionStartLocalOverrides` (lines 124–152) to separate body text from JSON stdout before calling `json.loads()`; skip if the Python handler remains unchanged

### Tests

- `scripts/tests/test_cli_decisions.py` — CLI tests using `patch.object(sys, "argv", ["ll-issues", "decisions", ...])` pattern from `scripts/tests/test_issues_cli.py:29`; covers `list`, `add`, `sync`, `outcome` sub-sub-commands; verify graceful degradation when `decisions.yaml` absent

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

19. Add `TestSyncToLocalMd` class to `scripts/tests/test_decisions.py` — new `sync_to_local_md` function has no test plan; follow `TestAppendSessionLogEntry` structure in `scripts/tests/test_session_log.py:57`; cover creates-section, replaces-existing, filters-advisory-rules, excludes-superseded, uses-atomic-write
20. Add `Bash(ll-issues:*)` to `allowed-tools` in `skills/go-no-go/SKILL.md` frontmatter — currently missing; required for the `ll-issues decisions add` call being wired in Step 6; `skills/decide-issue/SKILL.md` already has it as reference
21. Append `decisions` to `ll-issues` subcommand list in `.claude/CLAUDE.md` line 177 — currently ends at `epic-progress`; parallel update alongside `commands/help.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`decisions.py` CRUD layer (FEAT-1891 complete):**
- `load_decisions(path=None) -> list[AnyEntry]` — returns `[]` if file absent; supports bare list or `{"entries": [...]}` YAML format
- `add_entry(entry, path=None) -> None` — loads, appends, saves via `atomic_write`
- `list_entries(path, *, type, category, label)` — keyword-only filters; `--no-outcome`, `--before`, `--scope` flags require additional post-filtering in CLI handler (not in data layer)
- `set_outcome(entry_id, result, measured_at, notes=None, path=None, *, force=False)` — raises `KeyError` (missing ID), `TypeError` (not a `DecisionEntry`), `ValueError` (existing outcome without `--force`); the `outcome` sub-sub-command maps directly to this
- `resolve_active(entries)` — builds superseded ID set via `getattr(e, "supersedes", None)`; `sync` should call `list_entries(type="rule")` then `resolve_active()` to get active required rules

**`__init__.py` registration (3-step):**
1. Import `add_decisions_parser`, `cmd_decisions` in the `with cli_event_context()` block header (lines 21-46), following the `add_epic_progress_parser` import at line 674's surrounding block
2. Call `add_decisions_parser(subs)` after line 674 (`add_epic_progress_parser(subs)`)
3. Add `if args.command == "decisions": return cmd_decisions(config, args)` before the `return 1` fallthrough at line 733

**`epic_progress.py` two-function pattern (exact model):**
- `add_decisions_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser` — registers `decisions` parser and all sub-sub-command parsers; includes `add_config_arg(p)`
- `cmd_decisions(config: BRConfig, args: argparse.Namespace) -> int` — dispatches on `args.subcommand` (second-level arg); returns `0`/`1`

**`sync_to_local_md` implementation pattern (from `session_log.py:119-134`):**
```python
content = ll_local_path.read_text()
rules_block = "\n".join(f"- {r.rule}" for r in active_rules)
section = f"## Active Rules\n\n{rules_block}\n"
if "## Active Rules" in content:
    idx = content.rfind("## Active Rules\n")
    end = content.find("\n##", idx + 1)
    content = content[:idx] + section + (content[end:] if end != -1 else "")
else:
    content += f"\n\n{section}"
atomic_write(ll_local_path, content)
```

**`session-start.sh` body emission (inside `merge_local_config()` Python heredoc, after frontmatter merge):**
```python
# After sys.exit(0) in merge path — add before it:
parts = content.split("---", 2)
body = parts[2].strip() if len(parts) >= 3 else ""
if body:
    print(f"\n{body}", file=sys.stderr)
```
Note: emit to `stderr` to keep `stdout` clean for the JSON config merge output.

**Skill bridge graceful degradation pattern:**
```bash
if [ -f .ll/decisions.yaml ]; then
    ll-issues decisions add --type=decision --issue=$FILE \
      --rule="<chosen option title>" \
      --rationale="<Decision Rationale text>" \
      --alternatives-rejected="<other options + scores>"
fi
```
Alternatively: `ll-issues decisions add ... 2>/dev/null || true` (matches `2>/dev/null || true` pattern from `capture-issue` and `go-no-go` skills).

**Test fixture reuse (`test_cli_decisions.py`):**
```python
# Reuse from test_decisions.py
from scripts.tests.test_decisions import decisions_path, sample_rule, sample_decision

# Per-test argv pattern from test_issues_cli.py
with patch.object(sys, "argv", ["ll-issues", "decisions", "add",
    "--type", "rule", "--rule", "test rule", "--rationale", "reason",
    "--config", str(temp_project_dir)]):
    from little_loops.cli import main_issues
    result = main_issues()
assert result == 0
```

## Acceptance Criteria

- [ ] `cmd_decisions(config, args)` created at `scripts/little_loops/cli/issues/decisions.py`
- [ ] `decisions` subparser registered after line 124 in `cli/issues/__init__.py`
- [ ] Dispatch entry added to `main_issues()` chain (lines 689-733)
- [ ] `list` supports `--type`, `--category`, `--label`, `--no-outcome`, `--before`, `--scope` flags
- [ ] `add` supports all relevant flags for all three entry types
- [ ] `outcome <ID>` subcommand populates outcome; refuses overwrite without `--force`
- [ ] `sync` writes active `required` rules to `## Active Rules` in `.ll/ll.local.md`
- [ ] `hooks/scripts/session-start.sh` emits `## Active Rules` body content at session start
- [ ] `/ll:decide-issue` appends `decision` entry after option selection; silently skipped if `decisions.yaml` absent
- [ ] `/ll:tradeoff-review-issues` appends `decision` entry after analysis; silently skipped if absent
- [ ] `/ll:go-no-go` appends `decision` entry after verdict; silently skipped if absent
- [ ] `commands/help.md` documents `decisions` under `ll-issues`
- [ ] `docs/reference/CLI.md` has `#### ll-issues decisions` subsection
- [ ] `CONTRIBUTING.md` lists `cli/issues/decisions.py`
- [ ] `test_cli_decisions.py` covers CRUD ops and graceful degradation

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-03_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **13-file breadth is the primary complexity driver** — each individual site is low-risk and well-templated, but coordinating all 13 changes in one pass increases the chance of missing a wiring step; the enumerated acceptance criteria checklist mitigates this, but a deliberate pass through each checkbox on completion is advised.
- **`session-start.sh` heredoc modification affects every session start** — the body-extraction addition is documented with a code snippet and an explicit stderr-vs-stdout placement note, but the heredoc context is less testable than pure Python; Step 23's conditional test update provides a validation path if the Python handler is also extended.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-03
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-1894: Decisions Log — CLI Subcommand
- FEAT-1895: Decisions Log — Sync to ll.local.md and Session-Start Integration
- FEAT-1896: Decisions Log — Skill Bridges

## Session Log
- `/ll:wire-issue` - 2026-06-03T05:36:22 - `81d10f03-6ba5-41c1-9aaa-43ce0f85e0a9.jsonl`
- `/ll:refine-issue` - 2026-06-03T05:30:59 - `2e67a1df-fef7-4f3b-bb9f-adbc3396ea8e.jsonl`
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `6ce3dc94-d3af-4cb3-9e1d-55f458a093ad.jsonl`
- `/ll:issue-size-review` - 2026-06-03T00:00:00Z - `3b396e18-8717-4088-9842-5574f1659959.jsonl`
