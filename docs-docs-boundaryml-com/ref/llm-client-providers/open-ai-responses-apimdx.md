---
url: https://docs.boundaryml.com/ref/llm-client-providers/open-ai-responses-api.mdx
scraped_at: 2026-03-06T01:00:48.671079
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/open-ai-responses-apimdx.md
---


***

## title: openai-responses

The `openai-responses` provider supports OpenAI's `/responses` endpoint which uses the newer Responses API instead of the traditional Chat Completions API.
Read more about the differences between the Chat Completions API and the Responses API in [OpenAI's comparison guide](https://platform.openai.com/docs/guides/responses-vs-chat-completions).If you're a new user, OpenAI recommends using the `openai-responses` provider instead of the `openai` provider.`o1-mini` is not supported with the `openai-responses` provider.Example:

```baml BAML
clientMyResponsesClient {
  provider "openai-responses"
  options {
    api_key env.MY_OPENAI_KEY
    model "gpt-5"
    reasoning {
      effort "medium"
    }
  }
}
```

## BAML-specific request `options`

These unique parameters (aka `options`) modify the API request sent to the provider.Will be used to build the `Authorization` header, like so: `Authorization: Bearer $api_key`

  **Default: `env.OPENAI_API_KEY`**The base URL for the API.

  **Default: `https://api.openai.com/v1`**Additional headers to send with the request.

  Example:

  ```baml BAML
  clientMyResponsesClient {
    provider openai-responses
    options {
      api_key env.MY_OPENAI_KEY
      model "gpt-4.1"
      headers {
        "X-My-Header" "my-value"
      }
    }
  }
  ```Override the response format type. When using `openai-responses` provider, this defaults to `"openai-responses"`.

  You can also use the standard `openai` provider with `client_response_type: "openai-responses"` to format the response as a `openai-responses` response.

  Example:

  ```baml BAML
  clientStandardOpenAIWithResponses {
    provider openai
    options {
      api_key env.MY_OPENAI_KEY
      model "gpt-4.1"
      client_response_type "openai-responses"
    }
  }
  ```The role to use if the role is not in the allowed\_roles. **Default: `"user"` usually, but some models like OpenAI's `gpt-5` will use `"system"`**

  Picked the first role in `allowed_roles` if not "user", otherwise "user".Which roles should we forward to the API? **Default: `["system", "user", "assistant"]` usually, but some models like OpenAI's `o1-mini` will use `["user", "assistant"]`**

  When building prompts, any role not in this list will be set to the `default_role`.A mapping to transform role names before sending to the API. **Default: `{}`** (no remapping)

  For google-ai provider, the default is: `{ "assistant": "model" }`

  This allows you to use standard role names in your prompts (like "user", "assistant", "system") but send different role names to the API. The remapping happens after role validation and default role assignment.

  **Example:**

  ```json
  {
    "user": "human",
    "assistant": "ai",
  }
  ```

  With this configuration, `{{ _.role("user") }}` in your prompt will result in a message with role "human" being sent to the API.Which role metadata should we forward to the API? **Default: `[]`**

  For example you can set this to `["foo", "bar"]` to forward the cache policy to the API.

  If you do not set `allowed_role_metadata`, we will not forward any role metadata to the API even if it is set in the prompt.

  Then in your prompt you can use something like:

  ```baml
  clientFoo {
    provider openai
    options {
      allowed_role_metadata: ["foo", "bar"]
    }
  }

  clientFooWithout {
    provider openai
    options {
    }
  }
  template_string Foo() #"
    {{ _.role('user', foo={"type": "ephemeral"}, bar="1", cat=True) }}
    This will be have foo and bar, but not cat metadata. But only for Foo, not FooWithout.
    {{ _.role('user') }}
    This will have none of the role metadata for Foo or FooWithout.
  "#
  ```

  You can use the playground to see the raw curl request to see what is being sent to the API.### `media_url_handler`

Controls how media URLs are processed before sending to the provider. This allows you to override the default behavior for handling images, audio, PDFs, and videos.

```baml
clientMyClient {
  provider openai
  options {
    media_url_handler {
      image "send_base64"                    // Options: send_base64 | send_url | send_url_add_mime_type | send_base64_unless_google_url
      audio "send_url"
      pdf "send_url_add_mime_type"
      video "send_url"
    }
  }
}
```

#### Options

Each media type can be configured with one of these modes:

* **`send_base64`** - Always download URLs and convert to base64 data URIs
* **`send_url`** - Pass URLs through unchanged to the provider
* **`send_url_add_mime_type`** - Ensure MIME type is present (may require downloading to detect)
* **`send_base64_unless_google_url`** - Only process non-gs\:// URLs (keep Google Cloud Storage URLs as-is)

#### Provider Defaults

If not specified, each provider uses these defaults:

| Provider     | Image                           | Audio                    | PDF           | Video      |
| ------------ | ------------------------------- | ------------------------ | ------------- | ---------- |
| OpenAI       | `send_url`                      | `send_base64`            | `send_url`    | `send_url` |
| Anthropic    | `send_url`                      | `send_url`               | `send_base64` | `send_url` |
| Google AI    | `send_base64_unless_google_url` | `send_url`               | `send_url`    | `send_url` |
| Vertex AI    | `send_url_add_mime_type`        | `send_url_add_mime_type` | `send_url`    | `send_url` |
| AWS Bedrock  | `send_base64`                   | `send_base64`            | `send_base64` | `send_url` |
| Azure OpenAI | `send_url`                      | `send_base64`            | `send_url`    | `send_url` |

#### When to Use

* **Use `send_base64`** when your provider doesn't support external URLs and you need to embed media content
* **Use `send_url`** when your provider handles URL fetching and you want to avoid the overhead of base64 conversion
* **Use `send_url_add_mime_type`** when your provider requires MIME type information (e.g., Vertex AI)
* **Use `send_base64_unless_google_url`** when working with Google Cloud Storage and want to preserve gs\:// URLsURL fetching happens at request time and may add latency. Consider caching or pre-converting frequently used media when using `send_base64` mode.## Provider request parameters

These are parameters specific to the OpenAI Responses API that are passed through to the provider.Controls the amount of reasoning effort the model should use.

  | Value    | Description               |
  | -------- | ------------------------- |
  | `low`    | Minimal reasoning effort  |
  | `medium` | Balanced reasoning effort |
  | `high`   | Maximum reasoning effort  |

  Example:

  ```baml BAML
  clientHighReasoningClient {
    provider openai-responses
    options {
      model "o4-mini"
      reasoning {
        effort "high"
      }
    }
  }
  ```Most models support the Responses API, some of the most popular models are:

  | Model          | Use Case                                | Context    | Key Features                         |
  | -------------- | --------------------------------------- | ---------- | ------------------------------------ |
  | **gpt-5**      | Coding, agentic tasks, expert reasoning | 400K total | Built-in reasoning, 45% fewer errors |
  | **gpt-5-mini** | Well-defined tasks, cost-efficient      | 400K total | Faster alternative to GPT-5          |
  | **o4-mini**    | Fast reasoning tasks                    | Standard   | 92.7% AIME, cost-efficient reasoning |`o1-mini` is not supported with the `openai-responses` provider.See OpenAI's Responses API documentation for the latest available models.Tools that the model can use during reasoning. Supports function calling and web search.

  Example with web search:

  ```baml BAML
  clientWebSearchClient {
    provider openai-responses
    options {
      model "gpt-4.1"
      tools [
        {
          type "web_search_preview"
        }
      ]
    }
  }
  ```## Additional Use Cases

### Image Input Support

The `openai-responses` provider supports image inputs for vision-capable models:

```baml BAML
clientOpenAIResponsesVision {
  provider openai-responses
  options {
    model "gpt-4.1"
  }
}

function AnalyzeImage(image: image|string) -> string {
  client OpenAIResponsesVision
  prompt #"
    {{ _.role("user") }}
    What is in this image?
    {{ image }}
  "#
}
```

### Advanced Reasoning

Using reasoning models with high effort for complex problem solving:

```baml BAML
clientAdvancedReasoningClient {
  provider openai-responses
  options {
    model "o4-mini"
    reasoning {
      effort "high"
    }
  }
}

function SolveComplexProblem(problem: string) -> string {
  client AdvancedReasoningClient
  prompt #"
    {{ _.role("user") }}
    Solve this step by step: {{ problem }}
  "#
}
```

## Modular API Support

The `openai-responses` provider works with the [Modular API](../../../../../guide/baml-advanced/modular-api) for custom integrations:

```python Python
from openai import AsyncOpenAI
from openai.types.responses import Response
import typing

client = AsyncOpenAI()
req = await b.request.MyFunction("input")
res = typing.cast(Response, await client.responses.create(**req.body.json()))
parsed = b.parse.MyFunction(res.output_text)
```

For all other options, see the [official OpenAI Responses API documentation](https://platform.openai.com/docs/api-reference/responses).
