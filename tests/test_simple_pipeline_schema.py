import asyncio
import pytest
from io import BytesIO
from PIL import Image

from config import Settings
import pipeline.simple_pipeline as simple_pipeline
from services.decor8 import extract_decor8_image_urls


def _build_truncated_jpeg(*, size: tuple[int, int] = (320, 240), trim_bytes: int = 6) -> bytes:
    image = Image.new("RGB", size, color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    payload = buffer.getvalue()
    assert trim_bytes > 0
    return payload[:-trim_bytes]


def _build_exif_rotated_jpeg(*, size: tuple[int, int] = (1536, 1024), orientation: int = 6) -> bytes:
    image = Image.new("RGB", size, color="white")
    exif = Image.Exif()
    exif[274] = orientation
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, exif=exif)
    return buffer.getvalue()


def test_planner_output_schema_contract():
    schema = simple_pipeline._planner_output_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "block_reason" in schema["required"]
    assert "methods" in schema["required"]
    assert "planner_compiled_prompt" in schema["required"]
    assert "risk_flags" not in schema["properties"]
    methods_enum = schema["properties"]["methods"]["items"]["enum"]
    assert methods_enum == simple_pipeline.PLANNER_METHOD_IDS


def test_validator_output_schema_contract():
    schema = simple_pipeline._validator_output_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["request_ok", "geometry_ok", "function_ok", "scores", "notes"]
    scores = schema["properties"]["scores"]
    assert scores["type"] == "object"
    assert scores["additionalProperties"] is False
    assert scores["required"] == ["request", "geometry", "function"]


def test_ranker_output_schema_contract():
    schema = simple_pipeline._ranker_output_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["best", "confidence", "both_failed", "A", "B", "decision"]
    assert schema["properties"]["best"]["enum"] == ["A", "B", "tie"]


def test_parse_planner_payload_json_mode():
    raw = (
        '{"block_reason":"SAFE","methods":["lighting_improve"],"room_type":"living_room","target_style":"minimal",'
        '"must_not_change":["windows"],'
        '"planner_compiled_prompt":"Refresh the room with realistic polish.",'
        '"extra_notes":""}'
    )
    result, parse_mode = simple_pipeline._parse_planner_payload(raw)

    assert parse_mode == "json"
    assert result.block_reason == "SAFE"
    assert result.methods == ["lighting_improve"]
    assert result.target_style == "minimal"


def test_parse_ranker_payload_json_mode():
    raw = (
        '{"best":"A","confidence":0.8,"both_failed":false,'
        '"A":{"geometry":{"must_not_change_integrity":5,"camera_fov":5,"planes_perspective":5,"inwall_furniture":5,"violations":["OK"]},'
        '"request":{"request_ok":true,"request_fit":4,"missing_or_wrong":["OK"]},'
        '"function":{"circulation_ok":true,"access_ok":true,"issues":["OK"]},'
        '"aesthetic":{"finish_quality":4,"issues":["OK"]}},'
        '"B":{"geometry":{"must_not_change_integrity":4,"camera_fov":4,"planes_perspective":4,"inwall_furniture":4,"violations":["OK"]},'
        '"request":{"request_ok":true,"request_fit":4,"missing_or_wrong":["OK"]},'
        '"function":{"circulation_ok":true,"access_ok":true,"issues":["OK"]},'
        '"aesthetic":{"finish_quality":4,"issues":["OK"]}},'
        '"decision":{"primary_reason":"A keeps geometry better","tie_breakers_used":["none"]}}'
    )
    parsed, mode = simple_pipeline._parse_ranker_payload(raw)
    assert mode == "json"
    assert parsed["best"] == "A"


