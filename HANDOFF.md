# PML handoff

Updated: 2026-08-11

## Current focus

The behavior transition model received explicit owner approval on 2026-08-11.
The next work is the ordered schema and semantic-validator migration. Formatter,
compiler, bindings, probes, lock, and generated state follow only after validation
behavior and conformance examples are defined.

The design discussion was prompted by real definitions in
[`ag2trust/ag2trust-pml` PR #2](https://github.com/ag2trust/ag2trust-pml/pull/2),
especially an `attention_lifecycle` behavior whose `context` and `output` fields
obscured the initial state, initiating action, intended result, and downstream
consequences.

The approved decisions are captured in
[`docs/specs/0010-behavior-transition-model.md`](docs/specs/0010-behavior-transition-model.md).
No schema, validator, compiler, formatter, examples, bindings, probes, or
generated-state implementation has yet been changed for this design.

## Approved direction

The approved closed behavior shape is:

```text
behavior = {
  conditions?: conditions,
  trigger: trigger,
  outcome: outcome,
  failures?: failure-map,
  rules?: rule-map
}
```

Approved decisions:

- A behavior is one bounded, independently addressable product transition.
- Behaviors have no descriptive, `purpose`, or `intent` field; their semantic
  fields must be sufficient without a redundant summary.
- Replace behavior `context` with optional `conditions`.
- All conditions must hold when the trigger occurs. Otherwise the behavior does
  not apply and no evaluation begins; any required response is another behavior.
- `trigger` is required and contains either one direct trigger or an ID-keyed
  `one_of` map of alternative triggers.
- A direct trigger is either a `statement` or a reference to a declared signal.
- Replace `output` with required `outcome`. `outcome` means successful completion
  and requires a local statement. It may use `one_of` for multiple successful
  alternatives.
- Add optional `failures`, an ID-keyed map of unsuccessful completions. Each
  failure requires a local statement. A correctly produced authored failure is
  conformant.
- Every initiated evaluation completes exactly one successful outcome or one
  authored failure. None or multiple is nonconformant.
- Replace plural `emits` with an optional inline singular `signal` definition per
  outcome or failure: a completion contains no signal or one signal, never more.
- When a signal is authored, its inline definition is the authoritative producer
  for its globally unique ID. It contains `id`, optional product `subject`, and
  `meaning`; the separate global signal registry is removed.
- A signal's optional subject preserves one product-instance identity between
  producer and consumers without prescribing a technical payload or transport.
  It must reference a declared product concept and cannot introduce another
  product-object category.
- Completing a signal-bearing outcome or failure creates one occurrence. Each
  consuming behavior is considered once for that occurrence, and its conditions
  are evaluated then. Failed conditions do not cause later re-evaluation.
- One signal may have multiple consumers. Alternative causes of the same signal
  belong in the producer's `trigger.one_of`, not in multiple producers.
- Remove `reactions`; a signal consequence becomes an ordinary behavior triggered
  by that signal.
- Keep behavior-level `related_to` for broader symmetric product relationships.
  Signals express precise directed behavior causality. Remove behavior-level
  `architecture`, which remains a feature-level concern.
- Transition obligations use stable paths for conditions, triggers, completion
  exclusivity, outcomes, and failures; signals are verified within their producing
  completion rather than as separate obligations.
- Keep `experience` at feature scope because persistent surfaces commonly span
  several behaviors. Behavior-specific visible changes belong in outcomes/rules.
- Simplify feature use cases to `actor`, `goal`, and a unique non-empty list of
  behavior references. The list expresses contributing membership, not ordering.
- Use fully qualified behavior semantic paths for every use-case behavior
  reference; local references have no separate shorthand.
- Use-case goals remain independently verifiable end-to-end; conforming referenced
  behaviors alone does not prove goal conformance.
- Do not add structured lifecycle transition fields; they duplicate conditions and
  outcomes.
- Do not add a general workflow/order construct; signal-to-trigger edges express
  causal order.
- Keep precise time and quantity requirements in authored statements/rules until
  real definitions demonstrate a need for structured scalar types.
- Keep retry and concurrency requirements as observable conditions, outcomes,
  failures, or rules; do not add execution-control fields without a demonstrated
  language gap.

## Approval and delivery readiness

The foundational questions identified during discussion are resolved. The approved
now defines canonical behavior references, signal subjects, retry and concurrency
scope, transition obligation paths, collection bounds, closed grammar, and
migration authority boundaries. Definition-specific migration mappings remain
agent-assisted delivery work after semantic approval rather than a language-design
question.

Owner approval was given explicitly on 2026-08-11. Schema and semantic validation
are now authorized as the next delivery phase; downstream tooling is not yet
authorized to precede validation behavior.

## Planned post-approval improvement

After the behavior-transition semantics are owner approved, design a canonical
semantic intermediate representation compiled from validated PML. It should
resolve behavior identities, triggers, outcomes, failures, signals, consumers,
and obligations into one model used consistently by semantic validation and
downstream commands. PML YAML remains the authored language; the representation
is derived and MUST NOT alter approved intent.

Potential read-only interfaces include `pml compile --json`, `pml explain`, and
`pml graph`. The exact representation must follow the approved language design,
not precede or constrain it.

A later visual component should provide a web page for exploring PML artifacts
and their relationships. It should consume the same compiled semantic model and
offer navigable project/domain/feature/behavior views, causal signal graphs,
artifact details, and validation findings. Graph rendering should use a free
option such as Graphviz. The visual component is a derived, read-only projection;
it is not an authored PML format and MUST NOT modify or reinterpret approved
definitions.

## Required workflow

PML is a closed language. Continue in this order:

1. Update schema and semantic validation.
2. Add positive and negative conformance examples/tests.
3. Update obligation resolution, bindings/probes, formatter/compiler, lock/state,
   and command behavior only after validation behavior is defined.

Do not introduce compatibility aliases unless separately approved. Generated state
and evidence must never alter approved intent.

## Repository state

- Working directory: the active PML repository clone.
- Branch: `design/behavior-transition-model`
- The branch includes current `origin/master` at `6ac528a` (`Merge pull request
  #19 from ag2trust/feature/pml-init-skill`).
- The approved behavior-transition specification and this handoff are preserved on
  the dedicated design branch pending review and merge.
- The independent `pml init` and packaged-skill implementation was merged through
  PR #19.
- `git diff --check` passes.
- The final init slice passed its full test and packaging review before merge.

Unrelated pre-existing local artifacts are preserved in the named Git stash
`preserve pre-existing local artifacts 2026-08-06` rather than mixed into this
design branch:

```text
?? .claude/
?? 2026-07-31-132205-hi-keep-answers-short-check-handoff-handoffmd.txt
?? HANDOFF-2026-08-06-pml-init-skill.md
?? uv.lock
```

Preserve those artifacts. `.claude/` is represented by
[`ag2trust/pml` PR #5](https://github.com/ag2trust/pml/pull/5); the others were not
included in either focused change.

## Pickup

Start with:

```sh
git status --short
sed -n '1,320p' docs/specs/0010-behavior-transition-model.md
```

The next change should update the schema and semantic validator, with positive and
negative conformance examples. Do not update downstream formatter, compiler,
bindings, probes, lock, or state behavior before validation behavior is defined.
