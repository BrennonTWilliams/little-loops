---
target: aria-live
date: '2026-09-19'
status: proven
assertions:
- claim: aria-live="polite" is exposed in Chromium's AX tree as live=polite
  result: pass
- claim: aria-live="assertive" is exposed as live=assertive
  result: pass
- claim: aria-live="off" and an absent aria-live expose no live property
  result: pass
- claim: role="status" without aria-live implicitly exposes live=polite and atomic=true
  result: pass
- claim: role="alert" without aria-live implicitly exposes live=assertive and atomic=true
  result: pass
- claim: an explicit aria-live overrides the implicit live value of role="status"
  result: pass
- claim: mutating textContent of a live region does not change its exposed live property
  result: pass
- claim: an invalid aria-live value (e.g. "loud") is normalized to off in the AX tree
  result: fail
raw_output_path: .ll/learning-tests/raw/aria-live.txt
---
