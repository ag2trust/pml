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

Each condition item is either a prose statement or a structured mapping
`{concept: <concept-id>, state: <state>}` naming one declared state of one
declared concept:

```yaml
conditions:
  - concept: inbox_item
    state: needs_attention
  - The Member is authorized to record decisions.
```

Prefer the structured form whenever the condition is exactly a concept state:
it lets tooling check the reference against declared `concepts.<id>.states`, and
`pml explain <concept>` lists which behaviors require each state. Two structured
conditions cannot name the same concept in one behavior — split the behavior
instead.

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

## Do not

AI authors often create duplicate obligations, competing definitions, or
implementation-shaped behaviors. Keep each statement in the language field that
owns its meaning, name product concepts and actors explicitly, and split
capabilities rather than relocating their complexity.

### Restate a transition as a rule

```yaml
# Wrong
rules:
  item_handled: {statement: An Inbox Item MUST be handled when a Member handles it.}

# Right
behaviors:
  item_handling:
    trigger: {statement: A Member records a handling decision.}
    outcome: {statement: The Inbox Item is handled.}
```

### Define a term twice

```yaml
# Wrong
vocabulary:
  Member: {meaning: A person who uses the product.}
actors:
  member: {meaning: An authenticated person with access.}

# Right
actors:
  member: {meaning: An authenticated person with access.}
```

This is rejected with `PML-E-VOCABULARY-DUPLICATE`.

### Put an obligation in an experience surface

```yaml
# Wrong
experience:
  surfaces:
    inbox: {contains: [The handled Inbox Item MUST be absent.]}

# Right
behaviors:
  attention_view_update:
    outcome: {statement: The handled Inbox Item is absent from the needs-attention view.}
```

### Use a generic quantifier with no subject

```yaml
# Wrong
rules:
  ownership: {statement: Customer ownership MUST be enforced for every affected resource.}

# Right
rules:
  ownership: {statement: A Member MUST access only Inbox Items belonging to the Member's Customer.}
```

### Mirror an implementation unit

```yaml
# Wrong
behaviors:
  inbox_screen:
    trigger: {statement: A Member opens the Inbox screen.}
    outcome: {statement: The Inbox screen is displayed.}

# Right
behaviors:
  inbox_item_opening:
    trigger: {statement: A Member selects an Inbox Item.}
    outcome: {statement: The selected Inbox Item is available for review.}
```

### Move rules up to evade a count

```yaml
# Wrong
domains:
  inbox:
    rules:
      preserve_read_state: {statement: An opened Inbox Item MUST retain whether it needs attention.}
    features:
      item_handling: {purpose: Handle Inbox Items.}

# Right
domains:
  inbox:
    features:
      item_opening:
        purpose: Open Inbox Items.
        rules:
          preserve_read_state: {statement: An opened Inbox Item MUST retain whether it needs attention.}
      item_handling: {purpose: Handle Inbox Items.}
```

## Relate behavior without inventing control flow

Use `related_to` for a broader, symmetric association or change-impact relation
between a feature or behavior and another feature or behavior. Use a bare behavior
ID for a target in the same feature, and a fully qualified semantic path otherwise.
It does not imply causality or execution order; signals and
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

## Point surfaces at obligations

`experience.surfaces` describes where actors perceive product state. Each
`states.<id>` value is an object with optional `shows` and optional `contains`;
at least one is required. Use `shows` to reference the obligation the state
reflects, so the surface never repeats a `MUST`, `MUST NOT`, `SHALL`, or `SHOULD`
statement:

```yaml
experience:
  surfaces:
    creation_flow:
      contains:
        - Assistant identity input.
        - Creation action.
      states:
        submitting:
          contains:
            - Progress indication.
        failure:
          shows:
            - behaviors.assistant_creation.failures.rejected
```

Each `shows` entry may be a fully qualified obligation path anywhere in the
definition, a feature-relative path (e.g. `rules.<rule-id>` or
`behaviors.<behavior-id>.failures.<failure-id>`), a behavior-relative path
(dropping the leading `behaviors.`), or a bare last-segment ID that
unambiguously names one obligation in the enclosing feature. Two entries that
resolve to the same obligation are rejected as duplicates.

## State use-case goals

Use cases remain at feature scope. Each has only an `actor`, a `goal`, and a
unique `behaviors` list of one through seven behavior references. Use bare IDs for
behaviors in the same feature and fully qualified paths across features. The listed
behaviors are members of the actor's end-to-end goal, not ordered steps.

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

Do not use the superseded `given`, `when`, `then`, or `otherwise` scenario fields.
The goal remains independently verifiable: verifying each listed behavior alone
does not prove the actor can accomplish it.

## Keep verification external

The compiler resolves authored transitions and rules into stable obligations.
Product-local bindings assign probe, agent, and human coverage. Generated state
stores evidence and derived confidence. Definitions never contain current scores
or verification procedures.
