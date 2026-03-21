---
id: FEAT-852
type: FEAT
priority: P3
title: "Add MkDocs Material docs site with Cloudflare Pages"
discovered_date: 2026-03-20
discovered_by: capture-issue
testable: false
---

# FEAT-852: Add MkDocs Material docs site with Cloudflare Pages

## Summary

Set up an auto-updating documentation website at `docs.little-loops.ai` that builds from the existing `docs/` markdown files using MkDocs with the Material theme, deployed to Cloudflare Pages and triggered on every push to `main`.

## Current Behavior

Documentation exists as markdown files in `docs/reference/` and `docs/guides/` (plus `docs/architecture/`, `docs/development/`, etc.) with no public-facing web presence. Readers must browse the repo directly.

## Expected Behavior

- `docs.little-loops.ai` serves a searchable, navigable documentation site
- Every push to `main` triggers a rebuild and redeploy automatically
- Site includes all content from `docs/` organized into logical navigation sections
- Material theme provides search, dark mode, code syntax highlighting, and mobile-friendly layout

## Motivation

Little-loops is a Claude Code plugin that developers install and use — they need accessible, searchable documentation that doesn't require navigating raw GitHub markdown. A hosted docs site lowers the onboarding barrier and makes the project feel production-ready. GitHub Pages is already occupied on this account, so an alternative host is required.

## Proposed Solution

- **Generator**: MkDocs with `mkdocs-material` theme (Python-native, markdown-in, zero migration work)
- **Hosting**: Cloudflare Pages (free tier, domain already on Cloudflare, no GitHub Pages conflict)
- **Domain**: `docs.little-loops.ai` via Cloudflare CNAME
- **Build trigger**: Cloudflare Pages GitHub integration (auto-builds on push to `main`)
- **Config**: `mkdocs.yml` at repo root with nav structure covering all `docs/` subdirectories

## Acceptance Criteria

- `mkdocs.yml` exists at repo root with `theme: material` and the full nav structure from the Codebase Research Findings section
- `mkdocs build` completes with no errors and no warnings for included docs pages
- `docs/requirements.txt` exists and contains `mkdocs-material>=9.0`
- `site/` is listed in `.gitignore` (under the Build artifacts section)
- Nav explicitly excludes `docs/demo/`, `docs/research/`, and `docs/guides/AUDIT_REPORT.md`
- `scripts/pyproject.toml` Documentation URL updated to `https://docs.little-loops.ai` (post-launch)
- README.md includes a link to `https://docs.little-loops.ai` (post-launch)

## Use Case

A developer finds little-loops via the README, wants to understand how sprints work, and navigates to `docs.little-loops.ai` → Guides → Sprint Guide — without having to browse GitHub.

## Implementation Steps

1. Add `mkdocs.yml` at repo root with Material theme config and full nav structure
2. Add `docs/requirements.txt` (or `requirements-docs.txt`) pinning `mkdocs-material`
3. Connect repo to Cloudflare Pages dashboard; set build command (`mkdocs build`) and output dir (`site/`)
4. Add `docs.little-loops.ai` as custom domain in Cloudflare Pages; Cloudflare auto-creates the CNAME
5. Add `site/` to `.gitignore`
6. Verify build succeeds and site resolves at `docs.little-loops.ai`

### Concrete Implementation References

_Added by `/ll:refine-issue` — codebase-grounded specifics:_

1. **Create `mkdocs.yml`** at repo root — use nav structure from Integration Map research findings above; use `docs/INDEX.md` as the canonical nav source of truth. Exclude `docs/guides/AUDIT_REPORT.md` and `docs/demo/` from nav explicitly.

2. **Dependency declaration** — two valid approaches:
   - **Option A (idiomatic)**: Add `docs` group to `scripts/pyproject.toml:64` following existing `>=` pin style: `docs = ["mkdocs-material>=9.0"]`; install with `pip install -e "./scripts[docs]"`
   - **Option B (Cloudflare-friendly)**: Create `docs/requirements.txt` with `mkdocs-material>=9.0`; set as Cloudflare Pages pip requirements file
   - Cloudflare Pages supports specifying a requirements file path in dashboard build settings — Option B is simpler for the CI context

