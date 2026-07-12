import io
import zipfile
from dataclasses import dataclass
from typing import BinaryIO

from server.app.queue.service import normalize_safe_code

@dataclass(frozen=True)
class ParserLimits:
    max_source_bytes: int = 10 * 1024 * 1024; max_text_chars: int = 500_000; pdf_max_pages: int = 100
    docx_max_entries: int = 1000; docx_max_uncompressed_bytes: int = 50 * 1024 * 1024; docx_max_compression_ratio: int = 100

@dataclass(frozen=True)
class ParsedDocument:
    text: str; parser_version: str; quality: str

class ParserError(Exception):
    def __init__(self, safe_code: str) -> None: self.safe_code = normalize_safe_code(safe_code); super().__init__(self.safe_code)

_MIMES = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".txt": "text/plain"}

def parse_document(stream: BinaryIO, *, extension: str, mime_type: str, limits: ParserLimits = ParserLimits()) -> ParsedDocument:
    extension = extension.lower()
    if extension not in _MIMES: raise ParserError("file_type_not_allowed")
    if mime_type != _MIMES[extension]: raise ParserError("file_type_mismatch")
    stream.seek(0); data = stream.read(limits.max_source_bytes + 1)
    if len(data) > limits.max_source_bytes: raise ParserError("file_too_large")
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"): raise ParserError("file_magic_mismatch")
        return _pdf(data, limits)
    if extension == ".docx":
        if not data.startswith(b"PK\x03\x04"): raise ParserError("file_magic_mismatch")
        return _docx(data, limits)
    if data.startswith((b"%PDF-", b"PK\x03\x04")): raise ParserError("file_magic_mismatch")
    return _txt(data, limits)

def validate_upload_preflight(stream: BinaryIO, *, extension: str, mime_type: str, limits: ParserLimits = ParserLimits()) -> str:
    extension=extension.lower()
    if extension not in _MIMES: raise ParserError("file_type_not_allowed")
    if mime_type!=_MIMES[extension]: raise ParserError("file_type_mismatch")
    stream.seek(0); data=stream.read(limits.max_source_bytes+1); stream.seek(0)
    if not data: raise ParserError("empty_file")
    if len(data)>limits.max_source_bytes: raise ParserError("file_too_large")
    if extension==".pdf" and not data.startswith(b"%PDF-"): raise ParserError("file_magic_mismatch")
    if extension==".docx":
        if not data.startswith(b"PK\x03\x04"): raise ParserError("file_magic_mismatch")
        _docx_preflight(data,limits)
    if extension==".txt":
        if data.startswith((b"%PDF-",b"PK\x03\x04")): raise ParserError("file_magic_mismatch")
        if b"\x00" in data: raise ParserError("binary_text_rejected")
    return extension[1:]

def _docx_preflight(data,limits):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)>limits.docx_max_entries: raise ParserError("docx_entry_limit")
            total=0
            for info in infos:
                parts=info.filename.replace("\\","/").split("/")
                if ".." in parts or info.filename.startswith(("/","\\")): raise ParserError("docx_path_traversal")
                if info.filename.lower().endswith(("vbaproject.bin",".docm",".dotm")): raise ParserError("docx_macro_rejected")
                total+=info.file_size
                if total>limits.docx_max_uncompressed_bytes: raise ParserError("docx_size_limit")
                if info.file_size and info.file_size/max(1,info.compress_size)>limits.docx_max_compression_ratio: raise ParserError("docx_compression_ratio")
    except ParserError: raise
    except zipfile.BadZipFile: raise ParserError("docx_malformed") from None

def _bounded(text: str, limits: ParserLimits) -> str:
    if len(text) > limits.max_text_chars: raise ParserError("text_limit_exceeded")
    return text

def _pdf(data: bytes, limits: ParserLimits) -> ParsedDocument:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted: raise ParserError("pdf_encrypted")
        if len(reader.pages) > limits.pdf_max_pages: raise ParserError("pdf_page_limit")
        text = _bounded("\n".join(page.extract_text() or "" for page in reader.pages), limits)
    except ParserError: raise
    except Exception: raise ParserError("pdf_malformed") from None
    return ParsedDocument(text, "pdf-v1", "good" if text.strip() else "empty")

def _docx(data: bytes, limits: ParserLimits) -> ParsedDocument:
    try:
        _docx_preflight(data,limits)
        from docx import Document
        document = Document(io.BytesIO(data)); text = _bounded("\n".join(paragraph.text for paragraph in document.paragraphs), limits)
    except ParserError: raise
    except (zipfile.BadZipFile, KeyError, ValueError): raise ParserError("docx_malformed") from None
    return ParsedDocument(text, "docx-v1", "good" if text.strip() else "empty")

def _txt(data: bytes, limits: ParserLimits) -> ParsedDocument:
    if b"\x00" in data or (data and sum(byte < 9 or 13 < byte < 32 for byte in data) / len(data) > .02): raise ParserError("binary_text_rejected")
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try: text = data.decode(encoding); break
        except UnicodeDecodeError: continue
    else: raise ParserError("text_encoding_unsupported")
    return ParsedDocument(_bounded(text, limits), "txt-v1", "good" if text.strip() else "empty")
