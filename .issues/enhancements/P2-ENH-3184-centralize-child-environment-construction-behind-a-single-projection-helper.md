---
id: ENH-3184
title: Centralize child-environment construction behind a single projection helper
  in host_runner
type: ENH
priority: P2
status: done
testable: true
discovered_date: '2026-08-15'
completed_at: '2026-08-16T07:13:19Z'
labels: []
confidence_score: 100
outcome_confidence: 88
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
decision_needed: false
---

## Summary

Every child process little-loops spawns builds its environment ad hoc: **eleven** spawn sites hand-roll `os.environ.copy()`-style merges, and the remaining **134** of the package's **145** `subprocess.(run|Popen|check_output|call)` sites pass no `env=` at all and inherit implicitly. There is no single place that decides what a child process sees.

This issue lands **one shared projection helper** and routes every task-path spawn through it, **with zero behaviour change**, guarded by a test that fails when a new spawn site bypasses it. It ships a provable invariant and nothing else.

**This issue is step (a) of four.** It was originally scoped as end-to-end per-task credential scoping; that proved to be four separable pieces, and bundling them meant switching on deny-by-default semantics across a spawn-site map that had already been re-derived wrong twice. The remaining steps are filed separately:

- **(b) [ENH-3203]** — capability/secret declaration field, known-capability registry, deny-by-default projection, report-only mode.
- **(c) [ENH-3204]** — audit persistence of the granted scope (new schema migration).
- **(d) [ENH-3205]** — `gh`/`sync.py` scoping via `GH_TOKEN` + `GH_CONFIG_DIR` isolation.

All three of this issue's previously-unresolved Open Decisions moved with them — none of (b)/(c)/(d)'s design questions need answering to build (a). Deny semantics, declaration syntax, and the audit record are deliberately **not** in this issue.

## Current Behavior

- `HostInvocation.env` is documented and implemented as **override-only**: each spawn site does `os.environ.copy()` (or `{**os.environ, **inv.env}`) and merges the invocation's keys on top. Absence of a key means "inherit the parent's value" — there is no way to express "clear" or "deny." `_apply_automation_env()` (`host_runner.py:1784-1799`) states this contract explicitly.
- Eleven independent spawn sites hand-roll the child environment (census below). Three of them use `dict(os.environ)` rather than `os.environ.copy()` or `{**os.environ}`.
- The overwhelming majority of spawn sites pass no `env=` at all. **The two largest task-path exposures are in this category:**
  - `fsm/runners.py:266` — `DefaultActionRunner`'s shell branch runs `subprocess.Popen(["bash", "-c", action], cwd=..., start_new_session=True)` with no `env=` and no `HostInvocation` at any point. **This is how FSM loops do their real work**, including every `gh` invocation from a loop. `runner_spec.py` is *not* imported by `fsm/executor.py` at all.
  - `fsm/evaluators.py:1146, 1360, 1612` — `evaluate_llm_structured()`, `evaluate_blind_comparator()`, and the `contract` evaluator each do `subprocess.run([invocation.binary, *args], ...)` and **discard `invocation.env` entirely**. Every `llm_structured` evaluation in every loop spawns a host CLI with the full ambient environment and neither of the two keys `build_blocking_json()` computed (`LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS` — that env is a fixed literal; it carries no automation keys, see AC3). Highest-volume credential-bearing spawn in the system.
  - `cli/issues/decisions.py:811` — `subprocess.run([invocation.binary, *llm_args], ...)` on the `ll-issues decisions` LLM-extraction path, no `env=`, `invocation.env` discarded. Same defect class as the three `evaluators.py` sites; see AC7. **Missed by the first four census passes**, which is the third miss in the same direction and the reason AC2's guard is the deliverable rather than the map.
- `runner_spec.py::_run_prompt()` (line 304) computes a `HostInvocation` via `build_blocking_json()` and then calls `subprocess.run()` with no `env=`, discarding it — unlike its sibling `_run_skill()` (line 206), which merges `{**os.environ, **inv.env}`. Same defect class as the `evaluators.py` sites.
- `cli/loop/_helpers.py:1659` (detached `ll-loop` self-spawn, no `env=`) and `:2101` (`dict(os.environ)` + `LL_HOST_CLI` override) re-exec `ll-loop` itself.

Net: there is no chokepoint. Any statement about what a child process can or cannot see is currently unprovable, and any future scoping work has no place to attach.

## Expected Behavior

