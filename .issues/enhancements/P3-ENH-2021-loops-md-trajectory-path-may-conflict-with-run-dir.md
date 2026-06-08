---
id: ENH-2021
title: "loops.md trajectory artifact path may conflict with runner-injected run_dir"
status: open
priority: P3
type: ENH
created: 2026-06-08
---

## Problem

`docs/reference/loops.md` documents `harness-optimize` trajectory artifacts being written to `.ll/runs/harness-optimize/<run-id>/...`. However, `CLAUDE.md`'s MR-3 rule states that loops must write intermediate artifacts to `${context.run_dir}/`, which the runner injects as `.loops/runs/<loop>-<timestamp>/`.

The documented path (`.ll/runs/`) conflicts with the runner-injected path (`.loops/runs/`). This is either:
1. A stale doc path that was never updated after the `run_dir` mechanism was introduced, or
2. The loop itself violating MR-3 (writing to a shared path instead of `run_dir`)

## Investigation Needed

Read the actual `loops/harness-optimize.yaml` to check which path the loop writes to in practice. If it uses `${run_dir}`, update `loops.md` to reflect `.loops/runs/harness-optimize-<timestamp>/`. If it hard-codes `.ll/runs/`, fix the loop YAML to use `${run_dir}` and update the docs.

## Location

- Doc file: `docs/reference/loops.md` — `harness-optimize` State Graph section
- Loop file: `loops/harness-optimize.yaml`

## Source

Discovered during `/ll:audit-docs docs/reference` on 2026-06-08.
