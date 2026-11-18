import pytest
from sociodec.c1_decoding import C1DecodeError, parse_anonymous_objections_json, parse_c1_judge_json
from sociodec.algorithm3_c1 import AnonymousObjection, AnonymousObjections

def test_parse_strict_anonymous_objections():
    parsed = parse_anonymous_objections_json(
        '{"objections":[{"code":"coverage-gap","statement":"Missing validation","evidence":"No test phase"}]}',
        author_ids=("a1","a2"))
    assert parsed == AnonymousObjections((AnonymousObjection("coverage-gap","Missing validation","No test phase"),))

def test_reject_extra_fields_and_empty_objection_list():
    with pytest.raises(C1DecodeError):
        parse_anonymous_objections_json('{"objections":[]}', author_ids=())
    with pytest.raises(C1DecodeError):
        parse_anonymous_objections_json('{"objections":[{"code":"x","statement":"y","author":"a1"}]}', author_ids=())

def test_reject_author_identifier_in_objection_text():
    with pytest.raises(C1DecodeError, match="author attribution"):
        parse_anonymous_objections_json('{"objections":[{"code":"x","statement":"a1 produced this"}]}', author_ids=("a1",))

def test_judge_accept_contract_is_minimal():
    assert parse_c1_judge_json('{"verdict":"accept"}', author_ids=("a1",)) == ("accept",None)
    with pytest.raises(C1DecodeError):
        parse_c1_judge_json('{"verdict":"accept","objections":[]}', author_ids=())

def test_reject_judge_requires_typed_objections():
    verdict, objections = parse_c1_judge_json(
        '{"verdict":"reject","objections":[{"code":"gap","statement":"Add missing step"}]}',
        author_ids=("a1",))
    assert verdict == "reject"
    assert len(objections.items) == 1
    with pytest.raises(C1DecodeError):
        parse_c1_judge_json('{"verdict":"reject","objections":[]}', author_ids=())
