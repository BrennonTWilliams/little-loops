---
discovered_date: 2026-05-16
discovered_by: capture-issue
captured_at: '2026-05-17T00:04:56Z'
status: done
confidence_score: 91
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
decision_needed: false
implementation_order_risk: true
size: Very Large
---

# FEAT-1532: agent-loop-specialist monitors, analyzes, refines, and optimizes FSM loops

## Summary

Add a new `agent-loop-specialist` agent to the little-loops plugin that serves as a dedicated expert for the full lifecycle of FSM-based automation loops: monitoring active runs, diagnosing stuck or failing states, refining loop definitions, suggesting improvements, and optimizing performance. The agent acts as a single-stop loop expert invoked by the user or by automation tooling.

## Current Behavior

- Loop monitoring requires manually tailing logs (`ll-loop status`, `ll-loop history`)
- Loop improvement is ad-hoc: users must open the loop YAML, read the FSM manually, and decide what to change
- `ll-loop analyze` (FEAT-719) synthesizes issues from history but is a command, not an agent with persistent loop-domain expertise
- No single agent coordinates the monitor → diagnose → refine → optimize workflow
- Users must chain multiple tools (`ll-loop status`, `ll-loop history`, `ll-loop run --verbose`, `/ll:capture-issue`) without specialist guidance

## Expected Behavior

A new `agents/loop-specialist.md` agent that can be invoked via `--agent loop-specialist` (after `ll-adapt-agents-for-codex` scaffolds the TOML):

1. **Monitor** — inspect running/interrupted loops via `ll-loop status` and `ll-loop list`; surface anomalies (stuck states, repeated failures, timeout patterns)
2. **Analyze** — call `ll-loop history <name>` and parse execution events to identify root causes against an explicit failure-mode taxonomy (see Proposed Solution); write a structured diagnosis artifact to `.loops/diagnostics/<loop>-<ts>.md` *before* proposing edits
3. **Contract** — state a testable predicate for each proposed fix: "after this edit, state X should fire transition Y when output contains Z". This predicate is the verification target — no hand-wavy "should be better now."
4. **Refine** — propose targeted edits to the loop YAML (state prompts, transition conditions, retry logic, timeout values), show a diff preview, and apply with user approval
5. **Verify (active, not static)** — after applying the edit, re-run the loop against a fixture and confirm the contracted predicate fires. Reading `ll-loop history` is not sufficient evidence of a fix
6. **Improve** — suggest structural improvements (state decomposition, parallelism, error recovery states) scored against multiple dimensions: state coherence, transition coverage, prompt clarity, retry strategy, cost/iteration trend
7. **Optimize** — measure iteration cost/duration/token-per-iteration trends and recommend tuning (cache-friendly prompt ordering, token budgets, poll intervals); flag regressions vs. prior runs

### Design principle: don't let it grade its own fixes

Per Anthropic's harness-design guidance, models consistently rationalize their own output. The verify step (5) MUST exercise the loop at runtime rather than re-reading the agent's own reasoning. If the deeper separation is needed later, a distinct evaluator agent can be added; for the P3/small-effort framing, the in-agent `--verify` re-run is the minimum bar.

## Motivation

FSM loops are the highest-leverage automation primitive in little-loops, but they are also the hardest to tune. A specialist agent lowers the barrier to writing and iterating on loops — users should be able to say "my loop keeps getting stuck at the `validate` state, fix it" and have an expert handle diagnosis through fix.

## Use Case

A user has deployed an `issue-fixer` loop that processes backlog issues. After 3 iterations it consistently stalls at the `verify` state with no transition firing. They run `--agent loop-specialist` and describe the symptom. The agent reads the loop YAML, tails the history, identifies that the verify prompt returns ambiguous output that doesn't match any exit condition, proposes a refined prompt with explicit `PASS`/`FAIL` markers, and updates the file — all without the user touching the YAML directly.

## Acceptance Criteria

