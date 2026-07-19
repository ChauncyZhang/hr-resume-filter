import asyncio
import json
import time

import pytest
from pydantic import ValidationError

from server.app.llm.gateway import GatewayError, OpenAiCompatibleGateway, TransportResponse
from server.app.llm.policy import ProviderAllowlist
from server.app.llm.redaction import redact_screening_text
from server.app.llm.screening import (
    MAX_JD_CHARS,
    MAX_RESUME_CHARS,
    ScreeningRequest,
    ScreeningResult,
)


def resolver(host, port, type):
    return [(2, 1, 6, "", ("8.8.8.8", port))]


class Transport:
    def __init__(self, body, status=200):
        self.body = body; self.status=status
        self.calls = []

    def post(self, spec, address, path, headers, body, max_response_bytes):
        self.calls.append((spec, address, path, headers, body, max_response_bytes))
        return TransportResponse(self.status, self.body)


class SlowTransport(Transport):
    def __init__(self, body, delay):
        super().__init__(body)
        self.delay = delay

    def post(self, *args, **kwargs):
        time.sleep(self.delay)
        return super().post(*args, **kwargs)


def request(**changes):
    values = {
        "jd": "Python backend role",
        "resume": "Built Python services",
        "rule_facts": ["Python required: hit"],
    }
    values.update(changes)
    return ScreeningRequest(**values)


def provider_body(content, usage=None):
    document = {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}
    if usage is not None:
        document["usage"] = usage
    return json.dumps(document, ensure_ascii=False).encode()


def valid_result(**changes):
    value = {
        "score": 88,
        "recommendation": "优先沟通",
        "summary": "经验与职位较匹配",
        "strengths": ["Python"],
        "gaps": [],
        "risks": ["需确认到岗时间"],
        "questions": ["请说明高并发项目经验"],
    }
    value.update(changes)
    return value


def gateway(transport, **changes):
    policy = ProviderAllowlist(
        {"provider": {"base_url": "https://provider.example/v1", "models": ["model"]}},
        resolver=resolver,
    )
    return OpenAiCompatibleGateway(policy, transport, **changes)


def test_redaction_is_deterministic_and_removes_direct_identifiers():
    source = """姓名: 张三
Name: Jane Doe
邮箱: jane@example.com
Phone: +86 138-0013-8000
地址：上海市浦东新区
经历: Jane Doe 在 ACME 工作，备用电话 021-61234567。"""

    first = redact_screening_text(source, candidate_name="Jane Doe")

    assert first == redact_screening_text(source, candidate_name="Jane Doe")
    assert all(value not in first for value in ("张三", "Jane Doe", "jane@example.com", "138-0013-8000", "021-61234567", "上海市浦东新区"))
    assert "经历:" in first and "ACME" in first


def test_screening_request_bounds_all_provider_inputs():
    assert len(request(jd="j" * MAX_JD_CHARS).jd) == MAX_JD_CHARS
    assert len(request(resume="r" * MAX_RESUME_CHARS).resume) == MAX_RESUME_CHARS

    for changes in (
        {"jd": "j" * (MAX_JD_CHARS + 1)},
        {"resume": "r" * (MAX_RESUME_CHARS + 1)},
        {"rule_facts": ["x"] * 21},
        {"rule_facts": ["x" * 501]},
    ):
        with pytest.raises(ValidationError):
            request(**changes)


def test_redaction_cannot_expand_input_or_output_past_contract_bounds():
    with pytest.raises(ValidationError):
        request(resume="r"*(MAX_RESUME_CHARS-len(" a@b.co"))+" a@b.co")
    with pytest.raises(ValidationError):
        ScreeningResult.model_validate(valid_result(summary="x"*(1000-len(" a@b.co"))+" a@b.co"))


def test_screening_request_redacts_before_provider_serialization():
    screening_request = request(
        jd="Contact: hiring@example.test",
        resume="姓名: 张三\n张三 13800138000\nPython services",
        candidate_name="张三",
        rule_facts=["联系邮箱 reviewer@example.test", "张三 required hit"],
    )

    rendered = screening_request.provider_content()

    assert all(value not in rendered for value in ("hiring@example.test", "reviewer@example.test", "张三", "13800138000", "candidate_name"))
    assert "Python services" in rendered


