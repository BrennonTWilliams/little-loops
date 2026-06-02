---
id: ENH-1768
type: ENH
priority: P3
status: done
captured_at: '2026-05-28T19:48:44Z'
completed_at: '2026-05-28T20:11:43Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
parent: EPIC-1751
relates_to:
- EPIC-1751
- FEAT-1747
- FEAT-1748
- FEAT-1749
- FEAT-1750
labels:
- enh
- design-system
- loops
- config
- init
---

# ENH-1768: Multi-profile design-tokens system with an active profile selector

## Summary

Generalize the little-loops design-tokens system from a *single bundled
palette* into a **multi-profile** system. Each profile is a complete
token set (primitives + semantic + themes, and ideally typography +
spacing). Exactly one profile is **active** at a time, and the active
profile is what every artifact-producing loop (and any future
visual-output consumer) picks up via `design_tokens_context`.

The current implementation (FEAT-1747 → FEAT-1750) ships exactly one
palette — a Bootstrap-flavored neutral grayscale + Tailwind blue +
orange accent under `templates/design-tokens/`. That single palette is
the *only* thing every loop in every project can ever see. There is no
mechanism to swap aesthetics without hand-editing JSON.

The fix is a system-level change: introduce **profiles** as a
first-class concept, ship exactly **three** starter profiles (`default`
+ two opinionated alternatives), and add a one-line config switch
(`design_tokens.active: <name>`) that artifact loops transparently pick
up. Loops do not change; the tokens layer does. The `generate`
no-new-colors clamp stays untouched — the fix is better inputs, not a
weaker gate.

`html-website-generator.yaml` is the motivating witness — its
`originality` criterion (2× weighted, threshold 6) can never clear the
ceiling under the current single-cage palette — but this issue is
about the tokens system, not that loop.

## Current Behavior

- `templates/design-tokens/` ships exactly one palette. There is no
  notion of multiple profiles, no `active` selector, no way to ship
  alternatives.
- `DesignTokensConfig` (`scripts/little_loops/config/features.py`) has
  `enabled` and `path` only.
- `design_tokens.py` resolves token files from the flat top-level of
  `<path>/` — `primitives.json`, `semantic.json`, `themes/light.json`,
  `themes/dark.json`.
- `/ll:init` Round 7 offers only one bundled default; the user can
  point at an existing directory or skip, but cannot pick a vibe.
- `/ll:configure` has no design-tokens area for switching profiles
  (because there are none).
- `html-website-generator.yaml`'s `generate` state forbids inventing
  new colors outside the injected palette, so loops are forced into
  whatever single palette is installed.
- Net effect: every project shares the same generic SaaS aesthetic for
  every artifact, and `originality`-weighted scoring loops are
  structurally capped.

## Expected Behavior

- `ll-config.json` accepts `design_tokens.active: <profile-name>`
  (default `"default"`), and optionally
  `design_tokens.profiles_dir` (defaults to `<path>/profiles/`).
- `.ll/design-tokens/profiles/<name>/` holds each profile's token
  files. Switching the active profile is a one-line config change; no
  loop YAML edits required.
- `templates/design-tokens/profiles/` ships exactly three starter
  profiles, each WCAG AA verified: `default` (the current accessible
  baseline, moved here unchanged on the color side, augmented with a
  type + spacing layer), `editorial-mono`, and `warm-paper`. All three
  profiles include the typography + spacing layer — it's part of the
  profile shape contract, not an opt-in.
- `/ll:init` Round 7 offers the user a profile pick after they opt in
  to design tokens.
- `/ll:configure` exposes a `design_tokens` area that lists installed
  profiles, shows which is active, and lets the user switch.
- `ll-loop run` / `ll-loop resume` resolve `design_tokens_context` from
  the active profile only. Inactive profiles are inert files on disk.
- All six artifact loops (`hitl-compare`, `hitl-md`,
  `html-website-generator`, `html-anything`, `svg-image-generator`,
  `svg-textgrad`) keep working unchanged.
- If `design_tokens.active` names a profile that doesn't exist, the
  session_start hook warns and the loader degrades to no tokens (no
  crash).

