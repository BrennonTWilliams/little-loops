# oh-my-pi (`omp`) Skill/Command Discovery Surface

**Status:** Audit complete — native (`.omp/`) skill and slash-command discovery
confirmed from the actual `@oh-my-pi/pi-coding-agent` package source.
**Last verified:** 2026-08-08
**Research issue:** FEAT-3103 (EPIC-2258), blocking `OmpEmitter.emit_skill`/
`emit_command` (FEAT-3105, decomposed from FEAT-2787)
**Package:** `@oh-my-pi/pi-coding-agent@17.1.3` (Bun package; source read from a
local install under `~/node_modules/@oh-my-pi/pi-coding-agent` /
`~/.npm-cache/@oh-my-pi/pi-coding-agent@17.1.3@@@1`, not upstream inference)

## Sources

Read directly from the installed package's TypeScript source (not docs, not
inferred from other hosts):

- `src/discovery/builtin.ts` — the `"native"` provider (`.omp/` + `~/.omp`),
  `PRIORITY = 100`, registers skill and slash-command loaders (`loadSkills`,
  `loadSlashCommands`) — this is the format `OmpEmitter` must target.
- `src/discovery/helpers.ts` — `scanSkillsFromDir` (skill directory scan),
  `loadFilesFromDir` (flat markdown-file scan used for commands), `SOURCE_PATHS`
  (per-provider base dirs), `parseAgentFields` (sibling agent-frontmatter
  parser, for contrast).
- `src/capability/skill.ts` — `Skill`/`SkillFrontmatter` capability
  definitions (`[key: string]: unknown` — untyped passthrough).
- `src/capability/slash-command.ts` — `SlashCommand` capability definition.
- `src/extensibility/skills.ts` — `loadSkills()`, the higher-level skill
  aggregator that consumes the `"native"` provider's output (source-toggle
  gating, dedup, collision handling); also documents `SKILL.md` body
  stripping (`buildSkillPromptMessage`).
- `src/extensibility/slash-commands.ts` — `loadSlashCommands()`, the
  higher-level command aggregator (`parseCommandTemplate`): frontmatter
  `description` handling, first-line fallback, `$ARGUMENTS`/`{{args}}`
  substitution.
- `~/.npm-cache/@oh-my-pi/pi-utils@17.1.3@@@1/src/frontmatter.ts` —
  `parseFrontmatter`, the shared YAML-frontmatter parser used for both
  skills and commands (governs foreign-key tolerance).

## Skill discovery (native `.omp/` provider)

### Directory layout

```
Project (walk-up, closest ancestor first, stopping at repoRoot or home):
  <ancestor>/.omp/skills/<skill-name>/SKILL.md

User:
  <agentDir>/skills/<skill-name>/SKILL.md
  # agentDir = getAgentDir(), profile-scoped: ~/.omp/profiles/<profile>/agent
  # (NOT bare ~/.omp/skills/ — profile scoping is native-provider-specific,
  #  confirmed by builtin.ts:284-290 `getAgentDir(), "skills"`)
```

Source: `src/discovery/builtin.ts:271-297` (`loadSkills`). Project scan walks
`getAncestorDirs(ctx.cwd, ctx.repoRoot ?? ctx.home)` and probes
`<ancestor>/.omp/skills/` at every level (multiple project-level skill roots
can be active simultaneously — not just the nearest one). This differs from
the analogous rules/system-prompt loaders in the same file, which use
`findNearestProjectConfigDir` (nearest-only, single match).

### File format

- One skill = one directory containing `SKILL.md` (`scanSkillsFromDir`,
  `src/discovery/helpers.ts:355-420`).
- Directories starting with `.` are skipped; only `fs.Dirent` entries that are
  a directory or symlink are scanned (`entry.isDirectory() ||
  entry.isSymbolicLink()`).
- Non-recursive: only immediate children of the skills root are scanned as
  skill dirs (`<dir>/<name>/SKILL.md`), no deeper nesting.
- `includeSelf` (a `SKILL.md` sitting directly at the scanned root, matching
  the Claude plugin-manifest `"skills": ["./"]` convention) exists as an
  option on `scanSkillsFromDir` but is **not** passed by the native provider's
  `loadSkills` — only Claude-plugin discovery (`discovery/claude-plugins.ts`)
  opts in. `emit_skill` should target the standard `<dir>/<name>/SKILL.md`
  shape, not a bare root `SKILL.md`.

### Frontmatter

