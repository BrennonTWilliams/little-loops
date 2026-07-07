---
id: ENH-2534
type: ENH
priority: P4
status: open
captured_at: '2026-07-07T21:00:00Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
decision_needed: false
labels:
- loops
- hardening
---

# ENH-2534: rn-implement — check_blocked_by should emit UNRESOLVED/PARSE_ERROR tokens

## Summary

The upfront `check_blocked_by` state in
`scripts/little_loops/loops/rn-implement.yaml` still fails open *silently*
(`sys.exit(0)` with no output) when the issue file cannot be resolved or its
frontmatter cannot be parsed. The post-remediation recheck (~line 797) was
already hardened to print `UNRESOLVED` / `PARSE_ERROR`; mirror that in the
upfront gate.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposal 4). No defect was observed
in that run, but the fail-open path means a renamed/unresolvable issue file
silently proceeds past the blocked_by gate as READY. Benign today because the
readiness gate catches most issues, but a distinct defect class if a parked
issue's only constraint is `blocked_by`.

## Current Behavior

In `check_blocked_by` (~line 410):

```python
if not issue_path:
    sys.exit(0)  # unresolved -> fail-open (let downstream handle)
...
except Exception:
    sys.exit(0)  # parse error -> fail-open
```

No token is printed, so events/logs carry no trace that the gate was skipped
rather than passed.

## Expected Behavior

Fail-open behavior is preserved (processing is never blocked on a gate error),
but the skip is observable: print `UNRESOLVED` / `PARSE_ERROR` before exiting,
matching the recheck state, and optionally append a diagnostic line to a
run_dir sidecar (e.g. `blocked_by_gate_skips.txt`) so audits can distinguish
"no unmet deps" from "gate could not evaluate".

## Proposed Solution

- Add the two `print(...)` calls mirroring the recheck state.
- If routing on the token is desired later, add an `output_contains` route to
  a distinct diagnostic emit; not required for this issue — observability only.

## Impact

- **Severity**: Low (latent observability gap, no known defect)
- **Effort**: Trivial
- **Risk**: Low
