# Core 09 — Decision Operators and Strategy Catalogue

**Status:** PASS — decision operators and catalogue software acceptance on commit `724ab490169c453f09e18765e814014ae386f950`.  
**Scientific source:** Table 4 (thirteen strategies and protocol costs), Table 5 (design-space matrix), Section 5 (strategy mechanisms), Definition 10 and Section 6.2 (decision-rule properties).

## 1. Decision operators

The paper's seven decision rules are not interchangeable.

| Rule | Paper meaning | Software realization |
|---|---|---|
| Authority | A designated judge/decision-maker selects a candidate | `authority` accepts the judge's selected candidate ID and rationale; it cannot invent a candidate |
| Rank-sum | Each member ranks every whole draft; choose the minimum sum of ranks | `rank_sum` validates complete rankings and selects the minimum total |
| Majority | Each agent votes on every subproblem in the pooled list; retain items with strictly more than (n/2) votes | `majority` applies strict majority to canonical subproblem identities |
| Union | Combine the subproblem/dependency sets of candidates | `union` merges equivalent subproblems and combines edges and deliverable contributors |
| Synthesis | A synthesizer combines the structures of candidates | `synthesis` records an explicit synthesizer-produced decomposition and rationale |
| Compromise | A mediator negotiates a trade-off between two candidates | `compromise` requires exactly two candidates and records an explicit negotiated decomposition |
| Consensus | The meaning depends on the strategy protocol | Delphi uses the medoid of latest drafts; S10 uses sequential shared-draft deliberation and its stability/no-objection stopping rule |

### Distance and medoid

The medoid uses the paper's distance:

    dist(D,D') = 1 - 1/2 ( J([S],[S']) + J([E],[E']) )

The equivalence classes are represented by canonical subproblem and directed-edge signatures. J(empty, empty)=1. The candidate with the minimum sum of distances to all other candidates is returned.

### Important limitations and conventions

- The paper does not prescribe tie-breaking for rank-sum or medoid. The implementation uses the lexicographically smallest candidate identifier and records that convention in the result.
- The union preserves combined candidate edges even when they create a cycle. The common structural validator, not the union operator, detects it. This is consistent with the paper's warning that union does not preserve acyclicity.
- Majority is subproblem-level, not whole-draft selection. Its strict threshold is (>n/2), so an exact tie is not retained.
- Synthesis and compromise are semantic agent operations. A deterministic generic merge would silently invent policy; therefore this Core accepts their explicit agent-produced result instead.
- Authority similarly records a judge's choice rather than pretending a software rule can replace the judge.
- The medoid is the Delphi representative. S10 consensus deliberation is not reduced to a medoid.

## 2. Thirteen strategies from Table 4

The catalogue records each strategy's paper name, decision rule, agent pattern, visibility pattern, protocol summary, call formula and depth formula.

| ID | Strategy | Decision rule | Calls | Depth |
|---|---|---|---:|---:|
| S1 | Division of labour | Authority | (n+2) | 3 |
| S12 | Jigsaw | Union | (n+1) | 2 |
| S2 | Brainstorming | Union | (n+1) | 2 |
| S3 | Nominal group technique | Rank-sum | (2n) | 2 |
| S4 | Delphi | Consensus (medoid) | (T(n+1)) | (2T) |
| S9 | Majority vote | Majority | (2n) | 2 |
| S5 | Devil's advocate | Authority | 4 | 4 |
| S6 | Dialectical inquiry | Synthesis | 3 | 3 |
| S8 | Peer review | Authority | (k+3) | 4 |
| S13 | Role reversal | Authority | 4 | 4 |
| S7 | Adversarial procedure | Authority | 5 | 3 |
| S11 | Mediation | Compromise | 5 | 3 |
| S10 | Consensus deliberation | Consensus (shared draft) | (nT+1) | (nT+1) |

Default illustrative cost check (n=3,k=3,T=2) is tested against Table 4. Extraction calls (q) and the optional one repair call are excluded from these catalogue costs, as in the paper.

## 3. Five unexplored matrix cells

The five Table 5 cells are represented separately as candidates:
- C1 Objection ballot;
- C2 Patch merge;
- C3 Redundant jigsaw;
- C4 Interface negotiation;
- C5 Chaired deliberation.

They remain explicitly marked **candidate — not an established strategy in the paper**. They are not included in the thirteen-strategy catalogue and no effectiveness claim is made for them.

## 4. Scope boundary

This Core supplies pure decision operators and a strategy metadata catalogue. It does not yet provide complete end-to-end protocol implementations for all thirteen strategies, implement model-mediated judges/synthesizers/mediators, or select a strategy adaptively. The runtime and selector are separate units.

The formal results in Section 6.2 remain the paper's propositions; passing software tests does not constitute a new proof or experimental validation.

## 5. Acceptance evidence

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Result:** 148 passed in 0.21s; 0 failed; 0 skipped.  
**Exact tested commit:** `724ab490169c453f09e18765e814014ae386f950`.  
**CI:** [Workflow run 44188545307](https://github.com/msellamiTN/socioweave-studio/actions/runs/44188545307).  
See [CORE-09-TEST-REPORT.md](CORE-09-TEST-REPORT.md) for detailed scope and limitations.
