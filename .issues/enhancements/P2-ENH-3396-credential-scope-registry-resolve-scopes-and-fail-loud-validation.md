---
id: ENH-3396
type: ENH
title: 'Credential-scope registry: resolve_scopes() and fail-loud validation'
priority: P2
status: done
parent: ENH-3233
epic: EPIC-3212
blocked_by: []
discovered_by: /ll:issue-size-review
discovered_date: '2026-09-07'
completed_at: '2026-09-07T19:57:54Z'
testable: true
decision_needed: false
relates_to:
- ENH-3395
verify_verdict: NON_VALID
size: Very Large
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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
  line 52); `OPENROUTER_API_KEY` appears twice — in that same line-6 docstring and in a
  `print(..., file=sys.stderr)` error message at line 63 (not line 107 — the file has no line
  107). Neither variable is read
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

## Integration Map

### Codebase Research Findings

### Files to Modify
- `scripts/little_loops/host_runner.py` — add `CREDENTIAL_SCOPES: dict[str, frozenset[str]]` and
  `resolve_scopes(scopes: Iterable[str]) -> frozenset[str]`; the file has no `Iterable` import
  today (needs `from collections.abc import Iterable`)

### Dependent Files (Callers/Importers)
- None yet — repo-wide search for `resolve_scopes`/`CREDENTIAL_SCOPES` in production code returns
  zero hits. The only existing reference is a forward-looking `TODO(ENH-3396)` comment at
  `scripts/tests/test_host_runner.py:2209-2211`, inside `TestAC8BaselineCoverage`, anticipating
  this registry replacing that test's `_KNOWN_EXCEPTIONS` allowlist with a real
  registry-membership check — not a caller, a coupling point for a later pass

### Conventions in Force
- Module-level `dict[str, frozenset[str]]` registries carry exactly one doc comment above the
  whole literal, not one per entry — evidence: `dependency_mapper/analysis.py:39`
  (`_SECTION_KEYWORDS`), `:50` (`_MODIFICATION_TYPES`), the only two such literals in the repo
- Unknown-name raises follow one of two shapes: capitalized-no-list (`design_tokens.py:168`,
  `config/features.py:192`) or lowercase-with-sorted/joined-valid-list
  (`session_store/queries.py:75,283`, `host_runner.py:2167-2170`) — no third shape exists anywhere
  under `scripts/little_loops/`

### Tests
- `scripts/tests/test_host_runner.py` — `TestResolveHost::test_unknown_host_name_raises_with_hint`
  (lines 437-441) is the structural model this issue's own Tests section already points to; no
  shared fixture is needed since `resolve_scopes()`/`CREDENTIAL_SCOPES` are pure/stateless

### Documentation
- `docs/reference/API.md` — `### resolve_host` (line 10149) and `### project_child_env`
  (line 10173) are the nearest existing subsections. `scripts/tests/test_wiring_reference_docs.py`
  (lines 163-172) has no pinned entry for `project_child_env`/`env_allow`/`CREDENTIAL_SCOPES`/
  `resolve_scopes` yet, so no coordination conflict.
- No bare dict/frozenset module constant anywhere in API.md gets its own `###` heading today —
  only dataclasses and functions do. `CREDENTIAL_SCOPES` may read better documented inline within
  a `### resolve_scopes` heading than as its own heading, per this convention.

## Program Design

### Types
- `CREDENTIAL_SCOPES: dict[str, frozenset[str]]` — new module-level registry, `host_runner.py`

### Signatures
- `resolve_scopes(scopes: Iterable[str]) -> frozenset[str]` — new module-level resolver,
  `host_runner.py`; raises `ValueError` naming any scope not present in `CREDENTIAL_SCOPES`