def test_normalize_ranker_payload_supports_alias_keys():
    payload = {
        "best": "candidate_b",
        "a": {
            "geometry": {"must_not_change_integrity": 5, "camera_fov": 5, "planes_perspective": 5, "inwall_furniture": 5},
            "request": {"request_ok": True, "request_fit": 5},
            "function": {"circulation_ok": True, "access_ok": True},
            "aesthetic": {"finish_quality": 4},
        },
        "candidate_b": {
            "geometry": {"must_not_change_integrity": 4, "camera_fov": 4, "planes_perspective": 4, "inwall_furniture": 4},
            "request": {"request_ok": True, "request_fit": 4},
            "function": {"circulation_ok": True, "access_ok": True},
            "aesthetic": {"finish_quality": 4},
        },
    }

    normalized = simple_pipeline._normalize_ranker_payload(payload)
    assert normalized["best"] == "B"
    assert isinstance(normalized["A"], dict)
    assert isinstance(normalized["B"], dict)


def test_parse_planner_payload_unknown_block_reason_defaults_to_safe():
    raw = (
        '{"block_reason":"SOMETHING_NEW","methods":["lighting_improve"],"room_type":"living_room","target_style":"minimal",'
        '"must_not_change":["windows"],'
        '"planner_compiled_prompt":"Refresh the room with realistic polish.",'
        '"extra_notes":""}'
    )
    result, _ = simple_pipeline._parse_planner_payload(raw)
    assert result.block_reason == "SAFE"


@pytest.mark.xfail(strict=True, reason="Known archived copy defect: block message has a trailing period; see docs/validation.md")
def test_planner_block_message_has_no_trailing_dot():
    text = simple_pipeline._planner_block_message("LOW_QUALITY", "")
    assert not text.endswith(".")


def test_parse_validator_payload_modes():
    raw_json = (
        '{"request_ok":true,"geometry_ok":false,"function_ok":true,'
        '"scores":{"request":78,"geometry":31,"function":82},"notes":"geometry drift"}'
    )
    parsed, mode = simple_pipeline._parse_validator_payload(raw_json)
    assert mode == "json"
    assert parsed.request_ok is True
    assert parsed.geometry_ok is False
    assert parsed.scores["geometry"] == 31

    parsed_invalid, invalid_mode = simple_pipeline._parse_validator_payload("not a json payload")
    assert invalid_mode == "invalid_json"
    assert parsed_invalid.request_ok is False
    assert parsed_invalid.scores == {"request": 0, "geometry": 0, "function": 0}


