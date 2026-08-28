---
target: htmx
date: '2026-08-28'
status: proven
assertions:
- claim: hx-sse (the extension providing SSE support) ships separately from core htmx.js/htmx.min.js and is only present in the concatenated dist/htmax.js bundle (core + named extension list, per htmx.org@4.0.0's own package.json build:htmax script) — so vendoring core htmx.min.js alone would silently omit hx-sse
  result: pass
- claim: an element with hx-sse:connect="<url>" auto-establishes a streaming request on page load with no hand-written EventSource/fetch code
  result: pass
- claim: unnamed SSE data:-only messages auto-swap into the connecting element using its resolved hx-swap style (htmx 4 removed the old sse-swap attribute; this is confirmed both by a runtime console.warn in the bundle and by observed DOM mutation)
  result: pass
- claim: hx-swap="innerMorph" on the SSE-connected element preserves unrelated sibling DOM state (a user-typed <input> value) across repeated live-swapped updates — the specific property the issue's Motivation section claims (scroll/focus/input preservation)
  result: pass
- claim: a named SSE event (event:<name> frame) does NOT auto-swap; it dispatches as a DOM CustomEvent on the connecting element itself (detail={data, id}), not on document/body and not as a swap
  result: pass
- claim: a <hx-partial hx-target="#id" hx-swap="..."> tag present anywhere in an htmx-swapped response performs an out-of-band swap into that different target element, independent of the response's primary swap target
  result: pass
- claim: 'htmx 4''s explicit :inherited model: hx-confirm:inherited="msg" on a parent propagates to a descendant''s request (confirm() called with the parent''s message), while a plain (non-suffixed) hx-confirm="msg" on a parent does NOT propagate to a descendant''s request (confirm() not called at all)'
  result: pass
raw_output_path: .ll/learning-tests/raw/htmx.txt
---
