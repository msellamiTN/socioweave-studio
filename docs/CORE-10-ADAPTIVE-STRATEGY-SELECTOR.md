# Core 10 — Adaptive Strategy Selector

**Status:** IMPLEMENTED — acceptance pending full CI.  
**Scientific source:** Section 7.3, Algorithm 2, Table 8; Section 7.5 for typed strategy combinations.

## 1. Paper contract

The selector follows diagnose → select → escalate.

1. Reuse one multi-extractor result and account for its q extraction calls.
2. Obtain two isolated initial drafts. Use two model families when available; otherwise use two different decomposition principles. The caller must enforce isolation.
3. Estimate nc, nd, u, flags amb, conf, open, val, just, content gap gapS, structural gap gapE, mean coupling rho_hat, deployment high, and available model families fam.
4. Form the checked union of the two initial drafts.
5. Apply the first matching rule in each of the three stages of Table 8, without repeating a strategy.
6. Seed the first author of the next strategy with the preceding decomposition.
7. Stop when the budget cannot cover the next strategy plus one possible repair call; report all unrun items.
8. Escalate based on failures, retaining the best result under the paper's lexicographic order: fewest failures, highest coverage, lowest redundancy, lowest coupling.

Defaults are epsilon = 0.1 and theta_c = 5.

## 2. Table 8 decision list implemented

| Stage | Rule | Condition | Selection |
|---|---|---|---|
| Rule 0 | 0 | dist(Da,Db) <= epsilon; u=0; no flag; not high | checked union; empty chain |
| Reading | 1.1 | ambiguity and stakeholder values | S10 Consensus Deliberation |
| Reading | 1.2 | ambiguity | S4 Delphi |
| Production | 2.1 | open prompt | C8: S2 then S8 |
| Production | 2.2 | gapS <= epsilon < gapE and high | S7 Adversarial Procedure |
| Production | 2.3 | gapS <= epsilon < gapE | S6 Dialectical Inquiry |
| Production | 2.4 | epsilon < dist(Da,Db) <= 2epsilon and fam >= 2 | S9 Majority Vote |
| Production | 2.5 | nc >= theta_c or u > 0 | S12 Jigsaw |
| Production | 2.6 | nd >= 3 and rho_hat <= 1 | S1 Division of Labour |
| Production | 2.7 | gapS > 2epsilon and fam >= 2 | S3 Nominal Group Technique |
| Scrutiny | 3.1 | conflict | S11 Mediation |
| Scrutiny | 3.2 | high | S8 Peer Review |
| Scrutiny | 3.3 | justified plan and fam >= 2 | S13 Role Reversal |
| Scrutiny | 3.4 | no other rule matched and Rule 0 does not hold | S5 Devil's Advocate |

The first matching rule in each stage fires. The same strategy is not repeated in a chain. S5 is the stage-3 default only when no earlier stage-3 rule matched and Rule 0 does not hold.

## 3. Escalation

- Uncovered requirement or unresolved hypothesis: Jigsaw followed by Devil's Advocate (a paper-described combination).
- Cycle or composition failure: S8 Peer Review.
- Other failures, or high stakes without a remaining failure: C1 full pipeline (Nominal Group → Dialectical Inquiry → Delphi → Adversarial Procedure), composed by Algorithm 3 rather than four complete sequential strategy runs; for three agents and one revision it costs nine calls.
- The paper's combination labels C1/C2 are kept distinct from the five candidate design-space cells C1–C5 in the software model. They are not the same identifiers.

## 4. Software boundary and engineering conventions

- PromptFeatures validates ranges and types. diagnose_features derives extraction counts, ambiguity/conflict flags, Jaccard gaps, mean coupling and distance from supplied drafts.
- open_prompt, stakeholder_values and justified_plan are caller-supplied semantic flags: extraction schema currently does not infer them.
- Initial-draft isolation, model-family selection, LLM invocation, seed delivery, Algorithm 1 execution, dynamic failure refresh and best-result comparison remain orchestration responsibilities; this Core supplies a deterministic decision-list planner.
- Strategy costs use Table 4 formulas. Because the runtime does not yet expose seed-adjusted per-strategy call accounting, budget estimates conservatively use full catalogue costs plus one reserved repair call. This is not an exact measured call count for seeded runs.
- Escalation is planned from the supplied failure snapshot. An execution orchestrator must refresh failures after each strategy and re-run the escalation decision to reproduce the full dynamic loop of Algorithm 2.
- The planner does not choose any candidate C1–C5. C8 and the two escalation combinations are paper-described combinations, not candidate strategies.
- No learned policy is introduced; the paper says learning may replace the transparent list only after experiments provide feature/outcome pairs.

## 5. Tests

Run from engine/:

    python -m pip install -e ".[dev]"
    python -m pytest -q

Acceptance report is published separately after CI on the final commit.
