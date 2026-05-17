# Research: Codex CLI Agent Selection Gap

**Date**: 2026-05-16  
**Issue**: ENH-1531  
**Verdict**: Gap is permanent at current Codex CLI surface. No workaround viable for ll orchestration.

---

## Summary

Codex CLI has no `--agent` flag or equivalent mechanism that lets a caller select a named `.codex/agents/*.toml` persona at invocation time. Every approach investigated either does not exist or is restricted to internal `spawn_agent` tool calls (subagent spawning within an existing session), not the root-session persona.

The gap is permanent until OpenAI ships the feature request (issue #10067), which has no assigned PR or timeline.

---

## Approaches Investigated

### 1. `--agent` CLI flag

**Does not exist.** The complete `codex exec` flag surface includes `--profile`, `--model`, `--config`, `--sandbox`, `--output-schema`, `--json`, `--full-auto`, `--ephemeral`, `--ignore-rules`, `--ignore-user-config`, and `--skip-git-repo-check`. There is no `--agent`, `--agent-file`, `--agents`, or `--persona` flag.

Feature request: [openai/codex#10067](https://github.com/openai/codex/issues/10067) — "Add `--agents <name>` flag to select named agent profile at invocation time." Filed January 28, 2026. No linked PR, no assignee.

**Verdict: N/A — flag does not exist.**

### 2. `--profile` flag

**Exists but wrong surface.** `--profile <name>` selects a named configuration profile from `~/.codex/config.toml`. Profile stanzas control model, sandbox, and `model_reasoning_effort` — not `developer_instructions` or persona. There is no `developer_instructions` key under a profile.

```toml
[profiles.deep-review]
model = "gpt-5-pro"
model_reasoning_effort = "high"
approval_policy = "never"
# no developer_instructions — wrong surface
```

`profiles.<name>.model_instructions_file` is a documented key that could point to a different instructions file per profile — but it requires users to pre-define profiles in their `~/.codex/config.toml`, which is not a per-project mechanism and cannot be injected programmatically by `CodexRunner`.

**Verdict: Not viable for ll orchestration.**

### 3. `CODEX_AGENT` / `CODEX_PROFILE` environment variables

**Do not exist.** No `CODEX_AGENT`, `CODEX_PROFILE`, or similar env-var appears in any official Codex CLI documentation page (CLI reference, config-basic, config-reference, config-advanced). The only environment-level override is `CODEX_HOME`, which redirects the entire Codex home directory to a different path — a blunt instrument that requires full config tree duplication, not a per-invocation persona switch.

**Verdict: No env-var workaround available.**

### 4. Prompt injection

**No documented effect.** The AGENTS.md docs state: "Codex builds an instruction chain when it starts (once per run)." The discovery hierarchy (global override → global → git root → subdirs → cwd) runs at boot, not per-message. Prepending "Use the code-reviewer agent." to a `codex exec` prompt has no documented effect on which instruction chain is loaded.

Tested approach (hypothetical): prepend the `developer_instructions` content from `.codex/agents/<name>.toml` directly to the prompt payload in `CodexRunner.build_streaming()`. This would inject the persona instructions as prompt text rather than as a system prompt. While the model might follow these instructions, there is no structured guarantee — unlike a proper system prompt, prompt-injected instructions compete with the default system prompt and could be overridden or ignored by the model.

**Verdict: Unreliable; cannot be offered as a "partial" capability.**

### 5. `.codex/config.toml` `agents.<name>.config_file` stanza

**Exists but broken for tool-backed (exec) sessions.** The config schema supports:

```toml
[agents.reviewer]
description = "Reviews code for bugs and security issues"
config_file = "./agents/reviewer.toml"
```

However, this mechanism is exclusively for `spawn_agent` tool calls from *within* an existing Codex session — it does not affect the root session's persona. Additionally, [openai/codex#14579](https://github.com/openai/codex/issues/14579) documents that custom agent roles from `.codex/config.toml` are not recognized by `spawn_agent` in tool-backed (API/exec) sessions. The confirmed workaround is `-c` inline injection, which is still for `spawn_agent` — not the root session.

**Verdict: Wrong surface (subagent spawning ≠ root-session persona selection).**

### 6. `-c key=value` inline config injection

**Wrong surface.** `codex exec -c 'agents.reviewer.config_file=...'` injects config keys at invocation time and can make custom agent roles visible to `spawn_agent` tool calls within the session. It does not set the root session's `developer_instructions`.

**Verdict: Wrong surface.**

---

## Related Open Issues in openai/codex

| Issue | Status | Summary |
|-------|--------|---------|
| [#10067](https://github.com/openai/codex/issues/10067) | Open | Feature: `--agents <name>` flag to select named agent profile |
| [#15250](https://github.com/openai/codex/issues/15250) | Open | Bug: custom `.codex/agents/*.toml` not accessible via `spawn_agent` in tool-backed sessions |
| [#14579](https://github.com/openai/codex/issues/14579) | Closed | Bug: custom agent roles from `config.toml` not available to `spawn_agent` (workaround: `-c` injection) |
| [#11588](https://github.com/openai/codex/issues/11588) | Closed | Feature: `--system-prompt-file` flags (complementary; resolution unclear) |

---

## Conclusion

No CLI-level mechanism exists for selecting a named `.codex/agents/*.toml` persona at invocation time. The gap is **permanent until openai/codex#10067 is shipped**.

Documentation action (gap path):
- `docs/reference/HOST_COMPATIBILITY.md` — update `[^agent]` footnote with research findings and tracking issue
- `docs/codex/usage.md` — replace the current "mitigation" language in the `--agent` limitation with the permanent-gap finding
- `docs/codex/README.md` — update the "deferred" paragraph to add the permanent-gap rationale

No code changes are warranted. `CodexRunner` should continue to emit `CapabilityNotSupported` for `agent`, and `describe_capabilities()` should continue reporting `agent_select: unsupported`.
