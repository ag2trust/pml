# PML quickstart

PML describes required product behavior without describing implementation.

## Create a definition

```yaml
pml: "0.1-draft"

project:
  id: sample_product
  name: Sample Product
  purpose: Help a Member record durable Notes.

actors:
  member:
    meaning: A person authorized to use the product.

domains:
  notes:
    purpose: Allow Members to manage Notes.
    features:
      creation:
        purpose: Allow a Member to create a Note.
        actors: [member]
        rules:
          preserve_content:
            statement: THE SYSTEM MUST preserve accepted Note content.
        use_cases:
          create_note:
            actor: member
            goal: Record information for later use.
            given: [The Member is authorized.]
            when: [The Member submits Note content.]
            then: [The Note is available in a later session.]
            otherwise: [The Member receives an actionable explanation.]
```

Validate it with:

```bash
pml validate my-product.pml.yaml
```

Use components for direct behavioral parts of a feature, signals and reactions for
cross-node consequences, and architecture only for independently owner-mandated
technical choices. Components do not nest.

## Bind an implementation

Keep the approved definition and verification policy together in the
owner-controlled PML source. Keep only the lock and generated state in the
implementing product:

```text
sample-product-pml/          sample-product/
  sample.pml.yaml              .pml/
  bindings.yaml                  pml.lock
                                  state/**
```

`sample-product-pml/bindings.yaml` maps semantic nodes to product paths and assigns
verification coverage:

```yaml
pml_bindings: "0.1"
bindings:
  domains.notes.features.creation:
    paths: [src/notes]
    verification:
      domains.notes.features.creation.rules.preserve_content:
        probes: {preserve_content: 1.0}
      domains.notes.features.creation.use_cases.create_note:
        agent_judgment: 1.0
```

Paths are interpreted from `sample-product/`, even though the bindings file is in
`sample-product-pml/`. The product lock resolves that source and pins behavior and
verification policy independently:

```yaml
pml_lock: "0.1"
definition:
  source: ../sample-product-pml/sample.pml.yaml
  revision: approved-2026-07-31
  digest: sha256:<definition-digest>
bindings:
  digest: sha256:<bindings-digest>
```

Run `pml check sample-product-pml/sample.pml.yaml sample-product` to validate the
lock, owner bindings, and generated state before deriving current status.
