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
Not every top-level array is addressable by a single canonical ID: the
edge categories `relationships[]` and `use_case_memberships[]` are
tuple-identified (spec 0011:346-355 and spec 0011:587-588), so they cannot
be requested by an `explain <id>` invocation whose sole selector is a
single string. The requestable identities (spec 0011:122-149) are:

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

Non-requestable edge categories (surfaced only as derived inverse links
when their endpoint or membership record is explained):

| Category | Identity shape | Producer |
| --- | --- | --- |
| `relationships[]` | tuple `(endpoints[0], endpoints[1])` sorted lexically (spec 0011:346-350, 587); `declared_by` is derived independently | [`model_builder.py:217-232`](../../src/pml/model_builder.py) |
| `use_case_memberships[]` | tuple `(use_case, behavior)` (spec 0011:352-355, 588) | [`model_builder.py:248-255`](../../src/pml/model_builder.py) |

These two categories MUST NOT appear in the single-canonical-ID
requestable set. Explaining them by string would require an owner-approved
composite selector (for example a tuple flag), which spec 0011:665-671
does not authorize. The minimal slice therefore renders them only as
inverse links on their endpoint or membership records, using the two
lookup views defined in finding 7.

**Collision analysis** (this is the load-bearing correctness question for a
single-argument `pml explain <id>` command). Two schema facts govern which
strings each category can produce:

- The `#/$defs/id` regex `^[a-z][a-z0-9_]*$`
  ([`schema/pml.schema.json:19-21`](../../schema/pml.schema.json)) restricts
  `actor`, `concept`, and inline signal IDs to dotless lowercase snake_case,
  and hierarchy segments to the same alphabet
  ([`schema/pml.schema.json:47-48, 315`](../../schema/pml.schema.json)). No
  such value can contain a `.`.
- `vocabularyMap` at
  [`schema/pml.schema.json:61-65`](../../schema/pml.schema.json) has no
  `propertyNames` restriction; a vocabulary term is authored free text and
  may contain any Unicode scalar the loader accepts (spec 0011:83-101), and
  in particular may contain `.` and may equal a hierarchy path or an
  obligation ID verbatim.

The collision families are therefore:

1. **Across `actors`, `concepts`, `signals`** (dotless IDs): each is a
   separate authored namespace (spec 0011:143-145). Spec 0011 does not
   forbid an actor ID and a concept ID from being the same string, and the
   compiled arrays are keyed independently
   ([`model_builder.py:419-430`](../../src/pml/model_builder.py)). A single
   input ID string may therefore match records of more than one of these
   three categories. All three are constrained by `#/$defs/id` above, so
   these collisions cannot spill into hierarchy or obligation shapes.

2. **Vocabulary term vs. every other category**: because a term is
   unrestricted free text ([`schema/pml.schema.json:61-65`](../../schema/pml.schema.json)),
   a term may equal:
   - a bare `actor`, `concept`, or `signal` ID (e.g., the term `signal_a` and
     an inline signal with `id: signal_a`);
   - a domain, feature, behavior, or use-case hierarchy path (e.g., the term
     `domains.core.features.f`), producing a same-string collision with the
     `hierarchy paths` family below;
   - an architecture decision path
     (e.g., the term `architecture.database`);
   - an obligation ID at any depth (e.g., the term
     `domains.core.features.f.behaviors.b.completion` or
     `domains.core.features.f.use_cases.u`).

   This means the collision surface between `vocabulary` and the
   hierarchy/obligation families is not empty. It is not structurally
   forbidden today by
   [`schema/pml.schema.json:61-65`](../../schema/pml.schema.json) and is
   therefore observable by a legitimate compiled model.

3. **Hierarchy paths versus dotless IDs**: hierarchy paths always contain `.`
   segments beginning with `domains.` or `architecture.`
   ([`resolver.py:83-92`](../../src/pml/resolver.py);
   [`model_builder.py:266-357, 431-447`](../../src/pml/model_builder.py)),
   and dotless-ID categories are restricted to `^[a-z][a-z0-9_]*$` (no `.`)
   by `#/$defs/id`. Consequently a hierarchy path cannot collide with an
   actor, concept, or signal ID under the current schema.

