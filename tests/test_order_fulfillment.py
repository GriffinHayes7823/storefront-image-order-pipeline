from __future__ import annotations

import base64
import io
from decimal import Decimal

from PIL import Image

from storefront_pipeline.order_fulfillment import (
    CheckoutLine,
    CheckoutRequest,
    OrderFulfillmentPipeline,
    OrderStage,
)


class RecordingStorage:
    def __init__(self) -> None:
        self.bucket: str | None = None
        self.upload: tuple[str, bytes, str] | None = None

    def create_bucket(self, name: str) -> dict[str, str]:
        self.bucket = name
        return {"name": name}

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, str]:
        assert bucket == self.bucket
        assert content_type == "image/jpeg"
        assert max_bytes > 0
        assert len(idempotency_key) == 64
        return {
            "url": "https://uploads.example.test/order-image",
            "method": "POST",
            "fields": {"key": key, "policy": "signed-policy"},
        }

    def upload_signed(
        self, signed: dict[str, object], image_bytes: bytes, content_type: str
    ) -> None:
        assert signed["method"] == "POST"
        assert signed["fields"] == {
            "key": "orders/order-1042/catalog.jpg",
            "policy": "signed-policy",
        }
        self.upload = (str(signed["url"]), image_bytes, content_type)


def jpeg_base64(size: tuple[int, int]) -> str:
    output = io.BytesIO()
    Image.new("RGB", size, color=(90, 40, 120)).save(output, "JPEG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def test_large_image_is_resized_before_fulfillment_update() -> None:
    storage = RecordingStorage()
    request = CheckoutRequest(
        order_id="order-1042",
        customer_email="buyer@example.com",
        image_base64=jpeg_base64((1600, 900)),
        image_content_type="image/jpeg",
        lines=[CheckoutLine(sku="canvas-blue", quantity=2, unit_price="18.50")],
    )

    update = OrderFulfillmentPipeline(storage).process(request)  # type: ignore[arg-type]

    assert storage.upload is not None
    _, stored_bytes, stored_type = storage.upload
    with Image.open(io.BytesIO(stored_bytes)) as stored:
        assert stored.size == (640, 360)
    assert stored_type == "image/jpeg"
    assert update.receipt.stage is OrderStage.FULFILLED
    assert update.receipt.total == Decimal("37.00")
    assert update.receipt.image_key == "orders/order-1042/catalog.jpg"
    assert update.subject == "Order order-1042 fulfilled"
