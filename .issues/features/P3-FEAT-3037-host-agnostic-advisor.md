---
id: 3037
title: Host-agnostic advisor
type: FEAT
priority: P3
status: open
discovered_date: 2026-08-03
labels:
- planning-hub
---

# FEAT-3037: Host-agnostic advisor

Add a host-agnostic advisor consult path on top of existing `resolve_host()` +
`build_blocking_json(prompt, *, model=…)` substrate. Reuses the existing
transport — no new orchestration engine — and layers in accountability
(a capability floor, a budget cap, and a signal gate) so consults are
tied to discriminating signals rather than model self-vibes.

## Background

The upstream "Advisor Tool" bundled by Claude Code v2.1.98+ is three things:
(a) a one-shot escalation call to a second model, (b) **model-decided** invocation
at three canonical trigger points (pre-commit-to-approach, stuck-in-loop,
pre-done), and (c) a capability floor enforced trivially because advisor and
main model live on one tier ladder. Enablement is `--advisor opus` /
`/advisor opus` / `{"advisorModel": "opus"}`, Anthropic-API-only.

The little-loops version is **strictly more general** in one dimension and
**weaker** in another:

- **Stronger — cross-host advisors.** A Sonnet-on-`claude` session can consult
  Opus-on-`claude`, **or** GPT-on-`codex`, **or** a local model on `opencode`.
  The `host` field on the advisor config is intentionally decoupled from
  `orchestration.host_cli` so cross-provider consults work, and cross-host
  auth (Bedrock/Vertex by routing through a different host binary) is
  indirect but real.
- **Weaker — capability floor.** "advisor ≥ main" is trivial within one tier
  ladder; across providers there is no shared ranking. little-loops must ship
  its own capability-rank table and treat cross-host floors as advisory, not
  enforced (warn via `ll-doctor`, do not refuse).

### The native twist

little-loops has committed, in writing, to the position that the primary
model should not self-decide escalation on vibes. The `MR-1` meta-loop rule
and the "LLM self-grades are 33–55% accurate" citation exist to guard
against self-evaluation bias. Anthropic's Advisor is purely model-decided —
the exact failure mode little-loops engineers against elsewhere.

The correct framing is: **a consult is an escalation gated by a measurable
external signal.** Not "model feels stuck" but "tests still red AND retry_count
≥ 2" or "confidence-gate score < 85" or "`diff_stall` after N iterations."
The non-LLM evaluator decides *when to spend the expensive model*; the model
may also request a consult opportunistically.

**Design principle:** model-requested consults are *allowed*; signal-gated
consults are *preferred*.

## Architecture — three surfaces, no new engine

### Surface A — invocation mechanism (`/ll:advisor` skill + `ll-advise` CLI)

The model-decided path, mirroring Anthropic's ergonomics. A skill whose body:

1. Assemble decision context (current goal, approach under consideration,
   relevant diff/files, the specific question).
2. `resolve_host(advisor_host).build_blocking_json(prompt, model=advisor_model)`.
3. Return a **structured** verdict into the transcript:
   `{recommendation, risks[], confidence, dissent}`.

This is almost exactly what `ll-action` (skill one-shot → JSON) and
`ll-harness` (one-shot runner eval with semantic criteria) already do;
`ll-advise` is a thin sibling. Structured output (not prose) is deliberate —
it keeps the consult auditable and lets gates consume `confidence`
programmatically.

The skill is the human/model-facing entry; `ll-advise` is the CLI the hooks
and FSM states call so there is a single code path.

### Surface B — configuration (`advisor:` block in `.ll/ll-config.json`)

Mirror `orchestration.host_cli`:

```jsonc
"advisor": {
  "enabled": true,
  "host": "claude",          // may differ from orchestration.host_cli — cross-provider allowed
  "model": "opus",
  "min_tier": "opus",        // capability floor; validated best-effort against main model
  "max_consults_per_task": 3, // budget guard — a consult is not free
  "triggers": ["confidence_gate", "loop_stall", "pre_done"]
}
```

- `host` decoupled from the orchestration host so the advisor can live anywhere.
- `min_tier` uses a static capability-rank table (see Surface C note); within
  a host, enforce; across hosts, warn only.
- `max_consults_per_task` — the budget backstop, consistent with `calibrate-budget`.
- `ll-doctor` gains an advisor check: configured host reachable, supports
  `--model`, advisor plausibly ≥ the main model (warn if not).

Config-schema addition + `BRConfig` plumbing + a local-override merge test
(arrays replace, nested deep-merge — standard).

