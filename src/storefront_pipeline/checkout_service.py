from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .infrai_storage import InfraiError, InfraiStorage
from .order_fulfillment import (
    CheckoutRequest,
    CustomerOrderUpdate,
    OrderFulfillmentPipeline,
)

app = FastAPI(title="Storefront image order pipeline")


@app.post("/checkout", response_model=CustomerOrderUpdate)
def checkout(request: CheckoutRequest) -> CustomerOrderUpdate:
    storage = InfraiStorage()
    try:
        return OrderFulfillmentPipeline(storage).process(request)
    except InfraiError as exc:
        caller_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=caller_status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    finally:
        storage.close()
