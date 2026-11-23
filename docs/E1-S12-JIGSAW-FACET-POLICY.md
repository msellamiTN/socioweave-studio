# E1 S12 — Versioned Jigsaw facet policy

**Policy ID:** `paper-s12-3facet-v1`  
**Policy SHA-256:** computed from `PAPER_S12_POLICY_MANIFEST` in `engine/sociodec/jigsaw.py`  
**Implementation:** `PaperJigsawPromptViewFactory`

## 1. Paper basis

This implementation follows three distinct parts of the paper:

- **Table 4 (S12):** three facet experts, one integrator; each expert sees one facet; the integrator merges the partial decompositions by union.
- **Figure 3(b):** the illustrated facets are goals, constraints and actors.
- **Section 5.1.2:** requirement facets are derived from the extracted requirement types; the actor facet contains the extracted entity set and requirements that mention each entity; an empty facet is dropped and costs no call.

The paper's requirement type set is `T = {target, constraint, deliverable}`. It does not spell out a complete executable mapping from those three types to the three illustrated facets. The grouping below is therefore an explicit, versioned operationalization of the paper's example, not a claim that the exact grouping is prescribed verbatim.

## 2. Frozen operational mapping

| Expert | Facet | Source content |
|---|---|---|
| `expert-1` | Goals and deliverables | Requirements of type `target` or `deliverable` |
| `expert-2` | Constraints | Requirements of type `constraint` |
| `expert-3` | Actors and resources | `N_hat` plus the extracted requirements whose `entity_names` reference each entity |
| `integrator` | Integration | Full prompt and the visible expert outputs |

The two requirement-type groups form a disjoint partition of the paper's three requirement types. The actor facet is a separate entity-oriented view and may repeat requirements already present in a type facet, as described in §5.1.2.

## 3. Visibility and input rules

- Each expert receives only its facet view; the full prompt is not copied into the expert's prompt view or input content.
- The integrator receives `FULL_PROMPT` and the three expert outputs that remain after empty-facet removal.
- The runtime continues to pass the extracted hypotheses to every strategy agent through the common `ProtocolContext`, as required by the paper's extraction contract.
- An entity is not converted into a requirement. Actor-linked requirements are included only when their explicit `entity_names` identify that entity.
- A requirement that names an entity absent from `N_hat` fails closed rather than silently inventing an entity.

## 4. Empty-facet semantics and call accounting

A facet is empty when its assigned requirement set is empty, or when the actor facet has no extracted entities. The factory records the facet as `dropped_empty`; the direct protocol adapter removes that expert from the prompt-specific agent roster, role assignments, visibility relation and protocol. No provider is created for that expert and no model call is made.

The E1 condition still records the paper's declared S12 call budget of `n+1 = 4` for `n=3`. The run artifact separately records:

- declared paper call budget;
- scheduled calls after empty-facet removal;
- actual provider calls and traces;
- active and dropped facet IDs;
- policy ID, policy hash and per-facet content hashes.

At least one expert facet must remain active. If all three facets are empty, S12 fails closed and requires extraction review.

For heterogeneous runs, the adapter rechecks that the *active* experts plus integrator still contain at least two distinct model identities and, when family metadata is available, at least two distinct model families. Empty experts cannot be counted as evidence of heterogeneity.

## 5. Scientific and evidential boundaries

The policy is deterministic and versioned. Its SHA-256 binds the declared mapping, source anchors, integrator visibility and empty-facet rule. The no-call campaign preflight validates that the runtime is configured with this registered policy; it does not generate prompt-specific views because that requires a frozen prompt and extraction record.

Unit tests validate the facet partition, actor links, empty-facet dropping, call accounting and direct strategy integration. They do not establish extraction recall or semantic correctness. Table 13 still requires human audit of 20% of extracted prompts; that audit and the author/practitioner annotations remain independent E1 gates.

## 6. Reproduction

From `engine/`:

```bash
python -m pytest -q tests/test_direct_protocol.py tests/test_e1_runtime.py
```

The canonical policy manifest and hash are available from:

- Python: `sociodec.jigsaw.PAPER_S12_POLICY_MANIFEST`
- Studio API: `GET /api/v1/jigsaw/policy`

No model/provider calls are made when the policy manifest is read or when facet views are constructed.


## 7. Campaign checkpoint binding

`DirectE1Runtime.campaign_manifest()` now includes a
`runtime_policy.jigsaw` object with this policy ID and SHA-256.
`DirectE1CampaignConfig` requires that versioned policy identity and
canonicalizes it into `provider_manifest_json`. The campaign configuration
hash therefore changes if the Jigsaw policy changes, preventing a resumable
campaign from silently mixing rows produced under different facet mappings.

The Studio full campaign preflight exports this policy-bound
`runtime_campaign_manifest` and its SHA-256. Use that exported manifest when
constructing `DirectE1CampaignConfig`; the input to the Studio preflight
remains the canonical provider registry manifest, which does not yet include
runtime-policy metadata.