A single shared helper is the only place a child environment is constructed. Every task-path spawn obtains its `env=` from that helper. The helper's default behaviour is **identical to today's** — full parent inheritance plus the invocation's overrides — so nothing changes at runtime; it simply becomes the one seam where a future policy can be applied.

A guard test enumerates spawn calls in task-path modules and fails on any whose `env=` does not come from the helper, including sites that pass no `env=` at all. Deliberate exemptions are marked in-line and counted, so they are visible rather than silently absorbed.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — home of the new projection helper, alongside `_apply_automation_env()` (lines 1784-1799), which is the existing shared per-runner env-injection helper and the model for how the new helper documents its contract. **No spawn site here to convert**: `host_runner.py` contains **zero** `subprocess.*` calls, and `host_runner.py:1837`'s `env = dict(os.environ)` inside `resolve_host()` is a snapshot of the *parent's own* environment used to read `LL_HOST_CLI`/`LL_HOOK_HOST` for host selection — it is never passed as a child `env=`. Earlier drafts listed it among the hand-rolled child-env sites; it is a false positive and must **not** be routed through the helper.
- **`scripts/little_loops/fsm/runners.py::DefaultActionRunner` shell branch (line 266)** — the `bash -c` path every FSM loop's shell action takes. Mandatory; the largest single exposure and the one an earlier draft of this issue misattributed to `runner_spec.py::_run_cmd()`.
- **`scripts/little_loops/fsm/evaluators.py:1146, 1360, 1612`** — host-CLI spawns that discard `invocation.env`. See AC3, which is **not** a neutral plumbing fix. A fourth spawn in this module, `evaluators.py:644` (`git diff --stat` in the diff-scope evaluator), needs an exemption marker rather than projection.
- **`scripts/little_loops/cli/issues/decisions.py:811`** — host-CLI LLM spawn that discards `invocation.env`. See AC7.
- `scripts/little_loops/cli/action.py:347`, `scripts/little_loops/cli/doctor.py:925`, `scripts/little_loops/init/install_check.py:150` — host-CLI spawns that are **detection/maintenance probes**, not task work (`build_version_check()` twice, and `<host> plugin marketplace update` once). They still spawn a host CLI, so AC2's task-path rule reaches them; they are handled by exemption markers, not by narrowing the rule. See AC2.
- `scripts/little_loops/runner_spec.py` — `_run_skill()` (line 206, merges env), `_run_cmd()` (line 215, `bash -c`, no `env=`), `_run_prompt()` (line 304, computes `inv` then discards its env). The `ll-action`/`ll-queue`/`ll-harness` path.
- `scripts/little_loops/subprocess_utils.py:450` — `run_claude_command()`, the primary streaming path for FSM loops, `ll-parallel`, `ll-sprint`.
- `scripts/little_loops/parallel/worker_pool.py:812` — `_detect_worktree_model_via_api()` per-worktree probe.
- `scripts/little_loops/fsm/handoff_handler.py:131`, `scripts/little_loops/mcp_call.py:197`, `scripts/little_loops/worktree_utils.py:568`, `scripts/little_loops/learning_tests/extractor.py:135`, `scripts/little_loops/session_store/lifecycle.py:158`, `scripts/little_loops/git_operations.py:722`, `scripts/little_loops/prepatch_check.py:287` — remaining hand-rolled env sites.
- `scripts/little_loops/cli/loop/_helpers.py:1659, 2101` — launcher sites that re-exec `ll-loop` itself. See AC5.

**Spawn-site census (re-derived and re-verified 2026-08-15).**

The census must be taken over `subprocess.(run|Popen|check_output|call)`, **not** over `os.environ.copy()`. Grepping for env construction finds only the sites that build an environment; it structurally cannot find the sites that build *none*, which are the majority and include the two largest exposures. An earlier pass made exactly this mistake and therefore missed `fsm/runners.py:266` and the entire `fsm/evaluators.py` LLM-judge path while promoting `runner_spec.py::_run_cmd()` to "largest exposure" on the strength of a call path the FSM executor does not use.

