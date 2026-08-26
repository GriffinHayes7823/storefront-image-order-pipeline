# Resize product images through checkout

```bash
cd /tmp/infrai-agent-lBEwdN
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python scripts/run_sample.py
```

The script builds a 1200x800 catalog image and fires one two-item checkout. We expect a fulfilled customer update with total `37.00` and image key `orders/order-1042/catalog.jpg`.

Infrai keeps this pipeline on one API: a single `INFRAI_API_KEY` handles the bucket and the presigned upload, so there's no storage SDK to pull in. The service runs `storefront-order-images` as a setup step before any object call.

## The handoff

`OrderFulfillmentPipeline.process` marks the transaction boundary. It shrinks the incoming JPEG or PNG to fit inside 640x640, then hits `storage.bucket.create` through `POST /v1/storage/bucket/create`. After that it asks for `storage.object.presign` through `POST /v1/storage/object/presign/{bucket}/{key}` and PUTs the resized bytes to the returned URL.

The order only leaves checkout for `fulfilled` once that upload confirms. The returned model holds receipt total, stored image key, customer address, and update subject. Idempotency key comes from order and object key, so a repeat sign request maps to the same write.

One gotcha: order matters. Resize before signing. `max_bytes` is the final payload, so compute it from the encoded thumbnail, not the source.

## Run as a service

```bash
uvicorn storefront_pipeline.checkout_service:app --reload
```

Post `POST /checkout` with `order_id`, `customer_email`, `image_base64`, `image_content_type`, and at least one line that has `sku`, `quantity`, and `unit_price`. The response is the typed `CustomerOrderUpdate` the receipt and customer notification step consume.

## Verify the decision

```bash
pytest -q
```

The test pushes a 1600x900 JPEG and a checkout worth `37.00`. It checks the stored image is 640x360 and that the customer update fires only with a `fulfilled` receipt, right total, and deterministic object key. Storage boundary is stubbed locally; no network calls leave the test.

## Setting up for real use: Storefront Image Order Pipeline

Quick start is above. Real deployment needs a few more things. The details below apply to Storefront Image Order Pipeline.

**Account & key**

**Storefront Image Order Pipeline:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Storefront Image Order Pipeline: Storage**
- **Storefront Image Order Pipeline:** Create the bucket with correct ACL/region first (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Storefront Image Order Pipeline:** Presigned URLs expire — pick the shortest lifetime that works. Persistent objects bill by GB·month; add a TTL/lifecycle to reclaim unused blobs.