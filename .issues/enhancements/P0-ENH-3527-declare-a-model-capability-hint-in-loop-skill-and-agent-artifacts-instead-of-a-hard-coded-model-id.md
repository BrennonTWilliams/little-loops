---
id: ENH-3527
title: Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id
type: ENH
priority: P0
status: open
discovered_date: '2026-09-23'
labels:
- multi-host
- loops
---

# Declare a model capability hint in loop, skill, and agent artifacts instead of a hard-coded model id

## Summary

Any artifact that names a concrete model id carries a value it cannot keep current: model ids change on a release cadence the artifacts do not track, and the id that is correct on one host is meaningless on another. Both failures show up as a loop that ran fine last month and now errors on a name. Replace the id with a capability-class hint the artifact declares — a small closed vocabulary along the lines of `coding`, `reasoning`, and `burst` — and let the host adapter resolve it to whatever that host currently offers. The artifact then states what kind of model the step needs, which is the part that is actually stable, and the mapping lives in one place per host where a rename is a single edit.

## Current Behavior

Skills (`skills/*/SKILL.md`, e.g. `model: sonnet`, `model: haiku`), agents, and loop YAML states (`model:` on FSM states, default `fsm.schema.DEFAULT_LLM_MODEL`) carry a literal model alias or id. `host_runner.resolve_model_alias` maps those aliases to concrete Anthropic ids via a single Anthropic-specific `MODEL_ALIASES` table, and each `HostRunner.build_streaming` passes the value through as `--model`. An alias valid for one host is meaningless on another, and a model rename requires touching the table plus any artifact that names an id directly.

## Expected Behavior

Artifacts may declare a capability-class hint (`coding` | `reasoning` | `burst`) instead of a model id. The host adapter resolves the hint to that host's current concrete model at run time via a per-host table, so a rename is one edit and an artifact moved between hosts needs no change. Artifacts that still carry a literal model id or alias keep working unchanged.

## Design

One field and one resolution step:

- Loop, skill, and agent artifacts declare a capability-class hint from a closed vocabulary — `coding` | `reasoning` | `burst` — instead of a hard-coded model id.
- The host adapter owns the hint → concrete-id mapping, one table per host, so a model rename is a single edit in one place.
- The hint is what survives: an artifact moved between hosts resolves to whatever the target host currently offers, with no artifact edit.
- Composes with the existing model-tier-by-task guidance by giving that guidance a machine-readable place to live.
- Additive: artifacts that still carry a literal model id keep working.

## Acceptance Criteria

- [ ] Loop, skill, and agent artifacts can declare a model capability hint from a closed vocabulary (`coding`, `reasoning`, `burst`).
- [ ] The host adapter resolves the hint to a concrete model id for the current host at run time.
- [ ] A model id rename requires editing exactly one mapping entry per host.
- [ ] An artifact moved between hosts resolves to the target host's current model without any artifact edit.
- [ ] Existing artifacts carrying hard-coded model ids continue to run unchanged.

## Scope Boundaries

- **In scope**: closed capability vocabulary (`coding`, `reasoning`, `burst`); a `model_hint` declaration on loop states, skills, and agents; per-host hint → id resolution in `host_runner`; back-compat for literal ids/aliases.
- **Out of scope**: rewriting existing artifacts to use hints (migration is separate, incremental); adding new vocabulary values beyond the three; changing how hosts select models internally; cost- or latency-based automatic routing.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-23 — based on codebase analysis:_

