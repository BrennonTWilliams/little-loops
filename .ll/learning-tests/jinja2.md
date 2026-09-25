---
target: jinja2
date: '2026-09-24'
status: proven
assertions:
- claim: Environment.from_string() renders a template without any loader configured
  result: pass
- claim: repeated/conditional regions render correctly via for-loop and if inside a single template string
  result: pass
- claim: SandboxedEnvironment with StrictUndefined raises SecurityError on unsafe attribute access such as x.__class__ and x.__class__.__mro__
  result: pass
- claim: SandboxedEnvironment with the default Undefined silently renders unsafe attribute access as an empty string instead of raising
  result: pass
- claim: default {{ }} delimiters collide with JS-object-literal-like content and raise TemplateSyntaxError instead of silently mis-rendering
  result: pass
- claim: custom delimiters ([[= =]], [[% %]], [[# #]]) leave literal {{ }} content untouched while still substituting the custom-delimited variable
  result: pass
- claim: StrictUndefined raises UndefinedError for a missing variable
  result: pass
- claim: custom comment delimiters strip the commented text from output
  result: pass
raw_output_path: .ll/learning-tests/raw/jinja2.txt
---
