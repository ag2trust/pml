# PML canonical compiled semantic model

Status: Proposed — owner approval required

## Decision requested

Approve version 1 of the read-only compiled semantic model defined here as the
single derived representation shared by PML reference resolution, obligation
enumeration, and downstream inspection tools.

This specification does not change the PML language. It uses the behavior,
transition, signal, relationship, use-case, and obligation semantics approved in
[0010](0010-behavior-transition-model.md) exactly. It does not authorize schema,
validator, compiler, command, formatter, bindings, probe, lock, state, or web UI
implementation before owner approval.

## Purpose and authority boundary

PML YAML is the authored and authoritative statement of product intent. The
compiled semantic model is a deterministic, read-only index over one completely
validated PML definition. It makes identities and references explicit so every
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

Compilation operates on the single in-memory document produced by the existing
restricted-YAML loading and modular-document merge rules. The required pipeline is:

1. Load and merge the authored definition without aliases, duplicate keys, or
   implicit repairs.
2. Apply the exact schema and local language checks approved for the document's
   PML language version.
3. Resolve declared identities and references against that same in-memory
   document while collecting the approved reference diagnostics.
4. Apply any remaining approved semantic checks that depend on the resolved
   graph.
5. Materialize and serialize the compiled model only when the complete diagnostic
   set is empty.

Schema validation and local language checks may run before reference resolution.
Reference validation and compilation SHOULD share one resolver so signal,
relationship, actor, concept, architecture, and behavior references cannot acquire
different meanings in different commands. Graph-dependent semantic checks may
operate on the resolver's internal candidate tables, but an invalid candidate is
never a compiled model and MUST NOT be exposed as one.

The input is validated and compiled as one snapshot. An implementation MUST NOT
validate one read of a source and compile a later read without validating it again.

### Invalid input and unresolved references

Any loading, schema, language, duplicate-definition, or unresolved-reference
diagnostic prevents model production. In particular, compilation MUST NOT emit:

- a partial model;
- placeholder actors, concepts, features, behaviors, signals, architecture
  decisions, or obligations;
- dangling string references;
- an empty consumer or producer substituted for a failed signal reference; or
- a best-effort graph with invalid nodes omitted.

The library result is either a complete compiled model or the normal ordered
validation diagnostics, never both. A future `pml compile --json` command exits
nonzero, writes diagnostics to standard error, and writes no JSON to standard
output when validation fails. `explain`, `graph`, and the web UI observe the same
all-or-nothing boundary.

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
- actor IDs, concept IDs, architecture decision IDs, and vocabulary terms retain
  their authored global identity categories.

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

## Version 1 JSON structure

Every object below is closed: implementations MUST NOT add unlisted properties.
Properties marked `?` are omitted when their authored value is absent; they are not
serialized as `null`. All top-level arrays are present, including when empty. JSON
strings preserve authored Unicode text exactly.

```text
compiled-model = {
  format: "pml.compiled",
  format_version: 1,
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
  architecture: list[architecture-decision-id]
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
  statements: list[authored-text]
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
  definition: obligation-definition
}
```

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

The `definition_digest` uses the already approved definition-digest algorithm:
`sha256:` plus the lowercase SHA-256 digest of the validated, merged document's
UTF-8 JSON encoding with object keys sorted, arrays retained, non-ASCII text
encoded directly, and no insignificant whitespace. It identifies the authoritative
input snapshot; it does not make the compiled model authoritative.

### Structural records

The project, domain, and feature records preserve the hierarchy through canonical
references while allowing consumers to index each category directly. Their
`rule_obligations`, `constraint_obligations`, feature and behavior collections,
and architecture references point to existing records in the same compiled model.

Empty arrays normalize absent optional collections without inventing members. An
optional authored object such as `experience` or `conditions` remains omitted when
absent. Within a present experience definition, absent optional surface lists and
state maps compile to empty arrays.

Architecture remains separate from product behavior. `referenced_by` is the
derived inverse of feature `architecture` references and may contain only feature
paths under the approved transition model. Architecture constraints remain
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

Version 1 uses these closed `obligation-kind` values and definitions:

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

Every obligation object contains only the keys required by its row. Its `node` is
the owning project, domain, feature, behavior, or architecture decision path.
Project-wide rules use `project` as their node and ID prefix.

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
   `features[].related_to`, `features[].architecture`,
   `features[].experience.surfaces[].contains`,
   `features[].experience.surfaces[].accessibility`,
   `features[].experience.surfaces[].responsive_behavior`,
   `features[].experience.surfaces[].states[].statements`,
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

   The authored reference arrays named in rule 2 retain authored order instead;
   this table does not reorder them merely because their entries are references.
5. Sort each symmetric relationship's two `endpoints` lexically before using the
   endpoint tuple as its identity and sort `declared_by` lexically by semantic
   path. Emit only one relationship record per endpoint pair.
6. These rules exhaust every array in version 1. A future format change that adds
   an array MUST assign it either source-sequence preservation or an explicit total
   sort key before that format version is approved.
7. Serialize JSON object keys in Unicode code-point lexical order, use UTF-8
   without ASCII escaping, use two-space indentation, omit trailing whitespace,
   and end the document with one line feed.
8. Do not include timestamps, source paths, machine paths, random identifiers,
   generated state, or environment-dependent values.

Lexical ordering compares Unicode scalar values without locale-sensitive
collation. PML IDs are ASCII, but the same rule also makes vocabulary-term ordering
deterministic.

Authored mappings have no semantic priority based on YAML key position. Authored
sequences are retained for faithful display, but this retention never adds order
semantics where the language defines none.

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

### `pml graph`

Graph consumes only explicit compiled edges:

- directed producer-completion to signal to consumer-trigger edges;
- symmetric `related_to` edges; and
- use-case membership edges.

It must visually distinguish those three meanings. It must not derive workflow
order from use cases, direction from `related_to`, or a relationship from shared
actors, concepts, words, or hierarchy.

### Future web UI

The web UI consumes this same model for navigable project, domain, feature, and
behavior views; transition and signal details; use-case membership; relationship
and causal graphs; and stable obligation inspection. Validation findings are a
separate failed-compilation result, not nodes in a partial compiled model.

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

After approval, delivery follows the repository order:

1. Define the version 1 JSON Schema and shared in-memory types.
2. Refactor reference resolution and stable obligation enumeration to populate the
   model without changing validation outcomes.
3. Add positive and negative conformance fixtures plus deterministic serialization
   tests.
4. Add `compile --json`, then build `explain`, `graph`, and the future web UI as
   read-only consumers.

Existing approved definitions and their validation behavior are the compatibility
oracle. A refactor that changes accepted language, diagnostics, resolved paths, or
obligation meaning is a semantic change and requires separate owner approval.
