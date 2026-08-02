# PML 0.1 normalized architecture decisions

Status: Owner approved
Approved direction: 2026-07-29

## Decision

PML has one optional top-level `architecture` registry keyed by decision ID. A
decision is flat and has exactly these authored fields:

```text
category, selection, rationale, constraints
```

`category` is one of `database`, `framework`, `gateway`, `provider`,
`payment_processor`, or `runtime`. `selection` and `rationale` are canonical,
non-empty statements of the approved choice and why it requires owner approval.
`constraints` is optional and is an ID-keyed map of rules using the established
`statement` form.

Features and components reference decisions only with `architecture: [decision_id]`.
This is bottom-up: `applies_to`, `supports`, inline definitions, and decision-to-
decision references are not language constructs. Every declared decision must have
at least one such reference.

## Boundary and verification

Architecture specifies owner-mandated technical choices, not product behavior. It
continues to reject filenames, functions, classes, tables, endpoints, configuration
syntax, and topology. A technology being present is never proof that either product
or architecture constraints conform.

Architecture constraints resolve into `architecture.<decision_id>.constraints.<id>`
obligations. They use the established external verification plan and evidence model,
but are bound under the separate `architecture` section of the owner-controlled
bindings defined by [0005](0005-bindings-boundary.md), stored under
`.pml/architecture/`, and reported through separate architecture conformance
derivation. Product state and product status do not include architecture constraints.
