from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE = ROOT / "deploy" / "compose.yaml"
PRODUCTION_COMPOSE = ROOT / "deploy" / "compose.production.yaml"
OBSERVABILITY_COMPOSE = ROOT / "deploy" / "compose.observability.yaml"
ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
NGINX_TEMPLATE = ROOT / "deploy" / "nginx" / "production.conf.template"
SECURITY_HEADERS = ROOT / "deploy" / "nginx" / "snippets" / "security-headers.conf"
PRODUCTION_PREFLIGHT = ROOT / "deploy" / "production-preflight.sh"

FORBIDDEN_API_ENVIRONMENT = {
    "GOVERNANCE_DATABASE_URL",
    "GOVERNANCE_DELETE_ACCESS_KEY",
    "GOVERNANCE_DELETE_SECRET_KEY",
    "GOVERNANCE_LEDGER_ACCESS_KEY",
    "GOVERNANCE_LEDGER_SECRET_KEY",
    "GOVERNANCE_LEDGER_SIGNING_KEY",
    "GOVERNANCE_STORAGE_ENDPOINT",
}


def _compose_environment(
    cert_path: Path, key_path: Path, *, server_name: str | None
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "HTTPS_BIND_ADDRESS": "127.0.0.1",
            "HTTPS_PORT": "443",
            "QUEUE_METRICS_DB_PASSWORD": "synthetic-queue-metrics-password",
            "QUEUE_METRICS_DB_USER": "ux09_queue_metrics",
            "POSTGRES_EXPORTER_DB_PASSWORD": "synthetic-postgres-exporter-password",
            "POSTGRES_EXPORTER_DB_USER": "ux09_postgres_exporter",
            "TLS_CERTIFICATE_PATH": str(cert_path),
            "TLS_PRIVATE_KEY_PATH": str(key_path),
        }
    )
    if server_name is None:
        environment.pop("SERVER_NAME", None)
    else:
        environment["SERVER_NAME"] = server_name
    return environment


