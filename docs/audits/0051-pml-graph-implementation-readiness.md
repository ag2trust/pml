# `pml graph` implementation-readiness audit against spec 0011

Audit date: 2026-09-10

Baseline: `87bb224` (the current merged `pml explain` implementation). This is a
read-only audit. It changes no PML definition, specification status, schema,
validator, compiler, CLI, renderer, generated state, or evidence.

## Result

Spec 0011 approves `pml graph` as a read-only consumer, but fixes only its input
semantics: it consumes three kinds of explicit compiled edges and visually
distinguishes them ([0011:673-683](../specs/0011-compiled-semantic-model.md)). It
does not specify a command-output contract. The delivered `pml explain` indexes
are sufficient to locate all records and the two non-causal edge sets; a small,
pure compiled-model edge enumerator is still needed for a graph implementation.

The smallest safe next step is an owner-approved graph presentation contract with
examples, followed by an unfiltered `pml graph <manifest-path>` implementation.
It must emit only the three edge sets below and no inferred edges.

## Invocation and consumer boundary

The approved text names `pml graph` but gives no argument grammar. The current
CLI convention is source first: `compile <path> --json`, `explain <manifest>
<canonical-id>`, and `obligations <manifest> [<node-id>]`
([`src/pml/cli.py:40-56`](../../src/pml/cli.py)). `pml explain` itself loads,
validates, then passes `resolution.compiled_model` to its read-only consumer
([`src/pml/cli.py:107-125`](../../src/pml/cli.py)). Therefore the least novel
invocation is:

```text
pml graph <manifest-path>
```

That form is an implementation convention, not an approved output or selection
contract. It reads a validated source snapshot in the same process and consumes
only its complete compiled model. It must preserve the all-or-nothing boundary:
invalid input produces normal diagnostics and no graph on standard output
([0011:104-119](../specs/0011-compiled-semantic-model.md)). Before reading model
records, it must check `format == "pml.compiled"` and exactly
`format_version == 1`; an unknown version is unsupported, never guessed
([0011:651-656](../specs/0011-compiled-semantic-model.md)).

The existing helper already implements that guard as `is_supported_model`, and
`build_compiled_model_indexes` rejects before indexing
([`src/pml/explain.py:91-109`](../../src/pml/explain.py)). A graph consumer can
reuse it; it must not rely on in-process production as a substitute for the
consumer check.

## Exact permitted edge inventory

Only these three edge meanings are approved. The source field, endpoints, and
meaning must remain distinct in both the internal edge type and any presentation.

| Meaning | Compiled source | Explicit endpoints | Semantics that may be shown |
| --- | --- | --- | --- |
| Directed causal occurrence | `signals[]` | `producer.completion` obligation ID -> signal `id` -> each `consumers[].trigger` obligation ID | A producing completion includes one signal occurrence; a consumer entry identifies a behavior trigger considered for that occurrence. A signal has one producer and zero or more consumers. |
| Symmetric relationship | `relationships[]` | `endpoints[0]` <-> `endpoints[1]` (feature or behavior paths) | `related_to`; endpoints are normalized and lexical, while `declared_by` only records authored declarations. |
| Use-case membership | `use_case_memberships[]` | `use_case` path -- `behavior` path | Membership only; it carries neither list position nor execution order. |

The first row follows the signal record shape ([0011:332-344](../specs/0011-compiled-semantic-model.md)) and its causal semantics ([0011:457-473](../specs/0011-compiled-semantic-model.md)). The second and third follow the closed edge records
([0011:346-355](../specs/0011-compiled-semantic-model.md)) and their explicit
non-causal constraints ([0011:475-488](../specs/0011-compiled-semantic-model.md)).
The producer is stored once on a signal and `consumers` is sorted by
`(behavior, trigger)`; relationships and memberships are respectively sorted by
their endpoint and member tuples ([0011:570-597](../specs/0011-compiled-semantic-model.md)).

