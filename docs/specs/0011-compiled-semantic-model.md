# PML canonical compiled semantic model

Status: Owner approved on 2026-08-13

## Approved decision

Version 2 of the read-only compiled semantic model defined here is approved as the
single derived representation shared by PML reference resolution, obligation
enumeration, and downstream inspection tools. Version 2 supersedes the previously
approved version 1 to carry the surface-state and obligation shape changes owner
approved for task 16 (see the version 2 delta below); no other format-version 1
producers or consumers remain supported.

This specification does not change the PML language. It uses the behavior,
transition, signal, relationship, use-case, and obligation semantics approved in
[0010](0010-behavior-transition-model.md), as amended by
[0013](0013-bare-behavior-reference-normalization.md). It also approves the Unicode
scalar-string and string-key loading preconditions required for deterministic JSON
tooling; those preconditions are input well-formedness, not product meaning. It
does not authorize schema, validator, compiler, command, formatter, bindings,
probe, lock, state, or web UI implementation before owner approval. Owner approval
was given explicitly on 2026-08-13; implementation may now proceed in the delivery
order defined below.

## Purpose and authority boundary

PML YAML is the authored and authoritative statement of product intent. The
compiled semantic model is a deterministic, read-only index over one PML definition
with no error diagnostics. It makes identities and references explicit so every
consumer observes the same resolved model rather than independently interpreting
YAML.

Compilation MUST NOT:

- repair, default, rewrite, merge, broaden, narrow, or otherwise reinterpret
  authored intent;
- add language constructs, relationship types, lifecycle stages, workflow order,
  signal transport, or execution behavior;
- infer a behavior relationship from similar words or shared concepts;
- infer causal order from use-case membership or `related_to`;
- turn a signal into a separately verifiable obligation;
- combine generated state, bindings, evidence, implementation paths, or current
  conformance with the definition; or
- write to the definition, lock, bindings, state, or any other project artifact.

The model is not an alternative authoring format and cannot be approved or edited
in place. A change of product intent starts in PML YAML and passes normal owner
approval and validation before a new model may be compiled.

## Compilation boundary

Compilation operates on the single in-memory document produced by the
restricted-YAML loading and modular-document merge rules. The required pipeline is:

1. Load each authored source without aliases, duplicate keys, non-string mapping
   keys, Unicode surrogate code points, or implicit repairs, then merge the
   accepted source fragments.
2. Apply the exact schema and local language checks approved for the document's
   PML language version.
3. Apply the approved in-memory reference canonicalization from [0013](0013-bare-behavior-reference-normalization.md),
   then resolve declared identities and references while collecting the approved
   reference diagnostics.
4. Apply any remaining approved semantic checks that depend on the resolved
   graph.
5. Materialize and serialize the compiled model only when no diagnostic has
   `error` severity. Ordered `warning` diagnostics may accompany the model.

Schema validation and local language checks may run before reference resolution.
Reference validation and compilation SHOULD share one resolver so signal,
relationship, actor, concept, architecture, and behavior references cannot acquire
different meanings in different commands. Graph-dependent semantic checks may
operate on the resolver's internal candidate tables, but an invalid candidate is
never a compiled model and MUST NOT be exposed as one.

The input is validated and compiled as one snapshot. An implementation MUST NOT
validate one read of a source and compile a later read without validating it again.

### YAML string preconditions

Every YAML mapping key MUST decode to a string. This applies to every mapping at
every depth, including vocabulary terms, before modular merge or schema
validation. A key that decodes to a number, boolean, null, sequence, mapping, or
any other non-string value produces a `non-string-key` loading diagnostic. Loading
MUST NOT coerce the key to text or insert it into the in-memory document. The
diagnostic identifies the source location and decoded YAML type without using a
coerced key as a semantic path.

Every string decoded from YAML MUST consist only of Unicode scalar values:
U+0000 through U+D7FF or U+E000 through U+10FFFF. This requirement applies to
every mapping key and string value in every source fragment before modular merge,
not only to fields later copied into the compiled model.

If a decoded string contains any high or low surrogate code point from U+D800
through U+DFFF, loading produces an `invalid-unicode-scalar` diagnostic and the
source is not a valid PML document. This includes a surrogate introduced by a YAML
escape and adjacent escaped high and low surrogates. Loading MUST NOT replace a
surrogate, normalize it, discard it, or combine two surrogate code points into one
supplementary scalar. Authors express a supplementary character as that Unicode
scalar, directly or through a YAML escape that decodes to the scalar.

The diagnostic identifies the source location and offending code point using an
ASCII form such as `U+D800`; it MUST NOT reproduce a surrogate code point in
diagnostic output. This check occurs before schema validation, definition-digest
encoding, reference resolution, or compiled-model construction. It therefore
preserves the all-or-nothing result: an accepted document always has well-formed
UTF-8 and a rejected document never reaches compilation.

### Invalid input and unresolved references

Any loading, schema, language, duplicate-definition, or unresolved-reference
diagnostic with `error` severity prevents model production. In particular,
compilation MUST NOT emit:

