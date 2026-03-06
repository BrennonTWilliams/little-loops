---
url: https://docs.boundaryml.com/ref/attributes/description.mdx
scraped_at: 2026-03-06T01:00:35.087873
filepath: docs-docs-boundaryml-com/ref/attributes/descriptionmdx.md
---


The `@description` attribute in BAML provides additional context to fields or values in prompts. This can help the LLM understand the intended use or meaning of a field or value.

## Prompt Impact

### Without `@description`

```baml BAML
class MyClass {
  property1 string
}
```

**ctx.output\_format:**

```
{
  property1: string
}
```

### With `@description`

```baml BAML
class MyClass {
  property1 string @description("The name of the object")
}
```

**ctx.output\_format:**

```
{
  // The name of the object
  property1: string
}
```

## Prompt Impact (enum - value)

### Without `@description`

```baml BAML
enum MyEnum {
  Value1
  Value2
}
```

**ctx.output\_format:**

```
MyEnum
---
Value1
Value2
```

### With `@description`

```baml BAML
enum MyEnum {
  Value1 @description("The first value")
  Value2 @description("The second value")
}
```

**ctx.output\_format:**

```
MyEnum
---
Value1: The first value
Value2: The second value
```

## Prompt Impact (enum)

```baml BAML
enum MyEnum {
  Value1
  Value2

  @@description("This enum represents status codes")
}
```

**ctx.output\_format:**

```
MyEnum: This enum represents status codes
---
Value1
Value2
```
