import io
import socket
import subprocess
from types import SimpleNamespace

import pytest

from server.app.screening.parsers import ParserLimits, parse_document
from server.app.screening.pymupdf4llm_worker import _disable_network, extract_markdown
from server.app.screening.structured_pdf import StructuredPdfError, extract_structured_pdf


def _pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=600, height=800)
    writer.write(stream)
    return stream.getvalue()


def test_worker_explicitly_disables_ocr(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class Document:
        needs_pass = False
        page_count = 1

        def close(self) -> None:
            pass

    monkeypatch.setitem(__import__("sys").modules, "pymupdf", SimpleNamespace(open=lambda **_kwargs: Document()))
    monkeypatch.setitem(
        __import__("sys").modules,
        "pymupdf4llm",
        SimpleNamespace(to_markdown=lambda _document, **kwargs: calls.append(kwargs) or "# Profile\nPython"),
    )

    assert extract_markdown(b"%PDF-test", max_pages=2, max_text_chars=100) == "# Profile\nPython"
    assert calls == [{
        "use_ocr": False,
        "force_ocr": False,
        "write_images": False,
        "embed_images": False,
        "ignore_images": True,
        "page_chunks": False,
        "show_progress": False,
    }]


def test_worker_disables_network_in_its_own_process() -> None:
    original_socket = socket.socket
    try:
        _disable_network()
        with pytest.raises(PermissionError, match="network disabled"):
            socket.socket()
    finally:
        socket.socket = original_socket


def test_real_library_subprocess_handles_layout_and_clean_json_protocol() -> None:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=600, height=800)
    page.insert_text((40, 45), "CANDIDATE PROFILE", fontsize=18)
    page.insert_text((40, 90), "EXPERIENCE", fontsize=14)
    page.insert_text((40, 115), "Platform Engineer", fontsize=11)
    page.insert_text((330, 90), "EDUCATION", fontsize=14)
    page.insert_text((330, 115), "Example University", fontsize=11)
    rows = (("YEAR", "COMPANY", "ROLE"), ("2021-2025", "Example Tech", "AI Engineer"))
    x_positions = (40, 190, 360)
    for row_index, row in enumerate(rows):
        y = 210 + row_index * 32
        for column_index, value in enumerate(row):
            page.insert_text((x_positions[column_index] + 6, y + 21), value, fontsize=10)
    for x in (40, 190, 360, 540):
        page.draw_line((x, 210), (x, 274))
    for y in (210, 242, 274):
        page.draw_line((40, y), (540, y))
    source = document.tobytes()
    document.close()

    markdown = extract_structured_pdf(
        source,
        max_source_bytes=1024 * 1024,
        max_text_chars=20_000,
        max_pages=1,
        timeout_seconds=15,
    )

    assert markdown.strip()
    assert markdown.index("CANDIDATE PROFILE") < markdown.index("EXPERIENCE")
    assert "Platform Engineer" in markdown
    assert "EDUCATION" in markdown and "Example University" in markdown
    assert "2021-2025" in markdown and "Example Tech" in markdown and "AI Engineer" in markdown


def test_pdf_prefers_layout_markdown_with_columns_and_table(monkeypatch) -> None:
    markdown = """# 候选人资料

## 工作经历
左栏：平台研发

## 教育经历
右栏：某大学本科

| 时间 | 公司 | 职位 |
| --- | --- | --- |
| 2021-2025 | 示例科技 | AI 工程师 |
"""
    monkeypatch.setattr("server.app.screening.parsers.extract_structured_pdf", lambda *_args, **_kwargs: markdown)

    parsed = parse_document(io.BytesIO(_pdf_bytes()), extension=".pdf", mime_type="application/pdf")

    assert parsed.parser_version == "pdf-pymupdf4llm-v1"
    assert parsed.text.index("工作经历") < parsed.text.index("教育经历")
    assert "| 2021-2025 | 示例科技 | AI 工程师 |" in parsed.text


@pytest.mark.parametrize("structured_result", ["", "  \n"])
def test_pdf_falls_back_when_layout_result_is_empty(monkeypatch, structured_result: str) -> None:
    monkeypatch.setattr(
        "server.app.screening.parsers.extract_structured_pdf",
        lambda *_args, **_kwargs: structured_result,
    )

    parsed = parse_document(io.BytesIO(_pdf_bytes()), extension=".pdf", mime_type="application/pdf")

    assert parsed.parser_version == "pdf-v4"
    assert parsed.quality == "empty"


@pytest.mark.parametrize("safe_code", ["worker_failed", "timeout"])
def test_pdf_falls_back_when_layout_parser_fails(monkeypatch, safe_code: str) -> None:
    def fail(*_args, **_kwargs):
        raise StructuredPdfError(safe_code)

    monkeypatch.setattr("server.app.screening.parsers.extract_structured_pdf", fail)
    parsed = parse_document(io.BytesIO(_pdf_bytes()), extension=".pdf", mime_type="application/pdf")
    assert parsed.parser_version == "pdf-v4"


def test_pypdf_generic_failure_does_not_block_structured_success(monkeypatch) -> None:
    class BrokenReader:
        def __init__(self, *_args, **_kwargs) -> None:
            raise ValueError("strict parser rejected an otherwise readable PDF")

    monkeypatch.setattr("pypdf.PdfReader", BrokenReader)
    monkeypatch.setattr(
        "server.app.screening.parsers.extract_structured_pdf",
        lambda *_args, **_kwargs: "# Candidate\n\nStructured profile",
    )

    parsed = parse_document(io.BytesIO(b"%PDF-readable"), extension=".pdf", mime_type="application/pdf")

    assert parsed.parser_version == "pdf-pymupdf4llm-v1"
    assert "Structured profile" in parsed.text


def test_structured_parser_timeout_is_typed_and_bounded() -> None:
    with pytest.raises(StructuredPdfError) as raised:
        extract_structured_pdf(
            b"%PDF-private",
            max_source_bytes=1024,
            max_text_chars=1024,
            max_pages=1,
            timeout_seconds=0.1,
            worker_module="server.tests.parser_hang_worker",
        )
    assert str(raised.value) == "timeout"


def test_structured_parser_rejects_oversized_worker_output(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"x" * 9000),
    )
    with pytest.raises(StructuredPdfError) as raised:
        extract_structured_pdf(
            b"%PDF-test",
            max_source_bytes=1024,
            max_text_chars=1000,
            max_pages=1,
        )
    assert str(raised.value) == "worker_failed"