def _run_compose_config(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
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
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _merged_compose(cert_path: Path, key_path: Path) -> dict:
    environment = _compose_environment(
        cert_path, key_path, server_name="recruiting.example.test"
    )
    result = _run_compose_config(environment)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _generate_certificate(cert_path: Path, key_path: Path) -> None:
    openssl = shutil.which("openssl")
    assert openssl is not None, "OpenSSL is required for the disposable TLS syntax gate"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=recruiting.example.test",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _render_nginx(tmp_path: Path) -> tuple[Path, Path, Path]:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    _generate_certificate(cert_path, key_path)
    rendered = tmp_path / "default.conf"
    rendered.write_text(
        NGINX_TEMPLATE.read_text(encoding="utf-8").replace(
            "${SERVER_NAME}", "recruiting.example.test"
        ),
        encoding="utf-8",
    )
    return rendered, cert_path, key_path


def _nginx_container_arguments(
    image: str, rendered: Path, cert_path: Path, key_path: Path
) -> list[str]:
    return [
        "--add-host",
        "api:127.0.0.1",
        "--mount",
        f"type=bind,source={rendered},target=/etc/nginx/conf.d/default.conf,readonly",
        "--mount",
        f"type=bind,source={SECURITY_HEADERS},target=/etc/nginx/snippets/security-headers.conf,readonly",
        "--mount",
        f"type=bind,source={cert_path},target=/etc/nginx/tls/tls.crt,readonly",
        "--mount",
        f"type=bind,source={key_path},target=/etc/nginx/tls/tls.key,readonly",
        image,
    ]


def test_merged_production_topology_has_one_https_host_entry(tmp_path: Path) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()

    model = _merged_compose(cert_path, key_path)
    published = [
        (service_name, port)
        for service_name, service in model["services"].items()
        for port in service.get("ports", [])
    ]

    assert len(published) == 1
    service_name, port = published[0]
    assert service_name == "proxy"
    assert str(port["published"]) == "443"
    assert port["target"] == 8443
    assert port["protocol"] == "tcp"


def test_merged_production_topology_mounts_tls_files_without_api_privilege_leak(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()

    sentinel = f"phase6a-governance-sentinel-{uuid4().hex}"
    environment = _compose_environment(
        cert_path, key_path, server_name="recruiting.example.test"
    )
    for name in (
        "GOVERNANCE_DATABASE_URL",
        "GOVERNANCE_DB_USER",
        "GOVERNANCE_DB_PASSWORD",
        "GOVERNANCE_DELETE_ACCESS_KEY",
        "GOVERNANCE_DELETE_SECRET_KEY",
        "GOVERNANCE_EXPORT_BUCKET",
        "GOVERNANCE_EXPORT_PREFIX",
        "GOVERNANCE_LEDGER_ACCESS_KEY",
        "GOVERNANCE_LEDGER_BUCKET",
        "GOVERNANCE_LEDGER_PREFIX",
        "GOVERNANCE_LEDGER_SECRET_KEY",
        "GOVERNANCE_LEDGER_SIGNING_KEY",
        "GOVERNANCE_RESUME_BUCKET",
        "GOVERNANCE_RESUME_PREFIX",
        "GOVERNANCE_STORAGE_ENDPOINT",
    ):
        environment[name] = sentinel
    result = _run_compose_config(environment)
    assert result.returncode == 0, result.stderr
    model = json.loads(result.stdout)
    proxy = model["services"]["proxy"]
    mounts = {volume["target"]: volume for volume in proxy["volumes"]}

    assert mounts["/etc/nginx/tls/tls.crt"]["source"] == str(cert_path)
    assert mounts["/etc/nginx/tls/tls.key"]["source"] == str(key_path)
    assert mounts["/etc/nginx/tls/tls.crt"]["read_only"] is True
    assert mounts["/etc/nginx/tls/tls.key"]["read_only"] is True
    assert "TLS_PRIVATE_KEY" not in proxy.get("environment", {})
    assert proxy["environment"]["NGINX_ENVSUBST_FILTER"] == "^SERVER_NAME"
    api_environment = model["services"]["api"].get("environment", {})
    assert FORBIDDEN_API_ENVIRONMENT.isdisjoint(api_environment)
    assert all(sentinel not in str(value) for value in api_environment.values())
    assert model["services"]["api"]["environment"]["APP_ENVIRONMENT"] == "production"
    assert model["services"]["worker"]["environment"]["APP_ENVIRONMENT"] == "production"


def test_production_server_name_is_required(tmp_path: Path) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()

    result = _run_compose_config(
        _compose_environment(cert_path, key_path, server_name=None)
    )

    assert result.returncode != 0
    assert "SERVER_NAME" in result.stderr


def test_production_nginx_contract_is_https_only_and_keeps_metrics_private() -> None:
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")
    headers = SECURITY_HEADERS.read_text(encoding="utf-8")

    assert re.findall(r"\$\{([A-Z0-9_]+)\}", template) == ["SERVER_NAME"]
    assert "listen 8443 ssl" in template
    assert "ssl_protocols TLSv1.2 TLSv1.3" in template
    assert "ssl_certificate /etc/nginx/tls/tls.crt" in template
    assert "ssl_certificate_key /etc/nginx/tls/tls.key" in template
    assert "client_max_body_size 11m" in template
    assert "proxy_pass http://api:8000" in template
    assert "proxy_set_header X-Trace-ID $http_x_trace_id" in template
    assert "try_files $uri $uri/ /index.html" in template
    assert "location = /metrics" in template
    assert "return 404" in template
    assert "Cache-Control \"no-store\"" in template

    required_headers = (
        "Strict-Transport-Security",
        "X-Content-Type-Options \"nosniff\"",
        "X-Frame-Options \"DENY\"",
        "Referrer-Policy \"no-referrer\"",
        "Permissions-Policy",
        "default-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
    for directive in required_headers:
        assert directive in headers


def test_rendered_production_nginx_passes_nginx_t_with_disposable_certificate(
    tmp_path: Path,
) -> None:
    rendered, cert_path, key_path = _render_nginx(tmp_path)
    model = _merged_compose(cert_path, key_path)
    proxy_image = model["services"]["proxy"]["image"]

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            *_nginx_container_arguments(
                proxy_image, rendered, cert_path, key_path
            ),
            "nginx",
            "-t",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_metrics_paths_return_404_from_running_production_nginx(tmp_path: Path) -> None:
    rendered, cert_path, key_path = _render_nginx(tmp_path)
    model = _merged_compose(cert_path, key_path)
    proxy_image = model["services"]["proxy"]["image"]
    started = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-p",
            "127.0.0.1::8443",
            *_nginx_container_arguments(
                proxy_image, rendered, cert_path, key_path
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = started.stdout.strip()
    try:
        port_result = subprocess.run(
            ["docker", "port", container_id, "8443/tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
        host_port = int(port_result.stdout.strip().rsplit(":", 1)[1])
        context = ssl._create_unverified_context()
        for path in ("/metrics", "/metrics/child"):
            status = None
            for _ in range(30):
                try:
                    with urlopen(
                        f"https://127.0.0.1:{host_port}{path}",
                        context=context,
                        timeout=1,
                    ) as response:
                        status = response.status
                except HTTPError as error:
                    status = error.code
                except URLError:
                    time.sleep(0.1)
                    continue
                break
            assert status == 404, path
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            text=True,
            check=False,
        )


def _preflight_environment(cert_path: Path, key_path: Path) -> dict[str, str]:
    environment = _compose_environment(
        cert_path, key_path, server_name="recruiting.example.test"
    )
    environment["COMPOSE_ENV_FILE"] = "deploy/.env.example"
    return environment


def _shell_path(path: Path | str) -> str:
    value = Path(path).resolve().as_posix()
    if len(value) >= 3 and value[1:3] == ":/":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _run_preflight(
    environment: dict[str, str], *, shim_directory: Path | None = None
) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh") or "sh"
    shim = _shell_path(shim_directory) if shim_directory is not None else ""
    return subprocess.run(
        [
            shell,
            "-c",
            'if [ -n "$1" ]; then PATH="$1:$PATH"; export PATH; fi; '
            "exec sh deploy/production-preflight.sh",
            "phase6a-preflight",
            shim,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_docker_version_shim(tmp_path: Path) -> Path:
    shim = tmp_path / "docker"
    shim.write_text(
        """#!/bin/sh
if [ "$1" = compose ] && [ "$2" = version ] && [ "$3" = --short ]; then
    printf '%s\\n' "$FAKE_COMPOSE_VERSION"
    exit 0
fi
if [ -n "${CONFIG_CALL_MARKER:-}" ]; then
    printf '%s\\n' "$*" > "$CONFIG_CALL_MARKER"
fi
if [ "${ALLOW_REAL_DOCKER:-0}" = 1 ]; then
    exec "$REAL_DOCKER" "$@"
fi
printf '%s\\n' unexpected-compose-config-call > "$UNEXPECTED_CALL_MARKER"
exit 91
""",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return shim


def test_preflight_rejects_compose_older_than_minimum_before_config(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()
    _write_docker_version_shim(tmp_path)
    marker = tmp_path / "unexpected-call"
    environment = _preflight_environment(cert_path, key_path)
    environment.update(
        {
            "FAKE_COMPOSE_VERSION": "2.24.3",
            "UNEXPECTED_CALL_MARKER": _shell_path(marker),
        }
    )

    result = _run_preflight(environment, shim_directory=tmp_path)

    assert result.returncode != 0
    assert "2.24.4" in result.stderr
    assert not marker.exists()


def test_preflight_accepts_minimum_version_and_validates_merged_model(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()
    _write_docker_version_shim(tmp_path)
    real_docker = shutil.which("docker")
    assert real_docker is not None
    config_call = tmp_path / "config-call"
    environment = _preflight_environment(cert_path, key_path)
    environment.update(
        {
            "ALLOW_REAL_DOCKER": "1",
            "CONFIG_CALL_MARKER": _shell_path(config_call),
            "FAKE_COMPOSE_VERSION": "2.24.4",
            "REAL_DOCKER": _shell_path(real_docker),
        }
    )

    result = _run_preflight(environment, shim_directory=tmp_path)

    assert result.returncode == 0, result.stderr
    invoked = config_call.read_text(encoding="utf-8")
    assert "deploy/compose.yaml" in invoked.replace("\\", "/")
    assert "deploy/compose.production.yaml" in invoked.replace("\\", "/")


def test_preflight_accepts_installed_compose_and_validates_merged_model(
    tmp_path: Path,
) -> None:
    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
    cert_path.touch()
    key_path.touch()

    result = _run_preflight(_preflight_environment(cert_path, key_path))

    assert result.returncode == 0, result.stderr
