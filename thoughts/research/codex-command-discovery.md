# Codex CLI Slash-Command and Skill Discovery

**Status:** Research complete — Codex Skills API **confirmed stable**
**Last verified:** 2026-05-15
**Research issue:** FEAT-1483
**Codex version:** npm-installed v0.x (Rust-based GA release, not deprecated Node version)

## Sources

- `codex --help` output (locally installed via npm on dev host)
- `~/.codex/` directory inspection
- `codex plugin --help` and `codex plugin marketplace --help`
- `hooks/adapters/codex/README.md` — existing trust model documentation
- `docs/reference/HOST_COMPATIBILITY.md` — prior `[^cmds]` footnote (now revised)

## Discovery API: `~/.codex/skills/`

Codex has a native **Skills** extensibility system. The research question has a definitive answer: **YES, a plugin/command API exists and is marked stable.**

### Feature flags (as of research date)

| Feature          | Status              |
| ---------------- | ------------------- |
| `plugins`        | **stable**          |
| `hooks`          | **stable**          |
| `plugin_hooks`   | under development   |

### Skills directory layout

```
~/.codex/skills/
└── <skill-name>/
    ├── SKILL.md              # required — frontmatter + body
    ├── agents/
    │   └── openai.yaml       # recommended — UI metadata
    ├── scripts/              # optional — bundled scripts
    ├── references/           # optional — reference materials
    └── assets/               # optional — icons, images
```

### `SKILL.md` frontmatter (required fields)

```yaml
name: skill-name          # required; slug identifier; no Claude Code equivalent
description: >
  When and why Codex activates this skill.
  Used by the Codex agent to decide when to inject the skill body.
metadata:
  short-description: One-line chip label shown in the Codex TUI
```

Body: Markdown instructions injected into context when the skill triggers.

### `agents/openai.yaml` (recommended)

```yaml
interface:
  display_name: "Human-Readable Name"
  short_description: "One-line chip label"
  icon_small: "./assets/icon-small.svg"
  icon_large: "./assets/icon.png"
```

### Installation methods

| Method                                           | Notes                                              |
| ------------------------------------------------ | -------------------------------------------------- |
| `codex plugin marketplace add <source>`          | Supports `owner/repo[@ref]`, HTTP/HTTPS Git, SSH, local dirs |
| `--sparse <PATH>` flag                           | Install a subtree (e.g., a single skill) from a larger repo |
| Built-in `skill-installer` skill                 | `scripts/install-skill-from-github.py --repo <owner>/<repo> --path <path>` |
| Manual copy to `~/.codex/skills/<name>/`         | Works; requires Codex restart to pick up           |

After installation, the user must **restart Codex** to pick up new skills.

Skills install to `$CODEX_HOME/skills/<skill-name>` (default `~/.codex/skills`).

## No `.codex/prompts/` slash-command surface

**Finding**: No `~/.codex/prompts/` directory exists on the dev host. The
`codex --help` output and `~/.codex/config.toml` have no `prompts`-related
configuration. The `[^cmds]` footnote in `HOST_COMPATIBILITY.md` (prior to
this revision) referenced `.codex/prompts/` as a Codex command path — this
was speculative/incorrect. The Skills API (`~/.codex/skills/`) is the actual
extensibility surface for both "commands" and "skill discovery."

There is no separate slash-command registration mechanism in Codex (analogous
to `.claude/commands/*.md`). Skills subsume both use-cases: a skill's
frontmatter `description` is the trigger hint (when to activate), and the body
is the instruction payload — functionally equivalent to a command definition.

## Compatibility gap: ll `skills/*/SKILL.md` vs. Codex `SKILL.md`

ll's existing SKILL.md frontmatter format and Codex's required format differ:

| Field              | ll `skills/*/SKILL.md`          | Codex `~/.codex/skills/*/SKILL.md` | Compatible? |
| ------------------ | ------------------------------- | ----------------------------------- | ----------- |
| `name:`            | absent (uses directory name)    | **required** — slug identifier      | ✗ — must add |
| `description:`     | present (≤100 chars, for UI listing) | present (free-form, used as trigger hint) | ~✓ (same key, different semantics) |
| `argument-hint:`   | optional                        | not supported                       | N/A         |
| `allowed-tools:`   | optional                        | not supported                       | N/A         |
| `arguments:`       | optional                        | not supported                       | N/A         |
| `metadata.short-description:` | absent            | recommended (UI chip label)         | ✗ — should add |
| `agents/openai.yaml` | absent                        | recommended (UI display_name, icons)| ✗ — should add per skill |

**Key gap**: ll SKILL.md files lack the required `name:` field and the
recommended `metadata.short-description:` field. Adapting them requires:

1. Add `name:` to each `skills/*/SKILL.md` frontmatter (matches directory slug).
2. Add `metadata:\n  short-description:` to each skill's frontmatter (one-line label for TUI).
3. Add `agents/openai.yaml` per skill directory with `display_name` and `short_description`.
4. Register the skills directory via `codex plugin marketplace add BrennonTWilliams/little-loops --sparse skills`.

This work is tracked by **FEAT-1486** (child of EPIC-1463).

## Decision tree outcome

```
Codex has a plugin/command API?
└── YES → Skills API is confirmed stable (~/.codex/skills/<name>/SKILL.md)
    ├── FEAT-1486: Adapt ll skills/*/SKILL.md for Codex (add name:, agents/openai.yaml)
    └── FEAT-1487: Document that no .codex/prompts/ slash-command surface exists;
                   update HOST_COMPATIBILITY.md [^cmds] footnote
```

## Capability map

```python
# Codex Skills API capability addition (no code change needed in HostCapabilities yet;
# command_discovery flag deferred to FEAT-1486 implementation)
HostCapabilities(
    streaming=True,
    permission_skip=True,
    agent_select=False,
    tool_allowlist=False,
    # command_discovery: tracked as conditional in FEAT-1486
)
```

## Gating recommendation

Per the FEAT-1483 acceptance criteria:

- File **FEAT-1486** as child of EPIC-1463: adapt `skills/*/SKILL.md` for Codex
  (add `name:` + `agents/openai.yaml`; register via `codex plugin marketplace add`).
- File **FEAT-1487** as child of EPIC-1463: document the `.codex/prompts/` gap,
  update `HOST_COMPATIBILITY.md` parity matrix, and revise the `[^cmds]` footnote.
- The `HOST_COMPATIBILITY.md` Codex "Slash-command discovery" cell remains `✗`
  until FEAT-1487 resolves (Codex has no separate slash-command surface; skills
  cover both use cases). Codex "Skill discovery" cell remains `✗` until FEAT-1486
  is complete.