- **Explicit hand-rolled child env — 11 sites** (verified exact): `worktree_utils.py:568`, `git_operations.py:722`, `mcp_call.py:197`, `prepatch_check.py:287`, `subprocess_utils.py:450`, `runner_spec.py:206`, `parallel/worker_pool.py:812`, `fsm/handoff_handler.py:131`, `cli/loop/_helpers.py:2101`, `learning_tests/extractor.py:135`, `session_store/lifecycle.py:158`. A twelfth match, `host_runner.py:1837`, is **not** a child env — see Files to Modify.
- **Implicit inheritance (no `env=` kwarg) — the dominant category.** **145** spawn sites in total; all but the 11 above inherit implicitly. Not every one is on a task path, but the ones that matter are `fsm/runners.py:266`, `fsm/evaluators.py:1146/1360/1612`, `cli/issues/decisions.py:811`, and `runner_spec.py::_run_cmd()`/`_run_prompt()`.
- **Per-module spawn counts across the AC2 module list** (verified exact, this pass — these are *spawn* counts, the denominator for the AC2 marker table): `git_operations.py` 11, `parallel/worker_pool.py` 9, `worktree_utils.py` 4, `fsm/evaluators.py` 4, `runner_spec.py` 3, `prepatch_check.py` 2, `cli/loop/_helpers.py` 2, `cli/action.py` 1, `cli/doctor.py` 1, `init/install_check.py` 1, `cli/issues/decisions.py` 1, `fsm/runners.py` 1, `subprocess_utils.py` 1, `mcp_call.py` 1, `fsm/handoff_handler.py` 1, `learning_tests/extractor.py` 1, `session_store/lifecycle.py` 1, `host_runner.py` 0. Note `worker_pool.py` carries **9** spawns, not the single site at `:812` that earlier drafts implied.

The census having been wrong **three** times — twice on attribution, and once (this pass) by omitting `cli/issues/decisions.py:811`, a credential-bearing host-CLI spawn of exactly the AC3 defect class — is the load-bearing risk fact for this issue. Confidence that the map is now complete should be treated as provisional until AC2's guard is armed and green — which is precisely the argument for landing this centralization step, with zero behaviour change, before any policy is built on top of it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py`, `scripts/little_loops/fsm/evaluators.py` — dispatch actions through `host_runner`/`run_action()`.
- `scripts/little_loops/cli/action.py`, `scripts/little_loops/cli/harness.py`, `scripts/little_loops/cli/loop/run.py`, `scripts/little_loops/cli/parallel.py`, `scripts/little_loops/cli/sprint/run.py` — all invoke `resolve_host()`/`run_action()` for scheduled/unattended work.

### Conventions in Force
- `_apply_automation_env()` (`host_runner.py:1784-1799`) is the one existing shared per-runner env-injection helper, and documents its "absence in `env` means inherit the parent's value, never clear" contract explicitly. The new helper must document its own contract with the same explicitness (AC1), because a later step (ENH-3203) inverts that default.
- `HostInvocation.env`'s additive/override-only contract is relied on at all eleven explicit sites. This issue must **not** change it; deny capability, when it lands, needs a new field.
- **`# ll-no-project:` follows an existing marker convention — do not invent a second shape.** `# ll-private-ok: <reason>` (consumed by `ll-verify-private-refs`) is the established inline-exemption comment in this codebase. The AC2 guard's marker parsing mirrors it: `# ll-<gate>: <reason>`, reason mandatory and non-empty, matched on the spawn call's own line or the line immediately preceding it.
- `scripts/tests/test_host_runner.py::TestAutomationProfileEnvAcrossRunners` (lines 52-84) is the established table-driven, cross-all-runner-classes pattern (cited "BUG-3058 precedent" for why per-runner env behavior must be tested this way, to avoid drift). New tests follow this shape, parametrized across `ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner` plus the `OpenCodeRunner`/`PiRunner` stubs (which raise `HostNotConfigured` before building any env).

### Tests
- `scripts/tests/test_host_runner.py` — helper contract + cross-runner parity.
- `scripts/tests/test_runner_spec.py`, `scripts/tests/test_subprocess_utils.py` — existing coverage for the env-merge call sites.
- New: the AC2 spawn-site guard.

## Motivation

Centralization is worth having on its own merits — eleven hand-rolled env constructions in three different syntactic shapes is a maintenance hazard, and five spawn sites (`evaluators.py` ×3, `_run_prompt`, `decisions.py`) are outright dropping orchestration signals the runner computed.

It is also the precondition for everything in ENH-3203/3204/3205. Deny-by-default on process environments fails closed: a missed spawn site means the guarantee is silently false, which is worse than the status quo because it looks like protection that isn't there. Proving the chokepoint exists — with a guard, under no behaviour change — is what makes the later steps safe to attempt.

## Acceptance Criteria

