# PML behavior units and singular outputs

Status: Owner approved

## Purpose

PML models product behavior, not implementation structure. The term `component`
can imply a class, library, service, framework module, or concrete UI element and
therefore invites implementation-shaped definitions. This specification replaces
it with the canonical term `behavior` and makes each behavior complete with one
primary output.

This is a language design change. It introduces no compatibility alias and does
not alter generated state until the schema and semantic-validator migration is
approved and implemented.

Once approved, this specification supersedes the component hierarchy and component
input/output boundary in [0001](0001-language-design.md), supersedes the component
hierarchy in [0004](0004-language-normalization.md), and replaces later references
to component targets with behavior targets.

## Canonical hierarchy

```text
Project → Domain → Feature → Behavior
```

A behavior is a cohesive, independently addressable unit of observable product
conduct within a feature. It evaluates relevant context and, for each evaluation,
completes with one primary output. A behavior is not required to correspond to a
file, function, class, endpoint, service, job, UI component, or test.

Behavior evaluations are bounded. A completed evaluation produces exactly one
output; failure to complete is nonconformance unless failure is an authored output
alternative. Ongoing monitoring and invariant maintenance are expressed as rules or
as repeated bounded behavior evaluations, not as one never-completing behavior.

A behavior has no separate `purpose`. The containing feature owns the product
intention; the behavior ID identifies the conduct and its output states the
completion contract. A future need for independently authored behavior intention
requires a separate language decision rather than an alias for `purpose`.

Behaviors are direct children of features and do not nest. Features and behaviors
may establish symmetric `related_to` relationships with other features and
behaviors. Architecture decisions may be referenced by features and behaviors.

## Singular output

Every behavior has exactly one authored `output`. Relevant product information may
be listed in an optional `context` list. Context is not a function-argument or
payload declaration and does not imply that every item is always available. Output
is a singular completion contract, not a list of unrelated effects.

A direct output has one statement and may emit product signals:

```yaml
output:
  statement: One complete importance decision classifying the Inbound Email as important or ordinary.
  emits:
    - email_processed
```

A direct output completes once per behavior evaluation. If the behavior can
complete through mutually exclusive alternatives, its one output uses `one_of`:

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

Signals attached to a direct output or alternative are required effects and MUST
be emitted when that output completes. Behavior-level `emits` does not exist. A
signal common to every alternative is repeated explicitly on each alternative;
PML does not infer or inherit output effects.

An output statement describes an observable product result. It MUST NOT prescribe
filenames, functions, classes, endpoints, framework elements, tests, payload
schemas, or other implementation details. Several returned values that form one
cohesive observable result may be described as one composite output. Multiple
independent responsibilities require separate behaviors.

## Output obligations

Outputs are normative by their authored position and resolve into stable
obligations; authors do not duplicate them as rules merely to make them verifiable.
Output statements do not require `MUST` or `MUST NOT`; they retain the ambiguity,
observable-outcome, and implementation-detail checks applied to authored product
language.

- A direct output resolves to `<fully-qualified-behavior-id>.output`.
- A `one_of` output resolves an exclusivity obligation at
  `<fully-qualified-behavior-id>.output` and one alternative obligation at
  `<fully-qualified-behavior-id>.output.<alternative-id>`.

For example:

```text
domains.email.features.triage.behaviors.importance_decision.output
domains.email.features.triage.behaviors.importance_decision.output.processing_failure
```

The exclusivity obligation verifies that exactly one alternative completes for an
evaluation. An alternative obligation verifies the observable statement and signal
emissions for that alternative. Bindings may assign different verification methods
and weights to the exclusivity contract and to each alternative.

Output statements do not use rule keywords as aliases. Rules remain separately
identified invariants, reactions remain signal consequences, and use cases remain
actor goals and scenarios.

## Canonical grammar

```text
identifier = [a-z][a-z0-9_]*
declared-signal-id = identifier resolving in the product signal registry
feature-or-behavior-id = fully qualified feature or behavior semantic path
architecture-decision-id = identifier resolving in the architecture registry
rule-map = the closed ID-keyed rule map defined by the language
reaction-map = the closed ID-keyed reaction map defined by the language
output-case = {
  statement: non-empty text,
  emits?: unique non-empty list[declared-signal-id]
}
output = output-case | {
  one_of: map[identifier, output-case] with 2..7 entries
}
behavior = {
  context?: unique list[non-empty text] with 1..7 items,
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
- component `purpose` is removed rather than renamed;
- component `inputs` becomes behavior `context`;
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
