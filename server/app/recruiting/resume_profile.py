import re
from collections.abc import Iterable

from server.app.resume_text import sanitize_resume_text


_SECTION_ALIASES = {
    "summary": ("个人简介", "个人总结", "自我评价", "职业概述", "profile", "summary", "aboutme"),
    "skills": ("技能", "专业技能", "核心技能", "技术栈", "技能清单", "skills", "technicalskills"),
    "experience": ("工作经历", "工作经验", "任职经历", "项目经历", "professionalexperience", "workexperience", "experience"),
    "education": ("教育经历", "教育背景", "学历信息", "education", "academicbackground"),
}
_HEADING_LOOKUP = {
    re.sub(r"[\s:：_-]+", "", alias).casefold(): section
    for section, aliases in _SECTION_ALIASES.items()
    for alias in aliases
}
_CONTACT_PATTERN = re.compile(r"(?:\b1[3-9]\d{9}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})")
_BULLET_PATTERN = re.compile(r"^[\s\-•·▪●○◆◇►▸*]+")
_SKILL_PREFIX = re.compile(r"^(?:熟练(?:掌握|使用)?|掌握|熟悉|了解|擅长|技能|技术栈)\s*[:：]?\s*", re.I)
_NON_SKILL_LABELS = {"工具", "技术工具", "软件工具"}
_CJK_COMPACT_TERMS = (
    "平台产品经理", "产品经理", "项目经理", "技术负责人", "智能制造",
    "软件工程师", "算法工程师", "前端工程师", "后端工程师", "大模型工程师",
)
_KNOWN_SKILLS = (
    "Python", "Java", "C++", "C#", "Golang", "Go", "JavaScript", "TypeScript", "React", "Vue",
    "PyTorch", "TensorFlow", "Transformers", "HuggingFace", "FastAPI", "Django", "Flask", "Spring Boot",
    "RAG", "Agent", "LangChain", "LlamaIndex", "LLM", "NLP", "Embedding", "Prompt Engineering", "MCP",
    "OpenAI", "Claude", "DeepSeek", "Llama", "SFT", "RLHF", "LoRA", "Docker", "Kubernetes", "K8s",
    "Linux", "SQL", "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch", "Kafka", "Spark",
    "AWS", "Azure", "GCP",
)


def _clean_line(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", _BULLET_PATTERN.sub("", value)).strip()
    for term in _CJK_COMPACT_TERMS:
        cleaned = re.sub(r"\s*".join(map(re.escape, term)), term, cleaned)
    return cleaned


def _section_heading(line: str) -> tuple[str | None, str]:
    for separator in ("：", ":"):
        if separator in line:
            heading, remainder = line.split(separator, 1)
            key = re.sub(r"[\s_-]+", "", heading).casefold()
            if key in _HEADING_LOOKUP:
                return _HEADING_LOOKUP[key], _clean_line(remainder)
    key = re.sub(r"[\s:：_-]+", "", line).casefold()
    return (_HEADING_LOOKUP.get(key), "")


def _join_lines(lines: Iterable[str], *, limit: int) -> str | None:
    values: list[str] = []
    for line in lines:
        for segment in re.split(r"[；;]", line):
            value = segment.strip()
            compact = re.sub(r"\s+", "", value).casefold()
            if not value or _CONTACT_PATTERN.search(value) or "website:" in compact or "website：" in compact or "www." in compact:
                continue
            values.append(value)
    if not values:
        return None
    return "；".join(values)[:limit].rstrip("；")


def _deduplicate(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        canonical = value.casefold()
        if canonical in seen:
            continue
        seen.add(canonical)
        result.append(value)
    return result


def _skills_from_sections(lines: list[str], full_text: str) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        cleaned = _SKILL_PREFIX.sub("", line)
        for token in re.split(r"[、,，;；/|]+", cleaned):
            value = token.strip(" .。()（）")
            compact = re.sub(r"\s+", "", value).casefold()
            normalized = next((skill for skill in _KNOWN_SKILLS if re.sub(r"\s+", "", skill).casefold() == compact), value)
            if normalized and normalized not in _NON_SKILL_LABELS and len(normalized) <= 40 and not _CONTACT_PATTERN.search(normalized):
                tokens.append(normalized)
    if not tokens:
        for skill in _KNOWN_SKILLS:
            if re.search(rf"(?<![A-Za-z0-9+#]){re.escape(skill)}(?![A-Za-z0-9+#])", full_text, re.I):
                tokens.append(skill)
    return _deduplicate(tokens)[:20]


def extract_resume_profile(text: str) -> dict[str, object]:
    """Extract display-safe profile fields from parsed resume text without returning raw text."""
    text = sanitize_resume_text(text)
    sections: dict[str, list[str]] = {name: [] for name in _SECTION_ALIASES}
    current: str | None = None
    cleaned_lines: list[str] = []
    for raw_line in (text or "").splitlines():
        line = _clean_line(raw_line)
        if not line:
            continue
        cleaned_lines.append(line)
        heading, remainder = _section_heading(line)
        if heading:
            current = heading
            if remainder:
                sections[current].append(remainder)
            continue
        if current:
            sections[current].append(line)

    full_text = "\n".join(cleaned_lines)
    experience = _join_lines(sections["experience"][:8], limit=600)
    summary = _join_lines(sections["summary"][:3], limit=320) or _join_lines(sections["experience"][:2], limit=320)
    education = _join_lines(sections["education"][:5], limit=400)
    skills = _skills_from_sections(sections["skills"], full_text)
    populated = sum((bool(summary), bool(skills), bool(experience), bool(education)))
    status = "ready" if populated == 4 else "partial" if populated else "unavailable"
    return {
        "summary": summary,
        "skills": skills,
        "experience": experience,
        "education": education,
        "status": status,
    }
