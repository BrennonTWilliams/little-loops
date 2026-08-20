# Wire-Issue: Evidence Confirmation (Phase 5, Layer B)

Loaded by `/ll:wire-issue` Phase 5. Added by BUG-3260.

## Overview

Extends Phase 3.6's confirm-before-map to a previously uncovered input: Agent 1's
own free-form findings. Phase 3.6 only confirms `ll-code`-seeded candidates fed
into Agent 1's "Already-known callers"/"Key symbols" slots — it never touches
what Agent 1 discovers on its own. This is that missing coverage, not a
replacement for Phase 3.6.

`agents/codebase-locator.md` (Layer A) now requires Agent 1 to cite, per
returned path, the symbol or pattern its Grep matched there. This companion is
Layer B: the deterministic gate that spends that citation.

## The rule

For every path Agent 1 returns in a confirmable group (Direct importers,
Callers/consumers, Test files, Registration/manifest files, Config files), run
**one targeted Grep for the match string Agent 1 cited for that path** before
the path may enter `MISSING_WIRING` or the Integration Map:

- **Grep confirms it** → the path proceeds into `MISSING_WIRING` and Phase 8a's
  write-up exactly as today.
- **Grep finds nothing** → the path is dropped from the confirmable groups. It
  may still be recorded under a `## Inferred, Unconfirmed` note in the wiring
  output if it looks plausible, but it must never be written into
  `MISSING_WIRING` or the Integration Map as a confirmed finding.

## Degradation rule (no evidence field)

A path that arrives with **no cited match string** — Layer A ignored, or an
older host mirror still in play — is treated as inferred, unconfirmed and held
out of `MISSING_WIRING`. Do **not** fall back to grepping the full
`key_symbols` set for that path: that any-symbol fallback was tested against
BUG-3260's four recorded fabrications and caught only one of them, while
mechanically emptying the registration/config groups (those files legitimately
carry an entry-point name, dotted module path, or config key rather than a
Python symbol). Failing closed on a missing citation is simpler and stricter
than the any-symbol fallback, and does not cost those groups their real
entries.

## Inferred, Unconfirmed bucket

Agent 1's "Inferred, Unconfirmed" group (see `agents/codebase-locator.md`
Output Format) and any path demoted by this gate stay out of `MISSING_WIRING`.
If they survive to the written issue at all, they go in a distinct
`Inferred, unconfirmed` note beneath the confirmed entries in Phase 8a's
output, never mixed into the same bullet list as confirmed callers — a reader
of the issue must be able to tell which is which without re-running the pass.

## Scope

This is wire-issue-only logic — `/ll:refine-issue` and `/ll:manage-issue` do
not inherit Layer B, only Layer A (the shared agent definition). Phase 3.6's
existing confirm-before-map semantics for `ll-code`-seeded candidates are
unchanged; this only adds coverage for the input Phase 3.6 never touched.
