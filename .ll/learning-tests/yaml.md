---
target: yaml
date: '2026-09-16'
status: proven
assertions:
- claim: yaml.safe_load on malformed YAML raises a yaml.YAMLError subclass exposing
    a .problem_mark with .line/.column
  result: pass
- claim: yaml.safe_dump(..., default_flow_style=False) renders nested dicts in block
    style, not '{...}' flow style
  result: pass
- claim: yaml.safe_load on a mapping with duplicate keys does not raise, it silently
    keeps the last value
  result: pass
- claim: yaml.safe_dump can serialize a datetime.date object without a custom representer
  result: pass
- claim: A block scalar (|) round-trips embedded newlines exactly through safe_load
  result: fail
raw_output_path: .ll/learning-tests/raw/yaml.txt
---