4. **Hierarchy paths versus obligation IDs**: this is the one direct
   collision fixed by the approved obligation table
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

5. **Architecture path vs. architecture-constraint obligation**: the
   constraint obligation IDs extend the decision path with
   `.constraints.<constraint-id>`
   ([spec 0011:504](../specs/0011-compiled-semantic-model.md);
   [`model_builder.py:438-441`](../../src/pml/model_builder.py)). No
   collision with the flat `architecture.<decision-id>` path.

6. **Behavior path vs. its behavior-scoped obligations**: obligation IDs
   inside a behavior scope extend the behavior path with
   `.conditions`, `.trigger[.<alt>]`, `.completion`, `.outcome[.<alt>]`, and
   `.failures.<failure>`
   ([spec 0011:496-504](../specs/0011-compiled-semantic-model.md);
   [`resolver.py:169-240`](../../src/pml/resolver.py);
   [`model_builder.py:122-183`](../../src/pml/model_builder.py)). No
   behavior-record path equals an obligation ID.

7. **Feature path vs. feature-scoped obligations**: feature `rules` obligations
   extend the feature path with `.rules.<rule-id>`
   ([spec 0011:502](../specs/0011-compiled-semantic-model.md);
   [`model_builder.py:23-27`](../../src/pml/model_builder.py)); no collision
   with the flat feature path.

8. **`compiled-project.id` vs. project-scoped obligations**: project rules use
   `project` as their node prefix
   ([spec 0011:506-508](../specs/0011-compiled-semantic-model.md);
   [`resolver.py:143-160`](../../src/pml/resolver.py) line 147). The
   `compiled-project.id` is authored separately at
   [`model_builder.py:401`](../../src/pml/model_builder.py). A project-scoped
   rule obligation is `project.rules.<rule-id>`; it cannot collide with a
   feature path, but it is disjoint from the project record itself because
   the project record is addressed by the fixed keyword `project`.

**Conclusion**: the collision families a canonical-ID lookup must handle are:

- **actor / concept / signal** (dotless namespace): one input string may match
  up to three of these records.
- **vocabulary-term versus every other category**: because vocabulary terms
  are unrestricted free text
  ([`schema/pml.schema.json:61-65`](../../schema/pml.schema.json)), a term
  may collide with an actor/concept/signal ID, a hierarchy path
  (`domains.<d>.features.<f>[.behaviors.<b> | .use_cases.<u>]`), an
  architecture path (`architecture.<d>`), or any obligation ID. A minimal
  implementation MUST NOT drop a matching vocabulary record on the basis
  that "hierarchy paths cannot alias flat IDs"; that claim is true only for
  dotless namespaces.
- **use-case path**: same input string always denotes both a use-case
  compiled record and its `use_case` obligation (guaranteed identity by
  spec 0011:503-509, not a bug).

Prefix inspection alone is therefore insufficient: a term may syntactically
look like a hierarchy or obligation path. Dispatch MUST probe every category
index. Everything outside these families is structurally disjoint.

Classification: **implementation detail**. Category dispatch is a
`Category -> {id: record}` lookup that a minimal implementation must maintain
against the compiled model it already produces; the categories and ID rules
are approved. The vocabulary/hierarchy and vocabulary/obligation same-string
cases are collisions that the dispatch must render, not new contracts.

### 3. Exact authored fields and derived links per category

The full closed field list per category is enumerated at spec 0011:158-363,
implemented as the closed `TypedDict`s at
[`compiled_model.py:14-336`](../../src/pml/compiled_model.py). Nothing here
requires additional owner approval. The remaining question for `pml explain`
is the boundary spec 0011:670-671 requires: "It must distinguish authored
fields from derived inverse links".

