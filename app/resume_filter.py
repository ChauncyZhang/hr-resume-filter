from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUPPORTED_SUFFIXES = {".txt", ".md", ".csv", ".pdf", ".docx"}
CSV_COLUMNS = [
    ("file_name", "文件名"),
    ("score", "匹配分"),
    ("recommendation", "推荐结论"),
    ("required_hit_count", "必须条件命中数"),
    ("required_total", "必须条件总数"),
    ("required_missing", "缺失必须条件"),
    ("matched_terms", "命中必须条件"),
    ("bonus_terms", "命中加分项"),
    ("estimated_years", "识别年限"),
]


@dataclass(frozen=True)
class CandidateScore:
    file_name: str
    score: int
    recommendation: str
    required_hit_count: int
    required_total: int
    required_missing: str
    matched_terms: str
    bonus_terms: str
    estimated_years: int


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv"}:
        return _read_text_with_fallback(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    raise ValueError(f"Unsupported resume format: {path.name}")


def score_resume(resume_text: str, jd_text: str, file_name: str) -> CandidateScore:
    required_terms = _extract_terms(jd_text, ("必须条件", "硬性要求", "必备条件", "required"))
    bonus_terms = _extract_terms(jd_text, ("加分项", "优先", "bonus", "preferred"))

    if not required_terms:
        required_terms = _top_keywords(jd_text)

    required_hits = _matched_terms(resume_text, required_terms)
    bonus_hits = _matched_terms(resume_text, bonus_terms)
    missing = [term for term in required_terms if term not in required_hits]
    years = _estimate_years(resume_text)

    required_ratio = len(required_hits) / len(required_terms) if required_terms else 0
    bonus_ratio = len(bonus_hits) / len(bonus_terms) if bonus_terms else 0
    years_score = min(years, 5) / 5
    score = round(required_ratio * 75 + bonus_ratio * 15 + years_score * 10)

    if missing:
        score = min(score, 59)

    return CandidateScore(
        file_name=file_name,
        score=score,
        recommendation=_recommendation(score, bool(missing)),
        required_hit_count=len(required_hits),
        required_total=len(required_terms),
        required_missing=", ".join(missing),
        matched_terms=", ".join(required_hits),
        bonus_terms=", ".join(bonus_hits),
        estimated_years=years,
    )


def run_screening(input_dir: Path, jd_path: Path, output_csv: Path) -> list[CandidateScore]:
    jd_text = _read_text_with_fallback(jd_path)
    resumes = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    rows = []
    for resume in resumes:
        text = extract_text(resume)
        rows.append(score_resume(text, jd_text, resume.name))

    rows.sort(key=lambda row: (-row.score, row.file_name.lower()))
    _write_csv(output_csv, rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Screen authorized resume files against a job description."
    )
    parser.add_argument("--input", required=True, type=Path, help="Directory of resumes.")
    parser.add_argument("--jd", required=True, type=Path, help="Job description text file.")
    parser.add_argument("--output", required=True, type=Path, help="Output CSV path.")
    args = parser.parse_args(argv)

    rows = run_screening(args.input, args.jd, args.output)
    print(f"Screened {len(rows)} resumes. Wrote {args.output}")
    return 0


def _read_text_with_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF parsing requires pypdf: python -m pip install pypdf") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "DOCX parsing requires python-docx: python -m pip install python-docx"
        ) from exc

    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_terms(text: str, labels: Iterable[str]) -> list[str]:
    terms: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*[:：]\s*(.+)$"
            match = re.search(pattern, cleaned, flags=re.IGNORECASE)
            if match:
                terms.extend(_split_terms(match.group(1)))
    return _unique_preserve_order(terms)


def _split_terms(text: str) -> list[str]:
    parts = re.split(r"[,，、;/；|]\s*|\s{2,}", text)
    return [part.strip(" -\t\r\n") for part in parts if part.strip(" -\t\r\n")]


def _top_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[\u4e00-\u9fff]{2,}", text)
    stopwords = {"岗位", "职责", "要求", "经验", "负责", "熟悉", "相关", "优先"}
    return _unique_preserve_order(token for token in tokens if token not in stopwords)[:12]


def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    normalized = text.casefold()
    return [term for term in terms if term.casefold() in normalized]


def _estimate_years(text: str) -> int:
    years = [int(match) for match in re.findall(r"(?<!\d)(\d{1,2})\s*年", text)]
    return max(years, default=0)


def _recommendation(score: int, has_missing_required: bool) -> str:
    if has_missing_required:
        return "需人工复核"
    if score >= 85:
        return "优先沟通"
    if score >= 70:
        return "可沟通"
    return "暂缓"


def _write_csv(path: Path, rows: list[CandidateScore]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[header for _, header in CSV_COLUMNS],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {header: getattr(row, field_name) for field_name, header in CSV_COLUMNS}
            )


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
