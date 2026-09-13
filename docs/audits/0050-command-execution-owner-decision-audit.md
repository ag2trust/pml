# Task 5: proposed command-execution semantics delta audit

Audited at `3493fc890b25dc03bd3f6a934c0ad753003be1ab` on 2026-09-10.
This is a read-only owner-decision aid. It neither approves nor changes proposed
[0008](../specs/0008-command-execution-semantics.md), owner-approved
[0005](../specs/0005-bindings-boundary.md), [0007](../specs/0007-project-workflow.md),
[0010](../specs/0010-behavior-transition-model.md), or
[0011](../specs/0011-compiled-semantic-model.md). Generated state and evidence
remain non-authoritative records about an approved definition.

## Result and authority boundary

0008 remains **Proposed** ([0008:1-11](../specs/0008-command-execution-semantics.md)).
It is not authority to add its schemas, validators, commands, or execution
behavior. The checked-in handoff makes that same boundary explicit
([`HANDOFF.md`:20-31](../../HANDOFF.md)).

The checkout already implements the approved initialization contract, lock
*consumption* for independent definition/bindings digests, report ingestion, and
read-only state/status validation. It does **not** implement lock creation,
`sync`, `verify`, environments, tool-generated reports, or argument-free locked
commands. Some existing probe and state mechanics are useful foundations, but do
not satisfy the more specific 0008 rules and must not be described as such.

## Area-by-area delta

