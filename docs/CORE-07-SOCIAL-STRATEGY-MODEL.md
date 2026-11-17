# Core 07 — Social Strategy Model

**Status:** Implementation and full-suite acceptance pending.  
**Scientific source:** Definitions 9 and 10 and the accompanying strategy measures.

## 1. Paper contract

Definition 9 defines an agent (a=(m_a,c_a,mu_a)): underlying model, received context and optional memory. Agents are homogeneous iff they share the same underlying model.

Definition 10 defines a social strategy:

    sigma = (A, R, alpha, V, pi, omega)

- A: agents.
- R: roles.
- alpha: agent-to-role assignment at each round.
- V: per-round visibility relations; (a,b) means a sees b's outputs.
- eta: anonymity flag controlling whether author names are visible.
- pi: ordered protocol steps (agent, action, input).
- omega: decision rule.

The paper's roles are decomposer, critic, defender, judge, coordinator, aggregator, facilitator, mediator, moderator and voter. Actions are split, draft, critique, defend, revise, rank, vote, summarise, compare, merge, judge and check. Decision rules are authority, rank-sum, majority, union, synthesis, compromise and consensus.

The paper defines calls(sigma) as the number of protocol steps that invoke a model and depth(sigma) as the number of sequential stages when independent steps run in parallel. Independence holds when first-round agents do not see other agents' drafts. Role stability means alpha does not depend on the round.

## 2. Software representation

The model records stable agent identifiers, model identity, context and optional memory; role assignments for every agent and round; visibility relations; protocol action/input/stage; model-call accounting; anonymity; and decision rule.

The explicit `stage` and `invokes_model` fields are software representation choices that make the paper's calls/depth quantities computable. They are not extra social-theory claims.

## 3. Scope boundary

This Core models a strategy specification. It does not execute agents, implement decision rules, select a strategy for a prompt or assert that a social procedure improves quality. Strategy execution and adaptive selection are later units.

## 4. Acceptance

From `engine/`:

    python -m pip install -e '.[dev]'
    python -m pytest -q

Acceptance requires the complete integrated suite, including model invariants and boundary tests, to pass on the exact final commit.
