from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE = ROOT / "deploy" / "compose.yaml"
PRODUCTION_COMPOSE = ROOT / "deploy" / "compose.production.yaml"
ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
NGINX_TEMPLATE = ROOT / "deploy" / "nginx" / "production.conf.template"
SECURITY_HEADERS = ROOT / "deploy" / "nginx" / "snippets" / "security-headers.conf"
NGINX_IMAGE = "nginx:1.28.0-alpine"

FORBIDDEN_API_ENVIRONMENT = {
    "GOVERNANCE_DATABASE_URL",
    "GOVERNANCE_DELETE_ACCESS_KEY",
    "GOVERNANCE_DELETE_SECRET_KEY",
    "GOVERNANCE_LEDGER_ACCESS_KEY",
    "GOVERNANCE_LEDGER_SECRET_KEY",
    "GOVERNANCE_LEDGER_SIGNING_KEY",
    "GOVERNANCE_STORAGE_ENDPOINT",
}


def _merged_compose(cert_path: Path, key_path: Path) -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "HTTPS_BIND_ADDRESS": "127.0.0.1",
            "HTTPS_PORT": "443",
            "SERVER_NAME": "recruiting.example.test",
            "TLS_CERTIFICATE_PATH": str(cert_path),
            "TLS_PRIVATE_KEY_PATH": str(key_path),
        }
    )
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
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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

    model = _merged_compose(cert_path, key_path)
    proxy = model["services"]["proxy"]
    mounts = {volume["target"]: volume for volume in proxy["volumes"]}

    assert mounts["/etc/nginx/tls/tls.crt"]["source"] == str(cert_path)
    assert mounts["/etc/nginx/tls/tls.key"]["source"] == str(key_path)
    assert mounts["/etc/nginx/tls/tls.crt"]["read_only"] is True
    assert mounts["/etc/nginx/tls/tls.key"]["read_only"] is True
    assert "TLS_PRIVATE_KEY" not in proxy.get("environment", {})
    assert proxy["environment"]["NGINX_ENVSUBST_FILTER"] == "^SERVER_NAME"
    assert FORBIDDEN_API_ENVIRONMENT.isdisjoint(
        model["services"]["api"].get("environment", {})
    )


def test_production_nginx_contract_is_https_only_and_keeps_metrics_private() -> None:
    template = NGINX_TEMPLATE.read_text(encoding="utf-8")
    headers = SECURITY_HEADERS.read_text(encoding="utf-8")

    assert re.findall(r"\$\{([A-Z0-9_]+)\}", template) == ["SERVER_NAME"]
    assert "listen 8443 ssl" in template
    assert "ssl_protocols TLSv1.2 TLSv1.3" in template
    assert "ssl_certificate /etc/nginx/tls/tls.crt" in template
    assert "ssl_certificate_key /etc/nginx/tls/tls.key" in template
    assert "client_max_body_size 10m" in template
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
    openssl = shutil.which("openssl")
    assert openssl is not None, "OpenSSL is required for the disposable TLS syntax gate"

    cert_path = tmp_path / "tls.crt"
    key_path = tmp_path / "tls.key"
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
    rendered = tmp_path / "default.conf"
    rendered.write_text(
        NGINX_TEMPLATE.read_text(encoding="utf-8").replace(
            "${SERVER_NAME}", "recruiting.example.test"
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
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
            NGINX_IMAGE,
            "nginx",
            "-t",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
