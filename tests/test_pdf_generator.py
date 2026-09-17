from io import BytesIO

from PIL import Image

from utils import pdf_generator


def test_load_font_fallback_respects_requested_size(monkeypatch):
    original_truetype = pdf_generator.ImageFont.truetype

    def _raise_oserror(*args, **kwargs):
        if args and isinstance(args[0], str):
            raise OSError("font not found")
        return original_truetype(*args, **kwargs)

    monkeypatch.setattr(pdf_generator.ImageFont, "truetype", _raise_oserror)
    font = pdf_generator._load_font(26)
    assert getattr(font, "size", 0) >= 20


def test_apply_numbered_overlay_draws_visible_markers():
    image = Image.new("RGB", (320, 240), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    source = buffer.getvalue()

    overlay = pdf_generator._apply_numbered_overlay(
        source, [{"index": 1, "x": 0.5, "y": 0.5}]
    )

    assert overlay.startswith(b"\x89PNG\r\n\x1a\n")
    assert overlay != source


def test_apply_numbered_overlay_draws_labeled_boxes():
    image = Image.new("RGB", (400, 300), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    source = buffer.getvalue()

    overlay = pdf_generator._apply_numbered_overlay(
        source,
        [{"label": "Стул", "x1": 0.2, "y1": 0.2, "x2": 0.55, "y2": 0.75}],
    )

    assert overlay.startswith(b"\x89PNG\r\n\x1a\n")
    assert overlay != source
