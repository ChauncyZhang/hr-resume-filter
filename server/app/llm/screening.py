import json
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.app.llm.redaction import redact_screening_text


MAX_JD_CHARS = 12_000
MAX_RESUME_CHARS = 30_000
MAX_RULE_FACTS = 20
MAX_FACT_CHARS = 500
MAX_SUMMARY_CHARS = 1_000
MAX_LIST_ITEMS = 10
MAX_ITEM_CHARS = 500

SCREENING_SYSTEM_PROMPT = """You are an assistant for recruiter review. Evaluate only the supplied redacted job description, redacted resume, and rule facts. Return one JSON object with exactly these fields: score, recommendation, summary, strengths, gaps, risks, questions. score is an integer from 0 to 100. recommendation is one of 优先沟通, 可沟通, 暂缓, 需人工复核. Do not infer identity or protected traits."""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


RuleFact = Annotated[str, Field(min_length=1, max_length=MAX_FACT_CHARS)]
ResultItem = Annotated[str, Field(min_length=1, max_length=MAX_ITEM_CHARS)]


class ScreeningRequest(ContractModel):
    jd: str = Field(min_length=1, max_length=MAX_JD_CHARS)
    resume: str = Field(min_length=1, max_length=MAX_RESUME_CHARS)
    rule_facts: list[RuleFact] = Field(default_factory=list, max_length=MAX_RULE_FACTS)
    candidate_name: str | None = Field(default=None, min_length=1, max_length=200, exclude=True, repr=False)

    @model_validator(mode="after")
    def redact_inputs(self):
        self.jd = redact_screening_text(self.jd)
        self.resume = redact_screening_text(self.resume, candidate_name=self.candidate_name)
        self.rule_facts = [redact_screening_text(value, candidate_name=self.candidate_name) for value in self.rule_facts]
        if len(self.jd)>MAX_JD_CHARS or len(self.resume)>MAX_RESUME_CHARS or any(len(value)>MAX_FACT_CHARS for value in self.rule_facts): raise ValueError("redacted screening input exceeds bounds")
        return self

    def provider_content(self) -> str:
        return json.dumps(
            {"jd": self.jd, "resume": self.resume, "rule_facts": self.rule_facts},
            ensure_ascii=False,
            separators=(",", ":"),
        )


class ScreeningResult(ContractModel):
    score: int = Field(ge=0, le=100)
    recommendation: Literal["优先沟通", "可沟通", "暂缓", "需人工复核"]
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_CHARS)
    strengths: list[ResultItem] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    gaps: list[ResultItem] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    risks: list[ResultItem] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)
    questions: list[ResultItem] = Field(default_factory=list, max_length=MAX_LIST_ITEMS)

    @model_validator(mode="after")
    def redact_output(self):
        self.summary = redact_screening_text(self.summary)
        for field in ("strengths", "gaps", "risks", "questions"):
            setattr(self, field, [redact_screening_text(value) for value in getattr(self, field)])
        if len(self.summary)>MAX_SUMMARY_CHARS or any(len(value)>MAX_ITEM_CHARS for field in ("strengths","gaps","risks","questions") for value in getattr(self,field)): raise ValueError("redacted screening output exceeds bounds")
        return self


@dataclass(frozen=True)
class ScreeningEvaluation:
    result: ScreeningResult
    latency_ms: int
    usage: dict[str, int]
