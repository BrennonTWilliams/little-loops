---
url: https://docs.boundaryml.com/ref/llm-client-providers/microsoft-foundry.mdx
scraped_at: 2026-03-06T01:00:48.136720
filepath: docs-docs-boundaryml-com/ref/llm-client-providers/microsoft-foundrymdx.md
---


***

## title: Microsoft Foundry  / Azure AI Foundry

Microsoft Foundry is the new way to use AI models on Azure, which is a simplified version of Azure-on-openai provider.

To use the Microsoft Foundry (Azure AI) ([https://ai.azure.com](https://ai.azure.com)), you can leverage the [`openai-generic`](/docs/snippets/clients/providers/openai) provider.

Use the **Completions** API setup to make it work with BAML.

**Example:**

```baml BAML
clientMyClient {
  provider "openai-generic"
  options {
    // use the API key it indicates in the 'models' sidebar navigation menu, and clicking on the model you want to use
    base_url "https://boundarydev-resource.openai.azure.com/openai/v1/"
    api_key env.AZURE_AI_FOUNDRY_API_KEY
    model "gpt-5-mini" // use the model you actually deployed
  }
}
```

See here to see how to get your API key and base url:
