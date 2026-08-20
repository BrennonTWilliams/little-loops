---
name: ll-review-sprint
description: |
  AI-guided sprint health check that analyzes a sprint's current state and suggests improvements - removing stale issues, adding related backlog issues, and identifying dependency or contention problems. Pairs with `ll-sprint edit` (mechanics) the way `/ll:create-sprint` pairs with `ll-sprint create` (intelligence).

  Trigger keywords: "review sprint", "sprint health", "sprint review", "check sprint", "sprint suggestions", "optimize sprint", "sprint health check", "is my sprint still good"
argument-hint: "[sprint-name]"
allowed-tools:
  - Read
  - Glob
  - Bash(ll-sprint:*)
  - Bash(ll-issues:*)
  - Bash(ll-deps:*)
disable-model-invocation: true
metadata:
  short-description: AI-guided sprint health check that analyzes a sprint's current state and...
---

# Review Sprint

Bridged from `commands/review-sprint.md` for Codex Skills API discovery.
See the source command file for the full prompt body.