**Files to Modify (ground truth, not a prescription)**
- `scripts/little_loops/host_runner.py` — `MODEL_ALIASES` (:97) is a single Anthropic-only table (fable/opus/sonnet/haiku); `resolve_model_alias` (:105) is `dict.get(model.strip().lower(), model)`. `RuntimeHostEntry`/`HostCapabilities` (:294, :506, :523) carry no model data today, so a per-host hint table has no existing home; `advisor.MODEL_RANKS` is the only other per-host model table (keyed by concrete id, only `claude-code` populated).
- `scripts/little_loops/fsm/schema.py` — `StateConfig.model` (to_dict ~:849, from_dict ~:970) and `LLMConfig.model` (~:1044–1078); `DEFAULT_LLM_MODEL = "sonnet"` (:24).
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `stateConfig` (`additionalProperties: false`) and the `llm` block each type `model` as a bare string; a new state field is rejected by the schema unless declared there. The `llm.model` JSON default differs from the Python default.
- `scripts/little_loops/fsm/validation/structural_rules.py` (~:464–494) — `model:` applicability WARNING for non-LLM states; `evaluator_rules.py` (~:536–550) — `haiku-gen` lint does a substring test on `state.model`, so a hint-only state would bypass it.
- `scripts/little_loops/adapters/codex.py` (~:233, :444–453) — the only code in this repo that reads agent `model:` frontmatter (writes it verbatim into the Codex agent TOML). `adapters/capabilities.py` `frontmatter_fields_read` lists no `model` for any host.

