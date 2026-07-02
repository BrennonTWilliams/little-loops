---
id: ENH-2444
title: Constrain `diverge` state in brainstorm loop via per-state `tools:` allowlist
  (not prompt-level instruction); fix latent `tools=[]` semantics in host_runner;
  add end-to-end test for state-level tool allowlist
type: ENH
status: done
priority: P3
captured_at: '2026-07-02T20:17:01Z'
discovered_date: '2026-07-02'
discovered_by: manual
labels:
- enhancement
- loops
- fsm
- host-runner
- brainstorm
- tool-allowlist
completed_at: '2026-07-02T20:17:01Z'
---

# ENH-2444: Per-state `tools:` allowlist for `brainstorm` ideation states

## Summary

`websearch-failure-findings.md` documents a brainstorm-loop failure where the
LLM in the `diverge` state chose to do 10–15 parallel `site:github.com`
WebSearches, which tripped the US-only search backend's rate limits. The
findings doc recommends editing the `diverge` prompt to forbid WebSearch
("Option 1") — but that fix is *soft*: it asks the LLM politely to avoid
WebSearch while still leaving the tool available. The strongest fix is
*hard*: add a per-state `tools:` allowlist to the YAML so the host CLI
refuses WebSearch / WebFetch at the tool layer.

The infrastructure for that fix is **already wired and dormant**:

- `fsm/schema.py:624` reads `tools:` from each state
- `fsm/executor.py:1280` passes `state.tools` to `build_streaming` for
  prompt-mode actions
- `host_runner.py:256` translates it to `--tools` on the `claude` CLI for
  `ClaudeCodeRunner` (capability `tool_allowlist=True` at line 228)
- `host_runner.py:482-490` gracefully degrades to `CapabilityNotSupported`
  for `CodexRunner` (host-portable)
- `test_host_runner.py:145` / `:320` / `:509` / `:818` test the runner
  side end-to-end

`grep '^\s*tools:' scripts/little_loops/loops/*.yaml` returns **nothing** —
no built-in loop currently uses the field. The capability is built,
tested, and unused.

This issue closes that gap on the brainstorm loop, fixes a latent
`tools=[]` semantics bug in `host_runner.py`, and adds a test that
catches future regressions in the wiring.

## Current Behavior

The `diverge` state in `brainstorm.yaml:98-122` instructs the LLM to
"Generate exactly N distinct ideas through this lens" with no guidance
on whether to use WebSearch / WebFetch. The state has no `tools:`
allowlist, so the LLM receives the full default tool set including
`WebSearch` and `WebFetch`. The findings document
(`websearch-failure-findings.md`) records a 2026-07-02 run where the
LLM, on a `MiniMax-M3[1m]` model, chose to issue 10–15 parallel
`site:github.com` WebSearches across 5 facets, which tripped the
US-only search backend's rate limits. The LLM self-recovered by
switching to WebFetch with known URLs.

The findings doc misreads the root cause as "non-Claude model +
US-only backend" and recommends Option 1 (a prompt instruction
forbidding WebSearch). The actual cause is the loop YAML *omitting*
the per-state `tools:` allowlist that the FSM schema already supports.
The Claude runs on 2026-06-27 didn't hit the same wall only because
`claude-sonnet-4-6` happened to generate ideas inline from training
data — the LLM still had `WebSearch` available, it just didn't reach
for it. Any model/host combination where the LLM chooses a
`site:`-operator fan-out pattern would have hit the same wall.

A latent bug in `host_runner.py:255` compounds the omission: the
`if tools:` truthy check silently treats `tools=[]` as "no override"
rather than "deny all", so a future loop author who writes
`tools: []` expecting restriction would silently get the unfiltered
default set.

## Expected Behavior

1. **`brainstorm.yaml` ideation states declare `tools:` allowlists**
   that explicitly enumerate which tools the LLM may use, with
   `WebSearch` and `WebFetch` excluded. The host CLI rejects any tool
   not in the list — WebSearch is *unavailable*, not just "discouraged".
2. **`host_runner.py:255` honors `tools=[]`** as a real "deny all"
   restriction (changed to `if tools is not None:`), matching the
   `CodexRunner` precedent at line 481.
3. **An end-to-end test** confirms a state's `tools:` propagates
   through the FSM executor to the host CLI argv, so the dormant
   wiring can no longer silently regress.

## What Changed

### 1. `scripts/little_loops/loops/brainstorm.yaml` — per-state `tools:` on ideation states

The `diverge`, `frame`, `cluster`, `rank`, `converge`, and `done` states
of `brainstorm.yaml` now declare a `tools:` allowlist. WebSearch /
WebFetch are excluded from all of them; the ideation pipeline is offline
by default:

| State        | Allowed tools                          | Why                                              |
|--------------|----------------------------------------|--------------------------------------------------|
| `diverge`    | `Read`                                 | Read prior state output if needed; no web        |
| `frame`      | `Read`, `Write`                        | Writes `lenses.txt`; no web                      |
| `cluster`    | `Read`                                 | Reads `ideas.jsonl`; no web                      |
| `rank`       | `Read`                                 | Reads `clusters.md`, `ideas.jsonl`; no web       |
| `converge`   | `Read`                                 | Reads `ranked.md`, `clusters.md`; no web         |
| `done`       | `Read`                                 | Reads `brainstorm.md`; no web                    |

The state-level YAML is the source of truth; the prompt is *not* asked
to police tool use (LLM-self-policing is the failure mode we're
removing).

### 2. `scripts/little_loops/host_runner.py` — fix `tools=[]` semantics

