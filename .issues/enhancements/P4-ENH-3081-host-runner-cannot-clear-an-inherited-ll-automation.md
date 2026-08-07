---
id: ENH-3081
title: host_runner cannot clear an inherited LL_AUTOMATION, so an explicit opt-out
  is silently overridden
type: ENH
priority: P4
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-06
captured_at: '2026-08-06T00:35:00Z'
completed_at: '2026-08-07T00:22:43Z'
relates_to:
- ENH-2714
- BUG-3080
- BUG-3058
- BUG-2730
labels:
- automation
- host-runner
- hardening
confidence_score: 100
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
learning_tests_required:
- subprocess
---

# ENH-3081: `host_runner` cannot clear an inherited `LL_AUTOMATION`, so an explicit opt-out is silently overridden

## Summary

`LL_AUTOMATION` is a plain process env var exported into the child environment of
every host-CLI invocation that passes `automation_profile`. Every descendant of
that child inherits it, and **nothing in the tree ever unsets it**. A caller that
deliberately passes `automation_profile=None` — an explicit "this invocation is
not an automation invocation" — does not get that: it silently inherits whatever
its ancestor set.

`ll-parallel` is the concrete case. Nothing under
`scripts/little_loops/parallel/` mentions the parameter at all — verified by
`grep -r automation_profile scripts/little_loops/parallel/`, which returns
nothing — so its worker spawn path (`_run_claude_command` in
`parallel/worker_pool.py`) never opts in. But an `ll-parallel` invoked *from
inside* an automation-spawned session inherits `LL_AUTOMATION=1` anyway, and its
workers prune on a signal their own code declined to set.

This is hardening, not a live user-facing bug — see Scope Boundaries for what was
checked and found clean.

## Current Behavior

Five sibling blocks in `scripts/little_loops/host_runner.py`, one per host class
with a *working* `build_streaming` — `:351-353` (`ClaudeCodeRunner`), `:644-646`
(`CodexRunner`), `:1036-1038` (`GeminiRunner`), `:1223-1225` (`OmpRunner`),
`:1418-1420` (`KimiRunner`) — all read:

```python
if automation_profile is not None:
    env["LL_AUTOMATION"] = "1"
    env["LL_AUTOMATION_PROFILE"] = automation_profile
```

There is no `else`. `HostInvocation.env` is then merged *over* the parent
environment at four spawn sites — `subprocess_utils.py:412-425`
(`os.environ.copy()` + `update`), `runner_spec.py:189`,
`fsm/handoff_handler.py:131`, `session_store/lifecycle.py:157` — so an absent key
means "inherit", never "clear".

Note the two non-`build_streaming` merge sites cannot carry the signal at all:
`handoff_handler.py:117` calls `build_detached(prompt=...)` and
`lifecycle.py:154` calls `build_blocking_json(...)`, neither of which accepts
`automation_profile`. They are merge sites for *other* keys; see Scope
Boundaries for the residual.

Confirmed absent tree-wide: `grep 'pop("LL_AUTOMATION"|LL_AUTOMATION"] = ""|delenv("LL_AUTOMATION"'`
over `scripts/little_loops/` returns nothing.

## Expected Behavior

`automation_profile=None` means this invocation is not under automation, and the
child sees `LL_AUTOMATION` unset — regardless of what the parent process carried.
Opting out is expressible.

## Proposed Solution

Give each of the five blocks an explicit `else` that neutralizes the inherited
value:

```python
if automation_profile is not None:
    env["LL_AUTOMATION"] = "1"
    env["LL_AUTOMATION_PROFILE"] = automation_profile
else:
    # Neutralize an inherited value: env is merged OVER os.environ, so
    # omitting the key means "inherit", not "clear".
    env["LL_AUTOMATION"] = ""
    env["LL_AUTOMATION_PROFILE"] = ""
```

Empty string is sufficient and is the lightest-touch option: both runtime
consumers test truthiness, not presence —
`hooks/session_start.py:110` (`bool(_os.environ.get("LL_AUTOMATION"))`) and
`cli/history_context.py:206` (`if _os.environ.get("LL_AUTOMATION"):`). It also
avoids threading a "delete this key" convention through the four merge sites,
which currently only understand `dict.update`.