| 0008 area | Already implemented under earlier approved authority | Absent or diverged from proposed 0008 |
| --- | --- | --- |
| Initialization | `pml init --id --name` is registered in [`src/pml/cli.py`:31-81](../../src/pml/cli.py). `initialize_project` derives the fixed sibling source, emits exactly `pml: 0.1-draft` with project ID/name and empty bindings, creates `probes/`, `.pml/`, and the packaged skill ([`src/pml/initialize.py`:44-100](../../src/pml/initialize.py)); the layout is asserted in [`tests/test_initialize.py`:13-36](../../tests/test_initialize.py). This realizes 0007:69-94 and 0008:13-37 without creating a lock, state, review, or environment artifact. Top-level destination checks include dangling symlinks, and descriptor-relative exclusive creation plus the partial-artifact behavior are implemented in [`src/pml/initialize.py`:56-61, 78-134](../../src/pml/initialize.py), with race/collision tests at [`tests/test_initialize.py`:73-211](../../tests/test_initialize.py). | No material command-semantic gap found. The initialized definition deliberately fails ordinary definition validation because it omits `project.purpose` and domains, as 0008:30-33 requires; this follows directly from the emitted shape rather than an initialization-time validation call. The copied `SKILL.md` directs authors to the separately maintained language reference; audit 0049 finds that reference stale about removed transition grammar. The copied skill bytes therefore match the release, but its indirect guidance dependency is stale. |
| Lock creation and source identity | Lock **reading** validates the lock schema, definition digest, exact resolved source, adjacent bindings, and bindings digest ([`src/pml/project_state.py`:856-937](../../src/pml/project_state.py)). The current lock schema independently requires definition and bindings digests ([`schema/pml-lock.schema.json`:5-27](../../schema/pml-lock.schema.json)), implementing the 0005 separation in 0005:45-78. Bindings validation also enforces resolved obligation coverage and product-relative path safety ([`src/pml/project_state.py`:698-846](../../src/pml/project_state.py)). | No `lock` parser branch exists: the complete CLI registration is [`src/pml/cli.py`:31-73](../../src/pml/cli.py). No code writes a lock, discovers/validates lock-selected probes, obtains Git revision/cleanliness, serializes a product-relative source, or atomically replaces the lock. Current schema requires `definition.revision`, permits any nonempty (including absolute) `source`, and has no environment or review digest. `load_locked_bindings` calls `Path.resolve()` ([`src/pml/project_state.py`:881-905](../../src/pml/project_state.py)), so it is a consumer-side exact-source check, not 0008's non-symlink source traversal policy. |
| Generated-state reconciliation | Product and architecture state are distinct paths ([`src/pml/project_state.py`:54-60](../../src/pml/project_state.py)). Read-only validation detects missing state, stale node/bindings/input/relationship fingerprints, unexpected evidence, and missing obligations ([`src/pml/project_state.py`:1017-1135](../../src/pml/project_state.py)); `check` invokes those validators without writes ([`src/pml/cli.py`:233-276](../../src/pml/cli.py)). Report ingestion atomically replaces individual touched state files after validating its report and inputs ([`src/pml/ingest.py`:36-79, 178-324](../../src/pml/ingest.py); atomic writer [`src/pml/project_state.py`:253-351](../../src/pml/project_state.py)). | No `sync` command exists. Ingestion only reconciles touched nodes; it is not a complete desired-state plan. On a node definition or bindings digest change it clears **all** evidence before recording the report ([`src/pml/ingest.py`:227-240]), whereas 0008:79-106 retains stale records while their lane resolves and clears only disallowed methods/probes. Current state-level fields hold definition, bindings, input, and relationship fingerprints ([`schema/pml-state.schema.json`:7-28](../../schema/pml-state.schema.json)); accepted implementation records lack all four and deterministic evidence lacks target/bindings/relationship and environment fingerprints ([`schema/pml-state.schema.json`:82-186](../../schema/pml-state.schema.json)). It therefore cannot implement 0008's per-record freshness or its warning/removal rules. |
| Execution environments | The pre-existing probe shape requires an `env` identifier and permits an `as` actor ([`schema/pml-probe.schema.json`:5-17, 40-79](../../schema/pml-probe.schema.json)); the loader resolves `as` against definition actors ([`src/pml/probes.py`:87-105](../../src/pml/probes.py)). | There is no `environments.yaml` schema, loader, validator, lock field/digest, host-variable resolution, secret-redaction code, HTTP configuration, executable resolver, or fixture containment code. The probe loader does not resolve `env` at all. Its existing path grammar is not 0008's environment-path contract: it has no nested `.`-segment exclusion and does not establish filesystem containment ([`schema/pml-probe.schema.json`:20-29](../../schema/pml-probe.schema.json)). |
| Deterministic probe discovery and execution | `load_probes` validates the existing closed probe schema, unique probe IDs, resolved obligation targets, binding selection when bindings are supplied, actor references, duplicate captures, and use-before-capture ([`src/pml/probes.py`:33-106](../../src/pml/probes.py)). This provides part of 0007:116-125's static discovery/coverage boundary. Stored deterministic evidence retains a probe ID and probe fingerprint, and validation compares it with the loaded probe ([`src/pml/project_state.py`:1263-1366](../../src/pml/project_state.py)). | No `verify` command or runtime executor exists; a source search finds no subprocess or HTTP client use in `src/`. `load_probes` uses unbounded `Path.rglob` without regular-file/non-symlink checks, entry/file-size caps, or the 64-step schema limit ([`src/pml/probes.py`:40-64](../../src/pml/probes.py); [`schema/pml-probe.schema.json`:13-17](../../schema/pml-probe.schema.json)). Thus it also falls short of already-approved 0007:127-137. No current validation enforces 0008's contextual `${name}` syntax or allowed substitution sites, timeout ceiling, body/fixture semantics, session behavior, output caps, sequential ID order, failure/block distinction, or all-or-nothing hard-limit rule. The current loader's broad `\{name\}` scan ([`src/pml/probes.py`:23-24, 87-105](../../src/pml/probes.py)) is not that contract. |
| Tool-generated reports | External report ingestion is an existing atomic mutation boundary: it enforces closed report structure, report/target/evidence-lane semantics, duplicate lanes, and matching bound deterministic probes before writes ([`src/pml/ingest.py`:36-176](../../src/pml/ingest.py)). This implements the external-report portions of 0007:179-277. External reports can already record the four report verdicts and deterministic result values ([`schema/verification-report.schema.json`:20-31, 90-117](../../schema/verification-report.schema.json)). | The current report verifier is only the agent object ([`schema/verification-report.schema.json`:74-84](../../schema/verification-report.schema.json)); the state schema repeats that agent-only shape ([`schema/pml-state.schema.json`:50-59](../../schema/pml-state.schema.json)). There is no `{tool: "pml", version: ...}` union, generated report ID/time/version, product Git dirty calculation, execution-environment digest, report-environment grouping, secret redaction, or `verify` exit behavior. Ingestion does not derive or check a report verdict against check results; it only schema-checks the supplied verdict. 0008's tool-report union consequently changes the 0007:207-232 external-report grammar rather than merely filling in an implementation detail. |
| Locked and compatibility command forms | Current explicit `status`, `architecture-status`, `check`, and `ingest-report` calls load a lock and reject a manifest that does not identify its locked source ([`src/pml/cli.py`:108-175, 200-276](../../src/pml/cli.py); [`src/pml/project_state.py`:891-915](../../src/pml/project_state.py)). This is a useful 0005 exact-source safeguard, not a command-form implementation. | All registered product-state forms require explicit manifest and product-root positionals ([`src/pml/cli.py`:51-72](../../src/pml/cli.py)); none resolves `.pml/pml.lock` from the current directory, and `lock`, `sync`, and `verify` are absent. No deprecation warnings or compatibility-form equality checks exist. Moreover, the current explicit `ingest-report` accepts an arbitrary explicit probe path and never proves it is the lock-resolved source tree ([`src/pml/cli.py`:200-223](../../src/pml/cli.py)), contrary to 0007:279-296 and 0008:254-263's locked-policy boundary. |

