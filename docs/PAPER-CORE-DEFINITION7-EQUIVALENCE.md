# Definition 7 equivalence implementation note

## Source requirement

Definition 7 of *Societies of Decomposers* defines two sub-problems as
equivalent when a matcher judges that they ask for the same output under
the same local constraints. Equation (2) computes Jaccard similarity over
the resulting equivalence classes of sub-problems and dependencies.

The paper does **not** prescribe exact string equality as its semantic
matcher. It explicitly identifies matching as a central challenge and
notes that matcher errors affect deduplication, voting, distance and coverage.

## Implemented contract

- `SubproblemMatcher.equivalent(a, b)` is the injectable matcher interface.
- `equivalence_classes` validates reflexivity, symmetry and transitivity
  over the finite set being compared. It fails closed for a relation that
  is not an equivalence relation; it does not turn similarity connected
  components into equivalence classes.
- `ExactOutputConstraintMatcher` compares normalized output text and the
  normalized (kind, statement) local-constraint set. It deliberately ignores
  question wording, inputs and covered-requirement annotations, matching
  the literal dimensions stated in Definition 7.
- This default is a **lexical approximation**, not a semantic equivalence
  oracle. It must not be reported as validated semantic matching.
- `decomposition_distance`, `union` and `consensus_medoid` use the same
  matcher contract.

## Scientific limitations and next integration

The paper does not specify a concrete matcher model, threshold, prompt,
human adjudication protocol or calibration procedure. These must be
declared and evaluated for each experimental configuration. A semantic
matcher should preserve an audit record (model/provider/version, prompt
hash, pairwise judgment, confidence/abstention and adjudication provenance).
Pairwise judgments that fail equivalence axioms must not be silently coerced.

The current majority ballot API remains keyed by legacy deterministic
signatures. It has **not** yet been migrated to matcher-defined class IDs;
therefore majority voting must not be described as semantically matcher-
aligned in this increment. This is an explicit known gap, not a hidden claim.

## Tests

The focused tests cover paraphrase-like wording changes under identical
output/constraints, different outputs, different local constraints,
non-transitive and asymmetric matchers, distance, and union. These tests
validate the software contract, not the semantic quality of a real matcher.