No other compiled field is an edge source. In particular, hierarchy collections,
feature actors, architecture references, obligation ownership, authored
`related_to` arrays, signal subjects, and descriptive text are not graph edges.
`declared_by` is provenance for a symmetric relationship, not direction.

## Graph node boundary

The approved edge endpoints identify the complete semantic node universe for an
all-edges graph. Each listed endpoint is a graph node, not merely a record that a
renderer may annotate:

| Endpoint category | Existing compiled record | Must be a graph node because |
| --- | --- | --- |
| Signal | `signals[]`, by `id` | It is the middle endpoint of every directed causal path. |
| Completion and trigger | `obligations[]`, by stable `id` | The signal producer and consumer endpoints name distinct completion and trigger obligation IDs. |
| Feature and behavior | `features[]` and `behaviors[]`, by `path` | They are the only permitted `related_to` endpoints; behaviors also participate in memberships. |
| Use case | `use_cases[]`, by `path` | It is a use-case-membership endpoint. |

Every other record is annotation, if included at all: project, vocabulary, actor,
concept, domain, architecture decision, experience/surface, and every obligation
whose ID is not a `signals[].producer.completion` or `signals[].consumers[].trigger`
endpoint. An edge's `meaning`, a signal's `subject`, a relationship's
`declared_by`, and an obligation's `node`, `kind`, and `definition` are likewise
annotations, not additional edges or nodes.

Behavior records remain graph nodes only for their own `related_to` or membership
endpoints. They must never substitute for a causal completion or trigger
obligation node: one behavior can have multiple outcome/failure completion
obligations and multiple trigger alternatives, so substitution would collapse
distinct explicit causal paths. Labels, style, and layout are presentation details,
but the causal node identities are fixed by the compiled signal endpoints.

## Reusable views and the remaining pure query primitive

The actual post-task-3 API in [`src/pml/explain.py`](../../src/pml/explain.py),
not a presumed API, provides these reusable immutable views:

| Delivered view | Graph use |
| --- | --- |
| `categories`: per-category identity maps for project, vocabulary, actors, concepts, architecture, domains, features, behaviors, use cases, signals, and obligations | Resolve every edge endpoint to its record; `categories["obligations"]` resolves producer completion and consumer trigger IDs. |
| `reverse` and `matching_records()` | Detect canonical-ID category collisions without prefix heuristics. It is not a graph-edge source. |
| `relationships_by_endpoint` / `relationships_for_endpoint()` | Adjacency for normalized symmetric `related_to` records. |
| `memberships_by_use_case`, `memberships_by_behavior`, and their methods | Adjacency for membership records from either endpoint. |
| `obligations_by_node` / `obligations_for_node()` | Additional-obligation annotation only; it must not create owner-to-obligation edges or nodes beyond actual causal endpoints. |

Signals need no reconstructed resolver view: the complete directed information is
already on each `signals[]` record. What is missing is one graph-specific, pure
compiled-model query primitive that yields a canonical typed edge sequence:

```text
iter_explicit_graph_edges(model or supported indexes)
  -> producer_to_signal(producer_completion, signal) [exactly one per signal]
  -> signal_to_consumer_trigger(signal, consumer_trigger) [one per consumer]
  -> related_to(endpoint_a, endpoint_b, declared_by)
  -> use_case_membership(use_case, behavior)
```

It should validate support before record access, iterate canonical compiled-array
order, preserve the two signal legs as directed, and return no edges for
annotations. The producer-to-signal leg is always present, including when a
signal has zero consumers; the second directed leg is emitted only for actual
consumer entries. Together those two leg types are the one approved directed
causal meaning, not two new relationship meanings. An optional adjacency wrapper
belongs only after an owner selects root/filter behavior. No YAML loading,
reference resolution, inference, or new compiled-model field is required.

## Gaps and classifications

