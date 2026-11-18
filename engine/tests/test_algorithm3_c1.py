from sociodec.algorithm3_c1 import (Algorithm3C1Executor, C1Callbacks, AnonymousObjection, AnonymousObjections)


def _executor(*, n=3, T=1, distances=None, judge_verdicts=("accept",)):
    calls = {"draft": [], "compare": 0, "revise": [], "merge": 0,
             "judge": 0, "judge_revise": 0, "check": 0}
    verdicts = iter(judge_verdicts)
    distances = distances or {}

    def distance(left, right):
        return distances.get((left, right), distances.get((right, left), 1.0))

    def judge(candidate, candidates):
        calls["judge"] += 1
        verdict = next(verdicts)
        return verdict, AnonymousObjections((AnonymousObjection("gap", "repair this"),)) if verdict == "reject" else None

    callbacks = C1Callbacks(
        draft=lambda agent: (calls["draft"].append(agent) or f"draft-{agent}"),
        compare=lambda candidates: (calls.__setitem__("compare", calls["compare"] + 1)
                                    or AnonymousObjections((AnonymousObjection("gap", "missing dependency"),))),
        revise=lambda agent, own, objections: (
            calls["revise"].append((agent, own, objections)) or f"revised-{agent}"
        ),
        merge=lambda candidates: (calls.__setitem__("merge", calls["merge"] + 1)
                                  or {"merged": dict(candidates)}),
        judge=judge,
        judge_revise=lambda candidate, objections: (
            calls.__setitem__("judge_revise", calls["judge_revise"] + 1)
            or {"judge-revised": candidate}
        ),
        check_and_repair=lambda candidate: (
            calls.__setitem__("check", calls["check"] + 1)
            or ({"checked": candidate}, ())
        ),
        distance=distance,
    )
    models = {f"a{i}": (f"model-{i}", f"family-{i}") for i in range(1, n + 1)}
    executor = Algorithm3C1Executor(
        decomposer_models=models,
        comparator_model=("comparator-model", "comparator-family"),
        synthesizer_model=("synth-model", "synth-family"),
        judge_model=("judge-model", "judge-family"),
        callbacks=callbacks, epsilon=0.1, T=T,
    )
    return executor, calls


def test_algorithm3_c1_one_revision_round_costs_2n_plus_3():
    executor, calls = _executor(n=3, T=1)
    result = executor.run()
    assert result.calls_made == 9
    assert result.calls_made == 2 * 3 + 3
    assert result.revisions == 1
    assert result.judge_revisions == 0
    assert result.verdict == "accept"
    assert calls["draft"] == ["a1", "a2", "a3"]
    assert len(calls["revise"]) == 3


def test_algorithm3_early_agreement_skips_compare_and_revision():
    executor, calls = _executor(
        n=3, T=2,
        distances={("draft-a1", "draft-a2"): 0.0,
                   ("draft-a1", "draft-a3"): 0.0,
                   ("draft-a2", "draft-a3"): 0.0},
    )
    result = executor.run()
    assert result.early_agreement is True
    assert result.calls_made == 5  # n drafts + merge + judge
    assert calls["compare"] == 0
    assert calls["revise"] == []


def test_algorithm3_rejected_judge_gets_exactly_one_aggregator_revision():
    executor, calls = _executor(n=3, T=1, judge_verdicts=("reject", "accept"))
    result = executor.run()
    assert result.verdict == "accept"
    assert result.judge_revisions == 1
    assert calls["judge"] == 2
    assert calls["judge_revise"] == 1
    assert result.calls_made == 11


def test_second_rejection_is_returned_as_failure_not_approval():
    executor, _ = _executor(n=3, T=1, judge_verdicts=("reject", "reject"))
    result = executor.run()
    assert result.verdict == "reject"
    assert "rejected by the judge" in result.failures
    assert result.calls_made == 11


def test_algorithm3_worst_case_bound_matches_paper_formula():
    executor, _ = _executor(n=3, T=2)
    assert executor.worst_case_calls == 3 * (2 + 1) + 2 + 4


def test_judge_family_must_be_distinct_from_authors_and_synthesizer():
    import pytest
    models = {"a1": ("m1", "family-a"), "a2": ("m2", "family-b")}
    callbacks = C1Callbacks(
        draft=lambda agent: agent, compare=lambda candidates: AnonymousObjections((AnonymousObjection("gap", "missing"),)),
        revise=lambda agent, own, objections: own,
        merge=lambda candidates: candidates, judge=lambda candidate, candidates: ("accept", None),
        judge_revise=lambda candidate, objections: candidate,
        check_and_repair=lambda candidate: (candidate, ()),
        distance=lambda left, right: 1.0,
    )
    with pytest.raises(ValueError, match="Judge must belong"):
        Algorithm3C1Executor(
            decomposer_models=models,
            comparator_model=("cm", "family-c"),
            synthesizer_model=("ag", "family-d"),
            judge_model=("ju", "family-a"),
            callbacks=callbacks, epsilon=0.0, T=1,
        )


def test_budget_overrun_fails_closed():
    import pytest
    executor, _ = _executor(n=3, T=1)
    with pytest.raises(RuntimeError, match="available call budget"):
        executor.run(available_calls=8)


def test_objection_contract_rejects_author_attribution():
    import pytest
    bad = AnonymousObjections((AnonymousObjection("gap", "a1 authored this objection"),))
    with pytest.raises(ValueError, match="author attribution"):
        bad.validate_no_author_ids(("a1",))


def test_executor_rejects_untyped_comparator_objections():
    import pytest
    executor, _ = _executor()
    executor.callbacks = C1Callbacks(
        draft=lambda agent: f"draft-{agent}",
        compare=lambda candidates: {"gap": "not typed"},
        revise=lambda agent, own, objections: own,
        merge=lambda candidates: candidates,
        judge=lambda candidate, candidates: ("accept", None),
        judge_revise=lambda candidate, objections: candidate,
        check_and_repair=lambda candidate: (candidate, ()),
        distance=lambda left, right: 1.0,
    )
    with pytest.raises(TypeError, match="AnonymousObjections"):
        executor.run()


def test_each_revision_receives_only_own_candidate_and_anonymous_objections():
    executor, calls = _executor(n=2, T=1)
    result = executor.run()
    assert result.revisions == 1
    assert len(calls["revise"]) == 2
    for agent, own, objections in calls["revise"]:
        assert own == f"draft-{agent}"
        assert isinstance(objections, AnonymousObjections)
        assert all(agent.casefold() not in (item.statement + item.evidence).casefold()
                   for item in objections.items)
