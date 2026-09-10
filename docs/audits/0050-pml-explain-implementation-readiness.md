# `pml explain` implementation-readiness audit against spec 0011

Audit date: 2026-09-10
Baseline: worktree `daemon/bolt-7b9o-t2` at `3493fc8` (Merge PR #42), which is the
current post-Task-1 base with spec 0011 owner-approved on 2026-08-13 and the
compiled-model producer wired into `pml compile --json`.

This is a read-only implementation-readiness audit for the owner-approved
`pml explain` consumer described in
[`docs/specs/0011-compiled-semantic-model.md`](../specs/0011-compiled-semantic-model.md)
lines 665-671 and lines 725-726. It changes no schema, validator, compiler,
CLI, formatter, language, generated-state, or evidence artifact.

Its purpose is to determine whether a minimal `pml explain` implementation can
be added without silently choosing an externally observable contract that
requires owner approval, and to identify the reusable query primitives that a
minimal implementation should expose to the later `pml graph` and web explorer
consumers.

## Approved text and current-code baseline

Every finding below cites the exact lines audited.

Approved text authorizing and constraining `pml explain`:

- Delivery order authorizes explain after `compile --json`
  ([spec 0011:725-726](../specs/0011-compiled-semantic-model.md)).
- The consumer contract requires every consumer to check `format` and support
  the exact `format_version` before reading records, treat unknown versions as
  unsupported rather than guessing, and never manufacture nodes or reinterpret
  missing data ([spec 0011:651-656](../specs/0011-compiled-semantic-model.md)).
- The explain-specific paragraph states: "Explain resolves its requested
  canonical ID against the compiled indexes and shows the authored text plus
  direct semantic links: owning hierarchy, transition cases, producer or
  consumer signals, use-case memberships, symmetric relationships, and stable
  obligations. It must distinguish authored fields from derived inverse links
  and must not present a generated summary as approved intent."
  ([spec 0011:665-671](../specs/0011-compiled-semantic-model.md)).
- The all-or-nothing diagnostic behavior applies: "The library result is either
  a complete compiled model or the normal ordered validation diagnostics, never
  both. A future `pml compile --json` command exits nonzero, writes diagnostics
  to standard error, and writes no JSON to standard output when validation
  fails. `explain`, `graph`, and the web UI observe the same all-or-nothing
  boundary." ([spec 0011:104-119](../specs/0011-compiled-semantic-model.md)).

Current-code baseline this audit measures readiness against:

- The compiled model producer is `_build_compiled_model` in
  [`src/pml/model_builder.py`](../../src/pml/model_builder.py) lines 235-457,
  invoked from `validate_document` in
  [`src/pml/validator.py`](../../src/pml/validator.py) lines 446-474 only when
  the diagnostic set is empty.
- The shared closed types for every record category are declared in
  [`src/pml/compiled_model.py`](../../src/pml/compiled_model.py) lines 14-336.
- The reference resolver, its identity iterators, and its obligation
  enumerators are in [`src/pml/resolver.py`](../../src/pml/resolver.py) lines
  137-254, with candidate tables materialized in `ResolvedDefinition` lines
  52-76. `iter_nodes` (lines 143-160), `iter_architecture` (lines 162-167),
  `enumerate_obligations` (lines 169-240), and
  `enumerate_architecture_obligations` (lines 242-254) are the currently
  exposed query primitives.
- The current CLI in [`src/pml/cli.py`](../../src/pml/cli.py) lines 31-298
  registers `init`, `validate`, `compile`, `obligations`, `check`, `status`,
  `architecture-status`, `validate-probes`, and `ingest-report`. No `explain`
  subparser exists. `compile --json` is at lines 39-45 and 83-99. The one
  established "unknown identifier" diagnostic pattern is `obligations`'s
  `[unknown-node]` line at 285-287.
- Canonical serialization for the compiled JSON is
  [`src/pml/serialization.py`](../../src/pml/serialization.py) lines 89-92.
- `HANDOFF.md` lines 13-18 records that "`pml explain`, `pml graph`, and the
  future read-only web explorer described in 0011 are approved but remain
  unimplemented consumers of the compiled model."

## Audit findings

### 1. Invocation shape

**Determined by approved text and established convention**: `pml explain`
takes a single positional canonical ID plus a single positional definition
path, and delivers the human-readable projection to standard output.

The approved text at spec 0011:665-671 fixes that the command resolves a
"requested canonical ID" against the compiled indexes; the "canonical ID"
category is already fully specified in the identity rules at spec 0011:122-149.
Established CLI convention across the current subparsers is `pml
<subcommand> <manifest-path> [<node_id>]`
([`src/pml/cli.py`](../../src/pml/cli.py) lines 46-72), with `obligations`
taking exactly the shape `pml obligations <manifest> [<node_id>]`
([`src/pml/cli.py`](../../src/pml/cli.py) lines 46-50, 277-291). The `compile`
subparser at [`src/pml/cli.py`](../../src/pml/cli.py) lines 39-45 also takes
`<path>`. There is no existing subcommand that accepts an ID as its only
positional or as an option flag, so following the established shape yields
`pml explain <manifest-path> <canonical-id>` without a new convention.

**Owner-decision blocker on optional flags**: whether `pml explain` should
also accept an alternative output form (structured JSON echo, "authored only"
mode, or category filter) is not addressed by spec 0011:665-671. The audit
finds no approved authorization for such flags. A minimal implementation
therefore MUST NOT add them.

**Documentation gap**: the invocation string `pml explain <manifest-path>
<canonical-id>` is derived from convention but never printed in
[`README.md`](../../README.md) or the specs. A later documentation update
should record it once the command is delivered; that is a downstream
change, not a blocker for the minimal slice.

### 2. Requestable record categories and canonical-ID collisions

**Determined**: the compiled model's top-level record categories are
enumerated at spec 0011:158-177 and correspond one-to-one with the top-level
arrays materialized in `_build_compiled_model`
([`src/pml/model_builder.py`](../../src/pml/model_builder.py) lines 395-456).
Their identity categories (spec 0011:122-149) are:

| Category | Identity carrier | Producer |
| --- | --- | --- |
| `project` | fixed, singular | [`model_builder.py:400-406`](../../src/pml/model_builder.py) |
| `vocabulary[]` | `term` | [`model_builder.py:407-418`](../../src/pml/model_builder.py) |
| `actors[]` | `id` | [`model_builder.py:419-422`](../../src/pml/model_builder.py) |
| `concepts[]` | `id` | [`model_builder.py:423-430`](../../src/pml/model_builder.py) |
| `architecture[]` | `path` (`architecture.<decision-id>`) | [`model_builder.py:431-447`](../../src/pml/model_builder.py) |
| `domains[]` | `path` (`domains.<domain-id>`) | [`model_builder.py:266-280`](../../src/pml/model_builder.py) |
| `features[]` | `path` (`domains.<d>.features.<f>`) | [`model_builder.py:281-309`](../../src/pml/model_builder.py) |
| `behaviors[]` | `path` (`...features.<f>.behaviors.<b>`) | [`model_builder.py:311-343`](../../src/pml/model_builder.py) |
| `use_cases[]` | `path` (`...features.<f>.use_cases.<u>`) | [`model_builder.py:345-357`](../../src/pml/model_builder.py) |
| `signals[]` | `id` | [`model_builder.py:368-383`](../../src/pml/model_builder.py) |
| `obligations[]` | `id` (see below) | [`model_builder.py:385-393`](../../src/pml/model_builder.py) |

**Collision analysis** (this is the load-bearing correctness question for a
single-argument `pml explain <id>` command):

1. **Across `actors`, `concepts`, `signals`, `vocabulary`**: each is a
   separate authored namespace (spec 0011:143-145). Spec 0011 does not forbid
   an actor ID and a concept ID from being the same string, and the compiled
   arrays are keyed independently
   ([`model_builder.py:419-430`](../../src/pml/model_builder.py)). A single
   input ID string may therefore match records of more than one of these
   categories. A `vocabulary` `term` is authored free text; an `actor`,
   `concept`, or `signal` `id` is authored under
   [`schema/pml.schema.json`](../../schema/pml.schema.json). Two categories
   using the same string is an ambiguity, not a defect.

2. **Hierarchy paths versus flat IDs**: hierarchy paths always contain `.`
   segments beginning with `domains.` or `architecture.`. They cannot alias a
   bare `actor`, `concept`, `signal`, or `vocabulary term` under the current
   schema, but the resolver enforces this only structurally
   ([`resolver.py:83-92`](../../src/pml/resolver.py)); the ID grammar itself
   is not restricted from containing dots. Any dotted ID would not collide
   with a legal hierarchy path because it lacks the required prefix segments.

3. **Hierarchy paths versus obligation IDs**: this is the one direct collision
   fixed by the approved obligation table
   ([spec 0011:494-505](../specs/0011-compiled-semantic-model.md)):

   - `use_case` obligation ID: `<feature-path>.use_cases.<use-case-id>`
     ([spec 0011:503](../specs/0011-compiled-semantic-model.md)).
   - `use_case` compiled-record `path`:
     `<feature-path>.use_cases.<use-case-id>`
     ([spec 0011:322-330 and 130](../specs/0011-compiled-semantic-model.md),
     produced identically at
     [`model_builder.py:345-357`](../../src/pml/model_builder.py) where the
     compiled use-case's `obligation` field equals its own `path`).

   A single input string can therefore denote both the use-case compiled
   record and its `use_case` obligation. This is an approved-by-design
   collision: the compiled use-case record includes `obligation: <same path>`
   at [`model_builder.py:355`](../../src/pml/model_builder.py), and the
   obligation record's `node` is the same use-case path
   ([spec 0011:507-509](../specs/0011-compiled-semantic-model.md)). Both are
   legitimate reads of the same input.

4. **Architecture path vs. architecture-constraint obligation**: the
   constraint obligation IDs extend the decision path with
   `.constraints.<constraint-id>`
   ([spec 0011:504](../specs/0011-compiled-semantic-model.md);
   [`model_builder.py:438-441`](../../src/pml/model_builder.py)). No
   collision with the flat `architecture.<decision-id>` path.

5. **Behavior path vs. its behavior-scoped obligations**: obligation IDs
   inside a behavior scope extend the behavior path with
   `.conditions`, `.trigger[.<alt>]`, `.completion`, `.outcome[.<alt>]`, and
   `.failures.<failure>`
   ([spec 0011:496-504](../specs/0011-compiled-semantic-model.md);
   [`resolver.py:169-240`](../../src/pml/resolver.py);
   [`model_builder.py:122-183`](../../src/pml/model_builder.py)). No
   behavior-record path equals an obligation ID.

6. **Feature path vs. feature-scoped obligations**: feature `rules` obligations
   extend the feature path with `.rules.<rule-id>`
   ([spec 0011:502](../specs/0011-compiled-semantic-model.md);
   [`model_builder.py:23-27`](../../src/pml/model_builder.py)); no collision
   with the flat feature path.

7. **`compiled-project.id` vs. project-scoped obligations**: project rules use
   `project` as their node prefix
   ([spec 0011:506-508](../specs/0011-compiled-semantic-model.md);
   [`resolver.py:143-160`](../../src/pml/resolver.py) line 147). The
   `compiled-project.id` is authored separately at
   [`model_builder.py:401`](../../src/pml/model_builder.py). A project-scoped
   rule obligation is `project.rules.<rule-id>`; it cannot collide with a
   feature path, but it is disjoint from the project record itself because
   the project record is addressed by the fixed keyword `project`.

**Conclusion**: two collision families are real for a canonical-ID lookup:

- **actor / concept / signal / vocabulary-term**: same input string may match
  up to four category records.
- **use-case path**: same input string always denotes both a use-case record
  and its `use_case` obligation (guaranteed identity by spec, not a bug).

Everything else has structurally disjoint prefixes and can be dispatched by
prefix inspection alone.

Classification: **implementation detail**. Category dispatch is a
`Category -> {id: record}` lookup that a minimal implementation must maintain
against the compiled model it already produces; the categories and ID rules
are approved.

### 3. Exact authored fields and derived links per category

The full closed field list per category is enumerated at spec 0011:158-363,
implemented as the closed `TypedDict`s at
[`compiled_model.py:14-336`](../../src/pml/compiled_model.py). Nothing here
requires additional owner approval. The remaining question for `pml explain`
is the boundary spec 0011:670-671 requires: "It must distinguish authored
fields from derived inverse links".

The authored/derived split follows directly from the approved determinism
tables at spec 0011:536-591. Authored arrays and scalar fields are those in
rule 2 at spec 0011:538-547 plus the singleton authored scalars listed in the
record grammars at spec 0011:187-363. Every array in rule 4 at
spec 0011:571-591 is a derived record or reference. Concretely per category:

| Category | Authored fields | Derived inverse links |
| --- | --- | --- |
| `compiled-project` | `id`, `name`, `purpose` ([spec 0011:180-185](../specs/0011-compiled-semantic-model.md)) | `rule_obligations`, `domains` |
| `compiled-vocabulary-term` | `term`, `meaning`, `forbidden_synonyms` (authored sequence, rule 2 [spec 0011:538-540](../specs/0011-compiled-semantic-model.md)) | none |
| `compiled-actor` | `id`, `meaning` | none |
| `compiled-concept` | `id`, `meaning`, `states` (authored sequence, rule 2) | none |
| `compiled-architecture-decision` | `id`, `path`, `category`, `selection`, `rationale` | `constraint_obligations`, `referenced_by` (rule 4 [spec 0011:578-579](../specs/0011-compiled-semantic-model.md)) |
| `compiled-domain` | `id`, `path`, `purpose` | `rule_obligations`, `features` |
| `compiled-feature` | `id`, `path`, `domain`, `purpose`, `actors` (rule 2), `experience` (present-or-absent, spec 0011:236-251), `related_to` (rule 2, spec 0011:539), `architecture` (rule 2, spec 0011:539) | `rule_obligations`, `use_cases`, `behaviors` (all rule 4) |
| `compiled-behavior` | `id`, `path`, `feature`, `conditions.statements` (rule 2), `trigger`, `outcome`, `failures[]`, `related_to` (rule 2, spec 0011:540) | `rule_obligations`, `use_cases`, `completion_obligation` (a derived reference to the corresponding compiled obligation) |
| `compiled-use-case` | `id`, `path`, `feature`, `actor`, `goal`, `behaviors` (rule 2, spec 0011:540) | `obligation` (a derived reference to its `use_case` obligation) |
| `compiled-signal` | `id`, `meaning`, optional `subject` | `producer`, `consumers` (both derived from `outcome`/`failure` and trigger cases in the compiled behaviors, [`model_builder.py:186-214`](../../src/pml/model_builder.py); rule 4 [spec 0011:586](../specs/0011-compiled-semantic-model.md)) |
| `compiled-relationship` | none (record itself is derived) | `endpoints`, `declared_by` (both derived from authored `related_to`, [spec 0011:476-482](../specs/0011-compiled-semantic-model.md); [`model_builder.py:217-232`](../../src/pml/model_builder.py)) |
| `compiled-use-case-membership` | none | `use_case`, `behavior` (derived from use-case `behaviors`, spec 0011:484-488) |
| `compiled-obligation` | records whose `definition` fields are authored (statement, signal reference, condition statements, use-case actor/goal/behaviors); the `id`, `node`, `kind` are derived stable path/kind assignments | `outcomes`, `failures`, `alternatives` inside `completion` and `outcome_exclusivity` definitions are derived from the same behavior (see spec 0011:511-515) |

Trigger, outcome, and failure sub-cases inside a compiled behavior contain
authored `statement` or `signal` values plus derived `obligation` and `id`
references. The trigger and outcome `case`/`cases` structures are approved as
authored transition shape at spec 0011:432-450 and produced verbatim at
[`model_builder.py:46-95`](../../src/pml/model_builder.py).

Classification: **implementation detail**. The distinction is fully
determined; a minimal implementation renders each record's authored fields in
one section and its derived links in a clearly separated section.

### 4. Ordering: what is determined, what remains a presentation choice

**Determined**: every top-level array's order is fixed by rule 3 at
spec 0011:552-568. Every derived reference array's order is fixed by rule 4 at
spec 0011:570-591. Authored sequences retain authored order per rule 2 at
spec 0011:536-547. The compiled model already exposes each record with its
neighboring lists in the required order
([`_build_compiled_model` in `model_builder.py:235-456`](../../src/pml/model_builder.py)).
`pml explain` therefore inherits its data ordering by reading the compiled
model directly and MUST NOT reorder lists it displays.

**Not determined by spec 0011** — presentation choices the minimal
implementation must make:

- Which order to render the record's sections in (authored fields section
  first, or derived links first). Spec 0011:670-671 requires that the two are
  visually distinguished but does not fix which section comes first.
- Whether to inline the compiled obligation objects the record references, or
  to reference them by ID only. Inlining requires resolving obligation IDs
  from the record back to the top-level `obligations` array. Both are
  legitimate reads of the same model.
- How to render an `experience` block: reuse the record's authored sequence
  ordering (already available in the compiled model) or introduce a
  section-per-surface layout. The latter is a presentation choice.
- Whether to elide fields that are empty arrays or empty objects to reduce
  noise.

Classification: **implementation detail** for the presentation choices,
provided the minimal implementation does not commit to a machine-readable
output format or a stable format string. If any structured (e.g., JSON,
YAML, tab-separated) explain output is proposed later, it becomes an
**owner-decision blocker** because it would introduce a new externally
observable contract not authorized at spec 0011:665-671. Human-readable
text output without a stable machine grammar is the safe minimal slice.

### 5. Diagnostics and exit/stdout/stderr behavior

**Determined by approved text**:

- Invalid definitions inherit the compile-level all-or-nothing boundary
  (spec 0011:104-119). The command MUST exit nonzero, write diagnostics to
  standard error, and write no explanation to standard output.
- Unsupported compiled-model versions: spec 0011:653-656 requires every
  consumer to check `format` and `format_version` before reading records and
  treat unknown versions as unsupported. The current `pml explain` design
  reads the compiled model produced in the same process from the same
  validated definition, so the in-process model is guaranteed to satisfy the
  `format`/`format_version` check
  ([`compiled_model.py:319-336`](../../src/pml/compiled_model.py) fixes both
  values at construction). A later variant that reads a pre-serialized model
  from disk MUST reject a model whose `format` is not `pml.compiled` or whose
  `format_version` is not `1`. That is out of scope for the minimal slice.

**Not determined by approved text**:

- The exact code and diagnostic message for an unknown or ambiguous requested
  canonical ID. The obligations subcommand established one convention:
  `<id>: [unknown-node] node does not exist`
  ([`cli.py:285-287`](../../src/pml/cli.py)). This audit does not treat the
  reuse of `[unknown-id]` (or an analogous `unknown-<category>` diagnostic)
  as new externally observable contract, because it follows the established
  loader/validator diagnostic convention already used for `undefined-reference`
  ([`resolver.py:298-303, 313-320, 397-410, 417-424`](../../src/pml/resolver.py))
  and `unknown-node`
  ([`cli.py:285-287`](../../src/pml/cli.py)). Choosing a specific machine-
  readable code is an **implementation detail** provided the code shape
  matches the established `[<code>] <message>` format at
  [`diagnostics.py`](../../src/pml/diagnostics.py) and does not encode
  product-language semantics.
- The behavior for a requested ID that matches more than one category (the
  finding-2 collision families: actor/concept/signal/vocabulary-term, and
  the intentional use-case-path vs. use-case-obligation double). Spec 0011
  does not disambiguate. Three alternatives are all consistent with the
  approved text:

  1. Reject as ambiguous with a diagnostic and exit nonzero.
  2. Render all matching records under separate sections.
  3. Prefer a fixed category order (e.g., structural records first, then
     obligations) and render only one.

  Option 2 is the safest for a minimal slice because it neither hides a
  legitimate compiled record nor commits to a category-priority contract.
  Option 3 introduces a stable but new externally observable behavior — a
  priority contract — that spec 0011 has not approved and therefore an
  **owner-decision blocker** if the minimal implementation wants to hide
  matches. Option 1 is safe but would deny explain of any use-case (whose
  path is guaranteed to match both the compiled record and its obligation),
  so it is only viable if the use-case path collision is exempted from
  ambiguity.

Classification for unknown-ID: **implementation detail**. Classification for
ambiguity resolution: **owner-decision blocker** if the minimal slice wants
to hide matches; **implementation detail** if the minimal slice renders every
category match under a separate section.

### 6. Minimal-slice viability without new owner decisions

A minimal `pml explain` can be delivered without any new owner decision if:

- Invocation is `pml explain <manifest-path> <canonical-id>` following the
  established subparser convention at
  [`cli.py:37-72`](../../src/pml/cli.py).
- The command re-uses `load_document` + `validate_document` to obtain a
  complete compiled model, and inherits the all-or-nothing diagnostic
  boundary already implemented by
  [`cli.py:83-99`](../../src/pml/cli.py) for `compile`.
- The requested ID is dispatched by prefix inspection (finding 2) against
  the compiled model's category arrays, and every category that matches is
  rendered under its own section, so no category-priority contract is
  introduced.
- Each record's authored fields are rendered in one section and derived
  inverse links in another; empty derived arrays are rendered as an empty
  bullet list rather than as a claim of absence.
- Output is human-readable text on standard output with no stable
  machine-grammar claim; no `--json`, `--format`, or category filter flag is
  added.
- Unknown IDs use the existing `[<code>] <message>` diagnostic shape
  ([`diagnostics.py`](../../src/pml/diagnostics.py)) analogous to
  `[unknown-node]` at [`cli.py:285-287`](../../src/pml/cli.py).

Where the minimal slice must NOT go:

- No inference or paraphrase of authored text (spec 0011:29-40).
- No cross-category priority or "primary category" resolution when an ID
  matches more than one category (finding 5).
- No new record categories, no new closed enums, no new obligation
  interpretation.
- No `--json` or other machine-readable output format (finding 4).

### 7. Reusable query/index primitives

The compiled model is materialized once by
[`_build_compiled_model`](../../src/pml/model_builder.py) with every top-level
array already in canonical order. Neither `pml graph` nor the web explorer
needs YAML-level access. The reusable primitives a minimal `pml explain`
should establish (and only those; nothing new for `graph` or the UI beyond
what they will observe) are:

1. **Category-typed ID index over the compiled model**. A single pass that
   builds, for each category, a `dict[str, TypedRecord]` keyed by the record's
   identity field (`id`, `term`, or `path` per finding 2). This is a
   read-only projection of an already-materialized model
   ([`_build_compiled_model` at lines 395-456](../../src/pml/model_builder.py))
   and requires no schema change. `pml graph` reuses the same index to look
   up nodes referenced by directed producer-completion→signal→consumer-trigger
   edges, symmetric `related_to` edges, and use-case membership edges
   (spec 0011:673-683).

2. **`(canonical-id) -> [category]` reverse dispatch**. Given a canonical ID
   string, return every category whose ID index contains it, so a consumer
   can render or navigate every matching record without embedding
   category-priority semantics. This is the primitive that lets `pml graph`
   and the web UI share explain's dispatch without reinterpreting YAML.

3. **Obligation-back-reference view**. For a given non-obligation record's
   canonical ID, a helper that returns every compiled obligation whose `node`
   field equals that ID. This is a pure read over the already-materialized
   `obligations` array ordered by rule 3 (spec 0011:568). It supports
   explain's "stable obligations" section without duplicating obligation
   traversal in each consumer.

4. **Signal edge view**. For a signal ID, its producer and consumers are
   already present on `compiled-signal.producer` and `compiled-signal.consumers`
   ([`compiled_model.py:192-207`](../../src/pml/compiled_model.py); produced at
   [`model_builder.py:186-214`](../../src/pml/model_builder.py)). No new
   primitive is required beyond the ID index that maps the producer
   `behavior` and each consumer `behavior` back to their compiled-behavior
   records. This is the primitive `pml graph` will use to render the
   directed causal edges required by spec 0011:675-679.

None of these primitives require a schema, validator, compiler, CLI beyond
the new `explain` subparser, or generated-state change. Each is a pure
function over the compiled model.

## Gap classification summary

| Gap | Classification |
| --- | --- |
| Exact invocation string is derivable from convention but not printed in docs | Documentation gap (updated after implementation lands) |
| Optional flags (JSON echo, category filter, authored-only) | Owner-decision blocker — do not add |
| Category dispatch of a canonical ID via prefix + ID index | Implementation detail |
| Actor/concept/signal/vocabulary-term same-string ambiguity handling | Owner-decision blocker only if minimal slice hides matches; otherwise implementation detail (render each match) |
| Use-case path guaranteed to match both use-case record and use_case obligation | Approved by spec ([0011:503-509](../specs/0011-compiled-semantic-model.md)); implementation detail |
| Authored vs. derived split per record | Implementation detail |
| Presentation ordering within a rendered record | Implementation detail (human-readable text only) |
| Diagnostic code and message for unknown ID | Implementation detail (reuse existing `[code] message` shape) |
| Unsupported compiled-model version handling when explain is fed a pre-serialized model | Out of scope for minimal slice; owner-approved contract already at spec 0011:653-656 for the later variant |
| Structured (e.g., JSON) explain output | Owner-decision blocker — do not add |
| Reusable ID index and obligation-back-reference view for later `pml graph` and web explorer | Implementation detail (pure read over compiled model) |

## Recommended smallest next slice

Deliver, as one PR, a `pml explain <manifest-path> <canonical-id>` subcommand
that:

1. Loads and validates the definition with the existing
   `load_document` + `validate_document` path
   ([`validator.py:404-475`](../../src/pml/validator.py)) and inherits the
   all-or-nothing diagnostic boundary already used by `compile --json`
   ([`cli.py:83-99`](../../src/pml/cli.py)).
2. Builds a category-typed ID index over the compiled model as a private
   helper, without changing the compiled-model schema or the
   [`compiled_model.py`](../../src/pml/compiled_model.py) closed types.
3. Dispatches the requested ID against that index, and for every matching
   category renders one section header naming the category, an "Authored"
   subsection listing that record's authored fields, and a "Derived"
   subsection listing the derived inverse links and obligation references.
4. On no match, exits nonzero and writes a single
   `<id>: [unknown-id] no compiled record matches this ID` line to standard
   error, with empty standard output, following the
   [`cli.py:285-287`](../../src/pml/cli.py) precedent.
5. On invalid definition input, exits nonzero and writes the standard ordered
   diagnostics to standard error with empty standard output, mirroring the
   compile behavior at [`cli.py:83-99`](../../src/pml/cli.py).

No new flags, no new record categories, no new obligation kinds, no changes to
[`schema/pml.schema.json`](../../schema/pml.schema.json), no changes to
[`compiled_model.py`](../../src/pml/compiled_model.py), no changes to
[`serialization.py`](../../src/pml/serialization.py), and no changes to any
generated-state or evidence artifact.

### Positive conformance cases

- Explain an actor by ID and observe the authored `meaning` under Authored;
  no Derived links section is required beyond the empty inverse.
- Explain a concept by ID and observe authored `meaning` and `states`
  (authored sequence, per rule 2).
- Explain a feature by canonical `domains.<d>.features.<f>` and observe the
  authored `purpose`, `actors`, `related_to`, `architecture` (authored
  sequence for each), and derived `use_cases`, `behaviors`, `rule_obligations`
  (each rule-4 sorted); assert that the derived `architecture` inverse
  `referenced_by` on the referenced architecture record includes this
  feature's path.
- Explain a behavior and observe every trigger case (authored sequence for
  `trigger.one_of` alternatives per rule 3 [spec 0011:566], authored
  `statement` or resolved `signal` per case), the completion obligation
  reference, and the derived `use_cases` inverse.
- Explain a signal by ID and observe the authored `meaning`, optional
  `subject`, the derived `producer` (one behavior + completion obligation),
  and every derived `consumers` entry.
- Explain a use-case canonical path and observe **both** the compiled
  use-case record and its corresponding `use_case` obligation rendered under
  separate sections; assert both sections have the same `path`/`id` value.

### Negative conformance cases

- Explain an ID that is a syntactically valid semantic path but is not present
  in any category (e.g., `domains.missing.features.absent`). Assert exit
  code nonzero, empty standard output, standard error containing
  `[unknown-id]`, no changes to any file in the working directory.
- Explain a definition path that has validation diagnostics. Assert exit
  code nonzero, empty standard output, standard error containing the
  existing ordered diagnostics and `PML INVALID: N violation(s)` — the same
  contract asserted for `compile --json` at
  [`test_cli_compile.py:43-71`](../../tests/test_cli_compile.py).
- Explain an ID that is an obligation ID whose behavior has been removed.
  Assert `[unknown-id]` (i.e., the resolver's diagnostic path is not needed
  because the compiled model would already be empty of that record).
- Explain an ID whose input string matches an actor, a concept, and a signal
  simultaneously. Assert that every one of the three categories is rendered
  under a labeled section, in a deterministic order (top-level array order
  from spec 0011:158-177 is the safe order because it matches the closed
  grammar; this is not a semantic priority).
- Attempt `pml explain <manifest-path>` without an ID or
  `pml explain <manifest-path> <id> --something`. Assert argparse rejects
  the invocation before any I/O.
- Confirm the minimal implementation does not write any file, does not
  invoke any bindings, probes, ingestion, or state code path
  ([`project_state.py`](../../src/pml/project_state.py),
  [`ingest.py`](../../src/pml/ingest.py),
  [`probes.py`](../../src/pml/probes.py)).

## Verification

- Approved-text lines cited above are current at spec 0011 (owner-approved
  2026-08-13, present at
  [`docs/specs/0011-compiled-semantic-model.md`](../specs/0011-compiled-semantic-model.md)).
- Current-code lines cited above are present at the audit worktree base
  (`3493fc8`); every file and range in the finding tables corresponds to
  the file layout observed at
  [`src/pml/cli.py`](../../src/pml/cli.py),
  [`src/pml/compiled_model.py`](../../src/pml/compiled_model.py),
  [`src/pml/model_builder.py`](../../src/pml/model_builder.py),
  [`src/pml/resolver.py`](../../src/pml/resolver.py),
  [`src/pml/serialization.py`](../../src/pml/serialization.py), and
  [`src/pml/validator.py`](../../src/pml/validator.py).
- No source or specification file was modified by this audit;
  `git diff --check` produced no output.
