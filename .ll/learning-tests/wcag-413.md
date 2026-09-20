---
target: WCAG 4.1.3
date: '2026-09-19'
status: proven
assertions:
- claim: updating text in a role="status" element does not move keyboard focus
  result: pass
- claim: role="status" is exposed in the Chromium accessibility tree as a polite, atomic live region
  result: pass
- claim: role="alert" is exposed in the Chromium accessibility tree as an assertive, atomic live region
  result: pass
- claim: a visually-hidden (clip technique) role="status" element remains exposed as a live region
  result: pass
- claim: a role="status" element with display:none or aria-hidden="true" is absent from the accessibility tree
  result: pass
- claim: a role="status" element inserted into the DOM with its content already present is exposed as a polite live region
  result: pass
- claim: screen readers announce status-message changes in these regions
  result: untested
- claim: a role="status" element inserted together with its content is announced by screen readers
  result: untested
raw_output_path: .ll/learning-tests/raw/wcag-413.txt
---
