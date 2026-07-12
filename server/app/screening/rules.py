import re
from dataclasses import dataclass
from collections.abc import Iterable,Mapping

ENGINE_VERSION = "rule-v1"

@dataclass(frozen=True)
class RuleSnapshot:
    jd_text: str
    required_terms: tuple[str,...]|None=None
    bonus_terms: tuple[str,...]|None=None
    @classmethod
    def from_content(cls,jd_text:str,content:object):
        if not isinstance(jd_text,str) or len(jd_text)>500_000: raise RuleSnapshotError
        if not isinstance(content,Mapping) or not set(content)<={"required_terms","bonus_terms"}: raise RuleSnapshotError
        def terms(name):
            value=content.get(name)
            if value is None: return None
            if not isinstance(value,list) or len(value)>50 or any(not isinstance(term,str) or not 1<=len(term.strip())<=100 for term in value): raise RuleSnapshotError
            return tuple(_unique(term.strip() for term in value))
        return cls(jd_text,terms("required_terms"),terms("bonus_terms"))

class RuleSnapshotError(ValueError): pass

@dataclass(frozen=True)
class RuleResult:
    engine_version: str; score: int; recommendation: str
    required_hits: list[str]; required_missing: list[str]; bonus_hits: list[str]
    estimated_years: int; risks: list[str]; questions: list[str]

def score_resume(resume_text: str, snapshot: RuleSnapshot) -> RuleResult:
    required = list(snapshot.required_terms) if snapshot.required_terms is not None else (_extract_terms(snapshot.jd_text, ("必须条件", "硬性要求", "必备条件", "required")) or _top_keywords(snapshot.jd_text))
    bonus = list(snapshot.bonus_terms) if snapshot.bonus_terms is not None else _extract_terms(snapshot.jd_text, ("加分项", "优先", "bonus", "preferred"))
    required_hits = _matched_terms(resume_text, required); bonus_hits = _matched_terms(resume_text, bonus)
    missing = [term for term in required if term not in required_hits]; years = _estimate_years(resume_text)
    score = round((len(required_hits) / len(required) if required else 0) * 75 + (len(bonus_hits) / len(bonus) if bonus else 0) * 15 + min(years, 5) / 5 * 10)
    if missing: score = min(score, 59)
    return RuleResult(ENGINE_VERSION, score, _recommendation(score, bool(missing)), required_hits, missing, bonus_hits, years, [], [])

def _extract_terms(text: str, labels: Iterable[str]) -> list[str]:
    terms = []
    for line in text.splitlines():
        cleaned = line.strip()
        for label in labels:
            match = re.search(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", cleaned, re.IGNORECASE)
            if match: terms.extend(_split_terms(match.group(1)))
    return _unique(terms)

def _split_terms(text: str) -> list[str]:
    return [part.strip(" -\t\r\n") for part in re.split(r"[,，、;/；|]\s*|\s{2,}", text) if part.strip(" -\t\r\n")]

def _top_keywords(text: str) -> list[str]:
    stop = {"岗位", "职责", "要求", "经验", "负责", "熟悉", "相关", "优先"}
    return _unique(token for token in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}|[\u4e00-\u9fff]{2,}", text) if token not in stop)[:12]

def _matched_terms(text: str, terms: Iterable[str]) -> list[str]:
    folded = text.casefold(); return [term for term in terms if term.casefold() in folded]

def _estimate_years(text: str) -> int: return max((int(value) for value in re.findall(r"(?<!\d)(\d{1,2})\s*年", text)), default=0)
def _recommendation(score: int, missing: bool) -> str:
    if missing: return "需人工复核"
    if score >= 85: return "优先沟通"
    if score >= 70: return "可沟通"
    return "暂缓"
def _unique(values: Iterable[str]) -> list[str]:
    seen = set(); result = []
    for value in values:
        key = value.casefold()
        if key not in seen: seen.add(key); result.append(value)
    return result
