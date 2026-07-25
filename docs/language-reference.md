# PML 0.1 language reference

PML uses restricted YAML. Unknown attributes, duplicate keys, aliases, unquoted dates,
and unresolved references are invalid. IDs use lowercase letters, numbers, and
underscores and must begin with a letter.

`Required` below means structurally required by PML 0.1.

## Top level

| Attribute | Required | Meaning |
|---|---:|---|
| `pml` | yes | Language version. Must be `"0.1-draft"`. |
| `project` | yes | Product identity and purpose. |
| `imports` | no | Other PML definition files to compose. Import resolution is reserved for a later validator release. |
| `vocabulary` | no | Canonical product terms and forbidden synonyms. |
| `actors` | no | People, systems, or processes participating in behavior. |
| `concepts` | no | Meaningful product entities and their semantic lifecycle. |
| `events` | no | Meaningful occurrences used across components. |
| `policies` | no | Reusable project-wide normative rules. |
| `domains` | yes | Product responsibility areas containing features. |

## `project`

| Attribute | Required | Meaning |
|---|---:|---|
| `id` | yes | Stable machine-readable project ID. |
| `name` | yes | Human-readable name. |
| `purpose` | yes | Outcome the product exists to create. |

## `vocabulary.<Term>`

| Attribute | Required | Meaning |
|---|---:|---|
| `meaning` | yes | One authoritative meaning for the canonical term. |
| `forbidden_synonyms` | no | Terms that must not substitute for the canonical term. |

Vocabulary keys are canonical terms and may use product-appropriate capitalization.

## `actors.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `term` | conditional | References a canonical vocabulary term. |
| `meaning` | conditional | Defines the actor directly when no vocabulary term is needed. |

At least one of `term` or `meaning` is required.

## `concepts.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `term` | yes | Canonical term naming the concept. |
| `owned_by` | no | Canonical owner of the concept. |
| `lifecycle` | no | Ordered semantic states the concept may occupy. |

Concepts describe meaning, not database schemas or classes.

## `events.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `meaning` | yes | Product meaning of the occurrence. |
| `subject` | yes | Concept ID affected by the occurrence. |

Events are semantic occurrences, not transport messages.

## `policies.<id>` and `rules.<id>`

| Attribute | Required | Meaning | Values |
|---|---:|---|---|
| `statement` | yes | One controlled-natural-language obligation. | Must contain `MUST` or `MUST NOT`. |
| `severity` | yes | Consequence of violation. | `critical`, `high`, `normal`, `low` |
| `verification` | yes | Approved evidence lanes. | One or more evidence methods. |

## `domains.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `purpose` | yes | Product responsibility owned by the domain. |
| `features` | yes | One or more feature definitions. |

Domains follow product meaning rather than services, repositories, or deployments.

## `features.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `purpose` | yes | Outcome delivered by the feature. |
| `actors` | no | Actor IDs participating in the feature. |
| `inputs` | yes | Information or conditions accepted by the feature. |
| `outputs` | yes | Observable results produced by the feature. |
| `owns` | no | Concepts for which the feature is authoritative. |
| `uses` | no | Capabilities required by the feature. |
| `produces` | no | Event IDs caused by the feature. |
| `consumes` | no | Event IDs to which the feature reacts. |
| `updates` | no | Concepts changed by the feature. |
| `displays` | no | Concepts represented by its experience. |
| `protects` | no | Concepts or actions governed by its policies. |
| `blocks` | no | Behavior prevented by a feature state. |
| `rules` | yes | Feature obligations indexed by stable IDs. |
| `use_cases` | yes | End-to-end behavioral contracts. |
| `components` | no | Recursive semantic decomposition. |
| `experience` | no | Actor-visible surfaces and states. |
| `security` | no | ID-keyed feature-specific security obligations. |
| `reactions` | no | ID-keyed cross-component consequences of events. |
| `depends_on` | no | Semantic node IDs whose outcomes this node requires. |
| `operations` | no | Observable runtime signals and health outcomes. |
| `acceptance` | yes | ID-keyed observable outcomes required for acceptance. |

## `use_cases.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `actor` | yes | Declared actor pursuing the goal. |
| `goal` | yes | Outcome the actor wants. |
| `given` | yes | Preconditions before the behavior begins. |
| `when` | yes | Triggering actor or system actions. |
| `then` | yes | Required successful outcomes. |
| `otherwise` | no | Required rejection, failure, or recovery outcomes. Use whenever failure is possible. |
| `verification` | yes | Owner-approved evidence methods required for this obligation. |

Use cases describe behavior, not click-by-click UI scripts.

## `components.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `purpose` | yes | Semantic responsibility of the component. |
| `inputs` | no | Accepted information or conditions. |
| `outputs` | no | Observable results. |
| `rules` | no | Component-specific obligations. |
| `security` | no | Component-specific security obligations. |
| `reactions` | no | ID-keyed event-driven effects on other components. |
| `depends_on` | no | Semantic node IDs whose outcomes this component requires. |
| `components` | no | Nested semantic components at any useful depth. |
| `acceptance` | no | Conditions demonstrating component conformance. |

## `experience.surfaces.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `purpose` | yes | User outcome served by the surface. |
| `contains` | yes | Information and controls actors must perceive. |
| `actions` | no | Actions actors must be able to perform. |
| `states` | no | Observable behavior in states such as empty, loading, success, and failure. |
| `accessibility` | no | Observable accessibility obligations. |
| `responsive_behavior` | no | Behavior required across supported presentation sizes. |

Surfaces describe experience contracts, not framework components or pixel layouts.

## `reactions.<id>`

| Attribute | Required | Meaning |
|---|---:|---|
| `when` | yes | Declared event ID causing the reaction. |
| `target` | yes | Semantic target affected by the event. |
| `must` | yes | Observable consequence containing `MUST` or `MUST NOT`. |

## `operations`

| Attribute | Required | Meaning |
|---|---:|---|
| `observable_signals` | no | Product-significant occurrences that must be observable. |
| `health_outcomes` | no | Runtime conditions that indicate correct or degraded behavior. |

Do not name monitoring vendors, dashboards, metrics implementations, or alerting code.

## Deliberately outside PML definitions

The following belong in external mappings, evidence, state, or history:

- filenames, functions, endpoints, tables, frameworks, and infrastructure;
- tests and verification procedures;
- current status and evidence;
- issues, pull requests, commits, and artifacts;
- agent names, providers, models, and effort.