The authored/derived split follows from the approved determinism tables at
spec 0011:536-591 together with what `_build_compiled_model` actually
constructs. **Every `path`, `domain`, and `feature` cross-record reference
on a structural record is derived from the enclosing map keys, not authored
directly**: `_build_compiled_model` synthesizes `domains.<id>` at
[`model_builder.py:267`](../../src/pml/model_builder.py),
`domains.<d>.features.<f>` at
[`model_builder.py:282`](../../src/pml/model_builder.py),
`...behaviors.<b>` at
[`model_builder.py:312`](../../src/pml/model_builder.py), the use-case
`path` and its self-referring `obligation` at
[`model_builder.py:345-356`](../../src/pml/model_builder.py), and
`architecture.<d>` at [`model_builder.py:434, 439`](../../src/pml/model_builder.py).
The `id` field on a structural record is the authored map key of the
enclosing mapping (spec 0011:122-149; produced by dict iteration at
[`model_builder.py:266, 281, 311, 345, 446`](../../src/pml/model_builder.py)),
so `id` is authored but `path` is a canonical string built from that key
plus the parent hierarchy prefix. Likewise on a compiled behavior,
`trigger.kind`, `outcome.kind`, every `obligation` reference inside a
trigger/outcome/failure case, the top-level `completion_obligation`, and
the alternative case `id` field are all generated by
[`model_builder.py:46-95, 313-336`](../../src/pml/model_builder.py); the
authored transition values are `statement`, the resolved `signal`
reference, and `conditions.statements`. Concretely per category:

| Category | Authored values | Derived identity/structural fields | Derived inverse links |
| --- | --- | --- | --- |
| `compiled-project` | `id`, `name`, `purpose` ([spec 0011:180-185](../specs/0011-compiled-semantic-model.md); [`model_builder.py:400-406`](../../src/pml/model_builder.py)) | none | `rule_obligations` (rule 4), `domains` (rule 4) |
| `compiled-vocabulary-term` | `term` (authored map key), `meaning`, `forbidden_synonyms` (authored sequence, rule 2) | none | none |
| `compiled-actor` | `id` (authored map key), `meaning` | none | none |
| `compiled-concept` | `id` (authored map key), `meaning`, `states` (authored sequence, rule 2) | none | none |
| `compiled-architecture-decision` | `id` (authored map key), `category`, `selection`, `rationale` | `path` (`architecture.<id>`, derived at [`model_builder.py:434`](../../src/pml/model_builder.py)) | `constraint_obligations` (rule 4), `referenced_by` (rule 4, [spec 0011:578-579](../specs/0011-compiled-semantic-model.md)) |
| `compiled-domain` | `id` (authored map key), `purpose` | `path` (`domains.<id>`, derived at [`model_builder.py:267`](../../src/pml/model_builder.py)) | `rule_obligations` (rule 4), `features` (rule 4) |
| `compiled-feature` | `id` (authored map key), `purpose`, `actors` (rule 2), `experience` (present-or-absent, spec 0011:236-251), `related_to` (rule 2, spec 0011:539), `architecture` (rule 2, spec 0011:539; note that each authored decision ID is expanded to its `architecture.<d>` path at [`model_builder.py:301-304`](../../src/pml/model_builder.py)) | `path` (derived at [`model_builder.py:282`](../../src/pml/model_builder.py)), `domain` (parent hierarchy) | `rule_obligations`, `use_cases`, `behaviors` (all rule 4) |
| `compiled-behavior` | `id` (authored map key), `conditions.statements` (rule 2), the `statement` and resolved `signal` reference values inside each trigger/outcome/failure case, `related_to` (rule 2, spec 0011:540) | `path` (derived at [`model_builder.py:312`](../../src/pml/model_builder.py)), `feature`, `trigger.kind`, `outcome.kind`, `outcome.exclusivity_obligation`, each case `obligation` and case `id`, and `completion_obligation` (all built at [`model_builder.py:46-95, 313-336`](../../src/pml/model_builder.py)) | `rule_obligations`, `use_cases` (rule 4) |
| `compiled-use-case` | `id` (authored map key), `actor`, `goal`, `behaviors` (rule 2, spec 0011:540) | `path` (derived at [`model_builder.py:346`](../../src/pml/model_builder.py)), `feature`, and `obligation` (equals `path` per spec 0011:503-509; produced at [`model_builder.py:355`](../../src/pml/model_builder.py)) | none |
| `compiled-signal` | `id`, `meaning`, optional `subject` (authored inside the producing completion at [`resolver.py:284-311`](../../src/pml/resolver.py)) | none | `producer`, `consumers` (both derived from `outcome`/`failure` and trigger cases, [`model_builder.py:186-214`](../../src/pml/model_builder.py); rule 4 [spec 0011:586](../specs/0011-compiled-semantic-model.md)) |
| `compiled-relationship` | none (record itself is derived) | `kind`, `endpoints`, `declared_by` (all derived from authored `related_to`, [spec 0011:476-482](../specs/0011-compiled-semantic-model.md); [`model_builder.py:217-232`](../../src/pml/model_builder.py)) | (the record IS an inverse) |
| `compiled-use-case-membership` | none | `use_case`, `behavior` (derived from use-case `behaviors`, spec 0011:484-488; [`model_builder.py:248-260`](../../src/pml/model_builder.py)) | (the record IS an inverse) |
| `compiled-obligation` | inside `definition`: `statement` values, resolved `signal` reference values, condition `statements`, use-case `actor`, `goal`, `behaviors` | `id`, `node`, `kind`, and the `outcomes`/`failures`/`alternatives` reference arrays inside `completion` and `outcome_exclusivity` definitions (all built at [`model_builder.py:122-183`](../../src/pml/model_builder.py) from the approved obligation table [spec 0011:494-515](../specs/0011-compiled-semantic-model.md)) | none |

