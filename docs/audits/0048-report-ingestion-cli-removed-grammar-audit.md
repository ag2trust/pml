# Report ingestion and CLI removed-grammar audit

Audit date: 2026-08-12  
Baseline: merge commits `a05a6eb` (PR #21) and `8da0345` (PR #22)

## Result

There are **no remaining implementation dependencies** in report ingestion or
CLI output on the PR #21 removed grammar: behavior `context`, `output`,
`emits`, `reactions`, and `architecture`; the top-level `signals` registry; or
use-case `given`, `when`, `then`, and `otherwise` scenario fields. There is
also no dependency on the old `.output` obligation paths. The generic
obligation consumers now resolve the approved transition paths:

- `<behavior>.conditions` when conditions are authored;
- `<behavior>.trigger` or `<behavior>.trigger.<alternative>`;
- `<behavior>.completion`;
- `<behavior>.outcome` and, for alternatives,
  `<behavior>.outcome.<alternative>`; and
- `<behavior>.failures.<failure>`.

This audit changes neither language semantics nor implementation.

## Actual defects

None found.

### Report ingestion

`ingest_report` constructs its accepted target map solely from
`enumerate_obligations` and `enumerate_architecture_obligations`
([`src/pml/ingest.py`](../../src/pml/ingest.py), lines 80-86). It rejects a
target not in that map for both implementation assessments (lines 100-122) and
verification checks (lines 123-175). Therefore an old
`<behavior>.output[.<alternative>]` target is an undefined reference, rather
than a compatibility path.

When reconciling state, the same function obtains the touched behavior's
current obligations with `enumerate_obligations(definition, node_id)` and
rebuilds the state map from that result (lines 195-240). No removed grammar key
or old obligation suffix appears in this ingestion path. The report schema keeps
`target` deliberately grammar-neutral
([`schema/verification-report.schema.json`](../../schema/verification-report.schema.json),
lines 85-100); semantic resolution remains in `ingest_report`, where it is
current.

### CLI outputs

The `obligations` command prints only the results of the same product and
architecture enumerators
([`src/pml/cli.py`](../../src/pml/cli.py), lines 250-265). The `status` command
delegates its per-node rows to `product_status` (lines 81-112), which enumerates
the node's current obligations without grammar-specific branching
([`src/pml/status.py`](../../src/pml/status.py), lines 147-190). The
`ingest-report` command delegates to the ingestion function above (lines
173-205). None formats or accepts any removed PR #21 grammar or an old
`.output` path.

Direct command verification produced the transition IDs for both
`examples/minimal.pml.yaml` and `examples/behavior-one-of-output.pml.yaml`; in
particular, the latter emitted `conditions`, both `trigger` alternatives,
`completion`, `outcome`, both outcome alternatives, and the failure path, with
no `.output` entries.

## Already-covered generic obligation consumers

The enumerator change from PR #22 is covered directly, rather than relying on
an old-output alias:

- [`tests/test_state.py`](../../tests/test_state.py), lines 96-109 asserts the
  current minimal transition paths.
- [`tests/test_state.py`](../../tests/test_state.py), lines 112-152 asserts
  exact direct and alternative transition paths, including completion and
  failures.
- [`tests/test_state.py`](../../tests/test_state.py), lines 155-195 proves
  those paths are accepted in owner bindings and rejects the old component node
  form.
- [`tests/test_behavior_transition_validation.py`](../../tests/test_behavior_transition_validation.py),
  lines 91-104 rejects removed behavior keys, including `output`, `reactions`,
  and `emits`.
- [`tests/test_ingest.py`](../../tests/test_ingest.py), lines 450-463 covers the
  CLI-to-ingestion success path. It uses a rule obligation, but that is the
  intentionally generic target consumer described above, not a remaining
  removed-grammar dependency.

The full suite passed: `198 passed` using
`uv run --with 'jsonschema>=4.21,<5' --with 'PyYAML>=6,<7' --with
'pytest>=8,<9' -- python -m pytest -q`.

## Test-coverage gap (not an implementation dependency)

There is no dedicated end-to-end report ingestion or `pml obligations` CLI test
whose report target is a behavior transition obligation. The existing exact
enumerator and generic ingestion/CLI tests establish the code path, but an
explicit transition-target integration test would make a later regression easier
to diagnose. This is not a defect in the current implementation and does not
justify an alias for removed paths.

## Documentation gaps

### Current gap

[`docs/specs/0003-product-state.md`](../specs/0003-product-state.md), lines
22-31 is the sole current documentation gap: its approved, non-superseded
stable-obligations section still says reactions compile into independently
addressable obligation paths. Its repository-boundary and sync-execution
sections have later replacements, but that does not supersede this statement.
This is a documentation defect only; it does not alter the runtime acceptance
surface above.

### Resolved snapshot findings

The following were current user-facing documentation dependencies at the
immutable audit snapshot `34172a7`. They are all documentation gaps, not
implementation dependencies, and commit `98ef5e7`—already in this branch's
merged base—corrected every one. They are retained as audit evidence and are
not current gaps:

- [`README.md`](../../README.md), lines 6-7 and 24-27 called out outputs and
  reactions and directed readers to superseded specification 0009.
- [`docs/quickstart.md`](../quickstart.md), lines 29-36 used the removed
  `given`, `when`, `then`, and `otherwise` scenario fields; lines 45-47 also
  instructed readers to use reactions and a behavior output.
- [`docs/authoring-guide.md`](../authoring-guide.md), lines 19-21 described
  removed behavior `output` and `context`; lines 25-37 described reactions and
  `output.emits`; lines 30-31 described the removed use-case scenario model;
  and lines 42-49 allowed behavior-level architecture. The latter conflicts
  with the closed behavior schema
  ([`schema/pml.schema.json`](../../schema/pml.schema.json), lines 199-210) and
  its rejection test
  ([`tests/test_behavior_transition_validation.py`](../../tests/test_behavior_transition_validation.py),
  lines 91-104).
- [`docs/language-reference.md`](../language-reference.md), lines 20-58
  presented the removed top-level signals registry; lines 67-75 listed feature
  `reactions` and `emits`; lines 80-92 presented removed behavior fields and
  architecture; lines 102-107 described scenario fields; and lines 109-174
  described reactions, emits, and `.output` paths.
- [`docs/verification.md`](../verification.md), line 3 said reactions resolve
  into stable obligations.

## Superseded historical specifications (not current documentation gaps)

The audit also found the affected terms in approved historical specifications.
They are cited here to make the inventory complete, but are not classified as
current documentation defects because specification 0010 explicitly supersedes
their conflicting transition scope:

- [`docs/specs/0001-language-design.md`](../specs/0001-language-design.md) is
  normalized by 0004 and has its conflicting behavior, signal, reaction, and
  use-case scenario grammar superseded by 0010.
- [`docs/specs/0004-language-normalization.md`](../specs/0004-language-normalization.md),
  lines 37-50 and 61-65 contains the prior signals, reactions, obligation, and
  behavior-architecture model; 0010 supersedes the conflicting transition
  scope.
- [`docs/specs/0006-architecture-decisions.md`](../specs/0006-architecture-decisions.md),
  line 21 permits behavior-level `architecture`, but 0010 explicitly supersedes
  behavior architecture scope.
- [`docs/specs/0009-behavior-units-and-outputs.md`](../specs/0009-behavior-units-and-outputs.md)
  contains the old output, signal-registry, reactions, and obligation-path
  design; 0010 supersedes it where the specifications conflict.

The approved replacement is
[`docs/specs/0010-behavior-transition-model.md`](../specs/0010-behavior-transition-model.md):
its scope at lines 8-16 identifies the superseded areas, lines 145-167 define
the current transition paths and remove the registry/emission model, lines
203-208 remove reactions, lines 210-224 remove behavior-level architecture, and
lines 226-254 define the current use-case shape.
