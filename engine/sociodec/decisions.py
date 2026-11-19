"""Decision operators from Table 4 and Section 6.2 of the paper.

The operators are deliberately distinct: whole-candidate selection, rank
aggregation, subproblem ballots, structural union, synthesis, compromise and
consensus medoid. LLM-mediated synthesis/compromise/authority are supplied
as explicit adjudication results; this module does not invent their content.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from sociodec.extraction import _normalise
from sociodec.equivalence import DEFAULT_MATCHER, SubproblemMatcher, equivalence_classes
from sociodec.models.decomposition import (
    Decomposition, DeliverableComposition, Dependency, Subproblem,
)


def subproblem_signature(item: Subproblem) -> tuple:
    """Equivalence key for a subproblem; excludes its local identifier."""
    return (
        _normalise(item.question),
        tuple(sorted(_normalise(value) for value in item.inputs)),
        _normalise(item.output),
        tuple(sorted(
            (constraint.kind.value, _normalise(constraint.statement))
            for constraint in item.local_constraints
        )),
        tuple(sorted(
            (requirement.type.value, requirement.domain, _normalise(requirement.statement))
            for requirement in item.covered_requirements
        )),
    )


def decomposition_distance(
    left: Decomposition,
    right: Decomposition,
    *,
    matcher: SubproblemMatcher = DEFAULT_MATCHER,
) -> float:
    """Definition 7 distance over matcher-defined equivalence classes."""
    items = tuple(left.subproblems) + tuple(right.subproblems)
    labels = equivalence_classes(items, matcher)
    split = len(left.subproblems)
    left_labels, right_labels = labels[:split], labels[split:]
    left_by_id = {item.identifier: label for item, label in zip(left.subproblems, left_labels)}
    right_by_id = {item.identifier: label for item, label in zip(right.subproblems, right_labels)}
    left_s, right_s = frozenset(left_labels), frozenset(right_labels)
    left_e = frozenset((left_by_id[a], left_by_id[b]) for a, b in left.E)
    right_e = frozenset((right_by_id[a], right_by_id[b]) for a, b in right.E)
    return 1.0 - 0.5 * (_jaccard(left_s, right_s) + _jaccard(left_e, right_e))


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decomposition: Decomposition
    rule: str
    selected_candidate_id: str | None
    rationale: str
    engineering_tie_break: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    identifier: str
    decomposition: Decomposition

    def __post_init__(self) -> None:
        if not self.identifier.strip():
            raise ValueError("Candidate.identifier must not be empty")


def _candidate_map(candidates: Sequence[Candidate]) -> dict[str, Candidate]:
    result = {item.identifier: item for item in candidates}
    if not result:
        raise ValueError("At least one candidate is required")
    if len(result) != len(candidates):
        raise ValueError("Candidate identifiers must be unique")
    return result


def authority(
    candidates: Sequence[Candidate],
    *,
    judge_id: str,
    selected_candidate_id: str,
    rationale: str,
) -> DecisionResult:
    """Authority: return the candidate selected by the designated judge."""
    pool = _candidate_map(candidates)
    if not judge_id.strip() or not rationale.strip():
        raise ValueError("Authority requires judge identity and rationale")
    if selected_candidate_id not in pool:
        raise ValueError("Authority may select only a supplied candidate")
    return DecisionResult(
        pool[selected_candidate_id].decomposition, "authority",
        selected_candidate_id, f"Judge {judge_id}: {rationale}",
    )


def rank_sum(
    candidates: Sequence[Candidate],
    rankings: Mapping[str, Sequence[str]],
) -> DecisionResult:
    """Select argmin_j sum_i rank_i(D_j), as specified for S3."""
    pool = _candidate_map(candidates)
    if not rankings:
        raise ValueError("Rank-sum requires at least one voter ranking")
    expected = set(pool)
    totals = {identifier: 0 for identifier in pool}
    for voter, ranking in rankings.items():
        if not voter.strip() or len(ranking) != len(expected) or set(ranking) != expected:
            raise ValueError("Every ranking must be a complete permutation of candidates")
        for rank, candidate_id in enumerate(ranking, start=1):
            totals[candidate_id] += rank
    winner = min(totals, key=lambda item: (totals[item], item))
    return DecisionResult(
        pool[winner].decomposition, "rank-sum", winner,
        f"Minimum aggregate rank: {totals[winner]}.",
        "Lexicographically smallest candidate identifier breaks equal rank sums.",
    )


def union(candidates: Sequence[Candidate], *, matcher: SubproblemMatcher = DEFAULT_MATCHER) -> DecisionResult:
    """Union candidate subproblems/edges/composition, merging exact equivalents.

    The paper's coverage-preserving union is not a validity guarantee:
    cycles can be introduced and are left for the common structural checker.
    """
    pool = _candidate_map(candidates)
    all_items = [item for candidate in pool.values() for item in candidate.decomposition.subproblems]
    labels = equivalence_classes(all_items, matcher)
    representatives: dict[int, Subproblem] = {}
    for item, label in zip(all_items, labels):
        representatives.setdefault(label, item)
    ordered_labels = sorted(representatives)
    canonical_id = {label: f"union-{index + 1}" for index, label in enumerate(ordered_labels)}
    item_label = {id(item): label for item, label in zip(all_items, labels)}
    merged_subproblems = tuple(
        replace(representatives[label], identifier=canonical_id[label])
        for label in ordered_labels
    )

    merged_edges: set[tuple[str, str]] = set()
    merged_composition: dict[str, set[str]] = {}
    for candidate in pool.values():
        decomposition = candidate.decomposition
        local = {item.identifier: item_label[id(item)] for item in decomposition.subproblems}
        for source, target in decomposition.E:
            merged_edges.add((canonical_id[local[source]], canonical_id[local[target]]))
        for entry in decomposition.composition:
            contributors = merged_composition.setdefault(entry.deliverable, set())
            for contributor in entry.contributor_ids:
                contributors.add(canonical_id[local[contributor]])

    result = Decomposition(
        merged_subproblems,
        tuple(Dependency(a, b) for a, b in sorted(merged_edges)),
        tuple(
            DeliverableComposition(key, tuple(sorted(values)))
            for key, values in sorted(merged_composition.items())
        ),
    )
    return DecisionResult(
        result, "union", None,
        "Union of candidate subproblems, dependencies and deliverable contributors; "
        "equivalent subproblems deduplicated.",
    )


def majority(
    candidates: Sequence[Candidate],
    ballots: Mapping[str, frozenset[tuple]],
) -> DecisionResult:
    """Keep pooled subproblems endorsed by strictly more than n/2 voters.

    Ballots are keyed by the canonical subproblem_signature. Dependencies and
    deliverable contributors are retained from the union only when both
    endpoint/contributor subproblems survive the vote.
    """
    pool = _candidate_map(candidates)
    if not ballots:
        raise ValueError("Majority requires at least one voter ballot")
    if any(not voter.strip() for voter in ballots):
        raise ValueError("Voter identifiers must not be empty")

    all_items: dict[tuple, Subproblem] = {}
    all_edges: set[tuple[tuple, tuple]] = set()
    all_composition: dict[str, set[tuple]] = {}
    for candidate in pool.values():
        d = candidate.decomposition
        for item in d.subproblems:
            all_items.setdefault(subproblem_signature(item), item)
        by_id = {item.identifier: subproblem_signature(item) for item in d.subproblems}
        all_edges.update((by_id[a], by_id[b]) for a, b in d.E)
        for entry in d.composition:
            all_composition.setdefault(entry.deliverable, set()).update(
                by_id[item] for item in entry.contributor_ids
            )

    unknown = set().union(*ballots.values()) - set(all_items)
    if unknown:
        raise ValueError("Ballot contains a subproblem absent from the pooled candidate list")
    kept = {
        signature for signature in all_items
        if sum(signature in ballot for ballot in ballots.values()) > len(ballots) / 2
    }
    ordered = sorted(kept, key=repr)
    ids = {signature: f"majority-{i + 1}" for i, signature in enumerate(ordered)}
    subproblems = tuple(
        replace(all_items[signature], identifier=ids[signature])
        for signature in ordered
    )
    edges = tuple(
        Dependency(ids[a], ids[b])
        for a, b in sorted(all_edges, key=repr)
        if a in kept and b in kept
    )
    composition = tuple(
        DeliverableComposition(
            deliverable,
            tuple(sorted(ids[item] for item in contributors if item in kept)),
        )
        for deliverable, contributors in sorted(all_composition.items())
    )
    result = Decomposition(subproblems, edges, composition)
    return DecisionResult(
        result, "majority", None,
        "Subproblems retained only when endorsed by strictly more than half of voters.",
    )


def synthesis(
    candidates: Sequence[Candidate],
    synthesized: Decomposition,
    *,
    synthesizer_id: str,
    rationale: str,
) -> DecisionResult:
    """Accept an explicit synthesizer-produced decomposition, not a vote."""
    _candidate_map(candidates)
    if not synthesizer_id.strip() or not rationale.strip():
        raise ValueError("Synthesis requires synthesizer identity and rationale")
    return DecisionResult(
        synthesized, "synthesis", None,
        f"Synthesizer {synthesizer_id}: {rationale}",
    )


def compromise(
    candidates: Sequence[Candidate],
    negotiated: Decomposition,
    *,
    mediator_id: str,
    rationale: str,
) -> DecisionResult:
    """Accept the mediator's negotiated result between candidate positions."""
    if len(_candidate_map(candidates)) != 2:
        raise ValueError("The paper's compromise operator requires exactly two candidates")
    if not mediator_id.strip() or not rationale.strip():
        raise ValueError("Compromise requires mediator identity and rationale")
    return DecisionResult(
        negotiated, "compromise", None,
        f"Mediator {mediator_id}: {rationale}",
    )


def consensus_medoid(candidates: Sequence[Candidate], *, matcher: SubproblemMatcher = DEFAULT_MATCHER) -> DecisionResult:
    """Return the medoid candidate for Delphi-style consensus (Table 4 S4)."""
    pool = _candidate_map(candidates)
    if len(pool) == 1:
        only = next(iter(pool.values()))
        return DecisionResult(only.decomposition, "consensus-medoid", only.identifier,
                              "Only one candidate; it is the medoid.")
    totals = {
        identifier: sum(
            decomposition_distance(candidate.decomposition, other.decomposition, matcher=matcher)
            for other_id, other in pool.items()
            if other_id != identifier
        )
        for identifier, candidate in pool.items()
    }
    winner = min(totals, key=lambda item: (totals[item], item))
    return DecisionResult(
        pool[winner].decomposition, "consensus-medoid", winner,
        f"Candidate with minimum total distance to the other latest drafts: {totals[winner]:.6f}.",
        "Lexicographically smallest candidate identifier breaks equal medoid scores.",
    )
