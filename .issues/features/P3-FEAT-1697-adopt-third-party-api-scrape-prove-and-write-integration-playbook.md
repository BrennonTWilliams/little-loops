---
id: FEAT-1697
type: FEAT
priority: P3
status: done
captured_at: '2026-05-25T20:53:43Z'
completed_at: '2026-05-27T04:41:58Z'
discovered_date: '2026-05-25'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1695
- FEAT-1287
- FEAT-1283
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1697: `adopt-third-party-api` — scrape, prove, and write integration playbook

## Summary

Add `scripts/little_loops/loops/adopt-third-party-api.yaml` — an FSM loop that takes a vendor docs URL, invokes `/ll:scrape-docs` to mirror the docs locally, identifies up to 7 significant endpoints/features via an LLM enumeration prompt, gates them through `ready-to-implement-gate` (FEAT-1695), and produces a markdown **integration playbook** at `docs/integration-<domain>.md`. The playbook cites each proven Learning-Test record with sample call, gotchas (from any untested or refuted assertions), and partial-coverage flags up top when not every section is verified.

## Current Behavior

When a developer wants to adopt a new third-party API (Raycast manual, Stripe docs, OpenAI cookbook, etc.), the workflow today is:

- Run `/ll:scrape-docs <url>` (sometimes).
- Skim the mirrored docs, write integration prose into a personal scratch file.
- Write integration code based on the prose, with no falsifiable proof that the documented behavior matches actual behavior.
- Maintain neither the prose nor the proof; both rot independently of the API.

There is no automation that takes "I want to adopt this API" and produces a verified, citation-linked integration playbook that lives in `docs/` and stays accurate against `.ll/learning-tests/` records.

## Expected Behavior

```bash
ll-loop run adopt-third-party-api "https://manual.raycast.com/extensions"
```

The loop:

1. `scrape` (slash command) — runs `/ll:scrape-docs ${context.input}`, mirroring to `docs/docs-<domain>/` per the skill's contract (`<domain>` is `netloc.replace('.','-')`, e.g., `manual-raycast-com`).
2. `enumerate` (LLM prompt) — reads `docs/docs-<domain>/*.md`, identifies up to 7 significant endpoints/features, emits JSON `{"targets": [...], "domain": "<domain>", "count": N}`.
3. If `count == 0` → `failed` (could not identify integration surface).
4. `flatten_targets` (shell) — comma-separates the targets.
5. `prove` (sub-loop) — calls `ready-to-implement-gate` with `targets: "${captured.targets.output}"`, `max_retries: "2"`. Routes to `build_playbook` on success or `build_playbook_partial` on failure (the loop still produces a playbook on partial coverage, but flags unverified sections at the top).
6. `build_playbook` / `build_playbook_partial` (LLM prompts) — for each proven LT record, write a section in `docs/integration-<domain>.md` with proven shape, sample call, and any caveats from refuted/exhausted siblings.

## Motivation

- **Closes the "doc → code" gap end-to-end.** Today `/ll:scrape-docs` produces raw mirror; `/ll:explore-api` produces proof records. There's no automation that combines them into a developer-readable playbook. This loop is the joining piece.
- **Citation-linked docs that don't rot.** The playbook cites `.ll/learning-tests/*.md` for every claim. When the API changes and an LT is marked `stale`, the playbook's citation makes the affected section auditable in one grep.
- **Partial coverage is still valuable.** Unlike `assumption-firewall` (FEAT-1696) which gates *implementation*, this loop produces *documentation*. A playbook with 5-of-7 proven sections is more useful than no playbook at all — the unverified two are flagged for follow-up rather than blocking the whole artifact.
- **Bounded fan-out.** Cap at 7 endpoints prevents the loop from running `/ll:explore-api` 40+ times on a verbose API doc set. The enumeration prompt selects the highest-impact surfaces.

## Use Case

A developer wants to integrate the Raycast extension API. They run:

```bash
ll-loop run adopt-third-party-api "https://manual.raycast.com/extensions"
```

The loop:

