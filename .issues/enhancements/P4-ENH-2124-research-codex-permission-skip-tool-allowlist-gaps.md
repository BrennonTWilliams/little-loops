---
id: ENH-2124
title: Research and track Codex permission-skip and tool-allowlist capability gaps
type: ENH
priority: P4
status: deferred
captured_at: "2026-06-13T00:00:00Z"
discovered_date: 2026-06-13
discovered_by: capture-issue
parent: EPIC-1463
relates_to: [ENH-1529, ENH-2121, FEAT-1462, FEAT-2122]
labels: [codex, host-runner, sandbox, host-compat, research]
---

# ENH-2124: Research and track Codex permission-skip and tool-allowlist capability gaps

## Summary

The `Permission skip` and `Tool allowlist` rows of the Runner Capabilities
matrix mark Codex `✗`, but those cells were never backed by a tracking issue or
a research finding — they were asserted, not verified. This issue produces the
research note and either wires the capability or marks each a documented
permanent gap with evidence.

## Motivation

"100% feature parity" cannot be claimed for cells whose ✗ is unverified. Both
capabilities plausibly have Codex-native equivalents that ll is simply not
mapping:

- **Permission skip** — `CodexRunner` already passes
  `--dangerously-bypass-approvals-and-sandbox` (and ENH-1529 exposes
  `sandbox_mode`). Codex's approval-policy / `sandbox_mode` axis may *be* the
  permission-skip mechanism, in which case the cell is mismarked and should be
  ✓ or `partial`.
- **Tool allowlist** — Codex subagents accept `mcp_servers` and `skills.config`
  scoping (see ENH-2121). Per-agent tool scoping may satisfy the
  allowlist capability at the subagent layer even if there is no root-session
  flag.

## Current Behavior

`CodexRunner.describe_capabilities()` (`host_runner.py:590, 607`) already returns
`"full"` for `permission_skip` and `"partial"` for `tool_allowlist`. The capability
values are wired; what is missing is the rationale and the doc update:

- `HOST_COMPATIBILITY.md` still shows `✗[^runnercap]` for both Codex cells — the
  matrix has not been updated to match the code.
- `thoughts/research/codex-runner-capability-gaps.md` does not exist — no written
  rationale explains why `"full"` / `"partial"` is correct.
- The `[^runnercap]` footnote still says "unresearched" — it should be replaced with
  evidence citations once the research note exists.

## Expected Behavior

Each cell is either flipped to ✓/`partial` with the wiring that justifies it,
or kept ✗/N/A with a documented permanent-gap rationale and the evidence link.

## Acceptance Criteria

- Research note at `thoughts/research/codex-runner-capability-gaps.md` covering:
  - Whether Codex's approval-policy / `sandbox_mode` constitutes
    "permission skip" parity (relate to ENH-1529).
  - Whether `mcp_servers` / `skills.config` scoping constitutes "tool
    allowlist" parity (relate to ENH-2121).
- For each capability: a decision (wire / partial / permanent-gap) with
  rationale.
- `describe_capabilities()` and the `[^runnercap]` footnote updated to match
  the decision; if wired, `ll-doctor` reflects the new status and tests cover
  the capability probe.
- No `✗` cell in the Runner Capabilities Codex column lacks either a ✓ path or
  a documented permanent-gap footnote.

## Success Metrics

- Research note exists at `thoughts/research/codex-runner-capability-gaps.md` with a documented decision (wire / partial / permanent-gap) for each capability
- No `✗` cell in the Runner Capabilities Codex column lacks either a ✓ path or a permanent-gap footnote with evidence
- `describe_capabilities()` and `ll-doctor` output are consistent with the documented decisions in `HOST_COMPATIBILITY.md`

## Scope Boundaries

- **In scope**: Permission-skip and tool-allowlist capability rows for the Codex runner; updating `HOST_COMPATIBILITY.md` matrix, `describe_capabilities()`, and the `[^runnercap]` footnote; adding capability-probe tests if wiring is confirmed
- **Out of scope**: Other `✗` Codex capability cells beyond these two rows; implementation of ENH-1529 (sandbox_mode) or ENH-2121 (rich subagent fields) — sequence after both if their findings inform the answer

## Implementation Steps

1. Review current `describe_capabilities()` in `scripts/little_loops/host_runner.py` and the `[^runnercap]` footnote in `docs/reference/HOST_COMPATIBILITY.md` to confirm exact gap assertions
2. Research whether Codex's approval-policy / `sandbox_mode` axis satisfies "permission skip" — relate to ENH-1529; document result (wire / partial / permanent-gap)
3. Research whether Codex `mcp_servers` / `skills.config` scoping satisfies "tool allowlist" — relate to ENH-2121; document result
4. Write research note at `thoughts/research/codex-runner-capability-gaps.md` with evidence and decision for each capability
5. Update `describe_capabilities()`, the `[^runnercap]` footnote, and `HOST_COMPATIBILITY.md` matrix cells per findings; if wired, add capability-probe test(s) so `ll-doctor` reflects the new status

## API/Interface

Conditional — `describe_capabilities()` return dict may include updated values for `permission_skip` and/or `tool_allowlist` keys if wiring is confirmed; no new public methods planned. N/A if both are marked permanent gaps.

## Notes

- This is deliberately a research-first issue: the deliverable may be "these
  are genuine permanent gaps" — that is a valid, parity-completing outcome as
  long as it is documented with evidence rather than asserted.
- Overlaps ENH-2121 (tool scoping) and ENH-1529 (sandbox); sequence after both
  if their findings inform the answer.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `scripts/little_loops/host_runner.py` | `CodexRunner` capability reporting |
| `docs/reference/HOST_COMPATIBILITY.md` | `[^runnercap]` footnote points here |
| ENH-1529 | `sandbox_mode` exposure (permission-skip relation) |
| ENH-2121 | Rich subagent fields incl. `mcp_servers`/`skills.config` |


## Verification Notes
_Updated by `/ll:verify-issues` (2026-06-27):_ Current Behavior section corrected — `describe_capabilities()` already returns `"full"` / `"partial"` at `host_runner.py:590, 607`; the remaining work is the research rationale (`thoughts/research/codex-runner-capability-gaps.md`) and `HOST_COMPATIBILITY.md` doc update, not the code wiring. Prior notes from 2026-06-17 and 2026-06-19 calling for a body update have been addressed.

## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - EPIC-1463 tail cleanup: status -> deferred per decision SCOPE-042 in .ll/decisions.yaml (epic 23/30 done; value delivered).
- `/ll:verify-issues` - 2026-06-27T19:22:20 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-27T19:13:21 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-25T21:39:25 - `91915c5b-d793-486c-a140-be4dd3d8ca1f.jsonl`
- `/ll:verify-issues` - 2026-06-20T00:34:45 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:format-issue` - 2026-06-13T23:48:24 - `eef54360-d096-4a8c-a9e2-75102a87ce0d.jsonl`
