# PML repository instructions

PML is a language, not an open-ended documentation format.

## Authority

- Approved PML definitions are the authoritative statement of product intent.
- Generated state and evidence MUST NOT silently alter an approved definition.
- Language keywords and relationship types MUST be defined by the language spec.
- Agents MUST NOT introduce ad hoc document sections or synonyms.

## Development workflow

1. Change the language design.
2. Obtain owner approval for semantic changes.
3. Update the schema and semantic validator.
4. Add positive and negative conformance examples.
5. Update the formatter/compiler only after validation behavior is defined.

## Design constraints

- Prefer one canonical term for each concept.
- Prefer observable outcomes over implementation instructions.
- Keep authored definitions separate from generated state.
- Reject unknown keys and unresolved references.
- Do not encode filenames, functions, framework components, endpoints, or test names
  in normative product definitions.
- Do not treat implementation existence as proof of conformance.

## Authoring checklist

- Do not restate a behavior's condition, trigger, or outcome as a rule.
- Do not define the same term in vocabulary and again as a concept or actor.
- Do not put `MUST` or `MUST NOT` statements in experience surfaces.
- Do not write generic quantified rules without an actor or concept.
- Do not make behaviors mirror screens, endpoints, or code units.
- Do not move rules to a broader scope to evade a count; split the feature.
