import pytest

from services.furniture_vision_verifier import (
    FurnitureVisionVerifier,
    VerifierCandidate,
    _compute_verifier_cost,
)


def test_compute_verifier_cost_prefers_explicit_cost_field():
    cost, source = _compute_verifier_cost(
        usage={"cost_usd": 0.0123, "input_tokens": 1000, "output_tokens": 200},
        input_price_per_million=1.0,
        output_price_per_million=2.0,
    )
    assert cost == 0.0123
    assert source == "usage_cost_field"


def test_compute_verifier_cost_from_tokens_when_prices_set():
    cost, source = _compute_verifier_cost(
        usage={"input_tokens": 1500, "output_tokens": 500},
        input_price_per_million=2.0,
        output_price_per_million=4.0,
    )
    assert cost is not None
    assert round(cost, 8) == round((1500 / 1_000_000) * 2.0 + (500 / 1_000_000) * 4.0, 8)
    assert source == "usage_tokens"


@pytest.mark.asyncio
async def test_verify_uses_parsed_payload_for_top_ids(settings, monkeypatch):
    service = FurnitureVisionVerifier(
        settings.model_copy(update={"OPENAI_API_KEY": "test-key"}),
    )

    async def _fake_prepare(_candidates_by_market):
        return [
            {
                "marketplace": "ozon",
                "candidate": VerifierCandidate(
                    candidate_id=1,
                    marketplace="ozon",
                    title="Диван",
                    url="https://www.ozon.ru/product/divan-1/",
                    image_url="https://example.com/img.jpg",
                    token_score=1.0,
                    token_rank=1,
                ),
                "image_bytes": b"\xff\xd8\xff\xe0fakejpeg",
            }
        ], {"success_total": 1, "success_by_market": {"ozon": 1}}

    async def _fake_request(**_kwargs):
        return (
            {
                "parsed": {
                    "markets": [
                        {
                            "marketplace": "ozon",
                            "candidates": [
                                {
                                    "candidate_id": 1,
                                    "title": "Диван",
                                    "is_same_category": True,
                                    "is_accessory_or_decor": False,
                                    "match_score": 91,
                                    "reason_short": "визуально близко",
                                }
                            ],
                            "top3_candidate_ids": [1],
                        }
                    ],
                    "notes": "",
                },
                "usage": {"input_tokens": 1000, "output_tokens": 100},
            },
            {"failure_reason": None, "model": "test", "attempts": 1},
        )

    monkeypatch.setattr(service, "_prepare_candidates", _fake_prepare)
    monkeypatch.setattr(service, "_request_llm_detailed", _fake_request)

    result = await service.verify(
        crop_bytes=b"\xff\xd8\xff\xe0fakejpeg",
        crop_id="crop-1",
        expected_type="sofa",
        candidates_by_market={
            "ozon": [
                VerifierCandidate(
                    candidate_id=1,
                    marketplace="ozon",
                    title="Диван",
                    url="https://www.ozon.ru/product/divan-1/",
                    image_url="https://example.com/img.jpg",
                    token_score=1.0,
                    token_rank=1,
                )
            ]
        },
    )

    assert result is not None
    assert result.top_ids_by_market.get("ozon") == [1]
    assert result.score_by_id.get(1) == 91


@pytest.mark.asyncio
async def test_verify_with_debug_reports_invalid_json(settings, monkeypatch):
    service = FurnitureVisionVerifier(
        settings.model_copy(update={"OPENAI_API_KEY": "test-key"}),
    )

    async def _fake_prepare(_candidates_by_market):
        return [
            {
                "marketplace": "ozon",
                "candidate": VerifierCandidate(
                    candidate_id=1,
                    marketplace="ozon",
                    title="Кресло",
                    url="https://www.ozon.ru/product/kreslo-1/",
                    image_url="https://example.com/img.jpg",
                    token_score=1.0,
                    token_rank=1,
                ),
                "image_bytes": b"\xff\xd8\xff\xe0fakejpeg",
            }
        ], {"success_total": 1, "success_by_market": {"ozon": 1}}

    async def _fake_request(**_kwargs):
        return None, {
            "failure_reason": "invalid_json",
            "model": "gpt-4.1-mini",
            "attempts": 2,
            "response_preview": "{broken json",
        }

    monkeypatch.setattr(service, "_prepare_candidates", _fake_prepare)
    monkeypatch.setattr(service, "_request_llm_detailed", _fake_request)

    result, info = await service.verify_with_debug(
        crop_bytes=b"\xff\xd8\xff\xe0fakejpeg",
        crop_id="crop-2",
        expected_type="chair",
        candidates_by_market={
            "ozon": [
                VerifierCandidate(
                    candidate_id=1,
                    marketplace="ozon",
                    title="Кресло",
                    url="https://www.ozon.ru/product/kreslo-1/",
                    image_url="https://example.com/img.jpg",
                    token_score=1.0,
                    token_rank=1,
                )
            ]
        },
    )

    assert result is None
    assert info.failure_reason == "invalid_json"
    assert info.prepared_candidates_total == 1
    assert info.prepared_candidates_by_market.get("ozon") == 1
    assert info.response_preview == "{broken json"
