---
target: gitleaks
date: '2026-09-14'
status: proven
assertions:
- claim: gitleaks allowlists AWS access keys ending in the literal suffix "EXAMPLE"
    (e.g. the canonical AWS-docs key AKIAIOSFODNN7EXAMPLE) via an `allowlists`
    regex on the aws-access-token rule, so it is never flagged
  result: pass
- claim: a Python source line that assembles an AWS-key-shaped string at runtime
    via string concatenation (`"AKIA" + "I" * 16`) is not flagged, because gitleaks
    matches regexes against static file text, not evaluated output
  result: pass
- claim: gitleaks --report-format json output includes a RuleID field per finding
  result: pass
- claim: the default github-pat rule flags a `ghp_` token followed by 36 high-entropy
    alphanumeric characters
  result: pass
- claim: the default private-key rule flags a PEM private-key block (BEGIN/END
    PRIVATE KEY headers) when the body is realistic base64 key material
  result: pass
- claim: the default jwt rule flags a three-segment dot-separated base64url token
  result: pass
raw_output_path: .ll/learning-tests/raw/gitleaks.txt
---
