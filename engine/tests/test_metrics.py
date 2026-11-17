import pytest
from sociodec.metrics import (precision_recall_f1, span_entailment_rate, decomposition_metrics,
    process_gain, wilcoxon_paired, holm_correction, confidence_interval)

def test_prf_and_empty_cases():
    r=precision_recall_f1({"a","b"},{"b","c"})
    assert (r.true_positive,r.false_positive,r.false_negative)==(1,1,1)
    assert r.precision==r.recall==r.f1==.5
    assert precision_recall_f1(set(),set()).f1==1
    assert precision_recall_f1(set(),{"x"}).f1==0

def test_span_entailment_requires_annotations():
    assert span_entailment_rate([True,False,True])==pytest.approx(2/3)
    with pytest.raises(ValueError): span_entailment_rate([])
    with pytest.raises(TypeError): span_entailment_rate([1,0])

def test_table_nine_decomposition_metrics():
    m=decomposition_metrics(requirements={"r1","r2"},covered_requirements={"r1","r2"},
        subproblem_signatures=["a","a","b"],edges=[("s1","s2"),("s2","s3")],
        acyclic=True,composition_complete=True,subproblem_solved=[True,False,True],utility=.8,depth=2)
    assert m.valid and m.coverage==1
    assert m.redundancy==pytest.approx(2/3) and m.coupling==pytest.approx(2/3)
    assert m.solvability==pytest.approx(2/3) and m.utility==.8

def test_validity_needs_coverage_acyclicity_and_composition():
    m=decomposition_metrics(requirements={"r"},covered_requirements=set(),
        subproblem_signatures=["s"],edges=[("s","s")],acyclic=True,composition_complete=False)
    assert not m.valid and m.coverage==0

def test_execution_metrics_are_undefined_without_evidence():
    m=decomposition_metrics(requirements={"r"},covered_requirements={"r"},
        subproblem_signatures=["s"],edges=[],acyclic=True,composition_complete=True)
    assert m.solvability is None and m.utility is None

def test_process_gain():
    assert process_gain(.8,.6)==pytest.approx(.2)
    with pytest.raises(ValueError): process_gain(1.2,.2)

def test_wilcoxon_effect_ci_and_reproducibility():
    x=[.9,.8,.7,.9]; y=[.6,.7,.6,.8]
    r=wilcoxon_paired(x,y,seed=42,bootstrap_samples=500)
    assert r.n_pairs==4 and r.rank_biserial==1 and r.p_value<.1
    assert r.ci95_mean_difference[0]<=r.mean_difference<=r.ci95_mean_difference[1]
    assert r==wilcoxon_paired(x,y,seed=42,bootstrap_samples=500)

def test_wilcoxon_zero_differences_and_all_zero():
    assert wilcoxon_paired([1,2],[1,1]).n_pairs==1
    r=wilcoxon_paired([1,2],[1,2])
    assert r.n_pairs==0 and r.p_value==1

def test_holm_step_down():
    assert holm_correction({"a":.01,"b":.04,"c":.03})==pytest.approx({"a":.03,"b":.06,"c":.06})

def test_holm_rejects_invalid():
    with pytest.raises(ValueError): holm_correction({"bad":float("nan")})

def test_bootstrap_ci_constant_and_repeatable():
    assert confidence_interval([2,2,2],seed=7,bootstrap_samples=500)==(2,2)

@pytest.mark.parametrize("kwargs",[
    {"requirements":set(),"covered_requirements":set()},
    {"requirements":{"r"},"covered_requirements":{"r"},"subproblem_signatures":[]},
])
def test_reject_undefined_denominators(kwargs):
    base=dict(subproblem_signatures=["s"],edges=[],acyclic=True,composition_complete=True)
    base.update(kwargs)
    with pytest.raises(ValueError): decomposition_metrics(**base)
