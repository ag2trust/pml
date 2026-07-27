# Product verification protocol

PML resolves rules, reactions, and use cases into stable obligations. The approved
product definition states behavior; product-local bindings assign verification
coverage; generated state records evidence and derived confidence.

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
and are validated before state is updated.