- **AC1.** A single shared projection helper is the only place a child environment is constructed. It documents its allow/deny/inherit contract as explicitly as `_apply_automation_env()` documents its "absence means inherit" contract. Its **default behaviour is byte-identical to today's**: full parent inheritance plus `HostInvocation.env` overrides. No deny semantics land in this issue.
- **AC2.** A guard test keys on **spawn calls, not env construction**. It enumerates `subprocess.(run|Popen|check_output|call)` sites in task-path modules and fails on any whose `env=` does not come from the projection helper — **including sites that pass no `env=` at all**.
  - An `os.environ.copy()`-shaped guard is explicitly insufficient and must not be shipped as the AC2 test: it passes clean on today's tree while `fsm/runners.py:266` and `fsm/evaluators.py:1146/1360/1612` leak the full environment, and it misses the `dict(os.environ)` sites.
  - **Task-path definition.** A module is on a task path if it spawns a host CLI, spawns `bash -c` from user/loop-authored content, or spawns any process on behalf of a declared action. The guard's module list is asserted against this rule, so adding a module to a task path without adding it to the guard fails. List: `fsm/runners.py`, `fsm/evaluators.py`, `runner_spec.py`, `subprocess_utils.py`, `mcp_call.py`, `worktree_utils.py`, `parallel/worker_pool.py`, `fsm/handoff_handler.py`, `learning_tests/extractor.py`, `session_store/lifecycle.py`, `git_operations.py`, `prepatch_check.py`, `cli/loop/_helpers.py`, `cli/issues/decisions.py`, `cli/action.py`, `cli/doctor.py`, `init/install_check.py`, `host_runner.py`.
  - **Detection and maintenance probes are exempted by marker, not by narrowing the rule.** `cli/action.py:347`, `cli/doctor.py:925`, and `init/install_check.py:150` spawn a host CLI and therefore satisfy the task-path rule, but carry no prompt and no task payload. Earlier drafts omitted them from the list, which would have made the rule-vs-list self-assertion fail on day one. They stay in the list and each spawn carries an `# ll-no-project:` marker. **Adding a "probes don't count" clause to the rule is not an acceptable substitute** — an unstated carve-out defeats the mechanism the same way an unpinned cap does. `host_runner.py` stays in the list with an expected count of **0**, pinning the fact that it holds the helper and spawns nothing.
  - **Exemptions are marked and bounded, not trimmed away.** Several allowlisted modules contain spawns that legitimately need no projection — `git_operations.py` alone has **11** spawn sites, mostly `git rev-parse`-class calls, `parallel/worker_pool.py` has **9**, and `worktree_utils.py` and `fsm/evaluators.py` have **4** each (including `evaluators.py:644`'s `git diff --stat`). Each such call carries an inline `# ll-no-project: <reason>` marker.
  - **The cap is a pinned per-module table, not a single global maximum chosen at implementation time.** A lone "assert a maximum" is untestable in practice: whoever writes it picks whatever number makes the suite green, which defeats the mechanism. The guard asserts an **exact** expected marker count per module, so both a new unmarked spawn *and* a new exemption fail the test and force a deliberate table update. Assert the table's key set equals the task-path module list.
  - **Seeding the table.** Per-module *spawn* counts are pinned in the census above (verified exact); expected markers per module = spawns − projected spawns, resolved during implementation. Carry **both columns** in the table so a spawn appearing in a module is caught even if the implementer miscounts which ones get projected.
  - Narrowing the module list to make the guard green is not an acceptable resolution, because the module list is what makes the invariant meaningful.
- **AC3.** `fsm/evaluators.py`'s three host-CLI spawns (**1146, 1360, 1612** — re-verified this pass; earlier drafts cited 1140/1333/1585, which drifted under ENH-2627's `_structured_output_args` edits and point at comments and a string literal on the current tree) merge `invocation.env` before spawning. The module's fourth spawn, `evaluators.py:644` (`git diff --stat`), is exempted by marker, not projected. **This is a behaviour change and must be treated as one, not as neutral plumbing — but not the one an earlier draft of this issue claimed.**
  - **`LL_AUTOMATION` is not affected. Do not write a test asserting it is.** `_apply_automation_env()` is called from exactly six sites (`host_runner.py:367, 670, 1064, 1251, 1446, 1645`) and **every one is inside a `build_streaming()` method**. No `build_blocking_json()` implementation calls it, and none of the eight accepts an `automation_profile` parameter at all (see `host_runner.py:395-401`). Every implemented `build_blocking_json()` returns the same fixed literal env:

    ```python
    env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
    ```

    There is no `LL_AUTOMATION` key in it, so merging `invocation.env` leaves the value inherited from the loop process **untouched**. `cli/history_context.py:214` and `hooks/session_start.py` are not affected, and the previously-mandated either/or decision is moot — it was predicated on a call that does not exist.
  - **The actual delta**: the judge child newly receives `LL_NON_INTERACTIVE=1` and `DANGEROUSLY_SKIP_PERMISSIONS=1`. `LL_NON_INTERACTIVE` is a live `AUTO_MODE` gate read by ~15 skills (`skills/*/SKILL.md`, e.g. `confidence-check`, `spike`, `format-issue`). Blast radius here is small because the three evaluator spawns send **raw prompts, not skill invocations**, so no `AUTO_MODE` branch is reachable from them — but the test must assert the two keys that actually change, not the one that doesn't.
  - **Do not attempt to thread `automation_profile` into `build_blocking_json()`.** That would mean adding a parameter across eight runner classes, which Program Design explicitly forbids. The projection helper is applied at spawn time; the builders stay unchanged.
