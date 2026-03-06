---
url: https://docs.boundaryml.com/ref/llm-client-strategies/fallback.mdx
scraped_at: 2026-03-06T01:00:50.223771
filepath: docs-docs-boundaryml-com/ref/llm-client-strategies/fallbackmdx.md
---


***

## title: fallback

You can use the `fallback` provider to add more resilience to your application.

A fallback will attempt to use the first client, and if it fails, it will try the second client, and so on.You can nest fallbacks inside of other fallbacks.```baml BAML
clientSuperDuperClient {
  provider fallback
  options {
    strategy [
      ClientA
      ClientB
      ClientC
    ]
  }
}
```

## OptionsThe list of client names to try in order. Cannot be empty.## retry\_policy

Like any other client, you can specify a retry policy for the fallback client. See [retry\_policy](retry-policy) for more information.

The retry policy will test the fallback itself, after the entire strategy has failed.

```baml BAML
clientSuperDuperClient {
  provider fallback
  retry_policy MyRetryPolicy
  options {
    strategy [
      ClientA
      ClientB
      ClientC
    ]
  }
}
```

## Nesting multiple fallbacks

You can nest multiple fallbacks inside of each other. The fallbacks will just chain as you would expect.

```baml BAML
clientSuperDuperClient {
  provider fallback
  options {
    strategy [
      ClientA
      ClientB
      ClientC
    ]
  }
}

clientMegaClient {
  provider fallback
  options {
    strategy [
      SuperDuperClient
      ClientD
    ]
  }
}
```
