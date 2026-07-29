---
id: ENH-2920
type: enhancement
priority: P2
status: open
created: 2026-07-29
labels: [tooling, doctor, link-checker]
---

# ll-check-links: restore intended doc scope and classify non-authoritative HTTP statuses as non-fatal

## Status

open

## Summary

`ll-check-links` walks the entire repository tree instead of the documentation
surface it declares, and treats every HTTP error status as a broken link. Together
these produce a permanently-red `ll-doctor --full` gate reporting 600–800 "broken"
links, of which only a small residue are genuinely broken. Fix the scope regression
(`DEFAULT_DOC_FILES` is dead code) and add status-code tiering so the gate fires only
on statuses that actually assert a link is dead.

## Current Behavior

`ll-doctor --full` fails on `check_links` with 600–800 broken links. The count is not
reproducible between runs (616 in one `ll-doctor --full` run, 806 in a direct
`ll-check-links` run minutes later) — itself the tell that most failures are
rate-limiting artifacts rather than broken links.

Measured breakdown of one 806-link run:

| Error | Count | Reality |
|---|---:|---|
| HTTP 429 | 497 | Rate limiting — 10 concurrent workers hammering github.com |
| HTTP 403 | 120 | Auth-walled (SharePoint, Vertex grounding redirects) |
| HTTP 401 | 110 | Auth-walled (outlook.office365.com) |
| HTTP 404 | 72 | The only genuine broken-link candidates |
| 5xx / 400 | 7 | Transient server-side |

Scanned-file distribution shows the walk ranges far outside the documentation
surface: `docs/` 449, `thoughts/` 149, `.loops/` 144, `.issues/` 43 — including
`hooks/adapters/opencode/node_modules/zod/README.md` (vendored dependency) and
`.pytest_cache/README.md` (tool cache).

Of the 72 genuine 404s: ~33 are in `docs/research/dreaming-research-synthesis.md`
(bibliography link rot), 3 in vendored zod, 6 in `thoughts/`, 5 in `.issues/`. The
residue in maintained documentation is small.

## Root Cause

Two independent defects in `scripts/little_loops/link_checker.py`:

**1. Declared scope is dead code.** `DEFAULT_DOC_FILES` (line 40–44) declares the
intended surface:

```python
DEFAULT_DOC_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/**/*.md",
]
```

`grep -rn DEFAULT_DOC_FILES scripts/ --include='*.py'` returns **only its own
definition** — it is referenced nowhere. `check_links()` instead does:

```python
md_files = list(base_dir.rglob("*.md"))    # line 284
```

walking the entire tree: `node_modules/`, `.pytest_cache/`, `.loops/` run artifacts,
`thoughts/` scratch, `.issues/`. The intended scope was written and never wired up.

**2. Every HTTP error status is classified BROKEN.** `_check_url_once` (line 210–211):

```python
except urllib.error.HTTPError as e:
    return LinkOutcome.BROKEN, f"HTTP {e.code}"
```

No discrimination by status code. The `LinkOutcome.BROKEN` docstring (line 50) reads
"the host answered and said no" — but a 429 means "you asked too fast" and a 401/403
means "you are not authenticated," neither of which asserts the link is dead. Only
`BROKEN` gates the exit code (`has_errors`, line 118); `UNREACHABLE` is already
correctly non-fatal per ENH-2836.

## Expected Behavior

`ll-check-links` with no arguments checks only the documentation surface, and exits
non-zero only when a host authoritatively reports a link gone (404/410). Statuses
that reflect checker aggressiveness or missing credentials are reported for
visibility but do not gate, matching the ENH-2836 precedent for unreachable links.

## Proposed Solution

**Scope** — wire `DEFAULT_DOC_FILES` into `check_links()` as the default file set,
replacing the bare `rglob`. Keep a positional path override (already shown in
`--help` examples as `ll-check-links docs/`). Additionally apply a hard directory
denylist — `node_modules/`, `.pytest_cache/`, `.venv/`, `.git/`, `.loops/` — so an
explicit wider path still cannot drag in vendored or generated markdown.

**Status classification** — add a third outcome tier:

- `404`, `410` → `BROKEN` (fatal; the host asserts it is gone)
- `429`, `401`, `403`, `5xx` → new `INDETERMINATE` outcome — reported in output, does
  not gate exit code
- `--strict-network` gates `INDETERMINATE` as well as `UNREACHABLE`, consistent with
  existing behavior

**Rate-limit hygiene** — honor `Retry-After` on 429 with backoff in the existing
retry path, and lower the default `--workers` from 10. A 429 is evidence the checker
was too aggressive, not evidence about the link.

## Impact

The `ll-doctor --full` link gate is currently unactionable and permanently red, which
trains maintainers to ignore the entire `--full` exit code — eroding the value of
every other check it aggregates (`des_audit`, `design_tokens`, `host_map`,
`package_data`, and the rest). Fixing it restores a gate that can be trusted and
acted on, and removes pointless outbound HTTP traffic to auth-walled corporate URLs
captured in loop run artifacts.

## Acceptance Criteria

- [ ] `DEFAULT_DOC_FILES` is referenced by `check_links()`; no dead constant remains.
- [ ] `ll-check-links` with no arguments does not visit `node_modules/`,
      `.pytest_cache/`, `.loops/`, `thoughts/`, or `.issues/`.
- [ ] An explicit path argument still cannot pull in `node_modules/` or
      `.pytest_cache/` (denylist applies regardless of scope).
- [ ] HTTP 429/401/403/5xx are reported but do not set exit code 1; 404/410 still do.
- [ ] `--strict-network` gates on `INDETERMINATE` as well as `UNREACHABLE`.
- [ ] 429 responses honor `Retry-After` before retrying.
- [ ] Unit tests cover each status-code tier's outcome classification and the scope
      denylist, using a stubbed fetch layer (no live network in the suite).
- [ ] `ll-doctor --full` `check_links` passes on a clean tree, or reports a small
      actionable count of genuine 404s.

## Scope Boundaries

**In scope:** `scripts/little_loops/link_checker.py` scope resolution and HTTP status
classification; corresponding tests in `scripts/tests/`.

**Out of scope:** fixing the ~33 rotted bibliography URLs in
`docs/research/dreaming-research-synthesis.md`. That is content triage, not a tooling
defect — file separately once this lands and the real 404 list is legible. Consider
annotating that file as a citation list rather than chasing dead academic URLs.

Also out of scope: the `claude_md_suppression` and `auto_commit` ✗ marks in
`ll-doctor --full` output. Those are capability/config reporting, not failures.

## Notes

- Per project CI policy there is no hosted CI; tests live in `scripts/tests/` under
  `python -m pytest scripts/tests/` and must stub the fetch layer so the suite makes
  no live network calls.
- Related: ENH-2836 established the report-but-don't-gate stance for
  unreachable/timeout links. This extends the same reasoning to HTTP statuses that
  are not authoritative about link liveness.
