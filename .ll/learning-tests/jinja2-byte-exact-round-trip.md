---
target: jinja2-byte-exact-round-trip
date: '2026-08-24'
status: proven
assertions:
- claim: a literal-only template (no expressions/blocks) renders byte-identically to the source string under build_environment()
  result: pass
- claim: trim_blocks=True + lstrip_blocks=True strip a block tag's own line (leading indent and trailing newline) from the rendered output
  result: pass
- claim: autoescape=False stamps variable values verbatim, without re-escaping HTML entities like &amp; or &#39;
  result: pass
- claim: keep_trailing_newline=True preserves a trailing newline present in the source template
  result: pass
- claim: StrictUndefined raises UndefinedError when a template expression references a variable absent from the render context
  result: pass
- claim: a [[# ... #]] comment block is removed entirely from the rendered output, leaving no residue
  result: pass
- claim: a repeat region built as a [[% for x in y %]]...[[% endfor %]] loop with tags on their own line reproduces the exact concatenation of N iterations, with no extra whitespace from the loop tags themselves
  result: pass
raw_output_path: .ll/learning-tests/raw/jinja2-byte-exact-round-trip.txt
---