Prefer factoring the repeated block into a small helper rather than editing the
same five lines five ways — they have already drifted once (BUG-3058 found the
`ll-auto` path missing the parameter entirely).

**Helper shape — decided: module-level free function.** Use
`_apply_automation_env(env, automation_profile)` at module scope in
`host_runner.py`, called from all five `build_streaming` bodies. This is a
deliberate departure from the file's only existing env-helper precedent
(`GeminiRunner._worktree_env`, a `@staticmethod` on one runner class reached
cross-class via a qualified `GeminiRunner._worktree_env(...)` call). That shape
is what left `ClaudeCodeRunner` and `CodexRunner` still carrying inline
duplicates — a helper owned by one of five equal peers has no natural home and
invites partial adoption. A module-level function has no such asymmetry and
matches the file's existing `_`-prefixed module helpers. Recorded here so this
is not re-litigated at review time.

While here: `LL_AUTOMATION_PROFILE` has **zero runtime readers** (confirmed
tree-wide; `fsm/schema.py:472` and `docs/guides/LOOPS_GUIDE.md:628` both call it
informational). Either document that clearly at the assignment site or drop it.
Not worth its own issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Existing de-duplication precedent**: `GeminiRunner._worktree_env` (`host_runner.py:965-982`) is the only existing example in this file of factoring a repeated per-runner env-setup block. It is a `@staticmethod` defined on one runner class (`GeminiRunner`), reused cross-class via a qualified call — `GeminiRunner._worktree_env(...)` from `OmpRunner.build_streaming` (`host_runner.py:1226`) and `KimiRunner.build_streaming` (`host_runner.py:1421`) — not a module-level free function. The file's existing module-level `_`-prefixed helpers (`_build_search_tool_entry`, `_remediation_hint`, `_active_oauth_token`, `_anthropic_client`, `_text_from_content_blocks`, `_usage_from_response` — `host_runner.py:1555, 1646, 1817, 1832, 1851, 1861`) never construct env dicts, so there is no existing module-level-helper precedent to match; the closer precedent is a classmethod-qualified staticmethod. Notably `ClaudeCodeRunner` and `CodexRunner` still carry inline duplicates of the same `_worktree_env` logic instead of calling it (`host_runner.py:354-362`, `647-655`) — this file already tolerates partial (3-of-5) de-duplication of a near-identical block, so a helper that only some runners adopt would not be an unprecedented state for this file.
- **No existing "clear via empty string" idiom**: confirmed by grep, no assignment in `host_runner.py`'s `HostInvocation.env` construction ever sets a key to `""` to neutralize an inherited value today (all current assignments are `"1"`, a profile string, or a path). The codebase's only existing "clear an env var" idiom is test-side and presence-based, not value-based: `monkeypatch.delenv(VAR_NAME, raising=False)` (117 occurrences across 28 test files, e.g. `scripts/tests/test_host_runner.py:44-47`), which deletes the key from `os.environ` rather than emptying it. The empty-string approach this issue proposes is a genuinely new pattern for this file, not modeled on an existing one.

## Scope Boundaries

**In scope:** making `automation_profile=None` clear rather than inherit, at the
five `host_runner` blocks; the `LL_AUTOMATION_PROFILE` comment or removal.

**Out of scope / verified clean:**

- **FSM shell actions.** The obvious worry — `autodev.yaml:844` shelling out to
  `ll-auto --only` inside a loop that declares `pruning_profile` — is *not*
  affected. That is `action_type: shell`, run by the FSM executor process, and
  the executor itself never carries `LL_AUTOMATION`; it only injects into
  host-CLI children. The nested `ll-auto` starts from a clean environment and
  sets its own profile. Do not "fix" this path.
- **The pytest false-red.** An automation-session agent running
  `python -m pytest scripts/tests/` saw 48 phantom failures from this
  inheritance. Already fixed test-side by scrubbing the var in
  `scripts/tests/conftest.py:725` and guarded by
  `test_hook_session_start.py::TestAmbientAutomationEnvHermeticity`.
