from server.app.core.settings import Settings
from server.app.worker.main import build_screening_handlers

def test_production_screening_registry_is_allowlisted_and_scanner_settings_are_bounded():
    settings=Settings(clamav_host="clamav",clamav_port=3310,clamav_connect_timeout_seconds=1,clamav_read_timeout_seconds=3,clamav_total_timeout_seconds=4)
    handlers=build_screening_handlers(settings,object(),object())
    assert set(handlers)=={"screening.parse_item","screening.score_item"}
    assert settings.clamav_total_timeout_seconds>=settings.clamav_read_timeout_seconds
