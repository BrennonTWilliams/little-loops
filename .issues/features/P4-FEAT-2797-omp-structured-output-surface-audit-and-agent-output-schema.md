---
id: FEAT-2797
title: omp structured-output surface — audit findings, matrix correction, and agent `output:` schema wiring
type: feature
status: open
priority: P4
discovered_date: 2026-07-25
discovered_by: capture-issue
parent: EPIC-2258
relates_to:
- FEAT-2787
- FEAT-2261
verify_verdict: NON_VALID
labels:
- host-compat
- omp
- structured-output
- docs
- adapters
---

# FEAT-2797: omp structured-output surface — audit findings, matrix correction, and agent `output:` schema wiring

## Summary

`HOST_COMPATIBILITY.md` reports `✗[^omp]` for `json_schema` and (by dataclass
default) `False` for `structured_output` on omp. Those cells were never
researched — `thoughts/research/omp-headless-flags.md`, the FEAT-1850 audit
artifact the whole omp flag surface was derived from, contains **zero**
mentions of schema or structured output, and `OmpRunner.capabilities`
(`host_runner.py:1197-1201`) sets only four flags, letting
`structured_output` fall through to the `HostCapabilities` default
(`host_runner.py:106`).

An upstream docs audit (2026-07-25, below) found the **cells are correct at
the CLI level** but for a reason the footnote never states, and that omp has
a real structured-output mechanism ll is not using — one that directly
affects FEAT-2787's `emit_agent`.

## Audit findings (2026-07-25)

Verified against `can1357/oh-my-pi@main` via the GitHub contents API.

**1. No CLI-level schema flag exists.** `packages/coding-agent/src/cli/args.ts`
(420 lines — the complete flag surface) defines
`export type Mode = "text" | "json" | "rpc" | "acp" | "rpc-ui"` (line 18) and
has no schema/response-format flag of any kind. So:

- `json_schema: ✗` — **correct**, no flag to pass.
- `structured_output: False` — **correct**, since that flag narrowly means
  "honors the inline `--json-schema` the FSM evaluators append" (ENH-2627).
  Only the Anthropic `claude` CLI does.

**2. omp does have structured output, off the CLI path.** Two mechanisms:

- **Task-agent frontmatter `output:`** — a per-agent output schema, passed
  through as opaque schema data (`docs/task-agent-discovery.md:37`). Runtime
  precedence (ibid. 133-139): task item's explicit `outputSchema` → agent
  frontmatter `output` → parent session `outputSchema`. A per-item
  `schemaMode` overrides the session mode; default `permissive`.
- **SDK / RPC** — `createAgentSession({outputSchema, requireYieldTool})`
  (`docs/sdk.md:286`), and `--mode rpc`'s JSON-RPC protocol with a defined
  response schema (`docs/rpc.md:199-207`). Provider-side schema
  normalization is a first-class subsystem (`docs/ai-schema-normalize.md`,
  `@oh-my-pi/pi-ai/utils/schema`) with per-provider strict-mode adapters.

This is a file/tool-mediated path analogous to Codex's `--output-schema`, and
like Codex's, the FSM evaluators do not use it. It is **not** reachable by
adding a flag to `OmpRunner.build_blocking_json`.

**3. Cross-harness agent dirs are deliberately skipped.** `discoverAgents()`
merges OMP-native + Claude *plugin* roots, but explicitly skips
`.claude/agents`, `.codex/agents`, and `.gemini/agents` — their frontmatter
"is not the OMP task-agent contract"; `TASK_AGENT_CONFIG_SOURCE = ".omp"`
filters both dir lists (`docs/task-agent-discovery.md:60`).

## Current Behavior

The matrix asserts `json_schema: ✗` and `structured_output: False` for omp
with no supporting research, and the `[^omp]` footnote is silent on both.
A reader — human or automation reconciling the epic — concludes omp cannot do
structured output at all. `OmpRunner` inherits the `False` by default rather
than declaring it. FEAT-2787's `emit_agent` has no guidance on omp's agent
frontmatter contract and would plausibly emit Claude-shaped agents into a
directory omp deliberately ignores.

## Expected Behavior

The two cells stay `✗` but become *audited* claims with a stated reason, the
research artifact carries the structured-output findings, `OmpRunner` declares
the flag explicitly, and FEAT-2787 emits `.omp/agents/` files that populate
`output:` where a schema exists.

## Use Case

