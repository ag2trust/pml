---
name: pml
description: Author, review, and maintain Product Manifest Language (PML) definitions and their owner-controlled bindings and probes. Use when defining product intent in PML, changing .pml.yaml files, resolving PML validation errors, reviewing PML semantics, or working with pml init, validate, obligations, check, status, architecture-status, validate-probes, or ingest-report.
---

# PML

Treat approved PML definitions as authoritative product intent. Treat PML as a
closed language, not as an extensible documentation format.

## Work in authority order

1. Read the repository's `AGENTS.md` and the applicable PML language reference.
2. Identify whether the request affects language semantics, authored product
   intent, owner-controlled bindings or probes, or generated state.
3. For language changes, obtain owner approval before changing schemas or tools.
4. Update schema and semantic validation before formatter or compiler behavior.
5. Add both accepted and rejected conformance examples for language changes.
6. Run `pml validate` against every authored definition changed.

## Preserve boundaries

- Use only keywords and relationship types defined by the installed PML language.
- Reject unknown keys and unresolved references; do not invent sections or synonyms.
- State observable product outcomes, not filenames, functions, endpoints, framework
  components, classes, or tests in normative definitions.
- Keep authored definitions separate from generated state and evidence.
- Never interpret implementation existence as evidence of conformance.
- Never let generated state or evidence silently change approved definitions.

## Use project artifacts

Locate the owner-controlled definition and adjacent `bindings.yaml` and `probes/`
instead of assuming product-local copies. Use `.pml/` only for the content lock and
generated evidence state. Inspect the lock before commands that depend on an
approved source identity.

When validation fails, report the exact diagnostic and fix the authoritative
artifact responsible for it. Do not weaken validation merely to accept an invalid
definition.
