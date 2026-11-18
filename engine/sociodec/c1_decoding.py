"""Strict JSON decoding for C1 comparator and judge objection outputs."""
from __future__ import annotations
import json
from typing import Any
from sociodec.algorithm3_c1 import AnonymousObjection, AnonymousObjections

class C1DecodeError(ValueError):
    """Provider output does not satisfy the C1 typed JSON contract."""

def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise C1DecodeError(f"{label} must be a JSON object")
    return value

def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise C1DecodeError(f"{label} must be a non-empty string")
    return value.strip()

def parse_anonymous_objections_json(text: str, *, author_ids: tuple[str, ...]) -> AnonymousObjections:
    try:
        root = _object(json.loads(text), "root")
    except json.JSONDecodeError as exc:
        raise C1DecodeError(f"invalid JSON: {exc}") from exc
    if set(root) != {"objections"}:
        raise C1DecodeError("root must contain only 'objections'")
    raw = root["objections"]
    if not isinstance(raw, list) or not raw:
        raise C1DecodeError("objections must be a non-empty array")
    parsed = []
    for index, value in enumerate(raw):
        item = _object(value, f"objections[{index}]")
        allowed = {"code", "statement", "evidence"}
        if set(item) - allowed or not {"code", "statement"} <= set(item):
            raise C1DecodeError(f"objections[{index}] fields must be code, statement, optional evidence")
        objection = AnonymousObjection(
            code=_nonempty(item["code"], f"objections[{index}].code"),
            statement=_nonempty(item["statement"], f"objections[{index}].statement"),
            evidence=_nonempty(item["evidence"], f"objections[{index}].evidence") if "evidence" in item else "",
        )
        parsed.append(objection)
    try:
        result = AnonymousObjections(tuple(parsed))
        result.validate_no_author_ids(author_ids)
    except ValueError as exc:
        raise C1DecodeError(str(exc)) from exc
    return result

def parse_c1_judge_json(text: str, *, author_ids: tuple[str, ...]) -> tuple[str, AnonymousObjections | None]:
    try:
        root = _object(json.loads(text), "root")
    except json.JSONDecodeError as exc:
        raise C1DecodeError(f"invalid JSON: {exc}") from exc
    verdict = _nonempty(root.get("verdict"), "verdict").lower()
    if verdict not in {"accept", "reject"}:
        raise C1DecodeError("verdict must be exactly 'accept' or 'reject'")
    if verdict == "accept":
        if set(root) != {"verdict"}:
            raise C1DecodeError("accepted verdict must not include objections")
        return verdict, None
    if set(root) != {"verdict", "objections"}:
        raise C1DecodeError("rejected verdict must include objections and no extra fields")
    raw = root["objections"]
    if not isinstance(raw, list) or not raw:
        raise C1DecodeError("reject requires non-empty objections")
    # Reuse the strict objection parser by wrapping the array.
    objections = parse_anonymous_objections_json(
        json.dumps({"objections": raw}), author_ids=author_ids,
    )
    return verdict, objections