1. `/ll:scrape-docs` mirrors the docs to `docs/docs-manual-raycast-com/`.
2. Enumeration prompt reads the mirror, identifies 6 surfaces: `["Extension manifest (package.json) shape", "Command export signature (default export from .tsx)", "useNavigation hook contract", "showHUD vs showToast UX semantics", "LocalStorage API persistence guarantees", "preferences API schema"]`.
3. Gate proves 5 of the 6; one (`LocalStorage API persistence guarantees`) gets refuted because the actual behavior differs from the docs.
4. Gate routes `on_failure` → `build_playbook_partial`.
5. `build_playbook_partial` writes `docs/integration-manual-raycast-com.md` with:
   - A top section: *"⚠️ Partial coverage: 1 of 6 surfaces could not be proven (`LocalStorage API persistence guarantees`). See section below for details."*
   - One section per proven surface with sample call and citation to its LT record.
   - One section for the refuted surface, citing the LT record and noting *"Docs claim persistence across reboots; proof script demonstrates clearing after `pkill Raycast`. Design around in-memory + manual sync."*

The developer reads the playbook, implements with the proven surfaces, and either accepts the refuted-surface gotcha or files a follow-up issue. The playbook stays at `docs/integration-manual-raycast-com.md` and remains accurate against the LT records.

## Proposed Solution

```
scrape (slash_command)
  action: "/ll:scrape-docs ${context.input}"
  next: enumerate

enumerate (prompt)
  → reads docs/docs-<domain>/*.md (where <domain> is netloc.replace('.','-'))
  → identifies up to 7 significant endpoints/features
  → emits JSON {"targets": [...], "domain": "manual-raycast-com", "count": N}
  capture: enumeration
  evaluate: output_json .count gt 0
  on_yes → flatten_targets
  on_no  → failed (terminal — could not identify integration surface)

flatten_targets (shell)
  → python3 reads ${captured.enumeration.output} → comma-separated targets
  capture: targets
  next: prove

prove (sub-loop)
  loop: ready-to-implement-gate
  with:
    targets: "${captured.targets.output}"
    max_retries: "2"
  on_success → build_playbook
  on_failure → build_playbook_partial

build_playbook (prompt)
  → for each proven LT record, emit a section in docs/integration-<domain>.md:
    proven shape, sample call, gotchas from any untested/refuted assertions
  next: done

build_playbook_partial (prompt)
  → same, but flag at the top which sections are unverified and why
  next: done

done (terminal)
failed (terminal — enumeration produced no targets)
```

### `/ll:scrape-docs` output contract

Reference: `skills/scrape-docs/SKILL.md` — writes mirrored markdown to `docs/docs-<domain>/` where `<domain>` is `netloc.replace('.','-')`. The `enumerate` state must derive the same domain string (parse `${context.input}`, extract netloc, replace dots with dashes) to know where to read.

### Enumeration prompt

Must:
- Accept the docs directory (`docs/docs-<domain>/`) as input.
- Identify up to **7** significant endpoints, features, or behaviors (cap is hard).
- Phrase each target as a single concrete sentence suitable for `/ll:explore-api`.
- Emit JSON `{"targets": ["...", ...], "domain": "<domain>", "count": <len(targets)>, "rationale": "<why these N>"}`.

### Playbook prompts (`build_playbook`, `build_playbook_partial`)

