from utils.response_parser import (
    extract_searchapi_candidates,
    parse_searchapi,
    parse_vision,
    rank_searchapi_candidates,
)


def test_parse_vision_filters_and_sorts():
    payload = {
        "localizedObjectAnnotations": [
            {
                "name": "Chair",
                "score": 0.8,
                "boundingPoly": {
                    "normalizedVertices": [
                        {"x": 0.1, "y": 0.1},
                        {"x": 0.5, "y": 0.1},
                        {"x": 0.5, "y": 0.5},
                        {"x": 0.1, "y": 0.5},
                    ]
                },
            },
            {
                "name": "Table",
                "score": 0.9,
                "boundingPoly": {
                    "normalizedVertices": [
                        {"x": 0.6, "y": 0.6},
                        {"x": 0.75, "y": 0.6},
                        {"x": 0.75, "y": 0.75},
                        {"x": 0.6, "y": 0.75},
                    ]
                },
            },
            {
                "name": "Sofa",
                "score": 0.95,
                "boundingPoly": {
                    "normalizedVertices": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 0.2, "y": 0.0},
                        {"x": 0.2, "y": 0.2},
                        {"x": 0.0, "y": 0.2},
                    ]
                },
            },
        ]
    }

    excluded = {"sofa"}
    results = parse_vision(
        payload,
        exclude_labels=excluded,
        min_score=0.6,
        min_area=0.01,
        max_objects=5,
        prefetch_n=10,
        iou_threshold=0.85,
        containment_threshold=0.9,
        max_per_label=2,
    )

    assert [item.label for item in results] == ["Chair", "Table"]
    assert results[0].area >= results[1].area


def test_parse_searchapi_filters_ozon_products():
    payload = {
        "results": [
            {"link": "https://example.com/item/123"},
            {"link": "https://www.ozon.ru/product/some-chair-123/"},
            {"link": "https://www.ozon.ru/p/another/"},
        ]
    }

    results = parse_searchapi(payload, label="Chair", marketplace="ozon", limit=3)
    assert results
    assert all("ozon.ru" in item.url for item in results)
    assert results[0].label == "Chair"


def test_parse_searchapi_rejects_ozon_travel_product_urls():
    payload = {
        "results": [
            {"title": "Hotel", "link": "https://www.ozon.ru/travel/hotels/product/abc/"},
            {"title": "Sofa", "link": "https://www.ozon.ru/product/divan-123/"},
        ]
    }
    results = parse_searchapi(payload, label="Couch", marketplace="ozon", limit=3)
    assert len(results) == 1
    assert results[0].url == "https://www.ozon.ru/product/divan-123/"


def test_parse_searchapi_normalizes_yandex_questions_url():
    payload = {
        "results": [
            {
                "title": "Chair",
                "link": "https://market.yandex.ru/card/chair/123/questions/?sku=1",
            }
        ]
    }
    results = parse_searchapi(payload, label="Chair", marketplace="yandex_market", limit=1)
    assert len(results) == 1
    assert results[0].url == "https://market.yandex.ru/card/chair/123/"


def test_rank_searchapi_candidates_prefers_include_and_drops_exclude():
    payload = {
        "results": [
            {
                "title": "Панно декоративное",
                "link": "https://www.ozon.ru/product/panno-111/",
            },
            {
                "title": "Прямой диван",
                "link": "https://www.ozon.ru/product/divan-222/",
            },
        ]
    }
    candidates = extract_searchapi_candidates(
        payload=payload,
        label="Couch",
        marketplace="ozon",
        limit=10,
    )
    ranked = rank_searchapi_candidates(
        candidates=candidates,
        include_tokens=["диван", "sofa"],
        exclude_tokens=["панно", "poster"],
    )
    assert len(ranked) == 1
    assert ranked[0].url == "https://www.ozon.ru/product/divan-222/"


def test_rank_searchapi_candidates_orders_include_then_position():
    payload = {
        "results": [
            {
                "title": "Стол журнальный",
                "link": "https://www.ozon.ru/product/stol-10/",
            },
            {
                "title": "Подушка декоративная",
                "link": "https://www.ozon.ru/product/podushka-20/",
            },
            {
                "title": "Стол кухонный",
                "link": "https://www.ozon.ru/product/stol-30/",
            },
        ]
    }
    candidates = extract_searchapi_candidates(
        payload=payload,
        label="Table",
        marketplace="ozon",
        limit=10,
    )
    ranked = rank_searchapi_candidates(
        candidates=candidates,
        include_tokens=["стол"],
        exclude_tokens=[],
    )
    assert [item.url for item in ranked] == [
        "https://www.ozon.ru/product/stol-10/",
        "https://www.ozon.ru/product/stol-30/",
        "https://www.ozon.ru/product/podushka-20/",
    ]
    assert ranked[0].include_match is True
    assert ranked[2].include_match is False
