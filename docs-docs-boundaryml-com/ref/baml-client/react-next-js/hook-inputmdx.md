---
url: https://docs.boundaryml.com/ref/baml_client/react-next-js/hook-input.mdx
scraped_at: 2026-03-06T01:00:43.620920
filepath: docs-docs-boundaryml-com/ref/baml-client/react-next-js/hook-inputmdx.md
---


***

title: Hook Input Type Reference
description: Technical reference for the BAML React hook input type
-------------------------------------------------------------------

The `HookInput` type defines the configuration options for BAML React hooks.```typescript title="Example Usage"
  function Component() {
    const hook = useTestAws({
      stream: true, // optional, defaults to true
      onStreamData: (text) => console.log("Streaming:", text),
      onFinalData: (text) => console.log("Complete:", text),
      onData: (text) => console.log("Any update:", text),
      onError: (error) => console.error("Error:", error)
    })

    return{hook.data}}
  ```

  ```typescript title="Example Types"
  // Streaming configuration
  const streamingInput: HookInput<'TestAws', { stream: true }> = {
    stream: true,
    onStreamData: (text) => console.log("Streaming:", text),
    onFinalData: (text) => console.log("Final:", text),
    onData: (text) => console.log("Any update:", text),
    onError: (error) => console.error(error),
  }

  // Non-streaming configuration
  const nonStreamingInput: HookInput<'TestAws', { stream: false }> = {
    stream: false,
    onFinalData: (text) => console.log("Result:", text),
    onData: (text) => console.log("Result:", text),
    onError: (error) => console.error(error)
  }
  ```

  ```typescript title="Type Definition"
  type HookInput= {
    stream?: Options['stream']
    onStreamData?: Options['stream'] extends false ? never : (response?: StreamDataType) => void
    onFinalData?: (response?: FinalDataType) => void
    onData?: (response?: StreamDataType| FinalDataType) => void
    onError?: (error: BamlErrors) => void
  }
  ```## Type ParametersThe name of the BAML function being called. Used to infer the correct types for responses.Configuration object that determines streaming behavior. Defaults to `{ stream?: true }`.## PropertiesFlag to enable or disable streaming mode. When true, enables streaming responses.Callback function for streaming responses. Only available when `Options['stream']` is true.Callback function for the final response.Unified callback function that receives both streaming and final responses. For non-streaming hooks, only receives final responses.Callback function for error handling. See [Error Types](../errors/overview).
