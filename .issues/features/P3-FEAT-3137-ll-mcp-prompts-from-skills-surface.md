---
id: 3137
title: 'll-mcp: prompts-from-skills surface'
type: FEAT
priority: P3
status: open
labels:
- multi-host
- mcp
parent: EPIC-3127
blocked_by:
- FEAT-3135
learning_tests_required:
- mcp
relates_to:
- FEAT-3132
---

# FEAT-3137: ll-mcp: prompts-from-skills surface

## Summary

The MCP prompts surface for the `ll-mcp` server: every `SKILL.md` served
mechanically as an MCP prompt, with name, description, and args read from
frontmatter. This builds on the running server and dispatch loop from
FEAT-3135 — it adds `prompts/list` handling to the same server, backed by a
new recursive `SKILL.md` discovery walk (the existing
`tool_catalog._skill_entries` glob is non-recursive and cannot be reused
as-is).

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers prompts-from-skills; the server
skeleton, entry point, and tools surface are in FEAT-3135 (must land first —
this child registers its handlers on that server). The `ll://` resource
surface is a separate sibling, FEAT-3136.

## Bind resource resolution at discovery, not at call time

Because this server exposes skill-derived content to arbitrary MCP clients,
`little-loops` is the loader and the trust boundary is external — unlike
host-CLI-owned skill loading elsewhere in the project, where the caller is
already inside the trust boundary.

- **Pre-enumerate supporting files at discovery time.** Walk each skill
  once during startup and record the exact set of readable paths. A prompt-
  related resource request then accepts a skill name, or a
  `skill-name/relative/path` that was enumerated, and is rejected
  otherwise. The server must never perform an arbitrary filesystem read
  derived from client-supplied input at call time — the enumeration, not
  path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `prompts/list` needs name,
  description, and args; reading full skill bodies at list time is both a
  context cost and an unnecessary widening of what is loaded. Fetch bodies
  on demand.
- **Treat a nested `SKILL.md` as a separate skill.** When a skill directory
  contains a subdirectory with its own `SKILL.md`, register it as its own
  skill and do not descend into it as supporting files of the parent, so
  one skill can never serve another's contents.

This boundary must carry forward to the future mutation tier, where it
widens.

## Spec assumptions (MCP 2026-07-28)

- **Caching metadata is part of the contract.** `prompts/list` responses
  MUST include `ttlMs` and `cacheScope` per SEP-2549.
- **No `initialize` handshake.** Consistent with the server's existing
  dispatch loop from FEAT-3135 (protocol version + capabilities arrive in
  `_meta`).

## Integration Map

### Files to Modify
- The server module registered in FEAT-3135 (exact path depends on the
  module-placement decision made there) — add `prompts/list` handler
- New recursive `SKILL.md` discovery walk (not
  `tool_catalog._skill_entries`, which is non-recursive)
- `docs/reference/CLI.md` — extend the `ll-mcp` section added by FEAT-3135
  with the prompts surface

### Dependent Files (Callers/Importers)
- Depends on the server/dispatch-loop scaffolding registered by FEAT-3135;
  no other existing callers.

### Conventions in Force
- Skill/command/agent discovery already has one canonical
  frontmatter-parsing utility built explicitly to prevent reimplementation —
  evidence: `scripts/little_loops/tool_catalog.py` docstring (lines 1-9),
  `_skill_entries()` (line 95) walking `skills_dir.glob("*/SKILL.md")` via
  `parse_skill_frontmatter()` (`scripts/little_loops/frontmatter.py:371`).
  This glob is non-recursive and does not descend into nested skill
  directories. The "nested SKILL.md = separate skill" requirement needs new
  recursive-walk logic; `_skill_entries` cannot be reused as-is.
- A second independent skill-walk site exists:
  `adapters/core.py:process_skills()` (line 279) also globs `*/SKILL.md`
  (non-recursive) and applies a `disable-model-invocation` filter via
  `_is_model_invocation_disabled()` (`core.py:180`). Decide whether the new
  prompts-from-skills recursive walker honors this same filter — neither
  existing site's behavior can be assumed by default.
