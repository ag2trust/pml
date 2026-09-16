# PML behavior transition model

Status: Owner approved
Approved direction: 2026-08-11

## Scope

This specification defines the approved transition semantics for PML behaviors.
It supersedes the behavior structure, behavior architecture scope, signal
registry and emission model, reactions, and use-case scenario structure in
[0001](0001-language-design.md), [0004](0004-language-normalization.md),
[0006](0006-architecture-decisions.md), and
[0009](0009-behavior-units-and-outputs.md) where they conflict with this
specification. Existing schema, validator, examples, formatter, compiler, and
generated-state behavior remain unchanged until migrated in the required delivery
order below.

## Approved semantics

### Behavior structure

A behavior is one bounded, independently addressable product transition. It has
no descriptive, `purpose`, or `intent` field. Its semantic fields should make the
behavior understandable without a redundant summary.

The closed shape is:

```text
behavior = {
  conditions?: conditions,
  trigger: trigger,
  outcome: outcome,
  failures?: failure-map,
  rules?: rule-map,
  related_to?: unique non-empty list[feature-or-behavior-id]
}
```

- `conditions` describes relevant product state that must hold when the behavior
  is initiated. It is optional. Each condition item is either a prose statement
  or a closed structured mapping `{concept: <concept-id>, state: <state>}` naming
  one declared state of one declared concept. Two structured conditions in one
  behavior MUST NOT name the same concept.
- `trigger` identifies what initiates one behavior evaluation. It is required.
- `outcome` identifies successful completion. It is required.
- `failures` identifies authored unsuccessful completions. It is optional.
- `rules` contains invariants local to the behavior. It remains optional.

The prior `context` and `output` fields are replaced by `conditions` and
`outcome` respectively.

All authored conditions MUST hold when the trigger occurs. If any condition does
not hold, the behavior does not apply and no evaluation begins. A product response
required for that situation is modeled as a separate behavior rather than as a
failure of an inapplicable behavior.

### Triggers

A trigger is either one direct trigger or a closed, ID-keyed `one_of` map of
alternative triggers. A direct trigger is expressed by a statement or a declared
product signal.

```yaml
trigger:
  statement: An authorized Member records a handling decision.
```

```yaml
trigger:
  signal: inbox_item_expired
```

```yaml
trigger:
  one_of:
    member_decision:
      statement: An authorized Member records a handling decision.
    automatic_expiration:
      signal: inbox_item_expired
```

Each occurrence of an alternative trigger initiates a behavior evaluation.
`one_of` does not mean that the alternatives can occur only once globally.

### Outcomes and failures

An outcome is either one direct outcome or a closed, ID-keyed `one_of` map of
mutually exclusive successful alternatives. Every direct outcome or outcome
alternative requires one local `statement` and may define one signal, an optional
bounded product-state `transitions` map, or both.

Optional `failures` is a closed, ID-keyed map of authored unsuccessful
completions. Every failure requires one local `statement` and may define one
signal, an optional bounded product-state `transitions` map, or both. Rejections
and cancellations belong in `failures` only when they prevent the behavior's
successful result; otherwise they are separate behaviors.

Each initiated evaluation MUST complete exactly one successful outcome or one
authored failure. Completing none or more than one is nonconformant. A correctly
produced authored failure is conformant.

### Completion state transitions

A direct outcome, outcome alternative, or failure may define `transitions`: a
map of at most three concept IDs to `"<from> -> <to>"` strings. `from` is one
declared state of the named concept, `*` for any state, or `none` when the
instance comes into existence. `to` is one declared state or `none` when the
instance ceases to exist. `from` and `to` MUST differ. A completion may define
both an inline signal and `transitions`. A declared state is a non-empty state
token that is neither `*` nor `none`, does not contain ` -> `, does not begin
`-> `, and does not end ` ->`; the sentinels and separator fragments are reserved
so transition endpoints have one interpretation.
State tokens cannot contain line-break characters, so state graph output remains
single-line.

Transitions are completion-owned product semantics. They do not define
persistence, messaging, workflow order, or an implementation mechanism. Each
transition is verified as part of its owning completion obligation and creates no
separate obligation path. The validator rejects unknown concepts and undeclared
states, and derives reachability warnings from all completion transitions in the
definition.

```yaml
outcome:
  statement: The Inbox Item is handled and no longer needs attention.
  signal:
    id: inbox_item_handled
    subject: inbox_item
    meaning: An Inbox Item has been handled.
```

Several successful alternatives use `outcome.one_of`:

```yaml
outcome:
  one_of:
    immediately_available:
      statement: The purchased Credits are immediately available.
    pending_settlement:
      statement: The purchase is accepted and pending settlement is visible.
```

Unsuccessful alternatives are separate from the successful outcome:

```yaml
failures:
  declined:
    statement: The Payment remains unpaid and the decline is visible.
    signal:
      id: payment_declined
      subject: payment
      meaning: A Payment has been declined.
  processing_error:
    statement: The Payment remains unpaid and an actionable failure is visible.
```

This structure makes the successful result explicit without an `expected`
marker, boolean, or universal failure taxonomy.

