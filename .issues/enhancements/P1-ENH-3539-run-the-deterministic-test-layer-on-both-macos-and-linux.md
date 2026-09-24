---
id: 3539
title: Run the deterministic test layer on both macOS and Linux
type: ENH
priority: P1
status: open
discovered_date: '2026-09-23'
labels: []
---

# Run the deterministic test layer on both macOS and Linux

## Summary

The `ll-verify-*` family and the shipped bash hooks depend on `grep`, `date`,
`sort`, and `stat` — every one of which diverges between BSD and GNU. Users run
both platforms. A single-runner suite is structurally incapable of catching
this class of failure.

The concrete trap: the Claude Code harness aliases `grep` to `ugrep`, so a
GNU-only pattern in a hook passes on a macOS development machine, and bare BSD
grep on a user's machine treats the same pattern as a literal and silently
matches nothing. No error, no exit code — the hook just stops finding anything.

Add a second runner to the deterministic (free, gating) test layer. The change
is small; the class it closes fails silently on user machines and cannot fail
on ours.

Distinct from multi-host divergence at the model/prompt layer (divergence runs
for prompt-shaped changes) and host artifact parity — this is OS-level
divergence inside the deterministic tooling itself.

## Scope

1. Add a macOS runner alongside the Linux runner for the deterministic,
   gating tier of the test suite (the free, non-LLM layer — unit tests,
   wiring checks, doc-verification gates), so every PR gates on both.
2. Audit the deterministic tooling for BSD/GNU-divergent invocations of
   `grep`, `date`, `sort`, and `stat` in hooks and test helpers; fix each
   divergence or normalize the invocation.
3. Treat the `grep` → `ugrep` aliasing as a named hazard: patterns in shipped
   hooks and gates must be portable to bare BSD grep (or the invocation must
   pin a concrete grep), because the development machine's alias masks the
   divergence.

## Background

Harness-governance research into CI practice records the same design under
the name "Cross-OS Layer 0": a base test layer deliberately run on both
`macos-latest` and `ubuntu-latest`, with exactly this rationale — BSD/GNU
divergence in `grep`/`date`/`sort`/`stat` is *masked* on a macOS dev machine
by the harness's grep aliasing, and "a single-runner suite cannot catch this
class". little-loops ships bash and Python across both platforms and inherits
the same aliasing.

## Acceptance Criteria

- [ ] The deterministic, gating test tier runs on both macOS and Linux
      runners and gates merges on both.
- [ ] No shipped hook or deterministic gate depends on GNU-only behavior of
      `grep`, `date`, `sort`, or `stat` (each divergence found by the audit
      is fixed or explicitly normalized).
- [ ] A documented convention for portable pattern usage (or a pinned grep
      implementation) so new hooks do not reintroduce the class.