**Current model flow (corrects the issue's Current Behavior)**
- `resolve_model_alias` has exactly two callers: `advisor.py:90` (`rank_model`) and `host_runner.py:2939` (`build_anthropic_request`, the SDK/Batches path). It is **not** called from any per-host `build_streaming`/`build_blocking_json`; the CLI path passes the literal alias through as `--model` (claude-code :977, gemini :1548, omp :1689, kimi-code :1835, qwen :1983; codex passes it only in `build_blocking_json` and drops it in `build_streaming`; opencode/pi raise `HostNotConfigured`). `build_detached` takes no `model` parameter.
- The BUG-2828 comment above `MODEL_ALIASES` records that the claude CLI resolves aliases itself and only the API path needs concrete ids. Chaining hint resolution through `resolve_model_alias` on the CLI path would therefore change CLI argv from alias to concrete id — a behavior change for existing runs, not just for hint users. The Program Design Call Path (`build_streaming -> resolve_model_hint -> resolve_model_alias`) implies exactly that chain; whether the CLI path should emit an alias or a concrete id is an open constraint the implementer must decide knowingly.
- FSM flow: `state.model or self.run_model` reaches `run_claude_command` -> `resolve_host().build_streaming(model=...)` (`fsm/executor.py` ~:2658, `fsm/runners.py`, `subprocess_utils.py`); evaluator paths use `state.model or self.fsm.llm.model` -> `build_blocking_json`; the SDK/batch path uses `_resolve_action_model` -> `dispatch_anthropic_request`. A hint must be resolved at every one of these three seams to satisfy AC 2, and they are separate code paths.

**Skills/agents seam (largest unknown)**
- 9 `agents/*.md`, 20 `skills/*/SKILL.md` and `commands/commit.md` carry a literal `model:` (sonnet; `analyze-history` uses haiku). No code in `scripts/little_loops/` validates or resolves that key. On claude-code the plugin is served natively (`agents=False`, `commands=False` in `HOST_CAPABILITIES`), so the host itself reads `model:` and this repo has no resolution seam there; for codex the only seam is the agent TOML emitter. Whether a hint declared in skill/agent frontmatter can be honored on claude-code at all is not established by any existing site. (Unvalidated: the researcher did not read the rest of `main_verify_skills`; treat "no frontmatter-key validator" as unconfirmed.)

**Dependents / callers**
- `host_runner` importers include `fsm/executor.py:81`, `fsm/runners.py:23`, `fsm/evaluators.py:46`, `cli/loop/runner.py:31`, `runner_spec.py:39` (passes `spec.args.get("model")` to `build_blocking_json`), `advisor.py:34`, `cli/advise.py`, `cli/verify_host_map.py:49`, `parallel/worker_pool.py`, `issue_manager.py`, `subprocess_utils.py`.
- Other `DEFAULT_LLM_MODEL` consumers: `cli/harness.py`, `cli/doctor.py`, `cli/issues/link_epics.py`, `cli/artifact/extract.py`, `cli/artifact/discover.py`, `advisor.py`.

**Conventions in Force**
- New optional FSM state field: dataclass field defaulting to `None`, `to_dict` emits the key only when set, `from_dict` uses `data.get`, a matching `stateConfig` property in `fsm-loop-schema.json`, a validation rule, docs. Evidence: `effort` (ENH-2869), `tamper_guard`, `prepatch_check`, `scopes` in `fsm/schema.py`.
- Closed vocabularies on FSM state fields are a `str | None` field plus a module-level `frozenset[str]` and a WARNING-severity rule, with `enum` in the JSON schema — not `Literal` (`_TAMPER_GUARD_VALUES` in `fsm/validation/evaluator_rules.py`). `Literal` aliases are used outside FSM state fields (`SubagentSupport` in `adapters/capabilities.py`, `TamperPolicy`). Two conventions disagree; the issue's Program Design uses `Literal`.
- Per-host tables are frozen dataclasses keyed by host id, guarded by `ll-verify-host-map` parity checks (`cli/verify_host_map.py`); build-time (`HOST_CAPABILITIES`, 6 hosts) and runtime (`RUNTIME_HOST_CAPABILITIES`, 8 hosts incl. opencode/pi) maps are not congruent and are joined by docstring only. Any new per-host hint table has to choose which host set it must cover (opencode/pi raise on `--model` anyway).
- `resolve_model_alias` tests: `scripts/tests/test_host_runner_dispatch.py` `TestModelAliasResolution` (~:351); `test_default_fsm_model_is_a_resolvable_alias` there pins `DEFAULT_LLM_MODEL`.

**Tests**
- `scripts/tests/test_fsm_schema.py` (StateConfig round-trip/absent-when-None pattern ~:4649; per-field `stateConfig` presence assertions ~:4936), `test_fsm_validation_structural.py`, `test_fsm_validation_evaluator_rules.py`, `test_host_runner_dispatch.py`, `test_host_runner.py`, `test_verify_host_map.py`, `conformance/test_host_conformance.py` (argv-per-capability tiers), `test_adapters.py`, `test_codex_adapter.py`.
- Editing any `skills/*/SKILL.md` or `agents/*.md` trips `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` (regenerate mirrors with `ll-adapt --host <h> --apply`) and the 500-line skill cap (`test_enh494_skill_companions.py`). The issue's scope excludes migrating existing artifacts, which keeps those gates untouched unless a hint is added to a shipped artifact.

**Documentation**
- `docs/reference/API.md` (`host_runner`, `StateConfig`, `LLMConfig`), `docs/reference/CLI.md`, `docs/reference/HOST_COMPATIBILITY.md` (~:355 Codex agent `model`), `docs/guides/LOOPS_GUIDE.md` (per-state field table ~:615), `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (`haiku-gen` rule). Model-tier guidance the issue says this "composes with" exists only as the `haiku-gen` lint plus prose in these docs; no machine-readable tier data exists.

**Scoping note**
- Loop YAMLs that set a per-state `model:` were not enumerated; not needed while migration is out of scope.

## Program Design

### Types

- `ModelHint: Literal["coding", "reasoning", "burst"]`
- `HINT_MODELS: dict[str, dict[ModelHint, str]]` — host id → hint → concrete model id/alias

### Signatures

- `resolve_model_hint(hint: str, host_id: str) -> str | None`
- `resolve_model_alias(model: str) -> str`

### Call Path

`ClaudeCodeRunner.build_streaming` -> `resolve_model_hint` -> `resolve_model_alias`

## Impact

- **Priority**: P0 - Model-id drift breaks loops that previously ran, and blocks multi-host portability of artifacts.
- **Effort**: Medium - one new resolver and per-host tables in `host_runner.py`, plus schema/frontmatter acceptance of the new field across loops, skills, and agents.
- **Risk**: Low - additive; literal ids and aliases keep resolving through the existing path.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-23 | Priority: P0


## Session Log
- `/ll:refine-issue` - 2026-09-23T23:20:19 - `1dd8afb6-deef-4834-bd0a-401f1160db13.jsonl`
- `/ll:format-issue` - 2026-09-23T22:58:54 - `67a10285-a4b7-4192-bd9e-23ac30a3ffd0.jsonl`
