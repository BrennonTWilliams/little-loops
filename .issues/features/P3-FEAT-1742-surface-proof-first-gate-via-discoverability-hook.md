---
id: FEAT-1742
title: Surface proof-first gate via discoverability hook in mainstream impl loops
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T18:18:58Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
depends_on:
- FEAT-1743
relates_to:
- EPIC-1694
- FEAT-1738
- FEAT-1696
- FEAT-1695
decision_needed: false
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1742: Surface proof-first gate via discoverability hook in mainstream impl loops

## Summary

Add a discoverability surface that nudges users toward `proof-first-task` / `assumption-firewall` when a mainstream implementation loop (`general-task`, `autodev`, `scan-and-implement`) is about to touch unfamiliar external-API code. Without this surface, the EPIC-1694 gate primitives stay invisible to the developers who would benefit most — adoption depends entirely on the user already knowing to type a different loop name.

Two viable shapes (one to be chosen during refinement):

1. **`PreToolUse` hook** that intercepts `Write`/`Edit` against files referencing unfamiliar third-party imports (no matching proven LT record) and emits a one-line suggestion: *"No learning-test proof exists for `<package>` — consider re-running this task via `proof-first-task` first."*
2. **`/ll:confidence-check` integration** that, before any implementation-loop kickoff, runs `ll-learning-tests check` against any external APIs referenced in the linked issue file and recommends `assumption-firewall` / `proof-first-task` when proofs are missing or refuted.

## Current Behavior

EPIC-1694 ships four loops (`ready-to-implement-gate`, `assumption-firewall`, `integrate-sdk`, `adopt-third-party-api`) plus the planned `proof-first-task` wrapper (FEAT-1738). All of these are **opt-in by loop choice** — the user must already know:

- That the Learning Test Registry exists.
- That a gate primitive can prove API assumptions before code is written.
- That `proof-first-task` is the entry point bundling proof + implementation.
- That they should type `proof-first-task` instead of the more familiar `general-task` / `autodev` / `scan-and-implement`.

The mainstream impl loops have **zero awareness** of the registry. A developer who runs `general-task` against an issue mentioning Stripe webhooks gets no signal that a proof step is available. The epic explicitly defers "Wiring `ready-to-implement-gate` *into* existing implementation loops" as out of scope, leaving the discoverability gap unaddressed.

## Expected Behavior

### Shape A — `PreToolUse` hook

```bash
# User runs general-task against a task touching unfamiliar Stripe code
ll-loop run general-task --context task="Add webhook signature verification"

# When the impl loop attempts to Write/Edit a file with `import stripe`:
[ll: proof-first hint]
No learning-test record found for "stripe". You're about to write
integration code based on training-data assumptions. Consider:

  ll-loop run proof-first-task \
    --context task="Add webhook signature verification" \
    --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md"

Continue anyway? [y/N]
```

The hook **does not block** by default — it surfaces a soft nudge. A config knob (`learning_tests.gate_mode: warn | block | off`) lets teams escalate.

### Shape B — `/ll:confidence-check` integration

`/ll:confidence-check` (existing skill) gains a "registry probe" step: it inspects the issue file for external-API references, runs `ll-learning-tests check <target>` for each, and adds to its verdict:

```
Confidence: medium
- Implementation plan is concrete: yes
- Tests defined: yes
- External API proofs:
  - "stripe webhook signature": ❌ no record — recommend `assumption-firewall` first
  - "anthropic streaming":       ✅ proven (2026-04-10)

Recommended next step: ll-loop run proof-first-task --context issue_file=...
```

## Motivation