- [ ] `agents/loop-specialist.md` exists with clear description, triggers, and tool grants
- [ ] Agent can be scaffolded to `.codex/agents/loop-specialist.toml` via `ll-adapt-agents-for-codex`
- [ ] Agent correctly calls `ll-loop status`, `ll-loop history`, and `ll-loop list` to gather state
- [ ] Agent writes a structured diagnosis artifact to `.loops/diagnostics/<loop>-<ts>.md` before proposing any edits (failure mode + evidence + fix predicate)
- [ ] Agent proposes YAML edits with a diff preview before applying
- [ ] Agent states a testable fix predicate ("after edit, state X fires transition Y when output contains Z") and treats this as the verification target
- [ ] Agent re-runs the loop after applying an edit and verifies the predicted transition fires; verification by re-reading history alone is NOT sufficient
- [ ] Agent prompt embeds the failure-mode taxonomy (ambiguous output / infinite cycle / premature termination / feature-stubbing / drift / self-evaluation bias) — see Proposed Solution
- [ ] Agent's `optimize` step compares cost/duration/tokens-per-iteration against prior runs and flags regressions
- [ ] Agent generates `/ll:capture-issue` calls for bugs/enhancements it cannot fix inline
- [ ] Agent is listed in `docs/reference/API.md` under Agents
- [ ] Integration test or eval covers the monitor → diagnose → contract → refine → verify round-trip (not just monitor → diagnose → refine)

## API/Interface

New agent definition file with standard frontmatter schema (no Python API changes):

```yaml
---
name: loop-specialist
description: <string>
tools: Bash, Read, Edit, Write
triggers:
  - <keyword string>
---
```

Invoked via host CLI:
- Claude Code: `--agent loop-specialist`
- Codex (after scaffolding via `ll-adapt-agents-for-codex`): `codex --agent loop-specialist`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The frontmatter sketch above is **inaccurate for this repo**. Inspect `agents/consistency-checker.md:1-31` and `agents/plugin-config-auditor.md:1-32` for ground truth. The actual schema used by all 8 existing agents:

```yaml
---
name: loop-specialist                          # required; kebab-case; must match filename stem
description: |                                 # required; multi-line block scalar
  Use this agent when ...                      # first line acts as the selection trigger phrase

  <example>Prompt: "..." -> ...
  <commentary>...</commentary></example>

  When NOT to use this agent:
  - ...

  Trigger: <plain-text note describing when to invoke>
model: sonnet                                  # required by `ll-adapt-agents-for-codex`
tools: ["Bash", "Read", "Edit", "Write"]       # JSON-array syntax, NOT comma list
---
```

- There is **no `triggers:` YAML key** in any existing agent — trigger phrases live as prose inside `description:`. The Codex adapter (`scripts/little_loops/cli/adapt_agents_for_codex.py:_emit_agent_toml`) reads only `name`, `description` (first non-empty line, truncated to 80 chars), and `model`; the post-frontmatter body becomes `developer_instructions`.
- The generated `.codex/agents/loop-specialist.toml` will start with the marker line `# generated by ll-adapt-agents-for-codex` — files lacking this marker on line 1 are treated as user-authored and never overwritten (lines 138-142 of the adapter).

## Proposed Solution

Create `agents/loop-specialist.md` following the existing agent template pattern (see `agents/issue-expert.md` or `agents/code-reviewer.md` for structure). Key elements:

```markdown
---
name: loop-specialist
description: Expert agent for FSM loop lifecycle — monitors runs, diagnoses stuck states, refines YAML, and optimizes performance.
tools: Bash, Read, Edit, Write
triggers:
  - "my loop is stuck"
  - "fix my loop"
  - "optimize loop"
  - "analyze loop"
  - "refine loop"
  - "loop keeps failing"
---
```

Core tool grants needed:
- `Bash` — for `ll-loop status/history/list/run`
- `Read` / `Edit` — for reading and updating loop YAML files
- `Write` — for generating new loop states, templates, and diagnosis artifacts under `.loops/diagnostics/`

Reuse `ll-loop history` output parsing patterns already established in FEAT-719's implementation.

### Failure-mode taxonomy (embedded in agent prompt)

Per Anthropic's "grading criteria as steering mechanisms" guidance, the agent prompt names concrete failure modes rather than asking for open-ended "find issues":