- **AC4.** `runner_spec.py::_run_prompt()` (line 304) merges the `HostInvocation.env` it already computes, matching `_run_skill()` (line 206). Today it discards it. Same defect class as AC3, with the same corrected delta: the two `build_blocking_json()` keys above, **not** `LL_AUTOMATION` — which `build_blocking_json()` never supplies to any caller, `_run_skill()` included.
- **AC5.** The re-exec launcher sites (`cli/loop/_helpers.py:1659, 2101`) route through the helper, **and the cross-`execve` limitation is stated rather than implied**. Decision, recorded here so ENH-3203 does not rediscover it: both sites obtain their `env=` from the projection helper, but the re-exec'd `ll-loop` child **re-derives its own environment from scratch** at each of its own spawn sites. This issue therefore claims **no** inheritance guarantee across the `execve` boundary — with full-inheritance defaults nothing is lost, but once ENH-3203 turns on deny-by-default, a scope enforced only in the parent evaporates at re-exec and ENH-3203 must carry the policy across explicitly (env var, config file, or CLI flag — its call).
- **AC6.** Zero behaviour change outside AC3/AC4/AC7. Cross-runner tests (following `TestAutomationProfileEnvAcrossRunners`, `test_host_runner.py:63`) assert the helper produces the same child environment the hand-rolled sites produced. Parametrized across the **six implemented** runners (`ClaudeCodeRunner, CodexRunner, GeminiRunner, OmpRunner, KimiRunner, QwenRunner`); the `OpenCodeRunner`/`PiRunner` stubs are asserted to raise `HostNotConfigured` before constructing any env, so there is nothing to project for them. `python -m pytest scripts/tests/` exits 0.
- **AC7.** `cli/issues/decisions.py:811` merges the `HostInvocation.env` it already computes. Today `subprocess.run([invocation.binary, *llm_args], ...)` passes no `env=` and discards it — the same defect class as AC3 and AC4, on the `ll-issues decisions` LLM-extraction path, with the same delta (`LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`; **not** `LL_AUTOMATION`). This site was missed by all four prior census passes and is the third attribution error in the same direction; it is called out separately rather than folded into AC4 so the guard's module list cannot quietly drop it.

## Program Design

### Types
- No new dataclass is required for this issue. The helper is a function; `HostInvocation` is unchanged.
- `HostCapabilities` (`host_runner.py:119-144`, frozen dataclass of booleans) is per-runner-class feature support and is **not** the shape to extend — that question belongs to ENH-3203.

### Signatures
- **New — the helper this issue lands:**

  ```python
  def project_child_env(
      invocation: HostInvocation | None = None,
      *,
      extra: dict[str, str] | None = None,
  ) -> dict[str, str]:
  ```

  Returns a fully-formed `env=` mapping for `subprocess.*`. Default behaviour is byte-identical to today's: full `os.environ` inheritance, then `invocation.env` merged over it, then `extra` (for the handful of sites that add one-off keys such as `LL_HOST_CLI` at `cli/loop/_helpers.py:2101`).

  **`invocation` must be optional**, and this is load-bearing rather than cosmetic: the two `bash -c` paths — `fsm/runners.py:266` and `runner_spec.py::_run_cmd()` — never construct a `HostInvocation` at all, and `RunnerType.CMD` never calls `resolve_host()`. A signature requiring an invocation cannot cover the largest exposure in the census. `project_child_env()` with no arguments is exactly today's implicit inheritance, made explicit and interceptable.

  Placement: `host_runner.py`, adjacent to `_apply_automation_env()`. Name is not public API — it is imported by task-path modules only. It documents its allow/deny/inherit contract in its docstring as explicitly as `_apply_automation_env()` documents "absence means inherit" (AC1), because ENH-3203 inverts that default.