`SKILL.md` is parsed with `parseFrontmatter` (shared YAML-frontmatter parser).
Recognized `SkillFrontmatter` fields (`src/capability/skill.ts:12-32`):

| Field | Type | Effect |
|---|---|---|
| `name` | `string` | Skill's invocation name. Falls back to the containing directory's basename if absent/blank (`src/discovery/helpers.ts:383-385`). |
| `description` | `string` | **Required** — the native provider calls `scanSkillsFromDir` with `requireDescription: true` (`builtin.ts:280`, `:289`); a `SKILL.md` with no `description` key is silently skipped, not loaded with an empty description. |
| `enabled` | `boolean` | `enabled: false` → skill is skipped entirely (`helpers.ts:377-379`), independent of `requireDescription`. |
| `hide` | `boolean` | Skill loads and is reachable via `skill://<name>` / `/skill:<name>`, but is omitted from the rendered system-prompt `<skills>` listing. |
| `disableModelInvocation` | `boolean` | Agent-Skills-standard (agentskills.io) equivalent of `hide`; kebab-case `disable-model-invocation` in raw YAML normalizes to this camelCase key. Either flag hides the skill from the prompt listing. |

Any other frontmatter key is preserved untyped (`SkillFrontmatter` declares
`[key: string]: unknown`) — **foreign/extra keys are tolerated**, never
rejected. This is a property of the shared `parseFrontmatter` parser (see
"Frontmatter tolerance" below), not something skill-specific.

Body handling: `buildSkillPromptMessage` strips the leading `---\n...\n---\n`
block via `content.replace(/^---\n[\s\S]*?\n---\n/, "").trim()` before
rendering the skill body into the prompt — i.e. the frontmatter block must be
the very first thing in the file (starts at byte 0, no leading blank line) for
the strip regex to match.

### Discovery gating (aggregator layer, not the raw provider)

`loadSkills()` in `src/extensibility/skills.ts` sits above the raw `"native"`
provider and applies `SkillsSettings` toggles
(`enablePiUser`/`enablePiProject`, mapped from `provider === "native"`),
include/ignore glob patterns, and de-dup by realpath + by name (case-sensitive
first-wins across providers, sorted by `compareSkillOrder`: name
case-insensitive, then name, then path). None of this changes the on-disk
format `emit_skill` must write — it only affects which already-discovered
skills make it into the final prompt.

## Slash-command discovery (native `.omp/` provider)

### Directory layout

```
Project:
  <cwd>/.omp/commands/*.md          (only when .omp/ itself is a non-empty dir
                                      at cwd — see getConfigDirs below)

User:
  <agentDir>/commands/*.md          # agentDir = getAgentDir(), profile-scoped
```

Source: `src/discovery/builtin.ts:329-359` (`loadSlashCommands`), driven by
`getConfigDirs(ctx)` (`builtin.ts:57-72`): unlike skills, this is **not** an
ancestor walk-up — it only checks `ctx.cwd` directly (`ifNonEmptyDir(ctx.cwd,
".omp")`) plus the profile-scoped user agent dir. A `.omp/` in a parent
directory that isn't `ctx.cwd` itself is invisible to command discovery
(skills' walk-up behavior does not apply here).

### File format

- Flat directory scan, non-recursive: `loadFilesFromDir` is called with
  `extensions: ["md"]` and no `recursive: true`, so `pattern = "*.md"` (not
  `**/*.md`) — subdirectories under `commands/` are **not** scanned. No
  namespacing/nesting convention (contrast with hosts that support
  `commands/git/commit.md` → `/git:commit`).
- One command = one `.md` file. Command name = filename with `.md` stripped
  (`name.replace(/\.md$/, "")`, `builtin.ts:339`).
- No `SLASH_COMMAND.md`-style directory wrapper — this is unlike skills.

### Frontmatter

Parsed lazily by the aggregator (`parseCommandTemplate` in
`src/extensibility/slash-commands.ts:36-52`), using the same
`parseFrontmatter`:

| Field | Type | Effect |
|---|---|---|
| `description` | `string` | Shown in command listings/autocomplete. If absent or blank, falls back to the first non-empty line of the body, truncated to 60 chars (`...` appended if truncated). |

No other frontmatter fields are read by the native command loader itself.
The raw `SlashCommand` capability item (`src/capability/slash-command.ts`)
carries only `name`, `path`, `content`, `level`, `_source` — frontmatter
parsing happens downstream in the aggregator, not at discovery time. Any
frontmatter key beyond `description` is parsed but unused by native
(harmless to include — see tolerance below).

Body handling: the frontmatter block is stripped before the command body is
used as the prompt template. The body supports argument substitution via
`$ARGUMENTS` / `{{args}}`-style placeholders, resolved by
`substituteArgs`/`prompt.render` in `src/utils/command-args.ts` /
`@oh-my-pi/pi-utils` — out of scope for `emit_command`'s own contract (ll's
existing `core._select_frontmatter_fields` + body-passthrough model already
matches this: write frontmatter ll controls, leave body prose as-is).

