import json
import socket
import sys


def _network_disabled(*_args, **_kwargs):
    raise PermissionError("network disabled")


def _disable_network() -> None:
    socket.socket = _network_disabled


class PdfWorkerError(Exception):
    def __init__(self, safe_code: str) -> None:
        self.safe_code = safe_code
        super().__init__(safe_code)


def extract_markdown(source: bytes, *, max_pages: int, max_text_chars: int) -> str:
    import pymupdf
    import pymupdf4llm

    document = pymupdf.open(stream=source, filetype="pdf")
    try:
        if document.needs_pass:
            raise PdfWorkerError("pdf_encrypted")
        if document.page_count > max_pages:
            raise PdfWorkerError("pdf_page_limit")
        markdown = pymupdf4llm.to_markdown(
            document,
            use_ocr=False,
            force_ocr=False,
            write_images=False,
            embed_images=False,
            ignore_images=True,
            page_chunks=False,
            show_progress=False,
        )
    finally:
        document.close()
    if not isinstance(markdown, str) or len(markdown) > max_text_chars:
        raise ValueError("invalid structured PDF output")
    return markdown


def main() -> None:
    _disable_network()
    try:
        header = json.loads(sys.stdin.buffer.readline(8192))
        max_source_bytes = int(header["max_source_bytes"])
        max_text_chars = int(header["max_text_chars"])
        max_pages = int(header["max_pages"])
        source = sys.stdin.buffer.read(max_source_bytes + 1)
        if len(source) > max_source_bytes:
            raise ValueError("source limit")
        text = extract_markdown(source, max_pages=max_pages, max_text_chars=max_text_chars)
        output = {"ok": True, "text": text}
    except PdfWorkerError as error:
        output = {"ok": False, "safe_code": error.safe_code}
    except Exception:
        output = {"ok": False}
    sys.stdout.write(json.dumps(output, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
