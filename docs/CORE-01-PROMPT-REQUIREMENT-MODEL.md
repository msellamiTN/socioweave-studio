# Core 01 — Prompt & Requirement Model

**Status:** PASS — automated acceptance suite green on 2026-11-17 (see `CORE-01-TEST-REPORT.md`)  
**Engine package:** `engine/sociodec/models/prompt.py`  
**Scientific source:** *Societies of Decomposers: Social and Organisational Strategies for LLM-Based Multi-Agent Prompt Decomposition*, Section 3.2, Definitions 1–2 and Table 2.

## 1. Paper contract

The paper defines a prompt as:

```text
P = (x, ι), where ι = (g, C, I, O)
```

- `x`: the user-authored prompt text.
- `g`: the goal.
- `C = Ch ∪ Cs`: hard and soft constraints.
- `I`: input facts.
- `O`: expected outputs / deliverables.

The paper distinguishes the explicit requirement set `R(P)` from the implicit requirement set `Rimp(P)`. The full set is:

```text
R*(P) = R(P) ∪ Rimp(P)
```

Each explicit atomic requirement has a type in `{target, constraint, deliverable}`, a domain label and a source span in `x`. Entities named in the prompt are modelled separately: an entity is not itself a requirement.

## 2. Implementation mapping

| Paper concept | Python type / field |
|---|---|
| `P` | `Prompt` |
| `x` | `Prompt.text` / `Prompt.x` |
| `ι` | `Interpretation` / `Prompt.iota` |
| `g` | `Interpretation.goal` |
| `Ch ∪ Cs` | `Interpretation.constraints`, classified by `ConstraintKind` |
| `I` | `Interpretation.inputs` |
| `O` | `Interpretation.deliverables` |
| entity set | `Interpretation.entities` / `Entity` |
| `τ(r)` | `Requirement.type` |
| `dom(r)` | `Requirement.domain` |
| source span | `Requirement.source_span` / `SourceSpan` |

## 3. Scientific boundaries

1. The implementation stores a declared interpretation; it does not claim to recover every member of `Int(x)`.
2. The model does not infer implicit requirements. Definition 3's extractor and hypothesis mechanism belong to Core 02.
3. The model does not claim semantic equivalence between a requirement statement and its source span. It validates span bounds and non-empty source text only.
4. The paper states that a decomposer receives `x`, not `ι`. Later execution components must therefore control which representation is passed to each agent. This domain model retains both without implying that every agent sees both.
5. No LLM provider, orchestration framework or extraction prompt is coupled to these domain types.

## 4. Validation rules implemented

- Prompt text and interpretation goal must be non-empty.
- Constraint statements, entity names, requirement statements and domain labels must be non-empty.
- Source spans are half-open character intervals `[start, end)`, must be positive and must fit inside the original prompt.
- Explicit requirements are required to carry a source span when validated against a prompt.
- Entity names in one interpretation are unique case-insensitively.

The half-open interval convention is an implementation convention for stable Python slicing; the paper requires source spans but does not prescribe an indexing convention.

## 5. Running example

The paper's smart-administration prompt asks a municipality of 180,000 inhabitants to digitalise its building-permit process. It states a 20-day target, a nine-month deadline, four involved bodies, a single online application, data exchange, data protection, citizen inclusion, a paper channel, a 400,000 EUR budget, no new staff and seven deliverables.

The paper identifies 17 explicit atomic requirements and at least two implicit prerequisites: an as-is process analysis and data-sharing agreements among the four bodies. These are scientific reference facts for later fixtures; Core 01 does not silently generate the 17 requirements or the two hypotheses.

## 6. Acceptance tests

Run from the `engine/` directory:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Core 01 is accepted when the tests establish:
- preservation of prompt text and the interpretation tuple;
- separation of hard and soft constraints;
- typed requirements and source-span validation;
- distinction between entities and requirements;
- rejection of structurally invalid domain objects.

## 7. Next dependency

Core 02 implements the paper's requirement extraction contract:

```text
(R_hat, H_hat, N_hat) = extract(x; e_1, ..., e_q)
```

It must preserve the union of extractor outputs, deduplicate equivalent statements, retain hypotheses for later confirmation/rejection, flag ambiguous readings and possible conflicts, and keep extraction errors visible rather than treating extracted requirements as ground truth.
