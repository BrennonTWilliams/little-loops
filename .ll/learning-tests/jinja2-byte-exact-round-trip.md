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
- claim: a fully mid-line block tag (non-whitespace prefix AND non-newline suffix) round-trips byte-exactly, because lstrip_blocks requires a whitespace-only prefix and trim_blocks requires an immediate newline, so neither fires
  result: pass
- claim: the mixed form "whitespace-only prefix, no immediate newline" silently eats both the leading indent and the line's trailing newline, corrupting the round trip
  result: pass
- claim: the mixed form "non-whitespace prefix, immediate newline" silently eats the newline after the tag, corrupting the round trip
  result: pass
- claim: a mid-line [[% raw %]]/[[% endraw %]] wrapper escapes a literal delimiter inside a single-line <script>, byte-exactly — no own-line position is required
  result: pass
- claim: a literal [[% endraw %]] in the artifact terminates the raw wrapper and raises TemplateSyntaxError; there is no Jinja2 escape for it, so it cannot be handled by raw-wrapping
  result: pass
- claim: a *value* containing [[= ... =]] or [[% ... %]] renders verbatim without re-evaluation, so only literal non-region text needs raw-escaping
  result: pass
- claim: render_template reads its body via Path.read_text (universal newlines), so a CRLF template body is translated to LF before Jinja2 sees it — no CRLF artifact can round-trip through the frozen renderer
  result: pass
- claim: the [[%+ ... +%]] whitespace-control form injects a spurious blank line and fails the round trip
  result: pass
raw_output_path: .ll/learning-tests/raw/jinja2-byte-exact-round-trip.txt
---