### Surface C — automatic decision points (hooks + FSM, signal-gated)

This is where little-loops diverges from a port and adds the value. Each
trigger pairs a consult with a signal the harness already computes — no new
detection code, and the consult is never fired blind.

| Trigger            | Existing signal                                              | Wiring                                                                                                |
|--------------------|--------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `confidence_gate`  | `confidence-check` readiness score < `readiness_threshold` (85) | On sub-threshold, auto-consult advisor with the gap analysis instead of only blocking.                |
| `go_no_go`         | adversarial pre-implementation review verdict                | The consult *is* a structured second opinion before committing — natural fit.                         |
| `loop_stall`       | FSM `diff_stall` / `score_stall` / convergence non-progress   | An `on_stall` route to a consult state; advisor sees the stuck-state context.                          |
| `pre_done`         | `Stop` / pre-done hook on the final diff                     | "Before declaring done" → consult on the diff; the most direct map to Anthropic's third trigger.       |
| `retry_escalation` | host-CLI non-zero exit / repeated failure count               | After N failures, escalate the failing artifact rather than looping the cheap model.                  |

### Capability floor (the one genuinely hard part)

Anthropic gets "advisor ≥ main" for free. little-loops cannot, because
model capability is not comparable across providers. Resolution:

- **A. Static rank table.** Ship an ordered capability tier map
  (`{claude: {haiku:1, sonnet:2, opus:3}, codex: {...}}`). Enforce within
  a host, warn across. Simple, maintainable, honest about its limits. **Recommended.**
- **B. Trust the user.** No floor; `ll-doctor` prints an informational note
  only. Cheapest, but silently permits a weaker "advisor" — reintroduces the
  self-eval-bias risk the whole design fights.
- **C. Empirical floor.** Derive relative capability from `ll-harness` / eval
  history. Principled but heavy and cold-start-blocked.

Recommended: **A**, with the table living beside `HostCapabilities` and the
cross-host case downgraded to a warning surfaced by `ll-doctor`. Document
explicitly that cross-host floors are advisory.

## Why not subagents / detached sessions?

- Subagents are **same-host, same-model-family** and lack the model-override
  + structured-verdict-back-into-transcript contract. The advisor's whole
  point is a *different, stronger, possibly different-provider* model.
- A detached session is fire-and-forget; the advisor is **synchronous and
  in-band** — the verdict must return before the primary continues its
  decision.
- The consult must be **budget-counted and signal-gated**. Ad-hoc subagent
  spawns are neither.

So: reuse the *transport* (`build_blocking_json`), but the advisor is its
own thin, accountable layer on top.

## Scope — Slice 1 (MVP, model-decided only)

This issue covers Slice 1 only. Slices 2–4 are follow-ups.

- `advisor:` config block + schema + `BRConfig` plumbing.
- `ll-advise` CLI (context in → structured verdict out via `build_blocking_json`).
- `/ll:advisor` skill wrapping the CLI.
- `ll-doctor` reachability check + capability-floor warning.
- Static capability-rank table (Option A) living beside `HostCapabilities`.
- Tests: config merge (arrays replace, nested deep-merge), CLI contract
  (mock host runner), `ll-doctor` warning path, capability-floor enforcement
  within a host (warn-only across hosts).

## Out of scope (deferred to follow-up issues)

- Wiring `confidence_gate` / `pre_done` to auto-consult (Slice 2).
- `max_consults_per_task` budget enforcement and per-task counter (Slice 2).
- `on_stall` FSM escalation route consuming `diff_stall` / `score_stall`
  (Slice 3).
- Consult verdict as a routable `llm_structured` evaluator output (Slice 3).
- Logging consults to `.ll/history.db` for `ll-ctx-stats` / `calibrate-budget`
  analytics (Slice 4).

## Open questions for implementation

- **Context assembly** — how much diff/state to send. Start with an explicit,
  skill-authored context payload (not auto-slurp); revisit.
- **Cross-host auth** — a `codex` / `opencode` advisor needs that host
  authenticated. `ll-doctor` should verify; headless/cron runs may lack
  interactive auth. Fail soft: skip the consult, log why.
- **Determinism in loops** — keep advisor consults out of any replay / resume
  cache path, or mark them explicitly non-cacheable.
- **Ungated auto-consults** — Slice 1's `/ll:advisor` is always
  user/model-invoked; ungated auto-consults are not allowed. Every automatic
  consult must cite a signal (enforced in Slice 2+).
