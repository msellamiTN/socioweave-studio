from dataclasses import replace

from sociodec.models.prompt import Interpretation, Prompt
from sociodec.runtime import run_strategy
from sociodec.strategy_protocols import build_strategy_blueprint


class RecordingInvoker:
    def __init__(self):
        self.calls = 0

    def invoke(self, agent, step, context):
        self.calls += 1
        return f"mock:{step.action.value}"


def test_strategy_run_accounting_distinguishes_calls_seeds_and_precomputed_steps():
    prompt = Prompt("Example task", Interpretation("Example"))
    blueprint = build_strategy_blueprint("S2", n=2)

    # S2's aggregator normally invokes a model. For this accounting edge-case
    # test, explicitly mark the final step non-model and supply its output.
    protocol = tuple(
        replace(step, invokes_model=False) if index == 2 else step
        for index, step in enumerate(blueprint.strategy.protocol)
    )
    strategy = replace(blueprint.strategy, protocol=protocol)

    invoker = RecordingInvoker()
    run = run_strategy(
        "S2-accounting-test", prompt, strategy, invoker,
        prompt_views=blueprint.prompt_views,
        seeds={"participant-1": "seeded draft"},
        precomputed_outputs={"step:2": "precomputed aggregate"},
    )
    assert run.protocol_steps == 3
    assert run.model_invocations == run.calls_made == invoker.calls == 1
    assert run.seeded_steps == 1
    assert run.precomputed_steps == 1
    assert run.protocol_steps == (
        run.model_invocations + run.seeded_steps + run.precomputed_steps
    )
