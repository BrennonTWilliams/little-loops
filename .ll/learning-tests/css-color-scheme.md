---
target: CSS color-scheme
date: '2026-09-18'
status: proven
assertions:
- claim: 'with :root{color-scheme: light dark}, the system color Canvas resolves to
    white when the browser prefers light and rgb(18, 18, 18) when it prefers dark'
  result: pass
- claim: 'an explicit data-theme=dark rule setting color-scheme: dark on the root
    overrides the OS preference, resolving Canvas to rgb(18, 18, 18) even when light
    is emulated'
  result: pass
- claim: 'an explicit color-scheme: light on the root resolves Canvas to white even
    when dark is emulated'
  result: pass
- claim: 'an element-level color-scheme: light or dark overrides the inherited root
    value for that element''s Canvas color, independent of the OS preference'
  result: pass
- claim: color-scheme is inherited (child getComputedStyle().colorScheme equals the
    parent's declared 'light dark')
  result: pass
- claim: light-dark(a, b) resolves to a under a used light scheme and b under a used
    dark scheme, following the root data-theme override rather than the OS preference
  result: pass
- claim: an author-set explicit background-color is unaffected by color-scheme
  result: pass
raw_output_path: .ll/learning-tests/raw/css-color-scheme.txt
---
