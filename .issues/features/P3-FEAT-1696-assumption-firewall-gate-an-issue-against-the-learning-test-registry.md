---
id: FEAT-1696
type: FEAT
priority: P3
status: open
captured_at: '2026-05-25T20:53:43Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
parent: EPIC-1694
relates_to: [EPIC-1694, FEAT-1695, FEAT-1287, FEAT-1283]
---

# FEAT-1696: `assumption-firewall` — gate an issue against the Learning-Test Registry

## Summary

Add `scripts/little_loops/loops/assumption-firewall.yaml` — an FSM loop that takes an issue ID, uses an LLM prompt to extract every external-API assumption from the issue's plan/body (`max 7` per issue to bound fan-out), flattens the list to comma-separated targets, and delegates to `ready-to-implement-gate` (FEAT-1695) as a sub-loop. Terminates `done` (all assumptions proven, issue safe to implement), `blocked` (at least one refuted, surface as diagnosis), or `no_external_deps` (no assumptions found — pass-through).

## Current Behavior

When `/ll:manage-issue` or any implementation flow reaches an issue that references external APIs, the agent decides ad-hoc whether to check the Learning Test Registry. Outcomes today:

- Most often the agent skips the check, writes integration code against the issue's (potentially hallucinated) assumptions, and discovers divergence in test or production.
- Sometimes the agent runs `/ll:explore-api` for one or two surfaces, but rarely for the full set of assumptions an issue makes.
- There is no harness-level enforcement that an issue's external-dep assumptions must be `proven` before implementation begins.

The Learning Test Registry exists as data (`.ll/learning-tests/`), but its consultation is aspirational rather than structural.

## Expected Behavior

```bash
ll-loop run assumption-firewall --context input="FEAT-1234"
```

The loop:

1. `extract_assumptions` (LLM prompt) reads `ll-issues show FEAT-1234 --json | jq -r .plan,.body` and emits JSON `{"targets": [...], "rationale": "...", "count": N}` with `max 7` targets.
2. If `count == 0` → terminal `no_external_deps` (pass — nothing to gate).
3. `flatten_targets` (shell) comma-separates the extracted list.
4. `run_gate` (sub-loop) invokes `ready-to-implement-gate` with `targets: "${captured.targets.output}"` and `max_retries: "2"`.
5. Gate `on_success` → terminal `done`. Gate `on_failure` → terminal `blocked`.

Callers wrap this around implementation flows; if the firewall blocks, the issue is not safe to implement until the refuted assumption is addressed (update the hypothesis, accept the refutation and redesign, or close as not-feasible).

## Motivation

- **Structural enforcement of the registry's value proposition.** FEAT-1695 ships the gate primitive; this issue is the simplest defensive consumer — wrap the gate around an issue. If this loop ships, future flows can call `assumption-firewall` before any implementation step and the gate becomes structural.
- **Smallest validation of the sub-loop binding.** With FEAT-1695's gate as the dependency, this loop's only novelty is "extract a list from an issue and pass it to a sub-loop." That validates the `loop:` + `with:` + `on_success`/`on_failure` contract end-to-end with minimal additional surface.
- **Catches hallucinated assumptions before they become code.** The most expensive class of integration bugs is "agent assumed an API behaved one way; it behaved another." The firewall makes that assumption falsifiable *before* it touches a codebase.
- **Plan/body is the right extraction surface, not the implementation steps.** Issues describe assumptions in their narrative (motivation, use case, proposed solution) more than in their step list. The extraction prompt reads `plan` and `body`, not `implementation_steps`.

## Use Case

A developer queues `FEAT-2001 — "Add Stripe subscription webhook handler"` for implementation. Before running `/ll:manage-issue feat implement FEAT-2001`, they (or an automation wrapper) run:

```bash
ll-loop run assumption-firewall --context input="FEAT-2001"
```

The loop:

1. Pulls FEAT-2001's plan/body via `ll-issues show FEAT-2001 --json`.
2. LLM prompt extracts 4 assumptions: `["Stripe customer.subscription.updated webhook payload shape", "Stripe webhook signature verification (Stripe-Signature header)", "Stripe idempotency-key behavior on webhook retries", "Stripe subscription status state machine (active → past_due → canceled)"]`.
3. Flattens to comma-separated string.
4. Calls `ready-to-implement-gate` with the four targets. Three are already `proven` in the registry; the fourth (signature verification) is missing.
5. Gate's `explore` state runs `/ll:explore-api "Stripe webhook signature verification (Stripe-Signature header)"` once, which writes a `proven` record.
6. All four resolved → gate routes `done` → firewall terminates `done`.

