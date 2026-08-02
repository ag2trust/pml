# PML 0.1 project workflow

Status: Owner approved
Approved direction: 2026-08-02

This decision defines the low-friction workflow from installing PML through
initialization, authored policy, generated state, deterministic verification, and
external evidence ingestion. It does not add product-language keywords.

## Authority and artifact layout

Safety comes from artifact separation, not from a tooling approval ceremony.

The owner-controlled PML source contains authored product intent and verification
policy:

```text
<project>-pml/
  *.pml.yaml
  bindings.yaml
  probes/**/*.probe.yaml
```

The implementing product contains only the content lock and generated evidence
ledger:

```text
<project>/.pml/
  pml.lock
  state/**
  architecture/**
```

PML does not define an `approve` command or an authored approval field. Review and
ownership remain repository concerns. Creating a lock means only that the product
pins the exact current authored artifacts.

## Installation

PML is distributed as an isolated Python CLI application. The documented install
path is `uv tool install product-manifest-language`, with `pipx install
product-manifest-language` as an equivalent supported path. Installing PML does not
add a runtime dependency to the implementing product.

## Initialization

`pml init` runs from the implementing product repository. It deterministically
creates:

- a sibling `<project>-pml` source with minimal definition and bindings
  boilerplate; and
- the product-local `.pml/` directory.

Initialization MUST NOT inspect implementation code, infer product intent, create
verification claims, create state, or create `pml.lock`. Agents and clients may fill
the authored definition, bindings, and probes after initialization. Generated
boilerplate remains unpinned until it validates and `pml lock` is run.

## Validation and locking

Before the first lock, `pml validate <pml-source>` validates an explicitly supplied
single definition file or modular source directory.

From the product repository, `pml lock <pml-source>`:

1. loads and validates the definition;
2. loads the adjacent `bindings.yaml` and validates its schema, references,
   coverage, and product-relative paths;
3. computes the independent canonical definition and bindings digests; and
4. writes `.pml/pml.lock` only when every validation succeeds.

The initial command records the PML source. Later `pml lock` invocations may reuse
that source without another path argument. The lock records the source Git revision
when available; revision is descriptive while the content digests are authoritative.

The lock is regenerated when the definition or bindings change. Product code,
evidence, and generated-state changes do not change the lock.

## Probe discovery

Bindings name deterministic probes and assign their coverage. Probe definitions are
discovered recursively from `probes/**/*.probe.yaml` under the lock-resolved PML
source root and indexed by their unique authored `probe` ID.

Probe filenames and directory structure have no semantic meaning. Validation MUST
reject duplicate probe IDs, missing bound probes, target mismatches, and unbound
probe evidence. A probe definition change changes its fingerprint and makes evidence
recorded against the prior definition stale.

## State synchronization

From a locked product repository, `pml sync`:

- validates the locked definition and bindings;
- enumerates every product and architecture state scope and obligation;
- creates missing generated state files;
- records current definition, bindings, implementation-input, and relationship
  fingerprints;
- initializes new obligations with `implemented: unknown` and no evidence;
- preserves evidence that remains current; and
- keeps changed evidence tied to the definition, bindings, probe, and input
  fingerprints under which it was recorded, or clears it when policy reconciliation
  cannot preserve that stale association.

`pml sync` MUST NOT execute probes, manufacture evidence, infer implementation
progress, rewrite evidence fingerprints to make old evidence current, or alter the
definition or bindings.

## Deterministic verification

From a locked product repository, `pml verify` runs deterministic probes only. It:

1. resolves and validates the locked definition, bindings, and probe definitions;
2. selects every deterministic probe required by the bindings;
3. executes its declared steps;
4. constructs the standard verification-report representation in memory;
5. passes that result through the same ingestion validation boundary used for
   external reports; and
6. updates generated state only when the result is valid.

PML MUST NOT start, select, configure, or provide an interface to an agent. Coverage
assigned to agent judgment or human attestation remains pending until an external
report is ingested.

## External reports

Developer-managed agents and human workflows produce verification reports outside
PML. `pml ingest-report <report>` is their only supported state mutation boundary;
external producers MUST NOT directly edit generated state.

One report may cover one obligation, several features or components, or the whole
project. It uses flat lists of fully qualified obligation IDs rather than duplicating
the PML hierarchy. A report may contain either or both of:

- `implementation` assessments with `target`, `status`, and `observation`; and
- verification `checks` using an approved evidence method.

Implementation assessment and verification evidence remain independent. An
implementation status never contributes verification coverage.

Accepted implementation assessments are generated state records, not bare mutable
status flags. State retains their status, observation, report ID and digest,
recorded time, and verifier identity so tooling can distinguish an external claim
from a derived verification result.

Ingestion validates the complete report before writing any state. Every target MUST
resolve in the locked definition, every evidence method MUST be allowed by the
locked bindings, deterministic evidence MUST identify the matching approved probe,
and required method-specific fields MUST be present. Any unknown target or other
invalid entry rejects the whole report without partial state updates. Behavior not
yet represented in PML requires a separate authored definition change.

## Evidence origin

Accepted agent-judgment evidence records who produced it and the exact report from
which it came. Generated state stores:

- the report ID and canonical report digest;
- recorded time;
- agent, provider, model, and effort;
- result and observation; and
- replayable reproduction steps.

The original report is not moved into `.pml/` or otherwise archived by PML. External
systems may retain it as an artifact keyed by its digest. State contains the durable
normalized evidence needed for status and replay.

## Locked command form

After the initial lock, commands run from the implementing product repository and
resolve the definition, bindings, and probes through `.pml/pml.lock`:

```text
pml lock
pml sync
pml verify
pml ingest-report <report>
pml check
pml status
pml architecture-status
```

Explicit source and product paths may remain available for isolated validation and
advanced tooling, but they MUST NOT override locked policy during product-state
operations.

`pml check` validates the locked artifacts and generated ledger. `pml status` and
`pml architecture-status` read state and derive their respective views; they do not
write evidence.