- **Redesigning the signal** (depth counters, a scrub point at session
  boundaries, making it an invocation argument rather than an env var). The
  reachable surface does not justify it today.
- **`OpenCodeRunner` / `PiRunner`.** Both declare the `automation_profile` kwarg
  on `build_streaming` (`host_runner.py:808`, `:882`) but their bodies are
  `raise HostNotConfigured(...)` stubs (`:811`, `:885`) — there is no env dict to
  apply the helper to. Five, not seven, is correct; when either is wired it must
  call `_apply_automation_env`. Stated so a reviewer does not re-flag the count.

**Known residual (accepted, not fixed here):** the fix reaches only
`build_streaming`. `build_detached` and `build_blocking_json` take no
`automation_profile`, so they cannot express opt-out. An `ll-loop run` started
*from inside* an automation-spawned session carries `LL_AUTOMATION=1` in the FSM
executor process itself, and `handoff_handler.py:117-131` then spawns a detached
continuation with `env={**os.environ, **invocation.env}` — inheriting it with no
way to clear. This is narrower than the `ll-parallel` case (it needs a
human-in-an-automation-session entry point) and widening the kwarg to the other
two `build_*` methods is a larger change; file separately if it is ever
observed.

## Program Design

### Types

- `HostInvocation.env: dict[str, str]` — `scripts/little_loops/host_runner.py`.
  The type is the crux: a plain `dict[str, str]` merged via `dict.update` at
  every spawn site, so it can express "set to X" but has no representation for
  "remove this key". Empty string is the neutralization that fits the existing
  type rather than widening it to `dict[str, str | None]` and teaching four merge
  sites a delete convention.

### Signatures

- `ClaudeCodeRunner.build_streaming(..., automation_profile: str | None = None) -> HostInvocation`
  — `host_runner.py:297`, and the same trailing kwarg on `CodexRunner`,
  `GeminiRunner`, `OmpRunner`, `KimiRunner`. Signatures unchanged; only the body's
  `if automation_profile is not None:` block gains an `else`.
- New private helper, e.g.
  `_apply_automation_env(env: dict[str, str], automation_profile: str | None) -> None`
  — module-level in `host_runner.py`, called from all five `build_streaming`
  bodies in place of the duplicated block.

### Call Path

`build_streaming(...)` → `_apply_automation_env(env, automation_profile)` →
`HostInvocation.env` → merged over `os.environ` at
`subprocess_utils.py:412-425` (`os.environ.copy()` + `update`) →
child process → read by `hooks/session_start.py:110` and
`cli/history_context.py:206`, both via truthiness.

The `""` value therefore survives the merge as a present-but-falsy key, which
both consumers already treat as "not under automation". No consumer change is
required — which is exactly why the regression guard in the Tests section
matters: the behavior depends on an implicit truthiness contract that nothing
currently asserts.

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — the five blocks at `:351, :644, :1036,
  :1223, :1418`, ideally via one shared helper.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/worker_pool.py:885-935` — the worker spawn path
  whose deliberate non-opt-in this change makes real. It passes no
  `automation_profile`, so today it inherits.
- `scripts/little_loops/subprocess_utils.py:412-425`,
  `scripts/little_loops/runner_spec.py:189`,
  `scripts/little_loops/fsm/handoff_handler.py:131`,
  `scripts/little_loops/session_store/lifecycle.py:157` — the merge sites; all
  use `dict.update` semantics, which the empty-string approach relies on.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/learning_tests/extractor.py:135` — a fifth merge site
  (`env={**os.environ, **inv.env}`), same `dict.update` semantics; the `""`
  override reaches the child here too. [Agent 1 finding, verified]
- `scripts/little_loops/runner_spec.py:182` — direct caller of
  `resolve_host().build_streaming(..., automation_profile=automation_profile)`;
  defaults to `None` unless `spec.args` carries a profile. [Agent 1 finding,
  graph-confirmed]