- `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None` — the existing shared helper, and the model for the new one's placement and contract documentation (`host_runner.py:1784-1799`). Note it is reachable **only** from `build_streaming()`; see AC3.
- **Do not thread anything through `build_*()`.** `build_streaming(*, prompt, working_dir=None, resume=False, agent=None, tools=None, model=None, automation_profile=None, disable_background_tasks=False, workspace_root=None) -> HostInvocation` is **nine keyword-only parameters** across four build methods × eight runner classes (~32 signatures). The projection helper is called at **spawn time**, not build time, so the runner classes stay unchanged and `RunnerType.CMD` (which never calls `resolve_host()` at all) is covered by the same seam.
- `env: dict[str, str]` on `HostInvocation` keeps its additive/override-only contract verbatim in this issue.

### Call Path
`resolve_host()` → `build_*()` → `HostInvocation` → **projection helper** → `subprocess.*`

The helper sits between the invocation and the spawn — at **spawn time, not build time** — which is why `bash -c` paths with no `HostInvocation` at all (`fsm/runners.py:266`, `runner_spec.py::_run_cmd()`) can still route through it via `project_child_env()` with no argument.

### Decision Rules
- Default policy in this issue is "inherit everything, apply overrides" — the current behaviour, expressed once instead of eleven times.
- Exemption rule: a spawn may bypass projection only with an inline `# ll-no-project: <reason>` marker, counted and capped by the AC2 guard.

## Scope Boundaries

Explicitly **out of scope** (each has a home):

- **Deny-by-default semantics, capability declarations, the known-capability registry, the baseline inherit-set, report-only mode** — ENH-3203.
- **Audit persistence of granted scope** — ENH-3204.
- **`gh`/`sync.py` scoping** — ENH-3205. Note that env projection alone cannot constrain `gh`: its credential lives in the OS keyring / `~/.config/gh/hosts.yml`, not in `GITHUB_TOKEN`.
- **Token minting / credential exchange.** No GitHub App installation tokens, no AWS STS `AssumeRole`. `_active_oauth_token()` (`host_runner.py:2064-2076`) only *selects* among ambient vars; nothing in this codebase mints.
- **Disk-backed and keyring-backed credentials.** No `HOME` redirection, no per-task config directories, no keychain scoping.
- **Any change to `HostInvocation.env`'s contract.**

## Impact

- **Priority**: P2 — no runtime behaviour changes except two dropped-env bug fixes, but the cost of adding this grows with every new spawn site (three appeared between surveys), and it blocks ENH-3203/3204/3205.
- **Effort**: Medium — one helper, eleven explicit sites plus the implicit-inherit task paths, one guard test with an exemption mechanism, **five** dropped-env fixes (three in `evaluators.py`, `_run_prompt()`, `decisions.py:811`), cross-runner tests parametrized over the **six implemented** runners plus two stub assertions. Materially smaller than the original four-in-one scope.
- **Risk**: Medium — the dominant risk is an incomplete map, which is exactly what AC2's guard converts from an assumption into an assertion. The census has been wrong **three** times, most recently by omitting `cli/issues/decisions.py:811` through four review passes; treat completeness as provisional until the guard is green. AC3/AC4/AC7 are the one real behaviour change — two fixed keys (`LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`) reaching children that previously saw neither, with a test asserting exactly that and no `LL_AUTOMATION` movement. There is no deny-by-default in this issue, so the "shell action dies on an unrelated-looking error" failure mode (missing `VIRTUAL_ENV`, `SSH_AUTH_SOCK`, a proxy var) is structurally impossible here — it arrives with ENH-3203, which is the reason for the split.
- **Breaking Change**: No.

## Confidence Check Notes

**SUPERSEDED and removed** — the `/ll:confidence-check` run of 2026-08-15 scored the original four-in-one scope. Its findings no longer describe this issue and contradicted the body in two places (it cited "8 spawn sites" against a verified 12, and three unresolved Open Decisions that have all moved to ENH-3203/3204/3205). The frontmatter scores (`confidence_score: 85`, `outcome_confidence: 48`) are likewise stale. Only one of its findings survives, and it is now this issue's core: *a missed spawn site silently defeats the guarantee* — which is what AC2's guard converts from assumption to assertion. Re-run `/ll:confidence-check` against the current scope before implementing.

