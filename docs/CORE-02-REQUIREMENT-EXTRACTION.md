# Core 02 — Requirement Extraction

**Status:** PASS — software acceptance on commit `4b4d0b29eb1f6b963662e9f115e67a4db65fd851`; scientific extraction quality not yet evaluated.
**Scientific source:** Section 3.2, Definition 3 and Equation (1) of *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Prompt Decomposition*.

## 1. Paper contract

An extractor maps the original prompt text x to typed and labelled atomic requirements with source spans. The paper aggregates q extractors:

    (R_hat, H_hat, N_hat) = dedup(union from j=1 to q of e_j(x)).

- R_hat: explicit requirements whose source span is found in x.
- H_hat: hypotheses about implicit requirements; these are not treated as facts.
- N_hat: entities identified in the prompt.
- Explicit requirements have a type (target, constraint, deliverable), domain label and source span.
- The extractor flags requirements admitting multiple readings and pairs of requirements that appear to conflict.

The paper states that hypotheses are retained and passed to every strategy for confirmation or rejection. Each hypothesis must eventually carry a verdict. A confirmed hypothesis joins the requirement set and must then be covered.

## 2. Implementation

ProviderRequirementExtractor invokes the provider-neutral LLM interface. It requests JSON and parses the response into typed domain objects. Each explicit requirement must include a zero-based, half-open character interval into the exact prompt text.

aggregate_extractions performs union and deduplication. It retains extractor provenance for each merged requirement and hypothesis. Entities, ambiguity flags and conflicts are also merged without discarding their distinct categories.

## 3. Deduplication policy

The paper relies on an equivalence relation for deduplication but does not prescribe a concrete semantic matcher. The initial implementation therefore uses a conservative default: normalised exact statement match, with matching requirement type and domain. A custom equivalence matcher can be injected when a reviewed semantic matcher is available.

This is an implementation choice, not a claim that normalised string equality is the paper's definitive equivalence relation. False merges and missed semantic duplicates remain possible and must be measured.

## 4. Scientific safeguards

1. Hypotheses remain separate from explicit requirements until adjudicated.
2. A source span is checked for valid bounds and non-empty text; semantic support of the statement by the span is not automatically proven.
3. The extractor is instructed not to invent source spans. Structural validation catches invalid offsets, but cannot fully verify semantic alignment.
4. A union of extractors is not a guarantee of complete recall: all extractors may miss the same requirement.
5. Multiple LLM calls are not assumed independent, particularly when they share model families or providers.
6. Ambiguity and conflict flags are provisional extraction judgements, not formal proofs of ambiguity or inconsistency.

## 5. API example

    from sociodec.extraction import ProviderRequirementExtractor, run_extractors
    from sociodec.providers import HuggingFaceLocalProvider, OpenAICompatibleProvider

    local = HuggingFaceLocalProvider(model_id='Qwen/Qwen2.5-1.5B-Instruct')
    api = OpenAICompatibleProvider(
        provider_name='hf-inference',
        model='Qwen/Qwen2.5-7B-Instruct:fastest',
        base_url='https://router.huggingface.co/v1',
        api_key_env='HF_TOKEN',
    )
    extractors = [
        ProviderRequirementExtractor(local, 'local-1'),
        ProviderRequirementExtractor(api, 'api-1'),
    ]
    result = run_extractors(prompt_text, extractors)
    print(len(result.R_hat), len(result.H_hat), len(result.N_hat))

The two calls illustrate heterogeneous provider configuration. They do not establish statistical independence. The paper's experimental configuration and model-family assignments must govern formal experiments.

## 6. Acceptance tests

Run from engine/:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Recorded result:** 55 passed in 0.07s; 0 failed; 0 skipped.
**Exact tested commit:** `4b4d0b29eb1f6b963662e9f115e67a4db65fd851`.
**CI evidence:** [Workflow run 44181085215](https://github.com/msellamiTN/socioweave-studio/actions/runs/44181085215).
See [CORE-02-TEST-REPORT.md](CORE-02-TEST-REPORT.md) for environment, suite scope and limitations.

The software PASS is limited to the implementation at the tested commit. Documentation updates are tested by the repository workflow as well; those later CI runs are tracked separately and do not retroactively change the tested source-code commit.

## 7. Scientific evaluation still required

No benchmark-based extraction quality result is claimed. Precision, recall, F1, span entailment, hypothesis quality, ambiguity/conflict precision and recall, extractor correlation and robustness require human-annotated evaluation under the paper's protocol. T4 fit and throughput also remain unverified.

## 8. Next dependency

Core 03 will formalise decomposition objects D=(S,E,kappa), including sub-problems, dependency edges and the deliverable composition map. Core 04 will implement validity checks with a strict distinction between structural checks and execution-dependent checks.