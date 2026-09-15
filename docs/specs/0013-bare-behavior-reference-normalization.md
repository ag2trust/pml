# PML bare behavior reference normalization

Status: Owner approved
Approved direction: 2026-09-15

## Scope and authority

This specification approves bare behavior IDs as an additional authoring form for
same-feature behavior references. It supersedes the `related_to`, use-case
reference, and reference-grammar clauses of
[0010](0010-behavior-transition-model.md) and the compilation and
`definition_digest` clauses of [0011](0011-compiled-semantic-model.md) where
they conflict. All other approved language and compiled-model semantics remain
unchanged.

The bare form improves local authored definitions only. It does not add a new
semantic identity, relationship type, behavior category, or cross-feature
shortcut. The authored PML YAML remains authoritative; normalization is a
deterministic in-memory derivation used for reference resolution, compilation,
and definition digests.

## Reference forms and resolution

An `identifier` remains `[a-z][a-z0-9_]*`. A behavior reference is either a bare
`identifier` or a fully qualified behavior semantic path. A relationship reference
is either a bare `identifier` or a fully qualified feature or behavior semantic
path.

For `use_cases.<id>.behaviors`, a bare ID resolves to the behavior with that ID
in the enclosing feature. It is an error if that behavior is absent. A fully
qualified behavior path remains valid for same-feature references and is required
for cross-feature references.

For `related_to` on a feature, a bare ID resolves to the behavior with that ID in
the enclosing feature. For `related_to` on a behavior, a bare ID resolves to its
sibling behavior in the enclosing feature. A bare ID MUST NOT equal the ID of the
node declaring `related_to`; that is a self-reference error. Fully qualified
feature and behavior paths remain valid, and cross-feature references MUST be
fully qualified.

Every resolved target MUST exist in the required category. Uniqueness is evaluated
after resolution: a bare ID and a fully qualified path that resolve to the same
target in one `behaviors` or `related_to` list are a duplicate-reference error.

## Canonical form and definition digest

After structural validation accepts an authored definition and before reference
resolution, construct its canonical in-memory definition by replacing each bare
behavior reference with its corresponding fully qualified behavior path. Preserve
every other authored value and every array's authored order. The canonical
definition is not written back to the authored PML source.

The compiled model stores only these fully qualified canonical paths in use-case
behavior lists, `related_to` lists, memberships, relationships, and derived
obligation definitions. Before calculating `definition_digest`, apply the same
canonicalization to the merged definition, then encode and hash that canonical
definition under [0011](0011-compiled-semantic-model.md). Consequently, a valid
definition written with bare same-feature references has the same compiled model
and `definition_digest` as the equivalent definition written with fully qualified
paths.

## Delivery requirements

Schema validation MUST accept the two approved forms only for
`use_cases.<id>.behaviors` and `related_to`. Reference resolution MUST apply the
scope, absence, self-reference, and post-normalization uniqueness rules above.
Positive and negative conformance cases MUST cover bare resolution, missing local
targets, self-reference, duplicate normalized targets, fully qualified
cross-feature references, and digest equivalence.