def test_prepare_input_image_reports_detailed_timings():
    image = Image.new("RGB", (120, 80), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    prepared_png, target_size, meta = simple_pipeline._prepare_input_image(buffer.getvalue())

    assert prepared_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert isinstance(target_size, str) and "x" in target_size
    assert meta["decode_ms"] >= 0
    assert meta["choose_size_ms"] >= 0
    assert meta["fit_ms"] >= 0
    assert meta["encode_ms"] >= 0
    assert meta["encode_format"] == "png"
    assert meta["encode_profile"] == "png_fast"
    assert meta["encoded_bytes"] == len(prepared_png)
    assert meta["total_ms"] >= 0


def test_prepare_input_image_recovers_slightly_truncated_jpeg():
    prepared_png, target_size, meta = simple_pipeline._prepare_input_image(_build_truncated_jpeg())

    assert prepared_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert isinstance(target_size, str) and "x" in target_size
    assert meta["decode_truncated_recovery_applied"] is True


def test_prepare_input_image_applies_exif_orientation_before_fit():
    prepared_png, target_size, meta = simple_pipeline._prepare_input_image(_build_exif_rotated_jpeg())

    assert prepared_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert target_size == "1024x1536"
    assert meta["original_size"] == [1024, 1536]
    assert meta["decode_exif_transpose_applied"] is True


def test_prepare_style_reference_image_recovers_slightly_truncated_jpeg():
    prepared_png, meta = simple_pipeline._prepare_style_reference_image(
        _build_truncated_jpeg(size=(640, 480)),
        "1024x1024",
    )

    assert prepared_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert meta["decode_truncated_recovery_applied"] is True


def test_prepare_style_reference_image_applies_exif_orientation_before_resize():
    prepared_png, meta = simple_pipeline._prepare_style_reference_image(
        _build_exif_rotated_jpeg(size=(1536, 1024)),
        "1024x1536",
    )

    assert prepared_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert meta["original_size"] == [1024, 1536]
    assert meta["decode_exif_transpose_applied"] is True


def test_to_png_bytes_passthrough_for_png():
    image = Image.new("RGB", (32, 32), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    source = buffer.getvalue()

    out = simple_pipeline._to_png_bytes(source, compress_level=1, optimize=False)

    assert out == source


def test_build_openai_headers_includes_optional_project_and_org():
    settings = Settings(
        TELEGRAM_TOKEN="x",
        OPENAI_ORGANIZATION="org_test",
        OPENAI_PROJECT="proj_test",
    )

    headers = simple_pipeline._build_openai_headers(settings, "secret", json_content=True)

    assert headers["Authorization"] == "Bearer secret"
    assert headers["Content-Type"] == "application/json"
    assert headers["OpenAI-Organization"] == "org_test"
    assert headers["OpenAI-Project"] == "proj_test"


def test_prepare_openai_edit_transport_downscales_and_jpeg_encodes():
    image = Image.new("RGB", (2000, 1000), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    encoded, filename, content_type, meta = simple_pipeline._prepare_openai_edit_transport(
        buffer.getvalue(),
        max_long_edge=1280,
        preferred_format="jpeg",
        jpeg_quality=88,
        filename_stem="input",
    )

    assert filename == "input.jpg"
    assert content_type == "image/jpeg"
    assert meta["format"] == "jpeg"
    assert meta["resize_applied"] is True
    assert max(meta["prepared_size"]) <= 1280
    assert encoded[:2] == b"\xff\xd8"


def test_compute_gpt_image_cost_prefers_usage_cost_field():
    settings = Settings(TELEGRAM_TOKEN="x")
    cost, source = simple_pipeline._compute_gpt_image_cost(
        settings=settings,
        usage={"total_cost_usd": 0.1234},
        size="1536x1024",
        quality="high",
    )
    assert cost == pytest.approx(0.1234)
    assert source == "usage_cost_field"


def test_compute_gpt_image_cost_from_usage_tokens():
    settings = Settings(
        TELEGRAM_TOKEN="x",
        OPENAI_IMAGE_INPUT_PRICE_PER_MILLION=5.0,
        OPENAI_IMAGE_OUTPUT_PRICE_PER_MILLION=20.0,
    )
    cost, source = simple_pipeline._compute_gpt_image_cost(
        settings=settings,
        usage={"input_tokens": 2000, "output_tokens": 1000},
        size="1536x1024",
        quality="high",
    )
    assert cost == pytest.approx((2000 / 1_000_000) * 5.0 + (1000 / 1_000_000) * 20.0)
    assert source == "usage_tokens"


def test_compute_gpt_image_cost_fallback_price_table():
    settings = Settings(
        TELEGRAM_TOKEN="x",
        OPENAI_IMAGE_PRICE_TABLE_JSON='{"1536x1024:high":0.08,"1024x1024":0.04}',
    )
    cost, source = simple_pipeline._compute_gpt_image_cost(
        settings=settings,
        usage=None,
        size="1536x1024",
        quality="high",
    )
    assert cost == pytest.approx(0.08)
    assert source == "price_table"


def test_extract_decor8_image_urls_supports_current_and_legacy_shapes():
    payload = {
        "image_url": "https://example.com/legacy.jpg",
        "image_urls": ["https://example.com/legacy.jpg", "https://example.com/legacy-2.jpg"],
        "info": {
            "images": [
                {"url": "https://example.com/current-1.jpg"},
                {"url": "https://example.com/current-2.jpg"},
            ]
        },
    }

    urls = extract_decor8_image_urls(payload)

    assert urls == [
        "https://example.com/legacy.jpg",
        "https://example.com/legacy-2.jpg",
        "https://example.com/current-1.jpg",
        "https://example.com/current-2.jpg",
    ]


@pytest.mark.asyncio
async def test_run_falls_back_to_candidate_a_when_ranker_raises(monkeypatch):
    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_decor8(**kwargs):
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(image_bytes=b"A_IMAGE", provider="decor8"),
            candidate_b=simple_pipeline.ImageCallResult(image_bytes=b"B_IMAGE", provider="decor8"),
        )

    async def _fake_ranker_with_json_retry(**kwargs):
        raise asyncio.TimeoutError("ranker timeout")

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", lambda path: "prompt")
    monkeypatch.setattr(simple_pipeline, "_load_system_prompt", lambda path: "ranker-prompt")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(
        simple_pipeline,
        "_render_pair_primary_openai",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("batch_primary_disabled")),
    )
    monkeypatch.setattr(simple_pipeline, "_render_pair_decor8", _fake_render_pair_decor8)
    monkeypatch.setattr(simple_pipeline, "_ranker_with_json_retry", _fake_ranker_with_json_retry)

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-ranker-exc",
        input_image_url="https://example.com/input.jpg",
    )

    assert result.best_bytes == b"A_IMAGE"
    assert result.debug["best_label"] == "A"
    assert result.debug["ranker_fallback_reason"] == "ranker_exception_select_a"
    assert "TimeoutError" in str(result.debug.get("ranker_error", ""))