| Mode | Signal | Typical fix |
|---|---|---|
| Ambiguous output | No exit condition matches state output | Add explicit `PASS`/`FAIL` markers to state prompt |
| Infinite cycle | A → B → A repeated N times | Add cycle-break transition or iteration cap |
| Premature termination | Loop exits before work is done ("context anxiety") | Strengthen continuation condition; reset context between iterations |
| Feature-stubbing | Transition exists in YAML but never fires | Verify trigger predicate; add logging |
| Drift / loss-of-coherence | Behavior degrades after N iterations | Context reset via structured handoff artifact |
| Self-evaluation bias | Loop's verifier state passes broken output | Split verifier into separate state / external check |

### Diagnosis artifact format

Before any edit, write `.loops/diagnostics/<loop>-<ts>.md`:

```markdown
# Diagnosis: <loop-name> @ <timestamp>

## Symptom
<observable behavior, e.g. "stalls at verify state after 3 iterations">

## Failure mode
<one of: ambiguous-output | infinite-cycle | premature-termination | feature-stubbing | drift | self-eval-bias>

## Evidence
<excerpts from `ll-loop history`, line refs into YAML>

## Fix predicate (verification target)
After applying the proposed edit, when the loop is re-run against <fixture>,
state `<X>` should fire transition `<Y>` (currently fires nothing / wrong one).

## Proposed edit
<diff preview>
```

This artifact:
- Survives context resets (per harness-design "context resets via structured handoff")
- Plays well with the existing scratch-pad convention (CLAUDE.md "Automation: Scratch Pad")
- Provides an audit trail across iterations
- Becomes the input to the verify step — the agent doesn't re-derive intent from in-context reasoning

### Verification step

