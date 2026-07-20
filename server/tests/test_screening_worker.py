import uuid

import pytest

from server.app.core.settings import Settings
from server.app.queue.payloads import DEFAULT_PAYLOAD_POLICIES, UnsafePayload
from server.app.worker.main import build_screening_handlers

def test_production_screening_registry_is_allowlisted_and_scanner_settings_are_bounded():
    settings=Settings(clamav_host="clamav",clamav_port=3310,clamav_connect_timeout_seconds=1,clamav_read_timeout_seconds=3,clamav_total_timeout_seconds=4)
    handlers=build_screening_handlers(settings,object(),object())
    assert set(handlers)=={"screening.parse_item","screening.score_item","screening.llm_score_item","reports.export"}
    assert settings.clamav_total_timeout_seconds>=settings.clamav_read_timeout_seconds


def test_llm_queue_payload_accepts_application_id_without_business_facts():
    opaque_ids = {name: str(uuid.uuid4()) for name in (
        "organization_id",
        "screening_item_id",
        "screening_result_id",
        "application_id",
        "config_id",
        "prompt_version_id",
    )}
    payload = {**opaque_ids, "config_version": 3}

    assert DEFAULT_PAYLOAD_POLICIES.validate_job("screening.llm_score_item", payload) == payload
    for forbidden in ("required_hits", "required_missing", "bonus_hits", "rule_score", "rule_recommendation"):
        with pytest.raises(UnsafePayload):
            DEFAULT_PAYLOAD_POLICIES.validate_job(
                "screening.llm_score_item",
                {**payload, forbidden: "private-rule-fact"},
            )