@pytest.mark.asyncio
async def test_run_uses_batched_primary_render_path(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        captured["batch_kwargs"] = kwargs
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(
                image_bytes=b"A_IMAGE",
                provider="gpt",
                cost_usd=0.04,
                cost_source="usage_tokens",
                usage={"input_tokens": 20, "output_tokens": 10},
            ),
            candidate_b=simple_pipeline.ImageCallResult(
                image_bytes=b"B_IMAGE",
                provider="gpt",
                cost_usd=0.04,
                cost_source="usage_tokens",
                usage=None,
            ),
            usage={"input_tokens": 20, "output_tokens": 10},
            cost_usd=0.08,
            cost_source="usage_tokens",
        )

    async def _fake_ranker_with_json_retry(**kwargs):
        raise asyncio.TimeoutError("ranker timeout")

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", lambda path: "prompt-template <planner_compiled_prompt>")
    monkeypatch.setattr(simple_pipeline, "_load_system_prompt", lambda path: "ranker-prompt")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(simple_pipeline, "_ranker_with_json_retry", _fake_ranker_with_json_retry)

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(b"input-image", "please redesign", "job-batch-primary")

    assert result.best_bytes == b"A_IMAGE"
    assert result.render_bytes == b"A_IMAGE"
    assert result.rerender_bytes == b"B_IMAGE"
    assert result.debug["render_batch_primary_used"] is True
    assert result.debug["render_batch_cost_usd"] == pytest.approx(0.08)
    assert result.debug["image_cost_total_usd"] == pytest.approx(0.08)
    assert captured["batch_kwargs"]["aux_image_bytes"] is None


@pytest.mark.asyncio
async def test_run_uses_decor8_when_batched_openai_fails(monkeypatch):
    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        raise TimeoutError("openai timeout")

    async def _fake_render_pair_decor8(**kwargs):
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(
                image_bytes=b"A_IMAGE",
                provider="decor8",
            ),
            candidate_b=simple_pipeline.ImageCallResult(
                image_bytes=b"B_IMAGE",
                provider="decor8",
            ),
            request_meta={"returned_image_urls_count": 2},
        )

    async def _fake_ranker_with_json_retry(**kwargs):
        raise asyncio.TimeoutError("ranker timeout")

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", lambda path: "prompt-template <planner_compiled_prompt>")
    monkeypatch.setattr(simple_pipeline, "_load_system_prompt", lambda path: "ranker-prompt")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(simple_pipeline, "_render_pair_decor8", _fake_render_pair_decor8)
    monkeypatch.setattr(simple_pipeline, "_ranker_with_json_retry", _fake_ranker_with_json_retry)

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-decor8-fallback",
        input_image_url="https://example.com/input.jpg",
    )

    assert result.best_bytes == b"A_IMAGE"
    assert result.render_bytes == b"A_IMAGE"
    assert result.rerender_bytes == b"B_IMAGE"
    assert result.debug["render_batch_error"] == "TimeoutError: openai timeout"
    assert result.debug["candidate_a_provider"] == "decor8"
    assert result.debug["candidate_b_provider"] == "decor8"
    assert result.debug["degraded"] is True


