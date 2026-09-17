"""Overlay drawing helpers for furniture-search artifacts."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def apply_numbered_overlay(
    render_bytes: bytes,
    numbered_boxes: list[dict] | None,
    *,
    output_format: str = "PNG",
    jpeg_quality: int = 92,
) -> bytes:
    return _apply_numbered_overlay(
        render_bytes,
        numbered_boxes,
        output_format=output_format,
        jpeg_quality=jpeg_quality,
    )
def _apply_numbered_overlay(
    render_bytes: bytes,
    numbered_boxes: list[dict] | None,
    *,
    output_format: str = "PNG",
    jpeg_quality: int = 92,
) -> bytes:
    if not numbered_boxes:
        return render_bytes
    image = Image.open(BytesIO(render_bytes)).convert("RGBA")
    width, height = image.size
    if width <= 0 or height <= 0:
        return render_bytes
    draw = ImageDraw.Draw(image)
    min_dim = min(width, height)
    radius = max(12, int(min_dim * 0.026))
    ring_radius = radius + max(2, int(radius * 0.24))
    stroke_width = max(3, int(min_dim * 0.0038))
    label_font = _load_font(max(18, int(min_dim * 0.022)))
    placed: list[tuple[float, float]] = []
    for item in numbered_boxes:
        if _is_labeled_box(item):
            _draw_labeled_box(draw, item, width, height, stroke_width, label_font)
            continue
        try:
            index = int(item.get("index", 0))
        except (TypeError, ValueError):
            continue
        if index <= 0:
            continue
        x = float(item.get("x", 0.0) or 0.0)
        y = float(item.get("y", 0.0) or 0.0)
        cx = _clamp(x, 0.0, 1.0) * width
        cy = _clamp(y, 0.0, 1.0) * height
        cx, cy = _avoid_marker_overlap(cx, cy, placed, ring_radius, width, height)
        placed.append((cx, cy))
        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.ellipse(bbox, fill=(14, 165, 233, 235), outline=(255, 255, 255, 240), width=3)
        text = str(index)
        font_size = max(20, int(radius * 2.35))
        font = _load_font(font_size)
        text_w, text_h, text_dx, text_dy = _measure_text(draw, text, font)
        max_text = radius * 1.85
        while (text_w > max_text or text_h > max_text) and font_size > 14:
            font_size -= 2
            font = _load_font(font_size)
            text_w, text_h, text_dx, text_dy = _measure_text(draw, text, font)
        legacy_stroke = max(1, int(font_size * 0.1))
        draw.text(
            (cx - text_w / 2 - text_dx, cy - text_h / 2 - text_dy),
            text,
            fill=(255, 255, 255, 255),
            font=font,
            stroke_width=legacy_stroke,
            stroke_fill=(7, 52, 73, 255),
        )
    output = BytesIO()
    fmt = str(output_format or "PNG").upper().strip()
    rgb_image = image.convert("RGB")
    if fmt == "JPEG":
        rgb_image.save(
            output,
            format="JPEG",
            quality=max(60, min(95, int(jpeg_quality))),
            optimize=True,
        )
    else:
        rgb_image.save(output, format="PNG")
    return output.getvalue()


def _avoid_marker_overlap(
    cx: float,
    cy: float,
    placed: list[tuple[float, float]],
    ring_radius: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    if not placed:
        return cx, cy
    min_dist = ring_radius * 1.8
    offsets = [(0, 0)]
    step = ring_radius * 1.4
    for r in range(1, 4):
        for dx, dy in [
            (r, 0),
            (-r, 0),
            (0, r),
            (0, -r),
            (r, r),
            (-r, r),
            (r, -r),
            (-r, -r),
        ]:
            offsets.append((dx * step, dy * step))
    for ox, oy in offsets:
        nx = _clamp(cx + ox, ring_radius, width - ring_radius)
        ny = _clamp(cy + oy, ring_radius, height - ring_radius)
        if all((nx - px) ** 2 + (ny - py) ** 2 >= min_dist**2 for px, py in placed):
            return nx, ny
    return cx, cy


def _is_labeled_box(item: dict) -> bool:
    required = ("x1", "y1", "x2", "y2")
    return all(key in item and item.get(key) is not None for key in required)


def _draw_labeled_box(
    draw: ImageDraw.ImageDraw,
    item: dict,
    width: int,
    height: int,
    stroke_width: int,
    font: ImageFont.ImageFont,
) -> None:
    x1 = _clamp(float(item.get("x1", 0.0) or 0.0), 0.0, 1.0) * width
    y1 = _clamp(float(item.get("y1", 0.0) or 0.0), 0.0, 1.0) * height
    x2 = _clamp(float(item.get("x2", 0.0) or 0.0), 0.0, 1.0) * width
    y2 = _clamp(float(item.get("y2", 0.0) or 0.0), 0.0, 1.0) * height
    if x2 <= x1 or y2 <= y1:
        return

    line_color = (129, 147, 77, 255)
    badge_fill = (129, 147, 77, 255)
    badge_text = (255, 250, 240, 255)

    draw.rectangle([x1, y1, x2, y2], outline=line_color, width=stroke_width)

    label = str(item.get("label") or item.get("index") or "").strip()
    if not label:
        return

    label_padding_x = max(10, int(stroke_width * 2.4))
    label_padding_y = max(6, int(stroke_width * 1.6))
    text_w, text_h, text_dx, text_dy = _measure_text(draw, label, font)
    badge_h = text_h + label_padding_y * 2
    badge_w = text_w + label_padding_x * 2
    badge_x = max(0, min(x1, width - badge_w))
    badge_y = y1 - badge_h - stroke_width
    if badge_y < 0:
        badge_y = min(y1 + stroke_width, max(0, height - badge_h))
    badge_rect = [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h]
    corner_radius = max(8, int(badge_h * 0.35))
    draw.rounded_rectangle(badge_rect, radius=corner_radius, fill=badge_fill)
    draw.text(
        (
            badge_x + label_padding_x - text_dx,
            badge_y + label_padding_y - text_dy,
        ),
        label,
        fill=badge_text,
        font=font,
    )


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=max(12, size))
    except TypeError:
        return ImageFont.load_default()


def _measure_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
) -> tuple[int, int, int, int]:
    if hasattr(draw, "textbbox"):
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        return right - left, bottom - top, left, top
    width, height = draw.textsize(text, font=font)
    return width, height, 0, 0


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))
