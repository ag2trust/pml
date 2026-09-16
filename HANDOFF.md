# PML handoff

Updated: 2026-09-15

## Current implementation status

The owner-approved behavior transition model in
[`docs/specs/0010-behavior-transition-model.md`](docs/specs/0010-behavior-transition-model.md)
is implemented across the schema, semantic validation, conformance examples,
obligation resolution, bindings, probes, state consumers, and authoring
documentation.

The owner-approved version 3 compiled semantic model in
[`docs/specs/0011-compiled-semantic-model.md`](docs/specs/0011-compiled-semantic-model.md)
is implemented through canonical serialization and `pml compile --json`.

`pml explain` and `pml graph` are implemented read-only consumers of the compiled
model. The future read-only web explorer described in 0011 remains unimplemented.

The owner-approved human review workflow in
[`docs/specs/0012-human-review-workflow.md`](docs/specs/0012-human-review-workflow.md)
is implemented through the closed `reviews.yaml` schema, semantic validation,
digest-bound review targets, and interactive `pml review` command. Agent context
export and agent-harness execution remain deferred.

## Approval boundary

- [0007 project workflow](docs/specs/0007-project-workflow.md) is Owner approved.
- [0008 command execution semantics](docs/specs/0008-command-execution-semantics.md)
  is Proposed. It is not authorization to implement its detailed `lock`, `sync`,
  `verify`, execution-environment, or probe-execution semantics.
- [0010 behavior transition model](docs/specs/0010-behavior-transition-model.md)
  [0011 canonical compiled semantic model](docs/specs/0011-compiled-semantic-model.md),
  and [0012 human review workflow](docs/specs/0012-human-review-workflow.md) are
  Owner approved.

Approved PML definitions remain authoritative. Generated state and evidence do not
alter an approved definition.

## Repository state

- The checked-out history includes PR #41, which preserves concurrent generated
  state during report ingestion.
- `pml compile --json`, `pml explain`, and `pml graph` are implemented compiled-model
  inspection commands.
- `pml review` is implemented; `pml web` remains unavailable.
