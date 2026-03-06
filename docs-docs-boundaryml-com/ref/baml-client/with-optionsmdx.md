---
url: https://docs.boundaryml.com/ref/baml_client/with-options.mdx
scraped_at: 2026-03-06T01:00:44.762098
filepath: docs-docs-boundaryml-com/ref/baml-client/with-optionsmdx.md
---


***

## title: with\_optionsAdded in 0.79.0The `with_options` function creates a new client with default configuration options for logging, client registry, and type builders. These options are automatically applied to all function calls made through this client, but can be overridden on a per-call basis when needed.

## Quick Start```python
    from baml_client import b
    from baml_py import ClientRegistry, Collector

    # Simple: just set the client name
    my_b = b.with_options(client="openai/gpt-5-mini")

    # Or with full options for advanced use cases
    collector = Collector(name="my-collector")
    client_registry = ClientRegistry()
    client_registry.set_primary("openai/gpt-5-mini")
    env = {"BAML_LOG": "DEBUG", "OPENAI_API_KEY": "key-123"}

    # Create client with default options
    my_b = b.with_options(collector=collector, client_registry=client_registry, env=env)

    # Uses the default options
    result = my_b.ExtractResume("...")

    # Override options for a specific call
    other_collector = Collector(name="other-collector")
    result2 = my_b.ExtractResume("...", baml_options={"collector": other_collector})
    ``````typescript
    import { b } from "baml_client"
    import { Collector, ClientRegistry } from "@boundaryml/baml"

    // Simple: just set the client name
    const myB = b.withOptions({ client: "openai/gpt-5-mini" })

    // Or with full options for advanced use cases
    const collector = new Collector("my-collector")
    const clientRegistry = new ClientRegistry()
    clientRegistry.setPrimary("openai/gpt-5-mini")
    const env = {"BAML_LOG": "DEBUG", "OPENAI_API_KEY": "key-123"}

    // Create client with default options
    const myBAdvanced = b.withOptions({ collector, clientRegistry, env })

    // Uses the default options
    const result = await myBAdvanced.ExtractResume("...")

    // Override options for a specific call
    const otherCollector = new Collector("other-collector")
    const result2 = await myBAdvanced.ExtractResume("...", { collector: otherCollector })
    ```Go doesn't have a `with_options` method like Python/TypeScript. Instead, use individual option functions like `WithClient`, `WithCollector`, `WithClientRegistry`, and `WithEnv` directly in function calls.```go
    package main

    import (
        "context"

        b "example.com/myproject/baml_client"
    )

    func run() {
        ctx := context.Background()

        // Simple: just set the client name
        result, err := b.ExtractResume(ctx, "...", b.WithClient("openai/gpt-5-mini"))
        if err != nil {
            panic(err)
        }

        // Or with full options for advanced use cases
        collector, err := b.NewCollector("my-collector")
        if err != nil {
            panic(err)
        }

        env := map[string]string{
            "BAML_LOG": "DEBUG",
            "OPENAI_API_KEY": "key-123",
        }

        // Make function call with multiple options
        result, err = b.ExtractResume(ctx, "...",
            b.WithClient("openai/gpt-5-mini"),
            b.WithCollector(collector),
            b.WithEnv(env))
        if err != nil {
            panic(err)
        }

        // Override options for a specific call
        otherCollector, err := b.NewCollector("other-collector")
        if err != nil {
            panic(err)
        }
        result2, err := b.ExtractResume(ctx, "...", b.WithCollector(otherCollector))
        if err != nil {
            panic(err)
        }
    }
    ``````ruby
    require 'baml_client'

    # Set up default options for this client
    collector = Baml::Collector.new(name: "my-collector")
    client_registry = Baml::ClientRegistry.new
    client_registry.set_primary("openai/gpt-5-mini")
    env = {"BAML_LOG": "DEBUG", "OPENAI_API_KEY": "key-123"}

    # Create client with default options
    my_b = Baml.Client.with_options(collector: collector, client_registry: client_registry, env: env)

    # Uses the default options
    result = my_b.ExtractResume(input: "...")

    # Override options for a specific call
    other_collector = Baml::Collector.new(name: "other-collector")
    result2 = my_b.ExtractResume(input: "...", baml_options: { collector: other_collector })
    ```Rust doesn't have a `with_options` method. Instead, use builder methods like `.with_client()`, `.with_collector()`, `.with_client_registry()`, and `.with_env_var()` directly on function calls.```rust
    use myproject::baml_client::sync_client::B;
    use myproject::baml_client::new_collector;
    use baml::ClientRegistry;
    use std::collections::HashMap;

    fn main() {
        let collector = new_collector("my-collector");

        let mut registry = ClientRegistry::new();
        registry.set_primary_client("openai/gpt-5-mini");

        // Pass options per call using builder methods
        let result = B.ExtractResume
            .with_collector(&collector)
            .with_client_registry(&registry)
            .with_env_var("BAML_LOG", "DEBUG")
            .call("...")
            .unwrap();
    }
    ```## Common Use Cases

### Basic Configuration

Use `with_options` to create a client with default settings that will be applied to all function calls made through this client. These defaults can be overridden when needed.```python
    from baml_client import b
    from baml_py import ClientRegistry, Collector

    def run():
        # Configure options
        collector = Collector(name="my-collector")
        client_registry = ClientRegistry()
        client_registry.set_primary("openai/gpt-5-mini")

        # Create configured client
        my_b = b.with_options(collector=collector, client_registry=client_registry)

        # All calls will use the configured options
        res = my_b.ExtractResume("...")
        invoice = my_b.ExtractInvoice("...")

        # Access configuration
        print(my_b.client_registry)
        # Access logs from the collector
        print(collector.logs)
        print(collector.last)
    ``````typescript
    import { b } from "baml_client"
    import { Collector, ClientRegistry } from "@boundaryml/baml"

    const collector = new Collector("my-collector")
    const clientRegistry = new ClientRegistry()
    clientRegistry.setPrimary("openai/gpt-5-mini")

    const myB = b.withOptions({ collector, clientRegistry })

    // All calls will use the configured options
    const res = await myB.ExtractResume("...")
    const invoice = await myB.ExtractInvoice("...")

    // Access configuration
    console.log(myB.clientRegistry)
    console.log(collector.logs)
    console.log(collector.last?.usage)
    ```Go doesn't support client pre-configuration with `with_options`. Each function call requires options to be passed individually.```go
    package main

    import (
        "context"
        "fmt"
        
        b "example.com/myproject/baml_client"
    )

    func run() {
        ctx := context.Background()
        
        // Configure options for reuse
        collector, err := b.NewCollector("my-collector")
        if err != nil {
            panic(err)
        }
        
        clientRegistry, err := b.NewClientRegistry()
        if err != nil {
            panic(err)
        }
        err = clientRegistry.SetPrimary("openai/gpt-5-mini")
        if err != nil {
            panic(err)
        }
        
        // All calls must explicitly pass options
        res, err := b.ExtractResume(ctx, "...", nil, 
            b.WithCollector(collector), 
            b.WithClientRegistry(clientRegistry))
        if err != nil {
            panic(err)
        }
        
        invoice, err := b.ExtractInvoice(ctx, "...", 
            b.WithCollector(collector), 
            b.WithClientRegistry(clientRegistry))
        if err != nil {
            panic(err)
        }
        
        // Access logs from collector
        logs, err := collector.Logs()
        if err != nil {
            panic(err)
        }
        fmt.Printf("Logs: %+v\n", logs)
    }
    ``````ruby
    require 'baml_client'

    collector = Baml::Collector.new(name: "my-collector")
    client_registry = Baml::ClientRegistry.new
    client_registry.set_primary("openai/gpt-5-mini")

    my_b = Baml.Client.with_options(collector: collector, client_registry: client_registry)

    # All calls will use the configured options
    res = my_b.ExtractResume(input: "...")
    invoice = my_b.ExtractInvoice(input: "...")

    # Access configuration
    print(my_b.client_registry)
    print(collector.logs)
    print(collector.last.usage)
    ``````rust
    use myproject::baml_client::sync_client::B;
    use myproject::baml_client::new_collector;
    use baml::ClientRegistry;

    fn main() {
        let collector = new_collector("my-collector");

        let mut registry = ClientRegistry::new();
        registry.set_primary_client("openai/gpt-5-mini");

        // Pass options per call using builder methods
        let res = B.ExtractResume
            .with_collector(&collector)
            .with_client_registry(&registry)
            .call("...")
            .unwrap();

        let invoice = B.ExtractInvoice
            .with_collector(&collector)
            .with_client_registry(&registry)
            .call("...")
            .unwrap();

        // Access logs from collector
        let logs = collector.logs();
        println!("{:?}", logs);
    }
    ```### Per-call Tags

Add tags to a specific BAML function call. Tags are useful for correlating requests, A/B versions, user IDs, etc.```python
    from baml_client import b
    from baml_py import Collector

    collector = Collector(name="tags-collector")
    res = b.TestOpenAIGPT4oMini(
        "hello",
        baml_options={
            "collector": collector,
            "tags": {"call_id": "first", "version": "v1"},
        },
    )

    print(collector.last.tags)
    ``````typescript
    import { b } from "baml_client";
    import { Collector } from "@boundaryml/baml";

    const collector = new Collector("tags-collector");
    await b.TestOpenAIGPT4oMini("hello", { collector, tags: { callId: "first", version: "v1" } });
    console.log(collector.last!.tags);
    ``````go
    ctx := context.Background()
    collector, _ := b.NewCollector("tags-collector")
    tags := map[string]string{"callId": "first", "version": "v1"}
    _, _ = b.TestOpenAIGPT4oMini(ctx, "hello", b.WithCollector(collector), b.WithTags(tags))
    logs, _ := collector.Logs()
    if len(logs) > 0 {
        t, _ := logs[0].Tags()
        fmt.Println(t)
    }
    ``````rust
    use myproject::baml_client::sync_client::B;
    use myproject::baml_client::new_collector;

    let collector = new_collector("tags-collector");
    let result = B.TestOpenAIGPT4oMini
        .with_collector(&collector)
        .with_tag("call_id", "first")
        .with_tag("version", "v1")
        .call("hello")
        .unwrap();

    let logs = collector.logs();
    if let Some(log) = logs.last() {
        println!("{:?}", log.tags());
    }
    ```### Parallel Execution

When running functions in parallel, `with_options` helps maintain consistent configuration across all calls. This works seamlessly with the [`Collector`](./collector) functionality.```python
    from baml_client.async_client import b
    from baml_py import ClientRegistry, Collector
    import asyncio

    async def run():
        collector = Collector(name="my-collector")
        my_b = b.with_options(collector=collector, client_registry=client_registry)

        # Run multiple functions in parallel
        res, invoice = await asyncio.gather(
            my_b.ExtractResume("..."),
            my_b.ExtractInvoice("...")
        )

        # Access results and logs
        print(res)
        print(invoice)
        # Use tags or iterate logs to correlate specific calls
        for log in collector.logs:
            print(log.usage)
    ``````typescript
    import { Collector, ClientRegistry } from "@boundaryml/baml"

    const collector = new Collector("my-collector")
    const myB = b.withOptions({ collector, clientRegistry })

    // Run multiple functions in parallel
    const [
        {data: res, id: resumeId},
        {data: invoice, id: invoiceId}
    ] = await Promise.all([
        myB.raw.ExtractResume("..."),
        myB.raw.ExtractInvoice("...")
    ])

    // Access results and logs
    console.log(res)
    console.log(invoice)
    // Use tags or iterate logs to correlate specific calls
    for (const log of collector.logs) {
      console.log(log.usage)
    }
    ```BAML Ruby (beta) does not currently support async/concurrent calls. Reach out to us if it's something you need!### Streaming Mode

`with_options` can be used with streaming functions while maintaining all configured options.```python
    from baml_client.async_client import b
    from baml_py import Collector

    async def run():
        collector = Collector(name="my-collector")
        my_b = b.with_options(collector=collector, client_registry=client_registry)

        stream = my_b.stream.ExtractResume("...")
        async for chunk in stream:
            print(chunk)
        
        result = await stream.get_final_result()
        # Use tags or collector.last / collector.logs for usage
        print(collector.last.usage)
    ``````typescript
    import { Collector } from "@boundaryml/baml"

    const collector = new Collector("my-collector")
    const myB = b.withOptions({ collector, clientRegistry })

    const stream = myB.stream.ExtractResume("...")
    for await (const chunk of stream) {
        console.log(chunk)
    }

    const result = await stream.getFinalResult()
    // Use tags or collector.last / collector.logs for usage
    console.log(collector.last?.usage)
    ``````ruby
    require 'baml_client'

    collector = Baml::Collector.new(name: "my-collector")
    my_b = Baml.Client.with_options(collector: collector, client_registry: client_registry)

    stream = my_b.stream.ExtractResume(input: "...")
    stream.each do |chunk|
        print(chunk)
    end

    result = stream.get_final_result
    # Use tags or collector.last / collector.logs for usage
    print(collector.last.usage)
    ``````rust
    use myproject::baml_client::sync_client::B;
    use myproject::baml_client::new_collector;

    let collector = new_collector("my-collector");

    let mut stream = B.ExtractResume
        .with_collector(&collector)
        .stream("...")?;

    for partial in stream.partials() {
        println!("{:?}", partial?);
    }

    let result = stream.get_final_response()?;
    // Access usage from collector
    println!("{:?}", collector.usage());
    ```## API Reference

### with\_options ParametersThese can always be overridden on a per-call basis with the `baml_options` parameter in any function call.| Parameter         | Type                                           | Description                                                                      |
| ----------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- |
| `client`          | `string`                                       | Client name to use for all calls (shorthand for `client_registry.set_primary()`) |
| `collector`       | [`Collector`](/ref/baml_client/collector)      | Collector instance for tracking function calls and usage metrics                 |
| `client_registry` | `ClientRegistry`                               | Registry for managing LLM clients and their configurations                       |
| `type_builder`    | [`TypeBuilder`](/ref/baml_client/type-builder) | Custom type builder for function inputs and outputs                              |
| `env`             | `Dict/Object`                                  | Environment variables to set for the client                                      |
| `tags` (per-call) | `Dict/Object`                                  | Arbitrary metadata for this call; merged with parent trace tags                  |

### Configured Client PropertiesThe configured client maintains the same interface as the base `baml_client`, so you can use all the same functions and methods.## Related Topics

* [Collector](/ref/baml_client/collector) - Track function calls and usage metrics
* [TypeBuilder](/ref/baml_client/type-builder) - Build custom types for your functions
* [Client Registry](/ref/baml_client/client-registry) - Manage LLM clients and their configurations
* [Environment Variables](/ref/baml/general-baml-syntax/environment-variables) - Set environment variables
* [AbortController](/ref/baml_client/abort-signal) - Cancel in-flight operationsThe configured client maintains the same interface as the base client, so you can use all the same functions and methods.
