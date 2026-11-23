# E1 dataset source-intake audit

**Status:** source discovery completed; benchmark snapshot not approved or frozen  
**Audit date:** 2026-11-23  
**Scope:** source identity, available splits/formats, reference-data suitability, licensing/provenance risks, and unresolved selection decisions.  
**Boundary:** this document does not download, transform, select, approve, or synthesize benchmark examples.

## 1. Paper requirements

The paper's Table 12 defines the reference material and metric applicability:

| Dataset | Reference required by the paper | Metrics relevant to the source |
|---|---|---|
| BREAK | Gold decomposition into ordered steps | Reference agreement, redundancy, coupling, V2/V5 validity, stability, cost; no V1 coverage |
| StrategyQA | Annotated decomposition, evidence and answer | Implicit-step recall/reference agreement, answer accuracy/utility, process gain, stability, cost; no V1 coverage |
| TaskBench | Reference graph of sub-tasks | Sub-task and dependency agreement, V2/V5 validity, coupling, stability, cost; no V1 coverage |
| TravelPlanner | Annotated constraints and final-plan checks | Utility, solvability, process gain, V2/V5 validity, coverage only over annotated constraints, stability, cost; no reference decomposition |
| smart-administration | Requirement lists, hypotheses and practitioner-reviewed reference decompositions | All Table 9 metrics, including V1 coverage and hypothesis verdicts |

Section 8.1 states that 100 prompts are sampled from each public benchmark and that 60 smart-administration prompts are used. It does **not** specify the exact public prompt IDs, split names, sampling algorithm, random seed, or domain allocation. Those decisions must be explicitly preregistered; they must not be inferred from a convenient download or silently chosen as the first 100 rows.

## 2. Source audit

### 2.1 BREAK

- Paper source: https://allenai.github.io/Break/
- Official repository: https://github.com/allenai/Break
- Repository data artifact: `break_dataset/Break-dataset.zip`; GitHub API currently reports blob SHA `c5bd86bb9b7a2b6d9f8b18977da21dc4962dbef6` (this is a Git blob identifier, not a downloaded-file SHA-256).
- Official repository describes 83,978 human-annotated questions with QDMR decompositions. The QDMR format includes question ID, question text, decomposition, operators and split. The official repository reports QDMR train/dev/test counts of 44,321 / 7,760 / 8,069.
- The repository has an MIT LICENSE. However, BREAK aggregates questions sampled from ten underlying QA datasets. The Hugging Face `allenai/break_data` card currently labels the dataset license as **unknown** and its data documentation does not settle rights for every underlying source. The code-repository MIT license must not be treated as blanket clearance for all source questions.
- Candidate reference mapping: `question_text` -> `prompt_text`; retain `question_id`, `decomposition`, `operators`, and original split in `reference_data`/metadata.
- **Blocker:** source-level rights review and a decision on QDMR versus QDMR-high-level are required. Do not mix configurations in one 100-prompt sample without a preregistered rationale.

### 2.2 StrategyQA

- Paper source: https://allenai.org/data/strategyqa
- Official code repository: https://github.com/eladsegal/strategyqa
- The official code README points to the AllenAI dataset page for the dataset files. Its repository's `data/strategyqa/` directory currently contains `train.json` and `dev.json`; the README describes the train/dev split used for reproducing its baselines as an **unofficial 90%/10% random split of the official train set**. Do not mistake that local reproduction split for an official benchmark test split.
- The code repository has an MIT LICENSE; that alone does not establish the license/terms of the separately hosted dataset or all evidence passages.
- A Hugging Face mirror, `ChilleD/StrategyQA`, advertises MIT and exposes train/test splits (1,6xx and 687 rows in the inspected Hub structure). It is not the canonical AllenAI source and its provenance/equivalence to the exact paper dataset has not been established. It is **not approved as a substitute**.
- Candidate reference mapping: retain question, decomposition steps, evidence/facts, answer and source IDs as separate structured reference fields. The paper's Table 12 requires all three reference elements.
- **Blocker:** obtain the canonical data package and terms from the AllenAI dataset page/authors; establish the exact released version and whether an officially designated evaluation split exists. The AllenAI page returned an access-denied response during this audit, so its current download and license terms could not be independently inspected.

### 2.3 TaskBench

- Paper source: https://github.com/microsoft/JARVIS/tree/main/taskbench
- Official repository: https://github.com/microsoft/JARVIS/tree/main/taskbench
- Official Hugging Face dataset: https://huggingface.co/datasets/microsoft/Taskbench
- The inspected Hub structure exposes three test configurations: `huggingface` (about 7.5K rows), `multimedia` (about 5.6K), and `dailylifeapis` (about 4.3K), about 17.3K rows total. The Hub card declares MIT.
- The published schema contains IDs, sampled tool nodes/links, instruction, tool steps, tool nodes and tool links. The dataset README explains that the task solution is represented as a tool invocation graph with dependencies, which is consistent with the paper's reference-graph requirement.
- Candidate reference mapping: `instruction` -> `prompt_text`; preserve `tool_steps`, `tool_nodes`, `tool_links`, `sampled_nodes`, `sampled_links`, domain/config and row ID in structured `reference_data`.
- **Blocker:** the paper requires 100 prompts but does not specify domain proportions. The study must preregister whether it samples 100 from one domain or stratifies across all three, with exact counts and deterministic selection. Pin the exact Hub/repository revision and retain all graph fields.

