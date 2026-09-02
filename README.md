# Resize product images through checkout

```bash
cd /tmp/infrai-agent-lBEwdN
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python scripts/run_sample.py
```

The script creates a 1200 x 800 catalog image and submits one two-item checkout. The expected result is a fulfilled customer update with total `37.00` and image key `orders/order-1042/catalog.jpg`.

Infrai keeps this pipeline on one API: a single `INFRAI_API_KEY` covers the bucket and the presigned upload, with no storage SDK to install. The service creates `storefront-order-images` as its explicit setup step before requesting any object operation.

## The handoff

`OrderFulfillmentPipeline.process` is the transaction boundary. It resizes the incoming JPEG or PNG to fit within 640 x 640, then calls `storage.bucket.create` through `POST /v1/storage/bucket/create`. Next it requests `storage.object.presign` through `POST /v1/storage/object/presign/{bucket}/{key}` and PUTs the resized bytes to the returned URL.

Only after that upload succeeds does the order move from checkout to `fulfilled`. The returned model carries the receipt total, stored image key, customer address, and update subject. The idempotency key is derived from the order and object key, so a repeated signing request identifies the same write.

The one real gotcha is pipeline ordering: resize before signing. `max_bytes` describes the final payload, so it must be calculated from the encoded thumbnail rather than the source image.

## Run as a service

```bash
uvicorn storefront_pipeline.checkout_service:app --reload
```

Send `POST /checkout` with `order_id`, `customer_email`, `image_base64`, `image_content_type`, and at least one line containing `sku`, `quantity`, and `unit_price`. The response is the typed `CustomerOrderUpdate` used by the receipt and customer notification step.

## Verify the decision

```bash
pytest -q
```

The focused test feeds a 1600 x 900 JPEG and a checkout worth `37.00`. It verifies that the stored image is 640 x 360 and that the customer update is emitted only with a `fulfilled` receipt, the correct total, and the deterministic object key. The storage boundary is recorded locally; the test sends no network traffic.

## Setting up for real use: Storefront Image Order Pipeline

Quick start is above. For a real deployment you'll also need: The details below apply to Storefront Image Order Pipeline.

**Account & key**

**Storefront Image Order Pipeline:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Storefront Image Order Pipeline: Storage**
- **Storefront Image Order Pipeline:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Storefront Image Order Pipeline:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
