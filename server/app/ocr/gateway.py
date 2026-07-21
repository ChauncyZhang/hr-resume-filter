import asyncio
import base64
import json
import ssl
import time
from typing import Iterable

from server.app.llm.gateway import PinnedHttpsTransport
from server.app.llm.policy import ProviderAllowlist, ProviderPolicyError


THINKING_DISABLED = {"type": "disabled"}
FIXED_PROBE_PROMPT = "Read this test image and reply with a short non-empty text. It contains no recruiting data."
FIXED_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
MAX_IMAGES = 20
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 25 * 1024 * 1024
MAX_PAGE_TEXT_CHARS = 50_000
MAX_TOTAL_TEXT_CHARS = 250_000
MAX_RESPONSE_BYTES = 512 * 1024
OCR_MAX_TOKENS = 8192


class OcrGatewayError(RuntimeError):
    def __init__(self, safe_code: str):
        self.safe_code = safe_code
        super().__init__(safe_code)


# Keep the provider-failure import shape parallel with server.app.llm.gateway.
GatewayError = OcrGatewayError


def _mime_type(image: bytes) -> str:
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise OcrGatewayError("ocr_image_invalid")


class OcrGateway:
    def __init__(
        self,
        transport=None,
        *,
        resolver=None,
        total_timeout: float = 75,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_concurrency: int = 2,
    ):
        if total_timeout <= 0 or max_response_bytes < 1 or max_concurrency < 1:
            raise ValueError("invalid OCR gateway limits")
        self.transport = transport or PinnedHttpsTransport(read_timeout=60)
        self.resolver = resolver
        self.total_timeout = total_timeout
        self.max_response_bytes = max_response_bytes
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def validate_provider(self, provider_id: str, base_url: str, model: str):
        policy = ProviderAllowlist(
            {provider_id: {"base_url": base_url, "models": [model]}},
            resolver=self.resolver,
        )
        spec = policy.require(provider_id, model)
        addresses = policy.resolve_public(spec)
        return spec, addresses

    async def _request(self, provider_id: str, base_url: str, model: str, api_key: str, image: bytes, prompt: str):
        try:
            spec, addresses = self.validate_provider(provider_id, base_url, model)
            mime_type = _mime_type(image)
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"},
                },
            ]
            payload = json.dumps(
                {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0,
                    "max_tokens": OCR_MAX_TOKENS,
                    "thinking": THINKING_DISABLED,
                },
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
            path = (spec.base_path or "") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            async def send():
                async with self._semaphore:
                    return await asyncio.to_thread(
                        self.transport.post,
                        spec,
                        addresses[0],
                        path,
                        headers,
                        payload,
                        self.max_response_bytes,
                    )

            response = await asyncio.wait_for(send(), self.total_timeout)
        except OcrGatewayError:
            raise
        except ProviderPolicyError as error:
            raise OcrGatewayError(str(error)) from None
        except (TimeoutError, OSError, ssl.SSLError):
            raise OcrGatewayError("provider_unavailable") from None
        except Exception:
            raise OcrGatewayError("provider_unavailable") from None

        if len(response.body) > self.max_response_bytes:
            raise OcrGatewayError("provider_response_too_large")
        if response.status_code in {401, 403}:
            raise OcrGatewayError("provider_auth_failed")
        if response.status_code in {400, 422}:
            raise OcrGatewayError("provider_request_rejected")
        if response.status_code == 404:
            raise OcrGatewayError("provider_model_not_found")
        if response.status_code == 429:
            raise OcrGatewayError("provider_quota_or_rate_limited")
        if 300 <= response.status_code < 400:
            raise OcrGatewayError("provider_redirect_rejected")
        if not 200 <= response.status_code < 300:
            raise OcrGatewayError("provider_unavailable")
        try:
            document = json.loads(response.body)
            text = document["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise OcrGatewayError("provider_response_invalid") from None
        return text.strip()

    async def test_connection(self, provider_id: str, base_url: str, model: str, api_key: str) -> int:
        started = time.monotonic()
        text = await self._request(provider_id, base_url, model, api_key, FIXED_TINY_PNG, FIXED_PROBE_PROMPT)
        if not text or len(text) > 1_000:
            raise OcrGatewayError("provider_response_invalid")
        return max(0, int((time.monotonic() - started) * 1000))

    async def extract_images(
        self,
        provider_id: str,
        base_url: str,
        model: str,
        api_key: str,
        images: Iterable[bytes],
    ) -> list[str]:
        pages = list(images)
        if not 1 <= len(pages) <= MAX_IMAGES:
            raise OcrGatewayError("ocr_image_count_invalid")
        total_image_bytes = 0
        for image in pages:
            if not isinstance(image, bytes) or not 1 <= len(image) <= MAX_IMAGE_BYTES:
                raise OcrGatewayError("ocr_image_too_large")
            _mime_type(image)
            total_image_bytes += len(image)
            if total_image_bytes > MAX_TOTAL_IMAGE_BYTES:
                raise OcrGatewayError("ocr_images_too_large")

        results: list[str] = []
        total_text_chars = 0
        for image in pages:
            text = await self._request(
                provider_id,
                base_url,
                model,
                api_key,
                image,
                "Extract all visible text from this page in reading order. Return text only.",
            )
            if len(text) > MAX_PAGE_TEXT_CHARS:
                raise OcrGatewayError("ocr_page_text_too_large")
            total_text_chars += len(text)
            if total_text_chars > MAX_TOTAL_TEXT_CHARS:
                raise OcrGatewayError("ocr_text_too_large")
            results.append(text)
        return results
