---
target: playwright
date: '2026-09-29'
status: proven
assertions:
- claim: page.on('pageerror', e) always delivers an object where e instanceof Error is true
  result: pass
- claim: e.message on a pageerror event is always a string, even when the page throws a non-Error value (string, number, undefined, null, plain object, DOMException)
  result: pass
- claim: an unhandled in-page promise rejection also triggers a 'pageerror' event with a string .message
  result: pass
- claim: msg.text() on a console 'error' event always returns a string, including for multi-argument console.error(...) calls with object/array arguments
  result: pass
- claim: Array.prototype.join on an array of pageerror/console-error derived strings cannot throw due to a non-string entry, since Playwright always normalizes both to strings before the listener fires
  result: pass
- claim: 'page.screenshot({path}) on a file:// page writes a non-empty valid PNG (8-byte PNG signature) whose pixel size equals the context viewport (800x600 observed), including with fullPage: true (node @playwright/test 1.60.0)'
  result: pass
- claim: two consecutive page.screenshot() calls of the same static file:// page are byte-identical (SHA-256 equal), so screenshots are deterministic
  result: pass
- claim: 'with page.route(''**/*'', ...) continuing file: URLs and aborting all others, page.goto(''file://...'') still loads successfully (the route sees the file: request; goto took 23 ms)'
  result: pass
- claim: 'the same route aborts http: subresources of a file:// page (img, stylesheet, and script fetch()); each fires a requestfailed event and a local http server receives zero hits'
  result: pass
- claim: 'a page-initiated fetch() to an aborted http: URL rejects inside the page (window.__fetch is ''rejected''); it does not hang'
  result: pass
- claim: 'control: the same file:// page opened without the route reaches the local http server for all three subresources (3 hits), so the route-abort is what blocks the beacons'
  result: pass
raw_output_path: .ll/learning-tests/raw/playwright.txt
proven_package: playwright
proven_version: 1.57.0
---
