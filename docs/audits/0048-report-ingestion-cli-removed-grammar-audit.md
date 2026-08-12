# Report ingestion and CLI removed-grammar audit

Audit date: 2026-08-12  
Baseline: merge commits `a05a6eb` (PR #21) and `8da0345` (PR #22)

## Result

There are **no remaining implementation dependencies** in report ingestion or
CLI output on the removed behavior grammar (`output`, `emits`, `reactions`) or
its old `.output` obligation paths. The generic obligation consumers now
resolve the approved transition paths:

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
173-205). None formats or accepts `output`, `emits`, `reactions`, or an old
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

The following current user-facing documents still describe removed grammar or
old obligation paths. These are documentation defects only; they do not alter
the runtime acceptance surface above.

- [`README.md`](../../README.md), lines 6-7 and 24-27 calls out outputs and
  reactions and points readers to superseded specification 0009 as the current
  design.
- [`docs/quickstart.md`](../quickstart.md), lines 45-47 instructs readers to
  use reactions and says every behavior has one output.
- [`docs/authoring-guide.md`](../authoring-guide.md), lines 25-37 describes
  reaction statements, `output.emits`, and `reactions.on`.
- [`docs/language-reference.md`](../language-reference.md), lines 67-174
  presents `output`, `emits`, and `reactions` as valid grammar and documents
  the removed `.output` obligation paths.
- [`docs/verification.md`](../verification.md), line 3 says reactions resolve
  into stable obligations.
- [`docs/specs/0003-product-state.md`](../specs/0003-product-state.md), lines
  22-31 is an approved, non-superseded stable-obligations section that says
  reactions compile into independently addressable obligation paths. Its
  repository-boundary and sync-execution sections have later replacements, but
  that does not supersede this stable-obligations statement; it is therefore a
  current documentation defect.

[`docs/specs/0009-behavior-units-and-outputs.md`](../specs/0009-behavior-units-and-outputs.md)
also contains the old terms and paths, but it is a superseded historical design,
not a separate current-documentation defect. The approved replacement is
[`docs/specs/0010-behavior-transition-model.md`](../specs/0010-behavior-transition-model.md),
which defines the current paths at lines 145-167 and removes reactions at lines
203-208.
