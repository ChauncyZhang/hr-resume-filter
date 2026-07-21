import json
import math
import socket
import sys
from dataclasses import dataclass

import fitz


def _network_disabled(*_args, **_kwargs):
    raise PermissionError("network disabled")


socket.socket = _network_disabled


@dataclass(frozen=True)
class _Limits:
    max_source_bytes: int
    max_pages: int
    max_page_pixels: int
    max_total_pixels: int
    max_total_bytes: int
    dpi: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in self.__dict__.values()
        ) or self.dpi > 600:
            raise ValueError("invalid limits")


class _WorkerError(Exception):
    def __init__(self, safe_code: str) -> None:
        self.safe_code = safe_code


def _render(source: bytes, limits: _Limits) -> tuple[list[dict[str, int]], bytes]:
    if len(source) > limits.max_source_bytes:
        raise _WorkerError("file_too_large")
    if not source.startswith(b"%PDF-"):
        raise _WorkerError("file_magic_mismatch")

    try:
        document = fitz.open(stream=source, filetype="pdf")
    except Exception:
        raise _WorkerError("pdf_malformed") from None
    try:
        if document.needs_pass:
            raise _WorkerError("pdf_encrypted")
        page_count = document.page_count
        if page_count <= 0:
            raise _WorkerError("pdf_malformed")
        if page_count > limits.max_pages:
            raise _WorkerError("pdf_page_limit")

        scale = limits.dpi / 72.0
        dimensions: list[tuple[int, int]] = []
        total_pixels = 0
        for page_number in range(page_count):
            rect = document.load_page(page_number).rect
            if not all(math.isfinite(value) and value > 0 for value in (rect.width, rect.height)):
                raise _WorkerError("pdf_malformed")
            width = math.ceil(rect.width * scale)
            height = math.ceil(rect.height * scale)
            pixels = width * height
            if pixels > limits.max_page_pixels:
                raise _WorkerError("pdf_pixel_limit")
            total_pixels += pixels
            if total_pixels > limits.max_total_pixels:
                raise _WorkerError("pdf_total_pixel_limit")
            dimensions.append((width, height))

        images: list[bytes] = []
        metadata: list[dict[str, int]] = []
        total_bytes = 0
        matrix = fitz.Matrix(scale, scale)
        for index, (expected_width, expected_height) in enumerate(dimensions):
            try:
                pixmap = document.load_page(index).get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                image = pixmap.tobytes("png")
            except Exception:
                raise _WorkerError("pdf_render_failed") from None
            if pixmap.width != expected_width or pixmap.height != expected_height:
                raise _WorkerError("pdf_render_failed")
            total_bytes += len(image)
            if total_bytes > limits.max_total_bytes:
                raise _WorkerError("pdf_render_byte_limit")
            images.append(image)
            metadata.append({
                "page_number": index + 1,
                "width": pixmap.width,
                "height": pixmap.height,
                "length": len(image),
            })
        return metadata, b"".join(images)
    finally:
        document.close()


def main() -> None:
    payload = b""
    try:
        header = json.loads(sys.stdin.buffer.readline(8192))
        limits = _Limits(**header["limits"])
        source = sys.stdin.buffer.read(limits.max_source_bytes + 1)
        pages, payload = _render(source, limits)
        response = {"ok": True, "pages": pages}
    except _WorkerError as error:
        response = {"ok": False, "safe_code": error.safe_code}
    except Exception:
        response = {"ok": False, "safe_code": "pdf_render_failed"}
    sys.stdout.buffer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n" + payload)


if __name__ == "__main__":
    main()
