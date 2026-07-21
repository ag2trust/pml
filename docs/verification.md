# Product verification protocol

Product verification determines whether an implementation produces the outcomes
required by an approved PML component. It is performed by an independent agent after
code review and before merge when a suitable environment is available.

## Inputs

- Pull request and exact commit.
- Affected PML semantic IDs declared by the implementer.
- An integrated environment in which the product can be operated.

## Verifier responsibilities

1. Load each affected component, its rules, use cases, security expectations,
   acceptance statements, and connected reactions.
2. Interact with the product through realistic actor-facing or system-facing surfaces.
3. Observe required success, failure, persistence, and cross-component outcomes.
4. Record passed, failed, blocked, and unevaluated obligations honestly.
5. Report environment, version, model, effort, evidence, and limitations.

Reading code may support verification but cannot by itself prove user-visible or
operational behavior.

## Verdicts

- `verified`: evaluated obligations pass and required evidence exists.
- `failed`: at least one evaluated obligation fails.
- `incomplete`: important obligations were not evaluated.
- `blocked`: the environment or an external dependency prevented evaluation.

The verifier writes a report conforming to
[`schema/verification-report.schema.json`](../schema/verification-report.schema.json).

