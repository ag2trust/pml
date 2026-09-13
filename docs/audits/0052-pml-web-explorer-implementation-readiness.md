# Read-only PML web explorer implementation-readiness audit

Audit date: 2026-09-12

Baseline: `2c0282f` (current `master` merge base). This is a documentation-only
audit. It changes no PML definition, approval status, schema, validator,
compiler, command, renderer, bindings, probes, locks, evidence, or generated
state.

## Result

Spec 0011 approves a future web UI as a read-only consumer of one complete
compiled model, and fixes its semantic scope. It does **not** approve a web
invocation, server lifecycle, listener, asset/dependency policy, or presentation
contract. Those choices are externally observable and remain owner-decision
blockers.

The compiled-model, `compile --json`, and `explain` work are sufficient for a
web consumer to obtain and query the one permitted model. The graph work should
not be duplicated: [audit 0051](0051-pml-graph-implementation-readiness.md)
identifies the sole permitted graph edge inventory and reusable indexes. Task
#11 records the owner's approved deterministic DOT contract; at this audit's
baseline that documentation commit (`0dccd82`) is in review and is not yet in
the checked-out spec. Task #12 is the dependent implementation of that shared
explicit-edge iterator and DOT consumer; it is not yet delivered. The explorer
must wait for Task #12 rather than reconstructing graph edges itself.

Subject to the owner decisions listed below, the smallest safe web slice is a
one-process, loopback-only, snapshot server with packaged local assets, no
network clients, no persistent writes, and only the approved project/domain/
feature/behavior navigation plus their listed details. It must load and
validate once, retain only the resulting supported compiled model in memory,
and terminate without listening when compilation fails.

## Already-approved semantics

The following are requirements now; an explorer implementation must not seek a
second interpretation of authored PML to provide them.

| Concern | Approved requirement |
| --- | --- |
| Input and lifecycle boundary | The compiled model is a deterministic, read-only index of one completely validated PML definition; validation and compilation use one snapshot. A consumer receives either a complete model or ordered diagnostics, never both ([0011:21-40](../specs/0011-compiled-semantic-model.md), [0011:51-70](../specs/0011-compiled-semantic-model.md), [0011:104-119](../specs/0011-compiled-semantic-model.md)). |
| Model compatibility | Before reading records, every consumer checks `format == "pml.compiled"` and supports exactly `format_version == 1`; all other versions are unsupported, not guessed ([0011:651-656](../specs/0011-compiled-semantic-model.md)). The current `is_supported_model` and `build_compiled_model_indexes` already make that check before indexing ([explain.py:91-109](../../src/pml/explain.py)). |
| Navigation subject matter | The UI consumes that same model for project, domain, feature, and behavior views; transition and signal details; use-case membership; relationship and causal graphs; and stable obligation inspection ([0011:685-695](../specs/0011-compiled-semantic-model.md)). |
| Read-only boundary | It is a projection only. Editing, approving, rewriting, and synchronizing PML require a separate language and workflow decision ([0011:691-695](../specs/0011-compiled-semantic-model.md)). The compiled model excludes bindings, probes, locks, evidence, generated state, source paths, and YAML layout metadata ([0011:21-40](../specs/0011-compiled-semantic-model.md), [0011:147-149](../specs/0011-compiled-semantic-model.md), [0011:516-524](../specs/0011-compiled-semantic-model.md)). |
| Graph meaning | Only producer-completion → signal → consumer-trigger, symmetric `related_to`, and use-case membership are graph edges. The latter two create neither direction nor workflow order; no graph edge may be inferred from actors, concepts, words, hierarchy, or other shared fields ([0011:673-683](../specs/0011-compiled-semantic-model.md); [audit 0051](0051-pml-graph-implementation-readiness.md)). |
| Invalid definitions | Validation findings are a failed-compilation result, not nodes in a partial model or graph ([0011:104-119](../specs/0011-compiled-semantic-model.md), [0011:685-690](../specs/0011-compiled-semantic-model.md)). |
| Deterministic data | The same validated merged definition and compiler format version produce byte-identical model JSON, with no timestamps, machine paths, random IDs, generated state, or environment-dependent values ([0011:526-649](../specs/0011-compiled-semantic-model.md)). |

The current delivery path already supplies the required all-or-nothing input:
`pml compile --json` loads and validates before writing the model, and `pml
explain` follows the same load/validate path before calling the version-gated,
in-memory consumer ([cli.py:83-125](../../src/pml/cli.py)). `CompiledModelIndexes`
provides immutable category lookups, direct stable-obligation lookup, and the
two non-causal adjacency views; it does not read sources or product-local state
([explain.py:47-156](../../src/pml/explain.py)).

## Owner-decision blockers

