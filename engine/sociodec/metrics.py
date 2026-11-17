"""Paper-aligned metric computation and paired statistical analysis."""
from __future__ import annotations
import math, random
from dataclasses import dataclass
from statistics import median
from typing import Hashable, Iterable, Mapping, Sequence

@dataclass(frozen=True, slots=True)
class PRF:
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int

def precision_recall_f1(predicted: Iterable[Hashable], reference: Iterable[Hashable]) -> PRF:
    pred, gold = set(predicted), set(reference)
    tp = len(pred & gold); fp = len(pred - gold); fn = len(gold - pred)
    p = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    r = tp / len(gold) if gold else (1.0 if not pred else 0.0)
    return PRF(p, r, 2*p*r/(p+r) if p+r else 0.0, tp, fp, fn)

def span_entailment_rate(assessments: Sequence[bool]) -> float:
    if not assessments: raise ValueError("span entailment requires annotations")
    if any(type(x) is not bool for x in assessments): raise TypeError("assessments must be booleans")
    return sum(assessments) / len(assessments)

@dataclass(frozen=True, slots=True)
class DecompositionMetrics:
    validity: bool
    coverage: float
    redundancy: float
    coupling: float
    depth: int | None
    solvability: float | None
    utility: float | None

def decomposition_metrics(*, requirements: Iterable[Hashable], covered_requirements: Iterable[Hashable],
    subproblem_signatures: Sequence[Hashable], edges: Iterable[tuple[Hashable, Hashable]],
    acyclic: bool, composition_complete: bool, subproblem_solved: Sequence[bool] | None = None,
    utility: float | None = None, depth: int | None = None) -> DecompositionMetrics:
    req, covered = set(requirements), set(covered_requirements)
    if not req: raise ValueError("coverage is undefined for an empty requirement set")
    sigs = list(subproblem_signatures)
    if not sigs: raise ValueError("decomposition must contain a subproblem")
    if type(acyclic) is not bool or type(composition_complete) is not bool:
        raise TypeError("acyclic and composition_complete must be booleans")
    counts = {}
    for sig in sigs: counts[sig] = counts.get(sig, 0) + 1
    redundancy = sum(counts[sig] > 1 for sig in sigs) / len(sigs)
    edge_list = list(edges)
    if any(a == b for a,b in edge_list): acyclic = False
    coupling = len(set(edge_list)) / len(sigs)
    if depth is not None and (isinstance(depth,bool) or not isinstance(depth,int) or depth < 1):
        raise ValueError("depth must be a positive integer")
    solvability = None
    if subproblem_solved is not None:
        if not subproblem_solved or any(type(x) is not bool for x in subproblem_solved):
            raise ValueError("subproblem_solved must be non-empty booleans")
        solvability = sum(subproblem_solved) / len(subproblem_solved)
    if utility is not None and (isinstance(utility,bool) or not isinstance(utility,(int,float))
        or not math.isfinite(utility) or not 0 <= utility <= 1):
        raise ValueError("utility must be finite and in [0,1]")
    coverage = len(req & covered) / len(req)
    return DecompositionMetrics(acyclic and req.issubset(covered) and composition_complete,
        coverage, redundancy, coupling, depth, solvability, float(utility) if utility is not None else None)

def process_gain(strategy_utility: float, baseline_utility: float) -> float:
    for name,v in (("strategy_utility",strategy_utility),("baseline_utility",baseline_utility)):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 1:
            raise ValueError(f"{name} must be finite and in [0,1]")
    return float(strategy_utility-baseline_utility)

@dataclass(frozen=True, slots=True)
class PairedTestResult:
    n_pairs: int
    statistic_w_plus: float
    p_value: float
    rank_biserial: float
    median_difference: float
    mean_difference: float
    ci95_mean_difference: tuple[float,float]

def _ranks(values):
    order=sorted(range(len(values)),key=lambda i:values[i]); ranks=[0.0]*len(values); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]: j+=1
        rank=(i+1+j)/2
        for k in range(i,j): ranks[order[k]]=rank
        i=j
    return ranks

def _normal_cdf(z): return 0.5*(1+math.erf(z/math.sqrt(2)))

def _bootstrap(values, seed, samples):
    rng=random.Random(seed); n=len(values)
    means=sorted(sum(values[rng.randrange(n)] for _ in range(n))/n for _ in range(samples))
    return means[int(.025*(samples-1))],means[int(.975*(samples-1))]

def wilcoxon_paired(x: Sequence[float], y: Sequence[float], *, seed: int=0,
                    bootstrap_samples: int=4000) -> PairedTestResult:
    """Two-sided tie-corrected normal approximation to paired Wilcoxon signed-rank."""
    if len(x)!=len(y) or not x: raise ValueError("paired samples must have equal non-zero length")
    if bootstrap_samples<100: raise ValueError("bootstrap_samples must be >=100")
    diffs=[]
    for a,b in zip(x,y):
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (a,b)):
            raise ValueError("observations must be finite numbers")
        if a!=b: diffs.append(float(a-b))
    if not diffs: return PairedTestResult(0,0.0,1.0,0.0,0.0,0.0,(0.0,0.0))
    absvals=[abs(d) for d in diffs]; ranks=_ranks(absvals)
    wp=sum(r for r,d in zip(ranks,diffs) if d>0); wm=sum(r for r,d in zip(ranks,diffs) if d<0)
    n=len(diffs); ties={}
    for v in absvals: ties[v]=ties.get(v,0)+1
    var=(n*(n+1)*(2*n+1)-sum(t**3-t for t in ties.values())/2)/24
    mean=n*(n+1)/4
    z=max(0.0,abs(wp-mean)-.5)/math.sqrt(var) if var>0 else 0.0
    p=min(1.0,2*(1-_normal_cdf(z)))
    total=wp+wm
    return PairedTestResult(n,wp,p,(wp-wm)/total if total else 0.0,
        median(diffs),sum(diffs)/n,_bootstrap(diffs,seed,bootstrap_samples))

def holm_correction(p_values: Mapping[str,float]) -> dict[str,float]:
    if not p_values: return {}
    for k,p in p_values.items():
        if not isinstance(k,str) or not k or isinstance(p,bool) or not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1:
            raise ValueError("p-values must be named finite numbers in [0,1]")
    order=sorted(p_values,key=lambda k:p_values[k]); result={}; running=0.0; m=len(order)
    for i,k in enumerate(order):
        running=max(running,min(1.0,(m-i)*float(p_values[k]))); result[k]=running
    return {k:result[k] for k in p_values}

def confidence_interval(values: Sequence[float], *, seed: int=0, bootstrap_samples: int=4000):
    if not values or bootstrap_samples<100: raise ValueError("non-empty values and >=100 samples required")
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError("values must be finite numbers")
    return _bootstrap([float(v) for v in values],seed,bootstrap_samples)
