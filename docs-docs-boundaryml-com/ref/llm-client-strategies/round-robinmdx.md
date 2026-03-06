---
url: https://docs.boundaryml.com/ref/llm-client-strategies/round-robin.mdx
scraped_at: 2026-03-06T01:00:50.766454
filepath: docs-docs-boundaryml-com/ref/llm-client-strategies/round-robinmdx.md
---


***

## title: round-robin

The `round_robin` provider allows you to distribute requests across multiple clients in a round-robin fashion. After each call, the next client in the list will be used.

```baml BAML
clientMyClient {
  provider round-robin
  options {
    strategy [
      ClientA
      ClientB
      ClientC
    ]
  }
}
```

## OptionsThe list of client names to try in order. Cannot be empty.The index of the client to start with.

  **Default is `random(0, len(strategy))`**

  In the [BAML Playground](/docs/get-started/quickstart/editors-vscode), Default is `0`.## retry\_policy

When using a retry\_policy with a round-robin client, it will rotate the strategy list after each retry.

```baml BAML
clientMyClient {
  provider round-robin
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

## Nesting multiple round-robin clients

You can nest multiple round-robin clients inside of each other. The round-robin as you would expect.

```baml BAML
clientMyClient {
  provider round-robin
  options {
    strategy [
      ClientA
      ClientB
      ClientC
    ]
  }
}

clientMegaClient {
  provider round-robin
  options {
    strategy [
      MyClient
      ClientD
      ClientE
    ]
  }
}

// Calling MegaClient will call:
// MyClient(ClientA)
// ClientD
// ClientE
// MyClient(ClientB)
// etc.
```
