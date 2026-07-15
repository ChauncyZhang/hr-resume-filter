from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE = ROOT / "deploy" / "compose.yaml"
PRODUCTION_COMPOSE = ROOT / "deploy" / "compose.production.yaml"
OBSERVABILITY_COMPOSE = ROOT / "deploy" / "compose.observability.yaml"
ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
PROMETHEUS_CONFIG = ROOT / "deploy" / "observability" / "prometheus.yml"
ALERT_RULES = ROOT / "deploy" / "observability" / "alerts" / "ux09.rules.yml"
ALERTMANAGER_CONFIG = ROOT / "deploy" / "observability" / "alertmanager.yml"


def _compose_environment(tmp_path: Path) -> dict[str, str]:
    cert = tmp_path / "tls.crt"
    key = tmp_path / "tls.key"
    cert.touch()
    key.touch()
    environment = os.environ.copy()
    environment.update(
        {
            "HTTPS_BIND_ADDRESS": "127.0.0.1",
            "HTTPS_PORT": "443",
            "SERVER_NAME": "recruiting.example.test",
            "TLS_CERTIFICATE_PATH": str(cert),
            "TLS_PRIVATE_KEY_PATH": str(key),
            "OBSERVABILITY_DB_USER": "ux09_observer",
            "OBSERVABILITY_DB_PASSWORD": "synthetic-observer-password",
        }
    )
    return environment


def _merged_model(tmp_path: Path) -> dict:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ENV_EXAMPLE),
            "-f",
            str(BASE_COMPOSE),
            "-f",
            str(PRODUCTION_COMPOSE),
            "-f",
            str(OBSERVABILITY_COMPOSE),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=_compose_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_three_compose_files_publish_only_the_https_proxy(tmp_path: Path) -> None:
    model = _merged_model(tmp_path)
    published = [
        (name, port)
        for name, service in model["services"].items()
        for port in service.get("ports", [])
    ]

    assert len(published) == 1
    assert published[0][0] == "proxy"
    assert published[0][1]["target"] == 8443
    for name in (
        "prometheus",
        "alertmanager",
        "queue-exporter",
        "node-exporter",
        "cadvisor",
        "postgres-exporter",
    ):
        assert model["services"][name].get("ports", []) == []
        assert "private" in model["services"][name]["networks"]


def test_prometheus_scrapes_only_private_service_targets() -> None:
    config = PROMETHEUS_CONFIG.read_text(encoding="utf-8")

    for target in (
        "api:8000",
        "queue-exporter:9108",
        "node-exporter:9100",
        "cadvisor:8080",
        "postgres-exporter:9187",
        "minio:9000",
    ):
        assert target in config
    assert "localhost" not in config
    assert "host.docker.internal" not in config


def test_real_prometheus_and_alertmanager_images_load_configuration() -> None:
    prometheus = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/promtool",
            "-v",
            f"{PROMETHEUS_CONFIG}:/etc/prometheus/prometheus.yml:ro",
            "-v",
            f"{ALERT_RULES}:/etc/prometheus/rules/ux09.rules.yml:ro",
            "prom/prometheus:v3.5.0",
            "check",
            "config",
            "/etc/prometheus/prometheus.yml",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert prometheus.returncode == 0, prometheus.stdout + prometheus.stderr

    alertmanager = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/amtool",
            "-v",
            f"{ALERTMANAGER_CONFIG}:/etc/alertmanager/alertmanager.yml:ro",
            "prom/alertmanager:v0.28.1",
            "check-config",
            "/etc/alertmanager/alertmanager.yml",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert alertmanager.returncode == 0, alertmanager.stdout + alertmanager.stderr


