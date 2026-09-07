---
id: ENH-3396
type: ENH
title: "Credential-scope registry: resolve_scopes() and fail-loud validation"
priority: P2
status: open
parent: ENH-3233
epic: EPIC-3212
blocked_by: []
discovered_by: /ll:issue-size-review
discovered_date: '2026-09-07'
testable: true
decision_needed: false
relates_to:
- ENH-3395
---

# ENH-3396: Credential-scope registry: resolve_scopes() and fail-loud validation

## Summary

Add a credential-scope registry that maps scope names (e.g. `github`, `anthropic-api`) to the
env-var names they unlock, plus a `resolve_scopes(...)` function that raises directly
(`ValueError`, naming the bad scope) when asked to resolve a scope name not in the registry. This
is one of two sibling primitives decomposed from ENH-3233 ("chokepoint, capability registry, and
baseline"). It has no runtime dependency on the other sibling (ENH-3395, the deny-capable
`project_child_env()` chokepoint): nothing in this decomposition calls `resolve_scopes()` from
`project_child_env()` — a future caller (ENH-3234/ENH-3235, out of scope here) resolves scope
names into a `frozenset[str]` of env-var names and passes that pre-resolved set into
`env_allow`. This issue is independently testable and shippable: call `resolve_scopes({"github"})`
directly and assert the returned frozenset, or `resolve_scopes({"nonexistent"})` and assert the
raise.

## Parent Issue

Decomposed from ENH-3233: Deny-by-default env projection core — chokepoint, capability registry,
and baseline (itself decomposed from ENH-3203: Declare and enforce per-task credential scope via
deny-by-default env projection). This child covers the scope-name-to-env-var-names registry. The
deny-capable chokepoint and its always-on baseline is ENH-3395. Declaration-surface wiring for the
two `bash -c` paths remains out of scope here too, per ENH-3233's own Scope Boundaries — that's
ENH-3234 (`ActionSpec`/`runner_spec.py`) and ENH-3235 (FSM `StateConfig`/loop-YAML).

**Mechanism is env projection, not token minting** — see ENH-3203 Summary for the full framing;
that context is unchanged and not repeated here.

## Current Behavior

No credential-scope registry exists today. `scripts/little_loops/mcp_server/policy.py`'s
`MUTATING_TOOLS` — the nearest existing bare `frozenset[str]` allow-set — is consulted via
`tool_name in MUTATING_TOOLS` inside `check_tool_call()`; it carries no per-entry metadata and no
fail-loud-on-unknown-name behavior, so it is a shape precedent only, not a reusable registry.

## Expected Behavior