The developer now knows the four core assumptions are proven and proceeds to implementation. The firewall took ~2 minutes; it would have taken hours to debug a wrong-signature-shape bug in production.

If instead the signature verification turned out to be `refuted` (the docs and the actual header semantics diverged), the firewall terminates `blocked`. The developer reads the LT record, decides whether to update the issue's design or accept the refutation, and re-runs.

## Proposed Solution

Six states + three terminals. Builds on FEAT-1695 as a sub-loop.

```
extract_assumptions (LLM prompt)
  ↓ reads `ll-issues show ${context.input} --json | jq -r .plan,.body`
  ↓ emits JSON {"targets": [...], "rationale": "...", "count": N}
  ↓ capture: extracted
  ↓ evaluate: output_json .count gt 0
  on_yes → flatten_targets
  on_no  → no_external_deps (terminal pass — no assumptions to verify)

flatten_targets (shell)
  ↓ python3 reads ${captured.extracted.output} → echoes comma-separated targets
  ↓ capture: targets
  next: run_gate

run_gate (sub-loop)
  loop: ready-to-implement-gate
  with:
    targets: "${captured.targets.output}"
    max_retries: "2"
  on_success: done
  on_failure: blocked

done (terminal — all assumptions proven, issue safe to implement)
blocked (terminal — at least one assumption refuted, surface as diagnosis)
no_external_deps (terminal — pass; nothing to gate)
```

### Extraction prompt (`extract_assumptions`)

The prompt MUST:

- Read `ll-issues show ${context.input} --json` and parse `plan` + `body` fields. Pattern reference: `scripts/little_loops/loops/autodev.yaml:437–441`.
- Identify **external-API assumptions** only — claims about behavior of third-party services, SDKs, libraries, language stdlib functions whose contract is non-obvious. Internal-codebase claims are out of scope.
- Cap target count at **7** (`max 7`) so the gate doesn't fan out indefinitely on a verbose issue. If the issue has more than 7 plausible assumptions, the prompt selects the highest-risk seven and records the deferred ones in `rationale`.
- Phrase each target as a single concrete sentence suitable for `/ll:explore-api` (e.g., `"Stripe webhook signature verification (Stripe-Signature header)"` not `"how does signature verification work?"`).
- Emit valid JSON: `{"targets": ["...", ...], "rationale": "<one-paragraph why these N>", "count": <len(targets)>}`.

### Sub-loop binding pattern

Reference: `scripts/little_loops/loops/autodev.yaml:92–108` and `scripts/little_loops/loops/outer-loop-eval.yaml:55–63`. Explicit `with:` is the right shape here since we're binding a *captured* value, not passing context wholesale.

### Meta-loop compliance

This loop **does not modify harness artifacts** — it queries issue data and delegates proof to FEAT-1695. Rule MR-1 does not apply directly to this loop, but indirectly: the `run_gate` step's success/failure routing is gated by the sub-loop, whose evaluators are non-LLM by construction. The single LLM step (`extract_assumptions`) is paired with a non-LLM `output_json .count gt 0` evaluator on its capture.

## API/Interface

**Context variables (CLI / parent inputs):**

| Variable | Type | Required | Description |
|---|---|---|---|
| `input` | string | yes | Issue ID (e.g., `FEAT-2001`); passed via `--context input=...` per `input_key: input` convention (`general-task.yaml`) |

**Terminal states:**

- `done` — all extracted assumptions reached `proven` in the registry
- `blocked` — at least one assumption refuted or `/ll:explore-api` exhausted its retries
- `no_external_deps` — extraction found zero external-API assumptions; issue is safe to implement (pass-through)

**CLI invocation:**

```bash
ll-loop run assumption-firewall --context input="FEAT-2001"
```

**Sub-loop invocation (future wrappers around `/ll:manage-issue`):**

```yaml
firewall_step:
  loop: assumption-firewall
  with:
    input: "${context.issue_id}"
  on_success: proceed_to_implement
  on_failure: surface_blocked_assumptions
```

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/assumption-firewall.yaml` — **new** (the loop)
- `scripts/tests/test_builtin_loops.py` — add `"assumption-firewall"` to `expected` set in `test_expected_loops_exist`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` (FEAT-1695) — **hard dependency**; this loop calls it as a sub-loop
- `scripts/little_loops/cli/issues.py` (or wherever `ll-issues show --json` lives) — extraction step depends on the `--json` output schema (`plan`, `body` fields)
- `skills/explore-api/SKILL.md` — transitively, via FEAT-1695's gate

