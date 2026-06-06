---
id: EPIC-1978
title: CLI-first init — headless core with thin frontends
type: epic
status: open
priority: P2
discovered_date: 2026-06-05
discovered_by: capture-issue
relates_to: [EPIC-1463, EPIC-1622, FEAT-1475]
labels: [epic, init, cli, host-compat, dx]
---

# EPIC-1978: CLI-first init — headless core with thin frontends

## Summary

The current `/ll:init` skill is a ~1,250-line procedural script written in
English prose (`skills/init/SKILL.md` 500 lines + `interactive.md` 925 lines +
`templates.md` 328 lines) for an LLM to interpret step-by-step. A
step-by-step classification of all 12 steps plus the 12-round interactive
wizard found **essentially zero genuine LLM judgment** in the flow — every
step is deterministic: glob-based project detection, JSON template transforms,
`which` PATH checks, version compares, idempotent file appends, and menu
prompts.

Hosting a deterministic procedure inside an LLM interpreter is the worst-case
trade: slow, token-expensive, and unreliable. The unreliability is visible in
the skill's own defensive prose — e.g. Round 6's "**CRITICAL**: You MUST
execute this round… If you skipped here, **GO BACK and ask it now.**" That
scaffolding exists because the LLM drops steps. A Python implementation never
does.

This epic extracts the entire init procedure into a **headless Python core**
with two thin frontends, and deprecates the prose skill to a redirect stub.

## Motivation

Three drivers converge:

1. **First-run DX.** `/ll:init` is too long and off-putting to first-time
   users (a 12-round wizard interpreted token-by-token). A native terminal
   TUI (`questionary`/`rich`) with multi-select is dramatically faster and is
   the natural first-run surface — users are already in a terminal right after
   `pip install`.
2. **Host multi-select.** With Codex (EPIC-1463) and Pi (EPIC-1622) adapters
   landing, host selection (Claude Code / Codex / Pi) is a first-class init
   choice with install-time consequences (which adapter files to write). That
   seam is shared across both epics and belongs in one place.
3. **Correctness + maintenance.** A single tested Python core removes the
   step-dropping failure class and prevents the two-implementation drift that
   "keep both" would cause.

## Architecture

Headless core + two dumb frontends. Logic lives **once**, in Python:

```
ll-init (Python package under scripts/little_loops/)
├── core: detect_project_type(), build_config(), validate_deps(),
│         install_codex_adapter(), merge_settings(), write_config(),
│         update_gitignore(), update_claude_md()
│         — all programmatic; unit-tested once
├── ll-init                       → questionary/rich TUI (terminal frontend)
├── ll-init --yes / --force / …   → non-interactive flags (CI / scripted)
├── ll-init --plan                → emits JSON {detected, proposed_config, host_options}
└── ll-init apply --config <json> → performs the writes
```

The `/ll:init` skill is **deprecated to a redirect stub** (ENH-1982): instead
of 1,250 lines of prose, it either runs `ll-init --yes` non-interactively or
prints "run `ll-init` in your terminal for guided setup." This preserves an
in-session entry point (typing `/ll:init` still does something sensible)
without maintaining a parallel prose implementation.

Prior art to lean on: `ll-doctor` (host capability detection) and
`host_runner.resolve_host()` (host selection) already exist in Python.

## Design Decisions (this capture)

- **Deprecate the skill entirely** (user decision 2026-06-05). The skill
  becomes a thin redirect (ENH-1982), not a `--plan`/`apply` wrapper. Rationale:
  the in-session interactive path requires a real PTY that the host `!`-prefix
  cannot reliably provide; first-run almost always happens in a terminal where
  `ll-init` runs natively. The `--plan`/`apply` JSON contract is still built
  (FEAT-1979) so a future wrapper is possible, but is not wired into the skill
  now.

## Children

- **FEAT-1979** — Extract init logic into a headless `ll-init` Python core
  (detection, config generation, dependency validation, settings/gitignore/
  CLAUDE.md merges, `--plan`/`apply`/`--yes` non-interactive entry points;
  full unit coverage).