### Transition obligations

Transition fields are normative by their authored position and resolve into
stable obligations without repeating their statements as rules:

- optional conditions resolve together at
  `<fully-qualified-behavior-id>.conditions`; this obligation verifies that all
  authored conditions gate applicability;
- a direct trigger resolves at `<fully-qualified-behavior-id>.trigger`;
- each `trigger.one_of` alternative resolves at
  `<fully-qualified-behavior-id>.trigger.<alternative-id>`; the parent trigger
  has no exclusivity obligation because different trigger occurrences may each
  initiate an evaluation;
- every behavior resolves one completion-exclusivity obligation at
  `<fully-qualified-behavior-id>.completion`, verifying that each initiated
  evaluation completes exactly one outcome or authored failure;
- a direct outcome resolves at `<fully-qualified-behavior-id>.outcome`;
- `outcome.one_of` resolves successful-alternative exclusivity at
  `<fully-qualified-behavior-id>.outcome` and each alternative at
  `<fully-qualified-behavior-id>.outcome.<alternative-id>`; and
- each failure resolves at
  `<fully-qualified-behavior-id>.failures.<failure-id>`.

A signal or completion state transition is a required effect of the outcome or
failure that defines it and is verified as part of that completion obligation;
neither creates a separate obligation. Existing rule obligation paths remain
unchanged.

### Signals

Every direct outcome, outcome alternative, or failure contains either no `signal`
field or one inline `signal` definition. A signal is therefore optional; PML does
not require every completion or behavior to produce one. When present, its closed
definition contains `id`, optional `subject`, and `meaning`. The separate product
signal registry and prior plural `emits` lists are removed.

```yaml
signal:
  id: inbox_item_handled
  subject: inbox_item
  meaning: An Inbox Item has been handled.
```

An optional `subject` MUST reference one declared product concept and identifies
the primary concept concerned. It cannot reference an actor, feature, behavior, or
ad hoc object category. Each occurrence preserves the identity of one subject
instance between its producer and consumers. Global signals omit `subject`. This
product-level correlation does not prescribe a payload, identifier representation,
message, or transport.

An inline signal definition is the authoritative producer for its globally unique
signal ID. Signal references resolve to that definition, and the signal may trigger
multiple consuming behaviors. This producer rule applies only when a signal is
authored; it does not require a signal to exist.

Completing an outcome or failure containing a signal creates exactly one occurrence
of that signal for its subject. Each consuming behavior is considered once for
each occurrence, and its conditions are evaluated at that occurrence. If its
conditions do not hold, it does not evaluate later merely because they subsequently
become true.

Signals remain meaningful product occurrences, not required implementation events,
messages, queues, callbacks, persistence, or delivery infrastructure. An outcome
signal may be used as the trigger of another behavior, producing a directed causal
behavior graph.

```text
conditions + trigger -> outcome or failure -> optional signal -> another behavior trigger
```

### Reactions

The `reactions` construct is removed. A signal consequence is represented
as an ordinary behavior whose trigger references that signal. This provides one
canonical representation instead of overlapping reactions and signal-triggered
behaviors.

### Relationships and architecture

`related_to` remains a valid optional behavior field. It preserves the approved
untyped, symmetric relationship semantics and may reference features or other
behaviors. Its approved bare same-feature behavior form and canonical resolution
are defined by [0013](0013-bare-behavior-reference-normalization.md). It expresses
broader product association and change impact; it does not imply causality or
execution order.

`architecture` is not a valid behavior field and remains a feature-level
concern:

- signals express precise directed causal relationships among behaviors;
- feature- and behavior-level `related_to` express broader symmetric product
  relationships; and
- feature-level `architecture` associates approved technical constraints with a
  capability without attaching them to individual transitions.

### Experience and use cases

`experience` remains at feature scope because one persistent surface commonly
supports several behaviors. Behavior-specific visible changes belong in behavior
outcomes or rules.

`use_cases` remain at feature scope and contain only `actor`, `goal`, and a unique
non-empty list of behavior references. A use case states the actor requirement PML
aims to fulfill; its referenced behaviors collectively fulfill that goal.

Behavior references use the approved authored and canonical forms defined by
[0013](0013-bare-behavior-reference-normalization.md). Each reference MUST resolve
to a declared behavior.

The behavior list expresses membership, not execution order. Trigger and signal
relationships express causal order. The use-case goal remains an independently
verifiable end-to-end obligation; conformance of each referenced behavior does not
by itself prove that the actor can accomplish the goal.

```yaml
use_cases:
  handle_inbox_item:
    actor: member
    goal: Handle an Inbox Item requiring attention.
    behaviors:
      - inbox_item_opening
      - attention_handling
      - attention_view_update
```

## Consolidated example

```yaml
attention_handling:
  conditions:
    - The Inbox Item needs attention.

  trigger:
    one_of:
      member_decision:
        statement: An authorized Member records a handling decision.
      automatic_expiration:
        statement: The Inbox Item reaches its handling expiration.

  outcome:
    statement: The Inbox Item is handled and no longer needs attention.
    signal:
      id: inbox_item_handled
      subject: inbox_item
      meaning: An Inbox Item has been handled.

  rules:
    read_is_not_handled:
      statement: Opening an Inbox Item MUST leave whether it needs attention unchanged.
```

