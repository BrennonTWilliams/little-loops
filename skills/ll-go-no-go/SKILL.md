---
name: ll-go-no-go
description: Use when asked for an adversarial go/no-go review or whether an issue is worth implementing.
args: "[issue-id[,issue-id...] | sprint-name] [--check] [--auto]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash(find:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(git:*)
  - Agent
  - Edit
  - AskUserQuestion
  - Bash(ll-history-context:*)
metadata:
  short-description: Use when asked for an adversarial go/no-go review or whether an issue is worth i
---

# Go/No-Go

Bridged from `skills/go-no-go/SKILL.md` for Codex Skills API discovery.
See the source skill file for the full prompt body.
