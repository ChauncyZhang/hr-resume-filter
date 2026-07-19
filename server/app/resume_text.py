import re
from collections import Counter


_OBFUSCATION_MARKER = re.compile(r"[0-9a-f]{12,24}[A-Za-z0-9_-]{18,100}")


def is_obfuscation_marker(value: str) -> bool:
    return _OBFUSCATION_MARKER.fullmatch(value.strip()) is not None


def normalize_resume_line(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    spaced_cjk = re.findall(r"(?=[\u3400-\u9fff]\s+[\u3400-\u9fff，。；：！？、（）])", cleaned)
    if len(spaced_cjk) >= 3:
        cleaned = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff，。；：！？、（）])", "", cleaned)
        cleaned = re.sub(r"(?<=[，。；：！？、（])\s+(?=[\u3400-\u9fff])", "", cleaned)
    if len(re.findall(r"(?=\d\s+\d)", cleaned)) >= 2:
        cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
        cleaned = re.sub(r"(?<=\d)\s*([./-])\s*(?=\d)", r"\1", cleaned)
    cleaned = re.sub(r"\s*/\s*", "/", cleaned)
    cleaned = re.sub(r"\s+([，。；：！？、,.!?;）)])", r"\1", cleaned)
    cleaned = re.sub(r"([（(])\s+", r"\1", cleaned)
    return cleaned


def sanitize_resume_text(text: str) -> str:
    """Remove repeated standalone PDF text-layer markers without touching resume content."""
    lines = (text or "").splitlines()
    candidates = [line.strip() for line in lines if is_obfuscation_marker(line)]
    repeated = {value for value, count in Counter(candidates).items() if count >= 2}
    if not repeated:
        return text
    return "\n".join(line for line in lines if line.strip() not in repeated)