## Context

**Conversation mode**: Identified while reviewing whether the bundled
design-token defaults are a good aesthetic fit for
`scripts/little_loops/loops/html-website-generator.yaml`. The
conclusion: a *single* shipped palette can never be a good fit for
every artifact loop in every project. The system needs profiles +
an active selector.

Quoted from the `plan` state's brief:
> Anti-patterns to avoid: purple gradients on white cards, unmodified
> stock components, generic hero sections, AI-generated filler patterns

Quoted from the `generate` state:
> If design tokens are provided above, use their semantic names and
> resolved values for colors; do not invent new color values outside the
> token palette

The current single-palette bundle conflicts with the first quote and
is enforced by the second. Profiles let projects (and ll itself) ship
alternatives without rewriting either prompt.

## Motivation

- Design intent is project-specific. A B2B dashboard, an editorial
  site, and a brutalist art project should not share the same token
  set. The system should ship a few well-shaped starting points and
  let projects pick.
- The currently-bundled palette is also incomplete — only colors, no
  type scale, no spacing rhythm, no radii or shadows. Distinctiveness
  in artifact output (HTML pages, SVGs) comes mostly from typography
  and spacing. Profiles are a natural unit to extend with these.
- A single active-profile selector keeps the loop side trivial: loops
  continue to read `${context.design_tokens_context}` and don't know
  how it was assembled. The profile system lives entirely in
  config + loader + init/configure.
- The witness is the originality cap in `html-website-generator.yaml`:
  with one palette as the only option, `originality` (2× weighted,
  threshold 6) cannot escape the safe-SaaS ceiling. Profiles dissolve
  that constraint at the system level instead of patching it at the
  loop level.

## Implementation Steps

1. **Schema + dataclass.** Add `active` (string, default `"default"`)
   and optional `profiles_dir` (string) to the `design_tokens` block in
   `config-schema.json` and to `DesignTokensConfig`. Update
   `BRConfig` wiring in `scripts/little_loops/config/core.py`.
2. **Loader.** In `scripts/little_loops/design_tokens.py`, resolve
   token-file paths from `<path>/profiles/<active>/` instead of the
   flat layout. Keep a fallback to the legacy flat layout for projects
   already on FEAT-1746/1747. Emit a session_start warning when
   `active` names a missing profile, and degrade to no tokens (no
   crash).
3. **Bundle starter profiles.** Restructure `templates/design-tokens/`
   into `templates/design-tokens/profiles/{default,editorial-mono,warm-paper}/`.
   Move the current four files into `default/` unchanged (colors stay
   identical to today). Author two more complete profiles
   (`editorial-mono`, `warm-paper`), each WCAG AA verified. Add a
   typography + spacing layer (`typography.json` + `spacing.json`, or
   merged into `semantic.json`) to all three profiles — same key shape,
   different values. The type/spacing layer is part of the profile
   contract; do not ship a profile without it.
4. **Init materialization.** Update `skills/init/SKILL.md` Step 8
   item 6 to copy `templates/design-tokens/profiles/` into
   `.ll/design-tokens/profiles/`, and write
   `design_tokens.active: <chosen>` into config.
5. **Init UX.** Update `skills/init/interactive.md` Round 7 so that
   after the user opts in to design tokens, a profile picker is
   presented (default selected, the others described with a one-line
   vibe).
6. **Configure area.** Add a design-tokens area in
   `skills/configure/SKILL.md` + `skills/configure/areas.md`: list
   installed profile names from `.ll/design-tokens/profiles/`, show
   which is active, let the user switch (writes `active` to config).
7. **Loop wiring (no YAML change).** Verify the `run.py` and
   `lifecycle.py` injection points still produce
   `design_tokens_context` correctly under the profile layout — the
   six artifact loop YAMLs should require no edits.