- `scripts/little_loops/fsm/runners.py:51,110,191` — `ActionRunner` Protocol and
  `DefaultActionRunner.run()` forward `automation_profile` into
  `run_claude_command`; `SimulationActionRunner` declares but ignores it. [Agent 1
  finding, verified]
- `scripts/little_loops/issue_manager.py:217,349` — local `run_claude_command` /
  `run_with_continuation` wrappers forward `automation_profile`; the `ll-auto`
  paths hardcode `"ll-auto"` at `:1213` and `:1401` (non-`None`, unaffected).
  [Agent 1 finding, verified]
- `scripts/little_loops/fsm/executor.py:1902` — the non-`None` origin: sets
  `automation_profile` from the pruning-profile config when one is enabled. [Agent 1
  finding, verified]

### Tests

- `scripts/tests/test_host_runner.py` — extend the existing assertion at
  `:965-966` with the inverse: with `automation_profile=None`, assert
  `invocation.env["LL_AUTOMATION"] == ""`, for at least the Claude Code and one
  non-Claude runner.
- A truthiness regression guard: assert both consumers treat `""` as "not under
  automation" (`hooks/session_start.py:110`, `cli/history_context.py:198`), so a
  later switch to a presence check (`"LL_AUTOMATION" in os.environ`) fails loudly
  rather than silently re-enabling the gate.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_hook_session_start.py` — the SessionStart half of the
  truthiness regression guard: a `monkeypatch.setenv("LL_AUTOMATION", "")` variant
  of `TestAutomationPruningStayInTurn::test_no_automation_env_no_stay_in_turn_instruction`
  (`:579`), asserting `""` does not trigger the stay-in-turn instruction. [Agent 3
  finding]
- `scripts/tests/test_history_context_cli.py` — the history-context half of the
  guard: a `monkeypatch.setenv("LL_AUTOMATION", "")` variant asserting normal
  (non-pruned) output, mirroring `TestArgumentParsing::test_issue_id_accepted`
  (`:63`). [Agent 3 finding]
- `scripts/tests/test_subprocess_utils.py` — a new override regression test
  anchored on `test_invocation_env_overrides_os_environ` (`:2371-2403`): assert
  `LL_AUTOMATION=""` in `invocation.env` beats an ambient
  `os.environ["LL_AUTOMATION"]="1"` through the real `subprocess_utils.py:412-413`
  merge. No existing test asserts the empty-string semantics anywhere; no existing
  test breaks (verified: no presence-based absence assertion on the var tree-wide).
  [Agent 2/3 findings]

### Documentation

- `docs/ARCHITECTURE.md:777` and `docs/guides/LOOPS_GUIDE.md:628-632` — state the
  inheritance semantics and that `None` now clears.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Stale anchor**: `cli/history_context.py:198` (cited in Current Behavior and Program Design → Call Path) no longer resolves to the `LL_AUTOMATION` read — the current line is `cli/history_context.py:206` (`if _os.environ.get("LL_AUTOMATION"):`). The file has an uncommitted local diff at capture time; verify the anchor again before implementing in case it moves further.
- **Test coverage gap, precise**: the only existing `LL_AUTOMATION` assertion in `scripts/tests/test_host_runner.py` is `TestKimiRunner.test_automation_profile_env` (`:962-966`), covering Kimi's non-`None` branch only. No equivalent test exists for `ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, or `OmpRunner`, and no test in the file calls `build_streaming(automation_profile=None)` for any runner — the `None` branch is untested tree-wide today, not just for the regression this issue adds.
- **Truthiness convention confirmed at both consumers**: `hooks/session_start.py:110` (`bool(_os.environ.get("LL_AUTOMATION"))`) and `cli/history_context.py:206` both read via bare truthiness, never `"LL_AUTOMATION" in os.environ`. No consumer anywhere in the tree does a presence check on this var.

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `host_runner.py:233-237` — `ClaudeCodeRunner.build_streaming` docstring
  states "`None` (the default) preserves full unpruned behavior"; reword to reflect
  that `None` now actively clears an inherited `LL_AUTOMATION`. The other four
  runners carry no such prose, so this is the only in-file docstring to touch.
  [Agent 2/3 findings, verified]
