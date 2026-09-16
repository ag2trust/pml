# Product verification protocol

PML resolves rules, behavior transitions, and use cases into stable obligations. The approved
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
attestation. When an obligation has a verification plan, its configured coverage
must total `1.0`. An obligation without a plan has zero coverage and derives
`UNBOUND` status.

## Derived status

`pml status` derives an obligation signal from its approved plan and current
evidence. In precedence order, the signals are `FAILED`, `BLOCKED`, `VERIFIED`,
`PARTIAL`, `STALE`, `UNVERIFIED`, and `UNBOUND`. `UNBOUND` means no probes, agent
judgment, or human attestation is configured for that obligation. `UNVERIFIED`
means a plan is configured but it has no current evidence. Both have zero verified
coverage, but only the latter has a verification method awaiting evidence.

Each obligation row includes a compact plan summary such as
`plan=probes:2 agent:0.5 human:0`; probe counts are the number of configured
deterministic probes and agent and human values are their configured coverage. The
final status line reports the count of every signal, including `UNBOUND` separately.

## Deterministic probe eligibility

The following classification applies to the `verifies` target of every
deterministic probe and to any bindings plan that configures `probes`. A `partial`
kind remains probe-eligible, but a complete probe requires the supported setup
needed to establish its preconditions.

| Obligation kind | Probe-eligible | Reason |
| --- | --- | --- |
| Rule | yes | A probe can exercise and observe an individual rule. |
| Behavior trigger or trigger alternative | yes | A probe can establish a specific triggering event. |
| Behavior outcome or outcome alternative | yes | A probe can exercise and observe a specific result. |
| Behavior failure | yes | A probe can induce and observe a specified failure result. |
| Behavior conditions | partial | Establishing the conditions requires `setup`; setup support is defined separately. |
| Behavior completion exclusivity | no | A finite step sequence cannot prove that every alternative completion is exclusive. |
| Use-case goal | no | A use-case goal spans one or more behaviors and is not proved by one deterministic sequence. |
| Architecture constraint | yes | A probe can exercise and observe an individual constraint. |

Ineligible targets fail validation with `PML-E-PROBE-INELIGIBLE`.

A current passing probe contributes only its assigned coverage. Agent judgment must
include an observation and reproduction steps. Human evidence identifies the
attester. Reading implementation may guide verification but never proves behavior.

Changes to a node or a `related_to` node make its evidence stale. `pml sync`
reconciles generated state but never executes probes or refreshes evidence.
Deterministic probes run through `pml verify`; agent and human evidence require
explicit re-verification and report ingestion.

Architecture constraints use the same optional-plan coverage and evidence rules:
each configured plan totals `1.0`, while no plan derives `UNBOUND` with zero
coverage. Their bindings, state, and derived status are separate from product
conformance. Architecture evidence cannot establish product behavior, and product
evidence cannot establish an architecture decision.

A probe may declare an optional `setup` array of steps that runs before `steps`.
Setup expectations are asserted and captured values are visible to `steps`. A
failing setup step marks the probe result `inconclusive` rather than `failed`:
inconclusive results contribute no coverage and do not invalidate prior evidence
for the obligation. Only `steps` produce `passed` or `failed` outcomes.

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
