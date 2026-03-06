---
url: https://docs.boundaryml.com/ref/llm-client-providers/anthropic.mdx
scraped_at: 2026-03-06T01:00:45.998753
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/anthropicmdx.md
---


***

## title: anthropic

The `anthropic` provider supports all APIs that use the same interface for the `/v1/messages` endpoint.

Example:

```baml BAML
clientMyClient {
  provider anthropic
  options {
    model "claude-sonnet-4-20250514"
    temperature 0
  }
}
```

## BAML-specific request `options`

These unique parameters (aka `options`) modify the API request sent to the provider.

You can use this to modify the `headers` and `base_url` for example.Will be passed as a bearer token. **Default: `env.ANTHROPIC_API_KEY`**

  `Authorization: Bearer $api_key`The base URL for the API. **Default: `https://api.anthropic.com`**Additional headers to send with the request.

  Unless specified with a different value, we inject in the following headers:

  ```
  "anthropic-version" "2023-06-01"
  ```

  Example:

  ```baml
  clientMyClient {
    provider anthropic
    options {
      api_key env.MY_ANTHROPIC_KEY
      model "claude-sonnet-4-20250514"
      headers {
        "X-My-Header" "my-value"
      }
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

  For example you can set this to `["cache_control"]` to forward the cache policy to the API.

  If you do not set `allowed_role_metadata`, we will not forward any role metadata to the API even if it is set in the prompt.

  Then in your prompt you can use something like:

  ```baml
  clientClaudeWithCaching {
    provider anthropic
    options {
      model claude-3-5-haiku-20241022
      api_key env.ANTHROPIC_API_KEY
      max_tokens 1000
      allowed_role_metadata ["cache_control"]
      headers {
        "anthropic-beta" "prompt-caching-2024-07-31"
      }
    }
  }

  clientFooWithout {
    provider anthropic
    options {
    }
  }

  template_string Foo() #"
    {{ _.role('user', cache_control={"type": "ephemeral"}) }}
    This will be cached for ClaudeWithCaching, but not for FooWithout!
    {{ _.role('user') }}
    This will not be cached for Foo or FooWithout!
  "#
  ```

  You can use the playground to see the raw curl request to see what is being sent to the API.Whether the internal LLM client should use the streaming API. **Default: `true`**

  Then in your prompt you can use something like:

  ```baml
  clientMyClientWithoutStreaming {
    provider anthropic
    options {
      model claude-3-5-haiku-20241022
      api_key env.ANTHROPIC_API_KEY
      max_tokens 1000
      supports_streaming false
    }
  }

  function MyFunction() -> string {
    client MyClientWithoutStreaming
    prompt #"Write a short story"#
  }
  ```

  ```python
  # This will be streamed from your python code perspective, 
  # but under the hood it will call the non-streaming HTTP API
  # and then return a streamable response with a single event
  b.stream.MyFunction()

  # This will work exactly the same as before
  b.MyFunction()
  ```Which finish reasons are allowed? **Default: `null`**version 0.73.0 onwards: This is case insensitive.Will raise a `BamlClientFinishReasonError` if the finish reason is not in the allow list. See [Exceptions](/guide/baml-basics/error-handling#bamlclientfinishreasonerror) for more details.

  Note, only one of `finish_reason_allow_list` or `finish_reason_deny_list` can be set.

  For example you can set this to `["stop"]` to only allow the stop finish reason, all other finish reasons (e.g. `length`) will treated as failures that PREVENT fallbacks and retries (similar to parsing errors).

  Then in your code you can use something like:

  ```baml
  clientMyClient {
    provider "openai"
    options {
      model "gpt-5-mini"
      api_key env.OPENAI_API_KEY
      // Finish reason allow list will only allow the stop finish reason
      finish_reason_allow_list ["stop"]
    }
  }
  ```Which finish reasons are denied? **Default: `null`**version 0.73.0 onwards: This is case insensitive.Will raise a `BamlClientFinishReasonError` if the finish reason is in the deny list. See [Exceptions](/guide/baml-basics/error-handling#bamlclientfinishreasonerror) for more details.

  Note, only one of `finish_reason_allow_list` or `finish_reason_deny_list` can be set.

  For example you can set this to `["length"]` to stop the function from continuing if the finish reason is `length`. (e.g. LLM was cut off because it was too long).

  Then in your code you can use something like:

  ```baml
  clientMyClient {
    provider "openai"
    options {
      model "gpt-5-mini"
      api_key env.OPENAI_API_KEY
      // Finish reason deny list will allow all finish reasons except length
      finish_reason_deny_list ["length"]
    }
  }
  ```### `media_url_handler`

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
* **Use `send_base64_unless_google_url`** when working with Google Cloud Storage and want to preserve gs\:// URLsURL fetching happens at request time and may add latency. Consider caching or pre-converting frequently used media when using `send_base64` mode.Anthropic's default behavior is to convert PDFs to base64 (`send_base64`) while keeping other media types as URLs (`send_url`). This is because Anthropic's API requires PDFs to be base64-encoded.## Provider request parameters

These are other parameters that are passed through to the provider, without modification by BAML. For example if the request has a `temperature` field, you can define it in the client here so every call has that set.

Consult the specific provider's documentation for more information.BAML will auto construct this field for you from the prompt, if necessary.
  Only the first system message will be used, all subsequent ones will be cast to the `assistant` role.BAML will auto construct this field for you from the promptBAML will auto construct this field for you based on how you call the client in your codeThe model to use.

  | Model                         | Use Case                  | Release  | Context | Features                |
  | ----------------------------- | ------------------------- | -------- | ------- | ----------------------- |
  | **claude-opus-4-1-20250805**  | Complex coding, AI agents | Aug 2025 | 200K    | Most powerful reasoning |
  | **claude-sonnet-4-20250514**  | Default choice, versatile | May 2025 | 200K-1M | Hybrid reasoning modes  |
  | **claude-3-5-haiku-20241022** | Fast, cost-efficient      | Oct 2024 | 200K    | Speed optimized         |See anthropic docs for the latest list of all models. You can pass any model name you wish, we will not check if it exists.The maximum number of tokens to generate. **Default: `4069`**For all other options, see the [official anthropic API documentation](https://docs.anthropic.com/en/api/messages).
