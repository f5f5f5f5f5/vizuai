from io import BytesIO

from PIL import Image

from models.schemas import VisionObject, VisionVertex
from utils.image_processing import batch_crop, crop_by_bbox


def test_crop_by_bbox():
    image = Image.new("RGB", (100, 100), color="white")
    vertices = [
        VisionVertex(x=0.1, y=0.1),
        VisionVertex(x=0.9, y=0.1),
        VisionVertex(x=0.9, y=0.9),
        VisionVertex(x=0.1, y=0.9),
    ]
    cropped = crop_by_bbox(image, vertices)
    assert cropped.size == (80, 80)


def test_batch_crop_returns_bytes():
    image = Image.new("RGB", (50, 50), color="white")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")

    obj = VisionObject(
        label="Chair",
        score=0.9,
        area=0.04,
        bounding_box=[
            VisionVertex(x=0.0, y=0.0),
            VisionVertex(x=1.0, y=0.0),
            VisionVertex(x=1.0, y=1.0),
            VisionVertex(x=0.0, y=1.0),
        ],
    )
    results = batch_crop(buffer.getvalue(), [obj])
    assert len(results) == 1
    assert isinstance(results[0]["bytes"], bytes)