- A credential-scope registry maps scope names to the env-var names they unlock; resolving a
  scope name not in the registry **raises directly** (e.g. `ValueError`) at resolve time, naming
  the scope. Direct raise, not `warnings.simplefilter("error", ...)` promotion — promotion is
  opt-in per process and this check is fail-loud security. (This pins ENH-3203 Open Decision #3.)
- **Registry naming**: do not call this a "capability" registry in code. `host_runner.py` already
  uses the capability vocabulary for host-feature support (`HostCapabilities`, `CapabilityEntry`,
  `CapabilityNotSupported`, `describe_capabilities`) — a second meaning of "capability" in the
  same module invites confusion. Use "scope" (e.g. `CREDENTIAL_SCOPES`, `resolve_scopes(...)`).
- The registry ships with an initial entry set so ENH-3234/ENH-3235 don't each invent their own.
  **Enumerate it from the credential names the codebase already references** (repo-wide grep
  2026-09-04, `\b(ANTHROPIC|CLAUDE|OPENAI|GEMINI|GITHUB|GH|CODEX|KIMI|QWEN|OPENCODE)_[A-Z_]*(KEY|TOKEN|SECRET)\b`
  under `scripts/little_loops/`), not from two examples. Starting set:
  - `github` → `{GH_TOKEN, GITHUB_TOKEN, GH_ENTERPRISE_TOKEN, GITHUB_ENTERPRISE_TOKEN,
    GITHUB_ACCESS_TOKEN}`
  - `anthropic-api` → `{ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_OAUTH_TOKEN,
    CLAUDE_CODE_OAUTH_TOKEN}`
  - `openai-api` → `{OPENAI_API_KEY, OPENAI_CODEX_OAUTH_TOKEN}`
  - `gemini-api` → `{GEMINI_API_KEY}`
  - `kimi-api` → `{KIMI_API_KEY}`
  - `qwen-api` → `{QWEN_OAUTH_TOKEN, QWEN_PORTAL_API_KEY}`
  - `opencode-api` → `{OPENCODE_API_KEY}`

  Finalize during implementation with a justification comment per entry; drop any name that
  turns out to be a non-credential (`*_STATE_KEY`, `*_METADATA_KEY`, `*_CLIENT_KEY` hits from the
  same grep are deliberately excluded above).
- **Honesty note (mirror of ENH-3205's gh caveat)**: on macOS the host CLIs' own OAuth sessions
  (Claude Code, Codex, Gemini) live in the Keychain or under `$HOME`, not in env. This registry
  therefore does **not** capture the host CLI's own auth when a declaring `bash -c` state spawns a
  nested `claude -p`/`ll-loop`/`ll-auto`; it only enumerates the env-var-borne credentials known
  today. State this plainly in the registry's module-level docstring so nobody reads a `github`
  scope as "the child cannot reach the operator's `gh` session" when that session is
  keychain-backed.

### Registry starting-set gap (wiring pass finding, carried forward from ENH-3233)

_Wiring pass added by `/ll:wire-issue` — 2026-09-06:_
- This repo's own built-in loops already read three credential-shaped env vars via undeclared
  shell states that are in none of the 7 starting scopes above and none of the `LL_*`/`XDG_*`/
  `HOMEBREW_*` baseline (ENH-3395's baseline, not this registry): `VISION_API_KEY`
  (`scripts/little_loops/loops/rlhf-svg-evaluate.yaml:248,396`,
  `openscad-model-generator.yaml:313,411`, `svg-image-generator.yaml:153,207`,
  `flux-image-generator.yaml:265,334`, `interactive-component-generator.yaml:512,524,558`,
  `html-website-generator.yaml:189,202,253`), and `OPENROUTER_API_KEY`/`AUTOFIGURE_API_KEY`
  (`scripts/little_loops/loops/adversarial-redesign.yaml:16`, consumed by
  `scripts/autofigure_wrapper.py`). None of these are problems for an undeclared state
  (`env_allow=None` stays full-inherit — ENH-3395's default path), but they are candidates for
  this registry (e.g. `vision-api`, `openrouter-api`, `autofigure-api` scopes) so a state that
  later declares `scopes: [...]` for one of these loops doesn't lose ambient access to a var the
  registry doesn't know about. Finalize alongside the starting-set enumeration above, not as a
  blocker for this issue's own tests.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis (carried forward from
ENH-3233):_
- **Citation correction (autofigure_wrapper.py)**: `scripts/autofigure_wrapper.py` is 99 lines
  total, not 100+/107+. `AUTOFIGURE_API_KEY` appears once, in the module docstring at line 6 (not
  line 52); `OPENROUTER_API_KEY` appears once, in a `print(..., file=sys.stderr)` error message
  at line 63 (not line 107 — the file has no line 107). Neither variable is read
  programmatically in this file — it has no `import os` and never calls
  `os.environ`/`os.getenv`; both mentions are user-facing prose pointing at the external
  `autofigure` package (`from autofigure import AutoFigureAgent`, line 58), where the actual key
  read presumably happens outside this repo. This does not change the case for adding
  `openrouter-api`/`autofigure-api` scopes — it only corrects the citation.

## Motivation

Per-task credential scoping needs a single source of truth mapping human-meaningful scope names
to the env-var names they actually unlock, so the two declaration surfaces (`ActionSpec` and FSM
`StateConfig`, per ENH-3234/ENH-3235) resolve scope names identically instead of each
hand-rolling their own name→env-var table. Keeping this registry a separate primitive from the
deny-capable chokepoint (ENH-3395) means it can be reviewed, extended, and tested purely as a
static mapping problem, without touching `project_child_env()`'s merge/baseline/logging logic at
all.

## Proposed Solution

### Failure polarity (AC3) — decided
The one existing analog, `CapabilityNotSupported(UserWarning)` (`host_runner.py:109-117`), is
warn-and-drop at every site (`warnings.warn(..., CapabilityNotSupported, stacklevel=N)`). AC3
requires the opposite polarity for an unknown-scope-name-vs-registry mismatch — **decided:
direct raise** (see Expected Behavior). This resolves ENH-3203's Open Decision #3;
`simplefilter` promotion was rejected because it is opt-in per process and this check must
fail loudly everywhere.

### Registry shape and location
Define `CREDENTIAL_SCOPES: dict[str, frozenset[str]]` (module-level, in `host_runner.py`
alongside the other host-runner primitives — or a new small module if the maintainer prefers
isolating it; either is acceptable since nothing in ENH-3395 imports it) and
`resolve_scopes(scopes: Iterable[str]) -> frozenset[str]`, which unions the env-var names for
every requested scope and raises `ValueError` naming the first (or all) unknown scope name(s)
encountered.

## Acceptance Criteria

- **AC3.** Resolving a scope name not in the credential-scope registry fails loudly at resolve
  time via direct raise, naming the scope (see "Failure polarity" — pins ENH-3203 Open
  Decision #3).
- **AC-registry-1.** `resolve_scopes({"github"})` returns the exact frozenset documented in the
  starting set above (or its finalized equivalent after the justification-comment pass).
- **AC-registry-2.** `resolve_scopes({"github", "anthropic-api"})` returns the union of both
  scopes' env-var names.
- **AC-registry-3.** Every entry in `CREDENTIAL_SCOPES` carries a justification comment (per
  Expected Behavior) — enforced by a test that reads the source and checks a comment precedes (or
  is adjacent to) each dict entry, or by a docstring-per-entry convention if that's more testable
  given the chosen shape.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis (carried forward from
ENH-3233):_

- **Registry shape precedent**: the codebase has a closer shape precedent for this registry than
  the bare-`frozenset` `MUTATING_TOOLS` (cited under Current Behavior) — two module-level,
  module-private `dict[str, frozenset[str]]` literals in
  `scripts/little_loops/dependency_mapper/analysis.py:39` (`_SECTION_KEYWORDS`) and `:50`
  (`_MODIFICATION_TYPES`), each a dict literal of `frozenset({...})` values with a one-line doc
  comment above stating what the keys/values mean. Model `CREDENTIAL_SCOPES` on this shape.
- **Unknown-name fail-loud error convention — two shapes coexist, not reconciled**: (A) capitalized
  "Unknown X" `ValueError` naming only the bad value, no valid-set listing
  (`design_tokens.py:168`, `config/features.py:192`); (B) lowercase "unknown x" `ValueError` naming
  the bad value plus `sorted(...)` of the valid options (`session_store/queries.py:75,283`).
  `host_runner.py`'s own existing `HostNotConfigured` (its unknown-host case, ~line 2020) follows
  shape (B): names the bad value, lists `sorted(...)` of the valid set, and adds a remediation
  hint — the closest in-module precedent for this registry's unknown-scope-name raise. Follow
  shape (B).

### Tests
- New tests for: `resolve_scopes()` with a known scope (single and multi), `resolve_scopes()`
  with an unknown scope name (fail-loud direct raise, per-name message), and the AC-registry-3
  justification-comment check.
- **New-test precedent**: unknown-scope fail-loud raise →
  `scripts/tests/test_host_runner.py::TestResolveHost::test_unknown_host_name_raises_with_hint`
  (lines 310-314, `pytest.raises(HostNotConfigured)` + substring assert) mirrors the target
  `host_runner.py:2020-2023` `HostNotConfigured` raise shape — model the new
  `resolve_scopes()` unknown-name test on this.
- No shared fixture needed — `resolve_scopes()` and `CREDENTIAL_SCOPES` are pure/stateless.

### Documentation
- `docs/reference/API.md` — add a new subsection documenting `CREDENTIAL_SCOPES` and
  `resolve_scopes()` (name, signature, raise behavior, starting scope list) near the existing
  `### project_child_env`/`### HostInvocation` sections (ENH-3395's edits land those; this
  issue's doc addition can land independently and be sequenced by whichever PR merges second,
  since it's an addition, not a rewrite of existing pinned text).
- Check `scripts/tests/test_wiring_reference_docs.py` (~163-172) for any pinned substrings this
  addition might interact with; if none, no coordination needed with ENH-3395's doc edit.

## Scope Boundaries

Out of scope for this child (belongs to ENH-3395, ENH-3234/ENH-3235, or is out of scope for the
whole ENH-3203 effort per its Scope Boundaries section):

- The deny-capable `project_child_env()` chokepoint, `HostInvocation.env_allow`, the always-on
  baseline, DEBUG logging, and report-only/force-allow modes — that's ENH-3395.
- Calling `resolve_scopes()` from anywhere at runtime — no `ActionSpec` or `StateConfig` field
  exists yet to carry a `scopes:` declaration; that's ENH-3234 (action path) and ENH-3235 (FSM
  path).
- Disk-backed/keyring-backed credentials, token minting, MCP server credentials, secrets
  management, `gh`/`sync.py` scoping (ENH-3205), audit persistence (ENH-3204) — unchanged from
  ENH-3203's Scope Boundaries.

## Impact

- **Priority**: P2 — matches parent; ENH-3234/ENH-3235 need this registry to resolve declared
  `scopes:` into env-var names, and ENH-3395's AC8 static test references it once it lands.
- **Effort**: Small — a static dict, a resolve function, and a fail-loud raise; no chokepoint
  changes.
- **Risk**: Low — purely additive, no existing call site touches this registry, so there is no
  regression surface.
- **Breaking Change**: No — nothing in the codebase calls `resolve_scopes()` yet.

## Blocks

- ENH-3234
- ENH-3235
- ENH-3204
- ENH-3205

## Status

**Open** | Created: 2026-09-07 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-09-07T18:32:56 - `08ef3096-7021-4748-9fbe-8beb4da74092.jsonl`
