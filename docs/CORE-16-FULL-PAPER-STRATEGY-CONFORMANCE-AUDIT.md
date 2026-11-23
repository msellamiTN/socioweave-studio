# CORE 16 — Full-Paper Strategy Conformance Audit (Initial Findings)

**Status:** audit findings recorded; remediation not yet implemented.  
**Audited repository base:** `d3fab0109d564004eef8d87bd2b9d6b3c7f61973`  
**Source:** *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Prompt Decomposition*, Table 4, Sections 5.1–5.4, and Algorithms 1–2.  
**Scope:** targeted source-to-code inspection of all thirteen blueprint branches, adapter defaults, conditional strategy paths and reported software acceptance boundaries. This is not yet a complete formal proof of conformance.

## 1. Executive result

The repository does contain concrete protocol blueprints and decision assembly for all thirteen atomic strategies. The earlier statement that only S12 was implemented was wrong.

However, the existence of a blueprint and a passing unit suite does not establish exact execution fidelity. This audit identifies three concrete conformance risks and two known control-flow limitations that must be addressed before claiming end-to-end paper conformance.

| Finding | Strategy | Severity | Evidence |
|---|---|---|---|
| F16-01: adapter can silently supply the full prompt to partitioned agents | S1, S12 | **Critical** | `strategy_adapter.py` creates full-prompt preliminary views and defaults to full prompt for every agent when no prompt-view factory is supplied; this bypasses the builder's explicit partition/facet requirement. |
| F16-02: mediation extra round is unconditional and default configuration exceeds Table 4 base budget | S11 | **High** | `strategy_protocols.py` emits one mediator summary and two revisions for every configured T round. At T=2 it produces 8 model steps / 5 stages, while Table 4's base procedure is 5 / 3. |
| F16-03: peer-review revision branch is compiled as unconditional | S8 | **High** | `strategy_protocols.py` always emits the author revision step. Paper Table 4 says revise only if editor decision is revise. |
| F16-04: Delphi early-stop behavior is not executed | S4 | **Known limitation** | Current blueprint expands the maximum T-round schedule; a candidate-aware stability controller is still absent, as CORE 12 documents. |
| F16-05: consensus deliberation early-stop behavior is not executed | S10 | **Known limitation** | Current blueprint emits all nT participant turns and moderator closure; the paper permits stopping after a stable full turn or moderator no-objection. |

## 2. Source-grounded findings

### F16-01 — Partitioned strategies can receive an unpartitioned prompt

**Paper semantics**

- S1: coordinator splits the prompt by domain; each specialist receives and refines its assigned part (Section 5.1.1; Fig. 3a; Table 4).
- S12: each expert receives one facet only; the integrator receives the partial lists and assembles them (Section 5.1.2; Fig. 3b; Table 4).
- Algorithm 1 states that the default prompt view is the whole prompt, but partitioned strategies use the assigned `Π_i` or `Φ_i`.

**Implementation observation**

`strategy_protocols.py` correctly rejects a missing explicit S12 `prompt_views` mapping and has a partition placeholder for direct S1 blueprint construction. However, `ConcreteStrategyAdapter.__call__` creates preliminary S1/S12 views using the full prompt and, absent `prompt_view_factory`, constructs a mapping that gives `prompt.text` to every agent. It then passes that mapping into the blueprint builder.

Therefore, the adapter's default execution path does not enforce the partition/facet semantics. A caller may believe it is running S1/S12 while all agents actually receive the complete prompt.

**Required correction**

- Require an explicit partition/facet provider for S1 and S12.
- Validate that the specialist/expert views are proper declared subsets or structured facet objects derived from the frozen extraction.
- Ensure the integrator receives the full prompt plus all expert outputs only where the paper's protocol allows it.
- Add negative tests proving the adapter refuses S1/S12 execution without partition/facet inputs.
- Add leakage tests proving no specialist/expert receives another partition/facet.

### F16-02 — S11 mediation rounds are not conditionally controlled