None of the following is defined by the approved future-UI paragraph. They must
be approved as one delivery contract before a UI server, command, asset bundle,
or browser-facing test is implemented.

| Decision | Why approval is needed | Minimal proposal for review |
| --- | --- | --- |
| Invocation and lifecycle | Spec 0011 names a future UI but supplies no command grammar, URL, startup rule, shutdown rule, browser-launch behavior, or concurrent-instance behavior. | `pml web <manifest>` has no flags. It validates and compiles one snapshot before binding. On success it prints one loopback URL to stdout, serves until SIGINT/SIGTERM, then closes the listener; it neither opens a browser nor forks/backgrounds. A second process receives the normal bind failure and makes no writes. |
| Localhost binding | A web listener is a new attack surface. “Local” must not silently mean every interface, IPv6, or a proxy-reachable service. | Bind only `127.0.0.1` on an owner-chosen fixed port. Do not provide host, port, TLS, proxy, or public-bind flags in v1. A fixed port makes the printed URL and tests determinate; if port selection is not approved, no listener contract exists. |
| Output, assets, and dependencies | The approved model JSON and DOT bytes do not define HTTP responses, static files, a framework, a renderer, CSP, or third-party delivery. | Serve an embedded, versioned, same-origin HTML/CSS/JavaScript bundle and the complete in-memory v1 model only. No CDN, analytics, fonts, remote fetch, service worker, package-manager install at runtime, file-output, or Graphviz subprocess. Use only the approved Task #12 graph projection; selecting a UI framework or browser graph-layout library is an owner choice because it expands the dependency and update boundary. |
| Navigation scope | The paragraph states the allowed subjects but not routes, starting view, generic browsing, search, filtering, arbitrary record views, or whether details are linked in one or both directions. | Provide only a project landing view; domain, feature, and behavior views; behavior transition and signal details; use-case membership; stable obligations; and the two explicit graph views. Use canonical compiled IDs as route parameters and present records in compiled-array order. No search, deep graph filtering, editable forms, approval controls, sync controls, generic YAML/JSON/source browser, or views for bindings, probes, locks, evidence, or generated state. |
| Graph reuse and renderer | Re-enumerating edges in the UI would create a second graph model and risks forbidden inference. Task #11 selects deterministic DOT bytes; Task #12 owns the iterator/serializer implementation. The future-UI paragraph permits a free layout renderer but does not choose one. | Depend on Task #12's version-gated explicit-edge query. A causal graph renders only its causal legs; a relationship graph renders only normalized `related_to` edges; membership is displayed only with its explicit use-case/behavior links. Preserve the edge kind in presentation. The owner must select either a pinned local renderer/layout contract or an edge-list/SVG presentation whose layout is explicitly non-semantic; no renderer dependency may add nodes or edges. |
| Deterministic presentation | Deterministic model bytes do not automatically make DOM order, URL encoding, labels, graph layout, or responses deterministic. | For a fixed supported model and fixed asset version, routes, record order, edge order, labels, and static response bytes are deterministic. IDs are ordered before escaping. The server exposes no current time, random token, request-derived state, or live reload. If a renderer's pixel layout is not byte-stable, tests compare the ordered typed graph input rather than pixels; the owner must approve that qualification. |
| Failed compilation | The approved all-or-nothing rule excludes partial data, but it does not choose whether a listener may serve a diagnostic page. | On load, schema, reference, semantic, or exact-version failure, write normal diagnostics to stderr, exit nonzero, and bind no socket or HTTP route. Never serialize, cache, or display a candidate model. |
| Exact-version rejection | A process that currently compiles v1 still needs the consumer guard so a later producer change cannot be rendered by assumption. Error status and HTTP exposure are not specified for a web consumer. | Call the same exact-version guard before creating indexes, routes, or graph data. Treat wrong `format`, a non-integer version, and every version other than `1` as the failed-compilation lifecycle above; do not offer compatibility mode or a partial page. |
| Security boundary | Read-only semantics alone do not prevent source disclosure, path traversal, cross-origin fetches, unsafe HTML insertion, or future mutation endpoints. | Hold only the compiled model and packaged assets in memory. Do not serve manifest paths, YAML, directories, source maps, stack traces, state, or evidence. Treat all compiled strings as text, not HTML. Accept only GET/HEAD for fixed asset and approved read routes; reject all mutation methods and unknown paths. Use same-origin assets and a restrictive CSP; make no outbound requests. Loopback binding plus no mutation endpoint means no authentication/cookie/session/CSRF feature is introduced. |
| Test and verification contract | The existing test suite has no HTTP/UI contract. Without acceptance cases, a “read-only explorer” can accidentally become a source/state browser or semantic graph fork. | Add the approved positive and negative cases in the final section, run the focused web tests and full `pytest -q`, and run `git diff --check`. The owner must approve the route/response and renderer assertions selected above. |

