# PML authoring guide

## Write product truth

Describe observable behavior:

```yaml
statement: THE SYSTEM MUST preserve accepted Assistant configuration across sessions.
```

Do not name endpoints, tables, files, functions, frameworks, or tests.

## Use the hierarchy consistently

```text
Domain → Feature → Behavior
```

A feature is a complete capability. A behavior is a direct, non-nested unit of
observable conduct. Each behavior has one required direct or mutually exclusive
output and may list relevant product context.

## Write atomic obligations

Every rule and reaction statement contains `MUST` or `MUST NOT` and expresses one
independently verifiable constraint. Output statements are normative by position
and do not require those markers. Split multiple consequences into separate
ID-keyed entries.

Rules are invariants. Use cases describe actor goals, preconditions, actions, and
outcomes. Do not copy the same outcome into both.

## Connect behavior deliberately

Use `signals` for meaningful product facts, output `emits` to establish required
effects, and reactions with `on` for direct consequences. Signals never require
code events.

Use untyped `related_to` paths when changes in either feature or behavior should affect
the other's verification freshness.

## Record architecture decisions independently

Use the optional top-level `architecture` registry only for a technical selection
that needs Owner approval even when product behavior would still be correct. A
decision has a closed category, canonical `selection` and `rationale`, and optional
ID-keyed normative `constraints`. Reference its ID from the affected feature or
behavior; do not use `applies_to`, `supports`, inline definitions, or recursive
decisions. Every decision needs at least one reference.

Architecture constraints use external verification bindings and generated evidence
separately from product obligations. Do not use architecture to name files,
functions, classes, tables, endpoints, configuration syntax, or topology.

## Keep verification external

The compiler resolves authored behavior into stable obligations. Product-local
bindings assign probe, agent, and human coverage. Generated state stores evidence and
derived confidence. Definitions never contain current scores or verification
procedures.