## Session Log
- `/ll:manage-issue` - 2026-08-16T07:12:14 - `5d0b518d-16a0-47de-b0cf-8f665fe2546a.jsonl`
- `/ll:confidence-check` - 2026-08-16T06:12:24 - `7c646ce3-f44e-4eef-97cb-1c8c88c8d9d9.jsonl`
- `/ll:confidence-check` - 2026-08-16T05:31:05 - `bb755dcf-6087-41b3-80d2-a79a3aba782e.jsonl`
- `/ll:confidence-check` - 2026-08-16T04:58:48 - `3732fd32-810c-4cb4-9095-7a5a9dac49d5.jsonl`
- `/ll:confidence-check` - 2026-08-16T03:56:39 - `953e8134-a0de-46ec-8da0-03d0781ca4b7.jsonl`
- Pre-implementation review (fifth pass) - 2026-08-16 - **found a third census miss and removed a false positive.** (1) `host_runner.py:1837` is not a child env at all — it is `resolve_host()`'s snapshot of the *parent's* environment for reading `LL_HOST_CLI`/`LL_HOOK_HOST`; `host_runner.py` contains **zero** `subprocess.*` calls. Explicit sites corrected 12 → **11**, and the "Files to Modify" instruction to convert that line was removed before it could produce a wrong edit. (2) AC3's three line numbers were stale — real spawns are `evaluators.py:1146/1360/1612` (cited 1140/1333/1585, which land on comments and a string literal today); a **fourth** spawn at `:644` (`git diff --stat`) was unaccounted for. (3) **New AC7**: `cli/issues/decisions.py:811` spawns the host CLI with no `env=` and discards `invocation.env` — the exact AC3 defect class, missed by all four prior passes. (4) AC2's task-path rule reaches three host-CLI probe spawns the module list omitted (`cli/action.py:347`, `cli/doctor.py:925`, `init/install_check.py:150`), so the rule-vs-list self-assertion would have failed on day one; added them under markers rather than adding an unstated carve-out. (5) Pinned per-module spawn counts for the whole guard list — `worker_pool.py` has **9** spawns, not the single site at `:812` earlier drafts implied. (6) Cited `# ll-private-ok:` as the existing inline-exemption convention `# ll-no-project:` must mirror. (7) Fixed Impact's "eight runner classes" against AC6's six-plus-two-stubs. **Re-verified independently: 145 total spawns, 11 explicit child-env sites at the exact stated lines, `git_operations.py` 11 / `worktree_utils.py` 4 — exact. AC3's central premise re-confirmed:** `_apply_automation_env()` appears only at `host_runner.py:367/670/1064/1251/1446/1645`, all inside `build_streaming()`, and every implemented `build_blocking_json()` returns the fixed two-key literal.
- Pre-implementation review (fourth pass) - 2026-08-15 - **corrected AC3's central premise, which was false.** Verified against the tree that `_apply_automation_env()` is reachable only from `build_streaming()` (all six call sites: `host_runner.py:367, 670, 1064, 1251, 1446, 1645`) and that no `build_blocking_json()` accepts `automation_profile` — so the claimed `LL_AUTOMATION=1 → ""` flip cannot occur, `cli/history_context.py:214` is unaffected, and AC3's mandated either/or decision was moot. Both of its branches were also unbuildable: threading `automation_profile` into `build_blocking_json()` means 8 signature changes, which Program Design forbids. Restated the real delta (`LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`) and propagated the same correction to AC4 and Current Behavior. Named the helper and gave it a signature — the prior draft mandated a helper in AC1 with no name or shape anywhere, and the `invocation` parameter must be optional or the `bash -c` paths (the largest exposure) cannot route through it. Replaced AC2's unpinned "assert a maximum" with an exact per-module marker table. Decided AC5 (route through the helper; claim no cross-`execve` guarantee; hand the policy-carrying problem to ENH-3203 explicitly). Scoped AC6 to the six implemented runners, matching the cited precedent. Deleted the superseded confidence-check block. **Re-verified the census independently: 145 spawns, 12 explicit at the exact stated lines, `git_operations.py` 11 / `worktree_utils.py` 4 — all exact.**
- Pre-implementation review (third pass) - 2026-08-15 - **narrowed this issue to step (a), centralization with zero behaviour change**; filed ENH-3203/3204/3205 for declaration+enforcement, audit persistence, and `gh` scoping, taking all three unresolved Open Decisions with them. Verified census against the tree (145 spawns, 12 explicit — exact). Found AC6b's `evaluators.py` fix is **not** behaviour-neutral: all three sites pass no `automation_profile`, so merging `invocation.env` flips the judge child from inherited `LL_AUTOMATION=1` to `""`, changing the `cli/history_context.py:214` gate — rewritten as AC3 with an explicit decision. Added AC4 (`_run_prompt` dropped env, previously only a confidence-check footnote) and AC5 (re-exec, previously flagged in Files to Modify with no AC). Rewrote the AC2 guard with a task-path rule and an `# ll-no-project:` exemption mechanism, after confirming `git_operations.py` alone has 11 mostly-benign spawns that the guard as previously written would have failed on. Marked the confidence-check notes superseded (they cited 8 sites against a body saying 12).
- Pre-implementation review (second pass) - 2026-08-15 - **corrected the largest-exposure misattribution**: `fsm/runners.py:266` (`DefaultActionRunner` shell branch), not `runner_spec.py::_run_cmd()`, is the `bash -c` path FSM loops use. Added `fsm/evaluators.py` host-CLI spawns and `cli/loop/_helpers.py` launcher re-exec. Re-derived the census over `subprocess.*` instead of `os.environ.copy()`: 12 explicit sites (was 8), 145 total spawn sites, implicit inheritance dominant.
- `/ll:confidence-check` - 2026-08-15T20:37:09 - `418ba343-3272-4147-b043-1745e73ae713.jsonl`
- `/ll:refine-issue` - 2026-08-15T19:46:44 - `ccda3253-f4ab-44ac-a167-7fd374e66499.jsonl`
- Pre-implementation review - 2026-08-15 - corrected the `build_streaming` signature (9 kwargs, not 3) and ruled out threading scope through `build_*()`; scoped projection to declared specs only; replaced the guessed baseline with an empirically-derived one; named the disk-backed-credential limitation.

