# PML 0.1 Product State and Evidence Lanes

Status: Approved for implementation
Approved direction: 2026-07-22

## 1. Purpose

An approved PML definition states product intent. Each implementing product repository
keeps the implementation facts and verification evidence that apply to its own code.
Generated state never changes, weakens, or completes an approved definition.

## 2. Repository boundary

The approved definition remains in its owner-controlled repository. An implementing
repository contains only product-local metadata:

```text
.pml/
  pml.lock
  bindings.yaml
  state/**
```

`pml.lock` pins an immutable definition revision and digest. `bindings.yaml` maps
semantic node IDs to repository-relative implementation paths. `state/**` records
facts for one feature or component per file.

## 3. Obligations and evidence requirements

Every countable obligation has a stable ID. The countable sections are `rules`,
`use_cases`, `security`, `reactions`, and `acceptance`. Their entries are ID-keyed
objects, including entries that were lists in the initial language draft.

An obligation expresses one independently verifiable promise. When one statement
contains independently verifiable outcomes, authors split it into multiple
obligations instead of estimating partial probe coverage.

Every obligation declares the evidence lanes required for verification:

```yaml
verification:
  requires:
    - deterministic_probe
    - agent_judgment
```

Requirements are approved definition data. State files never redefine them. A
critical rule requires `deterministic_probe` or `human_attestation`; agent judgment
alone cannot satisfy it.

## 4. Evidence lanes

The evidence methods are `deterministic_probe`, `agent_judgment`, and
`human_attestation`. They are independent lanes, not additive confidence guesses.
If two lanes are required and one is current and passing, the obligation is one of
two lanes satisfied. Nobody authors a percentage.

Several approved probes may verify one obligation. Together they constitute one
deterministic lane; they do not increase its denominator weight. The lane is
satisfied only when every approved probe bound to it has current passing evidence.
One probe is sufficient only when its owner-approved binding says it verifies the
whole atomic obligation.

Agent-judgment evidence includes reproduction steps and an observation. Human
attestation identifies the attester and records an observation. Evidence results use
`passed`, `failed`, `blocked`, or `not_evaluated`.

## 5. Freshness

Evidence records a fingerprint of the relevant inputs, not the commit containing the
state file. The fingerprint covers the node's bound content, canonical approved node
definition, relevant dependency inputs, probe definition where applicable, and tool
or runner version. This avoids a self-referential state commit.

On read, current content matching the recorded fingerprint is `fresh`. A direct
input mismatch is `stale`. A changed `depends_on` node makes downstream evidence
`suspect`. Freshness is derived and never stored as a mutable flag.

## 6. Derived obligation signal

- `VERIFIED`: every required lane is fresh and passing.
- `PARTIAL`: at least one, but not every, required lane is fresh and passing.
- `FAILED`: any current required lane failed.
- `BLOCKED`: no required lane failed and required verification was blocked.
- `STALE`: prior required evidence exists, but none is current.
- `UNVERIFIED`: required evidence has never existed.

An obligation's displayed verification percentage is satisfied required lanes divided
by total required lanes. A node's verification progress is the same calculation over
all required obligation lanes. Failed, blocked, stale, and unevaluated lanes contribute
zero. The explicit signal always accompanies a percentage.

Implementation progress is separately derived from `implemented`, `partial`,
`missing`, and `unknown` facts. Verification failure does not silently rewrite an
implementation fact.

## 7. Commands and CI

`pml sync` recalculates affected nodes, traverses `depends_on`, runs approved probes,
and refreshes deterministic evidence. It carries other evidence forward without
claiming to refresh it. Explicit verification refreshes agent-judgment or human lanes.

CI recalculates relevant-input fingerprints. It does not trust timestamps, a stored
freshness flag, or a claim that sync ran. A mismatch proves that committed state does
not cover current relevant inputs. CI also validates the lock, bindings, obligation
IDs, state shape, definition hashes, evidence routing, and required probe results.

## 8. Implementation sequence

1. Make all obligations ID-addressable and declare evidence requirements.
2. Add lock, bindings, and state schemas plus semantic validation.
3. Add obligation and node enumeration.
4. Add read-only status and fingerprint checks.
5. Add probe execution and `pml sync`.
6. Add dependency propagation and unmatched-change reporting.
