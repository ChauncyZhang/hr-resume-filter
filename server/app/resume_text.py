import re
from collections import Counter


_OBFUSCATION_MARKER = re.compile(r"[0-9a-f]{12,24}[A-Za-z0-9_-]{18,100}")


def sanitize_resume_text(text: str) -> str:
    """Remove repeated standalone PDF text-layer markers without touching resume content."""
    lines = (text or "").splitlines()
    candidates = [line.strip() for line in lines if _OBFUSCATION_MARKER.fullmatch(line.strip())]
    repeated = {value for value, count in Counter(candidates).items() if count >= 2}
    if not repeated:
        return text
    return "\n".join(line for line in lines if line.strip() not in repeated)
