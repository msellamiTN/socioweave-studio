"""Definition 7 equivalence contract and finite equivalence-class construction."""
from __future__ import annotations
from typing import Protocol, Sequence, TypeVar
from sociodec.extraction import _normalise

T = TypeVar("T")

class SubproblemMatcher(Protocol):
    """A symmetric, reflexive and transitive equivalence judgment."""
    def equivalent(self, left, right) -> bool: ...

class ExactOutputConstraintMatcher:
    """Lexical proxy for Definition 7; explicitly not semantic equivalence."""
    name = "exact-output-local-constraints-v1"
    is_semantic = False

    def equivalent(self, left, right) -> bool:
        lc = frozenset((c.kind.value, _normalise(c.statement)) for c in left.local_constraints)
        rc = frozenset((c.kind.value, _normalise(c.statement)) for c in right.local_constraints)
        return _normalise(left.output) == _normalise(right.output) and lc == rc

DEFAULT_MATCHER = ExactOutputConstraintMatcher()

def equivalence_classes(items: Sequence[T], matcher: SubproblemMatcher = DEFAULT_MATCHER) -> tuple[int, ...]:
    """Return first-occurrence class labels; reject non-equivalence judgments."""
    n = len(items)
    matrix = [[False] * n for _ in range(n)]
    for i in range(n):
        value = matcher.equivalent(items[i], items[i])
        if type(value) is not bool or not value:
            raise ValueError("Matcher violates reflexivity")
        matrix[i][i] = True
        for j in range(i + 1, n):
            forward = matcher.equivalent(items[i], items[j])
            backward = matcher.equivalent(items[j], items[i])
            if type(forward) is not bool or type(backward) is not bool:
                raise TypeError("Matcher judgments must be booleans")
            if forward != backward:
                raise ValueError("Matcher violates symmetry")
            matrix[i][j] = matrix[j][i] = forward
    for i in range(n):
        for j in range(n):
            if matrix[i][j] and any(matrix[j][k] and not matrix[i][k] for k in range(n)):
                raise ValueError("Matcher violates transitivity")
    reps = []
    labels = []
    for i in range(n):
        label = next((c for c, r in enumerate(reps) if matrix[i][r]), None)
        if label is None:
            label = len(reps)
            reps.append(i)
        labels.append(label)
    return tuple(labels)