| Gap | Classification | Smallest safe disposition |
| --- | --- | --- |
| Input invocation | Documentation gap | Document the convention `pml graph <manifest-path>` when delivered; do not add selectors yet. |
| DOT, text, JSON, or rendered artifact; renderer dependency; how the three meanings are visually distinguished | Owner-decision blocker | Approve one output contract and representative output before implementation. Graphviz is permitted as a layout engine but cannot create edges ([0011:692-695](../specs/0011-compiled-semantic-model.md)). |
| Causal completion/trigger node projection | Already specified consumer requirement, not an owner gap | Render the exact obligation-ID endpoints as nodes; behavior nodes cannot replace them. Labels and style remain presentation details. |
| Node and edge encoding in the selected format, including escaping | Owner-decision blocker for a stable external format; implementation detail for private in-memory keys | Preserve the required canonical endpoint IDs and use a category discriminator internally where the selected format needs one. |
| Root selection, filtering, depth, and whether incident edges pull in neighboring nodes | Owner-decision blocker if offered | Initial slice renders the complete unfiltered edge set only. |
| Successful-output stream and diagnostics | Documentation gap for success; fixed requirement for invalid input | Write the selected graph to stdout by CLI convention; validation and unsupported-version failures are nonzero, diagnostic-only stderr, with empty stdout. |
| Empty graph representation | Owner-decision blocker because it depends on output format | Specify an explicit valid empty artifact, never an error or fabricated node. |
| Deterministic presentation ordering | Implementation detail once format is selected | Use the model's canonical array order; define a total serialization/order for any expanded legs or renderer IDs. |
| Unsupported `format` / `format_version` | Already specified consumer requirement, not an owner gap | Reuse the exact-version guard before indexing; reject with nonzero stderr diagnostic and no stdout. |
| Direct edge enumeration | Implementation detail | Add the small pure typed enumerator above, covered by model-only tests. |

## Non-inference safety boundary

The minimal graph must reject these tempting additions:

- no workflow or execution order from use-case behavior sequence or membership;
- no direction, dependency, or causal arrow from `related_to`, including
  `declared_by`;
- no edge from a shared actor, concept, vocabulary word, signal subject, or
  hierarchy relationship; and
- no payload, transport, delivery, persistence, retry, timing, or other technical
  interpretation of a signal.

Those prohibitions are direct requirements of the compiled-model boundary
([0011:29-40](../specs/0011-compiled-semantic-model.md)), behavior model
([0011:452-455](../specs/0011-compiled-semantic-model.md)), signal semantics
([0011:469-473](../specs/0011-compiled-semantic-model.md)), and graph consumer
contract ([0011:675-683](../specs/0011-compiled-semantic-model.md)).

## Recommended next slice and tests

1. Obtain owner approval for one output format, its external encoding/escaping,
   valid empty-graph representation, and whether the first command is necessarily
   unfiltered. Causal completion and trigger obligation nodes are already fixed by
   spec 0011 and are not an owner choice.
2. Add a pure, version-gated `iter_explicit_graph_edges` helper over the existing
   compiled model and an unfiltered `pml graph <manifest-path>` adapter. It should
   reuse the explain indexes and the existing load/validate diagnostic path.
3. Add output tests only after the approved rendering contract is fixed.

Positive tests should cover: one signal with one producer and multiple consumers;
a zero-consumer signal that still emits its one producer-to-signal edge and emits
no signal-to-trigger edge; multiple outcome/failure and trigger-alternative
obligations on one behavior that remain distinct causal nodes and legs; each
`related_to` direction authored separately but normalized to one symmetric edge;
feature-to-feature and behavior-to-behavior relationships; one use case with
multiple behaviors; an otherwise valid definition with zero explicit graph edges;
lexical/deterministic ordering despite reordered source maps; and supported model
rendering with no state reads or writes.

Negative tests should cover: invalid definitions and unsupported model versions
produce no stdout graph; no partial graph; no edge for shared actor, concept,
vocabulary term, hierarchy, or signal subject; no behavior-node substitution for
causal obligation endpoints; no directed arrow or workflow order from `related_to`
or use-case membership; no technical signal transport node/edge; and no duplicate
relationship edge for reciprocal authored declarations.
