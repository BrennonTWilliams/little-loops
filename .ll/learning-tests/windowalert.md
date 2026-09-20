---
target: window.alert
date: '2026-09-19'
status: proven
assertions:
- claim: In Node (no DOM), `window` is undefined so `window.alert` is unavailable
  result: pass
- claim: In Chromium, typeof window.alert is "function" and window.alert === alert
  result: pass
- claim: window.alert(msg) returns undefined
  result: pass
- claim: A Playwright `dialog` event fires with type "alert" and message equal to the argument
  result: pass
- claim: Non-string arguments are coerced to strings (123 -> "123", null -> "null", undefined -> "undefined", {} -> "[object Object]")
  result: pass
- claim: alert() with no arguments produces an empty-string message
  result: pass
- claim: Script execution blocks until the dialog is dismissed
  result: pass
raw_output_path: .ll/learning-tests/raw/windowalert.txt
---
