---
target: Clipboard API
date: '2026-09-17'
status: proven
assertions:
- claim: navigator.clipboard is defined and is an object in a secure/permitted context
  result: pass
- claim: navigator.clipboard instanceof Clipboard is true
  result: pass
- claim: navigator.clipboard.writeText(text) returns a Promise that resolves when
    clipboard-write permission is granted
  result: pass
- claim: after writeText(text), navigator.clipboard.readText() resolves with the
    same string that was written
  result: pass
- claim: document.execCommand('copy') is a synchronous function returning a boolean,
    distinct from the async Clipboard API
  result: pass
- claim: navigator.clipboard.writeText() without clipboard-write permission granted
    rejects with a DOMException named NotAllowedError
  result: pass
raw_output_path: .ll/learning-tests/raw/clipboard-api.txt
---
