# Task 49: initialization and packaged-skill transition compatibility audit

Audited at `8da0345` (PR #22), after the behavior-transition validation in PR
#21 and transition-obligation resolution in PR #22. This is a read-only
compatibility finding, not a language definition.

## Scope and baseline

The removed behavior grammar is `context`, `output`, `reactions`, `emits`, the
top-level `signals` registry, and use-case `given`/`when`/`then`/`otherwise`.
The removed behavior obligation paths include `*.output` and
`*.reactions.*`. The current resolver instead produces the behavior paths
`conditions`, `trigger`, `completion`, `outcome`, and `failures.*`.

Evidence for the replacement paths is
[`src/pml/obligations.py`](../../src/pml/obligations.py) in
`enumerate_obligations` (lines 80-165), with exact ID assertions in
[`tests/test_state.py`](../../tests/test_state.py) lines 96-152.

## Findings

### Actual defects

None. There is no remaining initialization-template or packaged-skill dependency
on removed grammar or an old obligation path.

`initialize_project` writes only the PML header/project identity and an empty,
generic bindings map; it does not author a behavior shape or verification-key
path. See [`src/pml/initialize.py`](../../src/pml/initialize.py) lines 63-69 and
91-99. Its layout test verifies those exact empty artifacts in
[`tests/test_initialize.py`](../../tests/test_initialize.py) lines 13-35.

The packaged `SKILL.md` contains no removed grammar spelling or obligation-path
example. It directs authors to the applicable language reference and requires
only installed keywords/relationship types; see
[`src/pml/resources/skills/pml/SKILL.md`](../../src/pml/resources/skills/pml/SKILL.md)
lines 13-24. `initialize_project` copies that package verbatim from the packaged
resource (lines 70-74 and 94-99 above), and package-data configuration includes
the entire resource directory in [`pyproject.toml`](../../pyproject.toml) lines
23-25.

`agents/openai.yaml` is the sole other packaged skill file and has only display
metadata/default invocation text; it contains neither grammar nor obligation
paths. See
[`src/pml/resources/skills/pml/agents/openai.yaml`](../../src/pml/resources/skills/pml/agents/openai.yaml).

### Documentation gap (not a stale dependency)

The packaged skill is intentionally process-oriented and does not enumerate the
current behavior-transition fields or transition-obligation IDs. Consequently it
does not independently teach `conditions`/`trigger`/`outcome`/`failures` or the
new paths. This is a documentation completeness gap only: its instruction to
consult the applicable language reference prevents the omission from directing
authors to removed grammar. No change is proposed by this audit.

### Already-covered generic obligation consumers (not findings)

The initializer's empty `bindings` map is generic by design. Consumers resolve
the current obligation set through `enumerate_obligations`, rather than matching
legacy IDs: `verification_plan` in
[`src/pml/obligations.py`](../../src/pml/obligations.py) lines 37-52, and the
status, probe, ingestion, and state-validation callers respectively in
[`src/pml/status.py`](../../src/pml/status.py) lines 168-182,
[`src/pml/probes.py`](../../src/pml/probes.py) lines 45-79,
[`src/pml/ingest.py`](../../src/pml/ingest.py) lines 82-149, and
[`src/pml/project_state.py`](../../src/pml/project_state.py) lines 725-740.

Those are generic consumers already covered by PR #22's transition-ID conformance
tests, including bindings-schema acceptance in
[`tests/test_state.py`](../../tests/test_state.py) lines 155-180 and probe targets
in [`tests/test_probes.py`](../../tests/test_probes.py) lines 86-126. They do not
create an initialization-template or packaged-guidance compatibility defect.
