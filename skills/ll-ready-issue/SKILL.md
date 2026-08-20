---
name: ll-ready-issue
description: Analyze and validate an issue file for accuracy, utility, and completeness, then auto-correct to make implementation-ready or close if invalid
argument-hint: "ISSUE_ID"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Task
  - Bash(git:*)
  - Bash(ll-history-context:*)
disable-model-invocation: true
metadata:
  short-description: Analyze and validate an issue file for accuracy, utility, and completeness,...
---

# Ready Issue

Bridged from `commands/ready-issue.md` for Codex Skills API discovery.
See the source command file for the full prompt body.
