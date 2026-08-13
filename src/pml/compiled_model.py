"""Shared in-memory types for the closed PML compiled-model v1 contract.

These types describe derived data only.  They intentionally do not compile,
validate, or reinterpret authored PML definitions.
"""

from typing import Literal, NotRequired, TypeAlias, TypedDict


Path: TypeAlias = str
ObligationId: TypeAlias = str


class CompiledProject(TypedDict):
    id: str
    name: str
    purpose: str
    rule_obligations: list[ObligationId]
    domains: list[Path]


class CompiledVocabularyTerm(TypedDict):
    term: str
    meaning: str
    forbidden_synonyms: list[str]


class CompiledActor(TypedDict):
    id: str
    meaning: str


class CompiledConcept(TypedDict):
    id: str
    meaning: str
    states: list[str]


class CompiledArchitectureDecision(TypedDict):
    id: str
    path: Path
    category: Literal["database", "framework", "gateway", "provider", "payment_processor", "runtime"]
    selection: str
    rationale: str
    constraint_obligations: list[ObligationId]
    referenced_by: list[Path]


class CompiledDomain(TypedDict):
    id: str
    path: Path
    purpose: str
    rule_obligations: list[ObligationId]
    features: list[Path]


class CompiledSurfaceState(TypedDict):
    id: str
    statements: list[str]


class CompiledSurface(TypedDict):
    id: str
    contains: list[str]
    states: list[CompiledSurfaceState]
    accessibility: list[str]
    responsive_behavior: list[str]


class CompiledExperience(TypedDict):
    surfaces: list[CompiledSurface]


class CompiledFeature(TypedDict):
    id: str
    path: Path
    domain: Path
    purpose: str
    actors: list[str]
    rule_obligations: list[ObligationId]
    use_cases: list[Path]
    behaviors: list[Path]
    experience: NotRequired[CompiledExperience]
    related_to: list[Path]
    architecture: list[Path]


class CompiledConditions(TypedDict):
    statements: list[str]
    obligation: ObligationId


class DirectStatementTriggerCase(TypedDict):
    obligation: ObligationId
    statement: str


class DirectSignalTriggerCase(TypedDict):
    obligation: ObligationId
    signal: str


CompiledDirectTriggerCase: TypeAlias = DirectStatementTriggerCase | DirectSignalTriggerCase


class DirectTrigger(TypedDict):
    kind: Literal["direct"]
    case: CompiledDirectTriggerCase


class StatementTriggerAlternative(TypedDict):
    id: str
    obligation: ObligationId
    statement: str


class SignalTriggerAlternative(TypedDict):
    id: str
    obligation: ObligationId
    signal: str


CompiledTriggerAlternative: TypeAlias = StatementTriggerAlternative | SignalTriggerAlternative


class OneOfTrigger(TypedDict):
    kind: Literal["one_of"]
    cases: list[CompiledTriggerAlternative]


CompiledTrigger: TypeAlias = DirectTrigger | OneOfTrigger


class CompiledOutcomeCase(TypedDict):
    obligation: ObligationId
    statement: str
    signal: NotRequired[str]


class CompiledOutcomeAlternative(TypedDict):
    id: str
    obligation: ObligationId
    statement: str
    signal: NotRequired[str]


class DirectOutcome(TypedDict):
    kind: Literal["direct"]
    case: CompiledOutcomeCase


class OneOfOutcome(TypedDict):
    kind: Literal["one_of"]
    exclusivity_obligation: ObligationId
    cases: list[CompiledOutcomeAlternative]


CompiledOutcome: TypeAlias = DirectOutcome | OneOfOutcome


class CompiledFailure(TypedDict):
    id: str
    obligation: ObligationId
    statement: str
    signal: NotRequired[str]


class CompiledBehavior(TypedDict):
    id: str
    path: Path
    feature: Path
    conditions: NotRequired[CompiledConditions]
    trigger: CompiledTrigger
    completion_obligation: ObligationId
    outcome: CompiledOutcome
    failures: list[CompiledFailure]
    rule_obligations: list[ObligationId]
    related_to: list[Path]
    use_cases: list[Path]


class CompiledUseCase(TypedDict):
    id: str
    path: Path
    feature: Path
    actor: str
    goal: str
    behaviors: list[Path]
    obligation: ObligationId


class SignalProducer(TypedDict):
    behavior: Path
    completion: ObligationId


class SignalConsumer(TypedDict):
    behavior: Path
    trigger: ObligationId


class CompiledSignal(TypedDict):
    id: str
    meaning: str
    subject: NotRequired[str]
    producer: SignalProducer
    consumers: list[SignalConsumer]


class CompiledRelationship(TypedDict):
    kind: Literal["related_to"]
    endpoints: tuple[Path, Path]
    declared_by: list[Path]


class CompiledUseCaseMembership(TypedDict):
    use_case: Path
    behavior: Path


class ConditionsDefinition(TypedDict):
    statements: list[str]


class StatementDefinition(TypedDict):
    statement: str


class SignalDefinition(StatementDefinition):
    signal: NotRequired[str]


class CompletionDefinition(TypedDict):
    outcomes: list[ObligationId]
    failures: list[ObligationId]


class OutcomeExclusivityDefinition(TypedDict):
    alternatives: list[ObligationId]


class UseCaseDefinition(TypedDict):
    actor: str
    goal: str
    behaviors: list[Path]


class _Obligation(TypedDict):
    id: ObligationId
    node: Path


class ConditionsObligation(_Obligation):
    kind: Literal["conditions"]
    definition: ConditionsDefinition


class TriggerObligation(_Obligation):
    kind: Literal["trigger"]
    definition: StatementDefinition | SignalDefinition


class CompletionObligation(_Obligation):
    kind: Literal["completion"]
    definition: CompletionDefinition


class OutcomeExclusivityObligation(_Obligation):
    kind: Literal["outcome_exclusivity"]
    definition: OutcomeExclusivityDefinition


class OutcomeObligation(_Obligation):
    kind: Literal["outcome"]
    definition: SignalDefinition


class FailureObligation(_Obligation):
    kind: Literal["failure"]
    definition: SignalDefinition


class RuleObligation(_Obligation):
    kind: Literal["rule"]
    definition: StatementDefinition


class UseCaseObligation(_Obligation):
    kind: Literal["use_case"]
    definition: UseCaseDefinition


class ArchitectureConstraintObligation(_Obligation):
    kind: Literal["architecture_constraint"]
    definition: StatementDefinition


CompiledObligation: TypeAlias = (
    ConditionsObligation
    | TriggerObligation
    | CompletionObligation
    | OutcomeExclusivityObligation
    | OutcomeObligation
    | FailureObligation
    | RuleObligation
    | UseCaseObligation
    | ArchitectureConstraintObligation
)


class CompiledModel(TypedDict):
    format: Literal["pml.compiled"]
    format_version: Literal[1]
    language_version: Literal["0.1-draft"]
    definition_digest: str
    project: CompiledProject
    vocabulary: list[CompiledVocabularyTerm]
    actors: list[CompiledActor]
    concepts: list[CompiledConcept]
    architecture: list[CompiledArchitectureDecision]
    domains: list[CompiledDomain]
    features: list[CompiledFeature]
    behaviors: list[CompiledBehavior]
    use_cases: list[CompiledUseCase]
    signals: list[CompiledSignal]
    relationships: list[CompiledRelationship]
    use_case_memberships: list[CompiledUseCaseMembership]
    obligations: list[CompiledObligation]
