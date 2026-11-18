"""Executable, callback-driven realization of Algorithm 3 (C1).

The executor preserves the paper's four phase semantics. Provider-specific
prompting/decoding is injected through callbacks; this module owns ordering,
family separation, call accounting, retry limits and failure propagation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Mapping, Sequence, TypeVar

from sociodec.phase_composition import (
    CandidateState, PhaseContract, PhaseKind, PhaseValue,
    validate_phase_preconditions,
)

Candidate = TypeVar("Candidate")
Merged = TypeVar("Merged")
Decomposition = TypeVar("Decomposition")


@dataclass(frozen=True, slots=True)
class AnonymousObjection:
    """One objection without author, voter, or candidate attribution."""
    code: str
    statement: str
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.statement.strip():
            raise ValueError("Objection code and statement must be non-empty")


@dataclass(frozen=True, slots=True)
class AnonymousObjections:
    """Immutable author-anonymous objection collection."""
    items: tuple[AnonymousObjection, ...]

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("Anonymous objections must not be empty")
        if len(set(self.items)) != len(self.items):
            raise ValueError("Anonymous objections must be unique")

    def validate_no_author_ids(self, author_ids: Sequence[str]) -> None:
        text = " ".join(
            part for item in self.items
            for part in (item.code, item.statement, item.evidence)
        ).casefold()
        if any(author.casefold() in text for author in author_ids):
            raise ValueError("Objections contain author attribution")


@dataclass(frozen=True, slots=True)
class C1Call:
    phase: str
    actor: str
    model_id: str
    model_family: str
    call_number: int


@dataclass(frozen=True, slots=True)
class C1Result(Generic[Decomposition]):
    decomposition: Decomposition | None
    candidates: Mapping[str, Candidate]
    objections: AnonymousObjections | None
    verdict: str
    judge_objections: AnonymousObjections | None
    failures: tuple[str, ...]
    calls: tuple[C1Call, ...]
    revisions: int
    judge_revisions: int
    early_agreement: bool

    @property
    def calls_made(self) -> int:
        return len(self.calls)


@dataclass(frozen=True, slots=True)
class C1Callbacks(Generic[Candidate, Merged, Decomposition]):
    draft: Callable[[str], Candidate]
    compare: Callable[[Mapping[str, Candidate]], AnonymousObjections]
    revise: Callable[[str, Candidate, AnonymousObjections], Candidate]
    merge: Callable[[Mapping[str, Candidate]], Merged]
    judge: Callable[[Merged | Decomposition, Mapping[str, Candidate]], tuple[str, AnonymousObjections | None]]
    judge_revise: Callable[[Merged | Decomposition, AnonymousObjections], Decomposition]
    check_and_repair: Callable[[Merged | Decomposition], tuple[Decomposition, Sequence[str]]]
    distance: Callable[[Candidate, Candidate], float]


class Algorithm3C1Executor(Generic[Candidate, Merged, Decomposition]):
    """Run Algorithm 3 with explicit model-family and bounded-call controls."""

    def __init__(
        self,
        *,
        decomposer_models: Mapping[str, tuple[str, str]],
        comparator_model: tuple[str, str],
        synthesizer_model: tuple[str, str],
        judge_model: tuple[str, str],
        callbacks: C1Callbacks[Candidate, Merged, Decomposition],
        epsilon: float,
        T: int,
    ) -> None:
        if len(decomposer_models) < 1:
            raise ValueError("C1 requires at least one decomposer")
        if T < 1:
            raise ValueError("T must be >= 1")
        if epsilon < 0:
            raise ValueError("epsilon must be >= 0")
        self.decomposers = dict(decomposer_models)
        self.comparator = comparator_model
        self.synthesizer = synthesizer_model
        self.judge = judge_model
        self.callbacks = callbacks
        self.epsilon = epsilon
        self.T = T
        author_families = {family for _, family in self.decomposers.values()}
        if self.judge[1] in author_families or self.judge[1] == self.synthesizer[1]:
            raise ValueError("Judge must belong to a model family distinct from authors and synthesizer")

    @property
    def worst_case_calls(self) -> int:
        n = len(self.decomposers)
        return n * (self.T + 1) + self.T + 4

    def run(self, *, available_calls: int | None = None) -> C1Result[Decomposition]:
        n = len(self.decomposers)
        if n < 2 and self.T > 0:
            # The algorithm's comparison phase requires at least two candidates.
            raise ValueError("C1 comparison requires at least two decomposers")
        if available_calls is not None and available_calls < n + 2:
            raise RuntimeError("Call budget cannot cover minimum C1 path")

        calls: list[C1Call] = []
        def record(phase: str, actor: str, model: tuple[str, str]) -> None:
            calls.append(C1Call(phase, actor, model[0], model[1], len(calls) + 1))
            if available_calls is not None and len(calls) > available_calls:
                raise RuntimeError("C1 exceeded available call budget")

        # gen: independent drafts; no peer candidate is passed to a drafter.
        candidates: dict[str, Candidate] = {}
        for agent_id, model in self.decomposers.items():
            record("gen", agent_id, model)
            candidates[agent_id] = self.callbacks.draft(agent_id)

        state = CandidateState(size=n, independent=True)
        last_objections: AnonymousObjections | None = None
        revisions = 0
        early_agreement = False

        # (exa rev)*; stop test is evaluated before each comparison.
        for round_index in range(1, self.T + 1):
            values = list(candidates.values())
            max_distance = max(
                (self.callbacks.distance(values[i], values[j])
                 for i in range(len(values)) for j in range(i + 1, len(values))),
                default=0.0,
            )
            if max_distance <= self.epsilon:
                early_agreement = True
                break

            exa = PhaseContract(
                PhaseKind.EXAMINATION, f"comparison-{round_index}",
                PhaseValue.CANDIDATE_SET, PhaseValue.OBJECTIONS,
                requires_min_candidates=2,
            )
            validate_phase_preconditions(exa, state)
            record("exa", "comparator", self.comparator)
            # Comparator sees candidate set; authors do not see each other's drafts.
            last_objections = self.callbacks.compare(dict(candidates))
            if not isinstance(last_objections, AnonymousObjections):
                raise TypeError("Comparator must return AnonymousObjections")
            last_objections.validate_no_author_ids(tuple(self.decomposers))

            rev = PhaseContract(
                PhaseKind.REVISION, f"anonymous-revision-{round_index}",
                PhaseValue.OBJECTIONS, PhaseValue.CANDIDATE_SET,
                requires_nonempty_objections=True,
                preserves_independence=True,
            )
            validate_phase_preconditions(
                rev, state,
                objections_nonempty=bool(last_objections.items),
            )
            revised: dict[str, Candidate] = {}
            for agent_id, old_candidate in candidates.items():
                record("rev", agent_id, self.decomposers[agent_id])
                # Only the acting author's own candidate and anonymized objections
                # are supplied; no other candidate is included in this callback.
                revised[agent_id] = self.callbacks.revise(
                    agent_id, old_candidate, last_objections,
                )
            candidates = revised
            revisions += 1

        # Merge and adjudicate are distinct calls; the judge sees merged candidate
        # and candidate set, but is independently sourced by model family.
        record("merge", "synthesizer", self.synthesizer)
        merged = self.callbacks.merge(dict(candidates))
        record("dec", "judge", self.judge)
        verdict, judge_objections = self.callbacks.judge(merged, dict(candidates))
        if verdict not in {"accept", "reject"}:
            raise ValueError("Judge verdict must be exactly 'accept' or 'reject'")

        judge_revisions = 0
        judged_candidate: Merged | Decomposition = merged
        if verdict == "reject":
            if not isinstance(judge_objections, AnonymousObjections):
                raise ValueError("A rejecting judge must provide AnonymousObjections")
            judge_objections.validate_no_author_ids(tuple(self.decomposers))
            # Algorithm 3 permits exactly one aggregator revision and one last verdict.
            record("judge-revision", "synthesizer", self.synthesizer)
            judged_candidate = self.callbacks.judge_revise(merged, judge_objections)
            judge_revisions = 1
            record("dec-second", "judge", self.judge)
            verdict, second_objections = self.callbacks.judge(
                judged_candidate, dict(candidates),
            )
            if verdict not in {"accept", "reject"}:
                raise ValueError("Second judge verdict must be exactly 'accept' or 'reject'")
            if second_objections is not None:
                if not isinstance(second_objections, AnonymousObjections):
                    raise TypeError("Judge must return AnonymousObjections")
                second_objections.validate_no_author_ids(tuple(self.decomposers))
            judge_objections = second_objections

        # Algorithm 1 check/repair is delegated as one typed operation. Its
        # callback must implement V1/V2/V5, deterministic cycle repair and at
        # most one model repair for other failures, then re-check.
        decomposition, remaining_failures = self.callbacks.check_and_repair(judged_candidate)
        failures = list(remaining_failures)
        if verdict == "reject":
            failures.append("rejected by the judge")
        return C1Result(
            decomposition=decomposition,
            candidates=dict(candidates),
            objections=last_objections,
            verdict=verdict,
            judge_objections=judge_objections,
            failures=tuple(dict.fromkeys(failures)),
            calls=tuple(calls),
            revisions=revisions,
            judge_revisions=judge_revisions,
            early_agreement=early_agreement,
        )
