# Product verification protocol

PML resolves rules, reactions, and use cases into stable obligations. The approved
product definition states behavior; owner-controlled bindings assign verification
coverage; product-local generated state records evidence and derived confidence.

The owner source contains the definition and `bindings.yaml`. The implementing
product contains `.pml/pml.lock` and `.pml/state/**`; it does not own a bindings
override. Tooling resolves bindings from `definition.source` in the lock, validates
their closed schema and all node and obligation references, then checks their
independent digest before validation, status, probe evidence checks, or report
ingestion. A missing or mismatched definition or bindings digest makes current
status unavailable.

The resolved `definition.source` must also be the exact definition file or modular
directory passed to the product-state command. A product-controlled copy with the
same definition content cannot redirect bindings lookup to a different policy.

Each generated node state also records the approved `bindings_digest`. When an
owner changes bindings and updates the lock, evidence in state carrying the prior
digest is stale until that state is reconciled. This prevents old evidence from
being reweighted under a new coverage policy.

When report ingestion reconciles a touched node to a new definition or bindings
digest, it clears that node's prior evidence before recording the report. A partial
report therefore cannot make untouched evidence current under the new policy.

Bindings paths retain their product meaning after this separation: `src/notes`
means `<implementing-product>/src/notes`, not a path under the owner source. Unsafe
paths and paths that resolve outside the product repository remain invalid.

Verification methods are deterministic probes, agent judgment, and human
attestation. Their configured coverage for each obligation must total `1.0`.

A current passing probe contributes only its assigned coverage. Agent judgment must
include an observation and reproduction steps. Human evidence identifies the
attester. Reading implementation may guide verification but never proves behavior.

Changes to a node or a `related_to` node make its evidence stale. `pml sync`
reconciles generated state but never executes probes or refreshes evidence.
Deterministic probes run through `pml verify`; agent and human evidence require
explicit re-verification and report ingestion.

Architecture constraints use the same verification methods and coverage total, but
their bindings, state, and derived status are separate from product conformance.
Architecture evidence cannot establish product behavior, and product evidence cannot
establish an architecture decision.

Reports conform to
[`schema/verification-report.schema.json`](../schema/verification-report.schema.json)
and are validated before state is updated. Probe execution and state synchronization
remain separate tooling operations.

The following remains available for isolated validation of an explicit owner
bindings file:

```bash
pml validate-probes definition.pml.yaml probes/ \
  --bindings bindings.yaml --require-complete
```

Product-state commands never treat that option or a legacy `.pml/bindings.yaml` as
an override of the locked policy.
