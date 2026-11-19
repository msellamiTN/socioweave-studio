# Table 12 dataset-specific metric applicability

This registry transcribes Table 12 of *Societies of Decomposers*. It keeps
metric applicability separate from metric computation.

| Dataset | Applicable metrics and restrictions |
|---|---|
| BREAK | Reference agreement, redundancy, coupling, validity (V2, V5), stability, cost. No coverage: no requirement list. |
| StrategyQA | Reference agreement (recall of implicit steps), utility (answer accuracy), process gain, stability, cost. No coverage. |
| TaskBench | Reference agreement (sub-tasks and dependencies), validity (V2, V5), coupling, stability, cost. No coverage. |
| TravelPlanner | Utility, solvability, process gain, validity (V2, V5), coverage restricted to annotated constraints, stability, cost. No reference decomposition. |
| smart-administration | All Table 9 metrics, including coverage (V1) and hypothesis verdicts. |

The profile prevents a missing reference or requirement universe from being
silently converted into a zero-valued metric. It does not infer that source
datasets or annotation files are present; the experiment must still record
the exact dataset snapshot and provenance.

The registry records the paper's validity components explicitly. On datasets
without a complete requirement list, the profile does not authorize reporting
full V1 coverage as part of validity; it records only V2 and V5 as applicable.
