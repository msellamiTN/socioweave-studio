# Majority ballots on Definition 7 equivalence classes

The majority operator now has a preferred ballot form in which each voter
submits a sequence of Subproblem records. The pooled candidate sub-problems
and ballot entries are classified together using the Definition 7 matcher.
A ballot endorses a class if it contains at least one member of that class;
each voter therefore contributes at most one endorsement to a class.
Retention remains strict majority: more than half of the supplied voters.

Unknown ballot items are rejected unless they match a pooled candidate class.
The finite matcher relation is checked for reflexivity, symmetry and
transitivity across the pooled items and all ballot entries.

For compatibility, the previous tuple-keyed ballot form remains available.
It uses subproblem_signature equality and is explicitly labelled in the
result rationale as a legacy exact-signature path. Do not mix the two ballot
representations within one call.

This is an implementation of the paper's majority inclusion rule using
Definition 7 classes. It does not establish semantic matcher accuracy or
prove that any external ballot generator made a correct judgment.
