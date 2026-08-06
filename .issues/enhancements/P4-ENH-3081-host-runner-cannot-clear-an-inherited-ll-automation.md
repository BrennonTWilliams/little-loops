---
id: ENH-3081
title: host_runner cannot clear an inherited LL_AUTOMATION, so an explicit opt-out
  is silently overridden
type: ENH
priority: P4
status: open
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-06
captured_at: '2026-08-06T00:35:00Z'
relates_to:
- ENH-2714
- BUG-3080
- BUG-3058
- BUG-2730
labels:
- automation
- host-runner
- hardening
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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
that implements `build_streaming` — `:351-353` (`ClaudeCodeRunner`), `:644-646`
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
`cli/history_context.py:198` (`if _os.environ.get("LL_AUTOMATION"):`). It also
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
`cli/history_context.py:198`, both via truthiness.

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

### Tests

- `scripts/tests/test_host_runner.py` — extend the existing assertion at
  `:965-966` with the inverse: with `automation_profile=None`, assert
  `invocation.env["LL_AUTOMATION"] == ""`, for at least the Claude Code and one
  non-Claude runner.
- A truthiness regression guard: assert both consumers treat `""` as "not under
  automation" (`hooks/session_start.py:110`, `cli/history_context.py:198`), so a
  later switch to a presence check (`"LL_AUTOMATION" in os.environ`) fails loudly
  rather than silently re-enabling the gate.

### Documentation

- `docs/ARCHITECTURE.md:777` and `docs/guides/LOOPS_GUIDE.md:628-632` — state the
  inheritance semantics and that `None` now clears.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Stale anchor**: `cli/history_context.py:198` (cited in Current Behavior and Program Design → Call Path) no longer resolves to the `LL_AUTOMATION` read — the current line is `cli/history_context.py:206` (`if _os.environ.get("LL_AUTOMATION"):`). The file has an uncommitted local diff at capture time; verify the anchor again before implementing in case it moves further.
- **Test coverage gap, precise**: the only existing `LL_AUTOMATION` assertion in `scripts/tests/test_host_runner.py` is `TestKimiRunner.test_automation_profile_env` (`:962-966`), covering Kimi's non-`None` branch only. No equivalent test exists for `ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, or `OmpRunner`, and no test in the file calls `build_streaming(automation_profile=None)` for any runner — the `None` branch is untested tree-wide today, not just for the regression this issue adds.
- **Truthiness convention confirmed at both consumers**: `hooks/session_start.py:110` (`bool(_os.environ.get("LL_AUTOMATION"))`) and `cli/history_context.py:206` both read via bare truthiness, never `"LL_AUTOMATION" in os.environ`. No consumer anywhere in the tree does a presence check on this var.

## Acceptance Criteria

_Added 2026-08-06 during pre-implementation review — this issue previously had none._

- [ ] A single module-level `_apply_automation_env(env, automation_profile)` helper exists
      in `host_runner.py` and is called from all five `build_streaming` bodies
      (`ClaudeCodeRunner`, `CodexRunner`, `GeminiRunner`, `OmpRunner`, `KimiRunner`); none
      of the five retains its own inline `if automation_profile is not None:` block.
- [ ] With `automation_profile=None`, `invocation.env["LL_AUTOMATION"] == ""` and
      `invocation.env["LL_AUTOMATION_PROFILE"] == ""` — the keys are **present and empty**,
      not absent, since absence means "inherit" at every merge site.
- [ ] With a non-`None` profile, behavior is unchanged: `"1"` and the profile string.
- [ ] Both branches are tested for at least `ClaudeCodeRunner` and one non-Claude runner.
      Note the `None` branch is untested tree-wide today — the only existing assertion is
      `TestKimiRunner.test_automation_profile_env` (`test_host_runner.py:962-966`), which
      covers Kimi's non-`None` branch only.
- [ ] A truthiness regression guard asserts both consumers treat `""` as "not under
      automation" (`hooks/session_start.py:110`, `cli/history_context.py:~206`), so a later
      switch to a presence check (`"LL_AUTOMATION" in os.environ`) fails loudly instead of
      silently inverting the gate. This is the AC that matters most: the whole approach
      rests on an implicit contract that nothing currently asserts.
- [ ] `LL_AUTOMATION_PROFILE` is either dropped or carries a comment at its assignment site
      stating it has zero runtime readers and is informational only.
- [ ] `docs/ARCHITECTURE.md:777` and `docs/guides/LOOPS_GUIDE.md:628-632` state the
      inheritance semantics and that `None` now clears.
- [ ] `python -m pytest scripts/tests/` exits 0.

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

- ENH-2714 — introduced `automation_profile` and never specified opt-out
  semantics.
- BUG-3080 — the other residual from the same investigation.
- BUG-3058 — found the `ll-auto` path missing `automation_profile` entirely; the
  drift that motivates factoring the five blocks into one helper.

## Status

- [ ] Not started


## Session Log
- `/ll:refine-issue` - 2026-08-06T17:43:47 - `dd5c238a-0e0c-4810-a3f6-b5d2f810c62d.jsonl`