- Update `subprocess_utils.py:364-367` — `run_claude_command` docstring repeats the
  same "None (default) preserves full unpruned behavior" phrasing on the chokepoint
  through which every `build_streaming` caller funnels; align it. [Agent 2 finding]
- Update `config/features.py:1033-1044` — `AutomationPruningConfig` docstring
  claims the env var "is only ever set by a loop/state that explicitly declares a
  `pruning_profile`"; the `else` branch makes this technically false (a `None`
  invocation now also sets it, to `""`). Mark as staleness. [Agent 2 finding,
  verified]
- Grouped informational alignment (forwarder docstrings with the same
  "None preserves full unpruned behavior" phrasing, lower value): `runner_spec.py:124-127`,
  `fsm/schema.py:452-453`, `issue_manager.py:172,300`, `fsm/runners.py:67,127`.
  [Agent 2 finding]
- Add the two consumer regression guards — `test_hook_session_start.py` and
  `test_history_context_cli.py` (see Integration Map → Tests for anchors).
  [Agent 3 finding]
- Add the override regression test in `test_subprocess_utils.py` (see Integration
  Map → Tests). [Agent 2/3 finding]
- Note on the `LL_AUTOMATION_PROFILE` drop option: if the "drop it" branch of the
  Proposed Solution is chosen, `test_host_runner.py:966` (`env["LL_AUTOMATION_PROFILE"] == "autodev"`)
  fails and must be updated; the informational readers `fsm/schema.py:472`,
  `docs/ARCHITECTURE.md:777`, `docs/guides/LOOPS_GUIDE.md:628`,
  `fsm-loop-schema.json:403`, `config/features.py:1038`, and the
  `host_runner.py:468` capability string all go stale. [Agent 2 finding]

## Acceptance Criteria

_Added 2026-08-06 during pre-implementation review — this issue previously had none._

- [x] A single module-level `_apply_automation_env(env, automation_profile)` helper exists
      in `host_runner.py` and is called from all five `build_streaming` bodies
      (`ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`); none
      of the five retains its own inline `if automation_profile is not None:` block.
- [x] With `automation_profile=None`, `invocation.env["LL_AUTOMATION"] == ""` and
      `invocation.env["LL_AUTOMATION_PROFILE"] == ""` — the keys are **present and empty**,
      not absent, since absence means "inherit" at every merge site.
- [x] With a non-`None` profile, behavior is unchanged: `"1"` and the profile string.
- [x] Both branches are tested **parametrized over all five implemented runners**, not just
      `ClaudeCodeRunner` plus one other. The whole point of the helper is that the five
      stop drifting (BUG-3058 precedent); a table-driven test is the thing that enforces
      it, and per-runner spot checks are what let the drift happen in the first place.
      Note the `None` branch is untested tree-wide today — the only existing assertion is
      `TestKimiRunner.test_automation_profile_env` (`test_host_runner.py:962-966`), which
      covers Kimi's non-`None` branch only.
- [x] A truthiness regression guard asserts both consumers treat `""` as "not under
      automation" (`hooks/session_start.py:110`, `cli/history_context.py:~206`), so a later
      switch to a presence check (`"LL_AUTOMATION" in os.environ`) fails loudly instead of
      silently inverting the gate. This is the AC that matters most: the whole approach
      rests on an implicit contract that nothing currently asserts.
- [x] `LL_AUTOMATION_PROFILE` is either dropped or carries a comment at its assignment site
      stating it has zero runtime readers and is informational only.
- [x] `docs/ARCHITECTURE.md:777` and `docs/guides/LOOPS_GUIDE.md:628-632` state the
      inheritance semantics and that `None` now clears.
- [x] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P4 — latent. The one observed symptom is already fixed at the
  test layer, and the highest-traffic nesting path (FSM shell actions) was
  verified clean. This closes the gap before it is rediscovered the expensive way.
- **Effort**: Small — five blocks (or one helper) plus tests.
- **Risk**: Low, with one thing to check: any consumer added later that tests
  *presence* rather than truthiness would read `""` as "under automation" —
  exactly backwards. The regression guard above exists for that.