After applying an edit, the agent runs `ll-loop run <name> --fixture <X>` (or `--dry-run` if available) and checks whether the contracted predicate fires. Only then is the fix considered done. If verification fails, the agent updates the diagnosis artifact with the negative result and either iterates or escalates via `/ll:capture-issue`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verification tool selection** (resolves Open Question #2 — fixture story):

- `ll-loop run <name> --fixture <X>` does **not exist**. `cmd_run()` in `scripts/little_loops/cli/loop/run.py` has no `--fixture` flag.
- `ll-loop run <name> --dry-run` exists but is **structural-only**: it calls `print_execution_plan()` and exits without executing a single state. It cannot verify a transition predicate.
- `ll-loop simulate <name> --scenario <all-pass|all-fail|all-error|first-fail|alternating>` (`cmd_simulate()` in `scripts/little_loops/cli/loop/testing.py`) is the closest deterministic-replay tool. It intercepts every action via `SimulationActionRunner` (in `scripts/little_loops/fsm/runners.py`) and returns synthetic `ActionResult` values per the chosen pattern, without subprocess execution or `.loops/.running/` writes. This is what the verify step should call.
- `ll-loop test <name>` (`cmd_test()` in `testing.py`) executes exactly one state and reports the transition that would fire — good for single-state predicate checks.
- **CORRECTION (second refine-issue pass)**: The recommendation above to prefer `ll-loop simulate --scenario` is wrong for content-sensitive predicates. `SimulationActionRunner` (used by both `ll-loop test` and `ll-loop simulate`) returns the literal string `"[simulated output for: ...]"` for every prompt/slash-command state — it never invokes the LLM. An evaluator checking `output_contains: "PASS"` against that synthetic string will always return `"no"`, meaning `ll-loop simulate --scenario all-pass` trivially "passes" any routing-table check but cannot confirm a content predicate fires.
  - **Correct verify step**: `ll-loop run <name> --max-iterations 1 [--context KEY=VALUE ...]` — this is the only invocation that calls the real LLM for prompt/slash states (`DefaultActionRunner.run()` → `run_claude_command()` in `runners.py:FSMExecutor`) and feeds real output to the configured evaluator. Use `ll-loop test <loop> --state <name>` only for shell-action states (where `DefaultActionRunner` IS used) or for routing-table wiring checks via `--exit-code N`.
  - **For non-initial states**: no built-in `--start-state` flag exists; an agent verifying a non-initial state must either reach it via `--max-iterations N` from initial, or limit verification scope to `ll-loop test --state <name>` for shell states only.

**Machine-parseable output**:

- `ll-loop history <name>` defaults to ANSI-colored human text via `_format_history_event()`. The agent **must pass `--json`** to get structured event dicts it can parse. Same for `ll-loop status --json` (returns `LoopState.to_dict()` plus `pid`, `pid_source`, `log_file`, `log_updated_ago`, `last_event`).
- Raw history events live at `.loops/.history/<run_id>-<loop_name>/events.jsonl` (one JSON object per line, read by `get_archived_events()` in `scripts/little_loops/cli/loop/persistence.py`); live state at `.loops/.running/<instance_id>.state.json`. The agent can read these directly when subcommands aren't expressive enough.

**Standard FSM vocabulary the agent will edit** (from `scripts/little_loops/fsm/schema.py`):

- Loop-level: `name`, `initial`, `states`, `description`, `context`, `parameters`, `scope`, `max_iterations` (default 50), `backoff`, `timeout`, `maintain`, `llm`, `on_handoff`.
- State-level: `action`, `action_type` (`prompt|slash_command|shell|mcp_tool`), `evaluate` (with `type`, `operator`, `target`, `pattern`, `prompt`, `min_confidence`), `route` (verdict → state dict; `_` is the default branch), `on_yes`/`on_no`/`on_error`/`on_partial` shorthand, `next`, `terminal`, `capture`, `timeout`, `max_retries`, `on_retry_exhausted`, `loop` + `with` (sub-loops), `agent`, `tools`.
- Standard verdict vocabulary: `yes`, `no`, `error`, `partial` (shorthand routes); arbitrary strings via `route:` table.

## Integration Map

### Files to Modify
- `agents/loop-specialist.md` — new agent definition (create)
- `docs/reference/API.md` — create new `## Agents` section (no such section exists yet); add `loop-specialist` entry
- `.claude-plugin/plugin.json` — **explicit agents array** (lines 21-29) lists all 8 agents by path; must add `"./agents/loop-specialist.md"` to the array
- `.gitignore` — `.loops/diagnostics/` is NOT gitignored (`.loops/tmp/` is, but diagnostics is absent); add `.loops/diagnostics/` pattern matching `.loops/tmp/` convention
- `README.md:164` — "**8 specialized agents**" → **9 specialized agents**
- `CONTRIBUTING.md:111` — "8 agent definitions (*.md)" → 9; add `│   ├── loop-specialist.md` to the tree listing
- `docs/ARCHITECTURE.md:25` — Mermaid diagram node `AGT[Agents<br/>8 specialized agents]` → 9
- `docs/ARCHITECTURE.md:71` — `# 8 specialized agents` → 9
- `docs/ARCHITECTURE.md:79` — add `│   ├── loop-specialist.md` to the agents directory tree

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/adapt_agents_for_codex.py` — auto-discovers all `agents/*.md` files; will process `loop-specialist.md` without code changes, but `ll-adapt-agents-for-codex --apply` must be re-run to generate `.codex/agents/loop-specialist.toml` [Agent 1 finding]
- `scripts/little_loops/cli/__init__.py` — imports/exports `main_adapt_agents_for_codex`; no changes needed [Agent 1 finding]
- `scripts/little_loops/loops/docs-sync.yaml` — behavioral coupling: the `verify_docs` initial state runs `ll-verify-docs 2>&1` and routes to `fix_docs` on non-zero exit; if `agents/loop-specialist.md` is committed before count strings in `README.md`, `CONTRIBUTING.md`, and `docs/ARCHITECTURE.md` are updated, this loop will auto-fire its repair state on next run — **implementation ordering risk: create agent file and update all count docs in the same commit** [Agent 2 finding]

Already-known callers:
- `ll-adapt-agents-for-codex` script — will auto-generate `.codex/agents/loop-specialist.toml` from the new file
- `scripts/little_loops/host_runner.py` — no changes needed; invoked by agent via Bash

### Similar Patterns
- `agents/consistency-checker.md` — follow same frontmatter + trigger + tools structure (note: `agents/issue-expert.md` and `agents/code-reviewer.md` do NOT exist in this repo)
- `agents/plugin-config-auditor.md` — another single-domain expert agent pattern

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_agents_for_codex.py:TestRealAgentsIntegrationGuard.test_all_real_agents_have_toml_files` — integration guard that checks all `agents/*.md` have a corresponding `.codex/agents/*.toml`; will fail until `ll-adapt-agents-for-codex --apply` is run after creating `loop-specialist.md` [Agent 1 finding — update test or run apply]
- `scripts/tests/` — add integration test covering the full monitor → diagnose → contract → refine → verify round-trip (not just static diagnosis); this is an acceptance criterion
- `scripts/tests/test_doc_counts.py` — **CORRECTION (second wiring pass)**: `TestVerifyDocumentation` and all methods in this class use `tmp_path` fixtures with synthetic data — they will **not fail** when disk count changes to 9. The real enforcement of count-string accuracy is `ll-verify-docs` CLI (via `verify_documentation(Path.cwd())`) and the `docs-sync.yaml` loop, not this test suite [Agent 2 + 3 finding]
- `scripts/tests/test_feat1532_doc_wiring.py` — new doc-wiring test; follow `test_feat1462_doc_wiring.py` pattern (one class per doc surface: `PROJECT_ROOT / "docs/reference/API.md"`, `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`; assert `"loop-specialist" in content`); also add **`TestPluginJsonWiring`** class asserting `"./agents/loop-specialist.md"` appears in `.claude-plugin/plugin.json` agents array [Agent 3 finding — class not yet specified in step 8]

### Documentation
- `docs/reference/API.md` — create new `## Agents` section; no such section exists yet [Agent 1 finding]
- `docs/reference/CLI.md:1524` — `ll-adapt-agents-for-codex` section already documented; no agent-specific changes needed [Agent 1 finding]
- `docs/generalized-fsm-loop.md` — FSM loop architecture docs; no change needed for a new agent [Agent 1 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.claude-plugin/plugin.json` — agents array is **explicit**, not auto-discovered at runtime; `"./agents/loop-specialist.md"` must be added [Agent 1 finding — critical]
- `.gitignore` — add `.loops/diagnostics/` alongside `.loops/tmp/` so diagnosis artifacts don't pollute git status [Agent 1 finding — implementation step needed]

## Implementation Steps

1. Audit existing agent files (`agents/consistency-checker.md`, `agents/plugin-config-auditor.md`) to confirm the correct frontmatter schema and tool grant syntax — note: `agents/issue-expert.md` and `agents/code-reviewer.md` do NOT exist; use the 8 existing agents as templates
2. Create `agents/loop-specialist.md` with the monitor → analyze → contract → refine → verify → improve → optimize instructions; embed the failure-mode taxonomy table inline
3. Add `.loops/diagnostics/` to `.gitignore` alongside `.loops/tmp/` so diagnosis artifacts don't pollute git status (confirm this is ephemeral, not committed audit trail)
4. Add `"./agents/loop-specialist.md"` to the `"agents"` array in `.claude-plugin/plugin.json` (lines 21-29) — this array is explicit; auto-discovery does not apply for Claude Code agent registration
5. Run `ll-adapt-agents-for-codex --apply` and verify `.codex/agents/loop-specialist.toml` is generated with valid marker, `name`, `description`, `model`, and `developer_instructions` fields
6. Update count references from 8 → 9 in: `README.md:164`, `CONTRIBUTING.md:111`, `docs/ARCHITECTURE.md:25,71`; add `│   ├── loop-specialist.md` to the explicit agent tree listing in `CONTRIBUTING.md:119` and `docs/ARCHITECTURE.md:79`
7. Create `## Agents` section in `docs/reference/API.md` (no such section exists yet); list `loop-specialist` and all 8 existing agents with descriptions
8. Write `scripts/tests/test_feat1532_doc_wiring.py` covering: (a) `agents/loop-specialist.md` exists with required frontmatter, (b) `.codex/agents/loop-specialist.toml` exists with marker, (c) `README.md` contains "9 specialized agents", (d) `docs/reference/API.md` contains "loop-specialist" — follow pattern from `test_feat1462_doc_wiring.py`
9. Write an eval YAML + pytest following `test_create_eval_from_issues.py` VARIANT_A pattern: `execute` state (`action_type: prompt`) drives the agent against a seeded broken loop, `check_skill` state uses `evaluate.type: llm_structured` to assert the contracted predicate fired after the agent called `ll-loop run --max-iterations 1`. Structural assertions follow `test_outer_loop_eval.py` pattern (`load_and_validate` + `validate_fsm`). The eval must cover the full contract → refine → verify round-trip, not just static diagnosis.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `.claude-plugin/plugin.json` — add `"./agents/loop-specialist.md"` to the `"agents"` array (explicit registration, not auto-discovered)
11. Update `.gitignore` — add `.loops/diagnostics/` pattern after `.loops/tmp/` line
12. Update `README.md:164` — change "**8 specialized agents**" → "**9 specialized agents**"
13. Update `CONTRIBUTING.md:111` — change "8 agent definitions (*.md)" → "9 agent definitions (*.md)"; add `│   ├── loop-specialist.md` to the tree
14. Update `docs/ARCHITECTURE.md:25` — change `AGT[Agents<br/>8 specialized agents]` → 9; update line 71 count and line 79 listing
15. Create `docs/reference/API.md` `## Agents` section — no section exists; create it listing all 9 agents with descriptions
16. Run `ll-adapt-agents-for-codex --apply` and commit `.codex/agents/loop-specialist.toml` — required to prevent `TestRealAgentsIntegrationGuard.test_all_real_agents_have_toml_files` from failing
17. Write `scripts/tests/test_feat1532_doc_wiring.py` — wiring test following the `test_feat1462_doc_wiring.py` pattern; include `TestPluginJsonWiring` class asserting `"./agents/loop-specialist.md"` in plugin.json agents array
18. **Commit atomically**: create `agents/loop-specialist.md` and update all count-bearing docs (README.md, CONTRIBUTING.md, docs/ARCHITECTURE.md) in the **same commit** to prevent `docs-sync.yaml`'s `verify_docs` → `fix_docs` auto-repair from firing between commits

## Open Questions

- ~~**Verifier separation**~~ — **RESOLVED (second refine-issue pass)**: `ll-loop run --max-iterations 1` is the in-agent verify step that calls the real LLM, so the "simulate can't verify" go/no-go blocker on AC-7 is resolved. The in-agent approach is viable at P3 effort. A separate evaluator agent remains a future option if self-evaluation bias appears in eval runs, but it is not a prerequisite to ship.
- ~~**Fixture story**~~ — **RESOLVED (UPDATED second refine-issue pass)**: no `--fixture` flag exists. `ll-loop simulate --scenario` uses `SimulationActionRunner` (synthetic results only) and cannot verify real predicates — see CORRECTION note in Proposed Solution > Codebase Research Findings. The correct verify step is `ll-loop run <name> --max-iterations 1`, which calls the real LLM. No precursor `ll-loop` enhancement required.
- ~~**Cost trend storage**~~ — **PARTIALLY RESOLVED** by `/ll:refine-issue` research: `duration_ms` per action and `accumulated_ms` total are recorded (events.jsonl + state.json); **cost and token counts are NOT tracked anywhere in `scripts/little_loops/fsm/`**. Scope the `optimize` step to duration/iteration-count regressions only, OR open a precursor ENH to add cost/token capture (likely required if the optimize step is to deliver real value).

## Impact

- **Priority**: P3 - Quality-of-life for loop authors; doesn't block other work
- **Effort**: Small — new agent file + docs update; no new Python code needed
- **Risk**: Low — additive only; existing commands untouched
- **Breaking Change**: No

## Related Key Documentation

- Anthropic Engineering — [Harness design for long-running agentic apps](https://www.anthropic.com/engineering/harness-design-long-running-apps) — source for the separation-of-concerns, failure-mode taxonomy, active-verification, and structured-handoff principles applied above
- `docs/ARCHITECTURE.md` — FSM loop architecture
- `.claude/CLAUDE.md` § Automation: Scratch Pad — convention reused for `.loops/diagnostics/` artifacts

## Labels

`agents`, `loops`, `fsm`, `captured`

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-05-16_ — **NO-GO (REFINE)**

**Deciding Factor**: Two acceptance criteria depend on infrastructure that demonstrably does not exist (AC-7 active verification, AC-62 cost/token comparison). Shipping now means quietly weakening the contract or stranding the agent with broken ACs. Refine the issue — or land precursor enhancements for token tracking and a real `--fixture` replay mode — before implementing.

### Key Arguments For
- Pattern fit is strong: 8 existing agents (`agents/consistency-checker.md`, `agents/plugin-config-auditor.md`) provide a direct template; `ll-adapt-agents-for-codex` auto-discovers `agents/*.md`; plugin registration is one line in `.claude-plugin/plugin.json:21-29`.
- Problem is observable now: two stuck runs in `.loops/.running/` (`autodev-20260516T201239` SIGKILL'd at iteration 13 after 573 events; `autodev-20260504T160814` abandoned in `refine_current` since May 4), plus 46 built-in loops and 225 archived history runs justify a dedicated coordinator.

### Key Arguments Against
- AC-7 "active verification" is not satisfiable with current tooling: `SimulationActionRunner` in `scripts/little_loops/fsm/runners.py` returns synthetic `ActionResult` values without invoking the LLM, so `ll-loop simulate --scenario all-pass` trivially "verifies" any change. `ll-loop test` only exercises one state in isolation. Real verification requires live `ll-loop run`, which has side effects and takes minutes.
- AC-62 cost/optimization comparison has no data source: FSM persistence (`scripts/little_loops/fsm/persistence.py:86-103`) stores `accumulated_ms` and per-action `duration_ms` but zero token/cost counts. The issue itself admits this; a precursor ENH to add token capture has not been opened.

### Rationale
The AGAINST side presents two concrete, codebase-grounded blockers that the FOR side does not credibly resolve: (1) `SimulationActionRunner` returns synthetic passes without invoking the LLM, so `ll-loop simulate --scenario` cannot satisfy AC-7's "active verification" requirement; and (2) AC-62's cost/token comparison is architecturally impossible because the FSM persistence layer tracks `accumulated_ms`/`duration_ms` but no token counts. The FOR side's "zero Python lines" framing is accurate for the agent markdown itself but elides that two acceptance criteria are unfulfillable with current infrastructure. The overlap with `debug-loop-run` + `audit-loop-run` + `review-loop` (1,361 lines combined) is real, but a thin orchestrator agent is still a defensible addition — the issue just needs its ACs reconciled with infrastructure reality before it ships.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 91/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- **Low test coverage (Criterion B: 10/25)**: `test_feat1532_doc_wiring.py` and `TestPluginJsonWiring` are co-deliverables of this issue; implement tests first so doc-wiring and plugin.json registration are validated before applying the main changes
- **Breadth across 9 sites (Criterion A: 5/12 breadth)**: coordination overhead across docs, config, agent definition, and test files — each site is mechanical/local, but the count means one missed update causes CI failure (docs-sync loop fires)

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-17
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- FEAT-1543: Create loop-specialist agent, wiring, docs, and doc-wiring test
- FEAT-1544: Write eval YAML + pytest for loop-specialist full behavioral round-trip

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `1f2aa363-89b4-48fb-b7e2-882be8ac2cc8.jsonl`
- `/ll:wire-issue` - 2026-05-17T06:01:21 - `38d57e6b-2308-4ce7-84c3-e08b16c8205e.jsonl`
- `/ll:refine-issue` - 2026-05-17T05:55:18 - `6075fffb-a261-4749-bc91-6a5ccd982e45.jsonl`
- `/ll:go-no-go` - 2026-05-16T00:00:00Z - `79ebee4b-bfa2-4125-97d9-5c564585a388.jsonl`
- `/ll:refine-issue` - 2026-05-17T01:55:41 - `b41cd01e-2f66-4d8a-9569-7533e00b817e.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `60ba9ff7-61cd-4a6b-83ff-2a4a1099aaf1.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `07f68ba4-062e-4796-966c-af5b799a1fb1.jsonl`
- `/ll:wire-issue` - 2026-05-17T01:47:32 - `9c6e016f-d3b2-4f3e-a2c1-6c7553275998.jsonl`
- `/ll:format-issue` - 2026-05-17T00:13:16 - `9399e2ff-d506-4e4e-838b-3a1fd8d6d558.jsonl`

- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `89589346-d055-4c50-9998-e16a3d3ff394.jsonl`
- `/ll:capture-issue` - 2026-05-17T00:04:56Z - `ff887948-4996-409c-8d0b-4292b9dd69d2.jsonl`

---

**Open** | Created: 2026-05-16 | Priority: P3
