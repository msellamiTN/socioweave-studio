import json
import pytest
from sociodec.evaluation import EvaluationObservation, load_observations_jsonl, aggregate_observations, paired_comparison, correct_comparison_family, write_evaluation_outputs

def row(s,e,v,rep=0,status="success",**kw):
    return EvaluationObservation("BREAK",e,s,rep,status,{"utility":v} if status=="success" else {},**kw)

def test_aggregate_includes_failures_and_missing_metrics():
    out=aggregate_observations([row("S1","a",.8,calls=4,tokens=200),row("S1","b",0,status="failed")])[0]
    assert (out["n_trials"],out["n_success"],out["n_failed"])==(2,1,1)
    assert out["failure_rate"]==.5 and out["metrics"]["utility"]["missing"]==1
    assert out["mean_calls"]==4

def test_paired_by_prompt_averages_repeats_and_counts_missing_pairs():
    rows=[row("S1","a",.9),row("S1","a",.7,1),row("BASE","a",.5),row("BASE","a",.7,1),
          row("S1","b",.8),row("S1","c",.4),row("BASE","c",.5)]
    r=paired_comparison(rows,dataset="BREAK",strategy_id="S1",baseline_id="BASE",metric="utility",bootstrap_samples=200)
    assert r["n_paired_prompts"]==2 and r["n_prompts_missing_pair"]==1
    assert r["mean_paired_difference"]==pytest.approx(.1)

def test_holm_adjustment():
    r=correct_comparison_family([{"dataset":"D","strategy_id":"A","metric":"u","p_value_normal_approx":.01},
      {"dataset":"D","strategy_id":"B","metric":"u","p_value_normal_approx":.04}])
    assert r[0]["p_value_holm"]==pytest.approx(.02)
    assert r[1]["p_value_holm"]==pytest.approx(.04)

def test_jsonl_loader_rejects_duplicate_and_malformed_rows(tmp_path):
    p=tmp_path/"x.jsonl"
    x={"dataset":"BREAK","example_id":"a","strategy_id":"S1","repeat_index":0,"status":"success","metrics":{"utility":.8}}
    p.write_text(json.dumps(x)+"\n"+json.dumps(x)+"\n")
    with pytest.raises(ValueError,match="duplicate"): load_observations_jsonl(p)
    p.write_text('{"dataset":')
    with pytest.raises(ValueError,match="line 1"): load_observations_jsonl(p)

def test_contract_rejects_invalid_observations():
    with pytest.raises(ValueError): row("S1","a",.2,status="failed")
    with pytest.raises(ValueError): EvaluationObservation("D","e","S",0,"success",{},calls=-1)

def test_exports_json_csv_and_jsonl(tmp_path):
    rows=[row("S1","a",.8,calls=3),row("BASE","a",.6,calls=1)]
    comp=[paired_comparison(rows,dataset="BREAK",strategy_id="S1",baseline_id="BASE",metric="utility",bootstrap_samples=200)]
    paths=write_evaluation_outputs(rows,tmp_path,comp)
    assert len(paths)==4
    assert json.loads(open(paths["summary_json"]).read())[0]["n_success"]==1
    assert json.loads(open(paths["comparisons_json"]).read())[0]["p_value_holm"]>=0