The `id` field on a structural record and the `path` field derived from
that same authored key are semantically the same identifier; only the
authored form (the map key) is authored intent, while the canonical
hierarchy `path` is a generated projection. `pml explain` MUST render them
under the "authored / derived" split accordingly: the authored map key in
the authored section, the canonical `path` in the derived section, and the
parent hierarchy references (`domain`, `feature`) alongside `path`.

Trigger and outcome case containers are approved authored transition shapes
(spec 0011:432-450) — but only the `statement` or resolved `signal`
reference inside each case is authored intent. The surrounding `kind`,
`obligation`, and alternative `id` fields are generated stable metadata.
Rendering the whole case container as "authored" would present generated
material as approved intent and is forbidden by spec 0011:665-671.

Classification: **implementation detail**. The split is fully determined by
the approved grammar plus what `_build_compiled_model` actually constructs;
a minimal implementation MUST render each record's authored values in one
section, its derived identity/structural fields (paths, hierarchy
back-references, generated obligation references, generated `kind` labels,
generated `case`/`alternative` metadata) in a second section, and its
derived inverse links (obligation and cross-record inverse arrays) in a
third section. Neither generated identity/structural fields nor generated
transition metadata may appear inside the authored section.

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
- **Unsupported compiled-model versions** (spec 0011:651-656): every
  consumer MUST check `format` and support the exact `format_version` before
  reading records, and MUST treat unknown versions as unsupported rather
  than guessing. This requirement is unconditional — the spec does not
  exempt an in-process consumer. `pml explain` MUST therefore, before
  building any category index or resolving the requested canonical ID
  against the model, verify that `model["format"] == "pml.compiled"` and
  `model["format_version"] == 1`
  ([`compiled_model.py:319-336`](../../src/pml/compiled_model.py) fixes both
  values at production, but the check is what the consumer contract
  requires — an inline producer sharing a process does not remove the
  invariant). On rejection, the command MUST exit nonzero, write a single
  `[unsupported-model] <format>@<format_version> is not supported` diagnostic
  (following the established `[<code>] <message>` shape at
  [`diagnostics.py`](../../src/pml/diagnostics.py); the specific code string
  is an implementation detail), and write nothing to standard output. This
  guard is a required seam even in the initial slice where the compiled
  model is produced in-process, because it is the same contract the future
  pre-serialized-model variant, `pml graph`, and the web explorer will
  reuse. The exact spelling of the diagnostic string is an implementation
  detail; the contractual behavior (checked before reading, nonzero exit,
  empty stdout, stderr diagnostic) is not.

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
  finding-2 collision families: dotless actor/concept/signal namespace,
  vocabulary-term vs. hierarchy path or obligation ID, and the intentional
  use-case-path vs. use-case-obligation double). Spec 0011 does not
  disambiguate. Three alternatives are all consistent with the approved
  text:

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
- Before building any category index or resolving the requested ID, the
  command asserts `model["format"] == "pml.compiled"` and
  `model["format_version"] == 1` (spec 0011:651-656) and emits the
  `[unsupported-model]` diagnostic + nonzero exit + empty standard output
  described in finding 5 on failure. The check is on the compiled-model
  seam so a later pre-serialized-model variant, `pml graph`, and the web
  explorer share the same guard.
