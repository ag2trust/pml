# PML authoring guide

## Write product truth

Describe observable behavior:

```yaml
statement: THE SYSTEM MUST preserve accepted Assistant configuration across sessions.
```

Do not name endpoints, tables, files, functions, frameworks, or tests.

## Use the hierarchy consistently

```text
Domain → Feature → Component
```

A feature is a complete capability. A component is a direct, non-nested behavioral
part. Component inputs and outputs describe product boundaries, not APIs.

## Write atomic obligations

Every rule and reaction statement contains `MUST` or `MUST NOT` and expresses one
independently verifiable constraint. Split multiple consequences into separate
ID-keyed entries.

Rules are invariants. Use cases describe actor goals, preconditions, actions, and
outcomes. Do not copy the same outcome into both.

## Connect behavior deliberately

Use `signals` for meaningful product facts, `emits` to establish those facts, and
reactions with `on` for direct consequences. Signals never require code events.

Use untyped `related_to` paths when changes in either feature/component should affect
the other's verification freshness.

## Keep verification external

The compiler resolves authored behavior into stable obligations. Product-local
bindings assign probe, agent, and human coverage. Generated state stores evidence and
derived confidence. Definitions never contain current scores or verification
procedures.
