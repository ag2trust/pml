# PML language normalization handoff

Updated: 2026-07-27

## Approved language model

The canonical hierarchy is:

```text
Project → Domain → Feature → Component
```

Components are direct, non-nested behavioral parts of features.

The canonical language decisions are recorded in
[`docs/specs/0004-language-normalization.md`](docs/specs/0004-language-normalization.md)
and applied to the language reference, schema, validator, examples, and tests.

Key decisions:

- Features have no generic inputs or outputs; components may have them.
- `related_to` replaces `uses` and `depends_on`. It is an untyped list of unique
  feature/component paths and is semantically symmetric.
- Product-level `signals` replace events. Nodes `emit` signals; reactions use `on`
  plus one atomic `statement`.
- `consumes`, `acceptance`, `security`, ownership fields, `updates`, `displays`,
  `protects`, `blocks`, `operations`, nested components, and inline verification
  mechanics were removed.
- `rules` is the one canonical normative container at project, domain, feature, and
  component scope.
- Actors and concepts define their own `meaning`; concept `lifecycle` became
  unordered `states`.
- Rule `severity` was removed.
- Surface actions and repetitive surface purposes were removed.
- `imports` remains outside 0.1 until composition semantics exist.
- Architecture is an optional flat registry referenced bottom-up by features and
  components. It is for independently owner-mandated choices, not product behavior
  or infrastructure detail.

## Obligation and verification model

“Obligation” is a compiler/tooling term, not an authored PML section. Rules,
reactions, and use cases resolve into stable obligation paths.

Verification is split into:

1. approved product definition: required behavior;
2. product-local bindings: implementation paths, methods, probe IDs, and coverage;
3. generated state: evidence and derived confidence/freshness.

Coverage for each obligation must total `1.0`. Current passing evidence contributes
its configured coverage. Changes to a node or either side of a `related_to` edge make
affected evidence stale. Sync may refresh probes but not agent or human evidence.

CI determines whether sync is current by recalculating fingerprints rather than
trusting timestamps or a stored “synced” flag.

## Implemented in the working tree

- Normalized language reference and normative specs.
- Strict schema for the approved grammar.
- Signal, architecture, relationship, actor, and reaction reference validation.
- Non-nested component validation.
- Project/domain/feature/component rule obligation enumeration.
- Product-local verification coverage schema and coverage-total validation.
- Symmetric related-node fingerprint freshness.
- Coverage-based derived verification status.
- Migrated valid and invalid examples.
- Positive and negative conformance tests.

## Remaining work

- Review whether individual use-case outcomes need stable sub-IDs or whether one
  use-case remains the atomic obligation.
- Define architecture-conformance evidence separately from behavioral obligation
  evidence.
- Implement executable `pml sync`; current code validates and ingests evidence but
  does not run probes.
- Reconcile and publish this semantic change as reviewable pull requests.