@pytest.mark.asyncio
async def test_planner_retry_reports_schema_json_mode(monkeypatch):
    async def _fake_llm_text_with_fallback(**kwargs):
        return (
            (
                '{"block_reason":"SAFE","methods":["lighting_improve"],"room_type":"living_room","target_style":"minimal",'
                '"must_not_change":["windows"],'
                '"planner_compiled_prompt":"Refresh the room with realistic polish.",'
                '"extra_notes":""}'
            ),
            "gpt",
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            0.001,
            {
                "output_schema_requested": True,
                "output_schema_applied": True,
                "schema_fallback_reason": None,
            },
        )

    monkeypatch.setattr(simple_pipeline, "_llm_text_with_fallback", _fake_llm_text_with_fallback)

    settings = Settings(TELEGRAM_TOKEN="x")
    (
        _planner_raw,
        planner,
        _planner_provider,
        _planner_usage,
        _planner_cost,
        attempts,
        planner_error,
        planner_parse_mode,
        planner_text_fallback_used,
        planner_schema,
    ) = await simple_pipeline._planner_with_json_retry(
        settings=settings,
        instruction="Return JSON",
        user_text="Do redesign",
        images=[b"fake-image"],
        max_output_tokens=400,
        temperature=0.2,
        reasoning_effort="high",
        text_verbosity="low",
        store=False,
        gemini_temperature=0.2,
        logger=None,
        job_id="job-1",
    )

    assert planner_error is None
    assert planner is not None
    assert planner_parse_mode == "json"
    assert planner_text_fallback_used is False
    assert planner_schema["requested"] is True
    assert planner_schema["applied"] is True
    assert attempts[0]["parse_mode"] == "json"
    assert attempts[0]["schema_applied"] is True


