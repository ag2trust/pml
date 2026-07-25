# PML 0.1 Language Design

Status: Approved for 0.1 MVP implementation; amended by spec 0003
Approved direction: 2026-07-21

## 1. Purpose

PML is a declarative product programming language. It provides a strict,
implementation-independent representation of product intent that agents can use to:

1. derive specifications and implementation plans;
2. build or rebuild a product;
3. discover missing, partial, inconsistent, or failing behavior;
4. calculate change impact across related product components;
5. verify that the product continues to satisfy its approved definition.

PML is not a replacement for source code. It is the authoritative contract against
which implementations are designed and evaluated.

## 2. Core decisions

### 2.1 Restricted YAML is the authoring syntax

PML uses YAML for readability and JSON-compatible data modeling. PML permits only a
restricted subset:

- mappings, sequences, strings, integers, numbers, booleans, and null;
- no custom tags;
- no anchors or aliases;
- no implicit timestamps;
- duplicate keys are invalid;
- unknown keys are invalid in all language-defined objects;
- canonical formatting and key order are formatter-enforced.

XML was rejected as the primary syntax because its additional visual structure does
not improve the semantic model enough to justify authoring and review noise. PML can
compile to JSON or XML if an integration requires either.

### 2.2 Definitions and state are separate

An authored definition states what the product must be. Generated state records
whether a particular product version conforms.

```text
definition.pml.yaml       human-approved intent
state/<version>.json      generated conformance result
evidence/...              generated supporting artifacts
```

Agents may update generated state. Agents may propose definition changes, but cannot
silently modify approved intent to match an implementation.

### 2.3 The source is modular; the compiled result is a graph

A project may split its definition across files. Each semantic object has one stable,
globally unique ID and exactly one authoritative definition. References connect files.
The compiler produces a unified graph and rejects unresolved or conflicting objects.

## 3. Semantic hierarchy

The principal containment hierarchy is:

```text
Project
  Domain
    Feature
      Component
        Component (recursive, to the useful level of detail)
      Rule
      Use case
      Experience
        Surface
```

The following graph objects may cross containment boundaries:

- actors;
- concepts;
- policies;
- events;
- `depends_on` dependencies;
- reactions;
- state and evidence references.

Containment communicates ownership, not isolation. A use case may traverse several
features, and an event may connect multiple domains.

## 4. Normative top-level structure

PML 0.1 permits these top-level keys:

```yaml
pml:
project:
imports:
vocabulary:
actors:
concepts:
events:
policies:
domains:
```

`pml` and `project` are required. Other sections are optional only when unused.
Unknown top-level keys are errors.

## 5. Canonical objects

### Project

Defines identity, name, and purpose. Purpose explains the outcome the product exists
to create, not its implementation.

### Vocabulary

Defines canonical domain terms. A vocabulary entry contains `meaning` and may contain
`forbidden_synonyms`. Terms are case-sensitive in normative statements. Validators
report forbidden synonyms and undefined capitalized domain terms.

### Actor

An entity that initiates or participates in behavior. An actor references a canonical
term or defines a concise meaning.

### Concept

A meaningful product entity or stateful abstraction. It may declare ownership,
relationships, and lifecycle states. It does not declare storage representation.

### Domain

A coherent product responsibility grouping related features. Domains must be based on
product meaning, not deployment or source-code layout.

### Feature

A product capability delivering a meaningful outcome. A feature may contain only:

```text
purpose, actors, inputs, outputs, owns, uses, produces, consumes, updates,
displays, protects, blocks, rules, use_cases, experience, security,
reactions, depends_on, operations, components, acceptance
```

`components` is recursive. Authors may stop at any semantic level that fully expresses
the intended contract. Components describe product responsibilities and observable
behavior; they must not mirror source-code organization.

### Rule

A stable behavioral or policy constraint with a unique ID, controlled-natural-language
statement, severity, and approved verification requirements.

### Use case

An end-to-end behavioral contract. It uses the fixed structure:

```text
actor, goal, given, when, then, otherwise
```

`actor`, `goal`, `when`, and `then` are required. `otherwise` is required when the
behavior can fail or be rejected. Use cases specify goals and outcomes, not UI click
sequences.

### Experience and surface

Experience describes what an actor must be able to perceive and operate. A surface
may define `purpose`, `contains`, `actions`, `states`, `accessibility`, and
`responsive_behavior`. It does not define framework components or visual pixel values.
Approved visual artifacts may be referenced separately when layout is normative.

### Event and reaction

An event represents a semantically meaningful occurrence, not a transport message.
A reaction defines cross-component consequences:

```yaml
- when: assistant_created
  target: assistants.list
  must: The created Assistant MUST appear without a new login.
```

Events and ID-keyed reactions provide change-impact edges in the compiled graph.

