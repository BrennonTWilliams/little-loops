---
name: ll-ready-issue
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready or close if invalid
args: "ISSUE_ID"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - Bash(git:*)
  - Bash(ll-history-context:*)
disable-model-invocation: true
metadata:
  short-description: Analyze and validate an issue file for accuracy, utility, and completeness, then
---

# Ready Issue

Bridged from `commands/ready-issue.md` for Codex Skills API discovery.
See the source command file for the full prompt body.

- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.