## Resolution

Implemented `project_child_env()` in `host_runner.py` exactly per the Program
Design signature and routed every task-path spawn through it (AC1). Re-verified
the census against the tree at implementation time and found one further drift
beyond the five prior passes: `init/install_check.py` carries **5** spawn sites
(2 `pip` introspection calls plus the 3 already-known host-CLI probes), not the
single site the body's per-module table implied — corrected in the AC2 guard's
pinned table, all 5 exempted by marker (none need projection).

- AC1: `project_child_env(invocation=None, *, extra=None)` lands in
  `host_runner.py` adjacent to `_apply_automation_env()`.
- AC2: `scripts/tests/test_enh3184_spawn_site_guard.py` — an AST-based guard
  (not a `subprocess.run`-regex or `os.environ.copy()`-shaped one) enumerating
  every `subprocess.(run|Popen|check_output|call)` site across the 18-module
  task-path list, asserting each is either routed through the helper or
  carries a `# ll-no-project: <reason>` marker, with an exact pinned
  (spawn-count, marker-count) table per module. 49 spawns total, 21 routed, 28
  exempted.
- AC3: `fsm/evaluators.py:1146/1360/1612` now merge `invocation.env`;
  `evaluators.py:644` (`git diff --stat`) is exempted by marker. Delta test in
  `test_fsm_evaluators.py` asserts the two `build_blocking_json()` keys land
  and `LL_AUTOMATION` is untouched.
- AC4: `runner_spec.py::_run_prompt()` now merges `invocation.env` (previously
  discarded it entirely), matching `_run_skill()`. Delta test in
  `test_runner_spec.py`.
- AC5: `cli/loop/_helpers.py:1659,2101` route through the helper; a code
  comment states the no-cross-`execve`-guarantee decision inline.
- AC6: `TestProjectChildEnvCrossRunnerParity` (6 implemented runners) +
  `TestProjectChildEnvStubRunnersRaiseFirst` (OpenCodeRunner/PiRunner) in
  `test_host_runner.py`. Full suite: 19517 passed, 46 skipped, 0 failed.
- AC7: `cli/issues/decisions.py:811` now merges `invocation.env` (previously
  passed no `env=` at all). Delta test in `test_cli_decisions.py`.

One addition beyond the pinned census: `parallel/worker_pool.py`'s
`ll-loop run proof-first-task` self-spawn (a declared-action launch, not git
plumbing) was routed through the helper rather than exempted, since it fits
the task-path rule cleanly.

## Status

**Open** | Created: 2026-08-15 | Priority: P2
