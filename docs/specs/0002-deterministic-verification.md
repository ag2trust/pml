# PML 0.1 deterministic verification

Status: Approved, normalized by [0004](0004-language-normalization.md)

## Purpose

Verification repeatedly evaluates resolved product obligations against current
implementation evidence. Implementation existence is never proof of conformance.

## Verification bindings

Product-local bindings map each semantic node to implementation paths and each
obligation to approved verification coverage:

```yaml
verification:
  domains.billing.features.purchase.rules.credits_added:
    probes:
      purchase_balance_probe: 0.6
    agent_judgment: 0.4
```

Coverage for one obligation must total exactly `1.0`. Probe, agent-judgment, and
human-attestation coverage are explicit. Coverage is approved verification metadata,
not part of the product definition and not a generated score.

## Deterministic probes

A probe is an approved executable verification definition bound to one obligation.
Its closed vocabulary may perform restricted HTTP, CLI, or session actions and
assert observable results. It does not allow arbitrary scripts, shell composition,
environment mutation, or code-level test references.

A current passing probe restores only its configured coverage. Several probes may
cover different portions of one obligation. Probe coverage does not substitute for
configured agent or human coverage.

## Agent and human evidence

Agent judgment records an observation and replayable reproduction steps. Human
attestation records an accountable attester and observation. Both are invalidated
by relevant changes and must be refreshed explicitly; `sync` cannot invent them.

## Results

Evidence results are `passed`, `failed`, `blocked`, or `not_evaluated`. Current
passing evidence contributes its configured coverage. Current failed evidence makes
the obligation failed even when other coverage passes.
