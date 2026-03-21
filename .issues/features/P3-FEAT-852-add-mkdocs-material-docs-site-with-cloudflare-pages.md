---
id: FEAT-852
type: FEAT
priority: P3
title: "Add MkDocs Material docs site with Cloudflare Pages"
discovered_date: 2026-03-20
discovered_by: capture-issue
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

## Use Case

A developer finds little-loops via the README, wants to understand how sprints work, and navigates to `docs.little-loops.ai` → Guides → Sprint Guide — without having to browse GitHub.

## Implementation Steps

1. Add `mkdocs.yml` at repo root with Material theme config and full nav structure
2. Add `docs/requirements.txt` (or `requirements-docs.txt`) pinning `mkdocs-material`
3. Connect repo to Cloudflare Pages dashboard; set build command (`mkdocs build`) and output dir (`site/`)
4. Add `docs.little-loops.ai` as custom domain in Cloudflare Pages; Cloudflare auto-creates the CNAME
5. Add `site/` to `.gitignore`
6. Verify build succeeds and site resolves at `docs.little-loops.ai`

## Integration Map

### Files to Create
- `mkdocs.yml` — nav config, theme settings, plugins
- `docs/requirements.txt` — `mkdocs-material==9.x`

### Files to Modify
- `.gitignore` — add `site/`

### Files to Exclude
- `docs/research/` — likely internal-only; decide whether to include
- `docs/demo/` — evaluate inclusion

### Documentation
- `README.md` — add link to docs site once live

## Impact

- **Priority**: P3 - Valuable for adoption, not blocking existing users
- **Effort**: Small - ~1 hour setup; no code changes, only config files
- **Risk**: Low - Additive only, no existing functionality affected
- **Breaking Change**: No

## Labels

`feat`, `docs`, `infrastructure`, `captured`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b316669-a54e-4b0e-bf7c-7cdcb231cb87.jsonl`
