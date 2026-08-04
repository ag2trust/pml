# PML behavior units and singular outputs

Status: Proposed

## Purpose

PML models product behavior, not implementation structure. The term `component`
can imply a class, library, service, framework module, or concrete UI element and
therefore invites implementation-shaped definitions. This specification replaces
it with the canonical term `behavior` and makes each behavior complete with one
primary output.

This is a language design change. It introduces no compatibility alias and does
not alter generated state until the schema and semantic-validator migration is
approved and implemented.

Once approved, this specification supersedes the component hierarchy and plural
output semantics in [0001](0001-language-design.md) and
[0004](0004-language-normalization.md), and replaces later references to component
targets with behavior targets.

## Canonical hierarchy

```text
Project → Domain → Feature → Behavior
```

A behavior is a cohesive, independently addressable unit of observable product
conduct within a feature. It accepts relevant context and, for each evaluation,
completes with one primary output. A behavior is not required to correspond to a
file, function, class, endpoint, service, job, UI component, or test.

Behaviors are direct children of features and do not nest. Features and behaviors
may establish symmetric `related_to` relationships with other features and
behaviors. Architecture decisions may be referenced by features and behaviors.

## Singular output

Every behavior has exactly one authored `output`. Inputs remain an optional list
because one behavior may require several pieces of product context. Output is a
singular completion contract, not a list of unrelated effects.

A direct output has one statement and may emit product signals:

```yaml
output:
  statement: One complete importance decision classifying the Inbound Email as important or ordinary.
  emits:
    - email_processed
```

A direct output completes once per successful behavior evaluation. If the behavior
can complete through mutually exclusive alternatives, its one output uses
`one_of`:

```yaml
output:
  one_of:
    decision:
      statement: One complete importance decision classifying the Inbound Email as important or ordinary.
      emits:
        - email_processed
    processing_failure:
      statement: A visible failure indicating that a complete decision could not be supported.
      emits:
        - email_processing_failed
```

`one_of` is a closed map of two through seven ID-keyed alternatives. For each
behavior evaluation, exactly one alternative MUST complete. Completing none or
more than one is nonconformant. Each alternative contains exactly one `statement`
and may contain one non-empty, unique list of declared signal IDs under `emits`.

Signals attached to a direct output or alternative are emitted when that output
completes. Behavior-level `emits` does not exist. A signal common to every
alternative is repeated explicitly on each alternative; PML does not infer or
inherit output effects.

An output statement describes an observable product result. It MUST NOT prescribe
filenames, functions, classes, endpoints, framework elements, tests, payload
schemas, or other implementation details. Several returned values that form one
cohesive observable result may be described as one composite output. Multiple
independent responsibilities require separate behaviors.

## Output obligations

Outputs are normative by their authored position and resolve into stable
obligations; authors do not duplicate them as rules merely to make them verifiable.

- A direct output resolves to `<behavior-id>.output`.
- A `one_of` output resolves an exclusivity obligation at
  `<behavior-id>.output` and one alternative obligation at
  `<behavior-id>.output.<alternative-id>`.

The exclusivity obligation verifies that exactly one alternative completes for an
evaluation. An alternative obligation verifies the observable statement and signal
emissions for that alternative. Bindings may assign different verification methods
and weights to the exclusivity contract and to each alternative.

Output statements do not use rule keywords as aliases. Rules remain separately
identified invariants, reactions remain signal consequences, and use cases remain
actor goals and scenarios.

## Canonical grammar

```text
output-case = {
  statement: non-empty text,
  emits?: unique non-empty list[declared-signal-id]
}
output = output-case | {
  one_of: map[identifier, output-case] with 2..7 entries
}
behavior = {
  purpose: non-empty text,
  inputs?: unique non-empty list[non-empty text],
  output: output,
  rules?: rule-map,
  reactions?: reaction-map,
  related_to?: unique non-empty list[feature-or-behavior-id],
  architecture?: unique non-empty list[architecture-decision-id]
}
```

Unknown keys remain invalid. An output cannot contain both `statement` and
`one_of`. Output alternative IDs are unique within their behavior. Every emitted
signal, relationship target, and architecture reference MUST resolve.

## Migration

This change keeps the draft language version `0.1-draft` while replacing its
canonical vocabulary before a stable release:

- feature `components` becomes `behaviors`;
- component definitions become behavior definitions;
- plural `outputs` becomes required singular `output`;
- behavior-level `emits` moves into the direct output or its alternatives;
- semantic paths replace `.components.` with `.behaviors.`;
- bindings, probe targets, reviews, relationships, generated-state node IDs, and
  obligation IDs use the behavior paths; and
- authored `components` and `outputs` become unknown keys after migration.

There is no period in which `component` and `behavior`, or `outputs` and `output`,
are accepted as synonyms. Existing approved definitions require an explicit owner
change and new lock. Generated state for old component paths becomes removed state
under the warned `pml sync` behavior defined by
[0008](0008-command-execution-semantics.md).

## Delivery boundary

This specification is a design proposal only. After owner approval, schema and
semantic validation change first, followed by positive and negative conformance
examples and tests. Formatter, compiler, state migration, and command behavior
follow only after validation behavior is defined.
