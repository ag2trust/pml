# PML handoff

Updated: 2026-09-10

## Current implementation status

The owner-approved behavior transition model in
[`docs/specs/0010-behavior-transition-model.md`](docs/specs/0010-behavior-transition-model.md)
is implemented across the schema, semantic validation, conformance examples,
obligation resolution, bindings, probes, state consumers, and authoring
documentation.

The owner-approved version 1 compiled semantic model in
[`docs/specs/0011-compiled-semantic-model.md`](docs/specs/0011-compiled-semantic-model.md)
is implemented through canonical serialization and `pml compile --json`.

`pml explain`, `pml graph`, and the future read-only web explorer described in
0011 are approved but remain unimplemented consumers of the compiled model.

## Approval boundary

- [0007 project workflow](docs/specs/0007-project-workflow.md) is Owner approved.
- [0008 command execution semantics](docs/specs/0008-command-execution-semantics.md)
  is Proposed. It is not authorization to implement its detailed `lock`, `sync`,
  `verify`, execution-environment, or probe-execution semantics.
- [0010 behavior transition model](docs/specs/0010-behavior-transition-model.md)
  and [0011 canonical compiled semantic model](docs/specs/0011-compiled-semantic-model.md)
  are Owner approved.

Approved PML definitions remain authoritative. Generated state and evidence do not
alter an approved definition.

## Repository state

- The checked-out history includes PR #41, which preserves concurrent generated
  state during report ingestion.
- `pml compile --json` is the implemented compiled-model inspection command.
- Do not represent the unimplemented consumers as available commands.
