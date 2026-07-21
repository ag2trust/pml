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

## Documentation

- [Quickstart](docs/quickstart.md) — write and validate a small manifest.
- [Language reference](docs/language-reference.md) — every PML 0.1 attribute.
- [Authoring guide](docs/authoring-guide.md) — write precise, implementation-free contracts.
- [Verification protocol](docs/verification.md) — verify an implementation against PML.
- [Language design](docs/specs/0001-language-design.md) — normative rationale and semantics.
- [Deterministic verification](docs/specs/0002-deterministic-verification.md) — probes, evidence kinds, and governance.

Examples:

- [Minimal valid manifest](examples/minimal.pml.yaml)
- [Richer Assistant creation manifest](examples/assistant-creation.pml.yaml)
- [Invalid manifest](examples/invalid.pml.yaml) with expected diagnostics
- [Verification report](examples/verification-report.yaml)
- [Probe definition](examples/assistant-persistence.probe.yaml)

## Repository layout

```text
docs/specs/       Normative language designs
examples/         Example PML programs
schema/           Reserved for the approved structural schema
src/              Parser and validator
tests/            Language conformance tests
```
