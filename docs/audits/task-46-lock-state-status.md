# Task 46: lock, state, and status compatibility audit

Audit target: the post-PR #21 validator and PR #22 transition-obligation
resolver (`d2ccc754d2c9fc2983a5d2eb245736d7def67290`). The findings inspect that
post-#22 implementation without changing it.

## Result

No remaining runtime dependency on removed behavior grammar or old obligation
paths was found in lock resolution, product-state reconciliation/validation, or
`pml status` after PR #22. Each scoped consumer obtains its node and obligation
set from `iter_nodes` and/or `enumerate_obligations`; PR #22 changes that single
resolver from legacy `.output`/`reactions` obligations to transition obligations.

The pre-#22 resolver in `src/pml/obligations.py:9,80-106` was a real dependency
on removed `output` and `reactions` grammar. It is not a remaining defect in the
audit target: PR #22 removes `reactions` from `OBLIGATION_SECTIONS` and resolves
`conditions`, `trigger`, `completion`, `outcome`, and `failures` instead
(`src/pml/obligations.py:9,80-168` at `d2ccc75`).

## Scoped evidence

| Area | Evidence | Finding |
| --- | --- | --- |
| Lock and bindings | `load_locked_bindings` validates the lock digest, then calls `load_bindings` (`src/pml/project_state.py:862-943`). `_bindings_semantic_diagnostics` calculates expected verification IDs with `enumerate_obligations` (`:704-756`), rather than matching `.output`, `.reactions`, or `.components` strings. | Covered generic obligation consumer; no defect. New transition IDs and rejection of a legacy component path are asserted by `tests/test_state.py:96-195` at `d2ccc75`. |
| State reconciliation/validation | Implemented reconciliation during report ingestion gets the complete product obligation map through `enumerate_obligations` (`src/pml/ingest.py:82-86`) and reconstructs each touched state's obligation map from that enumerator (`:195-247`). Read-only validation also builds both the allowed global IDs and each node's required IDs with `enumerate_obligations` (`src/pml/project_state.py:1023-1141`, especially `:1041-1044` and `:1126-1139`). Thus old state entries are dropped on an applicable ingestion reconciliation or diagnosed as undefined by validation; newly resolved transition entries are created or reported missing. | Covered generic obligation consumer; no defect. The transition ID set is explicitly asserted in `tests/test_state.py:96-152` at `d2ccc75`. |
| Status command | CLI `status` loads the lock first and delegates to `product_status` (`src/pml/cli.py:81-112`). `product_status` enumerates per-node obligations through `enumerate_obligations` and reports their returned IDs (`src/pml/status.py:118-192`, especially `:168-190`), without grammar-specific path logic. | Covered generic obligation consumer; no defect. The same expected transition IDs are the status input set tested in `tests/test_state.py:96-152` at `d2ccc75`. |

`tests/test_probes.py:89-130` at `d2ccc75` is additional boundary evidence: it
accepts `.completion` and `.failures.processing_failure` targets and rejects a
`.components.` target. This supports the resolver contract used by all three
scoped consumers, but is not itself a lock/state/status implementation test.

## Documentation gaps (not runtime defects)

These documents still describe grammar removed by the approved transition model;
they do not affect lock resolution, state validation, or status execution.

| File | Evidence | Gap |
| --- | --- | --- |
| `README.md:6-8,24-27` | The overview still lists `outputs`, `signals`, and `reactions` as PML constructs, and the current-status section calls 0009 the approved behavior/output design rather than the superseding 0010 transition model. | Both the overview and current-status documentation are stale. The lock/status invocation at `README.md:63-90` is otherwise grammar-neutral. |
| `docs/language-reference.md:22-31,67-133,168-174` | Documents the removed top-level `signals` registry; feature `reactions` and `emits`; behavior `context`, `output`, `reactions`, and `architecture`; and legacy `.output` / `.output.<alternative-id>` obligation IDs. | Stale language and obligation reference. Its lock-source boundary description at `:181-189` is otherwise generic. |
| `docs/quickstart.md:45-47` | Says behaviors use signals and reactions and have one `output`. | Stale authoring guidance. |
| `docs/authoring-guide.md:19-37` | Describes `output`, `context`, `reactions`, global `signals`, and `emits`. | Stale authoring guidance. |
| `docs/verification.md:3-5` | States that rules, reactions, and use cases resolve to obligations. | Stale obligation description; its lock/status boundary text at `:7-20` is otherwise generic. |

The approved historical specifications intentionally retain prior grammar for
design and migration record; they are not counted as documentation gaps in this
audit. Likewise, the separate architecture obligation consumer is outside the
requested product lock/state/status scope and is already independently generic.

The command-semantics specification names a separate `pml sync` command, but this
checkout does not register that command in `src/pml/cli.py:27-66`. Its absence is
not a dependency on removed grammar or old obligation paths, so it is outside this
compatibility audit rather than an additional finding.

No language semantics or implementation was changed by this audit.
