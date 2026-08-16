---
target: yaml
date: '2026-08-16'
status: proven
assertions:
- claim: yaml.safe_dump with sort_keys=False preserves dict insertion order in output
  result: pass
- claim: yaml.safe_dump renders None as the literal null
  result: pass
- claim: yaml.safe_load parses ~ as Python None
  result: pass
- claim: yaml.safe_dump raises yaml.representer.RepresenterError for an arbitrary
    custom class instance
  result: pass
- claim: yaml.safe_load_all correctly parses multiple ---separated documents into
    a generator yielding one dict per document
  result: pass
- claim: 'a string value containing '': '' (colon-space) is auto-quoted by safe_dump
    so it round-trips correctly through safe_load'
  result: pass
raw_output_path: .ll/learning-tests/raw/yaml.txt
---
