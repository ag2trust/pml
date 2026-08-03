# PML 0.1 project workflow

Status: Owner approved
Approved direction: 2026-08-02

This decision defines the low-friction workflow from installing PML through
initialization, authored policy, generated state, deterministic verification, and
external evidence ingestion. It does not add product-language keywords.

## Authority and artifact layout

Safety comes from artifact separation, not from a tooling approval ceremony.

The owner-controlled PML source contains authored product intent, verification
policy, and separate review metadata:

```text
<project>-pml/
  *.pml.yaml
  bindings.yaml
  probes/**/*.probe.yaml
  reviews.yaml
```

The implementing product contains only the content lock and generated evidence
ledger:

```text
<project>/.pml/
  pml.lock
  state/**
  architecture/**
```

Review metadata remains separate from the normative definition. For a feature,
component, or obligation, the optional `reviews.yaml` declares an authoring origin
of agent or human and records whether its current content is pending, approved, or
rejected. The origin is repository-controlled metadata, not a claim that PML
independently verifies. An absent review record is treated as pending. Each review
target is a feature, component, or obligation ID and must resolve in the validated
definition; an unknown target rejects the review metadata.

An approval is bound to the digest of the reviewed target. When that content
changes, the prior approval becomes stale and the target is treated as pending
until reviewed again. Ordinary validation permits pending targets; an explicit
strict check may require every reviewable target to have a current approval.

PML trusts review metadata because the owner-controlled PML repository and its
merge policy are the approval boundary; it does not attempt to cryptographically
prove that a reviewer is human. Creating a lock means only that the product pins
the exact current authored artifacts. The lock records a review digest separately
from definition and bindings digests so review changes do not masquerade as product
intent changes.

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

Discovery is a bounded tooling operation, not a filename convention or a product
language construct. Before parsing probe content, tooling MUST visit no more than
256 source-tree entries, accept no more than 64 regular probe files, and reject a
probe file larger than 1 MiB. It MUST reject rather than follow symbolic links.
Each accepted probe has at most 64 steps. A verification invocation executes no
more than 64 bound probes, no more than 64 steps per probe, and has a 15-minute
total wall-clock budget; a step has a 60-second wall-clock budget and at most 1 MiB
of captured output. Reaching any limit rejects the operation without treating
unvisited probes or incomplete execution as passing evidence. These limits bound
tooling resources only; bindings remain the owner-approved policy that selects
which probe IDs cover which obligations.

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

This decision supersedes the earlier statements in
[0003](0003-product-state.md#sync-and-ci) and
[0004](0004-language-normalization.md#verification-boundary) that sync runs probes.
`pml sync` MUST NOT execute probes, manufacture evidence, infer implementation
progress, rewrite evidence fingerprints to make old evidence current, or alter the
definition or bindings. Deterministic execution belongs only to `pml verify`.

## Deterministic verification

From a locked product repository, `pml verify` runs deterministic probes only. It:

1. resolves and validates the locked definition, bindings, and probe definitions;
2. independently discovers probe definitions under the locked source root, then
   selects every bound deterministic probe subject to the discovery and execution
   limits above;
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

One report may cover one obligation, several features or components, or an entire
project that fits the limits below. It uses flat lists of fully qualified obligation
IDs rather than duplicating the PML hierarchy. A report is bounded before parsing:
its UTF-8 representation is at most 1 MiB, it contains at most 64 declared targets,
64 implementation assessments, and 256 checks, and each text field is at most 4,096
Unicode code points. It may contain either or both of:

- `implementation` assessments with `target`, `status`, and `observation`; and
- verification `checks` using an approved evidence method.

The report format is a closed map. The following is its canonical field grammar;
future schema and semantic-validator work MUST implement this grammar before this
workflow is implemented:

```text
identifier        = [a-z][a-z0-9_]*
digest            = "sha256:" followed by 64 lowercase hexadecimal digits
recorded-time     = RFC 3339 UTC timestamp ending in "Z"
text              = non-empty Unicode scalar string, at most 4,096 code points
scope-id          = a resolved product node or architecture decision ID
obligation-id     = a resolved fully qualified product or architecture obligation ID

report            = {
  verification: identifier, version: text, recorded: recorded-time,
  environment: isolated | local_integrated | staging | production,
  verifier: {agent: text, provider: text, model: text,
             effort: low | medium | high},
  targets: unique non-empty list[scope-id],
  verdict: verified | failed | incomplete | blocked,
  implementation?: list[implementation-assessment],
  checks?: list[verification-check], limitations: list[text]
}
implementation-assessment = {
  target: obligation-id,
  status: implemented | partial | missing | unknown,
  observation: text
}
verification-check = deterministic-check | agent-judgment-check | human-attestation-check
common-check       = {target: obligation-id,
                      result: passed | failed | blocked | not_evaluated,
                      observation: text}
deterministic-check = common-check + {method: deterministic_probe,
                                      probe: identifier,
                                      evidence?: unique list[text]}
agent-judgment-check = common-check + {method: agent_judgment,
                                       reproduction: non-empty list[text] of at most 32 items}
human-attestation-check = common-check + {method: human_attestation,
                                          attester: text}
```

At least one of `implementation` or `checks` is non-empty. The resolved node of each
assessment or check obligation MUST occur in `targets`; duplicate
`(target, method, probe)` deterministic checks, duplicate `(target, method)` agent
or human checks, and duplicate implementation targets are invalid. This preserves
independent results for multiple approved deterministic probes on one obligation
without allowing a later entry to overwrite the same evidence lane. A deterministic
`probe` MUST be an approved probe ID for the check's target. Unknown fields,
targets, methods, statuses, and enum values are invalid.

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

Every accepted implementation assessment and evidence record retains its evidence
origin and the exact report representation from which it came. `verification` is
the canonical report ID. The canonical report digest is the `digest` production
above computed over the schema- and semantics-valid report encoded as UTF-8 JSON
with object keys sorted lexicographically, array order preserved, non-ASCII
characters encoded directly, and no insignificant whitespace. A producer-supplied
digest is not trusted or accepted as a substitute for this computed digest.

Generated state stores the common report ID, computed report digest, recorded time,
result, observation, and verifier fields. It additionally stores method-specific
origin: agent judgment retains replayable reproduction steps, human attestation
retains its accountable attester, and deterministic evidence retains the approved
probe ID and fingerprint. Sync produces no reports or evidence.

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

## Delivery boundary

This is a design decision only. It adds no schema, semantic-validator, formatter,
compiler, or CLI implementation. Those changes follow the repository development
workflow after the workflow semantics are accepted.
