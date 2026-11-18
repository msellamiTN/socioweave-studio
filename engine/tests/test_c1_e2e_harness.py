"""Deterministic end-to-end harness for Algorithm 3 C1.

This suite exercises executor phase order, call bounds, early agreement,
bounded judge retry, and fail-closed propagation without live providers.
"""
from __future__ import annotations

import pytest

from sociodec.algorithm3_c1 import (
    Algorithm3C1Executor, AnonymousObjection, AnonymousObjections, C1Callbacks,
)


def build_harness(*, n=3, T=2, epsilon=0.0, distances=None, judge=("accept",),
                 fail_at=None):
    state = {"drafts": [], "compare": 0, "revisions": [], "merge": 0,
             "judge": 0, "judge_revise": 0, "check": 0, "phase_order": []}
    verdicts = iter(judge)
    distances = distances or {}

    def inject(name):
        if fail_at == name:
            raise RuntimeError(f"injected failure at {name}")

    def draft(actor):
        inject("gen")
        state["phase_order"].append("gen")
        state["drafts"].append(actor)
        return {"actor": actor, "draft": len(state["drafts"])}

    def compare(pool):
        inject("exa")
        state["phase_order"].append("exa")
        state["compare"] += 1
        return AnonymousObjections((AnonymousObjection("gap", "A required step is missing"),))

    def revise(actor, own, objections):
        inject("rev")
        state["phase_order"].append("rev")
        state["revisions"].append((actor, own, objections))
        return {"actor": actor, "revision": len(state["revisions"])}

    def merge(pool):
        inject("merge")
        state["phase_order"].append("merge")
        state["merge"] += 1
        return {"merged": list(pool.values())}

    def adjudicate(candidate, pool):
        inject("dec")
        state["phase_order"].append("dec")
        state["judge"] += 1
        verdict = next(verdicts)
        typed = AnonymousObjections((AnonymousObjection("repair", "Clarify a missing step"),))
        return verdict, typed if verdict == "reject" else None

    def judge_revise(candidate, objections):
        inject("judge-revision")
        state["phase_order"].append("judge-revision")
        state["judge_revise"] += 1
        return {"judge-revised": candidate}

    def check(candidate):
        inject("algorithm1")
        state["phase_order"].append("algorithm1")
        state["check"] += 1
        return {"validated": candidate}, ()

    def distance(left, right):
        key = (left["actor"], right["actor"])
        reverse = (key[1], key[0])
        return distances.get(key, distances.get(reverse, 1.0))

    callbacks = C1Callbacks(draft, compare, revise, merge, adjudicate, judge_revise, check, distance)
    models = {f"author-{i}": (f"model-{i}", f"family-{i}") for i in range(1, n + 1)}
    executor = Algorithm3C1Executor(
        decomposer_models=models,
        comparator_model=("comparator", "comparison-family"),
        synthesizer_model=("synthesizer", "synthesis-family"),
        judge_model=("judge", "judge-family"),
        callbacks=callbacks, epsilon=epsilon, T=T,
    )
    return executor, state


def test_e2e_accept_path_phase_order_and_exact_one_round_cost():
    executor, state = build_harness(n=3, T=1, judge=("accept",))
    result = executor.run()
    assert result.calls_made == 9 == 2 * 3 + 3
    assert result.revisions == 1
    assert result.judge_revisions == 0
    assert state["phase_order"] == ["gen"] * 3 + ["exa"] + ["rev"] * 3 + ["merge", "dec", "algorithm1"]


def test_e2e_early_agreement_minimum_path_cost():
    distances = {("author-1", "author-2"): 0, ("author-1", "author-3"): 0,
                 ("author-2", "author-3"): 0}
    executor, state = build_harness(n=3, T=3, epsilon=0.0, distances=distances)
    result = executor.run()
    assert result.early_agreement
    assert result.calls_made == 5 == 3 + 2
    assert state["compare"] == 0 and state["revisions"] == []


def test_e2e_rejected_judge_then_accept_has_exactly_one_revision_and_second_verdict():
    executor, state = build_harness(n=3, T=2, judge=("reject", "accept"))
    result = executor.run()
    assert result.verdict == "accept"
    assert result.judge_revisions == 1
    assert state["judge"] == 2 and state["judge_revise"] == 1
    assert result.calls_made == 13  # 3 gen + 2*(exa+3 rev) + merge + 2 judge + 1 revise + check


def test_e2e_second_judge_rejection_is_preserved_as_failure():
    executor, state = build_harness(n=3, T=1, judge=("reject", "reject"))
    result = executor.run()
    assert result.verdict == "reject"
    assert "rejected by the judge" in result.failures
    assert result.judge_revisions == 1 and state["judge"] == 2
    assert result.calls_made == 11


@pytest.mark.parametrize("n,T", [(2,1), (3,1), (4,2), (5,3)])
def test_call_bound_covers_worst_case_rejection_path(n, T):
    executor, _ = build_harness(n=n, T=T, judge=("reject", "accept"))
    result = executor.run()
    bound = n * (T + 1) + T + 4
    assert executor.worst_case_calls == bound
    assert result.calls_made <= bound
    # This implementation reaches the bound when every comparison round is used
    # and the first judge rejects, requiring the bounded second verdict.
    assert result.calls_made == bound


@pytest.mark.parametrize("failure_phase", ["gen", "exa", "rev", "merge", "dec", "judge-revision", "algorithm1"])
def test_injected_failure_propagates_fail_closed(failure_phase):
    verdict = ("reject", "accept") if failure_phase == "judge-revision" else ("accept",)
    executor, state = build_harness(n=3, T=1, judge=verdict, fail_at=failure_phase)
    with pytest.raises(RuntimeError, match=f"injected failure at {failure_phase}"):
        executor.run()
    # Failed operation was counted by the executor before callback execution.
    assert failure_phase in state["phase_order"]


def test_budget_preflight_rejects_too_small_minimum_path_before_provider_calls():
    executor, state = build_harness(n=3, T=1)
    with pytest.raises(RuntimeError, match="minimum C1 path"):
        executor.run(available_calls=4)
    assert state["drafts"] == []


def test_runtime_budget_stops_before_call_exceeding_budget():
    executor, state = build_harness(n=3, T=1)
    with pytest.raises(RuntimeError, match="available call budget"):
        executor.run(available_calls=8)
    assert state["drafts"] == ["author-1", "author-2", "author-3"]
