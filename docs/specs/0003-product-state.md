# PML 0.1 product state

Status: Approved, normalized by [0004](0004-language-normalization.md); repository
boundary superseded by [0005](0005-bindings-boundary.md); sync execution behavior
superseded by [0007](0007-project-workflow.md)

## Repository boundary

The approved definition remains owner controlled. Each implementing repository owns:

```text
.pml/
  pml.lock
  bindings.yaml
  state/**
```

The lock pins the approved definition. Bindings map nodes to implementation paths
and obligations to approved verification coverage. State records implementation
claims and evidence; it cannot redefine behavior or coverage.

## Stable obligations

Rules, reactions, and use cases compile into independently addressable obligation
paths such as:

```text
domains.billing.features.purchase.rules.credits_added
```

Obligation is a tooling concept, not a PML section.

## Freshness and relationships

Evidence records a fingerprint of its node's current bound implementation inputs.
State also records fingerprints for every node connected through symmetric
`related_to` edges. A direct or related fingerprint mismatch makes prior evidence
stale.

Freshness is derived from content, never trusted from a timestamp, commit claim, or
stored freshness flag.

## Confidence

Each obligation's approved verification coverage totals `1.0`. Current passing
evidence contributes its configured portion:

- no current evidence: `UNVERIFIED` or `STALE`, 0%;
- some current passing coverage: `PARTIAL`;
- all coverage current and passing: `VERIFIED`, 100%;
- any current required check failed: `FAILED`;
- current verification prevented: `BLOCKED`.

Confidence is derived and displayed; it is not freely authored in state.
Implementation progress remains a separate dimension.

## Sync and CI

`pml sync` recalculates changed and related nodes, reconciles generated state, and
keeps changed evidence stale. It does not execute probes. Deterministic execution is
the separate `pml verify` operation defined by [0007](0007-project-workflow.md).

CI recomputes definition, input, related-node, and probe fingerprints. A mismatch
proves committed state does not cover current inputs, so CI can enforce that sync
has processed the latest change without trusting a mutable “synced” flag.

## Architecture conformance

Architecture constraints use the same plan and evidence requirements but do not
share product binding entries or state. Their owner-controlled bindings are keyed by
decision ID under the `architecture` map, generated state is
`.pml/architecture/<decision>.state.yaml`, and `pml architecture-status` derives
their status independently. Neither evidence kind can prove the other conformance
dimension.
