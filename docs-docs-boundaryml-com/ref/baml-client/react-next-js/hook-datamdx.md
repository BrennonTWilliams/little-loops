---
url: https://docs.boundaryml.com/ref/baml_client/react-next-js/hook-data.mdx
scraped_at: 2026-03-06T01:00:43.496241
filepath: docs-docs-boundaryml-com/ref/baml-client/react-next-js/hook-datamdx.md
---


***

title: Hook Data Type Reference
description: Technical reference for the BAML React hook data type
------------------------------------------------------------------

The `HookData` type represents the non-null data from a BAML React hook. This type is useful when you know the data exists and want to avoid undefined checks.```typescript title="Example Usage"
  function Component() {
    const hook = useTestAws({
      stream: true, // optional, defaults to true
    })

    const data = hook.data;

    return ({data} {/* No need for null checks */})
  }
  ```

  ```typescript title="Example Types"
  // Streaming configuration
  const streamingData: HookData<'TestAws', { stream: true }> = "Streaming response..."

  // Non-streaming configuration
  const nonStreamingData: HookData<'TestAws', { stream: false }> = "Final response"
  ```

  ```typescript title="Type Definition"
  type HookData= NonNullable['data']>
  ```## Type ParametersThe name of the BAML function being called. Used to infer input and output types.Configuration object that determines streaming behavior. Defaults to `{ stream?: true }`.## Type DetailsA utility type that removes undefined from the data property of HookOutput. This means the type will be either FinalDataType or StreamDataType depending on the streaming configuration.
