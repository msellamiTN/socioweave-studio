"""The thirteen strategies exactly as catalogued in Table 4 of the paper."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StrategyId(StrEnum):
    S1 = "S1"
    S12 = "S12"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S9 = "S9"
    S5 = "S5"
    S6 = "S6"
    S8 = "S8"
    S13 = "S13"
    S7 = "S7"
    S11 = "S11"
    S10 = "S10"


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    identifier: StrategyId
    name: str
    decision_rule: str
    call_formula: str
    depth_formula: str
    required_agents: str
    visibility_pattern: str
    protocol_summary: str

    def calls(self, *, n: int = 3, k: int = 3, T: int = 2) -> int:
        _validate_parameters(n, k, T)
        formulas = {
            StrategyId.S1: n + 2,
            StrategyId.S12: n + 1,
            StrategyId.S2: n + 1,
            StrategyId.S3: 2 * n,
            StrategyId.S4: T * (n + 1),
            StrategyId.S9: 2 * n,
            StrategyId.S5: 4,
            StrategyId.S6: 3,
            StrategyId.S8: k + 3,
            StrategyId.S13: 4,
            StrategyId.S7: 5,
            StrategyId.S11: 5,
            StrategyId.S10: n * T + 1,
        }
        return formulas[self.identifier]

    def depth(self, *, n: int = 3, k: int = 3, T: int = 2) -> int:
        _validate_parameters(n, k, T)
        formulas = {
            StrategyId.S1: 3,
            StrategyId.S12: 2,
            StrategyId.S2: 2,
            StrategyId.S3: 2,
            StrategyId.S4: 2 * T,
            StrategyId.S9: 2,
            StrategyId.S5: 4,
            StrategyId.S6: 3,
            StrategyId.S8: 4,
            StrategyId.S13: 4,
            StrategyId.S7: 3,
            StrategyId.S11: 3,
            StrategyId.S10: n * T + 1,
        }
        return formulas[self.identifier]


def _validate_parameters(n: int, k: int, T: int) -> None:
    if n < 1:
        raise ValueError("n must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")
    if T < 1:
        raise ValueError("T must be >= 1")


STRATEGIES: tuple[StrategyDefinition, ...] = (
    StrategyDefinition(StrategyId.S1, "Division of labour", "authority", "n+2", "3",
        "1 coordinator + n specialists", "Each specialist sees its assigned domain part",
        "Coordinator splits prompt; specialists draft in parallel; coordinator checks merged coverage."),
    StrategyDefinition(StrategyId.S12, "Jigsaw", "union", "n+1", "2",
        "n facet experts + 1 integrator", "Each expert sees one facet",
        "Experts draft facet lists in parallel; integrator merges and adds cross-facet dependencies."),
    StrategyDefinition(StrategyId.S2, "Brainstorming", "union", "n+1", "2",
        "n participants + 1 aggregator", "No sharing during generation",
        "Participants generate unfiltered candidate subproblems; aggregator merges duplicates and groups items."),
    StrategyDefinition(StrategyId.S3, "Nominal group technique", "rank-sum", "2n", "2",
        "n members + facilitator/rule", "Drafts hidden until pooled",
        "Members draft independently, then each ranks all whole drafts; minimum rank sum wins."),
    StrategyDefinition(StrategyId.S4, "Delphi", "consensus", "T(n+1)", "2T",
        "n anonymous experts + facilitator", "Anonymous summaries only",
        "Experts draft/revise over rounds; facilitator summarises divergences; stable medoid is returned."),
    StrategyDefinition(StrategyId.S9, "Majority vote", "majority", "2n", "2",
        "n decomposer-voters + teller/rule", "Drafts hidden until vote",
        "Agents draft independently; each votes on every pooled subproblem; strict majority items are kept."),
    StrategyDefinition(StrategyId.S5, "Devil's advocate", "authority", "4", "4",
        "decomposer + critic + judge", "Critic sees the author's draft",
        "Author drafts; critic lists typed objections; author revises; judge approves or rejects the response."),
    StrategyDefinition(StrategyId.S6, "Dialectical inquiry", "synthesis", "3", "3",
        "2 decomposers + synthesizer", "Second decomposer sees first draft",
        "Second author constructs a counter-plan; synthesizer combines the two structures."),
    StrategyDefinition(StrategyId.S8, "Peer review", "authority", "k+3", "4",
        "author + k reviewers + editor", "Reviewers independently see the draft",
        "Reviewers critique in parallel; editor decides whether revision is required; author revises once."),
    StrategyDefinition(StrategyId.S13, "Role reversal", "authority", "4", "4",
        "2 agents swapping author/critic roles", "Full visibility",
        "A drafts; B critiques and repairs; A critiques the repair; B's repaired draft is returned."),
    StrategyDefinition(StrategyId.S7, "Adversarial procedure", "authority", "5", "3",
        "2 decomposers + neutral judge", "Judge sees both defended cases",
        "Two parties draft independently and defend their structures; neutral judge selects one."),
    StrategyDefinition(StrategyId.S11, "Mediation", "compromise", "5", "3",
        "2 decomposers + mediator", "Mediator sees both drafts",
        "Two drafts are summarised by mediator; authors revise in parallel; negotiated result is returned."),
    StrategyDefinition(StrategyId.S10, "Consensus deliberation", "consensus", "nT+1", "nT+1",
        "n participants + moderator", "Everything shared",
        "Participants sequentially amend a shared draft until stable or the moderator reports no objection."),
)


def get_strategy(identifier: StrategyId | str) -> StrategyDefinition:
    key = StrategyId(identifier)
    return next(item for item in STRATEGIES if item.identifier is key)


class CandidateStrategyId(StrEnum):
    """Five unexplored matrix cells; candidates, not validated catalogue entries."""
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"
    C5 = "C5"


@dataclass(frozen=True, slots=True)
class CandidateStrategyDefinition:
    identifier: CandidateStrategyId
    name: str
    production_pattern: str
    decision_family: str
    status: str = "candidate — not an established strategy in the paper"

    def __post_init__(self) -> None:
        if self.status != "candidate — not an established strategy in the paper":
            raise ValueError("Candidate strategy status must remain explicitly unvalidated")


CANDIDATE_STRATEGIES: tuple[CandidateStrategyDefinition, ...] = (
    CandidateStrategyDefinition(CandidateStrategyId.C1, "Objection ballot",
        "One author, then critics", "Rank-sum or majority"),
    CandidateStrategyDefinition(CandidateStrategyId.C2, "Patch merge",
        "One author, then critics", "Union or synthesis"),
    CandidateStrategyDefinition(CandidateStrategyId.C3, "Redundant jigsaw",
        "Partitioned authors", "Rank-sum or majority"),
    CandidateStrategyDefinition(CandidateStrategyId.C4, "Interface negotiation",
        "Partitioned authors", "Compromise or consensus"),
    CandidateStrategyDefinition(CandidateStrategyId.C5, "Chaired deliberation",
        "Shared drafting", "Authority"),
)
