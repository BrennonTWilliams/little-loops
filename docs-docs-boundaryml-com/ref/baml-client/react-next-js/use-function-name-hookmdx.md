---
url: https://docs.boundaryml.com/ref/baml_client/react-next-js/use-function-name-hook.mdx
scraped_at: 2026-03-06T01:00:44.138206
filepath: docs-docs-boundaryml-com/ref/baml-client/react-next-js/use-function-name-hookmdx.md
---


***

title: Generated Hooks Reference
description: Technical reference for BAML's auto-generated React hooks
----------------------------------------------------------------------

BAML automatically generates a type-safe React hook for each BAML function. Each hook follows the naming pattern `use{FunctionName}` and supports both streaming and non-streaming modes.```typescript title="Example Usage"
  import { useWriteMeAStory } from "@/baml_client/react/hooks";

  // Basic usage with streaming enabled by default
  const hook = useWriteMeAStory();

  // Access streaming and final data
  const { data, streamData, finalData } = hook;

  // Track request state
  const { isLoading, isStreaming, isPending, isSuccess, isError } = hook;

  // Execute the function
  await hook.mutate("A story about a brave AI");

  // Reset state if needed
  hook.reset();
  ```

  ```baml title="BAML Function"
  class Story {
    title string @stream.not_null
    content string @stream.not_null
  }

  function WriteMeAStory(input: string) -> Story {
    client openai/gpt-4
    prompt #"
      Tell me a story.

      {{ ctx.output_format() }}

      {{ _.role("user") }}

      Topic: {{input}}
    "#
  }
  ```## HookInput

The hook accepts an optional configuration object. See [Hook Input](./hook-input) for complete details.Enable streaming mode for real-time updates. Defaults to true.Callback for streaming updates. Only available when streaming is enabled.Callback when the request completes.Unified callback for both streaming and final responses.Callback when an error occurs. See [Error Types](../errors/overview).## HookOutput

The hook returns an object with the following properties. See [Hook Output](./hook-output) for complete details.The current response data. Contains either streaming or final data depending on the request state.The final response data. Only available when the request completes.Latest streaming update. Only available in streaming mode.Error information if the request fails. See [Error Types](../errors/overview).True while the request is in progress (either pending or streaming).True if the request is pending (not yet streaming or completed).True if the request is currently streaming data. Only available in streaming mode.True if the request completed successfully.True if the request failed.Current state of the request. For streaming hooks: 'idle' | 'pending' | 'streaming' | 'success' | 'error'. For non-streaming hooks: 'idle' | 'pending' | 'success' | 'error'.Function to execute the BAML function. Returns a ReadableStream for streaming hooks, or a Promise of the final response for non-streaming hooks.Function to reset the hook state back to its initial values.
