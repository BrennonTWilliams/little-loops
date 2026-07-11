---
target: pyyaml
date: '2026-07-10'
status: proven
assertions:
  - claim: "yaml.safe_load raises yaml.YAMLError on malformed input (unterminated quoted string)"
    result: pass
  - claim: "yaml.parser.ParserError is a subclass of yaml.YAMLError caught by except YAMLError"
    result: pass
  - claim: "yaml.safe_load returns None for empty input (falsy)"
    result: pass
  - claim: "yaml.safe_load returns dict with 'entries' key for entries-topped valid yaml"
    result: pass
  - claim: "yaml.safe_load returns a dict for plain key-value input"
    result: pass
raw_output_path: .ll/learning-tests/raw/pyyaml.txt
---