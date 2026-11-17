# Core 03 — Decomposition Model

**Status:** PASS — software model acceptance on commit `d8160ed2f2211c964d51a4ef5ec08beecac7bd0a`.  
**Scientific source:** Definitions 4 and 5 in *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Prompt Decomposition*.

## 1. Formal contract

Definition 4 defines a subproblem as:

    s = (q_s, ins, outs, C_s)

where q_s is a question, ins the inputs it needs, outs the output it must produce, and C_s is the subset of prompt constraints that applies locally.

Definition 5 defines:

    D = (S, E, κ)

- S is the set of subproblems.
- E ⊆ S × S is the set of directed dependencies. (s_i, s_j) ∈ E exactly when the inputs of s_j use the output of s_i.
- κ : O → 2^S maps each expected deliverable o to the set of subproblems whose outputs form o.
- Each subproblem addresses cov(s) ⊆ R(P), and cov(D) is the union of cov(s) over all s ∈ S.

## 2. Software representation

- `Subproblem`: identifier, question, required input labels, produced output label, local constraints and covered explicit requirements.
- `Dependency`: source and target subproblem identifiers. Direction is source → target, meaning the target consumes the source output.
- `DeliverableComposition`: one deliverable key and its contributing subproblem identifiers.
- `Decomposition`: immutable tuples representing S, E and κ, with accessors for paper notation and union coverage.

The representation uses stable identifiers for graph references. Requirement coverage stores the corresponding Core 01 `Requirement` values, preserving their type, domain and source-span metadata. Local constraints reuse Core 01 `Constraint` values.

Prompt-relative validation requires κ to have exactly the declared deliverable keys, reflecting the total function κ : O → 2^S. It allows an empty contributor set for an individual deliverable because non-emptiness is a V5 validity condition checked by Core 04.

## 3. Representation integrity versus validity

This Core checks local model integrity:
- required text and identifiers are non-empty;
- identifiers, edges, mapping keys and repeated members are unique;
- dependency endpoints and composition contributors refer to existing subproblems;
- prompt-relative validation ensures local constraints belong to C and coverage entries belong to the supplied R(P);
- composition keys are exactly the declared prompt deliverables.

This Core intentionally does **not** enforce:
- V1: complete requirement coverage;
- V2: acyclicity;
- V3: solvability by executor M;
- V4: faithfulness of the composed answer to hard constraints;
- V5: non-empty contributors for every deliverable and sink contribution.

In particular, self-edges/cycles and empty κ(o) values remain representable so that Core 04 can report validity violations rather than having the data model erase or conflate them. A syntactically valid representation is not necessarily a valid decomposition.

The model does not infer semantic dependency edges from natural-language input/output descriptions. Edge semantics are supplied by the decomposition producer; semantic verification belongs to a later validation/evaluation layer.

## 4. Acceptance evidence

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

**Result:** 75 passed in 0.12s; 0 failed; 0 skipped.  
**Exact tested commit:** `d8160ed2f2211c964d51a4ef5ec08beecac7bd0a`.  
**CI:** [Workflow run 44185214955](https://github.com/msellamiTN/socioweave-studio/actions/runs/44185214955).  
See [CORE-03-TEST-REPORT.md](CORE-03-TEST-REPORT.md) for detailed scope and limitations.

This acceptance is software-level only; it is not evidence of LLM decomposition quality or executor-level correctness.
