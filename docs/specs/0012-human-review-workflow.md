# PML human review workflow

Status: Owner approved
Approved direction: 2026-09-15

## Purpose and boundary

This specification implements the review-metadata direction approved in
[0007](0007-project-workflow.md). It adds no PML definition keywords. Approved
definitions remain authoritative, while review decisions remain in the separate
owner-controlled `reviews.yaml` artifact.

The first delivery includes review-metadata validation, digest-bound decisions,
an interactive human review queue, rejection reasons, and manual editing. Agent
context export and agent-harness execution are deferred to a later owner decision.

## Reviewable targets

The complete supported compiled model supplies the review inventory. Exactly these
records are reviewable:

- every compiled feature;
- every compiled behavior; and
- every compiled product or architecture obligation.

Project and domain purposes, actor and concept meanings, vocabulary entries, signals,
and other descriptive records are not independent review targets. Normative rules,
use-case goals, behavior conditions, triggers, completion exclusivity, outcomes,
failures, and architecture constraints are covered by their stable obligation IDs.

The queue is sorted lexically by canonical target ID. A target kind is `feature`,
`behavior`, or `obligation`; the presentation may additionally show an obligation's
compiled kind, such as `rule` or `outcome`.

## Review target digests

A review target digest is `sha256:` followed by the lowercase SHA-256 digest of the
target representation's canonical UTF-8 JSON bytes. Canonical JSON uses the same
string, key-order, array-order, and whitespace rules as the approved definition
digest in [0011](0011-compiled-semantic-model.md).

The target representation is:

```text
review-target = {id: canonical-target-id,
                 kind: feature | behavior | obligation,
                 content: target-content}
```

Feature content contains the compiled `purpose`, `actors`, optional `experience`,
`related_to`, `architecture`, `rule_obligations`, `use_cases`, and `behaviors`
fields. Behavior content contains the compiled optional `conditions`, `trigger`,
`completion_obligation`, `outcome`, `failures`, `rule_obligations`, and `related_to`
fields plus an optional `produced_signals` list. Each produced-signal projection
contains its compiled `id`, optional `subject`, `meaning`, and producer `completion`,
so changing inline signal semantics makes the producing behavior review stale.
Obligation content contains the compiled `node`, obligation `kind`, and `definition`
fields.

These projections approve semantic content rather than YAML layout. Adding or
removing a child ID changes its feature or behavior digest, while changing the
child's normative content changes the child's own behavior or obligation digest.

## Review metadata grammar

For a modular source, `reviews.yaml` is at the source root. For a single-file source,
it is adjacent to that file. The file is optional; absence means every target is
pending.

```text
digest = "sha256:" followed by 64 lowercase hexadecimal digits
text   = non-empty Unicode scalar string, at most 4,096 code points

reviews-document = {
  pml_reviews: "0.1",
  reviews: map[canonical-target-id, review-record]
}

review-record = {
  origin: human | agent,
  status: pending | approved,
  digest: digest
} | {
  origin: human | agent,
  status: rejected,
  digest: digest,
  reason: text
}
```

The document and every record are closed maps. Review metadata does not impose a
record-count or target-ID-length limit beyond the limits of the approved PML
definition. Every target ID must resolve to the current validated review inventory.
Unknown targets are invalid. A syntactically valid non-current digest is not invalid;
it makes the record stale.

The canonical review-document digest uses the same canonical UTF-8 JSON algorithm.
Lock integration remains governed by 0007 and is outside this command slice.

## Derived review state

Review state is derived for the current target representation:

- no record means `pending`;
- a record whose digest differs from the current target digest means `stale`;
- a current record retains its authored `pending`, `approved`, or `rejected` status.

Both `pending` and `stale` require a new human decision. A current `rejected` target
is reviewed but unapproved and remains in future unresolved queues. Only a current
`approved` record is omitted from the queue.

Ordinary `pml validate` validates an adjacent `reviews.yaml` when present. Pending,
stale, and rejected targets do not make ordinary validation fail. Compilation,
explanation, and graph projection remain definition-only consumers and never read
review metadata.

