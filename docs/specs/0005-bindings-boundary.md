# PML 0.1 bindings boundary

Status: Owner approved
Approved direction: 2026-07-31

This decision separates owner-approved verification policy from generated product
state. It supersedes the repository layout in
[0003](0003-product-state.md#repository-boundary).

## Artifact boundary

The owner-controlled PML source contains both the approved product definition and
its bindings:

```text
<project>-pml/
  *.pml.yaml
  bindings.yaml
```

The implementing product repository contains only the lock and generated state:

```text
<project>/.pml/
  pml.lock
  state/**
```

Bindings remain authored, reviewed policy. They map definition nodes to product
implementation paths and obligations to approved verification coverage. Generated
state MUST NOT modify or override them.

## Path resolution

Paths in `bindings.yaml` remain relative to the implementing product repository,
not to the directory containing the bindings file. Moving bindings therefore does
not change their meaning.

Tooling MUST receive or resolve the product repository root independently from the
owner-controlled PML source. Bound paths MUST retain the existing path-safety
rules.

## Lock

The product-local `pml.lock` identifies the approved PML source and independently
pins the definition and bindings:

```yaml
pml_lock: "0.1"
definition:
  source: ../notes-pml
  revision: approved-2026-07-31
  digest: sha256:<definition-digest>
bindings:
  digest: sha256:<bindings-digest>
```

`definition.source` locates the owner-controlled PML source from the implementing
product repository. `definition.revision` identifies the approved source revision.
The two digests are separate so tooling can report whether behavior or verification
policy changed.

The definition digest covers the canonical approved definition. The bindings
digest covers the canonical validated bindings. A missing or mismatched digest is
an error; tooling MUST NOT evaluate current confidence against unpinned behavior or
coverage policy.

The canonical bindings digest is `sha256:` plus the lowercase SHA-256 hexadecimal
digest of the schema- and semantics-valid document encoded as UTF-8 JSON. Object
keys are sorted lexicographically, array order is preserved, non-ASCII characters
are encoded directly, and no insignificant whitespace is emitted.

## State authority

State remains product-local because it records evidence about the current product
implementation. State may derive status and confidence only from the exact
definition and bindings pinned by the lock.

A bindings change does not rewrite approved behavior, but it changes what evidence
counts and how coverage is calculated. Existing evidence MUST NOT be presented as
current under changed bindings until the lock and derived state have been
reconciled.

## Tooling consequences

Validation, status, probe validation, report ingestion, and future sync behavior
MUST use the lock-resolved owner-controlled bindings rather than a product-local
`.pml/bindings.yaml`.

All bindings read paths MUST perform schema and semantic validation before using
paths or coverage. An explicit bindings path may remain available for isolated
validation, but it does not override the locked bindings during product-state
operations.
