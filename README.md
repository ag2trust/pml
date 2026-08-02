# Product Manifest Language

Product Manifest Language (PML) is a small, opinionated, declarative language for
describing what a software product is and what it must do.

PML captures product concepts, actors, features, components, rules, use cases,
signals, reactions, relationships, experiences, and selected owner-mandated
architecture without prescribing code organization, APIs, database schemas, or tests.

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

`pml validate` accepts a single file or a directory. A directory is one modular
definition with path-derived mounting: each `*.pml.yaml` file's relative path is its
mount point in the document tree (`domains/billing/features/checkout.pml.yaml`
defines `domains.billing.features.checkout`), and `index.pml.yaml` mounts at its
directory itself. Fragments contain only their body. Defining the same field in two
fragments is a `conflict` diagnostic. Components are direct children of features and
do not nest.

Closed schemas prevent ad hoc sections. Product registries and behavioral maps have
explicit size and shape constraints.

Validation covers restricted YAML, exact structure, references, forbidden vocabulary,
and controlled normative language. Product verification is a separate agent workflow;
see [`docs/verification.md`](docs/verification.md).

## Product-local state

Approved definitions remain in an owner-controlled PML repository. An implementing
product repository carries `.pml/pml.lock` and one state file per feature or
component under `.pml/state/`. The owner-controlled source identified by
`definition.source` carries both the definition and `bindings.yaml`. The lock pins
their digests independently. Validate that boundary, including definition,
bindings, and relevant-input fingerprints, with:

```bash
pml check path/to/approved-definition.pml.yaml path/to/product-repository
```

Existing product-local bindings are not used as a fallback. Repositories adopting
this boundary must move `bindings.yaml` beside the locked definition, add the
independent lock digest, and reconcile generated state so it records that digest.

List the stable obligations that state must cover with:

```bash
pml obligations path/to/approved-definition.pml.yaml [node-id]
```

Inspect derived implementation progress and per-obligation verification signals with:

```bash
pml status path/to/approved-definition.pml.yaml path/to/product-repository
```

Validate owner-approved probe definitions against their PML obligations with:

```bash
pml validate-probes path/to/approved-definition.pml.yaml path/to/probes/
```

Use an explicit owner bindings file for isolated completeness validation:

```bash
pml validate-probes definition.pml.yaml probes/ \
  --bindings product-pml/bindings.yaml --require-complete
```

Add `--probes probes/` to `pml check` to validate the approved definitions and their
recorded evidence in product-local state.

Ingest a validated runner or verifier report into product-local state with:

```bash
pml ingest-report definition.pml.yaml product/ probes/ verification-report.yaml
```

Ingestion validates every check against the approved obligation, verification method,
coverage binding, and probe definition before updating touched state files. It does
not execute probes.

Verification coverage is approved per obligation in owner-controlled bindings. State
stores implementation facts and typed evidence; confidence and freshness are derived.
See [`docs/specs/0005-bindings-boundary.md`](docs/specs/0005-bindings-boundary.md).

For resource safety, PML tooling fingerprints bound inputs in fixed-size chunks,
reads at most 1 MiB from each generated `.state.yaml` file, and bounds
generated-state discovery and owner-binding boundary scans. Oversized state is
rejected before YAML parsing, and excess state files, discovery entries, or binding
entries produce a diagnostic without being materialized for validation. These are
tooling limits, not PML language constraints; current schemas and examples produce
state files far below the limits.

Architecture constraints have independent bindings and state. Inspect their derived
conformance without mixing it into product status with:

```bash
pml architecture-status definition.pml.yaml product/
```

## Documentation

- [Quickstart](docs/quickstart.md) — write and validate a small manifest.
- [Language reference](docs/language-reference.md) — every PML 0.1 attribute.
- [Authoring guide](docs/authoring-guide.md) — write precise, implementation-free contracts.
- [Verification protocol](docs/verification.md) — verify an implementation against PML.
- [Language design](docs/specs/0001-language-design.md) — normative rationale and semantics.
- [Deterministic verification](docs/specs/0002-deterministic-verification.md) — probes, evidence kinds, and governance.
- [Product state](docs/specs/0003-product-state.md) — bindings, fingerprints, and derived confidence.
- [Language normalization](docs/specs/0004-language-normalization.md) — approved canonical terms and removals.
- [Bindings boundary](docs/specs/0005-bindings-boundary.md) — owner policy, lock pins, and product-local state.
- [Architecture decisions](docs/specs/0006-architecture-decisions.md) — approved registry and separate conformance semantics.

Examples:

- [Minimal valid manifest](examples/minimal.pml.yaml)
- [Architecture decisions](examples/architecture-decisions.pml.yaml) and [invalid architecture](examples/architecture-invalid.pml.yaml)
- [Richer Assistant creation manifest](examples/assistant-creation.pml.yaml)
- [Invalid manifest](examples/invalid.pml.yaml) with expected diagnostics
- [Verification report](examples/verification-report.yaml)
- [Probe definition](examples/assistant-persistence.probe.yaml)
- [Owner-controlled bindings](examples/bindings.yaml)
- [Product lock](examples/product-repository/.pml/pml.lock)
- [Product-local state](examples/product-repository/.pml/state/domains/notes/features/creation.state.yaml)

## Repository layout

```text
docs/specs/       Normative language designs
examples/         Example PML programs
schema/           Reserved for the approved structural schema
src/              Parser and validator
tests/            Language conformance tests
```