def test_alerts_have_durations_runbooks_and_no_governance_contract() -> None:
    rules = ALERT_RULES.read_text(encoding="utf-8")

    assert rules.count("for:") >= 12
    assert rules.count("runbook_url:") >= 12
    for required in (
        "ApiHigh5xxRate",
        "ApiHighLatency",
        "QueueOldestReadyTooOld",
        "QueueExpiredLeases",
        "QueueDeadLetters",
        "ParseFailureRateHigh",
        "LlmFailureRateHigh",
        "HostStorageLow",
        "PostgresConnectionsHigh",
        "BackupStale",
    ):
        assert required in rules
    assert "governance" not in rules.lower()


def test_promtool_triggers_and_resolves_representative_alerts(tmp_path: Path) -> None:
    rule_test = tmp_path / "rules-test.yml"
    rule_test.write_text(
        """
rule_files:
  - /etc/prometheus/rules/ux09.rules.yml
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'ux09_expired_leases{queue="job"}'
        values: '1x20 0x20'
    alert_rule_test:
      - eval_time: 15m
        alertname: QueueExpiredLeases
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: Queue leases remain expired
              runbook_url: runbook.md#queueexpiredleases
      - eval_time: 30m
        alertname: QueueExpiredLeases
        exp_alerts: []
  - interval: 1m
    input_series:
      - series: 'ux09_job_dead_letters{job_type="screening.parse_item",organization="alice.canary@example.test"}'
        values: '1x15 0x15'
    alert_rule_test:
      - eval_time: 10m
        alertname: QueueDeadLetters
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: Dead-letter jobs require operator review
              runbook_url: runbook.md#queuedeadletters
      - eval_time: 25m
        alertname: QueueDeadLetters
        exp_alerts: []
  - interval: 1m
    input_series:
      - series: 'ux09_readiness_checks_total{dependency="database",result="failed"}'
        values: '0+60x10 600+0x20'
    alert_rule_test:
      - eval_time: 10m
        alertname: ApiReadinessFailure
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: A required API dependency is failing readiness checks
              runbook_url: runbook.md#apireadinessfailure
      - eval_time: 25m
        alertname: ApiReadinessFailure
        exp_alerts: []
  - interval: 1m
    input_series:
      - series: 'node_filesystem_avail_bytes{device="disk",fstype="ext4",mountpoint="/data"}'
        values: '10x20 50x20'
      - series: 'node_filesystem_size_bytes{device="disk",fstype="ext4",mountpoint="/data"}'
        values: '100x40'
    alert_rule_test:
      - eval_time: 16m
        alertname: HostStorageLowWarning
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: Host filesystem free capacity is below 20 percent
              runbook_url: runbook.md#hoststoragelowwarning
      - eval_time: 30m
        alertname: HostStorageLowWarning
        exp_alerts: []
  - interval: 1m
    input_series:
      - series: 'ux09_backup_last_success_timestamp_seconds'
        values: '-200000x40 2400x20'
    alert_rule_test:
      - eval_time: 35m
        alertname: BackupStaleWarning
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: Backup evidence is missing or older than 26 hours
              runbook_url: runbook.md#backupstalewarning
      - eval_time: 50m
        alertname: BackupStaleWarning
        exp_alerts: []
  - interval: 1m
    input_series:
      - series: 'ux09_job_attempts_total{job_type="screening.parse_item",result="failed",error_class="parse"}'
        values: '0+60x40 2400+0x30'
    alert_rule_test:
      - eval_time: 30m
        alertname: ParseFailureRateHigh
        exp_alerts:
          - exp_labels: {severity: warning}
            exp_annotations:
              summary: Resume parse failure ratio is above 10 percent
              runbook_url: runbook.md#parsefailureratehigh
      - eval_time: 60m
        alertname: ParseFailureRateHigh
        exp_alerts: []
""".lstrip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/promtool",
            "-v",
            f"{ALERT_RULES}:/etc/prometheus/rules/ux09.rules.yml:ro",
            "-v",
            f"{rule_test}:/tmp/rules-test.yml:ro",
            "prom/prometheus:v3.5.0",
            "test",
            "rules",
            "/tmp/rules-test.yml",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