## Current documentation and implementation divergences

The following are observations, not a request to change approved or proposed
normative text.

- [`docs/verification.md`:39-42](../verification.md) presents `pml sync` and
  `pml verify` as available workflow commands, while the CLI has neither command
  (the exhaustive registration is [`src/pml/cli.py`:31-73](../../src/pml/cli.py)).
  This is a documentation/implementation divergence, not evidence that 0008 is
  implemented.
- The same protocol says touched-node ingestion clears old evidence on a changed
  definition or bindings digest ([`docs/verification.md`:19-26](../verification.md)).
  That accurately describes current [`src/pml/ingest.py`:227-240](../../src/pml/ingest.py),
  but conflicts with proposed 0008:79-94's preserve-stale-by-allowed-lane rule.
- The handoff correctly labels 0008 unimplemented ([`HANDOFF.md`:20-25](../../HANDOFF.md)),
  and its broader claim that 0010 authoring documentation is implemented
  ([`HANDOFF.md`:5-11](../../HANDOFF.md)) is not contradicted by audit 0049.
  Audit 0049 recorded a historical stale-reference finding at `8da0345` (PR #22)
  before [PR #23](https://github.com/ag2trust/pml/pull/23) updated the README,
  authoring guide, language reference, quickstart, and verification guidance for
  the approved transition grammar. The current
  [`docs/language-reference.md`:73-119, 161-174](../language-reference.md)
  defines `conditions`, `trigger`, `outcome`, `failures`, inline signals, the
  current use-case shape, and current obligation paths; removed transition words
  appear there only as explicit rejections or contrasts. No current
  language-reference correction is pending. Initialization still copies only the
  packaged `SKILL.md` and `agents/openai.yaml`
  ([`src/pml/initialize.py`:17-20, 71-74, 94-100](../../src/pml/initialize.py)).
  The installed skill directs authors to the separately maintained language
  reference, so this remains an indirect non-normative guidance dependency rather
  than an artifact copied by initialization.

## Owner decisions required before any delivery

The proposal must be explicitly approved or amended after resolving these semantic
choices. They are deliberately not resolved by this audit.

1. **Artifact authority and review metadata.** Reconcile 0007:15-60's required
   review metadata validation, current/stale approval semantics, and separate
   review digest with 0008's lock rules, which only list definition, bindings,
   probes, environments, and a Git-clean set containing optional `reviews.yaml`
   (0008:47-72). Decide whether review metadata is validated and lock-pinned,
   whether its absence is allowed at lock time, and what `check` versus an
   unspecified strict-review form does with pending/stale review records.
2. **Lock identity and provenance.** Define the exact source value for both a
   single definition file and modular source directory; whether a non-Git lock
   omits `revision` or stores a null/absent field; the canonical digest algorithm
   and schema fields for environments/reviews; and exact Git treatment of staged,
   unstaged, untracked, ignored, and submodule files. Confirm that lock-time
   regular-path/no-symlink rules cover source roots, fragments, bindings, probes,
   environments, and reviews, and decide whether hard links are relevant.
3. **Probe approval pinning.** 0007 makes a probe fingerprint stale evidence
   (0007:118-125), while 0008 validates probes at lock time but names no probe
   aggregate digest in the lock (0008:49-72). Decide whether changed probe content
   is only detected per evidence record, requires a new lock, or is itself pinned
   by a new lock field. This determines whether `verify` can execute a changed
   owner-source probe under an otherwise unchanged lock.
4. **Environment document and secrets.** Approve the closed environment grammar
   as owner-controlled non-normative metadata and define its digest bytes. Resolve
   URL base-path joining, HTTP header case collisions, scalar substitution typing,
   exact executable/file/fixture symlink checks, authored timeouts above 60
   seconds, and a redaction algorithm that cannot persist secrets in observations,
   reports, state, diagnostics, or exceptions. Confirm whether a missing
   environment is legal when no selected deterministic probe needs it.
5. **Complete reconciliation and migration.** Define every state scope, including
   whether architecture decisions without constraints get a file; the treatment of
   implementation records when their obligation or binding changes; migration of
   pre-0008 records that lack per-record fields; and the exact warnings for removed
   files/obligations/cleared lanes. Decide how a planned multi-file sync avoids
   overwriting concurrent report ingestion; current history explicitly preserves
   concurrently installed generated state ([`HANDOFF.md`:33-36](../../HANDOFF.md)),
   while 0008 specifies only per-file atomic replacement and crash convergence.
6. **Execution and report outcomes.** Confirm that all 0007 discovery limits
   (256 visited entries, 64 regular files, 1 MiB probe file, 64 steps/probes) remain
   in force in addition to 0008's execution rules; specify the fate of existing
   `stdout_has`; and approve the precise observation/limitation data emitted by
   the tool. Decide whether external reports are also verdict-checked or only
   tool-generated reports derive verdicts, and approve the tool-verifier union,
   dirty-product version definition, generated-ID collision handling, and
   single-report-environment rule.
7. **Compatibility scope.** Enumerate every temporarily accepted explicit form,
   its equality comparison against the lock, warning channel/text, removal release
   or condition, and whether `validate-probes` remains isolated-only. This needs
   separate explicit approval because 0010:383-393 prohibits compatibility aliases
   unless separately approved, even though these would be command aliases rather
   than language grammar.

## Cross-spec boundaries to resolve

| Boundary | Why an owner decision is needed |
| --- | --- |
| 0005 exact lock source vs 0008 normalized relative source | 0005:57-61 requires the exact supplied definition source and rejects an equivalent redirect. 0008:51-54 adds a relative serialized source and non-symlink traversal. These are compatible only once file-versus-directory source identity and canonical path normalization are defined. |
| 0007 review digest vs 0008 lock fields | 0007:42-60 requires review semantics and a separately recorded digest. 0008:49-72 never says that its lock validates or records that digest, although it includes `reviews.yaml` in Git cleanliness. This is an omission with an observable lock/change-detection consequence. |
| 0007 probe limits vs 0008 executor limits | 0007:127-137 has discovery, file, step, and execution limits. 0008:166-200 adds runtime semantics and repeats only some numeric limits. Its “more specific” clause (0008:7-11) does not identify which 0007 limits, if any, it replaces; the safe reading is cumulative, but that needs confirmation. |
| 0007 agent verifier vs 0008 verifier union | 0007:207-232 defines only the agent verifier for external reports. 0008:204-236 adds a tool verifier and generated-report rules. This is a schema and state-record change, not an implementation-only detail. |
| 0010 transition/compatibility rules vs 0008 command compatibility | 0010:378-393 requires state reconciliation without evidence reassignment and rejects compatibility aliases absent separate approval. 0008's lane-preservation details can implement the former, but its legacy command forms require the latter approval. |
| 0011 compiled-model boundary vs workflow consumers | 0011:23-44 and 0011:523-524 keep bindings, state, evidence, and freshness out of the read-only compiled definition. Lock/sync/verify may consume the validated resolver/model, but must not add workflow data to the model or change its deterministic format; 0011:697-703 would require separate format approval for that. |

## Ordered owner-review checklist

1. Confirm that 0008 remains a proposal until the decisions above are recorded;
   approve, reject, or amend it as one workflow decision without changing product
   language semantics.
2. Resolve review metadata, lock source/provenance, probe-pinning, and environment
   authority/digests before selecting any lock schema.
3. Resolve state-record migration, stale-versus-cleared lanes, removal warnings,
   architecture scope, and concurrent sync/ingestion behavior before changing the
   generated-state schema or validator.
4. Resolve the cumulative probe limits, substitution/fixture/network safety rules,
   report union/verdict/version/redaction rules, and tool exit contract before
   authorizing execution.
5. Enumerate and sunset every compatibility form explicitly, or decline aliases.
6. Confirm that the delivery remains outside the compiled-model format and that
   all generated records stay separate from approved definitions and bindings.

## Smallest post-approval delivery slices

These are recommendations only. Each slice follows the repository order: define
the approved semantics first, update schemas and semantic validators, add positive
and negative conformance examples, and only then add command behavior. No formatter
or compiler change is implied unless an approved schema change genuinely requires
one.

1. **Lock inputs and source identity.** If retained, deliver the review-metadata
   contract as its own prerequisite. Then add the environment and revised lock
   schemas, source/Git/regular-path/probe-discovery/environment validators, and
   conformance cases before a minimal atomic `pml lock` command. This command must
   create no state or evidence.
2. **Generated-state reconciliation.** Add per-record freshness fields and their
   validators, complete desired-state planning, stale/clear/removal diagnostics,
   migration fixtures, and concurrent-write conformance before `pml sync`. Keep
   it probe-free and definition/bindings read-only.
3. **Deterministic execution and tool reports.** Add the contextual probe and
   environment validation rules plus the report-verifier union, tool-report/state
   record contract, redaction, and positive/negative execution fixtures before
   `pml verify`. It should use the existing ingestion validation boundary rather
   than creating a second state-mutation path.
4. **Locked forms and approved compatibility only.** After the locked operations
   exist, add current-directory lock resolution and the explicitly approved
   legacy-form equivalence/deprecation tests, then move `check`, status, and
   ingest-report to the selected locked forms. Retain isolated validation commands
   only where the owner has approved their scope.

No command, schema, validator, conformance case, or normative document was changed
by this audit.
