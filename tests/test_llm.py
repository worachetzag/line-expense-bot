import json

from app import llm
from app.config import settings


def test_extract_json_from_fenced_block():
    assert llm._extract_json('```json\n{"transactions": []}\n```') == {"transactions": []}
    assert llm._extract_json("no json here") == {}


def test_parse_disabled_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "")
    assert llm.parse_with_llm("อะไรก็ได้") is None


def test_parse_with_mocked_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "key")
    monkeypatch.setattr(settings, "llm_model", "model")

    content = json.dumps(
        {
            "transactions": [
                {"type": "expense", "amount": 60, "category": "อาหาร", "note": "ข้าวมันไก่"},
                {"type": "expense", "amount": 20, "category": "เดินทาง", "note": "วิน"},
            ]
        }
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: FakeResponse())

    items = llm.parse_with_llm("กินข้าวมันไก่ 60 นั่งวิน 20")
    assert items is not None
    assert len(items) == 2
    assert items[0].amount == 60
    assert items[0].category == "อาหาร"
    assert items[1].category == "เดินทาง"


def test_parse_ignores_zero_amount(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "key")
    monkeypatch.setattr(settings, "llm_model", "model")

    content = json.dumps({"transactions": [{"type": "expense", "amount": 0}]})

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: FakeResponse())
    assert llm.parse_with_llm("...") is None
