# PML 0.1 Deterministic Verification Design

Status: Approved direction, schema and runner pending  
Approved direction: 2026-07-21

## 1. Purpose

A contract without an enforcement mechanism is documentation. Agent-produced error
("slop") appears wherever an agent makes a judgment that nothing checks
deterministically: while implementing, while writing tests, and while verifying.
Re-running agents and verifying verifiers raises cost linearly while raising
confidence sublinearly.

This design takes a different route: **shrink the surface where judgment is needed,
make everything else deterministic, and make the judgment that remains cheap to
audit.** Three principles:

1. **Deterministic ratchet.** Agent judgment is expensive and unreliable every time;
   a deterministic check is expensive once and free forever. The verifier's primary
   job is not to be the check but to author the check. Over a product's life,
   obligations migrate from agent-judged to probe-covered, so the probability of
   undetected slop decreases monotonically instead of resetting each cycle.
2. **Verify claims, not agents.** Every verdict must be falsifiable and replayable:
   claim, exact reproduction, expected observation. Auditing then becomes cheap
   sampling — replaying a claim — rather than full re-verification.
3. **Route rigor by severity.** Not every obligation deserves the same cost.
   Severity, already declared on every rule, decides which evidence kinds are
   acceptable.

## 2. Evidence kinds

Every check in a verification report declares how it was evaluated:

| Kind | Meaning | Trust basis |
|---|---|---|
| `deterministic_probe` | An approved probe executed by the probe runner produced the result. | Replayable; artifact hash recorded. |
| `human_attestation` | A named person observed the obligation directly. | Accountability. |
| `agent_judgment` | An agent evaluated the obligation without a probe. | Weakest; must include reproduction steps. |

Evidence routing rules:

1. A rule with `severity: critical` reaches `passing` only through
   `deterministic_probe` or `human_attestation` evidence.
2. `agent_judgment` evidence alone caps a node's verification state at `pending`
   for critical rules; for lower severities it may produce `passing`.
3. `agent_judgment` evidence without reproduction steps is invalid.
4. Prose that asserts success without an observation ("confirmed it works") is
   invalid evidence of any kind.

## 3. Probes

A probe is an executable acceptance check owned by the contract, not by the
codebase. It differs from an integration test in governance, not mechanics:

| | Integration test | Probe |
|---|---|---|
| Owned by | Codebase; agents edit freely. | Contract; changes require Owner approval. |
| Binds to | Code: endpoints, models, fixtures, mocks. | A semantic ID and its obligation; black-box, actor-facing surfaces only. |
| Breaks when | Refactors and renames. | The product behavior actually breaks. |
| Result feeds | CI pass/fail. | An evidence record and the conformance state of one semantic ID. |

Consequences:

- An agent cannot make a failing check pass by weakening the check.
- Probes survive a full rebuild of the product; they are the only checks that live
  at the same altitude as the contract.
- Integration tests remain useful and remain the codebase's own concern. Probes do
  not replace them and are expected to be far fewer.

## 4. Probe definitions

A probe has two parts. Only one is authored.

- **Probe definition** — declarative YAML, one file per probe, Owner-approved. It
  is the probe: a closed step vocabulary that a generic runner executes verbatim.
- **Probe runner** — generic infrastructure, written and reviewed once, versioned.
  No per-probe code exists.

```yaml
probe: assistant_config_persistence
verifies: domains.assistants.features.creation.rules.persistent_configuration
env: staging
steps:
  - http: POST /assistants
    as: member
    body_from: fixtures/assistant.json
    expect: {status: 201, body_has: [id]}
    capture: {assistant_id: body.id}
  - session: reset
  - http: GET /assistants/{assistant_id}
    as: member
    within: 5s
    expect: {status: 200, body_matches_fixture: assistant.json#configuration}
```

### Closed step vocabulary