- **`parse_skill_frontmatter(text: str) -> dict[str, str]`**
  (`frontmatter.py:371-413`): returns `{}` if `text` doesn't start with
  `"---"` or has no closing `---`. Primary path is `yaml.safe_load()`,
  flattened to `dict[str, str]` — `None` becomes `""`, `bool`/`int`/`float`
  are stringified, and any list or nested-dict value is silently dropped
  (not present in the returned dict at all). Fallback (only on
  `yaml.YAMLError`) is a line-based scan of top-level `key: value` lines
  only. **`name` is never read from frontmatter** by either existing caller
  (`tool_catalog._skill_entries`, `adapters/core.py`) — both derive it from
  `skill_md.parent.name` (the directory name), not a frontmatter field.
- **`disable-model-invocation` filter mechanics**:
  `_is_model_invocation_disabled(fm: dict) -> bool` (`adapters/core.py:180-192`)
  — `None` → `False`; native `bool` → returned directly; anything else
  stringified/trimmed/lowercased and checked against `{"true", "yes",
  "1"}`. Applied by `adapters/core.py:process_skills()` (`:304`) and
  `process_commands()` (`:376`), and by `cli/help.py:190` when building the
  skill catalog listing. It is **not applied universally** —
  `cli/verify_triggers.py`'s loader (`:306-316`) documents the filter as
  opt-in via a `model_invocable_only: bool` param specifically because
  other callers (`issue_history.evolution._load_skill_keywords`) need the
  full unfiltered population.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`.

### Tests
- New tests for recursive `SKILL.md` discovery — no existing fixture for
  nested skill directories anywhere in `scripts/tests/`; author from
  scratch, extending `test_tool_catalog.py`'s flat `skills/<name>/SKILL.md`
  fixture base with a nested-subdirectory case.
- `test_frontmatter.py:320-366` (`TestParseSkillFrontmatter`) —
  prompts-from-skills edge cases: malformed YAML fallback, `None`→`""`,
  bool stringification.
- `test_tool_catalog.py:64-121` (`TestAssembleToolCatalogSkills`) — closest
  structural template for the new recursive `SKILL.md` walk's tests,
  including an unreadable-file-degrades pattern at lines 107-121.
- `test_adapters.py:102-126,202-235` (`_is_model_invocation_disabled`
  truthy-string matrix, `TestProcessSkillsTraversal` emitter-call pattern).

### Documentation
- `docs/reference/CLI.md` — extend the `ll-mcp` section (added by
  FEAT-3135) with the prompts-from-skills surface.

## Program Design

### Signatures
- `little_loops.frontmatter.parse_skill_frontmatter(text) -> dict[str,
  str]` — `frontmatter.py:371`; the canonical frontmatter parser,
  prompts-from-skills should reuse this rather than reimplement parsing.

### Call Path
- prompts-from-skills discovery → new recursive `SKILL.md` walk (not
  `tool_catalog._skill_entries`, which is non-recursive) →
  `little_loops.frontmatter.parse_skill_frontmatter()` → MCP `prompts/list`
  entries

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold. Whether the
recursive walker honors the `disable-model-invocation` filter (see
Conventions in Force) is an implementation decision to make explicitly, not
existing decision-rule logic.

## Implementation Steps

1. Prompts-from-skills discovery walks `SKILL.md` files recursively (not
   the existing non-recursive `tool_catalog._skill_entries` glob) and
   registers a nested `SKILL.md` as its own independent prompt. The walker
   explicitly decides whether to honor the `disable-model-invocation`
   filter used elsewhere. `prompts/list` responses include
   `ttlMs`/`cacheScope`.
2. `python -m pytest scripts/tests/` passes, including new coverage for the
   nested-`SKILL.md`-discovery walk.

## Acceptance criteria

- Every discovered `SKILL.md` is advertised as an MCP prompt with its name,
  description, and args derived from frontmatter; a nested `SKILL.md` is
  registered as its own skill.
- `prompts/list` responses include `ttlMs` and `cacheScope`.
- `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