**Paper semantics**

Table 4 gives S11 as two parallel drafts, one mediator summary, two parallel revisions: five calls, three stages. Section 5.4.2 says one additional round is used if the revisions still differ, and a maximum number of rounds must be set because the dialogue may fail to terminate.

**Implementation observation**

The blueprint creates the two initial drafts and then loops from 1 through T, unconditionally adding a mediator summary and two revisions per iteration. It exempts S11 from the Table 4 call-count assertion. At the default T=2, the resulting blueprint has eight calls and five stages, even if the first revisions have already converged.

**Required correction**

- Represent the Table 4 five-call/three-stage procedure as the base protocol.
- Treat any further negotiation as a conditional bounded extension, not an unconditional repeat.
- Require structured convergence evidence (the paper's distance condition) before scheduling another round.
- Record base calls, extension calls and actual calls separately.
- Add tests for immediate convergence (5 calls), one additional round (8 calls), and maximum-round exhaustion.
- Do not change the catalogue's Table 4 base formula.

### F16-03 — S8 peer-review branch is unconditional

**Paper semantics**

Table 4: the editor judges the draft and reviews; **if** the editor returns `revise`, the author revises. The paper's call formula k+3 is the revise-path budget.

**Implementation observation**

The current blueprint always appends an author revision step. The editor's typed decision is decoded later, but the protocol schedule itself does not branch on it. This means an accept outcome cannot terminate after the editor decision; the schedule still expects a revision call.

**Required correction**

- Introduce an explicit conditional protocol controller for the editor's typed `accept` / `revise` result.
- For `accept`, terminate with the original draft and account for k+2 calls / depth 3.
- For `revise`, execute the revision and account for k+3 calls / depth 4.
- Verify that the paper's formula is documented as the maximum revise-path budget rather than a mandatory call count.
- Add tests for both branches and ensure no hidden extra call.

## 3. Known early-stop limitations

### S4 — Delphi

The paper says rounds stop when drafts no longer change. Current code builds a bounded T-round maximum schedule, but does not stop early based on candidate-aware stability. This is already disclosed in CORE 12 and must remain a visible limitation until a structured controller is implemented.

### S10 — Consensus deliberation

The paper stops after a full turn leaves the shared draft stable, or at T. Current code builds all nT sequential participant revisions followed by moderator judgement. A structured full-turn stability/no-objection controller is required to reproduce early stopping. This is already disclosed in CORE 12.

## 4. Existing evidence and its limits

- CORE 12 reports 230 tests passed, 0 failed, 0 skipped on code commit `3f846916f5074440961734b51ae47cb48b5d4f76`.
- CORE 14 reports 257 tests passed, 0 failed, 0 skipped on code commit `db3b9f963a82680c3a4ef93283fdc2e9b57b087f`.
- CORE 15 reports 259 tests passed, 0 failed, 0 skipped on code commit `5e3b4df53bb166f855cee648912d8689d30819e4`.

These reports establish historical software test results on their stated commits. They do not establish that the current main commit was tested end-to-end, that all branches match paper semantics, or that any strategy improves decomposition quality. No E1–E9 scientific effectiveness result is claimed.

## 5. Remediation order

1. Fix F16-01 first: partition/facet semantics are foundational and currently bypassable through the default adapter path.
2. Fix F16-03: make S8's editor decision a real control-flow branch.
3. Fix F16-02: separate S11's base procedure from conditional additional negotiation rounds.
4. Implement structured early-stop controllers for S4 and S10.
5. Re-run all strategy protocol, adapter, decision, runtime and orchestration tests on one exact commit.
6. Reconcile the resulting traces against the paper's call/depth formulas and branch conditions.
7. Only then update the conformance status. Scientific evaluation remains a separate gate.

## 6. Non-claims

This audit does not claim that all thirteen strategies are fully paper-conformant, that the listed findings are the only possible defects, or that software tests establish strategy effectiveness. It records concrete, source-traceable discrepancies found during the initial end-to-end review.
