# Definition 8 redundancy and Definition 7 matcher integration

The paper defines redundancy as the share of sub-problems equivalent to
another sub-problem. The implementation now accepts the actual
Subproblem records and computes equivalence classes with the same
matcher contract used by Definition 7 distance and union.

For a class of size greater than one, every member is counted as redundant;
the metric is the number of members belonging to non-singleton classes
divided by the total number of sub-problems.

The older subproblem_signatures input remains available for compatibility.
It counts equality of supplied keys only and must be treated as a legacy
precomputed-key path, not semantic equivalence. New paper-aligned callers
should pass subproblem_items and, for research-grade semantic evaluation,
an explicitly validated and audited matcher.

This change aligns redundancy computation with the shared equivalence
contract; it does not validate the semantic quality of the default lexical
matcher and does not close the separate majority-ballot migration gap.
