# PML quickstart

PML describes required product behavior without describing its implementation.

## 1. Install the validator

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## 2. Create a manifest

Every manifest requires a language version, project, domain, and feature. A feature
requires inputs, outputs, rules, a use case, and acceptance conditions.

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
        actors:
          - member
        inputs:
          - Note content.
        outputs:
          - A durable Note.
        rules:
          preserve_content:
            statement: THE SYSTEM MUST preserve accepted Note content.
            severity: high
            verification: {requires: [deterministic_probe]}
        use_cases:
          create_note:
            actor: member
            goal: Record information for later use.
            given:
              - The Member is authorized.
            when:
              - The Member submits Note content.
            then:
              - The Note is available in a later session.
            otherwise:
              - The Member receives an actionable explanation.
            verification: {requires: [deterministic_probe, agent_judgment]}
        acceptance:
          note_is_available_later:
            statement: The Member MUST be able to access the accepted Note in a later session.
            verification: {requires: [deterministic_probe]}
```

## 3. Validate it

```bash
.venv/bin/pml validate my-product.pml.yaml
```

A valid definition prints:

```text
PML VALID: my-product.pml.yaml
```

An invalid definition identifies the location and violation. The validator never
silently changes product intent.

## 4. Add detail only where it clarifies the contract

Use vocabulary for important terms, concepts for meaningful entities, events and
reactions for cross-feature effects, experience for observable UI expectations, and
recursive components for finer semantic detail.

Do not add implementation details merely because they are known. A conforming rebuild
may use different technology while preserving the same behavior and constraints.

## 5. Use PML during delivery

```text
Author and approve PML
  -> derive specification and plan
  -> implement
  -> review code
  -> verify the product against affected PML IDs
  -> record evidence and verdict
```

See [verification.md](verification.md) for the verifier-agent contract.
