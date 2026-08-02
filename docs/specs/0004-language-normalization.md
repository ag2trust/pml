# PML 0.1 language normalization

Status: Owner approved
Approved direction: 2026-07-27
Artifact boundary superseded by [0005](0005-bindings-boundary.md)
Sync execution behavior superseded by [0007](0007-project-workflow.md)

This decision records the canonical language model agreed during the PML reference
review. It supersedes conflicting grammar in earlier draft documents.

## Canonical hierarchy

```text
Project → Domain → Feature → Component
```

Components are direct, non-nested parts of features. They may relate to features or
other components through `related_to`.

## Removed constructs

- Feature `inputs` and `outputs`
- `uses` and `depends_on`
- `consumes`
- `acceptance`
- `security`
- `owns` and concept `owned_by`
- `updates`, `displays`, `protects`, and `blocks`
- Experience `actions` and surface `purpose`
- `operations`
- Nested components
- Top-level `policies`
- `imports` until composition semantics exist
- Rule `severity`
- Inline verification requirements

## Renamed or normalized constructs

- `events` became product-level `signals`.
- `produces` became `emits`.
- Reactions use `on` plus one normative `statement`.
- `uses` and `depends_on` became one untyped, symmetric `related_to` path list.
- Actor definitions use one `meaning`.
- Concepts use one `meaning`; `lifecycle` became unordered `states`.
- Project-wide policies use the canonical `rules` term.

## Verification boundary

An obligation is a resolved tooling concept, not an authored section. Rules,
reactions, and use-case outcomes produce stable obligation paths. Approved product
definitions contain behavior only. Owner-controlled bindings stored beside the
definition define verification methods and coverage; their implementation paths
remain relative to the implementing product repository. Generated state remains
product-local and records evidence, scores, and freshness.

Changes to a node or a related node invalidate affected confidence. Sync reconciles
generated state without executing verification. The separate `pml verify` operation
may restore approved deterministic coverage by running probes; neither operation can
manufacture agent-judgment or human-attestation evidence.

## Architecture boundary

Architecture is an optional flat registry of independently owner-mandated technical
decisions. Features and components reference those decisions bottom-up. Architecture
does not duplicate behavioral outcomes and technology existence is never conformance
evidence.

Architecture decisions have the canonical fields `category`, `selection`,
`rationale`, and optional ID-keyed `constraints`. Categories are closed. Constraints
resolve into architecture-only obligations and use external verification bindings and
generated evidence independently of product obligations. Unreferenced decisions are
invalid; `applies_to`, `supports`, inline decisions, and recursive decisions do not
exist in the language.
