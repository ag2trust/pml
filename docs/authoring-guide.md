# PML authoring guide

## Write product truth

Describe observable behavior:

```yaml
statement: THE SYSTEM MUST preserve accepted Assistant configuration across sessions.
```

Do not name endpoints, tables, files, functions, frameworks, or tests.

## Use the hierarchy consistently

```text
Domain → Feature → Behavior
```

A feature is a complete capability. A behavior is one bounded, independently
addressable product transition; behaviors do not nest and have no `purpose` or
other descriptive summary field.

## Describe transitions

Use the behavior fields to state when a transition applies, what starts one
evaluation, and how it completes:

```yaml
attention_handling:
  conditions:
    - The Inbox Item needs attention.
  trigger:
    statement: An authorized Member records a handling decision.
  outcome:
    statement: The Inbox Item is handled and no longer needs attention.
```

`conditions` is optional and contains the product state that must hold at the
instant of the trigger. If a condition does not hold, this behavior does not
apply; author a separate behavior if the product must respond to that case.

`trigger` is required. It is either one `statement`, one signal reference, or a
closed `one_of` map of alternatives. Each alternative occurrence starts a new
evaluation; trigger alternatives are not globally exclusive.

`outcome` is required. It is either one successful completion or a closed
`one_of` map of mutually exclusive successful completions. Use optional
`failures` for named unsuccessful completions that prevent the successful result.
An initiated evaluation completes exactly one outcome or authored failure.
Rejections and cancellations that do not prevent success are separate behaviors.

Do not use the superseded `context` or `output` fields.

## Connect behaviors with optional inline signals

A completion may define one optional inline signal. The defining outcome or
failure is the signal's authoritative producer; its ID is globally unique.

```yaml
outcome:
  statement: The Inbox Item is handled and no longer needs attention.
  signal:
    id: inbox_item_handled
    subject: inbox_item
    meaning: An Inbox Item has been handled.
```

`subject` is optional and, when present, names the declared product concept whose
one instance is preserved from producer to consumers. Omit it for a global
product occurrence. Signals are meaningful product occurrences, not required
messages, queues, callbacks, or other implementation events.

Consume the signal by authoring an ordinary behavior with `trigger.signal`:

```yaml
attention_view_update:
  trigger:
    signal: inbox_item_handled
  outcome:
    statement: The handled Inbox Item is absent from the needs-attention view.
```

Do not author a global `signals` registry, `emits` lists, or `reactions`.

## Write atomic obligations

Every rule statement contains `MUST` or `MUST NOT` and expresses one
independently verifiable invariant. Transition statements are normative by their
authored position and do not require those markers. Split distinct rules,
outcome alternatives, and failures into separate ID-keyed entries.

## Relate behavior without inventing control flow

Use `related_to` for a broader, symmetric association or change-impact relation
between a feature or behavior and another feature or behavior. Use fully qualified
semantic paths. It does not imply causality or execution order; signals and
triggers express causal relationships.

Keep `architecture` at feature scope. It records an owner-approved technical
constraint associated with a capability, not with an individual transition.

## Record architecture decisions independently

Use the optional top-level `architecture` registry only for a technical selection
that requires Owner approval even when product behavior would still be correct.
Each decision has a closed `category`, `selection`, `rationale`, and optional
ID-keyed normative `constraints`; reference its ID from the affected feature.
Do not put architecture on a behavior or use `applies_to`, `supports`, inline
definitions, or recursive decisions. Architecture does not name files, functions,
classes, tables, endpoints, configuration syntax, or topology.

## State use-case goals

Use cases remain at feature scope. Each has only an `actor`, a `goal`, and a
unique non-empty `behaviors` list of fully qualified behavior paths. The listed
behaviors are members of the actor's end-to-end goal, not ordered steps.

```yaml
use_cases:
  handle_inbox_item:
    actor: member
    goal: Handle an Inbox Item requiring attention.
    behaviors:
      - domains.inbox.features.attention.behaviors.inbox_item_opening
      - domains.inbox.features.attention.behaviors.attention_handling
      - domains.inbox.features.attention.behaviors.attention_view_update
```

Do not use the superseded `given`, `when`, `then`, or `otherwise` scenario fields.
The goal remains independently verifiable: verifying each listed behavior alone
does not prove the actor can accomplish it.

## Keep verification external

The compiler resolves authored transitions and rules into stable obligations.
Product-local bindings assign probe, agent, and human coverage. Generated state
stores evidence and derived confidence. Definitions never contain current scores
or verification procedures.
