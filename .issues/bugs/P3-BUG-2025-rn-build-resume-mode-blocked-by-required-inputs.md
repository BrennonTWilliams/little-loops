---
id: BUG-2025
title: "rn-build resume mode blocked by required_inputs: [spec] pre-flight check"
status: done
priority: P3
type: BUG
captured_at: "2026-06-08T20:04:20Z"
discovered_date: "2026-06-08"
discovered_by: capture-issue
---

# BUG-2025: rn-build resume mode blocked by required_inputs: [spec] pre-flight check

## Summary

`ll-loop run rn-build --context resume_epic=EPIC-NNN` fails immediately with a
"spec context variable is required" error. The resume guard in the `init` shell
action never executes because the FSM runner enforces `required_inputs: [spec]`
before the FSM starts.

## Root Cause

`scripts/little_loops/loops/rn-build.yaml` declared:

```yaml
input_key: spec
required_inputs:
  - spec
```

The `required_inputs` list is validated by the runner as a pre-flight check —
before any FSM state executes. Resume mode relies on the `init` shell action to
detect a non-empty `resume_epic` context variable and short-circuit spec
validation, but that logic is never reached when `spec` is absent.

The `init` action already performs the spec validation itself (and emits a clear
error message), so `required_inputs` was a redundant and conflicting gate.

## Fix

Removed `required_inputs: [spec]` from `rn-build.yaml`. The `init` state remains
the sole gatekeeper for spec validation in normal mode, and resume mode can now
bypass it cleanly via the `RESUME_MODE:` output-contains evaluator.

## Verification

Resume invocation now works without a dummy spec:

```bash
ll-loop run rn-build \
  --context resume_epic=EPIC-NNN \
  --context resume_harness=<harness-name>
```

## Status

---


## Session Log
- `hook:posttooluse-status-done` - 2026-06-08T20:04:39 - `b7685d55-97ff-431b-a791-943e19ce5e78.jsonl`
