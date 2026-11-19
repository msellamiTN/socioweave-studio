# E1 — overall strategy and baseline comparison

## Source protocol

E1 asks how the strategies compare overall. It varies strategy and baseline
across all five datasets and reports applicable Table 9 metrics. The stated
expectation is that strategies with independent drafts lead on coverage,
while baselines lead on cost.

The protocol specifies thirteen Table 4 strategies and six baselines:
single-agent plan-and-solve, self-refinement, self-consistency, decomposer
plus separate evaluator, multi-agent debate, and nominal multi-agent baseline.

It specifies 100 prompts from each public benchmark and 60
smart-administration prompts; heterogeneous MA/MB/MC agents and a homogeneous
MA-only variant; fixed executor ME; n=3, k=3, T<=2; temperatures 0.7 for
drafting, 0.2 for criticism/review, and 0 for ranking/voting/merging/judging;
1,024 decomposition tokens and 512 other-call tokens; five seeds; baseline
call-budget matching; q=3 extractors with union and 20% human prompt audit;
two annotators on 10% of decompositions with Cohen's kappa; paired-prompt
Wilcoxon signed-rank and Holm correction at alpha=0.05.

## Manifest contract

Each condition records dataset, method, model mode, seed, exact frozen prompt
IDs and call budget. Every baseline row names the strategy whose budget it
matches. Validation checks the full dataset × strategy × baseline × mode ×
seed design. Metric obligations are taken from the Table 12 registry.

Prompt IDs are caller-supplied from frozen, provenance-recorded snapshots.
The validator does not download, invent, or sample benchmark prompts.

## Not yet implemented or evidenced

This is a design/manifest gate, not E1 execution. It does not provide the
benchmark snapshots, smart-administration annotations, prompt interpretation
records, provider credentials, executor ME, model version/access dates,
human ratings, actual LLM calls or empirical results. The adaptive campaign
is not a substitute for direct execution of every strategy and baseline.