- a partial model;
- placeholder actors, concepts, features, behaviors, signals, architecture
  decisions, or obligations;
- dangling string references;
- an empty consumer or producer substituted for a failed signal reference; or
- a best-effort graph with invalid nodes omitted.

The library result has a complete compiled model when it has no error diagnostics;
it may also carry normal ordered warning diagnostics. A result with one or more
error diagnostics has no compiled model. Warnings do not modify the model or its
digest. `pml compile --json` exits zero, writes warnings to standard error, and
writes JSON to standard output when warnings are the only diagnostics. It exits
nonzero, writes diagnostics to standard error, and writes no JSON to standard
output when an error diagnostic is present. `explain`, `graph`, and the web UI
MUST NOT expose a compiled model when an error diagnostic is present; their own
warning presentation and output policies do not alter this library boundary.

## Identity and reference rules

The compiled model does not define a second identity system:

- domains use `domains.<domain-id>`;
- features use `domains.<domain-id>.features.<feature-id>`;
- behaviors use
  `domains.<domain-id>.features.<feature-id>.behaviors.<behavior-id>`;
- use cases use
  `<fully-qualified-feature-id>.use_cases.<use-case-id>`;
- product rule obligations retain their approved scope paths;
- architecture decisions use `architecture.<decision-id>` and their constraints
  use the approved architecture obligation paths;
- inline signal IDs remain globally unique IDs; and
- actor IDs, concept IDs, and vocabulary terms retain their authored global
  identity categories.

Every cross-record reference in the model contains the canonical ID of an existing
record of the required category. Local IDs are included only on the record that
declares them; they are never accepted as shorthand for semantic paths.
Specifically, `id` is the declaring map key on domain, feature, behavior, use-case,
and architecture records, while `path` is that record's canonical semantic
identity. References to those records always use `path`. Globally declared actor,
concept, and signal records need only `id` because their authored IDs are already
their canonical identities.

Paths name semantic objects, not files. The compiled model contains no source file
paths or YAML layout metadata, so compiling the same merged definition as one file
or as an equivalent modular directory produces the same model.

## Version 2 delta

Version 2 replaces the previously approved version 1 grammar. Independent
compilers and consumers MUST emit and accept `format_version: 2` and MUST NOT
accept `format_version: 1` as a synonym; the two versions describe incompatible
`experience.surfaces` and obligation shapes. The version-2 changes are:

- `compiled-surface-state` is an object with optional `shows: list[obligation-id]`
  and optional `contains: list[authored-text]`, at least one of which is present.
  Version 1's mandatory `statements` list is removed.
- `compiled-obligation` gains an optional `surfaces: list[surface-state-path]`
  field that appears only on obligations of kind `rule`, `outcome`, or
  `failure`, and only when at least one surface state references the obligation
  through `shows`. All other obligation kinds omit it.
- Determinism adds one sort key: obligation `surfaces` lists are sorted by
  surface-state path.

Every other version-1 rule (identity, ordering, canonical JSON encoding,
definition digest, obligation inventory, closed enums) remains as approved.

## Version 2 JSON structure

Every object below is closed: implementations MUST NOT add unlisted properties.
Properties marked `?` are omitted when their authored value is absent; they are not
serialized as `null`. All top-level arrays are present, including when empty. JSON
strings preserve authored Unicode text exactly.

