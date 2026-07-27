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

Verification bindings and generated state live with the implementing product, not
inside this definition.