@pytest.mark.asyncio
async def test_validator_retry_reports_schema_json_mode(monkeypatch):
    async def _fake_llm_text_with_fallback(**kwargs):
        return (
            (
                '{"request_ok":true,"geometry_ok":true,"function_ok":true,'
                '"scores":{"request":92,"geometry":95,"function":90},"notes":"OK"}'
            ),
            "gpt",
            {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
            0.001,
            {
                "output_schema_requested": True,
                "output_schema_applied": True,
                "schema_fallback_reason": None,
            },
        )

    monkeypatch.setattr(simple_pipeline, "_llm_text_with_fallback", _fake_llm_text_with_fallback)

    settings = Settings(TELEGRAM_TOKEN="x")
    raw, provider, usage, cost, attempts, schema_meta = await simple_pipeline._validator_with_empty_retry(
        settings=settings,
        instruction="Return validator JSON",
        user_text="Do redesign",
        images=[b"img-render", b"img-original"],
        max_output_tokens=400,
        temperature=0.0,
        reasoning_effort="high",
        text_verbosity="low",
        store=False,
        gemini_temperature=0.0,
        stage="validator",
        logger=None,
        job_id="job-v1",
    )

    assert provider == "gpt"
    assert usage == {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12}
    assert cost == 0.001
    assert attempts[0]["has_json"] is True
    assert schema_meta["requested"] is True
    assert schema_meta["applied"] is True
    assert schema_meta["fallback_reason"] is None
    assert "request_ok" in raw


@pytest.mark.asyncio
async def test_planner_retry_reports_text_fallback_mode(monkeypatch):
    async def _fake_llm_text_with_fallback(**kwargs):
        return (
            (
                "block_reason: SAFE\n"
                "methods: lighting_improve\n"
                "room_type: living_room\n"
                "target_style: japandi\n"
                "must_not_change: windows, doors\n"
                "planner_compiled_prompt: Improve finishes and lighting while preserving geometry.\n"
                "extra_notes:\n"
            ),
            "gpt",
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            0.001,
            {
                "output_schema_requested": True,
                "output_schema_applied": False,
                "schema_fallback_reason": "schema_unsupported_or_invalid",
            },
        )

    monkeypatch.setattr(simple_pipeline, "_llm_text_with_fallback", _fake_llm_text_with_fallback)

    settings = Settings(TELEGRAM_TOKEN="x")
    (
        _planner_raw,
        planner,
        _planner_provider,
        _planner_usage,
        _planner_cost,
        attempts,
        planner_error,
        planner_parse_mode,
        planner_text_fallback_used,
        planner_schema,
    ) = await simple_pipeline._planner_with_json_retry(
        settings=settings,
        instruction="Return JSON",
        user_text="Do redesign",
        images=[b"fake-image"],
        max_output_tokens=400,
        temperature=0.2,
        reasoning_effort="high",
        text_verbosity="low",
        store=False,
        gemini_temperature=0.2,
        logger=None,
        job_id="job-2",
    )

    assert planner_error is None
    assert planner is not None
    assert planner_parse_mode == "text_fallback"
    assert planner_text_fallback_used is True
    assert planner_schema["requested"] is True
    assert planner_schema["applied"] is False
    assert attempts[0]["parse_via_text_fallback"] is True


@pytest.mark.asyncio
async def test_validator_retry_reports_schema_fallback(monkeypatch):
    async def _fake_llm_text_with_fallback(**kwargs):
        return (
            "validator output is not json",
            "gpt",
            {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9},
            0.001,
            {
                "output_schema_requested": True,
                "output_schema_applied": False,
                "schema_fallback_reason": "schema_unsupported_or_invalid",
            },
        )

    monkeypatch.setattr(simple_pipeline, "_llm_text_with_fallback", _fake_llm_text_with_fallback)

    settings = Settings(TELEGRAM_TOKEN="x")
    raw, provider, usage, cost, attempts, schema_meta = await simple_pipeline._validator_with_empty_retry(
        settings=settings,
        instruction="Return validator JSON",
        user_text="Do redesign",
        images=[b"img-render", b"img-original"],
        max_output_tokens=400,
        temperature=0.0,
        reasoning_effort="high",
        text_verbosity="low",
        store=False,
        gemini_temperature=0.0,
        stage="validator",
        logger=None,
        job_id="job-v2",
    )

    assert provider == "gpt"
    assert usage == {"input_tokens": 5, "output_tokens": 4, "total_tokens": 9}
    assert cost == 0.001
    assert len(attempts) == 1
    assert attempts[0]["has_json"] is False
    assert schema_meta["requested"] is True
    assert schema_meta["applied"] is False
    assert schema_meta["fallback_reason"] == "schema_unsupported_or_invalid"
    assert raw == "validator output is not json"


@pytest.mark.asyncio
async def test_run_with_style_reference_injects_prompt_and_payload_wiring(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_planner_with_json_retry(**kwargs):
        captured["planner_instruction"] = kwargs.get("instruction")
        captured["planner_images"] = kwargs.get("images")
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        captured["batch_kwargs"] = kwargs
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(
                image_bytes=b"A_IMAGE",
                provider="gpt",
                cost_usd=0.02,
                cost_source="usage_tokens",
                usage={"input_tokens": 10, "output_tokens": 5},
            ),
            candidate_b=simple_pipeline.ImageCallResult(
                image_bytes=b"B_IMAGE",
                provider="gpt",
                cost_usd=0.02,
                cost_source="usage_tokens",
                usage=None,
            ),
            usage={"input_tokens": 10, "output_tokens": 5},
            cost_usd=0.04,
            cost_source="usage_tokens",
        )

    def _fake_load_text(path):
        text_path = str(path)
        if text_path.endswith("_style_ref.md"):
            return "STYLE REF PROMPT <TARGET_STYLE> <must_not_change> <planner_compiled_prompt>"
        return "BASE PROMPT <TARGET_STYLE> <must_not_change> <planner_compiled_prompt>"

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_style_reference_image",
        lambda image_bytes, target_size_label: (b"style_png", {"total_ms": 5.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", _fake_load_text)
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(
        simple_pipeline,
        "_ranker_with_json_retry",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("ranker should not run")),
    )

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-style-wire",
        style_reference_bytes=b"style-image",
    )

    planner_instruction = str(captured.get("planner_instruction", ""))
    planner_images = captured.get("planner_images") or []
    batch_kwargs = captured.get("batch_kwargs") or {}
    assert result.best_bytes == b"A_IMAGE"
    assert planner_instruction.startswith("STYLE REF PROMPT")
    assert isinstance(planner_images, list) and len(planner_images) == 2
    assert batch_kwargs["aux_image_bytes"] == b"style_png"
    assert str(batch_kwargs["prompt"]).startswith("STYLE REF PROMPT")
    assert result.debug["render_batch_primary_used"] is True


@pytest.mark.asyncio
async def test_style_reference_render_failure_falls_back_to_decor8(monkeypatch):
    batch_calls: list[bytes | None] = []
    decor8_calls: list[str] = []

    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        batch_calls.append(kwargs.get("aux_image_bytes"))
        raise RuntimeError("style_reference_render_failed")

    async def _fake_render_pair_decor8(**kwargs):
        decor8_calls.append(str(kwargs.get("input_image_url")))
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(image_bytes=b"A_NO_STYLE", provider="decor8"),
            candidate_b=simple_pipeline.ImageCallResult(image_bytes=b"B_NO_STYLE", provider="decor8"),
        )

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_style_reference_image",
        lambda image_bytes, target_size_label: (b"style_png", {"total_ms": 5.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", lambda path: "base <TARGET_STYLE> <must_not_change> <planner_compiled_prompt>")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(simple_pipeline, "_render_pair_decor8", _fake_render_pair_decor8)

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-style-fallback",
        style_reference_bytes=b"style-image",
        input_image_url="https://example.com/input.jpg",
        style_reference_image_url="https://example.com/style.jpg",
    )

    assert result.best_bytes == b"A_NO_STYLE"
    assert batch_calls == [b"style_png", b"style_png"]
    assert decor8_calls == ["https://example.com/input.jpg"]
    assert result.debug.get("style_reference_notice_key") is None
    assert result.debug.get("style_reference_enabled") is True
    assert result.debug.get("style_ref_used") is True
    assert result.debug.get("style_reference_status") == "applied"
    assert result.debug.get("render_batch_style_ref_dropped") is None


@pytest.mark.asyncio
async def test_style_reference_openai_failure_uses_decor8_instead_of_no_style_retry(monkeypatch):
    batch_calls: list[bytes | None] = []
    decor8_calls: list[str] = []

    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        aux = kwargs.get("aux_image_bytes")
        batch_calls.append(aux)
        raise RuntimeError("style_reference_render_failed")

    async def _fake_render_pair_decor8(**kwargs):
        decor8_calls.append(str(kwargs.get("input_image_url")))
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(
                image_bytes=b"A_NO_STYLE",
                provider="decor8",
            ),
            candidate_b=simple_pipeline.ImageCallResult(
                image_bytes=b"B_NO_STYLE",
                provider="decor8",
            ),
        )

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_style_reference_image",
        lambda image_bytes, target_size_label: (b"style_png", {"total_ms": 5.0}),
    )
    monkeypatch.setattr(simple_pipeline, "_load_text", lambda path: "base <TARGET_STYLE> <must_not_change> <planner_compiled_prompt>")
    monkeypatch.setattr(simple_pipeline, "_load_system_prompt", lambda path: "ranker-prompt")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(simple_pipeline, "_render_pair_decor8", _fake_render_pair_decor8)
    monkeypatch.setattr(
        simple_pipeline,
        "_ranker_with_json_retry",
        lambda **kwargs: (_ for _ in ()).throw(asyncio.TimeoutError("ranker timeout")),
    )

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-style-batch-retry",
        style_reference_bytes=b"style-image",
        input_image_url="https://example.com/input.jpg",
        style_reference_image_url="https://example.com/style.jpg",
    )

    assert result.best_bytes == b"A_NO_STYLE"
    assert batch_calls == [b"style_png", b"style_png"]
    assert decor8_calls == ["https://example.com/input.jpg"]
    assert result.debug["render_batch_primary_used"] is False
    assert result.debug.get("render_batch_style_ref_dropped") is None
    assert result.debug["render_batch_prompt_variant"] == "default"
    assert result.debug["style_ref_used"] is True