```text
compiled-model = {
  format: "pml.compiled",
  format_version: 2,
  language_version: "0.1-draft",
  definition_digest: sha256-digest,
  project: compiled-project,
  vocabulary: list[compiled-vocabulary-term],
  actors: list[compiled-actor],
  concepts: list[compiled-concept],
  architecture: list[compiled-architecture-decision],
  domains: list[compiled-domain],
  features: list[compiled-feature],
  behaviors: list[compiled-behavior],
  use_cases: list[compiled-use-case],
  signals: list[compiled-signal],
  relationships: list[compiled-relationship],
  use_case_memberships: list[compiled-use-case-membership],
  obligations: list[compiled-obligation]
}

compiled-project = {
  id: authored-project-id,
  name: authored-text,
  purpose: authored-text,
  rule_obligations: list[obligation-id],
  domains: list[domain-path]
}

compiled-vocabulary-term = {
  term: authored-term,
  meaning: authored-text,
  forbidden_synonyms: list[authored-text]
}

compiled-actor = {
  id: actor-id,
  meaning: authored-text
}

compiled-concept = {
  id: concept-id,
  meaning: authored-text,
  states: list[authored-text]
}

compiled-architecture-decision = {
  id: local-architecture-decision-id,
  path: architecture-decision-path,
  category: authored-category,
  selection: authored-text,
  rationale: authored-text,
  constraint_obligations: list[obligation-id],
  referenced_by: list[feature-path]
}

compiled-domain = {
  id: local-domain-id,
  path: domain-path,
  purpose: authored-text,
  rule_obligations: list[obligation-id],
  features: list[feature-path]
}

compiled-feature = {
  id: local-feature-id,
  path: feature-path,
  domain: domain-path,
  purpose: authored-text,
  actors: list[actor-id],
  rule_obligations: list[obligation-id],
  use_cases: list[use-case-path],
  behaviors: list[behavior-path],
  experience?: compiled-experience,
  related_to: list[feature-or-behavior-path],
  architecture: list[architecture-decision-path]
}

compiled-experience = {
  surfaces: list[compiled-surface]
}

compiled-surface = {
  id: surface-id,
  contains: list[authored-text],
  states: list[compiled-surface-state],
  accessibility: list[authored-text],
  responsive_behavior: list[authored-text]
}

compiled-surface-state = {
  id: state-id,
  shows?: list[obligation-id],
  contains?: list[authored-text]
}

compiled-behavior = {
  id: local-behavior-id,
  path: behavior-path,
  feature: feature-path,
  conditions?: compiled-conditions,
  trigger: compiled-trigger,
  completion_obligation: obligation-id,
  outcome: compiled-outcome,
  failures: list[compiled-failure],
  rule_obligations: list[obligation-id],
  related_to: list[feature-or-behavior-path],
  use_cases: list[use-case-path]
}

compiled-conditions = {
  statements: list[authored-text],
  obligation: obligation-id
}

compiled-trigger =
  {kind: "direct", case: compiled-direct-trigger-case}
  | {kind: "one_of", cases: list[compiled-trigger-alternative]}

compiled-direct-trigger-case = {
  obligation: obligation-id,
  statement: authored-text
} | {
  obligation: obligation-id,
  signal: signal-id
}

compiled-trigger-alternative = {
  id: trigger-alternative-id,
  obligation: obligation-id,
  statement: authored-text
} | {
  id: trigger-alternative-id,
  obligation: obligation-id,
  signal: signal-id
}

compiled-outcome =
  {kind: "direct", case: compiled-outcome-case}
  | {
      kind: "one_of",
      exclusivity_obligation: obligation-id,
      cases: list[compiled-outcome-alternative]
    }

compiled-outcome-case = {
  obligation: obligation-id,
  statement: authored-text,
  signal?: signal-id
}

compiled-outcome-alternative = {
  id: outcome-alternative-id,
  obligation: obligation-id,
  statement: authored-text,
  signal?: signal-id
}

compiled-failure = {
  id: failure-id,
  obligation: obligation-id,
  statement: authored-text,
  signal?: signal-id
}

compiled-use-case = {
  id: local-use-case-id,
  path: use-case-path,
  feature: feature-path,
  actor: actor-id,
  goal: authored-text,
  behaviors: list[behavior-path],
  obligation: obligation-id
}

compiled-signal = {
  id: signal-id,
  meaning: authored-text,
  subject?: concept-id,
  producer: {
    behavior: behavior-path,
    completion: obligation-id
  },
  consumers: list[{
    behavior: behavior-path,
    trigger: obligation-id
  }]
}

compiled-relationship = {
  kind: "related_to",
  endpoints: [feature-or-behavior-path, feature-or-behavior-path],
  declared_by: list[feature-or-behavior-path]
}

compiled-use-case-membership = {
  use_case: use-case-path,
  behavior: behavior-path
}

compiled-obligation = {
  id: obligation-id,
  node: product-node-path | architecture-decision-path,
  kind: obligation-kind,
  definition: obligation-definition,
  surfaces?: list[surface-state-path]
}

surface-state-path =
  "<feature-path>.experience.surfaces.<surface-id>.states.<state-id>"
```

The optional `surfaces` field appears only on `rule`, `outcome`, and `failure`
obligations that are referenced by one or more `experience.surfaces.<id>.states`
`shows` entries. Its value is the sorted list of referencing surface-state paths.
The other obligation kinds omit it.

The model has these consistency invariants:

- each authored domain, feature, behavior, use case, actor, concept, vocabulary
  term, architecture decision, inline signal, and normative rule or transition
  position produces exactly one corresponding record where this grammar defines
  one;
- every `path` and obligation `id` is unique in its category, and every
  cross-record reference resolves to exactly one record of the required category;
- each compiled signal's producer completion names that signal, and its consumer
  entries are exactly the trigger cases that reference it;
- the use-case behavior lists, `use_case_memberships`, and inverse behavior
  `use_cases` lists describe the same set of memberships;
- the normalized relationship set is exactly the symmetric projection of the
  resolved authored `related_to` lists; and
- the compiled obligation set is exactly the stable obligation set defined below,
  with no obligation inferred from descriptive text, hierarchy, a signal alone,
  or another compiled edge.

The `definition_digest` uses the already approved definition-digest algorithm,
made fully explicit here for the version 2 byte contract. After complete schema
and semantic validation, apply the approved reference canonicalization from
[0013](0013-bare-behavior-reference-normalization.md), then encode the resulting
canonical definition with this compact canonical definition JSON algorithm:

- A valid PML definition contains only objects, arrays, and strings. A value of
  any other JSON kind has already failed schema validation and MUST NOT be hashed.
