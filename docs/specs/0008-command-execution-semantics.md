# PML command execution semantics

Status: Proposed

## Purpose

This specification closes implementation gaps in the project workflow defined by
[0007](0007-project-workflow.md). It does not add product-language keywords or
permit generated state to alter approved product intent. Where this specification
is approved, its more specific command semantics supersede the corresponding
underspecified statements in 0007.

## Initialization

`pml init --id <id> --name <name> [--source <path>]` runs from the implementing
product repository. The default source is the sibling `<product-directory>-pml`.
The command creates:

- source `pml.yaml` containing fixed language version `0.1-draft`, the project ID, and
  project name, while deliberately omitting normative purpose and domain content;
- source `bindings.yaml` with an empty bindings map;
- source `probes/`; and
- product-local `.pml/`.

The definition boilerplate is intentionally incomplete and MUST fail ordinary PML
validation until its owner supplies product intent. Initialization MUST NOT invent
placeholder intent merely to satisfy the definition schema. It creates no state,
environment configuration, review metadata, or lock.

Before writing, initialization checks that neither the selected source nor product
`.pml/` exists. A collision rejects the operation without merging or overwriting.
The command prepares temporary sibling paths and renames them into place only after
all boilerplate is ready. A runtime failure triggers best-effort cleanup; PML does
not claim transactional crash atomicity across filesystems.

## Lock creation and source identity

The first `pml lock <source>` validates the definition, adjacent bindings, bound
probe definitions, and execution environments before writing product
`.pml/pml.lock`. Later `pml lock` invocations reuse the recorded source. The source
argument and authored files traversed beneath it MUST be regular paths rather than
symbolic links. The lock records a normalized path relative to the product
repository, including `..` segments needed for a sibling source.

When the source belongs to a Git worktree, locking requires every file participating
in the lock operation to contain no tracked modifications and no untracked files.
That set is exactly the definition file or mounted definition fragments, adjacent
`bindings.yaml`, discovered probe definitions, optional `environments.yaml`, and
optional `reviews.yaml`. Unrelated files elsewhere in the worktree, including
adjacent specifications and handoffs, do not block locking. The lock records the
source commit. A non-Git source is permitted and omits `definition.revision`;
revision is descriptive and content digests remain authoritative.

Lock replacement is atomic for the lock file. A failed validation leaves any prior
lock unchanged. The lock independently pins definition and bindings digests.
Environment configuration is pinned separately as specified below when present.

## Generated-state reconciliation

`pml sync` resolves and validates the locked definition and bindings and validates
all existing product and architecture state before making changes. It does not
require, discover, validate, or execute probes. It computes the complete desired
state reconciliation before writing.

Every accepted implementation and evidence record stores the canonical fingerprint
of its target node or architecture decision, bindings digest,
implementation-input fingerprint, and relationship fingerprints under which it was
recorded. It does not store the whole-definition lock digest, so an unrelated node
change does not make the record stale. Deterministic evidence additionally stores
its probe ID, probe fingerprint, and execution-environment digest. Sync copies
these record-level fingerprints unchanged; it MUST NOT rewrite them to make
evidence current. A record is current only when every stored fingerprint matches
the corresponding locked or computed value.

Sync retains a stale record when its obligation and evidence lane still resolve.
It clears a record only when its evidence method or deterministic probe is no
longer allowed by current bindings. It warns for each cleared lane.

State scopes and obligation entries absent from the locked definition are removed.
Removing a whole state file emits one warning only; otherwise each removed
obligation emits one warning, without additional warnings for records nested under
that removal. Other missing scopes and obligations are created with `implemented:
unknown` and no evidence. Warnings do not make a successful sync fail.

All replacement documents are schema- and semantics-valid before mutation begins.
Each file is installed with an atomic replacement and obsolete files are removed
after replacements are ready. This prevents partial validation writes but is not a
multi-file transaction across a process or machine crash. A later sync converges a
partially installed valid reconciliation.

`pml check` remains read-only. Missing generated state is an error instructing the
user to run `pml sync`.

## Execution environments

Execution settings are non-normative, owner-controlled metadata in an optional
adjacent `environments.yaml`. They are separate from definitions, bindings, probes,
reviews, and generated state. The closed authored shape is:

```text
host-variable        = [A-Z_][A-Z0-9_]*
http-header          = an RFC 9110 field-name token
absolute-http-url    = absolute http or https URL with a host and without
                       user information, query, or fragment
environment-reference = {from_environment: host-variable}
actor-execution = {
  http_headers?: map[http-header, environment-reference],
  cli_environment?: map[identifier, environment-reference]
}
cli-executable = {path: safe-product-relative-path}
execution-environment = {
  report_environment: isolated | local_integrated | staging | production,
  http?: {base_url: absolute-http-url, follow_redirects?: boolean},
  cli?: {executables: map[identifier, cli-executable]},
  actors?: map[actor-id, actor-execution]
}
environments-document = {
  pml_environments: "0.1",
  environments: non-empty map[identifier, execution-environment]
}
```

Secret values are never authored. Header and process-environment values are read
from the named host environment variables at invocation time, redacted from output,
and never stored in reports or state. Probe `env` and `as` values MUST resolve to a
configured execution environment and a definition actor respectively. Configuration
needed by a selected step must exist before any probe runs.

