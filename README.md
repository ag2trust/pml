# Product Manifest Language

Product Manifest Language (PML) is a small, opinionated, declarative language for
describing what a software product is and what it must do.

PML captures product concepts, actors, features, rules, use cases, experiences,
security expectations, events, relationships, and operational outcomes without
prescribing source files, frameworks, APIs, database tables, or tests.

The intended workflow is:

```text
PML manifest
  -> structural and semantic validation
  -> owner approval
  -> specification
  -> implementation plan
  -> implementation
  -> conformance evidence and live product state
```

## Current status

The 0.1 language MVP is under implementation. The normative design is in
[`docs/specs/0001-language-design.md`](docs/specs/0001-language-design.md).

## Validate a manifest

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pml validate pml.yaml
```

Validation covers restricted YAML, exact structure, references, forbidden vocabulary,
and controlled normative language. Product verification is a separate agent workflow;
see [`docs/verification.md`](docs/verification.md).

## Repository layout

```text
docs/specs/       Normative language designs
examples/         Example PML programs
schema/           Reserved for the approved structural schema
src/              Parser and validator
tests/            Language conformance tests
```