### Similar Patterns

- `scripts/little_loops/loops/autodev.yaml:437–441` — `ll-issues show <id> --json | python3 -c ...` extraction pattern
- `scripts/little_loops/loops/outer-loop-eval.yaml:55–63` — sub-loop with explicit `with:` binding
- `scripts/little_loops/loops/general-task.yaml` — `input_key: input` positional context convention

### Tests

- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` — updated `expected` set
- Manual smoke (no external deps): `ll-loop test assumption-firewall --context input="<doc-only-issue-id>"` should reach `no_external_deps`
- Manual smoke (proven path): run against an issue whose external-API claims are already proven in the registry; expect `done`
- Manual smoke (refute path): run against an issue with a deliberately-wrong assumption; expect `blocked`

### Documentation

- Follow-up after EPIC-1694 ships all four loops; not in scope here

### Configuration

- N/A — no new config keys

## Implementation Steps

1. **Confirm FEAT-1695 is merged and validates** — this loop depends on `ready-to-implement-gate` being discoverable in `BUILTIN_LOOPS_DIR`.
2. **Draft `scripts/little_loops/loops/assumption-firewall.yaml`** using the six-state design above. The `extract_assumptions` step should be a `prompt` action_type that emits JSON; capture as `extracted`; evaluate `output_json` on `.count gt 0`.
3. **Write the extraction prompt inline in the YAML** (per the prompt requirements above): read `ll-issues show ${context.input} --json`, extract external-API assumptions, cap at 7, emit JSON.
4. **Wire `flatten_targets`** as a shell step using `python3` to read `${captured.extracted.output}` and `print(",".join(json.loads(...)["targets"]))`.
5. **Wire `run_gate`** as a sub-loop call to `ready-to-implement-gate` with `with: { targets: "${captured.targets.output}", max_retries: "2" }`; `on_success: done`, `on_failure: blocked`.
6. **Run `ll-loop validate assumption-firewall`** and iterate until no ERRORs.
7. **Update `scripts/tests/test_builtin_loops.py`** to add `"assumption-firewall"` to the `expected` set.
8. **Smoke test the no-deps path:** pick a doc-only issue (or one with no external API claims) and verify the loop terminates `no_external_deps` after extraction returns `count: 0`.
9. **Smoke test the proven path:** pick an issue whose assumptions are already in the registry as `proven`; verify the loop terminates `done` without invoking `/ll:explore-api`.
10. **Smoke test the explore + done path:** pick an issue with one missing assumption that `/ll:explore-api` can prove; verify the loop terminates `done` after exactly one `/ll:explore-api` invocation.
11. **Smoke test the blocked path:** craft an issue with a clearly-wrong assumption; verify the loop terminates `blocked` and the refuted target is visible in the gate's `probe` capture.

## Acceptance Criteria

- `scripts/little_loops/loops/assumption-firewall.yaml` exists and `ll-loop validate assumption-firewall` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with `"assumption-firewall"` in `expected`.
- `ll-loop list` surfaces `assumption-firewall`.
- Doc-only issue (zero external-API claims) reaches terminal `no_external_deps`.
- Issue with all assumptions already proven reaches terminal `done` without invoking `/ll:explore-api`.
- Issue with one missing assumption that can be proven reaches terminal `done` after exactly one `/ll:explore-api` invocation.
- Issue with a refuted assumption reaches terminal `blocked` with the refuted target captured.
- Extraction prompt caps target count at 7; verifiable by feeding an issue with >7 plausible assumptions and inspecting `extracted.output`.

## Impact

- **Priority**: P3 — Composes FEAT-1695 + issue-extraction into a developer-visible workflow. Not blocking (FEAT-1695 ships the primitive separately), but unlocks the structural-enforcement framing that justifies EPIC-1694.
- **Effort**: Small — One YAML, one test edit. The prompt design is the main investment; the rest is mechanical sub-loop binding.
- **Risk**: Low — Read-only against issues; delegates all proof to FEAT-1695, which has its own safety contract. Worst-case failure mode is "extraction prompt hallucinates non-existent assumptions," which the gate detects as `refuted` or `exhausted` and surfaces cleanly.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `issue-aware`, `gate-consumer`, `captured`

---

**Open** | Created: 2026-05-25 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-25T20:53:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/810cf8d1-477c-42da-bb20-b577b2ee3ad9.jsonl`
