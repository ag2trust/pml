# PML 0.1 language reference

PML is a restricted product-definition language, not an open-ended documentation
format. Unknown attributes, duplicate keys, aliases, unquoted dates, and unresolved
references are invalid. IDs use lowercase letters, numbers, and underscores and
must begin with a letter.

## Product structure

The only containment hierarchy is:

```text
Project → Domain → Feature → Component
```

A domain groups product responsibilities. A feature is a complete user or business
capability. A component is a non-nested behavioral part of one feature. Components
must not mirror code, framework, repository, service, or infrastructure structure.

## Top level

| Attribute | Required | Meaning |
|---|---:|---|
| `pml` | yes | Language version; `"0.1-draft"`. |
| `project` | yes | Product identity and purpose. |
| `vocabulary` | no | Canonical terms and forbidden synonyms. |
| `actors` | no | People, systems, or processes participating in behavior. |
| `concepts` | no | Meaningful product entities and their semantic states. |
| `signals` | no | Meaningful product facts connecting behavior. |
| `rules` | no | Project-wide normative obligations. |
| `architecture` | no | Owner-approved technical constraints. |
| `domains` | yes | Product responsibility areas containing features. |

## Descriptive objects

### `project`

`id`, `name`, and `purpose` are required.

### `vocabulary.<Term>`

`meaning` is required. `forbidden_synonyms` is optional. Vocabulary is used only
when terminology enforcement is valuable; product concepts do not depend on it.

### `actors.<id>`

Each actor has one required `meaning`.

### `concepts.<id>`

Each concept has one required `meaning` and may list unordered semantic `states`.
Rules, use cases, and signals describe valid transitions. Concepts do not declare
storage, classes, tables, or organizational ownership.

### `signals.<id>`

Each signal has one required `meaning`. A signal is a meaningful product fact, not
a required code event, message, log, queue item, or transport mechanism.

## Behavioral objects

### `domains.<id>`

A domain requires `purpose` and one or more `features`. It may contain scoped
`rules`.

### `features.<id>`

A feature requires `purpose` and at least one of `rules`, `use_cases`, or
`components`. It may contain:

```text
purpose, actors, rules, use_cases, components, experience, reactions,
related_to, emits, architecture
```

Features do not have generic inputs or outputs: those fields tend to restate use
cases or drift into API design.

### `components.<id>`

A component requires `purpose` and may contain:

```text
purpose, inputs, outputs, rules, reactions, related_to, emits, architecture
```

Components cannot contain components. Their inputs and outputs describe behavioral
boundaries, not function arguments, endpoints, payload schemas, or implementation
interfaces.

### `rules.<id>`

A rule contains one `statement` with `MUST` or `MUST NOT`. Rules express invariants
that apply across scenarios. Security requirements are ordinary rules rather than a
separate language section.

The location of a rule determines its scope: top-level, domain, feature, or component.

### `use_cases.<id>`

A use case contains `actor`, `goal`, `given`, `when`, and `then`; `otherwise` is
optional. It describes an end-to-end behavioral scenario, not click-by-click UI
instructions. Rules should not be copied into `then`; scenarios demonstrate rules
through concrete outcomes.

### `reactions.<id>`

A reaction contains:

```yaml
on: payment_failed
statement: Credits MUST NOT be added.
```

`on` references one signal. `statement` expresses one direct, independently
verifiable consequence. Multiple consequences are represented as multiple
ID-keyed reactions referring to the same signal.

### `related_to`

`related_to` is an untyped list of unique semantic paths resolving to features or
components. It establishes a symmetric behavioral relationship without declaring a
dependency direction. Tooling treats changes to either node as relevant to the
other node's verification freshness.

### `emits`

`emits` lists declared signal IDs established by a feature or component. It differs
from component `outputs`: outputs describe a boundary result, while signals connect
behavior across nodes.

### `experience`

`experience.surfaces.<id>.contains` describes information or controls actors must be
able to perceive or access. Surfaces may also define observable `states`,
`accessibility`, and `responsive_behavior`. Actor behavior belongs in use cases, so
surfaces do not have `actions` or a repetitive `purpose`.

## Architecture

`architecture` is a flat, optional registry of owner-approved technical decisions.
Each decision has:

```text
category, selection, rationale, constraints
```

Allowed categories are `database`, `framework`, `gateway`, `provider`,
`payment_processor`, and `runtime`. Features and components may reference decisions
bottom-up using `architecture: [decision_id]`.

A choice belongs here only when replacing it would require explicit owner approval
even if product behavior remained correct. Architecture may name approved
technologies, purposes, responsibilities, and normative constraints, but not
filenames, functions, classes, tables, endpoints, topology, or configuration syntax.
Technology existence never proves behavioral conformance.

## Obligations and verification

An **obligation** is the tooling term for one resolved, independently verifiable
product constraint. It is not an authored PML section. Rules, reactions, and
use-case outcomes resolve into stable obligation paths.

Definitions state behavior. External bindings select deterministic probes, agentic
verification, or human attestation and assign their coverage. Generated state records
current evidence, confidence, and freshness. Verification mechanics and scores never
appear in an approved product definition.

When a node or a `related_to` node changes, sync invalidates affected obligation
confidence. Current passing probes restore only their approved coverage; agentic or
human verification is required for the remaining approved coverage.

## Deliberately outside PML definitions

- implementation files, functions, endpoints, tables, and configuration;
- tests, probe procedures, and verification scores;
- current status, evidence, issues, commits, and artifacts;
- operational monitoring and infrastructure topology;
- organizational ownership and project-management metadata.
