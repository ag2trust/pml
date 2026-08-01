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

Each generated node state also records the approved `bindings_digest`. When an
owner changes bindings and updates the lock, evidence in state carrying the prior
digest is stale until that state is reconciled. This prevents old evidence from
being reweighted under a new coverage policy.

Bindings paths retain their product meaning after this separation: `src/notes`
means `<implementing-product>/src/notes`, not a path under the owner source. Unsafe
paths and paths that resolve outside the product repository remain invalid.

Verification methods are deterministic probes, agent judgment, and human
attestation. Their configured coverage for each obligation must total `1.0`.

A current passing probe contributes only its assigned coverage. Agent judgment must
include an observation and reproduction steps. Human evidence identifies the
attester. Reading implementation may guide verification but never proves behavior.

Changes to a node or a `related_to` node make its evidence stale. `pml sync` may
refresh deterministic probes; agent and human evidence require explicit
re-verification.

Reports conform to
[`schema/verification-report.schema.json`](../schema/verification-report.schema.json)
and are validated before state is updated. Executable sync remains a separate tooling
layer.

The following remains available for isolated validation of an explicit owner
bindings file:

```bash
pml validate-probes definition.pml.yaml probes/ \
  --bindings bindings.yaml --require-complete
```

Product-state commands never treat that option or a legacy `.pml/bindings.yaml` as
an override of the locked policy.