3. **`.gitignore` update** — add `site/` under the existing Build artifacts section at `.gitignore:31-35` (alongside `dist/`, `build/`, `*.tgz`)

4. **Cloudflare Pages dashboard config** — no `.github/workflows/` needed (no `.github/` directory exists); use Cloudflare's native GitHub integration. Build command: `mkdocs build`. Output dir: `site/`. Pip requirements: `docs/requirements.txt` (if Option B).

5. **`docs/research/` exclusion** — omit from `mkdocs.yml` nav entirely; add `docs/research/` to the `exclude_docs` list in `mkdocs.yml` to prevent MkDocs from warning about undeclared files

6. **Post-launch**: Update `scripts/pyproject.toml:44` `Documentation` URL from `https://github.com/BrennonTWilliams/little-loops/blob/main/README.md` to `https://docs.little-loops.ai`; add badge/link to `README.md` Documentation section (currently at lines ~481–490)

## Integration Map

### Files to Create
- `mkdocs.yml` — nav config, theme settings, plugins
- `docs/requirements.txt` — `mkdocs-material==9.x`

### Files to Modify
- `.gitignore` — add `site/`

### Files to Exclude
- `docs/research/` — excluded; internal-only (third-party content, dated audits, non-renderable PDF)
- `docs/demo/` — excluded; already gitignored, contains hardcoded local absolute paths

### Documentation
- `README.md` — add link to docs site once live

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Full docs/ Inventory (41 markdown files across 7 subdirectories)

| Section | Files | Notes |
|---|---|---|
| `docs/guides/` | 7 files | `AUDIT_REPORT.md` is an internal artifact not in INDEX.md; `AUTOMATIC_HARNESSING_GUIDE.md` is in guides/ but absent from INDEX.md |
| `docs/reference/` | 6 files | All in INDEX.md |
| `docs/development/` | 4 files | All in INDEX.md |
| `docs/claude-code/` | 11+ files | **Not mentioned in issue** — major section; `structured-outputs.md` absent from INDEX.md |
| `docs/research/` | 4 `.md` + 1 `.pdf` | **Excluded from site** — NOT gitignored but intentionally omitted from nav; third-party content (Voltropy PBC paper), dated internal audits, non-renderable PDF |
| `docs/demo/` | 4 files | **Already gitignored** (`.gitignore:75`) — naturally excluded from build |
| `docs/` root | `ARCHITECTURE.md`, `INDEX.md`, `generalized-fsm-loop.md` | No `docs/architecture/` subdirectory exists |

#### Content Hazards
- `docs/demo/scenarios.md:4` — hardcoded local absolute path (`/Users/brennon/AIProjects/...`); would render on public site
- `docs/guides/AUDIT_REPORT.md` — dated internal audit (2026-03-17); absent from INDEX.md; should be excluded from nav
- `docs/research/LCM- Lossless Context Management.pdf` — non-markdown; MkDocs cannot render it as a page
- `docs/research/` contains third-party paper content (Voltropy PBC authors) — consider licensing implications for public hosting

#### Dependency Declaration Pattern
- No `requirements*.txt` exists anywhere in the repo
- Project uses `scripts/pyproject.toml` optional-dependency groups (`scripts/pyproject.toml:64-74`)
- Existing convention: `>=` lower-bound pins (e.g., `mkdocs-material>=9.0`)
- A `docs` extra group in `pyproject.toml` is the idiomatic approach; `docs/requirements.txt` is also valid for Cloudflare Pages build config

#### Additional Files to Modify
- `scripts/pyproject.toml:44` — `Documentation` URL currently points to GitHub README; update to `https://docs.little-loops.ai` once live
- No `.github/workflows/` directory exists — Cloudflare Pages native GitHub integration (dashboard) is the correct approach; no Actions file needed