- **Breaking Change**: No.

## Related Issues

- **FEAT-3078 (open, P3) — sequencing conflict, implement ENH-3081 first.** It
  injects `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` into *the same*
  `if automation_profile is not None:` block, anchored on `host_runner.py:351`
  and explicitly designed to "mirror the existing `LL_AUTOMATION` gate"
  (FEAT-3078 Integration Map, `:85`, `:125`, `:128`). This issue's helper
  refactor deletes those five anchors. Landing ENH-3081 first turns FEAT-3078
  into a one-site change inside `_apply_automation_env` and gets it the same
  five-way de-duplication for free. The helper's `else` branch must then clear
  that var too — the same "absent means inherit" trap applies to it, and
  FEAT-3078 already adds it to `conftest.py`'s `_CMD_RUN_ENV_VARS` for the same
  leak reason. Landing them in the other order means rewriting FEAT-3078's work.
  (FEAT-3060, which covered similar ground, is already `done`.)
- ENH-2714 — introduced `automation_profile` and never specified opt-out
  semantics.
- BUG-3080 — the other residual from the same investigation.
- BUG-3058 — found the `ll-auto` path missing `automation_profile` entirely; the
  drift that motivates factoring the five blocks into one helper.

## Status

- [x] Completed

---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/host_runner.py`: added module-level `_apply_automation_env(env, automation_profile)`; replaced the five inline `if automation_profile is not None:` blocks; `automation_profile=None` now sets `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` to `""` (present-but-falsy) instead of inheriting; aligned the `ClaudeCodeRunner.build_streaming` docstring.
- `scripts/little_loops/subprocess_utils.py`: aligned `run_claude_command` docstring to the clear-on-`None` semantics.
- `scripts/little_loops/config/features.py`: fixed `AutomationPruningConfig` docstring claim (gate only fires for a declared profile; non-profile invocations clear the var).
- `scripts/tests/test_host_runner.py`: added `TestAutomationProfileEnvAcrossRunners` parametrized over all five implemented runners (None + non-None branches).
- `scripts/tests/test_hook_session_start.py`: added `test_empty_automation_env_no_stay_in_turn_instruction` (truthiness contract guard).
- `scripts/tests/test_history_context_cli.py`: added `test_empty_automation_env_produces_normal_output`.
- `scripts/tests/test_subprocess_utils.py`: added `test_empty_ll_automation_beats_ambient_env` (empty string survives the `os.environ.copy()` + `update` merge).
- `docs/ARCHITECTURE.md`, `docs/guides/LOOPS_GUIDE.md`: stated the inheritance semantics and that `None` now clears.
- `.ll/learning-tests/subprocess.md` + `raw/subprocess.txt`: subprocess learning-test proofs (required by frontmatter).

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 18547 passed, 42 skipped)
- Lint: PASS (`ruff check scripts/`)
- Types: PASS (`python -m mypy scripts/little_loops/`)
- Run: N/A (no run_cmd configured)
- Integration: PASS

## Session Log
- `/ll:manage-issue` - 2026-08-07T00:22:30 - `7c76dd26-508d-4cc0-8dc8-7d2ece77d79c.jsonl`
- `/ll:ready-issue` - 2026-08-07T00:03:18 - `8fe5cd0c-ae9a-40c7-b66e-843cc40108ef.jsonl`
- `/ll:confidence-check` - 2026-08-06T23:56:43 - `cd39e386-0e9d-4e2e-a5cb-0aa73d654b4e.jsonl`
- `/ll:confidence-check` - 2026-08-06T23:47:43 - `9dddd4da-429b-461f-b860-d4714848c4b0.jsonl`
- `/ll:wire-issue` - 2026-08-06T23:27:05 - `304efef5-84e8-4f90-bcb1-2c715d8e2940.jsonl`
- `/ll:refine-issue` - 2026-08-06T17:43:47 - `dd5c238a-0e0c-4810-a3f6-b5d2f810c62d.jsonl`
