---
name: ll-reconcile-issue
description: Rewrite an issue's Implementation Steps, Acceptance Criteria, and Integration Map (Files to Modify, Dependent Files, Similar Patterns, Tests, Documentation) in place from its own accumulated research findings — plus, conditionally, a Scope Boundaries claim contradicted by those findings — without appending or bulldozing human prose (with `--from-verify-evidence`, also decision-derived Program Design directives and Impact Effort/Risk lines named by DIRECTIVE_DRIFT evidence)
argument-hint: "ISSUE_ID [--check] [--from-verify-evidence]"
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
