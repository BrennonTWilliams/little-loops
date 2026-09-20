---
target: ARIA live regions
date: '2026-09-19'
status: proven
assertions:
- claim: role="status" implies live=polite and atomic=true in the Chromium accessibility tree
  result: pass
- claim: role="alert" implies live=assertive and atomic=true in the Chromium accessibility tree
  result: pass
- claim: a generic div with aria-live="polite" exposes live=polite with atomic=false by default
  result: pass
- claim: aria-atomic="true" on an aria-live region is exposed as atomic=true
  result: pass
- claim: an element with no live-region role or attribute exposes no live property
  result: pass
- claim: explicit aria-live="off" on role="alert" overrides the implicit assertive (no live property exposed)
  result: pass
- claim: screen readers actually announce text changes in these regions
  result: untested
raw_output_path: .ll/learning-tests/raw/aria-live-regions.txt
---
