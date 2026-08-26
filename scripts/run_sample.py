from __future__ import annotations

import base64
import io

from PIL import Image

from storefront_pipeline.infrai_storage import InfraiStorage
from storefront_pipeline.order_fulfillment import (
    CheckoutLine,
    CheckoutRequest,
    OrderFulfillmentPipeline,
)


def sample_image() -> str:
    output = io.BytesIO()
    Image.new("RGB", (1200, 800), color=(28, 92, 128)).save(output, "JPEG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def main() -> None:
    request = CheckoutRequest(
        order_id="order-1042",
        customer_email="buyer@example.com",
        image_base64=sample_image(),
        image_content_type="image/jpeg",
        lines=[CheckoutLine(sku="canvas-blue", quantity=2, unit_price="18.50")],
    )
    storage = InfraiStorage()
    try:
        update = OrderFulfillmentPipeline(storage).process(request)
        print(update.model_dump_json(indent=2))
    finally:
        storage.close()


if __name__ == "__main__":
    main()
