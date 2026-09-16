# Product Manifest Language

Product Manifest Language (PML) is a small, opinionated, declarative language for
describing what a software product is and what it must do.

PML captures product concepts, actors, features, behavior transitions, rules, use cases,
optional completion signals, relationships, experiences, and selected owner-mandated
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

The owner-approved behavior transition model in
[`docs/specs/0010-behavior-transition-model.md`](docs/specs/0010-behavior-transition-model.md)
is implemented across the schema, semantic validation, conformance examples,
obligation resolution, bindings, probes, state consumers, and authoring
documentation. The owner-approved version 2 compiled semantic model in
[`docs/specs/0011-compiled-semantic-model.md`](docs/specs/0011-compiled-semantic-model.md)
is implemented through canonical serialization and `pml compile --json`.

The owner-approved human review workflow in
[`docs/specs/0012-human-review-workflow.md`](docs/specs/0012-human-review-workflow.md)
is implemented through adjacent review validation and `pml review`.

The future read-only web explorer is an approved but unimplemented compiled-model
consumer.

## Development installation

Contributors can use an isolated environment for development and tests; a global
installation is not required:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

To make the CLI from this checkout available as `pml` on your `PATH`, first
configure uv's tool directory (once) and restart your shell:

```bash
uv tool update-shell
```

Then run:

```bash
./dev-install.sh
```

The script runs `uv tool install --editable . --force`. This is an editable
development installation of this repository, not an installation of a published
PML release.

## Validate a manifest

```bash
.venv/bin/pml validate pml.yaml
```

Compile a validated definition to the canonical compiled JSON model with:

```bash
.venv/bin/pml compile pml.yaml --json
```

`pml compile` requires `--json`, writes the model to standard output, and does
not write project state.

Explain one canonical compiled-model ID with:

```bash
.venv/bin/pml explain pml.yaml <canonical-id>
```

`pml explain` is a read-only human-readable view of the validated compiled model;
it does not load or modify bindings, probes, locks, evidence, or generated state.

Write the complete explicit graph as deterministic Graphviz DOT bytes with:

```bash
.venv/bin/pml graph pml.yaml
```

`pml graph` is read-only and emits only producer-completion-to-signal,
signal-to-consumer-trigger, `related_to`, and use-case membership edges.

Review every unresolved feature, behavior, and stable obligation interactively with:

```bash
pml review path/to/definition
```

The review command records digest-bound human decisions in the adjacent
owner-controlled `reviews.yaml`. It can approve, reject with a reason, skip, or open
the contributing source in `VISUAL`/`EDITOR` for a manual change. It never approves
edited content automatically. Use `--origin human` or `--origin agent` to set the
authoring origin for existing content whose provenance has not yet been recorded.

Initialize PML from an implementing product repository with:

```bash
pml init --id sample_product --name "Sample Product"
```

This creates the deterministic sibling PML source, product-local `.pml/`, and the
repository-scoped PML agent skill at `.agents/skills/pml/`. The source location is
not configurable. The generated definition is intentionally incomplete until its
owner authors product intent.

`pml validate` accepts a single file or a directory. A directory is one modular
definition with path-derived mounting: each `*.pml.yaml` file's relative path is its
mount point in the document tree (`domains/billing/features/checkout.pml.yaml`
defines `domains.billing.features.checkout`), and `index.pml.yaml` mounts at its
directory itself. Fragments contain only their body. Defining the same field in two
fragments is a `conflict` diagnostic. Behaviors are direct children of features and
do not nest.

Closed schemas prevent ad hoc sections. Product registries and behavioral maps have
explicit size and shape constraints.

Validation covers restricted YAML, exact structure, references, forbidden vocabulary,
and controlled normative language. Product verification is a separate agent workflow;
see [`docs/verification.md`](docs/verification.md).

## Product-local state

Approved definitions remain in an owner-controlled PML repository. An implementing
product repository carries `.pml/pml.lock` and one state file per feature or
behavior under `.pml/state/`. The owner-controlled source identified by
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
- [Behavior transition model](docs/specs/0010-behavior-transition-model.md) — approved transition grammar and migration guidance.
- [Canonical compiled semantic model](docs/specs/0011-compiled-semantic-model.md) — approved version 2 derived model and JSON contract.
- [Bare behavior reference normalization](docs/specs/0013-bare-behavior-reference-normalization.md) — approved same-feature reference and digest canonicalization rules.
- [Human review workflow](docs/specs/0012-human-review-workflow.md) — digest-bound review metadata and interactive review.

Examples:

- [Minimal valid manifest](examples/minimal.pml.yaml)
- [Architecture decisions](examples/architecture-decisions.pml.yaml) and [invalid architecture](examples/architecture-invalid.pml.yaml)
- [Richer Assistant creation manifest](examples/assistant-creation.pml.yaml)
- [Invalid manifest](examples/invalid.pml.yaml) with expected diagnostics
- [Verification report](examples/verification-report.yaml)
- [Probe definition](examples/assistant-persistence.probe.yaml)
- [Owner-controlled bindings](examples/bindings.yaml)
- [Owner review metadata](examples/reviewed-product/reviews.yaml)
- [Invalid review schema](examples/invalid-reviews-schema.yaml) and [unresolved review target](examples/reviewed-product-invalid/reviews.yaml)
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
