---
id: BUG-2355
type: BUG
priority: P2
status: done
size: Small
captured_at: '2026-06-27T22:13:07Z'
discovered_date: 2026-06-27
discovered_by: manual
completed_at: '2026-06-27T22:13:07Z'
labels:
- learning-gate
- host-abstraction
- ll-auto
- auth
---

# BUG-2355: Learning gate's direct Anthropic SDK call crashes ll-auto on non-Anthropic hosts

## Summary

`ll-auto` aborted an entire backlog run with a fatal error **immediately after
Phase 1 (`ready-issue`) succeeded**, before Phase 2 could start:

```
[16:58:39] ready-issue verdict: READY
[16:58:39] Phase 1 (ready-issue) completed in 53.2 seconds
[16:58:39] Fatal error: "Could not resolve authentication method. Expected one of
            api_key, auth_token, or credentials to be set. ..."
[16:58:39] State file cleaned up
```

That error string is the **Anthropic Python SDK's** auth error, not a host-CLI
error. The run was driving a **non-Anthropic backend** (`model: MiniMax-M3[1m]`
in the log) with no `ANTHROPIC_API_KEY` in the environment. Reproduced from a
real `ll-auto --only "BUG-372,BUG-373,BUG-374,BUG-375"` run in a downstream
project (`cards`).

## Root cause

Between Phase 1 and Phase 2, `process_issue_inplace()` runs the learning gate
(`scripts/little_loops/issue_manager.py:854`):

```python
if config.learning_tests.enabled is True and not dry_run:
    targets = resolve_learning_targets(info)   # line 855
```

The issue had no `learning_tests_required` frontmatter (field is `None`), so
`resolve_learning_targets()` fell through to JIT extraction →
`extract_learning_targets()` → `_default_llm_call()` at
`scripts/little_loops/learning_tests/extractor.py:57-70`, which instantiated the
Anthropic SDK **directly**:

```python
def _default_llm_call(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic()                 # direct SDK, no host abstraction
    message = client.messages.create(
        model="claude-haiku-4-5-20251001", ...      # hardcoded Anthropic model
    )
```

This was the only non-host-aware LLM call in the automation path and it violated
the Host CLI Abstraction rule in `.claude/CLAUDE.md` ("All host CLI invocations
must go through `resolve_host()` … Never add new `claude` literals to automation
code"). Two distinct defects:

- **(A) Wrong backend.** Learning extraction ignored the configured host and
  always tried Anthropic — the auth crash on a non-Anthropic host, plus silently
  routing to the wrong model/backend even when an `ANTHROPIC_API_KEY` happened to
  be present.
- **(B) Fatal blast radius.** A best-effort safety-net step let an uncaught
  exception propagate through `resolve_learning_targets` → the call site →
  aborting the **entire** backlog run instead of degrading gracefully.

The shared `_default_llm_call` default path is also used by **ll-sprint**
pre-flight (`cli/sprint/run.py`) and **ll-parallel** (`parallel/worker_pool.py`),
so all three runners carried the defect.

## Changes

### Fix — `scripts/little_loops/learning_tests/extractor.py`

- Rewrote `_default_llm_call()` to be host-aware: it now shells out via
  `resolve_host().build_blocking_json(prompt=..., model=None)` + `subprocess.run`
  with `env={**os.environ, **inv.env}`, mirroring the established pattern in
  `session_store._call_llm_for_summary` (`session_store.py:1546`). It parses the
  JSON envelope and returns the prose `result` field (which still carries the
  `TARGETS_JSON:{...}` line that `_TARGETS_JSON_RE` scans downstream).
- `model=None` lets the host pick its own default model — a hardcoded Anthropic
  model id would fail against a MiniMax / codex / opencode / pi backend.
- **Fail soft:** any host-call or parse failure (`TimeoutExpired`,
  `FileNotFoundError`, non-zero exit, empty stdout, unparseable JSON) logs a
  warning and returns `""`. `extract_learning_targets()` already returns `[]`
  when the regex finds no match, so a failed extraction degrades the gate to "no
  targets" and the run continues to Phase 2 rather than crashing.
- Removed the direct `import anthropic`, added a module logger and
  `_LLM_TIMEOUT_S = 60`, added top-level imports (`os`, `subprocess`, `logging`,
  `resolve_host`), and updated the module docstring (no longer "SDK-direct").
- Public signatures of `extract_learning_targets()` / `resolve_learning_targets()`
  and their `llm_call` mock-injection seam are unchanged, so all existing callers
  and tests keep working.

### Regression guard tests — `scripts/tests/test_learning_tests_extractor.py`

Added a `TestDefaultLlmCall` class (existing `llm_call`-mock tests never exercised
`_default_llm_call`, so they were untouched):

- Success path returns the prose `result` and asserts it routes through
  `resolve_host().build_blocking_json` with `model=None` (host-aware, not the SDK).
- End-to-end `extract_learning_targets()` via the default path returns targets.
- Fail-soft guards: non-zero exit / `FileNotFoundError` / `TimeoutExpired` /
  unparseable stdout each return `""` and do **not** raise (the regression guard
  for the fatal-crash defect); a host failure degrades extraction to `[]`.

## Verification

- `python -m pytest scripts/tests/test_learning_tests_extractor.py scripts/tests/test_worker_pool.py scripts/tests/test_sprint_integration.py` → 173 passed.
- `python -m mypy scripts/little_loops/learning_tests/extractor.py` → clean.
- `ruff check` + `ruff format --check` on the changed files → clean.

## Notes / decisions

- **Fail-soft vs. fail-loud:** the learning gate is a best-effort
  proof-of-external-API safety net; aborting a whole backlog run because its LLM
  call failed is the wrong tradeoff. Degrading to "no targets" (with a logged
  warning) restores pre-gate behavior and matches how `_call_llm_for_summary`
  already handles host-call failures. If stricter behavior is ever wanted, it
  should be an explicit config/flag, not an unhandled exception.
- One fix in `_default_llm_call` covers ll-auto, ll-sprint, and ll-parallel,
  since they share the default extraction path.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-27T22:14:34 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `manual` - 2026-06-27T22:13:07Z - documented post-fix in this session
