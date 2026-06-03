---
id: FEAT-1892
title: "Decisions Log — CLI Subcommand, Sync, and Skill Bridges"
type: FEAT
priority: P3
parent: FEAT-948
size: Large
discovered_date: 2026-06-02
depends_on: [FEAT-1891]
---

# FEAT-1892: Decisions Log — CLI Subcommand, Sync, and Skill Bridges

## Summary

Build the `ll-issues decisions` CLI subcommand with full CRUD sub-sub-commands, implement `ll-decisions sync` to surface active rules in `.ll/ll.local.md`, extend `hooks/scripts/session-start.sh` to emit `## Active Rules` at session start, and wire three skills (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to append `decision` entries as a side effect. Depends on FEAT-1891 (core CRUD layer).

## Parent Issue

Decomposed from FEAT-948: Rules and Decisions Log for Issue Compliance

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

## Session Log
- `/ll:issue-size-review` - 2026-06-02T00:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