### Call Path
`resolve_scopes` -> `HostNotConfigured` (unknown-scope raise mirrors `resolve_host`'s existing
raise shape at `host_runner.py:2167-2170`) — no runtime caller yet; the eventual consumer is
`project_child_env`'s `env_allow` parameter (ENH-3234/ENH-3235, out of scope here)

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

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **Citation correction**: this issue's existing citations for the `resolve_host` unknown-name
  raise are wrong. The raise is at `host_runner.py:2167-2170` (not "~line 2020"), and its test is
  `TestResolveHost::test_unknown_host_name_raises_with_hint` at
  `scripts/tests/test_host_runner.py:437-441` (not `310-314`). Confirmed by direct read.
- **Import gap**: `host_runner.py` has no `Iterable` import today (neither `typing.Iterable` nor
  `collections.abc.Iterable` appears anywhere in the file); `resolve_scopes(scopes: Iterable[str])`
  will need `from collections.abc import Iterable` added.
- **Forward reference already exists**: `scripts/tests/test_host_runner.py:2209-2211`, inside
  `TestAC8BaselineCoverage`, carries a `TODO(ENH-3396)` comment anticipating this registry as a
  replacement for that test's `_KNOWN_EXCEPTIONS` allowlist. Not a caller (wiring is out of scope
  here per this issue's own Scope Boundaries), but it is the one place in the tree that already
  anticipates `CREDENTIAL_SCOPES`/`resolve_scopes()`.