- **FEAT-1980** — `ll-init` interactive terminal TUI (questionary/rich
  multi-select for features; progress; confirmation summary) over the
  FEAT-1979 core.
- **FEAT-1981** — Host multi-select wiring: Claude Code / Codex / Pi selection
  in `ll-init`, dispatching to the correct adapter install (relates to
  EPIC-1463 Codex install path and EPIC-1622 Pi `/ll:init --pi` / FEAT-1475).
- **ENH-1982** — Deprecate `/ll:init` skill to a redirect stub; delete
  `interactive.md` prose flow once parity is verified.

## Scope

**In scope:**
- New `ll-init` console entry point in `scripts/pyproject.toml`.
- Port of all 12 skill steps + wizard rounds into tested Python functions.
- Terminal TUI with host + feature multi-select.
- Skill deprecation to a redirect stub.
- Docs: README install flow, HOST_COMPATIBILITY, CLAUDE.md CLI tool list.

**Out of scope:**
- New configuration options beyond what `/ll:init` already collects (parity
  first; net-new config is a follow-up).
- Codex/Pi adapter *implementation* (owned by EPIC-1463 / EPIC-1622); this
  epic only wires host selection to whatever install paths those provide.

## Success Criteria

- `ll-init` produces a byte-equivalent `.ll/ll-config.json` to `/ll:init` for
  the same inputs (parity test across all 9 project-type templates).
- Time-to-configured for a first-time user drops from a multi-round LLM
  wizard to a single TUI screen.
- The init procedure has unit tests (detection, generation, merges) — a class
  of correctness that prose-in-LLM could not have.
- `/ll:init` no longer contains a parallel implementation; one source of truth.
- Host selection (Claude Code / Codex / Pi) is a single multi-select that
  drives adapter install.

## Integration Map

### Files to Create
- `scripts/little_loops/init/` — core module (detection, config, validators,
  writers) + TUI frontend.
- `scripts/tests/test_init_core.py` — parity + unit tests.

### Files to Modify
- `scripts/pyproject.toml` — `ll-init` console script entry point.
- `skills/init/SKILL.md` — collapse to redirect stub (ENH-1982); remove
  `interactive.md`.
- `templates/` — read by the core instead of by prose (no template changes;
  consumer moves).
- `docs/reference/HOST_COMPATIBILITY.md` — note `ll-init` as the install path.
- `.claude/CLAUDE.md` — add `ll-init` to the CLI Tools list.
- `README.md` — first-run flow becomes `pip install … && ll-init`.

### Dependent Files
- `scripts/little_loops/host_runner.py` — reuse `resolve_host()` for host
  detection defaults.
- `ll-doctor` — share capability-detection helpers where they overlap.

## Impact

- **Priority**: P2 — first-run DX is a direct adoption lever, and the host
  seam unblocks clean Codex/Pi install. Above the P5 tracking epics it relates
  to because this is active product work, not deferred tracking.
- **Effort**: Large (aggregate) — core extraction is Medium-Large; TUI,
  host-wiring, and deprecation are Small-Medium each.
- **Risk**: Medium — parity with the existing skill must be exact or users get
  different configs than before; mitigated by a byte-equivalence parity test.
- **Breaking Change**: Soft — `/ll:init` behavior changes (redirect), but the
  produced config is unchanged.

## Related Key Documentation

| Document | Why relevant |
| --- | --- |
| [skills/init/SKILL.md](../../skills/init/SKILL.md) | The procedure being ported; source of parity truth. |
| [docs/reference/HOST_COMPATIBILITY.md](../../docs/reference/HOST_COMPATIBILITY.md) | Host matrix the multi-select drives. |
| [EPIC-1463](P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md) | Codex install path host selection feeds. |
| [EPIC-1622](P5-EPIC-1622-pi-adapter-remaining-work.md) | Pi `/ll:init --pi` / FEAT-1475 host selection feeds. |

## Labels

`epic`, `init`, `cli`, `host-compat`, `dx`

## Status

**Open** | Created: 2026-06-05 | Priority: P2