The proposed fixed port and selected renderer are genuine owner choices, not
implementation details. If the owner prefers an ephemeral port, a different
local transport, browser launch, or a framework, those changes need an explicit
replacement contract because they change invocation, security, and test
observables.

## Minimal proposed delivery contract for owner review

This is deliberately a proposed delivery contract, not an amendment to spec
0011 and not authorization to implement until approved.

1. `pml web <manifest>` is the only v1 invocation. It has no options and makes
   no files or process detachment. It loads and validates `<manifest>` once,
   obtains its complete compiled model, applies the exact v1 consumer guard,
   then serves that immutable snapshot until interrupted.
2. The server binds only the owner-selected loopback URL. It prints that one URL
   after a successful bind. It never opens a browser, listens publicly, proxies,
   accepts an upload, or observes later source changes. Failed loading,
   validation, compilation, support checking, or binding exits nonzero and
   never presents a partial model.
3. All responses consist of packaged same-origin assets and projections of the
   in-memory compiled model. The delivery contains no runtime downloads,
   external fonts/analytics, state/source reads, writes, subprocesses, or
   renderer service. Every string is text-escaped for its destination.
4. The landing view links only to the approved navigation scope: project,
   domains, features, behaviors, a behavior's transition cases, signals,
   use-case memberships, stable obligations, causal graph, and relationship
   graph. A link is a compiled canonical ID or an approved explicit edge
   endpoint; it does not expose a filesystem path or authored YAML.
5. A graph view obtains its typed edges exclusively from Task #12's shared,
   version-gated explicit-edge iterator. It uses the Task #11 DOT contract as
   the canonical graph serialization where DOT is exposed. It neither parses
   authored `related_to` fields nor derives adjacency from record similarity,
   hierarchy, signals' subjects, or provenance. A renderer may place existing
   nodes, but never makes a semantic node or edge.
6. For a fixed supported compiled model and packaged asset version, all
   navigation order and graph input order follow compiled-model order; labels
   retain the compiled identity. The UI does not claim that a renderer's spatial
   arrangement is product semantics. It contains no timestamps, random IDs,
   live data, approval status, implementation status, confidence, or evidence.
7. The server offers only read routes. It has no edit, save, approve, sync,
   reload, or action endpoint; all non-GET/HEAD methods fail. It does not read
   or modify bindings, probes, locks, evidence, generated state, or the
   approved definition after the initial load/compile operation.

## Required tests after approval

Positive coverage must prove that one valid complete model can navigate the
approved views; behavior transition cases and signals retain their compiled
details; use-case membership does not imply order; obligations retain stable
IDs; and the causal and relationship graph views receive precisely the shared
Task #12 edge sequence. It must cover a zero-consumer signal, distinct trigger
and completion obligation endpoints from one behavior, reciprocal
`related_to` declarations collapsed by the model, multiple memberships, and
reordered authored maps yielding the same ordered UI projection.

Negative coverage must prove all of the following:

- invalid source, schema, reference, and semantic failures bind no listener and
  expose no HTTP model or graph;
- wrong `format`, boolean/string/non-integer `format_version`, and every
  unsupported integer version are rejected before indexing or routing;
- no source/YAML/path, binding, probe, lock, evidence, or generated-state read
  occurs after the permitted initial definition load, and no write occurs at
  any point;
- a shared actor, concept, vocabulary term, hierarchy membership, signal
  subject, relationship `declared_by`, or descriptive text creates no graph
  edge; behavior paths do not replace causal obligation endpoints;
- no route or control edits, approves, rewrites, synchronizes, uploads, or
  executes a renderer; non-read HTTP methods and unknown routes are rejected;
  and
- rendered strings cannot become executable markup, external requests are not
  issued, static traversal attempts fail, and the listener is not reachable on
  a non-loopback interface.

Exact route/status/header/body assertions, the owner-selected port, and the
renderer/layout assertion belong in the approved delivery contract. The model
and graph semantic tests should reuse the conformance fixtures and golden
coverage already required by Tasks #11 and #12, rather than duplicating a
second graph fixture format.

## Recommended implementation order

After every owner-decision blocker is approved and Task #12 is merged, add only:

1. a pure web projection/router over `CompiledModelIndexes` and Task #12's
   explicit-edge iterator, both guarded by the existing exact-version check;
2. a minimal loopback server that loads, validates, compiles, and snapshots once
   before binding; and
3. a packaged local read-only shell plus the contract tests above.

Do not add a general API, file watcher, source editor, browser automation,
project-state integration, Graphviz invocation, remote asset dependency,
filter/search system, or a second resolver/graph builder in this slice.
