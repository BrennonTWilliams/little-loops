Looking at `skills/wire-issue/SKILL.md`, the current logic is biased toward little-loops itself — it hardcodes coupling categories like `plugin.json`, `__init__.py`, `commands/*.md`, `skills/*/SKILL.md`, `.claude/CLAUDE.md`, `hooks/hooks.json`, and uses Python-centric symbol heuristics. For a target project in Rust/Node/Go/Java, those signals don't map.

But "biased toward little-loops" overstates it. The hardcoded list actually splits into tiers, and only the innermost tier is truly little-loops-specific. The outer tiers are stable conventions shared by every project in their class, so they don't need to be re-derived per-project — they just need to be gated behind a detection step. The original framing assumed a single host (Claude Code); the reality is that multiple agent hosts (Claude Code, Codex, OpenCode, …) can coexist in the same repo, so tiers 1 and 2 are actually *per-host* profiles that can stack.

## Tiers of coupling

**Tier 1 — Agent host profile(s) (any project using an AI coding agent):**

Detect each host independently; activate any that are present. Multiple can be active simultaneously.

- **Claude Code host** — `.claude/` present:
  - `.claude/CLAUDE.md`
  - `.claude/settings.json`, `.claude/settings.local.json`
  - `.claude/commands/`, `.claude/agents/`, `.claude/skills/` (user- or project-level overrides)
