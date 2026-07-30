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
definition** — it is referenced nowhere. `check_markdown_links()` (line 259, the
function behind the `main_check_links` CLI entry in `cli/docs.py:313`) instead does:

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

There is a **second classification site**: line 208 returns
`LinkOutcome.BROKEN, f"HTTP {response.status}"` for non-2xx statuses that come back
through the success path (no exception raised). Both sites need the same tiering.

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

**Scope** — wire `DEFAULT_DOC_FILES` into `check_markdown_links()` as the default
file set, replacing the bare `rglob`. Keep a positional path override (already shown
in `--help` examples as `ll-check-links docs/`). Additionally apply a hard directory
denylist — `node_modules/`, `.pytest_cache/`, `.venv/`, `.git/`, `.loops/`, `.ll/` —
so an explicit wider path still cannot drag in vendored or generated markdown
(stray/quarantined `.ll/` contents included).

**Status classification** — add a third outcome tier via a single shared
status-code classifier applied at **both** sites (the non-2xx success path at line
208 and the `HTTPError` handler at line 210–211):

- `404`, `410` → `BROKEN` (fatal; the host asserts it is gone)
- `429`, `401`, `403`, `5xx` → new `INDETERMINATE` outcome — reported in output, does
  not gate exit code
- `--strict-network` gates `INDETERMINATE` as well as `UNREACHABLE`, consistent with
  existing behavior

The tier must be threaded through the result model and every consumer:
`LinkResult.status`, `LinkCheckResult` counters, `has_errors`, the JSON formatter
(`"has_errors"` key, line 527), and the `ll-doctor --full` adapter
(`cli/doctor.py:774` `_full_check_links_data()`), which currently gates on
`result.broken_links > 0` and string-filters `r.status == "broken"` /
`"unreachable"`. The adapter should surface `INDETERMINATE` as an informational
finding, the way it already handles unreachable.

**Rate-limit hygiene** — honor `Retry-After` on 429 with backoff in the existing
retry path, capping the honored delay (e.g. ≤30s) and the total per-run retry
budget so a large or adversarial `Retry-After` cannot stall the run; and lower the
default `--workers` from 10. A 429 is evidence the checker was too aggressive, not
evidence about the link.

## Program Design

### Types

- `LinkOutcome.INDETERMINATE` — new enum member alongside `VALID`/`BROKEN`/`UNREACHABLE` in `scripts/little_loops/link_checker.py`; carried through `LinkResult.status` as the string `"indeterminate"` and counted on `LinkCheckResult` as `indeterminate_links: int`.

### Signatures

- `_classify_http_status(code: int) -> LinkOutcome`

  New shared status→tier classifier: `404`/`410` → `BROKEN`; `429`/`401`/`403`/`5xx` → `INDETERMINATE`.

- `check_markdown_links(base_dir: Path, ignore_patterns: list[str], files: list[Path] | None = None) -> LinkCheckResult`

  Default file set from `DEFAULT_DOC_FILES` globs plus a hard directory denylist, replacing `base_dir.rglob("*.md")` (existing keyword args unchanged; `files` is additive).

- `_check_url_once(url: str, timeout: int) -> tuple[LinkOutcome, str | None]`

  Both classification sites (non-2xx success path and `HTTPError` handler) route through `_classify_http_status`.

### Call Path

`main_check_links` (`scripts/little_loops/cli/docs.py`) → `check_markdown_links` → `_check_url_once` → `_classify_http_status`; and `_full_check_links_data` (`scripts/little_loops/cli/doctor.py`) → `check_markdown_links`, with `_full_check_links_data` growing an informational branch on `indeterminate_links` mirroring its existing `unreachable_links` branch. `has_errors` on `LinkCheckResult` continues to gate only on `BROKEN`; `--strict-network` extends to `INDETERMINATE`.

## Impact

The `ll-doctor --full` link gate is currently unactionable and permanently red, which
trains maintainers to ignore the entire `--full` exit code — eroding the value of
every other check it aggregates (`des_audit`, `design_tokens`, `host_map`,
`package_data`, and the rest). Fixing it restores a gate that can be trusted and
acted on, and removes pointless outbound HTTP traffic to auth-walled corporate URLs
captured in loop run artifacts.

## Acceptance Criteria

- [ ] `DEFAULT_DOC_FILES` is referenced by `check_markdown_links()`; no dead
      constant remains.
- [ ] `ll-check-links` with no arguments does not visit `node_modules/`,
      `.pytest_cache/`, `.loops/`, `thoughts/`, or `.issues/`.
- [ ] An explicit path argument still cannot pull in `node_modules/` or
      `.pytest_cache/` (denylist applies regardless of scope).
- [ ] HTTP 429/401/403/5xx are reported but do not set exit code 1; 404/410 still
      do. Both classification sites (line 208 success path and the `HTTPError`
      handler) route through the same shared classifier.
- [ ] `--strict-network` gates on `INDETERMINATE` as well as `UNREACHABLE`.
- [ ] `ll-doctor --full`'s `_full_check_links_data()` adapter handles the
      `INDETERMINATE` tier (reported as informational, not error) and does not
      break on the new `LinkResult.status` value.
- [ ] 429 responses honor `Retry-After` before retrying, with the delay capped
      (≤30s) and a bounded total retry budget per run.
- [ ] Unit tests cover each status-code tier's outcome classification and the scope
      denylist, using a stubbed fetch layer (no live network in the suite).
- [ ] `ll-doctor --full` `check_links` reports only genuine 404/410s. A residual
      red count from `docs/research/dreaming-research-synthesis.md` (~33 rotted
      bibliography URLs) is expected until the follow-up content-triage issue
      lands — this issue does not make the gate green, it makes the red count
      honest and actionable.

## Scope Boundaries

**In scope:** `scripts/little_loops/link_checker.py` scope resolution and HTTP status
classification; corresponding tests in `scripts/tests/`.

**Out of scope:** fixing the ~33 rotted bibliography URLs in
`docs/research/dreaming-research-synthesis.md`. That is content triage, not a tooling
defect — file separately once this lands and the real 404 list is legible. Note the
consequence: because `DEFAULT_DOC_FILES` includes `docs/**/*.md`, the `ll-doctor
--full` gate stays red (with a small honest count) until that follow-up lands. Consider
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
