---
name: ll-reconcile-issue
description: Rewrite an issue's Implementation Steps, Acceptance Criteria, and Files to Modify in place from its own accumulated research findings, without appending or bulldozing human prose
args: "ISSUE_ID"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Edit
  - Bash(ll-issues:*)
  - Bash(git:*)
disable-model-invocation: true
metadata:
  short-description: Reconcile an issue's directive sections against its own research findings
---

# Reconcile Issue

Bridged from `commands/reconcile-issue.md` for Codex Skills API discovery.
See the source command file for the full prompt body.

- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.
