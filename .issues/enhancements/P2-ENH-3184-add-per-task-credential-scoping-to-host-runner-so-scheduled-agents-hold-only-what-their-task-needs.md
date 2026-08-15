---
id: 3184
title: Add per-task credential scoping to host_runner so scheduled agents hold only what their task needs
type: ENH
priority: P2
status: open
discovered_date: '2026-08-15'
labels: []
---

## Summary

`host_runner` passes broad credentials today. `--cwd` isolates the working directory, but the token scope is coarse: a scheduled agent doing a docs sweep holds the same authority as one opening pull requests.

Add per-task credential scoping. A runner spec declares which secrets and capabilities the task actually needs, and `host_runner` projects that into a scoped token at invocation time — the operational pattern of a fine-grained PAT scoped to one repository with read+write on Issues and nothing else.

## Motivation

Per-task scoping is a distinct axis from `--cwd`'s per-repo working directory, on the same runner. It matters for three reasons: a narrower scope is easier to audit; an over-broad scope hides failure modes until the run that exploits it; and an unattended agent holding write authority it never needed is the kind of exposure that is cheap to prevent and expensive to explain.

This becomes load-bearing wherever a scheduled agent touches a system whose credentials cannot be casually over-granted.

## Acceptance Criteria

- A runner spec can declare the capability set a task requires.
- `host_runner` projects that declaration into a scoped credential at invocation; an undeclared capability is unavailable at runtime, not merely discouraged.
- A task requesting a capability outside its declaration fails loudly, naming the capability.
- The declared scope is recorded with the run, so an audit can answer what authority a given run actually held.
- Existing runner specs without a declaration keep working, with the coarse behaviour and a deprecation path.
