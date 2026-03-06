---
url: https://docs.boundaryml.com/ref/baml_client/react-next-js/hook-output.mdx
scraped_at: 2026-03-06T01:00:43.914818
filepath: docs-docs-boundaryml-com/ref/baml-client/react-next-js/hook-outputmdx.md
---


***

title: Hook Output Type Reference
description: Technical reference for the BAML React hook output type
--------------------------------------------------------------------

The `HookOutput` type defines the return type for BAML React hooks.```typescript title="Example Usage"
  function Component() {
    const hook = useTestAws({
      stream: true, // optional, defaults to true
    })

    return ({hook.error &&Error: {hook.error.message}}hook.mutate("test")} disabled={hook.isLoading}>
          Submit)
  }
  ```

  ```typescript title="Example Types"
  // Streaming configuration
  const streamingResult: HookOutput<'TestAws', { stream: true }> = {
    data: "Any response",
    finalData: "Final response",
    streamData: "Streaming response...",
    error: undefined,
    isError: false,
    isLoading: true,
    isSuccess: false,
    isStreaming: true,
    isPending: false,
    status: 'streaming',
    mutate: async () => new ReadableStream(),
    reset: () => void
  }

  // Non-streaming configuration
  const nonStreamingResult: HookOutput<'TestAws', { stream: false }> = {
    data: "Final response",
    finalData: "Final response",
    error: undefined,
    isError: false,
    isLoading: false,
    isSuccess: true,
    isPending: false,
    status: 'success',
    mutate: async () => "Final response",
    reset: () => void
  }
  ```

  ```typescript title="Type Definition"
  type HookOutput= {
    data?: Options['stream'] extends false ? FinalDataType: FinalDataType| StreamDataTypefinalData?: FinalDataTypestreamData?: Options['stream'] extends false ? never : StreamDataTypeerror?: BamlErrors
    isError: boolean
    isLoading: boolean
    isPending: boolean
    isSuccess: boolean
    isStreaming: Options['stream'] extends false ? never : boolean
    status: HookStatusmutate: (...args: Parameters) => Options['stream'] extends false
      ? Promise>
      : Promise>
    reset: () => void
  }

  type HookStatus= Options['stream'] extends false
    ? 'idle' | 'pending' | 'success' | 'error'
    : 'idle' | 'pending' | 'streaming' | 'success' | 'error'
  ```## Type ParametersThe name of the BAML function being called. Used to infer input and output types.Configuration object that determines streaming behavior. Defaults to `{ stream?: true }`.## PropertiesThe current response data. For streaming hooks, this contains either the latest streaming response or the final response. For non-streaming hooks, this only contains the final response.The final response data. Only set when the request completes successfully.The latest streaming response. Only available when `Options['stream']` is true.Any error that occurred during the request. See [Error Types](../errors/overview).True if the request resulted in an error.True if the request is in progress (either pending or streaming).True if the request is pending (not yet streaming or completed).True if the request completed successfully.True if the request is currently streaming data. Only available when `Options['stream']` is true.The current status of the request. For streaming hooks: 'idle' | 'pending' | 'streaming' | 'success' | 'error'. For non-streaming hooks: 'idle' | 'pending' | 'success' | 'error'.Function to trigger the BAML action. Returns a ReadableStream for streaming hooks, or a Promise of the final response for non-streaming hooks.Function to reset the hook state back to its initial values.
