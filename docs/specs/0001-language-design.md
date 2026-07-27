# PML 0.1 language design

Status: Approved, normalized by [0004](0004-language-normalization.md)

## Purpose

PML is a small, closed language for approved product intent. It describes product
meaning and observable behavior without prescribing implementation. Unknown keys,
unresolved references, and ad hoc relationship types are invalid.

## Authority boundary

Approved definitions are authoritative. Generated state and evidence may report
conformance but may not weaken or silently change product intent.

## Canonical hierarchy

```text
Project → Domain → Feature → Component
```

- A domain groups product responsibilities.
- A feature is a complete user or business capability.
- A component is a direct, non-nested behavioral part of a feature.

Features and components may establish symmetric, untyped `related_to` edges using
unique semantic paths. Those edges carry change impact but do not imply a dependency
direction.

## Canonical objects

- `vocabulary`: terminology enforcement when useful.
- `actors`: participants, each with one meaning.
- `concepts`: meaningful product entities and optional unordered states.
- `signals`: meaningful product facts, never required code events or messages.
- `rules`: scoped normative invariants.
- `use_cases`: actor goals and end-to-end scenarios.
- `reactions`: direct normative consequences of signals.
- `experience`: actor-visible information, controls, and states.
- `architecture`: independently owner-mandated technical decisions.

Features may `emit` signals. Reactions refer to a signal with `on` and contain one
normative `statement`. Several consequences of one signal are several independently
identified reactions.

Inputs and outputs exist only on components. They describe product-behavior
boundaries, never function arguments, endpoints, or payload schemas.

## Controlled language

Each rule or reaction statement expresses one obligation and contains `MUST` or
`MUST NOT`. Descriptive fields such as `purpose`, `meaning`, and `goal` are not
normative. Validators reject ambiguous normative qualifiers such as `should`,
`normally`, `properly`, and `etc`.

## Obligations

Obligation is a compiler/tooling term, not an authored section. Rules, reactions,
and use-case outcomes resolve into stable obligation paths. Verification mechanics
are external bindings; current evidence and scores are generated state.

## Architecture

Architecture decisions are flat and optional. They may name a category, approved
selection, rationale, and normative constraints. A feature or component references
decisions bottom-up.

A technical choice belongs in architecture only when replacement requires explicit
owner approval even if product behavior remains correct. Architecture must not name
files, functions, classes, tables, endpoints, configuration syntax, or topology.
Technology existence never proves conformance.

## Validation

Validation proceeds through restricted YAML syntax, exact schema, reference
resolution, canonical vocabulary, normative-language checks, relationship checks,
and completeness checks. Validation reports ambiguity; it never silently repairs
intent.

## Non-goals

PML does not define code organization, APIs, storage schemas, tests, infrastructure,
monitoring configuration, implementation state, evidence, commits, or work tracking.
