---
id: ENH-3642
type: ENH
title: Built-in Codex model_hint mapping via host-default model and reasoning effort
priority: P3
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T20:53:36Z'
parent: EPIC-3563
labels:
- multi-host
deferred_by: human
deferred_date: '2026-09-28T20:53:42Z'
---

# ENH-3642: Built-in Codex model_hint mapping via host-default model and reasoning effort

## Summary

Give Codex a built-in `model_hint` mapping that never names a concrete model: use the Codex host-default model and vary reasoning effort (`reasoning` → high, `burst` → low, `coding` → host default). Deferred until a shipped loop actually declares `model_hint`; starts with a spike.

## Current Behavior

`_BUILTIN_HINT_MAPPINGS` (`little_loops.host_runner`) covers only `claude-code` and the test-only fake hosts. On `codex`, `resolve_model_hint` raises `ModelHintError` unless `orchestration.model_hints.codex.<hint>` is set, so a hint-declaring loop cannot run on Codex without a config edit. EPIC-3563 excluded non-Claude built-ins because concrete Codex IDs churn (e.g. `gpt-5.5` retires 2026-10-14) and cannot be verified in this repo. ENH-3533's generated Codex agent mirrors get "model omitted + warning" for the same reason.

## Expected Behavior

With no user config, a hint on Codex resolves to a selection the host owns and keeps stable:

| Hint | Codex selection |
|---|---|
| `coding` | host default model, host default effort |
| `reasoning` | host default model, `model_reasoning_effort = "high"` |
| `burst` | decided by the spike — low effort on the default model, or stays config-only |

No concrete Codex model ID ships in little-loops. User config (`orchestration.model_hints.codex`) still wins per hint. Selection diagnostics (ENH-3547 event payload, ENH-3638 header/`ll-loop show`) report the source as `builtin-effort` (or equivalent) so users can see the model was not pinned.

## Motivation

Second-opinion consult on 2026-09-28 (Fable 5.1 via `/ll:advise`, confidence 0.8) recommended this over runtime catalog probes or a models.dev lookup: it removes the config step for Codex while keeping resolution deterministic and offline. Research found no shared cross-tool role registry; tools that do role selection (opencode, Crush) still hard-code role lists over their catalogs, so a catalog alone does not solve it.

## Proposed Solution

After the spike confirms (1):

- Add a Codex entry that maps hints to effort-only selections (no model), with `coding` meaning "no override".
- Extend `CodexRunner.build_streaming` / `build_blocking_json` to forward effort as `-c model_reasoning_effort=...` alongside the existing `--model` forwarding.
- `ll-verify-host-map` coverage for the new entry; argv tests beside the existing hint argv tests.
- `docs/reference/HOST_COMPATIBILITY.md`: document the semantic difference. `reasoning` is a different model on Claude Code but the same model at higher effort on Codex.

## Impact

- **Priority**: P3 — deferred until a shipped loop declares `model_hint`; until then, config plus the `ll-doctor` check covers Codex users.
- **Effort**: Medium — the spike, plus a return-type change that crosses `resolve_model_hint` callers.
- **Risk**: Medium — users may assume `reasoning` means the same thing on every host; mitigated by docs and diagnostics.
- **Breaking Change**: No, if the return-type change keeps existing callers working.

## Open Questions (spike)

1. Does `codex exec -c model_reasoning_effort=<level>` (and `codex exec resume`) accept the override on the streaming and blocking paths `CodexRunner` builds?
2. Can generated Codex agent TOML (`CodexEmitter.emit_agent`) express reasoning effort, so ENH-3533 mirrors can use this mapping instead of omitting?
3. **`burst` semantics**: low effort on the default model is not the same as a small, cheap model. Is it close enough for `burst`, or should `burst` stay config-only on Codex?
4. Where the effort lives: `resolve_model_hint` returns `str` today. Options: return a small selection dataclass (`model: str | None`, `effort: str | None`, `source: str`), or keep `str` and add a parallel effort resolver. The first touches every `resolve_model_hint` caller and the BUG-3529 `--model` forwarding.

## Scope Boundaries

- **In**: Codex CLI dispatch; mirrors only if spike question 2 is yes.
- **Out**: concrete Codex model IDs; runtime catalog probes (the catalog is used only by the `ll-doctor` model-hints check); Gemini (tier aliases unverified — separate issue if confirmed); other non-Claude hosts.

## Acceptance Criteria

- [ ] Spike answers questions 1–4 with evidence (argv run against the installed `codex` binary).
- [ ] A hint-declaring fixture loop runs on Codex with no `orchestration.model_hints` entry; argv shows the effort override and no `--model`.
- [ ] User config for a hint overrides the built-in effort mapping.
- [ ] Diagnostics show the selection source.
- [ ] HOST_COMPATIBILITY.md documents the model-vs-effort difference.

## Status

**Open** | Created: 2026-09-28 | Priority: P3