8. **Tests.**
   - `scripts/tests/test_design_tokens.py`: profile resolution,
     missing-profile fallback, switching `active` changes resolved
     output, legacy-flat-layout fallback.
   - `scripts/tests/test_config.py` and `test_config_schema.py`:
     `active` / `profiles_dir` fields parse and round-trip.
   - `scripts/tests/test_builtin_loops.py`: existing per-loop
     `test_context_has_design_tokens_context` keeps passing under
     profile layout.
   - `scripts/tests/test_feat1756_init_wiring.py`: materialization
     writes profile dirs and `active` config.
   - `scripts/tests/test_feat1757_configure_wiring.py`: configure area
     can read installed profiles and switch active.
9. **Witness check.** Run `ll-loop run html-website-generator
   "a small bakery site"` against each shipped profile by toggling
   `design_tokens.active` between runs. Confirm visual output is
   meaningfully different across profiles, and that the non-default
   profiles raise the `critique.md` originality scores. Manual
   quality gate.

## API/Interface

- `ll-config.json` gains `design_tokens.active` (default `"default"`)
  and `design_tokens.profiles_dir` (default `<path>/profiles/`). Both
  optional; existing FEAT-1746/1747 configs continue to work via the
  legacy-layout loader fallback.
- Directory contract: `<design_tokens.path>/profiles/<name>/{primitives.json,semantic.json,themes/light.json,themes/dark.json,...}`
  where `<name>` matches `design_tokens.active`.
- `design_tokens.py` external surface unchanged; profile resolution
  happens inside the loader.
- Loop YAML public surface unchanged; `${context.design_tokens_context}`
  continues to work and now reflects the active profile.

## Scope Boundaries

### In scope

- Config schema + dataclass changes for `active` and `profiles_dir`.
- Loader changes to resolve from `profiles/<active>/`, with legacy
  fallback and missing-profile warning.
- Restructuring `templates/design-tokens/` into per-profile dirs and
  authoring exactly 3 starter profiles: `default` (current bundle
  moved here, colors unchanged), `editorial-mono`, `warm-paper`.
- Adding a typography + spacing layer to all 3 profiles (part of the
  profile shape contract).
- `/ll:init` Round 7 profile picker + Step 8 materialization update.
- `/ll:configure` design-tokens area for switching active profile.
- Tests covering schema, loader, materialization, configure switching,
  and per-loop context injection under the new layout.

### Out of scope

- Per-loop profile overrides (a loop YAML pinning a non-active
  profile). Possible later, not now.
- Profile inheritance / composition (`extends: default`). Possible
  later.
- Softening the `generate` "no new colors outside the palette" clamp
  in the artifact loops. Orthogonal — addressed only as a follow-up
  if the witness check (step 9) shows profiles alone don't move
  originality scores enough.
- Style Dictionary / Theo CSS-var transforms (still future per
  EPIC-1751).
- Runtime WCAG contrast validation of user-authored profiles
  (verified at author-time only).

## Impact

- **Priority**: P3 — quality and flexibility improvement on a P3 epic.
  No user is blocked; existing single-palette projects continue to
  work via legacy-layout fallback.
- **Effort**: Medium — touches schema, loader, two skills (init +
  configure), templates restructure, three authored profiles, and
  several test files. Larger than a single FEAT slice; consider
  decomposing into 2–3 children (schema/loader, profile content,
  init+configure wiring) if it lands as an EPIC.
- **Risk**: Low–Medium. The loader change is the highest-risk piece —
  legacy-layout fallback must be exercised in tests so existing
  projects don't break on upgrade. Additive bundled profiles don't
  affect existing consumers.
- **Breaking Change**: No, given the legacy-flat-layout fallback in
  the loader. (If the fallback is dropped in a future release, that
  becomes a major-version concern; flag in changelog.)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Design-tokens injection site for loops |
| guidelines | .claude/CLAUDE.md | Config + skill authoring patterns |

## Decision Record

- **2026-05-28** — Locked in **Option A** (ship more/better profiles,
  keep the clamp). Rejected Option B (soften the `generate`
  no-new-colors clamp) because it would convert tokens from
  source-of-truth to advisory, undermining the invariant FEAT-1747/1748
  shipped for projects that opted in *for* consistency. The clamp is
  doing its job; the bug is that the *default* it enforces is generic.
