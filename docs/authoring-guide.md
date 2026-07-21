# PML authoring guide

## Write product truth, not implementation

Describe what actors observe and which constraints remain true.

Good:

```yaml
statement: WHEN creation succeeds, THE SYSTEM MUST preserve the Assistant configuration across later sessions.
```

Avoid:

```yaml
statement: The POST endpoint must insert a row and return HTTP 201.
```

Endpoints, tables, files, functions, frameworks, and test names belong in generated
implementation mappings or evidence—not the authoritative definition.

## Use one canonical term

Define terms whose meaning matters and forbid confusing synonyms:

```yaml
vocabulary:
  Member:
    meaning: An authenticated person belonging to one Customer.
    forbidden_synonyms:
      - user
      - customer user
```

Use the exact canonical term everywhere afterward.

## Write one obligation per rule

Use `MUST` or `MUST NOT`:

```text
<Actor> MUST <observable behavior>.
<Actor> MUST NOT <forbidden behavior>.
WHEN <event>, THE SYSTEM MUST <observable outcome>.
IF <condition>, THE SYSTEM MUST <observable outcome>.
ON FAILURE, THE SYSTEM MUST <observable recovery or result>.
```

Avoid `should`, `normally`, `properly`, `appropriately`, `seamlessly`, `relevant`, and
`etc.` Replace them with behavior that a verifier can observe.

## Separate rules from use cases

A rule is always true within its scope:

```yaml
statement: A Member MUST access only Assistants owned by the Member's Customer.
```

A use case connects preconditions, action, and outcome:

```yaml
actor: member
goal: Create an Assistant.
given:
  - The Member is authenticated.
when:
  - The Member submits valid configuration.
then:
  - A usable Assistant exists.
otherwise:
  - No partial Assistant remains.
```

## Describe complete behavior

For each feature, consider:

- success and failure outcomes;
- ownership and permissions;
- persistence and lifecycle transitions;
- visible empty, loading, success, and failure states;
- effects on other components;
- recovery behavior;
- functional and non-functional requirements;
- what evidence would demonstrate conformance.

Do not add a section merely to fill a template. Add detail when omitting it would let
two materially different behaviors both appear conforming.

## Use recursive components sparingly

Components allow arbitrary semantic depth:

```yaml
components:
  configuration:
    purpose: Capture the behavior assigned to an Assistant.
    components:
      instructions:
        purpose: Define how the Assistant behaves.
        rules:
          persistence:
            statement: THE SYSTEM MUST preserve accepted Instructions across later sessions.
            severity: high
```

Stop decomposing when the parent rules and outcomes remove meaningful ambiguity. Never
mirror source-code directories or UI framework component trees.

## Keep generated facts outside PML

Implementation mappings, tests, current state, evidence, PRs, commits, models, effort,
and history reference PML IDs but live in separate structures. Code-to-PML analysis may
propose changes or report inconsistencies; it cannot rewrite approved intent.

