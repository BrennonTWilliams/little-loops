---
url: https://docs.boundaryml.com/ref/llm-client-providers/openrouter.mdx
scraped_at: 2026-03-06T01:00:49.174264
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/openroutermdx.md
---


***

## title: openrouter

The `openrouter` provider offers native integration with [OpenRouter](https://openrouter.ai), a unified API gateway providing access to 300+ AI models from OpenAI, Anthropic, Google, Meta, and others through a single interface.

Example:

```baml BAML
clientMyClient {
  provider openrouter
  options {
    model "openai/gpt-4o-mini"
  }
}
```You can also use [`openai-generic`](openai-generic) with OpenRouter by manually setting the `base_url`. The `openrouter` provider simplifies this by providing sensible defaults.## OpenRouter-specific options

The `openrouter` provider extends [`openai-generic`](openai-generic) with OpenRouter-specific defaults. See [`openai-generic`](openai-generic) for the full list of supported options.**Default: `env.OPENROUTER_API_KEY`****Default: `https://openrouter.ai/api/v1`**The model to use, in OpenRouter's `provider/model-name` format.

  | Model                               | Description          |
  | ----------------------------------- | -------------------- |
  | `openai/gpt-4o-mini`                | Fast, cost-effective |
  | `anthropic/claude-3.5-sonnet`       | Claude 3.5 Sonnet    |
  | `anthropic/claude-3-haiku`          | Fast Claude variant  |
  | `google/gemini-2.0-flash-001`       | Gemini 2.0 Flash     |
  | `meta-llama/llama-3.1-70b-instruct` | Llama 3.1 70B        |

  OpenRouter supports model variants for routing preferences (e.g., `:nitro` for high-throughput):

  ```baml BAML
  clientNitroClient {
    provider openrouter
    options {
      model "meta-llama/llama-3.1-70b-instruct:nitro"
    }
  }
  ```

  For the complete list, see [OpenRouter Models](https://openrouter.ai/models).## App attribution headers

OpenRouter supports optional headers for app attribution. Pass these via the `headers` option:

| Header         | Description                                    |
| -------------- | ---------------------------------------------- |
| `X-Title`      | Your app name, shown on openrouter.ai rankings |
| `HTTP-Referer` | Your site URL for rankings and attribution     |

```baml BAML
clientOpenRouterWithAttribution {
  provider openrouter
  options {
    model "anthropic/claude-3-haiku"
    headers {
      "X-Title" "My App"
      "HTTP-Referer" "https://myapp.com"
    }
  }
}
```

For all other options (`temperature`, `max_tokens`, `headers`, etc.), see [`openai-generic`](openai-generic) and the [OpenRouter API documentation](https://openrouter.ai/docs/api/reference/overview).