Level tag: loaded commands carry `level: "project" | "user"` from
`getConfigDirs`, surfaced in the UI as `"via OMP Project"` / `"via OMP User"`
(`slash-commands.ts:75-77`). `emit_command` does not need to produce this —
it's assigned at load time from which directory the file was found in, not
from frontmatter.

## Frontmatter tolerance (both skills and commands)

Confirmed at the parser level (`pi-utils/src/frontmatter.ts:106-175`,
shared by every capability including skills and commands):

- YAML frontmatter is parsed into a generic `Record<string, unknown>` — there
  is no schema/allowlist rejecting unrecognized keys. Consumers
  (`SkillFrontmatter`, the command aggregator) simply read the specific keys
  they care about and ignore the rest.
- Keys are normalized kebab-case → camelCase recursively
  (`disable-model-invocation` → `disableModelInvocation`), so ll's own
  frontmatter fields (any host-neutral metadata carried through
  `core._select_frontmatter_fields`) survive untouched as long as they're not
  literally `name`/`description`/`enabled`/`hide`/`disableModelInvocation`
  (skills) or `description` (commands) — those specific keys are
  interpreted, not just passed through.
- Malformed YAML degrades gracefully: on a parse error, the parser retries
  with ambiguous plain scalars auto-quoted, then falls back to naive
  `key: value` line parsing rather than failing the whole file (`level:
  "warn"` for user/project sources; the native provider's own bundled
  `EMBEDDED_SLASH_COMMANDS` use `level: "fatal"`, since a schema bug in a
  bundled template is a real bug, not fuzzy user input).

**Conclusion: both surfaces tolerate extra/foreign frontmatter keys.** No
special stripping is required before writing `emit_skill`/`emit_command`
output beyond mapping to the recognized keys above; unrecognized keys ll
happens to carry (e.g. from a Claude Code source skill's frontmatter) are
inert on the omp side, not rejected.

## Summary for `OmpEmitter.emit_skill` / `emit_command` (FEAT-3105)

```
emit_skill(skill, dest_dir, level):
  write to:  <dest_dir>/skills/<skill.name>/SKILL.md
             where dest_dir = ".omp" (project) or "<agentDir>/.omp"-equivalent (user)
  frontmatter: must include `description` (required — omitting it makes the
               skill invisible to native discovery, not just under-described)
  frontmatter: may include `name` (else dir basename is used — prefer setting
               name explicitly so directory basename and skill name never drift)
  frontmatter: `hide: true` / `disableModelInvocation: true` are the native
               vocabulary for "loaded but not prompt-listed" — map from
               whichever source field ll's IR already tracks for that concept
  body: skill markdown content only — no wrapper needed beyond the
        `---\n...\n---\n` block being exactly at the file start

emit_command(command, dest_dir, level):
  write to:  <dest_dir>/commands/<command.name>.md   (flat — no subdirs)
  frontmatter: `description` (optional but should always be set — omission
               falls back to a truncated first line, which is lossy for ll's
               already-authored descriptions)
  body: command template, unmodified passthrough is sufficient — omp's own
        $ARGUMENTS/{{args}} substitution runs downstream of discovery
```

## Out of scope here

- Agent-artefact discovery (`.omp/agents/`, `output:` frontmatter contract) —
  already resolved by FEAT-2797, not re-derived here.
- Custom TypeScript commands (`extensibility/custom-commands/`) — a distinct,
  code-executing command type (`index.ts`/`index.js` modules under
  `commands/<name>/`), unrelated to the markdown slash-command surface
  `emit_command` targets.
- CLI invocation flags (`--mode json`, `--tools`, etc.) — covered by
  `thoughts/research/omp-headless-flags.md` (FEAT-1850).
- Managed (auto-learn) skills (`~/.omp/agent/managed-skills`) — an
  OMP-internal auto-generated skill source, not something `emit_skill`
  writes to.
