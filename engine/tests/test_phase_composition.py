import pytest

from sociodec.phase_composition import (
    CandidateState,
    PhaseContract,
    PhaseKind,
    PhaseValue,
    c1_phase_contracts,
    transition_candidate_state,
    validate_phase_preconditions,
    validate_phase_chain,
)


def test_c1_has_generation_examination_revision_decision_order():
    phases = c1_phase_contracts(revision_rounds=1)
    assert [phase.kind for phase in phases] == [
        PhaseKind.GENERATION,
        PhaseKind.EXAMINATION,
        PhaseKind.REVISION,
        PhaseKind.DECISION,
    ]
    assert validate_phase_chain(phases).valid


def test_c1_allows_zero_revision_rounds_when_algorithm_agreement_stop_fires():
    phases = c1_phase_contracts(revision_rounds=0)
    assert [phase.kind for phase in phases] == [
        PhaseKind.GENERATION, PhaseKind.DECISION,
    ]


@pytest.mark.parametrize("phases", [
    (
        PhaseContract(PhaseKind.EXAMINATION, "compare",
                      PhaseValue.CANDIDATE_SET, PhaseValue.OBJECTIONS),
        PhaseContract(PhaseKind.DECISION, "judge",
                      PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION),
    ),
    (
        PhaseContract(PhaseKind.GENERATION, "generate",
                      PhaseValue.PROMPT, PhaseValue.CANDIDATE_SET),
        PhaseContract(PhaseKind.DECISION, "judge",
                      PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION),
        PhaseContract(PhaseKind.DECISION, "judge-again",
                      PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION),
    ),
    (
        PhaseContract(PhaseKind.GENERATION, "generate",
                      PhaseValue.PROMPT, PhaseValue.CANDIDATE_SET),
        PhaseContract(PhaseKind.DECISION, "judge",
                      PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION),
        PhaseContract(PhaseKind.REVISION, "revise",
                      PhaseValue.OBJECTIONS, PhaseValue.CANDIDATE_SET),
    ),
    (
        PhaseContract(PhaseKind.GENERATION, "generate",
                      PhaseValue.PROMPT, PhaseValue.CANDIDATE_SET),
        PhaseContract(PhaseKind.REVISION, "revise",
                      PhaseValue.OBJECTIONS, PhaseValue.CANDIDATE_SET),
        PhaseContract(PhaseKind.DECISION, "judge",
                      PhaseValue.CANDIDATE_SET, PhaseValue.DECOMPOSITION),
    ),
])
def test_invalid_phase_compositions_fail_closed(phases):
    with pytest.raises(ValueError, match="Invalid phase composition"):
        validate_phase_chain(phases)


def test_examination_requires_at_least_two_candidates():
    phase = c1_phase_contracts(1)[1]
    with pytest.raises(ValueError, match="at least 2"):
        validate_phase_preconditions(
            phase, CandidateState(size=1, independent=True)
        )


def test_revision_requires_nonempty_objections():
    phase = c1_phase_contracts(1)[2]
    with pytest.raises(ValueError, match="non-empty objection"):
        validate_phase_preconditions(
            phase, CandidateState(size=3, independent=True),
            objections_nonempty=False,
        )


def test_independence_is_monotone_and_cannot_be_restored():
    expose = PhaseContract(
        PhaseKind.EXAMINATION, "shared-deliberation",
        PhaseValue.CANDIDATE_SET, PhaseValue.OBJECTIONS,
        preserves_independence=False,
    )
    state = transition_candidate_state(
        expose, CandidateState(size=3, independent=True)
    )
    assert state.independent is False
    preserve = PhaseContract(
        PhaseKind.REVISION, "later-private-revision",
        PhaseValue.OBJECTIONS, PhaseValue.CANDIDATE_SET,
        preserves_independence=True,
    )
    assert transition_candidate_state(preserve, state).independent is False


def test_rank_like_precondition_rejects_lost_independence():
    phase = PhaseContract(
        PhaseKind.EXAMINATION, "independent-ranking",
        PhaseValue.CANDIDATE_SET, PhaseValue.OBJECTIONS,
        requires_independence=True,
    )
    with pytest.raises(ValueError, match="requires independent candidates"):
        validate_phase_preconditions(
            phase, CandidateState(size=3, independent=False)
        )


def test_c1_revision_preserves_independence_when_only_objections_are_shared():
    phases = c1_phase_contracts(1)
    state = CandidateState(size=3, independent=True)
    after_examination = transition_candidate_state(phases[1], state)
    after_revision = transition_candidate_state(phases[2], after_examination)
    assert after_revision.independent is True