- Encode an object as `{`, its properties, then `}`. Sort properties by their
  decoded key's Unicode scalar values using the lexical comparison defined below.
  Encode each property as the canonical encoded key string, `:`, and its recursively
  encoded value. Separate properties with `,`. Emit no whitespace. The empty object
  is `{}`.
- Encode an array as `[`, its recursively encoded elements in authored sequence
  order, then `]`. Separate elements with `,`. Emit no whitespace. The empty array
  is `[]`.
- Encode every key and string value with the exact string algorithm in
  [Canonical JSON encoding](#canonical-json-encoding): named escapes for quotation
  mark, reverse solidus, and the five named control characters; lowercase `\u00xx`
  for other U+0000 through U+001F controls; and direct UTF-8 for every other scalar,
  including solidus and non-ASCII scalars. No alternative JSON escape is allowed.
- Encode the top-level object directly as UTF-8 with no byte-order mark, leading or
  trailing whitespace, or final line feed.

Hash those exact bytes with SHA-256. The field value is `sha256:` followed by the
lowercase hexadecimal digest. This matches the established definition-digest
behavior while making it normative across independent compilers. It identifies
the authoritative input snapshot after its approved canonical reference
derivation; it does not make the compiled model authoritative. The string-key and
scalar-string loading checks precede this encoding, so every diagnostic-free
definition has a defined digest input.

### Structural records

The project, domain, and feature records preserve the hierarchy through canonical
references while allowing consumers to index each category directly. Their
`rule_obligations`, `constraint_obligations`, feature and behavior collections,
and architecture references point to existing records in the same compiled model.

Empty arrays normalize absent optional collections without inventing members. An
optional authored object such as `experience` or `conditions` remains omitted when
absent. Within a present experience definition, absent optional surface lists and
state maps compile to empty arrays. Each surface state omits `shows` or
`contains` when the corresponding authored key is absent; at least one is always
present. A `rule`, `outcome`, or `failure` obligation referenced by one or more
surface `shows` entries records the sorted list of referencing surface-state
paths in its optional `surfaces` field.

Architecture remains separate from product behavior. `referenced_by` is the
derived inverse of feature `architecture` references and may contain only feature
paths under the approved transition model. Each authored architecture decision ID
in a feature's `architecture` sequence resolves to the corresponding
`architecture.<decision-id>` path in `compiled-feature.architecture`; the compiled
array retains the authored sequence order. Architecture constraints remain
architecture obligations and do not become product obligations.

### Behaviors and transitions

Each behavior record preserves the exact approved transition shape:

- `conditions`, when present, contains every authored condition and its one
  collective applicability obligation;
- `trigger.kind` distinguishes the direct and `one_of` authored forms;
- every trigger case contains exactly one `statement` or resolved `signal` and
  the approved trigger obligation path;
- `completion_obligation` is always present and identifies the exactly-one
  successful-outcome-or-authored-failure obligation;
- `outcome.kind` distinguishes the direct and mutually exclusive `one_of` forms;
- an outcome `one_of` names its parent successful-alternative exclusivity
  obligation and each alternative's completion obligation;
- every failure is an independently identified authored unsuccessful completion;
  and
- a completion's optional `signal` is a reference to the compiled signal record
  produced by that same completion.

The model does not add trigger priority, a workflow, retry behavior, concurrency
control, or timing. A `one_of` trigger remains alternative initiating occurrences,
not an exclusivity obligation. Use-case membership and `related_to` remain
non-causal.

### Signals and causal edges

The top-level `signals` array is a derived index, not a restored authored signal
registry. Each record copies `id`, optional `subject`, and `meaning` from its one
authoritative inline definition. `producer.completion` identifies the outcome or
failure obligation whose required effect includes the signal.

Each `consumers` entry is derived from one direct or alternative signal trigger.
It names both the consuming behavior and that trigger's obligation. A signal may
have zero, one, or several consumers. Its producer is always singular because
duplicate inline signal IDs are invalid before compilation.

This index preserves all approved occurrence semantics from 0010: completion
creates exactly one occurrence for the optional subject instance, every consumer
is considered once for that occurrence, and failed conditions do not cause later
re-evaluation. The JSON adds no payload, transport, delivery, persistence, or
technical event interpretation.

### Signal coupling diagnostics

The owner-approved signal-coupling checks are advisory diagnostics derived only
from a complete version-2 compiled model. They add neither a PML construct nor a
compiled-model field, relationship, obligation, or causal edge. Warnings do not
prevent compilation or any read-only compiled-model consumer from receiving the
complete model.

For these diagnostics, a behavior's feature is its compiled `feature` path. A
feature consumes a signal when one of its behaviors is named by an entry in that
signal's `consumers` array. A signal's producer feature is the feature of its
`producer.behavior`.

- `PML-W-SIGNAL-FAN-IN` is a warning at a feature path when its behaviors
  consume signals produced by more than three distinct *other* features. A
  signal produced and consumed within the same feature is retained as a causal
  edge but never contributes to this count. Repeated behaviors or signals from
  one producer feature count once.
- `PML-W-SIGNAL-FAN-OUT` is a warning at a signal's
  `producer.completion` obligation path when that signal is consumed by
  behaviors in more than five distinct features. Each consumer feature counts
  once, including the producer's own feature when it consumes the signal.

Each qualifying feature or signal produces one warning. Coupling diagnostics are
ordered by diagnostic path and then code, using the compiled model's resolved
feature and behavior ownership rather than authored layout.

### Relationships and use-case membership

Feature and behavior `related_to` arrays preserve their resolved authored targets.
The top-level `relationships` array is the canonical symmetric graph projection.
Its two distinct endpoints are sorted lexically. Multiple reciprocal authored
references collapse to one edge, while `declared_by` records which endpoint or
endpoints actually authored the reference. No directed dependency or causality is
created.

`use_case_memberships` contains one record for every resolved item in a use case's
`behaviors` list. Each behavior's derived `use_cases` list provides the inverse
index. These are membership projections only. They carry no list position or
execution order, and they do not make behavior conformance sufficient proof of the
use-case goal.

## Stable obligations

Version 2 uses these closed `obligation-kind` values and definitions:

| `kind` | `definition` | Stable ID |
| --- | --- | --- |
| `conditions` | `{statements: list[authored-text]}` | `<behavior-path>.conditions` |
| `trigger` | `{statement: authored-text}` or `{signal: signal-id}` | direct: `<behavior-path>.trigger`; alternative: `<behavior-path>.trigger.<alternative-id>` |
| `completion` | `{outcomes: list[obligation-id], failures: list[obligation-id]}` | `<behavior-path>.completion` |
| `outcome_exclusivity` | `{alternatives: list[obligation-id]}` | `<behavior-path>.outcome` for `outcome.one_of` only |
| `outcome` | `{statement: authored-text, signal?: signal-id}` | direct: `<behavior-path>.outcome`; alternative: `<behavior-path>.outcome.<alternative-id>` |
| `failure` | `{statement: authored-text, signal?: signal-id}` | `<behavior-path>.failures.<failure-id>` |
| `rule` | `{statement: authored-text}` | `<scope-path>.rules.<rule-id>` |
| `use_case` | `{actor: actor-id, goal: authored-text, behaviors: list[behavior-path]}` | `<feature-path>.use_cases.<use-case-id>` |
| `architecture_constraint` | `{statement: authored-text}` | `architecture.<decision-id>.constraints.<constraint-id>` |

Every obligation object contains only the keys required by its row, plus the
optional `surfaces` field defined below. Its `node` is the owning project,
domain, feature, behavior, or architecture decision path. Project-wide rules use
`project` as their node and ID prefix.

Obligations of kind `rule`, `outcome`, and `failure` MAY carry an optional
`surfaces` field whose value is the sorted, unique list of surface-state paths
that reference the obligation through one `experience.surfaces.<id>.states.<id>`
`shows` entry. The field is present only when at least one such reference
exists, and every other obligation kind omits it. This is the inverse of the
authored `shows` reference and carries no independent obligation.

The completion definition lists the direct outcome obligation or every outcome
alternative obligation under `outcomes`, followed separately by every authored
failure obligation under `failures`. It represents exactly the 0010 rule that one
initiated evaluation completes exactly one member across those two lists. For an
`outcome.one_of`, the separate `outcome_exclusivity` obligation retains the
approved exclusivity among successful alternatives.

Condition statements remain one collective obligation. A `trigger.one_of` has no
parent exclusivity obligation. Signals remain required effects inside the
producing `outcome` or `failure` definition and have no independent obligation.
Use-case goals remain independently verifiable end to end. Existing scoped rules
and architecture constraints retain their approved paths and separation.

No verification method, weight, evidence, implementation status, or freshness is
part of a compiled obligation. Those remain in bindings and generated state.

## Determinism and ordering

Given the same validated merged definition and compiler format version, every
conforming compiler MUST produce byte-identical JSON.

The rules are:

1. Preserve every authored string code point for code point after YAML decoding.
   Do not trim, case-fold, Unicode-normalize, or reflow it.
2. Preserve authored sequence order in every array copied from an authored YAML
   sequence. The exhaustive set is:
   `vocabulary[].forbidden_synonyms`, `concepts[].states`, `features[].actors`,
   `features[].related_to`, `features[].architecture`, `behaviors[].related_to`,
   `features[].experience.surfaces[].contains`,
   `features[].experience.surfaces[].accessibility`,
   `features[].experience.surfaces[].responsive_behavior`,
   `features[].experience.surfaces[].states[].shows`,
   `features[].experience.surfaces[].states[].contains`,
   `behaviors[].conditions.statements`, and `use_cases[].behaviors`. The
   `conditions` and `use_case` obligation definitions preserve the same source
   sequence order. Consumers MUST still obey the approved semantics of each list;
   in particular, use-case behavior order does not imply execution order and
   condition order does not imply evaluation order.
3. Sort every array materialized from an ID-keyed authored map by the record key
   shown below. This rule applies recursively and does not depend on traversal or
   YAML mapping order:

   | Array | Sort key |
   | --- | --- |
   | top-level `vocabulary` | `term` |
   | top-level `actors` | `id` |
   | top-level `concepts` | `id` |
   | top-level `architecture` | `path` |
   | top-level `domains` | `path` |
   | top-level `features` | `path` |
   | top-level `behaviors` | `path` |
   | top-level `use_cases` | `path` |
   | top-level `signals` | `id` |
   | `experience.surfaces` | surface `id` |
   | `experience.surfaces[].states` | state `id` |
   | `trigger.cases` | alternative `id` |
   | `outcome.cases` | alternative `id` |
   | `behaviors[].failures` | failure `id` |
   | top-level `obligations` | obligation `id` |

4. Sort every array of references or records derived from maps, inverse indexes,
   or normalization by the exact key below:

   | Array | Sort key |
   | --- | --- |
   | `project.rule_obligations` | obligation ID |
   | `project.domains` | domain path |
   | `architecture[].constraint_obligations` | obligation ID |
   | `architecture[].referenced_by` | feature path |
   | `domains[].rule_obligations` | obligation ID |
   | `domains[].features` | feature path |
   | `features[].rule_obligations` | obligation ID |
   | `features[].use_cases` | use-case path |
   | `features[].behaviors` | behavior path |
   | `behaviors[].rule_obligations` | obligation ID |
   | `behaviors[].use_cases` | use-case path |
   | `signals[].consumers` | tuple `(behavior, trigger)` |
   | top-level `relationships` | tuple `(endpoints[0], endpoints[1])` |
   | top-level `use_case_memberships` | tuple `(use_case, behavior)` |
   | `completion` obligation `definition.outcomes` | obligation ID |
   | `completion` obligation `definition.failures` | obligation ID |
   | `outcome_exclusivity` obligation `definition.alternatives` | obligation ID |
   | obligation `surfaces` (rule/outcome/failure) | surface-state path |

   The authored reference arrays named in rule 2 retain authored order instead;
   this table does not reorder them merely because their entries are references.
5. Sort each symmetric relationship's two `endpoints` lexically before using the
   endpoint tuple as its identity and sort `declared_by` lexically by semantic
   path. Emit only one relationship record per endpoint pair.
6. These rules exhaust every array in version 2. A future format change that adds
   an array MUST assign it either source-sequence preservation or an explicit total
   sort key before that format version is approved.
7. Serialize the ordered model with the canonical JSON algorithm below. No other
   JSON layout or escape spelling conforms to version 2.
8. Do not include timestamps, source paths, machine paths, random identifiers,
   generated state, or environment-dependent values.

Lexical ordering compares Unicode scalar values without locale-sensitive
collation. PML IDs are ASCII, but the same rule also makes vocabulary-term ordering
deterministic.

Authored mappings have no semantic priority based on YAML key position. Authored
sequences are retained for faithful display, but this retention never adds order
semantics where the language defines none.

### Canonical JSON encoding

Encode the model recursively at an indentation depth beginning with zero. One
indentation unit is exactly two U+0020 SPACE characters. The output uses U+000A
LINE FEED for every line break, contains no U+FEFF byte-order mark, contains no
trailing spaces, and ends with exactly one line feed after the top-level value.

Emit values as follows:

- The version-2 model's only number is `format_version`, emitted as the single
  ASCII byte `2`. The model contains no booleans or nulls; absent optional
  properties are omitted as specified above.
- An empty object is `{}` and an empty array is `[]`.
- A non-empty object begins with `{`. For each property in Unicode scalar-value
  lexical key order, emit a line feed, one indentation unit per child depth, the
  encoded key string, `: `, and the recursively encoded value. Emit `,` immediately
  after every property value except the last. After the last property, emit a line
  feed, the current depth's indentation, and `}`. Thus every property occupies its
  own line, although a container value continues recursively from the opening `{`
  or `[` on that property line.
- A non-empty array follows the same layout with `[` and `]`: emit one element per
  line at one additional indentation depth and `,` immediately after every element
  except the last. A container element's opening `{` or `[` appears after that
  element's indentation on the same line.
- A string begins and ends with `"`. Process its Unicode scalar values in order.
  Encode U+0022 QUOTATION MARK as `\"`, U+005C REVERSE SOLIDUS as `\\`, U+0008 as
  `\b`, U+0009 as `\t`, U+000A as `\n`, U+000C as `\f`, and U+000D as `\r`.
  Encode every other scalar from U+0000 through U+001F as `\u00xx`, using lowercase
  hexadecimal digits. Emit every other scalar directly as its UTF-8 byte sequence,
  including U+002F SOLIDUS and all non-ASCII scalars; do not emit `\/`, surrogate-
  pair escapes, or optional Unicode escapes.

The punctuation in this algorithm is literal ASCII. There is exactly one space,
after `:`, between an object key and its value; there are no other insignificant
spaces. Object keys use the same string encoder as values. Ordering is determined
before escaping, so alternate spellings cannot affect sort order.

## Consumer contract

All consumers MUST check `format` and support the exact `format_version` before
reading records. They MUST treat unknown versions as unsupported rather than
guessing. They may select or render subsets, but may not reinterpret missing data
or manufacture nodes.

### `pml compile --json`

The command writes the complete versioned model to standard output. It is suitable
for automation, snapshots, and piping to other read-only tools. It performs no
state reconciliation and writes no files. Invalid definitions follow the
all-or-nothing diagnostic behavior above.

### `pml explain`

Explain resolves its requested canonical ID against the compiled indexes and shows
the authored text plus direct semantic links: owning hierarchy, transition cases,
producer or consumer signals, use-case memberships, symmetric relationships, and
stable obligations. It must distinguish authored fields from derived inverse
links and must not present a generated summary as approved intent.

For a feature record, explain also renders a `Derived coupling` section after the
derived inverse links. It is a read-only projection, not a field in the compiled
JSON model, with these fields in this order:

1. `signals_produced`: one entry per signal whose producer behavior belongs to
   the feature, ordered by signal ID, with `id` and `producer_behavior`.
2. `signals_consumed`: one entry per signal consumed by any behavior in the
   feature, ordered by signal ID, with `id` and `producer_feature`. A signal is
   listed once even if several behaviors in the feature consume it.
3. `distinct_producer_feature_count`: the number of distinct producer features
   in `signals_consumed`, excluding the explained feature itself. Thus this count
   is the fan-in count used by `PML-W-SIGNAL-FAN-IN`; same-feature consumption is
   visible in `signals_consumed` but does not increase the count.

### `pml graph`

Graph consumes only explicit compiled edges:

- directed producer-completion to signal to consumer-trigger edges;
- symmetric `related_to` edges; and
- use-case membership edges.

It must visually distinguish those three meanings. It must not derive workflow
order from use cases, direction from `related_to`, or a relationship from shared
actors, concepts, words, or hierarchy.

#### Approved DOT output contract

Owner approved on 2026-09-11.

`pml graph <manifest>` emits deterministic Graphviz DOT bytes to standard output
for the complete unfiltered explicit graph. It accepts no flags, filters,
alternate formats, renderer dependency, or file-output option. Invalid or
unsupported input emits diagnostics to standard error, exits nonzero, and
produces no standard output. It consumes only the complete supported compiled
model and never infers edges or reads state or evidence.

The graph name is `pml`. When the compiled model contains no explicit graph
edges, the exact output is:

```
digraph pml {
}
```

That output is two lines terminated by exactly one final line feed.

**Nodes.** Emit only nodes that participate in at least one edge, sorted
lexically by their compiled endpoint ID. Each node statement uses a double-quoted
node ID whose value equals the compiled endpoint ID. The `label` attribute
equals the node ID. Causal endpoints are the exact completion and trigger
obligation IDs from the compiled signal records; behavior paths must not
substitute for obligation endpoints.

**Edge order.** For each signal in compiled array order, emit the
completion-to-signal edge followed by each signal-to-consumer-trigger edge in
consumer array order. Then emit all relationships in compiled array order. Then
emit all use-case memberships in compiled array order. All edges use the `->`
DOT operator.

**Edge attributes.** Each edge meaning uses exactly these attributes in the
fixed alphabetical key order shown:

| Meaning | Attributes |
| --- | --- |
| Causal (completion→signal and signal→trigger) | `[kind="causal", style="solid"]` |
| Symmetric relationship | `[dir="none", kind="related_to", style="dashed"]` |
| Use-case membership | `[dir="none", kind="use_case_membership", style="dotted"]` |

Reciprocal authored `related_to` declarations between the same pair collapse to
one symmetric edge using the normalized endpoint pair from the compiled
`relationships` array. Use-case membership edges carry no order or direction.

**Layout.** Use two-space indentation. Place one statement per line. Terminate
every node and edge statement with a semicolon. End the output with exactly one
final line feed.

**Escaping.** Inside DOT double-quoted strings, escape `"` as `\"` and `\` as
`\\`. Emit all other characters directly as their UTF-8 bytes. Ordering is
determined before escaping.

#### Empty-graph example

A compiled model with no signals, relationships, or use-case memberships
produces:

```
digraph pml {
}
```

#### Representative non-empty example

Given a compiled model containing the signals, relationships, and use-case
memberships from the canonical conformance fixture, the exact output is:

```
digraph pml {
  "domains.a_work.features.workspace" [label="domains.a_work.features.workspace"];
  "domains.a_work.features.workspace.behaviors.a_start" [label="domains.a_work.features.workspace.behaviors.a_start"];
  "domains.a_work.features.workspace.behaviors.a_start.outcome.z_saved" [label="domains.a_work.features.workspace.behaviors.a_start.outcome.z_saved"];
  "domains.a_work.features.workspace.behaviors.a_start.trigger.z_ready" [label="domains.a_work.features.workspace.behaviors.a_start.trigger.z_ready"];
  "domains.a_work.features.workspace.behaviors.z_finish" [label="domains.a_work.features.workspace.behaviors.z_finish"];
  "domains.a_work.features.workspace.behaviors.z_finish.outcome" [label="domains.a_work.features.workspace.behaviors.z_finish.outcome"];
  "domains.a_work.features.workspace.use_cases.a_flow" [label="domains.a_work.features.workspace.use_cases.a_flow"];
  "domains.a_work.features.workspace.use_cases.z_flow" [label="domains.a_work.features.workspace.use_cases.z_flow"];
  "domains.z_archive.features.archive" [label="domains.z_archive.features.archive"];
  "record_ready" [label="record_ready"];
  "z_started" [label="z_started"];
  "domains.a_work.features.workspace.behaviors.z_finish.outcome" -> "record_ready" [kind="causal", style="solid"];
  "record_ready" -> "domains.a_work.features.workspace.behaviors.a_start.trigger.z_ready" [kind="causal", style="solid"];
  "domains.a_work.features.workspace.behaviors.a_start.outcome.z_saved" -> "z_started" [kind="causal", style="solid"];
  "domains.a_work.features.workspace" -> "domains.a_work.features.workspace.behaviors.z_finish" [dir="none", kind="related_to", style="dashed"];
  "domains.a_work.features.workspace" -> "domains.z_archive.features.archive" [dir="none", kind="related_to", style="dashed"];
  "domains.a_work.features.workspace.behaviors.a_start" -> "domains.a_work.features.workspace.behaviors.z_finish" [dir="none", kind="related_to", style="dashed"];
  "domains.a_work.features.workspace.behaviors.a_start" -> "domains.z_archive.features.archive" [dir="none", kind="related_to", style="dashed"];
  "domains.a_work.features.workspace.use_cases.a_flow" -> "domains.a_work.features.workspace.behaviors.a_start" [dir="none", kind="use_case_membership", style="dotted"];
  "domains.a_work.features.workspace.use_cases.z_flow" -> "domains.a_work.features.workspace.behaviors.a_start" [dir="none", kind="use_case_membership", style="dotted"];
  "domains.a_work.features.workspace.use_cases.z_flow" -> "domains.a_work.features.workspace.behaviors.z_finish" [dir="none", kind="use_case_membership", style="dotted"];
}
```

This example includes a signal with one consumer (`record_ready`), a
zero-consumer signal (`z_started`) that emits only its producer-to-signal edge,
four symmetric relationships, and three use-case memberships across two use
cases.

### Future web UI

The web UI consumes this same model for navigable project, domain, feature, and
behavior views; transition and signal details; use-case membership; relationship
and causal graphs; and stable obligation inspection. Validation findings with
`error` severity are a separate failed-compilation result, not nodes in a partial
compiled model. Warning diagnostics may accompany a complete model and are not
model nodes.

The UI is a read-only projection. Editing, approving, rewriting, or synchronizing
PML from the UI requires a separate language and workflow decision. Graphviz or
another free renderer may lay out the explicit graph but cannot add semantic
edges.

## Format evolution and delivery boundary

`format_version` versions this JSON contract independently from
`language_version`. Any change to its keys, closed enums, identity rules, ordering,
or field meanings requires a new format version and explicit owner approval. A
language revision also requires a new compiled format version when the current
structure cannot represent it without changing this contract.

With owner approval granted, delivery follows the repository order:

1. Add the `non-string-key` and `invalid-unicode-scalar` restricted-loading
   diagnostics without changing any other accepted syntax or validation outcome.
2. Add negative conformance cases for numeric, boolean, null, sequence, and mapping
   keys; escaped high and low surrogates; and adjacent escaped surrogate code
   points. Add a positive case containing a supplementary Unicode scalar.
3. Define the version 2 JSON Schema and shared in-memory types.
4. Refactor reference resolution and stable obligation enumeration to populate the
   model without changing validation outcomes.
5. Add compiled-model conformance fixtures plus deterministic serialization
   tests. Golden-byte cases MUST cover nested non-empty and empty objects and
   arrays, separator and indentation layout, an authored architecture reference,
   a behavior `related_to` array whose authored target order differs from lexical
   order, reordered authored maps, equivalent modular input, and authored strings
   containing quotation mark, reverse solidus, solidus, every named control escape,
   another U+0000–U+001F control, a basic non-ASCII scalar, and a supplementary
   scalar. A definition-digest golden case MUST independently fix the expected
   compact input bytes and digest for escape-sensitive authored text including a
   solidus, line feed, quotation mark, reverse solidus, and non-ASCII scalar.
6. Add `compile --json`, then build `explain`, `graph`, and the future web UI as
   read-only consumers.

Existing approved definitions and their validation behavior are the compatibility
oracle except for the approved string-key and scalar-string loading requirements
defined here. This specification authorizes those two syntax diagnostics before
compiled-model delivery; any other change to accepted language, diagnostics,
resolved paths, or obligation meaning requires separate owner approval.
