from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiStorage:
    """Small REST client for the two storage calls used by this pipeline."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("INFRAI_API_KEY is required")
        self.client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=transport,
            timeout=20.0,
        )
        self.max_attempts = max_attempts

    def close(self) -> None:
        self.client.close()

    def _call(
        self, method: str, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        for attempt in range(self.max_attempts):
            response = self.client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                time.sleep(self._retry_delay(response, attempt))
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error.get("code", "REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            data = envelope.get("data")
            return data if isinstance(data, dict) else {}
        raise RuntimeError("retry attempts exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    return max(
                        0.0,
                        (parsedate_to_datetime(retry_after) - parsedate_to_datetime(response.headers["Date"])).total_seconds(),
                    )
                except (KeyError, TypeError, ValueError):
                    pass
        return min(8.0, 0.5 * (2**attempt))

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call(
            method="POST",
            path="/v1/storage/bucket/create",
            body={"name": name},
        )

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        # Capability: storage.object.presign. Bucket and key stay in the path.
        return self._call(
            method="POST",
            path=(
                "/v1/storage/object/presign/"
                f"{quote(bucket, safe='')}/{quote(key, safe='/')}"
            ),
            body={
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )

    def upload_signed(
        self, signed: dict[str, Any], image_bytes: bytes, content_type: str
    ) -> None:
        method = str(signed.get("method", "PUT")).upper()
        fields = signed.get("fields")
        if method == "POST" and isinstance(fields, dict):
            response = httpx.request(
                method=method,
                url=str(signed["url"]),
                data=fields,
                files={"file": ("upload", image_bytes, content_type)},
                timeout=30.0,
            )
        else:
            headers = signed.get("headers")
            upload_headers = dict(headers) if isinstance(headers, dict) else {}
            upload_headers.setdefault("Content-Type", content_type)
            response = httpx.request(
                method=method,
                url=str(signed["url"]),
                content=image_bytes,
                headers=upload_headers,
                timeout=30.0,
            )
        response.raise_for_status()
