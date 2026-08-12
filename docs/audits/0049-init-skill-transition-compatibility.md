# Task 49: initialization and packaged-skill transition compatibility audit

Audited at `8da0345` (PR #22), after the behavior-transition validation in PR
#21 and transition-obligation resolution in PR #22. This is a read-only
compatibility finding, not a language definition.

## Scope and baseline

The removed behavior grammar is `context`, `output`, `reactions`, `emits`, and
behavior-level `architecture`; the top-level `signals` registry and use-case
`given`/`when`/`then`/`otherwise` are also removed.
The removed behavior obligation paths include `*.output` and
`*.reactions.*`. The current resolver instead produces the behavior paths
`conditions`, `trigger`, `completion`, `outcome`, and `failures.*`.

Evidence for the replacement paths is
[`src/pml/obligations.py`](../../src/pml/obligations.py) in
`enumerate_obligations` (lines 80-165), with exact ID assertions in
[`tests/test_state.py`](../../tests/test_state.py) lines 96-152.

## Findings

### Actual defects

One concrete indirect packaged-guidance dependency remains. This is a
documentation defect, not a language-semantics or implementation defect.

The packaged skill requires authors to read the applicable PML language reference
([`src/pml/resources/skills/pml/SKILL.md`](../../src/pml/resources/skills/pml/SKILL.md)
line 13), and the repository designates
[`docs/language-reference.md`](../language-reference.md) as the Language
reference for every PML 0.1 attribute
([`README.md`](../../README.md) lines 137-146). That referenced document still
instructs authors to use removed grammar: the top-level `signals` registry (lines
20-32), feature `reactions` and `emits` (lines 67-75), behavior `context`,
`output`, `reactions`, and `architecture` (lines 80-92), and use-case
`given`/`when`/`then`/`otherwise` (lines 102-107). It also describes the removed
`<behavior-id>.output` and alternative `*.output.*` obligation paths (lines
168-174), and elsewhere explicitly permits behaviors to reference architecture
decisions (lines 151-153 and 165). Thus the packaged skill's required reference
path can direct an author to syntax the current validator rejects and to obsolete
verification IDs.

The current behavior schema rejects the cited legacy keys, including `context`,
`output`, `reactions`, `emits`, and `architecture`, in
[`tests/test_behavior_transition_validation.py`](../../tests/test_behavior_transition_validation.py)
`test_removed_behavior_keys_are_rejected` (lines 90-104). The current obligation
IDs are instead asserted in [`tests/test_state.py`](../../tests/test_state.py)
lines 96-152. The owner-approved transition specification explicitly makes
`architecture` invalid at behavior scope and feature-level only
([`docs/specs/0010-behavior-transition-model.md`](../specs/0010-behavior-transition-model.md)
lines 210-224); the closed behavior schema likewise omits it while allowing it at
feature scope ([`schema/pml.schema.json`](../../schema/pml.schema.json) lines
175-210). Updating the pre-existing language reference is follow-up work outside
this read-only audit; this audit changes neither semantics nor implementation.

Apart from that indirect reference dependency, no initialization template encodes
removed grammar or an old obligation path.

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
new paths. This is a separate documentation-completeness gap. It would be
non-blocking if the designated reference were current, but the reference defect
above means the package currently has no safe detailed transition grammar source.
No language or implementation change is proposed by this audit.

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
