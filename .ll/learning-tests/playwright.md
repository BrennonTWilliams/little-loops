---
target: playwright
date: '2026-07-24'
status: proven
assertions:
- claim: page.on('pageerror', e) always delivers an object where e instanceof Error
    is true
  result: pass
- claim: e.message on a pageerror event is always a string, even when the page throws
    a non-Error value (string, number, undefined, null, plain object, DOMException)
  result: pass
- claim: an unhandled in-page promise rejection also triggers a 'pageerror' event
    with a string .message
  result: pass
- claim: msg.text() on a console 'error' event always returns a string, including
    for multi-argument console.error(...) calls with object/array arguments
  result: pass
- claim: Array.prototype.join on an array of pageerror/console-error derived strings
    cannot throw due to a non-string entry, since Playwright always normalizes both
    to strings before the listener fires
  result: pass
raw_output_path: .ll/learning-tests/raw/playwright.txt
proven_package: playwright
proven_version: 1.57.0
---