- **Codex host** — `.codex/` or `AGENTS.md` present:
  - `AGENTS.md` (Codex's authoritative wiring doc, peer to `CLAUDE.md`)
  - `.codex/agents/*.toml`
  - Codex config files
- **Other hosts** — `opencode/`, `pi`, etc. (extensible; mirrors `resolve_host()` in `scripts/little_loops/host_runner.py`)

The profile is a *set* of active hosts, not a single value. Each host contributes its own fixed ruleset.

**Tier 2 — Agent-tooling plugin/extension profile(s) (any plugin or extension repo):**

Also per-host, also stackable.

- **Claude Code plugin profile** — `.claude-plugin/plugin.json` present:
  - `.claude-plugin/plugin.json`
  - `commands/*.md`
  - `skills/*/SKILL.md`
  - `agents/*.md`
  - `hooks/hooks.json`, `hooks/prompts/`
  - `marketplace.json` (for published plugins)
- **Codex extension profile** — `.codex/agents/*.toml` or Codex Skills API frontmatter present:
  - `.codex/agents/*.toml`
  - Codex Skills API frontmatter blocks inside `skills/*/SKILL.md` (`name:`, `metadata.short-description:`, `agents/openai.yaml`)
  - Bridged `skills/ll-<name>/` entries generated from `commands/*.md`
  - Codex adapter directories (e.g. `hooks/adapters/codex/`)
- **Other host extensions** — analogous fixed rulesets as more hosts gain plugin/extension surfaces.

When more than one tier-2 profile is active in the same repo (this repo is the canonical example: a CC plugin *also* adapted for Codex), a new cross-host coupling kicks in — see the generated-artifact category below.

**Tier 3 — little-loops only:**
- `.issues/` issue files
- `.ll/ll-config.json`
- `scripts/little_loops/` Python package
- `ll-*` CLI entry points in `pyproject.toml`
- `loops/*.yaml`

Tiers 1 and 2 are concrete, reusable rulesets — the file paths and cross-reference patterns are fixed by each host's own conventions, not by anything specific to this repo. Only tier 3 needs the per-project role-resolution treatment.

Here are the options, roughly ordered from highest leverage to lowest:

### 1. Phase 0: tiered project profile (highest leverage)

Detect project kind in tiers, not just language/tooling:

a. **Host profiles (tier 1):** `detect_host_profiles()` returns a *set* of active hosts. Check for `.claude/`, `.codex/`/`AGENTS.md`, and any other supported host markers independently. Each present host activates its fixed ruleset; `CLAUDE.md` and `AGENTS.md` are both treated as primary wiring search surfaces when their host is active.

b. **Plugin/extension profiles (tier 2):** Per-host plugin signals — `.claude-plugin/plugin.json` activates the CC-plugin ruleset; `.codex/agents/*.toml` or Codex Skills frontmatter activates the Codex-extension ruleset. Multiple can activate; when they do, the **generated-artifact coupling** (option 4) becomes load-bearing.

c. **Project-specific signals (tier 3):** e.g. `.ll/ll-config.json`, language manifests, `pyproject.toml` declaring `ll-*` entry points → enable project-specific rules; detect language(s), package manager, test runner, build system, doc framework.

Cache to `.ll/project-profile.json` (now shaped as `{host_profiles: [...], plugin_profiles: [...], project_signals: {...}}`) and feed it into every agent prompt. The host and plugin tiers ship as built-in profiles (since conventions per host are stable); only the third tier reframes downstream as "what files in this project play these roles?"

### 2. Read project conventions from the project itself

Before spawning agents, ingest the active hosts' authoritative wiring docs and any project-level docs: `.claude/CLAUDE.md` *and/or* `AGENTS.md` (whichever exist), `CONTRIBUTING.md`, `ARCHITECTURE.md`, top-level READMEs. Most non-trivial projects already document "Key Directories," entry points, and where tests/docs live. Use that as the wiring search surface rather than guessing. For multi-host repos, both `CLAUDE.md` and `AGENTS.md` are authoritative for their respective hosts — read both and treat them as peers, not alternates.

### 3. Generalize the coupling categories (tier 3 only)

For the project-specific tier, replace hardcoded terms with abstract roles the agents resolve per-project: `package_manifests`, `module_exports/barrels`, `framework_registrations`, `migrations`, `generated_artifacts`, `build_configs`, `lockfiles`, `ci_pipelines`, `type_specs` (OpenAPI/GraphQL/proto/.d.ts), `i18n_assets`, `test_fixtures/snapshots`. The agent prompts ask "find files playing role X" rather than "look in `plugin.json`." Tiers 1 and 2 keep their concrete path lists — no generalization needed.

### 4. Add coverage for high-miss categories that are currently absent

- **Source → generated host adaptations** (new — exposed by multi-host support):
  - Editing `skills/foo/SKILL.md` couples to the Codex frontmatter block inside that same file (managed by `ll-adapt-skills-for-codex`), and to the adapter script itself if the schema changes.
  - Editing `agents/foo.md` couples to `.codex/agents/foo.toml` via `ll-adapt-agents-for-codex`.
  - Editing `commands/foo.md` couples to the bridged `skills/ll-foo/` entry the Codex adapter produces.
  - Generalizes: any registered host-adapter script establishes a `source_artifact → generated_artifact + adapter_script` triple. Wire-issue should know "if you touch a source artifact that has a registered adapter, surface both the adapter script and the generated output as wiring points." This pattern extends to any future host (OpenCode, pi, …) the same way.
- DB migrations + ORM models
- Generated artifacts beyond host adapters (`docs/reference/schemas/`, codegen outputs, protobuf, OpenAPI clients)
- Lockfiles / dependency manifests when deps change
- CI workflows / Dockerfiles / Makefiles referencing changed paths
- Snapshot/golden/fixture files

### 5. Git-history coupling (project-agnostic signal)

For each file in `files_to_modify`, look at the last N commits touching it and surface co-changed files above a frequency threshold. Catches couplings nobody documented. Tradeoff: noisy; works best as a tie-breaker, not a primary signal.

### 6. Project-supplied wiring recipes

A `.ll/wiring-recipes.yaml` where the project declares "if you touch `src/api/**/*.ts`, also check `openapi.yaml` and `clients/generated/`." Best-of-both: generic mechanism + project-specific knowledge, but only useful if maintainers fill it in. This is also the natural place to register custom host adapters that aren't built-in.

### 7. Markdown link / cross-reference grep

Cheap, generic addition: grep for `](path/to/changed/file)` and `:doc:` style references in `**/*.md` and `**/*.rst`. For multi-host repos, sweep both `CLAUDE.md`-rooted and `AGENTS.md`-rooted reference webs.

## Main tradeoff

Options 1–3 are the structural fix and unblock everything else, but they require rewriting the agent prompts and adding profile detection (real work, but bounded). The tiered framing in option 1 — now reshaped as *sets* of host/plugin profiles rather than a single CC-shaped path — reduces the scope: tiers 1 and 2 are still gated activations of fixed rulesets, just one ruleset per active host. The actual per-project resolution work in option 3 only applies to tier 3 signals.

Option 4's **source→generated host-adaptation** category is the substantive new coupling that multi-host support forces; it's a genuinely new category, not a rephrasing of existing ones, and it's the reason the original "tier 1 = Claude Code" framing had to be widened.

Options 5–7 are additive — each one is small, but without 1–3 you're just trading one set of hardcoded categories for a larger set.

Recommend starting with 1 + 2 + 3 + the new host-adapter coupling from 4 as one coordinated change, then layering in the remaining items from 4 and 7 as easy wins, and treating 5 and 6 as separate later issues.