The 0.1 vocabulary covers HTTP and CLI interactions: `http`, `cli`, `session`,
`capture`, `expect`, `within`. New step verbs require a runner version change,
exactly as new relationship types require a language version change. A free-form
`script` step type is forbidden permanently: the day arbitrary code is a step, the
reading-surface guarantee dies.

### Code may observe; only the definition may judge

Some obligations need custom observation (an email arriving, a log line appearing).
An observation plugin may fetch raw observations and return them as data. Every
assertion stays in the probe definition. Plugins are few, generic, reviewed once,
and reused across probes. The worst a defective plugin can do is misreport one
observation; it can never weaken an assertion.

## 5. Environment profiles

Probe definitions are environment-independent. A per-project profile binds actors
and locations to a concrete environment:

```yaml
# probes/env/staging.yaml
base_url: https://staging.example.com
actors:
  member:
    auth: bearer
    secret_ref: env:PROBE_MEMBER_TOKEN
```

Secrets are referenced, never inlined. `as: member` in a probe resolves through the
active profile; the meaning of the actor stays in the manifest, the credentials stay
in the environment.

## 6. Compilation to existing runners

Execution engines are a solved problem. The probe runner is a thin deterministic
compiler onto existing engines, not an automation engine:

```text
probe definition (approved)
  -> deterministic compile (versioned compiler)
  -> backend artifact (recorded hash)
  -> existing engine executes (Hurl first; others later)
  -> engine report -> evidence record -> conformance state
```

- The first backend is Hurl (plain-text HTTP files, built-in asserts, captures, and
  retries, deterministic exit codes, single binary).
- Compiled artifacts are derived reproducibly from approved definitions. Nobody
  reads them, and any hand edit breaks the recorded hash.
- The step vocabulary is designed as the intersection of what candidate backends
  support, not the union, so a backend swap is a compiler swap, not a probe rewrite.
- What never translates to a backend: `verifies` (semantic binding), severity
  routing, staleness, and approval. Those belong to PML.

## 7. Governance

Enforcement is deliberately boring and deterministic:

1. `probes/` requires Owner approval to change (repository ownership rules such as
   CODEOWNERS are sufficient). Agents may propose probe changes; they cannot merge
   them.
2. Continuous integration runs the probes relevant to a change and writes evidence
   records. A change touching semantic IDs whose critical rules lack fresh
   deterministic evidence does not merge.
3. Staleness resolution is cheap by construction: re-run the probes. Agent judgment
   re-enters only when a probe itself is invalid or missing.

## 8. Flakiness

Flakiness, not expressiveness, is the main threat to this design. One intermittent
probe teaches everyone to ignore red, and the entire conformance signal dies.

- Timing-sensitive assertions must declare `within` bounds; the runner maps them to
  the backend's retry mechanism.
- An intermittently failing probe is a failing probe. It must be fixed, or demoted
  to a non-critical obligation with Owner approval. Ignoring it is not an option
  the system offers.
- Fewer reliable probes beat many unreliable ones.

## 9. The verifier's role

The verification protocol (`docs/verification.md`) changes emphasis. On first
verification of an obligation the verifier explores the product and, wherever the
closed vocabulary can express the obligation, emits a probe definition proposal as
its primary output. Judgment remains only for the tail that probes cannot express,
and it is recorded as `agent_judgment` with reproduction steps, subject to the
routing rules in section 2.

## 10. Non-goals

- Building a test execution engine or replacing integration tests.
- Browser and mobile backends in the first iteration (the vocabulary must not
  preclude them).
- Proving arbitrary natural-language statements mechanically; the tail of
  agent-judged obligations never reaches zero.
- Preventing slop in probe authoring itself; that is what one-time Owner review of
  small declarative definitions is for.

## 11. Implementation sequence

1. Probe definition schema (`additionalProperties: false`) and validator support.
2. Environment profile schema and secret reference resolution.
3. Compiler to Hurl with artifact hashing.
4. Evidence records and severity-routed conformance calculation.
5. Continuous-integration gate consuming verification reports.
6. Pilot against one complete feature dossier from a real host product.