A maintainer closing EPIC-2258 needs the omp column to mean what it says. Two
of its cells currently encode an unexamined dataclass default as a researched
finding — the same class of error the epic's "no unknown cells" acceptance
criterion exists to prevent. Separately, whoever implements FEAT-2787 needs
omp's agent-frontmatter contract up front; discovering `.omp/`-only agent
discovery after writing the emitter means rewriting it.

## Acceptance Criteria

- `HOST_COMPATIBILITY.md`'s `[^omp]` footnote states *why* `json_schema` /
  `structured_output` are `✗` (no CLI flag exists; `--mode` is
  `text|json|rpc|acp|rpc-ui`) and records the agent-frontmatter `output:` /
  SDK `outputSchema` path as a real-but-unused capability, so the cells stop
  reading as "omp can't do structured output."
- `thoughts/research/omp-headless-flags.md` gains a "Structured output"
  section carrying these findings, so the next reader of the audit artifact
  isn't left with the same silent gap.
- `OmpRunner.capabilities` passes `structured_output=False` **explicitly**
  with a comment citing the absent flag, rather than inheriting the default —
  the value is unchanged; the point is that it becomes an audited claim.
- FEAT-2787's `emit_agent` writes to `.omp/agents/` (not a reused
  `.claude/agents` path) and populates frontmatter `output:` where the ll
  agent definition has a schema to express.
- A decision is recorded on whether to pursue the RPC/`outputSchema` path for
  FSM evaluators under omp, or to stay on prompt-and-parse with the BUG-2626
  `<StructuredOutput>` tag fallback. Recording "no, prompt-and-parse" with a
  rationale satisfies this.

## Impact

- **Priority**: P4 — same tier as the parent epic.
- **Effort**: Small for the doc/capability corrections; the RPC-path decision
  is a scoping call, and implementing it (if chosen) should be its own issue.
- **Risk**: Low — corrections are additive; no runner behavior changes.
- **Breaking Change**: No.

## Notes

- Blocked on nothing. Unlike FEAT-2261 / FEAT-2263, this is docs-level
  verification and does not need a working `omp` binary — relevant because
  `.ll/learning-tests/oh-my-pi.md` records `omp --version` and `omp -p` as
  **fail** in this environment (Bun 1.3.9 < the required 1.3.14).
- `docs/hooks.md` upstream documents omp's event surfaces (session,
  agent/context, tool pre/post) plus mutation semantics and ordering —
  direct input for FEAT-2261 / FEAT-2263, noted here so the pointer isn't
  lost.

## Status

**Open** | Created: 2026-07-25 | Priority: P4

## Related Key Documentation

- `.claude/CLAUDE.md` — the Host CLI Abstraction section governs `host_runner.py`/`OmpRunner.capabilities`, which this issue changes to explicitly declare `structured_output=False`.
- `docs/reference/API.md` — directly touches the documented `host_runner` module (`OmpRunner.capabilities`) and the adapters' `emit_agent` surface.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-2263 both specify content requirements for the same `HOST_COMPATIBILITY.md` `[^omp]` footnote — FEAT-2263 wants it to carry hook-intent tracking info (epic/research-spike/artifact path/gating statement); this issue wants it to state why `json_schema`/`structured_output` are `✗` and describe the frontmatter `output:` path. The footnote is a single shared definition — whichever issue lands first must extend it, not overwrite it, to preserve both requirements.

## Verification Notes

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: this issue's core acceptance criterion (`emit_agent` writing to `.omp/agents/` instead of `.claude/agents`) is ALREADY IMPLEMENTED — see `scripts/little_loops/adapters/omp.py`, commit `efc6a6c0`, part of the now-done FEAT-3104/FEAT-2787 work. Cited line `host_runner.py:1071-1075` is stale (content now at 1196-1201, unchanged). Remaining real gaps: the `[^omp]` footnote still doesn't explain why `json_schema`/`structured_output` show ✗; `omp-headless-flags.md` still has no "Structured output" section; `OmpRunner.capabilities` still omits an explicit `structured_output=False`; and omp's `frontmatter_fields_read` tuple is `('description','name')` which doesn't literally include `'output'`, contradicting the `omp.py` docstring's claim that `output:` is carried through unmodified — worth a follow-up bug/enh split off from this issue's narrower remaining scope.

### 2026-08-12 (`/ll:verify-issues`)

NEEDS_UPDATE. Confirmed the cited `host_runner.py:1071-1075` reference had
drifted further, to `1197-1201` (same `HostCapabilities(...)` block,
content unchanged) — corrected in the Summary section above. Remaining
gaps from the 2026-08-10 pass are unchanged and still outstanding.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:58 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:25 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:45 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