@pytest.mark.parametrize("recommendation", ["优先沟通", "可沟通", "暂缓", "需人工复核"])
def test_screening_result_is_strict_and_bounded(recommendation):
    assert ScreeningResult.model_validate(valid_result(recommendation=recommendation)).recommendation == recommendation

    invalid = (
        valid_result(score=101),
        valid_result(recommendation="录用"),
        valid_result(summary="x" * 1001),
        valid_result(strengths=["x"] * 11),
        valid_result(questions=["x" * 501]),
        {**valid_result(), "reasoning": "private chain of thought"},
    )
    for value in invalid:
        with pytest.raises(ValidationError):
            ScreeningResult.model_validate(value)


def test_gateway_evaluate_reuses_pinned_transport_and_returns_bounded_facts():
    transport = Transport(provider_body(valid_result(), {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}))

    evaluation = asyncio.run(gateway(transport).evaluate("provider", "model", "sk-secret", request()))

    assert evaluation.result.score == 88 and evaluation.latency_ms >= 0
    assert evaluation.usage == {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}
    _, address, path, headers, body, _ = transport.calls[0]
    assert address == "8.8.8.8" and path == "/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-secret"
    payload = json.loads(body)
    assert payload["response_format"] == {"type": "json_object"}
    assert "Python backend role" in payload["messages"][1]["content"]
    assert payload["max_tokens"] == 800


def test_gateway_evaluation_has_a_longer_budget_than_the_connection_probe():
    transport = SlowTransport(provider_body(valid_result()), delay=0.03)

    evaluation = asyncio.run(gateway(
        transport,
        total_timeout=0.01,
        evaluation_total_timeout=0.1,
    ).evaluate("provider", "model", "sk-secret", request()))

    assert evaluation.result.score == 88


def test_gateway_disables_default_thinking_for_official_glm_models():
    transport = Transport(provider_body(valid_result()))
    policy = ProviderAllowlist(
        {"zai": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-5.2"]}},
        resolver=resolver,
    )

    asyncio.run(OpenAiCompatibleGateway(policy, transport).evaluate("zai", "glm-5.2", "sk-secret", request()))

    payload = json.loads(transport.calls[0][4])
    assert payload["thinking"] == {"type": "disabled"}


def test_gateway_evaluate_redacts_identifiers_echoed_by_provider():
    echoed=valid_result(summary="联系 jane@example.test 或 13800138000",questions=["地址: 上海市浦东新区"])
    evaluation=asyncio.run(gateway(Transport(provider_body(echoed))).evaluate("provider","model","secret",request()))
    rendered=evaluation.result.model_dump_json()
    assert all(value not in rendered for value in ("jane@example.test","13800138000","上海市浦东新区"))


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"not-json", "provider_response_invalid"),
        (provider_body({**valid_result(), "unknown": True}), "provider_response_invalid"),
        (provider_body(valid_result(), {"total_tokens": "many"}), "provider_response_invalid"),
    ],
)
def test_gateway_evaluate_maps_malformed_output_to_safe_error(body, code):
    with pytest.raises(GatewayError) as raised:
        asyncio.run(gateway(Transport(body)).evaluate("provider", "model", "secret", request()))
    assert raised.value.safe_code == code and str(raised.value) == code


def test_gateway_evaluate_maps_oversize_response_to_safe_error():
    with pytest.raises(GatewayError) as raised:
        asyncio.run(gateway(Transport(b"x" * 101), max_response_bytes=100).evaluate("provider", "model", "secret", request()))
    assert raised.value.safe_code == "provider_response_too_large"


@pytest.mark.parametrize("status",[400,422])
def test_gateway_evaluate_treats_rejected_requests_as_permanent(status):
    with pytest.raises(GatewayError,match="provider_request_rejected") as raised:
        asyncio.run(gateway(Transport(b"private provider body",status)).evaluate("provider","model","secret",request()))
    assert raised.value.safe_code=="provider_request_rejected" and "private provider body" not in str(raised.value)
