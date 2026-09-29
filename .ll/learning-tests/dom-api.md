---
target: DOM API
date: '2026-09-24'
status: proven
assertions:
- claim: innerHTML assignment containing a script element does not execute the script
  result: pass
- claim: innerHTML assignment containing img with onerror does execute the handler
  result: pass
- claim: textContent assignment does not parse markup (no child elements, literal text preserved)
  result: pass
- claim: setAttribute data-x with markup characters round-trips verbatim via dataset.x
  result: pass
- claim: DOMParser text/html parses img but does not execute its onerror handler
  result: pass
- claim: querySelectorAll returns a static NodeList while getElementsByClassName is live
  result: pass
- claim: template.content is an inert DocumentFragment owned by a different document
  result: pass
raw_output_path: .ll/learning-tests/raw/dom-api.txt
---
