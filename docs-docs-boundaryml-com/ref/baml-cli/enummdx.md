---
url: https://docs.boundaryml.com/ref/baml/enum.mdx
scraped_at: 2026-03-06T01:00:37.542638
filepath: docs-docs-boundaryml-com/ref/baml-cli/enummdx.md
---


Enums are useful for classification tasks. BAML has helper functions that can help you serialize an enum into your prompt in a neatly formatted list (more on that later).

To define your own custom enum in BAML:```baml BAML
  enum MyEnum {
    Value1
    Value2
    Value3
  }
  ```

  ```python Python Equivalent
  from enum import StrEnum

  class MyEnum(StrEnum):
    Value1 = "Value1"
    Value2 = "Value2"
    Value3 = "Value3"
  ```

  ```typescript Typescript Equivalent
  enum MyEnum {
    Value1 = "Value1",
    Value2 = "Value2",
    Value3 = "Value3",
  }
  ```* You may have as many values as you'd like.
* Values may not be duplicated or empty.
* Values may not contain spaces or special characters and must not start with a number.

## Enum AttributesThis is the name of the enum rendered in the prompt.If set, will allow you to add/remove/modify values to the enum dynamically at runtime (in your python/ts/etc code). See [dynamic enums](/guide/baml-advanced/dynamic-runtime-types) for more information.```baml BAML
enum MyEnum {
  Value1
  Value2
  Value3

  @@alias("My Custom Enum")
  @@dynamic // allows me to later skip Value2 at runtime
}
```

## Value Attributes

When prompt engineering, you can also alias values and add descriptions, or even skip them.Aliasing renames the values for the llm to potentially "understand" your value better, while keeping the original name in your code, so you don't need to change your downstream code everytime.

  This will also be used for parsing the output of the LLM back into the enum.This adds some additional context to the value in the prompt.Skip this value in the prompt and during parsing.```baml BAML
enum MyEnum {
  Value1 @alias("complete_summary") @description("Answer in 2 sentences")
  Value2
  Value3 @skip
  Value4 @description(#"
    This is a long description that spans multiple lines.
    It can be useful for providing more context to the value.
  "#)
}
```

See more in [prompt syntax docs](/ref/prompt-syntax/what-is-jinja)
