---
target: WAI-ARIA
date: '2026-09-19'
status: proven
assertions:
- claim: role="button" on a div exposes accessibility role button in the Chromium accessibility tree
  result: pass
- claim: aria-label sets the accessible name of an element
  result: pass
- claim: aria-labelledby takes precedence over aria-label for the accessible name
  result: pass
- claim: aria-hidden="true" removes the element and its descendants from the accessibility tree
  result: pass
- claim: aria-expanded and aria-checked are exposed as expanded and checked properties
  result: pass
- claim: aria-disabled="true" on a native button exposes disabled=true while the element stays focusable
  result: pass
- claim: an unrecognized token in a role list falls back to the next valid role
  result: pass
- claim: screen readers announce these semantics identically to Chromium's accessibility tree
  result: untested
raw_output_path: .ll/learning-tests/raw/wai-aria.txt
---
