"""Explicit prompt partitioning and paper-defined sequential combinations.

Domain partitions are an engineering policy over extracted evidence, not a
claim that the paper mandates a particular assignment heuristic. The caller
must provide the domain-to-agent mapping; missing or multiply assigned
domains fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sociodec.catalogue import StrategyId, get_strategy
from sociodec.extraction import AggregatedExtraction
from sociodec.models.prompt import Prompt
from sociodec.orchestrator import StrategyOutcome
from sociodec.selector import PlanItem
from sociodec.strategy_adapter import ConcreteStrategyAdapter


@dataclass(frozen=True, slots=True)
class DomainPartition:
    agent_domains: Mapping[str, tuple[str, ...]]

    def __post_init__(self) -> None:
        if not self.agent_domains:
            raise ValueError("At least one agent domain partition is required")
        if any(not agent.strip() for agent in self.agent_domains):
            raise ValueError("Partition agent identifiers must be non-empty")
        if any(not domains for domains in self.agent_domains.values()):
            raise ValueError("Every partition agent must receive at least one domain")
        if any(not domain.strip() for domains in self.agent_domains.values() for domain in domains):
            raise ValueError("Domain labels must be non-empty")
        flattened = [domain for domains in self.agent_domains.values() for domain in domains]
        if len(flattened) != len(set(flattened)):
            raise ValueError("Each domain must be assigned to exactly one agent")


def build_domain_prompt_views(
    prompt: Prompt,
    extraction: AggregatedExtraction,
    *,
    strategy_id: StrategyId | str,
    partition: DomainPartition,
    integrator_id: str | None = None,
) -> dict[str, str]:
    """Render evidence-bounded views for S1 (specialists) or S12 (experts).

    The coordinator/integrator receives the full declared prompt. Domain
    agents receive the declared goal, global constraints, deliverable names,
    and only extracted requirements/hypotheses for their assigned domains.
    Raw prompt text is not copied into a specialist view.
    """
    sid = StrategyId(strategy_id)
    if sid not in {StrategyId.S1, StrategyId.S12}:
        raise ValueError("Domain prompt partitioning is defined only for S1 and S12")
    expected_prefix = "specialist-" if sid is StrategyId.S1 else "expert-"
    expected = {f"{expected_prefix}{i}" for i in range(1, len(partition.agent_domains) + 1)}
    actual = set(partition.agent_domains)
    if actual != expected:
        raise ValueError(f"Partition agents must be exactly {sorted(expected)}")
    known_domains = {x.domain for x in extraction.requirements}
    known_domains.update(x.domain for x in extraction.hypotheses)
    assigned = {d for values in partition.agent_domains.values() for d in values}
    if assigned != known_domains:
        missing, extra = sorted(known_domains - assigned), sorted(assigned - known_domains)
        raise ValueError(f"Domain partition mismatch; missing={missing}, unknown={extra}")

    global_context = {
        "goal": prompt.iota.goal,
        "global_constraints": [
            {"kind": item.kind.value, "statement": item.statement}
            for item in prompt.iota.constraints
        ],
        "deliverables": list(prompt.iota.deliverables),
        "inputs": list(prompt.iota.inputs),
    }
    views: dict[str, str] = {}
    for agent, domains in partition.agent_domains.items():
        selected = set(domains)
        payload = {
            **global_context,
            "assigned_domains": list(domains),
            "explicit_requirements": [
                {"type": x.type.value, "domain": x.domain, "statement": x.statement}
                for x in extraction.requirements if x.domain in selected
            ],
            "implicit_hypotheses": [
                {"type": x.type.value, "domain": x.domain,
                 "statement": x.statement, "rationale": x.rationale}
                for x in extraction.hypotheses if x.domain in selected
            ],
            "instruction": (
                "Decompose only the assigned domain. Do not infer requirements "
                "from another domain. Preserve global constraints and report "
                "cross-domain dependencies explicitly for the integrator."
            ),
        }
        import json
        views[agent] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if integrator_id is not None:
        if not integrator_id.strip() or integrator_id in views:
            raise ValueError("Integrator ID must be non-empty and distinct from partition agents")
        views[integrator_id] = prompt.text
    return views


class SequentialCompositionExecutor:
    """Execute the paper's C8 and C2 sequential chains using typed adapters.

    Each second strategy receives the preceding decomposition as the seed of
    one author only. The ConcreteStrategyAdapter enforces that placement.
    C1 is deliberately excluded: it is Algorithm 3 phase composition, not a
    sequential chain, and has a separate implementation contract.
    """

    _CHAINS = {
        PlanItem.C8_BRAINSTORM_THEN_REVIEW: (PlanItem.S2, PlanItem.S8),
        PlanItem.COMBO_JIGSAW_THEN_CRITIC: (PlanItem.S12, PlanItem.S5),
    }

    def __init__(self, adapter: ConcreteStrategyAdapter) -> None:
        self.adapter = adapter

    def __call__(
        self, item: PlanItem, prompt: Prompt, extraction: AggregatedExtraction,
        initial_drafts, chain_seed, available_calls: int,
    ) -> StrategyOutcome:
        if item not in self._CHAINS:
            raise ValueError(
                f"{item.value} is not a sequential combination; "
                "C1 requires the dedicated Algorithm 3 phase-composition executor"
            )
        first_item, second_item = self._CHAINS[item]
        n = getattr(self.adapter, "n", 3)
        k = getattr(self.adapter, "k", 3)
        T = getattr(self.adapter, "T", 2)
        first_allowance = get_strategy(StrategyId(first_item.value)).calls(n=n, k=k, T=T)
        second_allowance = get_strategy(StrategyId(second_item.value)).calls(n=n, k=k, T=T)
        if first_allowance + second_allowance > available_calls:
            raise RuntimeError("Available call budget cannot cover both sequential phases")
        # Definition 12: phase one must execute independently. Caller-supplied
        # drafts/seeds are composition-boundary inputs and cannot suppress
        # the first strategy's own draft calls.
        first = self.adapter(
            first_item, prompt, extraction, (), None,
            first_allowance,
        )
        if first.calls_made > first_allowance:
            raise RuntimeError("First chain phase exceeded its Table 4 call allowance")
        second = self.adapter(
            second_item, prompt, extraction, initial_drafts,
            first.decomposition, second_allowance,
        )
        if second.calls_made > second_allowance:
            raise RuntimeError("Second chain phase exceeded its Table 4 call allowance")
        total = first.calls_made + second.calls_made
        if total > available_calls:
            raise RuntimeError("Sequential composition exceeded the available call budget")
        verdicts = {}
        for verdict in (*first.hypothesis_verdicts, *second.hypothesis_verdicts):
            previous = verdicts.get(verdict.hypothesis)
            if previous is not None and previous != verdict.verdict:
                raise ValueError(
                    f"Conflicting chained hypothesis verdicts for {verdict.hypothesis.statement!r}"
                )
            verdicts[verdict.hypothesis] = verdict.verdict
        from sociodec.validation import HypothesisVerdict
        return StrategyOutcome(
            decomposition=second.decomposition,
            calls_made=total,
            hypothesis_verdicts=tuple(
                HypothesisVerdict(hypothesis, verdict)
                for hypothesis, verdict in verdicts.items()
            ),
            candidate_support_counts=second.candidate_support_counts,
            findings=tuple((*first.findings, *second.findings)),
            strategy_run_id=f"{item.value}:{first.strategy_run_id}>{second.strategy_run_id}",
        )
