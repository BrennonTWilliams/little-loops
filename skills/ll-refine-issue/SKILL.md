---
name: ll-refine-issue
description: Refine issue files with codebase-driven research to fill knowledge gaps needed for implementation
argument-hint: "ISSUE_ID [--auto] [--dry-run] [--gap-analysis] [--full-rewrite]"
allowed-tools:
  - Read
  - Glob
  - Edit(.issues/**)
  - Task
  - Bash(git:*, ll-issues:*)
  - Bash(ll-history-context:*)
  - Bash(ll-code:*)
disable-model-invocation: true
metadata:
  short-description: Refine issue files with codebase-driven research to fill knowledge gaps...
---

# Refine Issue

Bridged from `commands/refine-issue.md` for Codex Skills API discovery.
See the source command file for the full prompt body.
