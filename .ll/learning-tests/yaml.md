---
target: yaml
date: '2026-07-14'
status: proven
assertions:
- claim: yaml.safe_dump wraps long block-sequence scalar items across physical lines using indentation continuation when they exceed the default width
  result: pass
- claim: yaml.safe_load correctly round-trips a safe_dump'd block sequence with wrapped long items back to the original list
  result: pass
- claim: yaml.safe_load yields a Python int for a bare digit scalar unconditionally, regardless of any coerce_types-style flag
  result: pass
- claim: yaml.safe_load raises yaml.YAMLError on genuinely invalid YAML such as a bare list item line following a scalar-valued key
  result: pass
raw_output_path: .ll/learning-tests/raw/yaml.txt
---