```yaml
attention_view_update:
  conditions:
    - The handled Inbox Item appears in the needs-attention view.

  trigger:
    signal: inbox_item_handled

  outcome:
    statement: The handled Inbox Item is absent from the needs-attention view.
```

## Closed grammar

```text
identifier = [a-z][a-z0-9_]*
statement = non-empty text
state-token = non-empty single-line text excluding "*", "none", the substring
  " -> ", the prefix "-> ", and the suffix " ->"
declared-actor-id = identifier resolving to one declared actor
concept-id = identifier resolving to one declared product concept
declared-signal-id = identifier resolving to one inline signal definition
feature-or-behavior-id = fully qualified feature or behavior semantic path
behavior-id = fully qualified behavior semantic path
behavior-reference = identifier | behavior-id, resolved under 0013
relationship-reference = identifier | feature-or-behavior-id, resolved under 0013
rule-map = the closed ID-keyed rule map defined by the language

condition-item = statement | {concept: concept-id, state: state-token}
conditions = unique list[condition-item] with 1..7 items,
  no two structured items sharing the same concept
direct-trigger = {statement: statement} | {signal: declared-signal-id}
trigger = direct-trigger | {
  one_of: map[identifier, direct-trigger] with 2..7 entries
}
signal = {
  id: globally unique identifier,
  subject?: concept-id,
  meaning: non-empty text
}
completion-case = {
  statement: statement,
  signal?: signal,
  transitions?: transition-map
}
outcome = completion-case | {
  one_of: map[identifier, completion-case] with 2..7 entries
}
failure-map = map[identifier, completion-case] with 1..7 entries
transition-from = declared state-token of the named concept | "*" | "none"
transition-to = declared state-token of the named concept | "none"
state-transition = "<transition-from> -> <transition-to>", with distinct endpoints
transition-map = map[concept-id, state-transition] with at most 3 entries
behavior-reference-list = unique list[behavior-reference] with 1..7 items
relationship-list = unique list[relationship-reference] with 1..7 items
behavior = {
  conditions?: conditions,
  trigger: trigger,
  outcome: outcome,
  failures?: failure-map,
  rules?: rule-map,
  related_to?: relationship-list
}
use-case = {
  actor: declared-actor-id,
  goal: non-empty text,
  behaviors: behavior-reference-list
}
```

Every object is closed and rejects unknown keys. Direct and `one_of` trigger or
outcome forms are mutually exclusive. Every list is non-empty when present and
rejects duplicate values. Every ID-keyed map rejects duplicate IDs and every
reference MUST resolve to the required canonical object category. Reference
uniqueness after canonical resolution is defined by [0013](0013-bare-behavior-reference-normalization.md).

A structured condition item names one declared concept state exactly; it does
not encode workflow or ordering, and it never replaces outcomes or failures.
Completion-owned `transitions` is the sole structured lifecycle construct: it
records a declared concept state change as a completion effect without defining a
workflow. Other structured lifecycle or ordering fields remain rejected because
they duplicate conditions, completion transitions, or outcomes. No general
workflow or ordering construct is planned; signal-to-trigger relationships already
express required causal order.
Time and quantity requirements remain precise authored statements or rules unless
real product definitions demonstrate a need for structured scalar types.

Retry and concurrency requirements likewise remain observable conditions,
outcomes, failures, or rules. PML does not add retry counts, locks, queues,
scheduling, or execution-control fields. A future structured construct requires a
separate language decision supported by a product requirement that cannot be
stated precisely through the existing transition fields and rules.

## Migration guidance

Migration may be performed with agent assistance and adapted to each approved
definition, but it is never an automatic reinterpretation of owner intent. An
agent may propose rewritten behaviors, reference mappings, bindings, and probes;
the owner approves the changed definition and verification policy.

The migration must account explicitly for these semantic changes:

- `context` becomes applicability `conditions`, not a mechanical rename when an
  existing item does not actually gate behavior;
- successful `output` statements move to `outcome`, while unsuccessful alternatives
  move to `failures` only when the owner confirms that classification;
- global signal definitions and `emits` references move to optional inline signal
  definitions and signal triggers;
- reactions become independently identified behaviors when their consequence is
  retained; and
- renamed, removed, or newly introduced obligation paths require explicit updates
  to bindings and probes.

An approved migrated definition requires a new lock. Generated state is reconciled
against the new semantic and obligation paths. Evidence is not reassigned to a new
or renamed obligation merely because an agent considers it similar; unmatched old
state becomes removed or stale under the approved synchronization semantics.

## Required delivery order

Delivery follows the repository workflow:

1. Amend the language design and establish the exact grammar and semantics.
2. Update the schema and semantic validator.
3. Add positive and negative conformance examples.
4. Update obligation resolution, bindings, probes, formatter, compiler, and state
   behavior only after validation behavior is defined.

No compatibility aliases should be introduced unless separately approved.
