# Task 47 — probes and verification compatibility audit

Audited 2026-08-12 against PR #21 (`a05a6eb`) plus the post-#22 transition
obligation change (`d2ccc754d2c9fc2983a5d2eb245736d7def67290`,
`feature/transition-obligations`). Scope is the deterministic-probe and
verification-command path only. This is a read-only finding; it changes no PML
semantics or implementation.

## Result

No remaining **implementation defect** was found in probes or the implemented
verification commands. PR #22 removes the legacy `reactions` and behavior
`output` obligation paths at the one authoritative enumeration boundary and
updates the two path-admitting schemas. The downstream consumers are generic:
they consume resolved `Obligation` objects/IDs and therefore pick up the new
transition paths without a grammar-specific branch.

### Evidence that removed paths are not accepted or produced

| Surface | Evidence | Result |
| --- | --- | --- |
| Obligation resolution | `src/pml/obligations.py:9, 80-178` changes the section list to `rules`/`use_cases` and resolves behavior `conditions`, `trigger`, `completion`, `outcome`, and `failures`; `tests/test_state.py:test_direct_transition_has_exact_fully_qualified_obligation_ids` (lines 112-126) and `test_alternative_transition_has_exact_fully_qualified_obligation_ids` (129-152) assert the exact replacement IDs. | No old obligation path is produced. |
| Probe target grammar | `schema/pml-probe.schema.json:11` admits the transition IDs and no `reactions` or `output` segment; `tests/test_probes.py:test_probes_can_target_behavior_transition_obligations` (89-130) loads `.completion` and `.failures.processing_failure`. | New probe targets are admitted. |
| Binding target grammar | `schema/pml-bindings.schema.json:64` admits the same transition path family; `tests/test_state.py:test_behavior_transition_obligations_are_accepted_by_bindings_schema` (155-188) exercises every resolved behavior transition ID. | New coverage bindings are admitted. |
| Probe validation and completeness | `src/pml/probes.py:31-103` (`load_probes`) builds its target map from `enumerate_obligations`/`enumerate_architecture_obligations`; `missing_probe_diagnostics` at 107-121 uses the same enumeration and `verification_plan`. | Generic consumer; no removed-grammar dependency. |
| `pml validate-probes`, `pml check --probes`, and `pml ingest-report` | `src/pml/cli.py:149-244` delegates to the generic probe loader/completeness/evidence validation; the report path calls `src/pml/ingest.py:35-210`, whose target map is also built from the enumerators (82-86, 203-207). | Generic consumers; no removed-grammar dependency. |
| Stored probe-evidence verification | `src/pml/project_state.py:1269-1355` selects the product/architecture enumerator and looks up each resolved ID's `verification_plan`; `tests/test_state.py:475-515` covers probe-evidence validation. | Generic consumer; no removed-grammar dependency. |
| Status and `pml obligations` output | `src/pml/status.py:168-182` and `221-248`, plus `src/pml/cli.py:250-264`, enumerate resolved obligations rather than parse path segments. | Generic consumers; no removed-grammar dependency. |

The probe test's `legacy-component.probe.yaml` fixture name at
`tests/test_probes.py:123-130` is intentionally negative coverage for the
already-removed component path. Likewise, legacy field names in
`tests/test_validator.py` negative cases are rejection tests, not live grammar
consumers.

## Documentation gaps (not implementation defects)

1. `docs/verification.md:3` still says that `reactions` resolve to obligations.
   Under the approved transition model that term is removed; this is stale
   protocol prose only. The command behavior cited above is not dependent on it.
2. `README.md:6-7` still presents `outputs` and `reactions` as PML constructs,
   and `README.md:24-26` still points to the superseded output design. This is
   stale overview prose only; it does not configure probes, bindings, reports,
   or command behavior.
3. `docs/language-reference.md:168-174` still specifies that `reactions`,
   use-case outcomes, and behavior `outputs` resolve to obligations, including
   the removed `<behavior-id>.output` and
   `<behavior-id>.output.<alternative-id>` paths. This is stale reference prose
   only; the current probe and verification code derives targets from
   `enumerate_obligations`, not this document.
4. `docs/specs/0003-product-state.md:22-31` still says that `reactions`
   compile into independently addressable obligation paths. This is stale
   state-model prose only; no state, probe, or verification command reads it to
   resolve an obligation.

## Explicit non-findings

- No implemented `pml verify` subcommand exists in either #21 or #22
  (`src/pml/cli.py:29-264` registers `validate-probes`, `check`, and
  `ingest-report`, but not `verify`). The existing prose reference to `pml
  verify` is an implementation-scope/documentation mismatch, not a remaining
  dependency on removed grammar or old obligation paths, so it is not counted as
  a Task 47 defect.
- Architecture constraints retain their separate, unchanged obligation namespace;
  the probe and verification consumers explicitly enumerate them alongside
  product obligations. This is already-covered generic behavior, not a legacy
  product-obligation path.

## Verification note

Source inspection was performed against `feature/transition-obligations` at
`d2ccc75`. After the audit report was based on the post-#22 source, the focused
post-merge compatibility suite passed with `uv run --extra dev pytest -q
tests/test_probes.py tests/test_state.py tests/test_ingest.py
tests/test_behavior_transition_validation.py` (`112 passed`).
