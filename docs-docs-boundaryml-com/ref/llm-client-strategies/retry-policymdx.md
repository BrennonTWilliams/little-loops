---
url: https://docs.boundaryml.com/ref/llm-client-strategies/retry-policy.mdx
scraped_at: 2026-03-06T01:00:50.247186
filepath: docs-docs-boundaryml-com/ref/llm-client-strategies/retry-policymdx.md
---


***

## title: retry\_policy

A retry policy can be attached to any `client` and will attempt to retry requests that fail due to a network error.

```baml BAML
retry_policy MyPolicyName {
  max_retries 3
}
```

Usage:

```baml BAML
clientMyClient {
  provider anthropic
  retry_policy MyPolicyName
  options {
    model "claude-sonnet-4-20250514"
    api_key env.ANTHROPIC_API_KEY
  }
}
```

## FieldsNumber of **additional** retries to attempt after the initial request fails.The strategy to use for retrying requests. Default is `constant_delay(delay_ms=200)`.

  | Strategy              | Docs                         | Notes |
  | --------------------- | ---------------------------- | ----- |
  | `constant_delay`      | [Docs](#constant-delay)      |       |
  | `exponential_backoff` | [Docs](#exponential-backoff) |       |

  Example:

  ```baml BAML
  retry_policy MyPolicyName {
    max_retries 3
    strategy {
      type constant_delay
      delay_ms 200
    }
  }
  ```## Strategies

### constant\_delayConfigures to the constant delay strategy.The delay in milliseconds to wait between retries. **Default: 200**### exponential\_backoffConfigures to the exponential backoff strategy.The initial delay in milliseconds to wait between retries. **Default: 200**The multiplier to apply to the delay after each retry. **Default: 1.5**The maximum delay in milliseconds to wait between retries. **Default: 10000**