- **AC-registry-3's test approach has no repo precedent on a dict literal**: the only "test reads
  its own source for a justification comment" precedent, `test_feat3036_artifact_templates.py::
  TestJinja2Pin::test_jinja2_pinned_with_justifying_comment`, checks a single target string against
  one preceding comment window in `pyproject.toml` — not per-entry-in-a-dict adjacency. No existing
  dict-literal-comment-adjacency test exists anywhere in the repo to model AC-registry-3's test on;
  its test will be a new pattern, not a reuse of an existing one.
- **Two placement precedents confirmed, neither exclusive**: a module-level constant immediately
  followed by its one resolver function precedes the class block (`MODEL_ALIASES` +
  `resolve_model_alias()`, `host_runner.py:91-108`), and a constant-plus-helper pair also sits
  immediately before its eventual consumer (`_BASELINE_NAMES`/`_BASELINE_PREFIXES` +
  `_is_baseline_allowed()` before `project_child_env()`, `host_runner.py:1883-1949`). Both
  placements are precedented in this file for `CREDENTIAL_SCOPES`/`resolve_scopes()`.

_Added by `/ll:refine-issue` — 2026-09-07 — based on codebase analysis:_

- **AC-registry-3 test-shape nuance**: no `dict[str, frozenset[str]]` registry anywhere in this codebase comments each dict key individually — the closest confirmed shapes are per-member (not per-dict-key): `scripts/little_loops/cli/verify_package_data.py:34-39` (`_ALLOWLIST: frozenset[str]`) trails each set member with its own inline `#` comment, while `host_runner.py:1883-1919`'s own `_BASELINE_NAMES` and its test-side mirror `test_host_runner.py:2212-2233` (`_KNOWN_EXCEPTIONS`) group related entries under one shared comment per cluster. Neither is the `dict[str, frozenset[str]]` shape AC-registry-3 needs a test for.
- **Source-introspection test family is narrower than "no precedent" implies**: repo-wide, only `test_feat3036_artifact_templates.py::TestJinja2Pin::test_jinja2_pinned_with_justifying_comment` checks comment-adjacency by index window against a single target string. Every other source-introspecting test found (`test_host_runner.py`'s `TestAC8BaselineCoverage`/`_os_environ_read_names()` at :2255-2270, `fsm/validation/meta_rules.py:463-471`, `issues/symbol_claims.py:26-40`) instead regex-extracts identifiers into a set and asserts coverage against an allowlist — a distinct, more common family in this codebase than comment-adjacency checking.
- **No existing "resolve names to union of frozenset values, raise on unknown" helper**: no callable in this repo currently takes an iterable of names and returns the union of their frozenset values while raising on an unknown name. The one structural analog, `fsm/validation/meta_rules.py:463-471`'s `_GATE_COMPLETENESS_TABLES`, is a static one-time `frozenset(chain.from_iterable(EVALUATOR_REQUIRED_FIELDS.values()))` flatten, not a parametrized resolver — `resolve_scopes()` has no existing repo helper to be consistent with.

### Tests
- New tests for: `resolve_scopes()` with a known scope (single and multi), `resolve_scopes()`
  with an unknown scope name (fail-loud direct raise, per-name message), and the AC-registry-3
  justification-comment check.
- **New-test precedent**: unknown-scope fail-loud raise →
  `scripts/tests/test_host_runner.py::TestResolveHost::test_unknown_host_name_raises_with_hint`
  (lines 437-441, `pytest.raises(HostNotConfigured)` + substring assert) mirrors the target
  `host_runner.py:2167-2170` `HostNotConfigured` raise shape — model the new
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

## Verification Notes (2026-09-07, /ll:verify-issues)

Re-verified every `path:line` citation in the issue against current source: `host_runner.py`
(`MODEL_ALIASES`/`resolve_model_alias` :91-108, `HostNotConfigured` unknown-host raise
:2167-2170, `_BASELINE_NAMES`/`_BASELINE_PREFIXES`/`_is_baseline_allowed` :1883-1949, no
`Iterable` import present), `test_host_runner.py` (`test_unknown_host_name_raises_with_hint`
:437-441, `TestAC8BaselineCoverage` TODO :2209-2211, `_KNOWN_EXCEPTIONS` :2212-2233,
`_os_environ_read_names` :2255), `dependency_mapper/analysis.py` (`_SECTION_KEYWORDS` :39,
`_MODIFICATION_TYPES` :50), `cli/verify_package_data.py` (`_ALLOWLIST` :34-39),
`fsm/validation/meta_rules.py` (`_GATE_COMPLETENESS_TABLES` :463-471),
`test_feat3036_artifact_templates.py::TestJinja2Pin::test_jinja2_pinned_with_justifying_comment`
:53, `autofigure_wrapper.py` (99 lines total, `AUTOFIGURE_API_KEY` :6, `OPENROUTER_API_KEY` :63,
no `os.environ`/`os.getenv`), `docs/reference/API.md` (`### resolve_host` :10149,
`### project_child_env` :10173), `test_wiring_reference_docs.py` :163-172 (no pinned
`project_child_env`/`env_allow`/`CREDENTIAL_SCOPES`/`resolve_scopes` entry), and every
VISION_API_KEY/OPENROUTER_API_KEY/AUTOFIGURE_API_KEY loop-YAML line cited in the "Registry
starting-set gap" section. All confirmed accurate. `resolve_scopes`/`CREDENTIAL_SCOPES` still
have zero production references (only the `TODO(ENH-3396)` comment) — proposal remains purely
additive. Dependency graph: all four `## Blocks` targets (ENH-3234, ENH-3235, ENH-3204, ENH-3205)
carry a reciprocal `blocked_by: [..., ENH-3396]` — no DEP_ISSUES. Decisions log: no active
required rules (query succeeded, empty). `ll-verify-evidence --json`: clean (`"ok": true, "count":
0`). B6 proposal-vs-code check: no exception-handler incompatibility, test-fixture invalidation,
or uncovered integration point — `PROPOSAL_UNSOUND` does not apply.

**One drift found and corrected**: the "Tests" subsection's "New-test precedent" bullet still
cited the pre-correction line numbers (`test_host_runner.py` lines 310-314,
`host_runner.py:2020-2023`) for `test_unknown_host_name_raises_with_hint`/`HostNotConfigured`,
even though a later `/ll:refine-issue` pass had already corrected these same citations elsewhere
in this file (Codebase Research Findings, "Citation correction") to 437-441 / 2167-2170. Updated
the Tests bullet to match.

## Resolution

Implemented per the issue's own Program Design, exactly as specified:

- Added `CREDENTIAL_SCOPES: dict[str, frozenset[str]]` and
  `resolve_scopes(scopes: Iterable[str]) -> frozenset[str]` to
  `scripts/little_loops/host_runner.py`, placed after `MODEL_ALIASES`/
  `resolve_model_alias` (the precedented name→value-registry-plus-resolver
  placement). Added the missing `from collections.abc import Iterable` import.
- Registry ships 10 scopes: the 7 in Expected Behavior (`github`,
  `anthropic-api`, `openai-api`, `gemini-api`, `kimi-api`, `qwen-api`,
  `opencode-api`) plus the 3 gap-analysis candidates (`vision-api`,
  `openrouter-api`, `autofigure-api`), each with its own justification
  comment (AC-registry-3).
- Unknown-scope resolution raises `ValueError` directly (not a `warnings`
  promotion), naming the bad scope and `sorted(CREDENTIAL_SCOPES)` — mirrors
  `HostNotConfigured`'s shape-B raise (`host_runner.py:2167-2170`), pins
  ENH-3203 Open Decision #3 (AC3).
- Module-level docstring-style comment states the macOS Keychain/`$HOME`
  honesty caveat and the "scope, not capability" naming rationale.
- New `TestResolveScopes` class in `scripts/tests/test_host_runner.py`:
  `test_single_known_scope` (AC-registry-1), `test_multiple_scopes_union`
  (AC-registry-2), `test_unknown_scope_raises_with_name` (AC3),
  `test_every_scope_entry_has_a_justification_comment` (AC-registry-3,
  reads the module source and asserts a `#`-comment precedes every dict
  key line).
- Added `### resolve_scopes` subsection to `docs/reference/API.md`, between
  `### resolve_host` and `### project_child_env`.
- No deviation from the issue's Program Design — no `## Program Design`
  Deviations entry needed.
- Out of scope, per this issue's own Scope Boundaries, and left untouched:
  `TestAC8BaselineCoverage._KNOWN_EXCEPTIONS` in `test_host_runner.py` (its
  `TODO(ENH-3396)` anticipates a future wiring pass, not this issue), and any
  runtime caller wiring (`ActionSpec`/FSM `StateConfig`, ENH-3234/ENH-3235).

Full suite: `python -m pytest scripts/tests/` — 23298 passed, 43 skipped, 5
pre-existing failures unrelated to this change (bun/tsc adapter typecheck
environment issues, `ll-verify-evidence` findings on unrelated issue files,
an artifact-template golden-fixture drift, and a builtin-loop residual-dispatch
test) — none touch `host_runner.py`, `test_host_runner.py`, or
`docs/reference/API.md`.

## Status

**Open** | Created: 2026-09-07 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-09-07T19:57:43 - `f63c0706-fb10-442e-af2f-e125ef81bec6.jsonl`
- `/ll:ready-issue` - 2026-09-07T19:49:05 - `278007f4-6b60-4eac-bf9a-9ac0b368f43c.jsonl`
- `/ll:confidence-check` - 2026-09-07T19:46:31 - `3410975f-6737-4b2c-8124-e7fc532797c7.jsonl`
- `/ll:reconcile-issue` - 2026-09-07T19:45:23 - `fdbafb24-980c-4d21-9e5b-a3346686f6c8.jsonl`
- `/ll:verify-issues` - 2026-09-07T19:41:31 - `88738cb9-e099-492c-98fe-a6493242486b.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-07T19:38:19 - `79191a70-c071-40aa-926b-15f0c5900d32.jsonl`
- `/ll:verify-issues` - 2026-09-07T19:34:02 - `065782f8-28db-4e55-a6dc-b2f39071207a.jsonl`
- `/ll:refine-issue` - 2026-09-07T19:25:53 - `af1a15cd-fedc-44b5-9de2-bd7dd19bf829.jsonl`
- `/ll:issue-size-review` - 2026-09-07T18:32:56 - `08ef3096-7021-4748-9fbe-8beb4da74092.jsonl`
