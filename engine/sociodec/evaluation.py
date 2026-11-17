"""Core 18 campaign aggregation and paired evaluation."""
from __future__ import annotations
import csv, json, math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping
from sociodec.metrics import holm_correction, wilcoxon_paired

@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    dataset: str
    example_id: str
    strategy_id: str
    repeat_index: int
    status: str
    metrics: Mapping[str, float] = field(default_factory=dict)
    calls: int | None = None
    depth: int | None = None
    tokens: int | None = None
    latency_seconds: float | None = None
    failure_type: str | None = None
    def __post_init__(self):
        for name in ("dataset","example_id","strategy_id"):
            if not getattr(self,name).strip(): raise ValueError(f"{name} must be non-empty")
        if isinstance(self.repeat_index,bool) or not isinstance(self.repeat_index,int) or self.repeat_index<0:
            raise ValueError("repeat_index must be a non-negative integer")
        if self.status not in {"success","failed"}: raise ValueError("status must be success or failed")
        for name in ("calls","depth","tokens"):
            v=getattr(self,name)
            if v is not None and (isinstance(v,bool) or not isinstance(v,int) or v<0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if self.latency_seconds is not None and (isinstance(self.latency_seconds,bool) or
            not isinstance(self.latency_seconds,(int,float)) or not math.isfinite(self.latency_seconds) or self.latency_seconds<0):
            raise ValueError("latency_seconds must be finite and non-negative")
        for k,v in self.metrics.items():
            if not isinstance(k,str) or not k or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v):
                raise ValueError("metric values must be named finite numbers")
        if self.status=="failed" and self.metrics: raise ValueError("failed observations must not carry success metrics")

def load_observations_jsonl(path: str | Path) -> tuple[EvaluationObservation,...]:
    rows=[]; seen=set()
    with Path(path).open(encoding="utf-8") as f:
        for line_no,line in enumerate(f,1):
            if not line.strip(): continue
            try:
                row=EvaluationObservation(**json.loads(line))
                key=(row.dataset,row.example_id,row.strategy_id,row.repeat_index)
                if key in seen: raise ValueError(f"duplicate observation key {key}")
                seen.add(key); rows.append(row)
            except (TypeError,ValueError,KeyError,json.JSONDecodeError) as exc:
                raise ValueError(f"invalid observation at line {line_no}: {exc}") from exc
    return tuple(rows)

def aggregate_observations(observations: Iterable[EvaluationObservation]) -> tuple[dict,...]:
    groups=defaultdict(list)
    for r in observations: groups[(r.dataset,r.strategy_id)].append(r)
    out=[]
    for (dataset,strategy),rows in sorted(groups.items()):
        ok=[r for r in rows if r.status=="success"]
        names=sorted({k for r in ok for k in r.metrics})
        metrics={}
        for name in names:
            vals=[float(r.metrics[name]) for r in ok if name in r.metrics]
            metrics[name]={"n":len(vals),"mean":sum(vals)/len(vals),"missing":len(rows)-len(vals)}
        def avg(field):
            vals=[getattr(r,field) for r in ok if getattr(r,field) is not None]
            return sum(vals)/len(vals) if vals else None
        out.append({"dataset":dataset,"strategy_id":strategy,"n_trials":len(rows),
            "n_success":len(ok),"n_failed":len(rows)-len(ok),
            "failure_rate":(len(rows)-len(ok))/len(rows),"metrics":metrics,
            "mean_calls":avg("calls"),"mean_depth":avg("depth"),
            "mean_tokens":avg("tokens"),"mean_latency_seconds":avg("latency_seconds")})
    return tuple(out)

def paired_comparison(observations: Iterable[EvaluationObservation], *, dataset: str,
    strategy_id: str, baseline_id: str, metric: str, seed: int=0,
    bootstrap_samples: int=4000) -> dict:
    rows=[r for r in observations if r.dataset==dataset and r.strategy_id in {strategy_id,baseline_id}
          and r.status=="success" and metric in r.metrics]
    values=defaultdict(lambda:defaultdict(list))
    for r in rows: values[r.example_id][r.strategy_id].append(float(r.metrics[metric]))
    pairs=[(sum(v[strategy_id])/len(v[strategy_id]),sum(v[baseline_id])/len(v[baseline_id]))
           for v in values.values() if v[strategy_id] and v[baseline_id]]
    test=wilcoxon_paired([a for a,b in pairs],[b for a,b in pairs],
                         seed=seed,bootstrap_samples=bootstrap_samples)
    return {"dataset":dataset,"strategy_id":strategy_id,"baseline_id":baseline_id,"metric":metric,
        "n_paired_prompts":len(pairs),"n_prompts_missing_pair":len(values)-len(pairs),
        "mean_strategy":sum(a for a,b in pairs)/len(pairs) if pairs else None,
        "mean_baseline":sum(b for a,b in pairs)/len(pairs) if pairs else None,
        "mean_paired_difference":test.mean_difference,"median_paired_difference":test.median_difference,
        "wilcoxon_w_plus":test.statistic_w_plus,"p_value_normal_approx":test.p_value,
        "rank_biserial":test.rank_biserial,"bootstrap_95_ci_mean_difference":list(test.ci95_mean_difference),
        "p_value_method":"tie-corrected normal approximation with continuity correction"}

def correct_comparison_family(comparisons: Iterable[Mapping[str,object]]) -> tuple[dict,...]:
    items=[dict(x) for x in comparisons]
    pvals={f"{x['dataset']}::{x['strategy_id']}::{x['metric']}":float(x["p_value_normal_approx"]) for x in items}
    adjusted=holm_correction(pvals)
    for x in items:
        key=f"{x['dataset']}::{x['strategy_id']}::{x['metric']}"
        x["p_value_holm"]=adjusted[key]; x["significant_holm_0_05"]=adjusted[key]<.05
    return tuple(items)

def write_evaluation_outputs(observations: Iterable[EvaluationObservation], output_dir: str | Path,
    comparisons: Iterable[Mapping[str,object]]=()) -> dict[str,str]:
    target=Path(output_dir); target.mkdir(parents=True,exist_ok=True)
    rows=tuple(observations); summary=aggregate_observations(rows)
    corrected=correct_comparison_family(comparisons)
    files={"summary_json":target/"strategy_summary.json","summary_csv":target/"strategy_summary.csv",
           "comparisons_json":target/"paired_comparisons.json","observations_jsonl":target/"observations.jsonl"}
    files["summary_json"].write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    files["comparisons_json"].write_text(json.dumps(corrected,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    with files["observations_jsonl"].open("w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(asdict(r),sort_keys=True,allow_nan=False)+"\n")
    fields=["dataset","strategy_id","n_trials","n_success","n_failed","failure_rate","mean_calls","mean_depth","mean_tokens","mean_latency_seconds"]
    with files["summary_csv"].open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader()
        for r in summary: writer.writerow({k:r[k] for k in fields})
    return {k:str(v) for k,v in files.items()}