Both must:
- Write to `docs/integration-<domain>.md` (overwriting if it exists).
- One section per proven LT record: title, proven shape (extracted from the LT's frontmatter / body), sample call (cribbed from the proof script), citation `[Proof: .ll/learning-tests/<slug>.md](../.ll/learning-tests/<slug>.md)`.
- `build_playbook_partial` adds a top-of-file warning block listing which targets were refuted or exhausted, with citations to those LT records too.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete YAML patterns from codebase analysis:_

**`scrape` state** — slash_command pattern (from `outer-loop-eval.yaml:44–53`, `autodev.yaml:180–189`):
```yaml
scrape:
  action: "/ll:scrape-docs ${context.input}"
  action_type: slash_command
  capture: scrape_output
  on_error: failed
  next: enumerate
```
`action_type: slash_command` collapses to `"prompt"` mode internally — no evaluator needed when using `next:` for unconditional routing.

**`enumerate` state** — `output_json` evaluator exact syntax (from `assumption-firewall.yaml:78–83`, `ready-to-implement-gate.yaml:25–30`):
```yaml
  evaluate:
    type: output_json
    path: ".count"
    operator: gt
    target: 0
  on_yes: flatten_targets
  on_no: failed
```

**`flatten_targets` state** — triple-quote heredoc pattern for JSON parse (from `assumption-firewall.yaml:85–95`):
```yaml
flatten_targets:
  action_type: shell
  action: |
    python3 << 'PYEOF'
    import json
    data = json.loads("""${captured.enumeration.output}""")
    print(",".join(data["targets"]))
    PYEOF
  capture: targets
  on_error: failed
  next: prove
```
The `"""${captured.enumeration.output}"""` triple-quote form survives newlines and embedded quotes in the LLM output.

**`prove` state** — sub-loop invocation (from `assumption-firewall.yaml:97–105`). Note: `ready-to-implement-gate`'s failure terminal is `blocked` (not `failed`); `on_failure` routes correctly because any non-`done` terminal triggers `on_no`:
```yaml
prove:
  loop: ready-to-implement-gate
  with:
    targets: "${captured.targets.output}"
    max_retries: "2"
  on_success: build_playbook
  on_failure: build_playbook_partial
  on_error: build_playbook_partial
```

**Domain derivation in `enumerate` prompt** — parse `${context.input}` as a URL; the prompt must instruct the model to derive `<domain>` via `netloc.replace('.', '-')` (e.g., `manual.raycast.com` → `manual-raycast-com`) and embed it in the JSON output so that `build_playbook`/`build_playbook_partial` know where to read from.

### Meta-loop compliance

This loop **does not modify harness artifacts** — it writes to `docs/` and reads from `.ll/learning-tests/`. Rule MR-1 does not apply directly. The two LLM playbook-writing steps are not gated by evaluators (they always produce output and route to `done`); this is fine because their output is documentation, not code or harness config, and is reviewed by the developer before any code is written from it.

## API/Interface

**Context variables:**

| Variable | Type | Required | Description |
|---|---|---|---|
| `input` | string | yes | Vendor docs URL (e.g., `https://manual.raycast.com/extensions`); passed positionally per `input_key: input` convention (`general-task.yaml`) |

**Terminal states:**

- `done` — playbook written to `docs/integration-<domain>.md`; routed via `build_playbook` (full coverage) or `build_playbook_partial` (partial)
- `failed` — enumeration found zero significant targets; no playbook produced

**CLI invocation:**

```bash
ll-loop run adopt-third-party-api "https://manual.raycast.com/extensions"
```

**Outputs:**

- `docs/docs-<domain>/*.md` — scraped docs (side effect of `/ll:scrape-docs`)
- `.ll/learning-tests/<slug>.md` — one record per enumerated target (side effect of FEAT-1695's gate via `/ll:explore-api`)
- `docs/integration-<domain>.md` — the integration playbook with citations (the primary output)

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/adopt-third-party-api.yaml` — **new** (the loop)
- `scripts/tests/test_builtin_loops.py` — add `"adopt-third-party-api"` to `expected` set in `test_expected_loops_exist`; add `TestAdoptThirdPartyApiLoop` structural test class (see Tests section)
- `README.md` — update "N FSM loops" numeric count; tracked by `doc_counts.py` / `ll-verify-docs`; will fail CI check if not updated atomically with the new YAML [Wiring pass added by `/ll:wire-issue`]
- `CONTRIBUTING.md` — update "N YAML files" count in `loops/` entry under `## Project Structure`; tracked by `doc_counts.py` / `ll-verify-docs` [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/ready-to-implement-gate.yaml` (FEAT-1695) — **hard dependency** (sub-loop for the `prove` step); confirmed present, terminal states are `done` (success) and `blocked` (failure)
- `skills/scrape-docs/SKILL.md` — `scrape` step depends on the skill's output contract (`docs/docs-<domain>/` with `<domain> = netloc.replace('.','-')`)
- `skills/explore-api/SKILL.md` — transitively, via FEAT-1695's gate

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`skills/scrape-docs/SKILL.md` exists at `.claude/skills/scrape-docs/SKILL.md`** — confirmed present; the `/ll:scrape-docs` slash command is wired and available. The pre-implementation blocker identified during refinement is resolved.
- `scripts/tests/test_builtin_loops.py:68–124` — `test_expected_loops_exist` uses `expected == actual` (strict equality, not subset). The YAML file and the test update must be in the same commit; adding `"adopt-third-party-api"` to `expected` before the YAML exists will fail CI.

### Similar Patterns

- `scripts/little_loops/loops/outer-loop-eval.yaml:55–63` — sub-loop with explicit `with:` binding
- `scripts/little_loops/loops/general-task.yaml` — `input_key: input` positional context
- `scripts/little_loops/loops/eval-driven-development.yaml:49` — `${captured.<state>.output}` interpolation
- Any existing loop that invokes a slash command via `action_type: slash_command` (or equivalent) — pattern to copy for the `scrape` step

### Tests

- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` — updated `expected` set
- Manual smoke (zero targets): point at a docs URL with sparse content; expect `failed` terminal
- Manual smoke (full coverage): point at a docs URL whose API surface is fully provable; expect `done` via `build_playbook`, playbook at `docs/integration-<domain>.md` with citations
- Manual smoke (partial coverage): point at a docs URL with at least one refutable claim; expect `done` via `build_playbook_partial`, playbook with top warning block

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — add `TestAdoptThirdPartyApiLoop` class following the pattern in `TestAssumptionFirewallLoop` (lines 3794–3846); minimum assertions: `test_description_is_nonempty`, `test_prove_delegates_to_ready_to_implement_gate` (`prove.loop == "ready-to-implement-gate"`), `test_prove_with_contains_targets_and_max_retries`, `test_done_is_terminal`, `test_failed_is_terminal`
- **Sweep tests that auto-cover the new YAML** (no code change needed, but YAML must satisfy): `test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, `test_all_have_description_field` (requires non-empty top-level `description:`), `test_no_bare_bash_variable_in_shell_actions` (requires `$${VAR}` not `${VAR}` in shell actions), `test_all_failure_terminals_have_diagnostic_action`

### Documentation

- The loop *produces* documentation as output (`docs/integration-<domain>.md` per invocation)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — add catalog row for `adopt-third-party-api` in an Integration/API category section; convention-only, no automated test gate
- `docs/guides/LOOPS_GUIDE.md` — add row to `## Built-in Loops` section in an appropriate category (e.g., "API Adoption" or alongside `assumption-firewall`); this is the primary user-facing discovery surface; convention-only
- `docs/guides/LEARNING_TESTS_GUIDE.md` — add cross-reference under `## Practical Patterns` pointing to the combined scrape+prove+playbook workflow; convention-only

### Configuration

- N/A — no new config keys

## Implementation Steps

1. **Confirm FEAT-1695 is merged and validates** — this loop depends on `ready-to-implement-gate` being discoverable.
2. **Draft `scripts/little_loops/loops/adopt-third-party-api.yaml`** using the seven-state design above.
3. **Wire `scrape`** as `action_type: slash_command` with `action: "/ll:scrape-docs ${context.input}"`, `capture: scrape_output`, `on_error: failed`, `next: enumerate` — this exact shape is used in `outer-loop-eval.yaml:44–53` and `autodev.yaml:180–189`. The skill is confirmed available at `.claude/skills/scrape-docs/SKILL.md`.
4. **Author the enumeration prompt inline:** must parse `${context.input}` to derive `<domain>`, read `docs/docs-<domain>/*.md`, identify up to 7 targets, emit JSON. Evaluate `output_json .count gt 0`.
5. **Wire `flatten_targets`** as a shell step: `action_type: shell`, inline `python3 << 'PYEOF'` heredoc with `json.loads("""${captured.enumeration.output}""")` and `print(",".join(data["targets"]))` — exact pattern from `assumption-firewall.yaml:85–95`.
6. **Wire `prove`** as a sub-loop call to `ready-to-implement-gate` with the captured targets and `max_retries: "2"`; `on_success: build_playbook`, `on_failure: build_playbook_partial`.
7. **Author the two playbook prompts** (`build_playbook`, `build_playbook_partial`): both write to `docs/integration-<domain>.md`. Partial version flags refuted/exhausted targets at the top.
8. **Run `ll-loop validate adopt-third-party-api`** and iterate until no ERRORs.
9. **Update `scripts/tests/test_builtin_loops.py`** to add `"adopt-third-party-api"` to `expected`.
10. **Smoke test the failed path:** point at a near-empty docs URL; verify `failed` terminal.
11. **Smoke test the full-coverage path:** point at a tractable API (one whose surfaces are likely provable from public docs without auth); verify `done` via `build_playbook` and inspect `docs/integration-<domain>.md` for proper citations.
12. **Smoke test the partial-coverage path:** point at an API with at least one known refutable claim (or inject one by hand); verify `done` via `build_playbook_partial` with a top warning block.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. **Update `README.md` and `CONTRIBUTING.md` loop counts** — `doc_counts.py` scans these files for numeric loop counts and exits 1 if they don't match the filesystem. Update atomically in the same commit as the new YAML; run `ll-verify-docs` to confirm no mismatch.
14. **Add `TestAdoptThirdPartyApiLoop` class** to `scripts/tests/test_builtin_loops.py` — follow `TestAssumptionFirewallLoop` (lines 3794–3846) as the structural template; assert `prove.loop == "ready-to-implement-gate"`, `prove.with` has `targets` and `max_retries`, and `done`/`failed` are terminal states.
15. **Add catalog entries** — add a row to `scripts/little_loops/loops/README.md` and `docs/guides/LOOPS_GUIDE.md` for `adopt-third-party-api` in an Integration/API Adoption section alongside the other gate-consumer loops.

## Acceptance Criteria

- `scripts/little_loops/loops/adopt-third-party-api.yaml` exists and `ll-loop validate adopt-third-party-api` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with `"adopt-third-party-api"` in `expected`.
- `ll-loop list` surfaces `adopt-third-party-api`.
- Sparse-docs URL reaches terminal `failed` (enumeration emits `count: 0`).
- Provable-docs URL reaches terminal `done` via `build_playbook` and writes `docs/integration-<domain>.md` with one section per proven LT record and a citation link per section.
- Partial-coverage URL reaches terminal `done` via `build_playbook_partial` and writes `docs/integration-<domain>.md` with a top warning block listing refuted/exhausted targets.
- Enumeration prompt caps target count at 7 (verifiable by feeding a verbose API doc set and inspecting `enumeration.output`).
- Playbook citation links resolve to existing `.ll/learning-tests/*.md` files (manually verifiable).

## Impact

- **Priority**: P3 — Useful end-to-end developer workflow; not blocking other work. Lower priority than the gate primitive (P2 FEAT-1695) since it's a consumer, on par with FEAT-1692 and FEAT-1696.
- **Effort**: Medium — One YAML, one test edit, three prompts (enumeration + two playbook variants), one slash-command invocation pattern to look up. The playbook prompts are the main investment; the rest is mechanical.
- **Risk**: Low — Read-only against the codebase except for `docs/docs-<domain>/` (created by `/ll:scrape-docs`), `.ll/learning-tests/*.md` (created by `/ll:explore-api`), and `docs/integration-<domain>.md` (created by the playbook prompts). No source-code modification. Worst-case failure is "playbook prompts hallucinate," which the developer catches on review before integrating.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `docs-driven`, `integration-playbook`, `gate-consumer`, `captured`

---

**Open** | Created: 2026-05-25 | Priority: P3

## Resolution

Implemented `scripts/little_loops/loops/adopt-third-party-api.yaml` — a 9-state FSM loop:
- `scrape` (slash_command) → `/ll:scrape-docs ${context.input}`
- `enumerate` (prompt) → reads mirrored docs, emits `ENUMERATE_JSON:{...}` with up to 7 targets and derived domain
- `parse_enumeration` (shell) → extracts sentinel line, caps targets at 7, falls back domain from URL parse
- `flatten_targets` (shell) → joins targets as comma-separated string
- `prove` (sub-loop) → `ready-to-implement-gate` with `max_retries: "2"`
- `build_playbook` / `build_playbook_partial` (prompt) → writes `docs/integration-<domain>.md` with LT citations
- `done` / `failed` (terminal)

Also updated: `test_builtin_loops.py` (expected set + `TestAdoptThirdPartyApiLoop`), `README.md` (54→57 FSM loops), loops README catalog, LOOPS_GUIDE.md (API Adoption section), LEARNING_TESTS_GUIDE.md (end-to-end adoption pattern).

## Session Log
- `/ll:manage-issue` - 2026-05-27T04:41:58Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-27T04:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a67b0ab-80e1-4a4e-8e68-036bd62c36e3.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fdfb6b0a-f45e-498c-aa5c-9d67c1fbc347.jsonl`
- `/ll:wire-issue` - 2026-05-27T04:25:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec9a57c6-1dde-454e-9982-6951fab1dbee.jsonl`
- `/ll:refine-issue` - 2026-05-27T04:20:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4cc50b2-5fc3-49cf-96e7-6ce8189bc5f6.jsonl`
- `/ll:capture-issue` - 2026-05-25T20:53:43Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/810cf8d1-477c-42da-bb20-b577b2ee3ad9.jsonl`