`host_runner.py:255` uses `if tools:` (truthy check) which silently
treats `tools=[]` as "no override" and the LLM keeps the default tool
set. A future loop author who writes `tools: []` expecting "deny all"
would silently get the unfiltered set — a footgun. Tightened to
`if tools is not None:` so an empty list is honored as a real
restriction. `CodexRunner.build_streaming` already does this correctly
(line 481).

### 3. End-to-end test for state-level tool propagation

`scripts/tests/test_fsm_executor.py` (or a new
`test_fsm_state_tools.py`) — assert that when a state declares
`tools: ["Read"]`, the resulting `build_streaming` invocation carries
`--tools Read` on its argv for ClaudeCodeRunner and a
`CapabilityNotSupported` warning for CodexRunner. This closes the test
gap that allowed the dormant wiring to ship without a single loop
author using it.

## Why this beats Option 1 (prompt instruction)

|                          | Option 1 (prompt)                  | Per-state `tools:` allowlist              |
|--------------------------|------------------------------------|-------------------------------------------|
| Mechanism                | Soft: "please don't call WebSearch"| Hard: WebSearch is not in the tool set    |
| Failure under non-Claude | LLM may still call WebSearch       | WebSearch is rejected at the host CLI     |
| Token cost per diverge   | +~40 tokens                        | +0 tokens                                 |
| Discoverable             | Hidden in prompt prose             | YAML field, surfaceable in loop inspection|
| Future-proofing          | One loop                           | Pattern other ideation loops can adopt    |

## Verification

After landing the change:

```bash
# 1. The fix holds at the FSM level — state.tools is wired into argv.
python -m pytest scripts/tests/test_fsm_executor.py -k tools -v

# 2. The runtime fix holds — empty list is honored, not silently dropped.
python -m pytest scripts/tests/test_host_runner.py -k "empty or none" -v

# 3. End-to-end: brainstorm runs without any WebSearch tool calls.
ll-loop run brainstorm "a brief that would previously have triggered web research"
grep WebSearch .loops/runs/<ts>/events.jsonl    # expect: no matches
```

`ll-loop validate brainstorm` should pass without warnings (the
`tools:` field is in the schema, not a new key).

## Impact

- **Priority**: P3 — small change (one loop YAML, one host_runner line,
  one test file), no critical-path automation depends on it.
- **Effort**: ~30 minutes. `brainstorm.yaml` adds 6 `tools:` fields;
  `host_runner.py:255` is a one-line truthy check fix; the test is
  straightforward and mirrors the existing `test_host_runner.py`
  patterns.
- **Risk**: Low. The `tools:` field is already schema-validated;
  `CodexRunner` already has a graceful-degrade path; the empty-list
  fix is a behavior tightening (no false negative — only an empty
  list was previously treated as a no-op). `ll-loop validate
  brainstorm` should remain green.
- **Breaking Change**: No for callers who don't pass `tools:` (the
  default path is unchanged). Effectively a tightening for callers
  who *do* pass `tools: []`: previously a silent no-op, now a real
  restriction. Documented in the changelog as a behavior change.

## Scope Boundaries

**In scope:**

- Adding `tools:` allowlists to the ideation states of `brainstorm.yaml`
  (`frame`, `diverge`, `cluster`, `rank`, `converge`, `done`).
- Tightening `host_runner.py:255` from `if tools:` to
  `if tools is not None:`.
- Adding an end-to-end test that asserts `state.tools` propagates
  through the executor into the host CLI argv.

**Out of scope (deliberate):**

- **The 8 research-intent loops** (`apply-research`, `deep-research`,
  `deep-research-arxiv`, `rn-plan`, `rn-build`, `rn-implement`,
  `rn-refine`, `harness-plan-research-implement-report`, `loop-router`)
  are intentionally web-researching; the fix does not apply to them.
  The "ideation loops should be offline by default" rule is a
  follow-on doc addition for `docs/guides/` once we have ≥2
  examples, not in this issue.
- **A formal `context.allow_research` flag** (the findings doc's
  Option 2) is a sensible future addition, but it's additive: callers
  who want deterministic offline ideation can already pass
  `tools: []` once the executor honors it. Worth picking up only
  if users ask.
- **Other ideation-adjacent loops** that don't currently exist as
  web-researching — opportunistic `grep -l` sweeps for WebSearch
  calls in other loops can be a follow-on audit issue, but no
  other loop currently has the failure mode.

## Status

- **Action**: improve
- **Completed**: 2026-07-02
- **Status**: Completed (manual implementation, interactive session)
- **Implementation**: Per-state `tools:` allowlists on `brainstorm`
  ideation states, `tools=[]` semantics fix in `host_runner.py`, and
  end-to-end test for state-level tool propagation. The
  `websearch-failure-findings.md` session finding is fully addressed.

## References

- `websearch-failure-findings.md` — session finding (this work's prompt)
- `scripts/little_loops/loops/brainstorm.yaml:98-122` — `diverge` state
  (target of the per-state `tools:` change)
- `scripts/little_loops/fsm/schema.py:624` — `tools` field on the FSM
  state dataclass
- `scripts/little_loops/fsm/executor.py:1280` — executor wires
  `state.tools` into `build_streaming` for prompt actions
- `scripts/little_loops/host_runner.py:255-256` — ClaudeCodeRunner
  translates `tools` to `--tools`
- `scripts/little_loops/host_runner.py:481-490` — CodexRunner
  graceful-degrade path with `CapabilityNotSupported`
- `scripts/tests/test_host_runner.py:145`, `:320`, `:509`, `:818` —
  existing per-runner tool allowlist tests (the gap is the
  end-to-end FSM→host wiring test)


## Session Log
- `hook:posttooluse-status-done` - 2026-07-02T20:17:43 - `773160a7-0ea3-45c5-a981-ffcec9b6e154.jsonl`
