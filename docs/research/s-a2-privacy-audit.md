# S-A2 serialized privacy audit — evidence and limitations

## Scope of these tests

The provider-boundary regression tests exercise the actual JSON payload emitted by `ProviderProtocolInvoker` for synthetic runtime strategies configured with:

- `anonymous=True`: visible-history author labels are serialized as `anonymous` in later peer-visible steps;
- `peer_visible=False` in round 1: initial drafts do not include peer outputs in either `visible_history` or the serialized `input_content` field.

These are implementation-boundary tests of runtime behavior, not a proof that the paper's Delphi or Nominal Group Technique (NGT) strategy factory is correctly wired. The NGT test specifically covers initial draft isolation only; it does not verify ranking, pooled draft presentation, facilitator handling, or the exact strategy semantics.

## Proven by the current code/tests

- Runtime `visible_history` author labels are masked to `anonymous` when `SocialStrategy.anonymous=True`.
- Provider JSON serialization uses the runtime-filtered `visible_history` and preserves the masked labels.
- For tested synthetic strategies, round-1 provider prompts have no peer-visible draft content.
- Provider requests still serialize the acting `agent_id`; this is expected for routing/context and is not removed by author-label masking.

## Not proven / not guaranteed

- Full anonymity or identity unlinkability across rounds, providers, requests, or logs.
- No identifying information inside peer-generated text, prompt views, agent context, hypotheses, or input content.
- Privacy of `agent_id`, `agent_context`, provider trace fields, request IDs, token/latency logs, hashes, or external provider logging.
- Correct anonymity configuration of every actual Delphi (S4) strategy instance.
- Correct protocol wiring for paper-defined NGT (S3), including the ranking phase and anonymized pooled drafts.
- Formal privacy guarantee (e.g., differential privacy), adversarial resistance, or certification.

## Required follow-up before live-model experiments

Audit the actual S3/S4 strategy constructors/factories and all prompt construction paths; capture serialized prompts for each phase; inspect traces and provider logging controls; test cross-round identity-linkability; and decide whether pseudonymization must be scoped/rotated or whether stronger privacy mechanisms are required. No live model experiment is authorized by this audit alone.


## Sequential chain cost evidence (n=2, k=2, T=2)

The provider-backed composition regression currently measures actual provider invocations for both chains. The catalogue formulas imply the following unseeded budget and seeded actual call counts:

- C8 = S2 → S8: theoretical `S2= n+1 = 3`, `S8=k+3=5`, total 8. The second phase's single seeded author draft reduces actual provider calls by one; observed expected total is 7.
- C2 = S12 → S5: theoretical `S12=n+1=3`, `S5=4`, total 7. The second phase's one seeded draft reduces actual provider calls by one; observed expected total is 6.

The existing provider-backed tests assert these actual totals and verify that the second phase has one seeded agent. They do not yet assert every phase's full step-by-step theoretical-versus-actual ledger. That granular per-phase accounting is the next audit item.
