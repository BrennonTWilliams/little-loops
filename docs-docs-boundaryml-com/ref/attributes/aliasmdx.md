---
url: https://docs.boundaryml.com/ref/attributes/alias.mdx
scraped_at: 2026-03-06T01:00:34.411138
filepath: docs-docs-boundaryml-com/ref/attributes/aliasmdx.md
---


The `@alias` attribute in BAML is used to rename fields or values for better understanding by the LLM, while keeping the original name in your code. This is particularly useful for prompt engineering, as it allows you to provide a more intuitive name for the LLM without altering your existing codebase.

## Prompt Impact (class)

### Without `@alias`

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

### With `@alias`

```baml BAML
class MyClass {
  property1 string @alias("name")
}
```

**ctx.output\_format:**

```
{
  name: string
}
```

## Prompt Impact (enum)

```baml BAML
enum MyEnum {
  Value1 
  // Note that @@alias is applied to the enum itself, not the value
  @@alias("My Name")
}
```

**ctx.output\_format:**

```
My Name
---
Value1
```

## Prompt Impact (enum value)

```baml BAML
enum MyEnum {
  Value1 @alias("Something")
}
```

**ctx.output\_format:**

```
MyEnum
---
Something
```
