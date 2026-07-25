# Product verification protocol

Product verification determines whether an implementation produces the outcomes
required by an approved PML component. It is performed after code review and before
merge when a suitable environment is available. The design rationale is in
[`specs/0002-deterministic-verification.md`](specs/0002-deterministic-verification.md).

Verification has three evidence methods. The approved obligation declares which
methods are required; satisfying one lane does not replace another required lane:

1. **Probe execution.** Obligations covered by approved probes are verified by
   running the probes. No agent judgment is involved; the runner's report becomes
   `deterministic_probe` evidence.
2. **Agent judgment.** Obligations requiring qualitative examination are evaluated
   by an independent verification agent.
3. **Human attestation.** Obligations permitting accountable direct observation may
   be attested by a named person.

## Inputs

- Pull request and exact commit.
- Affected PML semantic IDs declared by the implementer.
- Approved probes bound to those semantic IDs, with an environment profile.
- An integrated environment in which the product can be operated.

## Verifier responsibilities

1. Run every approved probe bound to an affected semantic ID; record results as
   `deterministic_probe` evidence.
2. Load each affected component, its rules, use cases, security expectations,
   acceptance statements, and connected reactions.
3. For obligations requiring agent judgment, interact with the product through realistic
   actor-facing or system-facing surfaces and observe required success, failure,
   persistence, and cross-component outcomes.
4. **Author probes.** For each suitable obligation lacking a probe, emit a probe
   definition proposal whenever the closed step vocabulary can express it. Probe
   proposals are a primary output of verification, not a courtesy: they are what
   makes the next verification deterministic.
5. Record passed, failed, blocked, and unevaluated obligations honestly, each with
   its evidence kind.
6. Report environment, version, model, effort, evidence, and limitations.

## Evidence requirements

- Every check states its `method`: `deterministic_probe`, `human_attestation`, or
  `agent_judgment`.
- `agent_judgment` checks must include exact reproduction steps and the expected
  observation, so any claim can be replayed and audited by sampling.
- A rule with `severity: critical` passes only on `deterministic_probe` or
  `human_attestation` evidence. `agent_judgment` alone leaves it `pending`.
- Prose asserting success without an observation is not evidence.

Reading code may support verification but cannot by itself prove user-visible or
operational behavior.

## Verdicts

- `verified`: evaluated obligations pass and required evidence exists.
- `failed`: at least one evaluated obligation fails.
- `incomplete`: important obligations were not evaluated.
- `blocked`: the environment or an external dependency prevented evaluation.

The verifier writes a report conforming to
[`schema/verification-report.schema.json`](../schema/verification-report.schema.json).
