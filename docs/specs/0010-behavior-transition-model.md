# Behavior transition model

Status: Discussion draft; not owner approved

## Scope

This document records the current design direction for PML behaviors so the
discussion can continue without treating these decisions as implemented or
authoritative language semantics. It does not amend the approved language,
schema, validator, examples, formatter, compiler, or generated state.

## Current decisions

### Behavior structure

A behavior is one bounded, independently addressable product transition. It has
no descriptive, `purpose`, or `intent` field. Its semantic fields should make the
behavior understandable without a redundant summary.

The proposed closed shape is:

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
  is initiated. It is optional.
- `trigger` identifies what initiates one behavior evaluation. It is required.
- `outcome` identifies successful completion. It is required.
- `failures` identifies authored unsuccessful completions. It is optional.
- `rules` contains invariants local to the behavior. It remains optional.

The current `context` and `output` fields would be replaced by `conditions` and
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
alternative requires one local `statement` and may define one signal.

Optional `failures` is a closed, ID-keyed map of authored unsuccessful
completions. Every failure requires one local `statement` and may define one
signal. Rejections and cancellations belong in `failures` only when they prevent
the behavior's successful result; otherwise they are separate behaviors.

Each initiated evaluation MUST complete exactly one successful outcome or one
authored failure. Completing none or more than one is nonconformant. A correctly
produced authored failure is conformant.

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

A signal is a required effect of the outcome or failure that defines it and is
verified as part of that completion obligation; it does not create a separate
obligation. Existing rule obligation paths remain unchanged.

### Signals

Every direct outcome, outcome alternative, or failure contains either no `signal`
field or one inline `signal` definition. A signal is therefore optional; PML does
not require every completion or behavior to produce one. When present, its closed
definition contains `id`, optional `subject`, and `meaning`. The separate product
signal registry and current plural `emits` lists would be removed.

```yaml
signal:
  id: inbox_item_handled
  subject: inbox_item
  meaning: An Inbox Item has been handled.
```

An optional `subject` references the primary product concept concerned. Each
occurrence preserves the identity of one subject instance between its producer
and consumers. Global signals omit `subject`. This product-level correlation does
not prescribe a payload, identifier representation, message, or transport.

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

The `reactions` construct would be removed. A signal consequence is represented
as an ordinary behavior whose trigger references that signal. This provides one
canonical representation instead of overlapping reactions and signal-triggered
behaviors.

### Relationships and architecture

`related_to` remains a valid optional behavior field. It preserves the approved
untyped, symmetric relationship semantics and may reference features or other
behaviors using their fully qualified semantic paths. It expresses broader product
association and change impact; it does not imply causality or execution order.

`architecture` would not be a valid behavior field and remains a feature-level
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

## Open design questions

The following points were identified but have not been decided:

- the exact syntax for referencing local and cross-feature behaviors from use
  cases;
- whether signal `subject` may reference only declared concepts or another
  canonical product-object category;
- retry and concurrency requirements that cannot be stated precisely as rules;
- the exact size bounds and validation rules for `conditions` and `one_of` maps.

Structured lifecycle transition fields were considered and rejected because they
would duplicate conditions and outcomes. No general workflow or ordering construct
is planned; signal-to-trigger relationships already express required causal order.
Time and quantity requirements remain precise authored statements or rules unless
real product definitions demonstrate a need for structured scalar types.

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

## Required delivery order after approval

If this design is owner approved, delivery follows the repository workflow:

1. Amend the language design and establish the exact grammar and semantics.
2. Update the schema and semantic validator.
3. Add positive and negative conformance examples.
4. Update obligation resolution, bindings, probes, formatter, compiler, and state
   behavior only after validation behavior is defined.

No compatibility aliases should be introduced unless separately approved.