- **Closes the adoption gap left by EPIC-1694.** The gate primitives are well-designed but invisible — without a surface, they remain niche infrastructure rather than a default behavior.
- **Soft nudges beat opt-in flags.** A one-line hint at the moment of relevant action is far more effective than a doc paragraph the user must remember.
- **Composable with `proof-first-task`.** This issue does not modify the core impl loops (consistent with the epic's "don't pollute core loops" principle) — it adds an orthogonal surface that points users at the opt-in wrapper.
- **Measurable adoption signal.** A hook records when it fires and whether the user accepted the suggestion, giving a feedback signal on registry uptake.

## Use Case

A developer with no prior LT-registry experience runs:

```bash
ll-loop run general-task --context task="Add Stripe webhook signature verification"
```

The impl loop starts editing `webhooks/stripe.py`. The PreToolUse hook fires on the first `Write` attempt, detects `import stripe`, finds no proven record matching `stripe`, and emits the suggestion. The developer chooses to re-run as `proof-first-task`, the gate proves three assumptions, and the implementation proceeds with verified API shapes — preventing a class of bugs that would otherwise survive into review.

## Proposed Solution

### Shape decision

Refinement should pick A or B based on:

- **A (PreToolUse hook)** — higher reach (fires on any tool call regardless of loop), but requires file-content parsing and a package-detection heuristic; risk of noisy false positives.
> **Selected:** Shape A — PreToolUse hook — highest codebase fit; bash hook template, config utilities, registry lookup, and typed config dataclasses all exist and are directly reusable.
- **B (`/ll:confidence-check` integration)** — lower reach (only fires when user invokes confidence-check), but cleaner scope and reuses an existing surface; predictable invocation point.

A reasonable compromise: ship B first as a low-risk surface, then ship A as a follow-up once the import-detection heuristic is proven against the existing Learning Test Registry index.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Shape A — PreToolUse hook

**Reasoning**: Shape A scores 10/12 vs Shape B's 9/12. The decisive advantage is codebase consistency (3/3): two existing PreToolUse bash hooks (`check-duplicate-issue-id.sh`, `scratch-pad-redirect.sh`) are direct structural templates; `lib/common.sh` provides `ll_feature_enabled` and `ll_config_value` helpers; `check_learning_test()`, `DiscoverabilityConfig`, and `LearningTestsConfig` all exist and are ready to use; and `pre_tool_use.py` was explicitly scaffolded for this class of extension. Shape B's lower score (Consistency 2/3) reflects an unresolved design question (LLM vs. regex for API-reference extraction from issue bodies) and a missing `Bash(ll-learning-tests:*)` allowed-tools entry — plus it only fires when the user already knows to run `/ll:confidence-check`, which defeats the discoverability goal.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Shape A (PreToolUse hook) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Shape B (confidence-check) | 2/3 | 2/3 | 3/3 | 2/3 | 9/12 |

**Key evidence**:
- Shape A: `check-duplicate-issue-id.sh` is a direct bash hook template with identical `"Write|Edit"` matcher; `lib/common.sh` has `ll_feature_enabled`/`ll_config_value`; `check_learning_test()` at `scripts/little_loops/learning_tests.py:140` is ready; `DiscoverabilityConfig` at `scripts/little_loops/config/features.py:367` covers the config knob; `pre_tool_use.py` no-op handler explicitly designed for extension.
- Shape B: `Bash(ll-learning-tests:*)` absent from confidence-check allowed-tools; API-reference extraction from issue body is an open design question (LLM vs. regex, FEAT-1742 line 229); lower discoverability reach since it requires user to explicitly invoke the skill.

### Configuration surface

The canonical `learning_tests` configuration schema is defined by FEAT-1743 in `config-schema.json`. This issue references that schema and does not define its own. The discoverability hook checks `learning_tests.enabled` (master switch) and `learning_tests.discoverability.mode` (warn/block) as defined by FEAT-1743.

### Package detection heuristic

For Shape A: parse the file content being written/edited for top-level `import <pkg>` / `from <pkg> import` (Python) or `require('<pkg>')` / `import ... from '<pkg>'` (JS/TS), filter against `skip_packages`, and query `ll-learning-tests check <pkg>` for each. Cache per session to avoid repeated checks on the same package.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Shape A (PreToolUse hook) — files to modify

- `scripts/little_loops/hooks/pre_tool_use.py` — currently a **no-op baseline** (`handle()` at line 24 returns `LLHookResult(exit_code=0)` unconditionally). The Python dispatcher is opt-in only (documented in adapter READMEs). If Shape A is implemented as a **bash hook** (parallel to the two existing PreToolUse bash entries), it does NOT use this Python module.
- `hooks/hooks.json` — already has two `PreToolUse` bash-script entries: `check-duplicate-issue-id.sh` (matcher `"Write|Edit"`, filters to `.issues/*.md`) and `scratch-pad-redirect.sh` (matcher `"Bash|Read"`). The new hook would be a third entry matching `"Write|Edit"` against non-issue files, or an extension of the existing `"Write|Edit"` entry with an additional script. The payload arriving at bash hooks contains `tool_name` and `tool_input.file_path` (and `tool_input.content` for Write, `tool_input.new_string` for Edit). The output contract for bash hooks: JSON on stdout with `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}` (pass) or `"deny"` with `permissionDecisionReason` (block). See `hooks/scripts/check-duplicate-issue-id.sh` as the directly parallel example.
- **Design choice for implementer**: Shape A can be a bash script (following `check-duplicate-issue-id.sh` pattern, simpler, no Python cold-start) or a Python handler (following `pre_tool_use.py`, uses `LLHookResult`, requires opting in per adapter). Bash is lower friction given existing hooks are bash.

#### Shape A — new file to create

- `scripts/little_loops/hooks/learning_tests_gate.py` — new import-detection + registry-probe handler. Can be called from `pre_tool_use.py:handle()` or registered as a separate intent. Should import `check_learning_test` from `scripts/little_loops/learning_tests.py:check_learning_test()` (line 140) and `LearningTestsConfig`/`DiscoverabilityConfig` from `scripts/little_loops/config/features.py` (lines 367–410).

#### Shape B (/ll:confidence-check integration) — files to modify

- `skills/confidence-check/SKILL.md` — add a "Phase 2.9: Registry Probe" step between Phase 2b and Phase 3. The skill already has phases 1, 2, 2b, 3, 4, 4.5–4.9. The probe step scans the issue body for external-API references (keywords / imports), runs `ll-learning-tests check <target>` for each, and appends a registry line to the Phase 3 verdict block.

#### Config — already implemented by FEAT-1743 (no changes needed)

- `config-schema.json` (lines 870–904) — `learning_tests.enabled`, `learning_tests.discoverability.mode` (enum: `off`/`warn`/`block`, default `warn`), `learning_tests.discoverability.skip_packages` (array, default `["std", "typing", "os", "sys"]`) are **already defined**. Step 4 in Implementation Steps below is complete.
- `scripts/little_loops/config/features.py` — `DiscoverabilityConfig` (line 367) and `LearningTestsConfig` (line 390) dataclasses **already exist**. Access via `LearningTestsConfig.from_dict(config.get("learning_tests", {}))` to get typed config in the handler.

#### Hook semantics — LLHookResult exit codes

- `exit_code=0` — pass (no feedback injected). Used when registry has a proven record or feature is disabled.
- `exit_code=2` (Claude Code) — block the tool call and inject `feedback` into model context. Use for `mode: block`.
- Warn mode: return `exit_code=0` with `feedback` set to the suggestion string — Claude Code prints this as a hint without blocking.
- Per `scripts/little_loops/hooks/types.py:LLHookResult` (line 85).

#### Registry lookup

- `scripts/little_loops/learning_tests.py:check_learning_test(target, base_dir=None)` (line 140) — returns `LearnTestRecord | None`. `None` = no record exists (fire suggestion). `.status == "refuted"` = also fire suggestion. `.status == "proven"` = suppress suggestion.
- Registry files live in `.ll/learning-tests/<slug>.md`. Empty registry directory → all lookups return `None` → feature must be a no-op when `learning_tests.enabled` is `False`.

#### Patterns to follow (from existing handlers)

**Config loading in a Python handler** — copy `_load_config()` from `scripts/little_loops/hooks/post_tool_use.py`:
```python
cwd = Path(event.cwd) if event.cwd else Path.cwd()
config = _load_config(cwd)  # returns dict | None
lt_raw = (config or {}).get("learning_tests", {}) or {}
lt_enabled = lt_raw.get("enabled", False)
disc_mode = (lt_raw.get("discoverability") or {}).get("mode", "warn")
skip_packages = (lt_raw.get("discoverability") or {}).get("skip_packages", ["std","typing","os","sys"])
```

**Programmatic `check_learning_test()`** — model after `scripts/little_loops/fsm/executor.py:_run_learning_state()` (line 638):
```python
from little_loops.learning_tests import check_learning_test
record = check_learning_test(target)  # returns LearnTestRecord | None
```
`None` or `record.status in {"refuted", "stale"}` → fire suggestion; `record.status == "proven"` → suppress.

**Import detection (shell grep pattern)** — from `scripts/little_loops/loops/integrate-sdk.yaml` `scan_existing_usage` state:
```bash
grep -rln "import ${pkg}\|from ${pkg}" --include="*.py" . 2>/dev/null
```
Python handler alternative: module-level compiled regex (convention from `post_tool_use.py` and `sweep_stale_refs.py`):
```python
_PY_IMPORT_RE = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
```

**Warn vs block return values** (from `scripts/little_loops/hooks/types.py:LLHookResult`):
- `mode: warn` → `LLHookResult(exit_code=0, feedback=hint_text)` — stderr hint, tool call proceeds
- `mode: block` → `LLHookResult(exit_code=2, feedback=hint_text)` — blocks tool call, injects feedback into model context

**Hook handler test structure** — from `scripts/tests/test_hook_post_tool_use.py` and `scripts/tests/test_pre_compact.py`:
```python
def _event(payload=None, *, cwd=None):
    return LLHookEvent(host="claude-code", intent="pre_tool_use", payload=payload or {}, cwd=cwd)

def _write_config(project_dir, *, learning_tests_enabled=False, disc_mode="warn"):
    (project_dir / ".ll").mkdir(parents=True, exist_ok=True)
    (project_dir / ".ll" / "ll-config.json").write_text(json.dumps({"learning_tests": {"enabled": learning_tests_enabled, "discoverability": {"mode": disc_mode}}}))
```
Use `monkeypatch.chdir(tmp_path)` for isolation.

#### Tests

- `scripts/tests/test_learning_tests.py` — registry fixture patterns (`learning_tests_dir`, `write_record()`)
- `scripts/tests/test_hook_post_tool_use.py` — `_event()` + `_write_config()` + `monkeypatch.chdir` handler test structure
- `scripts/tests/test_pre_compact.py` — `exit_code=2` assertion pattern (`TestResultContract`)
- `scripts/tests/test_learning_tests_discoverability.py` — new file (per issue spec)

#### Documentation

- `docs/guides/LEARNING_TESTS_GUIDE.md` — add "Discoverability" section

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — `_dispatch_table()` registers and invokes `pre_tool_use.handle()`; module docstring/comments describe `pre_tool_use` as "(opt-in only)" — must update commentary when gate activates [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `hooks/adapters/codex/README.md` — "Opt-in: PreToolUse" section and event mapping table row describe the handler as a registered no-op; update to document active gate behavior once Shape A is implemented [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — `[^hot]` footnote says `pre_tool_use` is "opt-in only" for all hosts; update to reflect active Claude Code gate vs. still-opt-in Codex/OpenCode [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — `learning_tests.discoverability.mode` and `discoverability.skip_packages` rows describe config fields only; add "Hook behavior" paragraph explaining the PreToolUse gate these fields control [Agent 2 finding]
- `docs/reference/CLI.md` — `### ll-learning-tests` section describes use-cases as "skills and loops" only; add mention of hook-triggered invocation [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_post_tool_use.py` — `TestPreToolUseBaseline::test_empty_payload_returns_pass` and `test_arbitrary_payload_returns_pass` (lines 459–477) lack `monkeypatch.chdir` isolation; `feedback is None` assertions will break if the gate fires — **update**: add `monkeypatch.chdir(tmp_path)` before wiring the gate [Agent 3 finding]
- `scripts/tests/test_hook_intents.py` — `test_dispatch_pre_tool_use_happy_path` (line 347) asserts `stdout == ""` and `stderr == ""`; verify stays green under `cwd=tmp_path` + `tool_name: "Bash"` no-op conditions; add companion test for `Write` payload with `learning_tests.enabled=True` config [Agent 3 finding]

## Implementation Steps

1. **Decide Shape A vs B** (or both, B first). See `## Proposed Solution` above for trade-off summary. Update `decision_needed: false` in frontmatter after deciding; run `/ll:decide-issue FEAT-1742`.
2. **If Shape B:** open `skills/confidence-check/SKILL.md` and insert a "Phase 2.9: Registry Probe" step between Phase 2b and Phase 3. The step should: (a) scan the issue body for external API keywords, (b) run `ll-learning-tests check <target>` for each via `Bash`, (c) append proven/missing status lines to the Phase 3 verdict block under "External API proofs:".
3. **If Shape A:** implement `scripts/little_loops/hooks/learning_tests_gate.py` as the new handler — parse `payload["tool_input"]["content"]` (Write) or `payload["tool_input"]["new_string"]` (Edit) for `import <pkg>` / `from <pkg> import` (Python) and `require('<pkg>')` / `import ... from '<pkg>'` (JS/TS) patterns; filter against `DiscoverabilityConfig.skip_packages`; call `check_learning_test(pkg)` for each; return nudge `feedback` based on `DiscoverabilityConfig.mode`. Then extend `scripts/little_loops/hooks/pre_tool_use.py:handle()` to dispatch to the new gate when `tool_name in {"Write", "Edit"}` and config enables it. Finally, add a `PreToolUse` entry in `hooks/hooks.json` (see `hooks/adapters/codex/README.md:109` for the entry shape).
4. ~~Add config schema entries under `learning_tests.discoverability` in `config-schema.json`~~ — **already done by FEAT-1743** (`config-schema.json` lines 870–904, `features.py` lines 367–410). No action needed.
5. Add tests in `scripts/tests/test_learning_tests_discoverability.py` following fixture patterns from `scripts/tests/test_learning_tests.py`. Cover: (a) no-op when `learning_tests.enabled=False`, (b) no-op when registry is empty and feature enabled but `mode=off`, (c) suggestion fires when unfamiliar import seen (`mode=warn`), (d) no suggestion when proven record exists, (e) `skip_packages` is honored, (f) `mode=block` returns `exit_code=2`.
6. Update `docs/guides/LEARNING_TESTS_GUIDE.md` with a "Discoverability" section explaining the surface and how to tune it.
7. Update `.claude/CLAUDE.md` if Shape A is chosen (new PreToolUse hook behavior is worth documenting).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/hooks/__init__.py` — remove "(opt-in only)" annotation from `_dispatch_table()` docstring and any module-level USAGE comments that describe `pre_tool_use` as passive once the gate is active
9. Update `hooks/adapters/codex/README.md` — revise "Opt-in: PreToolUse" section and event mapping table row to describe the active gate; note Claude Code users get it via `hooks.json` while Codex users must opt in separately
10. Update `docs/reference/HOST_COMPATIBILITY.md` — revise `[^hot]` footnote: `pre_tool_use` is now active for Claude Code (wired in `hooks.json`) and remains opt-in for Codex/OpenCode
11. Update `docs/reference/CONFIGURATION.md` — add "Hook behavior" paragraph to the `discoverability.mode` and `discoverability.skip_packages` entries explaining the PreToolUse gate these fields control
12. Update `scripts/tests/test_hook_post_tool_use.py::TestPreToolUseBaseline` — add `monkeypatch.chdir(tmp_path)` to both baseline tests; guard `feedback is None` assertions so they explicitly depend on no-config being present (prevents false failures when the gate activates)

## Acceptance Criteria

- A discoverability surface exists that, given an issue or file touching an external API with no proven LT record, recommends `proof-first-task` / `assumption-firewall`.
- The surface is configurable via `learning_tests.discoverability.mode` (off / warn / block).
- When the registry has a proven record for the relevant package/target, no suggestion fires (no nag for already-proven APIs).
- When the user has not enabled the registry at all (empty `.ll/learning-tests/`), the feature is a no-op and does not produce false-positive suggestions on every tool call.
- Tests in `scripts/tests/test_learning_tests_discoverability.py` cover the empty-registry, missing-record, proven-record, and skip-list cases.
- `LEARNING_TESTS_GUIDE.md` documents the surface and tuning knobs.

## Open Questions

- Should the hint mention `assumption-firewall` directly (issue-driven path) or `proof-first-task` (bundled wrapper)? Recommendation: `proof-first-task` because it degrades gracefully.
- For Shape A, should the heuristic also scan changed files in `git diff` (broader signal) rather than only the file being written in the current tool call?
- For Shape B, should the registry probe extract API references via LLM or via simple keyword/regex on the issue body? LLM is more accurate but adds latency to every confidence-check run.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loop`, `learning-tests`, `discoverability`, `hook`, `confidence-check`, `adoption`, `captured`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-03T04:41:44 - `e84ddd5b-a592-4763-b68e-d277e0dded6c.jsonl`
- `/ll:confidence-check` - 2026-06-02T00:00:00 - `91239fbb-0d07-436b-9a22-b36f904bbd3f.jsonl`
- `/ll:wire-issue` - 2026-06-03T04:30:09 - `baf593fd-42f7-421a-8dd8-168a8978de94.jsonl`
- `/ll:decide-issue` - 2026-06-03T04:22:12 - `a11d2e64-c58f-424b-8fe2-9b5c35b06965.jsonl`
- `/ll:refine-issue` - 2026-06-03T04:15:25 - `211cdab0-5d62-49b4-bbd4-914635573536.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-01T02:53:57 - `5e05c48a-ca16-414b-a869-8184ba394f53.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:07 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-27T18:18:58Z - `5d67c925-b04f-4086-8575-fc25fa08257e.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Shape A PreToolUse hook handler (`learning_tests_gate.py`) must remain **warn-only and non-blocking** — it emits a one-line suggestion and optionally prompts, but does not pause FSM execution. This is distinct from the blocking `action_type: human_approval` FSM state introduced by FEAT-1794, which fully pauses loop execution awaiting a yes/no/edit verdict. These two surfaces are complementary: FEAT-1742 nudges at the tool-call layer; FEAT-1794 gates at the FSM state layer. If Shape A is chosen, the PreToolUse handler must not replicate the blocking semantics of FEAT-1794. Once FEAT-1794 ships, proof-first-task loops could replace the Shape A hook with a `human_approval` state — that refactor is out of scope here.