Rules, use cases, security expectations, reactions, and acceptance outcomes are
ID-keyed obligations. Each declares the evidence methods required for verification,
as specified by [0003](0003-product-state.md).

## 6. Controlled natural language

Normative statements use canonical terms and one of these forms:

```text
<Actor> MUST <observable behavior>.
<Actor> MUST NOT <forbidden behavior>.
WHEN <event>, THE SYSTEM MUST <observable outcome>.
IF <condition>, THE SYSTEM MUST <observable outcome>.
ON FAILURE, THE SYSTEM MUST <observable recovery or result>.
```

Each statement expresses one obligation. The validator rejects or warns on ambiguous
qualifiers including `should`, `normally`, `properly`, `appropriately`, `seamlessly`,
`relevant`, and `etc.`

PML prose fields such as `purpose`, `meaning`, and `goal` are descriptive and need not
use normative grammar. Rule, security, state, reaction, and acceptance statements are
normative.

## 7. Relationship vocabulary

PML 0.1 defines only these relationship types:

| Relationship | Meaning |
|---|---|
| `owns` | Component is authoritative for a concept. |
| `uses` | Component requires another capability. |
| `produces` | Component causes a semantic event. |
| `consumes` | Component reacts to a semantic event. |
| `updates` | Behavior changes a concept. |
| `displays` | Experience represents a concept. |
| `protects` | Policy governs a concept or action. |
| `blocks` | State prevents another behavior. |
| `depends_on` | Component requires another component's outcome. |
| `invalidates` | Change makes prior conformance evidence stale. |

New relationship types require a language-version change. Agents cannot introduce
synonyms such as `relies_on`, `needs`, or `connects_to` ad hoc.

## 8. Conformance state

State is generated for every addressable graph node using independent dimensions:

```yaml
definition: draft | review | approved | superseded
implementation: unknown | not_started | partial | complete | inconsistent
verification: unverified | pending | passing | failing | stale | blocked
operation: unknown | healthy | degraded | failing | unavailable
overall: unknown | planned | partial | healthy | degraded | failing | blocked
```

An evidence record states its kind, observed result, product version, time, producer,
confidence, and affected semantic IDs. A passing claim without evidence is invalid.
Evidence kinds, deterministic probes, and severity-based evidence routing are defined
in [`0002-deterministic-verification.md`](0002-deterministic-verification.md).

Overall state is calculated, never freely authored. Required child failures propagate
to parents. A failed required dependency blocks the dependent node. Relevant changes
make prior verification stale until re-evaluated.

## 9. Validation pipeline

The reference validator will apply these stages:

1. **Syntax:** restricted YAML and duplicate-key enforcement.
2. **Structure:** exact schema, required fields, permitted values.
3. **References:** every semantic ID resolves exactly once.
4. **Vocabulary:** canonical terms and forbidden synonyms.
5. **Language:** controlled normative sentence forms.
6. **Graph:** ownership conflicts, invalid cycles, and dependency consistency.
7. **Completeness:** required outcomes, failures, security, and acceptance coverage.

Diagnostics must identify file, semantic ID, field, violated rule, and a corrective
example. Validation must not silently repair author intent.

## 10. Compilation targets

The initial compiler may derive:

- a normalized product graph;
- human-readable feature specifications;
- implementation-planning inputs;
- change-impact sets;
- conformance checklists;
- status and gap dashboards.

Generated specifications and plans are downstream views. They cannot override the PML
definition.

## 11. Non-goals for version 0.1

- Expressing algorithms or implementation architecture.
- Naming source files, functions, endpoints, database tables, or tests.
- Automatically modifying approved product intent.
- Proving arbitrary natural-language statements mechanically.
- Defining visual design at pixel-level precision.
- Replacing implementation code or runtime telemetry.

## 12. Version 0.1 decisions

1. The provisional language and project name is `PML`.
2. Every use case has one owning feature. It may reference behavior in other features
   through events, reactions, and dependencies.
3. Normative statements remain controlled strings in 0.1. A future compiler may derive
   structured representations without changing their meaning.
4. Feature-specific security statements remain inline; reusable security requirements
   are declared as project policies and referenced by features.
5. Operations describe observable signals and health outcomes, never monitor or vendor
   implementation details.
6. Approval metadata lives outside definitions so approval activity cannot pollute or
   silently rewrite product intent.

## 13. Proposed implementation sequence after approval

1. Freeze the 0.1 object model and restricted-YAML profile.
2. Create the JSON Schema with `additionalProperties: false` throughout.
3. Implement parser and structural diagnostics.
4. Implement semantic ID, reference, and vocabulary validation.
5. Implement controlled-language linting.
6. Compile the normalized product graph.
7. Add generated conformance-state and change-impact views.
8. Pilot against one complete feature dossier from a real host product.
