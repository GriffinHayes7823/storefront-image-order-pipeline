from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from PIL import Image
from pydantic import BaseModel, Field, field_validator

from .infrai_storage import InfraiStorage


class OrderStage(StrEnum):
    CHECKED_OUT = "checked_out"
    FULFILLED = "fulfilled"


class CheckoutLine(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    quantity: int = Field(gt=0, le=100)
    unit_price: Decimal = Field(gt=0, decimal_places=2)


class CheckoutRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=80)
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    image_base64: str = Field(min_length=1)
    image_content_type: str = Field(pattern=r"^image/(jpeg|png)$")
    lines: list[CheckoutLine] = Field(min_length=1)

    @field_validator("image_base64")
    @classmethod
    def valid_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except ValueError as exc:
            raise ValueError("image_base64 must be valid base64") from exc
        return value


class Receipt(BaseModel):
    order_id: str
    total: Decimal
    stage: OrderStage
    image_key: str


class CustomerOrderUpdate(BaseModel):
    customer_email: str
    subject: str
    receipt: Receipt


@dataclass(frozen=True)
class PreparedImage:
    body: bytes
    content_type: str
    extension: str


class OrderFulfillmentPipeline:
    def __init__(
        self,
        storage: InfraiStorage,
        bucket: str = "storefront-order-images",
        thumbnail_size: tuple[int, int] = (640, 640),
    ) -> None:
        self.storage = storage
        self.bucket = bucket
        self.thumbnail_size = thumbnail_size

    def process(self, checkout: CheckoutRequest) -> CustomerOrderUpdate:
        prepared = self._resize(checkout)
        image_key = f"orders/{checkout.order_id}/catalog.{prepared.extension}"
        token = sha256(
            f"{checkout.order_id}:{image_key}".encode("utf-8")
        ).hexdigest()

        self.storage.create_bucket(self.bucket)
        signed = self.storage.presign_put(
            self.bucket,
            image_key,
            content_type=prepared.content_type,
            max_bytes=len(prepared.body),
            idempotency_key=token,
        )
        self.storage.upload_signed(
            signed, prepared.body, prepared.content_type
        )

        receipt = Receipt(
            order_id=checkout.order_id,
            total=sum(
                (line.unit_price * line.quantity for line in checkout.lines),
                start=Decimal("0.00"),
            ),
            stage=OrderStage.FULFILLED,
            image_key=image_key,
        )
        return CustomerOrderUpdate(
            customer_email=checkout.customer_email,
            subject=f"Order {checkout.order_id} fulfilled",
            receipt=receipt,
        )

    def _resize(self, checkout: CheckoutRequest) -> PreparedImage:
        raw = base64.b64decode(checkout.image_base64, validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            source.thumbnail(self.thumbnail_size, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            if checkout.image_content_type == "image/jpeg":
                source.convert("RGB").save(output, format="JPEG", quality=85)
                return PreparedImage(output.getvalue(), "image/jpeg", "jpg")
            source.save(output, format="PNG", optimize=True)
            return PreparedImage(output.getvalue(), "image/png", "png")
