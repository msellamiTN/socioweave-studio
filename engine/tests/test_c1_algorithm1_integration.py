from sociodec.algorithm1_adapter import Algorithm1CheckRepairAdapter
from sociodec.algorithm3_c1 import (
    Algorithm3C1Executor, C1Callbacks, AnonymousObjection, AnonymousObjections,
)
from test_validation import setup_case


def test_c1_is_wired_to_concrete_algorithm1_check_repair():
    prompt, requirements, _, _, good = setup_case()
    adapter = Algorithm1CheckRepairAdapter(prompt=prompt, requirements=requirements)
    objection = AnonymousObjections((AnonymousObjection("coverage", "Check deliverable coverage"),))
    callbacks = C1Callbacks(
        draft=lambda agent: good,
        compare=lambda candidates: objection,
        revise=lambda agent, own, objections: own,
        merge=lambda candidates: good,
        judge=lambda merged, candidates: ("accept", None),
        judge_revise=lambda merged, objections: merged,
        check_and_repair=lambda candidate: (
            (result.decomposition, result.failures)
            if (result := adapter.run(candidate)) else (candidate, ())
        ),
        distance=lambda left, right: 1.0,
    )
    executor = Algorithm3C1Executor(
        decomposer_models={"author-A": ("mA", "family-A"), "author-B": ("mB", "family-B")},
        comparator_model=("cmp", "family-C"),
        synthesizer_model=("syn", "family-D"),
        judge_model=("judge", "family-E"),
        callbacks=callbacks, epsilon=0.0, T=1,
    )
    result = executor.run()
    assert result.decomposition == good
    assert result.failures == ()
    assert result.calls_made == 7