### 2.4 TravelPlanner

- Paper source: https://osu-nlp-group.github.io/TravelPlanner/
- Official repository: https://github.com/OSU-NLP-Group/TravelPlanner
- Official dataset: https://huggingface.co/datasets/osunlp/TravelPlanner
- The official dataset card exposes 45 train query-plan pairs, 180 validation queries and 1,000 test queries. The inspected test schema contains `query`, `level`, constraints/context fields and `reference_information`. The official repository's 2026-11-18 update announces structured query annotations for all 1,000 test instances.
- The Hub dataset card declares CC-BY-4.0. The code repository has a separate MIT LICENSE; use the dataset-specific license and attribution requirements for the data.
- Candidate reference mapping: `query` -> `prompt_text`; preserve `reference_information`, constraints, level, and all query metadata in `reference_data`. Do not treat the reference plan as a gold decomposition: Table 12 explicitly says there is no reference decomposition.
- **Blocker:** pin the exact dataset revision and verify the structured annotation schema and attribution. If the study selects 100 from the 1,000 test instances, record the selection algorithm, seed, IDs and split in the preregistration.

### 2.5 smart-administration

- Paper status: “to be released with the code”; no public source URL is identified.
- Required size: 60 author-curated prompts across permits, social benefits, public procurement and civil-status records.
- Required references: requirement lists, hypotheses and reference decompositions written by the authors and reviewed by two practitioners.
- **Blocker:** the exact 60-prompt artifact, stable IDs, version, annotations, practitioner-review evidence, distribution/usage terms and source-file hash must be supplied. This audit found no public release and creates no substitute data.

## 3. Cross-dataset decisions that remain open

1. **Selection protocol:** the paper specifies sample sizes, not IDs/splits/seeds. Freeze a dataset-specific selection protocol before looking at model outputs. Record the full eligible population, split, filtering, deterministic seed (if randomized), selected IDs and exclusions.
2. **TaskBench domain balance:** decide and preregister the counts for `huggingface`, `multimedia`, and `dailylifeapis`; do not let file order decide.
3. **BREAK representation:** choose QDMR or QDMR-high-level and resolve underlying-source rights. Do not combine them without explicit protocol.
4. **StrategyQA canonicality:** do not substitute a third-party mirror for the canonical AllenAI package without a documented equivalence/provenance review.
5. **Licensing:** distinguish code repository licenses from dataset licenses and from licenses of upstream component sources. Record the actual dataset terms, attribution obligations, permitted research use and reviewer decision for each source.
6. **Schema preservation:** preserve dataset-native references. Conversion to the engine's JSONL wrapper must be lossless for all fields required by Table 12.
7. **smart-administration release:** do not freeze the four public datasets as a complete E1 snapshot while the fifth required dataset is absent.

## 4. Required immutable intake manifest

For every dataset, the operator must supply and the intake must record:

- canonical source URL and owner;
- exact upstream release/version and immutable revision or archive identifier;
- source file name, byte size and SHA-256;
- dataset license/terms URL, attribution and documented review status;
- original split and selection protocol (including seed and eligible population);
- exact selected example IDs and count;
- mapping specification from native fields to `example_id`, `prompt_text`, `split`, `metadata`, and dataset-native `reference_data`;
- row-level validation results and per-prompt/reference hashes.

The existing loader enforces exact counts (100/100/100/100/60), unique IDs, split consistency, structured reference data and a content-addressed snapshot. It does not independently prove upstream authenticity, license permission, or that the selection reproduces the paper's intended sample.

## 5. Current disposition

| Dataset | Source identified | Reference shape identified | Rights/provenance | Selection frozen | Intake |
|---|---|---|---|---|---|
| BREAK | Yes | Yes | **Open**: underlying sources and Hub license metadata | No | BLOCKED |
| StrategyQA | Canonical page identified; access not verified | Yes | **Open**: canonical data terms/package | No | BLOCKED |
| TaskBench | Yes | Yes | Hub declares MIT; exact revision/domain protocol open | No | BLOCKED |
| TravelPlanner | Yes | Yes | Hub declares CC-BY-4.0; exact revision/attribution open | No | BLOCKED |
| smart-administration | No public artifact found | Specified by paper | Author release/review evidence pending | No | BLOCKED |

**No benchmark rows were downloaded or transformed in this audit. No prompt sample was selected. No license was approved. No E1 run is authorized by this document.**