- The requested ID is dispatched against every category index (finding 2)
  so that vocabulary/hierarchy and vocabulary/obligation same-string
  matches are not dropped, and every category that matches is rendered
  under its own section, so no category-priority contract is introduced.
- Each record's authored values are rendered in one section, its derived
  identity/structural fields (paths, hierarchy back-references, generated
  transition/case metadata, generated obligation references) in a second
  section, and its derived inverse links in a third; empty derived arrays
  are rendered as an empty bullet list rather than as a claim of absence.
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
   identity field (`id`, `term`, or `path` per finding 2). Because vocabulary
   terms are unrestricted free text
   ([`schema/pml.schema.json:61-65`](../../schema/pml.schema.json)), the
   index MUST NOT be short-circuited by prefix filtering when the input
   string looks like a hierarchy or obligation path — every category's map
   must be consulted. This is a read-only projection of an
   already-materialized model
   ([`_build_compiled_model` at lines 395-456](../../src/pml/model_builder.py))
   and requires no schema change. `pml graph` reuses the same index to look
   up nodes referenced by directed producer-completion→signal→consumer-trigger
   edges, symmetric `related_to` edges, and use-case membership edges
   (spec 0011:673-683).

2. **`(canonical-id) -> [category]` reverse dispatch**. Given a canonical ID
   string, return every category whose ID index contains it, so a consumer
   can render or navigate every matching record without embedding
   category-priority semantics. Its return value MUST NOT depend on prefix
   heuristics; it MUST be built by probing every category's index. This is
   the primitive that lets `pml graph` and the web UI share explain's
   dispatch without reinterpreting YAML.

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

