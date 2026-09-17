"""Image cropping helpers."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

from models.schemas import VisionObject, VisionVertex


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(value, max_value))


def crop_by_bbox(image: Image.Image, vertices: list[VisionVertex]) -> Image.Image:
    left, top, right, bottom = _bbox_from_vertices(image.size, vertices)
    return image.crop((left, top, right, bottom))


def batch_crop(
    image_bytes: bytes,
    objects: list[VisionObject],
    image_format: str = "JPEG",
    mask_shrink_ratio: float = 0.15,
    mask_transparent: bool = False,
) -> list[dict]:
    base_mode = "RGBA" if mask_transparent else "RGB"
    image = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert(base_mode)
    bboxes = [_bbox_from_vertices(image.size, obj.bounding_box) for obj in objects]
    results: list[dict] = []
    for idx, obj in enumerate(objects):
        crop_image = image.crop(bboxes[idx])
        crop_image = _mask_inner_boxes(
            crop_image,
            bboxes[idx],
            bboxes,
            containment_threshold=0.8,
            shrink_ratio=mask_shrink_ratio,
            transparent=mask_transparent,
        )
        buffer = BytesIO()
        if mask_transparent and image_format.upper() == "JPEG":
            image_format = "PNG"
        crop_image.save(buffer, format=image_format)
        results.append({"object": obj, "bytes": buffer.getvalue()})
    return results


def _bbox_from_vertices(
    image_size: tuple[int, int], vertices: list[VisionVertex]
) -> tuple[int, int, int, int]:
    if not vertices:
        raise ValueError("No bounding box vertices provided.")
    width, height = image_size
    xs = [_clamp(v.x, 0.0, 1.0) * width for v in vertices]
    ys = [_clamp(v.y, 0.0, 1.0) * height for v in vertices]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)
    left = int(_clamp(left, 0, width))
    right = int(_clamp(right, 0, width))
    top = int(_clamp(top, 0, height))
    bottom = int(_clamp(bottom, 0, height))
    if right <= left or bottom <= top:
        raise ValueError("Invalid bounding box after clamping.")
    return left, top, right, bottom


def _mask_inner_boxes(
    crop_image: Image.Image,
    crop_bbox: tuple[int, int, int, int],
    all_bboxes: list[tuple[int, int, int, int]],
    containment_threshold: float = 0.8,
    shrink_ratio: float = 0.15,
    transparent: bool = False,
) -> Image.Image:
    left, top, right, bottom = crop_bbox
    crop_width = right - left
    crop_height = bottom - top
    crop_area = crop_width * crop_height
    if crop_width <= 0 or crop_height <= 0:
        return crop_image

    fill = (255, 255, 255, 0) if transparent else (255, 255, 255)
    draw = ImageDraw.Draw(crop_image)

    for inner in all_bboxes:
        if inner == crop_bbox:
            continue
        inner_left, inner_top, inner_right, inner_bottom = inner
        if inner_right <= inner_left or inner_bottom <= inner_top:
            continue
        inner_area = (inner_right - inner_left) * (inner_bottom - inner_top)
        if inner_area <= 0 or inner_area >= crop_area:
            continue
        shrink_w = (inner_right - inner_left) * shrink_ratio
        shrink_h = (inner_bottom - inner_top) * shrink_ratio
        inner_left = inner_left + shrink_w
        inner_right = inner_right - shrink_w
        inner_top = inner_top + shrink_h
        inner_bottom = inner_bottom - shrink_h
        if inner_right <= inner_left or inner_bottom <= inner_top:
            continue
        inter_left = max(left, inner_left)
        inter_top = max(top, inner_top)
        inter_right = min(right, inner_right)
        inter_bottom = min(bottom, inner_bottom)
        if inter_right <= inter_left or inter_bottom <= inter_top:
            continue
        inter_area = (inter_right - inter_left) * (inter_bottom - inter_top)
        if inter_area / inner_area < containment_threshold:
            continue
        rel_left = max(0, inter_left - left)
        rel_top = max(0, inter_top - top)
        rel_right = min(crop_width, inter_right - left)
        rel_bottom = min(crop_height, inter_bottom - top)
        if rel_right <= rel_left or rel_bottom <= rel_top:
            continue
        draw.rectangle([rel_left, rel_top, rel_right, rel_bottom], fill=fill)

    return crop_image
