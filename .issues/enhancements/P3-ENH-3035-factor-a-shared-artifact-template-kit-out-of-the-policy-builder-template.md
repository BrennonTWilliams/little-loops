---
id: ENH-3035
title: Factor a shared artifact template kit out of the policy-builder template
type: ENH
priority: P3
status: open
discovered_date: 2026-08-03
labels:
- artifact
- ll-artifact
parent: EPIC-3299
relates_to:
- FEAT-3308
- FEAT-3309
- FEAT-3304
- FEAT-3036
verify_verdict: VALID
---

# ENH-3035: Factor a shared artifact template kit out of the policy-builder template

Extract the reusable parts of the policy-builder HTML template into a small shared
template kit — page shell, design-token stamping, and the common head/asset-inlining
path — so the sql.js dashboard, the loop-fleet dashboard, and future artifacts build
on one set of conventions instead of each copying and drifting from policy-builder.
This is a refactor with a known shape, not an open design question; it was bundled
into the policy-builder template's decision gate and is split out because it pays
off the moment a second artifact template exists.

## Motivation

The parent epic exists in part to stop artifacts "accreting inconsistent per-artifact
conventions." Deferring this refactor until the Tier-3 gate guarantees exactly that:
the sql.js dashboard and the loop-fleet dashboard each ship a template, both copied
from policy-builder, and the kit is then extracted from three divergent copies
rather than one.

## Design Context

The artifact-templates design generalizes the policy-builder pattern: a `manifest.yaml`
+ Jinja2 body + assets layout under `.llat/`, with deterministic rendering
(`template + data.json → artifact`) and a separation of refinement (paid once at
template creation) from regeneration (cheap).

The template kit is the implementation vehicle for that design's shared parts: the
page shell, design-token stamping (via existing `load_design_tokens` /
`render_as_css_vars_themed`), and the head/asset-inlining path that policy-builder
currently does inline.

## Scope

- Identify what in the policy-builder template is genuinely artifact-agnostic
  (shell, token stamping, inlining) versus policy-builder-specific.
- Extract the agnostic parts into a template kit with a stable entry point.
- Pull design-token stamping out as its own unit, so token changes land in one place.
- Port policy-builder onto the kit — the refactor is not done until its sole
  existing consumer uses it.

## Non-goals

- Restyling or redesigning any existing artifact.
- Introducing a template engine or build step; artifacts stay single-file and
  dependency-free at view time.

## Acceptance Criteria

- [ ] A shared template kit module exists with a documented entry point.
- [ ] Design-token stamping is a separately callable unit, not inlined in a template.
- [ ] policy-builder renders byte-identically (or with reviewed, intentional diffs)
      after being ported onto the kit.
- [ ] The sql.js dashboard's artifact (FEAT-3304) is built on the kit rather than a
      copied template.
- [ ] **At least one templatized loop-generated artifact renders through the kit**
      (see Consumer mix below). A kit validated only by policy-builder and the sql.js
      dashboard has been validated against the wrong workload.
- [ ] The kit's token-stamping unit is reachable from the `templatize` token-lifting
      path (FEAT-3308) — i.e. it accepts a body whose token values were baked in as
      literals by a loop's prompt-time `design_tokens_context`, not only a body
      authored with stamp points.

## Consumer mix (added 2026-08-23)

Both consumers named in the original scope — `policy-builder` and the sql.js
dashboard — are hand-built data dashboards from the same lineage.
`policy-builder` is a 727-line `.tmpl` rendered by four `str.replace()` calls
(`cli/artifact.py:132-137`); the dashboard will be its sibling. A kit factored
from one and validated by the other will encode dashboard conventions and fit the
epic's primary workload — large, LLM-generated, self-contained artifacts from the
HTML loop family — badly or not at all.

The AC above therefore requires a third consumer from that family. If FEAT-3308
has not landed when this issue is implemented, satisfy it with a hand-templatized
loop artifact used as a fixture; the point is that the kit is exercised by a body
it did not author.

## Sequencing

Should land alongside or just before the sql.js dashboard — the first new artifact
is the forcing function. Does not gate the write-bridge work.

**Blocked on a hub decision (resolved 2026-08-23).** FEAT-3304 flagged that this
kit and FEAT-3036's Phase-1 `render` pipeline overlap, and that extracting the kit
before that is settled means "the kit gets extracted twice." FEAT-3036 now records
the packaging/engine/hash decisions (`.llat/` directory, sandboxed Jinja2,
separate lockfile), which is the fixed target this extraction builds against — the
contradiction the 2026-08-12 verification note flagged between this issue's Design
Context and FEAT-3036's Open Questions is closed in FEAT-3036's favour, matching
what this issue already assumed. Do not start the extraction against a different
shape.

## Verification Notes

**2026-08-12** (`/ll:verify-issues`): Frontmatter `id: 3035` did not match the
`ENH-NNNN` convention used by sibling issue files and has been corrected to
`id: ENH-3035`. Separately, this issue's Design Context presents a
`.llat/`+Jinja2+manifest.yaml packaging layout as settled, but sibling issue
FEAT-3036 (artifact templates design) still lists that packaging shape as an
open question — flagged here as needing reconciliation between the two
issues, not resolved as part of this verification pass.

- 2026-08-16: Issue body content is accurate and current; frontmatter carried a stale `verify_verdict: NON_VALID` left over from a prior --check run that contradicted the accurate body — corrected to `VALID` above. Verdict: NEEDS_UPDATE.

## Session Log
- `/ll:verify-issues` - 2026-08-16T16:40:23 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:59 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
