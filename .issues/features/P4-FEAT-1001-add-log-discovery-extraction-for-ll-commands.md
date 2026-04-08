---
id: FEAT-1001
type: FEAT
priority: P4
status: backlog
title: Add log discovery and extraction for ll-loop and ll-commands
discovered_date: 2026-04-08
discovered_by: capture-issue
---

# FEAT-1001: Add log discovery and extraction for ll-loop and ll-commands

## Summary

Identify system-level Claude log locations on this machine, then extract and save logs from running `ll-loop`, `/ll:` skills, and other ll-commands across all projects into a new `logs/` directory for analysis.

## Current Behavior

Claude Code writes session logs to `~/.claude/projects/<encoded-path>/*.jsonl`, but there is no tool or workflow for:
- Discovering which projects on this machine are running any ll- CLI tool
- Extracting ll-relevant entries (loop state transitions, skill invocations, CLI command invocations, results) from raw JSONL
- Aggregating logs from multiple projects into a single location for cross-project analysis

## Expected Behavior

A `logs/` directory (or CLI tool) that:
1. Discovers all Claude project log directories on the machine (`~/.claude/projects/*/`)
2. Filters sessions that contain any ll- CLI invocation (`ll-loop`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-messages`, `ll-history`, `ll-deps`, `ll-sync`, `ll-issues`, `ll-workflows`, `ll-gitignore`, `ll-verify-docs`, `ll-check-links`) or `/ll:` skill activity
3. Extracts relevant entries and writes them to `logs/<project>/<session>.log` (or structured JSONL)
4. Optionally tails active sessions for live ll-loop monitoring

## Motivation

Debugging ll-loop execution, skill failures, and command behavior across projects requires manually hunting through `~/.claude/projects/` JSONL files. A dedicated log extraction workflow would dramatically speed up analysis of FSM state transitions, identify cross-project patterns, and support the `ll-analyze-loop` and `ll-analyze-history` commands with richer source data.

## Use Case

Developer runs `ll-loop outer-loop-eval` on two separate projects. When a loop behaves unexpectedly, they want to quickly pull the relevant log entries from both projects into one place, correlate the FSM transitions, and understand what context was passed at each state.

## Implementation Steps

1. **Discover log directories**: Enumerate `~/.claude/projects/*/` and decode project paths from directory names
2. **Filter ll-relevant sessions**: Scan JSONL for entries referencing any ll- CLI tool (`ll-loop`, `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-messages`, `ll-history`, `ll-deps`, `ll-sync`, `ll-issues`, `ll-workflows`, `ll-gitignore`, `ll-verify-docs`, `ll-check-links`) or `/ll:` skill invocations
3. **Extract and transform**: Pull assistant messages, tool calls, and state transitions; strip noise
4. **Write to `logs/`**: Organize as `logs/<project-slug>/<session-id>.jsonl` with a `logs/index.md` summary
5. **CLI integration**: Expose as `ll-logs` CLI (or subcommand of an existing tool) with `--project`, `--loop`, `--since` filters

## API / Interface

```bash
# New CLI or subcommand
ll-logs discover                  # List all projects with ll activity
ll-logs extract --project <slug>  # Extract logs for one project
ll-logs extract --all             # Extract all projects to logs/
ll-logs tail --loop outer-loop-eval  # Live tail active loop sessions
ll-logs extract --cmd ll-history     # Extract logs for a specific ll- CLI tool
```

Output structure:
```
logs/
  index.md
  little-loops/
    e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl
    ...
  my-other-project/
    ...
```

## Acceptance Criteria

- [ ] `logs/` directory is populated with filtered entries from at least the current project
- [ ] Entries are correctly attributed to the specific ll- CLI tool or loop that produced them
- [ ] Cross-project discovery works for at least 2 projects on the machine
- [ ] `logs/index.md` provides a readable summary of what was extracted and when

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Architecture | ll-loop FSM internals and log structure |
| [docs/reference/API.md](../../docs/reference/API.md) | Architecture | CLI tool API reference |

## Session Log
- `/ll:capture-issue` - 2026-04-08T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e6d40974-cea1-44b9-8a10-0015ac9f66eb.jsonl`

---

## Status

- **Created**: 2026-04-08
- **Updated**: 2026-04-08