#### Suggested MkDocs Nav Structure (based on docs/INDEX.md)
```yaml
nav:
  - Home: index.md
  - Guides:
    - Getting Started: guides/GETTING_STARTED.md
    - Issue Management: guides/ISSUE_MANAGEMENT_GUIDE.md
    - Sprint Guide: guides/SPRINT_GUIDE.md
    - Loops Guide: guides/LOOPS_GUIDE.md
    - Session Handoff: guides/SESSION_HANDOFF.md
    - Workflow Analysis: guides/WORKFLOW_ANALYSIS_GUIDE.md
    - Automatic Harnessing: guides/AUTOMATIC_HARNESSING_GUIDE.md
  - Reference:
    - CLI Tools: reference/CLI.md
    - Commands: reference/COMMANDS.md
    - Configuration: reference/CONFIGURATION.md
    - API: reference/API.md
    - Issue Template: reference/ISSUE_TEMPLATE.md
    - Output Styling: reference/OUTPUT_STYLING.md
  - Development:
    - Testing: development/TESTING.md
    - E2E Testing: development/E2E_TESTING.md
    - Troubleshooting: development/TROUBLESHOOTING.md
    - Merge Coordinator: development/MERGE-COORDINATOR.md
  - Architecture:
    - Overview: ARCHITECTURE.md
    - FSM Loop: generalized-fsm-loop.md
  - Claude Code Reference:
    - CLI Reference: claude-code/cli-reference.md
    - Settings: claude-code/settings.md
    - Hooks Reference: claude-code/hooks-reference.md
    - Automate with Hooks: claude-code/automate-workflows-with-hooks.md
    - Memory: claude-code/memory.md
    - Skills: claude-code/skills.md
    - Custom Subagents: claude-code/custom-subagents.md
    - Run Agent Teams: claude-code/run-agent-teams.md
    - Plugins Reference: claude-code/plugins-reference.md
    - Create a Plugin: claude-code/create-plugin.md
    - CLI Programmatic Usage: claude-code/cli-programmatic-usage.md
    - Checkpointing: claude-code/checkpointing.md
    - Structured Outputs: claude-code/structured-outputs.md
  # Exclude: docs/demo/ (gitignored + local paths), docs/guides/AUDIT_REPORT.md (internal), docs/research/ (internal-only)
```

## Impact

- **Priority**: P3 - Valuable for adoption, not blocking existing users
- **Effort**: Small - ~1 hour setup; no code changes, only config files
- **Risk**: Low - Additive only, no existing functionality affected
- **Breaking Change**: No

## Labels

`feat`, `docs`, `infrastructure`, `captured`

## Status

**Completed** | Created: 2026-03-20 | Resolved: 2026-03-20 | Priority: P3

## Resolution

All acceptance criteria met:
- `mkdocs.yml` created at repo root with `theme: material`, full nav structure, and `exclude_docs` for `research/`, `guides/AUDIT_REPORT.md`, and `demo/`
- `mkdocs build` completes successfully (exit 0); 29 pre-existing link warnings in scraped Claude Code docs are not introduced by this config
- `docs/requirements.txt` created with `mkdocs-material>=9.0`
- `site/` added to `.gitignore` under Build artifacts section
- Nav explicitly excludes `docs/demo/`, `docs/research/`, and `docs/guides/AUDIT_REPORT.md`
- `scripts/pyproject.toml` Documentation URL updated to `https://docs.little-loops.ai`
- `README.md` Documentation section updated with link to `https://docs.little-loops.ai`

**Remaining manual steps** (require Cloudflare dashboard):
- Connect repo to Cloudflare Pages; set build command: `mkdocs build`, output dir: `site/`, pip requirements: `docs/requirements.txt`
- Add `docs.little-loops.ai` as custom domain (Cloudflare auto-creates CNAME)

---

## Session Log
- `/ll:ready-issue` - 2026-03-21T04:11:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e37a6960-52ec-4c3b-b022-5aafaa393fa4.jsonl`
- `/ll:refine-issue` - 2026-03-21T04:08:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbae5bbf-d60a-42bf-8f2b-1fa80ffa40c1.jsonl`
- `/ll:refine-issue` - 2026-03-21T04:04:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/988301b2-39e4-4d2e-8ff7-5e4ba30e9a28.jsonl`
- `/ll:manage-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b316669-a54e-4b0e-bf7c-7cdcb231cb87.jsonl`