## Interactive command

```text
pml review <manifest> [--origin human|agent]
```

The command completely loads, validates, and compiles the definition, then loads and
validates review metadata before presenting any target. Invalid input prints ordered
diagnostics, exits nonzero, prompts for nothing, and writes nothing.

For each unresolved target, the command displays its position, derived state, kind,
canonical ID, semantic content, and contributing source file or files. It accepts
exactly these actions:

- `a` or `approve`: atomically record `approved` for the current digest;
- `r` or `reject`: require a non-empty reason and atomically record `rejected` for
  the current digest;
- `s` or `skip`: make no metadata change and continue for this invocation;
- `e` or `edit`: invoke the configured editor for the contributing authored source;
  and
- `q` or `quit`: end normally while preserving already recorded decisions.

EOF or an interrupt at an interactive prompt has the same persistence boundary as
`quit`. Each approve or reject decision is installed with an atomic replacement, so
a later quit or interruption does not discard earlier decisions.

`origin` describes who authored the reviewed content, not who ran the review. A
current record's origin is preserved. A stale or absent record uses `--origin` when
provided; otherwise the command asks the human to select `human` or `agent` before
recording approval or rejection. PML trusts this repository-controlled declaration;
it does not attempt to prove human identity.

Normal completion and explicit quit exit zero even when skipped, rejected, or otherwise
unapproved targets remain. Input, validation, editor, or write failures exit nonzero.
The final summary distinguishes approvals, rejections, skips, manual edits, and the
number of targets still unresolved.

## Manual editing

The editor command is taken from `VISUAL`, then `EDITOR`. It is parsed as a POSIX
argument vector and executed directly without a shell. When neither variable supplies
a command, edit reports an error and returns to the current review prompt.

For a single-file definition, the command opens that file. For a modular definition,
it opens the validated fragments that contribute to the target's authored path. If
the exact contribution cannot be isolated, it opens the source root. PML never writes
the definition on the editor's behalf.

After a successful editor exit, PML reloads and validates the complete definition.
Invalid edits remain visible in the worktree, but review metadata is unchanged and the
command exits nonzero. For a valid edit, PML rebuilds the complete inventory. Every
new or changed target is recorded as `origin: human`, `status: pending`, at its new
digest. Review records for targets removed by that edit are removed with an explicit
notice. The metadata replacement is atomic, and the unresolved queue restarts against
the new snapshot. Git history remains the recovery mechanism for removed review
records.

## Resource and filesystem safety

`reviews.yaml` must be a regular non-symbolic file no larger than 1 MiB. It uses the
same restricted YAML loading rules as other PML artifacts. Review writes never follow
a symbolic-link destination and replace only the exact adjacent `reviews.yaml`. A
write whose complete UTF-8 serialization would exceed 1 MiB fails before replacement,
leaving the prior file unchanged.

Review writers serialize the short read/merge/replace operation for each source.
Each write compares the session's last saved snapshot with the current file and
three-way merges decisions for different target IDs. Concurrent incompatible changes
to the same target fail with a conflict diagnostic and leave the current file
unchanged. A successful merge becomes the session's new saved snapshot.

## Required conformance coverage

Positive cases cover closed valid metadata, deterministic target and document digests,
current approvals, stale approvals remaining valid, approve/reject/skip/quit behavior,
origin preservation and prompting, manual edits becoming human-authored pending
content, queue restart, and atomic incremental persistence.

Negative cases cover malformed and oversized YAML, duplicate or unknown targets,
unknown keys and enum values, malformed digests, missing or misplaced rejection
reasons, invalid definitions before prompting, missing or failing editors, invalid
post-edit definitions, symbolic review files, and write failure without partial
replacement. Concurrency coverage includes preservation of independent decisions and
rejection of incompatible decisions for the same target. Output-size coverage proves
that an oversized serialization leaves the prior file unchanged.
