---
target: jinja2
date: '2026-08-23'
status: proven
assertions:
- claim: repeated/conditional regions render correctly via for-loop and if inside
    a single template string
  result: pass
- claim: SandboxedEnvironment blocks unsafe attribute access (e.g. __class__ traversal)
  result: pass
- claim: default {{ }} / {% %} delimiters collide with literal JS-object-literal-like
    content and raise a TemplateSyntaxError instead of silently mis-rendering
  result: pass
- claim: 'custom delimiters (e.g. [[LLAT: ... ]]) avoid the collision and leave
    literal {{ }} content untouched while still substituting the custom-delimited
    variable'
  result: pass
- claim: Environment.from_string() renders a template without any loader configured
  result: pass
raw_output_path: .ll/learning-tests/raw/jinja2.txt
---