- **Profile count** — Exactly 3 (`default` + 2 alternatives). Rejected
  a third "brutalist" alternative from the original brief as sprawl;
  two alternatives are enough to prove the profile system without
  overcommitting on taste-driven design work.
- **Brutalist profile** — Not shipping. If demand surfaces later, add
  as a follow-up.

## Follow-ups (out of scope here)

- Per-loop profile overrides via loop YAML (e.g.
  `context.design_tokens_profile: editorial-mono`).
- Profile inheritance / composition (`extends: default`).
- If the step-9 witness check shows that *opinionated* profiles still
  don't lift originality scores enough, *then* file a separate ENH to
  revisit the clamp. Until that evidence exists, don't.

## Labels

`enh`, `design-system`, `loops`, `config`, `init`, `captured`

---

## Status

**Done** | Created: 2026-05-28 | Completed: 2026-05-28 | Priority: P3

## Resolution

Multi-profile design-tokens system landed:

- **Schema + dataclass** (`config-schema.json`, `scripts/little_loops/config/features.py`): added `design_tokens.active` (default `"default"`) and `design_tokens.profiles_dir` (default `null` → `"profiles"`).
- **Loader** (`scripts/little_loops/design_tokens.py`): resolves token files from `<path>/<profiles_dir or "profiles">/<active>/`. Falls back to legacy flat layout when no `profiles/` dir exists (pre-ENH-1768 projects keep working). Missing active profile under an existing `profiles/` emits a stderr warning and degrades to None (no crash). Now also loads `typography.json` and `spacing.json` alongside primitives/semantic/themes.
- **Session-start hook** (`scripts/little_loops/hooks/session_start.py`): warns when `design_tokens.active` names a profile that doesn't exist under `<path>/profiles/`.
- **Templates** (`templates/design-tokens/profiles/`): 3 starter profiles ship, each with the full 6-file layer (primitives, semantic, typography, spacing, themes/light, themes/dark) and WCAG-AA-verified body text contrast:
  - `default` — existing accessible neutral grayscale + blue brand + orange accent (colors unchanged from pre-ENH-1768).
  - `editorial-mono` — serif body, display-sans heads, true neutrals, single deep-ink-red accent. Long-read rhythm.
  - `warm-paper` — humanist serif, cream surfaces, soft brown text, terracotta accent.
- **Init** (`skills/init/SKILL.md` Step 8 + `skills/init/interactive.md` Round 7): Round 7 follow-up adds a profile picker after the user opts in to design tokens; materialization copies all 3 profiles and writes `design_tokens.active`.
- **Configure** (`skills/configure/areas.md`, `skills/configure/show-output.md`): design-tokens area lists installed profiles, surfaces `active`/`profiles_dir`, and lets the user switch.
- **Tests** (`scripts/tests/test_enh1768_profile_system.py`, plus updates to `test_design_tokens.py`'s integration block): cover profile resolution, missing-profile degradation, legacy fallback, switching active, typography/spacing layer load, bundled-template structure, schema fields, and init/configure wiring. Full suite: 8024 passed, 5 skipped.
- **Loop YAMLs**: unchanged. `${context.design_tokens_context}` continues to work and now reflects the active profile.

Out-of-scope (per Decision Record): per-loop profile overrides, profile inheritance, softening the no-new-colors clamp, runtime WCAG validation.

The manual step-9 witness check (running `html-website-generator` against each profile and comparing originality scores) is a follow-up — not blocking completion of the system-level change this issue captures.

## Session Log
- `/ll:manage-issue` - 2026-05-28T20:11:43Z - manage-issue session
- `/ll:decide-issue` - 2026-05-28T19:58:58 - `b6938ab1-fd59-4062-9b77-150da2247838.jsonl`
- `/ll:ready-issue` - 2026-05-28T19:56:14 - `48672b3d-8007-4e81-85e5-56ce5cf17dc1.jsonl`
- `/ll:capture-issue` - 2026-05-28T19:48:44Z - `74b05beb-27ad-4237-9e64-a76221b1fb65.jsonl`
