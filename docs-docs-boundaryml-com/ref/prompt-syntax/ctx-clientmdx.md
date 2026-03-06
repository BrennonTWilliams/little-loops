---
url: https://docs.boundaryml.com/ref/prompt-syntax/ctx-client.mdx
scraped_at: 2026-03-06T01:00:51.577513
filepath: docs-docs-boundaryml-com/ref/prompt-syntax/ctx-clientmdx.md
---


***

## title: ctx (accessing metadata)

If you try rendering `{{ ctx }}` into the prompt (literally just write that out!), you'll see all the metadata we inject to run this prompt within the playground preview.

In the earlier tutorial we mentioned `ctx.output_format`, which contains the schema, but you can also access client information:

## Usecase: Conditionally render based on client provider

In this example, we render the list of messages in XML tags if the provider is Anthropic (as they recommend using them as delimiters). See also  [template\_string](/ref/baml/template-string) as it's used in here.

```baml
template_string RenderConditionally(messages: Message[]) #"
  {% for message in messages %}
    {%if ctx.client.provider == "anthropic" %}{{ message.user_name }}: {{ message.content }}{% else %}
      {{ message.user_name }}: {{ message.content }}
    {% endif %}
  {% endfor %}
"#

function MyFuncWithGPT4(messages: Message[]) -> string {
  client GPT4o
  prompt #"
    {{ RenderConditionally(messages)}}
  "#
}

function MyFuncWithAnthropic(messages: Message[]) -> string {
  client Claude35
  prompt #"
    {{ RenderConditionally(messages )}}
  #"
}
```