5. **Relationship endpoint-lookup view**. For a feature or behavior path,
   return every `compiled-relationship` whose `endpoints` contains that
   path — regardless of which endpoint authored the reference (see
   `declared_by` at [`model_builder.py:217-232`](../../src/pml/model_builder.py)
   and spec 0011:346-350, 476-482). Because the top-level `relationships`
   array is the canonical symmetric projection of resolved authored
   `related_to` lists (spec 0011:476-482), an incoming-only edge (i.e., the
   other endpoint's authored `related_to` includes this path but this
   record's own `related_to` does not) still yields a matching relationship
   record whose `declared_by` names the other endpoint. The lookup MUST
   therefore probe `endpoints`, not the record's own authored `related_to`,
   so `pml explain` displays symmetric relationships as spec 0011:667-671
   requires. `pml graph` reuses this same view to render symmetric
   `related_to` edges without reinterpreting authored YAML.

6. **Use-case membership lookup view**. For a feature or behavior path,
   return every `compiled-use-case-membership` whose `behavior` field
   equals that path; for a use-case path, return every membership whose
   `use_case` field equals that path (spec 0011:352-355, 484-488; produced
   at [`model_builder.py:248-260`](../../src/pml/model_builder.py)). The
   inverse index on each behavior's `use_cases` array
   ([`compiled_model.py:168-180`](../../src/pml/compiled_model.py);
   [`model_builder.py:256-260, 335`](../../src/pml/model_builder.py)) and
   the authored-order behaviors list on each compiled use case
   ([`model_builder.py:354`](../../src/pml/model_builder.py)) are two
   projections of this set. Explaining a behavior therefore surfaces every
   use case that references it, and explaining a use case surfaces every
   behavior it authored — both sides of the membership, as spec 0011:667-671
   requires. `pml graph` reuses this same view to render use-case
   membership edges.

None of these primitives require a schema, validator, compiler, CLI beyond
the new `explain` subparser, or generated-state change. Each is a pure
function over the compiled model.

## Gap classification summary

| Gap | Classification |
| --- | --- |
| Exact invocation string is derivable from convention but not printed in docs | Documentation gap (updated after implementation lands) |
| Optional flags (JSON echo, category filter, authored-only) | Owner-decision blocker — do not add |
| Category dispatch of a canonical ID via prefix + ID index | Implementation detail |
| Actor/concept/signal same-string ambiguity (dotless namespace) | Owner-decision blocker only if minimal slice hides matches; otherwise implementation detail (render each match) |
| Vocabulary-term vs. hierarchy path or obligation ID same-string collision (vocabulary terms are unrestricted free text at [`schema/pml.schema.json:61-65`](../../schema/pml.schema.json)) | Implementation detail (dispatch probes every category index; dropping a matching vocabulary record would be a defect) |
| Use-case path guaranteed to match both use-case record and use_case obligation | Approved by spec ([0011:503-509](../specs/0011-compiled-semantic-model.md)); implementation detail |
| Tuple-identified edge categories `relationships[]` and `use_case_memberships[]` (spec 0011:346-355, 587-588) | Non-requestable by a single canonical ID; requestability would require an owner-approved composite selector. Minimal slice surfaces these edges only through the endpoint- and membership-lookup views (finding 7 primitives 5-6), including relationships declared only by the other endpoint and both sides of every membership. |
| Authored values vs. derived identity/structural fields vs. derived inverse links split per record | Implementation detail (three-section rendering required so generated `path`/`kind`/case metadata is not shown as authored) |
| Presentation ordering within a rendered record | Implementation detail (human-readable text only) |
| Diagnostic code and message for unknown ID | Implementation detail (reuse existing `[code] message` shape) |
| Unsupported compiled-model version check (spec 0011:651-656) | Required seam in the minimal slice; behavior fixed (checked before reading records, nonzero exit, empty stdout, `[unsupported-model]` diagnostic on stderr); message spelling remains an implementation detail |
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
2. Verifies, before building any category index or resolving the requested
   canonical ID, that `model["format"] == "pml.compiled"` and
   `model["format_version"] == 1` (spec 0011:651-656). On rejection, exits
   nonzero, writes a single `[unsupported-model] <observed-format>@<version> is not supported`
   line to standard error, and writes nothing to standard output.
3. Builds a category-typed ID index over the compiled model as a private
   helper, without changing the compiled-model schema or the
   [`compiled_model.py`](../../src/pml/compiled_model.py) closed types.
   The index probes every category rather than pre-filtering by input-string
   shape, so vocabulary/hierarchy and vocabulary/obligation same-string
   collisions surface as multi-category matches instead of being dropped.
4. Dispatches the requested ID against that index, and for every matching
   category renders one section header naming the category, an "Authored"
   subsection listing that record's authored values, a "Derived
   identity/structural" subsection listing the derived hierarchy `path`, any
   parent hierarchy references (`domain`, `feature`), generated `kind` and
   case metadata (for behaviors), and generated obligation references
   (`completion_obligation`, per-case `obligation`, use-case `obligation`),
   and a "Derived inverse links" subsection listing rule-4 back-references
   (`rule_obligations`, `use_cases`, `behaviors`, `features`, `domains`,
   `referenced_by`, signal `producer`/`consumers`) **plus** the results of
   the relationship endpoint-lookup and use-case-membership lookup views
   from finding 7 for feature, behavior, and use-case matches. For a
   feature or behavior match, every relationship with that path in
   `endpoints` is rendered under Derived inverse links regardless of
   `declared_by` — including a relationship declared only by the other
   endpoint — and every use-case membership with that path in `behavior`
   is rendered. For a use-case match, every membership with that path in
   `use_case` is rendered. Neither `compiled-relationship` nor
   `compiled-use-case-membership` is otherwise requestable by a single
   canonical ID; a user cannot ask for one directly, so `pml explain`
   surfaces them only through these inverse views.
5. On no match, exits nonzero and writes a single
   `<id>: [unknown-id] no compiled record matches this ID` line to standard
   error, with empty standard output, following the
   [`cli.py:285-287`](../../src/pml/cli.py) precedent.
6. On invalid definition input, exits nonzero and writes the standard ordered
   diagnostics to standard error with empty standard output, mirroring the
   compile behavior at [`cli.py:83-99`](../../src/pml/cli.py).

No new flags, no new record categories, no new obligation kinds, no changes to
[`schema/pml.schema.json`](../../schema/pml.schema.json), no changes to
[`compiled_model.py`](../../src/pml/compiled_model.py), no changes to
[`serialization.py`](../../src/pml/serialization.py), and no changes to any
generated-state or evidence artifact.

### Positive conformance cases

- Explain an actor by ID and observe the authored `id` and `meaning` under
  Authored; the "Derived identity/structural" subsection is empty because
  actors have no derived `path`, and the "Derived inverse links" subsection
  is empty because actors have no inverse arrays.
- Explain a concept by ID and observe authored `id`, `meaning`, and
  `states` (authored sequence, per rule 2).
- Explain a feature by canonical `domains.<d>.features.<f>` and observe
  authored `id`, `purpose`, `actors`, `related_to`, and `architecture`
  (authored sequences retained per rule 2) under Authored; the derived
  `path` and `domain` back-reference under Derived identity/structural; and
  `rule_obligations`, `use_cases`, `behaviors` (each rule-4 sorted) under
  Derived inverse links. Assert that the referenced architecture record's
  `referenced_by` includes this feature's `path`.
- Explain a behavior and observe under Authored only the `id`, authored
  `conditions.statements` (if present), authored `related_to`, and each
  case's `statement` or resolved `signal` reference value; observe under
  Derived identity/structural the `path`, `feature` back-reference,
  `trigger.kind`, `outcome.kind`, `outcome.exclusivity_obligation`, each
  case's generated `id` and `obligation` reference, and
  `completion_obligation`. Assert the "Authored" section does not include
  `path`, `feature`, `kind`, per-case `obligation`, or `completion_obligation`.
- Explain a signal by ID and observe under Authored `id`, `meaning`, and
  optional `subject`; the derived `producer` (one behavior + completion
  obligation) and every derived `consumers` entry appear under Derived
  inverse links.
- Explain a use-case canonical path and observe **both** the compiled
  use-case record and its corresponding `use_case` obligation rendered
  under separate sections; assert both sections have the same `path`/`id`
  value, and that the use-case compiled record's `path`, `feature`, and
  self-referring `obligation` appear only under Derived identity/structural.
- Explain a vocabulary term whose exact text is `domains.core.features.f`
  where a feature with that path also exists. Assert that both the
  vocabulary record and the feature record are rendered under separate
  category sections, and neither is dropped by dispatch.
- Explain a vocabulary term whose exact text is
  `domains.core.features.f.behaviors.b.completion` where that completion
  obligation also exists. Assert that the vocabulary record and the
  obligation record are both rendered under separate category sections.
- **Incoming-only relationship** (finding 7, primitive 5). Given two
  features `A` and `B` where only `B`'s authored `related_to` names `A`,
  the compiled model produces one symmetric relationship whose `endpoints`
  are `[A, B]` (spec 0011:476-482) and whose `declared_by` is `[B]` only
  ([`model_builder.py:217-232`](../../src/pml/model_builder.py)). Explain
  `A` and assert its Derived inverse links section shows that relationship
  with endpoints `[A, B]` and `declared_by: [B]`, even though `A`'s own
  `related_to` is empty. Explain `B` and assert its Derived inverse links
  section shows the same relationship. Neither invocation may drop the
  edge on the basis of `declared_by`.
- **Both sides of a use-case membership** (finding 7, primitive 6). Given
  a use case `U` at `domains.d.features.f.use_cases.u` whose authored
  `behaviors` names `domains.d.features.f.behaviors.b`, explain `U` and
  assert its authored `behaviors` list includes `b` in authored order and
  its Derived identity/structural section shows the self-referring
  `use_case` obligation; then explain `b` and assert its Derived inverse
  links section shows a use-case membership `(U, b)` (equivalently, `b`'s
  derived `use_cases` inverse contains `U`). Both directions must be
  rendered from the same materialized memberships.

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
- **Unsupported model seam**: at the same seam where the minimal
  implementation calls into its internal `explain` function, hand it a
  compiled-model-shaped mapping whose `format` is not `pml.compiled` or
  whose `format_version` is not `1`. Assert the function returns a nonzero
  exit code, writes nothing to standard output, and writes a single
  `[unsupported-model] ...` line to standard error before it consults the
  ID index. This exercises the consumer-contract guard required by
  spec 0011:651-656 even though the outer CLI path produces a compliant
  model in-process.
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