Locking discovers and validates every bound probe before writing. It rejects a
missing bound probe, invalid probe, unresolved probe environment or actor, invalid
environment document, or environment configuration missing capabilities required
by a selected step. An environment digest is independently recorded in the lock.
It participates in deterministic evidence freshness because changing destinations,
executable resolution, credential-variable references, or redirect behavior changes
what a probe executes. If no bound deterministic probes exist, `environments.yaml`
may be absent and the lock omits its environment digest.

Runtime secret values do not participate in a stored fingerprint: PML neither
stores them nor stores a reversible or brute-forceable derivative. Rotating a value
without changing its configured variable reference does not automatically stale
evidence; the operator explicitly reruns verification when credential rotation can
change observable behavior.

Configured CLI executables resolve to regular, executable files inside the
implementing product repository. Every executable path component MUST be
non-symbolic. The first authored CLI argument is the configured executable ID, not
an arbitrary `PATH` lookup. Fixture paths resolve inside the PML source root and
MUST remain contained there after filesystem resolution; fixtures and their path
components MUST NOT be symbolic links.

## Probe execution

`pml verify` validates every required artifact before execution, then runs all bound
deterministic probes sequentially in probe-ID order. Steps within a probe execute in
authored order. Captures, cookies, and HTTP session state are isolated to one probe;
`session: reset` clears that probe's HTTP cookies and session state.

An invocation with no bound deterministic probes fails before execution, emits no
report, and makes no state change. It MUST NOT derive a vacuous verified verdict.

CLI argument arrays execute directly from the product root without a shell. HTTP
steps use the selected environment's base URL and actor headers. Requests have no
automatic retry. Redirects are followed only when enabled by the environment and
MUST remain on the base URL's origin; a cross-origin redirect is blocked.
`body_from` loads JSON from an owner fixture and sends JSON after variable
substitution.

`body_has` requires a JSON response object with the named top-level keys.
`body_matches_fixture: file.json#field` compares the complete response JSON with
the named top-level fixture value; without a fragment it compares with the complete
fixture. Object key order is insignificant.

`capture: {value: body.field}` reads a scalar top-level response field.
`capture: {value: stdout.field}` reads a scalar top-level field from JSON emitted
by a CLI step. Undefined fields, non-scalar captures, and reassignment of a captured
name fail the probe.

`${name}` substitution is allowed only in HTTP paths, CLI arguments after the
executable ID, and scalar/string values in request-body fixtures. It is not shell
expansion and is forbidden in executable IDs, fixture paths, expectations,
environment or actor IDs, and capture expressions. An undefined variable fails the
probe.

Before execution, an unreadable or malformed fixture, invalid executable, missing
host variable, or other invalid configuration rejects the operation. During
execution, an omitted `within` uses 60 seconds. A shorter authored timeout that
expires is a failed probe result. An expectation mismatch, nonmatching CLI exit,
malformed JSON where structured output is expected, missing capture, or invalid
capture value is also failed. Failure to connect, interruption before a complete
HTTP response, or inability to start a prevalidated executable is blocked. A step
failure or block stops that probe; independent probes continue. Tool-generated
reports do not emit `not_evaluated`; that result remains available to external
reports.

The 60-second hard step ceiling, 1 MiB captured-output ceiling, and 15-minute
invocation ceiling are safety limits rather than ordinary probe results. Exceeding
one rejects the entire verification operation and ingests no partial report.
Truncated output is never evaluated as passing.

## Tool-generated reports

The report verifier is a closed union:

```text
agent-verifier = {agent: text, provider: text, model: text,
                  effort: low | medium | high}
tool-verifier  = {tool: "pml", version: text}
```

External agent reports use `agent-verifier`; `pml verify` uses `tool-verifier`.
The generated report environment is copied from the selected execution environment.
One verification invocation MUST NOT mix probes whose configured report environments
differ.

After probe execution and before ingestion, the report `version` is the implementing
product Git commit with `+dirty` when tracked or untracked product files outside
`.pml/` differ, or `unversioned` outside Git. Generated `.pml/` changes do not mark
the product version dirty. A generated report ID has the form
`pml_verify_<utc-basic-time>_<random-suffix>`, using only lowercase identifier
characters. Its recorded time is the invocation completion time.

Probe results derive the report verdict exactly:

- any `failed` result produces `failed`;
- otherwise, all `passed` results produce `verified`;
- otherwise, all `blocked` results produce `blocked`; and
- every other mixture of `passed`, `blocked`, and `not_evaluated` produces
  `incomplete`. (`not_evaluated` applies only when deriving a verdict for an
  externally supplied report.)

PML constructs observations from step outcomes and redacts configured secrets. A
schema- and semantics-valid report is passed through the ordinary atomic ingestion
boundary even when its verdict is not verified. `pml verify` exits zero only for a
`verified` report; it exits nonzero after ingesting failed, blocked, or incomplete
evidence.

## Locked and compatibility forms

Locked product operations resolve `.pml/pml.lock` from the current working directory
and do not search parents. Existing explicit source and product arguments may remain
temporarily available. They MUST resolve to the same product and source recorded by
the lock, otherwise the operation fails. Accepted legacy forms emit a deprecation
warning and cannot override locked policy.

## Delivery boundary

This specification is a design proposal only. After owner approval, implementation
follows the required order: schemas and semantic validators, positive and negative
conformance examples, then command behavior. Review metadata remains a separate
artifact and implementation stream.
