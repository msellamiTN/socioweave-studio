# E1 extraction and human-audit protocol

## Paper-specified elements

The E1 design registers three extractors (q=3), unions their outputs, and
subjects 20% of extracted requirement items to human audit. The engine already
implements structured extraction of explicit requirements, implicit
hypotheses, entities, ambiguity flags and potential conflicts, followed by
conservative union/deduplication with extractor provenance.

## Explicit operational choices

The paper does not specify the sampling algorithm or integer rounding rule.
The engine therefore freezes the following implementation choices rather
than silently presenting them as paper requirements:

- Audit population: deduplicated explicit requirements and implicit
  hypotheses. Entities, ambiguity flags and conflict pairs remain in the
  extractor evidence but are not sampling units.
- Sampling: SHA-256 rank sampling without replacement over the campaign-wide
  union item IDs, with a declared non-negative seed.
- Sample size: ceil(0.20 × union population).
- Deduplication: NFKC normalization, case-folding, punctuation/whitespace
  normalization, exact statement match within requirement type and domain.
- Three extractor identities and their provider/model revisions and
  configuration hashes are recorded. Distinct provider organizations are
  retained as provenance but are not asserted as a paper-mandated constraint.

## Audit evidence

Every sampled item begins with status PENDING. A completed audit requires
one decision for every sampled item, with reviewer ID, allowed decision,
non-empty rationale and timezone-aware ISO-8601 timestamp. Software does not
generate or infer human decisions. The frozen bundle hash covers extractor
outputs, union items, audit sample and subsequent decisions.

Allowed human decisions are correct, incorrect, incomplete and ambiguous.
A completed audit means all sampled items were reviewed; it does not imply
that every extracted item was judged correct.

## Reproduction and limitations

e1_extraction.py accepts already produced outputs from three extractors. It
does not invoke providers or fabricate benchmark content. Use
validate_e1_extraction_bundle(..., require_human_audit=True) before treating
the extraction bundle as campaign-ready. This module does not yet wire the
bundle into DirectE1CampaignRunner; that checkpoint integration is a
separate required step before live E1 execution can proceed.