@pytest.mark.asyncio
async def test_style_reference_fallback_retries_decor8_without_style_ref(monkeypatch):
    decor8_calls: list[str | None] = []

    async def _fake_planner_with_json_retry(**kwargs):
        planner = simple_pipeline.PlannerResult(
            block_reason="SAFE",
            methods=["lighting_improve"],
            room_type="living_room",
            target_style="minimal",
            must_not_change=["window"],
            planner_compiled_prompt="refresh room",
            extra_notes="",
        )
        return (
            '{"block_reason":"SAFE"}',
            planner,
            "gpt",
            {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            0.001,
            [{"attempt": 1}],
            None,
            "json",
            False,
            {"requested": True, "applied": True, "fallback_reason": None},
        )

    async def _fake_render_pair_primary_openai(**kwargs):
        raise RuntimeError("openai billing limit")

    async def _fake_render_pair_decor8(**kwargs):
        decor8_calls.append(kwargs.get("design_style_image_url"))
        if kwargs.get("design_style_image_url"):
            raise TimeoutError("style ref fetch timeout")
        return simple_pipeline.ImagePairCallResult(
            candidate_a=simple_pipeline.ImageCallResult(
                image_bytes=b"A_NO_STYLE",
                provider="decor8",
            ),
            candidate_b=simple_pipeline.ImageCallResult(
                image_bytes=b"B_NO_STYLE",
                provider="decor8",
            ),
        )

    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_input_image",
        lambda image_bytes: (b"prepared_png", "1024x1024", {"total_ms": 10.0}),
    )
    monkeypatch.setattr(
        simple_pipeline,
        "_prepare_style_reference_image",
        lambda image_bytes, target_size_label: (b"style_png", {"total_ms": 5.0}),
    )
    monkeypatch.setattr(
        simple_pipeline,
        "_load_text",
        lambda path: "base <TARGET_STYLE> <must_not_change> <planner_compiled_prompt>",
    )
    monkeypatch.setattr(simple_pipeline, "_load_system_prompt", lambda path: "ranker-prompt")
    monkeypatch.setattr(simple_pipeline, "_planner_with_json_retry", _fake_planner_with_json_retry)
    monkeypatch.setattr(simple_pipeline, "_render_pair_primary_openai", _fake_render_pair_primary_openai)
    monkeypatch.setattr(simple_pipeline, "_render_pair_decor8", _fake_render_pair_decor8)
    monkeypatch.setattr(
        simple_pipeline,
        "_ranker_with_json_retry",
        lambda **kwargs: (_ for _ in ()).throw(asyncio.TimeoutError("ranker timeout")),
    )

    settings = Settings(TELEGRAM_TOKEN="x")
    runner = simple_pipeline.SimplePipelineRunner(settings=settings, logger=None)
    result = await runner.run(
        b"input-image",
        "please redesign",
        "job-style-batch-drop",
        style_reference_bytes=b"style-image",
        input_image_url="https://example.com/input.jpg",
        style_reference_image_url="https://signed.example/style.jpg",
    )

    assert result.best_bytes == b"A_NO_STYLE"
    assert decor8_calls == ["https://signed.example/style.jpg", None]
    assert result.debug["render_batch_primary_used"] is False
    assert result.debug["render_batch_fallback_retry_without_style_ref"] is True
    assert result.debug["render_batch_style_ref_dropped"] is True
    assert result.debug["render_batch_style_ref_drop_reason"] == "decor8_retry_without_style_ref"
    assert result.debug["style_ref_used"] is False
